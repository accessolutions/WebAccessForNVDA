# globalPlugins/webAccess/gui/inspector.py
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
from baseObject import ScriptableObject
import braille
import controlTypes
import gui
from gui import guiHelper
from logHandler import log
import queueHandler
from scriptHandler import script
import speech
import ui
import vision

from ..utils import getCharFromKeyEvent, guarded
from . import ScalingMixin


addonHandler.initTranslation()



def truncText(text, end=False):
	LENGTH_LIMIT = 30
	WORDS_LIMIT = 5
	if len(text) < LENGTH_LIMIT:
		return text
	words = text.split()
	text = ""
	for word in reversed(words) if end else words:
		if len(text) + len(word) + 1 < LENGTH_LIMIT:
			parts = (text, word)
			if end:
				parts = reversed(parts)
			text = " ".join(parts)
		elif not text and word:
			return word[:LENGTH_LIMIT + 1]
		else:
			break
	return text


def getText(node, truncate=False):
	textList = getTextList(node)
	if not textList:
		return ""
	elif len(textList) == 1:
		return textList[0]
	else:
		desc = "%d %s\r\n" % (
			len(textList),
			pgettext("webAccess.inspector", "elements")
		)
		textFrom = ""
		for text in textList:
			if text:
				textFrom = truncText(text) if truncate else text
				break
		textTo = ""
		for text in textList[::-1]:
			if text:
				textTo = truncText(text, end=True) if truncate else text
				break
		desc += "    {} {}\n".format(
			# Translators: A mention on the Inspector dialog
			pgettext("webAccess.inspector", "from:"),
			textFrom
		)
		desc += "    {} {}".format(
			# Translators: A mention on the Inspector dialog
			pgettext("webAccess.inspector", "to:"),
			textTo
		)
		return desc


def getTextList(node):
	if hasattr(node, "text"):
		return [node.text.strip()]
	elif hasattr(node, "children"):
		textList = []
		for child in node.children:
			textList += getTextList(child)
		return textList
	else:
		return []


def getResultNames(node, root, identifier):
	from ..ruleHandler import DualNodeResult, SingleNodeResult
	nodeMgr = node.nodeManager
	if identifier is None or not node.isReady() or identifier != nodeMgr.identifier:
		return None
	if root != nodeMgr.mainNode:
		node = refresh(node, root, nodeMgr.mainNode)
		if node is None:
			return None
	ruleMgr = nodeMgr.treeInterceptor.webAccess.rootRuleManager
	if ruleMgr is None:
		return None
	names = []
	for result in ruleMgr.iterResultsAtTextInfo(node.getTextInfo()):
		if isinstance(result, SingleNodeResult):
			if result.node == node:
				names.append(result.rule.name)
		elif isinstance(result, DualNodeResult):
			if result.node == node:
				# Translators: A mention on the Inspector dialog
				names.append(_("{rule} (start)").format(rule=result.rule.name))
			if result.endNode == node:
				# Translators: A mention on the Inspector dialog
				names.append(_("{rule} (end)").format(rule=result.rule.name))
	return names


def coalesce(*args):
	if not args:
		raise ValueError
	for arg in args:
		if arg is not None:
			return arg


def getFieldLabels():
	from .rule.criteriaEditor import CriteriaPanel
	labels = {k: v.replace("&", "") for k, v in CriteriaPanel.FIELDS.items()}
	labels["content"] = _("Content:")
	return labels


def getNodeDescription(
	node,
	root=None,
	identifier=None,
	includeAncestors=False,
):
	labels = getFieldLabels()
	parts = []
	while True:
		results = getResultNames(node, root, identifier)
		if (includeAncestors and results) or results is not None:
			# Translators: An item in the Inspector dialog
			parts.append(_("Rules: {}").format(", ".join(results)))
		if not hasattr(node, "tag"):
			parts.append(f"{labels['text']} {getText(node)}")
		else:
			parts.append(f"{labels['tag']} {node.tag}")
			parts.append(f"{labels['role']} {node.role.displayString}")
			if not includeAncestors or node.id is not None:
				parts.append(f"{labels['id']} {coalesce(node.id, '')}")
			if not includeAncestors or node.className:
				parts.append(f"{labels['className']} {coalesce(node.className, '')}")
			states = ", ".join(sorted((
				state.displayString if isinstance(state, controlTypes.State) else str(state)
				for state in node.states
			)))
			if not includeAncestors or states:
				parts.append(f"{labels['states']} {states}")
			if not includeAncestors or node.src:
				parts.append(f"{labels['src']} {coalesce(node.src, '')}")
			try:
				url = node.url
			except AttributeError:
				# This requires an active TreeInterceptor, which might no longer be the case if
				# eg. the document was refreshed.
				pass
			else:
				if not includeAncestors or url:
					parts.append(f"{labels['url']} {coalesce(url, '')}")
			parts.append(f"{labels['content']} {getText(node)}")
		if includeAncestors:
			node = node.parent
			if node is not None:
				parts.append("")
				continue
		break
	return "\n".join(parts)


def computeRelativePath(node1, node2):
	log.info(f"node1: {node1}, node2: {node2}")
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
		raise ValueError("These nodes do not belong to the same document tree.")
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


marked = None
messageOnGainFocus = None
outputWindowHandle = None


class InspectorOutputOverlay(ScriptableObject):
	
	def event_gainFocus(self):
		global messageOnGainFocus
		super().event_gainFocus()
		if messageOnGainFocus is not None:
			speech.cancelSpeech()
			ui.message(messageOnGainFocus)
			messageOnGainFocus = None
	
	@script(gestures=(
			"kb:backspace",
			"kb:alt+downarrow",
			"kb:alt+uparrow",
	))
	def script_pass(self, gesture):
		gesture.send()


class InspectorDialog(ScalingMixin, wx.Dialog):

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
		global outputWindowHandle
		super().__init__(
			parent,
			# Translators: The title for the Inspector dialog
			title=_("Inspect element")
		)
		self.mgr = None
		self.history = []
		self.identifier = None
		self.root = None
		self.node = None
		self.lastNonTextLineNum = None
		self.showAncestors = False
		
		scale = self.scale
		sizer = wx.BoxSizer(wx.VERTICAL)
		item = self.output = wx.TextCtrl(
			self,
			wx.ID_ANY,
			size=scale(750, 320),
			style=wx.TE_MULTILINE | wx.TE_DONTWRAP | wx.TE_RICH2 | wx.TE_READONLY
		)
		outputWindowHandle = item.Handle
		# wx.EVT_CONTEXT_MENU is only triggered with a mouse right click
		# Application/Menu key support is handled via wx.EVT_KEY_DOWN
		item.Bind(wx.EVT_CONTEXT_MENU, self.onContextMenu)
		item.Bind(wx.EVT_KEY_DOWN, self.onKeyDown)
		sizer.Add(item, flag=wx.ALL, border=scale(guiHelper.BORDER_FOR_DIALOGS))
		self.SetSizerAndFit(sizer)
		self.CenterOnScreen()
		self.Bind(wx.EVT_CLOSE, self.onClose)
	
	def ancestor(self):
		if not self.showAncestors:
			wx.Bell()
			return
		output = self.output
		lineNum = output.PositionToXY(output.GetInsertionPoint())[2]
		lineNums = tuple(range(lineNum, output.PositionToXY(output.GetLastPosition())[2] + 1))
		for lineNum in lineNums:
			line = output.GetLineText(lineNum).strip()
			if not line:
				output.SetInsertionPoint(output.XYToPosition(0, lineNum + 1))
				return
		wx.Bell()
	
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
		if mgr is None or not mgr.isReady:
			wx.Bell()
			return
		node = mgr.getCaretNode()
		if not getResultNames(node, mgr.mainNode, mgr.identifier):
			node = node.parent
		self.inspect(node)
	
	def clear(self):
		self.history.clear()
		self.identifier = None
		self.mgr = None
		self.node = None
		self.root = None
		self.output.Clear()
		self.lastNonTextLineNum = None
	
	def copyRelativePath(self):
		if self.node is None:
			wx.Bell()
			return
		if marked is None:
			# Translators: An error message from the Inspector dialog
			self.message(_("First mark an origin node by hitting F9."))
			return
		markedNode, markedRoot, markedIdentifier = marked
		sameMgr = markedNode.nodeManager is self.mgr
		if markedRoot is not self.root:
			markedNode = refresh(markedNode, markedRoot, self.root)
			if markedNode is None:
				if sameMgr:
					# Translators: An error message on the Inspector dialog
					msg =_("The document has been updated.")
				else:
					# Translators: An error message from the Inspector dialog
					msg = _(
						"These nodes do not seem to belong to the same document "
						"or the page has been refreshed."
					)
				self.message(msg)
				return
		try:
			path = computeRelativePath(markedNode, self.node)
		except Exception:
			log.exception()
			wx.Bell()
			return
		if api.copyToClip(path):
			# A message from the Inspector dialog
			self.message(_("Relative path copied to clipboard"))
	
	def descendant(self):
		if not self.showAncestors:
			wx.Bell()
			return
		output = self.output
		lineNum = output.PositionToXY(output.GetInsertionPoint())[2]
		foundBreak = False
		for lineNum in range(lineNum, -1, -1):
			line = output.GetLineText(lineNum).strip()
			if not line and not foundBreak:
				foundBreak = True
				continue
			if foundBreak and (not line or lineNum == 0):
				if lineNum > 0:
					lineNum += 1
				output.SetInsertionPoint(output.XYToPosition(0, lineNum))
				return
		wx.Bell()
	
	def first(self):
		history = self.history
		if not history:
			wx.Bell()
			return
		self.inspect(*history[0])
	
	def initial(self, char):
		output = self.output
		lineNums = tuple(range(output.PositionToXY(output.GetLastPosition())[2] + 1))
		lineNum = output.PositionToXY(output.GetInsertionPoint())[2] + 1
		if self.showAncestors:
			lineNums = lineNums[lineNum:]
		else:
			lineNums = lineNums[lineNum:] + lineNums[:lineNum]
		for lineNum in lineNums:
			line = output.GetLineText(lineNum).strip()
			if line and line[0].casefold() == char.casefold():
				output.SetInsertionPoint(output.XYToPosition(0, lineNum))
				speech.speakMessage(line)
				return
		wx.Bell()
	
	def inspect(self, node, root=None, identifier=None, back=False):
		showAncestors = self.showAncestors
		output = self.output
		if showAncestors:
			lineNum = 0
			self.lastNonTextLineNum = None
		else:
			lineNum = output.PositionToXY(output.GetInsertionPoint())[2]
			if hasattr(self.node, "tag"):
				self.lastNonTextLineNum = lineNum
			elif hasattr(node, "tag") and self.lastNonTextLineNum is not None:
				lineNum = self.lastNonTextLineNum
		if node is None and self.mgr is None:
			# Translators: An error message shown on the Inspector dialog
			desc = _("Document not supported.")
		elif node is None:
			desc = ""
		else:
			mgr = self.mgr
			if mgr is None:
				mgr = self.mgr = node.nodeManager
			if not back and self.node is not None:
				self.history.append((self.node, self.root, self.identifier))
			if root is None:
				node, root = snapshot(node)
			if identifier is None:
				identifier = mgr.identifier
			desc = getNodeDescription(
				node, root, identifier, showAncestors
			)
			self.node = node
			self.root = root
			self.identifier = identifier
		output.SetValue(desc)
		lastLineNum = output.PositionToXY(output.GetLastPosition())[2]
		lineNum = min(lineNum, lastLineNum)
		output.SetInsertionPoint(output.XYToPosition(0, lineNum))
		if output.HasFocus():
			api.processPendingEvents()
			msg = output.GetLineText(lineNum)
			if not showAncestors and hasattr(node, "tag"):
				labels = getFieldLabels()
				if msg.startswith(labels["content"]):
					msg = f"{labels['content']} {getText(node, truncate=True)}"
				if not msg.startswith(labels["tag"]):
					msg = f"{node.tag}, {msg}"
			speech.speakMessage(msg)
			api.processPendingEvents()
			focus = api.getFocusObject()
			braille.handler.handleUpdate(focus)
			vision.handler.handleUpdate(focus, property="value")
	
	def mark(self):
		if self.node is None:
			wx.Bell()
			return
		global marked
		marked = (self.node, self.root, self.identifier)
		self.message(
			# Translators: A message from the Inspector dialog
			_(f"Node marked. Press F10 while inspecting another one to compute their relative path."),
		)
	
	def message(self, message):
		global messageOnGainFocus
		if api.getFocusObject().role == controlTypes.Role.MENUITEM:
			messageOnGainFocus = message
		else:
			ui.message(message)
	
	def moveTo(self):
		node = self.node
		if node is None or self.IsModal():
			wx.Bell()
			return
		mgr = self.mgr
		if not mgr.isReady:
			# Translators: An error message from the Inspector dialog
			self.message(_("Not ready"))
			return
		node = refresh(self.node, self.root, mgr.mainNode)
		if node is None:
			# Translators: An error message on the Inspector dialog
			self.message(_("The document has been updated."))
			return
		queueHandler.queueFunction(
			queueHandler.eventQueue,
			node.moveto,
			None
		)
		self.Close()
		self.Destroy()
	
	def onClose(self, evt):
		global outputWindowHandle
		self.clear()
		outputWindowHandle = None
		evt.Skip()
	
	def onContextMenu(self, evt=None):
		if self.node is None:
			evt.Skip()
			return
		menu = wx.Menu()
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Move to this position on the document\tEnter")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.moveTo(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Parent node\tAlt + Up Arrow or Alt + U")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.walk("u"), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("First child node\tAlt + Down Arrow or Alt + D")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.walk("d"), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Previous sibling node\tAlt + Left Arrow or Alt + L")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.walk("l"), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Next sibling node\tAlt + Right Arrow or Alt + R")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.walk("r"), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Previous node in document order\tAlt + Page Up or Alt + B")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.walk("b"), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Next node in document order\tAlt + Page Down or Alt + A")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.walk("a"), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Previous node in history\tBackspace or Alt + Backspace")
		)
		if not self.history:
			item.Enable(False)
		menu.Bind(wx.EVT_MENU, lambda evt: self.back(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("First node in history\tAlt + Home")
		)
		if not self.history:
			item.Enable(False)
		menu.Bind(wx.EVT_MENU, lambda evt: self.first(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Node at current reading position on the document\tAlt + End")
		)
		if not self.history:
			item.Enable(False)
		menu.Bind(wx.EVT_MENU, lambda evt: self.caret(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Mark node\tF9")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.mark(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Back to marked node\tShift + F9")
		)
		if marked is None:
			item.Enable(False)
		menu.Bind(wx.EVT_MENU, lambda evt: self.backToMark(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Compute relative path from marked node\tF10")
		)
		if marked is None:
			item.Enable(False)
		menu.Bind(wx.EVT_MENU, lambda evt: self.copyRelativePath(), item)
		item = menu.Append(
			wx.ID_ANY,
			# Translators: A context menu entry on the Inspector dialog
			_("Walk the relative path stored in the clipboard\tControl + V or Shift + Insert")
		)
		menu.Bind(wx.EVT_MENU, lambda evt: self.paste(), item)
		self.output.PopupMenu(menu)
		menu.Destroy()
	
	def onKeyDown(self, evt):
		keyCode = evt.GetKeyCode()
		mods = evt.GetModifiers()
		modsAlt = mods == wx.MOD_ALT
		if keyCode == wx.WXK_ESCAPE:
			self.Close()
			self.Destroy()
			return
		elif (keyCode == wx.WXK_WINDOWS_MENU and mods == wx.MOD_NONE):
			self.onContextMenu()
			return
		elif (
			keyCode == ord("V") and mods == wx.MOD_CONTROL
			or keyCode in (wx.WXK_INSERT, wx.WXK_NUMPAD_INSERT) and mods == wx.MOD_SHIFT
		):
			self.paste()
			return
		elif keyCode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and mods == wx.MOD_NONE:
			self.moveTo()
			return
		elif keyCode == wx.WXK_BACK and mods | wx.MOD_ALT == wx.MOD_ALT:
			self.back()
			return
		elif keyCode == wx.WXK_F5 and mods == wx.MOD_NONE:
			self.refresh()
			return
		elif keyCode == wx.WXK_F9 and mods == wx.MOD_NONE:
			self.mark()
			return
		elif keyCode == wx.WXK_F9 and mods == wx.MOD_SHIFT:
			self.backToMark()
			return
		elif keyCode == wx.WXK_F10 and mods == wx.MOD_NONE:
			self.copyRelativePath()
			return
		elif keyCode == wx.WXK_F12 and mods == wx.MOD_NONE:
			self.switchView()
			return
		elif mods == wx.MOD_ALT:
			if keyCode == wx.WXK_HOME:
				self.first()
				return
			elif keyCode == wx.WXK_END:
				self.caret()
				return
			elif keyCode in (wx.WXK_UP, wx.WXK_NUMPAD_UP, ord("U")):
				self.walk("u")
				return
			elif keyCode in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN, ord("D")):
				self.walk("d")
				return
			elif keyCode in (wx.WXK_LEFT, wx.WXK_NUMPAD_LEFT, ord("L")):
				self.walk("l")
				return
			elif keyCode in (wx.WXK_RIGHT, wx.WXK_NUMPAD_RIGHT, ord("R")):
				self.walk("r")
				return
			elif keyCode in (wx.WXK_PAGEUP, ord("B")):
				self.walk("b")
				return
			elif keyCode in (wx.WXK_PAGEDOWN, ord("A")):
				self.walk("a")
				return
		elif self.showAncestors and mods == wx.MOD_CONTROL:
			if keyCode in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
				self.descendant()
				return
			if keyCode in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
				self.ancestor()
				return
		char = getCharFromKeyEvent(evt)
		if char is not None and char > " ":  # First printable character
			self.initial(char)
			return
		evt.Skip()
	
	def paste(self):
		text = api.getClipData()
		if not self.walk(text):
			# Translators: An error message from the Inspector dialog
			self.message(_("Unable to walk this path"))
	
	def refresh(self):
		node = self.node
		if node is None or not node.isReady():
			wx.Bell()
			return
		self.inspect(refresh(node, self.root, self.mgr.mainNode), back=True)
	
	def switchView(self):
		showAncestors = self.showAncestors = not self.showAncestors
		if showAncestors:
			# Translators: A message from the Inspector dialog
			self.message(_("Show all ancestors"))
		else:
			# Translators: A message from the Inspector dialog
			self.message(_("Show single element"))
		self.inspect(self.node, self.root, self.identifier)
	
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
				node = mgr.getCaretNode()
				if node is not None and not getResultNames(node, mgr.mainNode, mgr.identifier):
					node = node.parent
	if parent is None:
		parent = gui.mainFrame
	dlg = InspectorDialog.getInstance(parent)
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
