# globalPlugins/webAccess/gui/rulesManager.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2019 Accessolutions (http://accessolutions.fr)
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

__version__ = "2019.04.11"
__author__ = u"Shirley Noël <shirley.noel@pole-emploi.fr>"


from collections import namedtuple
import wx

import addonHandler
import gui
import inputCore
import queueHandler

from ..ruleHandler import (
	MarkerQuery,
	MarkerResult,
	Zone,
	builtinRuleActions,
	ruleTypes,
	showCreator,
	showEditor,
)
from .. import webModuleHandler


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

lastGroupBy = "position"
lastActiveOnly = False


addonHandler.initTranslation()


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
	return u"{main} ({source})".format(source=source, main=main)


def getRuleLabel(rule):
	label = rule.name
	if rule._gestureMap:
		label += u" ({gestures})".format(gestures=u", ".join(
			inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
			for identifier in rule._gestureMap.keys()
		))
	return label


def getRulesByGesture(markerManager, filter=None, active=False):
	gestures = {}
	noGesture = []
	for rule in markerManager.getQueries():
		if filter and filter not in rule.name:
			continue
		if active and not rule.getResults():
			continue
		for gesture, action in iteritems(rule.gestures):
			rules = gestures.setdefault(getGestureLabel(gesture), [])
			rules.append(TreeItemData(
				label=(
					u"{rule} - {action}".format(
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
		gestures.items(),
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


def getRulesByName(markerManager, filter=None, active=False):
	return sorted(
		(
			TreeItemData(
				label=getRuleLabel(rule),
				obj=rule,
				children=[]
			)
			for rule in markerManager.getQueries()
			if (
				(not filter or filter.lower() in rule.name.lower())
				and (not active or rule.getResults())
			)
		),
		key=lambda tid: tid.label.lower()
	)


def getRulesByPosition(markerManager, filter=None, active=True):
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
	
	parent = None
	for result in markerManager.getResults():
		rule = result.markerQuery
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


def getRulesByType(markerManager, filter=None, active=False):
	types = {}
	for rule in markerManager.getQueries():
		if (
			(filter and filter.lower() not in rule.name.lower())
			or (active and not rule.getResults())
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
		contentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)
		
		filtersSizer = wx.GridSizer(1, 2, 10, 10)
		
		labeledCtrlHelper = gui.guiHelper.LabeledControlHelper(
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
			gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
		)
		
		item = self.tree = wx.TreeCtrl(
			self,
			size=wx.Size(700, 500),
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT
		)
		item.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.onTreeItemActivated)
		item.Bind(wx.EVT_TREE_KEY_DOWN, self.onTreeKeyDown)
		item.Bind(wx.EVT_TREE_SEL_CHANGED, self.onTreeSelChanged)
		self.treeRoot = item.AddRoot("root")
		contentsSizer.Add(item, flag=wx.EXPAND, proportion=1)
		contentsSizer.AddSpacer(
			gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
		)

		ruleCommentLabel = wx.StaticText(self, label="Description")
		contentsSizer.Add(ruleCommentLabel, flag=wx.EXPAND)
		self.ruleComment = wx.TextCtrl(
			self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NO_VSCROLL
		)
		contentsSizer.Add(self.ruleComment, flag=wx.EXPAND)
		contentsSizer.AddSpacer(
			gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
		)

		btnHelper = gui.guiHelper.ButtonHelper(wx.HORIZONTAL)
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
			border=gui.guiHelper.BORDER_FOR_DIALOGS,
			flag=wx.ALL | wx.EXPAND,
			proportion=1,
		)
		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.CLOSE),
			flag=wx.EXPAND | wx.BOTTOM,
			border=gui.guiHelper.BORDER_FOR_DIALOGS
		)
		mainSizer.Fit(self)
		self.Sizer = mainSizer
		self.CentreOnScreen()
	
	def initData(self, context):
		global lastGroupBy, lastActiveOnly
		self.context = context
		self.markerManager = context["webModule"].markerManager
		self.Title = u"Web Module - %s" % self.markerManager.webApp.name
		self.activeOnlyCheckBox.Value = lastActiveOnly
		self.groupByRadio.Selection = next((
			index
			for index, groupBy in enumerate(GROUP_BY)
			if groupBy.id == lastGroupBy
		))
		self.onGroupByRadio(None, refresh=True)
		self.refreshRuleList(selectObj=context.get("rule"))
	
	def getSelectedObject(self):
		return TreeCtrl_GetItemData(self.tree, self.tree.Selection).obj
	
	def getSelectedRule(self):
		obj = self.getSelectedObject()
		if not obj:
			return None
		elif isinstance(obj, MarkerQuery):
			return obj
		elif isinstance(obj, MarkerResult):
			return obj.markerQuery
		return None
	
	def refreshRuleList(self, selectName=None, selectObj=None):
		groupBy = GROUP_BY[self.groupByRadio.GetSelection()]
		filter = self.filterEdit.GetValue()
		active = self.activeOnlyCheckBox.Value
		self.tree.DeleteChildren(self.treeRoot)
		
		tids = groupBy.func(
			self.markerManager,
			filter,
			active
		) if groupBy.func else []
		
		# Would be replaced by use of nonlocal in Python 3
		class SharedScope(object):
			__slots__ = ("selectTreeItem",)
		
		shared = SharedScope()
		shared.selectTreeItem = None
		selectRule = None
		if selectObj and isinstance(selectObj, MarkerResult):
			selectRule = selectObj.markerQuery
		
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
			self.tree.SelectItem(shared.selectTreeItem)
			return
		wx.CallAfter(self.tree.Unselect)
	
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
		if isinstance(obj, MarkerResult):
			result = obj
		elif isinstance(obj, MarkerQuery):
			result = next(iter(obj.getResults()), None)
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
			self.markerManager.removeQuery(rule)
			webModuleHandler.update(
				webModule=self.context["webModule"],
				focus=self.context["focusObject"]
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
		if showEditor(context):
			# Pass the eventually changed rule name
			self.refreshRuleList(context["data"]["rule"]["name"])
		wx.CallAfter(self.tree.SetFocus)
	
	def onRuleNew(self, evt):
		context = self.context.copy()  # Shallow copy
		if showCreator(context):
			self.refreshRuleList(context["data"]["rule"]["name"])
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
		if evt.EventObject is None or evt.EventObject.IsBeingDeleted():
			return
		rule = self.getSelectedRule()
		if not rule:
			self.resultMoveToButton.Enabled = False
			self.ruleDeleteButton.Enabled = False
			self.ruleEditButton.Enabled = False
			self.ruleComment.Value = ""
		else:
			self.resultMoveToButton.Enabled = bool(rule.getResults())
			self.ruleDeleteButton.Enabled = True
			self.ruleEditButton.Enabled = True
			self.ruleComment.Value = rule.comment or ""
	
	def ShowModal(self, context):
		self.initData(context)
		self.Fit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.tree.SetFocus()
		return super(Dialog, self).ShowModal()
