# globalPlugins/webAccess/overlay.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (https://accessolutions.fr)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# See the file COPYING.txt at the root of this distribution for more details.

"""
WebAccess overlay classes
"""


__authors__ = (
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


import weakref
import wx

import NVDAObjects
from NVDAObjects.IAccessible import IAccessible
import addonHandler
import baseObject
import browseMode
import config
import controlTypes
import core
import cursorManager
from garbageHandler import TrackedObject
import gui
from logHandler import log
from scriptHandler import script
import speech
import textInfos
import treeInterceptorHandler
import ui
import virtualBuffers

from .utils import guarded, logException, tryInt



REASON_CARET = controlTypes.OutputReason.CARET

addonHandler.initTranslation()


SCRCAT_WEBACCESS = "WebAccess"


def getDynamicClass(bases):
	if not isinstance(bases, tuple):
		bases = tuple(bases)
	cache = NVDAObjects.DynamicNVDAObjectType._dynamicClassCache
	dynCls = cache.get(bases)
	if not dynCls:
		name = "Dynamic_%s" % "".join([x.__name__ for x in bases])
		dynCls = type(name, bases, {})
		cache[bases] = dynCls
	return dynCls


def mutateObj(obj, clsList):
	# Determine the bases for the new class.
	bases = []
	for index in range(len(clsList)):
		# A class doesn't need to be a base if it is already implicitly included
		# by being a superclass of a previous base.
		if index == 0 or not issubclass(clsList[index - 1], clsList[index]):
			bases.append(clsList[index])
	newCls = getDynamicClass(bases)
	oldMro = frozenset(obj.__class__.__mro__)
	# Mutate obj into the new class.
	obj.__class__ = newCls
	# Initialise the overlay classes.
	for cls in reversed(newCls.__mro__):
		if cls in oldMro:
			# This class was part of the initially constructed object,
			# so its constructor would have been called.
			continue
		initFunc = cls.__dict__.get("initOverlayClass")
		if initFunc:
			initFunc(obj)
		# Bind gestures specified on the class.
		try:
			obj.bindGestures(getattr(cls, "_%s__gestures" % cls.__name__))
		except AttributeError:
			pass


class ScriptWrapper(object):
	"""
	Wrap a script to help controlling its metadata or its execution.
	"""
	def __init__(self, script, override=None, arg="script", **defaults):
		self.script = script
		self.override = override
		self.arg = arg
		self.defaults = defaults

	def __getattribute__(self, name):
		# Pass existing wrapped script attributes such as __doc__, __name__,
		# category, ignoreTreeInterceptorPassThrough or resumeSayAllMode.
		# Note: scriptHandler.executeScript looks at script.__func__ to
		# prevent recursion.
		if name not in ("__class__", "script", "override", "defaults"):
			if self.override:
				try:
					return getattr(self.override, name)
				except AttributeError:
					pass
			try:
				return getattr(self.script, name)
			except AttributeError:
				pass
			try:
				return self.defaults[name]
			except KeyError:
				pass
		return object.__getattribute__(self, name)

	def __call__(self, gesture, **kwargs):
		if self.override:
			# Throws `TypeError` on purpose if `arg` is already in `kwargs`
			return self.override(gesture, **kwargs, **{self.arg: self.script})
		return self.script(gesture, **kwargs)


class WebAccessBmdtiHelper(TrackedObject):
	"""
	Utility methods and properties.
	"""
	WALK_ALL_TREES = False
	
	def __init__(self, treeInterceptor):
		self.caretHitZoneBorder = False
		self._nodeManager = None
		self._treeInterceptor = weakref.ref(treeInterceptor)
		self._rootWebModule = None
	
	def terminate(self):
		if self._rootWebModule is not None:
			self._rootWebModule.terminate()
		self._rootWebModule = None
		if self._nodeManager is not None:
			self._nodeManager.terminate()
		self._nodeManager = None
	
	@property
	@logException
	def nodeManager(self):
		nodeManager = self._nodeManager
		ti = self.treeInterceptor
		if not ti:
			self._nodeManager = None
			return None
		if (not nodeManager and (self.WALK_ALL_TREES or ti.webAccess.webModule)):
			from .nodeHandler import NodeManager
			from .webAppScheduler import scheduler
			nodeManager = self._nodeManager = NodeManager(ti, scheduler.onNodeMoveto)
		return nodeManager
	
	@property
	@logException
	def rootRuleManager(self):
		webModule = self.rootWebModule
		if not webModule:
			return None
		return webModule.ruleManager
	
	@property
	@logException
	def rootWebModule(self):
		from . import canHaveWebAccessSupport, webAccessEnabled
		if not webAccessEnabled:
			return None
		ti = self.treeInterceptor
		if not ti:
			self._rootWebModule = None
			return None
		webModule = self._rootWebModule
		if not webModule:
			obj = ti.rootNVDAObject
			if not canHaveWebAccessSupport(obj):
				return None
			from . import webModuleHandler
			try:
				webModule = self._rootWebModule = webModuleHandler.getWebModuleForTreeInterceptor(ti)
			except Exception:
				log.exception()
		return webModule
	
	@property
	@logException
	@logException
	def ruleManager(self):
		webModule = self.webModule
		if not webModule:
			return None
		return webModule.ruleManager
	
	@property
	@logException
	def treeInterceptor(self):
		if hasattr(self, "_treeInterceptor"):
			ti = self._treeInterceptor
			if isinstance(ti, weakref.ReferenceType):
				ti = ti()
			if ti and ti in treeInterceptorHandler.runningTable:
				return ti
			else:
				return None
	
	@property
	@logException
	def webModule(self):
		root = self.rootWebModule
		if not root:
			return None
		try:
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
		except Exception:
			#log.exception(stack_info=True)
			return root
		return root.ruleManager.subModules.atPosition(info._startOffset) or root
	
	@property
	@logException
	def zone(self):
		ruleManager = self.ruleManager
		if not ruleManager:
			return None
		return ruleManager.zone
	
	@zone.setter
	@logException
	def zone(self, value):
		if value is None:
			# Avoid raising an AttributeError if we only want to ensure
			# no zone restriction applies (ie. even if there is no WebModule)
			ruleManager = self.ruleManager
			if ruleManager:
				ruleManager.zone = value
			return
		# Properly raise AttributeError if there is no RuleManager.
		self.ruleManager.zone = value
	
	@logException
	def getWebModuleAtTextInfo(self, info):
		rootModule = self.webModule
		if not rootModule:
			return None
		return self.ruleManager.subModules.atPosition(info._startOffset) or rootModule


class WebAccessBmdtiTextInfo(textInfos.offsets.OffsetsTextInfo):
	"""
	WebAccess `OffsetTextInfo` overlay.

	Features:
	 - Enforce respect of the active zone borders.
	 - Override attributes of mutated controls.
	"""  # noqa: E101
	def find(self, text, caseSensitive=False, reverse=False):
		zone = self.obj.webAccess.zone
		if not zone:
			return super().find(
				text, caseSensitive, reverse
			)
		savedStart = self._startOffset
		savedEnd = self._endOffset
		found = super().find(
			text, caseSensitive, reverse
		)
		if not zone.containsTextInfo(self):
			self._startOffset = savedStart
			self._endOffset = savedEnd
			return None
		return found

	def move(self, unit, direction, endPoint=None):
		zone = self.obj.webAccess.zone
		if not zone:
			return super().move(
				unit, direction, endPoint=endPoint
			)
		wasCollapsed = self.isCollapsed
		count = 0
		while count != direction:
			lastStart = self._startOffset
			lastEnd = self._endOffset
			moved = super().move(
				unit, direction, endPoint=endPoint
			)
			if not moved:
				return count
			if zone.restrictTextInfo(self):
				if not wasCollapsed:
					# restrictTextInfo might have collapsed at zone border
					if direction > 0:
						if endPoint != "end":
							self._startOffset = lastEnd
					else:
						if endPoint != "start":
							self._endOffset = lastStart
				break
			elif wasCollapsed and zone.isTextInfoAtEnd(self) and direction > 0:
				# Step back rather than sit at the end of the unit.
				self._startOffset = self._endOffset = lastStart
				break
			count += moved
		return count

	def updateCaret(self):
		zone = self.obj.webAccess.zone
		if zone and not zone.containsTextInfo(self):
			self.obj.webAccess.zone = None
		super().updateCaret()

	def updateSelection(self):
		zone = self.obj.webAccess.zone
		if zone and not zone.containsTextInfo(self):
			self.obj.webAccess.zone = None
		super().updateSelection()

	def _getControlFieldAttribs(self, docHandle, id):
		info = self.copy()
		info.expand(textInfos.UNIT_CHARACTER)
		for field in reversed(info.getTextWithFields()):
			if (
				not isinstance(field, textInfos.FieldCommand)
				or field.command != "controlStart"
			):
				continue
			attrs = field.field
			if (
				tryInt(attrs["controlIdentifier_docHandle"]) == docHandle
				and tryInt(attrs["controlIdentifier_ID"]) == id
			):
				break
		else:
			raise LookupError
		mgr = self.obj.webAccess.rootRuleManager
		if not mgr:
			return attrs
		mutated = mgr.getMutatedControl((docHandle, id))
		if mutated:
			attrs.update(mutated.attrs)
		return attrs

	def _getFieldsInRange(self, start, end):
		fields = super()._getFieldsInRange(
			start, end
		)
		mgr = self.obj.webAccess.rootRuleManager
		if not mgr or not mgr.isReady:
			return fields
		for field in fields:
			if (
				not isinstance(field, textInfos.FieldCommand)
				or field.command != "controlStart"
			):
				continue
			attrs = field.field
			mutated = mgr.getMutatedControl((
				tryInt(attrs["controlIdentifier_docHandle"]), tryInt(attrs["controlIdentifier_ID"])
			))
			if mutated:
				attrs.update(mutated.attrs)
		return fields


class WebAccessMutatedQuickNavItem(browseMode.TextInfoQuickNavItem):
	"""
	A `TextInfoQuickNavItem` supporting mutated controls.
	"""
	def __init__(self, itemType, document, textInfo, controlId):
		super().__init__(
			itemType, document, textInfo
		)
		# Support for `virtualBuffers.VirtualBufferQuickNavItem.isChild`
		# so that the Elements List dialog can relate nested headings.
		self.vbufFieldIdentifier = controlId

	@property
	def obj(self):
		return self.document.getNVDAObjectFromIdentifier(self.vbufFieldIdentifier)

	def isChild(self, parent):
		if self.itemType == "heading":
			try:

				def getLevel(obj):
					return int(self.textInfo._getControlFieldAttribs(
						*self.vbufFieldIdentifier
					)["level"])

				if getLevel(self) > getLevel(parent):
					return True
			except (AttributeError, KeyError, ValueError, TypeError):
				return False
		return super().isChild(parent)

	@property
	def label(self):
		attrs = {}

		def propertyGetter(prop):
			if not attrs:
				# Lazily fetch the attributes the first time they're needed
				# that is, in the Elements List dialog.
				info = self.textInfo.copy()
				info.expand(textInfos.UNIT_CHARACTER)
				attrs.update(info._getControlFieldAttribs(*self.vbufFieldIdentifier))
			return attrs.get(prop)

		return self._getLabelForProperties(propertyGetter)


class WebAccessBmdti(browseMode.BrowseModeDocumentTreeInterceptor):
	"""
	WebAccess `BrowseModeDocumentTreeInterceptor` overlay.
	"""
	def __init__(self, obj):
		super().__init__(obj)
		self.webAccess = WebAccessBmdtiHelper(self)
		# As of NVDA commit 9a1a935491, `TreeInterceptor.TextInfo` can either
		# be an auto-property or a field.
		attr = None
		for cls in self.__class__.__mro__:
			if cls is WebAccessBmdti:
				continue
			try:
				attr = cls.__dict__["TextInfo"]
			except KeyError:
				continue
			break
		if attr and not isinstance(attr, baseObject.Getter):
			if issubclass(attr, textInfos.offsets.OffsetsTextInfo):
				self.TextInfo = getDynamicClass((WebAccessBmdtiTextInfo, attr))

	def terminate(self):
		self.webAccess.terminate()
		super().terminate()

	def _get_isAlive(self):
		isAlive = super().isAlive
		if isAlive:
			return isAlive
		# Due to unidentified race conditions, MSHTML sometimes caches a zero-valued IAccessibleRole
		# after a trapped COMError and then considers the TreeInterceptor as being dead.
		# Invalidating the property cache usually fixes the issue.
		root = self.rootNVDAObject
		if not root:
			return isAlive
		from NVDAObjects.IAccessible.MSHTML import MSHTML
		if not issubclass(root.APIClass, MSHTML):
			return isAlive
		try:
			del root._propertyCache[type(root).IAccessibleRole.fget]
		except KeyError:
			return isAlive
		except Exception:
			log.exception()
		else:
			isAlive = super().isAlive
		return isAlive

	def _get_TextInfo(self):
		superCls = super()._get_TextInfo()
		if not issubclass(superCls, textInfos.offsets.OffsetsTextInfo):
			return superCls
		return getDynamicClass((WebAccessBmdtiTextInfo, superCls))

	def _set_selection(self, info, reason=REASON_CARET):
		webModule = self.webAccess.getWebModuleAtTextInfo(info)
		if webModule and hasattr(webModule, "_set_selection"):
			webModule._set_selection(self, info, reason=reason)
			return
		super()._set_selection(info, reason=reason)

	def _caretMovementScriptHelper(
		self,
		gesture,
		unit,
		direction=None,
		posConstant=textInfos.POSITION_SELECTION,
		posUnit=None,
		posUnitEnd=False,
		extraDetail=False,
		handleSymbols=False
	):
		alreadyHit = self.webAccess.caretHitZoneBorder
		self.webAccess.caretHitZoneBorder = False
		zone = self.webAccess.zone
		if zone:
			# Detect zone border hit before-hand so that we can both inform
			# the user before a potentially long text and still call the
			# original NVDA implementation.
			info = self.makeTextInfo(textInfos.POSITION_CARET)
			if direction is not None:
				info.expand(unit)
				if direction > 0:
					if zone.isTextInfoAtEnd(info):
						self.webAccess.caretHitZoneBorder = True
				elif zone.isTextInfoAtStart(info):
					self.webAccess.caretHitZoneBorder = True
			elif (
				posUnit == textInfos.POSITION_LAST
				and zone.isTextInfoAtOfAfterEnd(info)
			) or (
				posUnit == textInfos.POSITION_FIRST
				and zone.isTextInfoAtStart(info)
			):
				self.webAccess.caretHitZoneBorder = True
			if self.webAccess.caretHitZoneBorder:
				msg = _("Zone border")
				if alreadyHit:
					msg += " "
					# Translators: Hint on how to cancel zone restriction.
					msg += _("Press escape to cancel zone restriction.")
				ui.message(msg)
			if posConstant == textInfos.POSITION_FIRST:
				pos = zone.result.startOffset
				posConstant = textInfos.offsets.Offsets(pos, pos)
			elif posConstant == textInfos.POSITION_LAST:
				pos = max(zone.result.endOffset - 1, zone.result.startOffset)
				posConstant = textInfos.offsets.Offsets(pos, pos)
		super()._caretMovementScriptHelper(
			gesture,
			unit,
			direction=direction,
			posConstant=posConstant,
			posUnit=posUnit,
			posUnitEnd=posUnitEnd,
			extraDetail=extraDetail,
			handleSymbols=handleSymbols
		)

	def _iterNodesByType(self, itemType, direction="next", pos=None):
		superIter = super()._iterNodesByType(
			itemType, direction, pos
		)
		if itemType == "focusable":
			# `VirtualBuffer._iterNodesByType` does not support yielding
			# multiple focusable elements: It causes a core freeze.
			# TODO: This does not support yielding items made focusable by mutation.
			try:
				yield next(superIter)
			except StopIteration:
				return
		mgr = self.webAccess.rootRuleManager
		if not mgr:
			for item in superIter:
				yield item
			return
		zone = self.webAccess.zone
		if (
			zone
			and direction == "up"
			and isinstance(pos, textInfos.offsets.OffsetsTextInfo)
			and pos._startOffset == pos._endOffset == zone.endOffset
		):
			pos = pos.copy()
			pos.move(textInfos.UNIT_CHARACTER, -1)

		criteria = self.__getCriteriaForMutatedControlType(itemType)
		mutatedIter = self.__iterMutatedControlsByCriteria(
			criteria, itemType, direction, pos
		)
		for item in browseMode.mergeQuickNavItemIterators(
			(mutatedIter, superIter),
			direction
		):
			if zone:
				if item.textInfo._startOffset < zone.result.startOffset:
					if direction == "next":
						continue
					else:
						return
				elif item.textInfo._startOffset >= zone.result.endOffset:
					if direction == "previous":
						continue
					else:
						return
			if not isinstance(item, WebAccessMutatedQuickNavItem):
				controlId = None
				if isinstance(item, virtualBuffers.VirtualBufferQuickNavItem):
					controlId = item.vbufFieldIdentifier
				elif isinstance(item, browseMode.TextInfoQuickNavItem):
					try:
						obj = item.textInfo.NVDAObjectAtStart
						controlId = self.getIdentifierFromNVDAObject(obj)
					except Exception:
						log.exception()
				if controlId is None:
					log.error((
						"Could not determine controlId for item: {}"
					).format(item))
				elif mgr.getMutatedControl(controlId):
					# Avoid iterating twice over mutated controls.
					continue
			yield item

	def __getCriteriaForMutatedControlType(self, itemType):
		"""
		Return the search attributes for matching mutated controls.

		Adapted from `Gecko_ia2._searchableAttribsForNodeType`

		See `__mutatedControlMatchesCriteria` for details on criteria format.
		"""
		if itemType == "annotation":
			attrs = {
				"IAccessible::role": [
					controlTypes.ROLE_DELETED_CONTENT,
					controlTypes.ROLE_INSERTED_CONTENT
				]
			}
		elif itemType == "blockQuote":
			attrs = {
				"role": [controlTypes.ROLE_BLOCKQUOTE]
			}
		elif itemType == "button":
			attrs = {"role": [controlTypes.ROLE_BUTTON]}
		elif itemType == "checkBox":
			attrs = {"role": [controlTypes.ROLE_CHECKBOX]}
		elif itemType == "comboBox":
			attrs = {"role": [controlTypes.ROLE_COMBOBOX]}
		elif itemType == "edit":
			attrs = [
				{
					"role": [controlTypes.ROLE_EDITABLETEXT],
					"states": [set((controlTypes.STATE_EDITABLE,))]
				},
				{
					"states": [set((controlTypes.STATE_EDITABLE,))],
					"parent::states::not": [
						set((controlTypes.STATE_EDITABLE,))
					]
				},
			]
		elif itemType == "embeddedObject":
			attrs = [
				{
					"tag": ["embed", "object", "applet", "audio", "video"]
				},
				{
					"role": [
						controlTypes.ROLE_APPLICATION,
						controlTypes.ROLE_DIALOG
					]
				}
			]
		elif itemType == "frame":
			attrs = {"role": [controlTypes.ROLE_INTERNALFRAME]}
		elif itemType == "focusable":
			attrs = {
				"states": [set((controlTypes.STATE_FOCUSABLE,))]
			}
		elif itemType == "formField":
			attrs = [
				{
					"role": [
						controlTypes.ROLE_BUTTON,
						controlTypes.ROLE_CHECKBOX,
						controlTypes.ROLE_COMBOBOX,
						controlTypes.ROLE_LIST,
						controlTypes.ROLE_MENUBUTTON,
						controlTypes.ROLE_RADIOBUTTON,
						controlTypes.ROLE_TOGGLEBUTTON,
						controlTypes.ROLE_TREEVIEW,
					],
					"states::not": [set((controlTypes.STATE_READONLY,))]
				},
				{
					"role": [
						controlTypes.ROLE_COMBOBOX,
						controlTypes.ROLE_EDITABLETEXT
					],
					"states": [set((controlTypes.STATE_EDITABLE,))]
				},
				{
					"states": [set((controlTypes.STATE_EDITABLE,))],
					"parent::states::not": [
						set((controlTypes.STATE_EDITABLE,))
					]
				},
			]
		elif itemType == "graphic":
			attrs = {"role": [controlTypes.ROLE_GRAPHIC]}
		elif itemType.startswith('heading'):
			attrs = {"role": [controlTypes.ROLE_HEADING]}
			if itemType[7:].isdigit():
				# "level" is int in position info,
				# but text in control field attributes...
				attrs["level"] = [itemType[7:]]
		elif itemType == "landmark":
			attrs = {"landmark": [True]}
		elif itemType == "link":
			attrs = {"role": [controlTypes.ROLE_LINK]}
		elif itemType == "list":
			attrs = {"role": [controlTypes.ROLE_LIST]}
		elif itemType == "listItem":
			attrs = {"role": [controlTypes.ROLE_LISTITEM]}
		elif itemType == "radioButton":
			attrs = {"role": [controlTypes.ROLE_RADIOBUTTON]}
		elif itemType == "separator":
			attrs = {"role": [controlTypes.ROLE_SEPARATOR]}
		elif itemType == "table":
			attrs = {"role": [controlTypes.ROLE_TABLE]}
			if not config.conf["documentFormatting"]["includeLayoutTables"]:
				attrs["table-layout"] = [False]
		elif itemType == "unvisitedLink":
			# We can't track this.
			# Thus, controls mutated to links aren't visited nor unvisited.
			attrs = {}
		elif itemType == "visitedLink":
			# We can't track this.
			# Thus, controls mutated to links aren't visited nor unvisited.
			attrs = {}
		else:
			attrs = {}
		return attrs

	def __iterMutatedControlsByCriteria(
		self, criteria, itemType, direction="next", pos=None
	):
		"""
		Iterate over mutated controls matching the given search criteria.

		See `__mutatedControlMatchesCriteria` for details on criteria format.
		"""
		mgr = self.webAccess.rootRuleManager
		if not mgr:
			return
		if not criteria:
			return
		for mutated in mgr.iterMutatedControls(
			direction=direction,
			offset=pos._startOffset if pos is not None else None
		):
			info = mutated.node.getTextInfo()
			if self.__mutatedControlMatchesCriteria(criteria, mutated, info):
				yield WebAccessMutatedQuickNavItem(
					itemType, self, info, mutated.controlId
				)

	def __mutatedControlMatchesCriteria(self, criteria, mutated, info=None):
		"""
		Check whether a mutated control matches the given criteria.

		Criteria are expected to be a list of dictionaries.
		Each item in the list represents a valid match alternative.
		The control matches if any of these alternatives matches.

		The dictionary for an alternative maps attribute names to a list of
		accepted values.
		Every key in the dictionary must be satisfied for an alternative to
		match.

		Possible values for a key are compared against the mutated control
		field attribute value with the same name, with a few twists:
		 - Missing control field attribute values are considered to be `None`.
		 - The key "tag" is checked against the attribute with the same name
		   on the node corresponding to the mutated control.
		 - If the key is prefixed with "parent::", the values are checked
		   against the parent node.
		 - If a key is suffixed with "::not", no criteria value should match
		   the candidate control field attribute value for the criteria to be
		   satisfied.
		 - If a possible value is boolean, the corresponding control field
		   attribute value is first converted to boolean before comparison.
		   That is, as an example, the criteria value `False` matches a missing
		   candidate control field attribute value.
		 - If a possible value is a set, the candidate control field attribute
		   value is also considered to be a set, and the key matches if the
		   former is a subset of the latter.
		   The "::not" key suffix also applies to sets, negating the match.
		"""  # noqa: E101
		if not criteria:
			return True
		if isinstance(criteria, dict):
			criteria = (criteria,)
		if info is None:
			info = mutated.node.getTextInfo()
		docHandle = self.rootDocHandle
		controlAttrs = info._getControlFieldAttribs(*mutated.controlId)
		controlNode = mutated.node
		parentAttrs = None  # Fetch lazily as seldom needed
		parentNode = mutated.node.parent
		for alternative in criteria:
			for key, values in alternative.items():
				if key.endswith("::not"):
					negate = True
					key = key[:-len("::not")]
				else:
					negate = False
				if key.startswith("parent::"):
					key = key[len("parent::"):]
					if parentAttrs is None:
						parent = mutated.node.parent
						parentInfo = parent.getTextInfo()
						parentAttrs = parentInfo._getControlFieldAttribs(*parent.controlIdentifier)
					attrs = parentAttrs
					node = parentNode
				else:
					attrs = controlAttrs
					node = controlNode
				if key == "tag":
					candidate = node.tag
				else:
					candidate = attrs.get(key)
				for value in values:
					if isinstance(value, set):
						if value.issubset(candidate or set()) == negate:
							break
						continue
					if isinstance(value, bool):
						candidate = bool(candidate)
					if (candidate != value) != negate:
						break
				else:
					# This attribute matches
					continue
				# An attribute did not match in this alternative
				break
			else:
				# All attributes matched in this alternative
				return True
		return False

	def _quickNavScript(
		self, gesture, itemType, direction, errorMessage, readUnit
	):
		if self.webAccess.zone:
			errorMessage += " "
			# Translators: Complement to quickNav error message in zone.
			errorMessage += _("in this zone.")
			errorMessage += " "
			# Translators: Hint on how to cancel zone restriction.
			errorMessage += _("Press escape to cancel zone restriction.")
		super()._quickNavScript(
			gesture, itemType, direction, errorMessage, readUnit
		)

	def _tabOverride(self, direction):
		if self.webAccess.zone:
			caretInfo = self.makeTextInfo(textInfos.POSITION_CARET)
			try:
				next(self._iterNodesByType("focusable", direction, caretInfo))
			except StopIteration:
				if direction == "next":
					msg = _("No more focusable element in this zone.")
				else:
					msg = _("No previous focusable element in this zone.")
				msg += " "
				if (self.passThrough and not self.disableAutoPassThrough):
					# Translators: Hint on how to cancel zone restriction.
					msg += _("Press escape twice to cancel zone restriction.")
				else:
					# Translators: Hint on how to cancel zone restriction.
					msg += _("Press escape to cancel zone restriction.")
				ui.message(msg)
				return True
		return super()._tabOverride(direction)

	def doFindText(self, text, reverse=False, caseSensitive=False, willSayAllResume=False):
		if not text:
			return
		info = self.makeTextInfo(textInfos.POSITION_CARET)
		res = info.find(text, reverse=reverse, caseSensitive=caseSensitive)
		if res:
			self.selection = info
			speech.cancelSpeech()
			info.move(textInfos.UNIT_LINE, 1, endPoint="end")
			if not willSayAllResume:
				speech.speakTextInfo(info, reason=REASON_CARET)
		elif self.webAccess.zone:
			
			def ask():
				if gui.messageBox(
					"\n".join((
						_('text "%s" not found') % text,
						"",
						_("Cancel zone restriction and retry?")
					)),
					caption=_("Find Error"),
					style=wx.OK | wx.CANCEL | wx.ICON_ERROR
				) == wx.OK:
					self.webAccess.zone = None
					self.doFindText(
						text,
						reverse=reverse,
						caseSensitive=caseSensitive
					)
			
			wx.CallAfter(ask)
		else:
			wx.CallAfter(
				gui.messageBox,
				_('text "%s" not found') % text,
				caption=_("Find Error"),
				style=wx.OK | wx.ICON_ERROR
			)
		cursorManager.CursorManager._lastFindText = text
		cursorManager.CursorManager._lastCaseSensitivity = caseSensitive

	def getAlternativeScript(self, gesture, script):

		class Break(Exception):
			"""Block-level break."""

		try:
			webModule = self.webAccess.webModule
			if not webModule:
				raise Break()
			try:
				funcName = script.__name__
			except AttributeError:
				raise Break()
			if not funcName.startswith("script_"):
				raise Break()
			scriptName = funcName[len("script_"):]
			overrideName = "override_{scriptName}".format(**locals())
			try:
				override = getattr(webModule, overrideName)
			except AttributeError:
				raise Break()
			script = ScriptWrapper(script, override)
		except Break:
			pass
		if script:
			if not webModule and getattr(script, "passThroughIfNoWebModule", False):
				if getattr(script, "supersedes", False) and script.supersedes:
					scriptName = "script_%s" % list(script.supersedes.values())[0]
					script = getattr(self, scriptName, None)
					if script: return script
				script = self.script_passThrough
			if getattr(script, "ignoreSingleLetterNavSetting", False):
				return script
		return super().getAlternativeScript(gesture, script)

	def getScript(self, gesture):
		webModule = self.webAccess.webModule
		if webModule:
			script = webModule.getScript(gesture)
			if script:
				return ScriptWrapper(
					script, ignoreTreeInterceptorPassThrough=True
				)
		return super().getScript(gesture)

	def event_treeInterceptor_gainFocus(self):
		webModule = self.webAccess.webModule
		if webModule and hasattr(webModule, "event_treeInterceptor_gainFocus"):
			if webModule.event_treeInterceptor_gainFocus():
				return
		super().event_treeInterceptor_gainFocus()

	def script_disablePassThrough(self, gesture):
		if (
			(not self.passThrough or self.disableAutoPassThrough)
			and self.webAccess.zone
		):
			self.webAccess.zone = None
			if self.webAccess.zone is None:
				# Translators: Reported when cancelling zone restriction
				ui.message(_("Zone restriction cancelled"))
			else:
				# Translators: Reported when cancelling zone restriction
				ui.message(_("Zone restriction enlarged to a wider zone"))
		else:
			super().script_disablePassThrough(gesture)

	script_disablePassThrough.ignoreTreeInterceptorPassThrough = True

	def script_elementsList(self, gesture):
		# We need this to be a modal dialog, but it mustn't block this script.
		def run():
			zone = self.webAccess.zone
			self.webAccess.zone = None
			gui.mainFrame.prePopup()
			d = self.ElementsListDialog(self)
			d.ShowModal()
			d.Destroy()
			gui.mainFrame.postPopup()

			def check():
				info = self.makeTextInfo(textInfos.POSITION_CARET)
				if zone and zone.containsTextInfo(info):
					self.webAccess.zone = zone

			core.callLater(150, check)
		wx.CallAfter(run)

	script_elementsList.__doc__ = \
		browseMode.BrowseModeDocumentTreeInterceptor.script_elementsList.__doc__
	script_elementsList.category = \
		browseMode.BrowseModeDocumentTreeInterceptor.scriptCategory
	script_elementsList.ignoreTreeInterceptorPassThrough = True

	@script(
		# Translators: The description for the elementsListInZone script
		description=_("Lists various types of elements in the current zone"),
		category=SCRCAT_WEBACCESS,
		gesture="kb:NVDA+shift+f7"
	)
	def script_elementsListInZone(self, gesture):
		super().script_elementsList(gesture)

	script_elementsListInZone.ignoreTreeInterceptorPassThrough = True
	script_elementsListInZone.passThroughIfNoWebModule = True

	@script(
		# Translators: The description for the quickNavToNextResultLevel1 script
		description=_("Move to next zone."),
		category=SCRCAT_WEBACCESS,
		gesture="kb:control+pagedown",
	)
	def script_quickNavToNextResultLevel1(self, gesture):
		self.webAccess.ruleManager.quickNavToNextLevel1()

	script_quickNavToNextResultLevel1.ignoreTreeInterceptorPassThrough = True
	script_quickNavToNextResultLevel1.passThroughIfNoWebModule = True

	@script(
		# Translators: The description for the quickNavToPreviousResultLevel1 script
		description=_("Move to previous zone."),
		category=SCRCAT_WEBACCESS,
		gesture="kb:control+pageup",
	)
	def script_quickNavToPreviousResultLevel1(self, gesture):
		self.webAccess.ruleManager.quickNavToPreviousLevel1()

	script_quickNavToPreviousResultLevel1.ignoreTreeInterceptorPassThrough = True
	script_quickNavToPreviousResultLevel1.passThroughIfNoWebModule = True

	@script(
		# Translators: The description for the quickNavToNextResultLevel2 script
		description=_("Move to next global marker."),
		category=SCRCAT_WEBACCESS,
		gesture="kb:pagedown"
	)
	def script_quickNavToNextResultLevel2(self, gesture):
		self.webAccess.ruleManager.quickNavToNextLevel2()

	script_quickNavToNextResultLevel2.ignoreTreeInterceptorPassThrough = True
	script_quickNavToNextResultLevel2.passThroughIfNoWebModule = True
	script_quickNavToNextResultLevel2.supersedes = {"kb:pagedown": "moveByPage_forward"}

	@script(
		# Translators: The description for the quickNavToPreviousResultLevel2 script
		description=_("Move to previous global marker."),
		category=SCRCAT_WEBACCESS,
		gesture="kb:pageup"
	)
	def script_quickNavToPreviousResultLevel2(self, gesture):
		self.webAccess.ruleManager.quickNavToPreviousLevel2()

	script_quickNavToPreviousResultLevel2.category = SCRCAT_WEBACCESS
	script_quickNavToPreviousResultLevel2.ignoreTreeInterceptorPassThrough = True
	script_quickNavToPreviousResultLevel2.passThroughIfNoWebModule = True
	script_quickNavToPreviousResultLevel2.supersedes = {"kb:pageup": "moveByPage_back"}

	@script(
		# Translators: The description for the quickNavToNextResultLevel3 script
		description=_("Move to next local marker."),
		category=SCRCAT_WEBACCESS,
		gesture="kb:shift+pagedown"
	)
	def script_quickNavToNextResultLevel3(self, gesture):
		self.webAccess.ruleManager.quickNavToNextLevel3()


	script_quickNavToNextResultLevel3.ignoreTreeInterceptorPassThrough = True
	script_quickNavToNextResultLevel3.passThroughIfNoWebModule = True

	@script(
		# Translators: The description for the quickNavToPreviousResultLevel3 script
		description=_("Move to previous local marker."),
		category=SCRCAT_WEBACCESS,
		gesture="kb:shift+pageup"
	)
	def script_quickNavToPreviousResultLevel3(self, gesture):
		self.webAccess.ruleManager.quickNavToPreviousLevel3()

	script_quickNavToPreviousResultLevel3.ignoreTreeInterceptorPassThrough = True
	script_quickNavToPreviousResultLevel3.passThroughIfNoWebModule = True

	@script(
		# Translators: The description for the refreshResults script
		description=_("Refresh results"),
		category=SCRCAT_WEBACCESS,
		gesture="kb:NVDA+shift+f5"
	)
	@guarded
	def script_refreshResults(self, gesture):
		# Translators: Notified when manually refreshing results
		ui.message(_("Refresh results"))
		self.webAccess.rootRuleManager.clear()
		self.webAccess.nodeManager.update(force=True)
	
	script_refreshResults.ignoreTreeInterceptorPassThrough = True
	script_refreshResults.passThroughIfNoWebModule = True

	def script_tab(self, gesture):
		if (
			(self.passThrough and not self.webAccess.zone)
			or not self._tabOverride("next")
		):
			gesture.send()

	script_tab.ignoreTreeInterceptorPassThrough = True

	def script_shiftTab(self, gesture):
		if (
			(self.passThrough and not self.webAccess.zone)
			or not self._tabOverride("previous")
		):
			gesture.send()

	script_shiftTab.ignoreTreeInterceptorPassThrough = True


class WebAccessObjectHelper(TrackedObject):
	"""
	Utility methods and properties.
	"""
	
	def __init__(self, obj: NVDAObjects.NVDAObject):
		self._obj: weakref.ref[NVDAObjects.NVDAObject] = weakref.ref(obj)
		self._webModule: weakref.ref[WebModule] = None
		"""Cached to try sustain operations during RuleManager update.
		"""
	
	@property
	@logException
	def controlId(self):
		obj = self.obj
		return obj.treeInterceptor.getIdentifierFromNVDAObject(obj)
	
	@property
	@logException
	def nodeManager(self):
		ti = self.treeInterceptor
		if not ti:
			return None
		return ti.webAccess.nodeManager

	@property
	@logException
	def obj(self):
		return self._obj()

	@property
	@logException
	def ruleManager(self):
		webModule = self.webModule
		if not webModule:
			return None
		return webModule.ruleManager
	
	@property
	@logException
	def rootRuleManager(self):
		ti = self.treeInterceptor
		if not isinstance(ti, WebAccessBmdti):
			return None
		return ti.webAccess.rootRuleManager
	
	@property
	@logException
	def treeInterceptor(self):
		obj = self.obj
		while True:
			if not hasattr(obj, "_treeInterceptor"):
				return None
			ti = obj._treeInterceptor
			if isinstance(ti, weakref.ReferenceType):
				ti = ti()
			if isinstance(ti, (type(None), WebAccessBmdti)):
				return ti
			try:
				obj = ti.rootNVDAObject.parent
			except Exception:
				return None
	
	@property
	@logException
	def webModule(self):
		mgr = self.rootRuleManager
		if mgr is None:
			return None
		try:
			controlId = self.controlId
		except Exception:
			log.exception()
			return None
		try:
			webModule = mgr.getWebModuleForControlId(controlId)
		except LookupError:
			log.warning(f"Unknown controlId: {controlId}")
			webModule = None
		if webModule is None and self._webModule is not None:
			# The RumeManager is not ready, return the last cached value
			return self._webModule()
		if webModule is None:
			# Lookup by controlId failed and there is no cached value.
			# Attempt lookup by position.
			ti = self.treeInterceptor
			if not ti:
				return None
			try:
				info = ti.makeTextInfo(self.obj)
			except Exception:
				log.exception(stack_info=True)
				# Failback to the WebModule at caret (not cached)
				return ti.webAccess.webModule
			webModule = ti.webAccess.getWebModuleAtTextInfo(info)
		if webModule is not None:
			self._webModule = weakref.ref(webModule)
		return webModule
	
	@logException
	def getMutatedControlAttribute(self, attr, default=None):
		mgr = self.rootRuleManager
		if not mgr:
			return default
		try:
			controlId = self.controlId
		except Exception:
			log.exception()
			return default
		mutated = mgr.getMutatedControl(controlId)
		if mutated:
			return mutated.attrs.get(attr, default)
		return default


class WebAccessObject(IAccessible):

	def initOverlayClass(self):
		self.webAccess = WebAccessObjectHelper(self)

	def _get_name(self, original=False):
		if original:
			self.webAccess._original = True
		try:
			name = super().name
			if original or not getattr(self, "webAccess", False) or getattr(self.webAccess, "_original", False):
				return name
			return self.webAccess.getMutatedControlAttribute("name", name)
		finally:
			if original:
				self.webAccess._original = False

	def _get_positionInfo(self):
		# "level" is text in control field attributes,
		# but int in position info...
		info = super().positionInfo
		level = self.webAccess.getMutatedControlAttribute("level")
		if level:
			try:
				level = int(level)
			except Exception:
				log.exception(
					"Could not convert to int: level={}".format(level)
				)
			info["level"] = level
		return info

	def _get_role(self, original=False):
		if original:
			self.webAccess._original = True
		try:
			role = super().role
			if original or not getattr(self, "webAccess", False) or getattr(self.webAccess, "_original", False):
				return role
			return self.webAccess.getMutatedControlAttribute("role", role)
		finally:
			if original:
				self.webAccess._original = False

	def _set_treeInterceptor(self, obj):
		super()._set_treeInterceptor(obj)
		if isinstance(obj, WebAccessBmdti):
			webModule = obj.webAccess.webModule
			if not webModule:
				return
			clsList = list(self.__class__.__mro__)
			res = webModule.chooseNVDAObjectOverlayClasses(self, clsList)
			if not res:
				return
			mutateObj(self, clsList)
			if res is True:
				return
			for cls in res:
				initFunc = getattr(cls, "initOverlayClass")
				if initFunc:
					try:
						initFunc(obj)
					except Exception:
						log.exception()


class WebAccessDocument(WebAccessObject):

	def _get_treeInterceptorClass(self):
		# Might raise NotImplementedError on purpose.
		superCls = super().treeInterceptorClass
		if not issubclass(
			superCls,
			browseMode.BrowseModeDocumentTreeInterceptor
		):
			return superCls
		return getDynamicClass((WebAccessBmdti, superCls))
