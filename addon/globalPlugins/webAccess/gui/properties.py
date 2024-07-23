__version__ = "2024.06.26"
__author__ = "Sendhil Randon <sendhil.randon-ext@francetravail.fr>"

from collections import OrderedDict
import addonHandler
from abc import ABC, abstractmethod, ABCMeta
from enum import Enum
from typing import Optional
import wx
import gui
from logHandler import log
from ..ruleHandler import ruleTypes
from ..ruleHandler.controlMutation import (
    MUTATIONS_BY_RULE_TYPE,
    mutationLabels
)
import ui

addonHandler.initTranslation()
from . import (
	ContextualSettingsPanel
)

# event handler constants
EVT_KEY_DOWN = wx.EVT_KEY_DOWN.typeId
EVT_CHAR_HOOK = wx.EVT_CHAR_HOOK.typeId

FIELDS = {
	# Translator: Multiple results checkbox label for the rule dialog's properties panel.
	"autoAction": _("Auto Actions"),
	# Translator: Multiple results checkbox label for the rule dialog's properties panel.
	"multiple": _("Multiple results"),
	# Translator: Activate form mode checkbox label for the rule dialog's properties panel.
	"formMode": _("Activate form mode"),
	# Translator: Skip page down checkbox label for the rule dialog's properties panel.
	"skip": _("Skip with Page Down"),
	# Translator: Speak rule name checkbox label for the rule dialog's properties panel.
	"sayName": _("Speak rule name"),
	# Translator: Custom name input label for the rule dialog's properties panel.
	"customName": _("Custom name"),
	# Label depends on rule type)
	"customValue": _("Custom value"),
	# Translator: Transform select label for the rule dialog's properties panel.
	"mutation": _("Transform")
}

FIELDS_WIDGET_MAP = {
	"autoAction": wx.ComboBox,
	"multiple": wx.CheckBox,
	"formMode": wx.CheckBox,
	"skip": wx.CheckBox,
	"sayName": wx.CheckBox,
	"customName": wx.TextCtrl,
	"customValue": wx.TextCtrl,
	"mutation": wx.ComboBox
}

RULE_TYPE_FIELDS = {
	ruleTypes.PAGE_TITLE_1: "customValue",
	ruleTypes.PAGE_TITLE_2: "customValue",
	ruleTypes.ZONE:
		(
			"autoAction", "formMode",
			"skip", "sayName",
			"customName", "customValue",
			"mutation"
		),

	ruleTypes.MARKER:
		(
			"autoAction", "multiple",
			"formMode", "skip",
			"sayName", "customName",
			"customValue", "mutation"
		)
}

def showPropsDialog(context, properties):
	"""
	Display context menu by clicking add button on properties criteira panel
	"""
	PropsMenu(context, properties).ShowModal()
	return True


class ListControl(ContextualSettingsPanel):

	def makeSettings(self, settingsSizer):
		self.hidable = []
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		row = 0
		# Translators: Displayed when the selected rule type doesn't support any action
		self.noPropertiesLabel = wx.StaticText(self, label=_("No properties available for the selected rule type."))
		gbSizer.Add(self.noPropertiesLabel, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

		row += 1
		# Translators: Keyboard shortcut input label for the rule dialog's action panel.
		self.propertiesLabel = wx.StaticText(self, label=_("&Properties List"))
		gbSizer.Add(self.propertiesLabel, pos=(row, 0), flag=wx.EXPAND)
		self.hidable.append(self.propertiesLabel)

		self.listCtrl = wx.ListCtrl(self, size=(-1, 250), style=wx.LC_REPORT | wx.BORDER_SUNKEN)
		self.listCtrl.InsertColumn(0, 'Properties')
		self.listCtrl.InsertColumn(1, 'Value')
		self.hidable.append(self.listCtrl)
		row += 1

		self.editable = wx.TextCtrl(self, size=(-1, 30))
		self.hidable.append(self.editable)

		self.toggleBtn = wx.ToggleButton(self, label="", size=(150, 30))
		self.hidable.append(self.toggleBtn)

		self.choice = wx.Choice(self, choices=[], size=(150, 30))
		self.hidable.append(self.choice)

		gbSizer.Add(self.listCtrl, pos=(row, 0), span=(3,3), flag=wx.EXPAND)
		row += 3
		gbSizer.Add(self.editable, pos=(row, 0), span=(0, 1), flag=wx.EXPAND)
		row += 1

		sizeBox = wx.BoxSizer(wx.HORIZONTAL)
		sizeBox.Add(self.toggleBtn)
		sizeBox.Add(self.choice)
		gbSizer.Add(sizeBox, pos=(row, 0), flag=wx.EXPAND)
		self.sizer = gbSizer
		# wx.List control event binding
		self.listCtrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onItemSelListCtrl)
		self.listCtrl.Bind(wx.EVT_KEY_DOWN, self.onKeyPress)
		self.listCtrl.Bind(wx.EVT_CHAR_HOOK, self.keyShiftSpace)
		self.toggleBtn.Bind(wx.EVT_TOGGLEBUTTON, self.updateValueEvtToggle)
		self.editable.Bind(wx.EVT_TEXT, self.updateValueEvtEdit)
		self.choice.Bind(wx.EVT_CHOICE, self.updateValueEvtChoice)

		# Local variables
		self.index = 0
		self.currentSelItem = None
		self.autoActionOptions = []
		self.mutationOptions = []
		self.gesturesOptions = []

		# Instanciation of increment the values for wx.choice and updates the correspondant wx.listCtrl
		self.objIncAutoAct = IncrDecrListPos()
		self.objIncMut = IncrDecrListPos()
		self.objIncGest = IncrDecrListPos()

		gbSizer.AddGrowableCol(0)

	def initData(self, context, **kwargs):
		"""
		Init wx.listCtrl elements
		"""
		self.context = context
		self.toggleBtn.Disable()
		self.editable.Disable()
		self.choice.Disable()
		self.getAutoActions()
		self.getMutationOptions()
		self.getGestureOptions()


	def setColumunWidthAutoSize(self):
		for i in range(self.listCtrl.GetColumnCount()):
			self.listCtrl.SetColumnWidth(i, wx.LIST_AUTOSIZE_USEHEADER)

	def showItems(self, data):
		ruleType = data.get("type")
		typeValues = RULE_TYPE_FIELDS.get(ruleType)
		if typeValues is None:
			for item in self.hidable:
				item.Hide()
			self.noPropertiesLabel.Show()
		else:
			for item in self.hidable:
				item.Show()
			self.noPropertiesLabel.Hide()

	def initPropertiesList(self, context):
		self.context = context
		index=self.listCtrl.GetFirstSelected()
		propsList = ListProperties()
		propsList.setPropertiesByRuleType(self.context)
		self.propertiesList = propsList.getPropertiesByRuleType()
		self.focusListCtrl(index=index)


	def updateListCtrl(self, data):
		"""SU ruleProps:
			data = dataRule["properties"]"""
		if data:
			for props in self.propertiesList:
				for key, value in data.items():
					if props.get_id() == key:
						props.set_flag(True)
						props.set_value(value)

	@staticmethod
	def getAltFieldLabel(ruleType, key, default=None):
		"""
		Function defines as static to customize customvalue and customName properties
		according to the rule
		"""
		if key == "customValue":
			if ruleType in (ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return _("Custom page title")
			elif ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
				# Translator: Field label on the RulePropertiesEditor dialog.
				return _("Custom message")
		elif key == "customName" and ruleType in (ruleTypes.ZONE, ruleTypes.MARKER):
			# Translator: Field label on the RulePropertiesEditor dialog.
			return _("Custom name")
		return default

	def getKeyByRuleType(self, displayName):
		"""
		Function converts the appropriate display name to the listctrl activate funtions
		"""
		if displayName == "Custom page title" or displayName == "Custom message":
			return "customValue"
		else:
			return displayName

	def customDisplayLabel(self, props):
		"""
		Function calls "getAltFieldLabel" static function and filter the Editable
		object and rule and return the appropriate display value
		"""
		dataRule = self.context["data"]["rule"]
		ruleType = dataRule.get("type")
		if isinstance(props, EditableProperty):
			return ListControl.getAltFieldLabel(ruleType, props.get_id())
		else:
			return props.get_displayName()

	def messageBox(self, message, caption):
		"""
		Message box function displays the given message and caption in a popup
		"""
		gui.messageBox(
			message=message,
			caption=caption,
			style=wx.OK | wx.ICON_EXCLAMATION
		)

	@staticmethod
	def getChoicesDisplayableValue(context, fieldName, value):
		if fieldName == "mutation":
			try:
				return list(mutationLabels.values())[value]
			except Exception as e:
				return 0
		elif fieldName == "autoAction":
			mgr = context["webModule"].ruleManager
			return mgr.getActions().get(value, None)
		return value

	@staticmethod
	def getChoiceOptionForField(fieldName, mgr):
		if fieldName == "mutation":
			return ListControl.buildMutationOptions()
		elif fieldName == "autoAction":
			return ListControl.buildAutoActionOptions(mgr)
		return []

	@staticmethod
	def getIndexOfCurrentChoice(fieldName, mgr, value):
		choiceKeysList = []
		if fieldName == "mutation":
			return int(value) if value else -1
		elif fieldName == "autoAction":
			choiceKeysList = mgr.getActions().keys()
		return list(choiceKeysList).index(value)

	@staticmethod
	def getValueAtIndex(fieldName, mgr, index):
		if fieldName == "mutation":
			return index # list(mutationLabels.keys())[index]
		elif fieldName == "autoAction":
			return list(mgr.getActions().keys())[index]
		raise ValueError(f"Field name '{fieldName}' could not be found in mutation or autoAction")

	def getChoiceOptionById(self, idOption):
		"""
		function return the list according to the option id
		"""
		choiceOption = {
			"autoAction": self.autoActionOptions,
			"mutation": self.mutationOptions,
			"gestures": self.gesturesOptions

		}
		return choiceOption[idOption] if idOption in choiceOption else []

	def getIncDecObjById(self, idOption):
		"""
		function return the incrDecr object according to the option id
		which is used to set the pos of the next element of the dropdown
		"""
		objIncDecPos = {
			"autoAction": self.objIncAutoAct,
			"mutation": self.objIncMut,
			"gestures": self.objIncGest
		}
		return objIncDecPos[idOption] if idOption in objIncDecPos else None

	def setValueSingleChoiceProps(self, val, id):
		"""
		Function set default updatable properties on panel activation
		"""
		retChoiceVal = lambda targetval, l: next((t[0] for t in [x for x in l if x[1] == targetval]), None)
		if id:
			retChoice = self.getChoiceOptionById(id)
			retObjIncr = self.getIncDecObjById(id)
			ret = retChoiceVal(val, retChoice)
			return ret if ret else self.setDefaultChoice(retObjIncr, retChoice)

	def setDefaultChoice(self, objToIncr, lst):
		"""
		Set the choice dropdown to default value if none is retrived
		"""
		self.choice.SetSelection(1)
		objToIncr.setPos(1)
		return lst[0][0]

	def updatedStrValues(self, val, id):
		"""
		Function set default updatable properties on panel activation
		"""
		if isinstance(self.getPropsObj(id), SingleChoiceProperty):
			return self.setValueSingleChoiceProps(val, id)
		elif isinstance(self.getPropsObj(id), ToggleProperty):
			# Translator: State properties boolean "Enabled"
			# Translator: State properties boolean "Disabled"
			return _("Enabled") if val else _("Disabled")
		elif isinstance(self.getPropsObj(id), EditableProperty):
			# Translator: State properties editable "Empty"
			return val if val else _("undefined")

	def onInitUpdateListCtrl(self):
		"""
		set fresh values on init for properties on wx.listCtrl
		"""
		self.listCtrl.DeleteAllItems()

		# clsInstance = self.propsPanel.__class__.__name__
		for p in reversed(self.propertiesList):
			if p.get_flag():
				val = self.updatedStrValues(p.get_value(), p.get_id())
				self.listCtrl.InsertStringItem(self.index, self.customDisplayLabel(p))
				self.listCtrl.SetStringItem(self.index, 1, val)
		self.setColumunWidthAutoSize()

	def onAddProperties(self, evt):
		"""
		wx.add button applicable only on criteria properties panel
		"""
		if showPropsDialog(self.context, self.propertiesList):
			self.appendToList()

	def onDeleteProperties(self, evt):
		"""
		wx.delete add applicable only on criteria properties panel
		"""
		selRow = self.getItemSelRow()
		index = self.listCtrl.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
		if index != -1:
			# Delete the selected item
			self.listCtrl.DeleteItem(index)
			self.focusListCtrl(index - 1, addOrDel=True)
			for p in self.propertiesList:
				if not self.customDisplayLabel(p) == selRow[0]:
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
		"""
		Append to list the chossen properties in the list on criteria editor panel
		"""
		obj = self.getListToAppend()
		if obj:
			self.listCtrl.InsertStringItem(self.index, self.customDisplayLabel(obj))
			self.listCtrl.SetStringItem(self.index, 1, self.updatedStrValues(obj.get_value(), obj.get_id()))
			self.index += 1
			lstIndex = self.listCtrl.GetItemCount()
			self.focusListCtrl(lstIndex-1, True)


	def getListToAppend(self):
		"""
		return the context menu value
		"""
		if AppendListCtrl.lst:
			val = AppendListCtrl.lst.pop()
			obj = self.getPropsObj(val)
			return obj
		else:
			log.debug("Context menu closed without chosen any")

	def focusListCtrl(self, index, addOrDel=None):
		"""
		Set to the focus to the last appended item to the list control
		"""
		firstItem = self.listCtrl.GetFirstSelected()
		if firstItem != -1:
			previous = firstItem
			self.listCtrl.Select(previous, False)
		if addOrDel:
			self.listCtrl.SetFocus()
			self.wxListCtrlFocus(index)
		if  index != -1:
			self.wxListCtrlFocus(index)

	def wxListCtrlFocus(self, index):
		"""
		Function set the focus and select the given index of the list control
		"""
		self.listCtrl.SetItemState(index, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
		self.listCtrl.SetItemState(index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)

	def getPropsObj(self, val):
		"""
		Function returns the properties obj
		"""
		for p in self.propertiesList:
			if val == p.get_id():
				return p

	def getItemSelRow(self):
		"""
		Returns the selected item from the properties list
		"""
		column_values = []
		focused_item = self.listCtrl.GetFocusedItem()
		if focused_item != -1:
			column_count = self.listCtrl.GetColumnCount()
			for column in range(column_count):
				column_value = self.listCtrl.GetItem(focused_item, column).GetText()
				column_values.append(column_value)
			return  column_values

	def onItemSelListCtrl(self, evt):
		"""
		Event handler function binded over while browsing on the properties list
		"""
		self.currentSelItem = evt.GetItem()
		listItem = self.getItemSelRow()
		customItem = self.getKeyByRuleType(listItem[0])
		for p in self.propertiesList:
			if not customItem == p.get_displayName():
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
					retVal, n = self.updateChoiceDropDown(p.get_value(), p.get_id())
					if retVal is not None:
						self.choice.SetSelection(n)
				else:
					retChoice = self.getChoiceOptionById(p.get_id())
					retObjIncr = self.getIncDecObjById(p.get_id())
					retObjIncr.setPos(1) if retChoice else None
					self.choice.SetSelection(0)
			elif isinstance(p, EditableProperty):
				self.editable.Enable()
				self.choice.Disable()
				self.toggleBtn.Disable()
				self.toggleBtn.SetLabel("")
				if p.get_value() is not None:
					self.editable.SetValue(p.get_value())
				else:
					pass

	def updateChoiceDropDown(self, val, idProps):
		"""
		Function updates the dropdown list and set the position to the selected value
		"""
		retChoice = self.getChoiceOptionById(idProps)
		retObjIncr = self.getIncDecObjById(idProps)
		lst = retChoice if retChoice is not None else None
		getTupleVal = lambda targetval: next((t[0] for t in [x for x in lst if x[1] == targetval]), None)
		n = self.choice.FindString(getTupleVal(val), False)
		if n != -1:
			self.choice.SetSelection(n)
			pos = self.choice.GetSelection()
			retObjIncr.setPos(pos + 1) if retObjIncr else None
			return getTupleVal(val), n

	def updateChoices(self, choiceItem, id):
		"""
		on init function updates the mutation and autoActions list
		"""
		if id:
			choiceItem.Clear()
			list(map(lambda x: choiceItem.Append(x[0]), self.getChoiceOptionById(id)))
		else:
			return


	def onKeyPress(self, evt):
		"""
		Event handler function bound to space key
		"""
		keycode = evt.GetKeyCode()
		modifiers = evt.GetModifiers()
		if keycode == wx.WXK_SPACE and not modifiers:
			rowItem = self.getItemSelRow()
			for p in self.propertiesList:
				if isinstance(p ,ToggleProperty) and rowItem[0] == p.get_displayName():
					self.updateToggleBtnPropertiest(rowItem[0])
					return
				elif isinstance(p, EditableProperty) and rowItem[0] == self.customDisplayLabel(p):
					retDialog = self.editableDialog(rowItem[0],p.get_value())
					self.updateEditableProperties(rowItem[0], retDialog)
					return
				elif isinstance(p, SingleChoiceProperty) and rowItem[0] == p.get_displayName():
					retChoiceList = self.setChoiceList(rowItem[0])
					retChoice = self.updateChoiceByList(evt.EventType, retChoiceList, p.get_id())
					ui.message("{}".format(retChoice))
					self.updateChoiceProperties(rowItem[0], retChoice)
					return
		evt.Skip()

	def keyShiftSpace(self, evt):
		"""
		Event handler function binded to shift+space key inorder to decrement the position of list
		"""
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

	def updateToggleBtnPropertiest(self, rowItem):
		"""
		Function updates the toggle btn display and sets value after the event from the onKeyPress fun.
		"""
		for p in self.propertiesList:
			if rowItem in p.get_displayName() and isinstance(p, ToggleProperty):
				val = not bool(self.toggleBtn.GetValue())
				self.toggleBtn.SetValue(val)
				p.set_value(val)
				# Translator: State properties "unchecked"
				# Translator: State properties"checked"
				ui.message(_("checked") if val else _("unchecked"))
				self.updatePropertiesList(rowItem)

	def updateEditableProperties(self, rowItem, val):
		"""
		Function updates the editable properties list
		"""
		for p in self.propertiesList:
			if self.customDisplayLabel(p) == rowItem:
				p.set_value(val)
				if val:
					self.editable.SetValue(val)
					return


	def editableDialog(self, label, currentValue):
		"""
		Function displays an input dialog after onkyepress event for ediable properteis
		"""
		dialog = wx.TextEntryDialog(self, label, label)
		dialog.SetValue(currentValue) if currentValue is not None else ""
		if dialog.ShowModal() == wx.ID_OK:
			return dialog.GetValue()
		dialog.Destroy()

	def setChoiceList(self, rowItem):
		"""
		Function set and option choosen from the dropDown list or onKeyPress event in the properties list
		"""
		for p in self.propertiesList:
			if rowItem == p.get_displayName():
				retOptions = self.getChoiceOptionById(p.get_id())
				return [i[0] for i in retOptions]

	def updateChoiceByList(self, eventType, listChoice, id):
		"""
		Function updates the choices uses binded onkeyPress events
		for increment and keyShiftSpace events for decrement the lists
		"""
		if id:
			retObjIncr = self.getIncDecObjById(id)
			if eventType == EVT_KEY_DOWN:
				retObjIncr.setListChoice(listChoice)
				return retObjIncr.getIncrChoice()
			elif eventType == EVT_CHAR_HOOK:
				retObjIncr.setListChoice(listChoice)
				return retObjIncr.getDecrChoice()

	def getChoiceKeyByValue(self, val, idOption):
		"""
		Function returns list key of a tuple according to the value
		"""
		options = self.getChoiceOptionById(idOption)
		getId = lambda x: next((t[1] for t in [x for x in options if x[0] == val]), val)
		return getId(val)

	def getChoiceValueByKey(self, key, idOption):
		"""
		Function returns list value of a tuple according to the key
		"""
		options = self.getChoiceOptionById(idOption)
		getValue = lambda x: next((t[0] for t in [x for x in options if x[1] == key]), key)
		return getValue(key)

	def updateChoiceProperties(self, rowItem, val):
		"""
		Updates the choice properties in the list from tab events as well as dropdown events
		"""
		for p in self.propertiesList:
			if p.get_displayName() == rowItem:
				val = self.getChoiceKeyByValue(val, p.get_id())
				p.set_value(val)
				valFindString = self.getChoiceValueByKey(val, p.get_id())
				if valFindString:
					n = self.choice.FindString(valFindString, False)
					if n != -1:
						self.choice.SetSelection(n)
						self.updatePropertiesList(rowItem)
						return
					return

	def updatePropertiesList(self, rowProps):
		"""
		Function updates the values in the properties list control globally
		"""
		# Translator: State properties boolean "Enable"
		# Translator: State properties boolean "Disable"
		ret = lambda x: _("Enable") if x == True else (_("Disable") if x == False else x)
		forVal = filter(lambda x: x.get_displayName() == rowProps, self.propertiesList)
		res = list(forVal)

		if res:
			valProps = res[0].get_value()
			val = ret(valProps) if valProps is not None else None
			index = self.currentSelItem.GetId()
			updateVal = self.getChoiceValueByKey(val, res[0].get_id())
			self.listCtrl.SetItem(index, 1, updateVal)
			return
		return

	def updateValueEvtToggle(self, evt):
		"""
		Event handler to update toggle button properties
		"""
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
		"""
		Event handler updates Editable properties
		"""
		text = self.editable.GetValue()
		index = self.currentSelItem.GetId()
		item = self.getItemSelRow()
		for p in self.propertiesList:
			if self.customDisplayLabel(p) == item[0]:
				p.set_value(text)
		self.listCtrl.SetItem(index, 1, text)

	def updateValueEvtChoice(self, evt):
		"""
		Event handler updates choice properties
		"""
		choiceVal = self.choice.GetString(self.choice.GetSelection())
		selRow = self.getItemSelRow()
		self.updateChoiceProperties(selRow[0], choiceVal)
		forVal = filter(lambda x: x.get_displayName() == selRow[0], self.propertiesList)
		res = list(forVal)
		pos = self.choice.GetSelection()
		retObjIncr = self.getIncDecObjById(res[0].get_id())
		retObjIncr.setPos(pos + 1) if res[0].get_id() else None
		self.updatePropertiesList(selRow[0])

	@staticmethod
	def buildAutoActionOptions(mgr):
		actionsDict = mgr.getActions()
		defaultval = ("Choose an option", "")
		return [defaultval] + [(actionsDict[i], i) for i in actionsDict]

	def getAutoActions(self):
		"""
		On init, function updates the autoActions list on run time
		"""
		mgr = self.context["webModule"].ruleManager
		# Translator: State properties "unchecked"
		self.autoActionOptions = self.buildAutoActionOptions(mgr)

	@staticmethod
	def buildMutationOptions():
		defaultval = ("Choose an option", "")
		return [defaultval] + [(mutationLabel, i) for i, mutationLabel in enumerate(mutationLabels.values())]


	def getMutationOptions(self):
		"""
		On init function updates the run time mutation list
		"""
		self.mutationOptions = self.buildMutationOptions()


	def getGestureOptions(self):
		"""
		On init function updates the run time gestures list
		"""
		self.gestures = []
		defaultval = (_("Choose an option"), "")
		self.gestures.insert(0, defaultval)


class AppendListCtrl(ListControl):
	"""
	Class append the context properties to the list
	"""
	lst = []

	def __init__(self, clientListBox):
		super().__init__(clientListBox)
		self.clientListBox = clientListBox

	def appendToList(self):
		if not AppendListCtrl.lst:
			return
		else:
			super().appendToList()
			AppendListCtrl.lst.clear()


class PropsMenu(wx.Menu):
	"""
	Class displays the context menu for criteria panel properties
	"""

	def __init__(self, context, properties):
		super().__init__()
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

	def displayLabel(self, props):
		"""
		getAltFieldLabel func calls static function and filter the Editable
		object and rule and return the appropriate display value
		"""
		dataRule = self.context["data"]["rule"]
		ruleType = dataRule.get("type")
		if isinstance(props, EditableProperty):
			return ListControl.getAltFieldLabel(ruleType, props.get_id())
		else:
			return props.get_displayName()

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
	"""
	Abstract class for properties
	"""

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
	"""
	Class creates toggle properties which takes boolean
	"""

	def __init__(
			self,
			id: str,
			display_name: str,
			value: bool,
			flag: bool,
	):
		super().__init__(id, display_name, PropertyType.TOGGLE)
		self.__flag = flag
		self.__value = value

	def get_id(self):
		return super().get_id()

	def get_displayName(self):
		return super().get_displayName()

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
	"""
	Class creates choice properites
	"""

	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			value: Optional[str] = None,
	):
		super().__init__(id, display_name, PropertyType.SINGLE_CHOICE)
		self.__value = value
		self.__flag = flag

	def get_id(self):
		return super().get_id()

	def get_displayName(self):
		return super().get_displayName()

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
	"""
	Class creates editable properites and set flag as a boolean
	"""

	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			value: Optional[str] = None,
	):
		super().__init__(id, display_name, PropertyType.EDITABLE)
		self.__value = value
		self.__flag = flag

	def get_id(self):
		return super().get_id()

	def get_displayName(self):
		return super().get_displayName()

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
	"""
	Initialising List of properties and append to the listProperties according
	to the rule
	"""
	propertiesList = []
	dataRule = None
	ruleType = None

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
		self.propertiesList = []
		self.dataRule = context["data"]["rule"]
		self.ruleType = self.dataRule.get("type")
		self.__autoAction = SingleChoiceProperty("autoAction", FIELDS["autoAction"], False)
		self.__propsMultiple = ToggleProperty("multiple", FIELDS["multiple"], False, False)
		self.__propsFormMode = ToggleProperty("formMode", FIELDS["formMode"], False, False)
		self.__propsSkip = ToggleProperty("skip", FIELDS["skip"], False, False)
		self.__propsSayName = ToggleProperty("sayName", FIELDS["sayName"], False, False)
		self.__propsCustomName = EditableProperty("customName", FIELDS["customName"], False)
		self.__propsCustomValue = EditableProperty("customValue", FIELDS["customValue"], False)
		self.__propsMutation = SingleChoiceProperty("mutation", FIELDS["mutation"], False)

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


class IncrDecrListPos:
	"""
	class increments and decrements a choosen list and
	it sets the get the positions of a list.
	This class is utilised by the single choice property
	"""
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
		ret = self.listChoice[self.getPos() - 1]
		return ret

# End of file
