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

A profile reference is either the key of a profile embedded in the WebModule
(see `WebModule.getProfileData`) or the name of an NVDA profile.

Embedded profiles are never written to NVDA's profiles directory: They are injected in
NVDA's profiles cache under a reserved name, and changes made while they are active
are saved in the writable layer of their WebModule when NVDA saves its configuration.
"""


__authors__ = (
	"André-Abush Clause <a.clause@accessolutions.fr>",
)


from bisect import bisect_right
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import itertools
import os
import re
import tempfile
import threading
import weakref

from configobj import ConfigObj
import wx

import addonHandler
import api
import appModuleHandler
import config
import core
from config import profileUpgrader
from config.configSpec import latestSchemaVersion
from logHandler import log
import NVDAState
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

	def getPageTypes(self) -> list[str]:
		from .ruleHandler import ruleTypes
		# Not using `RuleManager.getPageTypes` as it waits for ongoing updates.
		return [
			result.rule.name
			for result in self.webModules[0].ruleManager.getResults()
			if result.rule.type == ruleTypes.PAGE_TYPE
		]

	def getResultsAtCaret(self) -> tuple["Result", ...]:
		"""The Results containing the caret, for all the WebModules active on the document.
		"""
		offset = self.offset
		if offset is None:
			return ()
		return tuple(
			result
			for result in self.webModules[0].ruleManager.getAllResults()
			if containsOffset(result, offset)
		)


class ProfileHandle:
	"""Returned by `WebModule.pushProfile`.

	Can be used as a context manager.
	"""

	def __init__(self, webModule, ref: str):
		self._webModule = weakref.ref(webModule)
		self._webModuleName = None
		self.ref = ref

	def __enter__(self):
		return self

	def __exit__(self, excType, excVal, traceback):
		self.release()

	@property
	def webModule(self):
		return self._webModule()

	@property
	def webModuleName(self) -> str | None:
		"""The handle also applies to other instances of the same WebModule, eg. in a dialog
		of the page.

		Retrieved lazily, as the name is not known yet when called from the constructor.
		"""
		webModule = self._webModule()
		if webModule is not None and webModule.name:
			self._webModuleName = webModule.name
		return self._webModuleName

	def release(self):
		manager = profileManager
		if manager is not None:
			manager.releaseProfile(self)


@dataclass
class EmbeddedProfile:
	webModuleName: str
	key: str
	source: dict
	"""The data the profile has been built from, as found in the running WebModule.
	"""
	profile: ConfigObj


def getEmbeddedProfileName(webModule, key: str) -> str:
	# The colon is not allowed in file names, preventing conflicts with NVDA profiles.
	return f"WebAccess: {webModule.name} / {key}"


def buildEmbeddedProfile(name: str, data: dict) -> ConfigObj:
	profile = ConfigObj(None, indent_type="\t", encoding="UTF-8")
	# Some upgrade steps rely on the file name. Embedded profiles are removed from NVDA's
	# dirty profiles before it saves, but should one ever be written, it would not
	# abort the save as the directory exists.
	profile.filename = os.path.join(
		tempfile.gettempdir(),
		"nvda-" + re.sub(r'[\\/:*?"<>|]', "_", name) + ".ini",
	)
	profile.update(deepcopy(data))
	if profileUpgrader.SCHEMA_VERSION_KEY not in profile:
		profile[profileUpgrader.SCHEMA_VERSION_KEY] = latestSchemaVersion
	profileUpgrader.upgrade(profile, config.conf.validator, None)
	profile.name = name
	profile.manual = False
	profile.triggered = False
	return profile


def containsOffset(result, offset: int) -> bool:
	"""Whether a Result is at the given offset, consistently with `RuleManager.iterResultsAtTextInfo`.
	"""
	return result.startOffset <= offset <= result.endOffset


def toJsonValue(value):
	"""Convert a configuration value to a JSON serializable one.

	Values validated by NVDA, such as feature flags, are converted to strings, as they are
	written in NVDA profiles.
	"""
	if isinstance(value, Mapping):
		return {str(key): toJsonValue(item) for key, item in value.items()}
	if isinstance(value, (list, tuple)):
		return [toJsonValue(item) for item in value]
	if value is None or isinstance(value, (bool, int, float, str)):
		return value
	return str(value)


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


class _Retry(_KeepState):
	"""Raised when the profiles cannot be resolved for now and should be resolved again later.
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
		self._resolving = False
		self._handles: list[ProfileHandle] = []
		self._lastFocus = None
		"""The focus the profiles have last been resolved for upon focus change.
		"""
		self._nvdaProfileNames: set[str] | None = None
		self._warnedMissing: set[tuple[str, str]] = set()
		self._embedded: dict[str, EmbeddedProfile] = {}
		self._unsaved: set[str] = set()
		"""Embedded profiles that could not be saved, kept dirty for the next attempt.
		"""
		config.post_configReset.register(self.onConfigReset)
		config.pre_configSave.register(self.onPreConfigSave)
		config.post_configSave.register(self.onPostConfigSave)
		config.post_configProfileSwitch.register(self.onConfigProfileSwitch)
		appModuleHandler.post_appSwitch.register(self.requestUpdate)
		self._patchProfilesDialog()

	def terminate(self):
		self._terminated = True
		config.post_configReset.unregister(self.onConfigReset)
		config.pre_configSave.unregister(self.onPreConfigSave)
		config.post_configSave.unregister(self.onPostConfigSave)
		config.post_configProfileSwitch.unregister(self.onConfigProfileSwitch)
		appModuleHandler.post_appSwitch.unregister(self.requestUpdate)
		self._unpatchProfilesDialog()
		conf = config.conf
		# NVDA saves its configuration upon exit only after add-ons are terminated.
		if conf["general"]["saveConfigurationOnExit"] and NVDAState.shouldWriteToDisk():
			self.saveEmbeddedProfiles()
		# Avoid needlessly switching speech and braille settings while NVDA exits.
		if not getattr(core, "_hasShutdownBeenTriggered", False):
			self._apply([])
			embeddedProfiles = [embedded.profile for embedded in self._embedded.values()]
			remaining = [
				p for p in conf.profiles
				if not any(p is profile for profile in embeddedProfiles)
			]
			if len(remaining) != len(conf.profiles):
				conf.profiles[:] = remaining
				conf._handleProfileSwitch()
		self._applied.clear()
		self._interval = None
		self._lastFocus = None
		for name in self._embedded:
			conf._profileCache.pop(name, None)
			conf._dirtyProfiles.discard(name)
		self._embedded.clear()

	def _patchProfilesDialog(self):
		"""Have NVDA's Configuration Profiles dialog list the active embedded profiles.

		It fails to open if the edited profile, ie. the topmost one, is not listed.
		"""
		from gui.configProfiles import ProfilesDialog
		init = self._profilesDialogInit = ProfilesDialog.__init__
		manager = weakref.ref(self)

		def __init__(dialog, *args, **kwargs):
			instance = manager()
			if instance is None:
				return init(dialog, *args, **kwargs)
			with instance._listingActiveEmbeddedProfiles():
				return init(dialog, *args, **kwargs)

		ProfilesDialog.__init__ = self._patchedProfilesDialogInit = __init__

	def _unpatchProfilesDialog(self):
		from gui.configProfiles import ProfilesDialog
		if ProfilesDialog.__init__ is self._patchedProfilesDialogInit:
			ProfilesDialog.__init__ = self._profilesDialogInit

	@contextmanager
	def _listingActiveEmbeddedProfiles(self):
		conf = config.conf
		names = [profile.name for profile in conf.profiles[1:] if profile.name in self._embedded]
		if not names:
			yield
			return
		listProfiles = conf.listProfiles

		def wrapper():
			return itertools.chain(listProfiles(), names)

		conf.listProfiles = wrapper
		try:
			yield
		finally:
			if conf.__dict__.get("listProfiles") is wrapper:
				del conf.listProfiles

	def requestUpdate(self):
		"""Schedule an update on the main thread. Safe to call from any thread.
		"""
		with self._lock:
			if self._updatePending or self._terminated or self._resolving:
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
		if self._resolving:
			# Called from `WebModule.getProfiles`: Already being resolved.
			return
		self._update(treeInterceptor=treeInterceptor, offset=offset)

	def pushProfile(self, webModule, ref: str) -> ProfileHandle:
		handle = ProfileHandle(webModule, ref)
		self._handles.append(handle)
		self.update()
		return handle

	def releaseProfile(self, handle: ProfileHandle):
		try:
			self._handles.remove(handle)
		except ValueError:
			return
		self.update()

	def releaseProfiles(self, webModule):
		"""Release the profiles pushed by the given WebModule instance.
		"""
		handles = [handle for handle in self._handles if handle.webModule is webModule]
		for handle in handles:
			self._handles.remove(handle)
		if handles:
			self.requestUpdate()

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
		self._embedded.clear()
		self._unsaved.clear()
		self._stateTreeInterceptor = None
		self._lastFocus = None
		_failedProfiles.clear()
		self._warnedMissing.clear()
		self.requestUpdate()

	def onPreConfigSave(self):
		if not NVDAState.shouldWriteToDisk():
			# NVDA will not write anything either.
			return
		self.saveEmbeddedProfiles()

	def onPostConfigSave(self):
		config.conf._dirtyProfiles.update(self._unsaved)
		self._unsaved.clear()

	def saveEmbeddedProfiles(self, names: Iterable[str] | None = None):
		"""Save the given, or all, modified embedded profiles in their WebModule.
		"""
		dirty = config.conf._dirtyProfiles
		for name, embedded in list(self._embedded.items()):
			if name not in dirty or (names is not None and name not in names):
				continue
			# Prevent NVDA from writing it to a file.
			dirty.discard(name)
			try:
				saved = self._persist(embedded)
			except Exception:
				log.exception(f"Error saving embedded profile {name!r}")
				saved = False
			if not saved:
				self._unsaved.add(name)

	def _persist(self, embedded: EmbeddedProfile) -> bool:
		"""Save an embedded profile in the writable layer of a freshly loaded instance of its WebModule.

		The running instances are left untouched, and so is the source of the embedded profile:
		It is rebuilt only once these instances get reloaded.
		"""
		from .webModuleHandler import getEditableWebModule, getWebModule, save
		name = embedded.profile.name
		webModule = getWebModule(embedded.webModuleName)
		if webModule is None or webModule.getProfileData(embedded.key) is None:
			log.warning(f"Changes to embedded profile {name!r} discarded: No longer defined")
			return True
		editable = getEditableWebModule(webModule, prompt=False)
		if not editable:
			log.warning(f"Changes to embedded profile {name!r} not saved: WebModule not editable")
			return False
		editable.setProfileData(embedded.key, toJsonValue(embedded.profile.dict()))
		if not save(editable, prompt=False, reload=False):
			log.warning(f"Changes to embedded profile {name!r} not saved")
			return False
		return True

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
		except _Retry:
			self.requestUpdate()
			return
		except Exception:
			log.exception()
			ti = context = None
		if context is None:
			if ti is not None:
				# No WebModule on this document: Wait for a reset.
				self._interval = (weakref.ref(ti), float("-inf"), float("inf"))
			names = []
		else:
			self._resolving = True
			try:
				names = self._resolve(context)
			except _KeepState:
				return
			except Exception:
				log.exception()
				if self._isSameState(ti):
					return
				names = []
			finally:
				self._resolving = False
		self._stateTreeInterceptor = weakref.ref(ti) if ti is not None else None
		self._apply(names)
		self._releaseEmbedded(names)

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
			if ti.webAccess._loadingRootWebModule:
				# Re-entrant call, eg. `pushProfile` called from a WebModule constructor.
				raise _Retry
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
		 - The profile of each matched page type.
		 - The profile of each other Result at the caret, from the outermost to the innermost.
		 - The profiles returned by `WebModule.getProfiles`, for each WebModule from the root
		   to the innermost SubModule.
		 - The profiles pushed with `WebModule.pushProfile`, in the same order.
		"""
		from .ruleHandler import ruleTypes
		from .webModuleHandler.webModule import WebModule
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
		rangedResults = []
		for result in ruleManager.getAllResults():
			try:
				ref = result.properties.profile
				if not ref:
					continue
				owner = result.rule.ruleManager.webModule
				if owner not in context.webModules:
					continue
				if result.rule.type == ruleTypes.PAGE_TYPE:
					refs.append((owner, ref))
					continue
				# Inclusive end offset, see `containsOffset`
				positions.add((result.startOffset, result.endOffset + 1))
				if context.offset is not None and containsOffset(result, context.offset):
					rangedResults.append(result)
			except Exception:
				# Nodes might be deleted by an ongoing update.
				if self._isSameState(context.treeInterceptor):
					raise _KeepState
				log.exception()
		rangedResults.sort(key=lambda result: (result.startOffset, -result.endOffset))
		for result in rangedResults:
			refs.append((result.rule.ruleManager.webModule, result.properties.profile))
		self._setInterval(context, sorted({offset for position in positions for offset in position}))
		for webModule in context.webModules:
			if type(webModule).getProfiles is not WebModule.getProfiles:
				# Might depend on anything: Resolve again upon each caret movement.
				self._interval = None
			try:
				for ref in webModule.getProfiles(context):
					refs.append((webModule, ref))
			except Exception:
				log.exception(f"Error in getProfiles of WebModule {webModule.name!r}")
		self._handles = [handle for handle in self._handles if handle.webModule is not None]
		for webModule in context.webModules:
			for handle in self._handles:
				if handle.webModuleName == webModule.name:
					refs.append((webModule, handle.ref))
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
		data = webModule.getProfileData(ref)
		if data is not None:
			return self._getEmbeddedProfile(webModule, ref, data)
		if self._nvdaProfileNames is None:
			self._nvdaProfileNames = set(config.conf.listProfiles())
		if ref in self._nvdaProfileNames:
			return ref
		key = (webModule.name, ref)
		if key not in self._warnedMissing:
			self._warnedMissing.add(key)
			log.warning(f"Profile not found: {ref!r} (WebModule {webModule.name!r})")
		return None

	def _getEmbeddedProfile(self, webModule, key: str, data: dict) -> str | None:
		name = getEmbeddedProfileName(webModule, key)
		conf = config.conf
		embedded = self._embedded.get(name)
		if (
			embedded is not None
			and conf._profileCache.get(name) is embedded.profile
			# Keep unsaved changes
			and (embedded.source == data or name in conf._dirtyProfiles or name in self._unsaved)
		):
			return name
		try:
			profile = buildEmbeddedProfile(name, data)
		except Exception:
			if (webModule.name, key) not in self._warnedMissing:
				self._warnedMissing.add((webModule.name, key))
				log.exception(f"Invalid embedded profile {key!r} (WebModule {webModule.name!r})")
			return None
		conf._profileCache[name] = profile
		self._embedded[name] = EmbeddedProfile(
			webModuleName=webModule.name,
			key=key,
			source=deepcopy(data),
			profile=profile,
		)
		return name

	def _releaseEmbedded(self, keep: list[str]):
		"""Remove from NVDA's cache the embedded profiles no longer in use.
		"""
		conf = config.conf
		for name, embedded in list(self._embedded.items()):
			profile = embedded.profile
			if (
				name in keep
				or name in conf._dirtyProfiles
				or name in self._unsaved
				or any(p is profile for p in conf.profiles)
			):
				continue
			if conf._profileCache.get(name) is profile:
				del conf._profileCache[name]
			del self._embedded[name]

	def editEmbeddedProfile(self, webModule, key: str):
		"""Open NVDA settings to edit an embedded profile, manually activated meanwhile.

		Changes are saved in the WebModule as soon as NVDA settings are closed.
		"""
		import gui
		from gui import blockAction
		from gui.settingsDialogs import NVDASettingsDialog, SettingsDialog

		def error(message):
			gui.messageBox(
				message=message,
				# Translators: The title of an error message dialog
				caption=_("Error"),
				style=wx.OK | wx.ICON_ERROR,
				parent=gui.mainFrame,
			)

		modalDialogOpen = blockAction.Context.MODAL_DIALOG_OPEN
		if modalDialogOpen.blockActionIf():
			if modalDialogOpen.callback:
				modalDialogOpen.callback()
			return
		if any(
			isinstance(dialog, NVDASettingsDialog) and state is SettingsDialog.DialogState.CREATED
			for dialog, state in list(SettingsDialog._instances.items())
		):
			# Translators: An error message upon attempting to edit an embedded profile
			error(_("Please close NVDA settings first."))
			return
		data = webModule.getProfileData(key)
		name = self._getEmbeddedProfile(webModule, key, data) if data is not None else None
		if name is None:
			# Translators: An error message upon attempting to edit an embedded profile
			error(_("Unable to load this profile. See NVDA log for details."))
			return
		conf = config.conf
		previous = conf.profiles[-1].name if len(conf.profiles) > 1 and conf.profiles[-1].manual else None
		conf.manualActivateProfile(name)
		profile = conf.profiles[-1]
		closed = False

		def close():
			nonlocal closed
			if closed:
				return
			closed = True
			if len(conf.profiles) > 1 and conf.profiles[-1] is profile:
				try:
					conf.manualActivateProfile(previous)
				except Exception:
					log.exception(f"Error restoring manually activated profile {previous!r}")
					conf.manualActivateProfile(None)
			if NVDAState.shouldWriteToDisk():
				self.saveEmbeddedProfiles((name,))

		def onDestroy(evt):
			evt.Skip()
			# Destroy events of child windows are propagated, and the Python wrapper of the
			# dialog might differ from `dialog` while being destroyed. As in NVDA's
			# `SettingsDialog._onWindowDestroy`, check whether the dialog itself is still alive.
			if not dialog:
				wx.CallAfter(close)

		dialog = None
		gui.mainFrame.prePopup()
		try:
			dialog = NVDASettingsDialog(gui.mainFrame)
			dialog.Bind(wx.EVT_WINDOW_DESTROY, onDestroy)
			dialog.Show()
		except Exception:
			log.exception()
			if dialog:
				dialog.Destroy()
			close()
			# Translators: An error message upon attempting to edit an embedded profile
			error(_("Unable to open NVDA settings. See NVDA log for details."))
		finally:
			gui.mainFrame.postPopup()

	def _isCurrent(self, trigger: WebModuleProfileTrigger, name: str) -> bool:
		"""Whether the given applied trigger matches the given profile name.

		An embedded profile rebuilt since it has been applied must be re-entered.
		"""
		if trigger.profileName != name:
			return False
		embedded = self._embedded.get(name)
		return embedded is None or trigger._profile is None or trigger._profile is embedded.profile

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


def getProfileChoices(embeddedKeys: Iterable[str]) -> dict[str, str]:
	"""The labels of the profiles that can be referenced, by reference.

	Embedded profiles take precedence over NVDA profiles with the same name.
	"""
	choices = {key: key for key in embeddedKeys}
	for name in config.conf.listProfiles():
		if name not in choices:
			# Translators: A choice of NVDA configuration profile, as opposed to an embedded one
			choices[name] = _("{name} (NVDA profile)").format(name=name)
	return choices


def pushProfile(webModule, ref: str) -> ProfileHandle:
	manager = profileManager
	if manager is None:
		return ProfileHandle(webModule, ref)
	return manager.pushProfile(webModule, ref)


def releaseProfiles(webModule):
	manager = profileManager
	if manager is not None:
		manager.releaseProfiles(webModule)


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


def editEmbeddedProfile(webModule, key: str):
	manager = profileManager
	if manager is not None:
		manager.editEmbeddedProfile(webModule, key)


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
