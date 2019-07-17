# globalPlugins/webAccess/__init__.py
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

# Get ready for Python 3
from __future__ import absolute_import, division, print_function

__version__ = "2019.07.17"
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
from NVDAObjects.IAccessible.MSHTML import MSHTML
from NVDAObjects.IAccessible.ia2Web import Ia2Web
from NVDAObjects.IAccessible.mozilla import Mozilla
import NVDAObjects.JAB
import scriptHandler
import speech
import tones
import ui
import virtualBuffers

from . import nodeHandler
from . import overlay
from . import presenter
from . import webAppLib
from .webAppLib import *
from .webAppScheduler import WebAppScheduler
from . import webModuleHandler
from . import widgets


addonHandler.initTranslation()


TRACE = lambda *args, **kwargs: None  # @UnusedVariable
#TRACE = log.info

SCRIPT_CATEGORY = "WebAccess"

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

	def script_notAssigned(self, gesture):  # @UnusedVariable
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
		scheduler.start()
		
		# TODO: WIP on new coupling 
		# baseObject.ScriptableObject.getWebApp = getWebApp
		# scriptHandler.findScript = hook_findScript
		eventHandler._EventExecuter.gen = hook_eventGen
		virtualBuffers.VirtualBuffer.save_changeNotify = virtualBuffers.VirtualBuffer.changeNotify
		virtualBuffers.VirtualBuffer.changeNotify = hook_changeNotify
		virtualBuffers.VirtualBuffer.save_loadBufferDone = virtualBuffers.VirtualBuffer._loadBufferDone  
		# virtualBuffers.VirtualBuffer._loadBufferDone = hook_loadBufferDone
		virtualBuffers.VirtualBuffer.save_terminate = virtualBuffers.VirtualBuffer.terminate 
		virtualBuffers.VirtualBuffer.terminate = hook_terminate
		
		# Used to announce the opening of the Web Access menu
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

		log.info("Web Access for NVDA version %s initialized" % getVersion())
		showWebModulesLoadErrors()

	def terminate(self):
		scheduler.send(eventName="stop")
		
	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		if any(
			True
			for cls in (Ia2Web, Mozilla, MSHTML)
			if cls in clsList
		):
			if obj.role in (
				controlTypes.ROLE_DIALOG,
				controlTypes.ROLE_DOCUMENT,
			):
				clsList.insert(0, overlay.WebAccessDocument)
				return
			clsList.insert(0, overlay.WebAccessObject)
	
	def script_showWebAccessGui(self, gesture):  # @UnusedVariable
		wx.CallAfter(self.showWebAccessGui)
	
	# Translators: Input help mode message for show Web Access menu command.
	script_showWebAccessGui.__doc__ = _("Show the Web Access menu.")

	script_showWebAccessGui.category = SCRIPT_CATEGORY
	
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
		if obj.treeInterceptor is None or not isinstance(obj, overlay.WebAccessObject):
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be on the web page to use Web Access."))
			return

		from .gui import menu
		context = {}
		context["webAccess"] = self
		context["focusObject"] = obj
		webModule = obj.webAccess.webModule
		if webModule is not None:
			context["webModule"] = webModule
			context["pageTitle"] = webModule.pageTitle
		menu.show(context)
	
	def script_debugWebModule(self, gesture):  # @UnusedVariable
		global activeWebApp
		focus = api.getFocusObject()
		if \
				activeWebApp is None \
				and not hasattr(focus, "_webApp") \
				and not hasattr(focus, "treeInterceptor") \
				and not hasattr(focus.treeInterceptor, "_webApp") \
				and not hasattr(focus.treeInterceptor, "nodeManager"):
			ui.message(u"Pas de WebModule actif")
			return
		
		diverged = False
		focusModule = None
		treeModule = None
		msg = u"Divergence :"
		msg += os.linesep
		msg += u"activeWebApp = {webModule}".format(
			webModule=activeWebApp.storeRef
				if hasattr(activeWebApp, "storeRef")
				else activeWebApp
			)
		if activeWebApp is not None:
			msg += u" ({id})".format(id=id(activeWebApp))
		if not hasattr(focus, "_webApp"):
			msg += os.linesep
			msg += u"focus._webApp absent"
		else:
			focusModule = focus._webApp
			if activeWebApp is not focusModule:
				diverged = True
			msg += os.linesep
			msg += u"focus._webApp = {webModule}".format(
				webModule=
					focusModule.storeRef
					if hasattr(focusModule, "storeRef")
					else focusModule
				)
			if focusModule is not None:
				msg += u" ({id})".format(id=id(focusModule))
		if not hasattr(focus, "treeInterceptor"):
			diverged = True
			msg += os.linesep
			msg += u"focus.treeInterceptor absent"
		else:
			if focus.treeInterceptor is None:
				diverged = True
				msg += os.linesep
				msg += u"focus.treeInterceptor None"
# 			if not hasattr(focusModule, "treeInterceptor"):
# 				diverged = True
# 				msg += os.linesep
# 				msg += u"focus._webApp.treeInterceptor absent"
# 			elif focusModule.treeInterceptor is None:
# 				diverged = True
# 				msg += os.linesep
# 				msg += u"focus._webApp.treeInterceptor None"
# 			elif focus.treeInterceptor is not focusModule.treeInterceptor:
# 				diverged = True
# 				msg += os.linesep
# 				msg += u"TreeInterceptors différents"				
			if hasattr(focus.treeInterceptor, "_webApp"):
				treeModule = focus.treeInterceptor._webApp
				if \
						treeModule is not focusModule \
						or treeModule is not activeWebApp:
					diverged = True
				msg += os.linesep
				msg += u"treeInterceptor._webApp = {webModule}".format(
					webModule=
						treeModule.storeRef
						if hasattr(treeModule, "storeRef")
						else treeModule
					)
				if treeModule is not None:
					msg += u" ({id})".format(id=id(treeModule))
			if hasattr(focus.treeInterceptor, "nodeManager"):
				if focusModule is None:
					diverged = True
					msg += u"treeInterceptor.nodeManager "
					if focus.treeInterceptor.nodeManager is None:
						msg += u"est None"
					else:
						msg += u"n'est pas None"
				elif \
						focusModule.markerManager.nodeManager is not \
						focus.treeInterceptor.nodeManager:
					diverged = True
					msg += os.linesep
					msg += u"NodeManagers différents"
				elif focusModule.markerManager.nodeManager is None:
					msg += os.linesep
					msg += u"NodeManagers None"
					

		allMsg = u""

		if not diverged:
			try:
				from six import text_type
			except ImportError:
				# NVDA version < 2018.3
				text_type = unicode
			msg = text_type(focusModule.storeRef)
		speech.speakMessage(msg)
		allMsg += msg + os.linesep
		
		treeInterceptor = html.getTreeInterceptor()
		msg = u"nodeManager %d caractères, %s, %s" % (treeInterceptor.nodeManager.treeInterceptorSize, treeInterceptor.nodeManager.isReady, treeInterceptor.nodeManager.mainNode is not None)
		speech.speakMessage(msg)
		allMsg += msg + os.linesep
		api.copyToClip(allMsg)
	
	script_debugWebModule.category = SCRIPT_CATEGORY
	
	def script_showElementDescription(self, gesture):  # @UnusedVariable
		obj = api.getFocusObject()		
		if obj is None or obj.appModule is None:
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("The current object does not support Web Access."))
			return
		if obj.treeInterceptor is None:
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be on the web page to use Web Access."))
			return
		from .gui import elementDescription
		elementDescription.showElementDescriptionDialog()
	
	# Translators: Input help mode message for show Web Access menu command.
	script_showElementDescription.__doc__ = _("Show the element description.")

	script_showElementDescription.category = SCRIPT_CATEGORY
	
	def script_toggleWebAccessSupport(self, gesture):  # @UnusedVariable
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
	
	script_toggleWebAccessSupport.category = SCRIPT_CATEGORY
	
	__gestures = {
		"kb:nvda+w": "showWebAccessGui",
		"kb:nvda+shift+w": "toggleWebAccessSupport",
		"kb:nvda+control+w": "debugWebModule",
		"kb:nvda+control+e": "showElementDescription",
	}

def getActiveWebApp():
	global activeWebApp
	return activeWebApp

def webAppLoseFocus(obj):
	global activeWebApp
	if activeWebApp is not None:
		sendWebAppEvent('webApp_loseFocus', obj, activeWebApp)
		activeWebApp = None
		#log.info("Losing webApp focus for object:\n%s\n" % ("\n".join(obj.devInfo)))

def supportWebApp(obj):
	if obj is None or obj.appModule is None:
		return None
	return  obj.appModule.appName in supportedWebAppHosts
	

def getWebApp(self):
	global activeWebApp
	global webAccessEnabled

	# TODO: WIP on new coupling
	if (
		not webAccessEnabled
		or not supportWebApp(self)
		or not isinstance(self, overlay.WebAccessObject)
	):
		return None
	
	obj = self
	if isinstance(obj, NVDAObjects.JAB.JAB):
		# to avoid lock with jab object
		return
	
	outdated = None

	if hasattr(obj, "_webApp"):
		if hasattr(obj._webApp, "_outdated") and obj._webApp._outdated:
			outdated = obj._webApp
			TRACE(
				u"Removing cached outdated WebModule {webModule} from "
				u"obj {obj} with role {role}"
				u"".format(
					webModule=id(obj._webApp),
					obj=obj,
					role=obj._get_role(original=True)
				)
			)
			delattr(obj, "_webApp")
		else:
			return obj._webApp
	
	webApp = None
	objList = []

	# Before anything, check if the webApp window title matches the actuel one.
	if len(obj.windowText) > 0:
		for app in webModuleHandler.getWebModules():
			# TODO: Chrome: Retrieve proper window title
			if app.windowTitle and app.windowTitle in obj.windowText:
				webApp = app
				break

	i = 0
	while webApp is None and obj is not None and i < 50:
		i += 1

		if hasattr(obj, '_webApp'):
			if hasattr(obj._webApp, "_outdated") and obj._webApp._outdated:
				outdated = outdated or obj._webApp
				TRACE(
					u"Removing cached outdated WebModule {webModule} from parent "
					u"obj {obj} with role {role}"
					u"".format(
						webModule=id(obj._webApp),
						obj=obj,
						role=obj._get_role(original=True)
					)
				)
				delattr(obj, "_webApp")
			else:
				webApp = obj._webApp
				break

		objList.append(obj)

		if obj._get_role(original=True) == controlTypes.ROLE_DOCUMENT:
			try:
				url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
			except: 
				url = None
			if url:
				webApp = getWebAppFromUrl(url)

		obj = obj.parent
		if not isinstance(obj, overlay.WebAccessObject):
			break

	if webApp is None:
		obj = self
		# TODO: Remove this awful fix
		if outdated is not None and obj.role == 0:
			obj = NVDAObjects.NVDAObject.objectWithFocus()
			if \
					hasattr(obj, "_webApp") \
					and hasattr(obj._webApp, "_outdated") \
					and obj._webApp._outdated:
				delattr(obj, "_webApp")
			if isinstance(obj, overlay.WebAccessObject):
				webModule = obj.getWebApp()
			else:
				webModule = None
			TRACE(
				u"Real focus: obj={obj}, treeInterceptor={treeInterceptor}, "
				u"{webModule}".format(
				obj=obj,
				treeInterceptor=obj.treeInterceptor,
				webModule=u"{webModule} ({id})".format(
					webModule=webModule, id=id(webModule)
					) if webModule is not None else None
				))
			webApp = webModule
		else:
			return None

	for o in objList:
		o._webApp = webApp
	
	activeWebApp = webApp
	return webApp 
	# sendWebAppEvent('webApp_loseFocus', self, activeWebApp)
	# sendWebAppEvent('webApp_gainFocus', self, webApp)
	# sendWebAppEvent('webApp_pageChanged', wPageTitle, activeWebApp)

@classmethod
def hook_changeNotify(cls, rootDocHandle, rootID):
	#log.info (u"change notify")
	virtualBuffers.VirtualBuffer.save_changeNotify(rootDocHandle, rootID)

def hook_terminate(self):
	if hasattr(self, "nodeManager"):
		self.nodeManager.terminate()
		del self.nodeManager  
	virtualBuffers.VirtualBuffer.save_terminate(self)
	
# TODO: Isn't it dead code?
# Because 'webApp' instead of '_webApp'
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
	focus = api.getFocusObject()
	if focus.treeInterceptor == self:
		if hasattr(focus, 'webApp'):
			firstGainFocus = self._hadFirstGainFocus
			#self._hadFirstGainFocus = True
			scheduler.send(eventName="treeInterceptor_gainFocus", treeInterceptor=self, firstGainFocus=firstGainFocus)
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

	# App module default scripts.
	app = focus.appModule
	if app:
		# browsers default scripts.
		if supportWebApp(focus):
			func = scriptHandler._getObjScript(defaultBrowserScripts, gesture, globalMapScripts)
			if func:
				return func
		func = scriptHandler._getObjScript(app, gesture, globalMapScripts)
		if func:
			return func

	# webApp scripts
	webApp = focus.webAccess.webModule if isinstance(focus, overlay.WebAccessObject) else None
	if webApp is not None and searchWebApp is True:
		func = scriptHandler._getObjScript(webApp, gesture, globalMapScripts)
		if func:
			return func
		if webApp.markerManager:
			func = webApp.markerManager.getMarkerScript(gesture, globalMapScripts)
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
	scheduler.send(eventName="webApp", name=eventName, obj=obj, webApp=webApp)

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
	if  not supportWebApp(obj) and eventName in ["gainFocus"] and activeWebApp is not None:
		# log.info("Received event %s on a non-hosted object" % eventName)
		webAppLoseFocus(obj)
	else:
		webApp = obj.webAccess.webModule if isinstance(obj, overlay.WebAccessObject) else None
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

# Used to announce the opening of the Web Access menu
def mainFrame_prePopup_patched(self, contextMenuName=None):
	global mainFrame_prePopup_stock, popupContextMenuName
	popupContextMenuName = contextMenuName
	mainFrame_prePopup_stock()  # Stock method was stored bound

# Used to announce the opening of the Web Access menu
def mainFrame_postPopup_patched(self):
	global mainFrame_postPopup_stock, popupContextMenuName
	popupContextMenuName = None
	mainFrame_postPopup_stock()  # Stock method was stored bound

# Used to announce the opening of the Web Access menu
def appModule_nvda_event_NVDAObject_init_patched(self, obj):
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


def showWebModulesLoadErrors():
	errors = []
	webModuleHandler.getWebModules(errors=errors)
	if not errors:
		return
	
	class Case(object):
		__slots__ = ("excType", "msgSingular", "msgPlural", "refs")
		def __init__(self, *args):
			self.excType, self.msgSingular, self.msgPlural = args
			self.refs = []
	
	cases = (
		Case(
			webModuleHandler.NewerFormatVersion,
			_(
				"This web module has been created by a newer version of "
				"Web Access for NVDA and could not be loaded:"
			),
			_(
				"These web modules have been created by a newer version of "
				"Web Access for NVDA and could not be loaded:"
			)
		),
		Case(
			webModuleHandler.InvalidApiVersion,
			_(
				"This Python web module uses a different API version of "
				"Web Access for NVDA and could not be loaded:"
			),
			_(
				"These Python web modules use a different API version of "
				"Web Access for NVDA and could not be loaded:"
			)
		),
		Case(
			None,
			_(
				"An unexpected error occurred while attempting to load this "
				"web module:"
			),
			_(
				"An unexpected error occurred while attempting to load these "
				"web modules:"
			)
		)
	)
	for ref, exc_info in errors:
		if isinstance(ref, tuple):
			label = ref[-1]
			if len(ref) > 2 and ref[0] == "addons":
				label = u"{webModuleName} ({addonName})".format(
					webModuleName=ref[-1],
					addonName=ref[1]
				)
		else:
			label = ref
		for case in cases:
			if not case.excType or isinstance(exc_info[1], case.excType):
				case.refs.append(label)
				break
	parts = []
	for case in cases:
		if case.refs:
			parts.append("\n".join(
				[case.msgSingular if len(case.refs) == 1 else case.msgPlural]
				+ case.refs
			))
	if parts:
		msg = "\n\n".join(parts)
		wx.CallAfter(
			gui.messageBox,
			message=msg,
			caption=_("Web Access for NVDA"),
			style=wx.ICON_WARNING,
			parent=gui.mainFrame
		)
