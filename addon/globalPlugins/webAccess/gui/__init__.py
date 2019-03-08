# globalPlugins/webAccess/gui/__init__.py
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

from __future__ import absolute_import, division, print_function

__version__ = "2021.03.12"
__author__ = u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"


try:
	from gui import guiHelper
except ImportError:
	# NVDA < 2016.4
	from ..backports.nvda_2016_4 import gui_guiHelper as guiHelper


try:
	from gui.settingsDialogs import (
		MultiCategorySettingsDialog,
		SettingsDialog,
		SettingsPanel,
	)
except ImportError:
	# NVDA < 2018.2  
	from ..backports.nvda_2018_2.gui_settingsDialogs import (
		MultiCategorySettingsDialog,
		SettingsDialog,
		SettingsPanel
	)


try:
	from gui.dpiScalingHelper import DpiScalingHelperMixin
except ImportError:
	# NVDA < 2019.1
	from ..backports.nvda_2019_1.gui_dpiScalingHelper import DpiScalingHelperMixin 

	class MultiCategorySettingsDialog(MultiCategorySettingsDialog, DpiScalingHelper):
		pass
	
	class SettingsPanel(SettingsPanel, DpiScalingHelper):
		pass


class SettingsDialogWithoutApplyButton(SettingsDialog):

	def __init__(self, *args, **kwargs):
		kwargs["hasApplyButton"] = False
		super(SettingsDialogWithoutApplyButton, self).__init__(*args, **kwargs)


def configuredSettingsDialogType(**config):
	
	class Type(SettingsDialog):
		def __init__(self, *args, **kwargs):
			kwargs.update(config)
			return super(Type, self).__init__(*args, **kwargs)
	
	return Type


class SettingsPanelWithContext(SettingsPanel):
	
	def initData(self, context):
		raise NotImplemented()
	
	initData.onPanelActivated = False
	
	def onPanelActivated(self):
		if getattr(self.initData, "onPanelActivated", False):
			self.initData(self.context)
		super(SettingsPanelWithContext, self).onPanelActivated()


class MultiCategorySettingsDialogWithContext(
		MultiCategorySettingsDialog,
		configuredSettingsDialogType(hasApplyButton=False, multiInstanceAllowed=True)
):
	
	def initData(self, context):
		self.context = context
		panel = self.currentCategory
		if isinstance(panel, SettingsPanelWithContext):
			if getattr(panel.initData, "onPanelActivated", False):
				panel.context = context
			else:
				panel.initData(context)
	
	def _getCategoryPanel(self, catId):
		panel = super(MultiCategorySettingsDialogWithContext, self)._getCategoryPanel(catId)
		if (
			hasattr(self, "context")
			and isinstance(panel, SettingsPanelWithContext)
			and getattr(panel, "context", None) is not self.context
		):
			if getattr(panel.initData, "onPanelActivated", False):
				panel.context = self.context
			else:
				panel.initData(self.context)
		return panel


def showDialogWithContext(cls, context, parent, *args, **kwargs):
	if parent is not None:
		with cls(parent, *args, **kwargs) as dlg:
			dlg.initData(context)
			return dlg.ShowModal()
	import gui
	gui.mainFrame.prePopup()
	try:
		dlg = cls(gui.mainFrame, *args, **kwargs)
		dlg.initData(context)
		dlg.Show()
	finally:
		gui.mainFrame.postPopup()
