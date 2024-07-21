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
from ..webAppLib import playWebAppSound
from .. import ruleHandler

class InvalidApiVersion(version.InvalidVersion):
	pass


class WebModuleDataLayer(baseObject.AutoPropertyObject):

	def __init__(self, name, data, storeRef, rulesOnly=False, readOnly=None):
		self.name = name
		self.data = data
		self.storeRef = storeRef
		self.rulesOnly = rulesOnly
		if readOnly is not None:
			self.readOnly = readOnly
		self.dirty = False

	def __repr__(self):
		return "<WebModuleDataLayer (name={!r}, storeRef={!r}, rulesOnly={!r}".format(
			self.name, self.storeRef, self.rulesOnly
		)

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

	API_VERSION = version.parse("0.5")

	FORMAT_VERSION_STR = "0.10-dev"
	FORMAT_VERSION = version.parse(FORMAT_VERSION_STR)

	def __init__(self):
		super().__init__()
		self.layers = []  # List of `WebModuleDataLayer` instances
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

	def isReadOnly(self):
		try:
			return not bool(self._getWritableLayer())
		except LookupError:
			return True

	def load(self, layerName, index=None, data=None, storeRef=None, rulesOnly=False, readOnly=None):
		for candidateIndex, layer in enumerate(self.layers):
			if layer.name == layerName:
				self.unload(layerName)
				if index is None:
					index = candidateIndex
		if data is not None:
			from .dataRecovery import recover
			recover(data)
			layer = WebModuleDataLayer(layerName, data, storeRef, rulesOnly=rulesOnly)
		elif storeRef is not None:
			from . import store
			layer = store.getData(storeRef)
			layer.name = layerName
			layer.rulesOnly = rulesOnly
			data = layer.data
			from .dataRecovery import recover
			recover(data)
		else:
			data = OrderedDict({"WebModule": OrderedDict()})
			data["WebModule"] = OrderedDict()
			data["WebModule"]["name"] = self.name
			for attr in ("url", "windowTitle"):
				value = getattr(self, attr)
				if value:
					data["WebModule"][attr] = value
			layer = WebModuleDataLayer(layerName, data, storeRef, rulesOnly=rulesOnly)
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
			if layer.rulesOnly:
				continue
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

	def _getWritableLayer(self):
		for layer in reversed(self.layers):
			if not layer.readOnly and not layer.rulesOnly:
				return layer
			break
		raise LookupError("No suitable data layer")

	def _setLayeredProperty(self, name, value):
		layer = self._getWritableLayer()
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

	def event_webApp_init(self, obj, nextHandler):
		self.loadUserFile()
		nextHandler()

	def event_webApp_pageChanged(self, pageTitle, nextHandler):
		speech.cancelSpeech()
		playWebAppSound("pageChanged")
		speech.speakMessage(pageTitle)

	def event_webApp_gainFocus(self, obj, nextHandler):
		if obj.role not in [controlTypes.ROLE_DOCUMENT, controlTypes.ROLE_FRAME, controlTypes.ROLE_INTERNALFRAME]:
			nextHandler()

	def event_focusEntered(self, obj, nextHandler):
		if obj.role != controlTypes.ROLE_DOCUMENT:
			nextHandler()

	def event_gainFocus(self, obj, nextHandler):
		nextHandler()

	def event_webApp_loseFocus(self, obj, nextHandler):
		playWebAppSound("webAppLoseFocus")
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
