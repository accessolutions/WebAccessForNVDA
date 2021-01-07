# globalPlugins/webAccess/config.py
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

# Stay compatible with Python 2
from __future__ import absolute_import, division, print_function

__version__ = "2021.01.07"
__author__ = u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import config
from logHandler import log

from .nvdaVersion import nvdaVersion
from . import webModuleHandler


CONFIG_SPEC = {
	"devMode": "boolean(default=False)",
	"disableUserConfig": "boolean(default=False)",
	"writeInAddons": "boolean(default=False)",
}


_cache = None


def handleConfigChange():
	global _cache
	if _cache is not None:
		if (
			config.conf["webAccess"]["disableUserConfig"]
			!= _cache.get("webAccess", {}).get("disableUserConfig")
		) or (
			nvdaVersion >= (2019, 1)
			and config.conf["development"]["enableScratchpadDir"]
			!= _cache.get("development", {}).get("enableScratchpadDir")
		):
			webModuleHandler.terminate()
			webModuleHandler.initialize()
			webModuleHandler.getWebModules(refresh=True)
			webModuleHandler.resetRunningModules()
	if nvdaVersion >= (2018, 4):
		_cache = {"webAccess" : config.conf["webAccess"].dict()}
		if nvdaVersion >= (2019, 1):
			_cache["development"] = config.conf["development"].dict()
	else:
		_cache = {"webAccess": dict(config.conf["webAccess"].iteritems())}


def initialize():
	config.conf.spec["webAccess"] = CONFIG_SPEC
	# Disallow profiles from overriding the base configuration
	config.ConfigManager.BASE_ONLY_SECTIONS.add("webAccess")
	# Validate the section (required only as its been added to BASE_ONLY_SECTIONS)
	# See NVDA's config.ConfigManager._initBaseConf
	config.conf.profiles[0]["webAccess"].configspec = config.conf.spec["webAccess"]
	config.conf.profiles[0].validate(config.conf.validator, section=config.conf.profiles[0]["webAccess"])
	# Initialize cache for later comparison
	handleConfigChange()
	if nvdaVersion >= (2018, 3):
		# No need anymore to register on post_configProfileSwitch
		config.post_configReset.register(handleConfigChange)

def terminate():
	config.ConfigManager.BASE_ONLY_SECTIONS.remove("webAccess")
	if nvdaVersion >= (2018, 3):
		config.post_configProfileSwitch.unregister(handleConfigChange)
		config.post_configReset.unregister(handleConfigChange)
		config.post_configSave.unregister(handleConfigChange)
