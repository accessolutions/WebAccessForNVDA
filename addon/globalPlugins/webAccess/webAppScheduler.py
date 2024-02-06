# globalPlugins/webAccess/webAppScheduler.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2021 Accessolutions (http://accessolutions.fr)
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


__version__ = "2021.03.12"
__author__ = "Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import threading
import wx

import api
import textInfos

from .overlay import WebAccessBmdti, WebAccessObject
from .webAppLib import *


try:
	from six.moves import queue
except ImportError:
	# NVDA version < 2018.3
	import queue as queue


TRACE = lambda *args, **kwargs: None  # @UnusedVariable
#TRACE = log.info


scheduler = None


class WebAppScheduler(threading.Thread):
	
	lastTreeInterceptor = None
	
	def __init__(self):
		super(WebAppScheduler,self).__init__()
		self.daemon = True
		self.queue = queue.Queue()
		global scheduler
		scheduler = self
		
	def run(self):
		self.stop = False
		while not self.stop:
			try:
				event = self.queue.get(True, 0.5)
			except queue.Empty:
				event = {"eventName": "timeout"}
			if isinstance(event, dict):
				eventName = event.pop("eventName")
				#log.info (u"eventName : %s" % eventName)
				#self.checkTreeInterceptor (eventName)
				func = getattr(self, "event_%s" % eventName, None)
				if func:
					try:
						func(**event)
					except Exception:
						log.exception("Error executing event {}".format(eventName))

				else:
					log.info("event %s is not found" % eventName)
		log.info  ("webAppScheduler stopped !")

	def send(self, **kwargs):
		self.queue.put(kwargs)
		
	def event_stop(self):
		self.stop = True 
		
	def event_timeout(self):
		focus = api.getFocusObject()
		if not (
			isinstance(focus, WebAccessObject)
			and focus.webAccess.treeInterceptor
		):
			return
		self.send(
			eventName="updateNodeManager",
			treeInterceptor=focus.webAccess.treeInterceptor,
		)
	
	def fakeNext(self = None):
		return True

	def event_webApp(self, name=None, obj=None, webApp=None):
		funcName = 'event_%s' % name
		#log.info("webApp %s will handle the event %s" % (webApp.name, name))
		func = getattr(webApp, funcName, None)
		if func:
			func(obj, self.fakeNext)
	
	def event_treeInterceptor_gainFocus(self, treeInterceptor, firstGainFocus):
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
		# TODO: Should not be triggered anymore 
		log.error("event_checkWebAppManager")
		focus = api.getFocusObject()
		webApp = focus.webAccess.webModule if isinstance(focus, WebAccessObject) else None
		TRACE("event_checkWebAppManager: webApp={webApp}".format(
			webApp=id(webApp) if webApp is not None else None
			))
		if webApp:
			treeInterceptor = focus.treeInterceptor
			if treeInterceptor:
				#webApp.treeInterceptor = treeInterceptor
				nodeManager = getattr(treeInterceptor, "nodeManager", None)
				TRACE(
					"event_checkWebAppManager: "
					"nodeManager={nodeManager}".format(
						nodeManager=id(nodeManager)
							if nodeManager is not None else None
						)
					)
				if nodeManager:
					webApp.markerManager.update(nodeManager)
		
	def event_updateNodeManager(self, treeInterceptor):
		if not (
			isinstance(treeInterceptor, WebAccessBmdti)
			and treeInterceptor.webAccess.nodeManager
		):
			return
		treeInterceptor.webAccess.nodeManager.update()

	def event_nodeManagerUpdated(self, nodeManager):
		if not (
			nodeManager
			and nodeManager.treeInterceptor
			and isinstance(nodeManager.treeInterceptor, WebAccessBmdti)
			and nodeManager.treeInterceptor.webAccess.ruleManager
		):
			return
		nodeManager.treeInterceptor.webAccess.ruleManager.update(nodeManager)

	def event_markerManagerUpdated(self, markerManager):
		# Doesn't work outside of the main thread for Google Chrome 83
		wx.CallAfter(markerManager.checkPageTitle)
		# markerManager.checkAutoAction()

	def event_gainFocus(self, obj):
		pass

	def onNodeMoveto(self, node, reason):
		focus = api.getFocusObject()
		if not isinstance(focus, WebAccessObject):
			return
		webModule = focus.webAccess.webModule
		useInternalBrowser = False
	
		if webModule is not None:
			scheduler.send(
				eventName="webApp",
				name='node_gainFocus',
				obj=node, webApp=webModule
				)
			if useInternalBrowser is True: 
				beep(300, 30)
				wx.CallAfter(webModule.presenter.display, node)
