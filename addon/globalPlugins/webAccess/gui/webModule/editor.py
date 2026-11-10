# globalPlugins/webAccess/gui/webModule/editor.py
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
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


from collections import OrderedDict
from copy import deepcopy
import itertools
import os
from typing import Any
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

from ... import profiles
from ...utils import guarded
from ...webModuleHandler import WebModule, getEditableWebModule, getUrl, getWindowTitle, save, store
from .. import ContextualDialog, showContextualDialog

from collections.abc import Mapping


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
		item = wx.StaticText(self, label=_("Configuration profile:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.webModuleProfile = wx.Choice(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))

		row += 1
		# Translators: The label for a field in the WebModule editor
		item = wx.StaticText(self, label=_("Embedded profiles:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		sizer = wx.BoxSizer(wx.HORIZONTAL)
		item = self.embeddedProfiles = wx.ListBox(self)
		item.Bind(wx.EVT_LISTBOX, lambda evt: self.updateEmbeddedProfilesButtons())
		sizer.Add(item, proportion=1, flag=wx.EXPAND)
		sizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0))
		buttons = guiHelper.ButtonHelper(wx.VERTICAL)
		# Translators: A button in the WebModule editor
		item = self.newEmbeddedProfileButton = buttons.addButton(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onNewEmbeddedProfile)
		# Translators: A button in the WebModule editor
		item = self.renameEmbeddedProfileButton = buttons.addButton(self, label=_("&Rename..."))
		item.Bind(wx.EVT_BUTTON, self.onRenameEmbeddedProfile)
		# Translators: A button in the WebModule editor
		item = self.deleteEmbeddedProfileButton = buttons.addButton(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteEmbeddedProfile)
		# Translators: A button in the WebModule editor
		item = self.editEmbeddedProfileButton = buttons.addButton(self, label=_("Save and &edit settings..."))
		item.Bind(wx.EVT_BUTTON, self.onEditEmbeddedProfile)
		sizer.Add(buttons.sizer)
		gbSizer.Add(sizer, pos=(row, 2), flag=wx.EXPAND)

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
		self.SetSize(scale(790, 560))
		self.SetSizer(mainSizer)
		self.CentreOnScreen()
		self.webModuleName.SetFocus()
	
	def getData(self) -> Mapping[str, Any]:
		return self.context["data"]["webModule"]
	
	def getProfilesData(self) -> Mapping[str, Any]:
		return self.context["data"]["profiles"]
	
	def initData(self, context):
		super().initData(context)
		data = context.setdefault("data", {}).setdefault("webModule", {})
		profilesData = context["data"].setdefault("profiles", OrderedDict())
		self.editEmbeddedProfileKey = None
		self.lockedEmbeddedProfileKeys = set()
		if not context.get("new"):
			webModule = context.get("webModule")
			data.update(webModule.dump(webModule.layers[-1].name).data["WebModule"])
			# Might be defined in a lower layer
			data["profile"] = webModule.configProfile or None
			# Could not have been saved without triggers from this editor unless invoked
			# from the Rule or Criteria editor.
			subModule = data["subModule"] = not (data.get("url") or data.get("windowTitle"))
			# Translators: Web module edition dialog title
			title = _("Edit Web Module")
			if config.conf["webAccess"]["devMode"]:
				title += " ({})".format("/".join((layer.name for layer in webModule.layers)))
			for key in webModule.getProfileKeys():
				profilesData.setdefault(key, deepcopy(webModule.getProfileData(key)))
			try:
				writableLayer = webModule.getWritableLayer()
			except LookupError:
				writableLayer = None
			# Keys defined in other layers cannot be renamed or deleted from this one
			self.lockedEmbeddedProfileKeys = {
				key
				for layer in webModule.layers
				if layer is not writableLayer
				for key in layer.data.get("Profiles", {})
			}
		else:
			subModule = data.get("subModule", False)
			# Translators: Web module creation dialog title
			title = _("New Web Module")
			if config.conf["webAccess"]["devMode"]:
				try:
					guineaPig = getEditableWebModule(WebModule(), prompt=False)
					supportingStore = next(iter(store.getSupportingStores(
						"create",
						item=guineaPig
					))) if guineaPig is not None else None
					title += " ({})".format(
						supportingStore and (
							"user" if supportingStore.name == "userConfig" else supportingStore.name
						)
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
			urlsChoices.index(selectedUrl) if selectedUrl else 0 if not subModule else -1
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

		self.editEmbeddedProfileButton.Show(self.Parent is gui.mainFrame)
		self.updateProfiles()
	
	def updateData(self):
		data = self.getData()
		data["name"] = self.webModuleName.Value.strip()
		data["url"] = [url.strip() for url in self.webModuleUrl.Value.split(",") if url.strip()]
		data["windowTitle"] = self.webModuleWindowTitle.Value.strip()
		data["profile"] = self.getSelectedProfile()
	
	def getSelectedProfile(self) -> str | None:
		index = self.webModuleProfile.Selection
		if index == wx.NOT_FOUND:
			return None
		return self.profileChoices[index]
	
	def getSelectedEmbeddedProfileKey(self) -> str | None:
		index = self.embeddedProfiles.Selection
		if index == wx.NOT_FOUND:
			return None
		return tuple(self.getProfilesData())[index]
	
	def updateProfiles(self, selectKey=None):
		"""Refresh the profile controls from `data["profile"]` and the embedded profiles data.
		"""
		profilesData = self.getProfilesData()
		selected = self.getData().get("profile")
		choices = profiles.getProfileChoices(profilesData)
		if selected and selected not in choices:
			choices[selected] = f"*{selected}"
		# Translators: The choice for no configuration profile in the WebModule editor
		labels = [pgettext("webAccess.profile", "None")] + list(choices.values())
		self.profileChoices = [None] + list(choices)
		self.webModuleProfile.SetItems(labels)
		self.webModuleProfile.Selection = self.profileChoices.index(selected or None)
		keys = tuple(profilesData)
		self.embeddedProfiles.SetItems([
			# Translators: An embedded profile defined in a read-only layer, in the WebModule editor
			_("{name} (inherited)").format(name=key) if key in self.lockedEmbeddedProfileKeys else key
			for key in keys
		])
		if selectKey is not None:
			self.embeddedProfiles.Selection = keys.index(selectKey)
		elif keys and self.embeddedProfiles.Selection == wx.NOT_FOUND:
			self.embeddedProfiles.Selection = 0
		self.updateEmbeddedProfilesButtons()
	
	def updateEmbeddedProfilesButtons(self):
		key = self.getSelectedEmbeddedProfileKey()
		unlocked = key is not None and key not in self.lockedEmbeddedProfileKeys
		self.renameEmbeddedProfileButton.Enable(unlocked)
		self.deleteEmbeddedProfileButton.Enable(unlocked)
		self.editEmbeddedProfileButton.Enable(key is not None)
	
	def countProfileReferences(self, key: str) -> int:
		"""The number of rules of the edited WebModule referencing the given profile.
		"""
		webModule = self.context.get("webModule")
		if self.context.get("new") or webModule is None:
			return 0
		count = 0
		for rule in webModule.ruleManager.getRules():
			if rule.properties.profile == key or any(
				criteria.properties.dump().get("profile") == key
				for criteria in rule.criteria
			):
				count += 1
		return count

	def confirmProfileReferences(self, key: str) -> bool:
		count = self.countProfileReferences(key)
		if not count:
			return True
		return gui.messageBox(
			# Translators: A warning in the WebModule editor
			_(
				"{count} rule(s) reference the embedded profile {name}. "
				"They will not be updated. Do you want to continue?"
			).format(count=count, name=key),
			# Translators: The title of a warning dialog
			_("Warning"),
			wx.YES_NO | wx.ICON_WARNING,
			self,
		) == wx.YES

	def promptEmbeddedProfileKey(self, title, value=""):
		original = value
		while True:
			with wx.TextEntryDialog(
				self,
				# Translators: The label of a field in the dialog to name an embedded profile
				_("Profile name:"),
				title,
				value=value,
			) as dlg:
				if dlg.ShowModal() != wx.ID_OK:
					return None
				key = dlg.Value.strip()
			if not key:
				continue
			if original and key == original:
				return None
			if key in self.getProfilesData():
				gui.messageBox(
					# Translators: An error message in the WebModule editor
					_("An embedded profile with this name already exists."),
					_("Error"),
					wx.OK | wx.ICON_ERROR,
					self,
				)
				value = key
				continue
			if key in config.conf.listProfiles() and gui.messageBox(
				# Translators: A warning in the WebModule editor
				_(
					"An NVDA profile with this name exists. "
					"The embedded profile will take precedence. Do you want to continue?"
				),
				# Translators: The title of a warning dialog
				_("Warning"),
				wx.YES_NO | wx.ICON_WARNING,
				self,
			) != wx.YES:
				value = key
				continue
			return key
	
	def onNewEmbeddedProfile(self, evt):
		self.getData()["profile"] = self.getSelectedProfile()
		# Translators: The title of the dialog to create an embedded profile
		key = self.promptEmbeddedProfileKey(_("New embedded profile"))
		if key is None:
			return
		self.getProfilesData()[key] = OrderedDict()
		self.updateProfiles(selectKey=key)
		self.embeddedProfiles.SetFocus()
	
	def onRenameEmbeddedProfile(self, evt):
		oldKey = self.getSelectedEmbeddedProfileKey()
		# Translators: The title of the dialog to rename an embedded profile
		newKey = self.promptEmbeddedProfileKey(_("Rename embedded profile"), value=oldKey)
		if newKey is None or not self.confirmProfileReferences(oldKey):
			return
		self.context["data"]["profiles"] = OrderedDict(
			(newKey if key == oldKey else key, value)
			for key, value in self.getProfilesData().items()
		)
		data = self.getData()
		data["profile"] = self.getSelectedProfile()
		if data["profile"] == oldKey:
			data["profile"] = newKey
		self.updateProfiles(selectKey=newKey)
		self.embeddedProfiles.SetFocus()
	
	def onDeleteEmbeddedProfile(self, evt):
		key = self.getSelectedEmbeddedProfileKey()
		if not self.confirmProfileReferences(key):
			return
		if gui.messageBox(
			# Translators: A confirmation prompt in the WebModule editor
			_("Are you sure you want to delete the embedded profile {name}?").format(name=key),
			# Translators: The title of a confirmation prompt
			_("Confirm Deletion"),
			wx.YES_NO | wx.ICON_QUESTION,
			self,
		) != wx.YES:
			return
		del self.getProfilesData()[key]
		data = self.getData()
		data["profile"] = self.getSelectedProfile()
		if data["profile"] == key:
			data["profile"] = None
		self.embeddedProfiles.Selection = wx.NOT_FOUND
		self.updateProfiles()
		self.embeddedProfiles.SetFocus()
	
	def onEditEmbeddedProfile(self, evt):
		self.editEmbeddedProfileKey = self.getSelectedEmbeddedProfileKey()
		try:
			self.onOk(evt)
		finally:
			if self.GetReturnCode() != wx.ID_OK:
				self.editEmbeddedProfileKey = None
	
	@guarded
	def onOk(self, evt):
		self.updateData()
		data = self.getData()
		name = data["name"]
		if len(name) < 1:
			gui.messageBox(
				_("You must enter a name for this web module"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				self
			)
			self.webModuleName.SetFocus()
			return

		subModule: bool = data.get("subModule", False)
		url = data["url"]
		windowTitle = data["windowTitle"]
		help = self.help.Value.strip()
		if not (url or windowTitle or subModule):
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
		if (webModule.configProfile or None) != data["profile"]:
			# An empty string overrides a profile defined in a lower layer.
			webModule.configProfile = data["profile"] or ""
		profilesData = self.getProfilesData()
		for key in webModule.getProfileKeys():
			if key not in profilesData and key not in self.lockedEmbeddedProfileKeys:
				webModule.deleteProfileData(key)
		for key, value in profilesData.items():
			if webModule.getProfileData(key) != value:
				webModule.setProfileData(key, deepcopy(value))

		if not save(webModule, prompt=self.Title):
			return
		context["webModule"] = webModule
		self.DestroyLater()
		self.SetReturnCode(wx.ID_OK)
		if self.editEmbeddedProfileKey is not None:
			wx.CallAfter(profiles.editEmbeddedProfile, webModule, self.editEmbeddedProfileKey)


def show(context, parent=None):
	return showContextualDialog(Dialog, context, parent or gui.mainFrame) == wx.ID_OK
