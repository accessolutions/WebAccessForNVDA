# globalPlugins/webAccess/gui/menu.py
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


__version__ = "2021.03.12"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"

 
import wx

import addonHandler
addonHandler.initTranslation()
import gui

from ... import webAccess
from .. import ruleHandler
from .. import webModuleHandler  


def show(context):
	Menu(context).Show()

class Menu(wx.Menu):
	
	def __init__(self, context):
		super(Menu, self).__init__()
		
		self.context = context
		
		if webAccess.webAccessEnabled:
			webModule = context["webModule"] if "webModule" in context else None
			
			if webModule is not None:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("&New rule..."))
				self.Bind(wx.EVT_MENU, self.OnRuleCreate, item)
			
			if webModule is not None:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("Manage &rules..."))
				self.Bind(wx.EVT_MENU, self.OnRulesManager, item)
				self.AppendSeparator()
			
			if webModule is None:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("&New web module..."))
				self.Bind(wx.EVT_MENU, self.OnWebModuleCreate, item)
			else:
				item = self.Append(
					wx.ID_ANY,
					# Translators: Web Access menu item label.
					_("Edit &web module %s...") % webModule.name)
				self.Bind(wx.EVT_MENU, self.OnWebModuleEdit, item)
			
			item = self.Append(
				wx.ID_ANY,
				# Translators: Web Access menu item label.
				_("Manage web &modules...")
				)
			self.Bind(wx.EVT_MENU, self.OnWebModulesManager, item)
	
			self.AppendSeparator()

		item = self.AppendCheckItem(
			wx.ID_ANY,
			# Translators: Web Access menu item label.
			_("Temporarily &disable all web modules"),
			)
		item.Check(not webAccess.webAccessEnabled)
		self.Bind(wx.EVT_MENU, self.OnWebAccessToggle, item)
		
	def Show(self):
		gui.mainFrame.prePopup(contextMenuName="Web Access")
		gui.mainFrame.PopupMenu(self)
		gui.mainFrame.postPopup()
		
	def OnRuleCreate(self, evt):
		ruleHandler.showCreator(self.context)

	def OnRuleEdit(self, evt):
		pass

	def OnRulesManager(self, evt):
		ruleHandler.showManager(self.context)
		
	def OnWebModuleCreate(self, evt):
		webModuleHandler.showCreator(self.context)
	
	def OnWebModuleEdit(self, evt):
		webModuleHandler.showEditor(self.context)
	
	def OnWebModulesManager(self, evt):
		webModuleHandler.showManager(self.context)
	
	def OnWebAccessToggle(self, evt):
		self.context["webAccess"].script_toggleWebAccessSupport(None)
	
	
