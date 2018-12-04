# globalPlugins/webAccess/webAppScheduler.py
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

__version__ = "2018.10.21"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import wx
import Queue
import threading

import api
import textInfos

from .webAppLib import *


TRACE = lambda *args, **kwargs: None  # @UnusedVariable
#TRACE = log.info


scheduler = None


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
				event = {"eventName": "timeout"}
			if isinstance(event, dict):
				eventName = event.pop("eventName")
				#log.info (u"eventName : %s" % eventName)
				#self.checkTreeInterceptor (eventName)
				func = getattr(self, "event_%s" % eventName, None)
				if func:
					try:
						func(**event)
					except Exception, e:
						log.exception("Error executing event %s : %s" % (eventName, e))

				else:
					log.info(u"event %s is not found" % eventName)
		log.info  (u"webAppScheduler stopped !")

	def send(self, **kwargs):
		self.queue.put(kwargs)
		
	def event_stop(self):
		self.stop = True 
		
	def event_timeout(self):
		focus = api.getFocusObject()
		ti = focus.treeInterceptor
		webModule = focus.getWebApp()
		self.send(
			eventName="updateNodeManager",
			treeInterceptor=ti,
			webApp=webModule
			)
	
	def fakeNext(self = None):
		return True

	def event_webApp(self, name=None, obj=None, webApp=None):
		TRACE(
			u"event_webApp(name={name}, "
			u"obj={obj}, webApp={webApp})".format(
				name=name,
				obj=id(obj) if obj is not None else None,
				webApp=id(webApp) if webApp is not None else None 
				)
			)
		funcName = 'event_%s' % name
		#log.info("webApp %s will handle the event %s" % (webApp.name, name))
		func = getattr(webApp, funcName, None)
		if func:
			func(obj, self.fakeNext)
	
	def event_configurationChanged(self, webModule, focus):
		TRACE(
			u"event_configurationChanged("
			u"webModule={webModule}, focus={focus})".format(
				webModule=id(webModule) if webModule is not None else None,
				focus=id(focus) if focus is not None else None
				)
			)
		# The updated WebModule is a new object in the store.
		# Older references to the WebModule, MarkerManager or
		# NodeManager should not be used anymore.
		# Removing older cached references ensures a proper reload.
		def generator():
			yield focus
			if hasattr(focus, "treeInterceptor"):
				yield focus.treeInterceptor
			else:
				log.error("Focus has no treeInterceptor")
			obj = focus
			while hasattr(obj, "parent"):
				obj = obj.parent
				yield obj
		try:
			for obj in generator():
				if hasattr(obj, "_webApp"):
					delattr(obj, "_webApp")
				if hasattr(obj, "nodeManager"):
					delattr(obj, "nodeManager")
		except:
			log.exception("While clearing cached references")
		# Clear the pending events queue as well.
		self.queue = Queue.Queue()
		newWebModule = focus.getWebApp()
		newMarkerManager = newWebModule.markerManager \
			if newWebModule is not None else None
		TRACE(
			u"event_configurationChanged("
			u"webModule={webModule}, focus={focus}): "
			u"newWebModule={newWebModule}"
			u"newMarkerManager={newMarkerManager}".format(
				webModule=id(webModule) if webModule is not None else None,
				focus=id(focus) if focus is not None else None,
				newWebModule=id(newWebModule)
					if newWebModule is not None else None,
				newMarkerManager=id(newMarkerManager)
					if newMarkerManager is not None else None
				)
			)

	def event_treeInterceptor_gainFocus(self, treeInterceptor, firstGainFocus):
		TRACE(
			u"event_treeInterceptor_gainFocus("
			u"treeInterceptor: {treeInterceptor}, "
			u"firstGainFocus: {firstGainFocus})".format(
				treeInterceptor=id(treeInterceptor)
					if treeInterceptor is not None else None,
				firstGainFocus=firstGainFocus
				)
			)
		# TODO: Isn't it dead code?
		log.error("event_treeInterceptor_gainFocus")
		hadFirstGainFocus=treeInterceptor._hadFirstGainFocus
		treeInterceptor._hadFirstGainFocus = True
		if not hadFirstGainFocus:
			# This treeInterceptor is gaining focus for the first time.
			# Fake a focus event on the focus object, as the treeInterceptor may have missed the actual focus event.
			#focus = api.getFocusObject()
			#self.event_gainFocus(focus, lambda: focus.event_gainFocus())
			if not treeInterceptor.passThrough:
				# We only set the caret position if in browse mode.
				# If in focus mode, the document must have forced the focus somewhere,
				# so we don't want to override it.
				initialPos = treeInterceptor._getInitialCaretPos()
				if initialPos:
					treeInterceptor.selection = treeInterceptor.makeTextInfo(initialPos)
				#browseMode.reportPassThrough(treeInterceptor)
		self.send(eventName="updateNodeManager", treeInterceptor=treeInterceptor)

	def event_checkWebAppManager(self):
# 		TRACE(u"event_checkWebAppManager")
		focus = api.getFocusObject()
		webApp = focus.getWebApp()
		TRACE(u"event_checkWebAppManager: webApp={webApp}".format(
			webApp=id(webApp) if webApp is not None else None
			))
		if webApp:
			treeInterceptor = focus.treeInterceptor
			TRACE(
				u"event_checkWebAppManager: "
				u"treeInterceptor={treeInterceptor}".format(
					treeInterceptor=id(treeInterceptor)
						if treeInterceptor is not None else None
					)
				)
			if treeInterceptor:
				#webApp.treeInterceptor = treeInterceptor
				nodeManager = getattr(treeInterceptor, "nodeManager", None)
				TRACE(
					u"event_checkWebAppManager: "
					u"nodeManager={nodeManager}".format(
						nodeManager=id(nodeManager)
							if nodeManager is not None else None
						)
					)
				if nodeManager:
					webApp.markerManager.update(nodeManager)
		
	def event_updateNodeManager(self, treeInterceptor, webApp=None):
		TRACE(
			u"event_updateNodeManager("
			u"treeInterceptor={treeInterceptor}, "
			u"webApp={webApp})".format(
				treeInterceptor=id(treeInterceptor)
					if treeInterceptor is not None else None,
				webApp=id(webApp) if webApp is not None else None
				)
			)
		if treeInterceptor is None:
			return
		if hasattr(treeInterceptor, "nodeManager"):
			treeInterceptor.nodeManager.update ()
		else:
			from . import nodeHandler
			treeInterceptor.nodeManager = nodeHandler.NodeManager(treeInterceptor, self.onNodeMoveto)
# 		if webApp:
# 			webApp.treeInterceptor = treeInterceptor

	def event_nodeManagerUpdated(self, nodeManager):
		TRACE(
			u"event_nodeManagerUpdated("
			u"nodeManager={nodeManager})".format(
				nodeManager=id(nodeManager)
					if nodeManager is not None else None
				)
			)
		self.send(eventName="checkWebAppManager")

	def event_markerManagerUpdated(self, markerManager):
		TRACE(
			u"event_markerManagerUpdated("
			u"markerManager={markerManager})".format(
				markerManager=id(markerManager)
					if markerManager is not None else None
				)
			)
		markerManager.checkPageTitle()
		# markerManager.checkAutoAction()

	def event_gainFocus(self, obj):
		pass

	def checkTreeInterceptor(self, eventName):
		TRACE(
			u"checkTreeInterceptor(eventName={eventName})".format(
				eventName=eventName
				)
			)
		obj = api.getFocusObject()
		if not obj or not hasattr(obj, "treeInterceptor") or obj.treeInterceptor is None:
			return
		ti = obj.treeInterceptor
		if not ti.isReady:
			return
			
		if ti != self.lastTreeInterceptor:
			self.lastTreeInterceptor = ti
			log.info("new treeInterceptor")
			self.lastSize = 0
		try:
			info = ti.makeTextInfo(textInfos.POSITION_LAST)
			size = info._endOffset
			if size != self.lastSize:
				self.lastSize = size
				log.info(u"taille : %d" % size)
		except Exception:
			pass

	def onNodeMoveto(self, node, reason):
		TRACE(
			u"onNodeMoveto(node={node}, reason={reason})".format(
				node=id(node) if node is not None else None,
				reason=reason
				)
			)
		focus = api.getFocusObject()
		webModule = focus.getWebApp()
		useInternalBrowser = False
	
		if webModule is not None:
			scheduler.send(
				eventName="webApp",
				name='node_gainFocus',
				obj=node, webApp=webModule
				)
			webModule.widgetManager.claimVirtualBufferWidget(reason)
			if useInternalBrowser is True or webModule.activeWidget is not None:
				beep(300, 30)
				wx.CallAfter(webModule.presenter.display, node)
