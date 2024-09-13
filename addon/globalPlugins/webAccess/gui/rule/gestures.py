# globalPlugins/webAccess/gui/rule/gestures.py
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
	"Shirley Noel <shirley.noel@pole-emploi.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Sendhil Randon <sendhil.randon-ext@francetravail.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


import sys
from typing import Any
import wx

import addonHandler
import inputCore
import gui
from gui import guiHelper

from ...ruleHandler import ruleTypes
from ...utils import guarded
from .. import ContextualSettingsPanel, Change
from . import gestureBinding
from .abc import RuleAwarePanelBase


if sys.version_info[1] < 9:
    from typing import Mapping
else:
    from collections.abc import Mapping


addonHandler.initTranslation()


class GesturesPanelBase(RuleAwarePanelBase, metaclass=guiHelper.SIPABCMeta):
	"""ABC for Gestures panels
	
	Sub-classes must implement the methods `getData` (inherited from `ContextualSettingsPanel`)
	and `getRuleType` (inherited from `RuleTypeAware`).
	
	Known sub-classes:
	 - `criteriaEditor.GesturesPanel`
	 - `ruleEditor.GesturesPanel`
	"""

	# Translators: The label for a category in the Rule and Criteria editors
	title = _("Input Gestures")
	
	# Translators: Displayed when the selected rule type doesn't support input gestures
	descriptionIfNoneSupported = _("The selected Rule Type does not support Input Gestures.")
	
	def __init__(self, *args, **kwargs):
		self.hideable: Mapping[str, Sequence[wx.Window]] = {}
		super().__init__(*args, **kwargs)
	
	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		row = 0
		col = 0
		items = self.hideable["IfNotSupported"] = []
		item = wx.StaticText(self, label=self.descriptionIfNoneSupported)
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
		
		row += 1
		items = self.hideable["IfSupported"] = []
		# Translators: The label for a list on the Rule Editor dialog
		item = wx.StaticText(self, label=_("&Gestures"))
		items.append(item)
		gbSizer.Add(item, pos=(row, col), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		items.append(item)
		
		row += 1
		item = self.gesturesListBox = wx.ListBox(self, size=scale(-1, 100))
		items.append(item)
		gbSizer.Add(item, pos=(row, col), span=(6, 1), flag=wx.EXPAND)
		gbSizer.AddGrowableCol(col)
		gbSizer.AddGrowableRow(row + 5)
		
		col += 1
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, col))
		items.append(item)
		
		col += 1
		# Translators: The label for a button in the Rule Editor dialog
		item = self.addButton = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onAddGesture)
		items.append(item)
		gbSizer.Add(item, pos=(row, col), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL), pos=(row, col))
		items.append(item)
		
		row += 1
		# Translators: The label for a button in the Rule Editor dialog
		item = self.editButton = wx.Button(self, label=_("&Edit..."))
		item.Bind(wx.EVT_BUTTON, self.onEditGesture)
		items.append(item)
		gbSizer.Add(item, pos=(row, col), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL), pos=(row, col))
		items.append(item)
		
		row += 1
		# Translators: The label for a button in the Rule Editor dialog
		item = self.deleteButton = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
		items.append(item)
		gbSizer.Add(item, pos=(row, col), flag=wx.EXPAND)
	
	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		data = self.getData()
		self.gesturesMap = data.setdefault("gestures", {})
		self.updateGesturesListBox()
	
	def updateData(self):
		# Nothing to update: This panel writes directly into the data map.
		pass
	
	def getSelectedGesture(self):
		index = self.gesturesListBox.Selection
		return self.gesturesListBox.GetClientData(index) if index > -1 else None
	
	@guarded
	def onAddGesture(self, evt):
		context = self.context.copy()
		context["data"]["gestures"] = self.gesturesMap
		if gestureBinding.show(context, self):
			id = context["data"]["gestureBinding"]["gestureIdentifier"]
			self.onGestureChange(Change.CREATION, id)
	
	@guarded
	def onDeleteGesture(self, evt):
		index = self.gesturesListBox.Selection
		id = self.gesturesListBox.GetClientData(index)
		del self.gesturesMap[id]
		self.onGestureChange(Change.DELETION, index)

	@guarded
	def onEditGesture(self, evt):
		context = self.context.copy()
		gestures = context["data"]["gestures"] = self.gesturesMap
		id = self.getSelectedGesture()
		context["data"]["gestureBinding"] = {"gestureIdentifier": id, "action":  gestures[id]}
		if gestureBinding.show(context=context, parent=self):
			id = context["data"]["gestureBinding"]["gestureIdentifier"]
			self.onGestureChange(Change.UPDATE, id)
	
	def onGestureChange(self, change: Change, id: str):
		if change is Change.DELETION:
			index = None
		self.updateGesturesListBox(selectId=id, focus=True)
	
	def updateGesturesListBox(self, selectId: str = None, focus: bool = False):
		mgr = self.getRuleManager()
		map = self.gesturesMap
		if selectId is None:
			selectId = self.getSelectedGesture()
		listBox = self.gesturesListBox
		listBox.Clear()
		selectIndex = 0
		for index, (gestureIdentifier, action) in enumerate(map.items()):
			source, main = inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)
			actionDName = mgr.getActions().get(action, f"*{action}")
			listBox.Append(
				# Translators: A gesture binding on the editor dialogs
				"{gesture}: {action}".format(gesture=main, action=actionDName),
				gestureIdentifier
			)
			if gestureIdentifier == selectId:
				selectIndex = index
		if self.gesturesMap:
			listBox.SetSelection(selectIndex)
		enableBtn = listBox.Selection > -1
		for btn in (self.deleteButton, self.editButton):
			btn.Enable(enableBtn)
		if focus:
			self.gesturesListBox.SetFocus()
	
	@guarded
	def onPanelActivated(self):
		super().onPanelActivated()
		supported = self.getRuleType() in ruleTypes.ACTION_TYPES
		self.panelDescription = "" if supported else self.descriptionIfNoneSupported
		self.Freeze()
		for item in self.hideable["IfSupported"]:
			item.Show(supported)
		for item in self.hideable["IfNotSupported"]:
			item.Show(not supported)
		self.Thaw()
		self._sendLayoutUpdatedEvent()
	
	def onSave(self):
		super().onSave()
		data = self.getData()
		if self.getRuleType() not in ruleTypes.ACTION_TYPES:
			data.pop("gestures", None)
		elif not data.get("gestures"):
			data.pop("gestures", None)

