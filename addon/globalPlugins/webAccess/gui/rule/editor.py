# globalPlugins/webAccess/gui/rule/editor.py
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
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"Shirley Noël <shirley.noel@pole-emploi.fr>",
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Sendhil Randon <sendhil.randon-ext@francetravail.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)

from abc import abstractmethod
from collections import OrderedDict
import config
from dataclasses import dataclass
from enum import Enum
from functools import partial
import sys
from typing import Any
import wx
from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import addonHandler
import controlTypes
import gui
from gui import guiHelper
import inputCore
from logHandler import log
import ui

from ... import webModuleHandler
from ...ruleHandler import RuleManager, ruleTypes
from ...ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
from ...utils import guarded, logException, notifyError, updateOrDrop
from .. import (
	Change,
	ContextualSettingsPanel,
	SingleFieldEditorPanelBase,
	TreeContextualPanel,
	TreeMultiCategorySettingsDialog,
	TreeNodeInfo,
	ValidationError,
	showContextualDialog,
	stripAccel,
	stripAccelAndColon,
	stripAccelAndColon,
)
from . import createMissingSubModule, criteriaEditor, gestureBinding
from .abc import RuleAwarePanelBase
from .gestures import GesturesPanelBase
from .properties import (
	EditorType,
	Property,
	Properties,
	PropertiesPanelBase,
	SinglePropertyEditorPanelBase,
)


if sys.version_info[1] < 9:
    from typing import Mapping, Sequence
else:
    from collections.abc import Mapping, Sequence


addonHandler.initTranslation()

formModeRoles = [
	controlTypes.ROLE_EDITABLETEXT,
	controlTypes.ROLE_COMBOBOX,
]

SHARED_LABELS: Mapping[str, str] = {
	# Translators: The Label for a field on the Rule editor
	"type": _("Rule &type:"),
	# Translators: The Label for a field on the Rule editor
	"name": _("Rule &name:"),
}


def getSummary(context, data):
	ruleType = data.get("type")
	if ruleType is None:
		# Translators: A mention on the Rule summary report
		return _("No rule type selected.")
	parts = []
	parts.append("{} {}".format(
		stripAccel(SHARED_LABELS["type"]),
		ruleTypes.ruleTypeLabels.get(ruleType, "")
	))

	# Properties
	subParts = []
	props = Properties(context, data.get("properties", {}), iterOnlyFirstMap=True)
	for prop in props:
		subParts.append(
			# Translators: A mention on the Rule Summary report
			"  " + _("{field}: {value}").format(field=prop.displayName, value=prop.displayValue)
		)
	if subParts:
		# Translators: The label for a section on the Rule Summary report
		parts.append(_("{section}:").format(section=PropertiesPanel.title))
		parts.extend(subParts)

	# Criteria
	criteriaSets = data.get("criteria", [])
	if criteriaSets:
		subParts = []
		if len(criteriaSets) == 1:
			# Translators: The label for a section on the Rule Summary report
			parts.append(_("Criteria:"))
			parts.append(criteriaEditor.getSummary(context, criteriaSets[0], indent="  "))
		else:
			# Translators: The label for a section on the Rule Summary report
			parts.append(_("Multiple criteria sets:"))
			for index, alternative in enumerate(criteriaSets):
				name = alternative.get("name")
				if name:
					# Translators: The label for a section on the Rule Summary report
					altHeader = _('Alternative #{index} "{name}":').format(index=index, name=name)
				else:
					# Translators: The label for a section on the Rule Summary report
					altHeader = _("Alternative #{index}:").format(index=index)
				subParts.append("  " + altHeader)
				subParts.append(criteriaEditor.getSummary(context, alternative, indent="    "))
		parts.extend(subParts)
	return "\n".join(parts)


class RuleEditorTreeContextualPanel(RuleAwarePanelBase, TreeContextualPanel):
	
	def getData(self):
		return self.getRuleData()
	
	def onRuleType_change(self):
		prm = self.categoryParams
		categoryClasses = tuple(nodeInfo.categoryClass for nodeInfo in self.Parent.Parent.categoryClasses)
		for index in (categoryClasses.index(cls) for cls in (GeneralPanel, GesturesPanel, PropertiesPanel)):
			category = prm.tree.getXChild(prm.tree.GetRootItem(), index)
			self.refreshParent(category)


class RuleEditorSingleFieldChildPanel(SingleFieldEditorPanelBase, RuleEditorTreeContextualPanel):
	pass


class GeneralPanel(RuleEditorTreeContextualPanel):
	# Translators: The label for the General settings panel.
	title = _("General")

	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		#gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		row = 0
		item = wx.StaticText(self, label=SHARED_LABELS["type"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.ruleType = wx.Choice(
			self,
			choices=list(ruleTypes.ruleTypeLabels.values())
		)
		item.Bind(wx.EVT_CHOICE, self.onRuleType_choice)
		# todo: change tooltip's text
		# Translators: Tooltip for rule type choice list.
		item.SetToolTip(_("TOOLTIP EXEMPLE"))
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=SHARED_LABELS["name"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.ruleName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		self.ruleName.Bind(wx.EVT_TEXT, self.onRuleName)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Summar&y:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		gbSizer.Add(item, pos=(row, 2), span=(2, 1), flag=wx.EXPAND)

		row += 2
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Technical n&otes:"))
		gbSizer.Add(item, pos=(row, 0))
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), span=(2, 1), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row + 1)

		gbSizer.AddGrowableCol(2)
		gbSizer.FitInside(self)

	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		data = self.getData()
		self.ruleType.SetSelection(tuple(ruleTypes.ruleTypeLabels.keys()).index(data["type"]))
		# Does not emit EVT_TEXT
		self.ruleName.ChangeValue(data.get("name", ""))
		self.commentText.ChangeValue(data.get("comment", ""))
		self.refreshSummary()

	def updateData(self):
		data = self.getData()
		# The type and name are already stored by their respective event handlers and should
		# not be updated here to avoid resetting changes made through the SingleFieldEditor on
		# the tree child nodes.
		updateOrDrop(data, "comment", self.commentText.Value)

	def spaceIsPressedOnTreeNode(self, withShift=False):
		self.ruleType.SetFocus()

	@guarded
	def onRuleName(self, evt):
		data = self.getData()
		value = data["name"] = self.ruleName.Value.strip()
		prm = self.categoryParams
		for index, childPrm in enumerate(
			child.categoryParams
			for child in prm.tree.getTreeNodeInfo(prm.treeNode).children
		):
			if childPrm.fieldName == "name":
				break
		else:
			raise Exception("Could not find child TreeNode for updating")
			return
		nodeId = prm.tree.getXChild(prm.treeNode, index)
		nodeInfo = prm.tree.getTreeNodeInfo(nodeId)
		cls = nodeInfo.categoryClass.func  # This is a partial
		prm.tree.SetItemText(nodeId, cls.getTreeNodeLabel(childPrm.fieldDisplayName, value))

	@guarded
	def onRuleType_choice(self, evt):
		data = self.getData()
		data["type"] = self.getTypeFieldValue()
		self.refreshSummary()
		self.onRuleType_change()

	def getTypeFieldValue(self):
		return tuple(ruleTypes.ruleTypeLabels.keys())[self.ruleType.Selection]

	def getSummary(self):
		if not self.context:
			return "nope"
		data = self.getData().copy()
		for panel in list(self.Parent.Parent.catIdToInstanceMap.values()):
			panel.updateData()
		return getSummary(self.context, data)

	def refreshSummary(self):
		self.summaryText.Value = self.getSummary()

	def onPanelActivated(self):
		self.refreshSummary()
		super().onPanelActivated()

	def isValid(self):
		self.updateData()
		data = self.getData()
		# Type is required
		if not data.get("type"):
			# This should not happen as there is no way to unset the default choice
			gui.messageBox(
				# Translators: Error message when no type is chosen before saving the rule
				message=_("You must choose a type for this rule"),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.ruleType.SetFocus()
			return False

		# Name is required
		if not data.get("name"):
			gui.messageBox(
				# Translators: Error message when no name is entered before saving the rule
				message=_("You must choose a name for this rule"),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.ruleName.SetFocus()
			return False
		newName = data["name"]
		context = self.context
		if context.get("new"):
			prevName = None
			webModule = webModuleHandler.getEditableWebModule(context["webModule"])
			if not webModule:
				# Raising rather than returning False does not focus the panel
				raise ValidationError("The WebModule is not editable")
			layer = webModule.getWritableLayer()
		else:
			rule = context["rule"]
			prevName = rule.name
			layer = rule.layer
		if newName != prevName:
			mgr = self.getRuleManager()
			try:
				mgr.getRule(newName, layer)
			except LookupError:
				pass
			else:
				gui.messageBox(
					# Translators: Error message when another rule with the same name already exists
					message=_("There already is another rule with the same name."),
					caption=_("Error"),
					style=wx.ICON_ERROR | wx.OK,
					parent=self
				)
				return False
		return True


class AlternativesPanel(RuleEditorTreeContextualPanel):
	# Translators: The label for a category in the rule editor
	title = _("Criteria")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.indexCriteria = None

	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		row = 0
		# Translators: Label for a control in the Rule Editor
		item = wx.StaticText(self, label=_("&Alternatives"))
		gbSizer.Add(item, pos=(row, 0))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		
		row += 1
		listStartRow = row
		listEndCol = 2
		item = self.criteriaList = wx.ListBox(self)
		item.Bind(wx.EVT_LISTBOX, self.onCriteriaSelected)
		gbSizer.Add(item, pos=(row, 0), span=(6, 3), flag=wx.EXPAND)
		
		row += 6
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Summar&y:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL), pos=(row, 1))
		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		gbSizer.Add(item, pos=(row, 2), span=(2, 1), flag=wx.EXPAND)
		
		row += 2
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Technical n&otes:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL), pos=(row, 1))
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), span=(2, 1), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row + 1)
		
		row = listStartRow
		col = listEndCol + 1
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, col))
		
		col += 1
		# Translators: The label for a button on the Rule Editor dialog
		item = self.newButton = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onNewCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
		
		row += 1
		# Translators: The label for a button on the Rule Editor dialog
		item = self.editButton = wx.Button(self, label=_("&Edit..."))
		item.Bind(wx.EVT_BUTTON, self.onEditCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
		
		row += 1
		# Translators: The label for a button on the Rule Editor dialog
		item = self.deleteButton = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteCriteria)
		gbSizer.Add(item, pos=(row, col))

		gbSizer.AddGrowableCol(listEndCol)

	def getData(self):
		return super().getData().setdefault("criteria", [])

	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		self.initData_alternatives()

	def initData_alternatives(self) -> None:
		self.updateCriteriaList()

	def updateData(self):
		# Nothing to update: This panel writes directly into the data map.
		pass

	@staticmethod
	def getCriteriaName(criteria):
		if criteria.get("name"):
			return criteria["name"]
		else:
			return criteriaEditor.getSummary_context(criteria)[0]

	def spaceIsPressedOnTreeNode(self, withShift=False):
		if self.getData():
			self.criteriaList.SetFocus()
		else:
			self.newButton.SetFocus()

	def getIndex(self):
		return self.criteriaList.Selection

	def onCriteriaChange(self, change: Change, index: int):
		self.updateCriteriaList(index)
		self.refreshParent(self.categoryParams.treeNode)

	@guarded
	def onNewCriteria(self, evt):
		prm = self.categoryParams
		listData = self.getData()
		context = self.context.copy()
		context["new"] = True
		itemData = context["data"]["criteria"] = OrderedDict({
			"criteriaIndex": len(self.getData())
		})
		if criteriaEditor.show(context, parent=self):
			index = itemData.pop("criteriaIndex")
			listData.insert(index, itemData)
			self.onCriteriaChange(Change.CREATION, index)

	@guarded
	def onEditCriteria(self, evt):
		context = self.context.copy()
		context["new"] = False
		listData = self.getData()
		index = self.getIndex()
		itemData = context["data"]["criteria"] = listData[index].copy()
		itemData["criteriaIndex"] = index
		if criteriaEditor.show(context, self):
			del listData[index]
			index = itemData.pop("criteriaIndex")
			listData.insert(index, itemData)
			self.onCriteriaChange(Change.UPDATE, index)

	@guarded
	def onDeleteCriteria(self, evt):
		prm = self.categoryParams
		index = self.getIndex()
		if gui.messageBox(
			# Translator: A confirmation prompt on the Rule editor
			_("Are you sure you want to delete this alternative?"),
			# Translator: The title for a confirmation prompt on the Rule editor
			_("Confirm Deletion"),
			wx.YES | wx.NO | wx.CANCEL | wx.ICON_QUESTION, self
		) == wx.YES:
			del self.getData()[index]
			self.onCriteriaChange(Change.DELETION, index)

	@guarded
	def onCriteriaSelected(self, evt):
		self.editButton.Enable(True)
		self.deleteButton.Enable(True)
		data = self.getData()[self.criteriaList.Selection]
		self.summaryText.Value = criteriaEditor.getSummary(self.context, data)
		self.commentText.Value = data.get("comment", "")

	@staticmethod
	def getTreeNodeLabel(criteria):
		return AlternativesPanel.getCriteriaName(criteria)

	def updateCriteriaList(self, index=None):
		data = self.getData()
		ctrl = self.criteriaList
		if index is None:
			index = max(ctrl.Selection, 0)
		ctrl.Clear()
		for criteria in data:
			ctrl.Append(self.getCriteriaName(criteria))
		if data:
			index = min(index, len(data) - 1)
			ctrl.Select(index)
			self.onCriteriaSelected(None)
		else:
			self.summaryText.Value = ""
			self.commentText.Value = ""
			self.editButton.Disable()
			self.deleteButton.Disable()

	def onSave(self):
		super().onSave()
		data = super().getData()
		if not data.get("gestures"):
			data.pop("gestures", None)


class GesturesPanel(GesturesPanelBase, RuleEditorTreeContextualPanel):
	
	def delete(self):
		wx.Bell()
	
	def onGestureChange(self, change: Change, id: str):
		super().onGestureChange(change, id)
		prm = self.categoryParams
		self.refreshParent(prm.treeNode)			
	
	def spaceIsPressedOnTreeNode(self, withShift=False):
		self.gesturesListBox.SetFocus()


class PropertiesPanel(PropertiesPanelBase, RuleEditorTreeContextualPanel):
	
	# Called by SinglePropertyEditorPanelBase.initData
	def initData_properties(self):
		self.props = Properties(self.context, self.getData())
	
	# Overrides SingleFieldEditorMixin's
	def onEditor_change(self, reset=False):
		super().onEditor_change()
		prm = self.categoryParams
		# Refreshing all child nodes is too slow for quick editing
		prm.tree.SetItemText(
			prm.tree.getXChild(prm.treeNode, tuple(p.name for p in self.props).index(self.prop.name)),
			ChildPropertyPanel.getTreeNodeLabelForProp(self.prop)
		)


class ChildAlternativePanel(AlternativesPanel):

	def makeSettings(self, settingsSizer):
		scale = self.scale
		self.settingsSizer = gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		
		row = 0
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Summar&y"))
		gbSizer.Add(item, pos=(row, 0))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		
		row += 1
		summaryStartRow = row
		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		gbSizer.Add(item, pos=(row, 0), span=(5, 1), flag=wx.EXPAND)
		
		row += 5
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Technical n&otes"))
		gbSizer.Add(item, pos=(row, 0))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		
		row += 1
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 0), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)
		
		row = summaryStartRow
		col = 1
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(row, col))
		
		col += 1
		row += 2
		# Translators: Edit criteria button label
		item = self.editButton = wx.Button(self, label=_("&Edit..."))
		item.Bind(wx.EVT_BUTTON, self.onEditCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
		
		row += 1
		# Translators: Delete criteria button label
		item = self.deleteButton = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		# Keep natural visual ordering but set last in tab order
		row = summaryStartRow
		# Translators: New criteria button label
		item = self.newButton = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onNewCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
		
		gbSizer.AddGrowableCol(0)

	def spaceIsPressedOnTreeNode(self, withShift=False):
		self.editButton.SetFocus()
	
	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		prm = self.categoryParams
		self.indexCriteria = prm.tree.getSelectionIndex()
		data = self.getData()[self.indexCriteria]
		self.summaryText.Value = criteriaEditor.getSummary(self.context, data)
		self.commentText.Value = data.get("comment", "")

	def initData_alternatives(self) -> None:
		pass
	
	def updateData(self):
		pass

	def delete(self):
		self.onDeleteCriteria(None)

	def getIndex(self):
		return self.indexCriteria

	def onCriteriaChange(self, change: Change, index: int):
		prm = self.categoryParams
		self.refreshParent(prm.treeParent)
		if change is Change.DELETION:
			index = min(index, len(prm.tree.getChildren(prm.treeParent)) - 1)
			newItem = prm.tree.getXChild(prm.treeParent, index) if index >= 0 else prm.treeParent
		else:
			newItem = prm.tree.getXChild(prm.treeParent, index)
		prm.tree.SelectItem(newItem)
		prm.tree.SetFocusedItem(newItem)
		prm.tree.SetFocus()


class ChildGesturePanel(RuleEditorTreeContextualPanel):

	@dataclass
	class CategoryParams(TreeContextualPanel.CategoryParams):
		title: str = None
		gestureIdentifier: str = None
	
	@staticmethod
	def getTreeNodeLabel(mgr: RuleManager, gestureIdentifier, action):
		gestureSource, gestureMain = inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)
		# Translators: A gesture binding on the editor dialogs
		return "{gesture}: {action}".format(
			gesture=gestureMain, action=mgr.getActions().get(action, f"*{action}")
		)
	
	def makeSettings(self, sizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		sizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		row = 0
		col = 0
		# Not focusable, but really only serves as an eye-candy
		self.textCtrl = wx.TextCtrl(self, style=wx.TE_READONLY)
		gbSizer.Add(self.textCtrl, pos=(row, col), span=(1, 5), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, col))
		
		col += 2
		row += 1
		# Translators: The label for a button on the Rule Editor dialog
		item = self.editButton = wx.Button(self, label="&Edit...")
		item.Bind(wx.EVT_BUTTON, self.onEditGesture)
		gbSizer.Add(item, pos=(row, col))
		
		col += 1
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(row, col))
		
		col += 1
		# Translators: The label for a button on the Rule Editor dialog
		item = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
		gbSizer.Add(item, pos=(row, col))
		
		# Keep natural visual ordering but set last in tab order
		col = 0
		# Translators: The label for a button on the Rule Editor dialog
		item = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onAddGesture)
		gbSizer.Add(item, pos=(row, col))
		
		col += 1
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(row, col))
	
	def getData(self):
		return super().getData()["gestures"]
	
	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		self.textCtrl.Value = self.categoryParams.title
	
	def updateData(self):
		# Nothing to update: This panel writes directly into the data map.
		pass
	
	def delete(self):
		self.onDeleteGesture(None)
	
	@guarded
	def onAddGesture(self, evt):
		context = self.context.copy()
		context["data"]["gestures"] = self.getData()
		if gestureBinding.show(context, parent):
			index = context["data"]["gestureBinding"]["index"]
			self.updateTreeAndSelectItemAtIndex(index)
	
	@guarded
	def onDeleteGesture(self, evt):
		prm = self.categoryParams
		gestures = self.getData()
		id = prm.gestureIdentifier
		index = tuple(gestures.keys()).index(id)
		del gestures[id]
		if index >= len(gestures):
			index -= 1
		prm.tree.deleteSelection()
		item = prm.tree.getXChild(prm.treeParent, index) if index >= 0 else prm.treeParent
		prm.tree.SelectItem(item)
	
	@guarded
	def onEditGesture(self, evt):
		prm = self.categoryParams
		context = self.context.copy()
		gestures = context["data"]["gestures"] = self.getData()
		context["data"]["gestureBinding"] = {
			"gestureIdentifier": prm.gestureIdentifier,
			"action":  gestures[prm.gestureIdentifier],
		}
		if gestureBinding.show(context, self):
			index = context["data"]["gestureBinding"]["index"]
			self.updateTreeAndSelectItemAtIndex(index)
	
	def updateTreeAndSelectItemAtIndex(self, index):
		prm = self.categoryParams
		self.refreshParent(prm.treeParent)
		prm.tree.SelectItem(prm.tree.getXChild(prm.treeParent, index))
		prm.tree.SetFocus()
	
	def spaceIsPressedOnTreeNode(self, withShift=False):
		self.onEditGesture(None)


class ChildPropertyPanel(
	SinglePropertyEditorPanelBase,
	RuleEditorSingleFieldChildPanel,
	RuleEditorTreeContextualPanel
):
	
	def __init__(self, *args, prop: Property = None, **kwargs):
		self.prop: Property = prop
		super().__init__(*args, **kwargs)
	
	@classmethod
	def getTreeNodeLabelForProp(cls, prop: Property) -> str:
		return super().getTreeNodeLabel(prop.displayName, prop.value, prop.choices)
	
	# Called by SinglePropertyEditorPanelBase.initData
	def initData_properties(self):
		self.props = Properties(self.context, self.getData())
	
	# called by TreeMultiCategorySettingsDialog.onKeyDown
	def delete(self):
		self.prop_reset()


class RuleEditorDialog(TreeMultiCategorySettingsDialog):
	
	INITIAL_SIZE = (750, 520)
	categoryInitList = [
		(GeneralPanel, 'getGeneralChildren'),
		(AlternativesPanel, 'getAlternativeChildren'),
		(GesturesPanel, 'getGesturesChildren'),
		#FIXME PropertiesPanel, 'getPropertiesChildren'),
		(PropertiesPanel, 'getPropertiesChildren'),
	]
	categoryClasses = [
		GeneralPanel,
		AlternativesPanel,
		GesturesPanel,
		#FIXME PropertiesPanel,
		PropertiesPanel,
	]

	def __init__(self, *args, **kwargs):
		# Uncomment the below to focus the first field upon dialog appearance
		# kwargs["initialCategory"] = GeneralPanel
		super().__init__(*args, **kwargs)
		self.isCreation = False

	def getGeneralChildren(self):
		cls = RuleEditorSingleFieldChildPanel
		data = self.getData()
		return tuple(
			TreeNodeInfo(
				partial(cls, editorType=editorType),
				title=cls.getTreeNodeLabel(
					prm.fieldDisplayName, data.get(prm.fieldName), prm.editorChoices
				),
				categoryParams=prm
			)
			for editorType, prm in (
				(EditorType.CHOICE, cls.CategoryParams(
					editorChoices=ruleTypes.ruleTypeLabels,
					fieldDisplayName=SHARED_LABELS["type"],
					fieldName="type",
					onEditor_change=cls.onRuleType_change,
				)),
				(EditorType.TEXT, cls.CategoryParams(
					fieldDisplayName=SHARED_LABELS["name"],
					fieldName="name",
				)),
			)
		)

	def getAlternativeChildren(self):
		return tuple(
			TreeNodeInfo(
				ChildAlternativePanel,
				title=ChildAlternativePanel.getTreeNodeLabel(data),
				categoryParams=ChildAlternativePanel.CategoryParams()
			)
			for data in self.getData().get("criteria", [])
		)

	def getGesturesChildren(self):
		data = self.getData()
		if data["type"] not in [ruleTypes.ACTION_TYPES]:
			return []
		mgr = self.context["webModule"].ruleManager
		panels = []
		for key, value in data.get('gestures', {}).items():
			title = ChildGesturePanel.getTreeNodeLabel(mgr, key, value)
			prm = ChildGesturePanel.CategoryParams(title=title, gestureIdentifier=key)
			panels.append(TreeNodeInfo(ChildGesturePanel, title=title, categoryParams=prm))
		return panels

	def getPropertiesChildren(self) -> Sequence[TreeNodeInfo]:
		context = self.context
		data = self.getData().setdefault("properties", {})
		props = Properties(context, data)
		cls = ChildPropertyPanel
		return tuple(
			TreeNodeInfo(
				partial(cls, prop=prop),
				title=cls.getTreeNodeLabelForProp(prop),
				categoryParams=cls.CategoryParams(),
			)
			for prop in props
		)
	
	def getData(self):
		return self.context["data"]["rule"]
	
	def initData(self, context: Mapping[str, Any]) -> None:
		context.setdefault("data", {})
		webModule = context["webModule"]
		ruleManager = webModule.ruleManager
		if context.get("new"):
			data = context["data"]["rule"] = {"type": ruleTypes.MARKER}
			if ruleManager.parentZone is not None:
				# Translators: A title of the rule editor
				title = (_("Sub Module {} - New Rule").format(webModule.name))
			elif ruleManager.subModules.all():
				# Translators: A title of the rule editor
				title = (_("Root Module {} - New Rule").format(webModule.name))
			else:
				# Translators: A title of the rule editor
				title = (_("Web Module {} - New Rule").format(webModule.name))
		else:
			data = context["data"]["rule"] = context["rule"].dump()
			if ruleManager.parentZone is not None:
				# Translators: A title of the rule editor
				title = (_("Sub Module {} - Edit Rule {}").format(webModule.name, data.get("name")))
			elif ruleManager.subModules.all():
				# Translators: A title of the rule editor
				title = (_("Root Module {} - Edit Rule {}").format(webModule.name, data.get("name")))
			else:
				# Translators: A title of the rule editor
				title = (_("Web Module {} - Edit Rule {}").format(webModule.name, data.get("name")))
		if config.conf["webAccess"]["devMode"]:
			layerName = None
			if context.get("new"):
				try:
					webModule = webModuleHandler.getEditableWebModule(webModule, prompt=False)
					if webModule:
						layerName = webModule.getWritableLayer().name
				except Exception:
					log.exception()
			else:
				layerName = context["rule"].layer
			title += f" ({layerName})"
		self.SetTitle(title)
		nodeManager = ruleManager.nodeManager
		if nodeManager:
			node = nodeManager.getCaretNode()
			while node is not None:
				if node.role in formModeRoles:
					data.setdefault("properties", {})["formMode"] = True
					break
				node = node.parent
		super().initData(context)
	
	def _saveAllPanels(self):
		super()._saveAllPanels()
		context = self.context
		data = self.getData()
		mgr = context["webModule"].ruleManager
		if context.get("new"):
			layerName = None
		else:
			rule = context["rule"]
			layerName = rule.layer
		webModule = webModuleHandler.getEditableWebModule(mgr.webModule, layerName=layerName)
		if not webModule:
			raise ValidationError()  # Cancels closing of the dialog
		if createMissingSubModule(context, data, self) is False:
			raise ValidationError()  # Cancels closing of the dialog
		if context.get("new"):
			layerName = webModule.getWritableLayer().name
		else:
			mgr.removeRule(rule)
		context["rule"] = mgr.loadRule(layerName, data["name"], data)
		webModule.getLayer(layerName, raiseIfMissing=True).dirty = True
		if not webModuleHandler.save(webModule, layerName=layerName):
			raise ValidationError()  # Cancels closing of the dialog


def show(context, parent=None):
	return showContextualDialog(RuleEditorDialog, context, parent) == wx.ID_OK
