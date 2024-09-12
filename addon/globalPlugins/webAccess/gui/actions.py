# globalPlugins/webAccess/gui/actions.py
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


__version__ = "2024.08.24"
__authors__ = (
	"Shirley Noel <shirley.noel@pole-emploi.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
)


from collections.abc import Mapping
from typing import Any
import wx

import addonHandler
import inputCore
import gui
from gui import guiHelper

from ..ruleHandler import ruleTypes
from ..utils import guarded
from . import ContextualSettingsPanel, Change, gestureBinding
from .rule.abc import RuleAwarePanelBase


addonHandler.initTranslation()


class ActionsPanelBase(RuleAwarePanelBase, metaclass=guiHelper.SIPABCMeta):
	"""ABC for Actions panels
	
	Sub-classes must implement the methods `getData` (inherited from `ContextualSettingsPanel`)
	and `getRuleType` (inherited from `RuleTypeAware`).
	
	Known sub-classes:
	 - `criteriaEditor.ActionsPanel`
	 - `ruleEditor.ActionsPanel`
	"""

	# Translators: The label for a category in the Rule and Criteria editors
	title = _("Actions")
	
	# Translators: Displayed when the selected rule type doesn't support any action
	descriptionIfNoneSupported = _("No action available for the selected rule type.")
	
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
		gbSizer.Add(item, pos=(row, 0), span=(1, 5), flag=wx.EXPAND)
		
		row += 1
		items = self.hideable["IfSupported"] = []
		# Translators: The label for a list on the Rule Editor dialog
		item = wx.StaticText(self, label=_("&Gestures"))
		items.append(item)
		gbSizer.Add(item, pos=(row, col), span=(1, 3), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		items.append(item)
		
		row += 1
		item = self.gesturesListBox = wx.ListBox(self, size=scale(-1, 100))
		items.append(item)
		gbSizer.Add(item, pos=(row, col), span=(6, 3), flag=wx.EXPAND)
		
		col += 3
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
		
		row += 2
		col = 0
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
		items.append(item)
		
		row += 1
		# Translators: Automatic action at rule detection input label for the rule dialog's action panel.
		item = wx.StaticText(self, label=_("A&utomatic action at rule detection:"))
		items.append(item)
		gbSizer.Add(item, pos=(row, col))
		
		col += 1
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, col))
		items.append(item)
		
		col += 1
		item = self.autoActionChoice = wx.Choice(self, choices=[])
		item.Bind(wx.EVT_CHOICE, self.onAutoActionChoice)
		items.append(item)
		gbSizer.Add(item, pos=(row, col), span=(1, 3), flag=wx.EXPAND)
		
		gbSizer.AddGrowableCol(2)
	
	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		data = self.getData()
		self.gesturesMap = data.setdefault("gestures", {})
		self.updateGesturesListBox()
		self.updateAutoActionChoice(refreshChoices=True)
	
	def updateData(self):
		# Nothing to update: This panel writes directly into the data map.
		pass
	
	def getAutoAction(self):
		return self.getData().get("properties", {}).get("autoAction")
	
	def getAutoActionChoices(self) -> Mapping[str, str]:
		mgr = self.context["webModule"].ruleManager
		# Translators: An entry in the Automatic Action selection list.
		choices = {None: pgettext("webAccess.action", "No action")}
		choices.update(mgr.getActions())
		action = self.getAutoAction()
		if action not in choices:
			choices[action] = f"*{action}"
		return choices
		
	def getSelectedGesture(self):
		index = self.gesturesListBox.Selection
		return self.gesturesListBox.GetClientData(index) if index > -1 else None
	
	@guarded
	def onAutoActionChoice(self, evt):
		action = evt.EventObject.GetClientData(evt.Selection)
		self.getData().setdefault("properties", {})["autoAction"] = action
	
	@guarded
	def onAddGesture(self, evt):
		context = self.context
		context["data"]["gestures"] = self.gesturesMap
		if gestureBinding.show(context=context, parent=self) == wx.ID_OK:
			id = context["data"].pop("gestureBinding")["gestureIdentifier"]
			self.onGestureChange(Change.CREATION, id)
		del context["data"]["gestures"]

	@guarded
	def onDeleteGesture(self, evt):
		index = self.gesturesListBox.Selection
		id = self.gesturesListBox.GetClientData(index)
		del self.gesturesMap[id]
		self.onGestureChange(Change.DELETION, index)

	@guarded
	def onEditGesture(self, evt):
		context = self.context
		gestures = context["data"]["gestures"] = self.gesturesMap
		id = self.getSelectedGesture()
		context["data"]["gestureBinding"] = {"gestureIdentifier": id, "action":  gestures[id]}
		if gestureBinding.show(context=context, parent=self) == wx.ID_OK:
			id = context["data"]["gestureBinding"]["gestureIdentifier"]
			self.onGestureChange(Change.UPDATE, id)
		del context["data"]["gestureBinding"]
		del context["data"]["gestures"]
	
	def onGestureChange(self, change: Change, id: str):
		if change is Change.DELETION:
			index = None
		self.updateGesturesListBox(selectId=id, focus=True)
	
	def updateAutoActionChoice(self, refreshChoices: bool):
		ctrl = self.autoActionChoice
		value = self.getAutoAction()
		if refreshChoices:
			choices = self.getAutoActionChoices()
			ctrl.Clear()
			for action, displayName in choices.items():
				ctrl.Append(displayName, action)
			index = tuple(choices.keys()).index(self.getAutoAction())
		else:
			index = tuple(ctrl.GetClientData(i) for i in range(ctrl.Count)).index(value)
		ctrl.SetSelection(index)
	
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
		supported = self.getRuleType() in (ruleTypes.ZONE, ruleTypes.MARKER)
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
		if self.getRuleType() not in (ruleTypes.ZONE, ruleTypes.MARKER):
			data.pop("gestures", None)
			data.get("properties", {}).pop("autoAction", None)
		elif not data.get("gestures"):
			data.pop("gestures", None)

