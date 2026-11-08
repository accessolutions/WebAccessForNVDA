# globalPlugins/webAccess/ruleHandler/searchMode.py
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

"""How the criteria of a selector are matched against the nodes of the document.

This module does not depend on NVDA (apart from translations), so that it can be
unit tested.
"""


from enum import StrEnum
from typing import Any

import addonHandler

from collections.abc import Mapping


addonHandler.initTranslation()


class SearchMode(StrEnum):
	"""Serialized in selector data as `"mode"`, omitted when `SIMPLE`."""

	SIMPLE = "simple"
	"""Each criterion can be satisfied by the matched element or by any of its ancestors
	(historical behavior)."""

	SAME_NODE = "sameNode"
	"""All the criteria must be satisfied by the matched element itself."""

	CSS = "css"
	"""The structure is described by a CSS selector (`"css"`), the other criteria being
	satisfied by the matched element itself."""

	@property
	def displayString(self) -> str:
		return SEARCH_MODE_LABELS[self]


SEARCH_MODE_LABELS = {
	# Translators: A search mode of the criteria of a rule
	SearchMode.SIMPLE: pgettext(
		"webAccess.searchMode",
		"Simple: each criterion can apply to the element or to one of its parents",
	),
	# Translators: A search mode of the criteria of a rule
	SearchMode.SAME_NODE: pgettext(
		"webAccess.searchMode",
		"Same element: all the criteria apply to the found element",
	),
	# Translators: A search mode of the criteria of a rule
	SearchMode.CSS: pgettext("webAccess.searchMode", "CSS selector"),
}


CSS_REPLACED_FIELDS = ("tag", "id", "className", "src")
"""Selector fields replaced by the CSS selector in `SearchMode.CSS`."""


def getSearchMode(selectorData: Mapping[str, Any]) -> SearchMode:
	return SearchMode(selectorData.get("mode") or SearchMode.SIMPLE.value)


def normalizeSelectorData(selectorData: dict[str, Any]) -> None:
	"""Normalize, in place, the search mode related fields of serialized selector data.

	 - The default mode (`SearchMode.SIMPLE`) is omitted.
	 - The CSS selector is kept only in `SearchMode.CSS`, where it replaces the
	   `CSS_REPLACED_FIELDS`.
	"""
	mode = getSearchMode(selectorData)
	if mode is SearchMode.SIMPLE:
		selectorData.pop("mode", None)
	else:
		selectorData["mode"] = mode.value
	if mode is SearchMode.CSS:
		for key in CSS_REPLACED_FIELDS:
			selectorData.pop(key, None)
		css = (selectorData.get("css") or "").strip()
		if css:
			selectorData["css"] = css
		else:
			selectorData.pop("css", None)
	else:
		selectorData.pop("css", None)
