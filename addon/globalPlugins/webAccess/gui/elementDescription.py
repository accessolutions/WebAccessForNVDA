# globalPlugins/webAccess/gui/elementDescription.py
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


# Get ready for Python 3


__version__ = "2021.02.10"
__author__ = "Frédéric Brugnot <f.brugnot@accessolutions.fr>"
__license__ = "GPL"


import wx

import addonHandler
import controlTypes
import gui


addonHandler.initTranslation()


def truncText(node):
	textList = getTextList(node)
	if not textList:
		return ""
	elif len(textList) == 1:
		return textList[0]
	else:
		desc = "%d %s\r\n" % (
			len(textList),
			pgettext("webAccess.elementDescription", "elements")
			if len(textList) > 1
			else pgettext("webAccess.elementDescription", "element")
		)
		textFrom = ""
		for text in textList:
			if text and text.strip():
				textFrom = text.strip()
				break
		textTo = ""
		for text in textList[::-1]:
			if text and text.strip():
				textTo = text.strip()
				break
		desc += "        %s %s\r\n" % (
			pgettext("webAccess.elementDescription", "from:"),
			textFrom
		)
		desc += "        %s %s" % (
			pgettext("webAccess.elementDescription", "to:"),
			textTo
		)
		return desc


def getTextList(node):
	if hasattr(node, "text"):
		return [node.text]
		t = node.text.strip()
		if len(t) > 2:
			return [t]
		else:
			return []
	elif hasattr(node, "children"):
		textList = []
		for child in node.children:
			textList += getTextList(child)
		return textList
	else:
		return []


def formatAttributes(dic):
	t = ""
	for k in dic:
		t += "        %s=%s\r\n" % (k, dic[k])
	return t.strip()


def getNodeDescription():
	import api
	from ..overlay import WebAccessObject
	focus = api.getFocusObject()
	if not (
		isinstance(focus, WebAccessObject)
		and focus.webAccess.nodeManager
	):
		return _("No NodeManager")
	ruleManager = focus.webAccess.ruleManager
	results = ruleManager.getResults() if ruleManager else []
	node = focus.webAccess.nodeManager.getCaretNode()
	node = node.parent
	obj = node.getNVDAObject()
	branch = []
	while node is not None:
		parts = []
		parts.append("tag %s" % node.tag)
		ruleNames = []
		for result in results:
			if hasattr(result, "node") and result.node == node:
				ruleNames.append(result.rule.name)
		if ruleNames:
			parts.append("    rules %s" % ", ".join(ruleNames))
		if node.id is not None:
			parts.append("    id %s" % node.id)
		parts.append("    role %s" % controlTypes.roleLabels[node.role])
		if node.className:
			parts.append("    class %s" % node.className)
		if node.states:
			parts.append("    states %s" % (", ".join(sorted((
				controlTypes.stateLabels.get(state, state)
				for state in node.states
			)))))
		if node.src:
			parts.append("    src %s" % node.src)
		parts.append("    text %s" % truncText(node))
		branch.append("\n".join(parts))
		node = node.parent
		obj = obj.parent
	return "\n\n".join(branch)
		
	
def showElementDescriptionDialog():
	text = getNodeDescription()
	global dialog
	# Evaluates to False when not yet created or already destroyed.
	if not dialog:
		dialog = ElementDescriptionDialog(gui.mainFrame)
	dialog.Raise()
	dialog.Show(text)


# Singleton instance
dialog = None


class ElementDescriptionDialog(wx.Dialog):

	def __init__(self, parent):
		ElementDescriptionDialog._instance = self
		super().__init__(
			parent, title=_("Element description")
		)
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		item = self.output = wx.TextCtrl(
			self,
			wx.ID_ANY,
			size=(600, 600),
			style=wx.TE_MULTILINE | wx.TE_RICH | wx.TE_READONLY
		)
		item.Bind(wx.EVT_KEY_DOWN, self.OnOutputKeyDown)
		mainSizer.Add(item)

		self.Bind(wx.EVT_CLOSE, self.OnClose)

		self.EscapeId = wx.ID_CLOSE
		
		mainSizer.Fit(self)
		self.CenterOnScreen()

	def OnClose(self, evt):
		self.Destroy()
	
	def OnOutputKeyDown(self, evt):
		key = evt.GetKeyCode()
		if key == wx.WXK_ESCAPE:
			self.Close()
			return
		evt.Skip()
	
	def Show(self, description):
		self.output.Value = description
		super().Show()
