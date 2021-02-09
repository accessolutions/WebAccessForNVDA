# globalPlugins/webAccess/webModuleHandler/__init__.py
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

"""Web Access GUI."""

# Keep compatible with Python 2
from __future__ import absolute_import, division, print_function

__version__ = "2021.02.08"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import os
import pkgutil
import wx

import api
import controlTypes
import config
import globalVars
import gui
from logHandler import log
import ui

from .webModule import InvalidApiVersion, NewerFormatVersion, WebModule, WebModuleDataLayer
from ..lib.packaging import version
from ..nvdaVersion import nvdaVersion
from ..overlay import WebAccessBmdti
from ..store import DuplicateRefError
from ..store import MalformedRefError


store = None
_catalog = None
_webModules = None


def delete(webModule, prompt=True):
	if prompt:
		from ..gui.webModulesManager import promptDelete
		if not promptDelete(webModule):
			return False
	store.delete(webModule)
	getWebModules(refresh=True)
	resetRunningModules()
	return True


def getCatalog(refresh=False, errors=None):
	global _catalog, _webModules
	if not refresh:
		if _catalog:
			return _catalog
	else:
		_webModules = None
	_catalog = list(store.catalog(errors=errors))
	return _catalog


def getWebModuleForTreeInterceptor(treeInterceptor):
	obj = treeInterceptor.rootNVDAObject
	windowTitle = getWindowTitle(obj)
	if windowTitle:
		mod = getWebModuleForWindowTitle(windowTitle)
		if mod:
			return mod
	url = getUrl(obj)
	if url:
		return getWebModuleForUrl(url)
	return None


def getWebModuleForWindowTitle(windowTitle):
	if not windowTitle:
		return None
	for ref, meta in getCatalog():
		candidate = meta.get("windowTitle")
		if candidate and candidate in windowTitle:
			return store.get(ref)


def getWebModuleForUrl(url):
	matchedLen = 0
	matchedRef = None
	for ref, meta in getCatalog():
		urls = meta.get("url")
		if not urls:
			continue
		if not isinstance(urls, (tuple, list)):
			urls = (urls,)
		for candidate in urls:
			if candidate in url and len(candidate) > matchedLen:
				matchedRef = ref
				matchedLen = len(candidate)
	if matchedRef:
		return store.get(matchedRef)


def getWindowTitle(obj):
	from ..overlay import WebAccessObject
	if isinstance(obj, WebAccessObject):
		role = obj._get_role(original=True)
	else:
		role = obj.role
	if role == controlTypes.ROLE_DIALOG:
		try:
			root = obj.parent.treeInterceptor.rootNVDAObject
		except AttributeError:
			return None
		return getWindowTitle(root)
	if role != controlTypes.ROLE_DOCUMENT:
		try:
			root = obj.treeInterceptor.rootNVDAObject
		except AttributeError:
			return None
		if root is not obj:
			return getWindowTitle(root)
	res = None
	if isinstance(obj, WebAccessObject):
		res = obj._get_name(original=True)
	else:
		res = obj.name
	if res:
		return res
	try:
		res = obj.IAccessibleObject.accName(obj.IAccessibleChildID)
	except Exception:
		pass
	if res:
		return res
	return getattr(obj, "windowText", None)


def getUrl(obj):
	try:
		url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
	except Exception:
		url = None
	if url:
		return url
	try:
		if obj.parent and obj.parent.treeInterceptor:
			root = obj.parent.treeInterceptor.rootNVDAObject
			if root is not obj:
				return getUrl(root)
	except Exception:
		log.exception()
	return None


def getWebModules(refresh=False, errors=None):
	global _catalog, _webModules
	if not refresh:
		if _webModules:
			return _webModules
	else:
		_catalog = None
	_webModules = list(store.list(errors=errors))
	return _webModules


def resetRunningModules(webModule=None):
	import treeInterceptorHandler
	for ti in treeInterceptorHandler.runningTable:
		if not isinstance(ti, WebAccessBmdti):
			continue
		if webModule is not None and ti.webAccess.webModule != webModule:
			continue
		ti.webAccess._nodeManager = None
		ti.webAccess._webModule = None


def save(webModule, focus, layerName=None, prompt=True, force=False):
	if layerName is not None:
		layer = webModule.getLayer(layerName, raiseIfMissing=True)
	else:
		layers = [
			layer for layer in reversed(webModule.layers)
			if not layer.readOnly and layer.dirty
		]
		if len(layers) == 0:
			# Nothing to save
			return True
		elif len(layers) != 1:
			raise Exception((
				"Expecting a single data layer to save. Found {}. webModule={!r}, layers={!r}"
			).format(len(layers), webModule, webModule.layers))
		layer = layers[0]
	try:
		log.info("saving layer {!r}".format(layer))
		if layer.storeRef is None:
			storeRef = store.create(webModule, force=force)
			prompt and ui.message(
				# Translators: Confirmation message after web module creation.
				_(u"Your new web module {name} has been created.").format(name=webModule.name)
			)
		else:
			store.update(webModule, layerName=layer.name, force=force)
	except DuplicateRefError as e:
		if not prompt or force:
			return False
		from ..gui import webModuleEditor
		if webModuleEditor.promptOverwrite():
			return save(webModule, focus, layerName=layerName, prompt=prompt, force=True)
		return False
	except MalformedRefError:
		prompt and gui.messageBox(
			message=(
				_("The web module name should be a valid file name.")
				+ " " + os.linesep
				+ _("It should not contain any of the following:")
				+ os.linesep
				+ "\t" + "\\ / : * ? \" | "
			),
			caption=webModuleEditor.Dialog._instance.Title,
			style=wx.OK | wx.ICON_EXCLAMATION
		)
		return False
	except Exception:
		log.exception("save(webModule={!r}, focus={!r}, layerName=={!r}, prompt=={!r}, force=={!r}".format(
			webModule, focus, layerName, prompt, force
		))
		getWebModules(refresh=True)
		return False
	getWebModules(refresh=True)
	resetRunningModules()
	return True


def showCreator(context):
	showEditor(context, new=True)


def showEditor(context, new=False):
	from ..gui import webModuleEditor
	from .webModule import WebModule
	
	if "data" in context:
		del context["data"]
	if new:
		if "webModule" in context:
			del context["webModule"]
	webModuleEditor.show(context)
	return
	keepShowing = True
	force = False
	while keepShowing:
		if webModuleEditor.show(context):
			keepTrying = True
			while keepTrying:
				try:
					if new:
						webModule = context["webModule"] = WebModule()
						webModule.load(None, data=context["data"])
						create(
							webModule=webModule,
							focus=context.get("focusObject"),
							force=force
						)
						# Translators: Confirmation message after web module creation.
						ui.message(
							_(
								u"Your new web module {name} has been created."
								).format(name=webModule.name)
							)
					else:
						webModule = context["webModule"]
						for name, value in context["data"]["WebModule"].items():
							setattr(webModule, name, value)
						update(
							webModule=webModule,
							focus=context.get("focusObject"),
							force=force
						)
					keepShowing = keepTrying = False
				except DuplicateRefError as e:
					if webModuleEditor.promptOverwrite():
						force = True
					else:
						keepTrying = force = False
				except MalformedRefError:
					keepTrying = force = False
					gui.messageBox(
						message=(
							_("The web module name should be a valid file name.")
							+ " " + os.linesep
							+ _("It should not contain any of the following:")
							+ os.linesep
							+ "\t" + "\\ / : * ? \" | "
						),
						caption=webModuleEditor.Dialog._instance.Title,
						style=wx.OK | wx.ICON_EXCLAMATION
					)
				finally:
					if not new:
						getWebModules(refresh=True)
		else:
			keepShowing = False
			if new:
				# Translator: Canceling web module creation.
				ui.message(_("Cancel"))

	
def showManager(context):
	from ..gui import webModulesManager
	webModulesManager.show(context)


def getEditableWebModule(webModule, layerName=None, prompt=True):
	if layerName is not None:
		if not webModule.getLayer(layerName).readOnly:
			return webModule
		webModule = getEditableScratchpadWebModule(webModule, layerName=layerName, prompt=prompt)
	else:
		if not webModule.isReadOnly():
			return webModule
		webModule = (
			getEditableUserConfigWebModule(webModule)
			or getEditableScratchpadWebModule(webModule, prompt=prompt)
		)
	if webModule is not None:
		return webModule
	if prompt:
		msg = _("This web module cannot be saved under the current configuration.")
		hints = []
		if not config.conf["development"]["enableScratchpadDir"] and (layerName is not None or (
			config.conf["webAccess"]["devMode"]
			and config.conf["webAccess"]["disableUserConfig"]
		)):
			hints.append(_(u"• In the Advanced category, enable loading of the Scratchpad directory"))
		if not config.conf["webAccess"]["devMode"] and layerName is not None:
			hints.append(_(u"• In the WebAccess category, enable Developper Mode."))
		if config.conf["webAccess"]["disableUserConfig"] and layerName is None:
			hints.append(_(u"• In the WebAccess category, enable the User Configuration."))
		if hints:
			msg += os.linesep + os.linesep + _("You may, in NVDA Preferences:")
			for hint in hints:
				msg += os.linesep + hint
		gui.messageBox(
			message=msg,
			caption=_("Error"),
			style=wx.OK | wx.ICON_EXCLAMATION
		)
	

def getEditableScratchpadWebModule(webModule, layerName=None, prompt=True):
	if not (
		config.conf["development"]["enableScratchpadDir"]
		and config.conf["webAccess"]["devMode"]
	):
		return None
	layer = webModule.getLayer("scratchpad")
	if layer:
		if layer.readOnly:
			return None
		return webModule
	if prompt:
		from ..gui.webModulesManager import promptMask
		if not promptMask(webModule):
			return False
	if not webModule.layers:  # New module
		webModule.load("scratchpad")
		webModule.getLayer("scratchpad", raiseIfMissing=True).dirty = False
		return webModule
	if layerName is None:
		layerName = "addon"
	data = webModule.dump(layerName).data
	mask = type(webModule)()
	mask.load("scratchpad", data=data)
	mask.getLayer("scratchpad", raiseIfMissing=True).dirty = True
	return mask


def getEditableUserConfigWebModule(webModule):
	if config.conf["webAccess"]["disableUserConfig"]:
		return None
	layer = webModule.getLayer("user")
	if layer:
		if layer.readOnly:
			return None
		return webModule
	webModule.load("user")
	webModule.getLayer("user", raiseIfMissing=True).dirty = False
	return webModule


def getWebModuleFactory(name):
	if not hasCustomModule(name):
		return WebModule
	mod = None
	try:
		if nvdaVersion < (2019, 3):
			# Python 2.x can't properly handle unicode module names, so convert them.
			name = name.encode("mbcs")
			mod = __import__("webModules.{}".format(name), globals(), locals(), ("webModules",))
		else:
			import importlib
			mod = importlib.import_module("webModules.{}".format(name), package="webModules")
	except Exception:
		log.exception("Could not import custom module webModules.{}".format(name))
	if not mod:
		return WebModule
	apiVersion = getattr(mod, "API_VERSION", None)
	apiVersion = version.parse(apiVersion or "")
	if apiVersion != WebModule.API_VERSION:
		raise InvalidApiVersion(apiVersion)
	ctor = getattr(mod, "WebModule", None)
	if ctor is None:
		msg = u"Python module {} does not provide a 'WebModule' class: {}".format(
			mod.__name__,
			getattr(mod, "__file__", None) or getattr(mod, "__path__", None)
		)
		log.error(msg)
		raise AttributeError(msg)
	return ctor


def hasCustomModule(name):
	if nvdaVersion < (2019, 3):
		# Python 2.x can't properly handle unicode module names, so convert them.
		name = name.encode("mbcs")
	return any(
		importer.find_module("webModules.{}".format(name))
		for importer in _importers
		if importer
	)


def initialize():
	global store
	global _importers
	
	import imp
	webModules = imp.new_module("webModules")
	webModules.__path__ = list()
	import sys
	sys.modules["webModules"] = webModules
	config.addConfigDirsToPythonPackagePath(webModules)
	if nvdaVersion < (2019, 1) and not config.conf["webAccess"]["disableUserConfig"]:
		webModules.__path__.insert(0, os.path.join(globalVars.appArgs.configPath, "webModules"))
	_importers = list(pkgutil.iter_importers("webModules.__init__"))
	
	from ..store.webModule import WebModuleStore
	store = WebModuleStore()


def terminate():
	import sys
	try:
		del sys.modules["webModules"]
	except KeyError:
		pass
	_importers = None
