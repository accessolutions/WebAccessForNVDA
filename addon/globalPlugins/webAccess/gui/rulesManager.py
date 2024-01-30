# globalPlugins/webAccess/gui/rulesManager.py
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


__version__ = "2021.04.06"
__author__ = "Shirley Noël <shirley.noel@pole-emploi.fr>"


from collections import namedtuple
import wx

import addonHandler
import config
import gui
import inputCore
import queueHandler
from logHandler import log

from ..ruleHandler import (
	Rule,
	Result,
	Zone,
	builtinRuleActions,
	ruleTypes,
	showCreator,
	showEditor,
)
from ..webModuleHandler import getEditableWebModule, save

try:
	from six import iteritems
except ImportError:
	# NVDA version < 2018.3
	iteritems = dict.iteritems

try:
	TreeCtrl_GetItemData = wx.TreeCtrl.GetItemPyData
	TreeCtrl_SetItemData = wx.TreeCtrl.SetItemPyData
except AttributeError:
	# NVDA version < 2018.3
	TreeCtrl_GetItemData = wx.TreeCtrl.GetItemData
	TreeCtrl_SetItemData = wx.TreeCtrl.SetItemData

try:
	from gui import guiHelper
except ImportError:
	from ..backports.nvda_2016_4 import gui_guiHelper as guiHelper


addonHandler.initTranslation()


lastGroupBy = "position"
lastActiveOnly = False


def show(context):
	gui.mainFrame.prePopup()
	Dialog(gui.mainFrame).ShowModal(context)
	gui.mainFrame.postPopup()


TreeItemData = namedtuple("TreeItemData", ("label", "obj", "children"))


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
		layer = webModule._getWritableLayer().name
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


def getRulesByGesture(ruleManager, filter=None, active=False):
	gestures = {}
	noGesture = []

	for rule in getRules(ruleManager):
		if filter and filter not in rule.name:
			continue
		if active and not rule_getResults_safe(rule):
			continue
		for gesture, action in iteritems(rule.gestures):
			log.info("========================================> rule.gesture ====> {]".format(rule.gestures))
			rules = gestures.setdefault(getGestureLabel(gesture), [])
			rules.append(TreeItemData(
				label=(
					"{rule} - {action}".format(
						rule=rule.name,
						action=builtinRuleActions.get(action, action)
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
	for gesture, tids in sorted(
		list(gestures.items()),
		key=lambda kvp: kvp[0]
	):
		yield TreeItemData(
			label=gesture,
			obj=None,
			children=sorted(tids, key=lambda tid: tid.label)
		)
	if noGesture:
		yield TreeItemData(
			# Translator: TreeItem label on the RulesManager dialog.
			label=pgettext("webAccess.ruleGesture", "<None>"),
			obj=None,
			children=sorted(noGesture, key=lambda tid: tid.label)
		)


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
				(not filter or filter.lower() in rule.name.lower())
				and (not active or rule_getResults_safe(rule))
			)
		),
		key=lambda tid: tid.label.lower()
	)


def getRulesByPosition(ruleManager, filter=None, active=True):
	"""
	Yield rules by position.
	
	As position depends on result, the `active` criteria is ignored.
	"""
	Parent = namedtuple("Parent", ("parent", "tid", "zone"))
	
	def filterChildlessParent(parent):
		if (
			not filter
			or parent.tid.children
			or filter.lower() in parent.tid.obj.name.lower()
		):
			return False
		if parent.parent:
			parent.parent.tid.children.remove(parent)
		return True
	
	webModule = ruleManager.webModule
	if not webModule.isReadOnly():
		layer = webModule._getWritableLayer()
	elif config.conf["webAccess"]["devMode"]:
		layer = None
	else:
		return
	
	parent = None
	for result in ruleManager.getResults():
		rule = result.rule
		if layer is not None and rule.layer != layer.name:
			continue
		tid = TreeItemData(
			label=getRuleLabel(rule),
			obj=result,
			children=[]
		)
		zone = None
		if rule.type in (ruleTypes.PARENT, ruleTypes.ZONE):
			zone = Zone(result)
		elif filter and filter.lower() not in rule.name.lower():
			continue
		while parent:
			if parent.zone.containsResult(result):
				parent.tid.children.append(tid)
				if zone:
					parent = Parent(parent, tid, zone)
				break
			elif not filterChildlessParent(parent):
				yield parent.tid
			parent = parent.parent
		else:  # no parent
			assert parent is None
			if zone:
				parent = Parent(None, tid, zone)
			else:
				yield tid
	while parent:
		if not filterChildlessParent(parent):
			yield parent.tid
		parent = parent.parent


def getRulesByType(ruleManager, filter=None, active=False):
	types = {}
	for rule in getRules(ruleManager):
		if (
			(filter and filter.lower() not in rule.name.lower())
			or (active and not rule_getResults_safe(rule))
		):
			continue
		types.setdefault(rule.type, []).append(TreeItemData(
			label=getRuleLabel(rule),
			obj=rule,
			children=[]
		))
	for ruleType, label in iteritems(ruleTypes.ruleTypeLabels):
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
		id="gestures",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "&Gestures"),
		func=getRulesByGesture
	),
	GroupBy(
		id="name",
		# Translator: Grouping option on the RulesManager dialog.
		label=pgettext("webAccess.rulesGroupBy", "Nam&e"),
		func=getRulesByName
	),
)


class Dialog(wx.Dialog):

	def __init__(self, parent):
		super(Dialog, self).__init__(
			parent=gui.mainFrame,
			id=wx.ID_ANY,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX
		)
		
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		contentsSizer = wx.BoxSizer(wx.VERTICAL)
		
		item = self.groupByRadio = wx.RadioBox(
			self,
			# Translator: A label on the RulesManager dialog.
			label=_("Group by: "),
			choices=tuple((groupBy.label for groupBy in GROUP_BY)),
			majorDimension=len(GROUP_BY) + 3  # +1 for the label
		)
		item.Bind(wx.EVT_RADIOBOX, self.onGroupByRadio)
		contentsSizer.Add(item, flag=wx.EXPAND)
		contentsSizer.AddSpacer(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)
		
		filtersSizer = wx.GridSizer(1, 2, 10, 10)
		
		labeledCtrlHelper = guiHelper.LabeledControlHelper(
			self,
			# Translator: A label on the RulesManager dialog.
			_("&Filter: "),
			wx.TextCtrl, size=(250, -1), style=wx.TE_PROCESS_ENTER
		)
		item = self.filterEdit = labeledCtrlHelper.control
		item.Bind(wx.EVT_TEXT, lambda evt: self.refreshRuleList())
		item.Bind(wx.EVT_TEXT_ENTER, lambda evt: self.tree.SetFocus())
		filtersSizer.Add(labeledCtrlHelper.sizer, flag=wx.EXPAND)
		
		self.activeOnlyCheckBox = wx.CheckBox(
			self,
			# Translator: A label on the RulesManager dialog.
			label=_("Include only rules &active on the current page")
		)
		self.activeOnlyCheckBox.Bind(wx.EVT_CHECKBOX, self.onActiveOnlyCheckBox)
		filtersSizer.Add(self.activeOnlyCheckBox)
		
		contentsSizer.Add(filtersSizer, flag=wx.EXPAND)
		contentsSizer.AddSpacer(
			guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
		)
		
		item = self.tree = wx.TreeCtrl(
			self,
			size=wx.Size(700, 300),
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT
		)
		item.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.onTreeItemActivated)
		item.Bind(wx.EVT_TREE_KEY_DOWN, self.onTreeKeyDown)
		item.Bind(wx.EVT_TREE_SEL_CHANGED, self.onTreeSelChanged)
		self.treeRoot = item.AddRoot("root")
		contentsSizer.Add(item, flag=wx.EXPAND, proportion=2)
		contentsSizer.AddSpacer(
			guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
		)
		
		descSizer = wx.GridBagSizer()
		descSizer.EmptyCellSize = (0, 0)
		contentsSizer.Add(descSizer, flag=wx.EXPAND, proportion=1)
		#contentsSizer.Add(descSizer, flag=wx.EXPAND)
		
		# Translator: The label for a field on the Rules manager
		item = wx.StaticText(self, label=_("Summary"))
		descSizer.Add(item, pos=(0, 0), flag=wx.EXPAND)
		descSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(1, 0))
		item = self.ruleSummary = wx.TextCtrl(
			self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.TE_RICH
		)
		descSizer.Add(item, pos=(2, 0), flag=wx.EXPAND)
		
		descSizer.Add((guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL, 0), pos=(0, 1))
		
		# Translator: The label for a field on the Rules manager
		item = wx.StaticText(self, label=_("Technical notes"))
		descSizer.Add(item, pos=(0, 2), flag=wx.EXPAND)
		descSizer.Add((0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(1, 2))
		item = self.ruleComment = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY)
		descSizer.Add(item, pos=(2, 2), flag=wx.EXPAND)
		
		descSizer.AddGrowableCol(0)
		descSizer.AddGrowableCol(2)
		descSizer.AddGrowableRow(2)
		
		contentsSizer.AddSpacer(
			guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
		)

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
	
	def initData(self, context):
		global lastGroupBy, lastActiveOnly
		self.context = context
		ruleManager = self.ruleManager = context["webModule"].ruleManager
		webModule = ruleManager.webModule
		title = "Web Module - {}".format(webModule.name)
		if config.conf["webAccess"]["devMode"]:
			title += " ({})".format("/".join((layer.name for layer in webModule.layers)))
		self.Title = title
		self.activeOnlyCheckBox.Value = lastActiveOnly
		self.groupByRadio.Selection = next((
			index
			for index, groupBy in enumerate(GROUP_BY)
			if groupBy.id == lastGroupBy
		))
		self.onGroupByRadio(None, refresh=True)
		self.refreshRuleList(selectObj=context.get("rule"))
	
	def getSelectedObject(self):
		selection = self.tree.Selection
		if not selection.IsOk():
			return None
		return TreeCtrl_GetItemData(self.tree, self.tree.Selection).obj
	
	def getSelectedRule(self):
		obj = self.getSelectedObject()
		if not obj:
			return None
		elif isinstance(obj, Rule):
			return obj
		elif isinstance(obj, Result):
			return obj.rule
		return None
	
	def refreshRuleList(self, selectName=None, selectObj=None):
		groupBy = GROUP_BY[self.groupByRadio.GetSelection()]
		filter = self.filterEdit.GetValue()
		active = self.activeOnlyCheckBox.Value
		self.tree.DeleteChildren(self.treeRoot)
		
		tids = groupBy.func(
			self.ruleManager,
			filter,
			active
		) if groupBy.func else []
		
		# Would be replaced by use of nonlocal in Python 3
		class SharedScope(object):
			__slots__ = ("selectTreeItem",)
		
		shared = SharedScope()
		shared.selectTreeItem = None
		selectRule = None
		if selectObj and isinstance(selectObj, Result):
			selectRule = selectObj.rule
		
		def addToTree(parent, tids):
			for tid in tids:
				tii = self.tree.AppendItem(parent, tid.label)
				TreeCtrl_SetItemData(self.tree, tii, tid)
				if shared.selectTreeItem is None:
					if selectName:
						if tid.label == selectName:
							shared.selectTreeItem = tii
					elif selectObj is not None:
						if tid.obj is selectObj:
							shared.selectTreeItem = tii
						elif selectRule is not None and tid.obj is selectRule:
							shared.selectTreeItem = tii
				if tid.children:
					addToTree(tii, tid.children)
		
		addToTree(self.treeRoot, tids)
		
		if filter or groupBy.id == "position":
			self.tree.ExpandAllChildren(self.treeRoot)
		
		if shared.selectTreeItem is not None:
			# Async call ensures the selection won't get lost.
			wx.CallAfter(self.tree.SelectItem, shared.selectTreeItem)
			# Sync call ensures NVDA won't announce the first item of
			# the tree before reporting the selection.
			#self.tree.SelectItem(shared.selectTreeItem)
			return
		
		def unselect():
			self.tree.Unselect()
			self.onTreeSelChanged(None)
		
		wx.CallAfter(unselect)
	
	def onActiveOnlyCheckBox(self, evt):
		global lastActiveOnly
		if not self.Enabled:
			return
		lastActiveOnly = self.activeOnlyCheckBox.Value
		self.refreshRuleList()
	
	def onGroupByRadio(self, evt, refresh=True):
		global lastGroupBy, lastActiveOnly
		groupBy = GROUP_BY[self.groupByRadio.GetSelection()]
		lastGroupBy = groupBy.id
		if groupBy.id == "position":
			self.activeOnlyCheckBox.Enabled = False
			lastActiveOnly = self.activeOnlyCheckBox.Value
			self.activeOnlyCheckBox.Value = True
		else:
			self.activeOnlyCheckBox.Value = lastActiveOnly
			self.activeOnlyCheckBox.Enabled = True
		if refresh:
			self.refreshRuleList()
	
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
			wx.YES | wx.NO | wx.CANCEL | wx.ICON_QUESTION, self
		) == wx.YES:
			webModule = getEditableWebModule(self.ruleManager.webModule, layerName=rule.layer)
			if not webModule:
				return
			self.ruleManager.removeRule(rule)
			save(
				webModule=self.context["webModule"],
				layerName=rule.layer,
			)
			self.refreshRuleList()
		wx.CallAfter(self.tree.SetFocus)
	
	def onRuleEdit(self, evt):
		rule = self.getSelectedRule()
		if not rule:
			wx.Bell()
			return
		context = self.context.copy()  # Shallow copy
		context["rule"] = rule
		if showEditor(context, parent=self):
			self.Close()
			return
# 			# Pass the eventually changed rule name
# 			self.refreshRuleList(context["data"]["rule"]["name"])
		wx.CallAfter(self.tree.SetFocus)
	
	def onRuleNew(self, evt):
		context = self.context.copy()  # Shallow copy
		if showCreator(context, parent=self):
			self.Close()
			return
# 			self.groupByRadio.SetSelection(next(iter((
# 				index
# 				for index, groupBy in enumerate(GROUP_BY)
# 				if groupBy.id == "name"
# 			))))
# 			self.refreshRuleList(context["data"]["rule"]["name"])
		wx.CallAfter(self.tree.SetFocus)
	
	def onTreeItemActivated(self, evt):
		self.onResultMoveTo(evt)
	
	def onTreeKeyDown(self, evt):
		if evt.KeyCode == wx.WXK_F2:
			self.onRuleEdit(evt)
		elif evt.KeyCode == wx.WXK_DELETE:
			self.onRuleDelete(evt)
		else:
			return
		evt.Skip()
	
	def onTreeSelChanged(self, evt):
		from logHandler import log
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
			from .ruleEditor import getSummary
			self.ruleSummary.Value = getSummary(rule.dump())
			self.ruleComment.Value = rule.comment or ""
	
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		self.CentreOnScreen()
		self.tree.SetFocus()
		return super(Dialog, self).ShowModal()
