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

# Get ready for Python 3
from __future__ import absolute_import, division, print_function

__version__ = "2019.11.18"
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
import scriptHandler
import speech
import textInfos
import textInfos.offsets
import ui
import weakref

from .. import nodeHandler
from ..webAppLib import (
	html,
	logTimeStart,
	playWebAppSound,
)
from .. import webAppScheduler
from ..widgets import genericCollection
from .controlMutation import MUTATIONS, MutatedControl
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
	focus = context["focusObject"]
	context["rule"] = markerManager.getResultAtCaret(focus=focus)
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
		time.sleep(0.2)
		ui.message(self.warningMessage)

	__gestures = {}


class MarkerManager(baseObject.ScriptableObject):
	
	def __init__(self, webApp):
		super(MarkerManager,self).__init__()
		self._ready = False
		self.webModule = self.webApp = webApp
		self.nodeManager = None
		self.nodeManagerIdentifier = None
		self.lock = threading.RLock()
		self.rules = self.markerQueries = []
		self.results = self.markerResults = []
		self._mutatedControlsById = {}
		self._mutatedControlsByOffset = []
		self.triggeredIdentifiers = {}
		self.lastAutoMoveto = None
		self.lastAutoMovetoTime = 0
		self.defaultMarkerScripts = DefaultMarkerScripts(u"Aucun marqueur associé à cette touche")
		self.timerCheckAutoAction = None
		webApp.widgetManager.register(MarkerGenericCollection)
		self.zone = None

	def setQueriesData(self, queryData):
		self.markerQueries[:] = []
		self.markerResults[:] = []
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
	
	def getPrioritizedResultsByName(self, name):
		"""
		This is a temporary measure, allowing to get prioritized results
		during the update.
		This will no longer be necessary once multi criteria sets rules will
		be implemented, as rule names will be unique again.
		"""
		results = []
		for rule in sorted(
			(rule for rule in self.markerQueries if rule.name == name),
			key=lambda rule: rule.priority
		):
			results.extend(rule.getResults())
			if rule.priority is None:
				continue
			if results:
				break
		return results
	
	def iterMutatedControls(self, direction="next", offset=None):
		for entry in (
			self._mutatedControlsByOffset
			if direction == "next" else reversed(self._mutatedControlsByOffset)
		):
			if offset is not None:
				if direction == "next":
					if entry.start <= offset:
						continue
				elif direction == "previous":
					if entry.start >= offset:
						continue
				elif direction == "up":
					if not (entry.start < offset <= entry.end):
						continue
				else:
					raise ValueError(
						u"Not supported: direction={}".format(direction)
					)
			yield entry
	
	def getMutatedControl(self, controlId):
		return self._mutatedControlsById.get(controlId)
	
	def removeResults(self, query):
		for i in range(len(self.markerResults), 0, -1):
			if self.markerResults[i-1].markerQuery== query:
				del self.markerResults[i-1]

	def getActions(self):
		actions = builtinRuleActions.copy()
		prefix = "action_"
		for key in dir(self.webApp):
			if key[:len(prefix)] == prefix:
				actionId = key[len(prefix):]
				actionLabel = getattr(self.webApp, key).__doc__ or actionId
				# Prefix to denote customized action
				actionLabel = "*" + actionLabel
				actions.setdefault(actionId, actionLabel)
		return actions
				
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
		self._mutatedControlsById.clear()
		self._mutatedControlsByOffset[:] = []
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
			self.markerResults[:] = []
			self._mutatedControlsById.clear()
			self._mutatedControlsByOffset[:] = []
			for query in self.markerQueries:
				query.resetResults()
			
			# This is a temporary measure, no longer necessary once multi
			# criteria sets rules will be implemented, as rule names will be
			# unique again.
			for name in list(OrderedDict.fromkeys((
				rule.name
				for rule in sorted(
					self.markerQueries,
					key=lambda rule: (
						0 if rule.type in (
							ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2
						) else 1
					)
			))).keys()):
				results = self.getPrioritizedResultsByName(name)
			# for query in sorted(
			# 	self.markerQueries,
			# 	key=lambda query: (
			# 		0 if query.type in (
			# 			ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2
			# 		) else 1
			# 	)
			# ):
			# 	results = query.getResults()
				self.markerResults += results
				self.markerResults.sort()

			for result in self.markerResults:
				if not result.rule.mutation:
					continue
				controlId = int(result.node.controlIdentifier)
				entry = self._mutatedControlsById.get(controlId)
				if entry is None:
					entry = MutatedControl(result)
					self._mutatedControlsById[controlId] = entry
					self._mutatedControlsByOffset.append(entry)
				else:
					entry.apply(result)

			self._ready = True
			self.nodeManagerIdentifier = self.nodeManager.identifier
			if self.zone is not None:
				if not self.zone.update():
					self.zone = None
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
					# check only 100 first characters
					text = result.node.getTreeInterceptorText()[:100]
					autoActionName = result.markerQuery.autoAction
					func = getattr(result, "script_%s" % autoActionName)
					lastText = self.triggeredIdentifiers.get(controlIdentifier)
					if (lastText is None or text != lastText):
						self.triggeredIdentifiers[controlIdentifier] = text
						if autoActionName == "speak":
							playWebAppSound("errorMessage")
						elif autoActionName == "moveto": 
							if lastText is None:
								# only if it's a new identifier
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
		return " - ".join(parts)
	
	def _getPageTitle1(self):
		for result in self.markerResults:
			if result.markerQuery.type == ruleTypes.PAGE_TITLE_1:
				return result.value
		from ..webModuleHandler import _getWindowTitle
		windowTitle = _getWindowTitle(self.nodeManager.treeInterceptor.rootNVDAObject)
		return windowTitle or api.getForegroundObject().name
	
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

	def _getIncrementalResult(
		self,
		previous=False,
		relative=True,
		caret=None,
		types=None,
		name=None,
		respectZone=False,
		honourSkip=True,
	):
		if honourSkip:
			caret = caret.copy()
			caret.expand(textInfos.UNIT_CHARACTER)
			skippedZones = []
			for result in self.markerResults:
				query = result.markerQuery
				if not query.skip or query.type != ruleTypes.ZONE:
					continue
				zone = Zone(result)
				if not zone.containsTextInfo(caret):
					skippedZones.append(zone)
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
			elif honourSkip:
				if query.skip:
					continue
				if any(
					zone
					for zone in skippedZones
					if zone.containsResult(result)
				):
					continue
			if (
				hasattr(result, "node")
				and (
					not relative
					or (
						not previous
						and caret._startOffset < result.node.offset
					)
					or (previous and caret._startOffset > result.node.offset)
				)
				and (
					not (respectZone or (previous and relative))
					or not self.zone
					or (
						(
							not respectZone
							or self.zone.containsNode(result.node)
						)
						and not (
							# If respecting zone restriction or iterating
							# backwards relative to the caret position,
							# avoid returning the current zone itself.
							self.zone.name == result.markerQuery.name
							and self.zone.startOffset == result.node.offset
						)
					)
				)
			):
				return result
		return None
	
	def getResultAtCaret(self, focus=None):
		return next(self.iterResultsAtCaret(focus), None)
	
	def iterResultsAtCaret(self, focus=None):
		if focus is None:
			focus = api.getFocusObject()
		try:
			info = focus.treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
		except AttributeError:
			return
		for result in self.iterResultsAtTextInfo(info):
			yield result
	
	def iterResultsAtObject(self, obj):
		try:
			info = obj.treeInterceptor.makeTextInfo(obj)
		except AttributeError:
			return
		for result in self.iterResultsAtTextInfo(info):
			yield result
	
	def iterResultsAtTextInfo(self, info):
		if not self.isReady:
			return
		if not self.markerResults:
			return
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		offset = info._startOffset
# 		for result in self.iterResultsAtOffset(offset):
# 			yield result
# 	
# 	def iterResultsAtOffset(self, offset):
# 		if not self.isReady:
# 			return
# 		if not self.markerResults:
# 			return
		for r in reversed(self.markerResults):
			if (
				hasattr(r, "node")
				and r.node.offset <= offset < r.node.offset + r.node.size 
			):
				yield r
	
	def quickNav(
		self,
		previous=False,
		position=None,
		types=None,
		name=None,
		respectZone=False,
		honourSkip=True,
		cycle=True,
		quiet=False,
	):
		if not self.isReady:
			playWebAppSound("keyError")
			ui.message(_("Not ready"))
			return None
		
		if position is None:
			# Search first from the current caret position
			position = html.getCaretInfo()
		
		if position is None:
			playWebAppSound("keyError")
			ui.message(_("Not ready"))
			return None
		
		# If not found after/before the current position, and cycle is True,
		# return the first/last result.
		for relative in ((True, False) if cycle else (True,)):
			result = self._getIncrementalResult(
				previous=previous,
				caret=position,
				relative=relative,
				types=types,
				name=name,
				respectZone=respectZone,
				honourSkip=honourSkip
			)
			if result:
				if not relative:
					playWebAppSound("loop")
					time.sleep(0.2)
				break
		else:
			playWebAppSound("keyError")
			time.sleep(0.2)
			if quiet:
				return False
			elif types == (ruleTypes.ZONE,):
				if self.zone:
					if previous:
						# Translator: Error message in quickNav (page up/down)
						ui.message(_("No previous zone"))
					else:
						# Translator: Error message in quickNav (page up/down)
						ui.message(_("No next zone"))
				else:
					# Translator: Error message in quickNav (page up/down)
					ui.message(_("No zone"))
				return False
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
			return False
		result.script_moveto(None, fromQuickNav=True)
		return True
	
	def quickNavToNextLevel1(self):
		self.quickNav(types=(ruleTypes.ZONE,), honourSkip=False)
	
	def quickNavToPreviousLevel1(self):
		self.quickNav(previous=True, types=(ruleTypes.ZONE,), honourSkip=False)
	
	def quickNavToNextLevel2(self):
		self.quickNav(types=(ruleTypes.ZONE, ruleTypes.MARKER))
	
	def quickNavToPreviousLevel2(self):
		self.quickNav(previous=True, types=(ruleTypes.ZONE, ruleTypes.MARKER))
	
	def quickNavToNextLevel3(self):
		self.quickNav(
			types=(ruleTypes.ZONE, ruleTypes.MARKER),
			respectZone=True,
			honourSkip=False,
			cycle=False
		)
	
	def quickNavToPreviousLevel3(self):
		self.quickNav(
			previous=True,
			types=(ruleTypes.ZONE, ruleTypes.MARKER),
			respectZone=True,
			honourSkip=False,
			cycle=False
		)


class CustomActionDispatcher(object):
	"""
	Execute a custom action, eventually overriding a standard action.
	"""
	def __init__(self, actionId, standardFunc):
		self.actionId = actionId
		self.standardFunc = standardFunc
		self.webModules = weakref.WeakSet()
		self.instance = None
	
	def __get__(self, obj, type=None):
		if obj is None:
			return self
		bound = CustomActionDispatcher(self.actionId, self.standardFunc)
		bound.instance = obj
		return bound
	
	def __getattribute__(self, name):
		# Pass functions attributes such as __doc__, __name__,
		# category, ignoreTreeInterceptorPassThrough or resumeSayAllMode.
		# Note: scriptHandler.executeScript looks at script.__func__ to
		# prevent recursion.
		if name not in (
			"__call__",
			"__class__",
			"__get__",
			"actionId",
			"getCustomFunc",
			"instance",
			"standardFunc",
			"webModules",
		):
			def funcs():
				if self.instance:
					yield self.getCustomFunc()
				else:
					for webModule in self.webModules:
						yield self.getCustomFunc(webModule)
				yield self.standardFunc
			for func in funcs():
				if not func:
					continue
				try:
					return getattr(func, name)
				except AttributeError:
					pass
		return object.__getattribute__(self, name)
	
	def __call__(self, *args, **kwargs):
		if self.instance:
			args = (self.instance,) + args
			func = self.getCustomFunc()
			if func:
				if self.standardFunc:
					kwargs["script"] = self.standardFunc.__get__(self.instance)
			else:
				func = self.standardFunc
		else:
			func = self.standardFunc
		if not func:
			raise NotImplementedError
		func(*args, **kwargs)
	
	def getCustomFunc(self, webModule=None):
		if webModule is None:
			if self.instance is None:
				return None
			webModule = self.instance.markerQuery.markerManager.webApp
		return getattr(
			webModule,
			"action_{self.actionId}".format(**locals()),
			None
		)


class MarkerResult(baseObject.ScriptableObject):
	
	def __init__(self, markerQuery):
		super(MarkerResult, self).__init__()
		webModule = markerQuery.markerManager.webApp
		prefix = "action_"
		for key in dir(webModule):
			if key.startswith(prefix):
				actionId = key[len(prefix):]
				scriptAttrName = "script_%s" % actionId
				scriptFunc = getattr(self.__class__, scriptAttrName, None)
				if isinstance(scriptFunc, CustomActionDispatcher):
					scriptFunc.webModules.add(webModule)
					continue
				dispatcher = CustomActionDispatcher(actionId, scriptFunc)
				dispatcher.webModules.add(webModule)
				setattr(self.__class__, scriptAttrName, dispatcher)
				setattr(self, scriptAttrName, dispatcher.__get__(self))
		self.rule = self.markerQuery = markerQuery
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
				ruleName=query.label)
			)
		elif self.markerQuery.sayName:
			speech.speakMessage(query.label)
		treeInterceptor = self.node.nodeManager.treeInterceptor
		if not treeInterceptor or not treeInterceptor.isReady:
			return
		treeInterceptor.passThrough = query.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough
		if query.type == ruleTypes.ZONE:
			query.markerManager.zone = Zone(self)
			# Ensure the focus does not remain on a control out of the zone
			treeInterceptor.rootNVDAObject.setFocus()
		else:
			for result in reversed(query.markerManager.markerResults):
				if result.markerQuery.type != ruleTypes.ZONE:
					continue
				zone = Zone(result)
				if zone.containsResult(self):
					if zone != query.markerManager.zone:
						query.markerManager.zone = zone
					break
			else:
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
			nodeObject = self.node.getNVDAObject()
		except:
			nodeObject = None
		if nodeObject == focusObject and focusObject is not None:
			focusObject.reportFocus()
	
	def script_sayall(self, gesture, fromQuickNav=False):
		speech.cancelSpeech()
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.label)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		speechMode = speech.speechMode
		try:
			speech.speechMode = speech.speechMode_off
			treeInterceptor.passThrough = False
			browseMode.reportPassThrough.last = treeInterceptor.passThrough 
			self.node.moveto()
			html.speakLine()
			api.processPendingEvents()
		except:
			log.exception("Error during script_sayall")
			return
		finally:
			speech.speechMode = speechMode
		sayAllHandler.readText(sayAllHandler.CURSOR_CARET)
	
	def script_activate(self, gesture):
		if self.node.nodeManager is None:
			return
		if not self.markerQuery.markerManager.isReady :
			log.info (u"not ready")
			return
		treeInterceptor = self.node.nodeManager.treeInterceptor
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.label)
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
				parts.append(self.markerQuery.label)
			parts.append(self.value)
			msg = u" - ".join(parts)
			wx.CallAfter(ui.message, msg)
		else:
			self.script_moveto(None, fromSpeak=True)
	
	def script_mouseMove(self, gesture):
		if self.markerQuery.sayName:
			speech.speakMessage(self.markerQuery.label)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		treeInterceptor.passThrough = self.markerQuery.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough 
		self.node.mouseMove()
	
	def getTextInfo(self):
		return self.node.getTextInfo()
	
	def __lt__(self, other):
		return self.node.offset < other.node.offset
	
	def getTitle(self):
		return self.markerQuery.label + " - " + self.node.innerText


class MarkerQuery(baseObject.ScriptableObject):
	
	def __init__(self, markerManager):
		super(MarkerQuery,self).__init__()
		self.ruleManager = self.markerManager = markerManager
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
			ruleName=self.label)
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
		self.priority = dic.get("priority")
		self.index = dic.get("index")
		self.mutation = None
		if "mutation" in dic:
			try:
				self.mutation = MUTATIONS[dic["mutation"]]
			except LookupError:
				log.exception((
					u"Unexpected mutation template id \"{mutation}\" "
					u"in rule \"{rule}\"."
				).format(mutation=dic["mutation"], rule=self.name))
		self.gestures = dic.get("gestures", {})
		gesturesMap = {}
		for gestureIdentifier in self.gestures.keys():
			gesturesMap[gestureIdentifier] = "notFound"
		self.bindGestures(gesturesMap)
		self.autoAction = dic.get("autoAction")
		self.multiple = dic.get("multiple", False)
		self.formMode = dic.get("formMode", False)
		self.skip = dic.get("skip", False)
		self.sayName = dic.get("sayName", True)
		self.customName = dic.get("customName")
		self.customValue = dic.get("customValue")
		self.comment = dic.get("comment")
		self.createWidget = dic.get("createWidget", False)
	
	# TODO: Thoroughly check this wasn't used anywhere
	# In Python 3, all classes defining __eq__ must also define __hash__
# 	def __eq__(self, other):
# 		return self.dic == other.dic
	
	def _get_label(self):
		return self.customName or self.name
	
	def getData(self):
		return self.dic
		
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
				
				# This is a temporary measure, no longer necessary once multi
				# criteria sets rules will be implemented, as rule names will
				# be unique again.
				results = self.markerManager.getPrioritizedResultsByName(
					query.name
				)
				# results = query.getResults()
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
				# This is a temporary measure, no longer necessary once multi
				# criteria sets rules will be implemented, as rule names will
				# be unique again.
				results = self.markerManager.getPrioritizedResultsByName(
					query.name
				)
				# results = query.getResults()
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
		kwargs = getSimpleSearchKwargs(dic)
		if rootNodes:
			kwargs["roots"] = rootNodes
		if excludedNodes:
			kwargs["exclude"] = excludedNodes
		if not self.multiple:
			kwargs["maxIndex"] = self.index or 1
		kwargs["relativePath"] = dic.get("relativePath")
		
		results = []
		nodeList = self.markerManager.nodeManager.searchNode(**kwargs)
		#logTime(u"searchNode %s, %d results" % (self.name, len(nodeList)), t)
		index = 0
		for node in nodeList:
			index += 1  # 1-based
			if self.index and index < self.index:
				continue
			r = VirtualMarkerResult(self, node)
			results.append(r)
			if not self.multiple:
				break
		return results


def getSimpleSearchKwargs(criteriaDic, raiseOnUnsupported=False):
	kwargs = {}
	for prop, expr in criteriaDic.items():
		if prop not in [
			"className",
			"id",
			"role",
			"src",
			"states",
			"tag",
			"text",
		]:
			if raiseOnUnsupported:
				raise ValueError(
					u"Unsupported criteria: {prop}={expr!r}".format(**locals())
				)
			continue
		if not expr:
			continue
		if isinstance(expr, int):
			expr = str(expr)
		if prop == "text":
			if expr[0] == "<":
				kwargs["in_prevText"] = expr[1:]
				continue
			kwargs["in_text"] = expr[1:]
			continue
		if prop == "className":
			expr = expr.replace(" ", "&")
		for andIndex, expr in enumerate(expr.split("&")):
			expr = expr.strip()
			eq = []
			notEq = []
			in_ = []
			notIn = []
			for expr in expr.split("|"):
				expr = expr.strip()
				if not expr:
					continue
				if expr[0] == "!":
					if "*" in expr:
						notIn.append(expr[1:].strip())
					else:
						notEq.append(expr[1:].strip())
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
				kwargs[key] = values
	return kwargs


Rule = VirtualMarkerQuery


class Zone(textInfos.offsets.Offsets):
	
	def __init__(self, result):
		rule = result.markerQuery
		self.ruleManager = rule.markerManager
		self.name = rule.name
		super(Zone, self).__init__(startOffset=None, endOffset=None)
		self._update(result)
	
	def __bool__(self):  # Python 3
		return self.startOffset is not None and self.endOffset is not None
	
	def __eq__(self, other):
		return (
			isinstance(other, Zone)
			and other.ruleManager == self.ruleManager
			and other.name == self.name
			and other.startOffset == self.startOffset
			and other.endOffset == self.endOffset
		)
	
	def __hash__(self):
		return hash((self.startOffset, self.endOffset))
	
	def __nonzero__(self):  # Python 2
		return self.__bool__()
	
	def __repr__(self):
		if not self:
			return u"<Zone {} (invalidated)>".format(repr(self.name))
		return u"<Zone {} at ({}, {})>".format(
			repr(self.name), self.startOffset, self.endOffset
		)
	
	def containsNode(self, node):
		if not self:
			return False
		return self.startOffset <= node.offset < self.endOffset
	
	def containsResult(self, result):
		if not self:
			return False
		if hasattr(result, "node"):
			return self.containsNode(result.node)
		return False
	
	def containsTextInfo(self, info):
		if not self:
			return False
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		return (
			self.startOffset <= info._startOffset
			and info._endOffset <= self.endOffset
		)
	
	def getRule(self):
		return self.ruleManager.getQueryByName(self.name)
	
	def isTextInfoAtStart(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		return self and info._startOffset == self.startOffset
	
	def isTextInfoAtEnd(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		return self and info._endOffset == self.endOffset
	
	def restrictTextInfo(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError(u"Not supported {}".format(type(info)))
		if not self:
			return False
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
		results = self.ruleManager.getResultsByName(self.name)
		if not results:
			self.startOffset = self.endOffset = None
			return False
		return self._update(results[0])
	
	def _update(self, result):
		node = result.node
		if not node:
			self.startOffset = self.endOffset = None
			return False
		self.startOffset = node.offset
		self.endOffset = node.offset + node.size
		return True
