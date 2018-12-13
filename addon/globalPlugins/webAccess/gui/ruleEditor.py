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

__version__ = "2018.12.13"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import wx

import addonHandler
import controlTypes
import gui
import inputCore
from logHandler import log

from .. import ruleHandler
from ..ruleHandler import contextTypes
from .. import webModuleHandler


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
		leftSizer = wx.GridBagSizer(8, 8)
		rightSizer = wx.GridBagSizer(8, 8)
		columnsSizer.Add(leftSizer, pos=(0, 0), flag=wx.EXPAND)
		columnsSizer.Add(
			wx.StaticLine(self, style=wx.LI_VERTICAL),
			pos=(0, 1),
			flag=wx.EXPAND
		)
		columnsSizer.Add(rightSizer, pos=(0, 2), flag=wx.EXPAND)
		
		leftRow = 0
		item = wx.StaticText(self, label=_(u"Rule &name"))
		leftSizer.Add(item, pos=(leftRow, 0))
		item = self.markerName = wx.ComboBox(self)
		leftSizer.Add(item, pos=(leftRow, 1), flag=wx.EXPAND)
		
		# Static box grouping element selection criteria
		leftRow += 1
		criteriaBox = wx.StaticBox(self, label=_("Criteria"))
		criteriaSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(criteriaBox, orient=wx.VERTICAL)
		item.Add(criteriaSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, pos=(leftRow, 0), span=(1, 2), flag=wx.EXPAND)
		
		# Inputs
		row = 0
		item = wx.StaticText(criteriaBox, label=_(u"Conte&xt"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.requiresContextCombo = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"Search &text"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.searchText = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"&Role"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.roleCombo = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"&Tag"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.tagCombo = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"&ID"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.idCombo = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"&Class"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.classCombo = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"&Image source"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.srcCombo = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(criteriaBox, label=_(u"&Index"))
		criteriaSizer.Add(item, pos=(row, 0))
		item = self.indexText = wx.ComboBox(criteriaBox)
		criteriaSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)

		criteriaSizer.AddGrowableCol(1)
				
		# Static box grouping input elements for actions
		leftRow += 1
		actionsBox = wx.StaticBox(self, label=_("Actions"), style=wx.SB_RAISED)
		actionsSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(actionsBox, orient=wx.VERTICAL)
		item.Add(actionsSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, pos=(leftRow, 0), span=(1, 2), flag=wx.EXPAND)
		
		# Inputs
		row = 0
		item = wx.StaticText(actionsBox, label=_("&Keyboard shortcut"))
		actionsSizer.Add(item, pos=(row, 0), span=(2, 1))
		item = self.gesturesList = wx.ListBox(actionsBox)
		item.Bind(wx.EVT_LISTBOX, self.onGesturesListChoice)
		actionsSizer.Add(item, pos=(row, 1), span=(2, 1), flag=wx.EXPAND)
		
		item = wx.Button(actionsBox, label=_("Add a keyboard shortcut"))
		item.Bind(wx.EVT_BUTTON, self.onAddGesture)
		actionsSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		item = self.deleteGestureButton = wx.Button(
			actionsBox,
			label=_("Delete this shortcut")
		)
		item.Bind(wx.EVT_BUTTON, self.onDeleteGesture)
		actionsSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(
			actionsBox,
			label=_("&Automatic action at rule detection")
		)
		actionsSizer.Add(item, pos=(2, 0))
		item = self.autoActionList = wx.ComboBox(
			actionsBox,
			style=wx.CB_READONLY
		)
		actionsSizer.Add(item, pos=(row, 1), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(actionsBox, label=_(u"Custom m&essage"))
		actionsSizer.Add(item, pos=(row, 0))
		item = self.customValue = wx.TextCtrl(actionsBox)
		actionsSizer.Add(item, pos=(row, 1), span=(1, 2), flag=wx.EXPAND)
		
		# Static box grouping rule properties
		leftRow += 1
		propertiesBox = wx.StaticBox(self, label=_("Properties"))
		propertiesSizer = wx.GridBagSizer(8, 8)
		item = wx.StaticBoxSizer(propertiesBox, orient=wx.VERTICAL)
		item.Add(propertiesSizer, flag=wx.EXPAND | wx.ALL, border=4)
		leftSizer.Add(item, pos=(leftRow, 0), span=(1, 2), flag=wx.EXPAND)
		
		row = 0
		item = self.multipleCheckBox = wx.CheckBox(
			propertiesBox,
			label=_(u"&Multiple results available")
		)
		propertiesSizer.Add(item, pos=(row, 0), span=(1, 2), flag=wx.EXPAND)
		
		row += 1
		item = self.formModeCheckBox = wx.CheckBox(
			propertiesBox,
			label=_("Activate &form mode")
		)
		propertiesSizer.Add(item, pos=(row, 0), span=(1, 2), flag=wx.EXPAND)
		
		row += 1
		item = self.sayNameCheckBox = wx.CheckBox(
			propertiesBox,
			label=_("Speak r&ule name")
		)
		propertiesSizer.Add(item, pos=(row, 0), span=(1, 2), flag=wx.EXPAND)
		
		row += 1
		item = self.skipCheckBox = wx.CheckBox(
			propertiesBox,
			label=_("S&kip with Page Down")
		)
		propertiesSizer.Add(item, pos=(row, 0), span=(1, 2), flag=wx.EXPAND)
		
		row += 1
		item = self.isPageTitleCheckBox = wx.CheckBox(
			propertiesBox,
			label=_("&Page title")
		)
		propertiesSizer.Add(item, pos=(row, 0), span=(1, 2), flag=wx.EXPAND)
		
		row += 1
		item = wx.StaticText(propertiesBox, label=_("Defines a conte&xt"))
		propertiesSizer.Add(item, pos=(row, 0))
		item = self.definesContextList = wx.ComboBox(
			propertiesBox,
			style=wx.CB_READONLY
		)
		propertiesSizer.Add(item, pos=(row, 1), span=(1, 2), flag=wx.EXPAND)
		
		row += 1
		item = self.createWidgetCheckBox = wx.CheckBox(
			propertiesBox,
			label=_("Create a &list of items")
		)
		item.Enabled = False
		propertiesSizer.Add(item, pos=(row, 0), span=(1, 2), flag=wx.EXPAND)

		# Make inputs resizable with the window
		propertiesSizer.AddGrowableCol(1)
		leftSizer.AddGrowableCol(1)
			
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
		rightSizer.Add(
			item,
			pos=(row, 0),
			flag=wx.EXPAND
		)

		rightSizer.AddGrowableCol(0)
		rightSizer.AddGrowableRow(1)
		
		columnsSizer.AddGrowableCol(0)
		columnsSizer.AddGrowableCol(2)
		columnsSizer.AddGrowableRow(0)
		
		mainSizer.Add(
			self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
			flag=wx.EXPAND | wx.BOTTOM,
			border=8
		)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
		self.SetSizerAndFit(mainSizer)
	
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
		requiresContextChoices = self.getContextList()
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
		self.autoActionList.Append(
			# Translators: Action name
			pgettext("webAccess.action", "No action"),
			""
		)
		for action in actionsDict:
			self.autoActionList.Append(actionsDict[action], action)
		
		if len(self.getQueriesNames()) == 0:
			self.markerName.Set([""])
		else:
			self.markerName.Set(self.getQueriesNames())
		self.requiresContextCombo.Set(requiresContextChoices)
		self.searchText.Set(textChoices)
		self.roleCombo.Set(roleChoices)
		self.tagCombo.Set(tagChoices)
		self.idCombo.Set(idChoices)
		self.classCombo.Set(classChoices)
		self.initArray(self.srcCombo, srcChoices)
		self.definesContextList.Clear()
		self.definesContextList.Append("", False)
		for key, label in contextTypes.contextTypeLabels.items():
			self.definesContextList.Append(label, key)
		
		if self.rule is None:
			self.Title = _(u"New rule")
			self.indexText.Set([""])
			self.gestureMapValue = {}
			self.autoActionList.SetSelection(0)
			self.customValue.Value = ""
			self.multipleCheckBox.Value = False
			self.formModeCheckBox.Value = formModeControl
			self.sayNameCheckBox.Value = True
			self.skipCheckBox.Value = False
			self.isPageTitleCheckBox.Value = False
			self.definesContextList.SetSelection(0)
			self.createWidgetCheckBox.Value = False
			self.comment.Value = ""
		else:
			self.Title = _("Edit rule")
			self.markerName.Value = rule.name
			self.requiresContextCombo.Value = rule.dic.get(
				"requiresContext", "")
			self.searchText.Value = rule.dic.get("text", "")
			self.roleCombo.Value = convRoleIntegerToString(
				rule.dic.get("role", None))
			self.tagCombo.Value = rule.dic.get("tag", "")
			self.idCombo.Value = rule.dic.get("id", "")
			self.classCombo.Value = rule.dic.get("className", "")
			self.srcCombo.Value = rule.dic.get("src", "")
			self.indexText.Value = str(rule.dic.get("index", ""))
			self.gestureMapValue = rule.gestures.copy()
			self.autoActionList.SetSelection(
				markerManager.getActions().keys().index(
					rule.dic.get("autoAction", "")
				) + 1  # Empty entry at index 0
				if "autoAction" in rule.dic else 0
			)
			self.customValue.Value = rule.dic.get("customValue", "")
			self.multipleCheckBox.Value = rule.dic.get("multiple", False)
			self.formModeCheckBox.Value = rule.dic.get("formMode", False)
			self.sayNameCheckBox.Value = rule.dic.get("sayName", True)
			self.skipCheckBox.Value = rule.dic.get("skip", False)
			self.isPageTitleCheckBox.Value = rule.dic.get("isPageTitle", False)
			self.definesContextList.SetSelection(
				contextTypes.contextTypeLabels.keys().index(
					rule.dic.get("definesContext", "")
				) + 1  # Empty entry at index 0
				if rule.dic.get("definesContext") else 0
			)
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
	
	def getContextList(self):
		contextList = []
		for rule in self.markerManager.getQueries():
			if rule.definesContext and rule.name not in contextList:
				contextList.append(rule.name)
		return contextList
	
	def updateGesturesList(self, newGestureIdentifier=None):
		self.gesturesList.Clear()
		i = 0
		sel = 0
		for gestureIdentifier in self.gestureMapValue:
			gestureSource, gestureMain = \
				inputCore.getDisplayTextForGestureIdentifier(gestureIdentifier)
			actionStr = self.markerManager.getActions()[
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
			self.AddGestureAction(
				shortcutDialog.resultShortcut,
				shortcutDialog.resultActionData
			)
	
	def AddGestureAction(self, gestureIdentifier, action):
		self.gestureMapValue[gestureIdentifier] = action
		self.updateGesturesList(newGestureIdentifier=gestureIdentifier)
		self.gesturesList.SetFocus()
	
	def onOk(self, evt):
		name = self.markerName.Value.strip()
		if name == "":
			gui.messageBox(
				message=_("You must enter a name for this rule"),
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=self
			)
			self.markerName.SetFocus()
			return
		
		dic = self.data = self.context["data"]["rule"] = {"name": name}
		requiresContext = self.requiresContextCombo.Value.strip()
		if requiresContext:
			dic["requiresContext"] = requiresContext
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
		index = self.indexText.Value
		if index.strip() != "":
			try:
				i = int(index)
			except:
				i = 0
			if i > 0:
				dic["index"] = i

		dic["gestures"] = self.gestureMapValue
		sel = self.autoActionList.Selection
		autoAction = self.autoActionList.GetClientData(sel)
		if autoAction != "":
			dic["autoAction"] = autoAction
		if self.customValue.Value:
			dic["customValue"] = self.customValue.Value
		
		dic["multiple"] = self.multipleCheckBox.Value
		dic["formMode"] = self.formModeCheckBox.Value
		dic["sayName"] = self.sayNameCheckBox.Value
		dic["skip"] = self.skipCheckBox.Value
		dic["isPageTitle"] = self.isPageTitleCheckBox.Value
		definesContext = self.definesContextList.GetClientData(
			self.definesContextList.Selection
		)
		if definesContext:
			dic["definesContext"] = definesContext
		dic["createWidget"] = self.createWidgetCheckBox.Value
		dic["comment"] = self.comment.Value
		
		unic = True
		for rule in self.markerManager.getQueries():
			if name == rule.name and rule != self.rule:
				unic = False
		if not unic:
			if gui.messageBox(
				message=_(
					"There are other rules with the same name, "
					"will you continue and associate rules ?"
				),
				caption=_("Warning"),
				style=wx.ICON_WARNING | wx.YES | wx.NO,
				parent=self
			) == wx.NO:
				return
		
		if self.rule is not None:
			# modification mode, remove old rule
			self.markerManager.removeQuery(self.rule)
		rule = ruleHandler.VirtualMarkerQuery(self.markerManager, dic)
		self.markerManager.addQuery(rule)
		webModuleHandler.update(
			webModule=self.context["webModule"],
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
