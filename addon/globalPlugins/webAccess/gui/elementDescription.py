# globalPlugins/webAccess/gui/elementDescription.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2018 Accessolutions (http://accessolutions.fr)
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
from __future__ import absolute_import, division, print_function

__version__ = "2018.12.12"
__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"
__license__ = "GPL"


import wx

import addonHandler
import controlTypes
import gui
from logHandler import log


addonHandler.initTranslation()


def truncText(node):
	textList = getTextList(node)
	if not textList:
		return ""
	elif len(textList) == 1:
		return textList[0]
	else:
		desc = u"%d %s\r\n" % (
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
		desc += u"        %s %s\r\n" % (
			pgettext("webAccess.elementDescription", "from:"),
			textFrom
		)
		desc += u"        %s %s" % (
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
		for chield in node.children:
			textList += getTextList(chield)
		return textList
	else:
		return []


def formatAttributes(dic):
	t = ""
	for k in dic:
		t += "        %s=%s\r\n" % (k, dic[k])
	return t.strip()


def getNodeDescription():
	from globalPlugins.webAccess.webAppLib import html
	treeInterceptor = html.getTreeInterceptor()
	if not (treeInterceptor and hasattr(treeInterceptor, "nodeManager")):
		return _(u"No NodeManager")
	node = treeInterceptor.nodeManager.getCaretNode()
	node = node.parent
	obj = node.getNVDAObject()
	s = ""
	while node is not None:
		s += "tag %s\r\n    role %s\r\n" % (
			node.tag,
			controlTypes.roleLabels[node.role]
		)
		if node.id != "":
			s += "    id=%s\r\n" % node.id
		className = ""
		if node.className != "":
			className = node.className
		elif hasattr(node, "HTMLClassName"):
			className = node.HTMLClassName
		elif hasattr(obj, "HTMLNode"):
			className = obj.HTMLNode.attributes.item("class").nodeValue
			if className is None:
				className = ""
			node.HTMLClassName = className
			node.className = className
		if className is not None and className != "":
			s += "    class=%s\r\n" % className

		if node.src != "":
			s += "    src=%s\r\n" % node.src
		s += "    text=%s\r\n" % truncText(node)
		s += "\r\n"
		node = node.parent
		obj = obj.parent
	return s
		
	
def showElementDescriptionDialog():
	text = getNodeDescription()
	global dialog
	# Evaluate to False when not yet created or already destroyed.
	if not dialog:
		dialog = ElementDescriptionDialog(gui.mainFrame)
	dialog.Raise()
	dialog.Show(text)


# Singleton instance
dialog = None


class ElementDescriptionDialog(wx.Dialog):

	def __init__(self, parent):
		ElementDescriptionDialog._instance = self
		super(ElementDescriptionDialog, self).__init__(
			parent, title=_("Element description")
		)
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		item = self.output = wx.TextCtrl(
			self,
			wx.ID_ANY,
			size=(600, 600),
			style=wx.TE_MULTILINE | wx.TE_RICH
		)
		item.Bind(wx.EVT_KEY_DOWN, self.OnOutputKeyDown)
		mainSizer.Add(item)

		self.Bind(wx.EVT_CLOSE, self.OnClose)

		self.EscapeId = wx.ID_CLOSE
		
		mainSizer.Fit(self)
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)

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
		super(ElementDescriptionDialog, self).Show()
