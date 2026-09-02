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


import config
from logHandler import log

from . import webModuleHandler


CONFIG_SPEC = {
	"devMode": "boolean(default=False)",
	"disableUserConfig": "boolean(default=False)",
	"writeInAddons": "boolean(default=False)",
	"ruleWizardMode": "option('default', 'lastUsed', 'wizard', 'editor', default='default')",
	"ruleWizardLastUsed": "option('wizard', 'editor', default='wizard')",
	"ruleEditorMode": "option('default', 'lastUsed', 'simple', 'full', default='default')",
	"ruleEditorLastUsed": "option('simple', 'full', default='simple')",
	"criteriaEditorMode": "option('default', 'lastUsed', 'simple', 'full', default='default')",
	"criteriaEditorLastUsed": "option('simple', 'full', default='simple')",
	"inspectorMode": "option('default', 'lastUsed', 'single', 'ancestors', default='default')",
	"inspectorLastUsed": "option('single', 'ancestors', default='single')",
}


_UI_MODES = {
	"ruleWizard": {
		"pref": "ruleWizardMode",
		"lastUsed": "ruleWizardLastUsed",
		"values": ("wizard", "editor"),
	},
	"ruleEditor": {
		"pref": "ruleEditorMode",
		"lastUsed": "ruleEditorLastUsed",
		"values": ("simple", "full"),
	},
	"criteriaEditor": {
		"pref": "criteriaEditorMode",
		"lastUsed": "criteriaEditorLastUsed",
		"values": ("simple", "full"),
	},
	"inspector": {
		"pref": "inspectorMode",
		"lastUsed": "inspectorLastUsed",
		"values": ("single", "ancestors"),
	},
}


_cache = None


def resolveUiMode(name, defaultValue):
	spec = _UI_MODES[name]
	section = config.conf["webAccess"]
	pref = section[spec["pref"]]
	valid = spec["values"]
	if pref == "lastUsed":
		value = section[spec["lastUsed"]]
	elif pref == "default":
		value = defaultValue
	else:
		value = pref
	if value not in valid:
		value = defaultValue
	return value


def setUiModeLastUsed(name, value):
	spec = _UI_MODES[name]
	if value not in spec["values"]:
		raise ValueError("Invalid last-used value %r for %s" % (value, name))
	key = spec["lastUsed"]
	if config.conf["webAccess"][key] != value:
		config.conf["webAccess"][key] = value


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
	baseProfile.validate(config.conf.validator, section=section)
	# Initialize cache for later comparison
	handleConfigChange()
	config.post_configReset.register(handleConfigChange)


def terminate():
	config.ConfigManager.BASE_ONLY_SECTIONS.remove("webAccess")
	config.post_configReset.unregister(handleConfigChange)
