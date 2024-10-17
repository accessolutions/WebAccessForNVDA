# globalPlugins/webAccess/gui/gestureBinding.py
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


__author__ = "Shirley Noel <shirley.noel@pole-emploi.fr>"


import sys
from typing import Any
import wx

import addonHandler
import inputCore
import gui
from gui import guiHelper
import speech
import ui

from ..utils import guarded, logException
from . import ScalingMixin, showContextualDialog


if sys.version_info[1] < 9:
    from typing import Mapping
else:
    from collections.abc import Mapping


addonHandler.initTranslation()


class GestureBindingDialog(wx.Dialog, ScalingMixin):
	
	MIN_SIZE = (500, 150) # Min height required to show the OK, Cancel, Apply buttons
	INITIAL_SIZE = MIN_SIZE
	
	def __init__(self, parent: wx.Window):
		super().__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
			# Translators: The title for a dialog
			title=_("Input Gesture"),
		)
		self.buildGui()
	
	def ShowModal(self):
		self.gestureInput.SetFocus()
		return super().ShowModal()
	
	def buildGui(self):
		scale = self.scale
		vSizer = wx.BoxSizer(wx.VERTICAL)
		gbSizer = wx.GridBagSizer()
		vSizer.Add(gbSizer, flag=wx.ALL | wx.EXPAND, border=guiHelper.BORDER_FOR_DIALOGS, proportion=1)
		
		row = 0
		item = wx.StaticText(self, label=_("Gesture: "))
		gbSizer.Add(item, pos=(row, 0), flag=wx.EXPAND)
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.gestureInput = wx.TextCtrl(self)
		self.gestureInput.Bind(wx.EVT_SET_FOCUS, self.onGestureInput_setFocus)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		row += 1
		item = wx.StaticText(self, label=_("&Action to execute"))
		gbSizer.Add(item, pos=(row, 0), flag=wx.EXPAND)
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.actionChoice = wx.Choice(self)
		item.Bind(wx.EVT_CHOICE, self.onActionChoice)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		gbSizer.AddGrowableCol(2)
		
		vSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.TOP | wx.DOWN | wx.RIGHT,
			border=scale(guiHelper.BORDER_FOR_DIALOGS)
		)
		
		# Bind late as the CreateSeparatedButtonSizer makes focus flicker
		self.gestureInput.Bind(wx.EVT_KILL_FOCUS, self.onGestureInput_killFocus)
		
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
		
		self.SetSizer(vSizer)
		self.SetMinSize(scale(*self.MIN_SIZE))
		self.SetSize(scale(*self.INITIAL_SIZE))
		self.Fit()
		self.CenterOnScreen()
	
	def getData(self) -> Mapping[str, str]:
		return self.context["data"].setdefault("gestureBinding", {})
	
	def initData(self, context: Mapping[str, Any]):
		self.context = context
		data = self.getData()
		data["oldId"] = data["newId"] = data.pop("gestureIdentifier", None)
		self.updateGestureInput()
		# Translators: A prompt for selection in the action list on the Input Gesture dialog
		actions = data["actions"] = {None: _("Select an action")}
		mgr = context["webModule"].ruleManager
		actions.update(mgr.getActions())
		self.actionChoice.AppendItems(tuple(actions.values()))
		self.actionChoice.Selection = tuple(actions.keys()).index(data.get("action", None))
	
	@guarded
	def onActionChoice(self, evt):
		data = self.getData()
		data["action"] = tuple(data["actions"].keys())[evt.Selection]
		evt.Skip()
	
	@guarded
	def onGestureInput_setFocus(self, evt):
		# Translators: The prompt to enter a gesture on the Input Gesture dialog
		evt.EventObject.Value = _("Type now the desired key combination")
		inputCore.manager._captureFunc = self._captureFunc
		evt.Skip()
	
	@guarded
	def onGestureInput_killFocus(self, evt):
		inputCore.manager._captureFunc = None
		self.updateGestureInput()
		evt.Skip()
	
	@guarded
	def onOk(self, evt):
		data = self.getData()
		if not data.get("newId"):
			gui.messageBox(
				# Translators: A message on the Input Gesture dialog
				_("You must define a shortcut"),
				self.Title,
				wx.OK | wx.ICON_ERROR,
				self
			)
			self.gestureInput.SetFocus()
			return
		if not data.get("action"):
			gui.messageBox(
				# Translators: A message on the Input Gesture dialog
				_("You must choose an action"),
				self.Title,
				wx.OK | wx.ICON_ERROR,
				self
			)
			self.actionChoice.SetFocus()
			return
		gestures = self.context["data"]["gestures"]
		oldId = data.pop("oldId")
		newId = data["gestureIdentifier"] = data.pop("newId")
		action = data["action"]
		tmp = gestures.copy()
		if oldId:
			del tmp[oldId]
		tmp[newId] = action
		gestures.clear()
		gestures.update({k : tmp[k] for k in sorted(tmp)})
		data["index"] = tuple(gestures.keys()).index(newId)
		self.EndModal(wx.ID_OK)
	
	@guarded
	def onCancel(self, evt):
		self.EndModal(wx.ID_CANCEL)
	
	def updateGestureInput(self):
		data = self.getData()
		ctrl = self.gestureInput
		id = data.get("newId")
		if id:
			source, main = inputCore.getDisplayTextForGestureIdentifier(id)
			ctrl.Value = main
		else:
			# Translators: Displayed when no gesture as been entered on the Input Gesture dialog
			ctrl.Value = _("None")
	
	@logException
	def _captureFunc(self, gesture):
		data = self.getData()
		if gesture.isModifier:
			return False
		it = iter(gesture.normalizedIdentifiers)
		id = next(it)
		# Search the shortest gesture identifier (without source)
		for candidate in it:
			if len(candidate) < len(id):
				id = candidate
		inputCore._captureFunc = None
		if id in ("kb:enter", "kb:escape", "kb:tab", "kb:shift+tab"):
			self.updateGestureInput()
			return True
		data["newId"] = id
		self.updateGestureInput()
		ui.message(self.gestureInput.Value)
		wx.CallAfter(self.actionChoice.SetFocus)
		return False


def show(context: Mapping[str, Any], parent: wx.Window):
	return showContextualDialog(GestureBindingDialog, context, parent)
