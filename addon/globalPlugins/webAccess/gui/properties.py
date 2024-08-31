# globalPlugins/webAccess/gui/properties.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (http://accessolutions.fr)
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

__version__ = "2024.08.02"
__author__ = "Sendhil Randon <sendhil.randon-ext@francetravail.fr>"

from collections import ChainMap
from collections.abc import Iterator, Mapping
from abc import abstractmethod
from enum import Enum
from typing import Any
import wx

import addonHandler
import gui
from gui import guiHelper
import speech
import ui

from ..ruleHandler.controlMutation import MUTATIONS_BY_RULE_TYPE, mutationLabels
from ..ruleHandler.properties import PropertiesBase, PropertySpec, PropertySpecValue, PropertyValue
from ..utils import guarded, logException
from . import ContextualSettingsPanel, EditorType, ListCtrlAutoWidth, SingleFieldEditorMixin


addonHandler.initTranslation()


class Property:
	
	__slots__ = ("_container", "name")
	
	def __init__(self, container: "Properties", name: str):
		self._container: "Properties" = container
		self.name = name
	
	def __getattr__(self, name):
		if name in PropertySpecValue.__slots__:
			return getattr(PropertySpec[self.name], name)
		return super().__getattribute__(name)
	
	@property
	@logException
	def choices(self) -> Mapping[str, str]:
		if self.editorType is not EditorType.CHOICE:
			return None
		container = self._container
		context = container._context
		cache = context.setdefault("propertyChoiceCache", {})
		name = self.name
		if name in cache:
			return cache[name]
		undefined = {
			None: self.displayValueIfUndefined
		} if self.displayValueIfUndefined is not None else {}
		# The `match` statement was added only in Python 3.10
		# Mapping union was added only in Python 3.9
		if name == "autoAction":
			choices = dict(ChainMap(
				context["webModule"].ruleManager.getActions(),
				undefined  # Inserted as first item
			))
		elif name == "mutation":
			choices = dict(ChainMap(
				{
					value: mutationLabels[value]
					for ruleType, values in MUTATIONS_BY_RULE_TYPE.items()
					for value in values
					if ruleType in self.ruleTypes
				},
				undefined  # Inserted as first item
			))
		else:
			raise ValueError(f"prop.name: {name!r}")
		cache[name] = choices
		return choices
	
	@property
	@logException
	def default(self) -> PropertyValue:
		return self._container._map.parents[self.name]
	
	@property
	@logException
	def displayDefault(self) -> str:
		return self.getDisplayValue(self.default)
	
	@property
	@logException
	def displayName(self) -> str:
		return PropertySpec[self.name].getDisplayName(self._container.ruleType)
	
	@property
	@logException
	def displayValue(self) -> str:
		return self.getDisplayValue(self.value)
	
	@property
	@logException
	def displayValueIfUndefined(self) -> str:
		return PropertySpec[self.name].displayValueIfUndefined
	
	@property
	@logException
	def editorType(self) -> EditorType:
		if self.isRestrictedChoice:
			return EditorType.CHOICE
		elif issubclass(self.valueType, bool):
			return EditorType.CHECKBOX
		elif issubclass(self.valueType, str):
			return EditorType.TEXT
		else:
			raise Exception(f"Unable to determine EditorType for property {self.name!r}")
	
	@property
	@logException
	def value(self) -> PropertyValue:
		return getattr(self._container, self.name)
	
	@value.setter
	def value(self, value: PropertyValue) -> None:
		setattr(self._container, self.name, value)
	
	def getDisplayValue(self, value):
		if value in (None, ""):
			return self.displayValueIfUndefined
		if self.isRestrictedChoice:
			return self.choices[value]
		if self.valueType is bool:
			if value:
				# Translators: The displayed value of a yes/no rule property
				return _("Yes")
			else:
				# Translators: The displayed value of a yes/no rule property
				return _("No")
		if self.valueType is str:
			return value
		raise NotImplementedError(f"displayValue for {self.name}={value!r}")
	
	def reset(self) -> None:
		delattr(self._container, self.name)


class Properties(PropertiesBase):

	def __init__(self, context: Mapping[str, Any], *maps: Mapping[str, PropertyValue], iterOnlyFirstMap=False):
		"""iterOnlyFirstMap:
			True: When iterating, include only the properties defined in the first map.
			False: When iterating, include all the properties supported for the rule type.
		"""
		super().__init__(*maps)
		self._context = context
		self._iterOnlyFirstMap = iterOnlyFirstMap
	
	def __getitem__(self, item: int|str) -> Property:
		if isinstance(item, int):
			return tuple(iter(self))[item]
		elif isinstance(item, str):
			return self.getProperty(item)
		else:
			raise ValueError(f"item: {item!r}")
	
	def __iter__(self) -> Iterator[Property]:
		yield from (
			self.getProperty(name)
			for name in self.getSupportedPropertiesName()
			if not self._iterOnlyFirstMap or name in self._map.maps[0].keys()
		)
	
	@logException
	def __len__(self):
		return len(self._map.maps[0] if self._iterOnlyFirstMap else self.getSupportedPropertiesName())
	
	@property
	@logException
	def ruleType(self) -> str:
		try:
			return self._context["data"].get("rule", {}).get("type", None)
		except KeyError as e1:
			# Support getSummary calls from Rules Manager
			try:
				return self._context["rule"].type
			except Exception as e2:
				raise NotImplementedError
	
	def getProperty(self, name: str) -> Property:
		if name not in self.getSupportedPropertiesName():
			raise ValueError(f"Property not supported for rule type {self.ruleType}: {name}")
		return Property(self, name)


class SinglePropertyEditorPanelBase(SingleFieldEditorMixin, ContextualSettingsPanel):
	"""ABC for panels offering a single "Property" edit field.
	
	Known sub-classes:
	 - "PropertiesPanelBase"
	 - "rule.editor.ChildPropertyPanel"
	"""
	
	# Translators: The label for a category in the rule editor
	title: str = _("Properties")
	prop: Property = None
	
	@property
	def editorChoices(self):
		return self.prop.choices
	
	@property
	def editorType(self):
		return self.prop.editorType
	
	@property
	def fieldDisplayName(self):
		return self.prop.displayName
	
	@property
	def fieldName(self):
		return self.prop.name
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.props: Properties = None
	
	def getData(self):
		return super().getData().setdefault("properties", {})
	
	def initData(self, context):
		super().initData(context)
		self.initData_properties()
	
	@abstractmethod
	def initData_properties(self, context):
		"""Initialize `self.props`
		"""
	
	def updateData(self):
		data = self.getData()
		dumped = self.props.dump()
		data.clear()
		data.update(dumped)
	
	def getFieldValue(self):
		return self.prop.value
	
	def setFieldValue(self, value):
		# @@@
		self.prop.value = value
	
	def onSave(self):
		super().onSave()
		if not self.getData():
			del super().getData()["properties"]
	
	def prop_reset(self):
		self.prop.reset()
		self.updateEditor()
		self.onEditor_change(reset=True)
		speech.cancelSpeech()  # Avoid announcing the whole eventual control refresh
		# Translators: Announced when resetting a property to its default value in the editor
		ui.message(_("Reset to {value}").format(value=self.prop.displayValue))


class PropertiesPanelBase(SinglePropertyEditorPanelBase, metaclass=guiHelper.SIPABCMeta):
	"""ABC for panels listing Properties and editing them one at a time.
	
	Sub-classes must implement the `getData` (inherited from `ContextualSettingsPanel`)
	and `initData_properties` methods.
	
	Known sub-classes:
	 - `criteriaEditor.PropertiesPanel`
	 - `rule.editor.PropertiesPanel`
	"""

	# Translators: Displayed when the selected rule type doesn't support any property
	descriptionIfNoneSupported = _("No property available for this rule type.")
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._prop: Property = None
	
	@property
	@logException
	def editor(self) -> wx.Control:
		return {
			EditorType.CHECKBOX: self.editor_checkBox,
			EditorType.CHOICE: self.editor_choice_ctrl,
			EditorType.TEXT: self.editor_text_ctrl,
		}[self.prop.editorType]
	
	@property
	@logException
	def editorLabel(self) -> wx.Control:
		return {
			EditorType.CHECKBOX: self.editor_checkBox,
			EditorType.CHOICE: self.editor_choice_label,
			EditorType.TEXT: self.editor_text_label,
		}[self.prop.editorType]
	
	@property
	@logException
	def prop(self) -> Property:
		return self._prop
	
	@prop.setter
	def prop(self, prop: Property) -> None:
		self._prop = prop
		editorLabel = self.editorLabel
		editor = self.editor
		if prop.editorType is EditorType.CHOICE:
			self.updateEditorChoices()
		self.updateEditor()
		self.updateEditorLabel()
		self.Freeze()
		hideable = self.hideable
		hideIfNot = lambda editorType: f"hideIfNot{editorType.name}"
		show = {hideIfNot(editorType): False for editorType in EditorType}
		show[hideIfNot(prop.editorType)] = True
		for key, showItems in show.items():
			for uiItem in hideable[key]:
				uiItem.Show(showItems)
		self.Thaw()
		self._sendLayoutUpdatedEvent()
	
	def makeSettings(self, settingsSizer):
		scale = self.scale
		hideable = self.hideable = {}
		gbSizer = wx.GridBagSizer()
		gbSizer.EmptyCellSize = (0, 0)
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)

		row = 0
		items = hideable["hideIfSupported"] = []
		item = wx.StaticText(self, label=self.descriptionIfNoneSupported)
		items.append(item)
		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

		row += 1
		items = hideable["hideIfNoneSupported"] = []
		# Translators: The label for a list on the Rule Editor dialog
		item = self.listLabel = wx.StaticText(self, label=_("&Properties"))
		item.Hide()
		items.append(item)
		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

		row += 1
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL), pos=(row, 0))
		items.append(item)

		row += 1
		item = self.listCtrl = ListCtrlAutoWidth(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
		# Translators: A column header on the Rule Editor dialog
		item.InsertColumn(0, pgettext("webAccess.ruleEditor", "Property"))
		# Translators: A column header on the Rule Editor dialog
		item.InsertColumn(1, pgettext("webAccess.ruleEditor", "Value"))
		item.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onListCtrl_itemSelected)
		item.Bind(wx.EVT_CHAR_HOOK, self.onListCtrl_charHook)
		items.append(item)
		gbSizer.Add(item, pos=(row, 0), span=(4, 3), flag=wx.EXPAND)
		gbSizer.AddGrowableRow(row + 3)

		row += 4
		item = gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))
		items.append(item)

		row += 1
		items = hideable["hideIfNotCHECKBOX"] = []
		item = self.editor_checkBox = wx.CheckBox(self, label="")
		item.Bind(wx.EVT_CHECKBOX, self.onEditor_checkBox)
		item.Bind(wx.EVT_CHAR_HOOK, self.onEditor_charHook)
		items.append(item)
		gbSizer.Add(item, pos=(row, 0), span=(1, 3), flag=wx.EXPAND)

		row += 1
		items = hideable["hideIfNotCHOICE"] = []
		item = self.editor_choice_label = wx.StaticText(self, label="")
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		items.append(item)
		item = self.editor_choice_ctrl = wx.Choice(self, choices=[])
		item.Bind(wx.EVT_CHOICE, self.onEditor_choice)
		item.Bind(wx.EVT_CHAR_HOOK, self.onEditor_charHook)
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		row += 1
		items = hideable["hideIfNotTEXT"] = []
		item = self.editor_text_label = wx.StaticText(self, label="")
		items.append(item)
		gbSizer.Add(item, pos=(row, 0))
		item = gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		items.append(item)
		item = self.editor_text_ctrl = wx.TextCtrl(self)
		item.Bind(wx.EVT_TEXT, self.onEditor_text)
		item.Bind(wx.EVT_CHAR_HOOK, self.onEditor_charHook)
		items.append(item)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)

		for item in (
			hideable["hideIfNoneSupported"]
			+ hideable["hideIfNotCHECKBOX"]
			+ hideable["hideIfNotCHOICE"]
			+ hideable["hideIfNotTEXT"]
		):
			item.Show(False)

		gbSizer.AddGrowableCol(2)
		gbSizer.FitInside(self)
		self.gbSizer = gbSizer
	
	def initData(self, context):
		super().initData(context)
		self.listCtrl_update_all()
	
	# called by TreeMultiCategorySettingsDialog.onCatListCtrl_KeyDown
	def delete(self):
		wx.Bell()
	
	def listCtrl_setColumnWidthAutoSize(self):
		listCtrl = self.listCtrl
		autoSize = wx.LIST_AUTOSIZE if self.props else wx.LIST_AUTOSIZE_USEHEADER
		# Exclude the last column as it will fill the whole remaining available width.
		# Still not ideal as we have here no way to ask for max between header and content,
		for i in range(listCtrl.GetColumnCount() - 1):
			listCtrl.SetColumnWidth(i, autoSize)
		self._sendLayoutUpdatedEvent()
	
	def listCtrl_insert(self, index: int, prop: Property) -> None:
		listCtrl = self.listCtrl
		listCtrl.InsertStringItem(index, prop.displayName)
		listCtrl.SetStringItem(index, 1, prop.displayValue)
	
	def listCtrl_update_all(self):
		selectedProp = self.prop
		props = self.props
		listCtrl = self.listCtrl
		listCtrl.DeleteAllItems()
		selectIndex = 0
		for index, prop in enumerate(props):
			self.listCtrl_insert(index, prop)
			if selectedProp and selectedProp.name == prop.name:
				selectIndex = index
		hideable = self.hideable
		if props:
			listCtrl.Select(selectIndex)
			listCtrl.Focus(selectIndex)
		else:
			for editorType in EditorType:
				for item in hideable[f"hideIfNot{editorType.name}"]:
					item.Show(False)
		supported = len(props.getSupportedPropertiesName())
		self.panelDescription = "" if supported else self.descriptionIfNoneSupported
		for item in self.hideable["hideIfNoneSupported"]:
			item.Show(supported)
		for item in self.hideable["hideIfSupported"]:
			item.Show(not supported)
		self.listCtrl_setColumnWidthAutoSize()
	
	def listCtrl_update_value(self):
		listCtrl = self.listCtrl
		index = listCtrl.GetFirstSelected()
		if index == -1:
			raise Exception("wut?")  # FIXME
		prop = self.props[index]
		listCtrl.SetStringItem(index, 1, prop.displayValue)
		self.listCtrl_setColumnWidthAutoSize()
	
	def onEditor_change(self):
		super().onEditor_change()
		self.listCtrl_update_value()
	
	@guarded
	def onEditor_charHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_ESCAPE and not mods:
			self.listCtrl.SetFocus()
			return
		elif keycode == wx.WXK_DELETE and not mods:
			prop = self.prop
			if prop.editorType is not EditorType.TEXT:
				self.prop_reset()
				return
		evt.Skip()
	
	@guarded
	def onListCtrl_charHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_DELETE and not mods:
			prop = self.prop
			if prop:
				self.prop_reset()
			else:
				wx.Bell()
			return
		elif keycode == wx.WXK_F2 and not mods:
			if self.prop:
				self.editor.SetFocus()
			else:
				wx.Bell()
			return
		elif keycode == wx.WXK_SPACE and mods & ~wx.MOD_SHIFT == 0:
			if self.prop:
				self.toggleFieldValue(previous=mods)
			return
		evt.Skip()
	
	@guarded
	def onListCtrl_itemSelected(self, evt):
		index = evt.GetItem().GetId()
		self.listCtrl.Focus(index)
		self.prop = self.props[index]
	
	# called by TreeMultiCategorySettingsDialog.onKeyDown
	def spaceIsPressedOnTreeNode(self, withShift=False):
		# No shift special handling on category panels tree node
		self.listCtrl.SetFocus()