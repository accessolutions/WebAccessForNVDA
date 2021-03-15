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

__version__ = "2021.03.13"
__author__ = u"Shirley Noël <shirley.noel@pole-emploi.fr>"


import wx
import re
import gui
from collections import OrderedDict
from ..ruleHandler import ruleTypes
from ..gui import ruleEditor
import controlTypes
from logHandler import log

from .. import guarded
from . import (
	MultiCategorySettingsDialogWithContext,
	SettingsPanelWithContext,
	guiHelper
)

try:
	from six import iteritems, text_type
except ImportError:
	# NVDA version < 2018.3
	iteritems = dict.iteritems
	text_type = unicode


def setIfNotEmpty(dic, key, value):
	if value and value.strip():
		dic[key] = value
		return
	elif dic.get(key):
		del dic[key]


LABEL_ACCEL = re.compile("&(?!&)")
"""
Compiled pattern used to strip accelerator key indicators from labels.
"""

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


def translateStatesLblToId(expr):
	def translate(value):
		for key, candidate in iteritems(controlTypes.stateLabels):
			if candidate == value:
				return text_type(key)
		return value
	return translateExprValues(expr, translate)


def translateStatesIdToLbl(expr):
	def translate(value):
		try:
			return controlTypes.stateLabels[int(value)]
		except (KeyError, ValueError):
			return value
	return translateExprValues(expr, translate)


def translateRoleLblToId(expr):
	def translate(value):
		for key, candidate in iteritems(controlTypes.roleLabels):
			if candidate == value:
				return text_type(key)
		return value
	return translateExprValues(expr, translate)


def stripAccel(label):
	return LABEL_ACCEL.sub("", label)


def stripAccelAndColon(label):
	return stripAccel(label).rstrip(":").rstrip()


class GeneralPanel(SettingsPanelWithContext):
	# Translators: This is the label for the criteria general panel.
	title = _("General")
	
	@classmethod
	def getSummary(cls, data):
		summary = ""
		context = ContextPanel.getSummary(data)
		lines = context.split(u"\n")
		if len(lines) > 1:
			context = u"\n" + u"\n".join([u"  {}".format(line) for line in lines])
		else:
			context = u" " + context
		# Translators: A heading in the summary of a criteria set
		summary = _("Contexte :") + context + u"\n"
		criteria = CriteriaPanel.getSummary(data)
		lines = criteria.split(u"\n")
		if len(lines) > 1:
			criteria = u"\n" + u"\n".join([u"  {}".format(line) for line in lines])
		else:
			criteria = u" " + criteria
		# Translators: A heading in the summary of a criteria set
		summary += _("Criteria :") + criteria
		return summary
	
	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		def scale(*args):
			return self.scaleSize(args)
		
		row = 0
		# Translators: The label for a field in the Criteria Editor
		item = wx.StaticText(self, label=_("&Name"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.criteriaName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a field in the Criteria Editor
		item = wx.StaticText(self, label=_("&Sequence order"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.criteriaOrder = wx.Choice(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a field in the Criteria Editor
		item = wx.StaticText(self, label=_("Technical &notes"))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.criteriaComment = wx.TextCtrl(self, size=scale(400, 200), style=wx.TE_MULTILINE)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row)
		
		gbSizer.AddGrowableCol(2)
	
	def initData(self, context):
		self.context = context
		data = context["data"]["criteria"]
		new = data.get("new", False)
		
		self.criteriaOrder.Clear()
		log.warning("data: {}".format(context["data"]["rule"]))
		nbCriteria = len(context["data"]["rule"]["criteria"]) + (1 if new else 0)
		for index in range(nbCriteria):
			self.criteriaOrder.Append(str(index + 1))
		index = data.get("criteriaIndex", nbCriteria + 1)
		self.criteriaOrder.SetSelection(index)
		self.criteriaName.Value = data.get("name", "")
		self.criteriaComment.Value = data.get("comment", "")
	
	def onSave(self):
		data = self.context["data"]["criteria"]
		data["criteriaIndex"] = self.criteriaOrder.Selection
		setIfNotEmpty(data, "name", self.criteriaName.Value)
		setIfNotEmpty(data, "comment", self.criteriaComment.Value)


class ContextPanel(SettingsPanelWithContext):
	# Translators: This is the label for the criteria context panel.
	title = _("Context")
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		# Translator: Page title field label on the criteria set's context panel.
		("contextPageTitle", pgettext("webAccess.ruleContext", u"Page &title")),
		# Translator: Page type field label on the criteria set's context panel.
		("contextPageType", pgettext("webAccess.ruleContext", u"Page t&ype")),
		# Translator: Parent element field label on the criteria set's context panel.
		("contextParent", pgettext("webAccess.ruleContext", u"&Parent element")),
	))
	
	@classmethod
	def getSummary(cls, data):
		parts = []
		for key, label in cls.FIELDS.items():
			if key in data:
				parts.append(u"{} {}".format(stripAccel(label), data[key]))
		if parts:
			return "\n".join(parts)
		else:
			# Translators: Fail-back context summary in criteria set's context panel.
			return _("Global - Applies to the whole web module.")
	
	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		def scale(*args):
			return self.scaleSize(args)
		
		self.hidable = {}
		
		row = 0
		items = self.hidable["pageTitle"] = []
		item = wx.StaticText(self, label=self.FIELDS["contextPageTitle"])
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item.Show(False)
		items.append(item)
		item = self.pageTitleContext = wx.ComboBox(self)
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		item.Show(False)
		items.append(item)
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["contextPageType"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.pageTypeContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["contextParent"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.parentElementContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)		

	def initData(self, context):
		self.context = context
		data = self.context["data"]["criteria"]
		mgr = context["webModule"].ruleManager if "webModule" in context else None
		node = mgr.nodeManager.getCaretNode() if mgr else None
		
		ruleType = context["data"]["rule"].get("type")
		show = ruleType not in (ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2)
		for item in self.hidable["pageTitle"]:
			item.Show(show)
		
		self.pageTitleContext.Set([context.get("pageTitle")])
		self.pageTitleContext.Value = data.get("contextPageTitle", "")
		if mgr:
			self.pageTypeContext.Set(mgr.getPageTypes())
		self.pageTypeContext.Value = data.get("contextPageType", "")

		parents = []
		for result in mgr.getResults() if mgr else []:
			rule = result.rule
			if (
				rule.type in (ruleTypes.PARENT, ruleTypes.ZONE)
				and node in result.node
			):
				parents.insert(0, rule.name)
		self.parentElementContext.Set(parents)
		self.parentElementContext.Value = data.get("contextParent", "")
	
	def onSave(self):
		data = self.context["data"]["criteria"]
		setIfNotEmpty(data, "contextPageTitle", self.pageTitleContext.Value)
		setIfNotEmpty(data, "contextPageType", self.pageTypeContext.Value)
		setIfNotEmpty(data, "contextParent", self.parentElementContext.Value)


class CriteriaPanel(SettingsPanelWithContext):
	# Translators: This is the label for the criteria panel.
	title = _("Criteria")
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		("name", pgettext("webAccess.Rule.Criteria", u"&Name:")),
		# Translator: Page title field label on the criteria set's context panel.
		("contextPageTitle", pgettext("webAccess.ruleContext", u"Page &title")),
		# Translator: Page type field label on the criteria set's context panel.
		("contextPageType", pgettext("webAccess.ruleContext", u"Page t&ype")),
		# Translator: Parent element field label on the criteria set's context panel.
		("contextParent", pgettext("webAccess.ruleContext", u"&Parent element")),
		# Translator: Text criteria field label on the rule's criteria panel dialog.
		("text", pgettext("webAccess.ruleCriteria", u"&Text:")),
		# Translator: Role criteria field label on the rule's criteria panel dialog.
		("role", pgettext("webAccess.ruleCriteria", u"&Role:")),
		# Translator: Tag criteria field label on the rule's criteria panel dialog.
		("tag", pgettext("webAccess.ruleCriteria", u"T&ag:")),
		# Translator: ID criteria field label on the rule's criteria panel dialog.
		("id", pgettext("webAccess.ruleCriteria", u"&ID:")),
		# Translator: Class criteria field label on the rule's criteria panel dialog.
		("className", pgettext("webAccess.ruleCriteria", u"&Class:")),
		# Translator: States criteria field label on the rule's criteria panel dialog.
		("states", pgettext("webAccess.ruleCriteria", u"&States:")),
		# Translator: Images source criteria field label on the rule's criteria panel dialog.
		("src", pgettext("webAccess.ruleCriteria", u"Ima&ge source:")),
		# Translator: Relative path criteria field label on the rule's criteria panel dialog.
		("relativePath", pgettext("webAccess.ruleCriteria", u"R&elative path:")),
		# Translator: Index criteria field label on the rule's criteria panel dialog.
		("index", pgettext("webAccess.ruleCriteria", u"Inde&x:")),
	))
	
	@classmethod
	def getSummary(cls, data):
		parts = []
		for key, label in cls.FIELDS.items():
			if key in data:
				value = data[key]
				if key == "role":
					value = translateRoleIdToLbl(value)
				elif key == "states":
					value = translateStatesIdToLbl(value)
				parts.append(u"{} {}".format(stripAccel(label), value))
		if parts:
			return "\n".join(parts)
		else:
			# Translators: Fail-back criteria summary in rule's criteria panel dialog.
			return _("No criteria")
	
	def makeSettings(self, settingsSizer):
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		def scale(*args):
			return self.scaleSize(args)
		
		hidable = self.hidable = {}
		
		row = 0
		item = wx.StaticText(self, label=self.FIELDS["text"])
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.textContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["role"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.roleContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["tag"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.tagContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["id"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.idContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["className"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.classNameContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["states"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.statesContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["src"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.srcContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["relativePath"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.relativePathContext = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["index"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.indexContext = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a button in the Criteria Editor dialog
		item = wx.Button(self, label=_("&Test these criteria"))
		item.Bind(wx.EVT_BUTTON, self.onTestCriteria)
		gbSizer.Add(item, pos=(row, 0), span=(1, 3))
		
		gbSizer.AddGrowableCol(2)
	
	def initData(self, context):
		self.context = context
		data = self.context["data"]["criteria"]
		mgr = context["webModule"].ruleManager if "webModule" in context else None
		
		if mgr and mgr.nodeManager:
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
			# todo: actually there are empty choices created
			while node is not None:
				roleChoices.append(controlTypes.roleLabels.get(node.role, "") or "")
				tagChoices.append(node.tag or "")
				idChoices.append(node.id or "")
				classChoices.append(node.className or "")
				statesChoices.append(getStatesLblExprForSet(node.states) or "")
				srcChoices.append(node.src or "")
				node = node.parent
			
			self.textContext.Set(textChoices)
			self.roleContext.Set(roleChoices)
			self.tagContext.Set(tagChoices)
			self.idContext.Set(idChoices)
			self.classNameContext.Set(classChoices)
			self.statesContext.Set(statesChoices)
			self.srcContext.Set(srcChoices)
		
		self.textContext.Value = data.get("text", "")
		self.roleContext.Value = translateRoleIdToLbl(data.get("role", ""))
		self.tagContext.Value = data.get("tag", "")
		self.idContext.Value = data.get("id", "")
		self.classNameContext.Value = data.get("className", "")
		self.statesContext.Value = translateStatesIdToLbl(data.get("states", ""))
		self.srcContext.Value = data.get("src", "")
		self.relativePathContext.Value = str(data.get("relativePath", ""))
		self.indexContext.Value = str(data.get("index", ""))
		
	def isValid(self):
		self._isValid = False
		roleLblExpr = self.roleContext.Value
		if roleLblExpr:
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
				self.roleContext.SetFocus()
				return False
			roleIdExpr = translateRoleLblToId(roleLblExpr)
			if not EXPR_INT.match(roleIdExpr):
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't match any known identifier
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["role"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.roleContext.SetFocus()
				return False
			
		statesLblExpr = self.statesContext.Value
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
				self.statesContext.SetFocus()
				return False
			statesIdExpr = translateStatesLblToId(statesLblExpr)
			if not EXPR_INT.match(statesIdExpr):
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't match any known identifier
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["states"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.statesContext.SetFocus()
				return False
			
		index = self.indexContext.Value
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
				self.indexContext.SetFocus()
				return False
		self._isValid = True
		return True
		
	def onSave(self):
		assert getattr(self, "_isValid", False)
		data = self.context["data"]["criteria"]
		setIfNotEmpty(data, "text", self.textContext.Value)
		setIfNotEmpty(data, "tag", self.tagContext.Value)
		setIfNotEmpty(data, "id", self.idContext.Value)
		setIfNotEmpty(data, "className", self.classNameContext.Value)
		setIfNotEmpty(data, "src", self.srcContext.Value)
		setIfNotEmpty(data, "relativePath", self.relativePathContext.Value)
		
		roleLblExpr = self.roleContext.Value
		if roleLblExpr:
			roleIdExpr = translateRoleLblToId(roleLblExpr)
			data["role"] = roleIdExpr
		else:
			data.pop("role", None)
			
		statesLblExpr = self.statesContext.Value
		if statesLblExpr:
			statesIdExpr = translateStatesLblToId(statesLblExpr)
			data["states"] = statesIdExpr
		else:
			data.pop("states", None)
			
		index = self.indexContext.Value
		if index.strip():
			try:
				index = int(index)
			except Exception:
				index = 0
			if index > 0:
				data["index"] = index
			else:
				data.pop("index", None)
		else:
			data.pop("index", None)
	
	@guarded
	def onTestCriteria(self, evt):
		if self.isValid():
			self.onSave()
		else:
			return
		context = self.context
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
		gui.messageBox(message, caption=_("Criteria test"), parent=self)


class CriteriaPanel_(SettingsPanelWithContext):
	# Translators: This is the label for the criteria panel.
	title = _("Criteria")
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		("name", pgettext("webAccess.Rule.Criteria", u"&Name:")),
		# Translator: Page title field label on the criteria set's context panel.
		("contextPageTitle", pgettext("webAccess.ruleContext", u"Page &title")),
		# Translator: Page type field label on the criteria set's context panel.
		("contextPageType", pgettext("webAccess.ruleContext", u"Page t&ype")),
		# Translator: Parent element field label on the criteria set's context panel.
		("contextParent", pgettext("webAccess.ruleContext", u"&Parent element")),
		# Translator: Text criteria field label on the rule's criteria panel dialog.
		("text", pgettext("webAccess.ruleCriteria", u"&Text:")),
		# Translator: Role criteria field label on the rule's criteria panel dialog.
		("role", pgettext("webAccess.ruleCriteria", u"&Role:")),
		# Translator: Tag criteria field label on the rule's criteria panel dialog.
		("tag", pgettext("webAccess.ruleCriteria", u"T&ag:")),
		# Translator: ID criteria field label on the rule's criteria panel dialog.
		("id", pgettext("webAccess.ruleCriteria", u"&ID:")),
		# Translator: Class criteria field label on the rule's criteria panel dialog.
		("className", pgettext("webAccess.ruleCriteria", u"&Class:")),
		# Translator: States criteria field label on the rule's criteria panel dialog.
		("states", pgettext("webAccess.ruleCriteria", u"&States:")),
		# Translator: Images source criteria field label on the rule's criteria panel dialog.
		("src", pgettext("webAccess.ruleCriteria", u"Ima&ge source:")),
		# Translator: Relative path criteria field label on the rule's criteria panel dialog.
		("relativePath", pgettext("webAccess.ruleCriteria", u"R&elative path:")),
		# Translator: Index criteria field label on the rule's criteria panel dialog.
		("index", pgettext("webAccess.ruleCriteria", u"Inde&x:")),
	))
	
	@classmethod
	def getSummary(cls, data):
		parts = []
		for key, label in cls.FIELDS.items():
			if key in data:
				value = data[key]
				if key == "role":
					value = translateRoleIdToLbl(value)
				elif key == "states":
					value = translateStatesIdToLbl(value)
				parts.append(u"{} {}".format(stripAccel(label), value))
		if parts:
			return "\n".join(parts)
		else:
			# Translators: Fail-back criteria summary in rule's criteria panel dialog.
			return _("No criteria")
	
	def makeSettings(self, settingsSizer):
		self.settingsSizer = gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		#settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		
		def scale(*args):
			return self.scaleSize(args)
		
		hidable = self.hidable = {}
		
		row = 0
		item = wx.StaticText(self, label=_("Contexte:"))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		self.contextMacroChoices = OrderedDict((
			("none", [True, _("Global - Applies to the whole web module")]),
			("pageTitle", [True, _("Page title - Applies only to pages with the given title")]),
			("pageType", [True, _("Page type - Applies only to pages with the given type")]),
			("parent", [True, _("Parent element - Applies only within the results of another rule")]),
			("all", [True, _("Advanced")]),
		))
		item = self.contextMacroCombo = wx.ComboBox(self, style=wx.CB_READONLY)
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
		item = self.textContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["role"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.roleContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["tag"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.tagContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["id"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.idContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["className"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.classNameContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["states"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.statesContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["src"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.srcContext = wx.ComboBox(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["relativePath"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.relativePathContext = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		item = wx.StaticText(self, label=self.FIELDS["index"])
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.indexContext = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		
		row += 1
		# Translators: The label for a button in the Criteria Editor dialog
		item = wx.Button(self, label=_("&Test these criteria"))
		item.Bind(wx.EVT_BUTTON, self.onTestCriteria)
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
			
			self.textContext.Set(textChoices)
			self.roleContext.Set(roleChoices)
			self.tagContext.Set(tagChoices)
			self.idContext.Set(idChoices)
			self.classNameContext.Set(classChoices)
			self.statesContext.Set(statesChoices)
			self.srcContext.Set(srcChoices)
		
		self.refreshContextMacroChoices()
		if data.get("contextPageTitle") and data.get("contextPageType") and data.get("contextParent"):
			self.contextMacroCombo.Selection = 4
		elif data.get("contextPageTitle"):
			self.contextMacroCombo.Selection = 1
		elif data.get("contextPageType"):
			self.contextMacroCombo.Selection = 2
		elif data.get("contextParent"):
			self.contextMacroCombo.Selection = 3
		else:
			self.contextMacroCombo.Selection = 0
		self.onContextMacroChoice(None)
		self.contextPageTitleCombo.Value = data.get("contextPageTitle", "")
		self.contextPageTypeCombo.Value = data.get("contextPageType", "")
		self.contextParentCombo.Value = data.get("contextParent", "")
		
		self.textContext.Value = data.get("text", "")
		self.roleContext.Value = translateRoleIdToLbl(data.get("role", ""))
		self.tagContext.Value = data.get("tag", "")
		self.idContext.Value = data.get("id", "")
		self.classNameContext.Value = data.get("className", "")
		self.statesContext.Value = translateStatesIdToLbl(data.get("states", ""))
		self.srcContext.Value = data.get("src", "")
		self.relativePathContext.Value = str(data.get("relativePath", ""))
		self.indexContext.Value = str(data.get("index", ""))
		
	def isValid(self):
		self._isValid = False
		roleLblExpr = self.roleContext.Value
		if roleLblExpr:
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
				self.roleContext.SetFocus()
				return False
			roleIdExpr = translateRoleLblToId(roleLblExpr)
			if not EXPR_INT.match(roleIdExpr):
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't match any known identifier
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["role"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.roleContext.SetFocus()
				return False
			
		statesLblExpr = self.statesContext.Value
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
				self.statesContext.SetFocus()
				return False
			statesIdExpr = translateStatesLblToId(statesLblExpr)
			if not EXPR_INT.match(statesIdExpr):
				gui.messageBox(
					message=(
						# Translators: Error message when the field doesn't match any known identifier
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["states"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.statesContext.SetFocus()
				return False
			
		index = self.indexContext.Value
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
				self.indexContext.SetFocus()
				return False
		self._isValid = True
		return True
	
	def onPanelActivated(self):
		self.refreshContextMacroChoices()
		self.onContextMacroChoice(None)
		super(CriteriaPanel_, self).onPanelActivated()
	
	def onSave(self):
		assert getattr(self, "_isValid", False)
		data = self.context["data"]["criteria"]
		setIfNotEmpty(data, "text", self.textContext.Value)
		setIfNotEmpty(data, "tag", self.tagContext.Value)
		setIfNotEmpty(data, "id", self.idContext.Value)
		setIfNotEmpty(data, "className", self.classNameContext.Value)
		setIfNotEmpty(data, "src", self.srcContext.Value)
		setIfNotEmpty(data, "relativePath", self.relativePathContext.Value)
		
		roleLblExpr = self.roleContext.Value
		if roleLblExpr:
			roleIdExpr = translateRoleLblToId(roleLblExpr)
			data["role"] = roleIdExpr
		else:
			data.pop("role", None)
			
		statesLblExpr = self.statesContext.Value
		if statesLblExpr:
			statesIdExpr = translateStatesLblToId(statesLblExpr)
			data["states"] = statesIdExpr
		else:
			data.pop("states", None)
			
		index = self.indexContext.Value
		if index.strip():
			try:
				index = int(index)
			except Exception:
				index = 0
			if index > 0:
				data["index"] = index
			else:
				data.pop("index", None)
		else:
			data.pop("index", None)
	
	def refreshContextMacroChoices(self):
		if not getattr(self, "context", None):
			self.contextMacroCombo.Clear()
			return
		context = self.context
		choices = self.contextMacroChoices
		ruleType = context["data"]["rule"].get("type")
		choices["pageTitle"][0] = ruleType not in (
			ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2
		)
		self.contextMacroCombo.Set(
			[label for field, (show, label) in choices.items() if show]
		)
	
	def onContextMacroChoice(self, evt):
		sel = self.contextMacroCombo.Selection
		fields = {
			"contextPageTitle": False,
			"contextPageType": False,
			"contextParent": False
		}
		try:
			choice = [
				key
				for key, value in self.contextMacroChoices.items()
				if value[0]
			][sel]
		except IndexError:
			raise IndexError("Unexpected selection: {}".format(sel))
		if choice == "none":
			pass
		elif choice == "pageTitle":
			fields["contextPageTitle"] = True
		elif choice == "pageType":
			fields["contextPageType"] = True
		elif choice == "parent":
			fields["contextParent"] = True
		elif choice == "all":
			fields["contextPageTitle"] = True
			fields["contextPageType"] = True
			fields["contextParent"] = True
		else:
			raise ValueError("Unexpected selection: {}".format(sel))
		
		for field, show in fields.items():
			for item in self.hidable[field]:
				item.Show(show)
		
		self._sendLayoutUpdatedEvent()
	
	@guarded
	def onTestCriteria(self, evt):
		if self.isValid():
			self.onSave()
		else:
			return
		context = self.context
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
		gui.messageBox(message, caption=_("Criteria test"), parent=self)


# todo: make this panel
class OverridesPanes(SettingsPanelWithContext):
	# Translators: This is the label for the overrides's panel.
	title = _("Overrides")


class CriteriaEditorDialog(MultiCategorySettingsDialogWithContext):

	# Translators: This is the label for the WebAccess criteria settings dialog.
	title = _("WebAccess Criteria set editor")
	# categoryClasses = [GeneralPanel, ContextPanel, CriteriaPanel]
	categoryClasses = [GeneralPanel, CriteriaPanel_]
	INITIAL_SIZE = (800, 480)


def show(context, parent=None):
	from . import showDialogWithContext
	return showDialogWithContext(CriteriaEditorDialog, context, parent)
