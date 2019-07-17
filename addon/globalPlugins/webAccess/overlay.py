# globalPlugins/webAccess/overlay.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2019 Accessolutions (http://accessolutions.fr)
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

from __future__ import absolute_import, division, print_function

__version__ = "2019.07.16"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import weakref
import wx

import addonHandler
import baseObject
import browseMode
import controlTypes
import core
import cursorManager
import gui
from logHandler import log
import NVDAObjects
from NVDAObjects.IAccessible import IAccessible
import speech
import textInfos
import ui
import virtualBuffers

from .nvdaVersion import nvdaVersion


try:
	from six.moves import xrange
except ImportError:
	# NVDA version < 2018.3
	pass


addonHandler.initTranslation()


SCRIPT_CATEGORY = "WebAccess"


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
	for index in xrange(len(clsList)):
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
	def __init__(self, script, override=None, **defaults):
		self.script = script
		self.override = override
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
	
	def __call__(self, gesture):
		if self.override and self.override(gesture):
			# The override returned True, do not execute the original script.
			return
		self.script(gesture)


class IterNodesByTypeHitZoneBorder(StopIteration):
	pass


class WebAccessBmdtiHelper(object):
	"""
	Utility methods and properties.
	"""
	def __init__(self, treeInterceptor):
		self.treeInterceptor = treeInterceptor
		self.caretHitZoneBorder = False
	
	@property
	def ruleManager(self):
		# TODO: WIP on new coupling
		try:
			return self.webModule.ruleManager
		except AttributeError:
			return None
	
	@property
	def webModule(self):
		# TODO: WIP on new coupling
		from . import getWebApp, webAccessEnabled
		if not webAccessEnabled:
			return None
		return getWebApp(self.treeInterceptor.rootNVDAObject)
	
	@property
	def zone(self):
		ruleManager = self.ruleManager
		if not ruleManager:
			return None
		return ruleManager.zone
	
	@zone.setter
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


class WebAccessBmdtiTextInfo(textInfos.offsets.OffsetsTextInfo):
	"""
	WebAccess `OffsetTextInfo` overlay.
	
	Features:
	 - Enforce respect of the active zone borders.
	 - Override attributes of mutated controls.
	"""
	def find(self, text, caseSensitive=False, reverse=False):
		zone = self.obj.webAccess.zone
		if not zone:
			return super(WebAccessBmdtiTextInfo, self).find(
				text, caseSensitive, reverse
			)
		savedStart = self._startOffset
		savedEnd = self._endOffset
		found = super(WebAccessBmdtiTextInfo, self).find(
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
			return super(WebAccessBmdtiTextInfo, self).move(
				unit, direction, endPoint=endPoint
			)
		wasCollapsed = self.isCollapsed
		count = 0
		while count != direction:
			lastStart = self._startOffset
			lastEnd = self._endOffset
			moved = super(WebAccessBmdtiTextInfo, self).move(
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
		super(WebAccessBmdtiTextInfo, self).updateCaret()
	
	def updateSelection(self):
		zone = self.obj.webAccess.zone
		if zone and not zone.containsTextInfo(self):
			self.obj.webAccess.zone = None
		super(WebAccessBmdtiTextInfo, self).updateSelection()
	
	def _getControlFieldAttribs(self,  docHandle, controlId):
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
				int(attrs["controlIdentifier_docHandle"]) == docHandle
				and int(attrs["controlIdentifier_ID"]) == controlId
			):
				break
		else:
			raise LookupError
		mgr = self.obj.webAccess.ruleManager
		if not mgr:
			return attrs
		mutated = mgr.getMutatedControl(controlId)
		if mutated:
			attrs.update(mutated.attrs)
		return attrs

	def _getFieldsInRange(self, start, end):
		fields = super(WebAccessBmdtiTextInfo, self)._getFieldsInRange(
			start, end
		)
		mgr = self.obj.webAccess.ruleManager
		if not mgr or not mgr.isReady:
			return fields
		for field in fields:
			if (
				not isinstance(field, textInfos.FieldCommand)
				or field.command != "controlStart"
			):
				continue
			attrs = field.field
			controlId = int(attrs["controlIdentifier_ID"])
			mutated = mgr.getMutatedControl(controlId)
			if mutated:
				attrs.update(mutated.attrs)
		return fields


class WebAccessBmdtiQuickNavItem(browseMode.TextInfoQuickNavItem):
	"""
	A `TextInfoQuickNavItem` supporting mutated controls.
	"""
	def __init__(self, itemType, document, textInfo, controlId):
		super(WebAccessBmdtiQuickNavItem, self).__init__(
			itemType, document, textInfo
		)
		self.controlId = controlId
	
	if nvdaVersion >= (2017, 4):
		@property
		def label(self):
			attrs = {}
	
			def propertyGetter(prop):
				if not attrs:
					# Lazily fetch the attributes the first time they're needed
					# that is, in the Elements List dialog.
					info = self.textInfo.copy()
					info.expand(textInfos.UNIT_CHARACTER)
					attrs.update(info._getControlFieldAttribs(
						self.document.rootDocHandle,
						self.controlId
					))
				return attrs.get(prop)
	
			return self._getLabelForProperties(propertyGetter)


class WebAccessBmdti(browseMode.BrowseModeDocumentTreeInterceptor):
	"""
	WebAccess `BrowseModeDocumentTreeInterceptor` overlay.
	"""
	def __init__(self, obj):
		super(WebAccessBmdti, self).__init__(obj)
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
	
	def _get_TextInfo(self):
		superCls = super(WebAccessBmdti, self)._get_TextInfo()
		if not issubclass(superCls, textInfos.offsets.OffsetsTextInfo):
			return superCls
		return getDynamicClass((WebAccessBmdtiTextInfo, superCls))
	
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
				and zone.isTextInfoAtEnd(info)
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
				pos = zone.startOffset
				posConstant = textInfos.offsets.Offsets(pos, pos)
			elif posConstant == textInfos.POSITION_LAST:
				pos = max(zone.endOffset - 1, zone.startOffset)
				posConstant = textInfos.offsets.Offsets(pos, pos)
		super(WebAccessBmdti, self)._caretMovementScriptHelper(
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
		mgr = self.webAccess.ruleManager
		if not mgr:
			for item in super(WebAccessBmdti, self)._iterNodesByType(
				itemType, direction, pos
			):
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
		
		if itemType == "button":
			search = {"role": controlTypes.ROLE_BUTTON}
		elif itemType.startswith('heading'):
			search = {"role": controlTypes.ROLE_HEADING}
			if itemType[7:].isdigit():
				# "level" is int in position info,
				# but text in control field attributes...
				search["level"] = itemType[7:]
		elif itemType == "landmark":
			search = {"landmark": True}
		elif itemType == "link":
			search = {"role": controlTypes.ROLE_LINK}
		elif itemType == "table":
			search = {"role": controlTypes.ROLE_TABLE}
		else:
			search = {}
		
		def check(search, info, docHandle, controlId):
			"""
			Check whether a control meets the given search criteria.
			"""
			attrs = info._getControlFieldAttribs(docHandle, controlId)
			for key, value in search.items():
				candidate = attrs.get(key)
				if isinstance(value, bool):
					candidate = bool(candidate)
				if candidate != value:
					return False
			return True
		
		def iterMutated(mgr, check, search, direction, pos, document):
			"""
			Iterate over mutated controls matching the given search criteria.
			"""
			if not search:
				raise StopIteration()
			for entry in mgr.iterMutatedControls(
				direction=direction,
				offset=pos._startOffset if pos is not None else None
			):
				info = self.makeTextInfo(textInfos.offsets.Offsets(
					entry.start, entry.end
				))
				controlId = entry.controlId
				if not check(search, info, document.rootDocHandle, controlId):
					continue
				yield WebAccessBmdtiQuickNavItem(
					itemType, document, info, controlId
				)
		
		for item in browseMode.mergeQuickNavItemIterators(
			[
				iterMutated(mgr, check, search, direction, pos, self),
				super(WebAccessBmdti, self)._iterNodesByType(
					itemType, direction, pos
				)
			],
			direction
		):
			if zone:
				if item.textInfo._startOffset < zone.startOffset:
					if direction == "next":
						continue
					else:
						raise IterNodesByTypeHitZoneBorder
				elif item.textInfo._startOffset >= zone.endOffset:
					if direction == "previous":
						continue
					else:
						raise IterNodesByTypeHitZoneBorder
			if isinstance(item, virtualBuffers.VirtualBufferQuickNavItem):
				docHandle, controlId = item.vbufFieldIdentifier
				# Only perform the check if the control has been mutated.
				if mgr.getMutatedControl(controlId) and not check(
					search, item.textInfo, docHandle, controlId
				):
					continue 
				if pos is None and itemType == "heading":
					# Downgrade to the common base class so that the
					# Elements List dialog can relate nested headings.
					item.__class__ = browseMode.TextInfoQuickNavItem 
			elif not isinstance(item, WebAccessBmdtiQuickNavItem):
				log.error(u"Unexpected QuickNavItem type: {}".format(
					type(item)
				))
			yield item
		if zone:
			raise IterNodesByTypeHitZoneBorder
	
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
		super(WebAccessBmdti, self)._quickNavScript(
			gesture, itemType, direction, errorMessage, readUnit
		)
	
	def _tabOverride(self, direction):
		if self.webAccess.zone:
			caretInfo = self.makeTextInfo(textInfos.POSITION_CARET)
			try:
				next(self._iterNodesByType("focusable", direction, caretInfo))
			except IterNodesByTypeHitZoneBorder:
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
			except StopIteration:
				pass
		return super(WebAccessBmdti, self)._tabOverride(direction)
	
	def doFindText(self, text, reverse=False, caseSensitive=False):
		if not text:
			return
		info = self.makeTextInfo(textInfos.POSITION_CARET)
		res = info.find(text, reverse=reverse, caseSensitive=caseSensitive)
		if res:
			self.selection = info
			speech.cancelSpeech()
			info.move(textInfos.UNIT_LINE, 1, endPoint="end")
			speech.speakTextInfo(info, reason=controlTypes.REASON_CARET)
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
			return ScriptWrapper(script, override)
		except Break:
			pass
		return super(WebAccessBmdti, self).getAlternativeScript(gesture, script)
	
	def getScript(self, gesture):
		webModule = self.webAccess.webModule
		if webModule:
			func = webModule.getScript(gesture)
			if func:
				return ScriptWrapper(
					func, ignoreTreeInterceptorPassThrough=True
				)
		mgr = self.webAccess.ruleManager
		if mgr:
			func = mgr.getScript(gesture)
			if func:
				return ScriptWrapper(
					func, ignoreTreeInterceptorPassThrough=True
				)
		return super(WebAccessBmdti, self).getScript(gesture)
	
	def script_disablePassThrough(self, gesture):
		if (
			(not self.passThrough or self.disableAutoPassThrough)
			and self.webAccess.zone
		):
			self.webAccess.zone = None
			ui.message(_("Zone restriction cancelled"))
		else:
			super(WebAccessBmdti, self).script_disablePassThrough(gesture)
	
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
	
	script_elementsList.ignoreTreeInterceptorPassThrough = True
	
	def script_elementsListInZone(self, gesture):
		super(WebAccessBmdti, self).script_elementsList(gesture)
	
	script_elementsListInZone.ignoreTreeInterceptorPassThrough = True
	
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
	
	__gestures = {
		"kb:NVDA+shift+f7": "elementsListInZone",
	}


class WebAccessObjectHelper(object):
	"""
	Utility methods and properties.
	"""
	def __init__(self, obj):
		self.obj = obj
	
	@property
	def ruleManager(self):
		# TODO: WIP on new coupling
		try:
			return self.webModule.ruleManager
		except AttributeError:
			return None
	
	@property
	def webModule(self):
		# TODO: WIP on new coupling
		if not hasattr(self.obj, "_treeInterceptor"):
			return None
		ti = self.obj._treeInterceptor
		if isinstance(ti, weakref.ReferenceType):
			ti = ti()
		if ti is None:
			return None
		return ti.webAccess.webModule
	
	def getMutatedControlAttribute(self, attr, default=None):
		mgr = self.ruleManager
		if not mgr:
			return default
		obj = self.obj
		try:
			controlId = obj.treeInterceptor.getIdentifierFromNVDAObject(obj)[1]
		except:
			log.exception()
			return default
		mutated = mgr.getMutatedControl(controlId)
		if mutated:
			return mutated.attrs.get(attr, default)
		return default


class WebAccessObject(IAccessible):
	
	def initOverlayClass(self):
		self.webAccess = WebAccessObjectHelper(self) 
	
	def _get_name(self):
		name = super(WebAccessObject, self)._get_name()
		return self.webAccess.getMutatedControlAttribute("name", name)
	
	def _get_positionInfo(self):
		# "level" is text in control field attributes,
		# but int in position info...
		info = super(WebAccessObject, self)._get_positionInfo()
		level = self.webAccess.getMutatedControlAttribute("level")
		if level:
			try:
				level = int(level)
			except:
				log.exception(
					"Could not convert to int: level={}".format(level)
				)
			info["level"] = level
		return info
	
	def _get_role(self, original=False):
		role = super(WebAccessObject, self)._get_role()
		if original:
			return role
		return self.webAccess.getMutatedControlAttribute("role", role)
		
	def _set_treeInterceptor(self, obj):
		super(WebAccessObject, self)._set_treeInterceptor(obj)
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
					except:
						log.exception()
	
	if (2017, 3) <= nvdaVersion < (2019, 2):
		# Workaround for NVDA bug #9566
		# introduced by #7410 as of 393b55b in 2017.3
		# fixed by #9562 as of c20a503 in 2019.2
		
		def _get_columnNumber(self):
			res = super(WebAccessObject, self)._get_columnNumber()
			try:
				res = int(res)
			except ValueError:
				log.exception((
					u"Cannot convert columnNumber to int: {res}"
				).format(**locals()))
			return res
		
		def _get_rowNumber(self):
			res = super(WebAccessObject, self)._get_rowNumber()
			try:
				res = int(res)
			except ValueError:
				log.exception((
					u"Cannot convert rowNumber to int: {res}"
				).format(**locals()))
			return res
	
	if (2018, 4) <= nvdaVersion:
		# Workaround for NVDA bug #9520
		# introduced by #8898 as of b02ed2d in 2018.4
		# fixed by PR #9930 not yet merged
		
		def _get_table(self):
			try:
				super(WebAccessObject, self)._get_table()
			except NotImplementedError:
				return None


class WebAccessDocument(WebAccessObject):
	
	def _get_treeInterceptorClass(self):
		# Might raise NotImplementedError on purpose.
		superCls = super(WebAccessDocument, self).treeInterceptorClass
		if not issubclass(
			superCls,
			browseMode.BrowseModeDocumentTreeInterceptor
		):
			return superCls
		return getDynamicClass((WebAccessBmdti, superCls))
