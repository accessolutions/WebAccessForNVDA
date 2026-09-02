# globalPlugins/webAccess/gui/rule/Manager.py
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
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


from collections import namedtuple
import wx

import addonHandler
import config
import gui
from gui import guiHelper
import inputCore
import queueHandler
import ui

from ...ruleHandler import Criteria, GestureScope, Rule, Result, Selector, Zone, ruleTypes
from ...utils import getCharFromKeyEvent, guarded
from ...webModuleHandler import getEditableWebModule, save
from .. import ContextualDialog, showContextualDialog, stripAccel
from .editor import getSummary

from collections.abc import Mapping


addonHandler.initTranslation()


SCOPE_LABELS = {
	# Translators: The label for a gesture binding scope
	GestureScope.GLOBAL: _("Global scope"),
	# Translators: The label for a gesture binding scope
	GestureScope.NORMAL: _("Normal scope"),
	# Translators: The label for a gesture binding scope
	GestureScope.LOCAL: _("Local scope"),
}


lastGroupBy = "position"
lastActiveOnly = False


def show(context, parent=None):
	showContextualDialog(Dialog, context, parent)


TreeItemData = namedtuple("TreeItemData", ("label", "obj", "children"))


def getCriteriaOrSelectorLabel(criteriaOrSelector):
	if isinstance(criteriaOrSelector, Criteria):
		criteria = criteriaOrSelector
		selector = None
	elif isinstance(criteriaOrSelector, Selector):
		selector = criteriaOrSelector
		criteria = selector.criteria
	rule = criteria.rule
	label = rule.name
	if len(rule.criteria) > 1:
		if criteria.name:
			label += f" - {criteria.name}"
		else:
			label += f" - #{rule.criteria.index(criteria) + 1}"
	if rule._gestureMap:
		label += " ({gestures})".format(gestures=", ".join(
			inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
			for identifier in list(rule._gestureMap.keys())
		))
	if selector is not None:
		if selector is criteria.startSelector:
			# Translators: A mention on the Rules Manager dialog for free zone selectors
			label += _(" (start)")
		elif selector is criteria.endSelector:
			# Translators: A mention on the Rules Manager dialog for free zone selectors
			label += _(" (end)")
	return label


def getGestureLabel(gesture):
	source, main = inputCore.getDisplayTextForGestureIdentifier(
		inputCore.normalizeGestureIdentifier(gesture)
	)
	if gesture.startswith("kb:"):
		return main
	return "{main} ({source})".format(source=source, main=main)


def getRuleLabel(rule):
	label = rule.name
	if rule._gestureMap:
		label += " ({gestures})".format(gestures=", ".join(
			inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
			for identifier in list(rule._gestureMap.keys())
		))
	return label


def getRules(ruleManager):
	webModule = ruleManager.webModule
	if not webModule.isReadOnly():
		layer = webModule.getWritableLayer().name
	elif config.conf["webAccess"]["devMode"]:
		layer = None
	else:
		return []
	return ruleManager.getRules(layer=layer)


def rule_getResults_safe(rule):
	try:
		return rule.getResults()
	except Exception:
		return []


def iterRulesByGesture(ruleManager, filter=None, active=False):
	scopes = {}
	noGesture = []
	
	for rule in getRules(ruleManager):
		if filter and filter not in rule.name:
			continue
		if active and not rule_getResults_safe(rule):
			continue
		for gesture, (scope, action) in rule.gestures.items():
			rules = scopes.setdefault(
				scope, {}
			).setdefault(getGestureLabel(gesture), [])
			rules.append(TreeItemData(
				label=(
					"{rule} - {action}".format(
						rule=rule.name,
						action=rule.ruleManager.getActions().get(action, f"*{action}")
					)
					if action != "moveto"
					else rule.name
				),
				obj=rule,
				children=[]
			))
		if not rule.gestures:
			noGesture.append(
				TreeItemData(label=rule.name, obj=rule, children=[])
			)
	normalScopeOnly = len(scopes) == 1 and scopes.get(GestureScope.NORMAL)
	for scope, gestures in scopes.items():
		scopeChildren = []
		for gesture, gestureChildren in sorted(
			list(gestures.items()),
			key=lambda kvp: kvp[0]
		):
			scopeChildren.append(TreeItemData(
				label=gesture,
				obj=None,
				children=sorted(gestureChildren, key=lambda tid: tid.label)
			))
		if normalScopeOnly:
			yield from scopeChildren
		else:
			yield TreeItemData(
				label=SCOPE_LABELS[scope],
				obj=None,
				children=scopeChildren
			)
	if noGesture:
		yield TreeItemData(
			# Translator: TreeItem label on the RulesManager dialog.
			label=pgettext("webAccess.ruleGesture", "<None>"),
			obj=None,
			children=sorted(noGesture, key=lambda tid: tid.label)
		)


def getRulesByContext(ruleManager, filter=None, active=False):
	contexts: Mapping[tuple[str, str, str], Rule] = {}
	for rule in getRules(ruleManager):
		if filter and filter not in rule.name.casefold():
			continue
		if active:
			results = rule_getResults_safe(rule)
			if not results:
				continue
			alternatives = (result.criteria for result in results)
		else:
			alternatives = (criteria for criteria in rule.criteria)
		for selector in (
			s for c in alternatives for s in ( c.nodeSelector, c.startSelector, c.endSelector)
			if s is not None
		):
			contexts.setdefault((
				selector.contextPageTitle or "",  # Avoiding None eases later sorting
				selector.contextPageType or "",
				selector.contextParent or "",
			), []).append(TreeItemData(
				label=getCriteriaOrSelectorLabel(selector),
				obj=rule,
				children=[]
			))
	for context, tids in sorted(
		contexts.items(),
		key=lambda item: (item[0] == ("", "", ""), item[0])  # Move "General" to the end
	):
		parts = []
		if context[0]:
			# Translators: A part of a context grouping label on the Rules Manager
			parts.append(_("Page Title: {contextPageTitle}").format(contextPageTitle=context[0]))
		if context[1]:
			# Translators: A part of a context grouping label on the Rules Manager
			parts.append(_("Page Type: {contextPageTitle}").format(contextPageTitle=context[1]))
		if context[2]:
			# Translators: A part of a context grouping label on the Rules Manager
			parts.append(_("Parent: {contextPageTitle}").format(contextPageTitle=context[2]))
		if parts:
			label = ", ".join(parts)
		else:
			# Translators: A context grouping label on the Rules Manager
			label = "General"
		
		def sortKey(tld):
			label = tld.label
			for index, suffix in (
				# Translators: A mention on the Rules Manager dialog for free zone selectors
				(0, _(" (end)")),
				# Translators: A mention on the Rules Manager dialog for free zone selectors
				(1, _(" (end)")),
			):
				if label.endswith(suffix):
					label = label[:-len(suffix)] + str(index)
			return label
		
		yield TreeItemData(label=label, obj=None, children=sorted(tids, key=sortKey))


def getRulesByName(ruleManager, filter=None, active=False):
	return sorted(
		(
			TreeItemData(
				label=getRuleLabel(rule),
				obj=rule,
				children=[]
			)
			for rule in getRules(ruleManager)
			if (
				(not filter or filter in rule.name.casefold())
				and (not active or rule_getResults_safe(rule))
			)
		),
		key=lambda tid: tid.label.casefold()
	)


def getRulesByPosition(ruleManager, filter=None, active=True):
	"""
	Yield rules by position.

	Includes results from all active WebModules on the document.
	As position depends on result, the `active` criteria is ignored.
	"""
	webModule = ruleManager.webModule
	if not webModule.isReadOnly():
		layer = webModule.getWritableLayer().name
	elif config.conf["webAccess"]["devMode"]:
		layer = None
	else:
		return []
	roots: list[TreeItemData] = []
	ancestors: list[TreeItemData] = []
	for result in ruleManager.rootRuleManager.getAllResults():
		rule = result.rule
		if layer and rule.layer != layer:
			continue
		tid = TreeItemData(
			label=getCriteriaOrSelectorLabel(result.criteria),
			obj=result,
			children=[]
		)
		while ancestors:
			candidate = ancestors[-1]
			if candidate.obj.containsResult(result):
				candidate.children.append(tid)
				break
			ancestors.pop()
		else:
			roots.append(tid)
		if result.rule.type in (ruleTypes.PARENT, ruleTypes.ZONE):
			ancestors.append(tid)
	
	def passesFilter(tid) -> bool:
		for index, child in enumerate(tid.children.copy()):
			if not passesFilter(child) :
				del tid.children[index]
		return tid.children or filter in tid.obj.name.casefold()
	
	return tuple(tid for tid in roots if passesFilter(tid))


def getRulesByType(ruleManager, filter=None, active=False):
	types = {}
	for rule in getRules(ruleManager):
		if (
			(filter and filter not in rule.name.casefold())
			or (active and not rule_getResults_safe(rule))
		):
			continue
		types.setdefault(rule.type, []).append(TreeItemData(
			label=getRuleLabel(rule),
			obj=rule,
			children=[]
		))
	for ruleType, label in ruleTypes.ruleTypeLabels.items():
		try:
			tids = types[ruleType]
		except KeyError:
			continue
		yield TreeItemData(
			label=label,
			obj=None,
			children=sorted(tids, key=lambda tid: tid.label)
		)


GroupBy = namedtuple("GroupBy", ("id", "label", "func"))
GROUP_BY = (
	GroupBy(
		id="position",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "&Position"),
		func=getRulesByPosition
	),
	GroupBy(
		id="type",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "&Type"),
		func=getRulesByType
	),
	GroupBy(
		id="type",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "&Context"),
		func=getRulesByContext
	),
	GroupBy(
		id="gestures",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "&Gestures"),
		func=iterRulesByGesture
	),
	GroupBy(
		id="name",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "Nam&e"),
		func=getRulesByName
	),
)


class Dialog(ContextualDialog):
	
	def __init__(self, parent):
		super().__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX
		)
		
		scale = self.scale
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		contentsSizer = wx.BoxSizer(wx.VERTICAL)
		
		item = self.groupByRadio = wx.RadioBox(
			self,
			# Translator: A label on the RulesManager dialog.
			label=_("Group by: "),
			choices=tuple((groupBy.label for groupBy in GROUP_BY)),
		)
		item.Bind(wx.EVT_RADIOBOX, self.onGroupByRadio)
		contentsSizer.Add(item, flag=wx.EXPAND)
		contentsSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS))
		
		filtersSizer = wx.GridBagSizer()
		filtersSizer.SetEmptyCellSize((0, 0))
		
		row = 0
		col = 0
		# Translator: A label on the RulesManager dialog.
		item = wx.StaticText(self, label=_("&Filter: "))
		filtersSizer.Add(item, (row, col))
		col += 1
		filtersSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), (row, col))
		col += 1
		item = self.filterEdit = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
		item.Bind(wx.EVT_TEXT, lambda evt: self.refreshRuleList())
		item.Bind(wx.EVT_TEXT_ENTER, lambda evt: self.tree.SetFocus())
		filtersSizer.Add(item, (row, col), flag=wx.EXPAND)
		filtersSizer.AddGrowableCol(col)
		
		col += 1
		filtersSizer.Add(scale(20, 0), (row, col))
		
		col += 1
		item = self.activeOnlyCheckBox = wx.CheckBox(
			self,
			# Translator: A label on the RulesManager dialog.
			label=_("Include only rules &active on the current page")
		)
		item.Bind(wx.EVT_CHECKBOX, self.onActiveOnlyCheckBox)
		filtersSizer.Add(item, (row, col))
		
		contentsSizer.Add(filtersSizer, flag=wx.EXPAND)
		contentsSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS))
		
		item = self.tree = wx.TreeCtrl(
			self,
			size=scale(700, 300),
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT
		)
		item.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.onTreeItemActivated)
		item.Bind(wx.EVT_TREE_KEY_DOWN, self.onTreeKeyDown)
		item.Bind(wx.EVT_TREE_SEL_CHANGED, self.onTreeSelChanged)
		self.treeRoot = item.AddRoot("root")
		contentsSizer.Add(item, flag=wx.EXPAND, proportion=2)
		contentsSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS))
		
		descSizer = wx.GridBagSizer()
		descSizer.EmptyCellSize = (0, 0)
		contentsSizer.Add(descSizer, flag=wx.EXPAND, proportion=1)
		#contentsSizer.Add(descSizer, flag=wx.EXPAND)
		
		# Translator: The label for a field on the Rules manager
		item = wx.StaticText(self, label=_("Summary"))
		descSizer.Add(item, pos=(0, 0), flag=wx.EXPAND)
		descSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(1, 0))
		item = self.ruleSummary = wx.TextCtrl(
			self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.TE_RICH
		)
		descSizer.Add(item, pos=(2, 0), flag=wx.EXPAND)
		
		descSizer.Add(scale(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(0, 1))
		
		# Translator: The label for a field on the Rules manager
		item = wx.StaticText(self, label=_("Technical notes"))
		descSizer.Add(item, pos=(0, 2), flag=wx.EXPAND)
		descSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(1, 2))
		item = self.ruleComment = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
		descSizer.Add(item, pos=(2, 2), flag=wx.EXPAND)
		
		descSizer.AddGrowableCol(0)
		descSizer.AddGrowableCol(2)
		descSizer.AddGrowableRow(2)
		
		contentsSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS))
		
		btnHelper = guiHelper.ButtonHelper(wx.HORIZONTAL)
		item = self.resultMoveToButton = btnHelper.addButton(
			self,
			# Translator: The label for a button on the RulesManager dialog.
			label=_("Move to")
		)
		item.Bind(wx.EVT_BUTTON, self.onResultMoveTo)
		self.AffirmativeId = item.Id
		item.SetDefault()
		
		item = btnHelper.addButton(
			self,
			# Translator: The label for a button on the RulesManager dialog.
			label=_("&New rule...")
		)
		item.Bind(wx.EVT_BUTTON, self.onRuleNew)
		
		item = self.ruleEditButton = btnHelper.addButton(
			self,
			# Translator: The label for a button on the RulesManager dialog.
			label=_("&Edit...")
		)
		item.Bind(wx.EVT_BUTTON, self.onRuleEdit)
		item.Enabled = False
		
		item = self.ruleDeleteButton = btnHelper.addButton(
			self,
			# Translator: The label for a button on the RulesManager dialog.
			label=_("&Delete")
		)
		item.Bind(wx.EVT_BUTTON, self.onRuleDelete)
		item.Enabled = False
		
		contentsSizer.Add(btnHelper.sizer, flag=wx.ALIGN_RIGHT)
		mainSizer.Add(
			contentsSizer,
			border=guiHelper.BORDER_FOR_DIALOGS,
			flag=wx.ALL | wx.EXPAND,
			proportion=1,
		)
		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.CLOSE),
			flag=wx.EXPAND | wx.BOTTOM,
			border=guiHelper.BORDER_FOR_DIALOGS
		)
		mainSizer.Fit(self)
		self.Sizer = mainSizer
		self.CentreOnScreen()
		self.tree.SetFocus()
	
	def initData(self, context):
		global lastGroupBy, lastActiveOnly
		super().initData(context)
		context["initialSelectedResult"] = context.get("result")
		self.activeOnlyCheckBox.Value = lastActiveOnly
		mgr = context["webModule"].ruleManager
		# disableGroupByPosition returns True if it triggered refresh
		not mgr.isReady and self.disableGroupByPosition() or self.onGroupByRadio(None)
	
	def getSelectedObject(self):
		selection = self.tree.Selection
		if not selection.IsOk():
			return None
		return self.tree.GetItemData(self.tree.Selection).obj
	
	def getSelectedRule(self):
		obj = self.getSelectedObject()
		if not obj:
			return None
		elif isinstance(obj, Rule):
			return obj
		elif isinstance(obj, Result):
			return obj.rule
		return None
	
	def cycleGroupBy(self, previous: bool = False, report: bool = True):
		radioBox = self.groupByRadio
		index = radioBox.Selection
		for safeGuard in range(radioBox.Count):
			index = (index + (-1 if previous else 1)) % radioBox.Count
			if radioBox.IsItemEnabled(index):
				break
			safeGuard += 1
		radioBox.SetSelection(index)
		if report:
			# Translators: Reported when cycling through rules grouping on the Rules Manager dialog
			ui.message(_("Group by: {}").format(
				stripAccel(GROUP_BY[self.groupByRadio.GetSelection()].label).lower())
			)
		self.onGroupByRadio(None)
	
	@guarded
	def copyRule(self):
		obj = self.getSelectedObject()
		if obj is None:
			wx.Bell()
			return
		rule = None
		if isinstance(obj, Result):
			rule = obj.rule
		elif isinstance(obj, Rule):
			rule = obj
		data = {"webAccess.rule" : rule.dump()}
		import json
		data = json.dumps(data, indent=4)
		import api
		if api.copyToClip(data):
			# Translators: A message from the Rules Manager dialog
			ui.message(_("Rule data copied to clipboard"))
			return
		wx.Bell()
	
	def disableGroupByPosition(self) -> bool:
		"""Returns `True` if the tree was refreshed as of this call.
		"""
		radioBox = self.groupByRadio
		index = next(i for i, g in enumerate(GROUP_BY) if g.id == "position")
		if radioBox.IsItemEnabled(index):
			radioBox.EnableItem(index, False)
			if radioBox.Selection == index:
				self.cycleGroupBy(previous=True, report=False)  # Selects groupBy name
				return True
		return False
	
	def pasteRule(self):
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
		if not (isinstance(data, dict) and len(data) == 1):
			wx.Bell()
			return
		key, data = data.popitem()
		if key == "webAccess.rule":
			pass
		elif key == "webAccess.criteria":
			data = {"type": ruleTypes.MARKER, "criteria": [data]}
		elif key == "webAccess.selector":
			data = {"type": ruleTypes.MARKER, "criteria": [{"selector": data}]}
		else:
			wx.Bell()
			return
		self.onRuleNew(pastedData=data)
	
	def refreshRuleList(self):
		context = self.context
		result = context.pop("initialSelectedResult", None)
		groupBy = GROUP_BY[self.groupByRadio.GetSelection()]
		if groupBy.id == "position":
			selectObj = result
		else:
			# Pop the just created or edited rule in order to avoid keeping it selected
			# when later cycling through groupBy
			selectObj = context.pop("rule", result.rule if result else None)
		filter = self.filterEdit.Value.casefold()
		active = self.activeOnlyCheckBox.Value
		tree = self.tree
		root = self.treeRoot
		tree.DeleteChildren(root)
		
		tids = groupBy.func(
			self.context["webModule"].ruleManager,
			filter,
			active
		) if groupBy.func else []
		
		selectTreeItem = None
		
		def addToTree(parent, tids):
			nonlocal selectTreeItem
			for tid in tids:
				tii = tree.AppendItem(parent, tid.label)
				tree.SetItemData(tii, tid)
				if selectTreeItem is None:
					if tid.obj is selectObj:
						selectTreeItem = tii
				if tid.children:
					addToTree(tii, tid.children)
		
		addToTree(root, tids)
		
		if filter or groupBy.id == "position":
			tree.ExpandAllChildren(root)
		
		if selectTreeItem is None and groupBy.id != "position":
			firstChild, cookie = tree.GetFirstChild(root)
			if firstChild.IsOk():
				selectTreeItem = firstChild
		
		if selectTreeItem:
			tree.SelectItem(selectTreeItem)
			tree.EnsureVisible(selectTreeItem)
	
	def refreshTitle(self):
		context = self.context
		webModule = context["webModule"]
		groupBy = GROUP_BY[self.groupByRadio.GetSelection()]
		if self.filterEdit.Value:
			if groupBy.id != "position" and lastActiveOnly:
				# Translators: A possible title of the Rules Manager dialog
				title = "Web Module {} - Filtered active rules by {}"
			else:
				# Translators: A possible title of the Rules Manager dialog
				title = "Web Module {} - Filtered rules by {}"
		else:
			if groupBy.id != "position" and lastActiveOnly:
				# Translators: A possible title of the Rules Manager dialog
				title = "Web Module {} - Active rules by {}"
			else:
				# Translators: A possible title of the Rules Manager dialog
				title = "Web Module {} - Rules by {}"
		title = title.format(webModule.name, stripAccel(groupBy.label).lower())
		if groupBy.id == "position" and webModule.ruleManager.rootRuleManager.subModules.all():
			title += " for all active WebModules on this page"
		if config.conf["webAccess"]["devMode"]:
			title += " ({})".format("/".join((layer.name for layer in webModule.layers)))
		self.Title = title
	
	@guarded
	def onActiveOnlyCheckBox(self, evt):
		global lastActiveOnly
		if not self.Enabled:
			return
		lastActiveOnly = self.activeOnlyCheckBox.Value
		self.refreshRuleList()
	
	@guarded
	def onCharHook(self, evt: wx.KeyEvent):
		keyCode = evt.KeyCode
		mods = evt.GetModifiers()
		if keyCode == wx.WXK_ESCAPE:
			# Try to limit the difficulty of closing the dialog using the keyboard
			# in the event of an error later in this function
			evt.Skip()
			return
		elif keyCode == wx.WXK_F6 and mods | wx.MOD_SHIFT == wx.MOD_SHIFT:
			if self.tree.HasFocus():
				getattr(self, "_lastDetails", self.ruleSummary).SetFocus()
				return
			else:
				for ctrl in (self.ruleSummary, self.ruleComment):
					if ctrl.HasFocus():
						self._lastDetails = ctrl
						self.tree.SetFocus()
						return
		elif keyCode == wx.WXK_RETURN and mods == wx.MOD_NONE:
			# filterEdit is handled separately (TE_PROCESS_ENTER)
			for ctrl in (self.groupByRadio, self.activeOnlyCheckBox):
			 	if ctrl.HasFocus():
			 		self.tree.SetFocus()
			 		return
		elif (
			keyCode == wx.WXK_TAB
			and ((mods | wx.MOD_SHIFT) & wx.MOD_CONTROL) == (wx.MOD_CONTROL | wx.MOD_SHIFT)
		):
			self.cycleGroupBy(previous=evt.ShiftDown())
			return
		elif self.tree.HasFocus():
			# Collapse/Expand all instead of current node as there are only two levels.
			char = getCharFromKeyEvent(evt)
			if char == "*":
				self.tree.ExpandAll()
				return
			elif char == "/":
				self.tree.CollapseAll()
				return
			elif (
				keyCode in (ord("C"), wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT)
				and mods == wx.MOD_CONTROL
			):
				self.copyRule()
				return
			elif(
				keyCode == ord("V") and mods == wx.MOD_CONTROL
				or keyCode in (wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT) and mods == wx.MOD_SHIFT
			):
				self.pasteRule()
				return
		evt.Skip()
	
	@guarded
	def onGroupByRadio(self, evt=None, report=False):
		global lastGroupBy, lastActiveOnly
		self.refreshTitle()
		groupBy = GROUP_BY[self.groupByRadio.GetSelection()]
		lastGroupBy = groupBy.id
		if groupBy.id == "position":
			self.activeOnlyCheckBox.Enabled = False
			lastActiveOnly = self.activeOnlyCheckBox.Value
			self.activeOnlyCheckBox.Value = True
		else:
			self.activeOnlyCheckBox.Value = lastActiveOnly
			self.activeOnlyCheckBox.Enabled = True
		self.refreshRuleList()
	
	@guarded
	def onResultMoveTo(self, evt):
		obj = self.getSelectedObject()
		if not obj:
			wx.Bell()
			return
		result = None
		if isinstance(obj, Result):
			result = obj
		elif isinstance(obj, Rule):
			result = next(iter(rule_getResults_safe(obj)), None)
		if not result:
			wx.Bell()
			return
		queueHandler.queueFunction(
			queueHandler.eventQueue,
			result.script_moveto,
			None
		)
		self.Close()
	
	@guarded
	def onRuleDelete(self, evt):
		rule = self.getSelectedRule()
		if not rule:
			wx.Bell()
			return
		if gui.messageBox(
			(
				# Translator: A confirmation prompt on the RulesManager dialog.
				_("Are you sure you want to delete this rule?")
				+ "\n\n"
				+ rule.name
			),
			# Translator: The title for a confirmation prompt on the
			# RulesManager dialog.
			_("Confirm Deletion"),
			wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, self
		) == wx.YES:
			webModule = getEditableWebModule(self.context["webModule"], layerName=rule.layer)
			if not webModule:
				return
			rule.ruleManager.removeRule(rule)
			save(
				webModule=self.context["webModule"],
				layerName=rule.layer,
			)
			# As a rule was deleted, all results are to be considered obsolete
			self.disableGroupByPosition()
			self.refreshRuleList()
		wx.CallAfter(self.tree.SetFocus)
	
	@guarded
	def onRuleEdit(self, evt):
		rule = self.getSelectedRule()
		if not rule:
			wx.Bell()
			return
		context = self.context.copy()
		context["new"] = False
		context["rule"] = rule
		context["webModule"] = rule.ruleManager.webModule
		context.setdefault("data", {})["rule"] = rule.dump()
		from . import editor
		if editor.supportsSimpleMode(context):
			from . import wizard
			show = wizard.show
		else:
			show = editor.show
		if show(context, parent=self):
			rule = self.context["rule"] = context["rule"]
			# As the rule changed, all results are to be considered obsolete
			if not self.disableGroupByPosition():
				self.refreshRuleList()
		context.get("data", {}).pop("rule", None)
		wx.CallAfter(self.tree.SetFocus)
	
	@guarded
	def onRuleNew(self, evt=None, pastedData=None):
		context = self.context.copy()
		context["new"] = True
		context.get("data", {}).pop("rule", None)
		if pastedData:
			context.setdefault("data", {})["rule"] = pastedData
		from . import editor
		if not pastedData or editor.supportsSimpleMode(context):
			from . import wizard
			show = wizard.show
		else:
			show = editor.show
		if show(context, parent=self):
			rule = self.context["rule"] = context["rule"]
			# As a new rule was created, all results are to be considered obsolete
			if not self.disableGroupByPosition():
				self.refreshRuleList()
		wx.CallAfter(self.tree.SetFocus)
	
	@guarded
	def onTreeItemActivated(self, evt):
		self.onResultMoveTo(evt)
	
	@guarded
	def onTreeKeyDown(self, evt):
		keycode = evt.KeyCode
		if keycode == wx.WXK_DELETE:
			self.onRuleDelete(None)
		elif keycode == wx.WXK_F2:
			self.onRuleEdit(None)
		else:
			evt.Skip()
	
	@guarded
	def onTreeSelChanged(self, evt):
		if (
			evt is not None
			and (evt.EventObject is None or evt.EventObject.IsBeingDeleted())
		):
			return
		rule = self.getSelectedRule()
		if not rule:
			self.resultMoveToButton.Enabled = False
			self.ruleDeleteButton.Enabled = False
			self.ruleEditButton.Enabled = False
			self.ruleSummary.Value = ""
			self.ruleComment.Value = ""
		else:
			self.resultMoveToButton.Enabled = bool(rule_getResults_safe(rule))
			self.ruleDeleteButton.Enabled = True
			self.ruleEditButton.Enabled = True
			# Mapping union was added only in Python 3.9
			context = self.context.copy()
			context["rule"] = rule
			self.ruleSummary.Value = getSummary(context, rule.dump())
			self.ruleComment.Value = rule.comment or ""
