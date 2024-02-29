
__version__ = "2024.02.02"

from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional
import wx
import gui
from logHandler import log
from ..ruleHandler import ruleTypes
from ..ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
from collections import OrderedDict, namedtuple
import  ui

RULE_TYPE_FIELDS = OrderedDict((
	(ruleTypes.PAGE_TITLE_1, ("customValue",)),
	(ruleTypes.PAGE_TITLE_2, ("customValue",)),
	(ruleTypes.ZONE, (
		"autoAction"
		"formMode",
		"skip",
		"sayName",
		"customName",
		"customValue",
		"mutation"
	)),
	(ruleTypes.MARKER, (
		"autoAction"
		"multiple",
		"formMode",
		"skip",
		"sayName",
		"customName",
		"customValue",
		"mutation"
	)),
	))

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
		self.btnAddProps = propsPanel.btnAddProps
		self.btnDelProps = propsPanel.btnDelProps
		self.context = propsPanel.context

		# wx.List control event binding
		self.listCtrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onItemSelListCtrl)
		self.listCtrl.Bind(wx.EVT_KEY_DOWN, self.onKeyPress)
		self.toggleBtn.Bind(wx.EVT_TOGGLEBUTTON, self.updateValueEvtToggle)
		self.editable.Bind(wx.EVT_TEXT, self.updateValueEvtEdit)
		self.choice.Bind(wx.EVT_CHOICE, self.updateValueEvtChoice)
		self.btnAddProps.Bind(wx.EVT_BUTTON, self.onAddProperties)
		self.btnDelProps.Bind(wx.EVT_BUTTON, self.onDeleteProperties)

		#Local variables
		self.index = 0
		self.currentSelItem = None
		self.mutationOptions = []
		self.autoActionOptions = ["", "default"]

		# Instanciation of increment the values for wx.choice and updates the correspondant wx.listCtrl
		self.objIncAutoAct = IncrementValue()
		self.objIncMut = IncrementValue()
		self.objIncFormMde = IncrementValue()
		self.init()

	def init(self):
		self.toggleBtn.Disable()
		self.editable.Disable()
		self.choice.Disable()
		self.updateBtnState()
		self.getAutoActions()
		self.getMutationOptions()

	def messageBox(self, message, caption):
		gui.messageBox(
			message=message,
			caption=caption,
			style=wx.OK | wx.ICON_EXCLAMATION
		)

	# Translator: State properties boolean "Enable"
	# Translator: State properties boolean "Disable"
	# Translator: State properties boolean "Empty"
	def translateForDisplay(self, val):
		if val is True:
			return _("Enabled")
		elif val is False:
			return _("Disabled")
		elif val is None:
			return _("Disabled")

	def updatedStrValues(self, val, id):
		if id == "autoAction":
			if val:
				retAction = lambda targetval: next((t[0] for t in [x for x in self.autoActionOptions if x[1] == targetval]),None)
				if retAction(val) is not None:
					return retAction(val)
				return _("Choose a value")
			else:
				return _("Choose a value")
		elif id == "mutation":
			if val is None or val == "":
				ret = val
				retMut = _("Choose a value") if val is None or type(bool) else ret
				return retMut
		elif id == "skip" or id == "sayName" or id == "formMode" or id == "multiple":
			if val:
				return self.translateForDisplay(val)
			else:
				return self.translateForDisplay(val)
		elif id == "customValue" or id == "customName":
			if val:
				return val
			else:
				return _("Empty")

	def onInitUpdateListCtrl(self):
		self.listCtrl.DeleteAllItems()
		clsInstance = self.propsPanel.__class__.__name__
		for p in self.propertiesList:
			if p.get_flag():
				val = self.updatedStrValues(p.get_value(), p.get_id())
				self.listCtrl.InsertStringItem(self.index, p.get_displayName())
				self.listCtrl.SetStringItem(self.index, 1, val)

				if clsInstance == "OverridesPanel":
					self.listCtrl.SetStringItem(self.index, 2, self.isOverrided(p.get_id()))
				self.index += 1

	def onAddProperties(self, evt):
		if showPropsDialog(self.context, self.propertiesList):
			self.appendToList()

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

	def isOverrided(self, idProps):
		dataRule = self.context["data"]["rule"]
		ruleType = dataRule.get("type")
		ruleProps = dataRule.get("properties")

		if ruleType is not None and ruleProps is not None:
			if ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
				for key, value in list(ruleProps.items()):
					if idProps == key:
						return self.updatedStrValues(value, idProps)

	def getPropsObj(self, val):
		for p in self.propertiesList:
			if val == p.get_id():
				return p

	def updateBtnState(self):
		return
		nbRow = self.listCtrl.GetItemCount()
		if nbRow == len(propertiesList):
			self.btnAddProps.Disable()
			self.btnDelProps.Enable()
		elif nbRow > 0:
			self.btnDelProps.Enable()
			self.btnAddProps.Enable()
		elif nbRow == 0:
			self.btnDelProps.Disable()
			self.btnAddProps.Enable()

	def getItemSelRow(self):
		column_values = []
		focused_item = self.listCtrl.GetFocusedItem()
		if focused_item != -1:
			column_count = self.listCtrl.GetColumnCount()
			for column in range(column_count):
				column_value = self.listCtrl.GetItem(focused_item, column).GetText()
				column_values.append(column_value)
			return  column_values

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
					n = self.choice.FindString(p.get_value(), False)
					if n!=-1:
						self.choice.SetSelection(n)
			elif isinstance(p, EditableProperty):
				self.choice.Disable()
				self.toggleBtn.Disable()
				self.editable.Enable()
				self.toggleBtn.SetLabel("")
				if p.get_value() is not None:
					self.editable.SetValue(p.get_value())
				else:
					self.editable.SetValue("")

	def updateChoices(self,choiceItem ,id):
		if id == "mutation":
			choiceItem.Clear()
			list(map(lambda x: choiceItem.Append(x[0]), self.mutationOptions))
		elif id == "autoAction":
			choiceItem.Clear()
			list(map(lambda x:choiceItem.Append(x[0]), self.autoActionOptions))

	def onKeyPress(self, evt):
		keycode = evt.GetKeyCode()
		if keycode == wx.WXK_SPACE:
			rowItem = self.getItemSelRow()
			for p in self.propertiesList:
				if isinstance(p ,ToggleProperty) and rowItem[0] == p.get_displayName():
					self.updateToggleBtnPropertiest(rowItem[0])
				elif isinstance(p, EditableProperty) and rowItem[0] == p.get_displayName():
					retDialog = self.editablDialog(rowItem[0])
					self.updateEditableProperties(rowItem[0], retDialog)
					if retDialog is not None:
						self.updateEditableProperties(rowItem[0], retDialog)
					else:
						log.info("Ret value of dialog is empty!")
				elif isinstance(p, SingleChoiceProperty) and rowItem[0] == p.get_displayName():
					retChoiceList = self.setChoiceList(rowItem[0])
					retChoice = self.updateChoiceByList(retChoiceList, p.get_id())
					ui.message("{}".format(retChoice))
					self.updateChoiceProperties(rowItem[0], retChoice)
		evt.Skip()

	def updateToggleBtnPropertiest(self, rowItem):
		for p in self.propertiesList:
			if rowItem in p.get_displayName() and isinstance(p, ToggleProperty):
				val = self.toggleBtn.GetValue()
				if val:
					self.toggleBtn.SetValue(False)
					p.set_value(False)
					ui.message("{} {}".format(p.get_displayName(), "non coché"))
					self.updatePropertiesList(rowItem)
					return
				else:
					self.toggleBtn.SetValue(True)
					p.set_value(True)
					ui.message("{} {}".format(p.get_displayName(), "coché"))
					self.updatePropertiesList(rowItem)
					return

	def updateEditableProperties(self, rowItem, val):
		for p in self.propertiesList:
			if p.get_displayName() == rowItem:
				p.set_value(val)
				self.editable.SetValue(val)
		self.updatePropertiesList(rowItem)

	def editablDialog(self, label):
		dialog = wx.TextEntryDialog(self.propsPanel, label, label)
		if dialog.ShowModal() == wx.ID_OK:
			return dialog.GetValue()
		dialog.Destroy()

	def setChoiceList(self, rowItem):
		for p in self.propertiesList:
			if rowItem == p.get_displayName():
				if p.get_id() == "mutation":
					return [i[0] for i in self.mutationOptions]
				elif p.get_id() == "autoAction":
					return  [i[0] for i in self.autoActionOptions]

	def updateChoiceByList(self, listChoice, id):
		if id == "autoAction":
			self.objIncAutoAct.setListChoice(listChoice)
			return  self.objIncAutoAct.getIncrChoice()
		elif id == "mutation":
			self.objIncMut.setListChoice(listChoice)
			return self.objIncMut.getIncrChoice()

	def getMutationIdByValue(self, value):
		data = self.context["data"]["rule"]
		ruleType = data.get("type")
		for id_ in MUTATIONS_BY_RULE_TYPE.get(ruleType, []):
			label = mutationLabels.get(id_)
			if value == label:
				return id_

	def getMutationValueById(self, id):
		data = self.context["data"]["rule"]
		ruleType = data.get("type")
		for id_ in MUTATIONS_BY_RULE_TYPE.get(ruleType, []):
			label = mutationLabels.get(id_)
			if id_ == id:
				return label

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

	def updateValueEvtEdit(self, evt):
		text = self.editable.GetValue()
		index = self.currentSelItem.GetId()
		item = self.getItemSelRow()
		for p in self.propertiesList:
			if p.get_displayName() == item[0]:
				p.set_value(text)
		self.listCtrl.SetItem(index, 1, text)

	def updateValueEvtChoice(self, evt):
		choiceVal = self.choice.GetString(self.choice.GetSelection())
		selRow = self.getItemSelRow()
		self.updateChoiceProperties(selRow[0], choiceVal)
		self.updatePropertiesList(selRow[0])

	def getAutoActions(self):
		self.autoActionOptions =[]
		mgr = self.context["webModule"].ruleManager
		actionsDict = mgr.getActions()
		defaultval = ("", "")
		[self.autoActionOptions.append((actionsDict[i], i))for i in actionsDict]
		self.autoActionOptions.insert(0, defaultval)

	def getMutationOptions(self):
		self.mutationOptions = []
		defaultval = ("", "")
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
		"""options: Tuple[str, ...],
					selected_option: Optional[str] = None"""
		super(SingleChoiceProperty, self).__init__(id, display_name, PropertyType.SINGLE_CHOICE)
		self.__value = value
		self.__flag = flag
		#self.__selected_option = []

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

class ListProperties:

	propertiesList = []
	FIELDS = None

	def __init__(self):
		self.__propsMultiple = None
		self.__propsMutation = None
		self.__propsFormMode = None
		self.__propsCustomValue = None
		self.__propsCustomName = None
		self.__propsSkip = None
		self.__propsSayName = None
		self.__autoAction = None
		self.FIELDS = None

	def setProperties(self):
		self.FIELDS = self.getFields()
		self.__autoAction = SingleChoiceProperty("autoAction", self.FIELDS["autoAction"], False, "")
		self.__propsMultiple = ToggleProperty("multiple", self.FIELDS["multiple"], False, False)
		self.__propsFormMode = ToggleProperty("formMode", self.FIELDS["formMode"], False, False)
		self.__propsSkip = ToggleProperty("skip", self.FIELDS["skip"], False, False)
		self.__propsSayName = ToggleProperty("sayName", self.FIELDS["sayName"], False, False)
		self.__propsCustomName = EditableProperty("customName", self.FIELDS["customName"], False)
		self.__propsCustomValue = EditableProperty("customValue", self.FIELDS["customValue"], False)
		self.__propsMutation = SingleChoiceProperty("mutation", self.FIELDS["mutation"], False, "")

		self.propertiesList = [
			self.__autoAction,
			self.__propsMultiple,
			self.__propsFormMode,
			self.__propsSkip,
			self.__propsSayName,
			self.__propsCustomName,
			self.__propsCustomValue,
			self.__propsMutation
		]

	def setFields(self, fields):
		self.FIELDS = fields

	def getFields(self):
		return self.FIELDS

	def getProperties(self):
		return  self.propertiesList


class IncrementValue:

	incr = 0
	listChoice = []

	def __init__(self):
		pass

	def setListChoice(self, listChoice):
		self.listChoice = listChoice

	def getIncr(self):
		return self.incr

	def setIncr(self, val):
		self.incr = val

	def getIncrChoice(self):
		self.incr = 0 if self.incr == (len(self.listChoice) - 1) else self.incr
		ret = self.listChoice[self.getIncr()]
		self.incr += 1
		self.setIncr(self.incr)
		return ret











