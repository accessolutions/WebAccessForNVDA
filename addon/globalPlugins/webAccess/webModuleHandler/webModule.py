# globalPlugins/webAccess/webModuleHandler/webModule.py
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

# Get ready for Python 3
from __future__ import absolute_import, division, print_function

__version__ = "2019.07.19"
__author__ = (
	"Yannick Plassiard <yan@mistigri.org>, "
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>, "
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
	)


import os

import addonHandler
addonHandler.initTranslation()
import api
import baseObject
import braille
import controlTypes
from logHandler import log
import scriptHandler
import speech
import ui

from ..packaging import version
from .. import presenter
from .. import ruleHandler
from ..ruleHandler import ruleTypes
from ..webAppLib import *


try:
	import json
except ImportError:
	from .. import json

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


class WebModule(baseObject.ScriptableObject):
	
	API_VERSION = version.parse("0.1")
	FORMAT_VERSION_STR = "0.6-dev"
	FORMAT_VERSION = version.parse(FORMAT_VERSION_STR)
	
	url = None
	name = None
	windowTitle = None
	markerManager = None
	widgetManager = None
	activeWidget = None
	presenter = None

	def __init__(self, data=None):
		super(WebModule, self).__init__()
		self.activePageTitle = None
		self.activePageIdentifier = None
		from .. import widgets
		self.widgetManager = widgets.WidgetManager(self)
		self.activeWidget = None
		self.presenter = presenter.Presenter(self)
		self.ruleManager = self.markerManager = ruleHandler.MarkerManager(self)

		self.load(data)
		if self.name is None:
			log.error(u"No web module defined in the configuration data: %s" % data)
			raise Exception("No web module defined in the configuration data.")
	
	def __str__(self):
		return u"WebModule {name}".format(
			name=self.name if self.name is not None else "<noName>"
		)
	
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
	
	def dump(self):
		data = {"formatVersion": self.FORMAT_VERSION_STR}
		
		data["WebModule"] = {
			"name": self.name,
			"url": self.url,
			"windowTitle": self.windowTitle,
		}
		
		if self.markerManager is None:
			# Do not risk to erase an existing data file while in an
			# unstable state.
			raise Exception(
				"WebModule has no marker manager: {name}"
				"".format(name=self.name)
			)
		else:
			queriesData = self.markerManager.getQueriesData()
			if len(queriesData) > 0:
				data["Rules"] = queriesData
			else:
				data["Rules"] = []
		return data
	
	def load(self, data):
		if data is None:
			log.info(u"%s: No data to load" % self.name)
			return True
		
		formatVersion = data.get("formatVersion")
		# Ensure compatibility with data files prior to format versioning
		if formatVersion is None:
			formatVersion = ""
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
		
		formatVersion = version.parse(formatVersion)
		
		rules = data.get("Rules", [])
		
		if formatVersion < version.parse("0.2"):
			for rule in rules:
				if "context" in rule:
					rule["requiresContext"] = rule.pop("context")
				if "isContext" in rule:
					if rule.get("isContext"):
						rule["definesContext"] = "pageId"
					del rule["isContext"]
		
		if formatVersion < version.parse("0.3"):
			for rule in rules:
				if rule.get("autoAction") == "noAction":
					del rule["autoAction"]
		
		if formatVersion < version.parse("0.4"):
			markerKeys = (
				"gestures", "autoAction", "skip",
				"multiple", "formMode", "sayName",
			)
			splitTitles = []
			splitMarkers = []
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
		
		# Rules: New "states" criterion (#5)
		# Rules: Ignore more whitespace in criteria expressions (19f772b)
		# Rules: Support composition of the "role" criterion (#6)
		if formatVersion < version.parse("0.5"):
			for rule in rules:
				if "role" in rule:
					rule["role"] = text_type(rule["role"])
		
		# Browsers compatibility: Handle "tag" case inconsistency (da96341)
		# Mutate controls (#9)
		if formatVersion < version.parse("0.6"):
			for rule in rules:
				if rule.get("tag"):
					rule["tag"] = rule["tag"].lower()
		
		if formatVersion > self.FORMAT_VERSION:
			raise NewerFormatVersion(
				"WebModule format version not supported: {ver}".format(
					ver=formatVersion
				)
			)
		item = data.get("WebModule")
		if item is not None:
			if "name" in item:
				self.name = item["name"]
			else:
				log.warning("WebModule has no name")
			if "url" in item:
				url = item["url"]
				if not isinstance(url, list):
					log.warning(
						"Unexpected WebModule/url: "
						"{url}".format(url)
						)
				else:
					self.url = url
			if "windowTitle" in item:
				self.windowTitle = item["windowTitle"]
		del item
		items = data.get("Rules")
		if items is not None:
			self.markerManager.setQueriesData(items)
		del items
		return True
	
	_cache_pageTitle = False
	
	def _get_pageTitle(self):
		title = self.activePageTitle
		if not title:
			try:
				title = self.markerManager.getPageTitle()
			except:
				log.exception(
					u'Error while retrieving page title'
					u' in WebModule "{}"'.format(
						self.name
					)
				)
		if not title:
			title = api.getForegroundObject().name
		return title

	def getPresentationConfig(self):
		return {
			'braille.stripBlanks': True,
			}
	
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
		
	def claimForJABObject(self, obj):
		return False

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
		"kb:nvda+t": "title",
		"kb:nvda+shift+t": "sayWebModuleName",
	}
	