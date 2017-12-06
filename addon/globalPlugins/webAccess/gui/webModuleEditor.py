# globalPlugins/webAccess/gui/webModuleEditor.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2016 Accessolutions (http://accessolutions.fr)
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

__version__ = "2016.11.29"

__author__ = (
	"Yannick Plassiard <yan@mistigri.org>"
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>"
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
	)


import itertools
import os
import wx

import addonHandler
addonHandler.initTranslation()
from logHandler import log
import api
import controlTypes
import gui
from NVDAObjects import NVDAObject, IAccessible
import ui


def getUrlFromObject(obj, depth=20):
	found = False
	i = 0
	url = None
	while obj is not None and i < depth and found is False:
		if obj.role == controlTypes.ROLE_DOCUMENT:
			try:
				url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
			except:
				log.exception("Error searching for url.")
				obj = obj.parent
				i += 1
				continue
			if url is not None:
				found = True
				break
		i += 1
		obj = obj.parent
	if found:
		return url
	else:
		return None

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

		vSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND|wx.TOP|wx.DOWN,
			border=4
			)
		
		hSizer = wx.BoxSizer(wx.HORIZONTAL)
		hSizer.Add(
			vSizer,
			proportion=1,
			flag=wx.EXPAND|wx.ALL,
			border=4
			)
		
		self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
		self.Sizer = hSizer
	
	def InitData(self, context):
		self.context = context
		if "data" not in context:
			context["data"] = {}
		if "WebModule" not in context["data"]:
			data = self.data = context["data"]["WebModule"] = {}
		else:
			data = self.data = context["data"]["WebModule"]
		webModule = context["webModule"] if "webModule" in context else None
		
		if webModule is None:
			# Translators: Web module creation dialog title
			title = _("New Web Module")
		else:
			# Translators: Web module edition dialog title
			title = _("Edit Web Module")
		self.Title = title
		
		if "name" in data:
			name = data["name"]
		elif webModule is not None:
			name = webModule.name
		else:
			name = ""
		self.webModuleName.Value = name
		
		urls = []
		selectedUrl = None
		if "url" in data:
			url = ", ".join(data["url"])
			selectedUrl = url
			urls.append(url)
			for url in itertools.chain([url], data["url"]):
				if url not in urls:
					urls.append(url)
		if webModule is not None:
			url = ", ".join(webModule.url)
			if not selectedUrl:
				selectedUrl = url
			for url_ in itertools.chain([url], webModule.url):
				if url_ not in urls:
					urls.append(url_)
		if "focusObject" in context:
			urlFromObject = getUrlFromObject(context["focusObject"])
			log.info("urlFromObject: %s" % urlFromObject)
			if urlFromObject is None:
				if webModule is None:
					ui.message(_("URL not found"))
			elif urlFromObject not in urls:
				urls.append(urlFromObject)
		else:
			log.warn("focusObject not in context")
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
		if "windowTitle" in data:
			windowTitleIsFilled = True
			windowTitleChoices.append(
				data["windowTitle"]
				if data["windowTitle"]
				else ""
				)
		if (
				webModule is not None
				and webModule.windowTitle not in windowTitleChoices
				):
			windowTitleIsFilled = True
			windowTitleChoices.append(
				webModule.windowTitle
				if webModule.windowTitle
				else ""
				)
			windowTitleFilled = True
		if "focusObject" in context:
			obj = context["focusObject"]
			if obj.windowText not in windowTitleChoices:
				windowTitleChoices.append(obj.windowText)
		item = self.webModuleWindowTitle
		log.info("windowTitleChoices: %s" % windowTitleChoices)
		item.SetItems(windowTitleChoices)
		if windowTitleIsFilled:
			item.Selection = 0
		else:
			item.Value = ""
	
	def OnOk(self, evt):
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

		url = self.webModuleUrl.Value.strip()
		windowTitle = self.webModuleWindowTitle.Value.strip()
		if len(url) < 1 and len(title) < 1:
			gui.messageBox(
				_("You must specify an URL or window name"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				self,
				)
			self.webModuleUrl.SetFocus()
			return
		
		data = self.data
		data["name"] = name
		data["url"] = url.split(", ")
		data["windowTitle"] = windowTitle
		
		assert self.IsModal()
		self.EndModal(wx.ID_OK)

	def OnCancel(self, evt):
		self.data.clear()
		self.EndModal(wx.ID_CANCEL)
		
	def ShowModal(self, context):
		self.InitData(context)
		self.Fit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.webModuleName.SetFocus()
		return super(Dialog, self).ShowModal()
	
