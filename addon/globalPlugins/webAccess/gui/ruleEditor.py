# globalPlugins/webAccess/gui/ruleEditor.py
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


__version__ = "2024.06.26"
__author__ = "Shirley Noël <shirley.noel@pole-emploi.fr>"

from collections import OrderedDict, namedtuple
import wx
# TODO: Work-arround ExpandoTextCtrl mishandling maxHeight and vscroll
# from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import addonHandler
import controlTypes
import gui, ui
import inputCore
from logHandler import log

from ..ruleHandler import builtinRuleActions, ruleTypes
from .properties import RULE_TYPE_FIELDS, FIELDS_WIDGET_MAP
from .. import ruleHandler
from ..ruleHandler import ruleTypes
from ..ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
from ..utils import updateOrDrop
from .. import webModuleHandler
from . import (
	TreeMultiCategorySettingsDialog,
	ContextualSettingsPanel,
	guiHelper,
	stripAccel,
	stripAccelAndColon,
	TreeNodeInfo,
	ContextualMultiCategorySettingsDialog,
	stripAccelAndColon,
	properties
)
addonHandler.initTranslation()

formModeRoles = [
	controlTypes.ROLE_EDITABLETEXT,
	controlTypes.ROLE_COMBOBOX,
]


def getSummary(data):
	ruleType = data.get("type")
	if ruleType is None:
		# Translators: A mention on the Rule summary report
		return _("No rule type selected.")
	parts = []
	parts.append("{} {}".format(
		# Translators: The Label for a field on the Rule editor
		stripAccel(_("Rule &type:")),
		ruleTypes.ruleTypeLabels.get(ruleType, "")
	))

	# Properties
	subParts = []
	ruleProperties = data.get("properties")
	ruleTypeProperties = properties.RULE_TYPE_FIELDS.get(ruleType, [])
	if ruleProperties:
		for key, label in list(properties.FIELDS.items()):
			if (
				key not in ruleTypeProperties
				or key not in ruleProperties
				or ruleProperties[key] is None
			):
				continue
			elif key == "sayName":
				value = data.get(key, True)
			elif key == "autoAction":
				value = builtinRuleActions.get(ruleProperties[key], f"*{ruleProperties[key]}")
			else:
				value = ruleProperties[key]
			label = properties.ListControl.getAltFieldLabel(ruleType, key, label)
			label = stripAccel(label)
			if key == "mutation":
				value = mutationLabels.get(value)
			elif isinstance(value, bool):
				if value:
					label = stripAccelAndColon(label)
					subParts.append("  {}".format(label))
				continue
			subParts.append("  {} {}".format(label, value))
	if subParts:
		parts.append(_("Properties"))
		parts.extend(subParts)

	# Criteria
	criteriaSets = data.get("criteria", [])
	if criteriaSets:
		subParts = []
		from .criteriaEditor import getSummary as getCriteriaSummary
		if len(criteriaSets) == 1:
			parts.append(_("Criteria:"))
			parts.append(getCriteriaSummary(criteriaSets[0], indent="  "))
		else:
			parts.append(_("Multiple criteria sets:"))
			for index, alternative in enumerate(criteriaSets):
				name = alternative.get("name")
				if name:
					altHeader = _("Alternative #{index} \"{name}\":").format(index=index, name=name)
				else:
					altHeader = _("Alternative #{index}:").format(index=index)
				subParts.append("  " + altHeader)
				subParts.append(getCriteriaSummary(alternative, indent="    "))
		parts.extend(subParts)
	return "\n".join(parts)


class TreeContextualPanel(ContextualSettingsPanel):
	def initData(self, context, **kwargs):
		for key, value in kwargs.items():
			setattr(self, key, value)
		self.context = context

	def refreshParent(self, parentNodeId, deleteChildren=True):
		"""Refresh tree children of a parent item
		Deletes all the childs of a branch and recreates them. To use when items are add or deletes.
		"""
		self.Parent.Parent.refreshNodePanelData(parentNodeId)
		if deleteChildren:
			self.hardRefreshChildren(parentNodeId)
		else:
			self.softRefreshChildren(parentNodeId)

	def hardRefreshChildren(self, parentNodeId):
		parentTreeNodeInfo = self.tree.getTreeNodeInfo(parentNodeId)
		self.tree.DeleteChildren(parentNodeId)
		if parentTreeNodeInfo.children:
			self.tree.addToListCtrl(parentTreeNodeInfo.children, parentNodeId)
			self.tree.Expand(parentNodeId)

	def softRefreshChildren(self, parentNodeId):
		parentTreeNodeInfo = self.tree.getTreeNodeInfo(parentNodeId)
		parent = self.Parent.Parent
		newChildren = parentTreeNodeInfo.children
		for i, oldItem in enumerate(self.tree.getChildren(parentNodeId)):
			newChildInfo = newChildren[i]
			newChildInfo.updateTreeParams(self.tree, oldItem, parentNodeId)
			self.tree.SetItemText(oldItem, newChildInfo.title)
			self.tree.setTreeNodeInfo(oldItem, newChildInfo)
			parent.refreshNodePanelData(oldItem)

	def getRuleManager(self):
		return self.context["webModule"].ruleManager

	def getData(self):
		return self.context['data']

	def getRule(self):
		return self.context['data']['rule']

	def getType(self, rule):
		return rule.get('type')


class GeneralPanel(TreeContextualPanel):
	# Translators: The label for the General settings panel.
	title = _("General")

	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		def scale(*args):
			if len(args) == 1:
				return self.scaleSize(args[0])
			return tuple([
				self.scaleSize(arg) if arg > 0 else arg
				for arg in args
			])

		row = 0
		# Translators: The Label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Rule &type:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.ruleType = wx.Choice(
			self,
			choices=list(ruleTypes.ruleTypeLabels.values())
		)
		item.Bind(wx.EVT_CHOICE, self.onTypeChange)
		# todo: change tooltip's text
		# Translators: Tooltip for rule type choice list.
		item.SetToolTip(_("TOOLTIP EXEMPLE"))
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translators: The Label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Rule &name"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.ruleName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		self.ruleName.Bind(wx.EVT_KILL_FOCUS, self.onNameEdited)

		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("&Summary"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.summaryText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Technical &notes"))
		gbSizer.Add(item, pos=(row, 0))
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		gbSizer.AddGrowableCol(2)

	def initData(self, context, **kwargs):
		super().initData(context, **kwargs)
		data = self.getRule()
		if 'type' in data:
			self.ruleType.SetSelection(list(ruleTypes.ruleTypeLabels.keys()).index(data['type']))
		else:
			self.ruleType.SetSelection(0)

		self.ruleName.Value = data.get("name", "")
		self.commentText.Value = data.get("comment", "")
		self.refreshSummary()

	@staticmethod
	def initRuleTypeChoice(data, ruleTypeChoice):
		for index, key in enumerate(ruleTypes.ruleTypeLabels.keys()):
			if key == data["type"]:
				ruleTypeChoice.SetSelection(index)
				break

	def updateData(self, data=None):
		if data is None:
			data = self.getRule()
		# The rule type should already be stored as of onTypeChange
		data["name"] = self.ruleName.Value
		data['type'] = self.getTypeFieldValue()
		updateOrDrop(data, "comment", self.commentText.Value)

	def onNameEdited(self, evt):
		self.getRule()["name"] = self.ruleName.Value
		self.refreshParent(self.treeNode, deleteChildren=False)

	def onTypeChange(self, evt):
		data = self.getRule()
		data["type"] = self.getTypeFieldValue()
		self.refreshSummary()
		self.refreshParent(self.treeNode, deleteChildren=False)
		for i in [2, 3]:
			category = self.tree.getXChild(self.tree.GetRootItem(), i)
			self.refreshParent(category)

	def getTypeFieldValue(self):
		return tuple(ruleTypes.ruleTypeLabels.keys())[self.ruleType.Selection]

	def getSummary(self):
		if not self.context:
			return "nope"
		data = self.getRule().copy()
		for panel in list(self.Parent.Parent.catIdToInstanceMap.values()):
			panel.updateData(data)
		return getSummary(data)

	def refreshSummary(self):
		self.summaryText.Value = self.getSummary()

	def onPanelActivated(self):
		self.refreshSummary()
		super(GeneralPanel, self).onPanelActivated()

	def onPanelDeactivated(self):
		super(GeneralPanel, self).onPanelDeactivated()
		self.updateData()

	def isValid(self):
		# Type is required
		if not self.ruleType.Selection >= 0:
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
		if not self.ruleName.Value.strip():
			gui.messageBox(
				# Translators: Error message when no name is entered before saving the rule
				message=_("You must choose a name for this rule"),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.ruleName.SetFocus()
			return False

		mgr = self.getRuleManager()
		layerName = self.context["rule"].layer if "rule" in self.context else None
		webModule = webModuleHandler.getEditableWebModule(mgr.webModule, layerName=layerName)
		if not webModule:
			return False
		if layerName == "addon":
			if not webModule.getLayer("addon") and webModule.getLayer("scratchpad"):
				layerName = "scratchpad"
		elif layerName is None:
			layerName = webModule._getWritableLayer().name
		if layerName is None:
			layerName = False
		try:
			rule = mgr.getRule(self.ruleName.Value, layer=layerName)
		except LookupError:
			rule = None
		if rule is not None:
			moduleRules = self.getRuleManager().getRules()
			isExists = [True if i.name is rule.name else False for i in moduleRules]
			if "new" in self.context and self.context["new"]:
				if isExists:
					gui.messageBox(
						# Translators: Error message when another rule with the same name already exists
						message=_("There already is another rule with the same name."),
						caption=_("Error"),
						style=wx.ICON_ERROR | wx.OK,
						parent=self
					)
					return False
		return True

	def onSave(self):
		self.updateData()


class AlternativesPanel(TreeContextualPanel): # TODO : overrides don't work
	# Translators: The label for a category in the rule editor
	title = _("Criteria")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.isChildCriteria = False
		self.indexCriteria = None

	def makeSettings(self, settingsSizer):
		self.settingsSizer = gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		#settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		def scale(*args):
			return tuple([
				self.scaleSize(arg) if arg > 0 else arg
				for arg in args
			])

		# Translators: Label for a control in the Rule Editor
		item = wx.StaticText(self, label=_("&Alternatives"))
		gbSizer.Add(item, pos=(0, 0))
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(1, 0))
		item = self.criteriaList = wx.ListBox(self, size=scale(-1, 150))
		item.Bind(wx.EVT_LISTBOX, self.onCriteriaSelected)
		gbSizer.Add(item, pos=(2, 0), span=(6, 1), flag=wx.EXPAND)

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(8, 0))

		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Summary"))
		gbSizer.Add(item, pos=(9, 0))
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(10, 0))
		# 		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
		# 		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		# 		item.Bind(wx.EVT_TEXT_ENTER, lambda evt: self.Parent.Parent.ProcessEvent(wx.CommandEvent(
		# 			wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK
		# 		)))
		item = self.summaryText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		gbSizer.Add(item, pos=(11, 0), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(11)

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(12, 0))

		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Technical notes"))
		gbSizer.Add(item, pos=(13, 0))
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(14, 0))
		# 		item = self.commentText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE)
		# 		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(15, 0), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(15)

		gbSizer.Add((guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(2, 1))

		# Translators: New criteria button label
		item = self.newButton = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onNewCriteria)
		gbSizer.Add(item, pos=(2, 2))

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(3, 2))

		# Translators: Edit criteria button label
		item = self.editButton = wx.Button(self, label=_("&Edit..."))
		item.Bind(wx.EVT_BUTTON, self.onEditCriteria)
		gbSizer.Add(item, pos=(4, 2))

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(5, 2))

		# Translators: Delete criteria button label
		item = self.deleteButton = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteCriteria)
		gbSizer.Add(item, pos=(6, 2))

		gbSizer.AddGrowableCol(0)

	def initData(self, context, **kwargs):
		self.context = context
		for key, value in kwargs.items():
			setattr(self, key, value)
		if self.isChildCriteria:
			return
		data = context["data"]["rule"].setdefault("criteria", [])

		self.criteriaList.Clear()
		if not data:
			self.summaryText.Value = ""
			self.editButton.Disable()
			self.deleteButton.Disable()
		else:
			for criteria in data:
				self.criteriaList.Append(self.getCriteriaName(criteria))
			self.criteriaList.SetSelection(0)
			self.onCriteriaSelected(None)

	def updateData(self, data=None):
		# Nothing to update: This panel directly writes into the data map.
		pass

	@staticmethod
	def getCriteriaName(criteria):
		if criteria.get("name"):
			return criteria["name"]
		else:
			from . import criteriaEditor
			return criteriaEditor.getSummary(criteria, condensed=True).split("\n")[0]

	def getCriteriaSummary(self, criteria):
		from . import criteriaEditor
		return criteriaEditor.getSummary(criteria)

	def onNewCriteria(self, evt):
		context = self.context
		context["data"]["criteria"] = OrderedDict({
			"new": True,
			"criteriaIndex": len(context["data"]["rule"]["criteria"])
		})
		from . import criteriaEditor
		if criteriaEditor.show(context, parent=self) == wx.ID_OK:
			context["data"]["criteria"].pop("new", None)
			index = context["data"]["criteria"].pop("criteriaIndex")
			context["data"]["rule"]["criteria"].insert(index, context["data"]["criteria"])
			if self.isChildCriteria:
				self.refreshParent(self.treeParent)
				newItem = self.tree.getXChild(self.treeParent, index)
			else:
				self.refreshCriteria(index)
				self.refreshParent(self.treeNode)
				newItem = self.tree.getXChild(self.treeNode, index)
			self.tree.SelectItem(newItem)
			self.tree.SetFocusedItem(newItem)
			self.tree.SetFocus()
			return
		del context["data"]["criteria"]

	def onEditCriteria(self, evt):
		context = self.context
		index = self.indexCriteria if self.isChildCriteria else self.criteriaList.Selection
		context["data"]["criteria"] = context["data"]["rule"]["criteria"][index].copy()
		context["data"]["criteria"]["criteriaIndex"] = index
		from . import criteriaEditor
		try:
			if criteriaEditor.show(context, self) == wx.ID_OK:
				del context["data"]["rule"]["criteria"][index]
				index = context["data"]["criteria"].pop("criteriaIndex")
				context["data"]["rule"]["criteria"].insert(index, context["data"]["criteria"])
				if self.isChildCriteria:
					self.refreshParent(self.treeParent)
					newNodeToSelect = self.tree.getXChild(self.treeParent, index)
					self.tree.SelectItem(newNodeToSelect)
					self.tree.SetFocus()
				else:
					self.refreshCriteria(index)
					self.refreshParent(self.tree.GetSelection())
				return
		finally:
			del context["data"]["criteria"]

	def onDeleteCriteria(self, evt):
		context = self.context
		index = self.indexCriteria if self.isChildCriteria else self.criteriaList.Selection
		if gui.messageBox(
				# Translator: A confirmation prompt on the Rule editor
				_("Are you sure you want to delete this alternative?"),
				# Translator: The title for a confirmation prompt on the Rule editor
				_("Confirm Deletion"),
				wx.YES | wx.NO | wx.CANCEL | wx.ICON_QUESTION, self
		) == wx.YES:
			del context["data"]["rule"]["criteria"][index]
			if self.isChildCriteria:
				self.tree.SelectItem(self.treeParent)
				self.refreshParent(self.treeParent)
				newItem = self.tree.getXChild(self.treeParent, index)
			else:
				self.refreshCriteria()
				self.refreshParent(self.treeNode)
				newItem = self.tree.getXChild(self.treeNode, index)
			self.tree.SelectItem(newItem)
			self.tree.SetFocusedItem(newItem)
			self.tree.SetFocus()

	def onCriteriaSelected(self, evt):
		if not self.editButton.Enabled:
			self.editButton.Enable(enable=True)
			self.deleteButton.Enable(enable=True)
		data = self.getRule()["criteria"]
		criteria = data[self.criteriaList.Selection]
		self.summaryText.Value = self.getCriteriaSummary(criteria)
		self.commentText.Value = criteria.get("comment", "")

	@staticmethod
	def getTitle(criteria):
		return AlternativesPanel.getCriteriaName(criteria)

	def refreshCriteria(self, index=0):
		data = self.getRule()["criteria"]
		self.criteriaList.Clear()
		for criteria in data:
			self.criteriaList.Append(self.getCriteriaName(criteria))
		if data:
			self.criteriaList.Selection = index
		self.onCriteriaSelected(None)

	def onSave(self):
		# Nothing to save: This panel directly writes into data
		pass


class ActionsPanel(TreeContextualPanel):
	# Translators: The label for a category in the rule editor
	title = _("Actions")

	def makeSettings(self, settingsSizer):
		gbSizer = self.sizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		def scale(*args):
			return tuple([
				self.scaleSize(arg) if arg > 0 else arg
				for arg in args
			])

		row = 0
		# Translators: Displayed when the selected rule type doesn't support any action
		item = self.noActionsLabel = wx.StaticText(self, label=_("No action available for the selected rule type."))
		item.Hide()
		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

		row += 1
		# Translators: Keyboard shortcut input label for the rule dialog's action panel.
		item = wx.StaticText(self, label=_("&Gestures"))
		gbSizer.Add(item, pos=(row, 0), flag=wx.EXPAND)
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row + 1, 0))
		innerGbSizer = wx.GridBagSizer()
		item = self.gesturesList = wx.ListBox(self, size=scale(-1, 100))
		innerGbSizer.Add(item, pos=(0, 0), span=(4, 1), flag=wx.EXPAND)
		innerGbSizer.Add(scale(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(0, 1))
		# Translators: The label for a button in the Rule Editor dialog
		item = wx.Button(self, label=_("&Add"))
		item.Bind(wx.EVT_BUTTON, self.onAddGesture)
		innerGbSizer.Add(item, pos=(0, 2), flag=wx.EXPAND)
		innerGbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL), pos=(1, 2))
		# Translators: The label for a button in the Rule Editor dialog
		item = self.deleteButton = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
		innerGbSizer.Add(item, pos=(2, 2), flag=wx.EXPAND)
		innerGbSizer.AddGrowableCol(0)
		innerGbSizer.AddGrowableRow(3)
		gbSizer.Add(innerGbSizer, pos=(row + 2, 0), span=(1, 3), flag=wx.EXPAND)
		row += 2

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translators: Automatic action at rule detection input label for the rule dialog's action panel.
		self.labelAutoactions = wx.StaticText(self, label=_("A&utomatic action at rule detection:"))
		gbSizer.Add(self.labelAutoactions, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		self.autoActionList = wx.ComboBox(self, style=wx.CB_READONLY)
		gbSizer.Add(self.autoActionList, pos=(row, 2), flag=wx.EXPAND)

		gbSizer.AddGrowableCol(2)

	def initData(self, context, **kwargs):
		super().initData(context, **kwargs)
		data = self.getRule()
		mgr = self.getRuleManager()
		actionsDict = mgr.getActions()
		self.autoActionList.Clear()
		# Translators: No action choice
		self.autoActionList.Append(pgettext("webAccess.action", "No action"), "")
		for action in actionsDict:
			self.autoActionList.Append(actionsDict[action], action)

		if not data:
			self.gestureMapValue = {}
			self.autoActionList.SetSelection(0)
		else:
			self.gestureMapValue = data.get("gestures", {}).copy()
			index = 0
			if (
					"autoAction" in data.get("properties", {})
					and data["properties"]["autoAction"] in actionsDict
			):
				index = list(mgr.getActions().keys()).index(data["properties"]["autoAction"]) + 1
			self.autoActionList.SetSelection(index)
		self.updateGesturesList()

	def updateData(self, data=None):
		self.initData(self.context)

	def onAddGesture(self, evt):
		from ..gui import shortcutDialog
		mgr = self.getRuleManager()
		shortcutDialog.ruleManager = mgr
		if shortcutDialog.show():
			self.gestureMapValue[shortcutDialog.resultShortcut] = shortcutDialog.resultActionData
			self.onSave()
			self.refreshParent(self.treeNode)

	def onDeleteGesture(self, evt):
		gestureIdentifier = self.gesturesList.GetClientData(self.gesturesList.Selection)
		del self.gestureMapValue[gestureIdentifier]
		self.updateGesturesList(focus=True)
		self.onSave()

	def updateGesturesList(self, newGestureIdentifier=None, focus=False):
		mgr = self.getRuleManager()
		self.gesturesList.Clear()
		i = 0
		sel = 0
		for gestureIdentifier in self.gestureMapValue:
			gestureSource, gestureMain = inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)
			actionStr = mgr.getActions()[self.gestureMapValue[gestureIdentifier]]
			self.gesturesList.Append("%s = %s" % (gestureMain, actionStr), gestureIdentifier)
			if gestureIdentifier == newGestureIdentifier:
				sel = i
			i += 1
		if len(self.gestureMapValue) > 0:
			self.gesturesList.SetSelection(sel)

		if self.gesturesList.Selection < 0:
			self.deleteButton.Enabled = False
		else:
			self.deleteButton.Enabled = True

		if focus:
			self.gesturesList.SetFocus()

	def onPanelActivated(self):
		data = self.getRule() if hasattr(self, "context") else {}
		ruleType = data.get("type")
		show = ruleType in (ruleTypes.ZONE, ruleTypes.MARKER)
		self.sizer.ShowItems(show)
		self.noActionsLabel.Show(not show)

		super(ActionsPanel, self).onPanelActivated()

	def onSave(self):
		data = self.getRule()
		ruleType = data.get("type")
		if ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
			data["gestures"] = self.gestureMapValue
			autoAction = self.autoActionList.GetClientData(self.autoActionList.Selection)
		# updateOrDrop(data["properties"], "autoAction", autoAction)
		else:
			if data.get("gestures"):
				del data["gestures"]
			if data.get("properties", {}).get("autoAction"):
				del data["autoAction"]


class PropertiesPanel(TreeContextualPanel, properties.ListControl):
	# Translators: The label for a category in the rule editor
	title = _("Properties")
	PROPERTIES_KEY_NAME = "properties"
	propertiesList = []
	objListCtrl = None
	context = None
	tempList = []

	@staticmethod
	def getPropertyTitle(propertyName, value, type):
		propertyVerbose = properties.ListControl.getAltFieldLabel(type, propertyName, properties.FIELDS.get(propertyName, ''))
		return ChildOneInputPanel.getChildTitle(propertyVerbose, value)

	def makeSettings(self, settingsSizer):
		properties.ListControl.makeSettings(self, settingsSizer)

	def initData(self, context, **kwargs):
		TreeContextualPanel.initData(self, context, **kwargs)
		properties.ListControl.initData(self, context, **kwargs)
		self.context = context
		self.initPropertiesList(context)
		self.tempList = self.propertiesList
		self.updateData()

	def onInitUpdateListCtrl(self):
		super(PropertiesPanel, self).onInitUpdateListCtrl()

	def onInitUpdateListCtrl(self):
		super(PropertiesPanel, self).onInitUpdateListCtrl()

	def initPropertiesList(self, context):
		super(PropertiesPanel, self).initPropertiesList(self.context)
		index = self.listCtrl.GetFirstSelected()
		vnew = self.context.get("new")
		dataRule = self.getRule()
		ruleProps = dataRule.get("properties")
		if ruleProps:
			data = dataRule["properties"]
			self.updateListCtrl(data)
		if vnew:
			[p.set_flag(True) for p in self.propertiesList]
		self.onInitUpdateListCtrl()
		self.focusListCtrl(index=index)

	def updateListCtrl(self, data):
		super(PropertiesPanel, self).updateListCtrl(data)

	def updateData(self, data=None):
		propertiesMapValue = {}
		data = self.getRule()
		ruleType = data.get("type")
		if ruleType is not None and self.propertiesList:
			for props in self.propertiesList:
				propertiesMapValue[props.get_id()] = props.get_value()
			if data.get(self.PROPERTIES_KEY_NAME):
				del data[self.PROPERTIES_KEY_NAME]
			data[self.PROPERTIES_KEY_NAME] = propertiesMapValue
		self.propertiesList = self.tempList

	def onPanelActivated(self):
		super(PropertiesPanel, self).onPanelActivated()
		self.initPropertiesList(self.context)
		self.updateData()
		self.showItems(self.getRule())

	def onPanelDeactivated(self):
		self.updateData()
		self.refreshParent(self.treeNode, deleteChildren=False)
		super().onPanelDeactivated()

	def onSave(self):
		self.updateData()


class ChildOneInputPanel(TreeContextualPanel):
	def __init__(self, *args, **kwargs):
		self.editor = None
		self.editorClass = None
		self.editorParams = None
		self.fieldName = None
		self.treeNode = None
		self.treeParent = None
		self.tree = None
		super().__init__(*args, **kwargs)

	def makeSettings(self, sizer):
		gbSizer = wx.GridBagSizer()
		sizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		self.header = wx.StaticText(self, label='')
		gbSizer.Add(self.header, pos=(0, 0))
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(1, 0))
		self.gbSizer = gbSizer

	@staticmethod
	def getChildTitle(propName, value):
		if isinstance(value, bool):
			value = 'Activée' if value else 'Désactivée'
		elif not value:
			value = 'Vide'
		return f'{propName.capitalize()} : {value}'

	def initData(self, context, **kwargs):
		super().initData(context, **kwargs)
		if kwargs.get('hideLabel', False):
			self.header.Hide()
		if not self.editor:
			self.editor = self.editorClass(self, **self.editorParams)
			self.gbSizer.Add(self.editor, pos=(2, 0))
			self.editor.Bind(wx.EVT_KILL_FOCUS, self.onFieldChange)

		self.header.SetLabel(self.title)
		self.setEditorValue()

	def setEditorValue(self):
		value = self.getValue()
		if not value:
			return
		if self.editorIsChoice():
			self.editor.SetSelection(self.editor.FindString(value) if value else 0)
		else:
			self.editor.SetValue(value)

	def getValue(self):
		return self.getRule().get(self.fieldName)

	def onFieldChange(self, evt):
		self.updateData(self.getRule())

	def editorIsChoice(self):
		return isinstance(self.editor, wx.Choice) or isinstance(self.editor, wx.ComboBox)

	def updateData(self, data):
		updateOrDrop(data, self.fieldName, self.editor.Value)
		self.refreshParent(self.treeNode)

	def onPanelDeactivated(self):
		self.updateData(self.getRule())
		super().onPanelDeactivated()

	def onSave(self):
		self.updateData(self.getRule())


class CheckboxPanel(ChildOneInputPanel):
	def __init__(self, context, choices, defaultValue, **kwargs):
		self.choices = choices
		super().__init__(context, editorClass=wx.ComboBox, editorParams={'choices': choices}, **kwargs)


class ChildGeneralPanel(ChildOneInputPanel):
	TYPE_FIELD = "type"

	def initData(self, context, **kwargs):
		super().initData(context, **kwargs)
		if self.fieldName == self.TYPE_FIELD:
			self.editor.Bind(wx.EVT_CHOICE, self.onTypeChange)
			GeneralPanel.initRuleTypeChoice(self.getRule(), self.editor)

	def onTypeChange(self, evt):
		data = self.getRule()
		data["type"] = tuple(ruleTypes.ruleTypeLabels.keys())[self.editor.Selection]
		self.refreshSummary()
		for i in [2, 3]:
			category = self.tree.getXChild(self.tree.GetRootItem(), i)
			self.refreshParent(category)

	@staticmethod
	def getChildTitle(propName, value):
		if propName == ChildGeneralPanel.TYPE_FIELD:
			typeValue = ruleTypes.ruleTypeLabels[value] if isinstance(value, str) else \
				list(ruleTypes.ruleTypeLabels.values())[value]
			return ChildOneInputPanel.getChildTitle(propName, typeValue)
		return ChildOneInputPanel.getChildTitle(propName, value.capitalize())

	def updateData(self, data):
		if self.fieldName == self.TYPE_FIELD:
			updateOrDrop(data, self.fieldName, tuple(ruleTypes.ruleTypeLabels.keys())[self.editor.Selection])
			self.tree.SetItemText(self.treeNode, self.getChildTitle(self.fieldName, self.editor.Selection))
		else:
			updateOrDrop(data, self.fieldName, self.editor.Value)
			self.tree.SetItemText(self.treeNode, self.getChildTitle(self.fieldName, self.editor.Value))

	def refreshSummary(self):
		data = self.getRule().copy()
		for panel in list(self.Parent.Parent.catIdToInstanceMap.values()):
			panel.updateData(data)

	def delete(self):
		ui.message(_("You can't delete a child of the general branch."))


class ChildAlternativePanel(AlternativesPanel):
	def makeSettings(self, settingsSizer):
		self.settingsSizer = gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)

		# settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		def scale(*args):
			return tuple([
				self.scaleSize(arg) if arg > 0 else arg
				for arg in args
			])

		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Summary"))
		row = 0
		gbSizer.Add(item, pos=(row, 0))
		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		# 		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
		# 		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		# 		item.Bind(wx.EVT_TEXT_ENTER, lambda evt: self.Parent.Parent.ProcessEvent(wx.CommandEvent(
		# 			wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK
		# 		)))
		row += 1
		item = self.summaryText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 0), span=(6, 1), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)
		row += 6

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		row += 1
		# Translators: The label for a field on the Rule editor
		item = wx.StaticText(self, label=_("Technical notes"))
		gbSizer.Add(item, pos=(row, 0))
		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		# 		item = self.commentText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE)
		# 		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		row += 1
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 0), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		gbSizer.Add((guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(2, 1))

		# Translators: New criteria button label
		item = self.newButton = wx.Button(self, label=_("&New..."))
		item.Bind(wx.EVT_BUTTON, self.onNewCriteria)
		gbSizer.Add(item, pos=(2, 2))

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(3, 2))

		# Translators: Edit criteria button label
		item = self.editButton = wx.Button(self, label=_("&Edit..."))
		item.Bind(wx.EVT_BUTTON, self.onEditCriteria)
		gbSizer.Add(item, pos=(4, 2))

		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(5, 2))

		# Translators: Delete criteria button label
		item = self.deleteButton = wx.Button(self, label=_("&Delete"))
		item.Bind(wx.EVT_BUTTON, self.onDeleteCriteria)
		gbSizer.Add(item, pos=(6, 2))

		gbSizer.AddGrowableCol(0)

	def initData(self, context, **kwargs):
		super().initData(context, **kwargs)
		self.isChildCriteria = kwargs.get('isChildCriteria', False)
		self.indexCriteria = self.tree.getSelectionIndex()
		criteria = context['data']["rule"]['criteria'][self.indexCriteria]
		self.summaryText.Value = self.getCriteriaSummary(criteria)
		self.commentText.Value = criteria.get("comment", "")

	def delete(self):
		self.onDeleteCriteria(None)


class ChildActionPanel(TreeContextualPanel):
	def initData(self, context, **kwargs):
		super().initData(context, **kwargs)
		self.textCtrl.Value = self.title

	def makeSettings(self, sizer):
		gbSizer = wx.GridBagSizer()
		sizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		item = wx.Button(self, label='Modifier')
		item.Bind(wx.EVT_BUTTON, self.onEditGesture)
		gbSizer.Add(item, pos=(0, 0))
		item = wx.Button(self, label='Supprimer')
		gbSizer.Add(item, pos=(0, 1))
		item.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
		item = wx.Button(self, label='Ajouter')
		gbSizer.Add(item, pos=(0, 2))
		item.Bind(wx.EVT_BUTTON, self.onAddGesture)
		gbSizer.Add((150, 0), pos=(0, 3), flag=wx.EXPAND)
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL, 0), pos=(1, 0))
		self.textCtrl = wx.TextCtrl(self, value=self.title, size=(-1, 100))
		gbSizer.Add(self.textCtrl, pos=(2, 0), span=(1, 3), flag=wx.EXPAND)

	def updateTreeAndSelectItemAtIndex(self, index):
		self.refreshParent(self.treeParent)
		self.tree.SelectItem(self.tree.getXChild(self.treeParent, index))
		self.tree.SetFocus()

	def onAddGesture(self, evt):
		from ..gui import shortcutDialog
		shortcutDialog.ruleManager = self.getRuleManager()
		if shortcutDialog.show():
			data = self.getRule()
			gestures = data.get('gestures', {})
			gestures[shortcutDialog.resultShortcut] = shortcutDialog.resultActionData
			self.updateTreeAndSelectItemAtIndex(index=len(gestures) - 1)

	def onEditGesture(self, evt):
		from ..gui import shortcutDialog
		mgr = self.getRuleManager()
		shortcutDialog.ruleManager = mgr
		data = self.getRule()
		gestures = data.get('gestures', {})
		ruleType = data.get("type")
		if not ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
			return
		if shortcutDialog.show():
			del gestures[self.actionControl]
			self.actionControl = shortcutDialog.resultShortcut
			gestures[shortcutDialog.resultShortcut] = shortcutDialog.resultActionData
			title = self.getTitle(shortcutDialog.resultShortcut, shortcutDialog.resultActionData, mgr)
			self.textCtrl.Value = title
			self.tree.updateNodeText(self.treeNode, title)
			index = list(gestures.keys()).index(shortcutDialog.resultShortcut)
			self.updateTreeAndSelectItemAtIndex(index)

	def onDeleteGesture(self, evt):
		data = self.getRule()
		gestures = data.get('gestures', {})
		del gestures[self.actionControl]
		self.tree.deleteSelection()
		self.tree.selectLast(self.treeParent)

	def delete(self):
		self.onDeleteGesture(None)

	def onSave(self):
		pass

	def updateData(self, data):
		pass

	@staticmethod
	def getTitle(key, action, mgr):
		return f"{key} : {mgr.getActions()[action]}"


class ChildPropertyPanel(ChildOneInputPanel):

	def setEditorValue(self):
		if self.editorIsChoice():
			mgr = self.getRuleManager()
			value = self.getPropertiesHolder(self.context).get(self.fieldName)
			try:
				index = properties.ListControl.getIndexOfCurrentChoice(self.fieldName, mgr,
																  value) + 1  # +1 to take into account the default value
			except ValueError:
				index = 0
			self.editor.SetSelection(index)
		else:
			super().setEditorValue()

	def getValue(self):
		return self.getPropertiesHolder(self.context).get(self.fieldName)

	def updateData(self, data):
		value = self.editor.Value
		if self.editorIsChoice():
			mgr = self.getRuleManager()
			selection = self.editor.GetSelection()
			value = properties.ListControl.getValueAtIndex(self.fieldName, mgr,
													  selection - 1) if selection != 0 else ''  # -1 to remove the default value
		updateOrDrop(self.getPropertiesHolder(self.context), self.fieldName, value)
		displayableValue = properties.ListControl.getChoicesDisplayableValue(self.context, self.fieldName, value)
		title = PropertiesPanel.getPropertyTitle(self.fieldName, displayableValue, data.get('type', ''))
		self.tree.SetItemText(self.treeNode, title)
		propertyPanel = self.Parent.Parent.catIdToInstanceMap.get(PropertiesPanel.title)
		if propertyPanel:
			for property in propertyPanel.propertiesList:
				if self.fieldName == property.get_id():
					property.set_value(value)

	def delete(self):
		ui.message("You can't delete a child of the property branch.")

	@staticmethod
	def getPropertiesHolder(context):
		rule = context['data']['rule']
		return rule[PropertiesPanel.PROPERTIES_KEY_NAME] if PropertiesPanel.PROPERTIES_KEY_NAME in rule else rule

	@staticmethod
	def getPropertyValue(context, fieldName, editorClass):
		defaultValue = False if editorClass == wx.CheckBox else ''
		value = ChildPropertyPanel.getPropertiesHolder(context).get(fieldName, defaultValue)
		return properties.ListControl.getChoicesDisplayableValue(context, fieldName, value)


class RuleEditorDialog(TreeMultiCategorySettingsDialog):
	# Translators: The title of the rule editor
	title = _("WebAccess Rule editor")
	INITIAL_SIZE = (750, 520)
	categoryInitList = [
		(GeneralPanel, 'getGeneralChildren'),
		(AlternativesPanel, 'getAlternativeChildren'),
		(ActionsPanel, 'getActionsChildren'),
		(PropertiesPanel, 'getPropertiesChildren'),
	]
	categoryClasses = [
		GeneralPanel,
		AlternativesPanel,
		ActionsPanel,
		PropertiesPanel,
	]
	INITIAL_SIZE = (750, 520)

	def __init__(self, *args, **kwargs):
		# Uncomment the below to focus the first field upon dialog appearance
		# kwargs["initialCategory"] = GeneralPanel
		super(RuleEditorDialog, self).__init__(*args, **kwargs)
		self.isCreation = False

	# from . import criteriaEditor
	# self.categoryClasses.append(criteriaEditor.CriteriaPanel_)

	def getGeneralChildren(self):
		ruleData = self.context['data']['rule']
		nodes = []
		if self.isCreation:
			return []
		for fieldName in ['name', 'type']:
			if fieldName not in ruleData:
				continue
			title = ChildGeneralPanel.getChildTitle(fieldName, ruleData.get(fieldName, ""))
			node = TreeNodeInfo(ChildGeneralPanel, title=title)
			if fieldName == 'name':
				node.categoryParams = {
					'title': title,
					'fieldName': fieldName,
					'editorClass': wx.TextCtrl,
					'editorParams': {
						'value': ruleData[fieldName],
						'size': (300, -1)
					},
				}
			elif fieldName == ChildGeneralPanel.TYPE_FIELD:
				title = ChildGeneralPanel.getChildTitle(fieldName, ruleData.get(fieldName, ""))
				node.categoryParams = {
					'title': title,
					'fieldName': fieldName,
					'editorClass': wx.Choice,
					'editorParams': {
						'choices': list(ruleTypes.ruleTypeLabels.values())
					},
				}
			nodes.append(node)
		return nodes

	def getAlternativeChildren(self):
		ruleData = self.context['data']['rule']
		criteriaPanels = []
		for criterion in ruleData.get('criteria', []):
			title = ChildAlternativePanel.getTitle(criterion)
			criteriaPanels.append(
				TreeNodeInfo(ChildAlternativePanel, title=title, categoryParams={'isChildCriteria': True}))
		return criteriaPanels

	def getActionsChildren(self):
		ruleData = self.context['data']['rule']
		type = ruleData.get('type', '')
		if type not in [ruleTypes.ZONE, ruleTypes.MARKER]:
			return []
		mgr = self.context["webModule"].ruleManager
		actionsPanel = []
		for key, value in ruleData.get('gestures', {}).items():
			title = ChildActionPanel.getTitle(key, value, mgr)
			categoryParams = {
				'title': title,
				'actionControl': key
			}
			actionsPanel.append(TreeNodeInfo(ChildActionPanel, title=title, categoryParams=categoryParams))
		return actionsPanel

	def getPropertiesChildren(self):
		propertiesPanel = []
		ruleData = self.context['data']['rule']
		type = ruleData[ChildGeneralPanel.TYPE_FIELD] if ruleData else list(ruleTypes.ruleTypeLabels.keys())[0]
		fields = RULE_TYPE_FIELDS.get(type, '')
		for field in fields:
			editorClass = FIELDS_WIDGET_MAP[field]
			editorParams = {}
			value = ChildPropertyPanel.getPropertyValue(self.context, field, editorClass)
			title = PropertiesPanel.getPropertyTitle(field, value, type)
			node = TreeNodeInfo(ChildPropertyPanel, title=title)
			label = title.split(':')[0]
			hideLabel = False
			if editorClass == wx.CheckBox:
				editorParams = {'label': label}
				hideLabel = True
			elif editorClass == wx.TextCtrl:
				editorParams = {'size': (350, -1)}
			elif editorClass == wx.ComboBox:
				mgr = self.context["webModule"].ruleManager
				choices = list(map(lambda x: x[0], properties.ListControl.getChoiceOptionForField(field, mgr)))
				editorParams = {'style': wx.CB_READONLY, 'choices': choices}
			node.categoryParams = {
				'fieldName': field,
				'editorClass': editorClass,
				'editorParams': editorParams,
				'hideLabel': hideLabel
			}
			propertiesPanel.append(node)
		return propertiesPanel

	def initData(self, context):
		rule = context.get("rule")
		data = context.setdefault("data", {}).setdefault(
			"rule",
			rule.dump() if rule else OrderedDict()
		)
		mgr = context["webModule"].ruleManager if "webModule" in context else None
		if not rule and mgr and mgr.nodeManager:
			node = mgr.nodeManager.getCaretNode()
			while node is not None:
				if node.role in formModeRoles:
					dataProps = data.get("properties")
					if dataProps:
						dataProps["properties"]["formMode"] = False
					break
				node = node.parent
		super(RuleEditorDialog, self).initData(context)

	def _doCategoryChange__(self, newCatId):
		if (
				hasattr(self, "context")
				and newCatId == self.categoryClasses.index(AlternativesPanel)
		):
			context = self.context
			lst = context["data"]["rule"].setdefault("criteria", [{"new": True}])
			if len(lst) < 2:
				from . import criteriaEditor
				newCatId = self.categoryClasses.index(criteriaEditor.CriteriaPanel_)
				context["data"]["criteria"] = lst[0]

		super(RuleEditorDialog, self)._doCategoryChange(newCatId)

	def _doSave(self):
		super(RuleEditorDialog, self)._doSave()
		try:
			context = self.context
			mgr = context["webModule"].ruleManager
			data = context["data"]["rule"]
			rule = context.get("rule")
			layerName = rule.layer if rule is not None else None
			webModule = webModuleHandler.getEditableWebModule(mgr.webModule, layerName=layerName)
			if not webModule:
				return
			if rule is not None:
				# modification mode, remove old rule
				mgr.removeRule(rule)
			if layerName == "addon":
				if not webModule.getLayer("addon") and webModule.getLayer("scratchpad"):
					layerName = "scratchpad"
			elif layerName is None:
				layerName = webModule._getWritableLayer().name

			rule = webModule.createRule(data)
			mgr.loadRule(layerName, rule.name, data)
			webModule.getLayer(layerName, raiseIfMissing=True).dirty = True
			if not webModuleHandler.save(webModule, layerName=layerName):
				return
		except Exception:
			log.exception()
			gui.messageBox(
				message=_("An error occured. Please see NVDA log for more details."),
				caption=_("WebAccess"),
				style=wx.ICON_ERROR
			)
			raise


def show(context, parent=None):
	from . import showContextualDialog
	return showContextualDialog(RuleEditorDialog, context, parent)
