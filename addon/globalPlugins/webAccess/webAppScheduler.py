# webAppScheduler.py
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

__version__ = "2018.07.06"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import wx
import Queue
import threading

import api
import traceback
import textInfos
import ui

from .webAppLib import *


def displayTraceBack (msg):
	stack = ""
	for func in traceback.extract_stack()[:-1]:
		stack += func[2] + "\n"
	log.info (u"%s : %s" % (msg, stack))

class WebAppScheduler(threading.Thread):
	
	lastTreeInterceptor = None
	
	def __init__(self):
		super(WebAppScheduler,self).__init__()
		self.daemon = True
		self.queue = Queue.Queue()
		global scheduler
		scheduler = self
		
	def run(self):
		self.stop = False
		while not self.stop:
			try:
				event = self.queue.get(True, 0.5)
			except:
				event = {"eventName":"timeout"}
			if isinstance (event, dict):
				eventName = event["eventName"]
				del event["eventName"]
				#log.info (u"eventName : %s" % eventName)
				#self.checkTreeInterceptor (eventName)
				func = getattr (self, "event_%s" % eventName, None)
				if func:
					try:
						func (**event)
					except Exception, e:
						log.exception ("Error executing event %s : %s" % (eventName, e))

				else:
					log.info (u"event %s is not found" % eventName)
		log.info  (u"webAppScheduler stopped !")

	def send (self, **kwargs):
		self.queue.put (kwargs)
		
	def event_stop (self):
		self.stop = True 
		
	def event_timeout (self):
		self.send (eventName="updateNodeManager", treeInterceptor=api.getFocusObject().treeInterceptor )
				 
	def fakeNext(self = None):
		return True

	def event_webApp (self, name=None, obj=None, webApp=None):
		funcName = 'event_%s' % name
		#log.info("webApp %s will handle the event %s" % (webApp.name, name))
		func = getattr(webApp, funcName, None)
		if func:
			func(obj, self.fakeNext)
	
	def event_configurationChanged (self, webApp):
		from . import webModuleHandler
		webModuleHandler.update(webApp)

	def event_treeInterceptor_gainFocus (self, treeInterceptor, firstGainFocus):
		hadFirstGainFocus=treeInterceptor._hadFirstGainFocus
		treeInterceptor._hadFirstGainFocus = True
		if not hadFirstGainFocus:
			# This treeInterceptor is gaining focus for the first time.
			# Fake a focus event on the focus object, as the treeInterceptor may have missed the actual focus event.
			focus = api.getFocusObject()
			#self.event_gainFocus(focus, lambda: focus.event_gainFocus())
			if not treeInterceptor.passThrough:
				# We only set the caret position if in browse mode.
				# If in focus mode, the document must have forced the focus somewhere,
				# so we don't want to override it.
				initialPos = treeInterceptor._getInitialCaretPos()
				if initialPos:
					treeInterceptor.selection = treeInterceptor.makeTextInfo(initialPos)
				#browseMode.reportPassThrough(treeInterceptor)
		self.send (eventName="updateNodeManager", treeInterceptor=treeInterceptor )

	def event_checkWebAppManager (self):
		focus = api.getFocusObject ()
		webApp = focus.getWebApp()
		if webApp:
			treeInterceptor = focus.treeInterceptor
			if treeInterceptor:
				webApp.treeInterceptor = treeInterceptor
				nodeManager = getattr (treeInterceptor, "nodeManager", None)
				if nodeManager:
					webApp.markerManager.update (nodeManager)
		
	def event_updateNodeManager(self, treeInterceptor, webApp=None):
		if treeInterceptor is None:
			return
		if hasattr (treeInterceptor, "nodeManager"):
			treeInterceptor.nodeManager.update ()
		else:
			from . import nodeHandler
			treeInterceptor.nodeManager = nodeHandler.NodeManager (treeInterceptor, self.onNodeMoveto, inSeparateThread=True)
		if webApp:
			webApp.treeInterceptor = treeInterceptor

	def event_nodeManagerUpdated (self, nodeManager):
		self.send (eventName="checkWebAppManager")

	def event_markerManagerUpdated(self, markerManager):
		markerManager.checkPageTitle ()
		markerManager.checkAutoAction ()

	def event_gainFocus (self, obj):
		pass

	def checkTreeInterceptor (self, eventName):
		obj = api.getFocusObject ()
		if not obj or not hasattr (obj, "treeInterceptor") or obj.treeInterceptor is None:
			return
		ti = obj.treeInterceptor
		if not ti.isReady:
			return
			
		if ti != self.lastTreeInterceptor:
			self.lastTreeInterceptor = ti
			log.info ("new treeInterceptor")
			self.lastSize = 0
		try:
			info = ti.makeTextInfo(textInfos.POSITION_LAST)
			size = info._endOffset
			if size != self.lastSize:
				self.lastSize = size
				log.info (u"taille : %d" % size)
		except Exception, e:
			pass

	def onNodeMoveto(self, node, reason):
		focus = api.getFocusObject ()
		activeWebApp = focus.getWebApp()
		useInternalBrowser = False
	
		if activeWebApp is not None:
			scheduler.send (eventName="webApp", name='node_gainFocus', obj=node, webApp=activeWebApp)
			activeWebApp.widgetManager.claimVirtualBufferWidget(reason)
			if useInternalBrowser is True or activeWebApp.activeWidget is not None:
				beep (300, 30)
				wx.CallAfter(activeWebApp.presenter.display, node)
