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

__version__ = "2018.07.07"

__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import os
import wx

import api
import gui
from logHandler import log
import ui

from ..store import webModule as store
from ..store import DuplicateRefError
from ..store import MalformedRefError


def create(webModule, force=False, focus=None):
	store.getInstance().create(webModule, force=force)
	getWebModules(refresh=True)
	if focus:
		from .. import webAppScheduler
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=webModule,
			focus=focus
			)

def delete(webModule, prompt=True, focus=None):
	if prompt:
		from ..gui import webModulesManager
		if not webModulesManager.promptDelete(webModule):
			return False
	store.getInstance().delete(webModule)
	getWebModules(refresh=True)
	if focus:
		from .. import webAppSheduler
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=self.markerManager.webApp,
			focus=self.context["focusObject"]
			)
	return True

def getWebModules(refresh=False):
	global _webModuleCache
	if refresh or "_webModuleCache" not in globals():
		_webModuleCache = list(store.getInstance().list())
	return _webModuleCache

def update(webModule, force=False, focus=None):
	store.getInstance().update(webModule, force=force)
	getWebModules(refresh=True)
	if focus:
		from .. import webAppScheduler
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=webModule,
			focus=focus
			)

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
							webModule,
							force=force,
							focus=context.get("focusObject")
							)
						# Translators: Confirmation message after web module creation.
						ui.message(
							_("Your new web module %s has been created.")
							% webModule.name
							) 
					else:
						webModule = context["webModule"]
						webModule.load(context["data"])
						update(
							webModule,
							force=force,
							focus=context.get("focusObject")
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