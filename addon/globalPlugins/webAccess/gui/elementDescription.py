# globalPlugins/webAccess/gui/elementDescription.py
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


# Get ready for Python 3


__authors__ = (
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)
__license__ = "GPL"


import wx

import addonHandler
import api
import controlTypes
from globalCommands import commands
import gui
from logHandler import log
import queueHandler
import ui

from ..utils import guarded


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


def getNodeDescription(node):
	try:
		results = node.nodeManager.ruleManager.getResults()
	except AttributeError:
		results = []
	#node = node.parent
	branch = []
	if not hasattr(node, "tag"):
		branch.append("text %s" % truncText(node))
		node = node.parent
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
		if node.url:
			parts.append("    url %s" % node.url)
		parts.append("    text %s" % truncText(node))
		branch.append("\n".join(parts))
		node = node.parent
	return "\n\n".join(branch)


def computeRelativePath(node1, node2):
	if node1 is node2:
		return ""
	
	# Determine common ancestor
	ancestors = []
	node = node1
	while node is not None:
		ancestors.append(node)
		node = node.parent
	node = node2
	while node is not None:
		if node in ancestors:
			ancestor = node
			break
		node = node.parent
	else:
		ValueError("These nodes do not belong to the same document tree.")
	del ancestors
	
	if ancestor is node1:
		# Compute path from ancestor node1 to deepest node2
		path = ""
		child = node2
		parent = node2.parent
		while True:
			index = parent.children.index(child)
			path = "d" + ("r" * index) + path
			if parent is node1:
				break
			child = parent
			parent = parent.parent
		return path
	elif ancestor is node2:
		# Compute path from deepest node1 to ancestor node2
		path = ""
		parent = node1.parent
		while True:
			path += "u"
			if parent is ancestor:
				break
			parent = parent.parent
		return path
		
	# Compute path from node1 to first common ancestor child
	path1 = ""
	ancestorChild1 = node1
	parent = node1.parent
	while True:
		if parent is ancestor:
			break
		ancestorChild1 = parent
		path1 += "u"
		parent = parent.parent
	
	# Compute path from first common ancestor child to node2
	path2 = ""
	ancestorChild2 = child = node2
	parent = node2.parent
	while parent is not ancestor:
		ancestorChild2 = parent
		index = parent.children.index(child)
		path2 = "d" + ("r" * index) + path2
		child = parent
		parent = parent.parent
	
	# Chain path1 to path2
	children = ancestor.children
	index1 = children.index(ancestorChild1)
	index2 = children.index(ancestorChild2)
	if index1 < index2:
		link = "r" * (index2 - index1)
	else:
		link = "l" * (index1 - index2)	
	return path1 + link + path2


def getRoot(node):
	while True:
		parent = node.parent
		if parent is None:
			break
		node = parent
	return node


def refresh(oldNode, oldRoot, newRoot):
	"""Search in newRoot for a node corresponding to oldNode in oldRoot
	"""
	path = computeRelativePath(oldRoot, oldNode)
	newNode = newRoot.walk(path)
	if newNode is None or (
		(
			newNode.offset != oldNode.offset
			or newNode.size != oldNode.size
		) and getNodeDescription(newNode) != getNodeDescription(oldNode)
	):
		return None
	return newNode


def snapshot(node, candidateRoot=None):
	root = getRoot(node)
	if root is candidateRoot:
		return node
	from copy import deepcopy
	newRoot = deepcopy(root)
	return refresh(node, root, newRoot), newRoot


markedNode = None


class ElementDescriptionDialog(wx.Dialog):

	_instance = None
	
	@classmethod
	def getInstance(cls, parent):
		# Overriding __new__ instead does not seem supported:
		# Two  dialogs appear when reusing the singleton, but the first gets bogus.
		instance = cls._instance
		# Evaluates to False when not yet created or already destroyed.
		if instance:
			if instance.Parent is parent:
				return instance
			instance.Destroy()
		instance = cls._instance = cls(parent)
		return instance

	def __init__(self, parent):
		super().__init__(
			parent,
			# Translators: The title for the Element Description dialog
			title=_("Element description")
		)
		self.mgr = None
		self.history = []
		self.identifier = None
		self.root = None
		self.node = None
		
		sizer = wx.BoxSizer(wx.VERTICAL)
		item = self.output = wx.TextCtrl(
			self,
			wx.ID_ANY,
			size=(600, 600),
			style=wx.TE_MULTILINE | wx.TE_RICH | wx.TE_READONLY
		)
		item.Bind(wx.EVT_CHAR_HOOK, self.onKeyDownOrCharHook)
		item.Bind(wx.EVT_KEY_DOWN, self.onKeyDownOrCharHook)
		item.Bind(wx.EVT_SET_FOCUS, self.onSetFocus)
		sizer.Add(item)
		self.SetSizerAndFit(sizer)
		self.CenterOnScreen()
		self.Bind(wx.EVT_CLOSE, self.onClose)
	
	def back(self):
		history = self.history
		if not history:
			wx.Bell()
			return
		self.inspect(*history.pop(), back=True)
	
	def backToMark(self):
		if marked is None:
			wx.Bell()
			return
		self.inspect(*marked)
	
	def caret(self):
		mgr = self.mgr
		if mgr is None:
			wx.Bell()
			return
		node = mgr.getCaretNode().parent
		self.inspect(node)
	
	def clear(self):
		self.history.clear()
		self.identifier = None
		self.mgr = None
		self.node = None
		self.root = None
		self.output.SetValue("")
	
	def copyRelativePath(self):
		if self.node is None:
			wx.Bell()
			return
		if marked is None:
			# Translators: An error message from the Element Description dialog
			ui.message(_("First mark an origin node by hitting F9."))
			return
		markedNode, markedRoot, markedIdentifier = marked
		sameMgr = markedNode.nodeManager is self.mgr
		if markedRoot is not self.root:
			markedNode = refresh(markedNode, markedRoot, self.root)
			if markedNode is None:
				if sameMgr:
					# Translators: An error message on the Element Description dialog
					msg =_("The document has been updated.")
				else:
					# Translators: An error message from the Element Description dialog
					msg = _(
						"These nodes do not seem to belong to the same document "
						"or the page has been refreshed."
					)
				ui.message(msg)
				return
		try:
			path = computeRelativePath(markedNode, self.node)
		except Exception:
			log.exception()
			wx.Bell()
			return
		if api.copyToClip(path):
			# A message from the Element Description dialog
			ui.message(_("Relative path copied to clipboard"))
	
	def first(self):
		history = self.history
		if not history:
			wx.Bell()
			return
		self.inspect(*history[0])
	
	def inspect(self, node, root=None, identifier=None, back=False):
		if node is None and self.mgr is None:
			# Translators: An error message shown on the Element Description dialog
			desc = _("Document not supported.")
		elif node is None:
			desc = ""
		else:
			mgr = self.mgr
			if mgr is None:
				mgr = self.mgr = node.nodeManager
			if not back and self.node is not None and self.node is not None:
				self.history.append((self.node, self.root, self.identifier))
			if root is None:
				node, root = snapshot(node)
			if identifier is None:
				identifier = mgr.identifier
			desc = getNodeDescription(node)
			self.node = node
			self.root = root
			self.identifier = identifier
		output = self.output
		output.SetValue(desc)
		if output.HasFocus():
			api.processPendingEvents()
			commands.script_reportCurrentLine(None)
	
	def mark(self):
		if self.node is None:
			wx.Bell()
			return
		global marked
		marked = (self.node, self.root, self.identifier)
		# Translators: A message from the Element Description dialog
		ui.message(_(f"Node marked. Press F10 while inspecting another one to compute their relative path."))
	
	def moveTo(self):
		node = self.node
		if node is None or self.IsModal():
			wx.Bell()
		mgr = self.mgr
		if not mgr.isReady:
			# Translators: An error message from the Element Description dialog
			ui.message(_("Not ready"))
			return
		node = refresh(self.node, self.root, mgr.mainNode)
		if node is None:
			# Translators: An error message on the Element Description dialog
			ui.message(_("The document has been updated."))
			return
		queueHandler.queueFunction(
			queueHandler.eventQueue,
			node.moveto,
			None
		)
		self.Close()
	
	def onKeyDownOrCharHook(self, evt):
		keycode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		modsAlt = mods == wx.MOD_ALT
		modsAltOrNone = (mods | wx.MOD_ALT) == wx.MOD_ALT
		if keycode == wx.WXK_ESCAPE:
			self.Close()
			self.Destroy()
			return
		elif (
			keycode == ord("V") and mods == wx.MOD_CONTROL
			or keycode in (wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT) and mods == wx.MOD_SHIFT
		):
			self.paste()
			return
		elif keycode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and modsAltOrNone:
			self.moveTo()
			return
		elif keycode == wx.WXK_BACK and modsAltOrNone:
			self.back()
			return
		elif keycode == wx.WXK_HOME and modsAlt:
			self.first()
			return
		elif keycode == wx.WXK_END and modsAlt:
			self.caret()
			return
		elif (
			(keycode == ord("U") and modsAltOrNone)
			or (keycode == wx.WXK_UP and modsAlt)
		):
			self.walk("u")
			return
		elif (
			(keycode == ord("D") and modsAltOrNone)
			or (keycode == wx.WXK_DOWN and modsAlt)
		):
			self.walk("d")
			return
		elif (
			(keycode == ord("L") and modsAltOrNone)
			or (keycode == wx.WXK_LEFT and modsAlt)
		):
			self.walk("l")
			return
		elif (
			(keycode == ord("R") and modsAltOrNone)
			or (keycode == wx.WXK_RIGHT and modsAlt)
		):
			self.walk("r")
			return
		elif (
			(keycode == ord("B") and modsAltOrNone)
			or (keycode == wx.WXK_PAGEUP and modsAlt)
		):
			self.walk("b")
			return
		elif (
			(keycode == ord("A") and modsAltOrNone)
			or (keycode == wx.WXK_PAGEDOWN and modsAlt)
		):
			self.walk("a")
			return
		elif keycode == wx.WXK_F9 and mods == wx.MOD_NONE:
			self.mark()
			return
		elif keycode == wx.WXK_F9 and mods == wx.MOD_SHIFT:
			self.backToMark()
			return
		elif keycode == wx.WXK_F10 and mods == wx.MOD_NONE:
			self.copyRelativePath()
			return
		evt.Skip()
	
	def onClose(self, evt):
		self.clear()
		evt.Skip()
	
	def onSetFocus(self, evt):
		# Free the NVDAObject from its conflicting gesture bindings.
		evt.Skip()
		obj = evt.EventObject
		api.processPendingEvents()
		focus = api.getFocusObject()
		if getattr(focus, "windowHandle", None) != obj.Handle:
			return
		from editableText import EditableText
		gestureMap = focus._gestureMap
		for gestureId, func in tuple(gestureMap.items()):
			if (gestureId, func) in (
				("kb:backspace", EditableText.script_caret_backspaceCharacter),
				("kb:alt+downarrow", EditableText.script_caret_nextSentence),
				("kb:alt+uparrow", EditableText.script_caret_previousSentence),
			):
				del gestureMap[gestureId]
	
	def paste(self):
		text = api.getClipData()
		if not self.walk(text):
			# Translators: An error message from the Element Description dialog
			ui.message(_("Unable to walk this path"))
	
	def walk(self, path):
		node = self.node
		if node is None:
			wx.Bell()
			return None
		node = node.walk(path)
		if node is None:
			wx.Bell()
			return False
		self.inspect(node, self.root, self.identifier)
		return True


def show(parent=None, node=None, root=None, identifier=None):
	if node is None:
		focus = gui.mainFrame.prevFocus
		if focus is None:
			root = identifier = None
			focus = api.getFocusObject()
			try:
				mgr = focus.webAccess.nodeManager
			except AttributeError:
				mgr = None
			if mgr is None:
				ti = focus.treeInterceptor
				from ..overlay import WebAccessBmdti
				if isinstance(ti, WebAccessBmdti):
					from ..nodeHandler import NodeManager
					mgr = NodeManager(focus.treeInterceptor)
			if mgr is not None:
				caret = mgr.getCaretNode()
				if caret is not None:
					node = caret.parent
	if parent is None:
		parent = gui.mainFrame
	dlg = ElementDescriptionDialog.getInstance(parent)
	dlg.clear()
	dlg.inspect(node, root, identifier)
	if dlg.IsShown():
		dlg.Raise()
	else:
		if parent is gui.mainFrame:
			gui.mainFrame.prePopup()
			try:
				dlg.Show()
			finally:
				gui.mainFrame.postPopup()
		else:
			dlg.ShowModal()
