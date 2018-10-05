# globalPlugins/webAccess/nodeHandler.py
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

__version__ = "2018.09.13"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>, Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import Queue
import time
import weakref
import winUser
import wx
import api
import baseObject
import NVDAHelper
from xml.parsers import expat
import mouseHandler
import sayAllHandler
import ui

from .webAppLib import *
import gc


REASON_FOCUS = 0
REASON_NAVIGATION = 1
REASON_SHORTCUT = 2
_count = 0
countNode = 0
nodeManagerIndex = 0

class NodeManager(baseObject.ScriptableObject):
	
	def __init__(self, treeInterceptor, callbackNodeMoveto=None):
		super(NodeManager, self).__init__()
		global nodeManagerIndex
		nodeManagerIndex = nodeManagerIndex + 1
		self.index = nodeManagerIndex
		self._ready = False
		self.identifier = None 
		self.backendDict = {}
		if treeInterceptor is None:
			log.info (u"nodeManager created with none treeInterceptor")
			return
		self.treeInterceptor = treeInterceptor
		self.treeInterceptorSize = 0
		self.mainNode = None
		self.devNode = None
		self.callbackNodeMoveto = callbackNodeMoveto
		self.updating = False
		self.update()
		
	def terminate (self):
		for backend in self.backendDict:
			backend.event_nodeManagerTerminated (self)
		self._ready = False
		self.treeInterceptor = None
		self.treeInterceptorSize = 0
		if self.mainNode is not None:
			self.mainNode.recursiveDelete ()
		self.mainNode = None
		self.devNode = None
		self.callbackNodeMoveto = None
		self.updating = False
		self._curNode = self.caretNode = None
		
	def formatAttributes (self, attrs):
		s = ""
		for a in attrs:
			s = s + "     %s: %s\n" % (a, attrs[a])
		return s

	def _startElementHandler(self,tagName,attrs):
		#s = self.formatAttributes(attrs)
		#log.info (u"start : %s attrs : %s" % (tagName, s))
		if tagName=='unich':
			data=attrs.get('value',None)
			if data is not None:
				try:
					data=unichr(int(data))
				except ValueError:
					data=u'\ufffd'
				self._CharacterDataHandler(data)
			return
		elif tagName=='control':
			attrs = self.info._normalizeControlField (attrs)
			node = NodeField("control", attrs, self.currentParentNode, self.fieldOffset, self)
		elif tagName=='text':
			node = NodeField("format", attrs, self.currentParentNode, self.fieldOffset, self)
		else:
			raise ValueError("Unknown tag name: %s"%tagName)
		self.currentParentNode = node
		if self.mainNode is None:
			self.mainNode = node

	def _EndElementHandler(self,tagName):
		#log.info (u"end : %s" % tagName)
		if tagName=='unich':
			pass
		elif tagName in ("control", "text"):
			parent = self.currentParentNode.parent
			if parent is not None:
				parent.size += self.currentParentNode.size
			self.currentParentNode = parent
		else:
			raise ValueError("unknown tag name: %s"%tagName)

	def _CharacterDataHandler(self,data):
		#log.info (u"text : %s" % data)
		p = self.currentParentNode
		if not hasattr (p, "format"):
			raise
		p.size = len(data)
		p.text = data
		self.fieldOffset += p.size
		self.lastTextNode = p
		return
		if cmdList and isinstance(cmdList[-1],basestring):
			cmdList[-1]+=data
		else:
			cmdList.append(data)


	def parseXML(self, XMLText):
		parser=expat.ParserCreate('utf-8')
		parser.StartElementHandler=self._startElementHandler
		parser.EndElementHandler=self._EndElementHandler
		parser.CharacterDataHandler=self._CharacterDataHandler
		self.currentParentNode = None
		self.fieldOffset = 0
		self.lastTextNode = None
		self.mainNode = None
		parser.Parse(XMLText.encode('utf-8'))
	def afficheNode (self, node, level=0):
		if node is None:
			return ""
		indentation = ""
		for i in range (0, level):
			indentation += "  "
		if hasattr (node, "text"):
			s = node.text
		elif hasattr (node, "control"):
			s = node.tag
		elif hasattr (node, "format"):
			s = "format"
		else:
			s = "inconnu"
		s = indentation + s + "\n"
		for child in node.children:
			s += self.afficheNode (child, level + 1)
		return s
			
	def update(self):
		t = logTimeStart ()
		if self.treeInterceptor is None or not self.treeInterceptor.isReady:
			self._ready = False
			return False
		try:
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_LAST)
		except:
			self._ready = False
			return False
		try:
			size = info._endOffset+1
		except:
			self._ready = False
			return False
		if size == self.treeInterceptorSize:
			# probably not changed
			return False
		self.treeInterceptorSize = size
		if True:
			self.updating = True
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_ALL)
			self.info = info
			start=info._startOffset
			end=info._endOffset
			if start==end:
				self._ready = False
				return False
			text=NVDAHelper.VBuf_getTextInRange(info.obj.VBufHandle,start,end,True)
			if self.mainNode is not None:
				self.mainNode.recursiveDelete ()
			self.parseXML (text)
			#logTime ("Update node manager %d, text=%d" % (self.index, len(text)), t)
			self.info = None
			gc.collect ()
		else:
			self.updating = False
			self._ready = False
			log.info (u"reading vBuff error")
			return False
		#self.info = info
		if self.mainNode is None:
			self.updating = False
			self._ready = False
			return False
		self.identifier = time.time()
		#logTime ("Update node manager %d nodes" % len(fields), t)
		self.updating = False
		#playWebAppSound ("tick")
		self._curNode = self.caretNode = self.getCaretNode()
		try:
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_LAST)
		except:
			self._ready = False
			return False
		size = info._endOffset+1
		from . import webAppScheduler
		if size != self.treeInterceptorSize:
			# treeInterceptor has changed during analyze
			self._ready = False
			webAppScheduler.scheduler.send (eventName="updateNodeManager", treeInterceptor=self.treeInterceptor)
			return False
		else:
			self._ready = True
			webAppScheduler.scheduler.send (eventName="nodeManagerUpdated", nodeManager=self)
			return True
		return False

	def _get_isReady (self):
		if not self._ready or not self.treeInterceptor or not self.treeInterceptor.isReady:
			return False
		return True

	def addBackend (self, obj):
		self.backendDict[obj] = 1
	def searchString(self, text):
		if not self.isReady:
			return []
		return self.mainNode.searchString (text)

	def searchNode(self, **kwargs):
		if not self.isReady:
			return []
		t = logTimeStart ()
		global _count 
		_count = 0
		r = self.mainNode.searchNode (**kwargs)
		#logTime (u"search %d node %s " % (_count, kwargs), t)
		return r

	def searchOffset (self, offset):
		if not self.isReady:
			return None
		node = self.devNode if self.devNode else self.mainNode
		return node.searchOffset (offset)
	
	def getCaretNode(self):
		"""
		Returns the node on which the caret is currently placed.
		@param None
		@returns a valid node if Found, None oterwise
		@rtype NodeField
		"""
		if not self.isReady:
			return None
		try:
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
			return self.searchOffset (info._startOffset)
		except:
			return None

	def getCurrentNode(self):
		if not self.isReady:
			return None
		if self._curNode is None:
			self._curNode = getCaretNode()
		return self._curNode

	def setCurrentNode(self, node):
		if hasattr(node, 'control') is False:
			self._curNode = node.parent
		else:
			self._curNode = node

	def event_caret(self, obj, nextHandler):
		if not self.isReady:
			return
		self.display(self._curNode)
		nextHandler()
		
	def script_nextItem(self, gesture):
		if not self.isReady:
			return
		if self.treeInterceptor.passThrough is True:
			gesture.send()
			return
		c = self.searchOffset(self._curNode.offset + self._curNode.size + 0)
		if c == self._curNode or c is None:
			ui.message(u"Bas du document")
			self._curNode.moveto()
			return
		if c.parent.role not in (controlTypes.ROLE_SECTION, controlTypes.ROLE_PARAGRAPH):
			c = c.parent
		# log.info("C set to %s" % c)
		self._curNode = c
		c.moveto()

	def script_previousItem(self, gesture):
		if not self.isReady:
			return
		if self.treeInterceptor.passThrough is True:
			gesture.send()
			return
		c = self.searchOffset(self._curNode.offset - 1)
		# log.info("C is %s" % c)
		if c is None:
			ui.message(u"Début du document")
			self._curNode.moveto()
			return
		if c.parent.role not in (controlTypes.ROLE_SECTION, controlTypes.ROLE_PARAGRAPH):
			c = c.parent
		# log.info("C set to %s" % c)
		self._curNode = c
		c.moveto()

	def script_enter(self, gesture):
		if not self.isReady:
			return
		if self.treeInterceptor.passThrough is True:
			gesture.send()
			return
		self._curNode.moveto()
		self._curNode.activate()
		
		

	__gestures = {
		"kb:downarrow": "nextItem",
		"kb:uparrow": "previousItem",
		"kb:enter": "enter",
		}
	
class NodeField (baseObject.AutoPropertyObject):
	customText = ""
	
	def __init__(self, nodeType, attrs, parent, offset, nodeManager):
		super(NodeField, self).__init__()
		self.nodeManager = nodeManager
		self.parent = parent
		self.offset = offset
		self.size = 0
		self.children = []
		if nodeType == "text":
			self.size = len(attrs)
			self.text = attrs
			self.customText = attrs
			self.controlIdentifier = parent.controlIdentifier
			self.role = parent.role
		elif nodeType == "format":
			self.format = attrs
			self.controlIdentifier = 0
			self.role = 0
		elif nodeType == "control":
			self.control = attrs
			self.name = self.control.get("name", "")
			self.role = self.control["role"]
			self.controlIdentifier = self.control.get ("controlIdentifier_ID", 0)
			self.tag = self.control["IAccessible2::attribute_tag"] if "IAccessible2::attribute_tag" in self.control else None
			if not self.tag:
				self.tag = self.control["IHTMLDOMNode::nodeName"] if "IHTMLDOMNode::nodeName" in self.control else ""
			self.id = self.control["IAccessible2::attribute_id"] if "IAccessible2::attribute_id" in self.control else None
			if not self.id:
				self.id = self.control["HTMLAttrib::id"] if "HTMLAttrib::id" in self.control else ""

			self.className = self.control.get("IAccessible2::attribute_class", "")
			if not self.className:
				self.className = self.control.get("HTMLAttrib::class", "")
			if not self.className:
				self.className = self.control.get("HTMLAttrib::className", "")
			self.src = self.control["IAccessible2::attribute_src"] if "IAccessible2::attribute_src" in self.control else None
			if not self.src:
				self.src = self.control["HTMLAttrib::src"] if "HTMLAttrib::src" in self.control else ""
			self.children = []
		else:
			raise
		self.previousTextNode = nodeManager.lastTextNode
		if parent is not None:
			parent.children.append (self)
		global countNode
		countNode = countNode + 1

	def __del__ (self):
		#log.info (u"dell node")
		global countNode
		countNode = countNode - 1
		
	def __repr__ (self):
		if hasattr (self, "text"):
			return u"Node text : %s" % self.text
		elif hasattr (self, "control"):
			return u"Node %s : id=%s, className=%s" % (self.tag, self.id, self.className)
		elif hasattr (self, "format"):
			return u"Node format"
		else:
			return u"Node unknown"
		
	def isReady (self):
		return self.nodeManager is not None and self.nodeManager.isReady
	
	def checkNodeManager (self):
		if self.nodeManager is None or not self.nodeManager.isReady:
			playWebAppSound ("keyError")
			return False
		else:
			return True
		
	def recursiveDelete (self):
		n = 1
		if hasattr (self, "children"):
			for child in self.children:
				n = n + child.recursiveDelete ()
			self.children = []
		self.nodeManager = None
		self.previousTextNode = None
		self.parent = None
		self.format = None
		self.control = None
		self.text = None
		self.customText = None
		self.controlIdentifier = None
		return n


	def searchString (self, text):
		if not isinstance (text, list):
			text = [text]
		if hasattr (self, "text"):
			for t in text:
				if t in self.text:
					return [self]
			return []
		elif hasattr (self, "children"):
			result = []
			for child in self.children:
				result += child.searchString (text)
			return result
		return []

	def search_eq (self, itemList, value):
		if not isinstance (itemList, list):
			itemList = [itemList]
		for item in itemList:
			if item == value:
				return True
		return False
	
	def search_in (self, itemList, value):
		if value is None or value == "":
			return False
		if not isinstance (itemList, list):
			itemList = [itemList]
		for item in itemList:
			if item.replace ("*", "") in value:
				return True
		return False

	def searchNode (self, **kwargs):
		global _count
		nodeList = []
		_count += 1
		if hasattr (self, "control"):
			found = True
			for key in kwargs.keys(): 
				if key[:3] == "eq_": 
					if self.search_eq (kwargs[key], getattr (self, key[3:], None)):
						del kwargs[key]
					elif key != "eq_text":
						found = False
				if key[:3] == "in_": 
					if self.search_in (kwargs[key], getattr (self, key[3:], None)):
						del kwargs[key]
					elif key != "in_text":
						found = False
				if key[:6] == "notEq_": 
					if self.search_eq (kwargs[key], getattr (self, key[6:], None)):
						return []
				if key[:6] == "notIn_": 
					if self.search_in (kwargs[key], getattr (self, key[6:], None)):
						return []
			if found:
				text = kwargs.get ("eq_text", []) 
				prevText = kwargs.get ("prev_text", "") 
				if text != []:
					return self.searchString (text)
				elif prevText != "":
					if self.previousTextNode is not None and prevText in self.previousTextNode.text:
						return [self]
					else:
						return []
				else:
					return [self]
			for child in self.children:
				nodeList += child.searchNode (**kwargs)
		return nodeList

	def searchOffset (self, offset):
		if hasattr (self, "text"):
			if offset >= self.offset and offset < self.offset + self.size: 
				return self
		elif hasattr (self, "children"):
			for child in self.children:
				node = child.searchOffset (offset)
				if node:
					return node
		return None
	
	def firstTextNode(self):
		return self.searchOffset(self.offset)

	def nextTextNode(self):
		return self.nodeManager.searchOffset (self.offset + self.size)
	
	def moveto(self, reason=REASON_FOCUS):
		if not self.checkNodeManager ():
			return False 
		info = self.nodeManager.treeInterceptor.makeTextInfo(textInfos.offsets.Offsets(self.offset, self.offset))
		self.nodeManager.treeInterceptor.selection = info
		if self.nodeManager.callbackNodeMoveto is not None:
			#beep ()
			# log.info("node calls onMoveTo")
			self.nodeManager.callbackNodeMoveto(self, reason)
		return True
		
	def activate (self):
		if not self.checkNodeManager ():
			return False 
		info = self.getTextInfo ()
		self.nodeManager.treeInterceptor._activatePosition (info)

	def sayAll (self):
		if self.moveto ():
			sayAllHandler.readText(sayAllHandler.CURSOR_CARET)
			return True
		else:
			return False

	def getNVDAObject(self):
		info = self.getTextInfo ()
		obj = info.NVDAObjectAtStart
		return obj

	def mouseMove (self):
		if not self.checkNodeManager ():
			return False 
		self.moveto () 
		info = self.getTextInfo ()
		obj = info.NVDAObjectAtStart
		try:
			(left,top,width,height)=obj.location
		except:
			ui.message (u"Impossible de déplacer la souris à cet emplacement")
			return False
		x=left+(width/2)
		y=top+(height/2)
		winUser.setCursorPos(x,y)
		mouseHandler.executeMouseMoveEvent(x,y)

	def getPresentationString(self):
		"""Returns the current node text and role for speech and Braille.
		@param None
		@returns a presentation string
		@rtype str
		"""
		if hasattr(self, 'text'):
			return self.text
		elif self.role is controlTypes.ROLE_EDITABLETEXT:
			return u"_name_ _role_"
		elif self.role is controlTypes.ROLE_HEADING:
			return u"_innerText_ _role_ de niveau %s" % self.control["level"]
		return u"_innerText_ _role_"
		
	def getBraillePresentationString(self):
		return False
	
				
	def __eq__(self, node):
		if node is None:
			return False
		if self.offset == node.offset:
			return True
		return False

	def __lt__(self, node):
		if self.offset < node.offset:
			return True
		return False

	def __contains__(self, node):
		if self == node:
			return True
		if hasattr(self, "children"):
			for ch in self.children:
				if ch == node:
					return True
		return False

	def __len__(self):
		return self.size
	
	def _get_innerText (self):
		txt = ""
		if hasattr (self, "text"):
			txt = self.text
			try:
				txt = self.customText
			except:
				pass
		log.info("Txt is %s" % txt)
		if len(txt) > 0:
			if not txt.endswith('\n'):
				txt += " "
			return txt
 		if hasattr (self, "children"):
			for child in self.children:
				txt += child._get_innerText()
			return txt
		return ""

	def getTextInfo (self):
		if not self.isReady ():
			return None 
		return self.nodeManager.treeInterceptor.makeTextInfo(textInfos.offsets.Offsets(self.offset, self.offset+self.size))

	def getTreeInterceptorText (self):
		info = self.getTextInfo ()
		if info:
			return info.text
		else:
			return "" 
