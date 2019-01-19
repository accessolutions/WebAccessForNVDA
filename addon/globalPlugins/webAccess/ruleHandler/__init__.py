# globalPlugins/webAccess/ruleHandler/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2019 Accessolutions (http://accessolutions.fr)
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

__version__ = "2019.01.18"
__author__ = u"Frédéric Brugnot <f.brugnot@accessolutions.fr>"


from collections import OrderedDict
import threading
import time
import wx

import addonHandler
import api
import baseObject
import browseMode
import controlTypes
import gui
import inputCore
from logHandler import log
import queueHandler
import sayAllHandler
import speech
import textInfos
import textInfos.offsets
import ui

from .. import nodeHandler
from ..webAppLib import *
from .. import webAppScheduler
from ..widgets import genericCollection
from . import ruleTypes


addonHandler.initTranslation()


SCRIPT_CATEGORY = "WebAccess"


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
		self.triggeredIdentifiers = {}
		self.lastAutoMoveto = None
		self.lastAutoMovetoTime = 0
		self.defaultMarkerScripts = DefaultMarkerScripts(u"Aucun marqueur associé à cette touche")
		self.timerCheckAutoAction = None
		webApp.widgetManager.register(MarkerGenericCollection)
		self.zone = None

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
		dic = builtinRuleActions.copy()
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
	
	def getScript(self, gesture):
		func = super(MarkerManager, self).getScript(gesture)
		if func is not None:
			return func
		for result in self.getResults():
			func = result.getScript(gesture)
			if func is not None:
				return func
		for query in self.getQueries():
			func = query.getScript(gesture)
			if func is not None:
				return func
		return self.defaultMarkerScripts.getScript(gesture)
	
	def _get_isReady(self):
		if not self._ready or not self.nodeManager or not self.nodeManager.isReady or self.nodeManager.identifier != self.nodeManagerIdentifier:
			return False
		return True

	def event_nodeManagerTerminated(self, nodeManager):
		if self.nodeManager != nodeManager:
			log.warn(u"nodeManager different than self.nodeManager")
			return
		self._ready = False
		if self.timerCheckAutoAction:
			self.timerCheckAutoAction.cancel()
		self.nodeManager = None
		del self.markerResults[:]
		for q in self.markerQueries:
			q.resetResults()

	def update(self, nodeManager=None, force=False):
		with self.lock:
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
			
			for query in sorted(
				self.markerQueries,
				key=lambda query: (
					0 if query.type in (
						ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2
					) else 1
				)
			):
				results = query.getResults()
				self.markerResults += results
				self.markerResults.sort()
			if self.zone:
				if not self.zone.update():
					self.zone = None
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
		with self.lock:
			if not self.isReady:
				return
			funcMoveto = None
			firstCancelSpeech = True
			for result in self.markerResults:
				if result.markerQuery.autoAction:
					controlIdentifier = result.node.controlIdentifier
					text = result.node.getTreeInterceptorText()
					autoActionName = result.markerQuery.autoAction
					func = getattr(result, "script_%s" % autoActionName)
					lastText = self.triggeredIdentifiers.get(controlIdentifier)
					if (lastText is None or text != lastText):
						self.triggeredIdentifiers[controlIdentifier] = text
						speechOn()
						autoActionName = result.markerQuery.autoAction
						func = getattr(result, "script_%s" % autoActionName)
						if autoActionName == "speak":
							playWebAppSound("errorMessage")
						elif autoActionName == "moveto": 
							if lastText is None:
								# uniquement si c'est un nouveau controlIdentifier
								if funcMoveto is None:
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
							try:
								queueHandler.queueFunction(
									queueHandler.eventQueue,
									func,
									None
								) 
							except:
								log.exception((
									u'Error in rule "{rule}" while executing'
									u' autoAction "{autoAction}"'
								).format(
									rule=result.markerQuery.name,
									autoAction=autoActionName
								))
			if funcMoveto is not None:
				if firstCancelSpeech:
					speech.cancelSpeech()
					firstCancelSpeech = False
				self.lastAutoMoveto = funcMoveto.__name__
				self.lastAutoMovetoTime = time.time()
				queueHandler.queueFunction(
					queueHandler.eventQueue,
					funcMoveto,
					None
				) 
		
	def getPageTitle(self):
		with self.lock:
			if not self.isReady:
				return None
			return self._getPageTitle()
	
	def _getPageTitle(self):
		parts = [
			part
			for part in [
				self._getPageTitle1(),
				self._getPageTitle2(),
			]
			if part
		]
		if parts:
			return " - ".join(parts)
		# TODO: Failback first to HTML HEAD TITLE
		return api.getForegroundObject().name
	
	def _getPageTitle1(self):
		for result in self.markerResults:
			if result.markerQuery.type == ruleTypes.PAGE_TITLE_1:
				return result.value
	
	def _getPageTitle2(self):
		for result in self.markerResults:
			if result.markerQuery.type == ruleTypes.PAGE_TITLE_2:
				return result.value
	
	def getPageTypes(self):
		types = []
		with self.lock:
			if not self.isReady:
				return types
			for result in self.markerResults:
				if result.markerQuery.type == ruleTypes.PAGE_TYPE:
					types.append(result.markerQuery.name)
			return types

	def getNextResult(self, ruleType=None, name=None):
		return self._getIncrementalResult(ruleType=ruleType, name=None)
	
	def getPreviousResult(self, ruleType=None, name=None):
		return self._getIncrementalResult(
			previous=True,
			ruleType=ruleType,
			name=None
		)
	
	def _getIncrementalResult(
		self,
		previous=False,
		info=None,
		types=None,
		name=None,
		respectZone=False,
		honourSkip=True,
	):
		for result in (
			reversed(self.markerResults)
			if previous else self.markerResults
		):
			query = result.markerQuery
			if types and query.type not in types:
				continue
			if name:
				if query.name != name:
					continue
			elif honourSkip and query.skip:
				continue
			if (
				hasattr(result, "node")
				and (
					info is None
					or (
						not previous
						and info._startOffset < result.node.offset
					)
					or (previous and info._startOffset > result.node.offset)
				)
				and (
					not respectZone
					or not self.zone
					or (
						self.zone.containsNode(result.node)
						and not (
							# If respecting zone restriction, avoid returning
							# the zone itself.
							self.zone.name == result.markerQuery.name
							and self.zone.startOffset == result.node.offset
						)
					)
				)
			):
				return result
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
	
	def quickNav(
		self,
		previous=False,
		types=None,
		name=None,
		respectZone=False,
		honourSkip=True,
		cycle=True
	):
		if not self.isReady:
			playWebAppSound("keyError")
			ui.message(_("Not ready"))
			return
		
		# Search first from the current caret position
		info = html.getCaretInfo()
		
		# If not found after/before the current position, and cycle is True,
		# return the first/last result.
		for positioned in ((True, False) if cycle else (True,)):
			result = self._getIncrementalResult(
				previous=previous,
				info=info if positioned else None,
				types=types,
				name=name,
				respectZone=respectZone,
				honourSkip=honourSkip
			)
			if result:
				if not positioned:
					playWebAppSound("loop")
					sleep(0.2)
				break
		else:
			playWebAppSound("keyError")
			sleep(0.2)
			if types == (ruleTypes.ZONE,):
				# Translator: Error message in quickNav (page up/down)
				ui.message(_("No zone"))
				return
			if cycle:
				# Translator: Error message in quickNav (page up/down)
				msg = _("No marker")
			elif previous:
				# Translator: Error message in quickNav (page up/down)
				msg = _("No previous marker")
			else:
				# Translator: Error message in quickNav (page up/down)
				msg = _("No next marker")
			if respectZone and self.zone:
				msg += " "
				# Translators: Complement to quickNav error message in zone.
				msg += _("in this zone.") 
				msg += " "
				# Translators: Hint on how to cancel zone restriction.
				msg += _("Press escape to cancel zone restriction.")
			ui.message(msg)
			return
		if hasattr(self.webApp, "event_movetoFromQuickNav"):
			self.webApp.event_movetoFromQuickNav(result)
		else:
			result.script_moveto(None, fromQuickNav=True)
	
	def script_refreshMarkers(self, gesture):
		ui.message(u"refresh markers")
		self.update()
	
	def script_quickNavToNextLevel1(self, gesture):
		self.quickNav(types=(ruleTypes.ZONE,))
	
	# Translators: Input help mode message for quickNavToNextLevel1.
	script_quickNavToNextLevel1.__doc__ = _("Move to next zone.")
	
	script_quickNavToNextLevel1.category = SCRIPT_CATEGORY
	
	def script_quickNavToPreviousLevel1(self, gesture):
		self.quickNav(previous=True, types=(ruleTypes.ZONE,))
	
	# Translators: Input help mode message for quickNavToPreviousLevel1.
	script_quickNavToPreviousLevel1.__doc__ = _("Move to previous zone.")
	
	script_quickNavToPreviousLevel1.category = SCRIPT_CATEGORY
	
	def script_quickNavToNextLevel2(self, gesture):
		self.quickNav(types=(ruleTypes.ZONE, ruleTypes.MARKER))
	
	# Translators: Input help mode message for quickNavToNextLevel2.
	script_quickNavToNextLevel2.__doc__ = _("Move to next global marker.")
	
	script_quickNavToNextLevel2.category = SCRIPT_CATEGORY
	
	def script_quickNavToPreviousLevel2(self, gesture):
		self.quickNav(previous=True, types=(ruleTypes.ZONE, ruleTypes.MARKER))
	
	# Translators: Input help mode message for quickNavToPreviousLevel2.
	script_quickNavToPreviousLevel2.__doc__ = _("Move to previous global marker.")
	
	script_quickNavToPreviousLevel2.category = SCRIPT_CATEGORY
	
	def script_quickNavToNextLevel3(self, gesture):
		self.quickNav(
			types=(ruleTypes.ZONE, ruleTypes.MARKER),
			respectZone=True,
			honourSkip=False,
			cycle=False
		)
	
	# Translators: Input help mode message for quickNavToNextLevel3.
	script_quickNavToNextLevel3.__doc__ = _("Move to next local marker.")
	
	script_quickNavToNextLevel3.category = SCRIPT_CATEGORY
	
	def script_quickNavToPreviousLevel3(self, gesture):
		self.quickNav(
			previous=True,
			types=(ruleTypes.ZONE, ruleTypes.MARKER),
			respectZone=True,
			honourSkip=False,
			cycle=False
		)
	
	# Translators: Input help mode message for quickNavToPreviousLevel3.
	script_quickNavToPreviousLevel3.__doc__ = _("Move to previous local marker.")
	
	script_quickNavToPreviousLevel3.category = SCRIPT_CATEGORY
	
	__gestures = {
		"kb:control+nvda+r": "refreshMarkers",
		"kb:control+pagedown": "quickNavToNextLevel1",
		"kb:control+pageup": "quickNavToPreviousLevel1",
		"kb:pagedown": "quickNavToNextLevel2",
		"kb:pageup": "quickNavToPreviousLevel2",
		"kb:shift+pagedown": "quickNavToNextLevel3",
		"kb:shift+pageup": "quickNavToPreviousLevel3",
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
	
	def _get_value(self):
		raise NotImplementedError
	
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
	
	_cache_value = False
	
	def _get_value(self):
		return \
			self.markerQuery.customValue \
			or self.node.getTreeInterceptorText()
	
	def script_moveto(self, gesture, fromQuickNav=False, fromSpeak=False):
		if self.node.nodeManager is None:
			return
		query = self.markerQuery
		reason = nodeHandler.REASON_FOCUS
		if not fromQuickNav:
			reason = nodeHandler.REASON_SHORTCUT
		if fromSpeak:
			# Translators: Speak rule name on "Move to" action
			speech.speakMessage(_(u"Move to {ruleName}").format(
				ruleName=query.name))
		elif self.markerQuery.sayName:
			speech.speakMessage(query.name)
		treeInterceptor = self.node.nodeManager.treeInterceptor
		if not treeInterceptor or not treeInterceptor.isReady:
			return
		treeInterceptor.passThrough = query.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough
		if query.type == ruleTypes.ZONE:
			query.markerManager.zone = Zone(query)
			# Ensure the focus does not remain on a control out of the zone
			treeInterceptor.rootNVDAObject.setFocus()
		elif (
			query.markerManager.zone and
			not query.markerManager.zone.containsNode(self.node)
		):
			query.markerManager.zone = None
		info = treeInterceptor.makeTextInfo(
			textInfos.offsets.Offsets(self.node.offset, self.node.offset)
		)
		treeInterceptor.selection = info
		if not treeInterceptor.passThrough:
			info.expand(textInfos.UNIT_LINE)
			speech.speakTextInfo(
				info,
				unit=textInfos.UNIT_LINE,
				reason=controlTypes.REASON_CARET
			)
			return
		focusObject = api.getFocusObject()
		try:
			nodeObject = self.node.getNvdaObject()
		except:
			nodeObject = None
		if nodeObject == focusObject and focusObject is not None:
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
			parts = []
			if self.markerQuery.sayName:
				parts.append(self.markerQuery.name)
			parts.append(self.value)
			msg = u" - ".join(parts)
			wx.CallAfter(ui.message, msg)
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
		self.type = None
		self.skip = False
		self.results = None
	
	def resetResults(self):
		self.results = None
	
	def getResults(self):
		if self.results is None:
			self.results = self._getResults()
		return self.results
	
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
			ruleName=self.name)
		)


class VirtualMarkerQuery(MarkerQuery):
	
	def __init__(self, markerManager, dic):
		super(VirtualMarkerQuery,self).__init__(markerManager)
		self.dic = dic
		self.name = dic["name"]
		self.type = dic["type"]
		self.contextPageTitle = dic.get("contextPageTitle", "")
		self.contextPageType = dic.get("contextPageType", "")
		self.contextParent = dic.get("contextParent", "")
		self.gestures = dic.get("gestures", {})
		gesturesMap = {}
		for gestureIdentifier in self.gestures.keys():
			gesturesMap[gestureIdentifier] = "notFound"
		self.bindGestures(gesturesMap)
		self.autoAction = dic.get("autoAction")
		self.formMode = dic.get("formMode", False)
		self.sayName = dic.get("sayName", True)
		self.index = dic.get("index")
		self.multiple = dic.get("multiple", False)
		self.skip = dic.get("skip", False)
		self.isPageTitle = dic.get("isPageTitle", False)
		self.createWidget = dic.get("createWidget", False)
		self.customValue = dic.get("customValue")
	
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
	
	def checkContextPageTitle(self):
		"""
		Check whether the current page satisfies `contextPageTitle`.
		
		A leading '!' negates the match.
		A leading '\' escapes the first character to allow for a literal
		match.
		
		No further unescaping is performed past the first character. 
		"""
		expr = (self.contextPageTitle or "").strip()
		if not expr:
			return True
		if expr[0] == "!":
			exclude = True
			expr = expr[1:]
		else:
			exclude = False
		if expr.startswith("\\"):
			expr = expr[1:]
		# TODO: contextPageTitle: Handle '1:' and '2:' prefixes
		# TODO: contextPageTitle: Handle '*' partial match
		candidate = self.markerManager._getPageTitle()
		if expr == candidate:
			return not exclude
		return exclude
	
	def checkContextPageType(self):
		"""
		Check whether the current page satisfies `contextPageTitle`.
		
		'|', '!' and '&' are supported, in this order of precedence.
		"""
		for expr in (self.contextPageType or "").split("&"):
			expr = expr.strip()
			if not expr:
				continue
			if expr[0] == "!":
				exclude = True
				expr = expr[1:]
			else:
				exclude = False
			found = False
			for name in expr.split("|"):
				name = name.strip()
				if not name:
					continue
				query = self.markerManager.getQueryByName(name)
				if query is None:
					log.error((
						u"In rule \"{rule}\".contextPageType: "
						u"Rule not found: \"{pageType}\""
					).format(rule=self.name, pageType=name))
					return False
				results = query.getResults()
				if results:
					nodes = [result.node for result in results]
					if exclude:
						return False
					else:
						found = True
						break
				if found:
					break
			if not (found or exclude):
				return False
		return True
	
	def _getResults(self, widget=False):
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
		
		if not self.checkContextPageTitle():
			return []
		if not self.checkContextPageType():
			return []

		# Handle contextParent
		rootNodes = set()  # Set of possible parent nodes
		excludedNodes = set()  # Set of excluded parent nodes
		for expr in self.contextParent.split("&"):
			expr = expr.strip()
			if not expr:
				continue
			if expr[0] == "!":
				exclude = True
				expr = expr[1:]
			else:
				exclude = False
			altRootNodes = set()
			for name in expr.split("|"):
				name = name.strip()
				if not name:
					continue
				query = self.markerManager.getQueryByName(name)
				if query is None:
					log.error((
						u"In rule \"{rule}\".contextParent: "
						u"Rule not found: \"{parent}\""
					).format(rule=self.name, parent=name))
					return []
				results = query.getResults()
				if results:
					nodes = [result.node for result in results]
					if exclude:
						excludedNodes.update(nodes)
					else:
						altRootNodes.update(nodes)
			if not exclude and not altRootNodes:
				return []
			if exclude:
				continue
			if not rootNodes:
				rootNodes = altRootNodes
				continue
			newRootNodes = set()
			for node1 in rootNodes:
				for node2 in altRootNodes:
					node = nodeHandler.NodeField.getDeepest(node1, node2)
					if node is not None:
						newRootNodes.add(node)
			if not newRootNodes:
				return []
			rootNodes = newRootNodes
		
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


class Zone(textInfos.offsets.Offsets):
	
	def __init__(self, rule):
		self.ruleManager = rule.markerManager
		self.name = rule.name
		self.update()
	
	def __repr__(self):
		return u"<Zone {} at ({}, {})>".format(
			repr(self.name), self.startOffset, self.endOffset
		)
	
	def containsTextInfo(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		return (
			self.startOffset <= info._startOffset
			and info._endOffset <= self.endOffset
		)
	
	def containsNode(self, node):
		return self.startOffset <= node.offset < self.endOffset
	
	def isTextInfoAtStart(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		return info._startOffset == self.startOffset
	
	def isTextInfoAtEnd(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		return info._endOffset == self.endOffset
	
	def restrictTextInfo(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		res = False
		if info._startOffset < self.startOffset:
			res = True
			info._startOffset = self.startOffset
		elif info._startOffset > self.endOffset:
			res = True
			info._startOffset = self.endOffset
		if info._endOffset < self.startOffset:
			res = True
			info._endOffset = self.startOffset
		elif info._endOffset > self.endOffset:
			res = True
			info._endOffset = self.endOffset
		return res
	
	def update(self):
		rule = self.ruleManager.getQueryByName(self.name)
		if not rule:
			# The WebModule might have been edited and the rule deleted.
			return False
		results = rule.getResults()
		if not results:
			return False
		node = results[0].node
		if not node:
			return False
		self.startOffset = node.offset
		self.endOffset = node.offset + node.size
		return True
