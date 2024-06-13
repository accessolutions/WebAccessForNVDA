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



__version__ = "2024.06.13"
__author__ = "Shirley Noël <shirley.noel@pole-emploi.fr>"


from collections import OrderedDict, namedtuple
import wx
# TODO: Work-arround ExpandoTextCtrl mishandling maxHeight and vscroll
# from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import addonHandler
import controlTypes
import gui
import inputCore
from logHandler import log

from .. import ruleHandler
from ..ruleHandler import ruleTypes
from ..ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
from ..utils import updateOrDrop
from .. import webModuleHandler
from . import (
	ContextualMultiCategorySettingsDialog,
	ContextualSettingsPanel,
	guiHelper,
	stripAccel,
	stripAccelAndColon
)
from ..gui import properties as props
instanceListProperties = props.ListProperties()
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
	criteriaSets = data.get("criteria", [])
	if criteriaSets:
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
				parts.append("  {}".format(altHeader))
				parts.append(getCriteriaSummary(alternative, condensed=True, indent="    "))
	# Properties
	subParts = []
	data = data.get("properties")
	if data:
		for key, label in list(props.FIELDS.items()):
			if key not in props.RULE_TYPE_FIELDS.get(ruleType, []):
				continue
			if key == "sayName":
				value = data.get(key, True)
			elif key not in data:
				continue
			else:
				value = data[key]
			label = props.ListControl.getAltFieldLabel(ruleType, key, label)
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

	return "\n".join(parts)


class GeneralPanel(ContextualSettingsPanel):
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

	def initData(self, context):
		self.context = context
		rule = context.get("rule")
		data = context["data"]["rule"]

		if rule:
			for index, key in enumerate(ruleTypes.ruleTypeLabels.keys()):
				if key == data["type"]:
					self.ruleType.SetSelection(index)
					break
		else:
			self.ruleType.SetSelection(0)

		self.ruleName.Value = data.get("name", "")
		self.commentText.Value = data.get("comment", "")
		self.onTypeChange(None)
		self.refreshSummary()

	def updateData(self, data=None):
		if data is None:
			data = self.context["data"]["rule"]
		# The rule type should already be stored as of onTypeChange
		data["name"] = self.ruleName.Value
		updateOrDrop(data, "comment", self.commentText.Value)

	def onTypeChange(self, evt):
		data = self.context["data"]["rule"]
		data["type"] = tuple(ruleTypes.ruleTypeLabels.keys())[self.ruleType.Selection]
		self.refreshSummary()

	def getSummary(self):
		if not self.context:
			return "nope"
		data = self.context["data"]["rule"].copy()
		for panel in list(self.Parent.Parent.catIdToInstanceMap.values()):
			panel.updateData(data)
		return getSummary(data)

	def refreshSummary(self):
		self.summaryText.Value = self.getSummary()

	def onPanelActivated(self):
		self.refreshSummary()
		super(GeneralPanel, self).onPanelActivated()

	def onPanelDeactivated(self):
		self.updateData()
		super(GeneralPanel, self).onPanelDeactivated()

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

		candidate = self.ruleName.Value
		mgr = self.context["webModule"].ruleManager
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
			moduleRules = self.context["webModule"].ruleManager.getRules()
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


class AlternativesPanel(ContextualSettingsPanel):
	# Translators: The label for a category in the rule editor
	title = _("Criteria")

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

	def initData(self, context):
		self.context = context
		data = context["data"]["rule"].setdefault("criteria", [])

		if not data:
			self.criteriaList.Clear()
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

	def getCriteriaName(self, criteria):
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
			self.refreshCriteria(index)
			return
		del context["data"]["criteria"]

	def onEditCriteria(self, evt):
		context = self.context
		index = self.criteriaList.Selection
		context["data"]["criteria"] = context["data"]["rule"]["criteria"][index].copy()
		context["data"]["criteria"]["criteriaIndex"] = index
		from . import criteriaEditor
		try:
			if criteriaEditor.show(context, self) == wx.ID_OK:
				del context["data"]["rule"]["criteria"][index]
				index = context["data"]["criteria"].pop("criteriaIndex")
				context["data"]["rule"]["criteria"].insert(index, context["data"]["criteria"])
				self.refreshCriteria(index)
				return
		finally:
			del context["data"]["criteria"]

	def onDeleteCriteria(self, evt):
		context = self.context
		index = self.criteriaList.Selection
		if gui.messageBox(
			# Translator: A confirmation prompt on the Rule editor
			_("Are you sure you want to delete this alternative?"),
			# Translator: The title for a confirmation prompt on the Rule editor
			_("Confirm Deletion"),
			wx.YES | wx.NO | wx.CANCEL | wx.ICON_QUESTION, self
		) == wx.YES:
			del context["data"]["rule"]["criteria"][index]
			self.refreshCriteria()

	def onCriteriaSelected(self, evt):
		if not self.editButton.Enabled:
			self.editButton.Enable(enable=True)
			self.deleteButton.Enable(enable=True)
		data = self.context["data"]["rule"]["criteria"]
		criteria = data[self.criteriaList.Selection]
		self.summaryText.Value = self.getCriteriaSummary(criteria)
		self.commentText.Value = criteria.get("comment", "")

	def refreshCriteria(self, index=0):
		data = self.context["data"]["rule"]["criteria"]
		self.criteriaList.Clear()
		for criteria in data:
			self.criteriaList.Append(self.getCriteriaName(criteria))
		if data:
			self.criteriaList.Selection = index
		self.onCriteriaSelected(None)

	def onSave(self):
		# Nothing to save: This panel directly writes into data
		pass


class ActionsPanel(ContextualSettingsPanel):
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

	def initData(self, context):
		self.context = context
		rule = context.get("rule")
		data = context["data"]["rule"]
		mgr = context["webModule"].ruleManager

		actionsDict = mgr.getActions()
		self.autoActionList.Clear()
		# Translators: No action choice
		self.autoActionList.Append(pgettext("webAccess.action", "No action"), "")
		for action in actionsDict:
			self.autoActionList.Append(actionsDict[action], action)

		if not rule:
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
		pass # @@@

	def onAddGesture(self, evt):
		from ..gui import shortcutDialog
		mgr = self.context["webModule"].ruleManager
		shortcutDialog.ruleManager = mgr
		if shortcutDialog.show():
			self.gestureMapValue[shortcutDialog.resultShortcut] = shortcutDialog.resultActionData
			self.updateGesturesList(
				newGestureIdentifier=shortcutDialog.resultShortcut,
				focus=True
			)

	def onDeleteGesture(self, evt):
		gestureIdentifier = self.gesturesList.GetClientData(self.gesturesList.Selection)
		del self.gestureMapValue[gestureIdentifier]
		self.updateGesturesList(focus=True)

	def updateGesturesList(self, newGestureIdentifier=None, focus=False):
		mgr = self.context["webModule"].ruleManager
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
		data = self.context["data"]["rule"] if hasattr(self, "context") else {}
		ruleType = data.get("type")
		show = ruleType in (ruleTypes.ZONE, ruleTypes.MARKER)
		self.sizer.ShowItems(show)
		self.noActionsLabel.Show(not show)

		super(ActionsPanel, self).onPanelActivated()

	def onSave(self):
		data = self.context["data"]["rule"]
		ruleType = data.get("type")
		if ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
			data["gestures"] = self.gestureMapValue
			autoAction = self.autoActionList.GetClientData(self.autoActionList.Selection)
			#updateOrDrop(data["properties"], "autoAction", autoAction)
		else:
			if data.get("gestures"):
				del data["gestures"]
			if data.get("properties", {}).get("autoAction"):
				del data["autoAction"]


class PropertiesPanel(ContextualSettingsPanel):


	# Translators: The label for a category in the rule editor
	title = _("Properties")
	propertiesList = []
	objListCtrl = None
	context = None
	hidable = []

	def makeSettings(self, settingsSizer):

		self. hidable = []

		gbSizer = self.sizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		sizer = wx.GridBagSizer(hgap=5, vgap=5)
		row = 0
		# Translators: Displayed when the selected rule type doesn't support any action
		self.noPropertiesLabel = wx.StaticText(self, label=_("No properties available for the selected rule type."))
		sizer.Add(self.noPropertiesLabel, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

		row +=1
		# Translators: Keyboard shortcut input label for the rule dialog's action panel.
		self.propertiesLabel = wx.StaticText(self, label=_("&Properties List"))
		sizer.Add(self.propertiesLabel, pos=(row, 0), flag=wx.EXPAND)
		self.hidable.append(self.propertiesLabel)

		self.listCtrl = wx.ListCtrl(self, size=(650, 300), style=wx.LC_REPORT | wx.BORDER_SUNKEN)
		self.listCtrl.InsertColumn(0, 'Properties', width=322)
		self.listCtrl.InsertColumn(1, 'Value', width=322)
		self.hidable.append(self.listCtrl)
		row += 1

		self.editable = wx.TextCtrl(self, size=(650 , 30))
		self.hidable.append(self.editable)

		self.toggleBtn = wx.ToggleButton(self, label="", size=(325,30))
		self.hidable.append(self.toggleBtn)

		self.choice = wx.Choice(self, choices=[], size=(325, 30))
		self.hidable.append(self.choice)

		sizer = wx.GridBagSizer(hgap=5, vgap=5)
		sizer.Add(self.listCtrl, pos=(1, 0), flag=wx.EXPAND)

		sizeEdit = wx.BoxSizer(wx.HORIZONTAL)
		sizeEdit.Add(self.editable)
		sizer.Add(sizeEdit, pos=(2, 0), span=(0, 1), flag=wx.EXPAND)

		sizeBox = wx.BoxSizer(wx.HORIZONTAL)
		sizeBox.Add(self.toggleBtn)
		sizeBox.Add(self.choice, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL)
		sizer.Add(sizeBox, pos=(3, 0), flag=wx.EXPAND)
		self.SetSizer(sizer)

	def initData(self, context):
		self.context = context
		self.updateData()
		self.initPropertiesList()

	def loadPropsRulePanel(self):
		from ..gui import properties as p
		objListCtrl =p.ListControl(self)
		return objListCtrl

	def initPropertiesList(self):
		index=self.listCtrl.GetFirstSelected()
		instanceListProperties.setPropertiesByRuleType(self.context)
		self.propertiesList = instanceListProperties.getPropertiesByRuleType()
		self.updateListCtrl(self.context["data"]["rule"])
		self.loadPropsRulePanel().focusListCtrl(index)

	def updateListCtrl(self, dataRule):
		self.showItems(dataRule)
		ruleProps = dataRule.get("properties")
		if ruleProps:
			data = dataRule["properties"]
			for props in self.propertiesList:
				for key, value in data.items():
					if props.get_id() == key:
						props.set_flag(True)
						props.set_value(value)
		self.loadPropsRulePanel().onInitUpdateListCtrl()

	def updateData(self, data = None):
		propertiesMapValue = {}
		data = self.context["data"]["rule"]
		ruleType = data.get("type")
		if ruleType is not None and self.propertiesList:
			for props in self.propertiesList:
				propertiesMapValue[props.get_id()] = props.get_value()
			if data.get("properties"):
				del data["properties"]
			data["properties"] = propertiesMapValue
		self.propertiesList.clear()


	def showItems(self, data):
		ruleType = data.get("type")
		typeValues = props.RULE_TYPE_FIELDS.get(ruleType)
		if typeValues is None:
			for item in self.hidable:
				item.Hide()
			self.noPropertiesLabel.Show()
		else:
			for item in self.hidable:
				item.Show()
			self.noPropertiesLabel.Hide()

	def onPanelActivated(self):
		self.updateData()
		self.initPropertiesList()
		super(PropertiesPanel, self).onPanelActivated()

	def onSave(self):
		self.updateData()

class RuleEditorDialog(ContextualMultiCategorySettingsDialog):

	# Translators: The title of the rule editor
	title = _("WebAccess Rule editor")
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
		#from . import criteriaEditor
		#self.categoryClasses.append(criteriaEditor.CriteriaPanel_)

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
