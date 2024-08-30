# globalPlugins/webAccess/webModuleHandler/__init__.py
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

"""Web Access GUI."""


__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import os
import pkgutil
import wx

import api
import controlTypes
import config
import globalVars
import gui
from addonHandler.packaging import addDirsToPythonPackagePath
from logHandler import log
import ui

from .dataRecovery import NewerFormatVersion
from .webModule import InvalidApiVersion, WebModule, WebModuleDataLayer
from ..lib.packaging import version
from ..overlay import WebAccessBmdti
from ..store import DuplicateRefError
from ..store import MalformedRefError
from ..utils import notifyError


PACKAGE_NAME = "webModulesSM"

store = None
_catalog = None
_webModules = None


def delete(webModule, prompt=True):
	if prompt:
		from ..gui.webModule import promptDelete
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
	if store is None:
		return []
	_catalog = list(store.catalog(errors=errors))
	return _catalog


def getWebModule(name: str) -> WebModule:
	for ref, meta in getCatalog():
		candidate = meta.get("name")
		if candidate == name:
			return store.get(ref)


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


def save(webModule, layerName=None, prompt=True, force=False, fromRuleEditor=False):
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
		log.debug("saving layer {!r}".format(layer))
		if layer.storeRef is None:
			storeRef = store.create(webModule, force=force)
			prompt and ui.message(
				# Translators: Confirmation message after web module creation.
				_("Your new web module {name} has been created.").format(name=webModule.name)
			)
		else:
			store.update(webModule, layerName=layer.name, force=force)
	except DuplicateRefError as e:
		if not prompt or force:
			return False
		from ..gui.webModule.editor import promptOverwrite
		if promptOverwrite():
			return save(webModule, layerName=layerName, prompt=prompt, force=True)
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
			caption=prompt,
			style=wx.OK | wx.ICON_EXCLAMATION
		)
		return False
	except Exception:
		msg = "save(webModule={!r}, layerName=={!r}, prompt=={!r}, force=={!r}".format(
			webModule, layerName, prompt, force
		)
		if prompt:
			notifyError(msg)
		else:
			log.exception(msg)
		return False
	if not fromRuleEditor:
		# only if webModule creation or modification
		log.debug ("refresh %s" % prompt)
		getWebModules(refresh=True)
	resetRunningModules()
	return True


def getEditableWebModule(webModule, layerName=None, prompt=True):
	"""Ensure a WebModule is suitable for edition, eventually initializing a writable layer
	
	`layerName`
		The name of the layer from which a Rule is to be edited. Should be `None` for
		updating WebModule properties such as triggers and help content.
	
	See `WebModuleHandler.webModule.WebModuleDataLayer._get_readonly` for details regarding
	what configuration allows editing WebModules from which layer.
	
	Returns `None` if the current configuration does not allow editing the specified WebModule.
	"""
	try:
		if layerName is not None:
			if not webModule.getLayer(layerName).readOnly:
				return webModule
			webModule = _getEditableScratchpadWebModule(webModule, layerName=layerName, prompt=prompt)
		else:
			if not webModule.isReadOnly():
				return webModule
			webModule = (
				_getEditableUserConfigWebModule(webModule)
				or _getEditableScratchpadWebModule(webModule, prompt=prompt)
			)
	except Exception:
		log.exception("webModule={!r}, layerName={!r}".format(webModule, layerName))
	if webModule:
		return webModule
	if prompt:
		# Translators: An error message upon attempting to save a modification
		msg = _("This modification cannot be saved under the current configuration.")
		hints = []
		if config.conf["webAccess"]["disableUserConfig"] and layerName is None:
			# Translators: A hint on how to allow to save a modification
			hints.append(_("• In the WebAccess category, enable User WebModules."))
		if (
			not config.conf["webAccess"]["devMode"]
			and layerName not in ("user", None)
		):
			# Translators: A hint on how to allow to save a modification
			hints.append(_("• In the WebAccess category, enable Developper Mode."))
		if (
			not config.conf["development"]["enableScratchpadDir"]
			and (
				layerName is None and config.conf["webAccess"]["disableUserConfig"]
				or layerName not in ("user", None)
			)
		):
			# Translators: A hint on how to allow to save a modification
			hints.append(_("• In the Advanced category, enable loading of the Scratchpad directory"))
		if hints:
			if len(hints) > 1 and config.conf["webAccess"]["disableUserConfig"] and layerName is None:
				hints.insert(1, _("or"))
			msg += os.linesep + os.linesep
			# Translators: An introduction to hints on how to allow to save a modification
			msg += _("You may, in NVDA Preferences:")
			for hint in hints:
				msg += os.linesep + hint
		gui.messageBox(
			message=msg,
			# Translators: The title of an error message dialog
			caption=_("Error"),
			style=wx.OK | wx.ICON_EXCLAMATION
		)


def _getEditableScratchpadWebModule(webModule, layerName=None, prompt=True):
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
	if not webModule.layers:  # New module
		webModule.load("scratchpad")
		webModule.getLayer("scratchpad", raiseIfMissing=True).dirty = False
		return webModule
	if layerName is None:
		layerName = "addon"
	if layerName != "addon":
		return None
	if prompt:
		from ..gui.webModule import promptMask
		if not promptMask(webModule):
			return False
	data = webModule.dump(layerName).data
	mask = type(webModule)()
	mask.load("scratchpad", data=data)
	mask.getLayer("scratchpad", raiseIfMissing=True).dirty = True
	return mask


def _getEditableUserConfigWebModule(webModule):
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
	fqModName = f"{PACKAGE_NAME}.{name}"
	try:
		import importlib
		mod = importlib.import_module(fqModName, package=PACKAGE_NAME)
	except Exception:
		log.exception(f"Could not import custom module {fqModName}")
	if not mod:
		return WebModule
	apiVersion = getattr(mod, "API_VERSION", None)
	log.debug(f"apiVersion (str): {apiVersion!r}")
	apiVersion = version.parse(apiVersion or "")
	log.debug(f"apiVersion (obj): {apiVersion!r} ({apiVersion})")
	if apiVersion != WebModule.API_VERSION:
		raise InvalidApiVersion(apiVersion)
	ctor = getattr(mod, "WebModule", None)
	if ctor is None:
		msg = "Python module {} does not provide a 'WebModule' class: {}".format(
			mod.__name__,
			getattr(mod, "__file__", None) or getattr(mod, "__path__", None)
		)
		log.error(msg)
		raise AttributeError(msg)
	return ctor


def hasCustomModule(name):
	return any(
		importer.find_module(f"{PACKAGE_NAME}.{name}")
		for importer in _importers
		if importer
	)


def initialize():
	global store
	global _importers

	import imp
	webModules = imp.new_module(PACKAGE_NAME)
	webModules.__path__ = list()
	import sys
	sys.modules[PACKAGE_NAME] = webModules
	addDirsToPythonPackagePath(webModules)
	_importers = list(pkgutil.iter_importers(f"{PACKAGE_NAME}.__init__"))

	from ..store.webModule import WebModuleStore
	store = WebModuleStore()


def terminate():
	import sys
	try:
		del sys.modules[PACKAGE_NAME]
	except KeyError:
		pass
	_importers = None
