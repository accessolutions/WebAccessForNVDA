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



__version__ = "2021.04.06"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from collections import OrderedDict
import re
import wx

from logHandler import log

from gui import guiHelper, nvdaControls
from gui.settingsDialogs import (
	MultiCategorySettingsDialog,
	SettingsDialog,
	SettingsPanel,
)
from six import iteritems, text_type
from gui.dpiScalingHelper import DpiScalingHelperMixin


LABEL_ACCEL = re.compile("&(?!&)")
"""
Compiled pattern used to strip accelerator key indicators from labels.
"""

def stripAccel(label):
	"""Strip the eventual accelerator key indication from a field label

	This allows for registering a single literal (hence a single translation)
	for use both as form field label and to compose summary reports.
	"""
	return LABEL_ACCEL.sub("", label)


def stripAccelAndColon(label):
	"""Strip the eventual accelerator key indication from a field label

	This allows for registering a single literal (hence a single translation)
	for use both as form field label and to compose validation messages.
	"""
	return stripAccel(label).rstrip(":").rstrip()


class ValidationError(Exception):
	pass


class InvalidValue(object):
	"""Represents an invalid value
	"""

	def __init__(self, raw):
		# The raw value that could not be validated
		self.raw = raw

	def __str__(self):
		# Translator: The placeholder for an invalid value in summary reports
		return _("<Invalid>")


class FillableSettingsPanel(SettingsPanel):
	"""This `SettingsPanel` allows its controls to fill the whole available space.

	See `FillableMultiCategorySettingsDialog`
	"""

	def _buildGui(self):
		# Change to the original implementation: Add `proportion=1`
		self.mainSizer=wx.BoxSizer(wx.VERTICAL)
		self.settingsSizer=wx.BoxSizer(wx.VERTICAL)
		self.makeSettings(self.settingsSizer)
		self.mainSizer.Add(self.settingsSizer, flag=wx.ALL | wx.EXPAND, proportion=1)
		self.mainSizer.Fit(self)
		self.SetSizer(self.mainSizer)


class ContextualSettingsPanel(FillableSettingsPanel):

	def __init__(self, *args, **kwargs):
		self.context = None
		super(ContextualSettingsPanel, self).__init__(*args, **kwargs)

	def initData(self, context):
		raise NotImplementedError()

	# Set to True if the view depends on data that can be edited on other panels of the same dialog
	initData.onPanelActivated = False

	def onPanelActivated(self):
		if getattr(self.initData, "onPanelActivated", False):
			self.initData(self.context)
		super(ContextualSettingsPanel, self).onPanelActivated()


class PanelAccessible(wx.Accessible):

	"""
	WX Accessible implementation to set the role of a settings panel to property page,
	as well as to set the accessible description based on the panel's description.
	"""

	def GetRole(self, childId):
		return (wx.ACC_OK, wx.ROLE_SYSTEM_PROPERTYPAGE)

	def GetDescription(self, childId):
		return (wx.ACC_OK, self.Window.panelDescription)


class FillableMultiCategorySettingsDialog(MultiCategorySettingsDialog):
	"""This `MultiCategorySettingsDialog` allows its panels to fill the whole available space.

	See `FillableSettingsPanel`
	"""

	def _getCategoryPanel(self, catId):
		# Changes to the original implementation:
		#  - Add `proportion=1`
		#  - Remove `gui._isDebug()` test (introduced with NVDA 2018.2)
		panel = self.catIdToInstanceMap.get(catId, None)
		if not panel:
			try:
				cls = self.categoryClasses[catId]
			except IndexError:
				raise ValueError("Unable to create panel for unknown category ID: {}".format(catId))
			panel = cls(parent=self.container)
			panel.Hide()
			self.containerSizer.Add(
				panel, flag=wx.ALL | wx.EXPAND, proportion=1,
				border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL
			)
			self.catIdToInstanceMap[catId] = panel
			panelWidth = panel.Size[0]
			availableWidth = self.containerSizer.GetSize()[0]
			if panelWidth > availableWidth: # and gui._isDebug():
				log.debugWarning(
					("Panel width ({1}) too large for: {0} Try to reduce the width of this panel, or increase width of " +
					 "MultiCategorySettingsDialog.MIN_SIZE"
					).format(cls, panel.Size[0])
				)
			panel.SetLabel(panel.title)
			panel.SetAccessible(PanelAccessible(panel))

		return panel

	def _enterActivatesOk_ctrlSActivatesApply(self, evt):
		if evt.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			obj = evt.EventObject
			if isinstance(obj, wx.TextCtrl) and obj.IsMultiLine():
				evt.Skip()
				return
		super(FillableMultiCategorySettingsDialog, self)._enterActivatesOk_ctrlSActivatesApply(evt)


def configuredSettingsDialogType(**config):

	class Type(SettingsDialog):
		def __init__(self, *args, **kwargs):
			kwargs.update(config)
			return super(Type, self).__init__(*args, **kwargs)

	return Type


class ContextualMultiCategorySettingsDialog(
	FillableMultiCategorySettingsDialog,
	configuredSettingsDialogType(hasApplyButton=False, multiInstanceAllowed=True)
):

	def __init__(self, *args, **kwargs):
		self.context = None
		super(ContextualMultiCategorySettingsDialog, self).__init__(*args, **kwargs)

	def initData(self, context):
		self.context = context
		panel = self.currentCategory
		if isinstance(panel, ContextualSettingsPanel):
			if not getattr(panel.initData, "onPanelActivated", False):
				panel.initData(context)

	def _getCategoryPanel(self, catId):
		panel = super(ContextualMultiCategorySettingsDialog, self)._getCategoryPanel(catId)
		if (
			hasattr(self, "context")
			and isinstance(panel, ContextualSettingsPanel)
			and (
				getattr(panel, "context", None) is not self.context
				or getattr(panel.initData, "onPanelActivated", False)
			)
		):
			panel.initData(self.context)
		return panel


def showContextualDialog(cls, context, parent, *args, **kwargs):
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


class HideableChoice():

	__slots__ = ("key", "label", "enabled")

	def __init__(self, key, label, enabled=True):
		self.key = key
		self.label = label
		self.enabled = enabled


class DropDownWithHideableChoices(wx.ComboBox):

	def __init__(self, *args, **kwargs):
		style = kwargs.get("style", 0)
		style |= wx.CB_READONLY
		kwargs["style"] = style
		super(DropDownWithHideableChoices, self).__init__(*args, **kwargs)
		self.__choicesWholeMap = OrderedDict()
		self.__choicesFilteredList = []

	def Clear(self):
		self.__choicesWholeMap.clear()
		self.__choicesFilteredList[:] = []
		return super(DropDownWithHideableChoices, self).Clear()

	def setChoices(self, keyLabelPairs):
		self.__choicesWholeMap.clear()
		self.__choicesWholeMap.update({key: HideableChoice(key, label) for key, label in keyLabelPairs})
		self.__refresh()

	def getChoicesKeys(self):
		return list(self.__choicesWholeMap.keys())

	def getSelectedChoiceKey(self):
		choice = self.__getSelectedChoice()
		return choice and choice.key

	def setSelectedChoiceKey(self, key, default=None):
		choice = self.__getChoice(key)
		if choice.enabled:
			self.__setSelectedChoice(choice)
		elif default is not None:
			self.setSelectedChoiceKey(key=default, default=None)

	def setChoiceEnabled(self, key, enabled, default=None):
		choice = self.__getChoice(key)
		choice.enabled = enabled
		self.__refresh(default)

	def setChoicesEnabled(self, keys, enabled, default=None):
		for key in keys:
			self.setChoiceEnabled(key, enabled, default=default)

	def setAllChoicesEnabled(self, enabled, default=None):
		for key in self.getChoicesKeys():
			self.setChoiceEnabled(key, enabled, default=default)

	def __getChoice(self, key):
		return self.__choicesWholeMap[key]

	def __getSelectedChoice(self):
		index = self.Selection
		if index < 0:
			return None
		return self.__choicesFilteredList[index]

	def __setSelectedChoice(self, choice):
		if choice:
			self.Selection = self.__choicesFilteredList.index(choice)
		else:
			self.Selection = -1

	def __refresh(self, default=None):
		choice = self.__getSelectedChoice()
		whole = self.__choicesWholeMap
		filtered = self.__choicesFilteredList
		filtered[:] = [c for c in list(whole.values()) if c.enabled]
		self.Set([c.label for c in filtered])
		if choice is not None:
			if choice.enabled:
				self.__setSelectedChoice(choice)
			else:
				self.setSelectedChoiceKey(default)
