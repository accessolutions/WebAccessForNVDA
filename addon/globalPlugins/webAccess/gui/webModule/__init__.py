# globalPlugins/webAccess/gui/rule/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (http://accessolutions.fr)
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


import sys
from typing import Any

import os
import wx

import addonHandler
import config
import gui

from ...webModuleHandler import WebModule


if sys.version_info[1] < 9:
    from typing import Mapping
else:
    from collections.abc import Mapping


addonHandler.initTranslation()


def promptDelete(webModule: WebModule):
	msg = (
		# Translators: Prompt before deleting a web module.
		_("Do you really want to delete this web module?")
		+ os.linesep
		+ str(webModule.name)
	)
	if config.conf["webAccess"]["devMode"]:
		msg += " ({})".format("/".join((layer.name for layer in webModule.layers)))
	return gui.messageBox(
		parent=gui.mainFrame,
		message=msg,
		style=wx.YES_NO | wx.CANCEL | wx.NO_DEFAULT | wx.ICON_WARNING
	) == wx.YES


def promptMask(webModule: WebModule):
	ref = webModule.getLayer("addon", raiseIfMissing=True).storeRef
	if ref[0] != "addons":
		raise ValueError("ref={!r}".format(ref))
	addonName = ref[1]
	for addon in addonHandler.getRunningAddons():
		if addon.name == addonName:
			addonSummary = addon.manifest["summary"]
			break
	else:
		raise LookupError("addonName={!r}".format(addonName))
	log.info("Proposing to mask {!r} from addon {!r}".format(webModule, addonName))
	msg = _(
		"""This web module comes with the add-on {addonSummary}.
It cannot be modified at its current location.

Do you want to make a copy in your scratchpad?
"""
	).format(addonSummary=addonSummary)
	return gui.messageBox(
		parent=gui.mainFrame,
		message=msg,
		caption=_("Warning"),
		style=wx.ICON_WARNING | wx.YES | wx.NO
	) == wx.YES
