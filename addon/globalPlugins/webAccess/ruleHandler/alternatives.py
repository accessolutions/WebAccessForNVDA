# globalPlugins/webAccess/ruleHandler/alternatives.py
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

"""How the alternatives (Criteria) of a Rule are combined.

This module does not depend on NVDA, so that it can be unit tested.
"""


from enum import StrEnum
from typing import Protocol, TypeVar

import addonHandler

from collections.abc import Iterable


addonHandler.initTranslation()


class AlternativesMode(StrEnum):
	"""Determines which alternatives (Criteria) of a Rule produce Results.

	Serialized at Rule level as `"alternativesMode"`, omitted when `FIRST`.
	"""

	FIRST = "first"
	"""Only the first alternative yielding Results is considered (historical behavior)."""

	ALL = "all"
	"""Every alternative is considered.

	A node matched by several alternatives yields a single Result, from the
	first of them. The Results are sorted by position in the document.
	"""

	@property
	def displayString(self) -> str:
		return ALTERNATIVES_MODE_LABELS[self]


ALTERNATIVES_MODE_LABELS = {
	# Translators: A choice for the "When several alternatives match" option of a Rule
	AlternativesMode.FIRST: pgettext("webAccess.alternativesMode", "Use only the first matching alternative"),
	# Translators: A choice for the "When several alternatives match" option of a Rule
	AlternativesMode.ALL: pgettext("webAccess.alternativesMode", "Use all matching alternatives"),
}


class _ResultLike(Protocol):

	node: object
	startOffset: int


R = TypeVar("R", bound=_ResultLike)


def getResultKey(result: _ResultLike) -> tuple[object, object]:
	"""The identity of what a Result matched: Its node, and its end node for a free zone."""
	return (result.node, getattr(result, "endNode", None))


def mergeResults(results: Iterable[R]) -> list[R]:
	"""Merge the Results of several alternatives, as per `AlternativesMode.ALL`.

	`results` must be ordered by alternative.
	A node matched by several alternatives is kept only from the first of them,
	so that its properties and gestures apply.
	The returned Results are sorted by position in the document, the order of the
	alternatives being preserved for Results starting at the same position.
	"""
	seen = set()
	merged = []
	for result in results:
		key = getResultKey(result)
		if key in seen:
			continue
		seen.add(key)
		merged.append(result)
	merged.sort(key=lambda result: result.startOffset)
	return merged
