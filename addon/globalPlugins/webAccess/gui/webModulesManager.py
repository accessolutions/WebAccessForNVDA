# globalPlugins/webAccess/gui/webModulesManager.py
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


__version__ = "2021.01.05"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import os
import wx

import addonHandler
addonHandler.initTranslation()
import config
import core
import globalVars
import gui
import languageHandler
from logHandler import log

try:
	from gui.nvdaControls import AutoWidthColumnListCtrl
except ImportError:
	from ..backports.nvda_2016_4.gui_nvdaControls import AutoWidthColumnListCtrl


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


def show(context):
	gui.mainFrame.prePopup()
	Dialog(gui.mainFrame).Show(context)
	gui.mainFrame.postPopup()


class Dialog(wx.Dialog):
	# Singleton
	_instance = None
	def __new__(cls, *args, **kwargs):
		if Dialog._instance is None:
			return super(Dialog, cls).__new__(cls, *args, **kwargs)
		return Dialog._instance

	def __init__(self, parent):
		if Dialog._instance is not None:
			return
		Dialog._instance = self

		super(Dialog, self).__init__(
			parent,
			# Translators: The title of the Web Modules Manager dialog
			title=_("Web Modules Manager"),
			style=wx.DEFAULT_DIALOG_STYLE|wx.MAXIMIZE_BOX|wx.RESIZE_BORDER,
			#size=(600,400)
			)
		
		modulesListLabel = wx.StaticText(
			self,
			# Translators: The label for the modules list in the
			# Web Modules dialog.
			label=_("Available Web Modules:"),
			)

		item = self.modulesList = AutoWidthColumnListCtrl(
			self,
			style=wx.LC_REPORT|wx.LC_SINGLE_SEL,
			#size=(550,350),
			)
		# Translators: The label for a column of the web modules list
		item.InsertColumn(0, _("Name"), width=150)
		# Translators: The label for a column of the web modules list
		item.InsertColumn(1, _("Trigger"))
		## Translators: The label for a column of the web modules list
		##item.InsertColumn(1, _("URL"), width=50)
		#item.InsertColumn(1, _("URL"))
		## Translators: The label for a column of the web modules list
		##item.InsertColumn(2, _("Title"), width=50)
		#item.InsertColumn(2, _("Title"))
		item.resizeLastColumn(50)
		item.Bind(
			wx.EVT_LIST_ITEM_FOCUSED,
			self.onModulesListItemSelected)
		
		item = self.moduleCreateButton = wx.Button(
			self,
			# Translators: The label for a button in the Web Modules Manager
			label=_("&New web module..."),
			)
		item.Bind(wx.EVT_BUTTON, self.onModuleCreate)
		
		# Translators: The label for a button in the Web Modules Manager dialog
		item = self.moduleEditButton = wx.Button(self, label=_("&Edit..."))
		item.Disable()
		item.Bind(wx.EVT_BUTTON, self.onModuleEdit)
		
		# Translators: The label for a button in the Web Modules Manager dialog
		item = self.rulesManagerButton = wx.Button(self, label=_("Manage &rules..."))
		item.Disable()
		item.Bind(wx.EVT_BUTTON, self.onRulesManager)
		
		item = self.moduleDeleteButton = wx.Button(
			self,
			# Translators: The label for a button in the
			# Web Modules Manager dialog
			label=_("&Delete"))
		item.Disable()
		item.Bind(wx.EVT_BUTTON, self.onModuleDelete)
				
		vSizer = wx.BoxSizer(wx.VERTICAL)
		vSizer.Add(self.moduleCreateButton, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=4)
		vSizer.Add(self.moduleEditButton, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=4)
		vSizer.Add(self.rulesManagerButton, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=4)
		vSizer.Add(self.moduleDeleteButton, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=4)
		
		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		hSizer.Add(self.modulesList, proportion=1, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=4)
		hSizer.Add(vSizer)

		vSizer = wx.BoxSizer(wx.VERTICAL)
		vSizer.Add(modulesListLabel, flag=wx.EXPAND|wx.LEFT|wx.RIGHT, border=4)
		vSizer.Add(hSizer, proportion=1, flag=wx.EXPAND|wx.DOWN, border=4)
		vSizer.Add(
			self.CreateSeparatedButtonSizer(wx.CLOSE),
			flag=wx.EXPAND|wx.ALIGN_LEFT|wx.TOP|wx.DOWN,
			border=4
			)
		
		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		hSizer.Add(vSizer, proportion=1, flag=wx.EXPAND|wx.ALL, border=4)
		
		self.Sizer = hSizer
		
	
	def __del__(self):
		Dialog._instance = None
	
	def initData(self, context):
		self.context = context
		module = context["webModule"] if "webModule" in context else None
		self.refreshModulesList(selectItem=module)
	
	def onModuleCreate(self, evt=None):
		from .. import webModuleHandler
		context = dict(self.context)  # Shallow copy
		webModuleHandler.showCreator(context)
		if "webModule" in context:
			module = context["webModule"]
			self.refreshModulesList(selectItem=module) 
	
	def onModuleDelete(self, evt=None):
		index = self.modulesList.GetFirstSelected()
		if index < 0:
			return
		pass
		webModule = self.modules[index]
		from .. import webModuleHandler
		if webModuleHandler.delete(webModule=webModule):
			self.refreshModulesList()

	def onModuleEdit(self, evt=None):
		index = self.modulesList.GetFirstSelected()
		if index < 0:
			return
		context = dict(self.context)  # Shallow copy
		context["webModule"] = self.modules[index]
		from .. import webModuleHandler
		webModuleHandler.showEditor(context)
		self.refreshModulesList(selectIndex=index)
	
	def onModulesListItemSelected(self, evt):
		index = evt.GetIndex()
		item = self.modules[index] if index >= 0 else None
		self.moduleEditButton.Enable(item is not None)
		self.rulesManagerButton.Enable(
			item is not None
			and hasattr(item, "markerManager")
			and item.markerManager.isReady
			)
		self.moduleDeleteButton.Enable(item is not None)
	
	def onRulesManager(self, evt=None):
		index = self.modulesList.GetFirstSelected()
		if index < 0:
			return
		webModule = self.modules[index]
		context = self.context.copy()  # Shallow copy
		context["webModule"] = self.modules[index]
		from .. import ruleHandler
		ruleHandler.showManager(context)

	def refreshModulesList(self, selectIndex=0, selectItem=None):
		self.modulesList.DeleteAllItems()
		modules = self.modules = []
		modulesList = self.modulesList
		
		from .. import webModuleHandler
		for index, module in enumerate(webModuleHandler.getWebModules()):
			if module is selectItem:
				selectIndex = index
			trigger = (" %s " % _("and")).join(
				([
					"url=%s" % url
					for url in (module.url if module.url else [])
					])
				+ (
					["title=%s" % module.windowTitle]
					if module.windowTitle else []
					)
				)
			modulesList.Append((
				module.name,
				trigger,
				#module.url,
				#module.windowTitle,
				))
			modules.append(module)

		# Select the item at given index, or the first item if unspecified
		len_ = len(modules)
		if len_ > 0:
			if selectIndex == -1:
				selectIndex = len_ - 1
			elif selectIndex<0 or selectIndex>=len_:
				selectIndex = 0
			modulesList.Select(selectIndex, on=1)
			modulesList.Focus(selectIndex)
		else:
			self.moduleEditButton.Disable()
			self.rulesManagerButton.Disable()
			self.moduleDeleteButton.Disable()
	
	def Show(self, context):
		self.initData(context)
		self.Fit()
		self.modulesList.SetFocus()
		self.CentreOnScreen()
		return super(Dialog, self).Show()