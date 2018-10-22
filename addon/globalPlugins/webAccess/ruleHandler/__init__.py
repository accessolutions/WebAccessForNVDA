# globalPlugins/webAccess/ruleHandler/__init__.py
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


import addonHandler
addonHandler.initTranslation()


from collections import OrderedDict
import threading
import time
import wx

import api
import baseObject
import browseMode
import controlTypes
import gui
import inputCore
from logHandler import log
import sayAllHandler
import speech
import textInfos
import ui

from .. import nodeHandler
from .. import webAppScheduler
from ..widgets import genericCollection
from ..webAppLib import *
from . import contextTypes


TRACE = lambda *args, **kwargs: None
#TRACE = log.info


builtinRuleActions = OrderedDict()
# Translators: Action name
builtinRuleActions["moveto"] = pgettext("webAccess.action", "Move to")
# Translators: Action name
builtinRuleActions["sayall"] = pgettext("webAccess.action", "Say all") 
# Translators: Action name
builtinRuleActions["speak"] = pgettext("webAccess.action", "Speak")
# Translators: Action name
builtinRuleActions["activate"] = pgettext("webAccess.action", "Activate")
# Translators: Action name
builtinRuleActions["mouseMove"] = pgettext("webAccess.action", "Mouse move")
# Translators: Action name
builtinRuleActions["noAction"] = pgettext("webAccess.action", "No action")


def showCreator(context):
	return showEditor(context, new=True)

def showEditor(context, new=False):
	from ..gui import ruleEditor
	if new:
		if "rule" in context:
			del context["rule"]
		if "data" in context:
			del context["data"]["rule"]
	return ruleEditor.show(context)

def showManager(context):
	api.processPendingEvents()
	webModule = context["webModule"]
	markerManager = webModule.markerManager
	if not markerManager.isReady:
		ui.message(u"Marqueurs non disponibles")
		return
	focusObject = context["focusObject"]
	context["rule"] = markerManager.getCurrentResult(focusObject=focusObject)
	from ..gui import rulesManager
	rulesManager.show(context)


class MarkerGenericCollection(genericCollection.GenericCollection):
	
	@classmethod
	def useVirtualBuffer(cls):
		return True

	@classmethod
	def getInstanceList(cls, webApp, nodeManager):
		instanceList = []
		for query in webApp.markerManager.markerQueries:
			if query.createWidget:
				resultList = query.getResults(widget=True)
				nodeList = [] 
				for result in resultList:
					nodeList.append(result.node)
				if len(nodeList) > 0:
					instance = MarkerGenericCollection(webApp)
					instance._collection = nodeList
					instance._query = query
					instance.name = query.name
					instance.brailleName = query.name
					instanceList.append(instance)
		return instanceList

	def __init__(self, webApp, obj=None):
		self.supportSearch = True
		super(MarkerGenericCollection, self).__init__(webApp)
		self.autoEnter = False


class DefaultMarkerScripts(baseObject.ScriptableObject):
	
	def __init__(self, warningMessage):
		super(DefaultMarkerScripts,self).__init__()
		self.warningMessage = warningMessage
		for ascii in range(ord("a"), ord("z")+1):
			character = chr(ascii)
			self.__class__.__gestures["kb:control+shift+%s" % character] = "notAssigned"

	def script_notAssigned(self, gesture):
		playWebAppSound("keyError")
		sleep(0.2)
		ui.message(self.warningMessage)

	__gestures = {}


class MarkerManager(baseObject.ScriptableObject):
	
	def __init__(self, webApp):
# 		TRACE(
# 			u"MarkerManager.__init__("
# 			u"self={self}, webApp={webApp}".format(
# 				self=id(self),
# 				webApp=id(webApp) if webApp is not None else None
# 				)
# 			)
		super(MarkerManager,self).__init__()
		self._ready = False
		self.webApp = webApp
		self.nodeManager = None
		self.nodeManagerIdentifier = None
		self.markerQueries = []
		self.lock = threading.RLock()
		self.markerResults = []
		self.triggeredIdentifiers = []
		self.lastAutoMoveto = None
		self.lastAutoMovetoTime = 0
		self.defaultMarkerScripts = DefaultMarkerScripts(u"Aucun marqueur associé à cette touche")
		self.timerCheckAutoAction = None
		webApp.widgetManager.register(MarkerGenericCollection)

	def setQueriesData(self, queryData):
		self.markerQueries = []
		self.markerResults = [] 
		for qd in queryData:
			query = VirtualMarkerQuery(self, qd)
			self.addQuery(query)

	def getQueriesData(self):
		queryData = []
		for query in self.markerQueries:
			queryData.append(query.getData())
		return queryData 
	
	def addQuery(self, query):
		for q in self.markerQueries:
			if q == query:
				return
		self.markerQueries.append(query)

	def removeQuery(self, query):
		self.removeResults(query)
		for i in range(len(self.markerQueries), 0, -1):
			if self.markerQueries[i-1] == query:
				del self.markerQueries[i-1]

	def getQueryByName(self, name):
		for q in self.markerQueries:
			if q.name == name:
				return q
		return None

	def getQueries(self):
		queries = []
		for q in self.markerQueries:
			queries.append(q)
		return queries
	
	def getResults(self):
		if not self.isReady:
			return []
		return self.markerResults
	
	def getResultsByName(self, name):
		if not self.isReady:
			return []
		results = []
		for r in self.markerResults:
			if r.markerQuery.name == name:
				results.append(r)
		return results

	def removeResults(self, query):
		for i in range(len(self.markerResults), 0, -1):
			if self.markerResults[i-1].markerQuery== query:
				del self.markerResults[i-1]

	def getActions(self):
		dic = builtinRuleActions.copy ()
		prefix = "action_"
		for key in dir(self.webApp):
			if key[:len(prefix)] == prefix:
				actionName = key[len(prefix):]
				dic[actionName] = actionName
		return dic
				
	def getMarkerScript(self, gesture, globalMapScripts):
		func = scriptHandler._getObjScript(self, gesture, globalMapScripts)
		if func:
			return func
		pmList = self.getResults() + self.getQueries()
		for result in pmList:
			func = scriptHandler._getObjScript(result, gesture, globalMapScripts)
			if func:
				return func
		func = scriptHandler._getObjScript(self.defaultMarkerScripts, gesture, globalMapScripts)
		if func:
			return func
		return None
	
	def _get_isReady(self):
		if not self._ready or not self.nodeManager or not self.nodeManager.isReady or self.nodeManager.identifier != self.nodeManagerIdentifier:
			return False
		return True

	def event_nodeManagerTerminated(self, nodeManager):
		TRACE(
			u"event_nodeManagerTerminated("
			u"self={self}, nodeManager={nodeManager})".format(
				self=id(self),
				nodeManager=id(nodeManager)
					if nodeManager is not None else None
				)
			)
		if self.nodeManager != nodeManager:
			log.warn(u"nodeManager different than self.nodeManager")
			return
		self._ready = False
		if self.timerCheckAutoAction:
			self.timerCheckAutoAction.cancel()
		self.nodeManager = None
		del self.markerResults[:]
		for q in self.markerQueries:
			q.resetResults () 

	def update(self, nodeManager=None, force=False):
		TRACE(
			u"update(self={self}, "
			u"nodeManager={nodeManager}, force={force}"
			u"): Waiting for lock".format(
				self=id(self),
				nodeManager=id(nodeManager) if nodeManager is not None else None,
				force=force
				)
			)
		with self.lock:
			TRACE(
				u"update(self={self}, "
				u"nodeManager={nodeManager}, force={force}"
				u"): Obtained lock".format(
					self=id(self),
					nodeManager=id(nodeManager) if nodeManager is not None else None,
					force=force
					)
				)
			self._ready = False
			if nodeManager is not None:
				self.nodeManager = nodeManager
			if self.nodeManager is None or not self.nodeManager.isReady:
				return False
			self.nodeManager.addBackend (self)
			if not force and self.nodeManagerIdentifier == self.nodeManager.identifier:
				# already updated
				self._ready = True
				return False
			t = logTimeStart()
			self.markerResults = []
			for query in self.markerQueries:
				query.resetResults()
				
			for query in self.markerQueries:
				results = query.getResults()
				self.markerResults += results
				self.markerResults.sort()
			self.nodeManagerIdentifier = self.nodeManager.identifier
			self._ready = True
			#logTime("update marker", t)
			if self.isReady:
				webAppScheduler.scheduler.send(eventName="markerManagerUpdated", markerManager=self)
				self.timerCheckAutoAction = threading.Timer(
					1, # Accepts floating point number for sub-second precision
					self.checkAutoAction
					)
				self.timerCheckAutoAction.start()				
				return True
			else:
				log.error("Not yet")
		return False
		
	def checkPageTitle(self):
		title = self.getPageTitle()
		if title != self.webApp.activePageTitle:
			self.webApp.activePageTitle = title
			webAppScheduler.scheduler.send(eventName="webApp", name="webApp_pageChanged", obj=title, webApp=self.webApp)
			return True
		return False

	def checkAutoAction(self):
		TRACE(u"checkAutoAction(self={self}: Waiting for lock".format(
			self=id(self)
			))
		with self.lock:
			TRACE(u"checkAutoAction(self={self}): Obtained lock".format(
				self=id(self)
				))
			if not self.isReady:
				TRACE(u"checkAutoAction(self={self}): Not ready".format(
					self=id(self)
					))
				return
			TRACE(u"checkAutoAction(self={self}): Ready".format(
				self=id(self)
				))
			countMoveto = 0
			funcMoveto = None
			firstCancelSpeech = True
			for result in self.markerResults:
				if result.markerQuery.autoAction:
					controlIdentifier = result.node.controlIdentifier
					if not controlIdentifier in self.triggeredIdentifiers:
						self.triggeredIdentifiers.append(controlIdentifier)
						speechOn()
						autoActionName = result.markerQuery.autoAction
						func = getattr(result, "script_%s" % autoActionName)
						if autoActionName == "speak":
							playWebAppSound("errorMessage")
						elif autoActionName == "moveto":
							countMoveto += 1
							if countMoveto == 1:
								if func.__name__== self.lastAutoMoveto \
									and time.time() - self.lastAutoMovetoTime < 4:
									# no autoMoveto of same rule before 4 seconds
									continue
								else:
									funcMoveto = func
							func = None
						if func:
							if firstCancelSpeech:
								speech.cancelSpeech()
								firstCancelSpeech = False
							func(None)
			if funcMoveto is not None:
				if firstCancelSpeech:
					speech.cancelSpeech()
					firstCancelSpeech = False
				self.lastAutoMoveto = funcMoveto.__name__
				self.lastAutoMovetoTime = time.time()
				funcMoveto (None)
		
	def getPageTitle(self):
		with self.lock:
			if not self.isReady:
				return None
			for result in self.markerResults:
				if result.markerQuery.isPageTitle:
					return result.node.getTreeInterceptorText()
			return ""

	def getNextResult(self, name=None):
		if not self.isReady:
			return None
		if len(self.markerResults) < 1:
			return None
	
		# search from the actual caret position
		info = html.getCaretInfo()
		if info is None:
			return None
		for r in self.markerResults:
			if name is not None and r.markerQuery.name != name:
				continue
			if r.markerQuery.skip:
				continue
			if hasattr(r, "node") and info._startOffset < r.node.offset:
				return r

		# if not ffound, return the first result
		for r in self.markerResults:
			if not r.markerQuery.skip:
				playWebAppSound("loop")
				sleep(0.2)
				return r
		return None

	def getPreviousResult(self, name=None):
		if not self.isReady:
			return None
		if len(self.markerResults) < 1:
			return None

		# search from the actual caret position
		info = html.getCaretInfo()
		if info is None:
			return None
		for r in reversed(self.markerResults):
			if name is not None and r.markerQuery.name != name:
				continue 
			if r.markerQuery.skip:
				continue
			if hasattr(r, "node") and info._startOffset > r.node.offset:
				return r
			
		# if not ffound, return the latest result
		for r in reversed(self.markerResults):
			if not r.markerQuery.skip:
				playWebAppSound("loop")
				sleep(0.2)
				return r
		return None

	def getCurrentResult(self, focusObject=None):
		if not self.isReady:
			return None
		if len(self.markerResults) < 1:
			return None
		info = html.getCaretInfo(focusObject=focusObject)
		if info is None:
			return None
		offset = info._startOffset
		for r in reversed(self.markerResults):
			if hasattr(r, "node") and offset >= r.node.offset:
				return r
		return None

	def focusNextResult(self, name=None):
		r = self.getNextResult(name)
		if r is None:
			playWebAppSound("keyError")
			sleep(0.2)
			ui.message(u"Pas de marqueur")
			return
		if hasattr (self.webApp, "event_movetoFromQuickNav"):
			self.webApp.event_movetoFromQuickNav (r)
		else:
			r.script_moveto(None, fromQuickNav=True)
		
	def focusPreviousResult(self, name=None):
		r = self.getPreviousResult(name)
		if r is None:
			playWebAppSound("keyError")
			sleep(0.2)
			ui.message(u"Pas de marqueur")
			return
		if hasattr (self.webApp, "event_movetoFromQuickNav"):
			self.webApp.event_movetoFromQuickNav (r)
		else:
			r.script_moveto(None, fromQuickNav=True)
		
	def script_refreshMarkers(self, gesture):
		ui.message(u"refresh markers")
		self.update()
		
	def script_nextMarker(self, gesture):
		self.focusNextResult()

	def script_previousMarker(self, gesture):
		self.focusPreviousResult()

# 	def script_essai(self, gesture):
# 		ui.message(u"essai")
# 		ti = html.getTreeInterceptor()
# 		obj = ti.rootNVDAObject
# 		api.setNavigatorObject(obj)
# 		return
# 		t = logTimeStart()
# 		treeInterceptor = html.getTreeInterceptor()
# 		info = treeInterceptor.makeTextInfo(textInfos.POSITION_ALL)
# 		text=NVDAHelper.VBuf_getTextInRange(treeInterceptor.VBufHandle,info._startOffset,info._endOffset,True)
# 		commandList=XMLFormatting.XMLTextParser().parse(text)
# 		#text = info.getTextWithFields()
# 		logTime("all text : %d " % len(text), t)


	__gestures = {
		"kb:control+nvda+r" : "refreshMarkers",
		"kb:pagedown" : "nextMarker",
		"kb:pageup" : "previousMarker",
# 		"kb:alt+control+shift+e" : "essai",
	}


class MarkerResult(baseObject.ScriptableObject):
	
	def __init__(self, markerQuery):
		super(MarkerResult,self).__init__()
		prefix = "action_"
		for key in dir(markerQuery.markerManager.webApp):
			if key[:len(prefix)] == prefix:
				actionName = key[len(prefix):]
				func = lambda self, gesture, actionName=actionName: getattr(self.markerQuery.markerManager.webApp, "action_%s" % actionName)(self)
				setattr(self.__class__, "script_%s" % actionName, func)
		self.markerQuery = markerQuery
		self.bindGestures(markerQuery.gestures)

	def check(self):
		raise NotImplementedError

	def _get_name(self):
		return self.markerQuery.name
	
	def script_moveto(self, gesture):
		raise NotImplementedError

	def script_sayall(self, gesture):
		raise NotImplementedError
		
	def script_activate(self, gesture):
		raise NotImplementedError
		
	def script_speak(self, gesture):
		raise NotImplementedError

	def script_mouseMove(self, gesture):
		raise NotImplementedError
	
	def script_noAction(self, gesture):
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
	
	def __lt__(self, other):
		raise NotImplementedError

	def getDisplayString(self):
		return u" ".join(
			[self.name]
			+ [
				inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
				for identifier in self._gestureMap.keys()
				]
			)
	
class VirtualMarkerResult(MarkerResult):
	
	def __init__(self, markerQuery, node):
		super(VirtualMarkerResult ,self).__init__(markerQuery)
		self.node = node
	
	def script_moveto(self, gesture, fromQuickNav=False, fromSpeak=False):
		if self.node.nodeManager is None:
			return
		reason = nodeHandler.REASON_FOCUS
		if not fromQuickNav:
			reason = nodeHandler.REASON_SHORTCUT
		if fromSpeak:
			# Translators: Speak rule name on "Move to" action
			speech.speakMessage(_(u"Move to {ruleName}").format(
				ruleName=self.markerQuery.name))
		elif self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
		if self.markerQuery.createWidget:
			self.node.moveto(reason)
			return
		treeInterceptor = self.node.nodeManager.treeInterceptor
		if not treeInterceptor or not treeInterceptor.isReady:
			return
		focusObject = api.getFocusObject()
		try:
			nodeObject = self.node.getNvdaObject ()
		except:
			nodeObject = None
		treeInterceptor.passThrough = self.markerQuery.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough 
		self.node.moveto(reason)
		if not self.markerQuery.formMode:
			speechOff()
			html.speakLine()
			speechOn()
			#info = html.getCaretInfo()
			#info.expand(textInfos.UNIT_LINE)
			#speech.speakTextInfo(info, reason=controlTypes.REASON_FOCUS, unit=textInfos.UNIT_LINE)
			sleep(0.3)
			#log.info(u"trace")
			html.speakLine()
		elif nodeObject == focusObject and focusObject is not None:
			focusObject.reportFocus()
	
	def script_sayall(self, gesture, fromQuickNav=False):
		speech.cancelSpeech()
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		speechOff()
		treeInterceptor.passThrough = False
		browseMode.reportPassThrough.last = treeInterceptor.passThrough 
		self.node.moveto()
		html.speakLine()
		speechOn()
		sayAllHandler.readText(sayAllHandler.CURSOR_CARET)

	def script_activate(self, gesture):
		if self.node.nodeManager is None:
			return
		if not self.markerQuery.markerManager.isReady :
			log.info (u"not ready")
			return
		treeInterceptor = self.node.nodeManager.treeInterceptor
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
		self.node.activate()
		time.sleep(0.1)
		api.processPendingEvents ()
		if not treeInterceptor:
			return
		treeInterceptor.passThrough = self.markerQuery.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough 
		
	def script_speak(self, gesture):
		repeat = scriptHandler.getLastScriptRepeatCount()
		if repeat == 0:
			if self.markerQuery.sayName:
				speech.speakMessage(self.markerQuery.name)
			wx.CallAfter(ui.message, self.node.getTreeInterceptorText())
		else:
			self.script_moveto(None, fromSpeak=True)
			
	def script_mouseMove(self, gesture):
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		treeInterceptor.passThrough = self.markerQuery.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough 
		self.node.mouseMove()

	def getTextInfo(self):
		return self.node.getTextInfo.copy()
	
	def __lt__(self, other):
		return self.node.offset < other.node.offset

	def getTitle(self):
		return self.markerQuery.name + " - " + self.node.innerText

class MarkerQuery(baseObject.ScriptableObject):
	
	def __init__(self, markerManager):
		super(MarkerQuery,self).__init__()
		self.markerManager = markerManager
		self.name = None
		self.skip = False
		self.results = None

	def resetResults (self):
		self.results = None
		
	def getResults(self):
		return []

	def _getResults(self):
		raise NotImplementedError()
	
	def getData(self):
		return None
	
	def getDisplayString(self):
		return u" ".join(
			[self.name]
			+ [
				inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
				for identifier in self._gestureMap.keys()
				]
			)
	
	def script_notFound(self, gesture):
		speech.speakMessage(_(u"{ruleName} not found").format(
			ruleName=self.name))


class VirtualMarkerQuery(MarkerQuery):
	
	def __init__(self, markerManager, dic):
		super(VirtualMarkerQuery,self).__init__(markerManager)
		self.dic = dic
		self.name = dic["name"]
		self.requiresContext = dic.get("requiresContext")
		self.gestures = dic.get("gestures", {})
		gesturesMap = {}
		for gestureIdentifier in self.gestures.keys():
			gesturesMap[gestureIdentifier] = "notFound"
		self.bindGestures(gesturesMap)
		self.autoAction = dic.get("autoAction")
		self.formMode = dic.get("formMode", False)
		self.sayName = dic.get("sayName", True)
		self.index = dic.get("index")
		self.multiple = dic.get("multiple", True)
		self.skip = dic.get("skip", False)
		self.isPageTitle = dic.get("isPageTitle", False)
		self.definesContext = dic.get("definesContext")
		self.createWidget = dic.get("createWidget", False)

	def __eq__(self, other):
		return self.dic == other.dic

	def getData(self):
		return self.dic
		
	def addSearchKwargs(self, dic, prop, expr):
		if not expr:
			return
		if prop == "text":
			if expr[0] == "<":
				dic["in_prevText"] = expr[1:]
				return
			dic["in_text"] = expr[1:]
			return
		if prop == "className":
			expr = expr.replace(" ", "&")
		for andIndex, expr in enumerate(expr.split("&")):
			eq = []
			notEq = []
			in_ = []
			notIn = []
			for expr in expr.split("|"):
				if not expr:
					continue
				if expr[0] == "!":
					if "*" in expr:
						notIn.append(expr[1:])
					else:
						notEq.append(expr[1:])
				else:
					if "*" in expr:
						in_.append(expr)
					else:
						eq.append(expr)
			for test, values in (
				("eq", eq),
				("notEq", notEq),
				("in", in_),
				("notIn", notIn),
			):
				if not values:
					continue
				key = "{test}_{prop}#{index}".format(
					test=test,
					prop=prop,
					index=andIndex
				)
				dic[key] = values
		
	def getResults(self, widget=False):
		t = logTimeStart()
		dic = self.dic
		text = dic.get("text")
# 		if text is not None:
# 			if text[0:1] == "#":
# 				# use the named method in the webApp script instead of the query dictionnary
# 				funcName ="getResults_" + text[1:]
# 				func = getattr(self.markerManager.webApp, funcName)
# 				if func is not None:
# 					return func(self)
		rootNodes = []
		excludedNodes = []
		for alternatives in dic.get("requiresContext", "").split("&"):
			alternatives = alternatives.strip()
			if not alternatives:
				continue
			if alternatives[0] == "!":
				exclude = True
				alternatives = alternatives[1:]
			else:
				exclude = False
			found = False
			for context in alternatives.split("|"):
				context = context.strip()
				if not context:
					continue
				contextQuery = self.markerManager.getQueryByName(context)
				if contextQuery is None:
					log.error(u"Rule context \"{context}\" not found".format(
						context=context
					))
					return []
				contextResults = contextQuery.getResults()
				if contextResults:
					if exclude:
						if contextQuery.definesContext != contextTypes.ZONE:
							return []
						excludedNodes += [
							result.node for result in contextResults]
					else:
						found = True
						if contextQuery.definesContext == contextTypes.ZONE:
							rootNodes += [
							result.node for result in contextResults]
			if not exclude and not found:
				return []
		
		kwargs = {}
		if rootNodes:
			kwargs["roots"] = rootNodes
		if excludedNodes:
			kwargs["exclude"] = excludedNodes
		if not self.multiple:
			kwargs["maxIndex"] = self.index or 1
		self.addSearchKwargs(kwargs, "text", text)
		# TODO: Why store role as int and not allow !/|/& ?
		role = dic.get("role", None)
		if role:
			kwargs["eq_role"] = role
		self.addSearchKwargs(kwargs, "tag", dic.get("tag"))
		self.addSearchKwargs(kwargs, "id", dic.get("id"))
		self.addSearchKwargs(kwargs, "className", dic.get("className"))
		self.addSearchKwargs(kwargs, "src", dic.get("src"))
		
		results = []
		nodeList = self.markerManager.nodeManager.searchNode(**kwargs)
		#logTime(u"searchNode %s, %d results" % (self.name, len(nodeList)), t)
		index = 0
		for node in nodeList:
			index += 1  # 1-based
			if self.index and index < self.index:
				continue
			r = VirtualMarkerResult(self, node)
			if self.isPageTitle:
				r.text = node.getTreeInterceptorText()
			results.append(r)
			if not self.multiple:
				break
		return results

