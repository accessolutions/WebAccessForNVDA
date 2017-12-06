# globalPlugins/webAccess/webModuleHandler/webModule/webModule.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2016 Accessolutions (http://accessolutions.fr)
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


__version__ = "2017.09.17"

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

from .. import json
from .. import presenter
from .. import ruleHandler
from ..webAppLib import *


class WebModule(baseObject.ScriptableObject):
	url = None
	name = None
	windowTitle = None
	markerManager = None
	treeInterceptor = None
	widgetManager = None
	activeWidget = None
	presenter = None
	userDefined = False

	def __init__(self, data=None, jsonFile=None):
		super(WebModule, self).__init__()
		self.jsonDataFile = jsonFile
		self.activePageTitle = None
		self.activePageIdentifier = None
		from .. import widgets
		self.widgetManager = widgets.WidgetManager(self)
		self.activeWidget = None
		self.presenter = presenter.Presenter(self)
		self.markerManager = ruleHandler.MarkerManager(self)

		self.load(data)
		if self.name is None:
			log.error("No web module defined in the configuration data: %s" % data)
			raise Exception("No web module defined in the configuration data.")
		# log.info("Loaded %s: url = %s, windowTitle = %s" %(self.name, self.url, self.windowTitle))
	
	def __str__(self):
		return "webApp %s" % (self.name) if self.name is not None else "<noName>"

	def dump(self):
		data = {}
		if self.markerManager is None:
			log.info("Web module has no marker manager: %s" % self.name)
		else:
			queriesData = self.markerManager.getQueriesData(onlyUser=True)
			if len(queriesData) > 0:
				data["Rules"] = queriesData
			else:
				data["Rules"] = []
		# TODO: Implement field labels saving
		if self.userDefined:
			data["WebModule"] = {
				"name": self.name,
				"url": self.url,
				"windowTitle": self.windowTitle,
				}
		return data
	
	def load(self, data):
		if data is None:
			log.info("%s: No data to load" % self.name)
			return True
		item = data["WebModule"] if "WebModule" in data \
			else data["WebApp"] if "WebApp" in data \
			else None
		if item is not None:
			if "name" in item:
				self.name = item["name"]
			if self.url is not None and isinstance(self.url, basestring):
				self.url = [self.url]
			else:
				self.url = []
			if "url" in item:
				url = item["url"]
				if isinstance(url, basestring):
					self.url.append(url)
				else:
					self.url.extend(url)
			if "windowTitle" in item:
				self.windowTitle = item["windowTitle"]
			self.userDefined = True
		del item
		items = data["Rules"] if "Rules" in data \
			else data["PlaceMarkers"] if "PlaceMarkers" in data \
			else None
		if items is not None:
			self.markerManager.setQueriesData(items)
		del items
		if "FieldLabels" in data:
			# Load custom labels for certain fields
			log.info("Labels not supported")
		return True
	
	def _get_pageTitle(self):
		title = self.markerManager.getPageTitle ()
		if title is None:
			title = api.getFocusObject().windowText
		return title

	def getPresentationConfig(self):
		return {
			'braille.stripBlanks': True,
			}
	
	def setFocusToWebApp(self, webAppName):
		return setFocusToWebApp(self, webAppName)

	def event_webApp_init(self, obj, nextHandler):
		self.loadUserFile()
		nextHandler()

	def event_webApp_pageChanged(self, pageTitle, nextHandler):
		speech.cancelSpeech ()
		playWebAppSound ("pageChanged")
		speech.speakMessage (pageTitle)
	
	def event_webApp_gainFocus(self, obj, nextHandler):
		if obj.role not in [controlTypes.ROLE_DOCUMENT, controlTypes.ROLE_FRAME, controlTypes.ROLE_INTERNALFRAME]:
			nextHandler()

	def event_focusEntered(self, obj, nextHandler):
		if obj.role != controlTypes.ROLE_DOCUMENT:
			nextHandler()

	def event_gainFocus(self, obj, nextHandler):
		global activeWebApp
		global sheduler
		if False and activeWebApp is not None:
			speech.speakMessage (u"trace")
			scheduler.send (eventName="gainFocus",  obj=obj)
			return
		nextHandler()

	def event_webApp_loseFocus(self, obj, nextHandler):
		playWebAppSound ("webAppLoseFocus")
		nextHandler()
		
	def event_webApp_checkPendingActions(self, obj, nextHandler):
		self.markerManager.checkPendingActions()
		nextHandler()
		
	def claimForJABObject(self, obj):
		return False

	def script_essai (self, gesture):
		obj = api.getNavigatorObject ()
		html = obj.HTMLNode
		c = html.attributes.item ("class").nodeValue
		ui.message (u"class:%s" % c)

	def script_sayTitle(self, gesture):
		titleObj = api.getFocusObject()
		windowTitle = titleObj.windowText
		try:
			webAppTitle = self.pageTitle
		except Exception, e:
			log.exception("Error retrieving webApp title: %s" % e)
			webAppTitle = windowTitle
		if webAppTitle is None or webAppTitle == "":
			webAppTitle = windowTitle
		ui.message (webAppTitle)

	def script_sayWebAppName(self, gesture):
		# Translators: Speak name of current web module
		ui.message (_("Current web module is: %s") % (self.name))

	__gestures = {
		"kb:nvda+t": "sayTitle",
		"kb:nvda+e" : "essai",
		"kb:nvda+shift+t": "sayWebAppName",
	}
	