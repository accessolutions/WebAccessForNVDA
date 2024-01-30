# -*- coding: UTF-8 -*-
#settingsDialogs.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2006-2018 NV Access Limited, Peter Vágner, Aleksey Sadovoy, Rui Batista, Joseph Lee, Heiko Folkerts, Zahari Yurukov, Leonard de Ruijter, Derek Riemer, Babbage B.V., Davy Kager, Ethan Holliger
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

"""
Back-ported from NVDA 2018.2 gui.settingsDialogs:
 - SettingsDialog
 - _RWLayoutNeededEvent
 - EVT_RW_LAYOUT_NEEDED
 - SettingsPanel
 - MultiCategorySettingsDialog
"""

import time
import weakref
import wx

import gui
from logHandler import log

try:
	import wx.lib.newevent as newevent
except ImportError:
	from . import wx_lib_newevent as newevent

try:
	from wx.lib import scrolledpanel
except ImportError:
	from ..nvda_2016_4 import wx_lib_scrolledpanel as scrolledpanel

try:
	from gui import nvdaControls
except ImportError:
	from ..nvda_2016_4 import gui_nvdaControls as nvdaControls

try:
	import guiHelper
except ImportError:
	from ..nvda_2016_4 import gui_guiHelper as guiHelper

try:
	from windowUtils import getWindowScalingFactor
except ImportError:
	from .windowUtils import getWindowScalingFactor


class SettingsDialog(wx.Dialog):
	"""A settings dialog.
	A settings dialog consists of one or more settings controls and OK and Cancel buttons and an optional Apply button.
	Action may be taken in response to the OK, Cancel or Apply buttons.

	To use this dialog:
		* Set L{title} to the title of the dialog.
		* Override L{makeSettings} to populate a given sizer with the settings controls.
		* Optionally, override L{postInit} to perform actions after the dialog is created, such as setting the focus. Be
			aware that L{postInit} is also called by L{onApply}.
		* Optionally, extend one or more of L{onOk}, L{onCancel} or L{onApply} to perform actions in response to the
			OK, Cancel or Apply buttons, respectively.

	@ivar title: The title of the dialog.
	@type title: str
	"""

	class MultiInstanceError(RuntimeError): pass

	_instances=weakref.WeakSet()
	title = ""
	shouldSuspendConfigProfileTriggers = True

	def __new__(cls, *args, **kwargs):
		if next((dlg for dlg in SettingsDialog._instances if isinstance(dlg,cls)),None) or (
			SettingsDialog._instances and not kwargs.get('multiInstanceAllowed',False)
		):
			raise SettingsDialog.MultiInstanceError("Only one instance of SettingsDialog can exist at a time")
			pass
		obj = super(SettingsDialog, cls).__new__(cls, *args, **kwargs)
		SettingsDialog._instances.add(obj)
		return obj

	def __init__(self, parent,
	             resizeable=False,
	             hasApplyButton=False,
	             settingsSizerOrientation=wx.VERTICAL,
	             multiInstanceAllowed=False):
		"""
		@param parent: The parent for this dialog; C{None} for no parent.
		@type parent: wx.Window
		@param resizeable: True if the settings dialog should be resizable by the user, only set this if
			you have tested that the components resize correctly.
		@type resizeable: bool
		@param hasApplyButton: C{True} to add an apply button to the dialog; defaults to C{False} for backwards compatibility.
		@type hasApplyButton: bool
		@param settingsSizerOrientation: Either wx.VERTICAL or wx.HORIZONTAL. This controls the orientation of the
			sizer that is passed into L{makeSettings}. The default is wx.VERTICAL.
		@type settingsSizerOrientation: wx.Orientation
		@param multiInstanceAllowed: Whether multiple instances of SettingsDialog may exist.
			Note that still only one instance of a particular SettingsDialog subclass may exist at one time.
		@type multiInstanceAllowed: bool
		"""
		# if gui._isDebug():
		# 	startTime = time.time()
		windowStyle = wx.DEFAULT_DIALOG_STYLE | (wx.RESIZE_BORDER if resizeable else 0)
		super(SettingsDialog, self).__init__(parent, title=self.title, style=windowStyle)
		self.hasApply = hasApplyButton

		# the wx.Window must be constructed before we can get the handle.
		import windowUtils
		self.scaleFactor = getWindowScalingFactor(self.GetHandle())

		self.mainSizer=wx.BoxSizer(wx.VERTICAL)
		self.settingsSizer=wx.BoxSizer(settingsSizerOrientation)
		self.makeSettings(self.settingsSizer)

		self.mainSizer.Add(self.settingsSizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND, proportion=1)
		self.mainSizer.Add(wx.StaticLine(self), flag=wx.EXPAND)

		buttonSizer = guiHelper.ButtonHelper(wx.HORIZONTAL)
		# Translators: The Ok button on a NVDA dialog. This button will accept any changes and dismiss the dialog.
		buttonSizer.addButton(self, label=_("OK"), id=wx.ID_OK)
		# Translators: The cancel button on a NVDA dialog. This button will discard any changes and dismiss the dialog.
		buttonSizer.addButton(self, label=_("Cancel"), id=wx.ID_CANCEL)
		if hasApplyButton:
			# Translators: The Apply button on a NVDA dialog. This button will accept any changes but will not dismiss the dialog.
			buttonSizer.addButton(self, label=_("Apply"), id=wx.ID_APPLY)

		self.mainSizer.Add(
			buttonSizer.sizer,
			border=guiHelper.BORDER_FOR_DIALOGS,
			flag=wx.ALL | wx.ALIGN_RIGHT
		)

		self.mainSizer.Fit(self)
		self.SetSizer(self.mainSizer)

		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
		self.Bind(wx.EVT_BUTTON, self.onApply, id=wx.ID_APPLY)
		self.Bind(wx.EVT_CHAR_HOOK, self._enterActivatesOk_ctrlSActivatesApply)

		self.postInit()
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		# if gui._isDebug():
		# 	log.debug("Loading %s took %.2f seconds"%(self.__class__.__name__, time.time() - startTime))

	def _enterActivatesOk_ctrlSActivatesApply(self, evt):
		"""Listens for keyboard input and triggers ok button on enter and triggers apply button when control + S is
		pressed. Cancel behavior is built into wx.
		Pressing enter will also close the dialog when a list has focus
		(e.g. the list of symbols in the symbol pronunciation dialog).
		Without this custom handler, enter would propagate to the list control (wx ticket #3725).
		"""
		if evt.KeyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.ProcessEvent(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK))
		elif self.hasApply and evt.UnicodeKey == ord(u'S') and evt.controlDown:
			self.ProcessEvent(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_APPLY))
		else:
			evt.Skip()

	def makeSettings(self, sizer):
		"""Populate the dialog with settings controls.
		Subclasses must override this method.
		@param sizer: The sizer to which to add the settings controls.
		@type sizer: wx.Sizer
		"""
		raise NotImplementedError

	def postInit(self):
		"""Called after the dialog has been created.
		For example, this might be used to set focus to the desired control.
		Sub-classes may override this method.
		"""

	def onOk(self, evt):
		"""Take action in response to the OK button being pressed.
		Sub-classes may extend this method.
		This base method should always be called to clean up the dialog.
		"""
		self.DestroyChildren()
		self.Destroy()
		self.SetReturnCode(wx.ID_OK)

	def onCancel(self, evt):
		"""Take action in response to the Cancel button being pressed.
		Sub-classes may extend this method.
		This base method should always be called to clean up the dialog.
		"""
		self.DestroyChildren()
		self.Destroy()
		self.SetReturnCode(wx.ID_CANCEL)

	def onApply(self, evt):
		"""Take action in response to the Apply button being pressed.
		Sub-classes may extend or override this method.
		This base method should be called to run the postInit method.
		"""
		self.postInit()
		self.SetReturnCode(wx.ID_APPLY)

	def scaleSize(self, size):
		"""Helper method to scale a size using the logical DPI
		@param size: The size (x,y) as a tuple or a single numerical type to scale
		@returns: The scaled size, returned as the same type"""
		if isinstance(size, tuple):
			return (self.scaleFactor * size[0], self.scaleFactor * size[1])
		return self.scaleFactor * size


# An event and event binder that will notify the containers that they should
# redo the layout in whatever way makes sense for their particular content.
_RWLayoutNeededEvent, EVT_RW_LAYOUT_NEEDED = newevent.NewCommandEvent()

class SettingsPanel(wx.Panel):
	"""A settings panel, to be used in a multi category settings dialog.
	A settings panel consists of one or more settings controls.
	Action may be taken in response to the parent dialog's OK or Cancel buttons.

	To use this panel:
		* Set L{title} to the title of the category.
		* Override L{makeSettings} to populate a given sizer with the settings controls.
		* Optionally, extend L{onPanelActivated} to perform actions after the category has been selected in the list of categories, such as synthesizer or braille display list population.
		* Optionally, extend L{onPanelDeactivated} to perform actions after the category has been deselected (i.e. another category is selected) in the list of categories.
		* Optionally, extend one or both of L{onSave} or L{onDiscard} to perform actions in response to the parent dialog's OK or Cancel buttons, respectively.
		* Optionally, extend one or both of L{isValid} or L{postSave} to perform validation before or steps after saving, respectively.

	@ivar title: The title of the settings panel, also listed in the list of settings categories.
	@type title: str
	"""

	title=""

	def __init__(self, parent):
		"""
		@param parent: The parent for this panel; C{None} for no parent.
		@type parent: wx.Window
		"""
		# if gui._isDebug():
		# 	startTime = time.time()
		super(SettingsPanel, self).__init__(parent, wx.ID_ANY)
		# the wx.Window must be constructed before we can get the handle.
		import windowUtils
		self.scaleFactor = getWindowScalingFactor(self.GetHandle())
		self.mainSizer=wx.BoxSizer(wx.VERTICAL)
		self.settingsSizer=wx.BoxSizer(wx.VERTICAL)
		self.makeSettings(self.settingsSizer)
		self.mainSizer.Add(self.settingsSizer, flag=wx.ALL)
		self.mainSizer.Fit(self)
		self.SetSizer(self.mainSizer)
		# if gui._isDebug():
		# 	log.debug("Loading %s took %.2f seconds"%(self.__class__.__name__, time.time() - startTime))

	def makeSettings(self, sizer):
		"""Populate the panel with settings controls.
		Subclasses must override this method.
		@param sizer: The sizer to which to add the settings controls.
		@type sizer: wx.Sizer
		"""
		raise NotImplementedError

	def onPanelActivated(self):
		"""Called after the panel has been activated (i.e. de corresponding category is selected in the list of categories).
		For example, this might be used for resource intensive tasks.
		Sub-classes should extendthis method.
		"""
		self.Show()

	def onPanelDeactivated(self):
		"""Called after the panel has been deactivated (i.e. another category has been selected in the list of categories).
		Sub-classes should extendthis method.
		"""
		self.Hide()

	def onSave(self):
		"""Take action in response to the parent's dialog OK or apply button being pressed.
		Sub-classes should override this method.
		MultiCategorySettingsDialog is responsible for cleaning up the panel when OK is pressed.
		"""
		raise NotImplementedError

	def isValid(self):
		"""Evaluate whether the current circumstances of this panel are valid
		and allow saving all the settings in a L{MultiCategorySettingsDialog}.
		Sub-classes may extend this method.
		@returns: C{True} if validation should continue,
			C{False} otherwise.
		@rtype: bool
		"""
		return True

	def postSave(self):
		"""Take action whenever saving settings for all panels in a L{MultiCategorySettingsDialog} succeeded.
		Sub-classes may extend this method.
		"""

	def onDiscard(self):
		"""Take action in response to the parent's dialog Cancel button being pressed.
		Sub-classes may override this method.
		MultiCategorySettingsDialog is responsible for cleaning up the panel when Cancel is pressed.
		"""

	def _sendLayoutUpdatedEvent(self):
		"""Notify any wx parents that may be listening that they should redo their layout in whatever way
		makes sense for them. It is expected that sub-classes call this method in response to changes in
		the number of GUI items in their panel.
		"""
		event = _RWLayoutNeededEvent(self.GetId())
		event.SetEventObject(self)
		self.GetEventHandler().ProcessEvent(event)

	def scaleSize(self, size):
		"""Helper method to scale a size using the logical DPI
		@param size: The size (x,y) as a tuple or a single numerical type to scale
		@returns: The scaled size, returned as the same type"""
		if isinstance(size, tuple):
			return (self.scaleFactor * size[0], self.scaleFactor * size[1])
		return self.scaleFactor * size

class MultiCategorySettingsDialog(SettingsDialog):
	"""A settings dialog with multiple settings categories.
	A multi category settings dialog consists of a list view with settings categories on the left side, 
	and a settings panel on the right side of the dialog.
	Furthermore, in addition to Ok and Cancel buttons, it has an Apply button by default,
	which is different  from the default behavior of L{SettingsDialog}.

	To use this dialog: set title and populate L{categoryClasses} with subclasses of SettingsPanel.
	Make sure that L{categoryClasses} only  contains panels that are available on a particular system.
	For example, if a certain category of settings is only supported on Windows 10 and higher,
	that category should be left out of L{categoryClasses}
	"""

	title=""
	categoryClasses=[]

	class CategoryUnavailableError(RuntimeError): pass

	def __init__(self, parent, initialCategory=None):
		"""
		@param parent: The parent for this dialog; C{None} for no parent.
		@type parent: wx.Window
		@param initialCategory: The initial category to select when opening this dialog
		@type parent: SettingsPanel
		"""
		if initialCategory and not issubclass(initialCategory,SettingsPanel):
			# if gui._isDebug():
			# 	log.debug("Unable to open category: {}".format(initialCategory), stack_info=True)
			raise TypeError("initialCategory should be an instance of SettingsPanel")
		if initialCategory and initialCategory not in self.categoryClasses:
			# if gui._isDebug():
			# 	log.debug("Unable to open category: {}".format(initialCategory), stack_info=True)
			raise MultiCategorySettingsDialog.CategoryUnavailableError(
				"The provided initial category is not a part of this dialog"
			)
		self.initialCategory = initialCategory
		self.currentCategory = None
		self.setPostInitFocus = None
		# dictionary key is index of category in self.catList, value is the instance. Partially filled, check for KeyError
		self.catIdToInstanceMap = {}

		super(MultiCategorySettingsDialog, self).__init__(
			parent,
			resizeable=True,
			hasApplyButton=True,
			settingsSizerOrientation=wx.HORIZONTAL
		)

		# setting the size must be done after the parent is constructed.
		self.SetMinSize(self.scaleSize(self.MIN_SIZE))
		self.SetSize(self.scaleSize(self.INITIAL_SIZE))
		# the size has changed, so recenter on the screen
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)

	# Initial / min size for the dialog. This size was chosen as a medium fit, so the
	# smaller settings panels are not surrounded by too much space but most of
	# the panels fit. Vertical scrolling is acceptable. Horizontal scrolling less
	# so, the width was chosen to eliminate horizontal scroll bars. If a panel
	# exceeds the the initial width a debugWarning will be added to the log.
	INITIAL_SIZE = (800, 480)
	MIN_SIZE = (470, 240) # Min height required to show the OK, Cancel, Apply buttons

	def makeSettings(self, settingsSizer):
		sHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		# Translators: The label for the list of categories in a multi category settings dialog.
		categoriesLabelText=_("&Categories:")
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

		self.catListCtrl = nvdaControls.AutoWidthColumnListCtrl(
			self,
			autoSizeColumnIndex=0,
			size=catListDim,
			style=wx.LC_REPORT|wx.LC_SINGLE_SEL|wx.LC_NO_HEADER
		)
		# This list consists of only one column.
		# The provided column header is just a placeholder, as it is hidden due to the wx.LC_NO_HEADER style flag.
		self.catListCtrl.InsertColumn(0,categoriesLabelText)

		# Put the settings panel in a scrolledPanel, we don't know how large the settings panels might grow. If they exceed
		# the maximum size, its important all items can be accessed visually.
		# Save the ID for the panel, this panel will have its name changed when the categories are changed. This name is
		# exposed via the IAccessibleName property.
		global NvdaSettingsCategoryPanelId
		NvdaSettingsCategoryPanelId = wx.NewId()
		self.container = scrolledpanel.ScrolledPanel(
			parent = self,
			id = NvdaSettingsCategoryPanelId,
			style = wx.TAB_TRAVERSAL | wx.BORDER_THEME,
			size=containerDim
		)

		# Th min size is reset so that they can be reduced to below their "size" constraint.
		self.container.SetMinSize((1,1))
		self.catListCtrl.SetMinSize((1,1))

		self.containerSizer = wx.BoxSizer(wx.VERTICAL)
		self.container.SetSizer(self.containerSizer)

		for cls in self.categoryClasses:
			if not issubclass(cls,SettingsPanel):
				raise RuntimeError("Invalid category class %s provided in %s.categoryClasses"%(cls.__name__,self.__class__.__name__))
			# It's important here that the listItems are added to catListCtrl in the same order that they exist in categoryClasses.
			# the ListItem index / Id is used to index categoryClasses, and used as the key in catIdToInstanceMap
			self.catListCtrl.Append((cls.title,))

		# populate the GUI with the initial category
		initialCatIndex = 0 if not self.initialCategory else self.categoryClasses.index(self.initialCategory)
		self._doCategoryChange(initialCatIndex)
		self.catListCtrl.Select(initialCatIndex)
		# we must focus the initial category in the category list.
		self.catListCtrl.Focus(initialCatIndex)
		self.setPostInitFocus = self.container.SetFocus if self.initialCategory else self.catListCtrl.SetFocus

		self.gridBagSizer=gridBagSizer=wx.GridBagSizer(
			hgap=guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL,
			vgap=guiHelper.SPACE_BETWEEN_BUTTONS_VERTICAL
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
		self.catListCtrl.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.onCategoryChange)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.Bind(EVT_RW_LAYOUT_NEEDED, self._onPanelLayoutChanged)

	def _getCategoryPanel(self, catId):
		panel = self.catIdToInstanceMap.get(catId, None)
		if not panel:
			try:
				cls = self.categoryClasses[catId]
			except IndexError:
				raise ValueError("Unable to create panel for unknown category ID: {}".format(catId))
			panel = cls(parent=self.container)
			panel.Hide()
			self.containerSizer.Add(panel, flag=wx.ALL, border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL)
			self.catIdToInstanceMap[catId] = panel
			panelWidth = panel.Size[0]
			availableWidth = self.containerSizer.GetSize()[0]
			# if panelWidth > availableWidth and gui._isDebug():
			# 	log.debugWarning(
			# 		("Panel width ({1}) too large for: {0} Try to reduce the width of this panel, or increase width of " +
			# 		 "MultiCategorySettingsDialog.MIN_SIZE"
			# 		).format(cls, panel.Size[0])
			# 	)
		return panel

	def postInit(self):
		# By default after the dialog is created, focus lands on the button group for wx.Dialogs. However this is not where
		# we want focus. We only want to modify focus after creation (makeSettings), but postInit is also called after
		# onApply, so we reset the setPostInitFocus function.
		if self.setPostInitFocus:
			self.setPostInitFocus()
			self.setPostInitFocus = None
		else:
			# when postInit is called without a setPostInitFocus ie because onApply was called
			# then set the focus to the listCtrl. This is a good starting point for a "fresh state"
			self.catListCtrl.SetFocus()


	def onCharHook(self,evt):
		"""Listens for keyboard input and switches panels for control+tab"""
		if not self.catListCtrl:
			# Dialog has not yet been constructed.
			# Allow another handler to take the event, and return early.
			evt.Skip()
			return
		key = evt.GetKeyCode()
		listHadFocus = self.catListCtrl.HasFocus()
		if evt.ControlDown() and key==wx.WXK_TAB:
			# Focus the categories list. If we don't, the panel won't hide correctly
			if not listHadFocus:
				self.catListCtrl.SetFocus()
			index = self.catListCtrl.GetFirstSelected()
			newIndex=index-1 if evt.ShiftDown() else index+1
			# Less than first wraps to the last index, greater than last wraps to first index.
			newIndex=newIndex % self.catListCtrl.ItemCount
			self.catListCtrl.Select(newIndex)
			# we must focus the new selection in the category list to trigger the change of category.
			self.catListCtrl.Focus(newIndex)
			if not listHadFocus and self.currentCategory:
				self.currentCategory.SetFocus()
		else:
			evt.Skip()

	def _onPanelLayoutChanged(self,evt):
		# call layout and SetupScrolling on the container so that the controls apear in their expected locations.
		self.container.Layout()
		self.container.SetupScrolling()
		# when child elements get smaller the scrolledPanel does not
		# erase the old contents and must be redrawn
		self.container.Refresh()

	def _doCategoryChange(self, newCatId):
		oldCat = self.currentCategory
		# Freeze and Thaw are called to stop visual artifact's while the GUI
		# is being rebuilt. Without this, the controls can sometimes be seen being
		# added.
		self.container.Freeze()
		try:
			newCat = self._getCategoryPanel(newCatId)
		except ValueError as e:
			newCatTitle = self.catListCtrl.GetItemText(newCatId)
			log.error("Unable to change to category: {}".format(newCatTitle), exc_info=e)
			return
		if oldCat:
			oldCat.onPanelDeactivated()
		self.currentCategory = newCat
		newCat.onPanelActivated()
		# call Layout and SetupScrolling on the container to make sure that the controls apear in their expected locations.
		self.container.Layout()
		self.container.SetupScrolling()
		# Set the label for the container, this is exposed via the Name property on an NVDAObject.
		# For one or another reason, doing this before SetupScrolling causes this to be ignored by NVDA in some cases.
		# Translators: This is the label for a category within the settings dialog. It is announced when the user presses `ctl+tab` or `ctrl+shift+tab` while focus is on a control withing the NVDA settings dialog. The %s will be replaced with the name of the panel (eg: General, Speech, Braille, etc)
		self.container.SetLabel(_("%s Settings Category")%newCat.title)
		self.container.Thaw()

	def onCategoryChange(self, evt):
		currentCat = self.currentCategory
		newIndex = evt.GetIndex()
		if not currentCat or newIndex != self.categoryClasses.index(currentCat.__class__):
			self._doCategoryChange(newIndex)
		else:
			evt.Skip()

	def _doSave(self):
		for panel in self.catIdToInstanceMap.itervalues():
			if panel.isValid() is False:
				raise ValueError("Validation for %s blocked saving settings" % panel.__class__.__name__)
		for panel in self.catIdToInstanceMap.itervalues():
			panel.onSave()
		for panel in self.catIdToInstanceMap.itervalues():
			panel.postSave()

	def onOk(self,evt):
		try:
			self._doSave()
		except ValueError:
			log.debugWarning("", exc_info=True)
			return
		for panel in self.catIdToInstanceMap.itervalues():
			panel.Destroy()
		super(MultiCategorySettingsDialog,self).onOk(evt)

	def onCancel(self,evt):
		for panel in self.catIdToInstanceMap.itervalues():
			panel.onDiscard()
			panel.Destroy()
		super(MultiCategorySettingsDialog,self).onCancel(evt)

	def onApply(self,evt):
		try:
			self._doSave()
		except ValueError:
			log.debugWarning("", exc_info=True)
			return
		super(MultiCategorySettingsDialog,self).onApply(evt)
