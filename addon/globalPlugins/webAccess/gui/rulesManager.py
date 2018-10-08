# globalPlugins/webAccess/gui/rulesManager.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2018 Accessolutions (http://accessolutions.fr)
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

__version__ = "2018.10.06"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import wx

import addonHandler
addonHandler.initTranslation()
import api
import controlTypes
import gui
import inputCore
from logHandler import log
import ui

from .. import ruleHandler
from ..webAppLib import *
from .. import webAppScheduler
from . import ListCtrlAutoWidth


def show(context):
	gui.mainFrame.prePopup()
	Dialog(gui.mainFrame).ShowModal(context)
	gui.mainFrame.postPopup()


class Dialog(wx.Dialog):

	_instance = None

	def __new__(cls, *args, **kwargs):
		# Make this a singleton.
		if Dialog._instance is None:
			return super(Dialog, cls).__new__(cls, *args, **kwargs)
		return Dialog._instance

	def __init__(self, parent):
		if Dialog._instance is not None:
			return
		Dialog._instance = self
		super(Dialog, self).__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
			)

		# Colors and margins
		mainPadding = 10
		padding = 5

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		gridSizer = wx.GridBagSizer(padding, mainPadding)

		text = self.listLabel = wx.StaticText(self)
		gridSizer.Add(text, pos=(0, 0), flag=wx.EXPAND)

		listBox = self.ruleList = wx.ListBox(self)
		listBox.Bind(wx.EVT_LISTBOX, self.OnRuleListChoice)
		gridSizer.Add(listBox, pos=(1, 0), span=(4, 1), flag=wx.EXPAND)

		button = self.movetoButton = wx.Button(self, label=_("Move to"))
		button.Bind(wx.EVT_BUTTON, self.OnMoveto)
		self.AffirmativeId = button.Id
		button.SetDefault()
		gridSizer.Add(button, pos=(1, 1), flag=wx.EXPAND)

		button = self.newButton = wx.Button(self, label=_("&New rule..."))
		button.Bind(wx.EVT_BUTTON, self.OnNew)
		gridSizer.Add(button, pos=(2, 1), flag=wx.EXPAND)

		button = self.editButton = wx.Button(self, label=_("&Edit..."))
		button.Bind(wx.EVT_BUTTON, self.OnEdit)
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

	def __del__(self):
		Dialog._instance = None

	def InitData(self, context):
		self.context = context
		webModule = context["webModule"]
		self.markerManager = webModule.markerManager
		self.rule = context["rule"]
		self.Title = u"Web Module - %s" % webModule.name
		self.RefreshRuleList()


	def RefreshRuleList(self, selectName=None):
		"""
		Refresh the list of rules.
		
		If *selectName" is set, the rule with that name gets selected.
		Otherwise, the rule matching the current focus in the document,
		if any, gets selected.
		"""
		api.processPendingEvents()
		if not selectName:
			sel = self.ruleList.Selection
			if sel >= 0:
				selectName = self.ruleList.GetClientData(sel).name
		self.ruleList.Clear()
		self.listLabel.SetLabel(_("Active rules"))
		sel = None
		index = 0
		for result in self.markerManager.getResults():
			self.ruleList.Append(result.getDisplayString(), result)
			if selectName is not None:
				if result.name == selectName:
					sel == index
			elif result == self.rule:
				sel = index
			index += 1
		if not self.displayActiveRules.Value:
			self.listLabel.SetLabel(_("Rules"))
			for query in self.markerManager.getQueries():
				if query not in [r.markerQuery for r in self.markerManager.getResults()]:
					self.ruleList.Append(query.getDisplayString(), query)
					if query.name == selectName:
						sel = index
					index += 1
		if sel is not None:
			self.ruleList.Selection = sel
			self.ruleList.EnsureVisible(sel)
		self.OnRuleListChoice(None)

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
		webAppScheduler.scheduler.send(
			eventName="configurationChanged",
			webModule=self.markerManager.webApp,
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
		marker = self.ruleList.GetClientData(sel)
		if isinstance(marker, ruleHandler.VirtualMarkerQuery):
			self.movetoButton.Enabled = False
		else:
			self.movetoButton.Enabled = True
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

	def OnDisplayActiveRules(self, evt):
		# api.processPendingEvents()
		self.RefreshRuleList()
		# import time
		# time.sleep(0.4)
		self.ruleList.SetFocus()

	def ShowModal(self, context):
		self.InitData(context)
		self.Fit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.ruleList.SetFocus()
		return super(Dialog, self).ShowModal()
