# globalPlugins/webAccess/config.py
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


__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from enum import StrEnum, auto

import config

from . import webModuleHandler


class UiMode(StrEnum):
	"""Configurable UI surfaces stored under conf["webAccess"]["uiModes"]."""
	RULE_WIZARD = auto()
	RULE_EDITOR = auto()
	CRITERIA_EDITOR = auto()
	INSPECTOR = auto()


class UiModePref(StrEnum):
	"""Prefixed choice used only by the inspector (F12 toggles both ways)."""
	LAST_USED = auto()


class UiModeSetting(StrEnum):
	"""Keys of each per-surface subsection."""
	MODE = auto()
	LAST_USED = auto()


class RuleWizardMode(StrEnum):
	WIZARD = auto()
	EDITOR = auto()


class EditorMode(StrEnum):
	SIMPLE = auto()
	FULL = auto()


class InspectorMode(StrEnum):
	SINGLE = auto()
	ANCESTORS = auto()


# Maps each UI surface to its concrete mode enum.
# The first member is the built-in default; the last is the fallback.
UI_MODES = {
	UiMode.RULE_WIZARD: RuleWizardMode,
	UiMode.RULE_EDITOR: EditorMode,
	UiMode.CRITERIA_EDITOR: EditorMode,
	UiMode.INSPECTOR: InspectorMode,
}

# Only the inspector persists last-used: F12 switches both ways.
_REMEMBERS_LAST_USED = frozenset({UiMode.INSPECTOR})

_UI_MODES_SECTION = "uiModes"


def _optionSpec(values, default):
	return "option(%s, default=%r)" % (
		", ".join("%r" % str(v) for v in values),
		str(default),
	)


def _first(enumCls):
	return next(iter(enumCls))


def _last(enumCls):
	return tuple(enumCls)[-1]


def _coerceEnum(enumCls, value, default=None):
	if isinstance(value, enumCls):
		return value
	try:
		return enumCls(value)
	except ValueError:
		return default if default is not None else _first(enumCls)


def _uiModeName(name):
	return name if isinstance(name, UiMode) else UiMode(name)


def _remembersLastUsed(name):
	return _uiModeName(name) in _REMEMBERS_LAST_USED


def _uiModeConfSpec(enumCls, rememberLastUsed):
	modeValues = tuple(enumCls)
	if rememberLastUsed:
		modeValues = (UiModePref.LAST_USED,) + modeValues
	spec = {
		str(UiModeSetting.MODE): _optionSpec(modeValues, default=_first(enumCls)),
	}
	if rememberLastUsed:
		spec[str(UiModeSetting.LAST_USED)] = _optionSpec(
			tuple(enumCls),
			default=_first(enumCls),
		)
	return spec


CONFIG_SPEC = {
	"devMode": "boolean(default=False)",
	"disableUserConfig": "boolean(default=False)",
	"writeInAddons": "boolean(default=False)",
	_UI_MODES_SECTION: {
		str(name): _uiModeConfSpec(enumCls, name in _REMEMBERS_LAST_USED)
		for name, enumCls in UI_MODES.items()
	},
}


_cache = None


def _uiModeSection(name):
	return config.conf["webAccess"][_UI_MODES_SECTION][_uiModeName(name)]


def getUiModePref(name):
	name = _uiModeName(name)
	enumCls = UI_MODES[name]
	value = _uiModeSection(name)[UiModeSetting.MODE]
	if _remembersLastUsed(name):
		try:
			return value if isinstance(value, UiModePref) else UiModePref(value)
		except ValueError:
			pass
	return _coerceEnum(enumCls, value)


def setUiModePref(name, value):
	_uiModeSection(name)[UiModeSetting.MODE] = str(value)


def resolveUiMode(name):
	name = _uiModeName(name)
	enumCls = UI_MODES[name]
	section = _uiModeSection(name)
	pref = section[UiModeSetting.MODE]
	if _remembersLastUsed(name) and pref == UiModePref.LAST_USED:
		return _coerceEnum(enumCls, section[UiModeSetting.LAST_USED])
	return _coerceEnum(enumCls, pref)


def setUiModeLastUsed(name, value):
	name = _uiModeName(name)
	if not _remembersLastUsed(name):
		return
	enumCls = UI_MODES[name]
	value = value if isinstance(value, enumCls) else enumCls(value)
	section = _uiModeSection(name)
	if section[UiModeSetting.LAST_USED] != value:
		section[UiModeSetting.LAST_USED] = str(value)


def getUiMode(name, canPrefer=True):
	"""Return the concrete UI mode to use for `name`.

	When `canPrefer` is False (the simpler mode is not available), the fallback
	member is returned. Last-used is recorded only for surfaces that persist it
	(the inspector).
	"""
	name = _uiModeName(name)
	if not canPrefer:
		return _last(UI_MODES[name])
	value = resolveUiMode(name)
	if _remembersLastUsed(name):
		setUiModeLastUsed(name, value)
	return value


def handleConfigChange():
	global _cache
	if _cache is not None:
		if (
			config.conf["webAccess"]["disableUserConfig"]
			!= _cache.get("webAccess", {}).get("disableUserConfig")
		) or (
			config.conf["development"]["enableScratchpadDir"]
			!= _cache.get("development", {}).get("enableScratchpadDir")
		):
			webModuleHandler.terminate()
			webModuleHandler.initialize()
			webModuleHandler.getWebModules(refresh=True)
			webModuleHandler.resetRunningModules()
	_cache = {"webAccess" : config.conf["webAccess"].dict()}
	_cache["development"] = config.conf["development"].dict()


def initialize():
	key = "webAccess"
	config.conf.spec[key] = CONFIG_SPEC
	# ConfigObj mutates this into a configobj.Section.
	spec = config.conf.spec[key]
	# Disallow profiles from overriding the base configuration
	config.ConfigManager.BASE_ONLY_SECTIONS.add(key)
	# BASE_ONLY_SECTIONS are returned directly from the base config and need to be validated.
	# See NVDA's config.ConfigManager._initBaseConf
	baseProfile = config.conf.profiles[0]
	try:
		section = baseProfile[key]
	except KeyError:
		baseProfile[key] = {}
		# ConfigObj mutates this into a configobj.Section.
		section = baseProfile[key]
	section.configspec = spec
	# copy=True applies nested spec defaults (e.g. uiModes) on first run.
	baseProfile.validate(config.conf.validator, copy=True, section=section)
	# Initialize cache for later comparison
	handleConfigChange()
	config.post_configReset.register(handleConfigChange)


def terminate():
	config.ConfigManager.BASE_ONLY_SECTIONS.remove("webAccess")
	config.post_configReset.unregister(handleConfigChange)
