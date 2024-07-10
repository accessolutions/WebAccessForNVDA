# globalPlugins/webAccess/gui/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2021 Accessolutions (http://accessolutions.fr)
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


__version__ = "2021.04.06"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"

from collections import OrderedDict
import re
import wx

from logHandler import log

from gui import guiHelper, nvdaControls, _isDebug
from gui.settingsDialogs import (
	MultiCategorySettingsDialog,
	SettingsDialog,
	SettingsPanel,
	SettingsPanelAccessible,
	EVT_RW_LAYOUT_NEEDED
)
from six import iteritems, text_type
from gui.dpiScalingHelper import DpiScalingHelperMixin

LABEL_ACCEL = re.compile("&(?!&)")
"""
Compiled pattern used to strip accelerator key indicators from labels.
"""


def stripAccel(label):
	"""Strip the eventual accelerator key indication from a field label

	This allows for registering a single literal (hence a single translation)
	for use both as form field label and to compose summary reports.
	"""
	return LABEL_ACCEL.sub("", label)


def stripAccelAndColon(label):
	"""Strip the eventual accelerator key indication from a field label

	This allows for registering a single literal (hence a single translation)
	for use both as form field label and to compose validation messages.
	"""
	return stripAccel(label).rstrip(":").rstrip()


class CustomTreeCtrl(wx.TreeCtrl):
	NODE_INFO_KEY = "data"

	def getTreeNodeInfo(self, nodeId):
		return self.GetItemData(nodeId)[self.NODE_INFO_KEY]

	def setTreeNodeInfo(self, nodeId, treeNodeInfo):
		return self.SetItemData(nodeId, {self.NODE_INFO_KEY: treeNodeInfo})

	def getChildren(self, parent):
		child, cookie = self.GetFirstChild(parent)
		while child.IsOk():
			yield child
			child, cookie = self.GetNextChild(child, cookie)

	def getXChild(self, parent, i):
		for indexChild, child in enumerate(self.getChildren(parent)):
			if indexChild == i:
				return child
		raise IndexError(f'No child existing at this index {i} for parent {parent}')

	def getIndexChild(self, parent, targetChild):
		for indexChild, child in enumerate(self.getChildren(parent)):
			if child == targetChild:
				return indexChild
		raise ValueError(f'This child {targetChild} does not exists in parent {parent}')

	def getSelectionIndex(self):
		childNode = self.GetSelection()
		parentNode = self.GetItemParent(childNode)
		return self.getIndexChild(parentNode, childNode)

	def selectLast(self, parentItem):
		lastChild = self.GetLastChild(parentItem)
		if lastChild.IsOk():
			self.SelectItem(lastChild)
		else:
			self.SelectItem(parentItem)
		self.SetFocus()

	def deleteSelection(self):
		treeItem = self.GetSelection()
		self.Delete(treeItem)

	def updateNodeText(self, nodeId, text):
		self.SetItemText(nodeId, text)

	def addToListCtrl(self, categoryClasses, parent=None):
		for categoryClassInfo in categoryClasses:
			newParent = self.AppendItem(parent if parent else self.RootItem, categoryClassInfo.title)
			categoryClassInfo.updateTreeParams(self, newParent, parent)
			self.setTreeNodeInfo(newParent, categoryClassInfo)
			if categoryClassInfo.children:
				self.addToListCtrl(categoryClassInfo.children, newParent)


class ValidationError(Exception):
	pass


class InvalidValue(object):
	"""Represents an invalid value
	"""

	def __init__(self, raw):
		# The raw value that could not be validated
		self.raw = raw

	def __str__(self):
		# Translator: The placeholder for an invalid value in summary reports
		return _("<Invalid>")


class FillableSettingsPanel(SettingsPanel):
	"""This `SettingsPanel` allows its controls to fill the whole available space.

	See `FillableMultiCategorySettingsDialog`
	"""

	def _buildGui(self):
		# Change to the original implementation: Add `proportion=1`
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.settingsSizer = wx.BoxSizer(wx.VERTICAL)
		self.makeSettings(self.settingsSizer)
		self.mainSizer.Add(self.settingsSizer, flag=wx.ALL | wx.EXPAND, proportion=1)
		self.mainSizer.Fit(self)
		self.SetSizer(self.mainSizer)


class ContextualSettingsPanel(FillableSettingsPanel):

	def __init__(self, *args, **kwargs):
		self.context = None
		super(ContextualSettingsPanel, self).__init__(*args, **kwargs)

	def initData(self, context):
		raise NotImplemented()

	# Set to True if the view depends on data that can be edited on other panels of the same dialog
	initData.onPanelActivated = False

	def onPanelActivated(self):
		if getattr(self.initData, "onPanelActivated", False):
			self.initData(self.context)
		super(ContextualSettingsPanel, self).onPanelActivated()


class PanelAccessible(wx.Accessible):
	"""
	WX Accessible implementation to set the role of a settings panel to property page,
	as well as to set the accessible description based on the panel's description.
	"""

	def GetRole(self, childId):
		return (wx.ACC_OK, wx.ROLE_SYSTEM_PROPERTYPAGE)

	def GetDescription(self, childId):
		return (wx.ACC_OK, self.Window.panelDescription)


class FillableMultiCategorySettingsDialog(MultiCategorySettingsDialog):
	"""This `MultiCategorySettingsDialog` allows its panels to fill the whole available space.

	See `FillableSettingsPanel`
	"""

	def _getCategoryPanel(self, catId):
		# Changes to the original implementation:
		#  - Add `proportion=1`
		#  - Remove `gui._isDebug()` test (introduced with NVDA 2018.2)
		panel = self.catIdToInstanceMap.get(catId, None)
		if not panel:
			try:
				cls = self.categoryClasses[catId]
			except IndexError:
				raise ValueError("Unable to create panel for unknown category ID: {}".format(catId))
			panel = cls(parent=self.container)
			panel.Hide()
			self.containerSizer.Add(
				panel, flag=wx.ALL | wx.EXPAND, proportion=1,
				border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL
			)
			self.catIdToInstanceMap[catId] = panel
			panelWidth = panel.Size[0]
			availableWidth = self.containerSizer.GetSize()[0]
			if panelWidth > availableWidth:  # and gui._isDebug():
				log.debugWarning(
					(
							"Panel width ({1}) too large for: {0} Try to reduce the width of this panel, or increase width of " +
							"MultiCategorySettingsDialog.MIN_SIZE"
					).format(cls, panel.Size[0])
				)
			panel.SetLabel(panel.title)
			panel.SetAccessible(PanelAccessible(panel))

		return panel

	def _enterActivatesOk_ctrlSActivatesApply(self, evt):
		if evt.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			obj = evt.EventObject
			if isinstance(obj, wx.TextCtrl) and obj.IsMultiLine():
				evt.Skip()
				return
		super(FillableMultiCategorySettingsDialog, self)._enterActivatesOk_ctrlSActivatesApply(evt)


def configuredSettingsDialogType(**config):
	class Type(SettingsDialog):
		def __init__(self, *args, **kwargs):
			kwargs.update(config)
			return super(Type, self).__init__(*args, **kwargs)

	return Type


class ContextualMultiCategorySettingsDialog(
	FillableMultiCategorySettingsDialog,
	configuredSettingsDialogType(hasApplyButton=False, multiInstanceAllowed=True)
):

	def __init__(self, *args, **kwargs):
		self.context = None
		super(ContextualMultiCategorySettingsDialog, self).__init__(*args, **kwargs)

	def initData(self, context):
		self.context = context
		panel = self.currentCategory
		if isinstance(panel, ContextualSettingsPanel):
			if not getattr(panel.initData, "onPanelActivated", False):
				panel.initData(context)

	def _getCategoryPanel(self, catId):
		panel = super(ContextualMultiCategorySettingsDialog, self)._getCategoryPanel(catId)
		if (
				hasattr(self, "context")
				and isinstance(panel, ContextualSettingsPanel)
				and (
				getattr(panel, "context", None) is not self.context
				or getattr(panel.initData, "onPanelActivated", False)
		)
		):
			panel.initData(self.context)
		return panel


class TreeMultiCategorySettingsDialog(ContextualMultiCategorySettingsDialog):
	categoryInitList = []
	categoryClasses = []

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# Translators: The label for the list of categories in a multi category settings dialog.
		categoriesLabelText = _("&Categories:")
		categoriesLabel = wx.StaticText(self, label=categoriesLabelText)

		# since the categories list and the container both expand in height, the y
		# portion is essentially a "min" height.
		# These sizes are set manually so that the initial proportions within the dialog look correct. If these sizes are
		# not given, then I believe the proportion arguments (as given to the gridBagSizer.AddGrowableColumn) are used
		# to set their relative sizes. We want the proportion argument to be used for resizing, but not the initial size.
		catListDim = (150, 10)
		catListDim = self.scaleSize(catListDim)

		initialScaledWidth = self.scaleSize(self.INITIAL_SIZE[0])
		spaceForBorderWidth = self.scaleSize(20)
		catListWidth = catListDim[0]
		containerDim = (initialScaledWidth - catListWidth - spaceForBorderWidth, self.scaleSize(10))

		self.catListCtrl = CustomTreeCtrl(
			self,
			size=catListDim,
			style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT
		)
		# This list consists of only one column.
		# The provided column header is just a placeholder, as it is hidden due to the wx.LC_NO_HEADER style flag.
		self.catListCtrl.Bind(wx.EVT_TREE_SEL_CHANGED, self.onCategoryChange)
		self.catListCtrl.Bind(wx.EVT_KEY_DOWN, self.onDelPressed)
		self.catListCtrl.ExpandAll()

		self.container = nvdaControls.TabbableScrolledPanel(
			parent=self,
			style=wx.TAB_TRAVERSAL | wx.BORDER_THEME,
			size=containerDim,
		)

		# Th min size is reset so that they can be reduced to below their "size" constraint.
		self.container.SetMinSize((1, 1))
		self.catListCtrl.SetMinSize((1, 1))

		self.containerSizer = wx.BoxSizer(wx.VERTICAL)
		self.container.SetSizer(self.containerSizer)
		self.root = self.catListCtrl.AddRoot("root")

		# we must focus the initial category in the category list.
		self.setPostInitFocus = self.container.SetFocus if self.initialCategory else self.catListCtrl.SetFocus

		self.gridBagSizer = gridBagSizer = wx.GridBagSizer(
			hgap=guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL,
			vgap=guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL
		)
		# add the label, the categories list, and the settings panel to a 2 by 2 grid.
		# The label should span two columns, so that the start of the categories list
		# and the start of the settings panel are at the same vertical position.
		gridBagSizer.Add(categoriesLabel, pos=(0, 0), span=(1, 2))
		gridBagSizer.Add(self.catListCtrl, pos=(1, 0), flag=wx.EXPAND)
		gridBagSizer.Add(self.container, pos=(1, 1), flag=wx.EXPAND)
		# Make the row with the listCtrl and settings panel grow vertically.
		gridBagSizer.AddGrowableRow(1)
		# Make the columns with the listCtrl and settings panel grow horizontally if the dialog is resized.
		# They should grow 1:3, since the settings panel is much more important, and already wider
		# than the listCtrl.
		gridBagSizer.AddGrowableCol(0, proportion=1)
		gridBagSizer.AddGrowableCol(1, proportion=3)
		sHelper.sizer.Add(gridBagSizer, flag=wx.EXPAND, proportion=1)

		self.container.Layout()

		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.Bind(EVT_RW_LAYOUT_NEEDED, self._onPanelLayoutChanged)

	def initData(self, context):
		super().initData(context)
		self.categoryClasses = self.initCatClasses()
		self.catListCtrl.addToListCtrl(self.categoryClasses)
		self.catListCtrl.SelectItem(self.catListCtrl.GetFirstChild(self.root)[0])
		self.catListCtrl.ExpandAll()

	def getFirstChild(self):
		return self.categoryClasses[0]

	def initCatClasses(self):
		categoryClasses = []
		for categoryClass, childrenGetterName in self.categoryInitList:
			childrenGetter = getattr(self, childrenGetterName)
			categoryClasses.append(
				TreeNodeInfo(categoryClass, childrenGetter=childrenGetter, title=categoryClass.title))
		return categoryClasses

	def focus_first_field(self, evt):
		# if evt.GetKeyCode() == wx.WXK_CONTROL_A:
		page = self.tree.GetPage(self.tree.GetSelection())
		children = page.GetChildren()
		for child in children:
			if child.__class__.__name__ in ['ComboBox', 'TextCtrl', 'Button']:
				child.SetFocus()

	def _changeCategoryPanel(self, newCatInfos):
		configuredSettingsDialogType()
		panel = self.catIdToInstanceMap.get(newCatInfos.title, None)
		if panel:
			panel.initData(self.context, **newCatInfos.categoryParams)
			return panel
		panel = newCatInfos.categoryClass(parent=self.container)
		panel.Hide()
		self.containerSizer.Add(
			panel, flag=wx.ALL | wx.EXPAND,
			border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL
		)
		self.catIdToInstanceMap[newCatInfos.title] = panel
		panelWidth = panel.Size[0]
		availableWidth = self.containerSizer.GetSize()[0]
		if panelWidth > availableWidth : # and _isDebug():
			log.debugWarning(
				(
						"Panel width ({1}) too large for: {0} Try to reduce the width of this panel, or increase width of " +
						"MultiCategorySettingsDialog.MIN_SIZE"
				).format(newCatInfos.categoryClass, panel.Size[0])
			)
		panel.initData(self.context, **newCatInfos.categoryParams)
		panel.SetLabel(panel.title.replace('&', ""))
		panel.SetAccessible(SettingsPanelAccessible(panel))
		return panel

	def _doCategoryChange(self, newCatInfos):
		oldCat = self.currentCategory

		# Freeze and Thaw are called to stop visual artifact's while the GUI
		# is being rebuilt. Without this, the controls can sometimes be seen being
		# added.
		self.container.Freeze()
		if oldCat:
			oldCat.onPanelDeactivated()
		try:
			newPanel = self._changeCategoryPanel(newCatInfos)
		except ValueError as e:
			log.error("Unable to change to category: {}".format(newCatInfos.title), exc_info=e)
			return
		self.currentCategory = newPanel

		newPanel.onPanelActivated()
		# call Layout and SetupScrolling on the container to make sure that the controls apear in their expected locations.
		self.container.Layout()
		self.container.SetupScrolling()
		self.container.Thaw()

	def onCategoryChange(self, evt):
		currentCat = self.currentCategory
		try:
			newCatInfos = self.catListCtrl.getTreeNodeInfo(evt.GetItem())
		except RuntimeError as e:
			evt.Skip() # handling the case when the tree is called after panel deletion
			return
		if not currentCat or newCatInfos != currentCat:
			self._doCategoryChange(newCatInfos)
		else:
			evt.Skip()

	def onDelPressed(self, evt):
		if evt.GetKeyCode() == wx.WXK_DELETE:
			selectedItem = self.catListCtrl.GetSelection()
			if not self.catListCtrl.ItemHasChildren(selectedItem):
				self.currentCategory.delete()
				return
		elif evt.GetKeyCode() == wx.WXK_SPACE:
			self.currentCategory.spaceIsPressedOnTreeNode()

		evt.Skip()
		evt.StopPropagation()

	def refreshNodePanelData(self, node):
		nodeInfo = self.catListCtrl.getTreeNodeInfo(node)
		panel = self.catIdToInstanceMap.get(nodeInfo.title, None)
		if panel:
			nodeInfo.updateTreeParams(self.catListCtrl, node)
			panel.initData(self.context, **nodeInfo.categoryParams)



class TreeNodeInfo:
	def __init__(self, categoryClass, title=None, childrenGetter=None, categoryParams=None):
		self.categoryClass = categoryClass
		self.title = title
		if not childrenGetter:
			childrenGetter = lambda: []
		self.childrenGetter = childrenGetter
		self.categoryParams = categoryParams if categoryParams else {}
		# self.categoryParams = categoryParams
		self._children = []

	@property
	def children(self):
		return self.childrenGetter()

	@children.setter
	def children(self, children):
		self._children = children

	@children.deleter
	def children(self):
		self._children = []

	def __repr__(self):
		return self.__str__()

	def __str__(self):
		return f"{self.title} : {self.children}"

	def updateTreeParams(self, tree, treeNode, treeParent=None):
		if not treeParent:
			treeParent = tree.GetItemParent(treeNode)
		self.categoryParams.update(tree=tree, treeNode=treeNode, treeParent=treeParent)


def showContextualDialog(cls, context, parent, *args, **kwargs):
	if parent is not None:
		with cls(parent, *args, **kwargs) as dlg:
			dlg.initData(context)
			return dlg.ShowModal()
	import gui
	gui.mainFrame.prePopup()
	try:
		dlg = cls(gui.mainFrame, *args, **kwargs)
		dlg.initData(context)
		dlg.Show()
	finally:
		gui.mainFrame.postPopup()


class HideableChoice():
	__slots__ = ("key", "label", "enabled")

	def __init__(self, key, label, enabled=True):
		self.key = key
		self.label = label
		self.enabled = enabled


class DropDownWithHideableChoices(wx.ComboBox):

	def __init__(self, *args, **kwargs):
		style = kwargs.get("style", 0)
		style |= wx.CB_READONLY
		kwargs["style"] = style
		super(DropDownWithHideableChoices, self).__init__(*args, **kwargs)
		self.__choicesWholeMap = OrderedDict()
		self.__choicesFilteredList = []

	def Clear(self):
		self.__choicesWholeMap.clear()
		self.__choicesFilteredList[:] = []
		return super(DropDownWithHideableChoices, self).Clear()

	def setChoices(self, keyLabelPairs):
		self.__choicesWholeMap.clear()
		self.__choicesWholeMap.update({key: HideableChoice(key, label) for key, label in keyLabelPairs})
		self.__refresh()

	def getChoicesKeys(self):
		return list(self.__choicesWholeMap.keys())

	def getSelectedChoiceKey(self):
		choice = self.__getSelectedChoice()
		return choice and choice.key

	def setSelectedChoiceKey(self, key, default=None):
		choice = self.__getChoice(key)
		if choice.enabled:
			self.__setSelectedChoice(choice)
		elif default is not None:
			self.setSelectedChoiceKey(key=default, default=None)

	def setChoiceEnabled(self, key, enabled, default=None):
		choice = self.__getChoice(key)
		choice.enabled = enabled
		self.__refresh(default)

	def setChoicesEnabled(self, keys, enabled, default=None):
		for key in keys:
			self.setChoiceEnabled(key, enabled, default=default)

	def setAllChoicesEnabled(self, enabled, default=None):
		for key in self.getChoicesKeys():
			self.setChoiceEnabled(key, enabled, default=default)

	def __getChoice(self, key):
		return self.__choicesWholeMap[key]

	def __getSelectedChoice(self):
		index = self.Selection
		if index < 0:
			return None
		return self.__choicesFilteredList[index]

	def __setSelectedChoice(self, choice):
		if choice:
			self.Selection = self.__choicesFilteredList.index(choice)
		else:
			self.Selection = -1

	def __refresh(self, default=None):
		choice = self.__getSelectedChoice()
		whole = self.__choicesWholeMap
		filtered = self.__choicesFilteredList
		filtered[:] = [c for c in list(whole.values()) if c.enabled]
		self.Set([c.label for c in filtered])
		if choice is not None:
			if choice.enabled:
				self.__setSelectedChoice(choice)
			else:
				self.setSelectedChoiceKey(default)
