# globalPlugins/webAccess/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2018 Accessolutions (http://accessolutions.fr)
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

"""Core web module support.

This implements the main web module mechanisms including :
* web module searching and loading, either from a .py or JSON file.
* dispatching events to the active web module
* handling scripts for the active web module

Special objects:

* ruleHandler: Allows users to place markers onto a web page and associate
scripts to them.

* NodeManager: Creates a tree-based representation of the web content.
This is used to search for a specific class, tag, role, id, and so on in an
efficient way throughout the whole web page.

* WidgetManager: Allows web app creators to create and use widgets to identify
and navigate into specific elements such as eg. tab bars, button bars, or
tables.

* Presenter: Used to display information using speech and/or braille output
based on the current context (widget, nodeField, or object).

Overridden NVDA functions:
* EventExecuter.gen
* scriptHandler.findScript
"""

from __future__ import absolute_import

__version__ = "2018.07.06"

__author__ = (
	"Yannick Plassiard <yan@mistigri.org>, "
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>, "
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
	)


import os
import imp
import re
import sys
import time
import wx

import addonHandler
addonHandler.initTranslation()
import api
import baseObject
import braille
import config
import controlTypes
import eventHandler
import globalPluginHandler
import globalVars
import gui
import inputCore
from logHandler import log
import NVDAObjects
from NVDAObjects import NVDAObject, JAB
import scriptHandler
import speech
import tones
import ui
import virtualBuffers
import queueHandler

from . import json
from . import nodeHandler
from . import presenter
from . import webAppLib
from .webAppLib import *
from .webAppScheduler import WebAppScheduler
from . import webModuleHandler
from .webModuleHandler import webModule
from . import widgets


#
# defines sound directory
#

SOUND_DIRECTORY = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "sounds")



supportedWebAppHosts = ['firefox', 'chrome', 'java', 'iexplore', 'microsoftedgecp']

activeWebApp = None
useInternalBrowser = False
webAccessEnabled = True
scheduler = None

class DefaultBrowserScripts(baseObject.ScriptableObject):
	
	def __init__(self, warningMessage):
		super(DefaultBrowserScripts,self).__init__()
		self.warningMessage = warningMessage
		for ascii in range(ord("a"), ord("z")+1):
			character = chr(ascii)
			self.__class__.__gestures["kb:control+shift+%s" % character] = "notAssigned"

	def script_notAssigned(self, gesture):
		playWebAppSound("keyError")
		sleep(0.2)
		ui.message(self.warningMessage)

	__gestures = {}

defaultBrowserScripts = DefaultBrowserScripts(u"Pas de web module pour cette page")


def getVersion():
	try:
		thisPath = os.path.abspath(
			os.path.join(
				os.path.split(__file__)[0],
				"..\.."
				)
			)
		for addon in addonHandler.getAvailableAddons():
			addonPath = os.path.abspath(addon.path)
			if addonPath == thisPath:
				return addon.manifest["version"]
	except:
		log.exception("While retrieving addon version")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	
	def __init__(self):
		super(globalPluginHandler.GlobalPlugin, self).__init__()
		global scheduler
		scheduler = WebAppScheduler()
		scheduler.start ()
		
		baseObject.ScriptableObject.getWebApp = getWebApp
		scriptHandler.findScript = hook_findScript
		eventHandler._EventExecuter.gen = hook_eventGen
		virtualBuffers.VirtualBuffer.save_changeNotify = virtualBuffers.VirtualBuffer.changeNotify
		virtualBuffers.VirtualBuffer.changeNotify = hook_changeNotify
		virtualBuffers.VirtualBuffer.save_loadBufferDone = virtualBuffers.VirtualBuffer._loadBufferDone  
		virtualBuffers.VirtualBuffer._loadBufferDone = hook_loadBufferDone
		virtualBuffers.VirtualBuffer.save_terminate = virtualBuffers.VirtualBuffer.terminate 
		virtualBuffers.VirtualBuffer.terminate = hook_terminate
		
		global mainFrame_prePopup_stock
		mainFrame_prePopup_stock = gui.mainFrame.prePopup
		gui.mainFrame.prePopup = mainFrame_prePopup_patched.__get__(gui.mainFrame, gui.MainFrame)
		global mainFrame_postPopup_stock
		mainFrame_postPopup_stock = gui.mainFrame.postPopup
		gui.mainFrame.postPopup = mainFrame_postPopup_patched.__get__(gui.mainFrame, gui.MainFrame)

		global appModule_nvda_event_NVDAObject_init_stock
		from appModules.nvda import AppModule as NvdaAppModule
		appModule_nvda_event_NVDAObject_init_stock = NvdaAppModule.event_NVDAObject_init
		# The NVDA AppModule should not yet have been instanciated at this stage
		NvdaAppModule.event_NVDAObject_init = appModule_nvda_event_NVDAObject_init_patched 		

		#webModuleHandler.getWebModules(refresh=True)
		log.info("Web Access for NVDA version %s initialized" % getVersion())

	def terminate(self):
		scheduler.send(eventName="stop")
		
	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if activeWebApp is None:
			return
		if hasattr(activeWebApp, 'chooseNVDAObjectOverlayClasses'):
			activeWebApp.chooseNVDAObjectOverlayClasses(obj, clsList)
	
	def script_showWebAccessGui(self, gesture):
		wx.CallAfter(self.showWebAccessGui)
	# Translators: Input help mode message for show Web Access menu command.
	script_showWebAccessGui.__doc__ = _("Shows the Web Access menu.")

	def showWebAccessGui(self):
		obj = api.getFocusObject()		
		if obj is None or obj.appModule is None:
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("The current object does not support Web Access."))
			return
		if not supportWebApp(obj):
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be in a web browser to use Web Access."))
			return
		if obj.treeInterceptor is None:
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be on the web page to use Web Access."))
			return

		from .gui import menu
		context = {}
		context["webAccess"] = self
		context["focusObject"] = obj
		if hasattr(obj, "getWebApp"):
			webModule = obj.getWebApp()
			if webModule is not None:
				context["webModule"] = webModule
		menu.show(context)

	def script_debugWebApp (self, gesture):
		global activeWebApp
		if not activeWebApp:
			ui.message (u"pas de webApp active")
			return
		allMsg = ""
		msg = u"webApp %s" % activeWebApp.name
		speech.speakMessage (msg)
		allMsg += msg + "\r\n"
		
		treeInterceptor = html.getTreeInterceptor ()
		msg = u"nodeManager %d caractères, %s, %s" % (treeInterceptor.nodeManager.treeInterceptorSize, treeInterceptor.nodeManager.isReady, treeInterceptor.nodeManager.mainNode is not None)
		speech.speakMessage (msg)
		allMsg += msg + "\r\n"
		api.copyToClip (allMsg)
		 
	def script_toggleWebAccessSupport(self, gesture):
		global useInternalBrowser
		global webAccessEnabled

		if webAccessEnabled:
			useInternalBrowser = False
			webAccessEnabled = False
			ui.message(_("Web Access support disabled."))  # FR: u"Support Web Access désactivé."
		else:
			#useInternalBrowser = True
			webAccessEnabled = True
			ui.message(_("Web Access support enabled."))  # FR: u"Support Web Access activé."

	__gestures = {
		"kb:nvda+w": "showWebAccessGui",
		"kb:nvda+shift+w": "toggleWebAccessSupport",
		"kb:nvda+control+w" : "debugWebApp"
	}
	

def getActiveWebApp ():
	global activeWebApp
	return activeWebApp

def webAppLoseFocus(obj):
	global activeWebApp
	if activeWebApp is not None:
		sendWebAppEvent('webApp_loseFocus', obj, activeWebApp)
		activeWebApp = None
		#log.info("Losing webApp focus for object:\n%s\n" % ("\n".join(obj.devInfo)))

def supportWebApp (obj):
	if obj is None or obj.appModule is None:
		return None
	return  obj.appModule.appName in supportedWebAppHosts
	

def getWebApp(self, eventName=None):
	global activeWebApp
	global webAccessEnabled

	if not webAccessEnabled or not supportWebApp (self):
		return None
	
	obj = self

	if hasattr (obj, "_webApp"):
		return obj._webApp
	
	webApp = None
	objList = []

	# Before anything, check if the webApp window title matches the actuel one.
	if len(obj.windowText) > 0:
		for app in webModuleHandler.getWebModules():
			if app.windowTitle is not None and len(app.windowTitle) > 0 and app.windowTitle in obj.windowText:
				webApp = app
				break

	i = 0
	while webApp is None and obj is not None and i < 50:
		i += 1
		if hasattr(obj, '_webApp'):
			webApp = obj._webApp
			break

		objList.append(obj)

		# For Java Apps we can't rely on URLs so call a specific method, if implemented
		wa = getWebAppFromObject(obj, eventName)
		if wa:
			webApp = wa
			break
		
		# On HTML webApps, we extract the URL from the document IAccessible value.
		if obj.role == controlTypes.ROLE_DOCUMENT:
			try:
				#log.info (u"obj.IAccessibleChildID : %s" % obj.IAccessibleChildID)
				url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
			except: 
				url = None
			if url:
				webApp = getWebAppFromUrl(url)

		obj= obj.parent

	if webApp is None:
		return None

	for o in objList:
		o._webApp = webApp
		
	activeWebApp = webApp
	return webApp 
	# sendWebAppEvent('webApp_loseFocus', self, activeWebApp)
	# sendWebAppEvent('webApp_gainFocus', self, webApp)
	# sendWebAppEvent('webApp_checkPendingActions', self, webApp)
	# sendWebAppEvent('webApp_pageChanged', wPageTitle, activeWebApp)

@classmethod
def hook_changeNotify(cls, rootDocHandle, rootID):
	#log.info (u"change notify")
	virtualBuffers.VirtualBuffer.save_changeNotify (rootDocHandle, rootID)

def hook_terminate (self):
	if hasattr (self, "nodeManager"):
		self.nodeManager.terminate ()
		del self.nodeManager  
	virtualBuffers.VirtualBuffer.save_terminate (self)
	
def hook_loadBufferDone(self, success=True):
	#log.info (u"load buffer done")
	self._loadProgressCallLater.Stop()
	del self._loadProgressCallLater
	self.isLoading = False
	if not success:
		self.passThrough=True
		return
	if self._hadFirstGainFocus:
		# If this buffer has already had focus once while loaded, this is a refresh.
		# Translators: Reported when a page reloads (example: after refreshing a webpage).
		speech.speakMessage(_("Refreshed"))
	focus=api.getFocusObject()
	if api.getFocusObject().treeInterceptor == self:
		if hasattr(api.getFocusObject (), 'webApp'):
			firstGainFocus = self._hadFirstGainFocus
			#self._hadFirstGainFocus = True
			scheduler.send (eventName="treeInterceptor_gainFocus", treeInterceptor=self, firstGainFocus=firstGainFocus)
		else:
			self.event_treeInterceptor_gainFocus()


def hook_findScript(gesture, searchWebApp=True):
	global activeWebApp
	global useInternalBrowser
	global webAccessEnabled
	global defaultBrowserScripts

	focus = api.getFocusObject()
	if not focus:
		return None

	# Import late to avoid circular import.
	# We need to import this here because this might be the first import of this module
	# and it might be needed by global maps.
	import globalCommands

	globalMapScripts = []
	globalMaps = [inputCore.manager.userGestureMap, inputCore.manager.localeGestureMap]
	globalMap = braille.handler.display.gestureMap
	if globalMap:
		globalMaps.append(globalMap)
	for globalMap in globalMaps:
		# Changed from `identifiers` to `normalizedIdentifier in NVDA 2017.4
		# (new member introduced in NVDA 2017.2)
		for identifier in \
				gesture.normalizedIdentifiers \
				if hasattr(gesture, "normalizedIdentifiers") \
				else gesture.identifiers:
			globalMapScripts.extend(globalMap.getScriptsForGesture(identifier))
			
	# Gesture specific scriptable object.
	obj = gesture.scriptableObject
	if obj:
		func = scriptHandler._getObjScript(obj, gesture, globalMapScripts)
		if func:
			return func

	# Global plugin default scripts.
	for plugin in globalPluginHandler.runningPlugins:
		func = scriptHandler._getObjScript(plugin, gesture, globalMapScripts)
		if func:
			return func

	# webApp scripts
	webApp = focus.getWebApp ()
	if webApp is not None and searchWebApp is True:
		# Search if a place marker uses this shortcut
		if webApp.markerManager:
			func = webApp.markerManager.getMarkerScript(gesture, globalMapScripts)
			if func:
				return func
		func = scriptHandler._getObjScript(webApp.widgetManager, gesture, globalMapScripts)
		if func:
			return func
		activeWidget = getattr(webApp, 'activeWidget', None)
		if activeWidget is not None:
			func = scriptHandler._getObjScript(activeWidget, gesture, globalMapScripts)
			if func:
				return func
						
		func = scriptHandler._getObjScript(webApp, gesture, globalMapScripts)
		if func:
			return func
		#ti = webApp.treeInterceptor
		if False and hasattr(ti, 'nodeManager') and (useInternalBrowser is True or activeWidget is not None):
			func = scriptHandler._getObjScript(webApp.presenter, gesture, globalMapScripts)
			if func:
				return func
			func = scriptHandler._getObjScript(ti.nodeManager, gesture, globalMapScripts)
			if func:
				return func

	# App module default scripts.
	app = focus.appModule
	if app:
		# browsers default scripts.
		if supportWebApp (focus):
			func = scriptHandler._getObjScript(defaultBrowserScripts, gesture, globalMapScripts)
			if func:
				return func
		func = scriptHandler._getObjScript(app, gesture, globalMapScripts)
		if func:
			return func

	# Tree interceptor level.
	treeInterceptor = focus.treeInterceptor
	if treeInterceptor and treeInterceptor.isReady:
		func = scriptHandler._getObjScript(treeInterceptor, gesture, globalMapScripts)
		from browseMode import BrowseModeTreeInterceptor
		if isinstance(treeInterceptor,BrowseModeTreeInterceptor):
			func=treeInterceptor.getAlternativeScript(gesture,func)
			if func and (not treeInterceptor.passThrough or getattr(func,"ignoreTreeInterceptorPassThrough",False)) and (useInternalBrowser is False or getattr(activeWebApp, 'activeWidget', None) is None):
				return func

	# NVDAObject level.
	func = scriptHandler._getObjScript(focus, gesture, globalMapScripts)
	if func:
		return func
	for obj in reversed(api.getFocusAncestors()):
		func = scriptHandler._getObjScript(obj, gesture, globalMapScripts)
		if func and getattr(func, 'canPropagate', False): 
			return func

	# Global commands.
	func = scriptHandler._getObjScript(globalCommands.commands, gesture, globalMapScripts)
	if func:
		return func
	return None

def sendWebAppEvent(eventName, obj, webApp=None):
	if webApp is None:
		return
	scheduler.send (eventName="webApp", name=eventName, obj=obj, webApp=webApp)

def hook_eventGen(self, eventName, obj):
	#log.info("Event %s : %s : %s" % (eventName, obj.name, obj.value))
	global useInternalBrowser

	funcName = "event_%s" % eventName

	# Global plugin level.
	for plugin in globalPluginHandler.runningPlugins:
		func = getattr(plugin, funcName, None)
		if func:
			yield func, (obj, self.next)

	# webApp level
	if  not supportWebApp (obj) and eventName in ["gainFocus"] and activeWebApp is not None:
		# log.info("Received event %s on a non-hosted object" % eventName)
		webAppLoseFocus(obj)
	else:
		webApp = obj.getWebApp(eventName)
		if webApp is None:
			if activeWebApp is not None and obj.hasFocus:
				#log.info("Disabling active webApp event %s" % eventName)
				webAppLoseFocus(obj)
		else:
			# log.info("Getting method %s -> %s" %(webApp.name, funcName))
			if webApp.widgetManager.claimVirtualBufferWidget(nodeHandler.REASON_FOCUS) is False:
				webApp.widgetManager.claimObject(obj)
			if webApp.activeWidget is not None:
				func = getattr(webApp.activeWidget, funcName, None)
				if func:
					yield func,(obj, self.next)
			func = getattr(webApp, funcName, None)
			if func:
				yield func,(obj, self.next)

	# App module level.
	app = obj.appModule
	if app:
		func = getattr(app, funcName, None)
		if func:
			yield func, (obj, self.next)

	# Use a Presenter object to speak/braille the content
	presented = False
	if eventName == 'caret' and activeWebApp is not None and useInternalBrowser is True:
		presented = True
	# Tree interceptor level.
	treeInterceptor = obj.treeInterceptor
	if presented is False and treeInterceptor:
		func = getattr(treeInterceptor, funcName, None)
		if func and (getattr(func,'ignoreIsReady',False) or treeInterceptor.isReady):
			yield func, (obj, self.next)

	# NVDAObject level.
	func = getattr(obj, funcName, None)
	if func:
		if obj.name is not None and "http" in obj.name and obj.role in [controlTypes.ROLE_DOCUMENT, controlTypes.ROLE_FRAME]:
			return
		yield func, ()

def getWebAppFromObject(obj, eventName):
	# log.info("Searching for object webapp eventName = %s" % eventName)
	if eventName not in ("gainFocus", "becomeNavigatorObject"):
		return None
	for app in webModuleHandler.getWebModules():
		# log.info("object class is %s" % obj.__class__)
		if hasattr(app, "claimObjectClasses"):
			for cls in obj.__class__.__mro__:
				if cls in app.claimObjectClasses:
					log.info("app %s can claim for object %s" %(app.name, str(obj.__class__)))
					if app.claimForJABObject(obj) is True:
						return app
	return None

def getWebAppFromUrl(url):
	if url is None:
		return None
	matchedLen = 0
	matchedWebApp = None
	for webApp in webModuleHandler.getWebModules():
		if webApp.url is None:
			continue
		if isinstance(webApp.url, tuple) or isinstance(webApp.url, list):
			urls = webApp.url
		else:
			urls = [webApp.url]
		for wUrl in urls:
			if wUrl in url and len(wUrl) > matchedLen:
				# log.info("Webapp candidate url %s, len %d" % (wUrl, len(wUrl)))
				matchedWebApp = webApp
				matchedLen = len(wUrl)
	return matchedWebApp

def setFocusToWebApp(srcApp, webAppName):
	global activeWebApp

	if activeWebApp == srcApp:
		log.info("Posting setFocus event to ourself is not allowed.")
		return True
	for app in webModuleHandler.getWebModules():
		if app.name == webAppName:
			sendWebAppEvent('event_webApp_setFocus', srcApp, app)
			return True
	log.info("Set focus to webApp %s failed: Application not found.", webAppName)
	return False

def mainFrame_prePopup_patched(self, contextMenuName=None):
	global mainFrame_prePopup_stock, popupContextMenuName
	popupContextMenuName = contextMenuName
	mainFrame_prePopup_stock()  # Stock method was stored bound

def mainFrame_postPopup_patched(self):
	global mainFrame_postPopup_stock, popupContextMenuName
	popupContextMenuName = None
	mainFrame_postPopup_stock()  # Stock method was stored bound

def appModule_nvda_event_NVDAObject_init_patched(self, obj):
	import controlTypes
	from appModules.nvda import AppModule as NvdaAppModule
	global appModule_nvda_event_NVDAObject_init_stock, popupContextMenuName
	from NVDAObjects.IAccessible import IAccessible
	if (
			"popupContextMenuName" in globals()
			and popupContextMenuName is not None
			and isinstance(obj, IAccessible)
			and obj.role == controlTypes.ROLE_POPUPMENU
			):
		obj.name = popupContextMenuName
		popupContextMenuName = None
	# Stock method was stored unbound
	appModule_nvda_event_NVDAObject_init_stock.__get__(self, NvdaAppModule)(obj)

