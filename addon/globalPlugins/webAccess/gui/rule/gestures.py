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


from enum import Enum, auto
from typing import Any
import wx

import addonHandler
import inputCore
import gui
from gui import guiHelper

from ...ruleHandler import GestureScope, ruleTypes
from ...ruleHandler.gestureBindings import UNAVAILABLE_ACTION, getActionLabel, isUnavailableBinding
from ...utils import guarded, translate
from .. import ContextualSettingsPanel, Change
from . import gestureBinding
from .abc import RuleAwarePanelBase

from collections.abc import Mapping, Sequence


addonHandler.initTranslation()


class BindingKind(Enum):
	"""The kind of an entry in a Gestures panel."""

	OWN = auto()
	"""Defined at this level, not replacing any inherited binding."""
	OVERRIDE = auto()
	"""Defined at this level, replacing an inherited binding (Criteria level only)."""
	DISABLED = auto()
	"""Inherited binding disabled at this level, the gesture reaching the page (Criteria level only)."""
	UNAVAILABLE = auto()
	"""Inherited binding disabled at this level, announced as unavailable (Criteria level only)."""
	INHERITED = auto()
	"""Inherited binding, applying as is (Criteria level only)."""


def iterBindingEntries(
	own: Mapping[str, Sequence[str] | None],
	inherited: Mapping[str, Sequence[str]],
):
	"""Yield `(gestureId, kind, (scope, action))` for each binding, sorted by gesture.

	`own`: The bindings defined at the edited level, `None` or the "unavailable" action
	disabling an inherited one.
	`inherited`: The bindings inherited by the edited level (empty at Rule level).
	The identifiers of the inherited bindings are matched once normalized.
	"""
	normalize = inputCore.normalizeGestureIdentifier
	ownNormalized = {normalize(id): id for id in own}
	entries = {}
	for id, binding in inherited.items():
		ownId = ownNormalized.get(normalize(id))
		if ownId is None:
			entries[id] = (BindingKind.INHERITED, binding)
		elif own[ownId] is None:
			entries[ownId] = (BindingKind.DISABLED, binding)
		elif isUnavailableBinding(own[ownId]):
			entries[ownId] = (BindingKind.UNAVAILABLE, own[ownId])
		else:
			entries[ownId] = (BindingKind.OVERRIDE, own[ownId])
	for id, binding in own.items():
		if id in entries:
			continue
		if binding is None:
			# Disabling a binding the rule no longer defines: Listed so that it can be removed
			entries[id] = (BindingKind.DISABLED, (GestureScope.NORMAL.value, None))
		elif isUnavailableBinding(binding):
			entries[id] = (BindingKind.UNAVAILABLE, binding)
		else:
			entries[id] = (BindingKind.OWN, binding)
	for id in sorted(entries):
		kind, binding = entries[id]
		yield id, kind, binding


def getBindingLabel(
	actions: Mapping[str, str],
	gestureIdentifier: str,
	kind: BindingKind,
	binding: Sequence[str],
) -> str:
	scope, action = binding
	source, main = inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)
	if kind is BindingKind.DISABLED:
		# Translators: A disabled gesture binding on the Criteria editor
		return _("{gesture}: Disabled for this criteria set, reaches the page").format(gesture=main)
	if kind is BindingKind.UNAVAILABLE:
		# Translators: A disabled gesture binding on the Criteria editor
		return _("{gesture}: Disabled for this criteria set, announced as unavailable").format(
			gesture=main
		)
	actionDName = getActionLabel(actions, action)
	# Translators: A gesture binding on the editor dialogs
	label = _("{gesture}: {action}").format(gesture=main, action=actionDName)
	if scope != GestureScope.NORMAL.value:
		label += f" - {SCOPE_LABELS[scope]}"
	if kind is BindingKind.INHERITED:
		# Translators: Mention for an inherited gesture binding on the Criteria editor
		label += " " + _("(inherited from the rule)")
	elif kind is BindingKind.OVERRIDE:
		# Translators: Mention for a gesture binding replacing that of the rule on the Criteria editor
		label += " " + _("(replaces the rule shortcut)")
	return label


SCOPE_LABELS = {
	# Translators: The label for a gesture binding scope
	GestureScope.GLOBAL.value: _("Global scope"),
	# Translators: The label for a gesture binding scope
	GestureScope.LOCAL.value: _("Local scope"),
}


def getGesturesSummary(
	context: Mapping[str, Any],
	own: Mapping[str, Sequence[str] | None],
	inherited: Mapping[str, Sequence[str]] = None,
) -> list[str]:
	"""The labels of the bindings defined at the summarized level, omitting inherited ones."""
	actions = context["webModule"].ruleManager.getActions()
	return [
		getBindingLabel(actions, gestureIdentifier, kind, binding)
		for gestureIdentifier, kind, binding in iterBindingEntries(own, inherited or {})
		if kind is not BindingKind.INHERITED
	]


class GesturesPanelBase(RuleAwarePanelBase, metaclass=guiHelper.SIPABCMeta):
	"""ABC for Gestures panels
	
	Sub-classes must implement the method `getData` (inherited from `ContextualSettingsPanel`).
	
	Known sub-classes:
	 - `criteriaEditor.GesturesPanel`
	 - `ruleEditor.GesturesPanel`
	"""

	# Use translation from NVDA core
	title = translate("Input Gestures")
	
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
		item.Bind(wx.EVT_LISTBOX, self.onGesturesListBox)
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
		return self.gesturesListBox.GetClientData(index)[0] if index > -1 else None

	def getInheritedGestures(self) -> Mapping[str, Sequence[str]]:
		"""The bindings inherited by the edited level, as `{gestureId: (scope, action)}`.

		None at Rule level. Overridden for alternatives (Criteria).
		"""
		return {}

	def iterEntries(self):
		"""Yield `(gestureId, kind, (scope, action))` for each entry of the list, sorted."""
		return iterBindingEntries(self.gesturesMap, self.getInheritedGestures())
	
	@guarded
	def onAddGesture(self, evt):
		context = self.context
		data = context["data"]
		data["gestureBinding"] = {}
		data["gestures"] = self.gesturesMap
		if gestureBinding.show(context, self):
			id = data["gestureBinding"]["gestureIdentifier"]
			self.onGestureChange(Change.CREATION, id)
		del data["gestureBinding"]
		del data["gestures"]
	
	def promptDisableMode(self) -> bool | None:
		"""Ask how to disable an inherited binding.

		Returns `True` to announce the gesture as unavailable, `False` to let it reach
		the page, `None` if cancelled.
		"""
		menu = wx.Menu()
		# Translators: A choice when disabling a rule gesture on the Criteria editor
		passItem = menu.Append(wx.ID_ANY, _("Let the key reach the page"))
		# Translators: A choice when disabling a rule gesture on the Criteria editor
		announceItem = menu.Append(wx.ID_ANY, _("Announce the shortcut is not available here"))
		try:
			menuId = self.GetPopupMenuSelectionFromUser(menu)
		finally:
			menu.Destroy()
		if menuId == passItem.Id:
			return False
		elif menuId == announceItem.Id:
			return True
		return None

	@guarded
	def onDeleteGesture(self, evt):
		index = self.gesturesListBox.Selection
		id, kind = self.gesturesListBox.GetClientData(index)
		if kind is BindingKind.INHERITED:
			# Disable the inherited binding at this level
			announce = self.promptDisableMode()
			if announce is None:
				return
			if announce:
				scope = self.getInheritedGestures()[id][0]
				self.gesturesMap[id] = (scope, UNAVAILABLE_ACTION)
			else:
				self.gesturesMap[id] = None
		else:
			# Remove the binding defined at this level, or re-enable the inherited one
			del self.gesturesMap[id]
		self.onGestureChange(Change.DELETION, id)

	@guarded
	def onEditGesture(self, evt):
		context = self.context
		id, kind = self.gesturesListBox.GetClientData(self.gesturesListBox.Selection)
		data = context["data"]
		gestures = data["gestures"] = self.gesturesMap
		if kind in (BindingKind.INHERITED, BindingKind.DISABLED, BindingKind.UNAVAILABLE):
			# Editing creates a binding at this level, replacing the inherited one
			inherited = self.getInheritedGestures().get(id)
			if inherited:
				scope, action = inherited
			else:
				# Disabling a binding the rule no longer defines
				scope, action = (gestures.get(id) or (GestureScope.NORMAL.value,))[0], None
		else:
			scope, action = gestures[id]
		data["gestureBinding"] = {
			"gestureIdentifier": id, "action": action, "scope": scope
		}
		if gestureBinding.show(context=context, parent=self):
			id = data["gestureBinding"]["gestureIdentifier"]
			self.onGestureChange(Change.UPDATE, id)
		del data["gestureBinding"]
		del data["gestures"]
	
	def onGestureChange(self, change: Change, id: str):
		if change is Change.DELETION:
			index = None
		self.updateGesturesListBox(selectId=id, focus=True)
	
	def updateGesturesListBox(self, selectId: str = None, focus: bool = False):
		mgr = self.getRuleManager()
		if selectId is None:
			selectId = self.getSelectedGesture()
		listBox = self.gesturesListBox
		listBox.Clear()
		selectIndex = 0
		actions = mgr.getActions()
		for index, (gestureIdentifier, kind, binding) in enumerate(self.iterEntries()):
			label = getBindingLabel(actions, gestureIdentifier, kind, binding)
			listBox.Append(label, (gestureIdentifier, kind))
			if gestureIdentifier == selectId:
				selectIndex = index
		if listBox.Count:
			listBox.SetSelection(selectIndex)
		self.updateButtons()
		if focus:
			self.gesturesListBox.SetFocus()

	def updateButtons(self):
		listBox = self.gesturesListBox
		index = listBox.Selection
		enableBtn = index > -1
		for btn in (self.deleteButton, self.editButton):
			btn.Enable(enableBtn)
		kind = listBox.GetClientData(index)[1] if enableBtn else None
		if kind is BindingKind.INHERITED:
			# Translators: The label for a button on the Criteria editor dialog
			label = _("&Disable")
		elif kind in (BindingKind.DISABLED, BindingKind.UNAVAILABLE):
			# Translators: The label for a button on the Criteria editor dialog
			label = _("&Restore")
		else:
			# Translators: The label for a button in the Rule Editor dialog
			label = _("&Delete")
		self.deleteButton.Label = label

	@guarded
	def onGesturesListBox(self, evt):
		self.updateButtons()
	
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
