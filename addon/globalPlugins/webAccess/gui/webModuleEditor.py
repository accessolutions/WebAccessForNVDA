# globalPlugins/webAccess/gui/webModuleEditor.py
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
from gui import guiHelper
from logHandler import log
import ui

from ..webModuleHandler import WebModule, getEditableWebModule, getUrl, getWindowTitle, save
from . import ContextualDialog, showContextualDialog


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


class Dialog(ContextualDialog):

	def __init__(self, parent):
		super().__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		scale = self.scale
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		gbSizer = wx.GridBagSizer()
		mainSizer.Add(
			gbSizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL,
			border=guiHelper.BORDER_FOR_DIALOGS
		)

		row = 0
		# Translators: The label for a field in the WebModule editor
		item = wx.StaticText(self, label=_("Web module name:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.webModuleName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))

		row += 1
		# Translators: The label for a field in the WebModule editor
		item = wx.StaticText(self, label=_("URL:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.webModuleUrl = wx.ComboBox(self, choices=[])
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))

		row += 1
		# Translators: The label for a field in the WebModule editor
		item = wx.StaticText(self, label=_("Window title:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.webModuleWindowTitle = wx.ComboBox(self, choices=[])
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))

		row += 1
		# Translators: The label for a field in the WebModule editor
		item = wx.StaticText(self, label=_("Help (in Markdown):"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.help = wx.TextCtrl(self, style=wx.TE_MULTILINE)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		gbSizer.AddGrowableCol(2)
		gbSizer.AddGrowableRow(row)

		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.TOP | wx.DOWN,
			border=scale(guiHelper.BORDER_FOR_DIALOGS),
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.SetSize(scale(790, 400))
		self.SetSizer(mainSizer)
		self.CentreOnScreen()
		self.webModuleName.SetFocus()

	def initData(self, context):
		super().initData(context)
		data = context.setdefault("data", {})["webModule"] = {}
		if not context.get("new"):
			webModule = context.get("webModule")
			data.update(webModule.dump(webModule.layers[-1].name).data["WebModule"])
			# Translators: Web module edition dialog title
			title = _("Edit Web Module")
			if config.conf["webAccess"]["devMode"]:
				title += " ({})".format("/".join((layer.name for layer in webModule.layers)))
		else:
			# Translators: Web module creation dialog title
			title = _("New Web Module")
			if config.conf["webAccess"]["devMode"]:
				from .. import webModuleHandler
				try:
					guineaPig = getEditableWebModule(WebModule(), prompt=False)
					store = next(iter(webModuleHandler.store.getSupportingStores(
						"create",
						item=guineaPig
					))) if guineaPig is not None else None
					title += " ({})".format(
						store and ("user" if store.name == "userConfig" else store.name)
					)
				except Exception:
					log.exception()
		self.Title = title

		self.webModuleName.Value = data.get("name", "")

		urls = []
		selectedUrl = None
		if data.get("url"):
			url = selectedUrl = ", ".join(data["url"])
			for candidate in itertools.chain([url], data["url"]):
				if candidate not in urls:
					urls.append(candidate)
		if "focusObject" in context:
			focus = context["focusObject"]
			if focus and focus.treeInterceptor and focus.treeInterceptor.rootNVDAObject:
				urlFromObject = getUrl(focus.treeInterceptor.rootNVDAObject)
				if not urlFromObject:
					if context.get("new"):
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
		if data.get("windowTitle"):
			windowTitleIsFilled = True
			windowTitleChoices.append(data["windowTitle"])
		if "focusObject" in context:
			obj = context["focusObject"]
			windowTitle = getWindowTitle(obj)
			if windowTitle and windowTitle not in windowTitleChoices:
				windowTitleChoices.append(windowTitle)
		item = self.webModuleWindowTitle
		item.SetItems(windowTitleChoices)
		if windowTitleIsFilled:
			item.Selection = 0
		else:
			item.Value = ""

		self.help.Value = data.get("help", "")

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
		if context.get("new"):
			webModule = WebModule()
		else:
			webModule = context["webModule"]
		if webModule.isReadOnly():
			webModule = getEditableWebModule(webModule)
			if not webModule:
				return

		webModule.name = name
		webModule.url = url
		webModule.windowTitle = windowTitle
		webModule.help = help

		if not save(webModule, prompt=self.Title):
			return

		self.DestroyLater()
		self.SetReturnCode(wx.ID_OK)


def show(context, parent=None):
	return showContextualDialog(Dialog, context, parent or gui.mainFrame) == wx.ID_OK
