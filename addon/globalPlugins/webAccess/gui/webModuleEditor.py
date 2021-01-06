# globalPlugins/webAccess/gui/webModuleEditor.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2019 Accessolutions (http://accessolutions.fr)
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

__version__ = "2020.12.22"

__author__ = (
	"Yannick Plassiard <yan@mistigri.org>"
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>"
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
)


import itertools
import os
import wx

from NVDAObjects import NVDAObject, IAccessible
import addonHandler
import api
import controlTypes
import config
import gui
from logHandler import log
import ui

from ..webModuleHandler import WebModule, getEditableWebModule, save


addonHandler.initTranslation()


def promptOverwrite():
	return wx.MessageBox(
		parent=gui.mainFrame,
		message=(
				# Translators: Error message while naming a web module.
				_("A web module already exists with this name.")
				+ os.linesep
				# Translators: Prompt before overwriting a web module.
				+ _("Do you want to overwrite it?")
				),
		style=wx.YES_NO|wx.ICON_WARNING,
		) == wx.YES

def show(context):
	gui.mainFrame.prePopup()
	result = Dialog(gui.mainFrame).ShowModal(context)
	gui.mainFrame.postPopup()
	return result == wx.ID_OK

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
			style=wx.DEFAULT_DIALOG_STYLE|wx.MAXIMIZE_BOX|wx.RESIZE_BORDER,
		)

		vSizer = wx.BoxSizer(wx.VERTICAL)

		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: The label of a field to enter the name of the web module
		hSizer.Add(
			wx.StaticText(self, label=_("Web module name:")),
			flag=wx.ALL,
			border=4
		)
		item = self.webModuleName = wx.TextCtrl(self)
		hSizer.Add(
			item,
			proportion=1,
			flag=wx.ALL,
			border=4,
		)
		vSizer.Add(hSizer, flag=wx.EXPAND)
		
		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: The label of a field to enter the webModule URL
		hSizer.Add(
			wx.StaticText(self, label=_("URL:")),
			flag=wx.ALL,
			border=4
			)
		item = self.webModuleUrl = wx.ComboBox(self, choices=[])
		hSizer.Add(
			item,
			proportion=1,
			flag=wx.ALL,
			border=4,
		)
		vSizer.Add(hSizer, flag=wx.EXPAND)

		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: The label of a field to enter the window title
		hSizer.Add(
			wx.StaticText(self, label=_("Window title:")),
			flag=wx.ALL,
			border=4
		)
		item = self.webModuleWindowTitle = wx.ComboBox(self, choices=[])
		hSizer.Add(
			item,
			proportion=1,
			flag=wx.ALL,
			border=4,
		)
		vSizer.Add(hSizer, flag=wx.EXPAND)
		
		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		# Translators: The label of a field to enter the window title
		hSizer.Add(
			wx.StaticText(self, label=_("Help (in Markdown):")),
			flag=wx.ALL,
			border=4
		)
		item = self.help = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 300))
		hSizer.Add(
			item,
			proportion=1,
			flag=wx.ALL,
			border=4,
		)
		vSizer.Add(hSizer, flag=wx.EXPAND)

		vSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.TOP | wx.DOWN,
			border=4
		)
		
		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		hSizer.Add(
			vSizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL,
			border=4
		)
		
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
		self.Sizer = hSizer
	
	def initData(self, context):
		self.context = context
		webModule = context.get("webModule")
		if webModule is None:
			new = True
			webModule = WebModule()
		else:
			if any(layer.dirty and layer.storeRef is None for layer in webModule.layers):
				new = True
			elif any(layer.storeRef is not None for layer in webModule.layers):
				new = False
			else:
				new = True
		
		if new:
			# Translators: Web module creation dialog title
			title = _("New Web Module")
		else:
			# Translators: Web module edition dialog title
			title = _("Edit Web Module")
		if config.conf["webAccess"]["devMode"] and webModule is not None:
			title += " ({})".format("/".join((layer.name for layer in webModule.layers)))
		self.Title = title
		
		self.webModuleName.Value = (webModule.name or "") if webModule is not None else ""
		
		urls = []
		selectedUrl = None
		if webModule is not None and webModule.url:
			url = selectedUrl = ", ".join(webModule.url)
			for candidate in itertools.chain([url], webModule.url):
				if candidate not in urls:
					urls.append(candidate)
		if "focusObject" in context:
			focus = context["focusObject"]
			if focus and focus.treeInterceptor and focus.treeInterceptor.rootNVDAObject:
				from ..webModuleHandler import getUrl
				urlFromObject = getUrl(focus.treeInterceptor.rootNVDAObject)
				if not urlFromObject:
					if not webModule:
						ui.message(_("URL not found"))
				elif urlFromObject not in urls:
					urls.append(urlFromObject)
		else:
			log.warning("focusObject not in context")
		urlsChoices = []
		for url in urls:
			choice = url
			urlChoices = [choice]
			# Strip protocol
			if "://" in choice:
				choice = choice.split("://", 1)[-1]
				urlChoices.insert(0, choice)
			# Strip parameters
			if "?" in choice:
				choice = choice.rsplit('?', 1)[0]
				urlChoices.insert(0, choice)
			# Strip directories
			while "/" in choice[1:]:
				choice = choice.rsplit('/', 1)[0]
				urlChoices.insert(0, choice)
			# Reverse order for local resources (most specific first)
			if url.startswith("file:") or url.startswith("/"):
				urlChoices.reverse()
			urlsChoices.extend(urlChoices)
		urlsChoicesSet = set()
		urlsChoices = [
			choice
			for choice in urlsChoices
			if not(choice in urlsChoicesSet or urlsChoicesSet.add(choice))
		]
		self.webModuleUrl.SetItems(urlsChoices)
		self.webModuleUrl.Selection = (
			urlsChoices.index(selectedUrl)
			if selectedUrl
			else 0
		)
		
		windowTitleChoices = []
		windowTitleIsFilled = False 
		if webModule is not None and webModule.windowTitle:
			windowTitleIsFilled = True
			windowTitleChoices.append(webModule.windowTitle)
		if "focusObject" in context:
			obj = context["focusObject"]
			from ..webModuleHandler import getWindowTitle
			windowTitle = getWindowTitle(obj)
			if windowTitle and windowTitle not in windowTitleChoices:
				windowTitleChoices.append(windowTitle)
		item = self.webModuleWindowTitle
		item.SetItems(windowTitleChoices)
		if windowTitleIsFilled:
			item.Selection = 0
		else:
			item.Value = ""
		
		self.help.Value = webModule.help if webModule and webModule.help else ""
	
	def onOk(self, evt):
		name = self.webModuleName.Value.strip() 
		if len(name) < 1:
			gui.messageBox(
				_("You must enter a name for this web module"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				self
			)
			self.webModuleName.SetFocus()
			return

		url = [url.strip() for url in self.webModuleUrl.Value.split(",") if url.strip()]
		windowTitle = self.webModuleWindowTitle.Value.strip()
		help = self.help.Value.strip()
		if not (url or windowTitle):
			gui.messageBox(
				_("You must specify at least a URL or a window title."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			self.webModuleUrl.SetFocus()
			return
		
		context = self.context
		webModule = context.get("webModule")
		if webModule is None:
			webModule = context["webModule"] = WebModule()
		if webModule.isReadOnly():
			webModule = getEditableWebModule(webModule)
			if not webModule:
				return
		
		webModule.name = name
		webModule.url = url
		webModule.windowTitle = windowTitle
		webModule.help = help
		
		if not save(webModule):
			return
		
		assert self.IsModal()
		self.EndModal(wx.ID_OK)

	def onCancel(self, evt):
		self.EndModal(wx.ID_CANCEL)
		
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.webModuleName.SetFocus()
		return super(Dialog, self).ShowModal()
	
