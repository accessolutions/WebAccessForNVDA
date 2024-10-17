# globalPlugins/webAccess/gui/criteriaEditor.py
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



__author__ = "Shirley Noël <shirley.noel@pole-emploi.fr>"


from collections import OrderedDict
from copy import deepcopy
import re
import sys
from typing import Any
import wx
from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import controlTypes
import inputCore
import gui
from gui import guiHelper
from logHandler import log
import speech
import ui

import addonHandler
from ..ruleHandler import builtinRuleActions, ruleTypes
from ..utils import guarded, notifyError, updateOrDrop
from . import (
	ContextualMultiCategorySettingsDialog,
	ContextualSettingsPanel,
	DropDownWithHideableChoices,
	EditorType,
	InvalidValue,
	SizeFrugalComboBox,
	ValidationError,
	stripAccel,
	stripAccelAndColon,
)
from .actions import ActionsPanelBase
from .rule.abc import RuleAwarePanelBase
from .properties import Properties, PropertiesPanelBase, Property


if sys.version_info[1] < 9:
    from typing import Mapping, Sequence
else:
    from collections.abc import Mapping, Sequence


addonHandler.initTranslation()

from six import iteritems, text_type

EXPR_VALUE = re.compile("(([^!&| ])+( (?=[^!&|]))*)+")
"""
Compiled pattern used to capture values in expressions.
"""

EXPR = re.compile("^ *!? *[^!&|]+( *[&|] *!? *[^!&|]+)*$")
"""
Compiled pattern used to validate expressions.
"""

EXPR_INT = re.compile("^ *!? *[0-9]+( *[&|] *!? *[0-9]+)* *$")
"""
Compiled pattern used to validate expressions whose values are integers.
"""


def captureValues(expr):
	"""
	Yields value, startPos, endPos
	"""
	for match in EXPR_VALUE.finditer(expr):
		span = match.span()
		yield expr[span[0]:span[1]], span[0], span[1]


def getStatesLblExprForSet(states):
	return " & ".join((
		controlTypes.stateLabels.get(state, state)
		for state in states
	))


def translateExprValues(expr, func):
	buf = list(expr)
	offset = 0
	for src, start, end in captureValues(expr):
		dest = text_type(func(src))
		start += offset
		end += offset
		buf[start:end] = dest
		offset += len(dest) - len(src)
	return "".join(buf)


def translateRoleIdToLbl(expr):
	def translate(value):
		try:
			return controlTypes.roleLabels[int(value)]
		except (KeyError, ValueError):
			return value
	return translateExprValues(expr, translate)


def translateRoleLblToId(expr, raiseOnError=True):
	def translate(value):
		for key, candidate in iteritems(controlTypes.roleLabels):
			if candidate == value:
				return text_type(key.value)
		if raiseOnError:
			raise ValidationError(value)
		return value
	return translateExprValues(expr, translate)


def translateStatesIdToLbl(expr):
	def translate(value):
		try:
			return controlTypes.stateLabels[int(value)]
		except (KeyError, ValueError):
			return value
	return translateExprValues(expr, translate)


def translateStatesLblToId(expr, raiseOnError=True):
	def translate(value):
		for key, candidate in iteritems(controlTypes.stateLabels):
			if candidate == value:
				return text_type(key.value)
		if raiseOnError:
			raise ValidationError(value)
		return value
	return translateExprValues(expr, translate)


def getSummary_context(data) -> Sequence[str]:
	parts = []
	for key, label in list(CriteriaPanel.FIELDS.items()):
		if (
			key not in CriteriaPanel.CONTEXT_FIELDS
			or (
				key not in data
				and key not in data.get("properties", {})
			)
		):
			continue
		value = data[key]
		parts.append("{} {}".format(stripAccel(label), value))
	if not parts:
		# Translators: A mention on the Criteria summary report
		parts.append(_("Global - Applies to the whole web module"))
	return parts


def getSummary(context, data, indent="", condensed=False) -> str:
	parts = []
	subParts = getSummary_context(data)
	if condensed:
		parts.append(", ".join(subParts))
	else:
		parts.extend(subParts)
	subParts = []
	for key, label in list(CriteriaPanel.FIELDS.items()):
		if key in CriteriaPanel.CONTEXT_FIELDS or key not in data:
			continue
		value = data[key]
		if not isinstance(value, InvalidValue):
			if key == "role":
				value = translateRoleIdToLbl(value)
			elif key == "states":
				value = translateStatesIdToLbl(value)
		subParts.append("{} {}".format(
			stripAccel(label),
			value
		))
	if subParts:
		if condensed:
			parts.append(", ".join(subParts))
		else:
			parts.extend(subParts)
	
	# Properties
	subParts = []
	props = Properties(context, data.get("properties", {}), iterOnlyFirstMap=True)
	for prop in props:
		subParts.append(
			# Translators: A mention on the Criteria Summary report
			_("{indent}{field}: {value}").format(
				indent="  " if not condensed else "",
				field=prop.displayName,
				value=prop.displayValue,
			)
		)
	if subParts:
		# Translators: The label for a section on the Criteria Summary report
		parts.append(_("{section}:").format(section=PropertiesPanel.title))
		if condensed:
			parts.append(", ".join(subParts))
		else:
			parts.extend(subParts)

	if parts:
		return "{}{}".format(indent, "\n{}".format(indent).join(parts))
	# Translators: A mention on the Criteria Summary report
	return "{}{}".format(indent, _("No criteria"))


@guarded
def testCriteria(context):
	ruleData = deepcopy(context["data"]["rule"])
	ruleData["name"] = "__tmp__"
	ruleData.pop("new", None)
	ruleData["type"] = ruleTypes.MARKER
	critData = context["data"]["criteria"].copy()
	critData.pop("new", None)
	critData.pop("criteriaIndex", None)
	ruleData["criteria"] = [critData]
	ruleData.setdefault("properties", {})['multiple'] = True
	critData.setdefault("properties", {}).pop("multiple", True)
	mgr = context["webModule"].ruleManager
	from ..ruleHandler import Rule
	rule = Rule(mgr, ruleData)
	import time
	start = time.time()
	results = rule.getResults()
	duration = time.time() - start
	if len(results) == 1:
		message = _("Found 1 result in {:.3f} seconds.".format(duration))
	elif results:
		message = _("Found {} results in {:.3f} seconds.".format(len(results), duration))
	else:
		message = _("No result found on the current page.")
	gui.messageBox(message, caption=_("Criteria test"))


class CriteriaEditorPanel(RuleAwarePanelBase):
	
	def getData(self):
		return self.context["data"].setdefault("criteria", {})


class GeneralPanel(CriteriaEditorPanel):
	# Translators: The label for a Criteria editor category.
	title = _("General")
	
	def __init__(self, parent):
		self.hideable: Sequence[wx.Window] = []
		super().__init__(parent)
	
	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		row = 0
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("Criteria Set &name:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.criteriaName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		items = self.hideable
		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("&Sequence order:"))
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		items.append(item)
		item = self.sequenceOrderChoice = wx.Choice(self)
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("Summar&y:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		gbSizer.Add(item, pos=(row, 2), span=(2, 1), flag=wx.EXPAND)

		row += 2
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("Technical n&otes:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		gbSizer.AddGrowableCol(2)
	
	def initData(self, context):
		super().initData(context)
		data = self.getData()
		new = data.get("new", False)
		self.sequenceOrderChoice.Clear()
		nbCriteria = len(context["data"]["rule"]["criteria"]) + (1 if new else 0)
		if nbCriteria == 1:
			for item in self.hideable:
				item.Show(False)
		else:
			for index in range(nbCriteria):
				self.sequenceOrderChoice.Append(str(index + 1))
			index = data.get("criteriaIndex", nbCriteria + 1)
			self.sequenceOrderChoice.SetSelection(index)
		self.criteriaName.Value = data.get("name", "")
		self.commentText.Value = data.get("comment", "")
		self.refreshSummary()

	def updateData(self):
		data = self.getData()
		updateOrDrop(data, "name", self.criteriaName.Value)
		updateOrDrop(data, "comment", self.commentText.Value)

	def getSummary(self):
		if not self.context:
			return ""
		self.Parent.Parent.currentCategory.updateData()
		return getSummary(self.context, self.getData())

	def refreshSummary(self):
		self.summaryText.Value = self.getSummary()

	def onPanelActivated(self):
		self.refreshSummary()
		super().onPanelActivated()

	def spaceIsPressedOnTreeNode(self):
		self.criteriaName.SetFocus()

	def onSave(self):
		super().onSave()
		data = self.getData()
		index = self.sequenceOrderChoice.Selection
		data["criteriaIndex"] = index if index != -1 else 0


class CriteriaPanel(CriteriaEditorPanel):
	# Translators: The label for a Criteria editor category.
	title = _("Criteria")

	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		# Translator: The label for a Rule Criteria field
		("contextPageTitle", pgettext("webAccess.ruleCriteria", "Page &title:")),
		# Translator: The label for a Rule Criteria field
		("contextPageType", pgettext("webAccess.ruleCriteria", "Page t&ype")),
		# Translator: The label for a Rule Criteria field
		("contextParent", pgettext("webAccess.ruleCriteria", "&Parent element")),
		# Translator: The label for a Rule Criteria field
		("text", pgettext("webAccess.ruleCriteria", "&Text:")),
		# Translator: The label for a Rule Criteria field
		("role", pgettext("webAccess.ruleCriteria", "&Role:")),
		# Translator: The label for a Rule Criteria field
		("tag", pgettext("webAccess.ruleCriteria", "T&ag:")),
		# Translator: The label for a Rule Criteria field
		("id", pgettext("webAccess.ruleCriteria", "&ID:")),
		# Translator: The label for a Rule Criteria field
		("className", pgettext("webAccess.ruleCriteria", "&Class:")),
		# Translator: The label for a Rule Criteria field
		("states", pgettext("webAccess.ruleCriteria", "&States:")),
		# Translator: The label for a Rule Criteria field
		("src", pgettext("webAccess.ruleCriteria", "Ima&ge source:")),
		# Translator: The label for a Rule Criteria field
		("relativePath", pgettext("webAccess.ruleCriteria", "R&elative path:")),
		# Translator: The label for a Rule Criteria field
		("index", pgettext("webAccess.ruleCriteria", "Inde&x:")),
	))

	CONTEXT_FIELDS = ["contextPageTitle", "contextPageType", "contextParent"]

	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		hidable = self.hidable = {}

		row = 0
		item = wx.StaticText(self, label=_("Context:"))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.contextMacroDropDown = DropDownWithHideableChoices(self)
		item.setChoices((
			# Translator: A selection value for the Context field on the Criteria editor
			("global", _("Global - Applies to the whole web module")),
			# Translator: A selection value for the Context field on the Criteria editor
			("contextPageTitle", _("Page title - Applies only to pages with the given title")),
			# Translator: A selection value for the Context field on the Criteria editor
			("contextPageType", _("Page type - Applies only to pages with the given type")),
			# Translator: A selection value for the Context field on the Criteria editor
			("contextParent", _("Parent element - Applies only within the results of another rule")),
			# Translator: A selection value for the Context field on the Criteria editor
			("advanced", _("Advanced")),
		))
		item.Bind(wx.EVT_COMBOBOX, self.onContextMacroChoice)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		items = hidable["contextPageTitle"] = []
		item = wx.StaticText(self, label=self.FIELDS["contextPageTitle"])
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item.Show(False)
		items.append(item)
		item = self.contextPageTitleCombo = wx.ComboBox(self, size=(-1, 30))
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		item.Show(False)
		items.append(item)

		row += 1
		items = hidable["contextPageType"] = []
		item = wx.StaticText(self, label=self.FIELDS["contextPageType"])
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item.Show(False)
		items.append(item)
		item = self.contextPageTypeCombo = wx.ComboBox(self)
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		item.Show(False)
		items.append(item)

		row += 1
		items = hidable["contextParent"] = []
		item = wx.StaticText(self, label=self.FIELDS["contextParent"])
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item.Show(False)
		items.append(item)
		item = self.contextParentCombo = wx.ComboBox(self)
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		item.Show(False)
		items.append(item)

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["text"])
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.textCombo = SizeFrugalComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["role"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.roleCombo = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["tag"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.tagCombo = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["id"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.idCombo = SizeFrugalComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["className"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.classNameCombo = SizeFrugalComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["states"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.statesCombo = SizeFrugalComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["src"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.srcCombo = SizeFrugalComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["relativePath"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.relativePathCombo = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["index"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.indexText = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translators: The label for a button in the Criteria Editor dialog
		item = wx.Button(self, label=_("Test these criteria (F5)"))
		item.Bind(wx.EVT_BUTTON, self.Parent.Parent.onTestCriteria)
		gbSizer.Add(item, pos=(row, 0), span=(1, 3))

		gbSizer.AddGrowableCol(2)
	
	def initData(self, context):
		super().initData(context)
		data = self.getData()
		mgr = context["webModule"].ruleManager

		if mgr.isReady and mgr.nodeManager:
			node = mgr.nodeManager.getCaretNode()

			self.contextPageTitleCombo.Set([context["pageTitle"]])
			self.contextPageTypeCombo.Set(mgr.getPageTypes())
			parents = []
			for result in mgr.getResults():
				rule = result.rule
				if (
					rule.type in (ruleTypes.PARENT, ruleTypes.ZONE)
					and node in result.node
				):
					parents.insert(0, rule.name)
			self.contextParentCombo.Set(parents)

			textNode = node
			node = node.parent
			t = textNode.text
			if t == " ":
				t = ""
			textChoices = [t]
			if node.previousTextNode is not None:
				textChoices.append("<" + node.previousTextNode.text)

			roleChoices = []
			tagChoices = []
			idChoices = []
			classChoices = []
			statesChoices = []
			srcChoices = []
			# todo: actually there are empty choices created
			while node is not None:
				roleChoices.append(controlTypes.roleLabels.get(node.role, "") or "")
				tagChoices.append(node.tag or "")
				idChoices.append(node.id or "")
				classChoices.append(node.className or "")
				statesChoices.append(getStatesLblExprForSet(node.states) or "")
				srcChoices.append(node.src or "")
				node = node.parent
			
			self.textCombo.Set(textChoices)
			self.roleCombo.Set(roleChoices)
			self.tagCombo.Set(tagChoices)
			self.idCombo.Set(idChoices)
			self.classNameCombo.Set(classChoices)
			self.statesCombo.Set(statesChoices)
			self.srcCombo.Set(srcChoices)

		self.refreshContextMacroChoices(initial=True)
		self.onContextMacroChoice(None)
		self.contextPageTitleCombo.Value = data.get("contextPageTitle", "")
		self.contextPageTypeCombo.Value = data.get("contextPageType", "")
		self.contextParentCombo.Value = data.get("contextParent", "")

		self.textCombo.Value = data.get("text", "")
		value = data.get("role", "")
		if isinstance(value, InvalidValue):
			self.roleCombo.Value = value.raw
		else:
			self.roleCombo.Value = translateRoleIdToLbl(value)
		self.tagCombo.Value = data.get("tag", "")
		self.idCombo.Value = data.get("id", "")
		self.classNameCombo.Value = data.get("className", "")
		value = data.get("states", "")
		if isinstance(value, InvalidValue):
			self.statesCombo.Value = value.raw
		else:
			self.statesCombo.Value = translateStatesIdToLbl(value)
		self.srcCombo.Value = data.get("src", "")
		self.relativePathCombo.Value = str(data.get("relativePath", ""))
		value = data.get("index", "")
		if isinstance(value, InvalidValue):
			self.indexText.Value = value.raw
		else:
			self.indexText.Value = str(value)

	def updateData(self):
		data = self.getData()
		updateOrDrop(data, "contextPageTitle", self.contextPageTitleCombo.Value)
		updateOrDrop(data, "contextPageType", self.contextPageTypeCombo.Value)
		updateOrDrop(data, "contextParent", self.contextParentCombo.Value)
		updateOrDrop(data, "text", self.textCombo.Value)
		value = self.roleCombo.Value
		try:
			updateOrDrop(data, "role", translateRoleLblToId(value))
		except ValidationError:
			data["role"] = InvalidValue(value)
		updateOrDrop(data, "tag", self.tagCombo.Value)
		updateOrDrop(data, "id", self.idCombo.Value)
		updateOrDrop(data, "className", self.classNameCombo.Value)
		value = self.statesCombo.Value
		try:
			updateOrDrop(data, "states", translateStatesLblToId(value))
		except ValidationError:
			data["states"] = InvalidValue(value)
		updateOrDrop(data, "src", self.srcCombo.Value)
		updateOrDrop(data, "relativePath", self.relativePathCombo.Value)
		value = self.indexText.Value
		try:
			value = int(value) if value.strip() else None
		except Exception:
			value = InvalidValue(value)
		updateOrDrop(data, "index", value)

	def refreshContextMacroChoices(self, initial=False):
		context = self.context
		dropDown = self.contextMacroDropDown
		ruleType = context["data"]["rule"].get("type")
		if ruleType is None:
			dropDown.setAllChoicesEnabled(False)
		else:
			dropDown.setAllChoicesEnabled(True)
			self.contextMacroDropDown.setChoiceEnabled(
				"contextPageTitle",
				ruleType not in (ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2),
				default="advanced"
			)
			if initial:
				data = context["data"]["criteria"]
				filled = [
					field
					for field in ("contextPageTitle", "contextPageType", "contextParent")
					if data.get(field)
				]
				if not filled:
					dropDown.setSelectedChoiceKey("global")
				elif len(filled) > 1:
					dropDown.setSelectedChoiceKey("advanced")
				else:
					dropDown.setSelectedChoiceKey(filled[0], default="global")
		self.onContextMacroChoice(None)

	def onContextMacroChoice(self, evt):
		dropDown = self.contextMacroDropDown
		choice = self.contextMacroDropDown.getSelectedChoiceKey()
		fields = dict.fromkeys(
			("contextPageTitle", "contextPageType", "contextParent"),
			False
		)
		if choice in fields:
			fields[choice] = True
		elif choice == "advanced":
			for field in fields:
				fields[field] = True
		self.Freeze()
		for field, show in list(fields.items()):
			for item in self.hidable[field]:
				item.Show(show)
		self.Thaw()
		self._sendLayoutUpdatedEvent()

	def onPanelActivated(self):
		self.refreshContextMacroChoices()
		# self.onContextMacroChoice(None)
		super().onPanelActivated()

	def spaceIsPressedOnTreeNode(self):
		self.contextMacroDropDown.SetFocus()

	def isValid(self):
		data = self.context["data"]["criteria"]
		roleLblExpr = self.roleCombo.Value
		if roleLblExpr.strip():
			if not EXPR.match(roleLblExpr):
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't meet the required syntax
						_('Syntax error in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["role"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.roleCombo.SetFocus()
				return False
			try:
				roleIdExpr = translateRoleLblToId(roleLblExpr)
			except ValidationError:
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't match any known identifier
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["role"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.roleCombo.SetFocus()
				return False

		statesLblExpr = self.statesCombo.Value
		if statesLblExpr:
			if not EXPR.match(statesLblExpr):
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't meet the required syntax
						_('Syntax error in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["states"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.statesCombo.SetFocus()
				return False
			try:
				statesIdExpr = translateStatesLblToId(statesLblExpr)
			except ValidationError:
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't match any known identifier
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["states"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.statesCombo.SetFocus()
				return False

		index = self.indexText.Value
		if index.strip():
			try:
				index = int(index)
			except Exception:
				index = 0
			if index <= 0:
				gui.messageBox(
					# Translators: Error message when the index is not positive
					message=_("Index, if set, must be a positive integer."),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.indexText.SetFocus()
				return False

		return True


class ActionsPanel(ActionsPanelBase, CriteriaEditorPanel):
	
	def makeSettings(self, settingsSizer):
		super().makeSettings(settingsSizer)
		self.autoActionChoice.Bind(wx.EVT_CHAR_HOOK, self.onAutoActionChoice_charHook)
	
	def getAutoAction(self):
		return self.getData().get("properties", {}).get(
			"autoAction", self.getRuleAutoAction()
		)
	
	def getRuleAutoAction(self):
		return self.getRuleData().get("properties", {}).get("autoAction")
	
	def getAutoActionChoices(self):
		choices = super().getAutoActionChoices()
		ruleValue = self.getRuleAutoAction()
		# Translators: An entry in the Automatic Action list on the Criteria Editor denoting the rule value
		choices[ruleValue] = "{action} (default)".format(
			action=choices.get(ruleValue, f"*{ruleValue}")
		)
		return choices
	
	@guarded
	def onAutoActionChoice_charHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_DELETE and not mods:
			self.resetAutoAction()
			return
		evt.Skip()
	
	def resetAutoAction(self):
		data = self.getData().setdefault("properties", {})
		data["autoAction"] = self.getRuleAutoAction()
		self.updateAutoActionChoice(refreshChoices=False) 
		# Translators: Announced when resetting a property to its default value in the editor
		ui.message(_("Reset to {value}").format(value=self.autoActionChoice.StringSelection))


class PropertyOverrideSelectMenu(wx.Menu):
	"""Menu to select a property to override on the CriteriaPropertiesPanel
	"""
	
	def __init__(self, menuIdProps: Mapping[int, Property]):
		super().__init__(title=_("Select a property to override"))
		for menuId, prop in menuIdProps.items():
			self.Append(menuId, prop.displayName)


class PropertiesPanel(PropertiesPanelBase, CriteriaEditorPanel):
	
	def makeSettings(self, settingsSizer):
		super().makeSettings(settingsSizer)
		scale = self.scale
		gbSizer = self.gbSizer
		
		# Translators: The label for a list on the Criteria Editor dialog
		self.listLabel.Label = _("Properties specific to this criteria set")
		listCtrl = self.listCtrl
		# Translators: A hint stating a list is empty and how to populate it on the Criteria Editor dialog
		listCtrl.descriptionIfEmpty = _("None. Press alt+n to override a property.")
		# Translators: A column header in the Criteria Editor dialog
		self.listCtrl.InsertColumn(2, _("Rule value"))

		col = 4
		row = 3
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL), pos=(row, col))

		col += 1
		# Translators: The label for a button on the Criteria Editor dialog
		item = self.addPropBtn = wx.Button(self, label=_("&New")) #FIXME, size=(-1, 30))
		item.Enable(False)
		item.Bind(wx.EVT_BUTTON, self.onAddPropBtn)
		gbSizer.Add(item, pos=(row, col))

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, col))

		row += 1
		# Translators: The label for a button on the Criteria Editor dialog
		item = self.delPropBtn = wx.Button(self, label=_("&Delete")) # FIXME, size=(-1, 30))
		item.Enable(False)
		item.Bind(wx.EVT_BUTTON, self.onDelPropBtn)
		gbSizer.Add(item, pos=(row, col))
	
	# Called by PropertiesPanelBase.initData
	def initData_properties(self):
		context = self.context
		self.props = Properties(
			context,
			self.getData(),
			context["data"]["rule"].setdefault("properties", {}),
			iterOnlyFirstMap=True,
		)
	
	def listCtrl_insert(self, index: int, prop: Property) -> None:
		super().listCtrl_insert(index, prop)
		self.listCtrl.SetStringItem(index, 2, prop.displayDefault)

	def listCtrl_update_all(self):
		super().listCtrl_update_all()
		props = self.props
		self.delPropBtn.Enable(bool(props))
		self.addPropBtn.Enable(len(props.getSupportedPropertiesName()) > len(props))

	@guarded
	def onAddPropBtn(self, evt):
		props = self.props
		overrideable = tuple(
			props.getProperty(name)
			for name in props.getSupportedPropertiesName()
			if name not in props._map.maps[0]
		)
		startId = wx.Window.NewControlId(len(overrideable))
		try:
			menuIdProp = {startId + index: prop for index, prop in enumerate(overrideable)}
			menu = PropertyOverrideSelectMenu(menuIdProp)
			menuId = self.GetPopupMenuSelectionFromUser(menu)
		except Exception:
			try:
				# Reserved IDs are automatically reclaimed upon assignment to the MenuItem
				# In case something went wrong, try to unreserve them manually to avoid
				# running out of stock.
				wx.Window.UnreserveControlId(startId, len(overrideable))
			except Exception:
				pass
			notifyError()
			return
		prop = menuIdProp[menuId] if menuId != wx.ID_NONE else None
		if not prop:
			return
		prop.value = prop.default  # Setting any value actually adds to the ChainMap based container
		self.listCtrl_update_all()
		self.prop = prop
		if prop.editorType is EditorType.TEXT:
			self.editor.SetFocus()
		else:
			self.listCtrl.SetFocus()
	
	@guarded
	def onDelPropBtn(self, evt):
		self.prop.reset()
		self.listCtrl_update_all()
		if not self.props:
			self.addPropBtn.SetFocus()
	
	def prop_reset(self):
		# Using Property.reset would actually remove the overridden property from the list.
		# Manually reset to its default instead.
		# Note default values are dropped upon saving anyways.
		prop = self.prop
		prop.value = prop.default
		self.updateEditor()
		self.onEditor_change()
		speech.cancelSpeech()  # Avoid announcing the whole eventual control refresh
		# Translators: Announced when resetting a property to its default value in the editor
		ui.message(_("Reset to {value}").format(value=self.prop.displayValue))


class CriteriaEditorDialog(ContextualMultiCategorySettingsDialog):
	# Translators: The title of the Criteria Editor dialog.
	title = _("WebAccess Criteria Set editor")
	categoryClasses = [GeneralPanel, CriteriaPanel, ActionsPanel, PropertiesPanel]
	INITIAL_SIZE = (900, 580)
	
	def makeSettings(self, settingsSizer):
		super().makeSettings(settingsSizer)
		idTestCriteria = wx.NewId()
		self.Bind(wx.EVT_MENU, self.onTestCriteria, id=idTestCriteria)
		self.SetAcceleratorTable(wx.AcceleratorTable([
			(wx.ACCEL_NORMAL, wx.WXK_F5, idTestCriteria)
		]))

	def onTestCriteria(self, evt):
		self.currentCategory.updateData()
		testCriteria(self.context)


def show(context, parent=None):
	from . import showContextualDialog
	return showContextualDialog(CriteriaEditorDialog, context, parent)
