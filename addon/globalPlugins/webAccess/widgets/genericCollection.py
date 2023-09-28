# globalPlugins/webAccess/widgets/genericCollection.py 
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

"""This widget is a generic collection containing one or more elements.

It defines scripts to navigate from one element to another, and can be configured
to prevent the user to exit the widget by only pressing arrow keys.
"""

__version__ = "2016.11.18"

__author__ = "Yannick Plassiard <yan@mistigri.org>"


import os

import api
import braille
import controlTypes
from logHandler import log
from NVDAObjects import NVDAObject, IAccessible
import speech
import ui

from .. import webAppLib
from . import WebAppWidget


class GenericCollection(WebAppWidget):
	lockBoundaries = True
	supportSearch = False
	name = None
	brailleName = None
	_collection = []
	activeNode = None
	itemIndex = 0

	def _get_activeNodeRole(self):
		if self.activeNode is None:
			return controlTypes.ROLE_UNKNOWN
		return self.activeNode.role
	
	def _get_activeNodeName(self):
		if self.activeNode is None:
			return "Sans nom"
		try:
			n = self.activeNode.name
		except:
			n = ""
		if n is None or n == "":
			try:
				n = self.activeNode.text
			except:
				n = self.activeNode.innerText
		return n
	
	def __contains__(self, data):
		if self._useVirtualBuffer:
			# log.info("Searching for node offset %d in a %d length collection" %(data.offset, len(self._collection)))
			for x in self._collection:
				if x == data:
					return True
		else:
			log.info("operator __contains__ not supported for non-virtualbuffer wcgd!ts")
			return False
	
	def __init__(self, webApp, obj=None):
		super(GenericCollection, self).__init__(webApp)
		if self.name is None:
			self.name = "Collection d'objets sant nom"
		if self.brailleName is None:
			if self.name is not None:
				self.brailleName = self.name
			else:
				self.brailleName = "Barre"
		self.addGestures(self.__widgetGestures)
		letters = {}
		if self.supportSearch:
			for x in list(range(ord('A'), ord('Z') + 1)) + list(range(ord('a'), ord('z') + 1)) + [ord(' ')]:
				c = chr(x)
				if c.isupper():
					g = "shift+" + c
				elif c == ' ':
					g = "space"
				else:
					g = c
				letters["kb:" + g] = "typeLetter"
			self.addGestures(letters)
		

	def claimObject(self, obj):
		return False


	def _get_collectionCount(self):
		return len(self._collection)
	

	def getPresentationString(self):
		"""
		Builds and returns a presentation string used by L{presenter.Presenter} to
		be spoken.
		@returns the built presentation string.
		@rtype stra
		"""
		return "_activeNodeName_ _activeNodeRole_ %d sur _collectionCount_" % (self.itemIndex + 1)

	def getBraillePresentationString(self):
		if self.presentationConfig.get("braille.verticalPresentation", True) is True:
			return "%s: %s" %(self.brailleName, "_activeNodeName_ _activeNodeRole_   %d/_collectionCount_" %(self.itemIndex + 1))
		else:
			return ["%s:" % self.brailleName] + self._collection
	
	def getBraillePresentationStringForElement(self, element):
		n = element.name
		if n == "":
			n = element.innerText
		return n
	
	def getPresentationConfig(self):
		"""
		Returns a dictionnary containing the presentation configuration for this
		widget.
		@returns The config dictionnary
		@rtype dict
		"""
		return self.presentationConfig

	presentationConfig = {
		'braille.stripBlanks': True,
		'braille.verticalPresentation': True,
		'braille.showRoles': False,
	}
	


	def event_widget_gainFocus(self, node):
		idx = 0
		for x in self._collection:
			if x == node:
				self.itemIndex = idx
				self.activeNode = node
			idx += 1
		self.webApp.presenter.display()


	
	def script_typeLetter(self, gesture):
		if self._useVirtualBuffer:
			i = gesture.identifiers[0]
			if "shift" in i:
				i = i.partition("+")[2].upper()
			else:
				i = i.partition(':')[2]
			for x in self._collection[self.itemIndex + 1:]:
				if x.name != "":
					txt = x.name.upper()
				else:
					txt = x.innerText.upper()
				if txt.startswith(i.upper()):
					self.itemIndex = self._collection.index(x)
					self.activeNode = x
					self.activeNode.moveto()
					return True
			from ... import webAccess
			webAppLib.playSound(os.path.join(webAccess.SOUND_DIRECTORY, 'warningMessage.wav'))
			for x in self._collection:
				if x.name != "":
					txt = x.name.upper()
				else:
					txt = x.innerText.upper()
				if txt.startswith(i.upper()):
					self.itemIndex = self._collection.index(x)
					self.activeNode = x
					self.activeNode.moveto()
					return True
				
			ui.message("introuvable")
			return False
		else:
			ui.message("Recherche non supportée")
	
	def script_nextItem(self, gesture):
		if self._useVirtualBuffer:
			self.vbuf_nextItem(gesture)
		else:
			self.obj_nextItem(gesture)

	def vbuf_nextItem(self, gesture):
		if self.itemIndex + 1 >= self.collectionCount:
			if self.lockBoundaries is False:
				self.script_moveAfter(gesture)
			else:
				speech.speakMessage("Bas")
			return
		self.itemIndex += 1
		self.activeNode = self._collection[self.itemIndex]
		self.activeNode.moveto()

	def obj_nextItem(self):
		speech.speakMessage("Bas")

	def script_previousItem(self, gesture):
		if self._useVirtualBuffer:
			self.vbuf_previousItem(gesture)
		else:
			self.obj_previousItem(gesture)

	def vbuf_previousItem(self, gesture):
		if self.itemIndex <= 0:
			if self.lockBoundaries is False:
				self.script_moveBefore(gesture)
				return
			speech.speakMessage("haut")
			return
		self.itemIndex -= 1
		self.activeNode = self._collection[self.itemIndex]
		self.activeNode.moveto()

	def obj_previousItem(self, gesture):
		speech.speakMessage("haut")

	def script_activateItem(self, gesture):
		if self._useVirtualBuffer:
			self.vbuf_activateItem(gesture)
		else:
			self.obj_activateItem(gesture)

	def vbuf_activateItem(self, gesture):
		item = self._collection[self.itemIndex]
		if item is not None:
			item.activate()
	
	def obj_activateItem(self, gesture):
		ui.message("Aucune action définie.")
	
		
	def script_moveBefore(self, gesture):
		node = self._collection[0]
		if node.offset == 0:
			ui.message("Haut du document.")
			return
		if node:
			# log.info("Searching for offset: %d, size %d" % (node.offset + node.size, node.size))
			prevItem = self.widgetManager.nodeManager.searchOffset(node.offset - 1)
			# log.info("Searching for offset: %d, size %d" % (prevItem.offset + prevItem.size, prevItem.size))
			if prevItem is None:
				ui.message("erreur")
			elif prevItem != node:
				prevItem.moveto()
				self.widgetManager.nodeManager.setCurrentNode(prevItem)
		

	def script_moveAfter(self, gesture):
		node = self._collection[-1]
		if node:
			# log.info("Searching for offset: %d, size %d" % (node.offset + node.size, node.size))
			nextItem = self.widgetManager.nodeManager.searchOffset(node.offset + node.size)
			# log.info("Searching for offset: %d, size %d" % (nextItem.offset + nextItem.size, nextItem.size))
			if nextItem is None:
				ui.message("erreur")
			elif nextItem != node:
				nextItem.moveto()
				self.widgetManager.nodeManager.setCurrentNode(nextItem)
			else:
				ui.message("Bas")
				
	__widgetGestures = {
		"kb:uparrow": "previousItem",
		"kb:downarrow": "nextItem",
		"kb:enter": "activateItem",
		"kb:control+downarrow": "moveAfter",
		"kb:control+uparrow": "moveBefore",
	}
	
