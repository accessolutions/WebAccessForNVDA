# globalPlugins/webAccess/webModuleHandler/webModule.py
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


__authors__ = (
	"Yannick Plassiard <yan@mistigri.org>",
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


from collections import OrderedDict
import datetime
import json
import os
import sys

import addonHandler
addonHandler.initTranslation()
import api
import baseObject
import braille
import config
import controlTypes
import globalVars
from logHandler import log
import scriptHandler
import speech
import ui
from ..lib.markdown2 import markdown
from ..lib.packaging import version
from ..webAppLib import playWebAccessSound
from .. import ruleHandler

if sys.version_info[1] < 9:
    from typing import Sequence
else:
    from collections.abc import Sequence


class InvalidApiVersion(version.InvalidVersion):
	pass


class WebModuleDataLayer(baseObject.AutoPropertyObject):

	def __init__(self, name, data, storeRef, readOnly=None):
		self.name = name
		self.data = data
		self.storeRef = storeRef
		if readOnly is not None:
			self.readOnly = readOnly
		self.dirty = False

	def __repr__(self):
		return "<WebModuleDataLayer (name={!r}, storeRef={!r}>".format(self.name, self.storeRef)

	def _get_readOnly(self):
		storeRef = self.storeRef
		if storeRef is not None:
			if not (isinstance(storeRef, tuple) and len(storeRef) > 1):
				log.error("Unhandled storeRef format: {!r}".format(storeRef))
				return False
			storeName = self.storeRef[0]
			if storeName == "userConfig":
				if config.conf["webAccess"]["disableUserConfig"]:
					return True
			elif storeName == "scratchpad":
				if not config.conf["webAccess"]["devMode"]:
					return True
			elif storeName == "addons":
				if not (
					config.conf["webAccess"]["devMode"]
					and config.conf["webAccess"]["writeInAddons"]
				):
					return True
		return False


class WebModule(baseObject.ScriptableObject):

	API_VERSION = version.parse("0.6")

	FORMAT_VERSION_STR = "0.10-dev"
	FORMAT_VERSION = version.parse(FORMAT_VERSION_STR)

	def __init__(self):
		super().__init__()
		self.layers: Sequence[WebModuleDataLayer] = []
		self.activePageTitle = None
		self.activePageIdentifier = None
		self.ruleManager = ruleHandler.RuleManager(self)

	def __repr__(self):
		return "WebModule {name}".format(
			name=self.name if self.name is not None else "<noName>"
		)

	def _get_help(self):
		return self._getLayeredProperty("help")

	def _set_help(self, value):
		self._setLayeredProperty("help", value)

	def _get_name(self):
		return self._getLayeredProperty("name")

	def _set_name(self, value):
		self._setLayeredProperty("name", value)

	_cache_pageTitle = False

	def _get_pageTitle(self):
		title = self.activePageTitle
		if not title:
			try:
				title = self.ruleManager.getPageTitle()
			except Exception:
				log.exception(
					'Error while retrieving page title'
					' in WebModule "{}"'.format(
						self.name
					)
				)
		if not title:
			title = api.getForegroundObject().name
		return title

	def _get_url(self):
		return self._getLayeredProperty("url")

	def _set_url(self, value):
		self._setLayeredProperty("url", value)

	def _get_windowTitle(self):
		return self._getLayeredProperty("windowTitle")

	def _set_windowTitle(self, value):
		self._setLayeredProperty("windowTitle", value)

	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		"""
		Choose NVDAObject overlay classes for a given NVDAObject.

		This works in a similar manner as the methods with the same name in
		AppModule and GlobalPlugin but comes into play much later: It is
		called only when the TreeInterceptor is set on the NVDAObject. Hence,
		if removing a class from the list, beware its earlier presence might
		have had side effects.

		Also, this method should return:
		 - A sequence of the newly classes for which the method
		   `initOverlayClass` should be called once the object is mutated.
		 - `True`, if the object should be mutated but no method should
		   be called.
		 - Any negative value, if the object should not be mutated at all.
		"""
		return False

	def createRule(self, data):
		return ruleHandler.Rule(self.ruleManager, data)

	def dump(self, layerName):
		layer = self.getLayer(layerName, raiseIfMissing=True)
		data = layer.data
		data["formatVersion"] = self.FORMAT_VERSION_STR
		data["Rules"] = self.ruleManager.dump(layerName)
		return layer

	def equals(self, obj):
		"""Check if `obj` represents an instance of the same `WebModule`.
		
		This cannot be achieved by implementing the usual `__eq__` method
		because `baseObjects.AutoPropertyObject.__new__` requires it to
		operate on identity as it stores the instance as key in a `WeakKeyDictionnary`
		in order to later invalidate property cache.
		"""
		if type(self) is not type(obj):
			return False
		if self.name != obj.name:
			return False
		if len(self.layers) != len(obj.layers):
			return False
		for i in range(len(self.layers)):
			l1 = self.layers[i]
			l2 = obj.layers[i]
			if l1.name != l2.name or l1.storeRef != l2.storeRef:
				return False
		return True

	def isReadOnly(self):
		try:
			return not bool(self.getWritableLayer())
		except LookupError:
			return True

	def load(self, layerName, index=None, data=None, storeRef=None, readOnly=None):
		for candidateIndex, layer in enumerate(self.layers):
			if layer.name == layerName:
				self.unload(layerName)
				if index is None:
					index = candidateIndex
		if data is not None:
			from .dataRecovery import recover
			recover(data)
			layer = WebModuleDataLayer(layerName, data, storeRef)
		elif storeRef is not None:
			from . import store
			layer = store.getData(storeRef)
			layer.name = layerName
			data = layer.data
			from .dataRecovery import recover
			recover(data)
		else:
			data = OrderedDict({"WebModule": OrderedDict()})
			data["WebModule"] = OrderedDict()
			data["WebModule"]["name"] = self.name
			for attr in ("url", "windowTitle"):  # FIXME: Why not "help" as whell?
				value = getattr(self, attr)
				if value:
					data["WebModule"][attr] = value
			layer = WebModuleDataLayer(layerName, data, storeRef)
		if index is not None:
			self.layers.insert(index, layer)
		else:
			self.layers.append(layer)
		self.ruleManager.load(layer=layer.name, index=index, data=data.get("Rules", {}))

	def getLayer(self, layerName, raiseIfMissing=False):
		for layer in self.layers:
			if layer.name == layerName:
				return layer
		if raiseIfMissing:
			raise LookupError(repr(layerName))
		return None

	def getWritableLayer(self) -> WebModuleDataLayer:
		"""Retreive the lowest writable layer of this WebModule
		
		See also: `webModuleHandler.getEditableWebModule`
		"""
		for layer in reversed(self.layers):
			if not layer.readOnly:
				return layer
			break
		raise LookupError("No suitable data layer")

	def unload(self, layerName):
		for index, layer in enumerate(self.layers):
			if layer.name == layerName:
				break
		else:
			raise LookupError(layerName)
		self.ruleManager.unload(layerName)
		del self.layers[index]

	def terminate(self):
		self.ruleManager.terminate()

	def _getLayeredProperty(self, name, startLayerIndex=-1, raiseIfMissing=False):
		for index, layer in list(enumerate(self.layers))[startLayerIndex::-1]:
			data = layer.data["WebModule"]
			if name not in data:
				continue
			if index > 0 and name in data.get("overrides", {}):
				overridden = self._getLayeredProperty(name, startLayerIndex=index - 1)
				if overridden != data["overrides"][name]:
					return overridden
			return data[name]
		if raiseIfMissing:
			raise LookupError("name={!r}, startLayerIndex={!r}".format(name, startLayerIndex))

	def _setLayeredProperty(self, name, value):
		layer = self.getWritableLayer()
		data = layer.data["WebModule"]
		if data.get(name) != value:
			layer.dirty = True
			data[name] = value
		if "overrides" in data:
			data["overrides"].pop(name, None)
			try:
				overridden = self._getLayeredProperty(name, startLayerIndex=-2)
			except LookupError:
				return
			if data["overrides"].get(name) != overridden:
				layer.dirty = True
				data["overrides"][name] = overridden

	def event_webModule_pageChanged(self, pageTitle, nextHandler):
		speech.cancelSpeech()
		playWebAccessSound("pageChanged")
		speech.speakMessage(pageTitle)

	# Currently dead code, but will likely be revived for issue #17
	def event_webModule_gainFocus(self, obj, nextHandler):
		if obj.role not in [controlTypes.ROLE_DOCUMENT, controlTypes.ROLE_FRAME, controlTypes.ROLE_INTERNALFRAME]:
			nextHandler()

	# Currently dead code, but will likely be revived for issue #17
	def event_focusEntered(self, obj, nextHandler):
		if obj.role != controlTypes.ROLE_DOCUMENT:
			nextHandler()

	def event_gainFocus(self, obj, nextHandler):
		nextHandler()

	def event_webModule_loseFocus(self, obj, nextHandler):
		playWebAccessSound("webAppLoseFocus")
		nextHandler()

	def script_contextualHelp(self, gesture):
		if not self.help:
			# Translators: Presented when requesting a missing contextual help
			ui.message(_("No contextual help available."))
			return
		ui.browseableMessage(
			markdown(self.help),
			# Translators: Title of the Contextual Help dialog
			_("Contextual Help"),
			True
		)

	def script_title(self, gesture):
		title = self.pageTitle
		repeatCount = scriptHandler.getLastScriptRepeatCount()
		if repeatCount == 0:
			ui.message(title)
		elif repeatCount == 1:
			speech.speakSpelling(title)
		else:
			if api.copyToClip(title):
				ui.message(_("%s copied to clipboard") % title)

	def script_sayWebModuleName(self, gesture):
		# Translators: Speak name of current web module
		ui.message(_("Current web module is: {name}").format(name=self.name))

	__gestures = {
		"kb:nvda+h": "contextualHelp",
		"kb:nvda+t": "title",
		"kb:nvda+shift+t": "sayWebModuleName",
	}
