
__version__ = "2024.02.02"

from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional
import wx
import gui
from logHandler import log
from .. import ruleHandler
from ..ruleHandler import ruleTypes
from ..ruleHandler.controlMutation import (
	MUTATIONS_BY_RULE_TYPE,
	mutationLabels
)
from . import (
	ContextualMultiCategorySettingsDialog,
	ContextualSettingsPanel,
	guiHelper,
	stripAccel,
	stripAccelAndColon
)
from ..utils import updateOrDrop

from collections import OrderedDict, namedtuple
import  ui

mutation_options = ("","heading.1", "heading.2", "heading.3", "labelled")
formmode_options = ("","Inchangé", "Activé", "Désactivé")

FIELDS = OrderedDict((
		# Translator: Multiple results checkbox label for the rule dialog's properties panel.
		("multiple", pgettext("webAccess.ruleProperties", "&Multiple results")),
		# Translator: Activate form mode checkbox label for the rule dialog's properties panel.
		("formMode", pgettext("webAccess.ruleProperties", "Activate &form mode")),
		# Translator: Skip page down checkbox label for the rule dialog's properties panel.
		("skip", pgettext("webAccess.ruleProperties", "S&kip with Page Down")),
		# Translator: Speak rule name checkbox label for the rule dialog's properties panel.
		("sayName", pgettext("webAccess.ruleProperties", "&Speak rule name")),
		# Translator: Custom name input label for the rule dialog's properties panel.
		("customName", pgettext("webAccess.ruleProperties", "Custom &name:")),
		# Label depends on rule type)
		("customValue", None),
		# Translator: Transform select label for the rule dialog's properties panel.
		("mutation", pgettext("webAccess.ruleProperties", "&Transform:")),
	))

RULE_TYPE_FIELDS = OrderedDict((
	(ruleTypes.PAGE_TITLE_1, ("customValue",)),
	(ruleTypes.PAGE_TITLE_2, ("customValue",)),
	(ruleTypes.ZONE, (
		"formMode",
		"skip",
		"sayName",
		"customName",
		"customValue",
		"mutation"
	)),
	(ruleTypes.MARKER, (
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
	        *args
	):

		super(ListControl, self).__init__()
		self.propsPanel = args[0]
		self.propertiesList = args[1]
		log.info("======================================= properties list==============> {}".format(self.propertiesList))
		self.listCtrl = args[2]
		self.toggleBtn = args[3]
		self.editable = args[4]
		self.choice = args[5]
		self.btnAddProps = args[6]
		self.btnDelProps = args[7]
		self.context = args[8]

		self.listCtrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onItemSelListCtrl)
		self.listCtrl.Bind(wx.EVT_KEY_DOWN, self.onKeyPress)
		self.toggleBtn.Bind(wx.EVT_TOGGLEBUTTON, self.updateValueEvtToggle)

		self.editable.Bind(wx.EVT_TEXT, self.updateValueEvtEdit)

		self.choice.Bind(wx.EVT_CHOICE, self.updateValueEvtChoice)

		self.btnAddProps.Bind(wx.EVT_BUTTON, self.onAddProperties)
		self.btnDelProps.Bind(wx.EVT_BUTTON, self.onDeleteProperties)
		self.index = 0
		self.incr = 0
		self.currentSelItem = None
		self.init()

	def init(self):
		self.toggleBtn.Disable()
		self.editable.Disable()
		self.choice.Disable()
		self.updateBtnState()

	def interpretBoolVal(self, val):
		ret = lambda x: 'Actif' if x == True else ('Inactif' if x == False else x)
		retVal = lambda x: ret(x) if type(x) == bool else ("vide" if x == None else x)
		return retVal(val)

	def onInitUpdateListCtrl(self):
		self.listCtrl.DeleteAllItems()
		for p in self.propertiesList:
			if p.get_flag():
				self.listCtrl.InsertStringItem(self.index, p.get_displayName())
				self.listCtrl.SetStringItem(self.index, 1, self.interpretBoolVal(p.get_value()))
				self.listCtrl.SetStringItem(self.index, 2, "False")
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
				if p.get_displayName() == selRow[0]:
					if isinstance(p, ToggleProperty):
						p.set_flag(False)
						p.set_value(False)
					elif isinstance(p, EditableProperty):
						p.set_flag(False)
						p.set_value("")
					elif isinstance(p, SingleChoiceProperty):
						p.set_flag(False)
						p.set_value("")
					break


	def appendToList(self):
		val = AppendListCtrl.lst.pop()
		obj=self.getPropsObj(val)
		self.listCtrl.InsertStringItem(self.index, obj.get_displayName())
		self.listCtrl.SetStringItem(self.index, 1, self.interpretBoolVal(obj.get_value()))
		self.listCtrl.SetStringItem(self.index, 2, "False")
		self.index += 1
		#self.listCtrl.SetItemState(self.index+1,  wx.LIST_STATE_FOCUSED, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
		self.listCtrl.SetFocus()

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

	def onEvent(self, evt):
		pass

	def onItemSelListCtrl(self, evt):
		self.currentSelItem = evt.GetItem()
		listItem = self.getItemSelRow()
		for p in self.propertiesList:
			if isinstance(p, ToggleProperty):
				if listItem[0] == p.get_displayName():
					self.choice.Disable()
					self.editable.Disable()
					self.toggleBtn.Enable()
					self.toggleBtn.SetLabel("")
					self.toggleBtn.SetLabel(p.get_displayName())
					val = p.get_value()
					if val:
						self.toggleBtn.SetValue(True)
						return
					else:
						self.toggleBtn.SetValue(False)
						return
			if isinstance(p, SingleChoiceProperty):
				if listItem[0] == p.get_displayName():
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
							return
			if isinstance(p, EditableProperty):
				if listItem[0] == p.get_displayName():
					self.choice.Disable()
					self.toggleBtn.Disable()
					self.editable.Enable()
					self.toggleBtn.SetLabel("")
					if p.get_value() is not None:
						self.editable.SetValue(p.get_value())
					else:
						self.editable.SetValue("")
						return

	def updateChoices(self,choiceItem ,id):
		if id == "mutation":
			choiceItem.Clear()
			data = self.context["data"]["rule"]
			ruleType = data.get("type")
			for id_ in MUTATIONS_BY_RULE_TYPE.get(ruleType, []):
				label = mutationLabels.get(id_)
				if label is None:
					log.error("No label for mutation id: {}".format(id_))
				choiceItem.Append(label)
		elif id == "formMode":
			choiceItem.Clear()
			# self.listChoice = props.formmode_options
			for i in range(0, len(formmode_options)):
				choiceItem.Append(formmode_options[i])

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
				elif isinstance(p, SingleChoiceProperty) and rowItem[0] == p.get_displayName():
						self.setChoiceList(rowItem[0])
						retChoiceList = self.setChoiceList(rowItem[0])
						retChoice = self.updateChoiceByList(retChoiceList)
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
		mutation_options = []
		for p in self.propertiesList:
			if rowItem == p.get_displayName():
				if p.get_id() == "mutation":
					data = self.context["data"]["rule"]
					ruleType = data.get("type")
					for id_ in MUTATIONS_BY_RULE_TYPE.get(ruleType, []):
						label = mutationLabels.get(id_)
						if label is None:
							log.error("No label for mutation id: {}".format(id_))
						mutation_options.append(label)
					return mutation_options
				elif p.get_id() == "formMode":
					return formmode_options

	def updateChoiceByList(self, listChoice):
		self.incr = 0 if self.incr == (len(listChoice)-1) else self.incr
		self.incr += 1
		return listChoice[self.incr]

	def updateChoiceProperties(self, rowItem, val):
		for p in self.propertiesList:
			if p.get_displayName() == rowItem:
				p.set_value(val)
				n = self.choice.FindString(p.get_value(), False)
				if n != -1:
					self.choice.SetSelection(n)
					self.updatePropertiesList(rowItem)
					return

	def updatePropertiesList(self, rowProps):
		ret = lambda x: 'Actif' if x == True else ('Inactif' if x == False else x)
		for p in self.propertiesList:
			if p.get_displayName() == rowProps:
				id = p.get_id()
				obj=self.getPropsObj(id)

				index = self.currentSelItem.GetId()
				self.listCtrl.SetItem(index, 1, ret(obj.get_value()))
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
			options: Tuple[str, ...],
			selected_option: Optional[str] = None
	):
		super(SingleChoiceProperty, self).__init__(id, display_name, PropertyType.SINGLE_CHOICE)
		self.options = options
		self.__flag = flag
		self.__selected_option = selected_option if selected_option in options else options[0]

	def get_id(self):
		return super(SingleChoiceProperty, self).get_id()

	def get_displayName(self):
		return super(SingleChoiceProperty, self).get_displayName()

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def get_value(self):
		return self.__selected_option

	def set_value(self, option):
		self.__selected_option = option

	def updateFlag(self, evt):
		self.set_flag(True)
		AppendListCtrl.lst.append(self.get_id())

class MultipleChoiceProperty(Property):
	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			options: Tuple[str, ...],
			selected_options: Optional[Tuple[str, ...]] = (1, 3)
	):
		super(MultipleChoiceProperty, self).__init__(id, display_name, PropertyType.MULTIPLE_CHOICE)
		self.__flag = flag
		self.options = options
		self.__selected_options = selected_options if all(
			option in options for option in selected_options
		) else tuple()


	def get_id(self):
		return super(MultipleChoiceProperty, self).get_id()

	def get_displayName(self):
		return super(MultipleChoiceProperty, self).get_displayName()

	def get_value(self):
		return self.__selected_options


	def set_value(self, options):
		self.__selected_options = options

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

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

	def __init__(self):
		self.__propsSayName = ToggleProperty("sayName", "Dire le nom de la règle", False, False)
		self.__propsSkip = ToggleProperty("skip", "Ignorer la page suivante", False, False)
		self.__propsMultiple = ToggleProperty("multiple", "Résultats Multiples", False, False)
		self.__propsCustomName = EditableProperty("customName", "Nom personnalisé", False)
		self.__propscustomValue = EditableProperty("customValue", "Message personnalisé", False)
		self.__propsFormMode = SingleChoiceProperty("formMode", "Activer le mode formulaire", False, formmode_options)
		self.__propsMutation = SingleChoiceProperty("mutation", "Transformation", False, mutation_options)
		self.setProperties()

	def setProperties(self):
		self.propertiesList = [
			self.__propsSayName,
			self.__propsSkip,
			self.__propsMultiple,
			self.__propsCustomName,
			self.__propscustomValue,
			self.__propsFormMode,
			self.__propsMutation
		]
	def getProperties(self):
		log.info(self.propertiesList)
		return  self.propertiesList













