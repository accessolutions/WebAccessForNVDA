# globalPlugins/webAccess/gui/rule/wizard.py
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


__version__ = "2024.02.02"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from collections.abc import Mapping
from typing import Any

from itertools import pairwise
import wx
import wx.adv

import addonHandler
import api
import gui
from gui import guiHelper
from logHandler import log
import speech

from ...utils import guarded, notifyError
from ...ruleHandler import ruleTypes
from ...ruleHandler.properties import PropertySpec
from .. import ContextualSettingsPanel, EVT_RW_LAYOUT_NEEDED, ScalingMixin, ValidationError, stripAccel
from .abc import RuleAwarePanelBase
from .editor import SimpleSingleNodeCriteriaPanel
from .criteriaEditor import testCriteria
from .gestures import GesturesPanelBase
from .properties import Properties, PropertiesPanelBase
from . import editor, saveRule

addonHandler.initTranslation()


class Page(wx.adv.WizardPageSimple, ContextualSettingsPanel):

	wizardPageHeaderDescription = None
		
	def makeSettings(self, settingsSizer):
		scale = self.scale
		if self.wizardPageHeaderDescription:
			item = wx.StaticText(self, label=self.wizardPageHeaderDescription)
			item.Wrap(scale(690))
			settingsSizer.Add(item)
			settingsSizer.AddSpacer(scale(guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS) * 3)
		super().makeSettings(settingsSizer)
		self.Bind(EVT_RW_LAYOUT_NEEDED, lambda evt: self.Layout())


class GeneralPanel(RuleAwarePanelBase, ContextualSettingsPanel):
	
	def makeSettings(self, settingsSizer):
		scale = self.scale
		gbSizer = wx.GridBagSizer()
		settingsSizer.Add(gbSizer, flag=wx.EXPAND, proportion=1)
		row = 0
		col = 0
		item = wx.StaticText(self, label=stripAccel(editor.SHARED_LABELS["type"]))
		gbSizer.Add(item, (row, col))
		col += 1
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), (row, col))
		col += 1
		item = self.ruleType = wx.Choice(
			self,
			choices=list(ruleTypes.ruleTypeLabels.values())
		)
		gbSizer.Add(item, (row, col), flag=wx.EXPAND)
		
		row += 1
		gbSizer.Add(scale(0, guiHelper.SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS), pos=(row, 0))

		row += 1
		item = wx.StaticText(self, label=stripAccel(editor.SHARED_LABELS["name"]))
		gbSizer.Add(item, pos=(row, 0))
		gbSizer.Add(scale(guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL, 0), pos=(row, 1))
		item = self.ruleName = wx.TextCtrl(self)
		gbSizer.Add(item, pos=(row, 2), flag=wx.EXPAND)
		return row
	
	getData = RuleAwarePanelBase.getRuleData
	
	def initData(self, context):
		super().initData(context)
		data = self.getData()
		self.ruleType.SetSelection(tuple(ruleTypes.ruleTypeLabels.keys()).index(self.getRuleType()))
		self.ruleName.ChangeValue(data.get("name", ""))
	
	def updateData(self):
		data = self.getData()
		data["type"] = tuple(ruleTypes.ruleTypeLabels.keys())[self.ruleType.Selection]
		data["name"] = self.ruleName.Value
	
	isValid = editor.GeneralPanel.isValid
	

class GeneralPage(Page, GeneralPanel):
	
	# Translators: The description for a page of the Rule wizard
	wizardPageHeaderDescription = _(
		"First, choose a type and name for the new Rule."
		"\n"
		"At any time, press F12 to leave this wizard and open the full fledged editor."
	)



class CriteriaPageBase(Page, SimpleSingleNodeCriteriaPanel):
	
	def makeSettings_buttons(self, vBoxSizer):
		super(SimpleSingleNodeCriteriaPanel, self).makeSettings_buttons(vBoxSizer)
	
	def initData(self, context):
		super(SimpleSingleNodeCriteriaPanel, self).initData(context)


class ContextPage(CriteriaPageBase):
	
	# Translators: The description for a page of the Rule wizard
	wizardPageHeaderDescription = _(
		"Choose a context for the criteria of the new rule."
		"\n\n"
		"Contexts allow to restrict the look-up on some pages or some portion of the pages."
		"\n\n"
		"If unsure, keep the default \"General\" choice"
	)
	
	def makeSettings_others(self, gbSizer, row):
		return row
	
	def initData_others(self, context):
		pass
	
	def updateData_others(self):
		pass
	
	def isValid_others(self):
		return True


class CriteriaPage(CriteriaPageBase):
	
	# Translators: The description for a page of the Rule wizard
	wizardPageHeaderDescription = _(
		"Choose criteria for the new rule."
		"\n\n"
		"Each criterion corresponds to an attribute that will be looked-up on the elements all along the "
		"branches of the document tree."
		"\n"
		"Suggested values are provided in the drop-down list for most of them."
		"\n\n"
		"Press F5 to test these criteria. Once satisfied with the result, press Enter or click Next."
	)
	
	def GetNext(self):
		page = super().GetNext()
		# First called before initData
		ruleType = self.Parent.context.get("data", {}).get("rule", {}).get("type")
		if not ruleType in ruleTypes.ACTION_TYPES:
			# Skip the Gestures page
			page = page.GetNext()
		return page
	
	def makeSettings_context(self, gbSizer, row):
		return None
	
	def initData_context(self, context):
		pass
	
	def updateData_context(self):
		pass
	
	def isValid_context(self):
		return True


class GesturesPage(Page, GesturesPanelBase):
	
	# Translators: The description for a page of the Rule wizard
	wizardPageHeaderDescription = _(
		"You may associate an input gesture with an action on the result found."
		"\n\n"
		"Eg. define a keyboard shortcut to move to the desired location."
	)
	
	def GetNext(self):
		page = super().GetNext()
		# First called before initData
		ruleType = self.Parent.context.get("data", {}).get("rule", {}).get("type")
		if not PropertySpec.forRuleType(ruleType):
			# Skip the Properties page
			return None
		return page
	
	getData = RuleAwarePanelBase.getRuleData


class PropertiesPage(Page, PropertiesPanelBase):
	
	def GetPrev(self):
		page = super().GetPrev()
		# First called before initData
		ruleType = self.Parent.context.get("data", {}).get("rule", {}).get("type")
		if not ruleType in ruleTypes.ACTION_TYPES:
			# Skip the Gestures page
			page = page.GetPrev()
		return page
	
	def getData(self):
		return self.context["data"]["rule"]["properties"]
	
	def initData_properties(self):
		self.context["data"]["rule"].setdefault("properties", {})
		self.props = Properties(self.context, self.getData())
	
	def onListCtrl_charHook(self, evt):
		# For some reason, when the focus is on the ListCtrl, the return key
		# does not seem to validate the wizard page. This does not happen when
		# the same panel is shown on the editor.
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.Parent.forward()
			return
		super().onListCtrl_charHook(evt)


class Wizard(wx.adv.Wizard, ScalingMixin):
	
	pageClasses = (GeneralPage, ContextPage, CriteriaPage, GesturesPage, PropertiesPage)
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.finishing = False
		pages = self.pages = tuple(cls(self) for cls in self.pageClasses)
		for prevPage, nextPage in pairwise(pages):
			wx.adv.WizardPageSimple.Chain(prevPage, nextPage)
		self.GetPageAreaSizer().Add(pages[0])
		self.SetPageSize((self.scale(700), -1))
		self.Bind(wx.EVT_BUTTON, self.onBackOrNext, id=wx.ID_BACKWARD)
		self.Bind(wx.EVT_BUTTON, self.onBackOrNext, id=wx.ID_FORWARD)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.Bind(wx.adv.EVT_WIZARD_PAGE_CHANGED, self.onPageChanged)
		self.SetLayoutAdaptationMode(wx.DIALOG_ADAPTATION_MODE_ENABLED)
		
		# wxPython uses a non conventionnal French translation for this button.
		btn = wx.FindWindowById(wx.ID_BACKWARD, self)
		if btn.Label == "< &Retour":
			# Avoid removing another proper translation in a language WebAccess itself
			# would not be translated to.
			btn.SetLabel("< &Précédent")
	
	def getData(self):
		return self.context["data"]["rule"]
	
	def initData(self, context):
		self.context = context
		data = context.setdefault("data", {})
		if context.get("new"):
			# Translators: The title for the Rule Creation Wizard dialog
			title = _("Rule Creation Wizard")
			# There might be existing data pasted from the clipboard
			data.setdefault("rule", {"type": ruleTypes.MARKER})
		else:
			# Translators: The title for the Rule Creation Wizard dialog
			title = _("Rule Edit Wizard")
			data["rule"] = context["rule"].dump()
		self.SetTitle(title)
	
	def forward(self):
		btn = wx.FindWindowById(wx.ID_FORWARD, self)
		if not btn:
			log.error("Could not find button for id=wx.ID_FORWARD")
			return
		cmdEvt = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_FORWARD)
		cmdEvt.SetEventObject(btn)
		wx.PostEvent(self, cmdEvt)
	
	@guarded
	def onBackOrNext(self, evt):
		# Vetoing EVT_WIZARD_PAGE_CHANGING for the last page, or EVT_WIZARD_FINISHED,
		# does not appear to be working as documented.
		page = self.CurrentPage
		page.updateData()
		if evt.Id == wx.ID_BACKWARD:
			evt.Skip()
			return
		assert evt.Id == wx.ID_FORWARD
		# Using Page.Validate instead would not allow to bypass when moving backwards.
		try:
			if not page.isValid():
				self.finishing = False
				return
		except ValidationError:
			self.finishing = False
			return
		except Exception:
			notifyError()
			return
		if not (page.GetNext() or self.save()):
			return
		evt.Skip()
	
	@guarded
	def onCharHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		if keycode == wx.WXK_F5 and mods in (wx.MOD_NONE, wx.MOD_CONTROL):
			self.testCriteria()
			return
		elif keycode == wx.WXK_F12 and mods == wx.MOD_NONE:
			self.switchToEditor()
			return
		elif keycode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and mods == wx.MOD_CONTROL:
			self.finishing = True
			self.forward()
			return
		evt.Skip()
	
	@guarded
	def onPageChanged(self, evt):
		page = evt.Page
		page.initData(self.context)
		if page.GetNext() is None:
			btn = wx.FindWindowById(wx.ID_FORWARD, self)
			# wxPython uses a non conventionnal French translation for this button, and sets it lately
			# as we reach the last page.
			if btn.Label == "&Finir":
				# Avoid removing another proper translation in a language WebAccess itself
				# would not be translated to.
				btn.SetLabel("&Terminer")
		if self.finishing:
			self.forward()
			return
		# NVDA does not announce the new description on panel change, as if there was no new focus event
		api.processPendingEvents()
		speech.speakMessage(page.wizardPageHeaderDescription)
	
	@guarded
	def save(self):
		try:
			saveRule(self.context, self.getData(), self)
		except ValidationError:
			return False
		except Exception:
			notifyError()
			return False
		return True
	
	@guarded
	def switchToEditor(self):
		self.CurrentPage.updateData()
		context = self.context
		context["fromWizardPage"] = type(self.CurrentPage).__name__
		self.Hide()
		returnCode = wx.ID_OK if editor.show(context, self) else wx.ID_CANCEL
		self.EndModal(returnCode)  # RunWizard called ShowModal
	
	def testCriteria(self):
		self.CurrentPage.updateData()
		context = self.context
		context["data"]["criteria"] = self.getData().get("criteria", [{}])[0]
		testCriteria(self.context)
		del context["data"]["criteria"]


def show(context, parent=None):
	wizard = Wizard(parent)
	wizard.initData(context)
	return wizard.RunWizard(wizard.pages[0])
