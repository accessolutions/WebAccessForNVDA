# globalPlugins/webAccess/gui/settings.py
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


__version__ = "2021.02.04"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import wx

import addonHandler
import config
import gui


from gui import guiHelper, SettingsDialog, SettingsPanel


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
		super(WebAccessSettingsDialog, self).onOk(evt)

	def onCancel(self,evt):
		self.panel.onDiscard()
		self.panel.Destroy()
		super(WebAccessSettingsDialog, self).onCancel(evt)


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

	def onSave(self):
		config.conf["webAccess"]["devMode"] = self.devMode.GetValue()
		config.conf["webAccess"]["disableUserConfig"] = self.disableUserConfig.GetValue()
		config.conf["webAccess"]["writeInAddons"] = self.writeInAddons.GetValue()
		from ..config import handleConfigChange
		handleConfigChange()
