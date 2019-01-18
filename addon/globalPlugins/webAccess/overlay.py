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

__version__ = "2019.01.18"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


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
import speech
import textInfos
import ui


addonHandler.initTranslation()


SCRIPT_CATEGORY = "WebAccess"


def getDynamicClass(superCls, overlayCls):
	bases = tuple([overlayCls, superCls])
	cache = NVDAObjects.DynamicNVDAObjectType._dynamicClassCache
	dynCls = cache.get(bases)
	if not dynCls:
		name = "Dynamic_%s" % "".join([x.__name__ for x in bases])
		dynCls = type(name, bases, {})
		cache[bases] = dynCls
	return dynCls


class IgnorePassThroughScriptWrapper(object):
	"""
	Wrap a script function to ignore `TreeInterceptor.passThrough`.
	"""
	ignoreTreeInterceptorPassThrough = True
	
	def __init__(self, func):
		self._func = func
	
	def __call__(self, gesture):
		self._func(gesture)


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
		from . import getWebApp, webAccessEnabled
		if not webAccessEnabled:
			return None
		webModule = getWebApp(self.treeInterceptor.rootNVDAObject)
		if webModule:
			return webModule.markerManager
	
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
	An `OffsetTextInfo` enforcing respect of the active zone borders.
	"""
	def expand(self, unit):
		zone = self.obj.webAccess.zone
		if not zone:
			super(WebAccessBmdtiTextInfo, self).expand(unit)
			return
		zone.restrictTextInfo(self)
		if self._startOffset == self._endOffset == zone.endOffset:
			# If collapsed at the end of the zone, step back one unit in
			# order to expand backwards.
			self.move(unit, -1)
		super(WebAccessBmdtiTextInfo, self).expand(unit)
		zone.restrictTextInfo(self)
	
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
	
	def updateSelection(self):
		zone = self.obj.webAccess.zone
		if zone:
			zone.restrictTextInfo(self)
		super(WebAccessBmdtiTextInfo, self).updateSelection()


class WebAccessBmdti(browseMode.BrowseModeDocumentTreeInterceptor):
	
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
				self.TextInfo = getDynamicClass(attr, WebAccessBmdtiTextInfo)
	
	def _get_TextInfo(self):
		superCls = super(WebAccessBmdti, self)._get_TextInfo()
		if not issubclass(superCls, textInfos.offsets.OffsetsTextInfo):
			return superCls
		return getDynamicClass(superCls, WebAccessBmdtiTextInfo)
	
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
		zone = self.webAccess.zone
		if (
			zone
			and direction == "up"
			and isinstance(pos, textInfos.offsets.OffsetsTextInfo)
			and pos._startOffset == pos._endOffset == zone.endOffset
		):
			pos = pos.copy()
			pos.move(textInfos.UNIT_CHARACTER, -1)
		for item in super(WebAccessBmdti, self)._iterNodesByType(
			itemType, direction, pos
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
			yield item
		if zone:
			raise IterNodesByTypeHitZoneBorder
	
	def _quickNavScript(
		self, gesture, itemType, direction, errorMessage, readUnit
	):
		if self.webAccess.zone:
			errorMessage += " "
			# Translators: Complement to quicknav error message in zone.
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
	
	def getScript(self, gesture):
		mgr = self.webAccess.ruleManager
		if mgr:
			func = mgr.getScript(gesture)
			if func:
				return IgnorePassThroughScriptWrapper(func)
			func = mgr.webApp.getScript(gesture)
			if func:
				return IgnorePassThroughScriptWrapper(func)
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
	
	__gestures = {
		"kb:NVDA+shift+f7": "elementsListInZone",
	}


class WebAccessDocument(NVDAObjects.NVDAObject):
	
	def _get_treeInterceptorClass(self):
		# Might raise NotImplementedError on purpose.
		superCls = super(WebAccessDocument, self).treeInterceptorClass
		if not issubclass(
			superCls,
			browseMode.BrowseModeDocumentTreeInterceptor
		):
			return superCls
		return getDynamicClass(superCls, WebAccessBmdti)
