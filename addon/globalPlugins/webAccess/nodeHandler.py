# globalPlugins/webAccess/nodeHandler.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2020 Accessolutions (http://accessolutions.fr)
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

__version__ = "2020.10.26"
__authors__ = (
	u"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
)


import gc
import re
import time
from xml.parsers import expat
import weakref

import baseObject
import controlTypes
from logHandler import log
import mouseHandler
import NVDAHelper
import sayAllHandler
import textInfos
import treeInterceptorHandler
import ui
import winUser

from .webAppLib import *


try:
	from six import unichr
except ImportError:
	# NVDA version < 2018.3	
	pass

try:
	from ast import literal_eval
except ImportError:
	# NVDA < 2018.4
	from .ast import literal_eval

try:
	from garbageHandler import TrackedObject	
except ImportError:
	# NVDA < 2020.3
	TrackedObject = object


TRACE = lambda *args, **kwargs: None  # noqa: E731
# TRACE = log.info  # noqa: E731
# TRACE = lambda *args, **kwargs: trace.append((args, kwargs))  # noqa: E731
# trace = []


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
		self.backends = weakref.WeakSet()
		self.treeInterceptor = treeInterceptor
		self.treeInterceptorSize = 0
		self.mainNode = None
		self._lastTextNode = None
		self.devNode = None
		self.callbackNodeMoveto = None
		self.updating = False
		if treeInterceptor is None:
			log.info(u"nodeManager created with none treeInterceptor")
			return
		self.callbackNodeMoveto = callbackNodeMoveto
		self.update()
	
	def _get_treeInterceptor(self):
		if hasattr(self, "_treeInterceptor"):
			ti = self._treeInterceptor
			if isinstance(ti, weakref.ReferenceType):
				ti = ti()
			if ti and ti in treeInterceptorHandler.runningTable:
				return ti
			else:
				self._treeInterceptor = None
				return None
	
	def _set_treeInterceptor(self, obj):
		if obj:
			self._treeInterceptor = weakref.ref(obj)
		else:
			self._treeInterceptor = None
	
	def _get_lastTextNode(self):
		return self._lastTextNode and self._lastTextNode()
	
	def _set_lastTextNode(self, value):
		self._lastTextNode = weakref.ref(value) if value is not None else None
	
	def _get_currentParentNode(self):
		return self._currentParentNode and self._currentParentNode()
	
	def _set_currentParentNode(self, value):
		self._currentParentNode = weakref.ref(value) if value is not None else None
	
	def terminate(self):
		for backend in self.backends:
			backend.event_nodeManagerTerminated(self)
		self._ready = False
		self.treeInterceptor = None
		self.treeInterceptorSize = 0
		if self.mainNode is not None:
			self.mainNode.recursiveDelete()
		self.mainNode = None
		self.devNode = None
		self.callbackNodeMoveto = None
		self.updating = False
		self._curNode = self.caretNode = None
		
	def formatAttributes(self, attrs):
		s = ""
		for a in attrs:
			s = s + "     %s: %s\n" % (a, attrs[a])
		return s

	def _startElementHandler(self, tagName, attrs):
		TRACE(
			u"_startElementHandler(tagName={}, attrs={})".format(
				tagName, attrs)
		)
		# s = self.formatAttributes(attrs)
		# log.info (u"start : %s attrs : %s" % (tagName, s))
		if tagName == 'unich':
			data = attrs.get('value', None)
			if data is not None:
				try:
					data = unichr(int(data))
				except ValueError:
					data = u'\ufffd'
				self._CharacterDataHandler(data)
			return
		elif tagName == 'control':
			attrs = self.info._normalizeControlField(attrs)
			node = NodeField(
				nodeType="control",
				attrs=attrs,
				parent=self.currentParentNode,
				offset=self.fieldOffset,
				nodeManager=self
			)
		elif tagName == 'text':
			node = NodeField(
				nodeType="format",
				attrs=attrs,
				parent=self.currentParentNode,
				offset=self.fieldOffset,
				nodeManager=self
			)
		else:
			raise ValueError("Unknown tag name: %s" % tagName)
		self.currentParentNode = node
		if self.mainNode is None:
			self.mainNode = node

	def _EndElementHandler(self, tagName):
		TRACE(u"_EndElementHandler(tagName={})".format(tagName))
		if tagName == 'unich':
			pass
		elif tagName in ("control", "text"):
			parent = self.currentParentNode.parent
			if parent is not None:
				parent.size += self.currentParentNode.size
			self.currentParentNode = parent
		else:
			raise ValueError("unknown tag name: %s" % tagName)

	def _CharacterDataHandler(self, data):
		TRACE(u"_CharacterDataHandler(data={})".format(data))
		p = self.currentParentNode
		if not hasattr(p, "format"):
			raise
		size = len(data)
		p.size += size
		p.text = data
		self.fieldOffset += size
		self.lastTextNode = p

	def parseXML(self, XMLText):
		parser = expat.ParserCreate('utf-8')
		parser.StartElementHandler = self._startElementHandler
		parser.EndElementHandler = self._EndElementHandler
		parser.CharacterDataHandler = self._CharacterDataHandler
		self.currentParentNode = None
		self.fieldOffset = 0
		self.lastTextNode = None
		self.mainNode = None
		# trace[:] = []
		parser.Parse(XMLText.encode('utf-8'))
	
	def afficheNode(self, node, level=0):
		if node is None:
			return ""
		indentation = ""
		for unused in range(0, level):
			indentation += "  "
		if hasattr(node, "text"):
			s = node.text
		elif hasattr(node, "control"):
			s = node.tag
		elif hasattr(node, "format"):
			s = "format"
		else:
			s = "inconnu"
		s = indentation + s + "\n"
		for child in node.children:
			s += self.afficheNode(child, level + 1)
		return s
			
	def update(self):
		# t = logTimeStart()
		if self.treeInterceptor is None or not self.treeInterceptor.isReady:
			self._ready = False
			return False
		try:
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_LAST)
		except:
			self._ready = False
			return False
		try:
			size = info._endOffset + 1
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
			start = info._startOffset
			end = info._endOffset
			if start == end:
				self._ready = False
				return False
			text = NVDAHelper.VBuf_getTextInRange(
				info.obj.VBufHandle, start, end, True)
			if self.mainNode is not None:
				self.mainNode.recursiveDelete()
			self.parseXML(text)
			# logTime("Update node manager %d, text=%d" % (self.index, len(text)), t)
			self.info = None
			gc.collect()
		else:
			self.updating = False
			self._ready = False
			log.info(u"reading vBuff error")
			return False
		# self.info = info
		if self.mainNode is None:
			self.updating = False
			self._ready = False
			return False
		self.identifier = time.time()
		# logTime ("Update node manager %d nodes" % len(fields), t)
		self.updating = False
		# playWebAppSound ("tick")
		self._curNode = self.caretNode = self.getCaretNode()
		try:
			info = self.treeInterceptor.makeTextInfo(textInfos.POSITION_LAST)
		except:
			self._ready = False
			return False
		size = info._endOffset + 1
		from . import webAppScheduler
		if size != self.treeInterceptorSize:
			# treeInterceptor has changed during analyze
			self._ready = False
			webAppScheduler.scheduler.send(
				eventName="updateNodeManager",
				treeInterceptor=self.treeInterceptor
			)
			return False
		else:
			self._ready = True
			webAppScheduler.scheduler.send(
				eventName="nodeManagerUpdated",
				nodeManager=self
			)
			return True
		return False

	def _get_isReady(self):
		if (
			not self._ready
			or not self.treeInterceptor
			or not self.treeInterceptor.isReady
		):
			return False
		return True

	def addBackend(self, obj):
		self.backends.add(obj)
	
	def searchString(self, text):
		if not self.isReady:
			return []
		return self.mainNode.searchString(text)

	def searchNode(self, roots=None, exclude=None, **kwargs):
		if not self.isReady:
			return []
		# t = logTimeStart()
		global _count
		_count = 0
		r = []
		for node in roots or (self.mainNode,):
			if exclude and node in exclude:
				continue
			r += node.searchNode(exclude=exclude, **kwargs)
		# logTime(u"search %d node %s " % (_count, kwargs), t)
		return r

	def searchOffset(self, offset):
		if not self.isReady:
			return None
		node = self.devNode if self.devNode else self.mainNode
		return node.searchOffset(offset)
	
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
			return self.searchOffset(info._startOffset)
		except:
			return None

	def getCurrentNode(self):
		if not self.isReady:
			return None
		if self._curNode is None:
			self._curNode = self.getCaretNode()
		return self._curNode

	def setCurrentNode(self, node):
		if hasattr(node, 'control') is False:
			self._curNode = node.parent
		else:
			self._curNode = node

	def event_caret(self, obj, nextHandler):  # @UnusedVariable
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
		if c.parent.role not in (
			controlTypes.ROLE_SECTION, controlTypes.ROLE_PARAGRAPH
		):
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
		if c.parent.role not in (
			controlTypes.ROLE_SECTION, controlTypes.ROLE_PARAGRAPH
		):
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


class NodeField(TrackedObject):
	
	customText = ""
	
	@classmethod
	def getDeepest(cls, node1, node2):
		"""
		Given two nodes on the same branch, return the one closest to the tip.
		
		Returns `None` if the two nodes are not on the same branch. 
		"""
		if node1 in node2:
			return node1
		if node2 in node1:
			return node2
		if node1 == node2:
			return node1
		return None
	
	def __init__(self, nodeType, attrs, parent, offset, nodeManager):
		super(NodeField, self).__init__()
		self._nodeManager = weakref.ref(nodeManager)
		self._parent = weakref.ref(parent) if parent is not None else None
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
			self.controlIdentifier = parent.controlIdentifier
			self.role = 0
		elif nodeType == "control":
			self.control = attrs
			self.name = attrs.get("name", "")
			self.role = attrs["role"]
			self.states = attrs["states"]
			self.controlIdentifier = attrs.get("controlIdentifier_ID", 0)
			self.tag = attrs.get("IAccessible2::attribute_tag")
			if not self.tag:
				self.tag = attrs.get("IHTMLDOMNode::nodeName")
			# tag is reported lowercase in Chrome and FF, but uppercase in IE.
			if self.tag:
				self.tag = self.tag.lower()
			self.id = attrs.get("IAccessible2::attribute_id")
			if not self.id:
				self.id = attrs.get("HTMLAttrib::id")
			self.className = attrs.get("IAccessible2::attribute_class")
			if not self.className:
				self.className = attrs.get("HTMLAttrib::class")
			if not self.className:
				self.className = attrs.get("HTMLAttrib::className")
			self.src = attrs.get("IAccessible2::attribute_src")
			if not self.src:
				self.src = attrs.get("HTMLAttrib::src")
			self.children = []
		else:
			raise ValueError(
				u"Unexpected nodeType: {nodeType}".format(nodeType=nodeType))
		self._previousTextNode = \
			weakref.ref(nodeManager.lastTextNode) \
			if nodeManager.lastTextNode is not None \
			else None
		if parent is not None:
			self.index = len(parent.children)
			parent.children.append(self)
		else:
			self.index = 0
		global countNode
		countNode = countNode + 1

	def __del__(self):
		# log.info(u"dell node")
		global countNode
		countNode = countNode - 1
		super(NodeField, self).__del__()
		
	def __repr__(self):
		if hasattr(self, "text"):
			return "Node text: %s" % repr(self.text)
		elif hasattr(self, "control"):
			return "Node %s: id=%s, className=%s" % (
				self.tag, self.id, self.className
			)
		elif hasattr(self, "format"):
			return "Node format"
		else:
			return "Node unknown"
	
	@property
	def nodeManager(self):
		return self._nodeManager and self._nodeManager()
	
	@property
	def parent(self):
		return self._parent and self._parent()
	
	@property
	def previousTextNode(self):
		return self._previousTextNode and self._previousTextNode()
	
	def isReady(self):
		return self.nodeManager and self.nodeManager.isReady
	
	def checkNodeManager(self):
		if self.nodeManager is None or not self.nodeManager.isReady:
			playWebAppSound("keyError")
			return False
		else:
			return True
		
	def recursiveDelete(self):
		n = 1
		if hasattr(self, "children"):
			for child in self.children:
				n = n + child.recursiveDelete()
			self.children = []
		self._nodeManager = None
		self._previousTextNode = None
		self._parent = None
		self.format = None
		self.control = None
		self.text = None
		self.customText = None
		self.controlIdentifier = None
		return n
	
	def searchString(self, text, exclude=None, maxIndex=0, currentIndex=0):
		"""Searches the current node and its sub-tree for a match with the given text.
		
		Keyword arguments:
		  text: The text to search for.
		  exclude:
		    If specified, set of children nodes not to explore or  True  to not explore
		    children nodes at all.
		  maxIndex:
		    If set to 0 (default value), every result found is returned.
		    If greater than 0, only return the n first results (1 based).
		  currentIndex: Used to compare against maxIndex when searching down
		    sub-trees.
		
		Returns a list of the matching nodes.
		"""  # noqa
		if not isinstance(text, list):
			text = [text]
		if hasattr(self, "text"):
			for t in text:
				if t in self.text:
					return [self]
			return []
		elif exclude is not True and hasattr(self, "children"):
			result = []
			for child in self.children:
				if exclude and child in exclude:
					continue
				childResult = child.searchString(
					text,
					exclude=exclude,
					maxIndex=maxIndex,
					currentIndex=currentIndex
				)
				result += childResult
				if maxIndex:
					currentIndex += len(childResult)
					if currentIndex >= maxIndex:
						break
			return result
		return []

	def search_eq(self, itemList, value):
		if not isinstance(itemList, list):
			itemList = [itemList]
		for item in itemList:
			if item == value:
				return True
		return False
	
	def search_in(self, itemList, value):
		if value is None or value == "":
			return False
		if not isinstance(itemList, list):
			itemList = [itemList]
		for item in itemList:
			if item.replace("*", "") in value:
				return True
		return False

	def searchNode(
		self,
		exclude=None,
		relativePath=None,
		maxIndex=0,
		currentIndex=0,
		**kwargs
	):
		"""Searches the current node and its sub-tree for a match with the given criteria.
		
		Keyword arguments:
		  exclude:
		    If specified, set of children nodes not to explore or  True  to not explore
		    children nodes at all.
		  relativePath:
		    If specified, walk the given path from the matched nodes to
		    determine the final result. If the path cannot be walked, no
		    result is returned for the matched node.
		    See `walk` for the path expression syntax.
		  maxIndex:
		    If set to 0 (default value), every result found is returned.
		    If greater than 0, only return the n first results (1 based).
		  currentIndex: Used to compare against maxIndex when searching down
		    sub-trees.
		  
		Additional keyword arguments names are of the form:
		  `test_property[#index]`
		
		All of the criteria must be matched (logical `and`).
		Values can be lists, in which case any value in the list can match
		(logical `or`).
		Supported tests are: `eq`, `notEq`, `in` and `notIn`.
		
		Properties `text` and `prevText` are mutually exclusive, are only valid
		for the `in` test and do not support multiple values.
		
		Returns a list of the matching nodes.
		"""  # noqa
		global _count
		nodeList = []
		_count += 1
		found = True
		# Copy kwargs dict to get ready for Python 3:
		for key, allowedValues in kwargs.copy().items():
			if "_" not in key:
				log.warning(u"Unexpected argument: {arg}".format(arg=key))
				continue
			test, prop = key.split("_", 1)
			prop = prop.rsplit("#", 1)[0]
			if prop in ("text", "prevText"):
				continue
			if not hasattr(self, prop):
				if test in ("eq", "in"):
					found = False
				continue
			candidateValue = getattr(self, prop)
			candidateValues = (candidateValue,)
			if prop == "className":
				if candidateValue is not None: 
					candidateValues = candidateValue.split(" ")
			elif prop in ("role", "states"):
				try:
					allowedValues = [int(value) for value in allowedValues]
				except ValueError:
					log.error((
						"Invalid search criterion: {key}={allowedValues!r}"
					).format(**locals()))
				if prop == "states":
					candidateValues = candidateValue
			for candidateValue in candidateValues:
				if test == "eq":
					if self.search_eq(allowedValues, candidateValue):
						del kwargs[key]
						break
				elif test == "in":
					if self.search_in(allowedValues, candidateValue):
						del kwargs[key]
						break
				elif test == "notEq":
					if self.search_eq(allowedValues, candidateValue):
						return []
				elif test == "notIn":
					if self.search_in(allowedValues, candidateValue):
						return []
			else:  # no break
				if test in ("eq", "in"):
					found = False
		if found:
			matches = []
			text = kwargs.get("in_text", [])
			prevText = kwargs.get("in_prevText", "")
			if text != []:
				matches = self.searchString(
					text,
					exclude=exclude,
					maxIndex=maxIndex,
					currentIndex=currentIndex
				)
			elif prevText != "":
				if (
					self.previousTextNode is not None
					and prevText in self.previousTextNode.text
				):
					matches = [self]
				else:
					return []
			else:
				matches = [self]
			if relativePath:
				candidates = matches
				matches = []
				for candidate in candidates:
					match = candidate.walk(relativePath)
					if match:
						matches.append(match)
			return matches
		if exclude is True:
			return []
		for child in self.children:
			if exclude and child in exclude:
				continue
			childResult = child.searchNode(
				exclude=exclude,
				relativePath=relativePath,
				maxIndex=maxIndex,
				currentIndex=currentIndex,
				**kwargs
			)
			nodeList += childResult
			if maxIndex:
				currentIndex += len(childResult)
				if currentIndex >= maxIndex:
					break
		return nodeList
	

	def searchOffset(self, offset):
		if hasattr(self, "text"):
			if offset >= self.offset and offset < self.offset + self.size:
				return self
		elif hasattr(self, "children"):
			for child in self.children:
				node = child.searchOffset(offset)
				if node:
					return node
		return None
	
	RELATIVE_PATH_CRITERIA = re.compile(u"^{[^}]*}")
	
	def walk(self, path):
		"""Walk the node tree and return the destination node.
	    Returns None if the given path cannot be walked.
	    In the path expression, each character represents a step:
	      - "b": (before) previous text in the document flow
	      - "a": (after) next text in the document flow
	      - "u": (up) parent node
	      - "d": (down) first child node
	      - "l": (left) previous sibling node
	      - "r": (right) next sibling node
	    Criteria expressions can be checked on the way. They are introduced by the
	    non-moving step "c" (check) and are formatted as a Python dictionary literal.
	    Additionally, regular steps can be expressed upper-case, in which case they are
	    immediately followed by a criteria expression.
	    They allow to walk in the given direction until the criteria are met.
		"""  # noqa
		node = self
		skipUntil = None
		searchKwargs = None
		for index, step in enumerate(path):
			if skipUntil and index < skipUntil:
				continue
			while True:
				if searchKwargs:
					matches = node.searchNode(
						exclude=step != "d",  # search sub-tree only when walking down.
						maxIndex=1,
						currentIndex=0,
						**searchKwargs
					)
					if matches:
						node = matches[0]
						searchKwargs = None
						break  # continue to the next step
					if step == "c":
						return None
				# No check or no match, keep walking...
				if step == "b":  # First node with lesser offset
					node = node.previousTextNode
					if not node:
						return None
					node = node.parent
				elif step == "a": # First node with greater offset
					offset = node.offset
					while True:
						try:
							node = node.children[0]
						except:
							while True:
								try:
									node = node.parent.children[node.index + 1]
									break
								except:
									node = node.parent
									if node is None:
										return None
						if node.offset > offset or searchKwargs:
							break
				elif step == "u":
					node = node.parent
				elif step == "d":
					try:
						node = node.children[0]
					except:
						return None
				elif step == "l":
					if node.index == 0 or node.parent is None:
						return None
					node = node.parent.children[node.index - 1]
				elif step == "r":
					try:
						node = node.parent.children[node.index + 1]
					except:
						return None
				elif step == "c" or step.isupper():
					assert searchKwargs is None
					if step.isupper():
						step = step.lower()
					index = index + 1
					match = self.RELATIVE_PATH_CRITERIA.match(path[index:])
					if not match:
						log.error((
							u"Malformed criteria expression in relative path expression "
							u"at position {index}: {path}"
						).format(**locals()))
						return None
					# TODO: Refactor to break this coupling
					from .ruleHandler import getSimpleSearchKwargs
					criteria = literal_eval(match.group())
					searchKwargs = getSimpleSearchKwargs(criteria)
					skipUntil = match.end() + 1
					continue
				else:
					log.error((
						u'Invalid step "{step}" at index {index}'
						u' in path expression: "{path}"'
					).format(
						step=step,
						index=index,
						path=path
					))
					return None
				if not node:
					return None
				if not searchKwargs:
					break
		return node
	
	def firstTextNode(self):
		return self.searchOffset(self.offset)

	def nextTextNode(self):
		return self.nodeManager.searchOffset(self.offset + self.size)
	
	def moveto(self, reason=REASON_FOCUS):
		if not self.checkNodeManager():
			return False
		info = self.nodeManager.treeInterceptor.makeTextInfo(
			textInfos.offsets.Offsets(self.offset, self.offset)
		)
		self.nodeManager.treeInterceptor.selection = info
		if self.nodeManager.callbackNodeMoveto is not None:
			# beep()
			# log.info("node calls onMoveTo")
			self.nodeManager.callbackNodeMoveto(self, reason)
		return True
		
	def activate(self):
		if not self.checkNodeManager():
			return False
		info = self.getTextInfo()
		self.nodeManager.treeInterceptor._activatePosition(info=info)

	def sayAll(self):
		if self.moveto():
			sayAllHandler.readText(sayAllHandler.CURSOR_CARET)
			return True
		else:
			return False

	def getNVDAObject(self):
		info = self.getTextInfo()
		obj = info.NVDAObjectAtStart
		return obj

	def mouseMove(self):
		if not self.checkNodeManager():
			return False
		self.moveto()
		info = self.getTextInfo()
		obj = info.NVDAObjectAtStart
		try:
			(left, top, width, height) = obj.location
		except:
			ui.message(u"Impossible de déplacer la souris à cet emplacement")
			return False
		x = left + (width / 2)
		y = top + (height / 2)
		winUser.setCursorPos(x, y)
		mouseHandler.executeMouseMoveEvent(x, y)

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
				
	# TODO: Thoroughly check this wasn't used anywhere
	# In Python 3, all classes defining __eq__ must also define __hash__
# 	def __eq__(self, node):
# 		if node is None:
# 			return False
# 		if self.offset == node.offset:
# 			return True
# 		return False
	
	def __lt__(self, node):
		"""
		Compare nodes based on their offset.
		"""
		if self.offset < node.offset:
			return True
		return False

	def __le__(self, node):
		"""
		Compare nodes based on their offset.
		"""
		if self.offset <= node.offset:
			return True
		return False

	def __gt__(self, node):
		"""
		Compare nodes based on their offset.
		"""
		if self.offset > node.offset:
			return True
		return False

	def __ge__(self, node):
		"""
		Compare nodes based on their offset.
		"""
		if self.offset >= node.offset:
			return True
		return False

	def __contains__(self, node):
		"""
		Check whether the given node belongs to the subtree of this node, based
		on their offset.
		"""
		if self <= node:
			return False
		if not self.children:
			return False
		lastChild = self.children[-1]
		if lastChild >= node:
			return True
		return node in lastChild

	def __len__(self):
		return self.size
	
	@property
	def innerText(self):
		txt = ""
		if hasattr(self, "text"):
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
		if hasattr(self, "children"):
			for child in self.children:
				txt += child._get_innerText()
			return txt
		return ""

	def getTextInfo(self):
		if not self.isReady():
			return None
		return self.nodeManager.treeInterceptor.makeTextInfo(
			textInfos.offsets.Offsets(self.offset, self.offset + self.size)
		)

	def getTreeInterceptorText(self):
		info = self.getTextInfo()
		if info:
			return info.text
		else:
			return ""
