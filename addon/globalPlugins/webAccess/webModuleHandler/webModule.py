# globalPlugins/webAccess/webModuleHandler/webModule.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2021 Accessolutions (http://accessolutions.fr)
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

# Keep compatible with Python 2
from __future__ import absolute_import, division, print_function

__version__ = "2021.09.10"
__author__ = (
	"Yannick Plassiard <yan@mistigri.org>, "
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>, "
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
	)


from collections import OrderedDict
import os

import addonHandler
addonHandler.initTranslation()
import api
import baseObject
import braille
import controlTypes
import globalVars
from logHandler import log
import scriptHandler
import speech
import ui

from ..lib.packaging import version
# from .. import presenter
from .. import ruleHandler
from ..ruleHandler import ruleTypes
from ..webAppLib import *


try:
	import json
except ImportError:
	from ..lib import json

try:
	from six import string_types, text_type
except ImportError:
	# NVDA version < 2018.3
	string_types = basestring
	text_type = unicode


class NewerFormatVersion(version.InvalidVersion):
	pass


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
		return u"<WebModuleDataLayer (name={!r}, storeRef={!r}, rulesOnly={!r}".format(
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
	
	API_VERSION = version.parse("0.4")
	
	FORMAT_VERSION_STR = "0.6-dev"
	FORMAT_VERSION = version.parse(FORMAT_VERSION_STR)
	
	def __init__(self):
		super(WebModule, self).__init__()
		self.layers = []  # List of `WebModuleDataLayer` instances
		self.activePageTitle = None
		self.activePageIdentifier = None
		# from .. import widgets
		# self.widgetManager = widgets.WidgetManager(self)
#		self.activeWidget = None
		# self.presenter = presenter.Presenter(self)
		self.ruleManager = self.markerManager = ruleHandler.MarkerManager(self)
	
# 	def __del__(self):
# 		del self.ruleManager, self.markerManager
# 		super(WebModule, self).__del__()
	
	def __repr__(self):
		return u"WebModule {name}".format(
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
				title = self.markerManager.getPageTitle()
			except Exception:
				log.exception(
					u'Error while retrieving page title'
					u' in WebModule "{}"'.format(
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
			recover(data)
			layer = WebModuleDataLayer(layerName, data, storeRef, rulesOnly=rulesOnly)
		elif storeRef is not None:
			from . import store
			layer = store.getData(storeRef)
			layer.name = layerName
			layer.rulesOnly = rulesOnly
			data = layer.data
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
		rules = data.get("Rules")
		if rules:
			self.ruleManager.load(layer=layer.name, index=index, data=rules)	
	
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
		rootDirs = []
		for storeRef in self.alternatives:
			if storeRef[0] == "userConfig":
				rootDirs.append(globalVars.appArgs.configPath)
			elif storeRef[0] == "addons":
				rootDirs.append(os.path.join(globalVars.appArgs.configPath, "addons", storeRef[1]))
		from ..lib.browsableMessage import browsableMessage
		browsableMessage(
			self.help,
			"markdown",
			# Translators: Title of the Contextual Help dialog
			_("Contextual Help"),
			rootDirs,
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
		ui.message(_(u"Current web module is: {name}").format(name=self.name))

	__gestures = {
		"kb:nvda+h": "contextualHelp",
		"kb:nvda+t": "title",
		"kb:nvda+shift+t": "sayWebModuleName",
	}


def recover(data):
	formatVersion = data.get("formatVersion")
	# Ensure compatibility with data files prior to format versioning
	if formatVersion is None:
		formatVersion = ""
		recoverFrom_legacy(data)
	formatVersion = version.parse(formatVersion)
	if formatVersion < version.parse("0.2"):
		recoverFrom_0_2(data)
	if formatVersion < version.parse("0.3"):
		recoverFrom_0_3(data)
	if formatVersion < version.parse("0.4"):
		recoverFrom_0_4(data)
	if formatVersion < version.parse("0.5"):
		recoverFrom_0_5(data)
	if formatVersion < version.parse("0.6"):
		recoverFrom_0_6(data)
	if formatVersion > WebModule.FORMAT_VERSION:
		raise NewerFormatVersion(
			"WebModule format version not supported: {ver}".format(
				ver=formatVersion
			)
		)


def recoverFrom_legacy(data):
	# Back to the "WebAppHandler" days
	if "WebModule" not in data and "WebApp" in data:
		data["WebModule"] = data.pop("WebApp")
	if "Rules" not in data and "PlaceMarkers" in data:
		data["Rules"] = data.pop("PlaceMarkers")
	# Earlier versions supported only a single URL trigger
	url = data.get("WebModule", {}).get("url", None)
	if isinstance(url, string_types):
		data["WebModule"]["url"] = [url]
	# Custom labels for certain fields are not supported anymore
	# TODO: Re-implement custom field labels?
	if "FieldLabels" in data:
		log.warning("FieldLabels not supported")


def recoverFrom_0_2(data):
	rules = data.get("Rules", [])
	for rule in rules:
		if "context" in rule:
			rule["requiresContext"] = rule.pop("context")
		if "isContext" in rule:
			if rule.get("isContext"):
				rule["definesContext"] = "pageId"
			del rule["isContext"]


def recoverFrom_0_3(data):
	rules = data.get("Rules", [])
	for rule in rules:
		if rule.get("autoAction") == "noAction":
			del rule["autoAction"]


def recoverFrom_0_4(data):
	markerKeys = (
		"gestures", "autoAction", "skip",
		"multiple", "formMode", "sayName",
	)
	splitTitles = []
	splitMarkers = []
	rules = data.get("Rules", [])
	for rule in rules:
		rule.setdefault("type", ruleTypes.MARKER)
		if rule.get("definesContext") and rule.get("isPageTitle"):
				split = rule.copy()
				del rule["isPageTitle"]
				split["type"] = ruleTypes.PAGE_TITLE_1
				split["name"] = u"{} (title)".format(rule["name"])
				for key in markerKeys:
					try:
						del split[key]
					except KeyError:
						pass
				splitTitles.append(split)
				log.warning((
					u'Web module \"{module}\" - rule "{rule}": '
					u'Splitting "isPageTitle" from "definesContext".'
				).format(
					module=data.get("WebModule", {}).get("name"),
					rule=rule.get("name")
				))
		elif rule.get("definesContext"):
			if rule["definesContext"] in ("pageId", "pageType"):
				rule["type"] = ruleTypes.PAGE_TYPE
			else:
				rule["type"] = ruleTypes.PARENT
			reason = "definesContext"
		elif rule.get("isPageTitle"):
			rule["type"] = ruleTypes.PAGE_TITLE_1
			reason = "isPageTitle"
		else:
			reason = None
		if reason:
			if (
				rule.get("gestures")
				or rule.get("autoAction")
				or not rule.get("skip", False)
			):
				split = rule.copy()
				del split[reason]
				split["type"] = ruleTypes.MARKER
				split["name"] = u"{} (marker)".format(rule["name"])
				splitMarkers.append(split)
				log.warning((
					u'Web module \"{module}\" - rule "{rule}": '
					u'Splitting "{reason}" from marker.'
				).format(
					module=data.get("WebModule", {}).get("name"),
					rule=rule.get("name"),
					reason=reason
				))
			for key in markerKeys:
				try:
					del rule[key]
				except KeyError:
					pass
	
	rules.extend(splitTitles)
	rules.extend(splitMarkers)

	for rule in rules:
		if rule.get("requiresContext"):
			rule["contextPageType"] = rule["requiresContext"]
			log.warning(
				u"Web module \"{module}\" - rule \"{rule}\": "
				u"Property \"requiresContext\" has been copied to " 
				u"\"contextPageType\", which is probably not accurate. "
				u"Please redefine the required context.".format(
					module=data.get("WebModule", {}).get("name"),
					rule=rule.get("name")
				)
			)
		
		for key in (
			"definesContext",
			"requiresContext",
			"isPageTitle"
		):
			try:
				del rule[key]
			except KeyError:
				pass
		
		# If it is upper-case (as in non-normalized identifiers),
		# `keyboardHandler.KeyboardInputGesture.getDisplayTextForIdentifier`
		# does not properly handle the NVDA key. 
		gestures = rule.get("gestures", {})
		# Get ready for Python 3: dict.items will return an iterator.
		for key, value in list(gestures.items()):
			if "NVDA" not in key:
				continue
			del gestures[key]
			key = key.replace("NVDA", "nvda")
			gestures[key] = value				


def recoverFrom_0_5(data):
	# Rules: New "states" criterion (#5)
	# Rules: Ignore more whitespace in criteria expressions (19f772b)
	# Rules: Support composition of the "role" criterion (#6)
	rules = data.get("Rules", [])
	for rule in rules:
		if "role" in rule:
			rule["role"] = text_type(rule["role"])


def recoverFrom_0_6(data):
	# Browsers compatibility: Handle "tag" case inconsistency (da96341)
	# Mutate controls (#9)
	rules = data.get("Rules", [])
	for rule in rules:
		if rule.get("tag"):
			rule["tag"] = rule["tag"].lower()
