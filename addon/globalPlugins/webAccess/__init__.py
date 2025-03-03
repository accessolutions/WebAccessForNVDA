# globalPlugins/webAccess/__init__.py
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

Monkey-patched NVDA functions:
* appModules.nvda.AppModule.event_NVDAObject_init
* eventHandler._EventExecuter.gen
* gui.mainFrame.prePopup
* gui.mainFrame.postPopup
* virtualBuffers.VirtualBuffer.changeNotify
* virtualBuffers.VirtualBuffer._loadBufferDone
"""


__authors__ = (
	"Yannick Plassiard <yan@mistigri.org>",
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


import os
import re
import wx

from NVDAObjects.IAccessible import IAccessible
from NVDAObjects.IAccessible.MSHTML import MSHTML
from NVDAObjects.IAccessible.ia2Web import Ia2Web
from NVDAObjects.IAccessible.mozilla import Mozilla
import addonHandler
import api
import baseObject
from buildVersion import version_detailed as NVDA_VERSION
import controlTypes
import core
import eventHandler
import globalPluginHandler
import gui
from logHandler import log
from scriptHandler import script
import ui
import virtualBuffers

from . import overlay, webModuleHandler
from .webAppLib import playWebAccessSound, sleep
from .webAppScheduler import WebAppScheduler


addonHandler.initTranslation()


SCRIPT_CATEGORY = "WebAccess"
SOUND_DIRECTORY = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "sounds")
SUPPORTED_HOSTS = ['brave', 'firefox', 'chrome', 'java', 'iexplore', 'microsoftedgecp', 'msedge']
TRACE = lambda *args, **kwargs: None  # @UnusedVariable
#TRACE = log.info


# Currently dead code, but will likely be revived for issue #17.
activeWebModule = None

webAccessEnabled = True
scheduler = None


class DefaultBrowserScripts(baseObject.ScriptableObject):

	def __init__(self, warningMessage):
		super().__init__()
		self.warningMessage = warningMessage
		for ascii in range(ord("a"), ord("z")+1):
			character = chr(ascii)
			self.__class__.__gestures["kb:control+shift+%s" % character] = "notAssigned"

	def script_notAssigned(self, gesture):  # @UnusedVariable
		playWebAccessSound("keyError")
		sleep(0.2)
		ui.message(self.warningMessage)

	__gestures = {}

defaultBrowserScripts = DefaultBrowserScripts("Pas de web module pour cette page")


def getVersion():
	try:
		thisPath = os.path.abspath(
			os.path.join(
				os.path.split(__file__)[0],
				r"..\.."
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
		super().__init__()

		from .config import initialize as config_initialize
		config_initialize()
		from .gui.settings import initialize as settings_initialize
		# FIXME:
		# After the above import, it appears that the `gui` name now points to the `.gui` module
		# rather that NVDA's `gui`… No clue why…
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

		self.restorePackage()
		core.callLater (2000, self.loadWebModules)

	def loadWebModules(self):
		webModuleHandler.initialize()
		log.info("Web Access for NVDA version %s initialized" % getVersion())
		showWebModulesLoadErrors()

	def restorePackage(self):
		"""Temporary remediation for the end of the webModulesMC/SM transition phase
		"""
		import os
		import os.path
		import globalVars
		mcPath = os.path.join(globalVars.appArgs.configPath, "webModulesMC")
		smPath = os.path.join(globalVars.appArgs.configPath, "webModulesSM")
		wmPath = os.path.join(globalVars.appArgs.configPath, "webModules")
		if not os.path.exists(mcPath) or not os.path.isdir(mcPath):
			mcPath = False
		if not os.path.exists(smPath) or not os.path.isdir(smPath):
			smPath = False
		if not (mcPath or smPath):
			return
		if mcPath and not os.listdir(mcPath):
			os.rmdir(mcPath)
			mcPath = False
		if smPath and not os.listdir(smPath):
			os.rmdir(smPath)
			smPath = False
		if not (mcPath or smPath):
			return
		if not os.path.exists(wmPath) and (bool(mcPath) ^ bool(smPath)):
			fromPath = mcPath or smPath
			os.rename(fromPath, wmPath)
			log.warning(f'Directory "{fromPath}" renamed to "{wmPath}"')
			return
		if not os.path.isdir(wmPath):
			log.error(f"Path exists but is not a directory: {wmPath}")
			return
		if not os.listdir(wmPath) and (bool(mcPath) ^ bool(smPath)):
			fromPath = smPath = mcPath or smPath
			os.rmdir(wmPath)
			os.rename(fromPath, wmPath)
			log.warning(f'Directory "{fromPath}" renamed to "{wmPath}"')
			return
		
		def getUniquePath(base):
			candidate = base
			i = 0
			while os.path.exists(candidate):
				i += 1
				candidate = f"{base}-{i:03}"
			return candidate
		
		wmBackupPath = getUniquePath(os.path.join(globalVars.appArgs.configPath, "webModules.old"))
		os.rename(wmPath, wmBackupPath)
		log.warning(f'Directory "{wmPath}" renamed to "{wmBackupPath}"')
		mcBackupPath = mcPath and getUniquePath(os.path.join(wmBackupPath, "MC"))
		smBackupPath = smPath and getUniquePath(os.path.join(wmBackupPath, "SM"))
		os.mkdir(wmPath)
		import shutil
		notifyDuplicate = notifyOther = False
		for src1, src2, src3 in (
			(wmBackupPath, mcPath, smPath),
			(mcPath, wmBackupPath, smPath),
			(smPath, wmBackupPath, mcPath),
		):
			if not src1:
				continue
			for filename in os.listdir(src1):
				fp1 = os.path.join(src1, filename)
				if not os.path.isfile(fp1) or not filename.endswith(".json"):
					notifyOther = True
					continue
				mtime1 = os.path.getmtime(fp1)
				mtime2 = 0
				if src2:
					fp2 = os.path.join(src2, filename)
					if os.path.exists(fp2) and os.path.isfile(fp2):
						mtime2 = os.path.getmtime(fp2)
				mtime3 = 0
				if src3:
					fp3 = os.path.join(src3, filename)
					if os.path.exists(fp3) and os.path.isfile(fp3):
						mtime3 = os.path.getmtime(fp3)
				if mtime1 < mtime2 or mtime1 < mtime3:
					notifyDuplicate = True
					continue
				shutil.copy(fp1, wmPath)
		if mcPath:
			os.rename(mcPath, mcBackupPath)
			log.warning(f'Directory "{mcPath}" moved to "{mcBackupPath}"')
		if smPath:
			os.rename(smPath, smBackupPath)
			log.warning(f'Directory "{mcPath}" moved to "{mcBackupPath}"')
		wmPath = os.path.basename(wmPath)
		mcPath = mcPath and os.path.basename(mcPath)
		smPath = smPath and os.path.basename(smPath)
		wmBackupPath = os.path.basename(wmBackupPath)
		mcBackupPath = mcPath and os.path.join(wmBackupPath, "MC")
		smBackupPath = smPath and os.path.join(wmBackupPath, "SM")
		if not (notifyDuplicate or notifyOther):
			return
		# Do not use translation to limit merge conflicts
		msg = "La période de transition webModulesMC/SM est révolue.\n"
		msg += "Dans votre dossier de configuration utilisateur :\n"
		msg += " - {wmPath} a été renommé en {wmBackupPath} pour sauvegarde.\n"
		if mcPath:
			msg += " - {mcPath} a été déplacé vers {mcBackupPath} pour sauvegarde.\n"
		if smPath:
			msg += " - {smPath} a été déplacé vers {smBackupPath} pour sauvegarde.\n"
		msg += "- Le plus récent de chaque webModule trouvé à ces emplacements a été "
		msg += "copié dans votre nouveau dossier {wmPath}."
		if notifyOther:
			msg += "\n"
			msg += " - Tout autre contenu dans ces dossiers a été ignoré."
		msg = msg.format(**locals())
		import gui
		wx.CallAfter(
			gui.messageBox,
			message=msg,
			# Translators: The title of a message dialog
			caption=_("Web Access for NVDA"),
			style=wx.ICON_INFORMATION,
			parent=gui.mainFrame
		)

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
				controlTypes.ROLE_APPLICATION,
				controlTypes.ROLE_DIALOG,
				controlTypes.ROLE_DOCUMENT,
			):
				clsList.insert(0, overlay.WebAccessDocument)
				return
			clsList.insert(0, overlay.WebAccessObject)
		else:
			from .gui import inspector
			if (
				inspector.outputWindowHandle is not None
				and obj.role == controlTypes.ROLE_EDITABLETEXT
				and obj.windowHandle == inspector.outputWindowHandle
				and obj.appModule.appName == "nvda"
			):
				clsList.insert(0, inspector.InspectorOutputOverlay)
	@script(
		# Translators: Input help mode message for show Web Access menu command.
		description=_("Show the Web Access menu."),
		category=SCRIPT_CATEGORY,
		gesture="kb:nvda+w"
	)
	def script_showWebAccessGui(self, gesture):  # @UnusedVariable
		wx.CallAfter(self.showWebAccessGui)

	def showWebAccessGui(self):
		obj = api.getFocusObject()
		if not canHaveWebAccessSupport(obj):
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be in a web browser to use Web Access."))
			return
		if not isinstance(obj.treeInterceptor, overlay.WebAccessBmdti):
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be on the web page to use Web Access."))
			return
		from .gui import menu
		context = {
			"webAccess": self,
			"focusObject": obj,
		}
		# Use the helper of the TreeInterceptor to get the WebModule at caret
		# rather than the one where the focus is stuck.
		webModule = obj.treeInterceptor.webAccess.webModule
		if webModule:
			context["webModule"] = webModule
			context["pageTitle"] = webModule.pageTitle
			mgr = webModule.ruleManager
			context["result"] = mgr.getResultAtCaret()
			stack = []
			while True:
				stack.append(webModule)
				try:
					webModule = webModule.ruleManager.parentRuleManager.webModule
				except AttributeError:
					break
			if len(stack) > 1:
				context["webModuleStackAtCaret"] = stack
		menu.show(context)

	@script(
		# Translators: Input help mode message for open Web Access settings command.
		description=_("Open the Web Access Settings."),
		category=SCRIPT_CATEGORY,
		gesture="kb:nvda+control+w"
	)
	def script_showWebAccessSettings(self, gesture):  # @UnusedVariable
		from .gui.settings import WebAccessSettingsDialog
		# FIXME:
		# After the above import, it appears that the `gui` name now points to the `.gui` module
		# rather than NVDA's `gui`… No clue why…
		import gui
		if NVDA_VERSION < "2023.2":
			# Deprecated as of NVDA 2023.2
			gui.mainFrame._popupSettingsDialog(WebAccessSettingsDialog)
		else:
			# Now part of the public API as of NVDA PR #15121
			gui.mainFrame.popupSettingsDialog(WebAccessSettingsDialog)

	@script(
		# Translators: Input help mode message for a WebAccess command
		description=_("Inspect the element at caret"),
		category=SCRIPT_CATEGORY,
		gesture="kb:nvda+control+e"
	)
	def script_inspect(self, gesture):  # @UnusedVariable
		obj = api.getFocusObject()
		if obj is None or obj.appModule is None:
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("The current object does not support Web Access."))
			return
		if obj.treeInterceptor is None:
			# Translators: Error message when attempting to show the Web Access GUI.
			ui.message(_("You must be on the web page to use Web Access."))
			return
		from .gui import inspector
		inspector.show()


	@script(
		description=_("""Toggle Web Access support."""),
		category=SCRIPT_CATEGORY,
		gesture="kb:nvda+shift+w"
	)
	def script_toggleWebAccessSupport(self, gesture):  # @UnusedVariable
		global webAccessEnabled

		if webAccessEnabled:
			webAccessEnabled = False
			ui.message(_("Web Access support disabled."))  # FR: u"Support Web Access désactivé."
		else:
			webAccessEnabled = True
			ui.message(_("Web Access support enabled."))  # FR: u"Support Web Access activé."


def getActiveWebModule():
	global activeWebModule
	return activeWebModule


def webModuleLoseFocus(obj):
	global activeWebModule
	if activeWebModule is not None:
		sendWebModuleEvent('webModule_loseFocus', obj, activeWebModule)
		activeWebModule = None
		#log.info("Losing webModule focus for object:\n%s\n" % ("\n".join(obj.devInfo)))


def canHaveWebAccessSupport(obj):
	if obj is None or obj.appModule is None:
		return False
	return obj.appModule.appName in SUPPORTED_HOSTS


def VirtualBuffer_changeNotify(cls, rootDocHandle, rootID):
	# log.info(u"change notify")
	# Stock classmethod was stored bound
	VirtualBuffer_changeNotify.super(rootDocHandle, rootID)


def virtualBuffer_loadBufferDone(self, success=True):
	# log.info(u"load buffer done")
	# Stock method was stored unbound
	virtualBuffer_loadBufferDone.super.__get__(self)(success=success)


def sendWebModuleEvent(eventName, obj, webModule=None):
	if webModule is None:
		return
	scheduler.send(eventName="webModule", name=eventName, obj=obj, webModule=webModule)


def eventExecuter_gen(self, eventName, obj):
	# log.info("Event %s : %s : %s" % (eventName, obj.name, obj.value))

	funcName = "event_%s" % eventName

	# Global plugin level.
	for plugin in globalPluginHandler.runningPlugins:
		func = getattr(plugin, funcName, None)
		if func:
			yield func, (obj, self.next)

	# WebModule level.
	webModule = obj.webAccess.webModule if isinstance(obj, overlay.WebAccessObject) else None
	if webModule is None:
		# Currently dead code, but will likely be revived for issue #17.
		if activeWebModule is not None and obj.hasFocus:
			#log.info("Disabling active webApp event %s" % eventName)
			webAppLoseFocus(obj)
	else:
		# log.info("Getting method %s -> %s" %(webApp.name, funcName))
		func = getattr(webModule, funcName, None)
		if func:
			yield func, (obj, self.next)

	# App module level.
	app = obj.appModule
	if app:
		func = getattr(app, funcName, None)
		if func:
			yield func, (obj, self.next)

	# Tree interceptor level.
	treeInterceptor = obj.treeInterceptor
	if treeInterceptor:
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
				label = "{webModuleName} ({addonName})".format(
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
