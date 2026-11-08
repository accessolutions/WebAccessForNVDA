# globalPlugins/webAccess/nodeMatching.py
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

"""Matching search criteria against a single node.

The search criteria are those built by `ruleHandler.getSimpleSearchKwargs`, named
`test_property[#index]`, eg. `eq_tag`, `notIn_className#1` or `in_text`.

In the historical ("simple") search mode, implemented by `NodeField.searchNode`,
each criterion can be satisfied by the matched node or by any of its ancestors.
This module implements the "same node" evaluation, where all the criteria must be
satisfied by the matched node itself. It relies on duck typing and does not depend
on NVDA, so that it can be unit tested.
"""


from typing import Any, Callable

from collections.abc import Iterable, Mapping


def iterCandidateValues(node: Any, prop: str) -> Iterable[Any]:
	"""The values of a node property to test, eg. each class of `className`."""
	value = getattr(node, prop)
	if prop == "className":
		if value is not None:
			value = value.strip()
			if value:
				return value.split()
		return (value,)
	if prop == "states":
		# A set of states
		return value
	return (value,)


def testValue(test: str, candidate: Any, searchedValues: Iterable[Any]) -> bool:
	"""Whether a candidate value is a hit for the given test.

	For negative tests (`notEq`, `notIn`), a hit means the node is excluded.
	"""
	if test in ("eq", "notEq"):
		return candidate in searchedValues
	if test in ("in", "notIn"):
		return bool(candidate) and any(searched in candidate for searched in searchedValues)
	raise ValueError(f"Unexpected test: {test!r}")


def literalHolds(node: Any, prop: str, test: str, value: Any) -> bool:
	"""Whether a single literal of an `any_` clause holds for the node itself.

	A positive literal (`eq`, `in`) holds if any candidate value matches. A negative
	literal (`notEq`, `notIn`) holds if none does, including if the node lacks the property.
	"""
	negative = test in ("notEq", "notIn")
	if not hasattr(node, prop):
		return negative
	hit = any(testValue(test, candidate, (value,)) for candidate in iterCandidateValues(node, prop))
	return not hit if negative else hit


def clauseHolds(node: Any, prop: str, literals: Iterable[tuple[str, Any]]) -> bool:
	"""Whether an `any_` clause (a disjunction of `(test, value)` literals) holds for the node."""
	return any(literalHolds(node, prop, test, value) for test, value in literals)


def matchesOnSameNode(
	node: Any,
	criteria: Mapping[str, Any],
	containsText: Callable[[Any, Any], bool],
) -> bool:
	"""Whether all the given criteria are satisfied by the node itself.

	`containsText(node, text)` tells whether the text content of the node contains the
	given text (or any of the given texts, for a list). The `prevText` criterion is
	tested against the text node preceding the node (`node.previousTextNode`).
	"""
	for key, searchedValues in criteria.items():
		test, prop = key.split("_", 1)
		prop = prop.rsplit("#", 1)[0]
		if prop == "text":
			if not containsText(node, searchedValues):
				return False
			continue
		if prop == "prevText":
			previous = getattr(node, "previousTextNode", None)
			if previous is None or searchedValues not in previous.text:
				return False
			continue
		if test == "any":
			if not clauseHolds(node, prop, searchedValues):
				return False
			continue
		if not hasattr(node, prop):
			if test in ("eq", "in"):
				return False
			continue
		hit = any(
			testValue(test, candidate, searchedValues)
			for candidate in iterCandidateValues(node, prop)
		)
		if test in ("eq", "in") and not hit:
			return False
		if test in ("notEq", "notIn") and hit:
			return False
	return True
