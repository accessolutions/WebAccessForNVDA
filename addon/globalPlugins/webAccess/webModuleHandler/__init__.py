# globalPlugins/webAccess/webModuleHandler/__init__.py
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

"""Web Access GUI."""

from __future__ import absolute_import

__version__ = "2019.10.23"

__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import os
import wx

import api
import gui
from logHandler import log
import ui

from .webModule import InvalidApiVersion, NewerFormatVersion, WebModule
from ..store import webModule as store
from ..store import DuplicateRefError
from ..store import MalformedRefError


_catalog = None
_webModules = None


def create(webModule, focus, force=False):
	store.getInstance().create(webModule, force=force)
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
	store.getInstance().delete(webModule)
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
	if not refresh:
		if _catalog:
			return _catalog
	else:
		global _webModules
		_webModules = None
	global _catalog
	_catalog = list(store.getInstance().catalog(errors=errors))
	return _catalog

def getWebModuleForTreeInterceptor(treeInterceptor):
	obj = treeInterceptor.rootNVDAObject
	windowTitle = _getWindowTitle(obj)
	if windowTitle:
		mod = getWebModuleForWindowTitle(windowTitle)
		if mod:
			return mod
	try:
		url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
	except: 
		url = None
	if url:
		return getWebModuleForUrl(url)
	return None

def getWebModuleForWindowTitle(windowTitle):
	if not windowTitle:
		return None
	for ref, meta in getCatalog():
		if meta.get("windowTitle") == windowTitle:
			return store.getInstance().get(ref)

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
		return store.getInstance().get(matchedRef)

def _getWindowTitle(obj):
	windowText = obj.windowText
	if windowText == u"Chrome Legacy Window" and obj.parent:
		return _getWindowTitle(obj.parent)
	return windowText


def getWebModules(refresh=False, errors=None):
	if not refresh:
		if _webModules:
			return _webModules
	else:
		global _catalog
		_catalog = None
	global _webModules
	_webModules = list(store.getInstance().list(errors=errors))
	return _webModules


def update(webModule, focus, force=False):
	updatable, mask = checkUpdatable(webModule)
	if mask:
		return create(webModule, focus, force=force)
	if updatable:
		store.getInstance().update(webModule, force=force)
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
	store_ = store.getInstance()
	if store_.supports("update", item=webModule):
		return True, False
	if store_.supports("mask", item=webModule):
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
