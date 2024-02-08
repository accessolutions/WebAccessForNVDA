# globalPlugins/webAccess/widgets/__init__.py
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

"""Widgets are designed to be used programatically."""

__version__ = "2016.11.18"

__author__ = "Yannick Plassiard <yan@mistigri.org>"


import api
import baseObject
import eventHandler
from logHandler import log
from NVDAObjects import NVDAObject
import speech
import ui

from .. import nodeHandler
from ..webAppLib import *


class WidgetManager(baseObject.ScriptableObject):
	widgets = {}
	webApp = None
	nodeManager = None

	def __init__(self, webApp):
		super(WidgetManager, self).__init__()
		self.webApp = webApp

	def update(self):
		logTimeStart()
		if self.nodeManager is None:
			self.nodeManager = getattr(self.webApp.treeInterceptor, 'nodeManager', None)
			if self.nodeManager is None:
				logTime("nodeManager update cancelled")
				return
		instances = 0
		for x in self.widgets:
			ret = x.useVirtualBuffer()
			if ret is True:
				#log.info("Getting instances list for %s" % (x.__name__))
				instanceList = x.getInstanceList(self.webApp, self.nodeManager)
				instances += len(instanceList)
				for i in instanceList:
					i._useVirtualBuffer = True
				self.widgets[x] = instanceList
		self.claimVirtualBufferWidget(nodeHandler.REASON_FOCUS)
		#logTime("Created %d widget instances." % instances)
		
	def register(self, widgetClass):
		if widgetClass.__name__ in self.widgets:
			return False
		self.widgets[widgetClass] = []
		return True

	def unregister(self, widgetClass):
		if widgetClass.__name__ in self.widgets:
			for x in self.widgets[widgetClass.__name__]:
				del x
			del self.widgets[widgetClass.__name__]
			return True
		return False

	def claimVirtualBufferWidget(self, reason):
		if self.nodeManager is None:
			# log.error("Node manager is none, unfortunately.")
			return False
		caretNode = None
		curNode = None
		try:
			caretNode = self.nodeManager.getCaretNode()
			curNode = self.nodeManager.getCurrentNode()
			#log.info (u"suite")
		except Exception as e:
			# log.error("Get caret node failed: %s" % e)
			return False
		if caretNode is None and curNode is None:
			return False
		for cls in self.widgets:
			if cls.useVirtualBuffer():
				# log.info("Looking for %s instances..." % (cls.__name__))
				for instance in self.widgets[cls]:
					if caretNode in instance or curNode in instance:
						self.handleWidgetSwitch(instance, reason)
						return True
		self.handleWidgetSwitch(None, reason)
		return False
	
	def claimObject(self, obj):
		for wclass in self.widgets:
			if wclass.useVirtualBuffer() is True:
				continue
			if wclass.check(obj) is False:
				continue
			instanceList = self.widgets[wclass]
			for instance in instanceList:
				if instance.claimObject(obj) is True:
					self.handleWidgetSwitch(instance, nodeHandler.REASON_FOCUS)
					return
			instance = wclass(self.webApp, obj)
			if instance.group == "":
				self.handleWidgetSwitch(None, nodeHandler.REASON_FOCUS)
				return
			instance._useVirtualBuffer = False
			instanceList.append(instance)
			self.handleWidgetSwitch(instance, nodeHandler.REASON_FOCUS)
			return
		self.handleWidgetSwitch(None, nodeHandler.REASON_FOCUS)

				
	def handleWidgetSwitch(self, widget, reason):
		# log.info("Switching to widget %s" %(widget.name if widget is not None else "(none)"))
		if widget == self.webApp.activeWidget:
			return
		if self.webApp.activeWidget is not None:
			speech.speakMessage("Sortie de %s, %s" %(self.webApp.activeWidget.name, self.webApp.activeWidget.group))
			self.sendWidgetEvent('widget_loseFocus', self.webApp.activeWidget)
			self.webApp.activeWidget = None
			if webAppHandler.useInternalBrowser is False and widget == None:
				#: We don't switch to another widget but returns to a browseMode presentation.
				self.webApp.presenter.restoreBrailleBuffer()
				ti = html.getTreeInterceptor()
				if ti and hasattr(ti, '_enteringFromOutside'):
					#: Set to L{True} to force the treeInterceptor to refresh itself.
					ti._enteringFromOutside = True
					ti._hasFirstGainFocus = True
					info = html.getCaretInfo()
					if info:
						html.speakLine(info)
						#: Switch from and back to browseMode to force braille output.
						html.formMode()
						html.browseMode()
						
		if widget is not None and (widget.autoEnter is True or reason is nodeHandler.REASON_SHORTCUT):
			self.webApp.activeWidget = widget
			speech.cancelSpeech()
			speech.speakMessage("Entrée dans %s, %s" %(widget.name, widget.group))
			self.sendWidgetEvent('widget_gainFocus', widget)
		else:
			self.webApp.activeWidget = None

	def sendWidgetEvent(self, eventName, widget):
		if widget is None:
			return False
		if eventName is None or eventName == "":
			return False
		funcName = "event_%s" % eventName
		func = getattr(widget, funcName, None)
		if func:
			func(self.nodeManager.getCaretNode())
		return True

	def script_listWidgets(self, gesture):
		msg = "Liste de widgets: "
		for cls in self.widgets:
			msg += "Widget %s: " % (cls.__name__)
			for x in self.widgets[cls]:
				msg += "Instance: %s, groupe %s" % (x.name, x.group)
		ui.message(msg)

	__gestures = {
		"kb:nvda+alt+l": "listWidgets",
	}

class WebAppWidget(baseObject.ScriptableObject):
	name = None
	lockBoundaries = False
	autoEnter = True
	webApp = None
	myObjects = []
	group = ""

	@classmethod
	def useVirtualBuffer(cls):
		"""
		The next class method has to be defined to return True ifthe widget uses 
		the virtual buffer to retri1re its content or not.
		"""
		return True

	@classmethod
	def getInstanceList(cls, webApp, nodeManager):
		"""
		If using virtua; buffer, this will return an instance list of all present
		widget of this class type on the actual web page.
		"""
		return []
	

	
	@classmethod
	def check(cls, obj):
		"""
		If not using virtual buffers, this will be called on each object to know
		if it belongs to this widges class. If so, an instance will be created.
		"""
		return False
	
	def __init__(self, webApp, obj=None):
		super(WebAppWidget, self).__init__()
		self.webApp = webApp
		self.widgetManager = webApp.widgetManager
		self.gesturesMap = {}
		self.addGestures(self.__basicGestures)

	def __contains__(self, node):
		return False
	def addGestures(self, gesturesMap):
		m = self.gesturesMap.copy()
		m.update(gesturesMap)
		self.gesturesMap = m
		self.bindGestures(m)
		# log.info("Gestures: %s" % repr(m))
	
	def claimObject(self, obj):
		return False

	def addObject(self, obj):
		if obj in self.myObjects:
			log.info("This object (%s) is already added" %(obj.name))
			return
		self.myObjects.append(obj)
	
	def script_toggleLockBoundaries(self, gesture):
		if self.lockBoundaries is True:
			speech.speakMessage("Barrières désactivées.")
			self.lockBoundaries = False
		else:
			speech.speakMessage("Barrières activées.")
			self.lockBoundaries = True
	def script_disableInstance(self, gesture):
		self.autoEnter = False
		speech.speakMessage("L'entrée automatique dans %s est désactivée." % self.name)
		self.widgetManager.handleWidgetSwitch(None, nodeHandler.REASON_FOCUS)

	def script_whereAmI(self, gesture):
		speech.speakMessage("Composant: %s, groupe %s" %(self.name if self.name is not None else "sans nom", self.group))

	def script_activateItem(self, gesture):
		speech.speakMessage("Aucune action définie.")
		
	__basicGestures = {
		"kb:control+alt+l": "toggleLockBoundaries",
		"kb:escape": "disableInstance",
		"kb:enter": "activateItem",
		"kb:nvda+shift+w": "whereAmI",
	}
