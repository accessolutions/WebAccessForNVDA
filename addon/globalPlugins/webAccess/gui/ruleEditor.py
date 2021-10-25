# globalPlugins/webAccess/gui/ruleEditor.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2021 Accessolutions (https://accessolutions.fr)
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

# Keep compatible with Python 2
from __future__ import absolute_import, division, print_function

__version__ = "2021.10.25"
__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import re
import wx

import addonHandler
from collections import OrderedDict
import controlTypes
import config
import gui
import inputCore
from logHandler import log

from ..nvdaVersion import nvdaVersion
from .. import ruleHandler
from ..ruleHandler import ruleTypes
from ..ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
from ..webModuleHandler import getEditableWebModule, save

try:
	from wx.lib.expando import ExpandoTextCtrl
except ImportError:
	from ..backports.nvda_2018_2.wx_lib_expando import ExpandoTextCtrl

try:
	from six import iteritems, text_type
except ImportError:
	# NVDA version < 2018.3
	iteritems = dict.iteritems
	text_type = unicode

addonHandler.initTranslation()


formModeRoles = [
	controlTypes.ROLE_EDITABLETEXT,
	controlTypes.ROLE_COMBOBOX,
]


LABEL_ACCEL = re.compile("&(?!&)")
"""
Compiled pattern used to strip accelerator key indicators from labels.
"""

EXPR = re.compile("^ *!? *[^!&|]+( *[&|] *!? *[^!&|]+)*$")
"""
Compiled pattern used to validate expressions.
"""

EXPR_INT = re.compile("^ *!? *[0-9]+( *[&|] *!? *[0-9]+)* *$")
"""
Compiled pattern used to validate expressions whose values are integers.
"""

EXPR_VALUE = re.compile("(([^!&| ])+( (?=[^!&|]))*)+")
"""
Compiled pattern used to capture values in expressions.
"""

def stripAccel(label):
	return LABEL_ACCEL.sub("", label)

def stripAccelAndColon(label):
	return stripAccel(label).rstrip(":").rstrip()

def setIfNotEmpty(dic, key, value):
	if value and value.strip():
		dic[key] = value


def captureValues(expr):
	"""
	Yields value, startPos, endPos
	"""
	for match in EXPR_VALUE.finditer(expr):
		span = match.span()
		yield expr[span[0]:span[1]], span[0], span[1]


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


def translateRoleLblToId(expr):
	def translate(value):
		for key, candidate in iteritems(controlTypes.roleLabels):
			if candidate == value:
				# The key is an enum as of NVDA 2021.2
				return text_type(int(key))
		return value
	return translateExprValues(expr, translate)


def getRoleLblForInt(role):
	return controlTypes.roleLabels.get(role, "")


def translateStatesIdToLbl(expr):
	def translate(value):
		try:
			return controlTypes.stateLabels[int(value)]
		except (KeyError, ValueError):
			return value
	return translateExprValues(expr, translate)


def translateStatesLblToId(expr):
	def translate(value):
		for key, candidate in iteritems(controlTypes.stateLabels):
			if candidate == value:
				# The key is an enum as of NVDA 2021.2
				return text_type(int(key))
		return value
	return translateExprValues(expr, translate)


def getStatesLblExprForSet(states):
	return " & ".join((
		controlTypes.stateLabels.get(state, state)
		for state in states
	))


def safeDelete(dic, key):
	try:
		del dic[key]
	except KeyError:
		pass


def updateAndDeleteMissing(keys, src, dest):
	for key in keys:
		if key in src:
			dest[key] = src[key]
		else:
			safeDelete(dest, key)


def updateOrDeleteIfEmpty(dic, key, value):
	if value:
		dic[key] = value
	else:
		safeDelete(dic, key)


def show(context):
	gui.mainFrame.prePopup()
	with RuleEditor(gui.mainFrame) as dlg:
		result = dlg.ShowModal(context)
	gui.mainFrame.postPopup()
	return result == wx.ID_OK


class RuleContextEditor(wx.Dialog):
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		(
			"contextPageTitle",
			# Translator: Field label on the RuleContextEditor dialog.
			pgettext("webAccess.ruleContext", u"Page &title:")
		),
		(
			"contextPageType",
			# Translator: Field label on the RuleContextEditor dialog.
			pgettext("webAccess.ruleContext", u"Page t&ype:")
		),
		(
			# Translator: Field label on the RuleContextEditor dialog.
			"contextParent",
			pgettext("webAccess.ruleContext", u"&Parent element:")
		),
		(
			# Translator: Field label on the RuleContextEditor dialog.
			"priority",
			pgettext("webAccess.ruleContext", u"Pri&ority:")
		),
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
			# Translators: Fail-back context summary in RuleEditor dialog.
			return _("Global - Applies to the whole web module.")
	
	def __init__(self, parent):
		super(RuleContextEditor, self).__init__(
			parent,
			# Translator: The title for the RuleContextEditor dialog.
			title=_("Rule Context"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		fgSizer = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
		mainSizer.Add(fgSizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

		item = self.pageTitleLabel = wx.StaticText(
			self, label=self.FIELDS["contextPageTitle"]
		)
		item.Hide()  # Visibility depends on rule type
		fgSizer.Add(item)
		item = self.pageTitleCombo = wx.ComboBox(self)
		item.Hide()  # Visibility depends on rule type
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["contextPageType"])
		fgSizer.Add(item)
		item = self.pageTypeCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["contextParent"])
		fgSizer.Add(item)
		item = self.parentCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)

		item = wx.StaticText(self, label=self.FIELDS["priority"])
		fgSizer.Add(item)
		item = self.priorityText = wx.TextCtrl(self, size=(350, -1))
		fgSizer.Add(item, flag=wx.EXPAND)

		fgSizer.AddGrowableCol(1)
		
		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.BOTTOM,
			border=8
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.SetSizerAndFit(mainSizer)
	
	def initData(self, context):
		data = self.data = context["data"]["rule"]
		markerManager = self.markerManager = context["webModule"].markerManager
		node = markerManager.nodeManager.getCaretNode()
		
		showPageTitle = data["type"] != ruleTypes.PAGE_TITLE_1
		if showPageTitle:
			self.pageTitleCombo.Set([context["pageTitle"]])
			self.pageTitleCombo.Value = data.get("contextPageTitle", "")
		self.pageTitleLabel.Show(showPageTitle)
		self.pageTitleCombo.Show(showPageTitle)
			
		self.pageTypeCombo.Set(markerManager.getPageTypes())
		self.pageTypeCombo.Value = data.get("contextPageType", "")
		
		parents = []
		for result in markerManager.getResults():
			query = result.markerQuery
			if (
				query.type in (ruleTypes.PARENT, ruleTypes.ZONE)
				and node in result.node
			):
				parents.insert(0, query.name)
		self.parentCombo.Set(parents)
		self.parentCombo.Value = data.get("contextParent", "")
		
		self.priorityText.Value = str(data.get("priority", ""))
	
	def onOk(self, evt):
		data = dict()
		
		setIfNotEmpty(data, "contextPageTitle", self.pageTitleCombo.Value)
		setIfNotEmpty(data, "contextPageType", self.pageTypeCombo.Value)
		setIfNotEmpty(data, "contextParent", self.parentCombo.Value)
		
		priority = self.priorityText.Value
		if priority.strip():
			try:
				priority = int(priority)
			except ValueError:
				gui.messageBox(
					message=_("Priority, if set, must be a positive integer."),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.priorityText.SetFocus()
				return
			data["priority"] = priority
		
		updateAndDeleteMissing(self.FIELDS, data, self.data)

		assert self.IsModal()
		self.EndModal(wx.ID_OK)
	
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		if nvdaVersion < (2021, 1):
			self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		else:  # wx 4.1.1
			self.CentreOnScreen()
		if self.pageTitleCombo.IsShown():
			self.pageTitleCombo.SetFocus()
		else:
			self.pageTypeCombo.SetFocus()
		return super(RuleContextEditor, self).ShowModal()


class RuleCriteriaEditor(wx.Dialog):
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("text", pgettext("webAccess.ruleCriteria", u"&Text:")),
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("role", pgettext("webAccess.ruleCriteria", u"&Role:")),
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("tag", pgettext("webAccess.ruleCriteria", u"T&ag:")),
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("id", pgettext("webAccess.ruleCriteria", u"&ID:")),
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("className", pgettext("webAccess.ruleCriteria", u"&Class:")),
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("states", pgettext("webAccess.ruleCriteria", u"&States:")),
		# Translator: Field label on the RuleCriteriaEditor dialog.
		("src", pgettext("webAccess.ruleCriteria", u"Ima&ge source:")),
		(
			"relativePath",
			# Translator: Field label on the RuleCriteriaEditor dialog.
			pgettext("webAccess.ruleCriteria", u"R&elative path:")
		),
		# Translator: Field label on the RuleCriteriaEditor dialog.
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
			# Translators: Fail-back criteria summary in RuleEditor dialog.
			return _("No criteria")
	
	def __init__(self, parent):
		super(RuleCriteriaEditor, self).__init__(
			parent,
			# Translator: The title for the RuleContextEditor dialog.
			title=_("Rule Criteria"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		fgSizer = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
		mainSizer.Add(fgSizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

		item = wx.StaticText(self, label=self.FIELDS["text"])
		fgSizer.Add(item)
		item = self.searchText = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["role"])
		fgSizer.Add(item)
		item = self.roleCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["tag"])
		fgSizer.Add(item)
		item = self.tagCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["id"])
		fgSizer.Add(item)
		item = self.idCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["className"])
		fgSizer.Add(item)
		item = self.classCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["states"])
		fgSizer.Add(item)
		item = self.statesCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["src"])
		fgSizer.Add(item)
		item = self.srcCombo = wx.ComboBox(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["relativePath"])
		fgSizer.Add(item)
		item = self.relativePathText = wx.TextCtrl(self)
		fgSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=self.FIELDS["index"])
		fgSizer.Add(item)
		item = self.indexText = wx.TextCtrl(self)
		fgSizer.Add(item, flag=wx.EXPAND)

		fgSizer.AddGrowableCol(1)
		
		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.BOTTOM,
			border=8
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.SetSizerAndFit(mainSizer)
	
	def initData(self, context):
		data = self.data = context["data"]["rule"]
		markerManager = self.markerManager = context["webModule"].markerManager
		node = markerManager.nodeManager.getCaretNode()

		textNode = node
		node = node.parent
		t = textNode.text
		if t == " ":
			t = ""
		textChoices = [t]
		if node.previousTextNode is not None:
			textChoices.append("<" + node.previousTextNode.text)
		roleChoices = []
		statesChoices = []
		tagChoices = []
		idChoices = []
		classChoices = []
		srcChoices = []
		while node is not None:
			roleChoices.append(getRoleLblForInt(node.role) or "")
			tagChoices.append(node.tag or "")
			idChoices.append(node.id or "")
			classChoices.append(node.className or "")
			statesChoices.append(getStatesLblExprForSet(node.states) or "")
			srcChoices.append(node.src or "")
			node = node.parent
		
		self.searchText.Set(textChoices)
		self.roleCombo.Set(roleChoices)
		self.tagCombo.Set(tagChoices)
		self.idCombo.Set(idChoices)
		self.classCombo.Set(classChoices)
		self.statesCombo.Set(statesChoices)
		self.srcCombo.Set(srcChoices)
		
		self.searchText.Value = data.get("text", "")
		self.roleCombo.Value = translateRoleIdToLbl(data.get("role", ""))
		self.tagCombo.Value = data.get("tag", "")
		self.idCombo.Value = data.get("id", "")
		self.classCombo.Value = data.get("className", "")
		self.statesCombo.Value = translateStatesIdToLbl(data.get("states", ""))
		self.srcCombo.Value = data.get("src", "")
		self.relativePathText.Value = str(data.get("relativePath", ""))
		self.indexText.Value = str(data.get("index", ""))
	
	def onOk(self, evt):
		data = dict()
		
		setIfNotEmpty(data, "text", self.searchText.Value)
		
		roleLblExpr = self.roleCombo.Value
		if roleLblExpr:
			if not EXPR.match(roleLblExpr):
				gui.messageBox(
					message=(
						_('Syntax error in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["role"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.roleCombo.SetFocus()
				return
			roleIdExpr = translateRoleLblToId(roleLblExpr)
			if not EXPR_INT.match(roleIdExpr):
				gui.messageBox(
					message=(
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["role"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.roleCombo.SetFocus()
				return
			data["role"] = roleIdExpr
		
		setIfNotEmpty(data, "tag", self.tagCombo.Value.lower())
		setIfNotEmpty(data, "id", self.idCombo.Value)
		setIfNotEmpty(data, "className", self.classCombo.Value)
		
		statesLblExpr = self.statesCombo.Value
		if statesLblExpr:
			if not EXPR.match(statesLblExpr):
				gui.messageBox(
					message=(
						_('Syntax error in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["states"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.statesCombo.SetFocus()
				return
			statesIdExpr = translateStatesLblToId(statesLblExpr)
			if not EXPR_INT.match(statesIdExpr):
				gui.messageBox(
					message=(
						_('Unknown identifier in the field "{field}"')
					).format(field=stripAccelAndColon(self.FIELDS["states"])),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.statesCombo.SetFocus()
				return
			data["states"] = statesIdExpr
		
		setIfNotEmpty(data, "src", self.srcCombo.Value)
		setIfNotEmpty(data, "relativePath", self.relativePathText.Value)
		
		index = self.indexText.Value
		if index.strip():
			try:
				index = int(index)
			except Exception:
				index = 0
			if index > 0:
				data["index"] = index
			else:
				gui.messageBox(
					message=_("Index, if set, must be a positive integer."),
					caption=_("Error"),
					style=wx.OK | wx.ICON_ERROR,
					parent=self
				)
				self.indexText.SetFocus()
				return
		
		updateAndDeleteMissing(self.FIELDS, data, self.data)
		
		assert self.IsModal()
		self.EndModal(wx.ID_OK)
	
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		if nvdaVersion < (2021, 1):
			self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		else:  # wx 4.1.1
			self.CentreOnScreen()
		self.searchText.SetFocus()
		return super(RuleCriteriaEditor, self).ShowModal()


class RulePropertiesEditor(wx.Dialog):
	
	# The semi-column is part of the labels because some localizations
	# (ie. French) require it to be prepended with one space.
	FIELDS = OrderedDict((
		(
			"multiple",
			# Translator: Field label on the RulePropertiesEditor dialog.
			pgettext(
				"webAccess.ruleProperties",
				u"&Multiple results"
			)
		),
		(
			"formMode",
			# Translator: Field label on the RulePropertiesEditor dialog.
			pgettext("webAccess.ruleProperties", u"Activate &form mode")
		),
		(
			# Translator: Field label on the RulePropertiesEditor dialog.
			"skip",
			pgettext("webAccess.ruleProperties", u"S&kip with Page Down")
		),
		(
			# Translator: Field label on the RulePropertiesEditor dialog.
			"sayName",
			pgettext("webAccess.ruleProperties", u"&Speak rule name")
		),
		(
			# Translator: Field label on the RulePropertiesEditor dialog.
			"customName",
			pgettext("webAccess.ruleProperties", u"Custom &name:")
		),
		("customValue", None),  # Label depends on rule type)
		(
			# Translator: Field label on the RulePropertiesEditor dialog.
			"mutation",
			pgettext("webAccess.ruleProperties", u"&Transform:")
		),
	))
	
	RULE_TYPE_FIELDS = OrderedDict((
		(ruleTypes.PAGE_TITLE_1, ("customValue",)),
		(ruleTypes.PAGE_TITLE_2, ("customValue",)),
		(
			ruleTypes.ZONE,
			(
				"formMode",
				"skip",
				"sayName",
				"customName",
				"customValue",
				"mutation",
			)
		),
		(
			ruleTypes.MARKER,
			(
				"multiple",
				"formMode",
				"skip",
				"sayName",
				"customName",
				"customValue",
				"mutation",
			)
		),
	))
	
	@classmethod
	def getAltFieldLabel(cls, ruleType, key, default=None):
		if key == "customValue":
			if ruleType in (ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return pgettext(
					"webAccess.ruleProperties", u"Custom page &title:"
				)
			elif ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return pgettext(
					"webAccess.ruleProperties", u"Custom messa&ge:"
				)
		return default
	
	@classmethod
	def getSummary(cls, data):
		parts = []
		ruleType = data.get("type")
		data = data.copy()
		data.setdefault("sayName", True)
		for key in cls.RULE_TYPE_FIELDS.get(ruleType, {}):
			if key in data:
				label = cls.FIELDS[key]
				label = cls.getAltFieldLabel(ruleType, key, label)
				label = stripAccel(label)
				value = data[key]
				if key == "mutation":
					value = mutationLabels.get(value)
				elif isinstance(value, bool):
					if value:
						parts.append(label.strip().strip(":").strip())
					continue
				parts.append(u"{} {}".format(label, value))
		if parts:
			return "\n".join(parts)
		else:
			# Translators: Fail-back property summary in RuleEditor dialog.
			return _("None.")
	
	def __init__(self, parent):
		super(RulePropertiesEditor, self).__init__(
			parent,
			# Translator: The title for the RulePropertiesEditor dialog.
			title=_("Rule Properties"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		gbSizer = self.contextSizer = wx.GridBagSizer()
		gbSizer.SetEmptyCellSize((0, 0))
		mainSizer.Add(
			gbSizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL | wx.ALIGN_TOP,
			border=8
		)
				
		row = 0
		item = self.multipleCheckBox = wx.CheckBox(
			self,
			label=self.FIELDS["multiple"]
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			span=(1, 2),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
			border=4
		)
		
		row += 1
		item = self.formModeCheckBox = wx.CheckBox(
			self,
			label=self.FIELDS["formMode"]
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			span=(1, 2),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
			border=4
		)
		
		row += 1
		item = self.skipCheckBox = wx.CheckBox(
			self,
			label=_("S&kip with Page Down")
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			span=(1, 2),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
			border=4
		)
		
		row += 1
		item = self.sayNameCheckBox = wx.CheckBox(
			self,
			label=self.FIELDS["sayName"]
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			span=(1, 2),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM,
			border=4
		)
		
		row += 1
		item = self.customNameLabel = wx.StaticText(
			self,
			label=self.FIELDS["customName"] or ""
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			flag=wx.TOP | wx.BOTTOM | wx.RIGHT,
			border=4
		)
		item = self.customNameText = wx.TextCtrl(self, size=(350, -1))
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 1),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM | wx.LEFT,
			border=4
		)
		
		row += 1
		item = self.customValueLabel = wx.StaticText(
			self,
			label=self.FIELDS["customValue"] or ""
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			flag=wx.TOP | wx.BOTTOM | wx.RIGHT,
			border=4
		)
		item = self.customValueText = wx.TextCtrl(self, size=(350, -1))
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 1),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM | wx.LEFT,
			border=4
		)
		
		row += 1
		item = self.mutationLabel = wx.StaticText(
			self,
			label=self.FIELDS["mutation"]
		)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 0),
			flag=wx.TOP | wx.BOTTOM | wx.RIGHT,
			border=4
		)
		item = self.mutationCombo = wx.ComboBox(self, style=wx.CB_READONLY)
		item.Hide()  # Visibility depends on rule type
		gbSizer.Add(
			item,
			pos=(row, 1),
			flag=wx.EXPAND | wx.TOP | wx.BOTTOM | wx.LEFT,
			border=4
		)
		
		gbSizer.AddGrowableCol(1)

		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.BOTTOM,
			border=8
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.SetSizerAndFit(mainSizer)
	
	def initData(self, context):
		data = self.data = context["data"]["rule"]
		
		ruleType = data.get("type")
		fields = self.RULE_TYPE_FIELDS.get(ruleType, {})
		
		if "multiple" in fields:
			self.multipleCheckBox.Value = data.get("multiple", False)
			self.multipleCheckBox.Show()
		if "formMode" in fields:
			self.formModeCheckBox.Value = data.get("formMode", False)
			self.formModeCheckBox.Show()
		if "skip" in fields:
			self.skipCheckBox.Value = data.get("skip", False)
			self.skipCheckBox.Show()
		if "sayName" in fields:
			self.sayNameCheckBox.Value = data.get("sayName", True)
			self.sayNameCheckBox.Show()
		if "customName" in fields:
			self.customNameText.Value = data.get("customName", "")
			self.customNameLabel.Show()
			self.customNameText.Show()
		if "customValue" in fields:
			self.customValueText.Value = data.get("customValue", "")
			self.customValueLabel.Label = self.getAltFieldLabel(
				ruleType, "customValue"
			)
			self.customValueLabel.Show()
			self.customValueText.Show()
		if "mutation" in fields:
			self.mutationCombo.Append(
				# Translators: The label when there is no control mutation.
				pgettext("webAccess.controlMutation", "<None>"),
				""
			)
			for id_ in MUTATIONS_BY_RULE_TYPE.get(ruleType, []):
				label = mutationLabels.get(id_)
				if label is None:
					log.error("No label for mutation id: {}".format(id_))
					label = id_
				self.mutationCombo.Append(label, id_)
			mutation = data.get("mutation")
			if mutation:
				for index in range(1, self.mutationCombo.Count + 1):
					id_ = self.mutationCombo.GetClientData(index)
					if id_ == mutation:
						break
				else:
					# Allow to bypass mutation choice by rule type
					label = mutationLabels.get(id_)
					if label is None:
						log.error("No label for mutation id: {}".format(id_))
						label = id_
					self.mutationCombo.Append(label, id_)
					index += 1
			else:
				index = 0
			self.mutationCombo.SetSelection(index)
			self.mutationLabel.Show()
			self.mutationCombo.Show()
	
	def onOk(self, evt):
		data = OrderedDict()
		
		fields = self.RULE_TYPE_FIELDS.get(self.data.get("type"), {})
		
		# Among these properties, only "sayName" defaults to True
		# All others default to False or empty.
		
		if "multiple" in fields and self.multipleCheckBox.Value:
			data["multiple"] = True
		if "formMode" in fields and self.formModeCheckBox.Value:
			data["formMode"] = True
		if "skip" in fields and self.skipCheckBox.Value:
			data["skip"] = True
		if "sayName" in fields and not self.sayNameCheckBox.Value:
			data["sayName"] = False
		if "customName" in fields:
			setIfNotEmpty(data, "customName", self.customNameText.Value)
		if "customValue" in fields:
			setIfNotEmpty(data, "customValue", self.customValueText.Value)
		if "mutation" in fields:
			if self.mutationCombo.Selection > 0:
				data["mutation"] = self.mutationCombo.GetClientData(
					self.mutationCombo.Selection
				)
		
		updateAndDeleteMissing(fields, data, self.data)

		assert self.IsModal()
		self.EndModal(wx.ID_OK)
	
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		if nvdaVersion < (2021, 1):
			self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		else:  # wx 4.1.1
			self.CentreOnScreen()
		for ctrl in (
			self.multipleCheckBox,
			self.formModeCheckBox,
			self.customValueText
		):
			if ctrl.IsShown():
				ctrl.SetFocus()
				break
		return super(RulePropertiesEditor, self).ShowModal()


class RuleEditor(wx.Dialog):
	
	def __init__(self, parent):
		super(RuleEditor, self).__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		self.hasMoved = False
		
		# Dialog main sizer
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		
		# Form part
		columnsSizer = wx.GridBagSizer(8, 8)
		mainSizer.Add(
			columnsSizer,
			proportion=1,
			flag=wx.EXPAND | wx.ALL,
			border=8
		)
		leftSizer = wx.FlexGridSizer(cols=1, vgap=8, hgap=8)
		rightSizer = wx.GridBagSizer(8, 8)
		columnsSizer.Add(leftSizer, pos=(0, 0), flag=wx.EXPAND)
		columnsSizer.Add(
			wx.StaticLine(self, style=wx.LI_VERTICAL),
			pos=(0, 1),
			flag=wx.EXPAND
		)
		columnsSizer.Add(rightSizer, pos=(0, 2), flag=wx.EXPAND)
		columnsSizer.AddGrowableCol(0)
		columnsSizer.AddGrowableCol(2)
		columnsSizer.AddGrowableRow(0)
		
		# Header section
		headerSizer = wx.FlexGridSizer(cols=2, vgap=8, hgap=8)
		leftSizer.Add(headerSizer, flag=wx.EXPAND)

		item = wx.StaticText(self, label=_(u"Rule &type:"))
		headerSizer.Add(item)
		item = self.ruleTypeCombo = wx.ComboBox(self, style=wx.CB_READONLY)
		item.Bind(wx.EVT_COMBOBOX, self.onRuleTypeChoice)
		for key, label in ruleTypes.ruleTypeLabels.items():
			self.ruleTypeCombo.Append(label, key)
		headerSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(self, label=_(u"Rule &name:"))
		headerSizer.Add(item)
		item = self.ruleNameText = wx.ComboBox(self)
		headerSizer.Add(item, flag=wx.EXPAND)
		
		headerSizer.AddGrowableCol(1)
		
		# Context Box
		contextBox = self.contextBox = wx.StaticBox(self, label=_("Context"))
		contextSizer = self.contextSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(contextBox, orient=wx.VERTICAL)
		item.Add(contextSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, flag=wx.EXPAND)
				
		item = self.contextText = ExpandoTextCtrl(
			contextBox,
			size=(250, -1),
			style=wx.TE_PROCESS_ENTER | wx.TE_MULTILINE | wx.TE_READONLY,
		)
		item.Bind(wx.EVT_TEXT_ENTER, self.onOk)
		contextSizer.Add(item, pos=(0, 0), span=(2, 1), flag=wx.EXPAND)
		item = wx.Button(contextBox, label=_("Edit conte&xt"))
		item.Bind(wx.EVT_BUTTON, self.onContextBtn)
		contextSizer.Add(item, pos=(0, 1))
		contextSizer.AddGrowableCol(0)
		contextSizer.AddGrowableRow(1)
		
		# Criteria Box
		criteriaBox = wx.StaticBox(self, label=_("Criteria"))
		criteriaSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(criteriaBox, orient=wx.VERTICAL)
		item.Add(criteriaSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, flag=wx.EXPAND)
		item = self.criteriaText = ExpandoTextCtrl(
			criteriaBox,
			size=(250, -1),
			style=wx.TE_PROCESS_ENTER | wx.TE_MULTILINE | wx.TE_READONLY,
		)
		item.Bind(wx.EVT_TEXT_ENTER, self.onOk)
		criteriaSizer.Add(item, pos=(0, 0), span=(2, 1), flag=wx.EXPAND)
		item = wx.Button(criteriaBox, label=_("Edit c&riteria"))
		item.Bind(wx.EVT_BUTTON, self.onCriteriaBtn)
		criteriaSizer.Add(item, pos=(0, 1))
		criteriaSizer.AddGrowableCol(0)
		criteriaSizer.AddGrowableRow(1)
		
		# Actions Box
		actionsBox = self.actionsBox = wx.StaticBox(
			self, label=_("Actions"), style=wx.SB_RAISED
		)
		actionsBox.Hide()  # Visibility depends on rule type
		actionsSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(actionsBox, orient=wx.VERTICAL)
		item.Add(actionsSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, flag=wx.EXPAND)
		
		item = wx.StaticText(actionsBox, label=_("&Keyboard shortcut"))
		actionsSizer.Add(item, pos=(0, 0))
		item = self.gesturesList = wx.ListBox(actionsBox)
		item.Bind(wx.EVT_LISTBOX, self.onGesturesListChoice)
		actionsSizer.Add(item, pos=(0, 1), span=(3, 1), flag=wx.EXPAND)
		
		item = wx.Button(actionsBox, label=_("Add a keyboard shortcut"))
		item.Bind(wx.EVT_BUTTON, self.onAddGesture)
		actionsSizer.Add(item, pos=(0, 2), flag=wx.EXPAND)
		
		item = self.deleteGestureButton = wx.Button(
			actionsBox,
			label=_("Delete this shortcut")
		)
		item.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
		actionsSizer.Add(item, pos=(1, 2), flag=wx.EXPAND)
		
		item = wx.StaticText(
			actionsBox,
			label=_("&Automatic action at rule detection")
		)
		actionsSizer.Add(item, pos=(3, 0))
		item = self.autoActionList = wx.ComboBox(
			actionsBox,
			style=wx.CB_READONLY
		)
		actionsSizer.Add(item, pos=(3, 1), flag=wx.EXPAND)
		
		actionsSizer.AddGrowableCol(1)
		actionsSizer.AddGrowableCol(2)
		actionsSizer.AddGrowableRow(2)
		
		# Properties Box
		propertiesBox = self.propertiesBox = wx.StaticBox(
			self,
			label=_("Properties")
		)
		propertiesBox.Hide()  # Visibility depends on rule type
		propertiesSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(propertiesBox, orient=wx.VERTICAL)
		item.Add(propertiesSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, flag=wx.EXPAND)
		item = self.propertiesText = ExpandoTextCtrl(
			propertiesBox,
			size=(250, -1),
			style=wx.TE_PROCESS_ENTER | wx.TE_MULTILINE | wx.TE_READONLY,
		)
		item.Bind(wx.EVT_TEXT_ENTER, self.onOk)
		propertiesSizer.Add(item, pos=(0, 0), span=(2, 1), flag=wx.EXPAND)
		item = wx.Button(propertiesBox, label=_("Edit &properties"))
		item.Bind(wx.EVT_BUTTON, self.onPropertiesBtn)
		propertiesSizer.Add(item, pos=(0, 1))
		propertiesSizer.AddGrowableCol(0)
		propertiesSizer.AddGrowableRow(1)
		
		leftSizer.AddGrowableCol(0)
			
		# Comment section
		row = 0
		rightSizer.Add(
			wx.StaticText(self, label=_("&Comment")),
			pos=(row, 0)
		)
		
		row += 1
		item = self.comment = wx.TextCtrl(
			self,
			size=(500, 300),
			style=wx.TE_MULTILINE
		)
		rightSizer.Add(item, pos=(row, 0), flag=wx.EXPAND)

		rightSizer.AddGrowableCol(0)
		rightSizer.AddGrowableRow(1)
				
		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.BOTTOM,
			border=8
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
		self.Bind(wx.EVT_SIZE, self.onSize)
		self.Bind(wx.EVT_MOVE_END, self.onMoveEnd)
		self.SetSizerAndFit(mainSizer)
	
	def __del__(self):
		RuleEditor._instance = None
	
	def initData(self, context):
		self.context = context
		rule = self.rule = context.get("rule")
		self.data = context.setdefault("data", {}).setdefault(
			"rule",
			rule.dump() if rule else OrderedDict()
		)
		ruleManager = self.ruleManager = context["webModule"].ruleManager
		if not self.rule and ruleManager.nodeManager:
			node = ruleManager.nodeManager.getCaretNode()
			while node is not None:
				if node.role in formModeRoles:
					self.data["formMode"] = True
					break
				node = node.parent
		
		actionsDict = self.ruleManager.getActions()
		self.autoActionList.Clear()
		self.autoActionList.Append(
			# Translators: Action name
			pgettext("webAccess.action", "No action"),
			""
		)
		for action in actionsDict:
			self.autoActionList.Append(actionsDict[action], action)
		
		if len(self.getQueriesNames()) == 0:
			self.ruleNameText.Set([""])
		else:
			self.ruleNameText.Set(self.getQueriesNames())
		
		if self.rule is None:
			title = _(u"New rule")
			if config.conf["webAccess"]["devMode"]:
				webModule = ruleManager.webModule
				if not webModule.isReadOnly():
					title += " ({})".format(webModule._getWritableLayer().name)
				else:
					title += " ({})".format("/".join((layer.name for layer in webModule.layers)))
			self.Title = title
			self.ruleTypeCombo.SetSelection(-1)
			self.gestureMapValue = {}
			self.autoActionList.SetSelection(0)
			self.comment.Value = ""
		else:
			title = _("Edit rule")
			if config.conf["webAccess"]["devMode"] and rule.layer is not None:
				title += " ({})".format(rule.layer)
			self.Title = title
			self.ruleNameText.Value = rule.name
			for index, key in enumerate(ruleTypes.ruleTypeLabels.keys()):
				if key == rule.type:
					break
			else:
				log.error(u"Unexpected rule type: {}".format(rule.type))
				index = -1
			self.ruleTypeCombo.SetSelection(index)
			self.gestureMapValue = rule.gestures.copy()
			self.autoActionList.SetSelection(
				list(ruleManager.getActions().keys()).index(
					rule.dic.get("autoAction", "")
				) + 1  # Empty entry at index 0
				if "autoAction" in rule.dic else 0
			)
			self.comment.Value = rule.dic.get("comment", "")
		
		self.onRuleTypeChoice(None)
		self.refreshContext()
		self.refreshCriteria()
		self.refreshProperties()
		self.updateGesturesList()
	
	def getQueriesNames(self):
		nameList = []
		for rule in self.ruleManager.getRules():
			if rule.name not in nameList:
				nameList.append(rule.name)
		return nameList
	
	def onRuleTypeChoice(self, evt):
		ruleType = None
		if self.ruleTypeCombo.Selection >= 0:
			ruleType = self.ruleTypeCombo.GetClientData(
				self.ruleTypeCombo.Selection
			)
		self.data["type"] = ruleType
		if "rule" not in self.context:
			if ruleType == ruleTypes.ZONE:
				self.data["skip"] = True
			elif ruleType == ruleTypes.MARKER:
				self.data["skip"] = False
		for control, types in (
			(
				self.actionsBox, (
					ruleTypes.ZONE,
					ruleTypes.MARKER,
				),
			),
			(
				self.propertiesBox,
				(
					ruleTypes.PAGE_TITLE_1,
					ruleTypes.PAGE_TITLE_2,
					ruleTypes.ZONE,
					ruleTypes.MARKER,
				)
			)
		):
			control.Show(ruleType in types)
		
		self.refreshProperties()
		
		self.Sizer.Layout()
		if not self.IsMaximized():
			self.Fit()
			if not self.hasMoved:
				self.CenterOnScreen()
	
	def onContextBtn(self, evt):
		with RuleContextEditor(self) as dlg:
			if dlg.ShowModal(self.context) == wx.ID_OK:
				self.refreshContext()
	
	def refreshContext(self):
		self.contextText.Value = RuleContextEditor.getSummary(self.data)
		self.Sizer.Layout()
		if not self.IsMaximized():
			self.Fit()
			if not self.hasMoved:
				self.CenterOnScreen()
	
	def onCriteriaBtn(self, evt):
		with RuleCriteriaEditor(self) as dlg:
			if dlg.ShowModal(self.context) == wx.ID_OK:
				self.refreshCriteria()
	
	def refreshCriteria(self):
		self.criteriaText.Value = RuleCriteriaEditor.getSummary(self.data)
		self.Sizer.Layout()
		if not self.IsMaximized():
			self.Fit()
			if not self.hasMoved:
				self.CenterOnScreen()
	
	def onPropertiesBtn(self, evt):
		with RulePropertiesEditor(self) as dlg:
			if dlg.ShowModal(self.context) == wx.ID_OK:
				self.refreshProperties()
	
	def refreshProperties(self):
		self.propertiesText.Value = RulePropertiesEditor.getSummary(self.data)
		self.Sizer.Layout()
		if not self.IsMaximized():
			self.Fit()
			if not self.hasMoved:
				self.CenterOnScreen()
	
	def updateGesturesList(self, newGestureIdentifier=None):
		self.gesturesList.Clear()
		i = 0
		sel = 0
		for gestureIdentifier in self.gestureMapValue:
			gestureSource, gestureMain = \
				inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)
			actionStr = self.ruleManager.getActions()[
				self.gestureMapValue[gestureIdentifier]
			]
			self.gesturesList.Append("%s = %s" % (
				gestureMain, actionStr), gestureIdentifier)
			if gestureIdentifier == newGestureIdentifier:
				sel = i
			i += 1
		if len(self.gestureMapValue) > 0:
			self.gesturesList.SetSelection(sel)
		self.onGesturesListChoice(None)
		self.gesturesList.SetFocus()
		self.Sizer.Layout()
		if not self.IsMaximized():
			self.Fit()
			if not self.hasMoved:
				self.CenterOnScreen()
	
	def onGesturesListChoice(self, evt):
		sel = self.gesturesList.Selection
		if sel < 0:
			self.deleteGestureButton.Enabled = False
		else:
			self.deleteGestureButton.Enabled = True
	
	def onDeleteGesture(self, evt):
		sel = self.gesturesList.Selection
		gestureIdentifier = self.gesturesList.GetClientData(sel)
		del self.gestureMapValue[gestureIdentifier]
		self.updateGesturesList()
	
	def onAddGesture(self, evt):
		from ..gui import shortcutDialog
		shortcutDialog.ruleManager = self.ruleManager
		if shortcutDialog.show():
			self.AddGestureAction(
				shortcutDialog.resultShortcut,
				shortcutDialog.resultActionData
			)
	
	def AddGestureAction(self, gestureIdentifier, action):
		self.gestureMapValue[gestureIdentifier] = action
		self.updateGesturesList(newGestureIdentifier=gestureIdentifier)
		self.gesturesList.SetFocus()
	
	def onOk(self, evt):
		data = self.data
		ruleType = data.get("type")
		if not ruleType:
			gui.messageBox(
				message=_("You must choose a type for this rule"),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.ruleTypeCombo.SetFocus()
			return
		name = self.ruleNameText.Value.strip()
		if not name:
			gui.messageBox(
				message=_("You must enter a name for this rule"),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.ruleNameText.SetFocus()
			return
		data["name"] = name

		if ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
			data["gestures"] = self.gestureMapValue
			sel = self.autoActionList.Selection
			autoAction = self.autoActionList.GetClientData(sel)
			updateOrDeleteIfEmpty(data, "autoAction", autoAction)
		else:
			safeDelete(data, "gestures")
			safeDelete(data, "autoAction")
		
		propertyFieldsForType = RulePropertiesEditor.RULE_TYPE_FIELDS.get(
			ruleType, {}
		)
		for key in RulePropertiesEditor.FIELDS:
			if key not in propertyFieldsForType:
				safeDelete(data, key)
		
		updateOrDeleteIfEmpty(data, "comment", self.comment.Value)
		
		synonyms = 0
		for rule in self.ruleManager.getRules():
			if name == rule.name and rule != self.rule:
				synonyms += 1
				if synonyms >= 2:
					break
		if synonyms and "priority" not in data:
			if synonyms == 1:
				msg=_(
					"There is another rule with the same name."
					"\n\n"
					"You probably should consider setting a priority."
				)
			else:
				msg=_(
					"There are other rules with the same name."
					"\n\n"
					"You probably should consider setting a priority."
				)
			if gui.messageBox(
				message=msg,
				caption=_("Warning"),
				style=wx.ICON_WARNING | wx.OK | wx.CANCEL,
				parent=self
			) == wx.CANCEL:
				return
		
		layerName = None
		if self.rule is not None:
			layerName = self.rule.layer
		webModule = getEditableWebModule(self.ruleManager.webModule, layerName=layerName)
		if not webModule:
			return
		if self.rule is not None:
			# modification mode, remove old rule
			self.ruleManager.removeRule(self.rule)
		if layerName == "addon":
			if not webModule.getLayer("addon") and webModule.getLayer("scratchpad"):
				layerName = "scratchpad"
		elif layerName is None:
			layerName = webModule._getWritableLayer().name
		
		ruleManager = self.ruleManager = webModule.ruleManager
		rule = webModule.createRule(data)
		if layerName not in ruleManager.layers:
			ruleManager.layers[layerName] = []
			ruleManager.layersIndex = dict(
				((layerName, layerIndex) for layerIndex, layerName in enumerate(ruleManager.layers.keys()))
			)
		ruleManager.loadRule(layerName, None, data)
		webModule.getLayer(layerName, raiseIfMissing=True).dirty = True
		if not save(webModule, layerName=layerName):
			return
		
		assert self.IsModal()
		self.EndModal(wx.ID_OK)
	
	def onCancel(self, evt):
		safeDelete(self.context, "rule")
		self.EndModal(wx.ID_CANCEL)
	
	def onSize(self, evt):
		if not self.IsMaximized():
			self.Fit()
			if not self.hasMoved:
				self.CenterOnScreen()
		evt.Skip()
	
	def onMoveEnd(self, evt):
		self.hasMoved = True
	
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		if nvdaVersion < (2021, 1):
			self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		else:  # wx 4.1.1
			self.CentreOnScreen()
		self.ruleTypeCombo.SetFocus()
		return super(RuleEditor, self).ShowModal()
