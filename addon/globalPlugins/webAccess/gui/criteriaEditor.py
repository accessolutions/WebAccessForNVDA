# globalPlugins/webAccess/gui/criteriaEditor.py
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



__version__ = "2021.06.26"
__author__ = "Shirley Noël <shirley.noel@pole-emploi.fr>"


from collections import OrderedDict
import re
import wx
# from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import controlTypes
import inputCore
import gui
from logHandler import log

import addonHandler
from ..ruleHandler import ruleTypes
from ..utils import guarded, updateOrDrop
from . import (
	ContextualMultiCategorySettingsDialog,
	ContextualSettingsPanel,
	DropDownWithHideableChoices,
	InvalidValue,
	ValidationError,
	guiHelper,
	stripAccel,
	stripAccelAndColon,
	ruleEditor,
	properties
)
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


def getSummary(data, indent="", condensed=False):
	parts = []
	subParts = []
	for key, label in list(properties.FIELDS.items()):
		if key not in CriteriaPanel.CONTEXT_FIELDS or key not in data:
			continue
		value = data[key]
		subParts.append("{} {}".format(stripAccel(label), value))
	if not subParts:
		# Translators: A mention on the Criteria summary report
		subParts.append(_("Global - Applies to the whole web module"))
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
		subParts.append("{} {}".format(stripAccel(label), value))
	if subParts:
		if condensed:
			parts.append(", ".join(subParts))
		else:
			parts.extend(subParts)
	subParts = []
	data = data.get("overrides")
	if data:
		for key, label in list(properties.FIELDS.items()):
			if key not in data:
				continue
			value = data[key]
			if value:
				subParts.append("{}:{}".format(stripAccel(label), value))
	if subParts:
		if condensed:
			parts.append("{}:{}".format(
				_("Overrides"),
				", ".join(subParts)
			))
		else:
			parts.append(_("Overrides:"))
			for subPart in subParts:
				parts.append("{}".format(subPart))
	if parts:
		return "{}{}".format(indent, "\n{}".format(indent).join(parts))
	else:
		# Translators: Fail-back criteria summary in rule's criteria panel dialog.
		return "{}{}".format(indent, _("No criteria"))


@guarded
def testCriteria(context):
	ruleData = context["data"]["rule"].copy()
	ruleData["name"] = "tmp"
	ruleData.setdefault("type", ruleTypes.MARKER)
	if "properties" not in ruleData:
		ruleData["properties"] = {}
	ruleData["properties"]["multiple"] = True
	critData = context["data"]["criteria"].copy()
	critData.pop("criteriaIndex", None)
	critData.pop("new", None)
	ruleData["criteria"] = [critData]
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


class GeneralPanel(ContextualSettingsPanel):
	# Translators: The label for a Criteria editor category.
	title = _("General")

	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		def scale(*args):
			return self.scaleSize(args)

		row = 0
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("&Name"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.criteriaName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("&Sequence order"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.sequenceOrderChoice = wx.Choice(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("Technical &notes"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.commentText = wx.TextCtrl(self, size=scale(400, 100), style=wx.TE_MULTILINE)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("&Summary"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.summaryText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		row += 1
		gbSizer.Add((0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		# Translator: The label for a field on the Criteria editor
		item = wx.StaticText(self, label=_("Technical &notes"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add((guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)

		gbSizer.AddGrowableCol(2)

	def initData(self, context):
		self.context = context
		data = context["data"]["criteria"]
		new = data.get("new", False)
		self.sequenceOrderChoice.Clear()
		nbCriteria = len(context["data"]["rule"]["criteria"]) + (1 if new else 0)
		if nbCriteria == 1:
			self.sequenceOrderChoice.Hide()
		else:
			for index in range(nbCriteria):
				self.sequenceOrderChoice.Append(str(index + 1))
			index = data.get("criteriaIndex", nbCriteria + 1)
			self.sequenceOrderChoice.SetSelection(index)
		self.criteriaName.Value = data.get("name", "")
		self.commentText.Value = data.get("comment", "")
		self.refreshSummary()

	def updateData(self, data=None):
		if data is None:
			data = self.context["data"]["criteria"]
		updateOrDrop(data, "name", self.criteriaName.Value)
		updateOrDrop(data, "comment", self.commentText.Value)

	def getSummary(self):
		if not self.context:
			return ""
		data = self.context["data"]["criteria"]
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

	def onSave(self):
		self.updateData()
		data = self.context["data"]["criteria"]
		data["criteriaIndex"] = self.sequenceOrderChoice.Selection


class CriteriaPanel(ContextualSettingsPanel):
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

	def getSummary(self):
		if not self.context:
			return ""
		data = self.context["data"]["criteria"].copy()
		self.updateData(data)
		return getSummary(data)

	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		def scale(*args):
			return self.scaleSize(args)

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
		item = self.contextPageTitleCombo = wx.ComboBox(self)
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
		item = self.textCombo = wx.ComboBox(self)
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
		item = self.idCombo = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["className"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.classNameCombo = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["states"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.statesCombo = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=self.FIELDS["src"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.srcCombo = wx.ComboBox(self)
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
		self.context = context
		data = self.context["data"]["criteria"]
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

	def updateData(self, data=None):
		if data is None:
			data = self.context["data"]["criteria"]
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
		#self.onContextMacroChoice(None)
		super(CriteriaPanel, self).onPanelActivated()

	def onPanelDeactivated(self):
		self.updateData()
		super(CriteriaPanel, self).onPanelDeactivated()

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

	def onSave(self):
		self.updateData()


class OverridesPanel(properties.ListControl):
	"""
	List control properties of the criteria editor for overriden properties
	"""

	# Translators: The label for a Criteria editor category.
	title = _("Overrides")
	context = None
	hidable = []


	def makeSettings(self, settingsSizer):
		super(OverridesPanel, self).makeSettings(settingsSizer)

		# Adding 3 column to the listControl
		self.listCtrl.InsertColumn(2, 'Overrided rule props.', width=215)

		# Getting the grid sizer from the parent
		sizer = self.GetSizer()
		self.btnAddProps = wx.Button(self, label=_("&Add"), size=(325, 30))
		self.hidable.append(self.btnAddProps)
		self.btnDelProps = wx.Button(self, label=_("&Delete"), size=(325, 30))
		self.hidable.append(self.btnDelProps)

		btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
		btn_sizer.Add(self.btnAddProps, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL)
		btn_sizer.Add(self.btnDelProps, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL)
		sizer.Add(btn_sizer, pos=(4, 0), flag=wx.EXPAND)

		self.btnAddProps.Bind(wx.EVT_BUTTON, self.onAddProperties)
		self.btnDelProps.Bind(wx.EVT_BUTTON, self.onDeleteProperties)

	def initData(self, context):
		super(OverridesPanel, self).initData(context)
		self.hidable.clear()
		self.context = context
		self.initPropertiesList(context)
		self.updateData()


	def onAddProperties(self, evt):
		super(OverridesPanel, self).onAddProperties(evt)


	def getListToAppend(self):
		val = super(OverridesPanel, self).getListToAppend()
		if val is not None:
			self.updateOverridenData(self.index, val)
		self.onInitUpdateListCtrl()
		lstIndex = self.listCtrl.GetItemCount()
		self.focusListCtrl(lstIndex - 1, True)


	def onDeleteProperties(self, evt):
		super(OverridesPanel, self).onDeleteProperties(evt)


	def initPropertiesList(self, context):
		super(OverridesPanel, self).initPropertiesList(context)
		dataTypeCrit = self.context["data"]["criteria"]
		typeOverride = dataTypeCrit.get("overrides")
		if typeOverride:
			data = dataTypeCrit["overrides"]
			self.updateListCtrl(data)
		self.onInitUpdateListCtrl()


	def onInitUpdateListCtrl(self):
		self.listCtrl.DeleteAllItems()
		for p in reversed(self.propertiesList):
			if p.get_flag():
				self.updateOverridenData(self.index, p)
		self.setColumunWidthAutoSize()


	def updateOverridenData(self, index, props):
		val = self.updatedStrValues(props.get_value(), props.get_id())
		self.listCtrl.InsertStringItem(index, self.customDisplayLabel(props))
		self.listCtrl.SetStringItem(index, 1, val)
		self.listCtrl.SetStringItem(index, 2, self.isOverrided(props.get_id()))


	def isOverrided(self, idProps):
		"""
		Function updates the overrided values on the criteria editor panel 3rd Column
		"""
		dataRule = self.context["data"]["rule"]
		ruleType = dataRule.get("type")
		ruleProps = dataRule.get("properties")
		typeRule = properties.RULE_TYPE_FIELDS.get(ruleType)
		if ruleType is not None and ruleProps is not None:
			# if idProps in typeRule:
			for key, value in list(ruleProps.items()):
				if idProps in typeRule and idProps == key:
					# Translator: State properties "Not assigned"
					return  self.updatedStrValues(value, idProps) if value or isinstance(self.getPropsObj(idProps), props.ToggleProperty)else _("Not assigned")


	def updateData(self, data = None):
		propertiesMapValue = {}
		data = self.context["data"]["rule"]
		ruleType = data.get("type")
		dataCrit = self.context["data"]["criteria"]
		if ruleType is not None:
			for props in self.propertiesList:
				if props.get_value():
					propertiesMapValue[props.get_id()] = props.get_value()
			if data.get("overrides"):
				del data["overrides"]
			dataCrit["overrides"] = propertiesMapValue

	def onPanelActivated(self):
		super(OverridesPanel, self).onPanelActivated()


	def onSave(self):
		self.updateData()

# gesture override
class GestureOverride(ruleEditor.ActionsPanel):

	title = _("Actions Overrides")

	def makeSettings(self, settingsSizer):
		super(GestureOverride, self).makeSettings(settingsSizer)
		self.autoActionList.Destroy()
		self.labelAutoactions.Destroy()

	def initData(self, context):
		self.context = context
		data = self.context["data"]["criteria"]
		self.gestureMapValue = {}
		self.gestureMapValue = data.get("gesturesOverrides", {}).copy()
		self.updateGesturesList()

	def onPanelActivated(self):
		super(GestureOverride, self).onPanelActivated()

	def onAddGesture(self, evt):
		super(GestureOverride, self).onAddGesture(evt)

	def updateGesturesList(self, newGestureIdentifier=None, focus=False):
		super(GestureOverride, self).updateGesturesList(newGestureIdentifier=None, focus=False)

	def onDeleteGesture(self, evt):
		super(GestureOverride, self).onDeleteGesture(evt)

	def updateData(self, data = None):
		rule = self.context["data"]["rule"]
		data = self.context["data"]["criteria"]
		ruleType = rule.get("type")
		if ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
			data["gesturesOverrides"] = self.gestureMapValue
		else:
			if data.get("gestures"):
				del data["gestures"]

	def onSave(self):
		self.updateData()


class CriteriaEditorDialog(ContextualMultiCategorySettingsDialog):

	# Translators: This is the label for the WebAccess criteria settings dialog.
	title = _("WebAccess Criteria set editor")
	categoryClasses = [GeneralPanel, CriteriaPanel, OverridesPanel, GestureOverride]
	INITIAL_SIZE = (800, 480)
	def makeSettings(self, settingsSizer):
		super(CriteriaEditorDialog, self).makeSettings(settingsSizer)
		idTestCriteria = wx.NewId()
		self.Bind(wx.EVT_MENU, self.onTestCriteria, id=idTestCriteria)
		self.SetAcceleratorTable(wx.AcceleratorTable([
			(wx.ACCEL_NORMAL, wx.WXK_F5, idTestCriteria)
		]))

	def onTestCriteria(self, evt):
		self.updateData()
		testCriteria(self.context)

	def updateData(self):

		for panel in list(self.catIdToInstanceMap.values()):
			panel.updateData()


def show(context, parent=None):
	from . import showContextualDialog
	return showContextualDialog(CriteriaEditorDialog, context, parent)
