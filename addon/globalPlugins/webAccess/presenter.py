# globalPlugins/webAccess/presenter.py
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

__version__ = "2016.11.18"

__author__ = (
	"Yannick Plassiard <yan@mistigri.org>, "
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>"
	)


import re

import api
import braille
import speech
import baseObject
import controlTypes
from logHandler import log
from NVDAObjects import NVDAObject
import ui

from . import nodeHandler


class BrailleOffset(object):
	"""
	This objcect is used to map an object displayed on the braille display with
  its start and end offsets. This will allow the L{Presenter} to notify him when
	a routine cursor click is made.
	"""
	def __init__(self, object, displayedString):
		super(BrailleOffset, self).__init__()
		self.object = object
		self.presentationString = displayedString
		self.startOffset = 0
		self.endOffset = 0

	def setOffset(self, startOffset):
		if startOffset < 0:
			raise ValueError("Invalid offset value: %d" % startOffset)
		self.startOffset = startOffset
		self.endOffset = self.startOffset + len(self.presentationString) - 1

	def updatePresentationString(self, text):
		"""
		Updates the presentation for this object. This also updates the end offset
		value.
		@param text: A string representing the object
		@type text: str
		@returns None
		"""
		self.presentationString = text
		self.endOffset = self.startOffset + len(text)


class Presenter(baseObject.ScriptableObject):
	brailleObjects = []
	brailleDisplayName = None

	def __init__(self, webApp):
		super(Presenter, self).__init__()
		self.bh = braille.handler
		self.webApp = webApp
		self.bindBrailleGestures()
	
	def bindBrailleGestures(self):
		display = braille.handler.display
		if display.name != self.brailleDisplayName:
			self.bindGestures({
				"br(%s):routing" % display.name: "brailleRouting",
			})
			self.brailleDisplayName = display.name

	def restoreBrailleBuffer(self):
		"""
		Restores the braille buffer to allow the treeInterceptor to update it.
		"""
		braille.handler.mainBuffer.clear()
		braille.handler.mainBuffer.update()
		braille.handler.update()

	def display(self, element=None):
		"""
		Displays the  given element using speech and braille ouptut.
		@param element : The given element which has to be an instance of
		L{nodeHandler.NodeField} or L{NVDAObjects.NVDAObject} classes.
		@returns None
		@raises ValueError if the given element doesn't satisfy the above 
		condition.
		"""

		#: Updates braille gestures based on the actual conoected display
		#webAppLib.beep ()

		self.bindBrailleGestures()
		self.brailleObjects = []
		if element is None:
			try:
				element = self.webApp.treeInterceptor.nodeManager.getCaretNode()
			except:
				element = None
			if element is None:
				return False
		if isinstance(element, NVDAObject) is False and isinstance(element, nodeHandler.NodeField) is False:
			raise ValueError("The given element type %s is not an instance of NVDAObject or NodeField" % (element.__class__.__name__))
		# log.info("Display %s" % element)
		if self.webApp is None:
			ui.message("WebApp is none... snif")
			return False
		ret = False
		if ret is False and hasattr(self.webApp, 'getPresentationString') is True:
			ret = self.displayFromContext(element, self.webApp)
		if ret is False and isinstance(element, nodeHandler.NodeField):
			ret = self.displayFromContext(element)
		return ret

	def displayFromContext(self, element, ctx=None):
		"""
		Gets the presentation string from the given context.
		@param ctx: The given context (webapp, node)
		@type ctx: any
		@param element: The given element which has the focus.
		@type element: WebApp or NodeField
		@returns True if some text has been output, False otherwise.
		@rtype Bool
		"""

		# Gets presentation string f!om the context, if any.
		ret = ()
		if ctx is not None:
			ret = self.extractAttributes(ctx)
			config = ctx.getPresentationConfig()
		else:
			# log.info("Getting presentation from element.")
			ret = self.extractAttributes(element)
			config = self.webApp.getPresentationConfig()
		brailleString = ret[1]
		presString = ret[0]
		if presString is False:
			raise ValueError("Template building failed.")
		if brailleString is False:
			brailleString = presString
		log.info("Will speak: %s" % presString)
		speech.speakMessage(presString)
		region = braille.TextRegion(brailleString)
		region.obj = None
		region.update()
		# TODO : Apply cursor positioning and text selection attributes.
		if 'braille.stripBlanks' in config:
			outBrl = []
			startStrip = False
			for i in region.brailleCells:
				if i == 0x00 and startStrip == False:
					outBrl.append(i)
					startStrip = True
				elif i != 0x00:
					outBrl.append(i)
					startStrip = False
			region.brailleCells = outBrl
		self.bh.mainBuffer.clear()
		self.bh.mainBuffer.regions.append(region)
		self.bh.mainBuffer.update()
		self.bh.update()
		return True
	
	def	extractAttributes(self, ctx):
		speechPres = ctx.getPresentationString()
		braillePres = ctx.getBraillePresentationString()
		if braillePres is None:
			braillePres = speechPres
		if isinstance(braillePres, list):
			for s in braillePres:
				if isinstance(s, str):
					outStr = self.formatPresentation(s, ctx, True)
					self.brailleObjects.append(BrailleOffset(ctx, outStr))
				else:
					try:
						outStr = ctx.getBraillePresentationStringForElement(s)
					except Exception as e:
						log.exception("getBraillePresentationStringForElement failed: %s" % e)
						outStr = "sansnom"
					self.brailleObjects.append(BrailleOffset(ctx, outStr))
		else:
			pObj = BrailleOffset(ctx, self.formatPresentation(braillePres, ctx, True))
			if pObj.presentationString is False:
				pObj.updatePresentationString("sansnom")
			self.brailleObjects.append(pObj)
		presString = self.formatPresentation(speechPres, ctx)
		brailleString = ""

		# Builds the whole braille string, and update offsets accordingly.
		offset = 0
		for obj in self.brailleObjects:
			brailleString += obj.presentationString + " "
			obj.setOffset(offset)
			offset = obj.endOffset + 1
			
			
			
		return (presString, brailleString)
	
	def formatPresentation(self, string, ctx, isBraille=False):
		found = True
		if string is False:
			found = False
		while found:
			# log.info("presString is %s"% presString)
			match = re.match("[^_]*(_[A-Za-z]+_).*", string)
			if match is None:
				found = False
				continue
			key = match.group(1)[1:len(match.group(1)) - 1]
			try:
				attr = getattr(ctx, key)
			except Exception as e:
				log.error("Failed to extract attribute %s from context %s" %(key, ctx))
				return False
			if isinstance(attr, int):
				if "ROLE" in key.upper():
					if isBraille is False:
						attr = controlTypes.roleLabels[attr]
					else:
						try:
							attr = braille.roleLabels[attr]
						except KeyError:
							attr = controlTypes.roleLabels[attr]
				else:
					attr = str(attr)
			string = string.replace(match.group(1), attr, 1)
		return string


	def script_brailleRouting(self, gesture):
		idx = braille.handler.mainBuffer.windowStartPos + gesture.routingIndex
		for obj in self.brailleObjects:
			log.info("obj %s, offsets(%d %d)" %(obj.presentationString, obj.startOffset, obj.endOffset))
			if idx >= obj.startOffset and idx <= obj.endOffset:
				log.info("Object type is %s" % repr(obj.object))
				try:
					obj.object.activate()
				except:
					try:
						obj.object.script_activateItem(gesture)
					except:
						speech.speakMessage("Pas d'action")
				return
		speech.speakMessage("Clic inconnu")
