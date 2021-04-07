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

from __future__ import absolute_import, division, print_function

__version__ = "2021.04.06"
__author__ = u"Shirley Noël <shirley.noel@pole-emploi.fr>"


from collections import OrderedDict
import re
import wx
# from wx.lib.expando import EVT_ETC_LAYOUT_NEEDED, ExpandoTextCtrl

import controlTypes
import gui
from logHandler import log

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
	stripAccelAndColon
)

try:
	from six import iteritems, text_type
except ImportError:
	# NVDA version < 2018.3
	iteritems = dict.iteritems
	text_type = unicode


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
	return u"".join(buf)


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
				return text_type(key)
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
				return text_type(key)
		if raiseOnError:
			raise ValidationError(value)
		return value
	return translateExprValues(expr, translate)


def getSummary(data, indent="", condensed=False):
	parts = []
	subParts = []
	for key, label in CriteriaPanel.FIELDS.items():
		if key not in CriteriaPanel.CONTEXT_FIELDS or key not in data:
			continue
		value = data[key]
		subParts.append(u"{} {}".format(stripAccel(label), value))
	if not subParts:
		# Translators: A mention on the Criteria summary report
		subParts.append(_("Global - Applies to the whole web module"))
	if condensed:
		parts.append(u", ".join(subParts))
	else:
		parts.extend(subParts)
	subParts = []
	for key, label in CriteriaPanel.FIELDS.items():
		if key in CriteriaPanel.CONTEXT_FIELDS or key not in data:
			continue
		value = data[key]
		if not isinstance(value, InvalidValue):
			if key == "role":
				value = translateRoleIdToLbl(value)
			elif key == "states":
				value = translateStatesIdToLbl(value)
		subParts.append(u"{} {}".format(stripAccel(label), value))
	if subParts:
		if condensed:
			parts.append(u", ".join(subParts))
		else:
			parts.extend(subParts)
	subParts = []
	for key, label in OverridesPanel.FIELDS.items():
		if key not in data:
			continue
		value = data[key]
		subParts.append(u"{} {}".format(stripAccel(label), value))
	if subParts:
		if condensed:
			parts.append(u"{} {}".format(
				_("Overrides:"),
				u", ".join(subParts)
			))
		else:
			for subPart in subParts:
				parts.append(u"{} {}".format(_("Overrides"), subPart))
	if parts:
		return u"{}{}".format(indent, u"\n{}".format(indent).join(parts))
	else:
		# Translators: Fail-back criteria summary in rule's criteria panel dialog.
		return u"{}{}".format(indent, _("No criteria"))


@guarded
def testCriteria(context):
	ruleData = context["data"]["rule"].copy()
	ruleData["name"] = "tmp"
	ruleData.setdefault("type", ruleTypes.MARKER)
	ruleData["multiple"] = True
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
# 		item = self.summaryText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
# 		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
# 		item.Bind(wx.EVT_TEXT_ENTER, lambda evt: self.Parent.Parent.ProcessEvent(wx.CommandEvent(
# 			wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK
# 		)))
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
# 		item = self.commentText = ExpandoTextCtrl(self, style=wx.TE_MULTILINE)
# 		item.Bind(EVT_ETC_LAYOUT_NEEDED, lambda evt: self._sendLayoutUpdatedEvent())
		item = self.commentText = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_RICH)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)
		
		gbSizer.AddGrowableCol(2)
	
	def initData(self, context):
		self.context = context
		data = context["data"]["criteria"]
		new = data.get("new", False)
		
		# TODO: Hide Sequence Order when there are only one choice
		self.sequenceOrderChoice.Clear()
		nbCriteria = len(context["data"]["rule"]["criteria"]) + (1 if new else 0)
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
		for panel in self.Parent.Parent.catIdToInstanceMap.values():
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
		("contextPageTitle", pgettext("webAccess.ruleCriteria", u"Page &title:")),
		# Translator: The label for a Rule Criteria field
		("contextPageType", pgettext("webAccess.ruleCriteria", u"Page t&ype")),
		# Translator: The label for a Rule Criteria field
		("contextParent", pgettext("webAccess.ruleCriteria", u"&Parent element")),
		# Translator: The label for a Rule Criteria field
		("text", pgettext("webAccess.ruleCriteria", u"&Text:")),
		# Translator: The label for a Rule Criteria field
		("role", pgettext("webAccess.ruleCriteria", u"&Role:")),
		# Translator: The label for a Rule Criteria field
		("tag", pgettext("webAccess.ruleCriteria", u"T&ag:")),
		# Translator: The label for a Rule Criteria field
		("id", pgettext("webAccess.ruleCriteria", u"&ID:")),
		# Translator: The label for a Rule Criteria field
		("className", pgettext("webAccess.ruleCriteria", u"&Class:")),
		# Translator: The label for a Rule Criteria field
		("states", pgettext("webAccess.ruleCriteria", u"&States:")),
		# Translator: The label for a Rule Criteria field
		("src", pgettext("webAccess.ruleCriteria", u"Ima&ge source:")),
		# Translator: The label for a Rule Criteria field
		("relativePath", pgettext("webAccess.ruleCriteria", u"R&elative path:")),
		# Translator: The label for a Rule Criteria field
		("index", pgettext("webAccess.ruleCriteria", u"Inde&x:")),
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
		item = wx.StaticText(self, label=_("Contexte:"))
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
		for field, show in fields.items():
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


# todo: make this panel
class OverridesPanel(ContextualSettingsPanel):
	# Translators: The label for a Criteria editor category.
	title = _("Overrides")
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
# 		# Translator: Multiple results checkbox label for the rule dialog's properties panel.
# 		("multiple", pgettext("webAccess.ruleProperties", u"&Multiple results")),
# 		# Translator: Activate form mode checkbox label for the rule dialog's properties panel.
# 		("formMode", pgettext("webAccess.ruleProperties", u"Activate &form mode")),
# 		# Translator: Skip page down checkbox label for the rule dialog's properties panel.
# 		("skip", pgettext("webAccess.ruleProperties", u"S&kip with Page Down")),
# 		# Translator: Speak rule name checkbox label for the rule dialog's properties panel.
# 		("sayName", pgettext("webAccess.ruleProperties", u"&Speak rule name")),
		# Translator: Custom name input label for the rule dialog's properties panel.
		("customName", pgettext("webAccess.ruleProperties", u"Custom &name:")),
		# Label depends on rule type)
		("customValue", None),
# 		# Translator: Transform select label for the rule dialog's properties panel.
# 		("mutation", pgettext("webAccess.ruleProperties", u"&Transform:")),
	))
	
	RULE_TYPE_FIELDS = OrderedDict((
		(ruleTypes.PAGE_TITLE_1, ("customValue",)),
		(ruleTypes.PAGE_TITLE_2, ("customValue",)),
		(ruleTypes.ZONE, (
# 			"formMode",
# 			"skip",
# 			"sayName",
			"customName",
			"customValue",
# 			"mutation"
		)),
		(ruleTypes.MARKER, (
# 			"multiple",
# 			"formMode",
# 			"skip",
# 			"sayName",
			"customName",
			"customValue",
# 			"mutation"
		)),
	))
	
	@staticmethod
	def getAltFieldLabel(ruleType, key, default=None):
		if key == "customValue":
			if ruleType in (ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return pgettext("webAccess.ruleProperties", u"Custom page &title:")
			elif ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return pgettext("webAccess.ruleProperties", u"Custom messa&ge:")
		return default
	
	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		def scale(*args):
			return tuple([
				self.scaleSize(arg) if arg > 0 else arg
				for arg in args
			])
		
		hidable = self.hidable = {"spacers": []}
		
		row = 0
		# Translators: Displayed when the selected rule type doesn't support any property
		item = self.noPropertiesLabel = wx.StaticText(self, label=_("No property available for the selected rule type"))
		item.Hide()
		hidable["noProperties"] = [item]
		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

# 		row += 1
# 		item = self.multipleCheckBox = wx.CheckBox(self, label=self.FIELDS["multiple"])
# 		item.Hide()
# 		hidable["multiple"] = [item]
# 		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
# 		
# 		row += 1
# 		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
# 		item.Show(False)
# 		hidable["spacers"].append(item)
# 		
# 		row += 1
# 		item = self.formModeCheckBox = wx.CheckBox(self, label=self.FIELDS["formMode"])
# 		item.Hide()
# 		hidable["formMode"] = [item]
# 		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
# 		
# 		row += 1
# 		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
# 		item.Show(False)
# 		hidable["spacers"].append(item)
# 		
# 		row += 1
# 		item = self.skipCheckBox = wx.CheckBox(self, label=self.FIELDS["skip"])
# 		item.Hide()
# 		hidable["skip"] = [item]
# 		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
# 		
# 		row += 1
# 		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
# 		item.Show(False)
# 		hidable["spacers"].append(item)
# 		
# 		row += 1
# 		item = self.sayNameCheckBox = wx.CheckBox(self, label=self.FIELDS["sayName"])
# 		item.Hide()
# 		hidable["sayName"] = [item]
# 		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)
# 		
# 		row += 1
# 		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
# 		item.Show(False)
# 		hidable["spacers"].append(item)
		
		row += 1
		items = hidable["customName"] = []
		item = self.customNameLabel = wx.StaticText(self, label=self.FIELDS["customName"])
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item.Show(False)
		items.append(item)
		item = self.customNameText = wx.TextCtrl(self, size=scale(350, -1))
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		item.Show(False)
		hidable["spacers"].append(item)
		
		row += 1
		items = hidable["customValue"] = []
		item = self.customValueLabel = wx.StaticText(self, label=self.FIELDS["customValue"] or "")
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item.Show(False)
		items.append(item)
		item = self.customValueText = wx.TextCtrl(self, size=scale(350, -1))
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
# 		row += 1
# 		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
# 		item.Show(False)
# 		hidable["spacers"].append(item)
# 		
# 		row += 1
# 		items = hidable["mutation"] = []
# 		item = self.mutationLabel = wx.StaticText(self, label=self.FIELDS["mutation"])
# 		item.Hide()
# 		items.append(item)
# 		gbSizer.Add(item, pos=(row, 0))
# 		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
# 		item.Show(False)
# 		items.append(item)
# 		item = self.mutationCombo = wx.ComboBox(self, style=wx.CB_READONLY)
# 		item.Hide()
# 		items.append(item)
# 		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		gbSizer.AddGrowableCol(2)
		
	def initData(self, context):
		self.context = context
		for items in self.hidable.values():
			for item in items:
				item.Show(False)
		if not context:
			for item in self.hidable["noProperties"]:
				item.Show()
			return
		data = context["data"]["criteria"]
		
		ruleType = context["data"]["rule"].get("type")
		fields = self.RULE_TYPE_FIELDS.get(ruleType, {})
		hidable = self.hidable
		
		if not fields:
			for item in hidable["noProperties"]:
				item.Show(True)
				return
		
		for field in fields:
			if field in hidable:
				for item in hidable[field]:
					item.Show(True)
		
		for item in hidable["spacers"][:len(fields) - 1]:
			item.Show(True)
		
# 		self.multipleCheckBox.Value = data.get("multiple", False)
# 		self.formModeCheckBox.Value = data.get("formMode", False)
# 		self.skipCheckBox.Value = data.get("skip", False)
# 		self.sayNameCheckBox.Value = data.get("sayName", True)
		self.customNameText.Value = data.get("customName", "")
		self.customValueLabel.Label = self.getAltFieldLabel(ruleType, "customValue")
		self.customValueText.Value = data.get("customValue", "")
		
# 		self.mutationCombo.Clear()
# 		self.mutationCombo.Append(
# 			# Translators: The label when there is no control mutation.
# 			pgettext("webAccess.controlMutation", "<None>"),
# 			""
# 		)
# 		for id in MUTATIONS_BY_RULE_TYPE.get(ruleType, []):
# 			label = mutationLabels.get(id)
# 			if label is None:
# 				log.error("No label for mutation id: {}".format(id))
# 				label = id
# 			self.mutationCombo.Append(label, id)
# 		mutation = data.get("mutation") # if show else None
# 		if mutation:
# 			for index in range(1, self.mutationCombo.Count + 1):
# 				id = self.mutationCombo.GetClientData(index)
# 				if id == mutation:
# 					break
# 			else:
# 				# Allow to bypass mutation choice by rule type
# 				label = mutationLabels.get(id)
# 				if label is None:
# 					log.warning("No label for mutation id: {}".format(id))
# 					label = id
# 				self.mutationCombo.Append(label, id)
# 				index += 1
# 		else:
# 			index = 0
# 		self.mutationCombo.SetSelection(index)
	
	def updateData(self, data=None):
		if data is None:
			data = self.context["data"]["criteria"]
		data = self.context["data"]["rule"]
# 		updateOrDrop(data, "multiple", str(self.multipleCheckBox.Value))
# 		updateOrDrop(data, "formMode", str(self.formModeCheckBox.Value))
# 		updateOrDrop(data, "skip", str(self.skipCheckBox.Value))
# 		updateOrDrop(data, "sayName", str(self.sayNameCheckBox.Value))
		updateOrDrop(data, "customName", self.customNameText.Value)
		updateOrDrop(data, "customValue", self.customValueText.Value)
# 		if self.mutationCombo.Selection > 0:
# 			data["mutation"] = self.mutationCombo.GetClientData(self.mutationCombo.Selection)
	
	def onSave(self):
		self.updateData()
		data = self.context["data"]["rule"]
		ruleType = data["type"]
		showedFields = self.RULE_TYPE_FIELDS.get(ruleType, {})
		for field in self.FIELDS.keys():
			if field not in showedFields and data.get(field):
				del data[field]


class CriteriaEditorDialog(ContextualMultiCategorySettingsDialog):

	# Translators: This is the label for the WebAccess criteria settings dialog.
	title = _("WebAccess Criteria set editor")
	categoryClasses = [GeneralPanel, CriteriaPanel, OverridesPanel]
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
		for panel in self.catIdToInstanceMap.values():
			panel.updateData()


def show(context, parent=None):
	from . import showContextualDialog
	return showContextualDialog(CriteriaEditorDialog, context, parent)
