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
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from functools import partial
import sys
from typing import Any
import wx
from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import addonHandler
import config
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
from . import criteriaEditor, gestureBinding, saveRule
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
					altHeader = _('Alternative #{index} "{name}":').format(index=index + 1, name=name)
				else:
					# Translators: The label for a section on the Rule Summary report
					altHeader = _("Alternative #{index}:").format(index=index + 1)
				subParts.append("  " + altHeader)
				subParts.append(criteriaEditor.getSummary(
					context, alternative, indent="    ", condensed=True
				))
		parts.extend(subParts)
	return "\n".join(parts)


def supportsSimpleMode(context):
	alternatives = context.get("data", {}).get("rule", {}).get("criteria", [])
	if not alternatives:
		return True
	if len(alternatives) > 1:
		return False
	return True


class RuleEditorTreeContextualPanel(RuleAwarePanelBase, TreeContextualPanel):
	
	def getData(self):
		return self.getRuleData()
	
	def confirmRuleTypeChange(self):
		data = self.getRuleData()
		if any(
			criteriaEditor.isDualNode(alternative)
			for alternative in data.get("criteria", [])
		):
			if gui.messageBox(
				_(
					#Translators: A prompt for confirmation on the Rule editor
					"""This will delete your End Criteria choices.

Do you want to proceed?"""
				),
				# Translators: The title of a prompt for confirmation on the Rule editor
				caption=_("Rule Type change"),
				style=wx.ICON_WARNING | wx.YES_NO | wx.NO_DEFAULT
			) != wx.YES:
				return False
			for alternative in data["criteria"]:
				if criteriaEditor.isDualNode(alternative):
					criteriaEditor.convertToSingleNode(alternative)
		return True
	
	def onRuleType_change(self):
		prm = self.categoryParams
		categoryClasses = tuple(nodeInfo.categoryClass for nodeInfo in self.Parent.Parent.categoryClasses)
		for index in (categoryClasses.index(cls) for cls in (GesturesPanel, PropertiesPanel)):
			category = prm.tree.getXChild(prm.tree.RootItem, index)
			self.refreshParent(category)


class GeneralPanel(RuleEditorTreeContextualPanel):
	# Translators: The label for the General settings panel.
	title = _("General")

	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
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
		# Translators: The label for a field on the Rule editor
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
		prm.tree.updateNodeText(nodeId, cls.getTreeNodeLabel(childPrm.fieldDisplayName, value))

	@guarded
	def onRuleType_choice(self, evt):
		if not self.confirmRuleTypeChange():
			self.initData(self.context)
			return
		data = self.getData()
		value = data["type"] = self.getTypeFieldValue()
		self.refreshSummary()
		prm = self.categoryParams
		for index, childPrm in enumerate(
			child.categoryParams
			for child in prm.tree.getTreeNodeInfo(prm.treeNode).children
		):
			if childPrm.fieldName == "type":
				break
		else:
			raise Exception("Could not find child TreeNode for updating")
			return
		nodeId = prm.tree.getXChild(prm.treeNode, index)
		nodeInfo = prm.tree.getTreeNodeInfo(nodeId)
		cls = nodeInfo.categoryClass.func  # This is a partial
		prm.tree.updateNodeText(nodeId, cls.getTreeNodeLabel(
			childPrm.fieldDisplayName, value, childPrm.editorChoices
		))
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
		# Beware this method is also used on the GeneralPage of the Rule Creation Wizard
		self.updateData()
		data = self.getData()
		# Type is required
		if not data.get("type"):
			# This should not happen as there is no way to unset the default choice
			gui.messageBox(
				# Translators: Error message when no type is chosen before saving the rule
				message=_("You must choose a type for this rule"),
				# Translators: The title of a message dialog
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
			layer = webModule.getWritableLayer().name
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
		self.criteriaIndex = None

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
		item.Bind(wx.EVT_CHAR_HOOK, self.onCriteriaListCharHook)
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

	def isValid(self):
		self.updateData()
		data = self.getData()
		if not data or any(
			not crit.get("selector")
			for crit in data
		):
			gui.messageBox(
				# Translators: An error message on the Rule Editor
				message=_("You must choose at least one criteria."),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			return False
		return True

	@guarded
	def copyAlternative(self):
		index = self.getIndex()
		if index == wx.NOT_FOUND:
			wx.Bell()
			return
		data = {"webAccess.criteria" : self.getData()[index]}
		import json
		data = json.dumps(data, indent=4)
		import api
		if api.copyToClip(data):
			# Translators: A message from the Rule Editor dialog
			ui.message(_("Criteria data copied to clipboard"))
			return
		wx.Bell()
	
	def pasteAlternative(self):
		import api
		data = api.getClipData()
		if not data:
			wx.Bell()
			return
		import json
		try:
			data = json.loads(data)
		except Exception:
			wx.Bell()
			return
		if not isinstance(data, dict) and len(data) == 1:
			wx.Bell()
			return
		key, data = data.popitem()
		if key == "webAccess.rule":
			try:
				data = data["criteria"]
				if len(data) != 1:
					wx.Bell()
					return
				data = data[0]
			except (AttributeError, TypeError):
				wx.Bell()
				return
		elif key == "webAccess.criteria":
			pass
		elif key == "webAccess.selector":
			data = {"selector": data} 
		else:
			wx.Bell()
			return
		if criteriaEditor.isDualNode(data) and self.getRuleType() != ruleTypes.ZONE:
			wx.Bell()
			return
		self.onNewCriteria(pastedData=data)
	
	def onCriteriaChange(self, change: Change, index: int):
		self.updateCriteriaList(index)
		self.refreshParent(self.categoryParams.treeNode)

	@guarded
	def onCriteriaListCharHook(self, evt):
		keyCode = evt.KeyCode
		mods = evt.GetModifiers()
		if keyCode == wx.WXK_DELETE and mods == wx.MOD_NONE:
			self.onDeleteCriteria()
			return
		elif (
			keyCode in (ord("C"), wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT)
			and mods == wx.MOD_CONTROL
		):
			self.copyAlternative()
			return
		elif (
			keyCode == ord("V") and mods == wx.MOD_CONTROL
			or keyCode in (wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT) and mods == wx.MOD_SHIFT
		):
			self.pasteAlternative()
			return
		evt.Skip()

	@guarded
	def onNewCriteria(self, evt=None, pastedData=None):
		listData = self.getData()
		index = self.getIndex()
		if index != wx.NOT_FOUND:
			itemData = listData[index]
			if not itemData.get("name"):
				with wx.TextEntryDialog(
					self,
					# Translators: A prompt on the Rule editor
					_("You may first provide a name for the current criteria set:"),
					# Translators: The title of an input dialog in the Rule Editor dialog
					_("Add alternatives"),
				) as dlg:
					if dlg.ShowModal() != wx.ID_OK:
						return
					name = dlg.Value
					if name:
						itemData["name"] = name
						self.onCriteriaChange(Change.UPDATE, index)
		context = self.context.copy()
		context["new"] = True
		itemData = context["data"]["criteria"] = OrderedDict({
			"criteriaIndex": len(self.getData())
		})
		if pastedData:
			itemData.update(pastedData)
		if criteriaEditor.show(context, parent=self):
			index = itemData.pop("criteriaIndex")
			listData.insert(index, itemData)
			self.onCriteriaChange(Change.CREATION, index)

	@guarded
	def onEditCriteria(self, evt, convertToDualNode=False):
		context = self.context.copy()
		context["new"] = False
		listData = self.getData()
		index = self.getIndex()
		itemData = context["data"]["criteria"] = deepcopy(listData[index])
		if convertToDualNode:
			criteriaEditor.convertToDualNode(itemData)
		itemData["criteriaIndex"] = index
		if criteriaEditor.show(context, self):
			del listData[index]
			index = itemData.pop("criteriaIndex")
			listData.insert(index, itemData)
			self.onCriteriaChange(Change.UPDATE, index)

	@guarded
	def onDeleteCriteria(self, evt=None):
		index = self.getIndex()
		if index == wx.NOT_FOUND:
			wx.Bell()
			return
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
			index = ctrl.Selection
			if index < 0:
				# When first displaying the list, attempt to select the
				# alternative corresponding to the result at caret, if any.
				try:
					result = self.context["result"]
					if self.getRuleData()["name"] == result.rule.name:
						index = self.getData().index(result.criteria.dump())
				except Exception:
					pass
			if index < 0:
				index = 0
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
	def onEditor_change(self):
		super().onEditor_change()
		prm = self.categoryParams
		# Refreshing all child nodes is too slow for quick editing
		prm.tree.updateNodeText(
			prm.tree.getXChild(prm.treeNode, tuple(p.name for p in self.props).index(self.prop.name)),
			PropertyChildPanel.getTreeNodeLabelForProp(self.prop)
		)


class RuleEditorSingleFieldChildPanel(SingleFieldEditorPanelBase, RuleEditorTreeContextualPanel):
	pass


class RuleTypeChildPanel(RuleEditorSingleFieldChildPanel):

	def onEditor_change(self):
		super().onEditor_change()
		self.onRuleType_change()
	
	@guarded
	def onEditor_choice(self, evt):
		if self.confirmRuleTypeChange():
			super().onEditor_choice(evt)
		else:
			self.updateEditor()
	
	def toggleFieldValue(self, previous: bool = False) -> None:
		if self.confirmRuleTypeChange():
			super().toggleFieldValue(previous=previous)


class AlternativeChildPanel(AlternativesPanel):

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
		
		self.makeSettings_buttons(gbSizer, summaryStartRow, 1)
		
		gbSizer.AddGrowableCol(0)
	
	def makeSettings_buttons(self, gbSizer, row, col, full=True):
		scale = self.scale
		startRow = row
		
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(row, col))
		
		col += 1
		row += 2
		# Translators: Edit criteria button label
		item = self.editButton = wx.Button(self, label=_("&Edit..."))
		item.Bind(wx.EVT_BUTTON, self.onEditCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		if full:
			row += 1
			gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
			
			row += 1
			# Translators: Delete criteria button label
			item = self.deleteButton = wx.Button(self, label=_("&Delete"))
			item.Bind(wx.EVT_BUTTON, self.onDeleteCriteria)
			gbSizer.Add(item, pos=(row, col))
		
		# Keep natural visual ordering but set last in tab order
		row = startRow
		# Translators: New criteria button label
		item = self.newButton = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onNewCriteria)
		gbSizer.Add(item, pos=(row, col))
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))
		
	
	def spaceIsPressedOnTreeNode(self, withShift=False):
		self.editButton.SetFocus()
	
	def initData(self, context: Mapping[str, Any]) -> None:
		super().initData(context)
		data = self.getData()[self.getIndex()]
		self.summaryText.Value = criteriaEditor.getSummary(self.context, data)
		self.commentText.Value = data.get("comment", "")

	def initData_alternatives(self) -> None:
		prm = self.categoryParams
		self.criteriaIndex = prm.tree.getSelectionIndex()
	
	def updateData(self):
		pass

	def delete(self):
		self.onDeleteCriteria(None)

	def getIndex(self):
		return self.criteriaIndex

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


class PropertyChildPanel(
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


class SimpleSingleNodeCriteriaPanel(criteriaEditor.CriteriaPanel):
	
	def makeSettings_buttons(self, vBoxSizer):
		super().makeSettings_buttons(vBoxSizer)
		scale = self.scale
		hidable = self.hidable
		
		items = hidable["convertToDual"] = []
		item = vBoxSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL))
		items.append(item)
		item.Show(False)
		# Translators: The label for a button in the Rule Editor dialog
		item = wx.Button(self, label=_("Convert to free &zone (two sets of criteria)"))
		item.Bind(wx.EVT_BUTTON, self.Parent.onConvertToDualNode)
		vBoxSizer.Add(item, flag=wx.EXPAND)
		items.append(item)
		item.Hide()
		
		vBoxSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL))
		# Translators: The label for a button in the Rule Editor dialog
		item = wx.Button(self, label=_("Add alternati&ves"))
		item.Bind(wx.EVT_BUTTON, self.Parent.onAddAlternative)
		vBoxSizer.Add(item, flag=wx.EXPAND)
		
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
	
	def getData(self):
		return self.getRuleData().setdefault(
			"criteria", [{}]
		)[0].setdefault("selector", {})
	
	def initData(self, context):
		super().initData(context)
		self.Freeze()
		show = self.getRuleType() == ruleTypes.ZONE
		for item in self.hidable["convertToDual"]:
			item.Show(show)
			if isinstance(item, wx.Window):
				# Enabled buttons can still be activated using their accelerator,
				# even when hidden.
				item.Enable(show)
		self.Thaw()
	
	def onCharHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_F5 and mods == wx.MOD_NONE:
			self.testCriteria()
			return
		evt.Skip()
	
	def onTestCriteria(self, evt):
		# Bound to the test button by CriteriaPanel.makeSettings
		self.testCriteria()
	
	def testCriteria(self):
		self.updateData()
		context = self.context
		context["data"]["criteria"] = {"selector": self.getData()}
		criteriaEditor.testCriteria(context)
		del context["data"]["criteria"]
	
	def spaceIsPressedOnTreeNode(self):
		self.contextMacroDropDown.SetFocus()


class SimpleSummaryCriteriaPanel(AlternativeChildPanel):
	
	def makeSettings_buttons(self, gbSizer, row, col):
		super().makeSettings_buttons(gbSizer, row, col, full=False)
	
	def initData_alternatives(self) -> None:
		self.criteriaIndex = 0
	
	def onCriteriaChange(self, change: Change, index: int):
		parent = self.Parent
		dlg = parent.Parent.Parent
		if change is Change.CREATION:
			dlg.switchToFullEditor()
			return
		parent.switchToAppropriatePanel()
		parent.shownPanel.initData(self.context)


class SimpleCriteriaPanel(RuleEditorTreeContextualPanel):
	
	# Translators: The label for a category in the rule editor
	title = _("Criteria")
	
	def makeSettings(self, settingsSizer):
		item = self.singleNodePanel = SimpleSingleNodeCriteriaPanel(self)
		settingsSizer.Add(item, flag=wx.EXPAND, proportion=1)
		item.Hide()
		
		item = self.summaryPanel = SimpleSummaryCriteriaPanel(self)
		settingsSizer.Add(item, flag=wx.EXPAND, proportion=1)
		item.Hide()
		
		self.shownPanel = None
	
	def getData(self):
		return self.getRuleData().get("criteria", [{}])[0]
	
	def initData(self, context):
		super().initData(context)
		for panel in (self.singleNodePanel, self.summaryPanel):
			panel.initData(context)
		self.switchToAppropriatePanel()
	
	def updateData(self):
		self.shownPanel.updateData()
	
	def onAddAlternative(self, evt):
		self.summaryPanel.onNewCriteria(evt)
	
	def onConvertToDualNode(self, evt):
		self.summaryPanel.onEditCriteria(evt, convertToDualNode=True)
	
	def onPanelActivated(self):
		super().onPanelActivated()
		self.shownPanel.onPanelActivated()
	
	def isValid(self):
		return self.shownPanel.isValid()
	
	def delete(self):
		wx.Bell()
	
	def pasteAlternative(self):
		self.summaryPanel.pasteAlternative()
	
	def spaceIsPressedOnTreeNode(self):
		self.shownPanel.spaceIsPressedOnTreeNode()
	
	def switchToAppropriatePanel(self):
		data = self.getData()
		showSummary = (
			data.get("gestures")
			or data.get("properties")
			or set(data.get("selector", {}).keys()) == {"start", "end"}
		)
		singleNode = self.singleNodePanel
		summary = self.summaryPanel
		shown, hidden = (summary, singleNode) if showSummary else (singleNode, summary)
		if shown is self.shownPanel:
			return
		self.shownPanel = shown
		self.Freeze()
		shown.Show()
		hidden.Hide()
		self.Thaw()
		for child in hidden.Children:
			if child.HasFocus():
				if showSummary:
					shown.SetFocus()
				else:
					self.Parent.tree.SetFocus()
				break


class RuleEditorDialog(TreeMultiCategorySettingsDialog):
	
	INITIAL_SIZE = (750, 520)
	categoryInitList = [
		(GeneralPanel, 'getGeneralChildren'),
		(AlternativesPanel, 'getAlternativesChildren'),
		(GesturesPanel, 'getGesturesChildren'),
		(PropertiesPanel, 'getPropertiesChildren'),
	]
	categoryClasses = [
		GeneralPanel,
		AlternativesPanel,
		GesturesPanel,
		PropertiesPanel,
	]

	def __init__(self, parent, *args, simpleMode=False, **kwargs):
		self.simpleMode = simpleMode
		if simpleMode:
			self.categoryInitList = [
				(GeneralPanel, 'getGeneralChildren'),
				(SimpleCriteriaPanel, 'getSimpleCriteriaChildren'),
				(GesturesPanel, 'getGesturesChildren'),
				(PropertiesPanel, 'getPropertiesChildren'),
			]
			self.categoryClasses = [
				GeneralPanel,
				SimpleCriteriaPanel,
				GesturesPanel,
				PropertiesPanel,
			]
		super().__init__(parent, *args, **kwargs)

	def makeSettings(self, settingsSizer):
		super().makeSettings(settingsSizer)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

	def getGeneralChildren(self):
		data = self.getData()
		return tuple(
			TreeNodeInfo(
				partial(cls, editorType=editorType),
				title=cls.getTreeNodeLabel(
					prm.fieldDisplayName, data.get(prm.fieldName), prm.editorChoices
				),
				categoryParams=prm
			)
			for cls, editorType, prm in (
				(
					RuleTypeChildPanel,
					EditorType.CHOICE,
					RuleEditorSingleFieldChildPanel.CategoryParams(
						editorChoices=ruleTypes.ruleTypeLabels,
						fieldDisplayName=SHARED_LABELS["type"],
						fieldName="type",
					)
				),
				(
					RuleEditorSingleFieldChildPanel,
					EditorType.TEXT,
					RuleEditorSingleFieldChildPanel.CategoryParams(
						fieldDisplayName=SHARED_LABELS["name"],
						fieldName="name",
					)
				),
			)
		)

	def getAlternativesChildren(self):
		cls = AlternativeChildPanel
		return tuple(
			TreeNodeInfo(
				cls,
				title=cls.getTreeNodeLabel(data),
				categoryParams=cls.CategoryParams()
			)
			for data in self.getData().get("criteria", [])
		)

	def getSimpleCriteriaChildren(self):
		return tuple()

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
		cls = PropertyChildPanel
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
		self.context = context
		data = self.getData()
		webModule = context["webModule"]
		ruleManager = webModule.ruleManager
		fromWizardPage = context.pop("fromWizardPage", None)
		reload = context.pop("RuleEditorFocusOnReload", None)
		if context.get("new"):
			if ruleManager.parentZone is not None:
				# Translators: A title of the rule editor
				title = (_("Sub Module {} - New Rule").format(webModule.name))
			elif ruleManager.subModules.all():
				# Translators: A title of the rule editor
				title = (_("Root Module {} - New Rule").format(webModule.name))
			else:
				# Translators: A title of the rule editor
				title = (_("Web Module {} - New Rule").format(webModule.name))
			nodeManager = ruleManager.nodeManager
			if nodeManager:
				node = nodeManager.getCaretNode()
				while node is not None:
					if node.role in formModeRoles:
						data.setdefault("properties", {})["formMode"] = True
						break
					node = node.parent
		else:
			if ruleManager.parentZone is not None:
				# Translators: A title of the rule editor
				title = _("Sub Module {} - Edit Rule {}").format(webModule.name, data.get("name"))
			elif ruleManager.subModules.all():
				# Translators: A title of the rule editor
				title = _("Root Module {} - Edit Rule {}").format(webModule.name, data.get("name"))
			else:
				# Translators: A title of the rule editor
				title = _("Web Module {} - Edit Rule {}").format(webModule.name, data.get("name"))
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
		if (
			fromWizardPage is not None or reload is not None
		) and data.get("criteria") == [{"selector": {}}]:
			del data["criteria"]
		super().initData(context)
		if fromWizardPage is not None or reload is not None:
			if fromWizardPage is not None:
				treePath = ({
					"GeneralPage": 0,
					"ContextPage": 1,
					"CriteriaPage": 1,
					"GesturesPage": 2,
					"PropertiesPage": 3,
				}[fromWizardPage],)
				treeFocus = True
			else:
				treePath = reload["tree.path"]
				treeFocus = reload["tree.focus"]
			tree = self.catListCtrl
			node = tree.RootItem
			for index in treePath:
				children = tree.getChildren(node)
				node = children[index]
			tree.SelectItem(node)
			catInfos = tree.getTreeNodeInfo(node)
			self._doCategoryChange(catInfos)
			if treeFocus:
				tree.SetFocus()
			else:
				self.currentCategory.SetFocus()
	
	def focusContainerControl(self, index: int):
		try:
			super().focusContainerControl(index)
		except IndexError:
			cat = self.currentCategory
			if isinstance(cat, SimpleCriteriaPanel):
				[
					child for child in cat.shownPanel.GetChildren()
					if isinstance(child, wx.Control) and child.CanAcceptFocusFromKeyboard()
				][index].SetFocus()
	
	def onCharHook(self, evt):
		# Bound by TreeMultiCategorySettingsDialog.makeSettings
		keyCode = evt.KeyCode
		mods = evt.GetModifiers()
		if keyCode == wx.WXK_F12 and mods == wx.MOD_NONE:
			self.switchToFullEditor()
			return
		if self.catListCtrl.HasFocus():
			cat = self.currentCategory
			if (
				isinstance(cat, SimpleCriteriaPanel)
				and keyCode in (ord("C"), wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT)
				and mods == wx.MOD_CONTROL
			):
				cat.updateData()
				cat.summaryPanel.copyAlternative()
				return
			elif (
				isinstance(cat, (AlternativesPanel, SimpleCriteriaPanel))
				and (
					keyCode == ord("V") and mods == wx.MOD_CONTROL
					or keyCode in (wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT) and mods == wx.MOD_SHIFT
				)
			):
				if (
					isinstance(cat, SimpleCriteriaPanel)
					and isinstance(cat.shownPanel, SimpleSingleNodeCriteriaPanel)
				):
					cat.updateData()
				cat.pasteAlternative()
				return
		super().onCharHook(evt)
	
	def switchToFullEditor(self):
		if not self.simpleMode:
			wx.Bell()
			return
		self.currentCategory.updateData()
		tree = self.catListCtrl
		treePath = []
		child = tree.GetSelection()
		while child != tree.RootItem:
			parent = tree.GetItemParent(child)
			children = tree.getChildren(parent)
			index = children.index(child)
			treePath.append(index)
			child = parent
		treePath.reverse()
		self.context["RuleEditorFocusOnReload"] = {
			"tree.path": treePath,
			"tree.focus": tree.HasFocus(),
		}
		self.EndModal(wx.ID_MORE)
	
	def _validateAllPanels(self):
		# Ensure all first level panels are loaded, hence validated
		tree = self.catListCtrl
		for node in tree.getChildren(tree.RootItem):
			info = tree.getTreeNodeInfo(node)
			panel = self._getCategoryPanel(info)
		super()._validateAllPanels()
	
	def _saveAllPanels(self):
		super()._saveAllPanels()
		saveRule(self.context, self.getData(), self)


def show(context, parent=None):
	if parent is None:
		parent = gui.mainFrame
	data = context.setdefault("data", {})
	# Do not erase data eventualy coming from the Rule wizard
	if context.get("new"):
		data.setdefault("rule", {"type": ruleTypes.MARKER})
	elif not data.get("rule"):
		rule = context["rule"]
		data["rule"] = rule.dump()
	
	def show(simpleMode):
		return showContextualDialog(
			RuleEditorDialog,
			context,
			parent,
			simpleMode=simpleMode,
		)
	
	res = show(simpleMode=supportsSimpleMode(context))
	if res == wx.ID_MORE:
		res = show(simpleMode=False)
	return res == wx.ID_OK
