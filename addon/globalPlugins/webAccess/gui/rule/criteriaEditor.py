# globalPlugins/webAccess/gui/rule/criteriaEditor.py
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
	"Shirley Noël <shirley.noel@pole-emploi.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Sendhil Randon <sendhil.randon-ext@francetravail.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


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
from ...ruleHandler import ruleTypes
from ...utils import guarded, notifyError, updateOrDrop
from .. import (
	ContextualMultiCategorySettingsDialog,
	ContextualSettingsPanel,
	DropDownWithHideableChoices,
	EditorType,
	InvalidValue,
	SizeFrugalComboBox,
	ValidationError,
	stripAccel,
	showContextualDialog,
	stripAccelAndColon,
)
from . import createMissingSubModule
from .abc import RuleAwarePanelBase
from .gestures import GesturesPanelBase
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
		parts.append(_("General - Applies to the whole web module"))
	return parts


def getSummary_selector_full(data, condensed=False) -> Sequence[str]:
	if set(data.keys()) == {"start", "end"}:
		parts = []
		sections = {
			"start": _("Start:"),
			"end": _("End:"),
		}
		contexts = {
			key: getSummary_context(data[key])
			for key in ("start", "end")
		}
		sameContext = contexts["start"] == contexts["end"]
		if sameContext:
			subParts = next(iter(contexts.values()))
			if condensed:
				parts.append(", ".join(subParts))
			else:
				parts.extend(subParts)
		indent = "    "
		for key in ("start", "end"):
			if not (condensed and sameContext):
				parts.append(sections[key])
			if not sameContext:
				subParts = contexts[key]
				if condensed:
					parts.append(indent + ", ".join(subParts))
				else:
					parts.extend((indent + subPart for subPart in subParts))
			subParts = getSummary_selector_unit(data[key])
			if condensed:
				if sameContext:
					parts.append(f'{sections[key]} {" ".join(subParts)}')
				else:
					parts.append(indent + ", ".join(subParts))
			else:
				parts.extend((indent + subPart for subPart in subParts))
		return parts
	else:
		parts = []
		parts.extend(getSummary_context(data))
		subParts = getSummary_selector_unit(data)
		if condensed:
			parts.append(", ".join(subParts))
		else:
			parts.extend(subParts)
		return parts


def getSummary_selector_unit(data) -> Sequence[str]:
	parts = []
	for key, label in list(CriteriaPanel.FIELDS.items()):
		if key in CriteriaPanel.CONTEXT_FIELDS or key not in data:
			continue
		value = data[key]
		if not isinstance(value, InvalidValue):
			if key == "role":
				value = translateRoleIdToLbl(value)
			elif key == "states":
				value = translateStatesIdToLbl(value)
		parts.append("{} {}".format(
			stripAccel(label),
			value
		))
	if parts:
		return parts
	# Translators: A mention on the Criteria Summary report
	return [_("No criteria")]


def getSummary(context, data, indent="", condensed=False) -> str:
	parts = []
	
	parts.extend(getSummary_selector_full(
		data.get("selector", {}), condensed=condensed
	))
	
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


@guarded
def testCriteria(context, restrictDualNodeTo=None):
	ruleData = deepcopy(context["data"]["rule"])
	ruleData["name"] = "__tmp__"
	if restrictDualNodeTo:
		critData = {
			"selector": context["data"]["criteria"]["selector"][
				restrictDualNodeTo
			],
		}
		caption = {
			# Translators: The title of a dialog in the Criteria Set editor
			"start": _("Start Criteria test"),
			# Translators: The title of a dialog in the Criteria Set editor
			"end": _("End Criteria test"),
		}[restrictDualNodeTo]
	else:
		critData = context["data"]["criteria"].copy()
		if isDualNode(critData):
			# Translators: The title of a dialog in the Criteria Set editor
			caption = _("Combined Criteria test")
		else:
			# Translators: The title of a dialog in the Criteria Set editor
			caption = _("Criteria test")
	critData.pop("new", None)
	critData.pop("criteriaIndex", None)
	ruleData["criteria"] = [critData]
	# Ensure the user is informed about all the match occurrences, even if only
	# the first is retained by a disabled "multiple" property.
	# All rule types do not support this property, hence force the rule type "marker".
	# Rather than filtering out properties not supported for this type, simply drop them all
	# as they have no impact on the actual search.
	ruleData["type"] = ruleTypes.MARKER
	ruleData["properties"] = {"multiple": True}
	critData["properties"] = {"multiple": True}
	mgr = context["webModule"].ruleManager
	from ...ruleHandler import Rule
	rule = Rule(mgr, ruleData)
	import time
	start = time.time()
	results = rule.getResults()
	duration = time.time() - start
	if len(results) == 1:
		# Translators: Reported upon testing criteria
		message = _("Found 1 result in {:.3f} seconds.".format(duration))
	elif results:
		# Translators: Reported upon testing criteria
		message = _("Found {} results in {:.3f} seconds.".format(len(results), duration))
	else:
		# Translators: Reported upon testing criteria
		message = _("No result found on the current page.")
	gui.messageBox(message, caption=caption)


def isDualNode(data):
	return set(data.get("selector", {}).keys()) == {"start", "end"}


def supportsSimpleMode(data):
	if any(
		k in ("gestures", "properties")
		for k in data.keys()
	):
		return False
	return True


def convertToDualNode(data):
	if isDualNode(data):
		raise ValueError("This selector is already dual node")
	selector = data.get("selector", {})
	data["selector"] = {"start": selector.copy(), "end": selector.copy()}


def convertToSingleNode(data):
	if not isDualNode(data):
		raise ValueError("This selector is not dual node")
	data["selector"] = data["selector"]["start"]


class CriteriaEditorPanel(RuleAwarePanelBase):
	
	def getData(self):
		# Should always be initialized, as the Rule Editor populates it with at least
		# the index of this Alternative Criteria Set ("criteriaIndex").
		return self.context["data"]["criteria"]


class GeneralPanel(CriteriaEditorPanel):
	# Translators: The label for a Criteria editor category.
	title = _("General")
	
	def __init__(self, parent):
		self.hideable: Mapping[Sequence[wx.Window]] = {}
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

		items = self.hideable["order"] = []
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

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

		items = self.hideable["convert.dual"] = []
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

		row += 1
		# Translators: The label for a button in the Criteria Editor dialog
		item = wx.Button(self, label=_("Convert to free &zone (two sets of criteria)"))
		item.Bind(wx.EVT_BUTTON, self.Parent.Parent.onConvertToDualNode)
		item.Disable()
		items.append(item)
		item = gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
		items.append(item)
		for item in items:
			item.Show(False)

		items = self.hideable["convert.single"] = []
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

		row += 1
		# Translators: The label for a button in the Criteria Editor dialog
		item = wx.Button(self, label=_("Convert to simple &zone (one set of criteria)"))
		item.Bind(wx.EVT_BUTTON, self.Parent.Parent.onConvertToSingleNode)
		item.Disable()
		items.append(item)
		item = gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
		items.append(item)
		for item in items:
			item.Show(False)

		gbSizer.AddGrowableCol(2)
	
	def initData(self, context):
		super().initData(context)
		self.sequenceOrderChoice.Clear()
		nbAlternatives = len(context["data"]["rule"]["criteria"])
		if context.get("new"):
			nbAlternatives += 1
		data = self.getData()
		if nbAlternatives == 1:
			for item in self.hideable["order"]:
				item.Show(False)
		else:
			for index in range(nbAlternatives):
				self.sequenceOrderChoice.Append(str(index + 1))
			index = data.get("criteriaIndex", nbAlternatives + 1)
			self.sequenceOrderChoice.SetSelection(index)
		if self.getRuleType() == ruleTypes.ZONE:
			key = "convert.single" if isDualNode(data) else "convert.dual"
			for item in self.hideable[key]:
				if isinstance(item, wx.Button):
					item.Enable()
				item.Show(True)
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
	"""Criteria Panel of the Alternative Criteria Set Editor
	
	To accomodate with the Rule Creation Wizard which reuses this panel split on two different pages,
	several method are split in two: "<method>_context" and "<method>_others".
	"""
	
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
		("url", pgettext("webAccess.ruleCriteria", "Document &URL:")),
		# Translator: The label for a Rule Criteria field
		("relativePath", pgettext("webAccess.ruleCriteria", "R&elative path:")),
		# Translator: The label for a Rule Criteria field
		("index", pgettext("webAccess.ruleCriteria", "Inde&x:")),
	))

	CONTEXT_FIELDS = ["contextPageTitle", "contextPageType", "contextParent"]

	def makeSettings(self, settingsSizer):
		scale = self.scale
		self.hidable = {}
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		row = 0
		row = self.makeSettings_context(gbSizer, row)
		if row is not None:
			row += 1
			item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
			row += 1
		else:
			row = 0
		self.makeSettings_others(gbSizer, row)
		gbSizer.AddGrowableCol(2)

	def makeSettings_context(self, gbSizer, row):
		# This part is shown on its own page on the Rule Creation Wizard
		scale = self.scale
		hidable = self.hidable
		item = wx.StaticText(self, label=_("Context:"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.contextMacroDropDown = DropDownWithHideableChoices(self)
		item.setChoices((
			# Translator: A selection value for the Context field on the Criteria editor
			("general", _("General - Applies to the whole web module")),
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
		items = hidable["contextPageTitle"] = []
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["contextPageTitle"])
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		items.append(item)
		item = self.contextPageTitleCombo = wx.ComboBox(self, size=(-1, 30))
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		items = hidable["contextPageType"] = []
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["contextPageType"])
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		items.append(item)
		item = self.contextPageTypeCombo = wx.ComboBox(self)
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		items = hidable["contextParent"] = []
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["contextParent"])
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		items.append(item)
		item = self.contextParentCombo = wx.ComboBox(self)
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		return row

	def makeSettings_others(self, gbSizer, row):
		scale = self.scale
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
		item = wx.StaticText(self, label=self.FIELDS["url"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.urlCombo = SizeFrugalComboBox(self)
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
		## Translators: The label for a button in the Criteria Editor dialog
		#item = wx.Button(self, label=_("Test these criteria (F5)"))
		#item.Bind(wx.EVT_BUTTON, self.onTestCriteria)
		#gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
		vBoxSizer = wx.BoxSizer(wx.VERTICAL)
		self.makeSettings_buttons(vBoxSizer)
		gbSizer.Add(vBoxSizer, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

	def makeSettings_buttons(self, vBoxSizer):
		# Translators: The label for a button in the Criteria Editor dialog
		item = wx.Button(self, label=_("Test these criteria (F5)"))
		item.Bind(wx.EVT_BUTTON, self.onTestCriteria)
		vBoxSizer.Add(item, flag=wx.EXPAND)

	def getData(self):
		return super().getData().setdefault("selector", {})

	def initData(self, context):
		super().initData(context)
		self.initData_context(context)
		self.initData_others(context)
	
	def initData_context(self, context):
		data = self.getData()
		self.contextPageTitleCombo.Set([context["pageTitle"]])
		mgr = context["webModule"].ruleManager
		if mgr.isReady:
			self.contextPageTypeCombo.Set(mgr.getPageTypes())
			node = mgr.nodeManager.getCaretNode()
			parents = []
			for result in mgr.getResults():
				rule = result.rule
				if (
					rule.type in (ruleTypes.PARENT, ruleTypes.ZONE)
					and result.containsNode(node)
				):
					parents.insert(0, rule.name)
			self.contextParentCombo.Set(parents)
		self.refreshContextMacroChoices(initial=True)
		self.contextPageTitleCombo.Value = data.get("contextPageTitle", "")
		self.contextPageTypeCombo.Value = data.get("contextPageType", "")
		self.contextParentCombo.Value = data.get("contextParent", "")
	
	def initData_others(self, context):
		data = self.getData()
		mgr = context["webModule"].ruleManager
		if mgr.isReady:
			node = mgr.nodeManager.getCaretNode()
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
			urlChoices = []
			# todo: actually there are empty choices created
			while node is not None:
				roleChoices.append(controlTypes.roleLabels.get(node.role, "") or "")
				tagChoices.append(node.tag or "")
				idChoices.append(node.id or "")
				classChoices.append(node.className or "")
				statesChoices.append(getStatesLblExprForSet(node.states) or "")
				srcChoices.append(node.src or "")
				urlChoices.append(node.url or "")
				node = node.parent
			
			self.textCombo.Set(textChoices)
			self.roleCombo.Set(roleChoices)
			self.tagCombo.Set(tagChoices)
			self.idCombo.Set(idChoices)
			self.classNameCombo.Set(classChoices)
			self.statesCombo.Set(statesChoices)
			self.srcCombo.Set(srcChoices)
			self.urlCombo.Set(urlChoices)
		
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
		self.urlCombo.Value = data.get("url", "")
		self.relativePathCombo.Value = str(data.get("relativePath", ""))
		value = data.get("index", "")
		if isinstance(value, InvalidValue):
			self.indexText.Value = value.raw
		else:
			self.indexText.Value = str(value)

	def updateData(self):
		self.updateData_context()
		self.updateData_others()
	
	def updateData_context(self):
		data = self.getData()
		updateOrDrop(data, "contextPageTitle", self.contextPageTitleCombo.Value)
		updateOrDrop(data, "contextPageType", self.contextPageTypeCombo.Value)
		updateOrDrop(data, "contextParent", self.contextParentCombo.Value)
	
	def updateData_others(self):
		data = self.getData()
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
		updateOrDrop(data, "url", self.urlCombo.Value)
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
				data = self.getData()
				filled = [
					field
					for field in ("contextPageTitle", "contextPageType", "contextParent")
					if data.get(field)
				]
				if not filled:
					dropDown.setSelectedChoiceKey("general")
				elif len(filled) > 1:
					dropDown.setSelectedChoiceKey("advanced")
				else:
					dropDown.setSelectedChoiceKey(filled[0], default="general")
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

	@guarded
	def onTestCriteria(self, evt):
		self.updateData()
		testCriteria(self.context)
	
	def onPanelActivated(self):
		self.refreshContextMacroChoices()
		super().onPanelActivated()
	
	def onTestCriteria(self, evt):
		self.updateData()
		testCriteria(self.context)
	
	def isValid(self):
		self.updateData()		
		return self.isValid_context() and self.isValid_others()
	
	def isValid_context(self):
		# TODO: Check the syntax of expressions
		return True
	
	def isValid_others(self):
		# TODO: Check the syntax of expressions
		data = self.getData()
		
		if not data:
			gui.messageBox(
				# Translators: An error message on the Criteria Editor
				message=_("You must choose at least one criteria."),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.SetFocus()
			return False
		
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


class StartCriteriaPanel(CriteriaPanel):
	# Translators: The label for a Criteria editor category.
	title = _("Start Criteria")
	
	def getData(self):
		return super().getData()["start"]
	
	def onTestCriteria(self, evt):
		self.updateData()
		testCriteria(self.context, restrictDualNodeTo=="start")


class EndCriteriaPanel(CriteriaPanel):
	# Translators: The label for a Criteria editor category.
	title = _("End Criteria")
	
	def getData(self):
		return super().getData()["end"]
	
	def onTestCriteria(self, evt):
		self.updateData()
		testCriteria(self.context, restrictDualNodeTo="end")


class GesturesPanel(GesturesPanelBase, CriteriaEditorPanel):
	pass


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
		self.prop = prop
		self.listCtrl_update_all()
		if prop.editorType in (EditorType.COMBO, EditorType.TEXT):
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
	categoryClasses = [GeneralPanel, CriteriaPanel, GesturesPanel, PropertiesPanel]
	INITIAL_SIZE = (900, 580)
	
	def __init__(
		self,
		parent,
		*args,
		dualNode=False,
		simpleMode=True,
		**kwargs
	):
		catList = self.categoryClasses = [GeneralPanel]
		if dualNode:
			catList.append(StartCriteriaPanel)
			catList.append(EndCriteriaPanel)
		else:
			catList.append(CriteriaPanel)
		self.simpleMode = simpleMode
		if not simpleMode:
			catList.append(GesturesPanel)
			catList.append(PropertiesPanel)
		super().__init__(parent, *args, **kwargs)
	
	def getData(self):
		# Should always be initialized, as the Rule Editor populates it with at least
		# the index of this Alternative Criteria Set ("criteriaIndex").
		return self.context["data"]["criteria"]
	
	def initData(self, context):
		super().initData(context)
		reload = context.pop("CriteriaEditorFocusOnReload", None)
		if reload is not None:
			catList = self.catListCtrl
			catType = reload.pop("catType")
			if not isinstance(self.currentCategory, catType):
				index = self.categoryClasses.index(catType)
				catList.Select(index)
				catList.Focus(index)  # Triggers category change
			if reload["catList.focus"]:
				catList.SetFocus()
			else:
				self.currentCategory.SetFocus()
	
	def makeSettings(self, settingsSizer):
		super().makeSettings(settingsSizer)
	
	def onCharHook(self, evt):
		# Bound by MultiCategorySettingsDialog.makeSettings
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_F5 and mods in (wx.MOD_NONE, wx.MOD_CONTROL):
			currCat = self.currentCategory
			restrictDualNodeTo = None
			if mods == wx.MOD_NONE:
				if isinstance(currCat, StartCriteriaPanel):
					restrictDualNodeTo = "start"
				elif isinstance(currCat, EndCriteriaPanel):
					restrictDualNodeTo = "end"
			currCat.updateData()
			testCriteria(self.context, restrictDualNodeTo=restrictDualNodeTo)
		elif keycode == wx.WXK_F8 and mods == wx.MOD_NONE:
			from ..inspector import show
			try:
				node = self.context["webModule"].ruleManager.nodeManager.getCaretNode().parent
			except Exception:
				wx.Bell()
				return
			show(parent=self, node=node)
			return
		elif keycode == wx.WXK_F12 and mods == wx.MOD_NONE:
			self.switchToFullEditor()
			return
		super().onCharHook(evt)
	
	def onConvertToDualNode(self, evt):
		convertToDualNode(self.getData())
		self.EndModal(wx.ID_CONVERT)
	
	def onConvertToSingleNode(self, evt):
		if gui.messageBox(
			_(
				#Translators: A prompt for confirmation on the Criteria Set editor
				"""This will delete your End Criteria choices.

Do you want to proceed?"""
			),
			# Translators: The title of prompt for confirmation on the Criteria Set editor
			caption=_("Convert to simple zone (one set of criteria)"),
			style=wx.ICON_WARNING | wx.YES_NO | wx.NO_DEFAULT
		) != wx.YES:
			return
		convertToSingleNode(self.getData())
		self.EndModal(wx.ID_CONVERT)
	
	def switchToFullEditor(self):
		if not self.simpleMode:
			wx.Bell()
			return
		currCat = self.currentCategory
		currCat.updateData()
		self.context["CriteriaEditorFocusOnReload"] = {
			"catType": type(currCat),
			"catList.focus": self.catListCtrl.HasFocus(),
		}
		self.EndModal(wx.ID_MORE)
	
	def _validateAllPanels(self):
		# Ensure all panels are loaded, hence validated
		for catId in range(len(self.categoryClasses)):
			self._getCategoryPanel(catId)
		super()._validateAllPanels()
		
	def _saveAllPanels(self):
		super()._saveAllPanels()
		
		critData = self.getData()
		ruleData = self.context["data"]["rule"]
		
		if set(critData.get("selector", {}).keys()) == {"start", "end"} and (
			any(
				key == "mutation" and value
				for key, value in critData.get("properties", {}).items()
			) or any(
				key == "mutation" and value
				for key, value in ruleData.get("properties", {}).items()
			)
		):
			if gui.messageBox(
				# Translators: A warning message on the Criteria editor
				_(
					'''The "Transform" property is not supported with free zones (two sets of criteria).

Do you want to proceed anyway?
'''
				),
				# Translators: The title of a message dialog
				caption=_("Warning"),
				style=wx.ICON_WARNING | wx.YES_NO | wx.CANCEL | wx.NO_DEFAULT
			) != wx.YES:
				raise ValidationError()  # Cancels closing of the dialog
		
		if createMissingSubModule(self.context, self.getData(), self) is False:
			raise ValidationError()  # Cancels closing of the dialog


def show(context, parent=None):
	if parent is None:
		parent = gui.mainFrame
	data = context.get("data", {}).get("criteria", {})
	simpleMode = supportsSimpleMode(data)
	while True:
		res = showContextualDialog(
			CriteriaEditorDialog,
			context,
			parent,
			dualNode=isDualNode(data),
			simpleMode=simpleMode
		)
		if res == wx.ID_MORE:
			simpleMode = False
		elif res != wx.ID_CONVERT:
			break
	return res == wx.ID_OK
