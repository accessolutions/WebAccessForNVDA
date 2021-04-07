# globalPlugins/webAccess/__init__.py
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

Monkey-patched NVDA functions:
* appModules.nvda.AppModule.event_NVDAObject_init
* eventHandler._EventExecuter.gen
* gui.mainFrame.prePopup
* gui.mainFrame.postPopup
* virtualBuffers.VirtualBuffer.changeNotify
* virtualBuffers.VirtualBuffer._loadBufferDone
"""

# Keep compatible with Python 2
from __future__ import absolute_import, division, print_function

__version__ = "2021.03.12"
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

from NVDAObjects.IAccessible import IAccessible
from NVDAObjects.IAccessible.MSHTML import MSHTML
from NVDAObjects.IAccessible.ia2Web import Ia2Web
from NVDAObjects.IAccessible.mozilla import Mozilla
import addonHandler
import api
import baseObject
import controlTypes
import eventHandler
import globalPluginHandler
import gui
from logHandler import log
import scriptHandler
import speech
import ui
import virtualBuffers

from . import nodeHandler
from .nvdaVersion import nvdaVersion
from . import overlay
from . import presenter
from . import webAppLib
from .webAppLib import *
from .webAppScheduler import WebAppScheduler
from . import webModuleHandler


addonHandler.initTranslation()


TRACE = lambda *args, **kwargs: None  # @UnusedVariable
#TRACE = log.info

SCRIPT_CATEGORY = "WebAccess"

#
# defines sound directory
#

SOUND_DIRECTORY = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "sounds")



supportedWebAppHosts = ['firefox', 'chrome', 'java', 'iexplore', 'microsoftedgecp', 'msedge']

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
	except Exception:
		log.exception("While retrieving addon version")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	
	def __init__(self):
		super(globalPluginHandler.GlobalPlugin, self).__init__()

		from .config import initialize as config_initialize
		config_initialize()
		from .gui.settings import initialize as settings_initialize
		# FIXME:
		# After the above import, it appears that the `gui` name now points to the `.gui` module
		# rather that NVDA's `gui`… No clue why… (Confirmed with Python 2 & 3)
		import gui
		settings_initialize()
		
		global scheduler
		scheduler = WebAppScheduler()
		scheduler.start()
		
		eventHandler._EventExecuter.gen = eventExecuter_gen
		VirtualBuffer_changeNotify.super = virtualBuffers.VirtualBuffer.changeNotify
		# This is a classmethod, thus requires binding
		virtualBuffers.VirtualBuffer.changeNotify = VirtualBuffer_changeNotify.__get__(
			virtualBuffers.VirtualBuffer
		)
		virtualBuffer_loadBufferDone.super = virtualBuffers.VirtualBuffer._loadBufferDone
		virtualBuffers.VirtualBuffer._loadBufferDone = virtualBuffer_loadBufferDone
		
		# Used to announce the opening of the Web Access menu
		mainFrame_prePopup.super = gui.mainFrame.prePopup
		gui.mainFrame.prePopup = mainFrame_prePopup.__get__(gui.mainFrame, gui.MainFrame)
		mainFrame_postPopup.super = gui.mainFrame.postPopup
		gui.mainFrame.postPopup = mainFrame_postPopup.__get__(gui.mainFrame, gui.MainFrame)
		from appModules.nvda import AppModule as NvdaAppModule
		appModule_nvda_event_NVDAObject_init.super = NvdaAppModule.event_NVDAObject_init
		# The NVDA AppModule should not yet have been instanciated at this stage
		NvdaAppModule.event_NVDAObject_init = appModule_nvda_event_NVDAObject_init 		
		
		webModuleHandler.initialize()
		log.info("Web Access for NVDA version %s initialized" % getVersion())
		showWebModulesLoadErrors()

	def terminate(self):
		scheduler.send(eventName="stop")
		webModuleHandler.terminate()
		from .config import terminate as config_terminate
		config_terminate()
		from .gui.settings import terminate as settings_terminate
		settings_terminate()
		
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
	
	def script_showWebAccessSettings(self, gesture):  # @UnusedVariable
		from .gui.settings import WebAccessSettingsDialog
		# FIXME:
		# After the above import, it appears that the `gui` name now points to the `.gui` module
		# rather that NVDA's `gui`… No clue why… (Confirmed with Python 2 & 3)
		import gui
		gui.mainFrame._popupSettingsDialog(WebAccessSettingsDialog)
	
	# Translators: Input help mode message for a command.
	script_showWebAccessSettings.__doc__ = _("Open the Web Access Settings.")

	script_showWebAccessSettings.category = SCRIPT_CATEGORY
	
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
						focusModule.ruleManager.nodeManager is not \
						focus.treeInterceptor.nodeManager:
					diverged = True
					msg += os.linesep
					msg += u"NodeManagers différents"
				elif focusModule.ruleManager.nodeManager is None:
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
		"kb:nvda+control+w": "showWebAccessSettings",
		"kb:nvda+control+shift+w": "debugWebModule",
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
	

def VirtualBuffer_changeNotify(cls, rootDocHandle, rootID):
	# log.info(u"change notify")
	# Stock classmethod was stored bound
	VirtualBuffer_changeNotify.super(rootDocHandle, rootID)


def virtualBuffer_loadBufferDone(self, success=True):
	# log.info(u"load buffer done")
	# Stock method was stored unbound
	virtualBuffer_loadBufferDone.super.__get__(self)(success=success)


def sendWebAppEvent(eventName, obj, webApp=None):
	if webApp is None:
		return
	scheduler.send(eventName="webApp", name=eventName, obj=obj, webApp=webApp)


def eventExecuter_gen(self, eventName, obj):
	# log.info("Event %s : %s : %s" % (eventName, obj.name, obj.value))
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
			# if webApp.widgetManager.claimVirtualBufferWidget(nodeHandler.REASON_FOCUS) is False:
			# 	webApp.widgetManager.claimObject(obj)
			# if webApp.activeWidget is not None:
			# 	func = getattr(webApp.activeWidget, funcName, None)
			# 	if func:
			# 		yield func,(obj, self.next)
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
		yield func, ()


# Used to announce the opening of the Web Access menu
def mainFrame_prePopup(self, contextMenuName=None):
	global popupContextMenuName
	popupContextMenuName = contextMenuName
	mainFrame_prePopup.super()  # Stock method was stored bound


# Used to announce the opening of the Web Access menu
def mainFrame_postPopup(self):
	global popupContextMenuName
	popupContextMenuName = None
	mainFrame_postPopup.super()  # Stock method was stored bound


# Used to announce the opening of the Web Access menu
def appModule_nvda_event_NVDAObject_init(self, obj):
	global popupContextMenuName
	if (
		"popupContextMenuName" in globals()
		and popupContextMenuName is not None
		and isinstance(obj, IAccessible)
		and obj.role == controlTypes.ROLE_POPUPMENU
	):
		obj.name = popupContextMenuName
		popupContextMenuName = None
	# Stock method was stored unbound
	appModule_nvda_event_NVDAObject_init.super.__get__(self)(obj)


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
				if not case.excType:
					log.exception(exc_info=exc_info)
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
		import gui
		wx.CallAfter(
			gui.messageBox,
			message=msg,
			# Translators: The title of an error message dialog
			caption=_("Web Access for NVDA"),
			style=wx.ICON_WARNING,
			parent=gui.mainFrame
		)


if (2018, 1) <= nvdaVersion < (2019, 2, 1):
	
	# Workaround for NVDA bug #10227 / PR #10231 / Fix up #10282
	# "IA2: Do not treat huge base64 data as NVDA might freeze in Google Chrome"
	
	ATTRIBS_STRING_BASE64_PATTERN = re.compile(
		r"(([^\\](\\\\)*);src:data\\:[^\\;]+\\;base64\\,)[A-Za-z0-9+/=]+"
	)
	ATTRIBS_STRING_BASE64_REPL = r"\1<truncated>"
	ATTRIBS_STRING_BASE64_THRESHOLD = 4096

	def splitIA2Attribs(attribsString):
		if len(attribsString) >= ATTRIBS_STRING_BASE64_THRESHOLD:
			attribsString = ATTRIBS_STRING_BASE64_PATTERN.sub(ATTRIBS_STRING_BASE64_REPL, attribsString)
			if len(attribsString) >= ATTRIBS_STRING_BASE64_THRESHOLD:
				log.debugWarning(u"IA2 attributes string exceeds threshold: {}".format(attribsString))
		return splitIA2Attribs.super(attribsString)

	import IAccessibleHandler

	splitIA2Attribs.super = IAccessibleHandler.splitIA2Attribs
	IAccessibleHandler.splitIA2Attribs = splitIA2Attribs
