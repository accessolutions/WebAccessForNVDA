# globalPlugins/webAccess/ruleHandler/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2016 Accessolutions (http://accessolutions.fr)
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

__version__ = "2017.11.27"

__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import wx
import addonHandler
addonHandler.initTranslation()
import api
import baseObject
import browseMode
import controlTypes
import gui
import inputCore
import sayAllHandler
import speech
import textInfos
import threading
import ui
from logHandler import log
from .. import nodeHandler
from .. import webAppScheduler
from ..widgets import genericCollection
from ..webAppLib import *

markerActions = ["moveto", "sayall", "speak", "activate", "mouseMove"]
markerActionsDic = {
				# Translators: Action name
				"moveto" : pgettext("webAccess.action", "Move to"),
				# Translators: Action name
				"sayall" : pgettext("webAccess.action", "Say all"), 
				# Translators: Action name
				"speak" : pgettext("webAccess.action", "Speak"),
				# Translators: Action name
				"activate" : pgettext("webAccess.action", "Activate"),
				# Translators: Action name
				"mouseMove" : pgettext("webAccess.action", "Mouse move"),
				}


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
		super(MarkerManager,self).__init__()
		self._ready = False
		self.webApp = webApp
		self.nodeManager = None
		self.nodeManagerIdentifier = None
		self.markerQueries = []
		self.lock = threading.RLock()
		self.markerResults = []
		self.pendingMoveto = None 
		self.triggeredIdentifiers = []
		self.defaultMarkerScripts = DefaultMarkerScripts(u"Aucun marqueur associé à cette touche")
		webApp.widgetManager.register(MarkerGenericCollection)

	def setQueriesData(self, queryData):
		self.markerQueries = []
		self.markerResults = []
		for qd in queryData:
			if qd["class"] == "Virtual":
				query = VirtualMarkerQuery(self, qd)
				self.addQuery(query)

	def getQueriesData(self, onlyUser=False):
		queryData = []
		for query in self.markerQueries:
			if not onlyUser or query.user:
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

	def getQueries(self, onlyUser=False):
		queries = []
		for q in self.markerQueries:
			if not onlyUser or q.user:
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
		dic = {
			# Translators: Action name
			"moveto" : pgettext("webAccess.action", "Move to"),
			# Translators: Action name
			"sayall" : pgettext("webAccess.action", "Say all"), 
			# Translators: Action name
			"speak" : pgettext("webAccess.action", "Speak"),
			# Translators: Action name
			"activate" : pgettext("webAccess.action", "Activate"),
			# Translators: Action name
			"mouseMove" : pgettext("webAccess.action", "Mouse move"),
			}
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

	def update(self, nodeManager=None, force=False):
		with self.lock:
			self._ready = False
			if nodeManager is not None:
				self.nodeManager = nodeManager
			if not self.nodeManager.isReady:
				return False
			if not force and self.nodeManagerIdentifier == self.nodeManager.identifier:
				# already updated
				self._ready = True
				return False
			t = logTimeStart()
			self.markerResults = []
			for query in self.markerQueries:
				results = query.getResults()
				self.markerResults += results
			self.markerResults.sort()
			self.nodeManagerIdentifier = self.nodeManager.identifier
			self._ready = True
			#logTime("update marker", t)
			if self.isReady:
				webAppScheduler.scheduler.send(eventName="markerManagerUpdated", markerManager=self)
				return True
		return False
		
	def checkPageTitle(self):
		title = self.getPageTitle()
		if title != self.webApp.activePageTitle:
			self.webApp.activePageTitle = title
			webAppScheduler.scheduler.send(eventName="webApp", name="webApp_pageChanged", obj=title, webApp=self.webApp)
			return True
		return False

	def checkAutoAction(self):
		countMoveto = 0
		with self.lock:
			if not self.isReady:
				return
			i = 0
			for result in self.markerResults:
				i += 1
				if result.markerQuery.autoAction:
					controlIdentifier = result.node.controlIdentifier
					if not controlIdentifier in self.triggeredIdentifiers:
						self.triggeredIdentifiers.append(controlIdentifier)
						speechOn()
						speech.cancelSpeech()
						autoActionName = result.markerQuery.autoAction
						func = getattr(result, "script_%s" % autoActionName)
						if autoActionName == "speak":
							playWebAppSound("errorMessage")
							#sleep(0.5)
						elif autoActionName == "moveto":
							countMoveto += 1
							if countMoveto > 1:
								func = None
						if func:
							func(None)
		
	def checkPendingActions(self):
		if not self.isReady:
			self.pendingMoveto = None
			return
		if self.pendingMoveto is not None:
			wx.CallAfter(self.pendingMoveto.script_moveto, None)
			self.pendingMoveto = None
			
	def requestMoveto(self, result):
		if not self.isReady:
			self.pendingMoveto = None
			return
		self.pendingMoveto = result
		
	def getPageTitle(self):
		with self.lock:
			if not self.isReady:
				return None
			for result in self.markerResults:
				if result.markerQuery.isPageTitle:
					return result.text
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
		r.script_moveto(None, fromQuickNav=True)
		
	def focusPreviousResult(self, name=None):
		r = self.getPreviousResult(name)
		if r is None:
			playWebAppSound("keyError")
			sleep(0.2)
			ui.message(u"Pas de marqueur")
			return
		r.script_moveto(None, fromQuickNav=True)
		
	def script_refreshMarkers(self, gesture):
		ui.message(u"refresh markers")
		self.update()
		
	def script_nextMarker(self, gesture):
		self.focusNextResult()

	def script_previousMarker(self, gesture):
		self.focusPreviousResult()

	def script_essai(self, gesture):
		ui.message(u"essai")
		ti = html.getTreeInterceptor()
		obj = ti.rootNVDAObject
		api.setNavigatorObject(obj)
		return
		t = logTimeStart()
		treeInterceptor = html.getTreeInterceptor()
		info = treeInterceptor.makeTextInfo(textInfos.POSITION_ALL)
		text=NVDAHelper.VBuf_getTextInRange(treeInterceptor.VBufHandle,info._startOffset,info._endOffset,True)
		commandList=XMLFormatting.XMLTextParser().parse(text)
		#text = info.getTextWithFields()
		logTime("all text : %d " % len(text), t)
		beep()


	__gestures = {
				"kb:control+nvda+r" : "refreshMarkers",
				"kb:pagedown" : "nextMarker",
				"kb:pageup" : "previousMarker",
				"kb:alt+control+shift+e" : "essai",
				}


class MarkerResult(baseObject.ScriptableObject):
	
	def __init__(self, markerQuery):
		super(MarkerResult,self).__init__()
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
	
	def __lt__(self, other):
		raise NotImplementedError

	def getDisplayString(self):
		gestures = ""
		for identifier in self._gestureMap.keys():
			source, main = inputCore.getDisplayTextForGestureIdentifier(identifier)
			gestures += main + " "
		#g = inputCore.getDisplayTextForGestureIdentifier(identifier)
		return self.markerQuery.name + " " + gestures
	
class VirtualMarkerResult(MarkerResult):
	
	def __init__(self, markerQuery, node):
		func = lambda self, gesture: getattr(self.markerQuery.markerManager.webApp, "action_clickMenu")(self)
		setattr(self.__class__, "script_clickMenu", func)
		super(VirtualMarkerResult ,self).__init__(markerQuery)
		self.node = node
	
	def script_moveto(self, gesture, fromQuickNav=False, fromSpeak=False):
		reason = nodeHandler.REASON_FOCUS
		if not fromQuickNav:
			reason = nodeHandler.REASON_SHORTCUT
		if fromSpeak:
			# Translators: Speak rule name on "Move to" action
			speech.speakMessage(_("Move to %s") % self.markerQuery.name)
		elif self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
		if self.markerQuery.createWidget:
			self.node.moveto(reason)
			return
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor or not treeInterceptor.isReady:
			return
		focusObject = api.getFocusObject()
		try:
			nodeObject = self.node.getTextInfo().NVDAObjectAtStart
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
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.name)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		treeInterceptor.passThrough = self.markerQuery.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough 
		self.node.activate()
		
	def script_speak(self, gesture):
		repeat = scriptHandler.getLastScriptRepeatCount()
		if repeat == 0:
			if self.markerQuery.sayName:
				speech.speakMessage(self.markerQuery.name)
			ui.message(self.node.getTreeInterceptorText())
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

	def script_custom(self, gesture):
		webApp = self.markerQuery.markerManager.webApp
		if not hasattr(self.markerQuery, "customActionName"):
			ui.message(_("customAction not found"))
			return
		action = "action_%s" % self.markerQuery.customActionName
		log.info("custom webapp : %s" % webApp)
		if hasattr(webApp, action):
			getattr(webApp, action)(self)
		else:
			ui.message(u"%s introuvable" % action)

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
		self.pageIdentifier = None
		self.user = False
		self.skip = False

	def getResults(self):
		return []
	
	def getData(self):
		return None
	
	def getDisplayString(self):
		gestures = ""
		for identifier in self.gestures.keys():
			source, main = inputCore.getDisplayTextForGestureIdentifier(identifier)
			gestures += main + " "
		#g = inputCore.getDisplayTextForGestureIdentifier(identifier)
		return self.name + " " + gestures
	
	def script_notFound(self, gesture):
		speech.speakMessage(u"%s introuvable" % self.name)

class VirtualMarkerQuery(MarkerQuery):
	
	def __init__(self, markerManager, dic):
		super(VirtualMarkerQuery,self).__init__(markerManager)
		dic["class"] = "Virtual"
		self.dic = dic
		self.name = dic["name"]
		self.pageIdentifier = dic.get("pageIdentifier", None)
		self.user= dic.get("user", False)
		self.gestures= dic.get("gestures", {})
		gesturesMap = {}
		for gestureIdentifier in self.gestures.keys():
			gesturesMap[gestureIdentifier] = "notFound"
		self.bindGestures(gesturesMap)
		self.autoAction= dic.get("autoAction", None)
		self.formMode = dic.get("formMode", False)
		self.sayName = dic.get("sayName", True)
		self.skip = dic.get("skip", False)
		self.isPageTitle = dic.get("isPageTitle", False)
		self.index = dic.get("index", 0)
		self.multiple = dic.get("multiple", True)
		self.createWidget = dic.get("createWidget", False)

	def __eq__(self, other):
		return self.dic == other.dic

	def getData(self):
		return self.dic
		
	def addSearchKwargs(self, dic, argName, strArg):
		if strArg is None or strArg == "":
			return
		if argName == "text" and strArg[0] == "<":
			dic["prev_text"] = strArg[1:]
			return
		eq = []
		notEq = []
		_in = []
		notIn = []
		argList = strArg.split("|")
		for arg in argList:
			if arg == "":
				continue
			if arg[0] == "!":
				if "*" in arg:
					notIn.append(arg[1:])
				else:
					notEq.append(arg[1:])
			else:
				if "*" in arg:
					_in.append(arg)
				else:
					eq.append(arg)
		if eq != []:
			dic["eq_"+argName] = eq
		if notEq != []:
			dic["notEq_"+argName] = notEq
		if _in != []:
			dic["in_"+argName] = _in
		if notIn != []:
			dic["notIn_"+argName] = notIn

	def getResults(self, widget=False):
		t = logTimeStart()
		dic = self.dic
		kwargs = {}
		text = dic.get("text", None)
		if text is not None:
			if text[0:1] == "#":
				# use the named method in the webApp script instead of the query dictionnary
				funcName ="getResults_" + text[1:]
				func = getattr(self.markerManager.webApp, funcName)
				if func is not None:
					return func(self)
				raise
		self.addSearchKwargs(kwargs, "text", text)
		role = dic.get("role", None)
		if role:
			kwargs["eq_role"] = role
		self.addSearchKwargs(kwargs, "tag", dic.get("tag", None))
		self.addSearchKwargs(kwargs, "id", dic.get("id", None))
		self.addSearchKwargs(kwargs, "className", dic.get("className", None))
		self.addSearchKwargs(kwargs, "src", dic.get("src", None))
		
		results = []
		nodeList = self.markerManager.nodeManager.searchNode(**kwargs)
		#logTime(u"searchNode %s, %d results" % (self.name, len(nodeList)), t)
		i = 0
		for node in nodeList:
			i += 1
			r = VirtualMarkerResult(self, node)
			if r.markerQuery.isPageTitle:
				r.text = node.getTreeInterceptorText()
			if self.index > 0:
				if self.index == i:
					results.append(r)
					break
				else:
					continue
			results.append(r)
			if not widget and not self.multiple:
				break
		return results

