# globalPlugins/webAccess/profiles.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2026 Accessolutions (https://accessolutions.fr)
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

"""NVDA configuration profiles triggered by WebModules.

The profiles to apply are resolved from the focused document and the caret position,
then applied as NVDA profile triggers, stacked above the application profile and
below the manually activated profile, if any.

A profile reference is the name of an NVDA profile.
"""


__authors__ = (
	"André-Abush Clause <a.clause@accessolutions.fr>",
)


from bisect import bisect_right
from contextlib import contextmanager
from dataclasses import dataclass
import threading
import weakref

import wx

import addonHandler
import api
import appModuleHandler
import config
import core
from logHandler import log
import speech
import textInfos


addonHandler.initTranslation()


@dataclass
class ProfileContext:
	focus: "NVDAObjects.NVDAObject"
	treeInterceptor: "WebAccessBmdti"
	offset: int | None
	webModules: tuple["WebModule", ...]
	"""The root WebModule followed by the SubModules at the caret, from the outermost
	to the innermost.
	"""


class WebModuleProfileTrigger(config.ProfileTrigger):

	def __init__(self, profileName: str):
		self.spec = f"webAccess:{profileName}"
		self.profileName = profileName
		self._profile = None

	def enter(self):
		try:
			config.conf._triggerProfileEnter(self)
		except Exception:
			if self.profileName not in _failedProfiles:
				_failedProfiles.add(self.profileName)
				log.exception(f"Error entering trigger {self.spec}")

	__enter__ = enter


_failedProfiles: set[str] = set()
"""Profiles that failed to activate, logged only once.
"""


class _KeepState(Exception):
	"""Raised when the profiles cannot be resolved for now and the current state should be kept.
	"""


class ProfileManager:

	def __init__(self):
		self._lock = threading.Lock()
		self._updatePending = False
		self._terminated = False
		self._applied: list[WebModuleProfileTrigger] = []
		self._interval: tuple[weakref.ref, float, float] | None = None
		"""The TreeInterceptor and the range of offsets within which the resolved
		profiles cannot change.
		"""
		self._stateTreeInterceptor: weakref.ref | None = None
		"""The TreeInterceptor the current state has been resolved for.
		"""
		self._triggersEnabled = config.conf.profileTriggersEnabled
		self._lastFocus = None
		"""The focus the profiles have last been resolved for upon focus change.
		"""
		self._nvdaProfileNames: set[str] | None = None
		self._warnedMissing: set[tuple[str, str]] = set()
		config.post_configReset.register(self.onConfigReset)
		config.post_configProfileSwitch.register(self.onConfigProfileSwitch)
		appModuleHandler.post_appSwitch.register(self.requestUpdate)

	def terminate(self):
		self._terminated = True
		config.post_configReset.unregister(self.onConfigReset)
		config.post_configProfileSwitch.unregister(self.onConfigProfileSwitch)
		appModuleHandler.post_appSwitch.unregister(self.requestUpdate)
		# Avoid needlessly switching speech and braille settings while NVDA exits.
		if not getattr(core, "_hasShutdownBeenTriggered", False):
			self._apply([])
		self._applied.clear()
		self._interval = None
		self._lastFocus = None

	def requestUpdate(self):
		"""Schedule an update on the main thread. Safe to call from any thread.
		"""
		with self._lock:
			if self._updatePending or self._terminated:
				return
			self._updatePending = True
		wx.CallAfter(self._update)

	def update(self, treeInterceptor=None, offset: int | None = None):
		"""Update immediately if on the main thread, else schedule an update.

		`treeInterceptor`, `offset`
			The caret position to resolve the profiles for, if not the current one.
		"""
		if threading.current_thread() is not threading.main_thread():
			self.requestUpdate()
			return
		self._update(treeInterceptor=treeInterceptor, offset=offset)

	def isInInterval(self, treeInterceptor, offset: int | None) -> bool:
		interval = self._interval
		if interval is None or offset is None:
			return False
		tiRef, start, end = interval
		return tiRef() is treeInterceptor and start <= offset < end

	def onFocusChanging(self):
		"""Called upon each event NVDA executes for a new focus, before reporting it.

		After setting the new focus, NVDA executes "foreground", "focusEntered" and
		"treeInterceptor_gainFocus" events, which might report the new focus, before the
		"gainFocus" event itself. The application profile is switched even earlier.
		"""
		focus = api.getFocusObject()
		if focus is self._lastFocus:
			return
		self.update()
		if config.conf._suspendedTriggers is None:
			self._lastFocus = focus

	def onCaretMoved(self, treeInterceptor, info):
		offset = getattr(info, "_startOffset", None)
		if self.isInInterval(treeInterceptor, offset):
			return
		self.update(treeInterceptor=treeInterceptor, offset=offset)

	@contextmanager
	def updatingBeforeSpeech(self, treeInterceptor):
		"""Apply the profiles of the target position before it is spoken.

		NVDA speaks the target of a caret movement before actually moving the caret.
		"""
		speakTextInfo = speech.speakTextInfo

		def wrapper(info, *args, **kwargs):
			try:
				self.onCaretMoved(treeInterceptor, info)
			except Exception:
				log.exception()
			return speakTextInfo(info, *args, **kwargs)

		speech.speakTextInfo = wrapper
		try:
			yield
		finally:
			if speech.speakTextInfo is wrapper:
				speech.speakTextInfo = speakTextInfo

	def onTimeout(self):
		"""Called periodically from the scheduler thread.

		Catches caret movements not notified, eg. during or at the end of say all.
		"""
		if self._interval is not None:
			wx.CallAfter(self._checkCaret)

	def _checkCaret(self):
		interval = self._interval
		if interval is None or self._terminated or interval[1:] == (float("-inf"), float("inf")):
			return
		if speech.sayAll.SayAllHandler and speech.sayAll.SayAllHandler.isRunning():
			# Switching profiles might cancel speech.
			return
		ti = interval[0]()
		if ti is None:
			self.requestUpdate()
			return
		try:
			offset = ti.makeTextInfo(textInfos.POSITION_CARET)._startOffset
		except Exception:
			return
		if not self.isInInterval(ti, offset):
			self.update()

	def onWebModulesReset(self):
		self._warnedMissing.clear()
		self.requestUpdate()

	def onConfigProfileSwitch(self, *args, **kwargs):
		enabled = config.conf.profileTriggersEnabled
		if enabled and not self._triggersEnabled:
			# NVDA only re-enters the trigger of the current application.
			self.requestUpdate()
		self._triggersEnabled = enabled

	def onConfigReset(self, factoryDefaults=False):
		# The profiles stack and cache have been cleared by NVDA, but not the suspended triggers.
		suspended = config.conf._suspendedTriggers
		if suspended:
			for trigger in list(suspended):
				if isinstance(trigger, WebModuleProfileTrigger):
					del suspended[trigger]
		self._applied.clear()
		self._stateTreeInterceptor = None
		self._lastFocus = None
		_failedProfiles.clear()
		self._warnedMissing.clear()
		self.requestUpdate()

	def _update(self, treeInterceptor=None, offset: int | None = None):
		with self._lock:
			self._updatePending = False
		if self._terminated:
			return
		if config.conf._suspendedTriggers is not None:
			# NVDA's GUI has focus: Keep the profiles as they are, as NVDA does for the
			# application profile, so that the user can change settings in the right profile.
			return
		self._interval = None
		self._nvdaProfileNames = None
		try:
			ti, context = self._getContext(treeInterceptor, offset)
		except Exception:
			log.exception()
			ti = context = None
		if context is None:
			if ti is not None:
				# No WebModule on this document: Wait for a reset.
				self._interval = (weakref.ref(ti), float("-inf"), float("inf"))
			names = []
		else:
			try:
				names = self._resolve(context)
			except _KeepState:
				return
			except Exception:
				log.exception()
				if self._isSameState(ti):
					return
				names = []
		self._stateTreeInterceptor = weakref.ref(ti) if ti is not None else None
		self._apply(names)

	def _isSameState(self, treeInterceptor) -> bool:
		tiRef = self._stateTreeInterceptor
		return tiRef is not None and tiRef() is treeInterceptor

	def _getContext(
		self,
		treeInterceptor=None,
		offset: int | None = None,
	) -> tuple["WebAccessBmdti | None", ProfileContext | None]:
		from . import webAccessEnabled
		from .overlay import WebAccessBmdti, WebAccessObject
		if not webAccessEnabled:
			return None, None
		focus = api.getFocusObject()
		if not isinstance(focus, WebAccessObject):
			return None, None
		ti = focus.webAccess.treeInterceptor
		if not isinstance(ti, WebAccessBmdti):
			return None, None
		root = ti.webAccess.rootWebModule
		if root is None:
			return ti, None
		if offset is None or treeInterceptor is not ti:
			try:
				offset = ti.makeTextInfo(textInfos.POSITION_CARET)._startOffset
			except Exception:
				offset = None
		webModules = [root]
		if offset is not None:
			webModules.extend(root.ruleManager.subModules.iterAtPosition(offset))
		return ti, ProfileContext(
			focus=focus,
			treeInterceptor=ti,
			offset=offset,
			webModules=tuple(webModules),
		)

	def _resolve(self, context: ProfileContext) -> list[str]:
		"""Resolve the profiles to apply, from the lowest to the highest priority:
		 - The profile of each WebModule, from the root to the innermost SubModule.
		"""
		refs = [
			(webModule, webModule.configProfile)
			for webModule in context.webModules
			if webModule.configProfile
		]
		ruleManager = context.webModules[0].ruleManager
		if not ruleManager.isReady and self._isSameState(context.treeInterceptor):
			# Being updated: Keep the contextual profiles until the update completes.
			raise _KeepState
		positions = set(ruleManager.subModules.iterPositions())
		self._setInterval(context, sorted({offset for position in positions for offset in position}))
		names = []
		for owner, ref in refs:
			name = self._getProfileName(owner, ref)
			if name is None:
				continue
			if name in names:
				names.remove(name)
			names.append(name)
		return names

	def _setInterval(self, context: ProfileContext, boundaries: list[int]):
		if context.offset is None:
			return
		index = bisect_right(boundaries, context.offset)
		start = boundaries[index - 1] if index > 0 else float("-inf")
		end = boundaries[index] if index < len(boundaries) else float("inf")
		self._interval = (weakref.ref(context.treeInterceptor), start, end)

	def _getProfileName(self, webModule, ref: str) -> str | None:
		if self._nvdaProfileNames is None:
			self._nvdaProfileNames = set(config.conf.listProfiles())
		if ref in self._nvdaProfileNames:
			return ref
		key = (webModule.name, ref)
		if key not in self._warnedMissing:
			self._warnedMissing.add(key)
			log.warning(f"Profile not found: {ref!r} (WebModule {webModule.name!r})")
		return None

	def _isCurrent(self, trigger: WebModuleProfileTrigger, name: str) -> bool:
		"""Whether the given applied trigger matches the given profile name.
		"""
		return trigger.profileName == name

	def _isApplied(self, trigger: WebModuleProfileTrigger) -> bool:
		profile = trigger._profile
		return profile is not None and any(p is profile for p in config.conf.profiles)

	def _isAboveAppProfiles(self) -> bool:
		"""Whether the applied profiles are above the application profiles.

		An application profile might have been re-entered above them, eg. while triggers
		were suspended.
		"""
		if not self._applied:
			return True
		profiles = config.conf.profiles
		ours = [trigger._profile for trigger in self._applied]
		first = ours[0]
		index = next((index for index, profile in enumerate(profiles) if profile is first), None)
		if index is None:
			return False
		for mod in list(appModuleHandler.runningTable.values()):
			profile = getattr(getattr(mod, "_configProfileTrigger", None), "_profile", None)
			if profile is None or any(p is profile for p in ours):
				continue
			if any(p is profile for p in profiles[index + 1:]):
				return False
		return True

	def _apply(self, names: list[str]):
		conf = config.conf
		if not conf.profileTriggersEnabled:
			# NVDA has already deactivated all the triggered profiles.
			self._applied.clear()
			self._interval = None
			return
		if conf._suspendedTriggers is None:
			self._applied = [trigger for trigger in self._applied if self._isApplied(trigger)]
		applied = self._applied
		common = 0
		if conf._suspendedTriggers is not None or self._isAboveAppProfiles():
			for trigger, name in zip(applied, names):
				if not self._isCurrent(trigger, name):
					break
				common += 1
		if common == len(applied) == len(names):
			return
		with conf.atomicProfileSwitch():
			for trigger in reversed(applied[common:]):
				trigger.exit()
			del applied[common:]
			for name in names[common:]:
				trigger = WebModuleProfileTrigger(name)
				trigger.enter()
				if conf._suspendedTriggers is not None or self._isApplied(trigger):
					applied.append(trigger)


profileManager: ProfileManager | None = None


def initialize():
	global profileManager
	profileManager = ProfileManager()


def terminate():
	global profileManager
	if profileManager is not None:
		profileManager.terminate()
	profileManager = None


def onWebModulesReset():
	manager = profileManager
	if manager is not None:
		manager.onWebModulesReset()


def requestUpdate():
	manager = profileManager
	if manager is not None:
		manager.requestUpdate()


def update():
	manager = profileManager
	if manager is not None:
		manager.update()


def onFocusChanging():
	manager = profileManager
	if manager is not None:
		manager.onFocusChanging()


@contextmanager
def updatingBeforeSpeech(treeInterceptor):
	manager = profileManager
	if manager is None:
		yield
		return
	with manager.updatingBeforeSpeech(treeInterceptor):
		yield


def onTimeout():
	manager = profileManager
	if manager is not None:
		manager.onTimeout()


def onCaretMoved(treeInterceptor, info):
	manager = profileManager
	if manager is not None:
		manager.onCaretMoved(treeInterceptor, info)
