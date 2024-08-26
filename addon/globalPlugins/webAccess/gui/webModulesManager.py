# globalPlugins/webAccess/gui/webModulesManager.py
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


__authors__ = (
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


import os
import wx

import addonHandler
addonHandler.initTranslation()
import config
import core
import globalVars
import gui
from gui import guiHelper
import languageHandler
from logHandler import log

from ..utils import guarded
from . import ContextualDialog, ListCtrlAutoWidth, showContextualDialog


def promptDelete(webModule):
	msg = (
		# Translators: Prompt before deleting a web module.
		_("Do you really want to delete this web module?")
		+ os.linesep
		+ str(webModule.name)
	)
	if config.conf["webAccess"]["devMode"]:
		msg += " ({})".format("/".join((layer.name for layer in webModule.layers)))
	return gui.messageBox(
		parent=gui.mainFrame,
		message=msg,
		style=wx.YES_NO | wx.ICON_WARNING
	) == wx.YES


def promptMask(webModule):
	ref = webModule.getLayer("addon", raiseIfMissing=True).storeRef
	if ref[0] != "addons":
		raise ValueError("ref={!r}".format(ref))
	addonName = ref[1]
	for addon in addonHandler.getRunningAddons():
		if addon.name == addonName:
			addonSummary = addon.manifest["summary"]
			break
	else:
		raise LookupError("addonName={!r}".format(addonName))
	log.info("Proposing to mask {!r} from addon {!r}".format(webModule, addonName))
	msg = _(
		"""This web module comes with the add-on {addonSummary}.
It cannot be modified at its current location.

Do you want to make a copy in your scratchpad?
"""
	).format(addonSummary=addonSummary)
	return gui.messageBox(
		parent=gui.mainFrame,
		message=msg,
		caption=_("Warning"),
		style=wx.ICON_WARNING | wx.YES | wx.NO
	) == wx.YES


class Dialog(ContextualDialog):
	
	def __init__(self, parent):
		super().__init__(
			parent,
			# Translators: The title of the Web Modules Manager dialog
			title=_("Web Modules Manager"),
			style=wx.DEFAULT_DIALOG_STYLE|wx.MAXIMIZE_BOX|wx.RESIZE_BORDER,
		)		
		scale = self.scale
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		gbSizer = wx.GridBagSizer()
		mainSizer.Add(
			gbSizer,
			border=scale(guiHelper.BORDER_FOR_DIALOGS),
			flag=wx.ALL | wx.EXPAND,
			proportion=1
		)
		row = 0
		col = 0
		item = modulesListLabel = wx.StaticText(
			self,
			# Translators: The label for the modules list in the
			# Web Modules dialog.
			label=_("Available Web Modules:"),
		)
		gbSizer.Add(item, (row, col), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), (row, col))
		
		row += 1
		item = self.modulesList = ListCtrlAutoWidth(self, style=wx.LC_REPORT)
		# Translators: The label for a column of the web modules list
		item.InsertColumn(0, _("Name"), width=150)
		# Translators: The label for a column of the web modules list
		item.InsertColumn(1, _("Trigger"))
		item.Bind(
			wx.EVT_LIST_ITEM_FOCUSED,
			self.onModulesListItemSelected)
		gbSizer.Add(item, (row, col), span=(8, 1), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row+7)
		gbSizer.AddGrowableCol(col)
		
		col += 1
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), (row, col))
		
		col += 1
		item = self.moduleCreateButton = wx.Button(
			self,
			# Translators: The label for a button in the Web Modules Manager
			label=_("&New web module..."),
		)
		item.Bind(wx.EVT_BUTTON, self.onModuleCreate)
		gbSizer.Add(item, (row, col), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), (row, col))
		
		row += 1
		# Translators: The label for a button in the Web Modules Manager dialog
		item = self.moduleEditButton = wx.Button(self, label=_("&Edit..."))
		item.Disable()
		item.Bind(wx.EVT_BUTTON, self.onModuleEdit)
		gbSizer.Add(item, (row, col), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), (row, col))
		
		row += 1
		# Translators: The label for a button in the Web Modules Manager dialog
		item = self.rulesManagerButton = wx.Button(self, label=_("Manage &rules..."))
		item.Disable()
		item.Bind(wx.EVT_BUTTON, self.onRulesManager)
		gbSizer.Add(item, (row, col), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), (row, col))
		
		row += 1
		item = self.moduleDeleteButton = wx.Button(
			self,
			# Translators: The label for a button in the
			# Web Modules Manager dialog
			label=_("&Delete"))
		item.Disable()
		item.Bind(wx.EVT_BUTTON, self.onModuleDelete)
		gbSizer.Add(item, (row, col), flag=wx.EXPAND)

		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.CLOSE),
			flag=wx.EXPAND | wx.BOTTOM | wx.LEFT | wx.RIGHT,
			border=scale(guiHelper.BORDER_FOR_DIALOGS),
		)
		self.SetSize(scale(790, 400))
		self.SetSizer(mainSizer)
		self.CentreOnScreen()
		self.modulesList.SetFocus()
	
	def __del__(self):
		Dialog._instance = None
	
	def initData(self, context):
		super().initData(context)
		module = context["webModule"] if "webModule" in context else None
		self.refreshModulesList(selectItem=module)
	
	@guarded
	def onModuleCreate(self, evt=None):
		context = self.context.copy()
		context["new"] = True
		from .webModuleEditor import show
		if show(context, self):
			self.refreshModulesList(selectItem=context["webModule"])
	
	@guarded
	def onModuleDelete(self, evt=None):
		index = self.modulesList.GetFirstSelected()
		if index < 0:
			return
		webModule = self.modules[index]
		from .. import webModuleHandler
		if webModuleHandler.delete(webModule=webModule):
			self.refreshModulesList()
	
	@guarded
	def onModuleEdit(self, evt=None):
		index = self.modulesList.GetFirstSelected()
		if index < 0:
			wx.Bell()
			return
		context = self.context
		context.pop("new", None)
		context["webModule"] = self.modules[index]
		from .webModuleEditor import show
		if show(context, self):
			self.refreshModulesList(selectIndex=index)
	
	@guarded
	def onModulesListItemSelected(self, evt):
		self.refreshButtons()
	
	@guarded
	def onRulesManager(self, evt=None):
		index = self.modulesList.GetFirstSelected()
		if index < 0:
			wx.Bell()
			return
		webModule = self.modules[index]
		context = self.context
		if not webModule.equals(context.get("webModule")):
			context["webModule"] = webModule
			context.pop("result", None)
		from .rule.manager import show
		show(context, self)
	
	def refreshButtons(self):
		index = self.modulesList.GetFirstSelected()
		hasSelection = index >= 0
		self.moduleEditButton.Enable(hasSelection)
		self.rulesManagerButton.Enable(hasSelection)
		self.moduleDeleteButton.Enable(hasSelection)
	
	def refreshModulesList(self, selectIndex: int = None, selectItem: "WebModule" = None):
		ctrl = self.modulesList
		ctrl.DeleteAllItems()
		contextModule = self.context.get("webModule")
		contextModules = {
			(module.name, module.layers[0].storeRef): module
			for module in list(reversed(contextModule.ruleManager.subModules.all())) + [contextModule]
		} if contextModule else {}
		modules = self.modules = []
		from .. import webModuleHandler
		for index, module in enumerate(webModuleHandler.getWebModules()):
			if selectIndex is None and module.equals(selectItem):
				selectIndex = index
			module = contextModules.get((module.name, module.layers[0].storeRef), module)
			trigger = (" %s " % _("and")).join(
				([
					"url=%s" % url
					for url in (module.url if module.url else [])
				]) + (
					["title=%s" % module.windowTitle]
					if module.windowTitle else []
				)
			)
			ctrl.Append((
				module.name,
				trigger,
			))
			modules.append(module)

		if selectIndex is None:
			selectIndex = min(0, len(modules) - 1)
		else:
			selectIndex %= len(modules)
		if selectIndex >= 0:
			ctrl.Select(selectIndex, on=1)
			ctrl.Focus(selectIndex)
		self.refreshButtons()


def show(context):
	showContextualDialog(Dialog, context, gui.mainFrame)
