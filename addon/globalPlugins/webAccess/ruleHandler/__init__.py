# globalPlugins/webAccess/ruleHandler/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (https://accessolutions.fr)
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


__authors__ = (
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Sendhil Randon <sendhil.randon-ext@francetravail.fr>",
	"Gatien Bouyssou <gatien.bouyssou@francetravail.fr>",
)


from functools import partial
from itertools import chain
from pprint import pformat
import threading
import time
import sys
from typing import Any
import weakref

import wx

import addonHandler
import api
from baseObject import AutoPropertyObject, ScriptableObject
import browseMode
import controlTypes
import inputCore
from logHandler import log
import queueHandler
import scriptHandler
import speech
import textInfos
import textInfos.offsets
import ui
from core import callLater
from garbageHandler import TrackedObject

from .. import nodeHandler
from ..utils import logException
from ..webAppLib import (
	html,
	logTimeStart,
	playWebAccessSound,
)
from .. import webAppScheduler
from . import ruleTypes
from .controlMutation import MUTATIONS, MutatedControl, getMutationId
from .properties import RuleProperties, CriteriaProperties


if sys.version_info[1] < 9:
    from typing import Mapping, Sequence
else:
    from collections.abc import Mapping, Sequence


addonHandler.initTranslation()

SCRIPT_CATEGORY = "WebAccess"

builtinRuleActions = {}
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


class DefaultScripts(ScriptableObject):

	def __init__(self, warningMessage):
		super().__init__()
		self.warningMessage = warningMessage
		for ascii in range(ord("a"), ord("z")+1):
			character = chr(ascii)
			self.__class__.__gestures["kb:control+shift+%s" % character] = "notAssigned"

	def script_notAssigned(self, gesture):
		playWebAccessSound("keyError")
		callLater(200, ui.message, self.warningMessage)

	__gestures = {}


class RuleManager(ScriptableObject):

	def __init__(self, webModule):
		super().__init__()
		self._ready = False
		self._webModule = weakref.ref(webModule)
		self._nodeManager = None
		self.nodeManagerIdentifier = None
		self.lock = threading.RLock()
		self._layers = {}
		self._layersIndex = {}
		self._rules = {}
		self._results = []
		self._mutatedControlsById = {}
		self._mutatedControlsByOffset = []
		self.triggeredIdentifiers = {}
		self.lastAutoMoveto = None
		self.lastAutoMovetoTime = 0
		self.defaultScripts = DefaultScripts("Aucun marqueur associé à cette touche")
		self.timerCheckAutoAction = None
		self._zone: Zone = None
		self.subModules: SubModules = SubModules(self)
		self._controlIdToPosition: Mapping[str, int] = {}
		"""Used for safer retrieval of the WebModule associated to an object in focus mode
		"""
		self._allResults: Sequence["Result"] = []
		"""Results for this WebModule and all of its SubModules.
		""" 
		self.parentZone: Zone = None
		"""The zone containing this SubModule in its parent WebModule
		"""

	def _get_rootRuleManager(self):
		parent = self.parentRuleManager
		if parent:
			return parent.rootRuleManager
		return self
	
	def _get_nodeManager(self):
		root = self.rootRuleManager
		if root is not self:
			return root.nodeManager
		return self._nodeManager() if self._nodeManager else None
	
	def _get_parentNode(self):
		parentZone = self.parentZone
		if parentZone is not None:
			return parentZone.result.Node
		return self.nodeManager.mainNode
	
	def _get_parentRuleManager(self):
		try:
			return self.parentZone.ruleManager
		except AttributeError:
			return None
	
	def _get_webModule(self):
		return self._webModule()

	@logException
	def _get_zone(self):
		if self.parentZone is not None:
			return self.parentRuleManager.zone
		else:
			return self._zone
	
	@logException
	def _set_zone(self, value, force=False):
		if value is None and not force:
			curZone = self.zone
			curResult = curZone.result if curZone is not None else None
			if curResult is not None:
				for candidate in self.iterResultsAtCaret():
					if candidate.zone not in (None, curZone) and candidate.containsResult(curResult):
						value = candidate.zone
						break
		if self.parentZone is not None:
			self.parentRuleManager.zone = value
		else:
			self._zone = value
	
	def dump(self, layer):
		return {name: rule.dump() for name, rule in list(self._layers[layer].items())}

	def load(self, layer, index, data):
		self.unload(layer)
		self._initLayer(layer, index)
		for ruleName, ruleData in list(data.items()):
			self._loadRule(layer, ruleName, ruleData)

	def _initLayer(self, layer, index):
		self._layers[layer] = {}
		if index is not None:
			for otherIndex, otherLayer in enumerate(list(self._layers.keys())):
				if otherIndex >= index:
					self._layers.move_to_end(otherLayer)
		self._layersIndex = dict(
			((layerName, layerIndex) for layerIndex, layerName in enumerate(self._layers.keys()))
		)

	def loadRule(self, layer: str, name: str, data: Mapping[str, Any]) -> "Rule":
		if layer not in self._layers:
			self._initLayer(layer, None)
		return self._loadRule(layer, name, data)

	def _loadRule(self, layer: str, name: str, data: Mapping[str, Any]) -> "Rule":
		rule = self.webModule.createRule(data)
		rule.layer = layer
		self._layers[layer][name] = rule
		self._rules.setdefault(name, {})[layer] = rule
		return rule

	def unload(self, layer):
		for index in range(len(self._results)):
			if self._results[index].rule.layer == layer:
				del self._results[index]
		for ruleLayers in list(self._rules.values()):
			ruleLayers.pop(layer, None)
		self._layers.pop(layer, None)

	def removeRule(self, rule):
		self.removeResults(rule)
		self._rules.pop(rule.name, None)
		self._layers[rule.layer].pop(rule.name, None)

	def getRules(self, layer=None):
		if layer not in (None, False):
			return tuple(self._layers[layer].values())
		return tuple([
			rule
			for ruleLayers in self._rules.values()
			for rule in reversed(ruleLayers.values())
		])

	def getRule(self, name, layer=None):
		if layer is None:
			for layer in list(self._layers.keys()):
				if layer != "user" or len(self._layers) == 1:
					break
		ruleLayers = self._rules[name]
		if layer not in (None, False):
			return ruleLayers[layer]
		try:
			return next(iter(reversed(ruleLayers.values())))
		except StopIteration:
			raise LookupError({"name": name, "layer": layer})

	def getResults(self) -> tuple["Result"]:
		"""Get the results for all the layers of this WebModule, excluding SubModules.
		"""
		if not self.isReady:
			return []
		return tuple(self._results)
	
	def getAllResults(self) -> tuple["Result"]:
		"""Get the results for all the layers of this WebModule and all its SubModules.
		"""
		if not self.isReady:
			return []
		return tuple(self._allResults)

	def getResultsByName(self, name, layer=None):
		return list(self.iterResultsByName(name, layer=layer))

	def iterResultsByName(self, name, layer=None):
		if not self.isReady:
			return
		if layer is None:
			for layer in list(self._layers.keys()):
				if layer != "user" or len(self._layers) == 1:
					break
		for result in self.getResults():
			rule = result.rule
			if rule.name != name:
				continue
			elif (
				layer not in (None, False)
				or tuple(self._layers.keys()).index(layer) >= tuple(self._layers.keys()).index(rule.layer)
			):
				yield result

	def iterMutatedControls(self, direction="next", offset=None):
		if self.parentZone is not None:
			raise Exception("Supported on the root RuleManager only")
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
						"Not supported: direction={}".format(direction)
					)
			yield entry

	def getMutatedControl(self, controlId):
		if self.parentZone is not None:
			raise Exception("Supported on the root RuleManager only")
		return self._mutatedControlsById.get(controlId)

	def removeResults(self, rule):
		for index, result in enumerate(self._results):
			if result.rule is rule:
				del self._results[index]

	def getActions(self) -> Mapping[str, str]:
		actions = builtinRuleActions.copy()
		prefix = "action_"
		for key in dir(self.webModule):
			if key[:len(prefix)] == prefix:
				actionId = key[len(prefix):]
				actionLabel = getattr(self.webModule, key).__doc__ or actionId
				# Prefix to denote customized action
				actionLabel = "*" + actionLabel
				actions.setdefault(actionId, actionLabel)
		return actions

	def getGlobalScript(self, gesture, caret=None, fromParent=False):
		if caret is None:
			webModuleAtCaret = self.nodeManager.treeInterceptor.webAccess.webModule
			return webModuleAtCaret.ruleManager.getGlobalScript(gesture, caret=webModuleAtCaret)
		
		def gen():
			nonlocal caret
			for subMod in self.subModules.all():
				if subMod is not caret:
					yield partial(subMod.ruleManager.getGlobalScript, caret=caret, fromParent=True)
			for result in self.getResults():
				if result.rule.type == ruleTypes.GLOBAL_MARKER:
					yield result.getScript
			if not fromParent and self.parentZone:
				parent = self.parentRuleManager
				if parent.webModule is not caret:
					yield partial(parent.getGlobalScript, caret=caret)
		
		for func in gen():
			script = func(gesture)
			if script:
				return script		

	def getScript(self, gesture):
		script = super().getScript(gesture)
		if script:
			return script
		script = self.getGlobalScript(gesture)
		if script:
			return script
		for layer in reversed(list(self._layers.keys())):
			for result in self.getResults():
				if result.rule.type is ruleTypes.GLOBAL_MARKER or result.rule.layer != layer:
					continue
				script = result.getScript(gesture)
				if script:
					return script
# 		for rules in reversed(list(self._layers.values())):
# 			for rule in list(rules.values()):
# 				for criterion in rule.criteria:
# 					func = rule.getScript(gesture)
# 					if func is not None:
# 						return func
# 				func = rule.getScript(gesture)
# 				if func is not None:
# 					return func
		return self.defaultScripts.getScript(gesture)
	
	def getWebModuleForControlId(self, controlId):
		if self.parentZone is not None:
			raise Exception("Supported on the root RuleManager only")
		if not self.isReady:
			return None
		# Raises LookupError on purpose, to distinguish from returning None meaning "Not Ready"
		offset = self._controlIdToPosition[controlId]
		webModule = self.subModules.atPosition(offset)
		if webModule is None:
			webModule = self.webModule
		return webModule
	
	def _get_isReady(self):
		if not self._ready or not self.nodeManager or not self.nodeManager.isReady or self.nodeManager.identifier != self.nodeManagerIdentifier:
			return False
		return True

	def terminate(self):
		self._ready = False
		self._webModule = None
		self.subModules.terminate()
		try:
			self.timerCheckAutoAction.cancel()
		except Exception:
			pass
		self.timerCheckAutoAction = None
		self._nodeManager = None
		self.clear()
	
	def clear(self):
		self._ready = False
		self._results.clear()
		self._allResults.clear()
		self._mutatedControlsById.clear()
		self._mutatedControlsByOffset.clear()
		self._controlIdToPosition.clear()
		for rule in self.getRules():
			rule.resetResults()
	
	@logException
	def update(self, nodeManager=None, force=False):
		if self.webModule is None:
			# This instance has been terminated
			return
		with self.lock:
			self._ready = False
			try:
				self.timerCheckAutoAction.cancel()
			except AttributeError:
				pass
			self.timerCheckAutoAction = None
			if nodeManager is None:
				nodeManager = self.nodeManager
			else:
				self._nodeManager = weakref.ref(nodeManager)
			if nodeManager is None or not nodeManager.isReady:
				return False
			if not force and self.nodeManagerIdentifier == nodeManager.identifier:
				# already updated
				self._ready = True
				return False
			self.nodeManagerIdentifier = nodeManager.identifier
			t = logTimeStart()
			self.clear()
			# Do not clear the other mappings in subModules to avoid reloading
			# modules that were already loaded on the last update.
			self.subModules._results.clear()
			
			for rule in (rule for rule in self.getRules() if rule.properties.subModule):
				results = rule.getResults()
				self._results.extend(results)
				self.subModules._results.extend(results)
			for rule in sorted(
				(rule for rule in self.getRules() if not rule.properties.subModule),
				key=lambda rule: (
					0 if rule.type in (
						ruleTypes.PAGE_TITLE_1, ruleTypes.PAGE_TITLE_2
					) else 2
				)
			):
				self._results.extend(rule.getResults())
			
			def resultSortKey(result):
				# If two Results start at the same offset, sort first the widest
				return result.startOffset#, -result.endOffset
			
			self._results.sort(key=resultSortKey)
			self._allResults.extend(self._results)
			
			for result in self._results:
				if not (hasattr(result, "node") and result.properties.mutation):
					continue
				controlId = result.node.controlIdentifier
				entry = self._mutatedControlsById.get(controlId)
				if entry is None:
					entry = MutatedControl(result)
					self._mutatedControlsById[controlId] = entry
					self._mutatedControlsByOffset.append(entry)
				else:
					entry.apply(result)
			self.subModules.update()
			self._allResults.sort(key=resultSortKey)
			if self is self.rootRuleManager:
				self._mutatedControlsByOffset.sort(key=lambda m: m.start)
				self._controlIdToPosition = nodeManager.getControlIdToPosition()
			self._ready = True
			# Zone update check can be performed only once ready
			if self.zone is not None:
				if not self.zone.update() or not self.zone.containsTextInfo(
					nodeManager.treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
				):
					self.zone = None
			#logTime("update marker", t)
			if self.isReady:
				webAppScheduler.scheduler.send(eventName="ruleManagerUpdated", ruleManager=self)
				self.timerCheckAutoAction = threading.Timer(
					1,  # Accepts floating point number for sub-second precision
					self.checkAutoAction
				)
				self.timerCheckAutoAction.start()
				return True
			else:
				log.error("Not yet")
		return False

	def checkPageTitle(self):
		if self.webModule is None:
			# This instance has been terminated
			return
		title = self.getPageTitle()
		webModule = self.webModule
		if title != webModule.activePageTitle:
			webModule.activePageTitle = title
			webAppScheduler.scheduler.send(
				eventName="webModule",
				name="webModule_pageChanged",
				obj=title,
				webModule=webModule
			)
			return True
		return False

	def checkAutoAction(self):
		self.timerCheckAutoAction = None
		with self.lock:
			if self.webModule is None:
				# This instance has been terminated
				return
			if not self.isReady:
				return
			funcMoveto = None
			firstCancelSpeech = True
			for result in self.getResults():
				if result.properties.autoAction:
					controlIdentifier = result.node.controlIdentifier
					# check only 100 first characters
					text = result.node.getTreeInterceptorText()[:100]
					autoActionName = result.properties.autoAction
					func = getattr(result, "script_%s" % autoActionName)
					lastText = self.triggeredIdentifiers.get(controlIdentifier)
					if (lastText is None or text != lastText):
						self.triggeredIdentifiers[controlIdentifier] = text
						if autoActionName == "speak":
							playWebAccessSound("errorMessage")
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
							except Exception:
								log.exception((
									'Error in rule "{rule}" while executing'
									' autoAction "{autoAction}"'
								).format(
									rule=result.rule.name,
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
		if self._results:
			for result in self._results:
				if result.rule.type == ruleTypes.PAGE_TITLE_1:
					return result.value
		from ..webModuleHandler import getWindowTitle
		windowTitle = getWindowTitle(self.nodeManager.treeInterceptor.rootNVDAObject)
		return windowTitle or api.getForegroundObject().name

	def _getPageTitle2(self):
		if not self._results:
			return
		for result in self._results:
			if result.rule.type == ruleTypes.PAGE_TITLE_2:
				return result.value

	def getPageTypes(self):
		types = []
		with self.lock:
			if not self.isReady:
				return types
			for result in self.getResults():
				if result.rule.type == ruleTypes.PAGE_TYPE:
					types.append(result.rule.name)
			return types

	def _getIncrementalResult(
		self,
		caret: textInfos.offsets.OffsetsTextInfo,
		previous=False,
		relative=True,
		types=None,
		name=None,
		respectZone=False,
		honourSkip=True,
	):
		if honourSkip:
			caret = caret.copy()
			caret.expand(textInfos.UNIT_CHARACTER)
			skippedZones = []
			for result in self.getResults():
				rule = result.rule
				if not result.properties.skip or rule.type != ruleTypes.ZONE:
					continue
				zone = result.zone
				if not zone.containsTextInfo(caret):
					skippedZones.append(zone)
		results = self.getResults() if respectZone and self.zone else self.rootRuleManager.getAllResults()
		for result in (reversed(results) if previous else results):
			rule = result.rule
			if types and rule.type not in types:
				continue
			if name:
				if rule.name != name:
					continue
			elif honourSkip:
				if result.properties.skip:
					continue
				if any(
					zone
					for zone in skippedZones
					if zone.containsResult(result)
				):
					continue
			if (
				(
					not relative
					or (
						not previous
						and caret._startOffset < result.startOffset
					)
					or (previous and caret._startOffset > result.startOffset)
				)
				and (
					not (respectZone or (previous and relative))
					or not self.zone
					or (
						(
							not respectZone
							or self.zone.containsResult(result)
						)
						# If respecting zone restriction or iterating backwards relative to the
						# caret position, avoid returning the current zone itself.
						and not self.zone.equals(result.zone)
					)
				)
			):
				return result
		return None

	def getResultAtCaret(self):
		"""Includes Results from all WebModules active on the document
		"""
		return next(self.iterResultsAtCaret(), None)

	def iterResultsAtCaret(self):
		"""Includes Results from all WebModules active on the document
		"""
		try:
			ti = self.nodeManager.treeInterceptor
		except AttributeError:
			return
		info = ti.makeTextInfo(textInfos.POSITION_CARET)
		for result in self.iterResultsAtTextInfo(info):
			yield result

	def iterResultsAtObject(self, obj):
		"""Includes Results from all WebModules active on the document
		"""
		try:
			info = obj.treeInterceptor.makeTextInfo(obj)
		except AttributeError:
			return
		for result in self.iterResultsAtTextInfo(info):
			yield result

	def iterResultsAtTextInfo(self, info):
		"""Includes Results from all WebModules active on the document
		"""
		root = self.rootRuleManager
		if not root.isReady:
			return
		results = root.getAllResults()
		if not results:
			return
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError("Not supported {}".format(type(info)))
		offset = info._startOffset
		for r in reversed(results):
			if r.startOffset <= offset <= r.endOffset:
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
			playWebAccessSound("keyError")
			# Translators: Reported when attempting an action while WebAccess is not ready
			ui.message(_("Not ready"))
			return None

		if position is None:
			# Search first from the current caret position
			position = html.getCaretInfo()

		if position is None:
			playWebAccessSound("keyError")
			# Translators: Reported when attempting an action while WebAccess is not ready
			ui.message(_("Not ready"))
			return None

		# If not found after/before the current position, and cycle is True,
		# return the first/last result.
		for relative in ((True, False) if cycle else (True,)):
			result = self._getIncrementalResult(
				caret=position,
				previous=previous,
				relative=relative,
				types=types,
				name=name,
				respectZone=respectZone,
				honourSkip=honourSkip
			)
			if result:
				if not relative:
					playWebAccessSound("loop")
					time.sleep(0.2)
				break
		else:
			playWebAccessSound("keyError")
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
		self.quickNav(types=ruleTypes.ACTION_TYPES)

	def quickNavToPreviousLevel2(self):
		self.quickNav(previous=True, types=ruleTypes.ACTION_TYPES)

	def quickNavToNextLevel3(self):
		self.quickNav(
			types=ruleTypes.ACTION_TYPES,
			respectZone=True,
			honourSkip=False,
			cycle=False
		)

	def quickNavToPreviousLevel3(self):
		self.quickNav(
			previous=True,
			types=ruleTypes.ACTION_TYPES,
			respectZone=True,
			honourSkip=False,
			cycle=False
		)


class SubModules(AutoPropertyObject):
	
	def __init__(self, ruleManager: RuleManager):
		self._ruleManager = weakref.ref(ruleManager)
		self._webModulesByNameAndIndex: Mapping[tuple(str, int), "WebModule"] = {}
		"""Ensure SubModules are not re-instanciated upon update 
		"""
		self._webModulesByPosition: Mapping[tuple(int, int), "WebModule"] = {}
		self._results: Sequence["SingleNodeResult"] = []
		"""Results for this WebModule that should load a SubModule (ie. `result.properties.subModule` is set)
		
		Used in `Criteria.iterResults` to not search for nested matches.
		"""
	
	def _get_ruleManager(self):
		return self._ruleManager()
	
	def all(self) -> Sequence["WebModule"]:
		return tuple(self._webModulesByPosition.values())
	
	@logException
	def atPosition(self, offset) -> "WebModule":
		for (start, end), webModule in self._webModulesByPosition.items():
			if start <= offset < end:
				subModule = webModule.ruleManager.subModules.atPosition(offset)
				return subModule if subModule is not None else webModule
	
	@logException
	def update(self):
		from ..webModuleHandler import getWebModule
		webModulesByNameAndIndex = self._webModulesByNameAndIndex
		webModulesByPosition = self._webModulesByPosition
		previousByNameAndIndex = webModulesByNameAndIndex.copy()
		webModulesByNameAndIndex.clear()
		webModulesByPosition.clear()
		ruleManager = self.ruleManager
		rootRuleManager = ruleManager.rootRuleManager
		nodeManager = rootRuleManager.nodeManager
		mutatedControlsById = rootRuleManager._mutatedControlsById
		mutatedControlsByOffset = rootRuleManager._mutatedControlsByOffset
		for result in self._results:
			key = (result.rule.name, result.index)
			webModule = previousByNameAndIndex.get(key)
			if not webModule:
				webModule = getWebModule(result.properties.subModule)
			else:
				webModule.ruleManager.parentZone.update(result=result)
			if not webModule:
				log.error(f"WebModule not found: {result.properties.subModule!r}")
				continue
			webModulesByNameAndIndex[key] = webModule
			webModulesByPosition[(result.startOffset, result.endOffset)] = webModule
			subRuleManager = webModule.ruleManager
			subRuleManager.parentZone = result.zone
			subRuleManager.update(nodeManager)
			ruleManager._allResults.extend(subRuleManager.getAllResults())
			mutatedControlsById.update(subRuleManager._mutatedControlsById)
			mutatedControlsByOffset.extend(subRuleManager._mutatedControlsByOffset)
	
	def terminate(self):
		self._ruleManager = None
		for webModule in self._webModulesByNameAndIndex.values():
			webModule.terminate()
		self._results.clear()
		self._webModulesByNameAndIndex.clear()
		self._webModulesByPosition.clear()


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
		bound.instance = weakref.ref(obj)  # Avoid cyclic references (cf. NVDA #11499)
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
			if self.instance is not None:
				instance = self.instance()
				if instance is None:
					# The bound instance has been terminated.
					return object.__getattribute__(self, name)

			def funcs():
				if instance:
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
		if self.instance is not None:
			instance = self.instance()
			if instance is None:
				# The bound instance has been terminated.
				return
			args = (instance,) + args
			func = self.getCustomFunc()
			if func:
				if self.standardFunc:
					kwargs["script"] = self.standardFunc.__get__(instance)
			else:
				func = self.standardFunc
		else:
			func = self.standardFunc
		if not func:
			raise NotImplementedError
		func(*args, **kwargs)

	def getCustomFunc(self, webModule=None):
		if webModule is None:
			if self.instance is not None:
				instance = self.instance()
				if instance is None:
					# The bound instance has been terminated
					return None
				webModule = instance.rule.ruleManager.webModule
		return getattr(
			webModule,
			"action_{self.actionId}".format(**locals()),
			None
		)


class Result(ScriptableObject):

	def __init__(self, criteria, context, index):
		super().__init__()
		self._criteria = weakref.ref(criteria)
		self.context: textInfos.offsets.Offsets = context
		self.index = index
		self.properties = criteria.properties
		rule = criteria.rule
		self._rule = weakref.ref(rule)
		self.zone = Zone(self) if rule.type == ruleTypes.ZONE else None
		webModule = rule.ruleManager.webModule
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
		self.bindGestures({
			gestureId: action
			for gestureId, action in rule.gestures.items()
			if gestureId not in criteria.gestures
		})
		self.bindGestures(criteria.gestures)

	def _get_criteria(self):
		return self._criteria()

	def _get_label(self):
		return self.properties.customName or self.rule.name

	def _get_name(self):
		return self.rule.name

	def _get_rule(self):
		return self._rule()

	def _get_value(self):
		customValue = self.properties.customValue
		if customValue:
			return customValue
		raise NotImplementedError

	def _get_startOffset(self):
		raise NotImplementedError

	def _get_endOffset(self):
		raise NotImplementedError

	def script_moveto(self, gesture):
		raise NotImplementedError

	def script_sayall(self, gesture):
		raise NotImplementedError

	def script_activate(self, gesture):
		raise NotImplementedError

	def script_speak(self, gesture):
		repeat = scriptHandler.getLastScriptRepeatCount() if gesture is not None else 0
		if repeat == 0:
			parts = []
			if self.properties.sayName:
				parts.append(self.label)
			parts.append(self.value)
			msg = " - ".join(parts)
			wx.CallAfter(ui.message, msg)
		else:
			self.script_moveto(None, fromSpeak=True)

	def script_mouseMove(self, gesture):
		raise NotImplementedError

	def __bool__(self):
		raise NotImplementedError

	def __lt__(self, other):
		try:
			return self.startOffset < other.startOffset
		except AttributeError as e:
			raise TypeError(f"'<' not supported between instances of '{type(self)}' and '{type(other)}'") from e

	def containsNode(self, node):
		offset = node.offset
		return self.startOffset <= offset and self.endOffset >= offset + node.size

	def containsResult(self, result):
		return self.startOffset <= result.startOffset and self.endOffset >= result.endOffset

	def getDisplayString(self):
		return " ".join(
			[self.name]
			+ [
				inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
				for identifier in list(self._gestureMap.keys())
			]
		)


class SingleNodeResult(Result):

	def __init__(self, criteria, node, context, index):
		self._node = weakref.ref(node)
		super().__init__(criteria, context, index)

	def _get_node(self):
		return self._node()

	def _get_value(self):
		return self.properties.customValue or self.node.getTreeInterceptorText()

	def _get_startOffset(self):
		return self.node.offset

	def _get_endOffset(self):
		node = self.node
		return node.offset + node.size

	def script_moveto(self, gesture, fromQuickNav=False, fromSpeak=False):
		if self.node is None or self.node.nodeManager is None:
			return
		rule = self.rule
		reason = nodeHandler.REASON_FOCUS
		if not fromQuickNav:
			reason = nodeHandler.REASON_SHORTCUT
		if fromSpeak:
			# Translators: Speak rule name on "Move to" action
			speech.speakMessage(_("Move to {ruleName}").format(
				ruleName=self.label)
			)
		elif self.properties.sayName:
			speech.speakMessage(self.label)
		treeInterceptor = self.rule.ruleManager.nodeManager.treeInterceptor
		if not treeInterceptor or not treeInterceptor.isReady:
			return
		treeInterceptor.passThrough = self.properties.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough
		if self.zone:
			rule.ruleManager.zone = self.zone
			# Ensure the focus does not remain on a control out of the zone
			treeInterceptor.rootNVDAObject.setFocus()
		else:
			for result in reversed(rule.ruleManager.getResults()):
				zone = result.zone
				if zone is None:
					continue
				if zone.containsResult(self):
					rule.ruleManager.zone = zone
					break
			else:
				rule.ruleManager._set_zone(rule.ruleManager.parentZone, force=True)
		offset = self.startOffset
		info = treeInterceptor.makeTextInfo(textInfos.offsets.Offsets(offset, offset))
		treeInterceptor.selection = info
		# Refetch the position in case some dynamic content has shrunk as we left it.
		info = treeInterceptor.selection.copy()
		if not treeInterceptor.passThrough:
			info.expand(textInfos.UNIT_LINE)
			speech.speakTextInfo(
				info,
				unit=textInfos.UNIT_LINE,
				reason=controlTypes.OutputReason.CARET
			)
			return
		focusObject = api.getFocusObject()
		try:
			nodeObject = self.node.getNVDAObject()
		except Exception:
			nodeObject = None
		if nodeObject == focusObject and focusObject is not None:
			focusObject.reportFocus()

	def script_sayall(self, gesture, fromQuickNav=False):
		speech.cancelSpeech()
		if self.properties.sayName:
			speech.speakMessage(self.label)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		speechMode = speech.getState().speechMode
		try:
			speech.setSpeechMode(speech.SpeechMode.off)
			treeInterceptor.passThrough = False
			browseMode.reportPassThrough.last = treeInterceptor.passThrough
			self.node.moveto()
			html.speakLine()
			api.processPendingEvents()
		except Exception:
			log.exception("Error during script_sayall")
			return
		finally:
			speech.setSpeechMode(speechMode)
		speech.sayAll.SayAllHandler.readText(
			speech.sayAll.CURSOR.CARET
		)

	def script_activate(self, gesture):
		if self.node is None or self.node.nodeManager is None:
			return
		if not self.rule.ruleManager.isReady :
			log.info ("not ready")
			return
		treeInterceptor = self.node.nodeManager.treeInterceptor
		if self.properties.sayName:
			speech.speakMessage(self.label)
		self.node.activate()
		time.sleep(0.1)
		api.processPendingEvents ()
		if not treeInterceptor:
			return
		treeInterceptor.passThrough = self.properties.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough

	def script_mouseMove(self, gesture):
		rule = self.rule
		criteria = self.criteria
		if self.properties.sayName:
			speech.speakMessage(self.label)
		treeInterceptor = html.getTreeInterceptor()
		if not treeInterceptor:
			return
		treeInterceptor.passThrough = self.properties.formMode
		browseMode.reportPassThrough.last = treeInterceptor.passThrough
		self.node.mouseMove()

	def getTextInfo(self):
		return self.node.getTextInfo()

	def __bool__(self):
		return bool(self.node)

	def containsNode(self, node):
		return node in self.node

	def getTitle(self):
		return self.label + " - " + self.node.innerText


class Criteria(ScriptableObject):

	def __init__(self, rule, data):
		super().__init__()
		self._rule = weakref.ref(rule)
		self.properties = CriteriaProperties(self)
		self.load(data)

	def _get_layer(self):
		return self.rule.layer

	def _get_rule(self):
		return self._rule()

	def _get_ruleManager(self):
		return self.rule.ruleManager

	def load(self, data):
		data = data.copy()
		self.name = data.pop("name", None)
		self.comment = data.pop("comment", None)
		self.contextPageTitle = data.pop("contextPageTitle", None)
		self.contextPageType = data.pop("contextPageType", None)
		self.contextParent = data.pop("contextParent", None)
		self.text = data.pop("text", None)
		self.role = data.pop("role", None)
		self.tag = data.pop("tag", None)
		self.id = data.pop("id", None)
		self.className = data.pop("className", None)
		self.states = data.pop("states", None)
		self.src = data.pop("src", None)
		self.url = data.pop("url", None)
		self.relativePath = data.pop("relativePath", None)
		self.index = data.pop("index", None)
		self.gestures = data.pop("gestures", {})
		gesturesMap = {}
		for gestureIdentifier in list(self.gestures.keys()):
			gesturesMap[gestureIdentifier] = "notFound"
		# self.bindGestures(gesturesMap)
		self.properties.load(data.pop("properties", {}))
		if data:
			raise ValueError(
				"Unexpected attribute"
				+ ("s" if len(data) > 1 else "")
				+ ": "
				+ ", ".join(list(data.keys()))
			)

	def dump(self):
		data = {}

		def setIfNotDefault(key, value, default=None):
			if value != default:
				data[key] = value

		def setIfNotNoneOrEmptyString(key, value):
			if value and value.strip():
				data[key] = value

		setIfNotNoneOrEmptyString("name", self.name)
		setIfNotNoneOrEmptyString("comment", self.comment)
		setIfNotNoneOrEmptyString("contextPageTitle", self.contextPageTitle)
		setIfNotNoneOrEmptyString("contextPageType", self.contextPageType)
		setIfNotNoneOrEmptyString("contextParent", self.contextParent)
		setIfNotNoneOrEmptyString("text", self.text)
		setIfNotDefault("role", self.role)
		setIfNotNoneOrEmptyString("tag", self.tag)
		setIfNotNoneOrEmptyString("id", self.id)
		setIfNotNoneOrEmptyString("className", self.className)
		setIfNotNoneOrEmptyString("states", self.states)
		setIfNotNoneOrEmptyString("src", self.src)
		setIfNotNoneOrEmptyString("url", self.url)
		setIfNotNoneOrEmptyString("relativePath", self.relativePath)
		setIfNotDefault("index", self.index)
		setIfNotDefault("gestures", self.gestures, {})
		setIfNotDefault("properties", self.properties.dump(), {})

		return data

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
		candidate = self.rule.ruleManager._getPageTitle()
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
				if not name.strip():
					continue
				rule = self.ruleManager.getRule(name, layer=self.layer)
				if rule is None:
					log.error((
						"In rule \"{rule}\".contextPageType: "
						"Rule not found: \"{pageType}\""
					).format(rule=self.rule.name, pageType=name))
					return False

				results = rule.getResults()
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

	def createResult(self, node, context, index):
		return SingleNodeResult(self, node, context, index)

	def iterResults(self):
		t = logTimeStart()
		mgr = self.rule.ruleManager
		text = self.text
		if not self.checkContextPageTitle():
			return
		if not self.checkContextPageType():
			return
		# Handle contextParent
		rootNodes = set()  # Set of possible parent nodes
		excludedNodes = set()  # Set of excluded parent nodes
		multipleContext = None  # Will be later set to either `True` or `False`
		for expr in (self.contextParent or "").split("&"):
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
				rule = mgr.getRule(name, layer=self.layer)
				if rule is None:
					log.error((
						"In rule \"{rule}\".contextParent: "
						"Rule not found: \"{parent}\""
					).format(rule=self.name, parent=name))
					return
				results = rule.getResults()
				if not exclude and any(r.properties.multiple for r in results):
					if multipleContext is None:
						multipleContext = True
				else:
					multipleContext = False
				if results:
					nodes = (result.node for result in results)
					if exclude:
						excludedNodes.update(nodes)
					else:
						altRootNodes.update(nodes)
			if not exclude and not altRootNodes:
				return
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
				return
			rootNodes = newRootNodes
		kwargs = getSimpleSearchKwargs(self)
		excludedNodes.update({
			result.node for result in self.rule.ruleManager.subModules._results
		})
		if excludedNodes:
			kwargs["exclude"] = excludedNodes
		limit = None
		if not self.properties.multiple:
			limit = self.index or 1  # 1-based

		index = 0
		if not rootNodes:
			parentZone = mgr.parentZone
			if parentZone is not None:
				rootNodes = (parentZone.result.node,)
			else:
				rootNodes = (mgr.nodeManager.mainNode,)
		for root in rootNodes or (parentNode,):
			rootLimit = limit
			if multipleContext:
				index = 0
			for node in root.searchNode(limit=rootLimit, **kwargs):
				index += 1  # 1-based
				if self.index:
					if index < self.index:
						continue
					elif index > self.index:
						break
				if limit is not None and not multipleContext:
					limit -= 1
				context = textInfos.offsets.Offsets(
					startOffset=root.offset,
					endOffset=root.offset + root.size
				) if root is not self.ruleManager.nodeManager.mainNode else None
				yield self.createResult(node, context, index)
				if not self.properties.multiple and not multipleContext:
					return

	def script_notFound(self, gesture):
		speech.speakMessage(_("{criteriaName} not found").format(
			criteriaName=self.label)
		)


class Rule(ScriptableObject):

	def __init__(self, ruleManager, data):
		super().__init__()
		self.layer = None
		self._ruleManager = weakref.ref(ruleManager)
		self._results = None
		self.properties = RuleProperties(self)
		self.load(data)

	def _get_label(self):
		return self.properties.customName or self.name

	def _get_ruleManager(self):
		return self._ruleManager()

	def dump(self):

		def setIfNotDefault(key, value, default=None):
			if value != default:
				data[key] = value

		def setIfNotNoneOrEmptyString(key, value):
			if value and value.strip():
				data[key] = value

		data = {}
		data["name"] = self.name
		data["type"] = self.type
		setIfNotNoneOrEmptyString("comment", self.comment)
		setIfNotDefault("gestures", self.gestures, {})
		if self.criteria:
			items = data["criteria"] = []
			for criteria in self.criteria:
				items.append(criteria.dump())
		setIfNotDefault("properties", self.properties.dump(), {})

		return data

	def load(self, data):
		data = data.copy()
		self.name = data.pop("name")
		self.type = data.pop("type")
		self.comment = data.pop("comment", None)
		self.criteria = [Criteria(self, criteria) for criteria in data.pop("criteria", [])]
		self.gestures = data.pop("gestures", {})
		gesturesMap = {}
		for gestureIdentifier in list(self.gestures.keys()):
			gesturesMap[gestureIdentifier] = "notFound"
		self.bindGestures(gesturesMap)
		self.properties.load(data.pop("properties", {}))
		if data:
			raise ValueError(
				"Unexpected attribute"
				+ ("s" if len(data) > 1 else "")
				+ ": "
				+ ", ".join(list(data.keys()))
			)

	def resetResults(self):
		self._results = None

	def getDisplayString(self):
		return " ".join(
			[self.name]
			+ [
				inputCore.getDisplayTextForGestureIdentifier(identifier)[1]
				for identifier in list(self._gestureMap.keys())
			]
		)

	def script_notFound(self, gesture):
		speech.speakMessage(_("{ruleName} not found").format(
			ruleName=self.label)
		)

	def getResults(self):
		if self._results is None:
			self._results = self._getResults()
		return self._results

	def _getResults(self):
		t = logTimeStart()
		for criteria in self.criteria:
			results = list(criteria.iterResults())
			if results:
				return results
		return []


def getSimpleSearchKwargs(criteria, raiseOnUnsupported=False):
	kwargs = {}
	for prop, expr in list(criteria.dump().items()):
		if prop in ("contextPageTitle", "contextPageType", "contextParent"):
			continue
		if prop not in [
			"className",
			"id",
			"relativePath",
			"role",
			"src",
			"states",
			"tag",
			"text",
			"url",
		]:
			if raiseOnUnsupported:
				raise ValueError(
					"Unsupported criteria: {prop}={expr!r}".format(**locals())
				)
			continue
		if not expr:
			continue
		if prop == "relativePath":
			kwargs["relativePath"] = expr
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
			# For "className", both space and ampersand are treated as "and" operator
			expr = expr.replace(" ", "&")
		# For "url", only space is treated as "and" operator
		for andIndex, expr in enumerate(expr.split("&" if prop != "url" else " ")):
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
					expr = expr[1:].strip()
					if prop == "url":
						if expr[0] == "=":
							notEq.append(expr[1:].strip())
						else:
							notIn.append(expr)
					else:
						if "*" in (expr[0], expr[-1]):
							notIn.append(expr.strip("*").strip())
						else:
							notEq.append(expr)
				else:
					if prop == "url":
						if expr[0] == "=":
							eq.append(expr[1:].strip())
						else:
							in_.append(expr)
					else:
						if "*" in (expr[0], expr[-1]):
							in_.append(expr.strip("*").strip())
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
				if prop in ("role", "states"):
					try:
						values = [int(value) for value in values]
					except ValueError:
						log.error(f"Invalid search criterion: {prop} {test} {values}")
				key = "{test}_{prop}#{index}".format(
					test=test,
					prop=prop,
					index=andIndex
				)
				kwargs[key] = values
	return kwargs


class Zone(AutoPropertyObject):

	def __init__(self, result):
		super().__init__()
		self.result = result
		rule = result.rule
		self._ruleManager = weakref.ref(rule.ruleManager)
		self.layer = rule.layer
		self.name = rule.name
		self.index = result.index

	def _get_ruleManager(self):
		return self._ruleManager()

	def _get_result(self):
		return self._result and self._result()

	def _set_result(self, result):
		self._result = weakref.ref(result)

	def __bool__(self):
		return bool(self.result)

	def __repr__(self):
		layer = self.layer
		name = self.name
		if not self:
			return f"<Zone {name} (invalidated)>"
		result = self.result
		startOffset = result.startOffset
		endOffset = result.endOffset
		return f"<Zone {layer}/{name} at ({startOffset}, {endOffset})>"

	def containsNode(self, node):
		offset = node.offset
		return self.containsOffsets(offset, offset + node.size)

	def containsOffsets(self, startOffset, endOffset):
		result = self.result
		return (
			result
			and result.startOffset <= startOffset
			and result.endOffset >= endOffset
		)

	def containsResult(self, result):
		r = self.result
		return r and r.containsResult(result)

	def containsTextInfo(self, info):
		try:
			return self.containsOffsets(info._startOffset, info._endOffset)
		except AttributeError:
			if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
				raise ValueError("Not supported {}".format(type(info)))
			raise

	def equals(self, other):
		"""Check if `obj` represents an instance of the same `Zone`.
		
		This cannot be achieved by implementing the usual `__eq__` method
		because `baseObjects.AutoPropertyObject.__new__` requires it to
		operate on identity as it stores the instance as key in a `WeakKeyDictionnary`
		in order to later invalidate property cache.
		"""
		return (
			isinstance(other, type(self))
			and self.name == other.name
			and self.index == other.index
		)

	def getRule(self):
		return self.ruleManager.getRule(self.name, layer=self.layer)

	def isOffsetAtStart(self, offset):
		result = self.result
		return result and result.startOffset == offset

	def isOffsetAtEnd(self, offset):
		result = self.result
		return result and result.endOffset == offset

	def isTextInfoAtStart(self, info):
		try:
			return self.isOffsetAtStart(info._startOffset)
		except AttributeError:
			if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
				raise ValueError("Not supported {}".format(type(info)))
			raise

	def isTextInfoAtEnd(self, info):
		try:
			return self.isOffsetAtEnd(info._endOffset)
		except AttributeError as e:
			if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
				raise ValueError("Not supported {}".format(type(info))) from e

	def restrictTextInfo(self, info):
		if not isinstance(info, textInfos.offsets.OffsetsTextInfo):
			raise ValueError("Not supported {}".format(type(info)))
		result = self.result
		if not result:
			return False
		res = False
		if info._startOffset < result.startOffset:
			res = True
			info._startOffset = result.startOffset
		elif info._startOffset > result.endOffset:
			res = True
			info._startOffset = result.endOffset
		return res

	def update(self, result=None):
		if result is not None:
			self._result = result
			return True
		try:
			# Result index is 1-based
			self.result = self.getRule().getResults()[self.index - 1]
		except IndexError:
			self._result = None
			return False
		except Exception:
			log.exception()
			self._result = None
			return False
		return True
