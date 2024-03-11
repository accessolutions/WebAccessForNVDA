
__version__ = "2024.03.07"
__author__ = "Sendhil Randon <sendhil.randon-ext@pole.-emploi.fr>"

from collections import OrderedDict
import addonHandler
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
import wx
import gui
from logHandler import log
from ..ruleHandler.ruleTypes import RULE_TYPE_FIELDS
from ..ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
import  ui
addonHandler.initTranslation()

# event hander constants
EVT_KEY_DOWN = 10057
EVT_CHAR_HOOK = 10055

# The semi-column is part of the labels because some localizations
# (ie. French) require it to be prepended with one space.
FIELDS = {
	# Translator: Multiple results checkbox label for the rule dialog's properties panel.
	"autoAction": pgettext("webAccess.ruleProperties", "Auto Actions"),
	# Translator: Multiple results checkbox label for the rule dialog's properties panel.
	"multiple": pgettext("webAccess.ruleProperties", "Multiple results"),
	# Translator: Activate form mode checkbox label for the rule dialog's properties panel.
	"formMode": pgettext("webAccess.ruleProperties", "Activate form mode"),
	# Translator: Skip page down checkbox label for the rule dialog's properties panel.
	"skip": pgettext("webAccess.ruleProperties", "Skip with Page Down"),
	# Translator: Speak rule name checkbox label for the rule dialog's properties panel.
	"sayName": pgettext("webAccess.ruleProperties", "Speak rule name"),
	# Translator: Custom name input label for the rule dialog's properties panel.
	"customName": pgettext("webAccess.ruleProperties", "Custom name"),
	# Label depends on rule type)
	"customValue": pgettext("webAccess.ruleProperties", "Custom value"),
	# Translator: Transform select label for the rule dialog's properties panel.
	"mutation": pgettext("webAccess.ruleProperties", "Transform"),
}


def showPropsDialog(context, properties):
	PropsMenu(context, properties).ShowModal()
	return True

class ListControl(object):

	def __init__(
			self,
	        propsPanel
	):
		# wx.List control elements from client side
		super(ListControl, self).__init__()
		self.propsPanel = propsPanel
		self.propertiesList = propsPanel.propertiesList
		self.listCtrl = propsPanel.listCtrl
		self.toggleBtn = propsPanel.toggleBtn
		self.editable = propsPanel.editable
		self.choice = propsPanel.choice
		self.context = propsPanel.context

		# wx.List control event binding
		self.listCtrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onItemSelListCtrl)
		self.listCtrl.Bind(wx.EVT_KEY_DOWN, self.onKeyPress)
		self.listCtrl.Bind(wx.EVT_CHAR_HOOK, self.keyShiftSpace)
		self.toggleBtn.Bind(wx.EVT_TOGGLEBUTTON, self.updateValueEvtToggle)
		self.editable.Bind(wx.EVT_TEXT, self.updateValueEvtEdit)
		self.choice.Bind(wx.EVT_CHOICE, self.updateValueEvtChoice)

		#Local variables
		self.index = 0
		self.currentSelItem = None
		self.mutationOptions = []
		self.autoActionOptions = ["", "default"]

		# Instanciation of increment the values for wx.choice and updates the correspondant wx.listCtrl
		self.objIncAutoAct = IncrDecrListPos()
		self.objIncMut = IncrDecrListPos()
		self.init()

	def init(self):
		self.updateBtnState()
		self.toggleBtn.Disable()
		self.editable.Disable()
		self.choice.Disable()
		self.getAutoActions()
		self.getMutationOptions()

	# Message box function displays the given message and caption in a popup
	def messageBox(self, message, caption):
		gui.messageBox(
			message=message,
			caption=caption,
			style=wx.OK | wx.ICON_EXCLAMATION
		)

	# Function set default updatable properties on panel activation
	def setValueSingleChoiceProps(self, val, id):
		retChoiceVal = lambda targetval, l: next((t[0] for t in [x for x in l if x[1] == targetval]), None)
		if id == "autoAction":
			ret = retChoiceVal(val, self.autoActionOptions)
			return ret if ret else self.setDefaultChoice(self.objIncAutoAct, self.autoActionOptions)
		elif id == "mutation":
			ret = retChoiceVal(val, self.mutationOptions)
			return ret if ret else self.setDefaultChoice(self.objIncMut, self.mutationOptions)

	# Set the choice dropdown to default value if none is retrived
	def setDefaultChoice(self, objToIncr, lst):
		self.choice.SetSelection(1)
		objToIncr.setPos(1)
		return lst[0][0]

	# Function set default updatable properties on panel activation
	def updatedStrValues(self, val, id):
		if isinstance(self.getPropsObj(id), SingleChoiceProperty):
			return self.setValueSingleChoiceProps(val, id)
		elif isinstance(self.getPropsObj(id), ToggleProperty):
			# Translator: State properties boolean "Enabled"
			# Translator: State properties boolean "Disabled"
			return _("Enabled") if val else _("Disabled")
		elif isinstance(self.getPropsObj(id), EditableProperty):
			# Translator: State properties editable "Empty"
			return val if val else _("Empty")

	@staticmethod
	def getAltFieldLabel(ruleType, key, default=None):
		if key == "customValue":
			if ruleType in (ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return _("Custom page title")
			elif ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return  _("Custom message")
		return default

	def customDisplayLabel(self, props):
		dataRule = self.context["data"]["rule"]
		ruleType = dataRule.get("type")
		if isinstance(props, EditableProperty):
			return ListControl.getAltFieldLabel(ruleType, props.get_id())

	# Set fresh values on init for properties
	def onInitUpdateListCtrl(self):
		self.listCtrl.DeleteAllItems()
		clsInstance = self.propsPanel.__class__.__name__
		for p in self.propertiesList:
			if p.get_flag():
				val = self.updatedStrValues(p.get_value(), p.get_id())
				displayName = p.get_displayName() if  self.customDisplayLabel(p) is None else self.customDisplayLabel(p)
				self.listCtrl.InsertStringItem(self.index, displayName)
				self.listCtrl.SetStringItem(self.index, 1, val)
				if clsInstance == "OverridesPanel":
					self.listCtrl.SetStringItem(self.index, 2, self.isOverrided(p.get_id()))
				self.index += 1

	# wx.add button applicable only on criteria properties panel
	def onAddProperties(self, evt):
		if showPropsDialog(self.context, self.propertiesList):
			self.appendToList()

	# wx.delete add applicable only on criteria properties panel
	def onDeleteProperties(self, evt):
		selRow= self.getItemSelRow()
		index = self.listCtrl.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
		if index != -1:
			# Delete the selected item
			self.listCtrl.DeleteItem(index)
			for p in self.propertiesList:
				if not p.get_displayName() == selRow[0]:
					continue
				if isinstance(p, ToggleProperty):
					p.set_flag(False)
					p.set_value(False)
				elif isinstance(p, EditableProperty):
					p.set_flag(False)
					p.set_value("")
				elif isinstance(p, SingleChoiceProperty):
					p.set_flag(False)
					p.set_value("")

	# Append to list the chossen properties in the list on criteria editor panel
	def appendToList(self):
		clsInstance = self.propsPanel.__class__.__name__
		val = AppendListCtrl.lst.pop()
		obj=self.getPropsObj(val)
		self.listCtrl.InsertStringItem(self.index, obj.get_displayName())
		self.listCtrl.SetStringItem(self.index, 1, self.updatedStrValues(obj.get_value(), obj.get_id()))
		if clsInstance == "OverridesPanel":
			overridden = self.isOverrided(obj.get_id())
			if overridden is not None:
				self.listCtrl.SetStringItem(self.index, 2, overridden)
		self.index += 1
		self.listCtrl.SetFocus()

	# Function updates the overrided values on the criteria editor panel 3rd Column
	def isOverrided(self, idProps):
		dataRule = self.context["data"]["rule"]
		ruleType = dataRule.get("type")
		ruleProps = dataRule.get("properties")
		typeRule = RULE_TYPE_FIELDS.get(ruleType)
		if ruleType is not None and ruleProps is not None:
			#if idProps in typeRule:
			for key, value in list(ruleProps.items()):
				if  idProps in typeRule and idProps == key:
					# Translator: State properties "Not assigned"
					return self.updatedStrValues(value, idProps) if value else _("Not assigned")

	# Function returns the properties obj
	def getPropsObj(self, val):
		for p in self.propertiesList:
			if val == p.get_id():
				return p

	def updateBtnState(self):
		if self.propsPanel.__class__.__name__ ==  "OverridesPanel":
			self.btnAddProps = self.propsPanel.btnAddProps
			self.btnDelProps = self.propsPanel.btnDelProps
			self.btnAddProps.Bind(wx.EVT_BUTTON, self.onAddProperties)
			self.btnDelProps.Bind(wx.EVT_BUTTON, self.onDeleteProperties)


	# Retruns the selected item from the properties list
	def getItemSelRow(self):
		column_values = []
		focused_item = self.listCtrl.GetFocusedItem()
		if focused_item != -1:
			column_count = self.listCtrl.GetColumnCount()
			for column in range(column_count):
				column_value = self.listCtrl.GetItem(focused_item, column).GetText()
				column_values.append(column_value)
			return  column_values

	# Event handler function binded over while browsing on the properties list
	def onItemSelListCtrl(self, evt):
		self.currentSelItem = evt.GetItem()
		listItem = self.getItemSelRow()
		for p in self.propertiesList:
			if not listItem[0] == p.get_displayName():
				continue
			if isinstance(p, ToggleProperty):
				self.choice.Disable()
				self.editable.Disable()
				self.toggleBtn.Enable()
				self.toggleBtn.SetLabel("")
				self.toggleBtn.SetLabel(p.get_displayName())
				val = p.get_value()
				if val:
					self.toggleBtn.SetValue(True)
				else:
					self.toggleBtn.SetValue(False)
			elif isinstance(p, SingleChoiceProperty):
				self.updateChoices(self.choice, p.get_id())
				self.toggleBtn.Disable()
				self.toggleBtn.SetLabel("")
				self.editable.Disable()
				self.choice.Enable()
				self.choice.id = p.get_value()
				if p.get_value() is not None:
					retVal, n =self.updateChoiceDropDown(p.get_value(), p.get_id())
					if retVal is not None:
						self.choice.SetSelection(n)
				else:
					self.objIncAutoAct.setPos(1) if p.get_id() == "autoAction" else (self.objIncMut.setPos(1) if p.get_id() == "mutation" else None)
					self.choice.SetSelection(0)
			elif isinstance(p, EditableProperty):
				self.choice.Disable()
				self.toggleBtn.Disable()
				self.editable.Enable()
				self.toggleBtn.SetLabel("")
				if p.get_value() is not None:
					self.editable.SetValue(p.get_value())
				else:
					self.editable.SetValue("")

	# Function updates the dropdown list and set the postion to the selected value
	def updateChoiceDropDown(self, val, idProps):
		lst = self.autoActionOptions if idProps == "autoAction" else (self.mutationOptions if  idProps == "mutation" else None)
		getTupleVal = lambda targetval: next((t[0] for t in [x for x in lst if x[1] == targetval]), None)
		n = self.choice.FindString(getTupleVal(val), False)
		if n != -1:
			self.choice.SetSelection(n)
			pos = self.choice.GetSelection()
			self.objIncAutoAct.setPos(pos+1) if idProps == "autoAction"  else (self.objIncMut.setPos(pos+1) if  idProps == "mutation" else None)
			return getTupleVal(val), n

	# on init function updates the mutation and autoActions list
	def updateChoices(self,choiceItem ,id):
		if id == "mutation":
			choiceItem.Clear()
			list(map(lambda x: choiceItem.Append(x[0]), self.mutationOptions))
		elif id == "autoAction":
			choiceItem.Clear()
			list(map(lambda x:choiceItem.Append(x[0]), self.autoActionOptions))

	# Event handler function binded to space key
	def onKeyPress(self, evt):
		keycode = evt.GetKeyCode()
		modifiers = evt.GetModifiers()
		if keycode == wx.WXK_SPACE and not modifiers:
			rowItem = self.getItemSelRow()
			for p in self.propertiesList:
				if isinstance(p ,ToggleProperty) and rowItem[0] == p.get_displayName():
					self.updateToggleBtnPropertiest(rowItem[0])
					return
				elif isinstance(p, EditableProperty) and rowItem[0] == self.customDisplayLabel(p):
					retDialog = self.editablDialog(rowItem[0])
					self.updateEditableProperties(rowItem[0], retDialog)
					if retDialog is not None:
						self.updateEditableProperties(rowItem[0], retDialog)
						return
					else:
						log.info("Ret value of dialog is empty!")
				elif isinstance(p, SingleChoiceProperty) and rowItem[0] == p.get_displayName():
					retChoiceList = self.setChoiceList(rowItem[0])
					retChoice = self.updateChoiceByList(evt.EventType, retChoiceList, p.get_id())
					ui.message("{}".format(retChoice))
					self.updateChoiceProperties(rowItem[0], retChoice)
					return
		evt.Skip()

	# Event handler function binded to shift+space key inorder to decrement the position of list
	def keyShiftSpace(self, evt):
		keycode = evt.GetKeyCode()
		modifiers = evt.GetModifiers()
		if modifiers == wx.MOD_SHIFT and keycode == wx.WXK_SPACE:
			rowItem = self.getItemSelRow()
			for p in self.propertiesList:
				if isinstance(p, SingleChoiceProperty) and rowItem[0] == p.get_displayName():
					retChoiceList = self.setChoiceList(rowItem[0])
					retChoice = self.updateChoiceByList(evt.EventType, retChoiceList, p.get_id())
					ui.message("{}".format(retChoice))
					self.updateChoiceProperties(rowItem[0], retChoice)
					return
		evt.Skip()

	# Function updates the toggle btn display and sets value after the event from the onKeyPress fun.
	def updateToggleBtnPropertiest(self, rowItem):
		for p in self.propertiesList:
			if rowItem in p.get_displayName() and isinstance(p, ToggleProperty):
				val = not bool(self.toggleBtn.GetValue())
				self.toggleBtn.SetValue(val)
				p.set_value(val)
				# Translator: State properties "unchecked"
				# Translator: State properties"checked"
				ui.message(_("checked") if val else _("unchecked"))
				self.updatePropertiesList(rowItem)

	# Function updates the editable properties list
	def updateEditableProperties(self, rowItem, val):
		for p in self.propertiesList:
			if self.customDisplayLabel(p) == rowItem:
				p.set_value(val)
				self.editable.SetValue(val)
		self.updatePropertiesList(rowItem)

	# Function displays an input dialog after onkyepress event for ediable properteis
	def editablDialog(self, label):
		dialog = wx.TextEntryDialog(self.propsPanel, label, label)
		if dialog.ShowModal() == wx.ID_OK:
			return dialog.GetValue()
		dialog.Destroy()

	# Function set and option choosen from the dropDown list or onKeyPress event in the properties list
	def setChoiceList(self, rowItem):
		for p in self.propertiesList:
			if rowItem == p.get_displayName():
				if p.get_id() == "mutation":
					return [i[0] for i in self.mutationOptions]
				elif p.get_id() == "autoAction":
					return  [i[0] for i in self.autoActionOptions]

	# Function updates the choices uses binded onkeyPress events for increment and keyShiftSpace events for decrement the lists
	def updateChoiceByList(self, eventType ,listChoice, id):
		if id == "autoAction":
			if eventType == EVT_KEY_DOWN:
				self.objIncAutoAct.setListChoice(listChoice)
				return  self.objIncAutoAct.getIncrChoice()
			elif eventType == EVT_CHAR_HOOK:
				self.objIncAutoAct.setListChoice(listChoice)
				return self.objIncAutoAct.getDecrChoice()
		elif id == "mutation":
			if eventType == EVT_KEY_DOWN:
				self.objIncMut.setListChoice(listChoice)
				return  self.objIncMut.getIncrChoice()
			elif eventType == EVT_CHAR_HOOK:
				self.objIncMut.setListChoice(listChoice)
				return self.objIncMut.getDecrChoice()

	# Function returs id or value of mutation and autoActions according to the requirements
	def getChoiceIdOrValues(self, val, id, target):
		getActionVal = lambda targetval: next((t[0] for t in [x for x in self.autoActionOptions if x[1] == targetval]), None)
		getActionId = lambda targetId: next((t[1] for t in [x for x in self.autoActionOptions if x[0] == targetId]), None)
		getMutVal = lambda targetval: next((t[0] for t in [x for x in self.mutationOptions if x[1] == targetval]), None)
		getMutId = lambda targetId: next((t[1] for t in [x for x in self.mutationOptions if x[0] == targetId]), None)
		if target == "id":
			return  getMutId(val) if id == "mutation" else (getActionId(val) if id == "autoAction" else val)
		elif target == "val":
			return  getMutVal(val) if id == "mutation" else (getActionVal(val) if id == "autoAction" else val)

	# Updates the choice properties in the list from tab events as well as dropdown events
	def updateChoiceProperties(self, rowItem, val):
		retId = lambda x,y: self.getChoiceIdOrValues(x, y, "id")
		retValue = lambda x,y: self.getChoiceIdOrValues(x, y, "val")
		for p in self.propertiesList:
			if p.get_displayName() == rowItem:
				val = retId(val, p.get_id())
				p.set_value(val)
				valFindString = retValue(val,p.get_id())
				n = self.choice.FindString(valFindString, False)
				if n != -1:
					self.choice.SetSelection(n)
					self.updatePropertiesList(rowItem)
					return

	# Function updates the values in the properties list control globally
	def updatePropertiesList(self, rowProps):
		# Translator: State properties boolean "Enable"
		# Translator: State properties boolean "Disable"
		ret = lambda x: _("Enable") if x == True else ( _("Disable") if x == False else x)
		forVal = filter(lambda x: x.get_displayName() == rowProps, self.propertiesList)
		getDisplayVal = lambda targetStr: next((t[0] for t in [x for x in self.autoActionOptions if x[1] == targetStr]), None)
		getMutId = lambda targetId: next((t[0] for t in [x for x in self.mutationOptions if x[1] == targetId]), None)
		listDisVal = lambda x, y: getMutId(x) if y == "mutation" else (getDisplayVal(x) if y == "autoAction" else x)
		res = list(forVal)
		valProps = res[0].get_value()
		val = ret(valProps)  if valProps is not None else ""
		index = self.currentSelItem.GetId()
		self.listCtrl.SetItem(index, 1, listDisVal(val, res[0].get_id()))
		return

	# Event handler to update toggle button properties
	def updateValueEvtToggle(self, evt):
		evtObj = evt.GetEventObject()
		for p in self.propertiesList:
			if evt.GetEventType() == wx.EVT_TOGGLEBUTTON.evtType[0]:
				if evtObj.GetLabel() in p.get_displayName():
					state = evtObj.GetValue()
					if state:
						p.set_value(True)
						self.toggleBtn.SetValue(True)
						self.updatePropertiesList(evtObj.GetLabel())
					else:
						p.set_value(False)
						self.toggleBtn.SetValue(False)
						self.updatePropertiesList(evtObj.GetLabel())
					return

	# Event handler updates Editable properties
	def updateValueEvtEdit(self, evt):
		text = self.editable.GetValue()
		index = self.currentSelItem.GetId()
		item = self.getItemSelRow()
		for p in self.propertiesList:
			if p.get_displayName() == item[0]:
				p.set_value(text)
		self.listCtrl.SetItem(index, 1, text)

	# Event handler updates choice properties
	def updateValueEvtChoice(self, evt):
		choiceVal = self.choice.GetString(self.choice.GetSelection())
		selRow = self.getItemSelRow()
		self.updateChoiceProperties(selRow[0], choiceVal)
		forVal = filter(lambda x: x.get_displayName() == selRow[0], self.propertiesList)
		res = list(forVal)
		pos = self.choice.GetSelection()
		self.objIncAutoAct.setPos(pos+1) if res[0].get_id() == "autoAction" else (self.objIncMut.setPos(pos+1) if res[0].get_id() == "mutation" else None)
		self.updatePropertiesList(selRow[0])

	# On init, function updates theautoActions list on run time
	def getAutoActions(self):
		self.autoActionOptions =[]
		mgr = self.context["webModule"].ruleManager
		actionsDict = mgr.getActions()
		# Translator: State properties "unchecked"
		defaultval = ("Choose an option", "")
		[self.autoActionOptions.append((actionsDict[i], i))for i in actionsDict]
		self.autoActionOptions.insert(0, defaultval)

	# On init function updated the run time mutation list
	def getMutationOptions(self):
		self.mutationOptions = []
		# Translator: State properties "unchecked"
		defaultval = ("Choose an option", "")
		[self.mutationOptions.append((mutationLabels[i], i)) for i in mutationLabels]
		self.mutationOptions.insert(0, defaultval)


class AppendListCtrl(ListControl):


	lst =[]
	def __init__(self, clientListBox):
		super(AppendListCtrl, self).__init__(clientListBox)
		self.clientListBox =clientListBox

	def appendToList(self):
		if not AppendListCtrl.lst:
			return
		else:
			super(AppendListCtrl, self).appendToList()
			AppendListCtrl.lst.clear()


class PropsMenu(wx.Menu):


	def __init__(self, context, properties):
		super(PropsMenu, self).__init__()
		self.context = context
		self.properties = properties
		for props in self.properties:
			if props.get_flag():
				id = self.FindItem(props.get_displayName())
				if id != -1:
					self.Delete(id)
					self.Bind(wx.EVT_MENU, props.updateFlag)
					return
			else:
				itemCheck = self.Append(wx.ID_ANY, props.get_displayName())
				self.Bind(wx.EVT_MENU, props.updateFlag, itemCheck)

	def ShowModal(self):
		gui.mainFrame.prePopup(contextMenuName="Properties rules")
		gui.mainFrame.PopupMenu(self)
		gui.mainFrame.postPopup()

class PropertyType(Enum):
	TOGGLE = "toggle"  # True / False
	EDITABLE = "editable"
	SINGLE_CHOICE = "singleChoice"
	MULTIPLE_CHOICE = "multipleChoice"

class Property(ABC):
	@abstractmethod
	def __init__(
			self,
			id: str,
			display_name: str,
			type: PropertyType
	):
		self.__id = id
		self.__display_name = display_name
		self.__type = type

	@abstractmethod
	def get_id(self):
		return self.__id

	@abstractmethod
	def get_displayName(self):
		return self.__display_name

class ToggleProperty(Property):
	def __init__(
			self,
			id: str,
			display_name: str,
			value: bool,
			flag: bool,
	):
		super(ToggleProperty, self).__init__(id, display_name, PropertyType.TOGGLE)
		self.__flag = flag
		self.__value = value

	def get_id(self):
		return super(ToggleProperty, self).get_id()

	def get_displayName(self):
		return super(ToggleProperty, self).get_displayName()

	def get_value(self):
		return self.__value

	def set_value(self, value):
		self.__value = value

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def updateFlag(self, evt):
		self.set_flag(True)
		AppendListCtrl.lst.append(self.get_id())

class SingleChoiceProperty(Property):
	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			value: str,
	):
		super(SingleChoiceProperty, self).__init__(id, display_name, PropertyType.SINGLE_CHOICE)
		self.__value = value
		self.__flag = flag

	def get_id(self):
		return super(SingleChoiceProperty, self).get_id()

	def get_displayName(self):
		return super(SingleChoiceProperty, self).get_displayName()

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def get_value(self):
		return self.__value

	def set_value(self, value):
		self.__value = value

	def updateFlag(self, evt):
		self.set_flag(True)
		AppendListCtrl.lst.append(self.get_id())

class EditableProperty(Property):

	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			value: Optional[str] = None,
	):
		super(EditableProperty, self).__init__(id, display_name, PropertyType.EDITABLE)
		self.__value = value
		self.__flag = flag

	def get_id(self):
		return super(EditableProperty, self).get_id()

	def get_displayName(self):
		return super(EditableProperty, self).get_displayName()

	def get_value(self):
		return self.__value

	def set_value(self, options):
		self.__value = options

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def updateFlag(self, evt):
		self.set_flag(True)
		AppendListCtrl.lst.append(self.get_id())

# Initialising List of properties
class ListProperties:

	propertiesList = []
	dataRule = None
	ruleType =None

	def __init__(self):
		self.__propsMultiple = None
		self.__propsMutation = None
		self.__propsFormMode = None
		self.__propsCustomValue = None
		self.__propsCustomName = None
		self.__propsSkip = None
		self.__propsSayName = None
		self.__autoAction = None

	def setPropertiesByRuleType(self, context):
		self.propertiesList =[]
		self.dataRule = context["data"]["rule"]
		self.ruleType = self.dataRule.get("type")
		self.__autoAction = SingleChoiceProperty("autoAction", FIELDS["autoAction"], False, "")
		self.__propsMultiple = ToggleProperty("multiple", FIELDS["multiple"], False, False)
		self.__propsFormMode = ToggleProperty("formMode", FIELDS["formMode"], False, False)
		self.__propsSkip = ToggleProperty("skip", FIELDS["skip"], False, False)
		self.__propsSayName = ToggleProperty("sayName", FIELDS["sayName"], False, False)
		self.__propsCustomName = EditableProperty("customName", FIELDS["customName"], False)
		self.__propsCustomValue = EditableProperty("customValue", FIELDS["customValue"], False)
		self.__propsMutation = SingleChoiceProperty("mutation", FIELDS["mutation"], False, "")

		availProps = [
			self.__autoAction,
			self.__propsMultiple,
			self.__propsFormMode,
			self.__propsSkip,
			self.__propsSayName,
			self.__propsCustomName,
			self.__propsCustomValue,
			self.__propsMutation
		]
		typeValues = RULE_TYPE_FIELDS.get(self.ruleType)
		if typeValues:
			for props in availProps:
				if props.get_id() in typeValues:
					self.propertiesList.append(props)

	def getPropertiesByRuleType(self):
		return self.propertiesList

# Class increments and decrements a list
class IncrDecrListPos:

	pos = 0
	listChoice = []

	def __init__(self):
		pass

	def setListChoice(self, listChoice):
		self.listChoice = listChoice

	def setPos(self, pos):
		self.pos = pos

	def getPos(self):
		return self.pos

	def getIncrChoice(self):
		self.pos = 0 if self.pos == (len(self.listChoice)) else self.getPos()
		ret = self.listChoice[self.getPos()]
		self.setPos(self.pos)
		self.pos += 1
		return ret

	def getDecrChoice(self):
		self.pos = len(self.listChoice) if self.pos == 0 else self.getPos()
		self.setPos(self.getPos())
		self.pos -= 1
		ret = self.listChoice[self.getPos()-1]
		return ret
