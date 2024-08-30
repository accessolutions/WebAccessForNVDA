# globalPlugins/webAccess/gui/menu.py
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


__authors__ = (
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)

 
import wx

import addonHandler
import config
import gui

from ... import webAccess
from .. import ruleHandler
from ..utils import guarded


addonHandler.initTranslation()


@guarded
def show(context):
	Menu(context).show()

class Menu(wx.Menu):
	
	def __init__(self, context):
		super().__init__()
		
		self.context = context
		
		if webAccess.webAccessEnabled:
			webModule = context.get("webModule")
			
			if webModule:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("&New rule...")
				)
				self.Bind(wx.EVT_MENU, self.onRuleCreate, item)
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("Manage &rules...")
				)
				self.Bind(wx.EVT_MENU, self.onRulesManager, item)
				self.AppendSeparator()
			
			if not webModule:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("&New web module..."))
				self.Bind(wx.EVT_MENU, self.onWebModuleCreate, item)
			
			stack = context.get("webModuleStackAtCaret", []).copy()
			if stack:
				subMenu = wx.Menu()
				while stack:
					mod = stack.pop(0)
					handler = lambda evt, webModule=mod: self.onWebModuleEdit(evt, webModule=webModule)
					item = subMenu.Append(wx.ID_ANY, mod.name)
					subMenu.Bind(wx.EVT_MENU, handler, item)
				self.AppendSubMenu(
					subMenu,
					# Translators: Web Access menu item label.
					_("Edit &web module")
				)
			elif webModule:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("Edit &web module %s...") % webModule.name
				)
				self.Bind(wx.EVT_MENU, self.onWebModuleEdit, item)
			
			item = self.Append(
				wx.ID_ANY,
				# Translators: Web Access menu item label.
				_("Manage web &modules...")
			)
			self.Bind(wx.EVT_MENU, self.onWebModulesManager, item)
			
			self.AppendSeparator()
		
		if config.conf["webAccess"]["devMode"]:
			item = self.Append(
				wx.ID_ANY,
				# Translators: Web Access menu item label.
				_("&Element description...")
			)
			self.Bind(wx.EVT_MENU, self.onElementDescription, item)
			
			self.AppendSeparator()
		
		item = self.AppendCheckItem(
			wx.ID_ANY,
			# Translators: Web Access menu item label.
			_("Temporarily &disable all web modules"),
		)
		item.Check(not webAccess.webAccessEnabled)
		self.Bind(wx.EVT_MENU, self.onWebAccessToggle, item)
	
	def show(self):
		gui.mainFrame.prePopup(contextMenuName="Web Access")
		gui.mainFrame.PopupMenu(self)
		gui.mainFrame.postPopup()
	
	@guarded
	def onElementDescription(self, evt):
		from .elementDescription import showElementDescriptionDialog
		showElementDescriptionDialog()
	
	@guarded
	def onRuleCreate(self, evt):
		self.context["new"] = True
		from .rule.editor import show
		show(self.context, gui.mainFrame)
	
	@guarded
	def onRulesManager(self, evt):
		from .rule.manager import show
		show(self.context, gui.mainFrame)
	
	@guarded
	def onWebModuleCreate(self, evt, webModule=None):
		self.context["new"] = True
		from .webModule.editor import show
		show(self.context)
	
	@guarded
	def onWebModuleEdit(self, evt, webModule=None):
		if webModule is not None:
			self.context["webModule"] = webModule
		from .webModule.editor import show
		show(self.context)
	
	@guarded
	def onWebModulesManager(self, evt):
		from .webModule.manager import show
		show(self.context)
	
	@guarded
	def onWebAccessToggle(self, evt):
		self.context["webAccess"].script_toggleWebAccessSupport(None)
