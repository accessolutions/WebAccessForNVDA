# globalPlugins/webAccess/config.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2020 Accessolutions (http://accessolutions.fr)
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

__version__ = "2020.12.18"
__author__ = u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import config
from logHandler import log

from .nvdaVersion import nvdaVersion


CONFIG_SPEC = {
	"devMode": "boolean(default=False)",
	"disableUserConfig": "boolean(default=False)",
	"writeInAddons": "boolean(default=False)",
}


def handlePostConfigProfileSwitch():
	pass  # TODO


def handlePostConfigReset():
	pass  # TODO


def handlePostConfigSave():
	pass  # TODO


def initialize():
	config.conf.spec["webAccess"] = CONFIG_SPEC
	if nvdaVersion >= (2018, 3):
		config.post_configProfileSwitch.register(handlePostConfigProfileSwitch)
		config.post_configReset.register(handlePostConfigReset)
		config.post_configSave.register(handlePostConfigSave)
	from .gui.settings import initialize as settings_initialize
	settings_initialize()

def terminate():
	if nvdaVersion >= (2018, 3):
		config.post_configProfileSwitch.unregister(handlePostConfigProfileSwitch)
		config.post_configReset.unregister(handlePostConfigReset)
		config.post_configSave.unregister(handlePostConfigSave)
	from .gui.settings import terminate as settings_terminate
	settings_terminate()
