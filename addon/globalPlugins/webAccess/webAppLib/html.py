# globalPlugins/webAccess/webAppLib/html.py
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

__version__ = "2016.12.20"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"

import textInfos
import api
import speech
from NVDAObjects.IAccessible import IAccessible
import controlTypes
from logHandler import log
import virtualBuffers

# global variable that stores the last valid document tree interceptor
documentTreeInterceptor = None

def searchNext (info, reverse=False, func=None, max=15):
	direction = 1
	if func is None:
		return None
	if reverse:
		direction = -1
	i=0
	info.move(textInfos.UNIT_LINE, direction)
	while i < max and not func(info):
		info.move(textInfos.UNIT_LINE, direction)
		i += 1
	if i >= max:
		return None
	else:
		return info
		
def getIEHTMLAttributes (obj):
	try:
		node = obj.HTMLNode
		if node is None:
			return ""
		s = u"tag %s\r\n" % (node.nodeName)
		if node.id is not None:
			s += u"id=%s\r\n" % (node.id)
			if node.className is not None:
				s += u"class=%s\r\n" % (node.className)
	except:
		return ""
	
	try:
		if node.src is not None:
			s += u"src=%s\r\n" % (node.src)
	except:
		pass
	s += u"\r\n"
	return s
			
def getHTMLAttributes(obj):
	if hasattr (obj, "HTMLNode"):
		return getIEHTMLAttributes (obj)
	if not isinstance(obj, IAccessible):
		return u"pas IAccessibe\r\n"
	try:
		attributes = obj.IA2Attributes
	except:
		attributes =()
	s = u""
	try:
		s += u"id=%s\r\n" %(attributes["id"])
	except:
		pass
	try:
		s += u"class=%s\r\n" %(attributes["class"])
	except:
		pass
	try:
		tag = attributes["tag"]
	except:
		tag = "inconnu"
	try:
		s += u"src=%s\r\n" %(attributes["src"])
	except:
		pass
	try:
		if tag == "body":
			url = obj.IAccessibleObject.accValue(obj.IAccessibleChildID)
			s += u"url=%s\r\n" %(url)
	except:
		pass
	return(u"tag %s\r\n%s\r\n" %(tag, s))

def getFirstChildName (obj):
	# retourne le premier name non nul a partir de l'objet en cours
	if obj is None:
		return ""
	if obj.name is not None and obj.name != "":
		return obj.name
	for o in obj.children:
		name = getFirstChildName(o)
		if name != "":
			return name
	return ""

def getFirstChildDescription (obj):
	# retourne la premiÃ¨re description non nul a partir de l'objet en cours
	if obj is None:
		return ""
	if obj.description is not None and obj.description != "":
		return obj.description
	for o in obj.children:
		description = getFirstChildDescription(o)
		if description != "":
			return description
	return ""


def getElementDescription(obj, max=15):
	s = ""
	while obj and max > 0:
		s += getHTMLAttributes(obj)
		if hasattr (obj, "libParent"):
			obj = obj.libParent
		else:
			p = obj.parent
			obj.libParent = p
			obj = p
		max -= 1
	return s

def setTreeInterceptor(document):
	return
	global documentTreeInterceptor

	if document.treeInterceptor is not None:
		documentTreeInterceptor = document.treeInterceptor
	
def getTreeInterceptor(focusObject=None):
	global documentTreeInterceptor

	ti = None
	try:
		if focusObject is None:
			focusObject = api.getFocusObject()
		ti = focusObject.treeInterceptor
	except:
		pass
	if ti is None and documentTreeInterceptor is not None:
		ti = documentTreeInterceptor
	return ti

def getCaretInfo(focusObject=None):
	treeInterceptor = getTreeInterceptor(focusObject=focusObject)
	if not treeInterceptor: 
		return None
	return treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)

def getCaretObject():
	info = getCaretInfo()
	if info is None:
		return None
	return info.NVDAObjectAtStart

def moveCaret (info):
	info.collapse ()
	info.updateCaret ()

def moveFocus (info):
	info.collapse ()
	treeInterceptor = getTreeInterceptor()
	treeInterceptor.selection=info

def activatePosition (info=None):
	treeInterceptor = getTreeInterceptor()
	if info is None:
		info = getCaretInfo()
	treeInterceptor._activatePosition(info)
	
def searchString(text, info=None, id=None, className=None, src=None, func=None, first=False, reverse=False, maxAncestors=1):
	treeInterceptor = getTreeInterceptor ()
	if treeInterceptor is None:
		return None
	if info is None:
		if first:
			info=treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
		else:
			info=treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
	ok = False
	while not ok:
		if info.find(text,reverse=reverse):
			if id is not None or className is not None or src is not None:
				obj = info.NVDAObjectAtStart
				ok = parentsContainsAttributes (obj, id=id, className=className, src=src, max=maxAncestors)
			elif func is not None:
				ok = func(info)
			else:
				ok = True
		else:
			return None
	return info

def nextLine (info=None):
	treeInterceptor = getTreeInterceptor ()
	if treeInterceptor is None:
		return None
	if info is None:
		info=treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
	info.move(textInfos.UNIT_LINE,1)
	return info

def previousLine (info=None):
	treeInterceptor = getTreeInterceptor ()
	if treeInterceptor is None:
		return None
	if info is None:
		info=treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
	info.move(textInfos.UNIT_LINE,-1)
	return info

def topOfDocument ():
	treeInterceptor = getTreeInterceptor()
	info =treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
	return info

def getLine (info=None):
	if info is None:
		info = getCaretInfo ().copy ()
	info.collapse ()
	info.expand(textInfos.UNIT_LINE)
	return info.text

def speakLine(info=None):
	if info is None:
		info = getCaretInfo()
		if info is None:
			return
	info = info.copy()
	info.expand(textInfos.UNIT_LINE)
	speech.speakTextInfo(info,unit=textInfos.UNIT_LINE,reason=controlTypes.REASON_CARET)

def formMode():
	try:
		treeInterceptor = getTreeInterceptor()
		treeInterceptor.passThrough = True
	except:
		pass

def browseMode ():
	try:
		treeInterceptor = getTreeInterceptor()
		treeInterceptor.passThrough = False
	except:
		pass

def parentsContainsAttributes (obj, id=None, className=None, src=None, max=None):
	if max is None:
		max = 30
	if isinstance(id, tuple) or isinstance(id, list):
		ids = id
	elif id is not None:
		ids = [id]
	else:
		ids = []
	if isinstance(className, tuple) or isinstance(className, list):
		classNames = className
	elif className is not None:
		classNames = [className]
	else:
		classNames = []
	if isinstance(src, tuple) or isinstance(src, list):
		srcs = src
	elif src is not None:
		srcs = [src]
	else:
		srcs = []
	while obj and max > 0:
		attributes = getHTMLAttributes(obj)
		for id in ids:
			if id in attributes:
				return True
		for className in classNames:
			if className in attributes:
				return True
		for src in srcs:
			if src in attributes:
				return True
		obj = obj.parent
		max -=1
	return False

def oneStepTagSearch(dir, focus, nodeType, start):
	target = None
	for itemType in nodeType.split("|"):
		try:
			item = next(focus._iterNodesByType(itemType, dir, start))
		except StopIteration:
			continue
		except Exception, e:
			log.exception("Generic exception while searching for a %s tag: %s" %(itemType, e))
			return None
		# log.info("Found item %s" %(repr(item)))
		if item is not None:
			if target is None:
				target = item
			elif target.textInfo._startOffset > item.textInfo._startOffset and dir == "next":
				target = item
			elif target.textInfo._startOffset < item.textInfo._startOffset and dir == "previous":
				target = item
	return target

def searchTag_2015(nodeType, info=None, id=None, className=None, src=None, text=None, first=False, reverse=False, func=None, max=None, moveFocus=False):
	if True:
		focus = getTreeInterceptor()
		dir = "next" if not reverse else "previous"
		if info is None:
			if first:
				info=focus.makeTextInfo(textInfos.POSITION_FIRST)
			else:
				info=focus.makeTextInfo(textInfos.POSITION_CARET)
		startOffset=info._startOffset
		endOffset=info._endOffset
		ok = False
		while not ok:
			item = oneStepTagSearch(dir, focus, nodeType, info)
			if item is None:
				return None
			info = focus.makeTextInfo(textInfos.offsets.Offsets(item.textInfo._startOffset, item.textInfo._endOffset))
			if text is not None:
				if isinstance(text, tuple) or isinstance(text, list):
					texts = text
				else:
					texts = [text]
				for text in texts:
					if text in info.text:
						ok = True
			elif id is not None or className is not None or src is not None:
				obj = info.NVDAObjectAtStart
				ok = parentsContainsAttributes (obj, id=id, className=className, src=src, max=max)
			elif func is not None:
				ok = func(info)
			else:
				ok = True
	else:
	#except Exception, e:
		#log.exception("searchTag exception: %s" % e)
		return None
	return info
	info = focus.makeTextInfo(textInfos.offsets.Offsets(item.textInfo._startOffset, item.textInfo._endOffset))
	if func is not None:
		if not func(info):
			return None
	fieldInfo = info.copy()
	info.collapse()
	info.move(textInfos.UNIT_LINE, 1, endPoint="end")
	if info.compareEndPoints(fieldInfo, "endToEnd") > 0:
		# We've expanded past the end of the field, so limit to the end of the field.
		info.setEndPoint(fieldInfo, "endToEnd")
	info.collapse()
	if moveFocus:
		item.moveTo()
	api.setReviewPosition(info)
	return info

"""
NVDA 2014.4 and lower code for searchTag
"""

def nextTag (focus, nodeType, start):
	if nodeType == "button|link":
		type1 = "button"
		type2 = "link"
	else:
		type1 = nodeType
		type2 = None
	try:
		node1, start1, end1 = next(focus._iterNodesByType(type1, "next", start))
	except:
		start1 = 1000000
	try:
		node2, start2, end2 = next(focus._iterNodesByType(type2, "next", start))
	except:
		start2 = 1000000
	if start1 < start2:
		return node1, start1, end1
	elif start2 < start1:
		return node2, start2, end2
	else:
		raise

def previousTag (focus, nodeType, start):
	if nodeType == "button|link":
		type1 = "button"
		type2 = "link"
	else:
		type1 = nodeType
		type2 = None
	try:
		node1, start1, end1 = next(focus._iterNodesByType(type1, "previous", start))
	except:
		start1 = -1
	try:
		node2, start2, end2 = next(focus._iterNodesByType(type2, "previous", start))
	except:
		start2 = -1
	if start1 > start2:
		return node1, start1, end1
	elif start2 > start1:
		return node2, start2, end2
	else:
		raise

def searchTag_2014(nodeType, first=False, reverse=False, func=None, elementDescription=None, moveFocus=True):
	try:
		focus = api.getFocusObject()
		focus = focus.treeInterceptor
		if moveFocus:
			focus.passThrough = False
		virtualBuffers.reportPassThrough.last = False # pour que le changement de mode ne soit pas lu  automatiquement
		if first:
			info=focus.makeTextInfo(textInfos.POSITION_FIRST)
		else:
			info=focus.makeTextInfo(textInfos.POSITION_CARET)
		startOffset=info._startOffset
		endOffset=info._endOffset
		ok = False
		while not ok: 
			if reverse:
				node, startOffset, endOffset = previousTag (focus, nodeType, startOffset)
			else:
				node, startOffset, endOffset = nextTag (focus, nodeType, startOffset)
			info = focus.makeTextInfo(textInfos.offsets.Offsets(startOffset, endOffset))
			if elementDescription is not None:
				obj = info.NVDAObjectAtStart
				ok = getElementDescription (obj).find (elementDescription) > 0
			elif func is not None:
				ok = func(info)
			else:
				ok = True
	except:
		return False
	info = focus.makeTextInfo(textInfos.offsets.Offsets(startOffset, endOffset))
	if func is not None:
		if not func(info):
			return False
	fieldInfo = info.copy()
	info.collapse()
	info.move(textInfos.UNIT_LINE, 1, endPoint="end")
	if info.compareEndPoints(fieldInfo, "endToEnd") > 0:
		# We've expanded past the end of the field, so limit to the end of the field.
		info.setEndPoint(fieldInfo, "endToEnd")
	info.collapse()
	if moveFocus:
		focus._set_selection(info)
	api.setReviewPosition(info)
	return True


	
"""
searchTag - searches for a specific tag into the document.
This calls either the 2015.1 or 2014.4 version, depending on the NVDA version we actually use.
"""

def searchTag(nodeType, info=None, id=None, className=None, src=None, text=None, first=False, reverse=False, func=None, maxAncestors=1, moveFocus=False):
	if hasattr (virtualBuffers, "reportPassThrough"):
		# ancienne version de NVDA
		return searchTag_2014(nodeType, first, reverse, func, moveFocus)
	else:
		return searchTag_2015(nodeType, info=info, id=id, className=className, src=src, text=text, first=first, reverse=reverse, func=func, max=maxAncestors, moveFocus=moveFocus)
	