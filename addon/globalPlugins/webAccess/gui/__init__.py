# globalPlugins/webAccess/gui/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (https://accessolutions.fr)
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


__authors__ = (
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


from abc import abstractmethod
from buildVersion import version_detailed as NVDA_VERSION
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum, auto
import re
import sys
from typing import Any, Callable
import wx
import wx.lib.mixins.listctrl as listmix

import gui
from gui import guiHelper, nvdaControls
from gui.dpiScalingHelper import DpiScalingHelperMixinWithoutInit
from gui.settingsDialogs import (
	MultiCategorySettingsDialog,
	SettingsDialog,
	SettingsPanel,
	SettingsPanelAccessible,
	EVT_RW_LAYOUT_NEEDED
)
from logHandler import log
import addonHandler
import speech
import ui
import winUser

from ..utils import guarded, logException, notifyError, updateOrDrop


if sys.version_info[1] < 9:
    from typing import Mapping, Sequence, Set
else:
    from collections.abc import Mapping, Sequence, Set


addonHandler.initTranslation()

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


def stripAngleBrackets(value):
	"""Strip the eventual angle-brackets surrounding a display value
	
	This is used to convert some display values to spoken text.
	"""
	if value.startswith("<") and value.endswith(">"):
		return value.lstrip("<").rstrip(">")
	return value


class CustomTreeCtrl(wx.TreeCtrl):
	NODE_INFO_KEY = "data"

	def getTreeNodeInfo(self, nodeId):
		return self.GetItemData(nodeId)[self.NODE_INFO_KEY]

	def setTreeNodeInfo(self, nodeId, treeNodeInfo):
		return self.SetItemData(nodeId, {self.NODE_INFO_KEY: treeNodeInfo})

	def getChildren(self, parent):
		return tuple(self.iterChildren(parent))

	def iterChildren(self, parent):
		child, cookie = self.GetFirstChild(parent)
		while child.IsOk():
			yield child
			child, cookie = self.GetNextChild(child, cookie)

	def getXChild(self, parent, i):
		for indexChild, child in enumerate(self.iterChildren(parent)):
			if indexChild == i:
				return child
		raise IndexError(f'No child existing at this index {i} for parent {parent}')

	def getIndexChild(self, parent, targetChild):
		for indexChild, child in enumerate(self.iterChildren(parent)):
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


class ListCtrlAccessible(wx.Accessible):
	"""`wx.Accessible` implementation advertising when a `wx.ListCtrl` is empty.
	
	The associated control may customize the message through its `descriptionIfEmpty` attribute.
	"""
	
	Window: wx.ListCtrl
	
	@logException
	def GetDescription(self, childId):
		if childId == winUser.CHILDID_SELF:
			if self.Window.GetItemCount() == 0:
				# Translators: Announced when a list is empty
				desc = getattr(self.Window, "descriptionIfEmpty", _("Empty"))
				return (wx.ACC_OK, desc)
		return super().GetDescription(childId)


class ListCtrlAutoWidth(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
	"""A `wx.ListCtrl` that expands by default its last column to the whole available width.
	
	Call `setResizeColumn` to auto resize another column instead.
	"""
	
	LIST_AUTORESIZE = -3
	
	def __init__(self, *args, **kwargs):
		wx.ListCtrl.__init__(self, *args, **kwargs)
		listmix.ListCtrlAutoWidthMixin.__init__(self)
		self.SetAccessible(ListCtrlAccessible(self))


class SizeFrugalComboBox(wx.ComboBox):
	"""A ComboBox that does not request for more size to acomodate its content.
	
	Used to avoid uselessly increase the virtual size of scrollable panels.
	"""
	
	def DoGetBestSize(self):
		return wx.Size(0, 0)


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


class ScalingMixin(DpiScalingHelperMixinWithoutInit):
	
	def scale(self, *args):
		sizes = tuple((
			self.scaleSize(arg) if arg > 0 else arg
			for arg in args
		))
		if len(sizes) == 2:
			return sizes
		elif len(sizes) == 1:
			return sizes[0]
		else:
			raise ValueError(args)


class FillableSettingsPanel(SettingsPanel, ScalingMixin):
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


# TODO: Consider migrating to NVDA's SettingsDialog once we hit 2023.2 as minimum version 
class ContextualDialog(ScalingMixin, wx.Dialog):
	
	def initData(self, context):
		self.context = context


class ContextualSettingsPanel(FillableSettingsPanel, metaclass=guiHelper.SIPABCMeta):
	"""ABC for the different editor panels.
	
	Sub-classes must override:
	 - `getData`, retrieving the data map targeted by this panel from the context,
	 ie. a sub-map within `context["data"]`.
	 - `initData`, initializing the panel with the data found in the context.
	 - `updateData`, consolidating the panel content back into the data map.
	"""
	
	def __init__(self, *args, **kwargs):
		self.context = None
		super().__init__(*args, **kwargs)
	
	@abstractmethod
	def getData(self):
		"""Retrieve the data map targetted by this panel.
		"""
		raise NotImplementedError
	
	@abstractmethod
	def initData(self, context: Mapping[str, Any]) -> None:
		"""Initialize this panel with the data found in the context.
		"""
		self.context = context
	
	# Set to True if the view depends on data that can be edited on other panels of the same dialog
	initData.onPanelActivated = False
	
	@abstractmethod
	def updateData(self):
		"""Consolidate the data from this panel into the data map.
		"""
	
	def onPanelActivated(self):
		if getattr(self.initData, "onPanelActivated", False):
			self.initData(self.context)
		super().onPanelActivated()
	
	def onPanelDeactivated(self):
		self.updateData()
		super().onPanelDeactivated()
	
	def onSave(self):
		self.updateData()


class FillableMultiCategorySettingsDialog(MultiCategorySettingsDialog, ScalingMixin):
	"""This `MultiCategorySettingsDialog` allows its panels to fill the whole available space.

	See `FillableSettingsPanel`
	"""
	
	onCategoryChange = guarded(MultiCategorySettingsDialog.onCategoryChange)
	
	def _getCategoryPanel(self, catId):
		# Changes to the original implementation:
		#  - Add `proportion=1`
		#  - Remove `gui._isDebug()` test (introduced with NVDA 2018.2)
		#  - Add scaling
		scale = self.scale
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
				border=scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL)
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
			panel.SetAccessible(SettingsPanelAccessible(panel))

		return panel
	
	@guarded
	def _enterActivatesOk_ctrlSActivatesApply(self, evt):
		if evt.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			obj = evt.EventObject
			if isinstance(obj, wx.TextCtrl) and obj.IsMultiLine():
				evt.Skip()
				return
		super()._enterActivatesOk_ctrlSActivatesApply(evt)


def configuredSettingsDialogType(hasApplyButton: bool) -> type(SettingsDialog):
	"""Allow to disable the apply button on subclasses of NVDA's `MultiCategorySettingsDialog`
	
	`MultiCategorySettingsDialog` forcibly initializes its base `SettingsDialog` with an apply button.
	Adding the type returned by this function to the bases of a subclass of `MultiCategorySettingsDialog`
	allows to change this behavior.
	"""
	
	class Type(SettingsDialog):
		
		def __init__(self, *args, **kwargs):
			if NVDA_VERSION < "2023.2":
				kwargs["hasApplyButton"] = hasApplyButton
			else:
				buttons: Set[int] = kwargs.get("buttons", {wx.OK, wx.CANCEL})
				if not hasApplyButton:
					buttons -= {wx.APPLY}
			super().__init__(*args, **kwargs)
	
	return Type


class KbNavMultiCategorySettingsDialog(FillableMultiCategorySettingsDialog):
	
	# Bound during MultiCategorySettingsDialog.makeSettings	
	@guarded
	def onCharHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_F6 and mods == wx.MOD_NONE:
			if self.catListCtrl.HasFocus():
				self.container.SetFocus()
			else:
				self.catListCtrl.SetFocus()
			return
		elif keycode == wx.WXK_HOME and mods == wx.MOD_ALT:
			try:
				self.focusContainerControl(0)
			except IndexError:
				wx.Bell()
		elif keycode == wx.WXK_END and mods == wx.MOD_ALT:
			try:
				self.focusContainerControl(-1)
			except IndexError:
				wx.Bell()
			return
		elif keycode == wx.WXK_RETURN and mods == wx.MOD_CONTROL:
			self.ProcessEvent(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK))
			return
		super().onCharHook(evt)  # Handles control(+shift)+tab
	
	def focusContainerControl(self, index: int):
		[
			child for child in self.currentCategory.GetChildren()
			if isinstance(child, wx.Control) and child.CanAcceptFocusFromKeyboard()
		][index].SetFocus()


class ContextualMultiCategorySettingsDialog(
	KbNavMultiCategorySettingsDialog,
	configuredSettingsDialogType(hasApplyButton=False),
	ContextualDialog,
):

	def __new__(cls, *args, **kwargs):
		kwargs["multiInstanceAllowed"] = True
		return super().__new__(cls, *args, **kwargs)

	def __init__(self, *args, **kwargs):
		self.context = None
		super().__init__(*args, **kwargs)

	def initData(self, context: Mapping[str, Any]) -> None:
		self.context = context
		panel = self.currentCategory
		if isinstance(panel, ContextualSettingsPanel):
			if not getattr(panel.initData, "onPanelActivated", False):
				panel.initData(context)
	
	# Changed from NVDA's MultiCategorySettingsDialog: Use ValidationError instead of ValueError,
	# in order to not misinterpret a real unintentional ValueError.
	@guarded
	def onOk(self, evt):
		try:
			self._doSave()
		except ValidationError:
			# ContextualSettingsPanel.isValid is expected to have properly notified the user about
			# the reason why the panel data is not valid.
			evt.StopPropagation()
		except Exception:
			notifyError()
		else:
			self.DestroyLater()
			self.SetReturnCode(wx.ID_OK)
	
	def selectPanel(self, panel: ContextualSettingsPanel):
		index = self.categoryClasses.index(type(panel))
		self.catListCtrl.Select(index)
		self.catListCtrl.Focus(index)
	
	def _getCategoryPanel(self, catId):
		panel = super()._getCategoryPanel(catId)
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
	
	# Changed from NVDA's MultiCategorySettingsDialog: Use ValidationError instead of ValueError,
	# in order to not misinterpret a real unintentional ValueError.
	# Additionnaly, this implementation selects the category for the invalid panel.
	def _validateAllPanels(self):
		"""Check if all panels are valid, and can be saved
		@note: raises ValidationError if a panel is not valid. See c{SettingsPanel.isValid}
		"""
		for panel in self.catIdToInstanceMap.values():
			if not panel.isValid():
				self.selectPanel(panel)
				raise ValidationError("Validation for %s blocked saving settings" % panel.__class__.__name__)


class TreeContextualPanel(ContextualSettingsPanel):

	CATEGORY_PARAMS_CONTEXT_KEY = "TreeContextualPanel.categoryParams"

	@dataclass
	class CategoryParams:
		tree: CustomTreeCtrl = None
		treeNode: wx.TreeItemId = None
		treeParent: wx.TreeItemId = None

	def __init__(self, parent):
		super().__init__(parent)
		self.categoryParams = None

	def initData(self, context: Mapping[str, Any]) -> None:
		self.categoryParams = context.pop(self.CATEGORY_PARAMS_CONTEXT_KEY, None)
		super().initData(context)

	def refreshParent(self, parentNodeId, deleteChildren=True):
		"""Refresh tree children of a parent item
		Deletes all the childs of a branch and recreates them. To use when items are add or deletes.
		"""
		self.Parent.Parent.refreshNodePanelData(parentNodeId)
		if deleteChildren:
			self.hardRefreshChildren(parentNodeId)
		else:
			self.softRefreshChildren(parentNodeId)

	def hardRefreshChildren(self, parentNodeId):
		prm = self.categoryParams
		parentTreeNodeInfo = prm.tree.getTreeNodeInfo(parentNodeId)
		prm.tree.DeleteChildren(parentNodeId)
		if parentTreeNodeInfo.children:
			prm.tree.addToListCtrl(parentTreeNodeInfo.children, parentNodeId)
			prm.tree.Expand(parentNodeId)

	def softRefreshChildren(self, parentNodeId):
		prm = self.categoryParams
		parentTreeNodeInfo = prm.tree.getTreeNodeInfo(parentNodeId)
		parent = self.Parent.Parent
		newChildren = parentTreeNodeInfo.children
		for i, oldItem in enumerate(prm.tree.iterChildren(parentNodeId)):
			newChildInfo = newChildren[i]
			newChildInfo.updateTreeParams(prm.tree, oldItem, parentNodeId)
			prm.tree.SetItemText(oldItem, newChildInfo.title)
			prm.tree.setTreeNodeInfo(oldItem, newChildInfo)
			parent.refreshNodePanelData(oldItem)


class TreeMultiCategorySettingsDialog(ContextualMultiCategorySettingsDialog):

	categoryInitList: Sequence[tuple[type(TreeContextualPanel), str]] = None
	categoryClasses: Sequence[type(TreeContextualPanel)] = None

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

		self.container = nvdaControls.TabbableScrolledPanel(
			parent = self,
			style = wx.TAB_TRAVERSAL | wx.BORDER_THEME,
			size=containerDim
		)

		# Th min size is reset so that they can be reduced to below their "size" constraint.
		self.container.SetMinSize((1,1))
		self.catListCtrl.SetMinSize((1,1))

		self.containerSizer = wx.BoxSizer(wx.VERTICAL)
		self.container.SetSizer(self.containerSizer)
		self.root = self.catListCtrl.AddRoot("root")

		# we must focus the initial category in the category list.
		self.setPostInitFocus = self.container.SetFocus if self.initialCategory else self.catListCtrl.SetFocus

		self.gridBagSizer = gridBagSizer = wx.GridBagSizer(
			hgap=self.scaleSize(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL),
			vgap=self.scaleSize(guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL)
		)
		# add the label, the categories list, and the settings panel to a 2 by 2 grid.
		# The label should span two columns, so that the start of the categories list
		# and the start of the settings panel are at the same vertical position.
		gridBagSizer.Add(categoriesLabel, pos=(0,0), span=(1,2))
		gridBagSizer.Add(self.catListCtrl, pos=(1,0), flag=wx.EXPAND)
		gridBagSizer.Add(self.container, pos=(1,1), flag=wx.EXPAND)
		# Make the row with the listCtrl and settings panel grow vertically.
		gridBagSizer.AddGrowableRow(1)
		# Make the columns with the listCtrl and settings panel grow horizontally if the dialog is resized.
		# They should grow 1:3, since the settings panel is much more important, and already wider
		# than the listCtrl.
		gridBagSizer.AddGrowableCol(0, proportion=1)
		gridBagSizer.AddGrowableCol(1, proportion=3)
		sHelper.sizer.Add(gridBagSizer, flag=wx.EXPAND, proportion=1)

		self.container.Layout()
		self.catListCtrl.Bind(wx.EVT_TREE_SEL_CHANGED, self.onCategoryChange)
		self.catListCtrl.Bind(wx.EVT_KEY_DOWN, self.onCatListCtrl_keyDown)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.Bind(EVT_RW_LAYOUT_NEEDED, self._onPanelLayoutChanged)

	def initData(self, context: Mapping[str, Any]) -> None:
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

	def _changeCategoryPanel(self, newCatInfos):
		panel = self.catIdToInstanceMap.get(newCatInfos.title, None)
		if panel:
			self.context[panel.CATEGORY_PARAMS_CONTEXT_KEY] = newCatInfos.categoryParams
			panel.initData(self.context)
			return panel
		panel = newCatInfos.categoryClass(parent=self.container)
		panel.Hide()
		self.containerSizer.Add(
			panel, flag=wx.ALL | wx.EXPAND, proportion=1,
			border=self.scaleSize(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL)
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
		self.context[panel.CATEGORY_PARAMS_CONTEXT_KEY] = newCatInfos.categoryParams
		panel.initData(self.context)
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

	def cycleThroughCategories(self, previous=False):
		tree = self.catListCtrl
		selected = tree.GetSelection()
		parent = tree.GetItemParent(selected)
		children = tree.getChildren(parent)
		index = children.index(selected)
		index += -1 if previous else 1
		index %= len(children)
		child = children[index]
		treeHadFocus = tree.HasFocus()
		tree.SelectItem(child)
		catInfos = tree.getTreeNodeInfo(child)
		self._doCategoryChange(catInfos)
		if not treeHadFocus:
			self.currentCategory.SetFocus()

	@guarded
	def onCategoryChange(self, evt):
		try:
			newCatInfos = self.catListCtrl.getTreeNodeInfo(evt.GetItem())
		except RuntimeError as e:
			evt.Skip() # handling the case when the tree is called after panel deletion
			return
		self._doCategoryChange(newCatInfos)

	@guarded
	def onCatListCtrl_keyDown(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_DELETE and mods == wx.MOD_NONE:
			selectedItem = self.catListCtrl.GetSelection()
			if not self.catListCtrl.ItemHasChildren(selectedItem):
				self.currentCategory.delete()
				return
			else:
				wx.Bell()
		elif keycode == wx.WXK_SPACE and mods in (wx.MOD_NONE, wx.MOD_SHIFT):
			self.currentCategory.spaceIsPressedOnTreeNode(
				withShift=mods == wx.MOD_SHIFT
			)
			return

		evt.Skip()

	# overrides MultiCategorySettingsDialog
	@guarded
	def onCharHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_TAB and mods & ~wx.MOD_SHIFT == wx.MOD_CONTROL:
			self.cycleThroughCategories(previous=mods & wx.MOD_SHIFT)
			return
		super().onCharHook(evt)  # Handles F6

	def refreshNodePanelData(self, node):
		nodeInfo = self.catListCtrl.getTreeNodeInfo(node)
		panel = self.catIdToInstanceMap.get(nodeInfo.title, None)
		if panel:
			nodeInfo.updateTreeParams(self.catListCtrl, node)
			self.context[panel.CATEGORY_PARAMS_CONTEXT_KEY] = nodeInfo.categoryParams
			panel.initData(self.context)

	def selectPanel(self, panel: TreeContextualPanel):
		if panel is self.currentCategory:
			return
		categoryClass = type(panel)
		categoryParams = getattr(panel, "categoryParams")
		tree: CustomTreeCtrl = self.catListCtrl
		for child in tree.iterChildren(self.root):
			childInfo = tree.getTreeNodeInfo(child)
			if (
				childInfo.categoryClass is not categoryClass
				or childInfo.categoryParams != categoryParams
			):
				continue
			tree.SelectItem(child)
			self._doCategoryChange(childInfo)
			self.currentCategory.SetFocus()
			return
		raise LookupError(f"{categoryClass}, {categoryParams}")


class TreeNodeInfo:

	def __init__(self, categoryClass, title=None, childrenGetter=None, categoryParams=None):
		self.categoryClass = categoryClass
		self.title = title
		if not childrenGetter:
			childrenGetter = lambda: []
		self.childrenGetter = childrenGetter
		if categoryParams is not None:
			self.categoryParams = categoryParams
		else:
			self.categoryParams = TreeContextualPanel.CategoryParams()
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
		return f"{self.title}: {self.children}"

	def updateTreeParams(self, tree, treeNode, treeParent=None):
		if not treeParent:
			treeParent = tree.GetItemParent(treeNode)
		prm = self.categoryParams
		prm.tree = tree
		prm.treeNode = treeNode
		prm.treeParent = treeParent


def showContextualDialog(
	cls: type(ContextualDialog),
	context: Mapping[str, Any],
	parent: wx.Window,
	*args,
	**kwargs
):
	"""
	Show a `ContextualDialog`
	
	If a `parent` is specified, the dialog is shown modal and this function
	returns its return code.
	"""
	if parent is not None:
		with cls(parent, *args, **kwargs) as dlg:
			dlg.initData(context)
			return dlg.ShowModal()
	gui.mainFrame.prePopup()
	try:
		dlg = cls(gui.mainFrame, *args, **kwargs)
		dlg.initData(context)
		dlg.Show()
	finally:
		gui.mainFrame.postPopup()


class HideableChoice:
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
		super().__init__(*args, **kwargs)
		self.__choicesWholeMap = OrderedDict()
		self.__choicesFilteredList = []

	def Clear(self):
		self.__choicesWholeMap.clear()
		self.__choicesFilteredList[:] = []
		return super().Clear()

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


@dataclass
class EditorTypeValue:
	editorClass: type(wx.Control) = None
	eventType: int = None
	eventHandlerAttrName: str = None
	isLabeled: bool = None


class Change(Enum):
	CREATION = auto()
	UPDATE = auto()
	DELETION = auto()


class EditorType(Enum):
	CHECKBOX = EditorTypeValue(wx.CheckBox, wx.EVT_CHECKBOX, "onEditor_checkBox", True)
	CHOICE = EditorTypeValue(wx.Choice, wx.EVT_CHOICE, "onEditor_choice", False)
	TEXT = EditorTypeValue(wx.TextCtrl, wx.EVT_TEXT, "onEditor_text", False)


class SingleFieldEditorMixin(metaclass=guiHelper.SIPABCMeta):
	"""Abstract mixin for handling single field edition
	
	Sub-classes are expected to bind `wx.EVT_CHECKBOX`, `wx.EVT_CHOICE` and `wx.EVT_TEXT`
	to `onEditor_checkBox`, `onEditor_choice` and `onEditor_text` respectively.
	
	Known sub-classes:
	 - `SingleFieldEditorPanelBase`
	 - `properties.PropertiesListBase`
	"""
	
	@classmethod
	def getFieldDisplayValue(cls, value: Any, choices: Mapping[Any, str] = None) -> str:
		if choices is not None:
			try:
				index = tuple(choices.keys()).index(value)
			except ValueError:
				raise ValueError(f"Can't find index: {value!r} not in {choices!r}")
			return tuple(choices.values())[index]
		elif isinstance(value, bool):
			if value:
				# Translators: The display value of a yes/no field
				return _("Yes")
			else:
				# Translators: The displayed value of a yes/no field
				return _("No")
		return str(value)
	
	@property
	@abstractmethod
	def editor(self) -> wx.Control:
		raise NotImplementedError
	
	@property
	@abstractmethod
	def editorChoices(self) -> Mapping[Any, str]:
		raise NotImplementedError
	
	@property
	@abstractmethod
	def editorLabel(self) -> wx.Control:
		raise NotImplementedError
	
	@property
	@abstractmethod
	def editorType(self) -> EditorType:
		raise NotImplementedError
	
	@property
	@abstractmethod
	def fieldDisplayName(self) -> str:
		raise NotImplementedError
	
	@abstractmethod
	def getFieldValue(self):
		raise NotImplementedError
	
	@abstractmethod
	def setFieldValue(self, value):
		raise NotImplementedError
	
	def onEditor_change(self):
		"""Called whenever the value changed.
		"""
	
	@guarded
	def onEditor_checkBox(self, evt):
		self.setFieldValue(evt.IsChecked())
		self.onEditor_change()
	
	@guarded
	def onEditor_choice(self, evt):
		index = evt.Selection
		self.setFieldValue(tuple(self.editorChoices.keys())[index])
		self.onEditor_change()
	
	@guarded
	def onEditor_text(self, evt):
		self.setFieldValue(evt.EventObject.Value)
		self.onEditor_change()
	
	def toggleFieldValue(self, previous: bool = False) -> None:
		value = self.getFieldValue()
		editorType = self.editorType
		if editorType is EditorType.CHECKBOX:
			value = not value
		elif editorType is EditorType.CHOICE:
			choices = self.editorChoices
			keys = tuple(choices.keys())
			try:
				index = (keys.index(value) + (-1 if previous else 1)) % len(choices)  # Wrap arround
			except ValueError:
				notifyError(f"value: {value!r}, choices: {choices!r}")
				return
			value = keys[index]
		elif editorType is EditorType.TEXT:
			self.editor.SetFocus()
			return
		else:
			raise NotImplementedError(editorType)
		self.setFieldValue(value)
		self.updateEditor()
		self.onEditor_change()
		
		def report():
			speech.cancelSpeech()  # Avoid announcing the whole eventual control refresh
			ui.message(self.getFieldDisplayValue(value, choices=self.editorChoices))
		
		# Should be triggered right after the tree node update
		wx.CallLater(5, report)
	
	def updateEditor(self) -> None:
		editor = self.editor
		value = self.getFieldValue()
		editorType = self.editorType
		if editorType is EditorType.CHECKBOX:
			# Does not emit wx.EVT_CHECKBOX
			editor.Value = value
		elif editorType is EditorType.CHOICE:
			# Does not emit wx.EVT_CHOICE
			editor.Selection = tuple(self.editorChoices.keys()).index(value)
		elif editorType is EditorType.TEXT:
			# Does not emit wx.EVT_TEXT
			editor.ChangeValue(value if value is not None else "")
	
	def updateEditorChoices(self):
		editor = self.editor
		editor.Clear()
		editor.AppendItems(tuple(self.editorChoices.values()))
	
	def updateEditorLabel(self):
		# Translators: A field label. French typically adds a space before the colon.
		self.editorLabel.Label = _("{field}:").format(field=self.fieldDisplayName)


class SingleFieldEditorPanelBase(SingleFieldEditorMixin, TreeContextualPanel):
	"""ABC for panels offering a single edit field.
	
	Sub-classes must implement `getData`, inherited from `ContextualSettingsPanel`.
	
	Known sub-classes:
	 - `rule.editor.RuleEditorSingleFieldChildPanel`
	"""
	
	# Overrides the abstract properties getter from SingleFieldEditorMixin,
	# thus allowing to use these names for instance attribute.
	editor: wx.Control = None
	editorLabel: wx.Control = None
	editorType: EditorType = None
	
	@dataclass
	class CategoryParams(TreeContextualPanel.CategoryParams):
		editorChoices: Mapping[Any, str] = None
		fieldDisplayName: str = None
		fieldName: str = None
		# Type hint "Self" was added only in Python 3.11 (NVDA >= 2024.1)
		onEditor_change: Callable[["SingleFieldEditorPanelBase"], None] = None
		"""Additional `onEditor_change` handler callback.
		
		It is called with a reference to the panel during `onEditor_change`, thus avoiding the need
		to sub-class only for extending this method.
		"""
	
	@classmethod
	def getTreeNodeLabel(cls, displayName: str, value: Any, choices: Mapping[Any, str] = None) -> str:
		displayName = stripAccel(displayName).strip().rstrip(":").rstrip()
		displayValue = cls.getFieldDisplayValue(value, choices=choices)
		# Translators: The label for a node in the category tree on a multi-category dialog
		return _("{field}: {value}").format(field=displayName, value=displayValue)
	
	def __init__(self, *args, editorType: EditorType = None, **kwargs):
		if editorType is not None:  # Allow mixing with classes where this is a readonly property
			self.editorType = editorType
		super().__init__(*args, **kwargs)
	
	@property
	def editorChoices(self) -> str:
		return self.categoryParams.editorChoices
	
	@property
	def fieldDisplayName(self) -> str:
		return self.categoryParams.fieldDisplayName
	
	@property
	def fieldName(self) -> str:
		return self.categoryParams.fieldName
	
	def makeSettings(self, settingsSizer):
		scale = self.scale
		typeParams = self.editorType.value
		gbSizer = wx.GridBagSizer()
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		col = 0
		if not typeParams.isLabeled:
			item = self.editorLabel = wx.StaticText(self, label='')
			gbSizer.Add(item, pos=(0, col))
			col += 1
			gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(0, col))
			col += 1
		item = self.editor = typeParams.editorClass(self)
		gbSizer.Add(item, pos=(0, col), flag=wx.EXPAND)
		item.Bind(typeParams.eventType, getattr(self, typeParams.eventHandlerAttrName))
		gbSizer.AddGrowableCol(col)
	
	def initData(self, context):
		super().initData(context)
		editorType = self.editorType
		if editorType.value.isLabeled:
			self.editorLabel = self.editor
		if editorType is EditorType.CHOICE:
			self.updateEditorChoices()
		self.updateEditor()
		self.updateEditorLabel()
	
	def updateData(self):
		updateOrDrop(self.getData(), self.fieldName, self.getFieldValue())
	
	def getFieldValue(self):
		return self.getData().get(self.fieldName)
	
	def setFieldValue(self, value):
		self.getData()[self.fieldName] = value
	
	# called by TreeMultiCategorySettingsDialog.onCatListCtrl_KeyDown
	def delete(self):
		wx.Bell()
	
	def onEditor_change(self):
		super().onEditor_change()
		prm = self.categoryParams
		prm.tree.SetItemText(prm.treeNode, self.getTreeNodeLabel(
			self.fieldDisplayName, self.getFieldValue(), self.editorChoices
		))
		if prm.onEditor_change:
			prm.onEditor_change(self)
	
	def onPanelActivated(self):
		self.updateEditor()
		super().onPanelActivated()
	
	# called by TreeMultiCategorySettingsDialog.onKeyDown
	def spaceIsPressedOnTreeNode(self, withShift=False):
		if self.editorType is EditorType.TEXT:
			self.editor.SetFocus()
		else:
			self.toggleFieldValue(previous=withShift)
