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

import wx

import addonHandler
import gui
from logHandler import log


if sys.version_info[1] < 9:
    from typing import Mapping
else:
    from collections.abc import Mapping


addonHandler.initTranslation()


def createMissingSubModule(
		context: Mapping[str, Any],
		data: Mapping[str, Any],
		parent: wx.Window
	) -> bool:
	"""Create the missing SubModule from Rule or Criteria data
	
	If a SubModule is specified in the provided data, it is looked-up in the catalog.
	If it is missing from the catalog, the user is prompted for creating it.
	
	This function returns:
	 - `None` if no creation was necessary or if the user declined the prompt.
	 - `False` if the user canceled the prompt or if the creation failed or has been canceled.
	 - `True` if the creation succeeded.
	"""
	name = data.get("properties", {}).get("subModule")
	if not name:
		return None
	from ...webModuleHandler import getCatalog
	if any(meta["name"] == name for ref, meta in getCatalog()):
		return True
	res = gui.messageBox(
		message=(
			# Translators: A prompt for creation of a missing SubModule
			_(f"""SubModule {name} could not be found.

Do you want to create it now?""")
		),
		style=wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
		parent=parent,
	)
	if res is wx.NO:
		return None
	elif res is wx.CANCEL:
		return False
	context = context.copy()
	context["new"] = True
	context["data"] = {"webModule": {"name": name, "subModule": True}}
	from ..webModule.editor import show
	res = show(context, parent)
	if res:
		newName = context["webModule"].name
		if newName != name:
			data["properties"]["subModule"] = newName
	return res
