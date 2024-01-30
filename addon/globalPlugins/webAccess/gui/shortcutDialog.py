# globalPlugins/webAccess/gui/shortcutDialog.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2020 Accessolutions (http://accessolutions.fr)
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


__version__ = "2020.12.22"
__author__ = "Shirley Noel <shirley.noel@pole-emploi.fr>"


import wx

import addonHandler
import inputCore
import gui
import speech
import ui


addonHandler.initTranslation()


def show():
	gui.mainFrame.prePopup()
	result = Dialog(gui.mainFrame).ShowModal()
	gui.mainFrame.postPopup()
	return result == wx.ID_OK


ruleManager = None
resultShortcut = ""
resultActionData = ""


class Dialog(wx.Dialog):
	
	def __init__(self, parent):
		super(Dialog, self).__init__(
			parent,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		
		vSizer = wx.BoxSizer(wx.VERTICAL)
		gridSizer = wx.GridBagSizer(10, 10)
		
		gridSizer.Add(
			wx.StaticText(self, label=_("&Type shortcut")),
			pos=(0, 0),
			flag=wx.EXPAND
		)
		inputShortcut = self.inputShortcut = wx.TextCtrl(
			self,
#			style=wx.TE_READONLY | wx.TAB_TRAVERSAL,
			value=_("NONE")
		)
		self.inputShortcut.Bind(wx.EVT_SET_FOCUS, self.onInputShortcutFocus)
		self.inputShortcut.Bind(wx.EVT_KILL_FOCUS, self.onInputShortcutBlur)
		
		gridSizer.Add(inputShortcut, pos=(0, 1), flag=wx.EXPAND)
		
		gridSizer.Add(
			wx.StaticText(self, label=_("&Action to execute")),
			pos=(1, 0),
			flag=wx.EXPAND
		)
		
		global ruleManager
		choiceAction = self.action = wx.Choice(self)
		actionsDict = ruleManager.getActions()
		choiceAction.Append("", "")
		for action in actionsDict:
			choiceAction.Append(actionsDict[action], action)
		
		gridSizer.Add(choiceAction, pos=(1, 1), flag=wx.EXPAND)
		
		gridSizer.AddGrowableCol(0)
		gridSizer.AddGrowableCol(1)
		
		vSizer.Add(gridSizer, flag=wx.ALL | wx.EXPAND, border=10)
		
		vSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.TOP | wx.DOWN | wx.RIGHT,
			border=5
		)
		
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
		
		vSizer.AddSpacer(5)
		self.Sizer = vSizer
	
	def initData(self):
		self.Title = _("Shortcut dialog")
		self.isModifierActive = False
		self.inputShortcut.Value = _("NONE")
		self.action.SetSelection(-1)
		global resultShortcut
		resultShortcut = ""
		global resultActionData
		resultActionData = ""
	
	def onInputShortcutFocus(self, evt):
		inputCore.manager._captureFunc = self._captureFunc
	
	def _captureFunc(self, gesture):
		oldValue = self.inputShortcut.Value
		if gesture.isModifier:
			return False
		gestureIdentifier = None
		# Search the shortest gesture identifier (without source)
		for identifier in gesture.normalizedIdentifiers:
			if gestureIdentifier is None:
				gestureIdentifier = identifier
			elif len(identifier) < len(gestureIdentifier):
				gestureIdentifier = identifier

		source, main = inputCore.getDisplayTextForGestureIdentifier(
			gestureIdentifier
		)

		if gestureIdentifier not in [
			"kb:tab",
			"kb:shift+tab",
			"kb:escape",
			"kb:enter",
		]:
			# TODO: Why isn't braille refreshed?
			self.inputShortcut.Value = main
			global resultShortcut
			resultShortcut = gestureIdentifier
			if oldValue != main:
				wx.CallAfter(
					wx.CallLater,
					100,
					ui.message,
					_("Shortcut set to %s" % main)
				)
		elif gestureIdentifier == "kb:tab":
			return True
		elif gestureIdentifier == "kb:shift+tab":
			return True
		elif gestureIdentifier == "kb:escape":
			self.onCancel(None)
		elif gestureIdentifier == "kb:enter":
			speech.cancelSpeech()
			self.onOk(None)
		return False
	
	def onInputShortcutBlur(self, evt):
		inputCore.manager._captureFunc = None
	
	def onOk(self, evt):
		if resultShortcut == "":
			gui.messageBox(
				_("You must define a shortcut"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				self
			)
			self.inputShortcut.SetFocus()
			return
		if self.action.GetSelection() == -1:
			gui.messageBox(
				_("You must define an action"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				self
			)
			self.action.SetFocus()
			return
		global resultActionData
		resultActionData = self.action.GetClientData(self.action.Selection)
		assert self.IsModal()
		self.EndModal(wx.ID_OK)
	
	def onCancel(self, evt):
		self.EndModal(wx.ID_CANCEL)
	
	def ShowModal(self):
		self.initData()
		self.Fit()
		self.CenterOnScreen()
		self.inputShortcut.SetFocus()
		return super(Dialog, self).ShowModal()