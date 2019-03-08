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

__version__ = "2019.03.08"
__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import wx

import addonHandler
addonHandler.initTranslation()
import controlTypes
import gui
import inputCore
from logHandler import log
import ui

from .. import ruleHandler
from ..webAppLib import *
from .. import webModuleHandler
from . import ListCtrlAutoWidth


def show(context):
	gui.mainFrame.prePopup()
	Dialog(gui.mainFrame).ShowModal(context)
	gui.mainFrame.postPopup()


class TreeRule:
	def __init__(self, name, data, treeid):
		self.name = name
		self.data = data
		self.treeid = treeid
	
	def __repr__(self):
		return repr((self.name, self.treeid))

class Dialog(wx.Dialog):

	def __init__(self, parent):
		super(Dialog, self).__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)

		# Colors and margins
		mainPadding = 10
		padding = 5

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		contentsSizer = wx.BoxSizer(wx.VERTICAL)

		self.radioButtons = wx.RadioBox(self, wx.ID_ANY, label=_("Group by: "), choices=tuple(et[1] for et in self.GROUP_BY))
		self.radioButtons.SetSelection(0)
		self.radioButtons.Bind(wx.EVT_RADIOBOX, self.RefreshRuleList)
		contentsSizer.Add(self.radioButtons, flag=wx.EXPAND)
		contentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		filtersSizer = wx.GridSizer(rows=1, cols=2)

		filterText = _("Filt&er by:")
		labelledCtrl = gui.guiHelper.LabeledControlHelper(self, filterText, wx.TextCtrl)
		self.filterEdit = labelledCtrl.control
		self.filterEdit.Bind(wx.EVT_TEXT, self.RefreshRuleList)
		filtersSizer.Add(labelledCtrl.sizer)

		self.displayActiveRules = wx.CheckBox(self, label=_("Display only &active rules"))
		self.displayActiveRules.Value = False
		self.displayActiveRules.Bind(wx.EVT_CHECKBOX, self.RefreshRuleList)
		filtersSizer.Add(self.displayActiveRules)

		contentsSizer.Add(filtersSizer, flag=wx.EXPAND)
		contentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		self.ruleTree = wx.TreeCtrl(self, size=wx.Size(700, 600), style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT)
		self.ruleTree.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnRuleListChoice)
		self.ruleTreeRoot = self.ruleTree.AddRoot("root")
		contentsSizer.Add(self.ruleTree,flag=wx.EXPAND)
		contentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		ruleCommentLabel = wx.StaticText(self, label="Description")
		contentsSizer.Add(ruleCommentLabel, flag=wx.EXPAND)
		self.ruleComment = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NO_VSCROLL)
		contentsSizer.Add(self.ruleComment, flag=wx.EXPAND)
		contentsSizer.AddSpacer(gui.guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

		bHelper = gui.guiHelper.ButtonHelper(wx.HORIZONTAL)
		self.movetoButton = bHelper.addButton(self, label=_("Move to"))
		self.movetoButton.Bind(wx.EVT_BUTTON, self.OnMoveto)
		self.AffirmativeId = self.movetoButton.Id
		self.movetoButton.SetDefault()

		self.newButton = bHelper.addButton(self, label=_("&New rule..."))
		self.newButton.Bind(wx.EVT_BUTTON, self.OnNew)

		self.editButton = bHelper.addButton(self, label=_("&Edit..."))
		self.editButton.Bind(wx.EVT_BUTTON, self.OnEdit)
		self.editButton.Enabled = False
		gridSizer.Add(button, pos=(3, 1), flag=wx.EXPAND)

		button = self.deleteButton = wx.Button(self, label=_("&Delete"))
		button.Bind(wx.EVT_BUTTON, self.OnDelete)
		self.deleteButton.Enabled = False
		gridSizer.Add(button, pos=(4, 1), flag=wx.EXPAND)

		checkBox = self.displayActiveRules = wx.CheckBox(self, label=_("Display only &active rules"))
		checkBox.Value = False
		checkBox.Bind(wx.EVT_CHECKBOX, self.OnDisplayActiveRules)
		gridSizer.Add(checkBox, pos=(5, 0), flag=wx.EXPAND)

		mainSizer.Add(gridSizer, flag=wx.EXPAND | wx.ALL, border=mainPadding)

		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.CLOSE),
			flag=wx.EXPAND
			)
		mainSizer.AddSpacer(mainPadding)
		mainSizer.Fit(self)
		self.Sizer = mainSizer

		self.CentreOnScreen()

	def __del__(self):
		Dialog._instance = None

	def InitData(self, context):
		self.context = context
		webModule = context["webModule"]
		self.markerManager = webModule.markerManager
		self.rule = context["rule"]
		self.GetRules()
		self.RefreshRuleList()

	def GetRules(self):
		self.treeRuleList = []
		for result in self.markerManager.getResults():
			self.treeRuleList.append(TreeRule(self.GetRuleName(result, result.markerQuery.gestures), result, None))

		for query in self.markerManager.getQueries():
			if query not in [x.markerQuery for x in self.markerManager.getResults()]:
				self.treeRuleList.append(TreeRule(self.GetRuleName(query, query.gestures), query, None))

	def RefreshRuleList(self, selectName = None):
		api.processPendingEvents()
		"""
		Refresh the list of rules.
		
		If *selectName" is set, the rule with that name gets selected.
		Otherwise, the rule matching the current focus in the document,
		if any, gets selected.
		"""
		currentGroupBy = self.GROUP_BY[self.radioButtons.GetSelection()][0]
		filterText = self.filterEdit.GetValue()
		self.ruleTree.DeleteChildren(self.ruleTreeRoot)

		# NAME GROUP BY
		if currentGroupBy == 'Name':
			sortedTreeRuleList = sorted(self.treeRuleList, key=lambda rule: rule.name.lower())

			for rule in sortedTreeRuleList:
				if not self.displayActiveRules.Value or isinstance(rule.data, ruleHandler.MarkerResult):
					if not filterText or filterText in rule.name:
						rule.treeid = self.ruleTree.AppendItem(self.ruleTreeRoot, rule.name)

		# GESTURES GROUP BY
		elif currentGroupBy == 'Gestures':
			gesturesDic = {}
			noGesturesList = []
			for rule in self.treeRuleList:
				if not self.displayActiveRules.Value or isinstance(rule.data, ruleHandler.MarkerResult):
					if not filterText or filterText in rule.name:
						gestures = []
						if isinstance(rule.data, ruleHandler.MarkerResult):
							gestures = rule.data.markerQuery.gestures
						else:
							gestures = rule.data.gestures
						if len(gestures):
							for gesture in gestures:
								if gesturesDic.get(gesture):
									gesturesDic[gesture].append(rule.data)
								else:
									gesturesDic[gesture] = [rule.data]
						else:
							noGesturesList.append(rule.data)

			for gestureKey in gesturesDic.keys():
				gestureTreeId = self.ruleTree.AppendItem(self.ruleTreeRoot, gestureKey)
				for rule in gesturesDic[gestureKey]:
					rule.treeid = self.ruleTree.AppendItem(gestureTreeId, rule.name)

			noGestureTreeId = self.ruleTree.AppendItem(self.ruleTreeRoot, 'none')
			for rule in noGesturesList:
				rule.treeid = self.ruleTree.AppendItem(noGestureTreeId, rule.name)

		if selectName and isinstance(selectName, str):
			print("SELECT", selectName)
			self.ruleTree.SelectItem([x.treeid for x in self.treeRuleList if x.data.name == selectName][0])
		elif self.rule:
			print("RULE", self.rule.name, [x.treeid for x in self.treeRuleList if x.data.name == self.rule.name], [x.name for x in self.treeRuleList if x.data.name == self.rule.name])
			self.ruleTree.SelectItem([x.treeid for x in self.treeRuleList if x.data.name == self.rule.name][0])

	def GetRuleName(self, rule, gestures):
		ruleName = [rule.name]
		gesturesKeys = gestures.keys()

		if len(gesturesKeys):
			for gestureKey in gesturesKeys:
				ruleName.append(" - ")
				ruleName.append(gestures[gestureKey])
		return ''.join(ruleName)

	def OnMoveto(self, evt):
		sel = self.ruleList.Selection
		result = self.ruleList.GetClientData(sel)
		if not isinstance(result, ruleHandler.MarkerResult):
			wx.Bell()
			return
		result.script_moveto (None)
		self.Close()

	def OnNew(self, evt):
		context = self.context.copy()  # Shallow copy
		if ruleHandler.showCreator(context):
			self.RefreshRuleList(context["data"]["rule"]["name"])
			self.ruleList.SetFocus()

	def OnDelete(self, evt):
		sel = self.ruleList.Selection
		if gui.messageBox(
			_("Are you sure you want to delete this rule?"),
			_("Confirm Deletion"),
			wx.YES | wx.NO | wx.ICON_QUESTION, self
		) == wx.NO:
			return
		rule = self.ruleList.GetClientData(sel)
		if isinstance(rule, ruleHandler.MarkerQuery):
			query = rule
		else:
			query = rule.markerQuery
		self.markerManager.removeQuery(query)
		webModuleHandler.update(
			webModule=self.context["webModule"],
			focus=self.context["focusObject"]
			)
		self.RefreshRuleList()
		self.ruleList.SetFocus()

	def OnRuleListChoice(self, evt):
		sel = self.ruleList.Selection
		if sel < 0:
			self.movetoButton.Enabled = False
			self.deleteButton.Enabled = False
			self.editButton.Enabled = False
			return
		result = [x.data for x in self.treeRuleList if x.treeid == sel][0]
		comment = ''
		if isinstance(result, ruleHandler.MarkerResult):
			self.movetoButton.Enabled = True
			if result.markerQuery.comment:
				comment = result.markerQuery.comment
		else:
			self.movetoButton.Enabled = False
			if result.comment:
				comment = result.comment
		self.ruleComment.SetValue(comment)
		self.deleteButton.Enabled = True
		self.editButton.Enabled = True

	def OnEdit(self, evt):
		sel = self.ruleList.Selection
		marker = self.ruleList.GetClientData(sel)
		if isinstance(marker, ruleHandler.MarkerQuery):
			query = marker
		else:
			query = marker.markerQuery
		context = self.context.copy()  # Shallow copy
		context["rule"] = query
		if ruleHandler.showEditor(context):
			# Pass the eventually changed rule name
			self.RefreshRuleList(context["data"]["rule"]["name"])
			self.ruleList.SetFocus()


	def ShowModal(self, context):
		self.InitData(context)
		self.Fit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.ruleList.SetFocus()
		return super(Dialog, self).ShowModal()
