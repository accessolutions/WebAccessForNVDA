# globalPlugins/webAccess/gui/settings.py
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


__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import wx

import addonHandler
import config
import gui


from gui import guiHelper
from gui.settingsDialogs import SettingsDialog, SettingsPanel

from ..config import (
	EditorMode,
	InspectorMode,
	RuleWizardMode,
	UiMode,
	UiModePref,
	getUiModePref,
	handleConfigChange,
	setUiModePref,
)


addonHandler.initTranslation()


def initialize():
	gui.NVDASettingsDialog.categoryClasses.append(WebAccessSettingsPanel)

def terminate():
	gui.NVDASettingsDialog.categoryClasses.remove(WebAccessSettingsPanel)


class WebAccessSettingsDialog(SettingsDialog):

	panel = None
	# Translators: The title of a dialog
	title = _("WebAccess Preferences")

	def makeSettings(self, settingsSizer):
		panel = self.panel = WebAccessSettingsPanel(self)
		settingsSizer.Add(
			panel,
			flag=wx.EXPAND | wx.ALL,
			proportion=1,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL
		)

	def postInit(self):
		self.Layout()
		self.panel.SetFocus()

	def _doSave(self):
		if self.panel.isValid() is False:
			raise ValueError("Validation for %s blocked saving settings" % self.panel.__class__.__name__)
		self.panel.onSave()
		self.panel.postSave()

	def onOk(self,evt):
		try:
			self._doSave()
		except ValueError:
			log.debugWarning("", exc_info=True)
			return
		self.panel.Destroy()
		super().onOk(evt)

	def onCancel(self,evt):
		self.panel.onDiscard()
		self.panel.Destroy()
		super().onCancel(evt)


class WebAccessSettingsPanel(SettingsPanel):
	# Translators: The label for a category in the settings dialog
	title = _("WebAccess")

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		item = self.devMode = sHelper.addItem(
			# Translators: The label for a settings in the WebAccess settings panel
			wx.CheckBox(self, label=_("&Developer mode"))
		)
		item.SetValue(config.conf["webAccess"]["devMode"])
		item = self.disableUserConfig = sHelper.addItem(
			# Translators: The label for a settings in the WebAccess settings panel
			wx.CheckBox(self, label=_("Disable all &user WebModules (activate only scratchpad and addons)"))
		)
		item.SetValue(config.conf["webAccess"]["disableUserConfig"])
		item = self.writeInAddons = sHelper.addItem(
			# Translators: The label for a settings in the WebAccess settings panel
			wx.CheckBox(self, label=_("Write into add-ons' \"webModules\" folder (not recommended)"))
		)
		item.SetValue(config.conf["webAccess"]["writeInAddons"])

		group = guiHelper.BoxSizerHelper(
			self,
			sizer=wx.StaticBoxSizer(
				wx.StaticBox(
					self,
					# Translators: The title of a group of settings in the WebAccess settings panel
					label=_("Default UI modes")
				),
				wx.VERTICAL
			)
		)
		sHelper.addItem(group.sizer, flag=wx.EXPAND)
		self._modeChoices = []
		for name, label, defaultLabel, extraChoices in (
			(
				UiMode.RULE_WIZARD,
				# Translators: The label for a setting in the WebAccess settings panel
				_("Rule &wizard"),
				# Translators: A choice in the WebAccess settings panel
				_("Default (wizard if simple)"),
				(
					# Translators: A choice in the WebAccess settings panel
					(RuleWizardMode.WIZARD, _("Wizard if simple")),
					# Translators: A choice in the WebAccess settings panel
					(RuleWizardMode.EDITOR, _("Editor")),
				),
			),
			(
				UiMode.RULE_EDITOR,
				# Translators: The label for a setting in the WebAccess settings panel
				_("Rule &editor"),
				# Translators: A choice in the WebAccess settings panel
				_("Default (simple if one criteria set)"),
				(
					# Translators: A choice in the WebAccess settings panel
					(EditorMode.SIMPLE, _("Simple if one criteria set")),
					# Translators: A choice in the WebAccess settings panel
					(EditorMode.FULL, _("Full")),
				),
			),
			(
				UiMode.CRITERIA_EDITOR,
				# Translators: The label for a setting in the WebAccess settings panel
				_("&Criteria editor"),
				# Translators: A choice in the WebAccess settings panel
				_("Default (simple if no gestures/properties)"),
				(
					# Translators: A choice in the WebAccess settings panel
					(EditorMode.SIMPLE, _("Simple if no gestures/properties")),
					# Translators: A choice in the WebAccess settings panel
					(EditorMode.FULL, _("Full")),
				),
			),
			(
				UiMode.INSPECTOR,
				# Translators: The label for a setting in the WebAccess settings panel
				_("Element &inspector"),
				# Translators: A choice in the WebAccess settings panel
				_("Default (single element)"),
				(
					# Translators: A choice in the WebAccess settings panel
					(InspectorMode.SINGLE, _("Single element")),
					# Translators: A choice in the WebAccess settings panel
					(InspectorMode.ANCESTORS, _("All ancestors")),
				),
			),
		):
			choices = (
				(UiModePref.DEFAULT, defaultLabel),
				# Translators: A choice in the WebAccess settings panel
				(UiModePref.LAST_USED, _("Last used")),
			) + extraChoices
			ctrl, keys = self._addModeChoice(group, label, getUiModePref(name), choices)
			self._modeChoices.append((name, ctrl, keys))

	def _addModeChoice(self, sHelper, label, current, choices):
		keys = tuple(key for key, _lbl in choices)
		item = sHelper.addLabeledControl(
			label,
			wx.Choice,
			choices=[lbl for _key, lbl in choices]
		)
		try:
			item.SetSelection(keys.index(current))
		except ValueError:
			try:
				item.SetSelection(tuple(str(k) for k in keys).index(str(current)))
			except ValueError:
				item.SetSelection(0)
		return item, keys

	def _getModeChoiceValue(self, ctrl, keys):
		index = ctrl.GetSelection()
		if index < 0 or index >= len(keys):
			return keys[0]
		return keys[index]

	def onSave(self):
		config.conf["webAccess"]["devMode"] = self.devMode.GetValue()
		config.conf["webAccess"]["disableUserConfig"] = self.disableUserConfig.GetValue()
		config.conf["webAccess"]["writeInAddons"] = self.writeInAddons.GetValue()
		for name, ctrl, keys in self._modeChoices:
			setUiModePref(name, self._getModeChoiceValue(ctrl, keys))
		handleConfigChange()
