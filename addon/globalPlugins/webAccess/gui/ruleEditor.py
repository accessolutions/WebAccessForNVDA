# globalPlugins/webAccess/gui/ruleEditor.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2016 Accessolutions (http://accessolutions.fr)
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

__version__ = "2018.10.08"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"

import wx

import addonHandler
import api
import controlTypes
import gui
import inputCore
from logHandler import log
import ui

from .. import ruleHandler
from .. import webModuleHandler
from ..webAppLib import *

addonHandler.initTranslation()

formModeRoles = [
		controlTypes.ROLE_EDITABLETEXT,
		controlTypes.ROLE_COMBOBOX,
]


def convRoleIntegerToString(role):
		return controlTypes.roleLabels.get(role, "")


def convRoleStringToInteger(role):
		for (roleInteger, roleString) in controlTypes.roleLabels.items():
				if role == roleString:
						return roleInteger
		return None


def show(context):
		gui.mainFrame.prePopup()
		result = Dialog(gui.mainFrame).ShowModal(context)
		gui.mainFrame.postPopup()
		return result == wx.ID_OK


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

				# Fonts variables
				fontTitle = wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.NORMAL, wx.NORMAL)

				# Margins
				mainPadding = 10
				padding = 5

				# Dialog main sizer
				mainSizer = wx.BoxSizer(wx.VERTICAL)
				mainSizer.AddStretchSpacer(prop=1)  # vertical centering
				mainSizer.AddSpacer(mainPadding)

				# Dialog title
				labelMainTitle = wx.StaticText(self, label=_("Add rule"))
				labelMainTitle.SetFont(fontTitle)
				mainSizer.Add(labelMainTitle, flag=wx.LEFT, border=mainPadding)
				
				# Form part
				columnSizer = wx.GridBagSizer() 

				# Static box grouping input elements for rule properties
				staticBoxRuleDef = wx.StaticBox(self, label=_("Define rule properties"))
				staticBoxSizer = wx.StaticBoxSizer(staticBoxRuleDef, orient=wx.VERTICAL)
				gridSizer = wx.GridBagSizer(padding, mainPadding)

				# Inputs
				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"Rule &name")), pos=(0, 0))
				inputCtrl = self.markerName = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(0, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"Conte&xt")), pos=(1, 0))
				inputCtrl = self.ruleContextCombo = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(1, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"Search &text")), pos=(2, 0))
				inputCtrl = self.searchText = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(2, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"&Role")), pos=(3, 0))
				inputCtrl = self.roleCombo = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(3, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"&Tag")), pos=(4, 0))
				inputCtrl = self.tagCombo = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(4, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"&ID")), pos=(5, 0))
				inputCtrl = self.idCombo = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(5, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"&Class")), pos=(6, 0))
				inputCtrl = self.classCombo = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(6, 1), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"&Image source")), pos=(7, 0))
				inputCtrl = self.srcCombo = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(7, 1), flag=wx.EXPAND)

				# Separation with options related to multiple results
				line = wx.StaticLine(staticBoxRuleDef)
				gridSizer.Add(line, pos=(8, 0), span=(1, 2), flag=wx.EXPAND | wx.BOTTOM | wx.TOP, border=padding)

				checkBox = self.multipleCheckBox = wx.CheckBox(staticBoxRuleDef, label=_(u"&Multiple results available"))
				gridSizer.Add(checkBox, pos=(9, 0), flag=wx.EXPAND)

				gridSizer.Add(wx.StaticText(staticBoxRuleDef, label=_(u"&Index")), pos=(10, 0))
				inputCtrl = self.indexText = wx.ComboBox(staticBoxRuleDef)
				gridSizer.Add(inputCtrl, pos=(10, 1), flag=wx.EXPAND)

				# Make inputs resizable with the window
				for i in range(2):
					gridSizer.AddGrowableCol(i)

				staticBoxSizer.Add(gridSizer, flag=wx.EXPAND | wx.ALL, border=mainPadding)
				columnSizer.Add(staticBoxSizer, pos=(0, 0), flag=wx.EXPAND | wx.ALL, border=mainPadding)

				# Static box grouping input elements for keyboard shortcuts
				staticBoxKeyboard = wx.StaticBox(self, label=_("Define shortcuts"))
				staticBoxSizer = wx.StaticBoxSizer(staticBoxKeyboard, orient=wx.VERTICAL)
				keyboardGridSizer = wx.GridBagSizer(padding, mainPadding)

				# Inputs
				keyboardGridSizer.Add(wx.StaticText(staticBoxKeyboard, label=_("&Keyboard shortcut")), pos=(0, 0), span=(2, 1))
				inputGesturesList = self.gesturesList = wx.ListBox(staticBoxKeyboard)
				inputGesturesList.Bind(wx.EVT_LISTBOX, self.onGesturesListChoice)
				keyboardGridSizer.Add(inputGesturesList, pos=(0, 1), span=(2, 1), flag=wx.EXPAND)

				buttonAddGesture = wx.Button(staticBoxKeyboard, label=_("Add a keyboard shortcut"))
				buttonAddGesture.Bind(wx.EVT_BUTTON, self.onAddGesture)
				keyboardGridSizer.Add(buttonAddGesture, pos=(0, 2), flag=wx.EXPAND)

				buttonDelGesture = self.deleteGestureButton = wx.Button(staticBoxKeyboard, label=_("Delete this shortcut"))
				buttonDelGesture.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
				keyboardGridSizer.Add(buttonDelGesture, pos=(1, 2), flag=wx.EXPAND)

				keyboardGridSizer.Add(wx.StaticText(staticBoxKeyboard, label=_("&Automatic action at rule detection")), pos=(2, 0))
				inputAutoAction = self.autoActionList = wx.ListBox(staticBoxKeyboard)
				keyboardGridSizer.Add(inputAutoAction, pos=(2, 1), flag=wx.EXPAND)

				line = wx.StaticLine(staticBoxKeyboard)
				keyboardGridSizer.Add(line, pos=(3, 0), span=(1, 3), flag=wx.EXPAND | wx.BOTTOM | wx.TOP, border=padding)

				checkMode = self.formModeCheckBox = wx.CheckBox(staticBoxKeyboard, label=_("Activate &form mode"))
				checkSayName = self.sayNameCheckBox = wx.CheckBox(staticBoxKeyboard, label=_("Speak r&ule name"))
				checkSkip = self.skipCheckBox = wx.CheckBox(staticBoxKeyboard, label=_("S&kip with Page Down"))
				checkIsPageTitle = self.isPageTitleCheckBox = wx.CheckBox(staticBoxKeyboard, label=_("&Page title"))
				checkIsContext = self.isContextCheckBox = wx.CheckBox(staticBoxKeyboard, label=_("&Is a context"))
				checkCreateWidget = self.createWidgetCheckBox = wx.CheckBox(staticBoxKeyboard, label=_("Create a &list of items"))
				checkCreateWidget.Enabled = False

				checkBoxTab = [checkMode, checkSayName, checkSkip, checkIsPageTitle, checkIsContext, checkCreateWidget]

				for i in range(len(checkBoxTab)):
					keyboardGridSizer.Add(checkBoxTab[i], pos=(i + 4, 0), flag=wx.TOP, border=-3)

				# Make inputs resizable with the window
				for i in range(3):
					keyboardGridSizer.AddGrowableCol(i)
					
				# Comment section
				commentBox = wx.StaticBox(self, label=_("&Comment"))
				commentBoxSizer = wx.StaticBoxSizer(commentBox, orient=wx.VERTICAL)
				inputComment = self.comment = wx.TextCtrl(commentBox, size=(500, 300), style=wx.TE_MULTILINE)
				commentBoxSizer.Add(inputComment, proportion=1, flag=wx.EXPAND | wx.ALL, border=mainPadding)
				columnSizer.Add(commentBoxSizer, pos=(0, 1), span=(3, 3), flag=wx.EXPAND | wx.ALL, border=mainPadding)

				staticBoxSizer.Add(keyboardGridSizer, flag=wx.EXPAND | wx.ALL, border=mainPadding)
				columnSizer.Add(staticBoxSizer, pos=(1, 0), flag=wx.EXPAND | wx.ALL, border=mainPadding)
				columnSizer.AddGrowableCol(0)
				columnSizer.AddGrowableCol(1)

				mainSizer.Add(columnSizer, flag=wx.EXPAND)
				mainSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), flag=wx.BOTTOM | wx.LEFT, border=mainPadding)
				self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
				self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
				mainSizer.AddStretchSpacer(prop=1)  # vertical centering
				mainSizer.Fit(self)
				self.Sizer = mainSizer

		def __del__(self):
				Dialog._instance = None

		def InitData(self, context):
				self.context = context
				if "data" not in context:
						context["data"] = {}
				if "rule" not in context["data"]:
						data = self.data = context["data"]["rule"] = dict()
				else:
						data = self.data = context["data"]["rule"]
				markerManager = self.markerManager = context["webModule"].markerManager
				rule = self.rule = context["rule"] if "rule" in context else None

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
				tagChoices = []
				idChoices = []
				classChoices = []
				srcChoices = []
				ruleContextChoices = self.getContextList () 
				formModeControl = False
				while node is not None:
						roleChoices.append(convRoleIntegerToString(node.role))
						if node.role in formModeRoles:
								formModeControl = True
						tagChoices.append(node.tag)
						idChoices.append(node.id)
						classChoices.append(node.className)
						srcChoices.append(node.src)
						node = node.parent

				actionsDict = self.markerManager.getActions()
				self.autoActionList.Clear()
				self.autoActionList.Append("", "")
				for action in actionsDict:
						self.autoActionList.Append(actionsDict[action], action)

				if len(self.getQueriesNames()) == 0:
						self.markerName.Set([""])
				else:
						self.markerName.Set(self.getQueriesNames())
				self.searchText.Set(textChoices)
				self.roleCombo.Set(roleChoices)
				self.tagCombo.Set(tagChoices)
				self.idCombo.Set(idChoices)
				self.classCombo.Set(classChoices)
				self.initArray(self.srcCombo, srcChoices)
				self.ruleContextCombo.Set(ruleContextChoices)

				if self.rule is None:
						self.Title = _(u"New rule")
						self.gestureMapValue = {}
						self.autoActionList.SetSelection(0)
						self.multipleCheckBox.Value = False
						self.indexText.Set([""])
						self.formModeCheckBox.Value = formModeControl
						self.sayNameCheckBox.Value = True
						self.skipCheckBox.Value = False
						self.isPageTitleCheckBox.Value = False
						self.isContextCheckBox.Value = False
						self.comment.Value = ""
				else:
						self.Title = _("Edit rule")
						self.markerName.Value = rule.name
						self.searchText.Value = rule.dic.get("text", "")
						self.roleCombo.Value = convRoleIntegerToString(
								rule.dic.get("role", None))
						self.tagCombo.Value = rule.dic.get("tag", "")
						self.idCombo.Value = rule.dic.get("id", "")
						self.classCombo.Value = rule.dic.get("className", "")
						self.srcCombo.Value = rule.dic.get("src", "")
						self.ruleContextCombo.Value = rule.dic.get("context", "")
						self.gestureMapValue = rule.gestures.copy()
						self.autoActionList.SetSelection(
								markerManager.getActions().keys().index(
										rule.dic.get("autoAction", "")
								) + 1  # Empty entry at index 0
								if "autoAction" in rule.dic else 0
						)
						self.multipleCheckBox.Value = rule.dic.get("multiple", False)
						self.indexText.Value = str(rule.dic.get("index", ""))
						self.formModeCheckBox.Value = rule.dic.get("formMode", False)
						self.sayNameCheckBox.Value = rule.dic.get("sayName", True)
						self.skipCheckBox.Value = rule.dic.get("skip", False)
						self.isPageTitleCheckBox.Value = rule.dic.get("isPageTitle", False)
						self.isContextCheckBox.Value = rule.dic.get("isContext", False)
						self.createWidgetCheckBox.Value = rule.dic.get(
								"createWidget", False)
						self.comment.Value = rule.dic.get("comment", "")

				self.updateGesturesList()

		def getQueriesNames(self):
				nameList = []
				for rule in self.markerManager.getQueries():
						if rule.name not in nameList:
								nameList.append(rule.name)
				return nameList

		def getContextList (self):
				contextList = []
				for rule in self.markerManager.getQueries():
						if rule.isContext and rule.name not in contextList:
								contextList.append(rule.name)
				return contextList
		
		def updateGesturesList(self, newGestureIdentifier=None):
				self.gesturesList.Clear()
				i = 0
				sel = 0
				for gestureIdentifier in self.gestureMapValue:
						gestureSource, gestureMain = inputCore.getDisplayTextForGestureIdentifier(
								gestureIdentifier)
						actionStr = self.markerManager.getActions()[self.gestureMapValue[gestureIdentifier]]
						self.gesturesList.Append("%s = %s" % (
								gestureMain, actionStr), gestureIdentifier)
						if gestureIdentifier == newGestureIdentifier:
								sel = i
						i += 1
				if len(self.gestureMapValue) > 0:
						self.gesturesList.SetSelection(sel)
				self.onGesturesListChoice(None)
				self.gesturesList.SetFocus()

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
			shortcutDialog.markerManager = self.markerManager
			if shortcutDialog.show():
				self.AddGestureAction(shortcutDialog.resultShortcut, shortcutDialog.resultActionData)

		def AddGestureAction(self, gestureIdentifier, action):
				self.gestureMapValue[gestureIdentifier] = action
				self.updateGesturesList(newGestureIdentifier=gestureIdentifier)
				self.gesturesList.SetFocus()

		def onOk(self, evt):
				name = self.markerName.Value.strip()
				if name == "":
						gui.messageBox(_("You must enter a name for this rule"),
													_("Error"), wx.OK | wx.ICON_ERROR, self)
						self.markerName.SetFocus()
						return

				dic = self.data = self.context["data"]["rule"] = {"name": name}
				text = self.searchText.Value
				if text.strip() != "":
						dic["text"] = text
				roleString = self.roleCombo.Value.strip()
				role = convRoleStringToInteger(roleString)
				if role is not None:
						dic["role"] = role
				tag = self.tagCombo.Value.strip()
				if tag != "":
						dic["tag"] = tag
				id = self.idCombo.Value
				if id.strip() != "":
						dic["id"] = id
				className = self.classCombo.Value
				if className.strip() != "":
						dic["className"] = className
				src = self.srcCombo.Value
				if src.strip() != "":
						dic["src"] = src
				ruleContext = self.ruleContextCombo.Value
				if ruleContext.strip() != "":
						dic["context"] = ruleContext
				dic["gestures"] = self.gestureMapValue

				sel = self.autoActionList.Selection
				autoAction = self.autoActionList.GetClientData(sel)
				if autoAction != "":
						dic["autoAction"] = autoAction
				dic["multiple"] = self.multipleCheckBox.Value
				index = self.indexText.Value
				if index.strip() != "":
						try:
								i = int(index)
						except:
								i = 0
						if i > 0:
								dic["index"] = i
				dic["formMode"] = self.formModeCheckBox.Value
				dic["sayName"] = self.sayNameCheckBox.Value
				dic["skip"] = self.skipCheckBox.Value
				dic["isPageTitle"] = self.isPageTitleCheckBox.Value
				dic["isContext"] = self.isContextCheckBox.Value
				dic["createWidget"] = self.createWidgetCheckBox.Value
				dic["comment"] = self.comment.Value

				unic = True
				for rule in self.markerManager.getQueries():
						if name == rule.name and rule != self.rule:
								unic = False
				if not unic:
						if gui.messageBox(
								_("There are other rules with the same name, "
									"will you continue and associate rules ?"),
								_("Warning"), wx.ICON_WARNING | wx.YES | wx.NO, self
						) == wx.NO:
								return

				if self.rule is not None:
						# modification mode, remove old rule
						self.markerManager.removeQuery(self.rule)
				rule = ruleHandler.VirtualMarkerQuery(self.markerManager, dic)
				self.markerManager.addQuery(rule)
				webModuleHandler.update(
					webModule=self.markerManager.webApp,
					focus=self.context["focusObject"]
					)
				assert self.IsModal()
				self.EndModal(wx.ID_OK)

		def onCancel(self, evt):
				self.data.clear()
				self.EndModal(wx.ID_CANCEL)

		def getHtmlNodeAttributes(self, obj):
				if hasattr(obj, "IA2Attributes"):
						# Firefox
						attrib = obj.IA2Attributes
						log.info("attrib : %s" % repr(attrib))
						id = attrib.get("id", None)
						className = attrib["class"] if "class" in attrib else None
						src = attrib["src"] if "src" in attrib else None
				elif hasattr(obj, "HTMLNode"):
						# Internet Explorer
						node = obj.HTMLNode
						id = node.id
						className = node.className
						src = node.src
				else:
						id = className = src = -1
				return id, className, src

		def getAllAttributes(self, info):
				idList = []
				classList = []
				srcList = []
				obj = info.NVDAObjectAtStart
				max = 30
				while obj and max > 0:
						id, className, src = self.getHtmlNodeAttributes(obj)
						if id == -1:
								break
						if id is not None:
								idList.append(id)
						if className is not None:
								classList.append(className)
						if src is not None:
								srcList.append(src)
						max -= 1
						obj = obj.parent
				return idList, classList, srcList

		def initArray(self, array, valueArray):
				if len(valueArray) == 0:
					array.Set([""])
				else:
					array.Set(valueArray)

		def ShowModal(self, context):
				self.InitData(context)
				self.Fit()
				self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
				self.markerName.SetFocus()
				return super(Dialog, self).ShowModal()
