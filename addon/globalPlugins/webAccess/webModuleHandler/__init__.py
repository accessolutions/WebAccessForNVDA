# globalPlugins/webAccess/webModuleHandler/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2020 Accessolutions (http://accessolutions.fr)
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

from __future__ import absolute_import

__version__ = "2020.02.19"
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

from .webModule import InvalidApiVersion, NewerFormatVersion, WebModule
from ..packaging import version
from ..nvdaVersion import nvdaVersion
from ..store import DuplicateRefError
from ..store import MalformedRefError


_store = None
_catalog = None
_webModules = None


def create(webModule, focus, force=False):
	_store.create(webModule, force=force)
	getWebModules(refresh=True)
	if focus:
		from .. import webAppScheduler
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=webModule,
			focus=focus
			)
	else:
		log.error("No focus to update")


def delete(webModule, focus, prompt=True):
	if prompt:
		from ..gui.webModulesManager import promptDelete
		if not promptDelete(webModule):
			return False
	_store.delete(webModule)
	getWebModules(refresh=True)
	if focus:
		from .. import webAppScheduler
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=webModule,
			focus=focus
			)
	return True


def getCatalog(refresh=False, errors=None):
	global _catalog, _webModules
	if not refresh:
		if _catalog:
			return _catalog
	else:
		_webModules = None
	_catalog = list(_store.catalog(errors=errors))
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
			return _store.get(ref)


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
		return _store.get(matchedRef)


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
	except:
		pass
	if res:
		return res
	return getattr(obj, "windowText", None)


def getUrl(obj):
	try:
		url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
	except: 
		url = None
	if url:
		return url
	try:
		if obj.parent and obj.parent.treeInterceptor:
			root = obj.parent.treeInterceptor.rootNVDAObject
			if root is not obj:
				return getUrl(root)
	except:
		log.exception()
	return None


def getWebModules(refresh=False, errors=None):
	global _catalog, _webModules
	if not refresh:
		if _webModules:
			return _webModules
	else:
		_catalog = None
	_webModules = list(_store.list(errors=errors))
	return _webModules


def update(webModule, focus, force=False):
	updatable, mask = checkUpdatable(webModule)
	if mask:
		return create(webModule, focus, force=force)
	if updatable:
		_store.update(webModule, force=force)
		ui.message(_("Web module updated."))
		log.info(u"WebModule updated: {webModule}".format(webModule=webModule))
	getWebModules(refresh=True)
	if focus:
		from .. import webAppScheduler
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=webModule,
			focus=focus
			)
	return True


def checkUpdatable(webModule):
	"""
	Check if a WebModule can be updated in place.
	
	If not, prompts the user if they want to mask it with a
	copy in userConfig (which is the default store when
	creating a new WebModule).
	
	Returns (isUpdatable, shouldMask)
	"""
	if _store.supports("update", item=webModule):
		return True, False
	if _store.supports("mask", item=webModule):
		from ..gui.webModulesManager import promptMask
		if promptMask(webModule):
			return False, True
		return False, False


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
	keepShowing = True
	force = False
	while keepShowing:
		if webModuleEditor.show(context):
			keepTrying = True
			while keepTrying:
				try:
					if new:
						webModule = context["webModule"] = \
							WebModule(data=context["data"])
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
						webModule.load(context["data"])
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


def hasCustomModule(name):
	if nvdaVersion < (2019, 3):
		# Python 2.x can't properly handle unicode module names, so convert them.
		name = name.encode("mbcs")
	return any(
		importer.find_module("webModules.{}".format(name))
		for importer in _importers
	)


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
	except:
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


def initialize():
	global _importers, _store
	
	import imp
	webModules = imp.new_module("webModules")
	webModules.__path__ = list()
	import sys
	sys.modules["webModules"] = webModules
	config.addConfigDirsToPythonPackagePath(webModules)
	webModules.__path__.insert(
		1 if config.conf["development"]["enableScratchpadDir"] else 0,
		os.path.join(globalVars.appArgs.configPath, "webModules")
	)
	_importers = list(pkgutil.iter_importers("webModules.__init__"))
	
	from ..store.webModule import WebModuleStore
	_store = WebModuleStore()


def terminate():
	import sys
	try:
		del sys.modules["webModules"]
	except KeyError:
		pass
	_importers = None
