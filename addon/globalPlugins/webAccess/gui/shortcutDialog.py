# globalPlugins/webAccess/gui/shortcutDialog.py
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

__version__ = "2018.01.03"

__author__ = (
		"Shirley Noel <shirley.noel@pole-emploi.fr>"
		)


import wx

import addonHandler
addonHandler.initTranslation()
import inputCore
from logHandler import log
import gui
import ui


def show():
	gui.mainFrame.prePopup()
	result = Dialog(gui.mainFrame).ShowModal()
	gui.mainFrame.postPopup()
	return result == wx.ID_OK


markerManager = None
resultShortcut = ""
resultActionData = ""


class Dialog(wx.Dialog):

	# Singleton
	_instance = None
	def __new__(cls, *args, **kwargs):
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

		vSizer = wx.BoxSizer(wx.VERTICAL)
		gridSizer = wx.GridBagSizer(10, 10)

		gridSizer.Add(wx.StaticText(self, label=_("&Type shortcut")), pos=(0, 0), flag=wx.EXPAND)
		inputShortcut = self.inputShortcut = wx.TextCtrl(self, value=_("NONE"))
		self.inputShortcut.Bind(wx.EVT_SET_FOCUS, self.OnFocus)
		self.inputShortcut.Bind(wx.EVT_KILL_FOCUS, self.OnBlur)

		gridSizer.Add(inputShortcut, pos=(0, 1), flag=wx.EXPAND)

		gridSizer.Add(wx.StaticText(self, label=_("&Action to execute")), pos=(1, 0), flag=wx.EXPAND)

		global markerManager
		choiceAction = self.action = wx.Choice(self)
		actionsDict = markerManager.getActions ()
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

		self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)

		vSizer.AddSpacer(5)
		self.Sizer = vSizer


	def InitData(self):
		self.Title = _("Shortcut dialog")
		self.isModifierActive = False
		self.inputShortcut.Value = _("NONE")
		self.action.SetSelection(-1)
		global resultShortcut
		resultShortcut = ""
		global resultActionData
		resultActionData = ""


	def OnFocus(self, evt):
		inputCore.manager._captureFunc = self.CaptureFunction


	def CaptureFunction(self, gesture):
		oldValue = self.inputShortcut.Value
		if not gesture.isModifier:
			gestureIdentifier = None
			# search the shortest gesture identifier(without source)
			for identifier in gesture.identifiers:
				if gestureIdentifier is None:
					gestureIdentifier = identifier
				elif len(identifier) < len(gestureIdentifier):
					gestureIdentifier = identifier

			oldValue = self.inputShortcut.Value
			source, main = inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)

			if gestureIdentifier not in ["kb:tab", "kb:shift+tab", "kb:escape", "kb:enter"] :
				self.inputShortcut.Value = main
				global resultShortcut
				resultShortcut = gestureIdentifier
				if oldValue != main:
					wx.CallAfter(ui.message, _(u"Shortcut set to %s" % main))
			elif gestureIdentifier == "kb:tab":
				return True
			elif gestureIdentifier == "kb:shift+tab":
				return True
			elif gestureIdentifier == "kb:escape":
				self.OnCancel(None)
			elif gestureIdentifier == "kb:enter":
				speech.cancelSpeech()
				self.OnOk(None)
			return False
		else:
			return False


	def OnBlur(self, evt):
		inputCore.manager._captureFunc = None


	def OnOk(self, evt):
		if resultShortcut == "":
			gui.messageBox(_("You must define a shortcut"),
											_("Error"), wx.OK | wx.ICON_ERROR, self)
			self.inputShortcut.SetFocus()
			return
		if self.action.GetSelection() == -1:
			gui.messageBox(_("You must define an action"),
											_("Error"), wx.OK | wx.ICON_ERROR, self)
			self.action.SetFocus()
			return
		global resultActionData
		resultActionData = self.action.GetClientData(self.action.Selection)
		assert self.IsModal()
		self.EndModal(wx.ID_OK)


	def OnCancel(self, evt):
		self.EndModal(wx.ID_CANCEL)


	def ShowModal(self):
		self.InitData()
		self.Fit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		self.inputShortcut.SetFocus()
		return super(Dialog, self).ShowModal()

