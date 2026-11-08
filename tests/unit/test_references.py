# tests/unit/test_references.py
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

"""Tests for `ruleHandler.references`."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.ruleHandler.references import (
	ContextTerm,
	Reference,
	buildDependencyGraph,
	findCaseInsensitiveHomonyms,
	findCyclePath,
	findCycles,
	findDanglingReferences,
	formatContextExpression,
	getDependents,
	getRuleNameError,
	iterContextNames,
	iterReferences,
	parseContextExpression,
	renameInContextExpression,
	renameReferences,
)


def rule(*selectors):
	"""Serialized rule data with one alternative per selector."""
	return {"name": "R", "type": "marker", "criteria": [{"selector": s} for s in selectors]}


class TestParse(unittest.TestCase):

	def test_empty(self):
		self.assertEqual(parseContextExpression(None), ())
		self.assertEqual(parseContextExpression(""), ())
		self.assertEqual(parseContextExpression(" & | & "), ())

	def test_terms(self):
		self.assertEqual(
			parseContextExpression("A | B & !C"),
			(ContextTerm(("A", "B")), ContextTerm(("C",), negated=True)),
		)

	def test_spaces(self):
		self.assertEqual(
			parseContextExpression("  A|B  &  ! C | D "),
			(ContextTerm(("A", "B")), ContextTerm(("C", "D"), negated=True)),
		)

	def test_namesWithSpaces(self):
		self.assertEqual(parseContextExpression("Main menu"), (ContextTerm(("Main menu",)),))

	def test_format(self):
		self.assertEqual(formatContextExpression(parseContextExpression("A|B&!C")), "A | B & !C")

	def test_roundTrip(self):
		for expr in ("A", "A | B", "!A", "A & !B | C"):
			self.assertEqual(formatContextExpression(parseContextExpression(expr)), expr)

	def test_iterNames(self):
		self.assertEqual(list(iterContextNames("A | B & !C & A")), ["A", "B", "C", "A"])


class TestRenameInExpression(unittest.TestCase):

	def test_wholeTokensOnly(self):
		self.assertEqual(
			renameInContextExpression("Menu | Main menu & !SubMenu", "Menu", "Nav"),
			"Nav | Main menu & !SubMenu",
		)

	def test_unchangedKeepsFormatting(self):
		self.assertEqual(renameInContextExpression("A|B", "C", "D"), "A|B")
		self.assertIsNone(renameInContextExpression(None, "C", "D"))

	def test_negated(self):
		self.assertEqual(renameInContextExpression("!A", "A", "B"), "!B")


class TestReferences(unittest.TestCase):

	def test_iterReferences(self):
		data = rule(
			{"contextParent": "P", "contextPageType": "T1 | T2"},
			{"start": {"contextParent": "S"}, "end": {"contextPageType": "!E"}},
		)
		self.assertEqual(list(iterReferences(data)), [
			Reference(0, None, "contextPageType", "T1"),
			Reference(0, None, "contextPageType", "T2"),
			Reference(0, None, "contextParent", "P"),
			Reference(1, "start", "contextParent", "S"),
			Reference(1, "end", "contextPageType", "E"),
		])

	def test_contextPageTitleIsNotAReference(self):
		self.assertEqual(list(iterReferences(rule({"contextPageTitle": "A"}))), [])

	def test_renameReferences(self):
		data = rule(
			{"contextParent": "A | B"},
			{"start": {"contextParent": "A"}, "end": {"contextPageType": "!A"}},
		)
		self.assertTrue(renameReferences(data, "A", "Z"))
		self.assertEqual(data["criteria"][0]["selector"]["contextParent"], "Z | B")
		self.assertEqual(data["criteria"][1]["selector"]["start"]["contextParent"], "Z")
		self.assertEqual(data["criteria"][1]["selector"]["end"]["contextPageType"], "!Z")
		self.assertFalse(renameReferences(data, "A", "Z"))

	def test_graphAndDependents(self):
		rules = {
			"A": rule({"contextParent": "B"}),
			"B": rule({"contextPageType": "T"}),
			"C": rule({"contextParent": "B"}, {"contextParent": "!B"}),
			"T": rule({}),
		}
		self.assertEqual(buildDependencyGraph(rules), {"A": {"B"}, "B": {"T"}, "C": {"B"}, "T": set()})
		dependents = getDependents(rules, "B")
		self.assertEqual(sorted(dependents), ["A", "C"])
		self.assertEqual(len(dependents["C"]), 2)
		self.assertEqual(getDependents(rules, "A"), {})

	def test_dangling(self):
		rules = {"A": rule({"contextParent": "B | X"}), "B": rule({})}
		dangling = findDanglingReferences(rules, rules)
		self.assertEqual(list(dangling), ["A"])
		self.assertEqual([ref.name for ref in dangling["A"]], ["X"])

	def test_danglingWithOtherLayers(self):
		rules = {"A": rule({"contextParent": "Base"})}
		self.assertEqual(findDanglingReferences(rules, {"A", "Base"}), {})


class TestCycles(unittest.TestCase):

	def test_none(self):
		self.assertEqual(findCycles({"A": {"B"}, "B": {"C"}, "C": set()}), [])

	def test_diamondIsNotACycle(self):
		self.assertEqual(findCycles({"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": set()}), [])

	def test_selfReference(self):
		self.assertEqual(findCycles({"A": {"A"}, "B": set()}), [["A"]])

	def test_twoAndThree(self):
		graph = {"A": {"B"}, "B": {"A"}, "C": {"D"}, "D": {"E"}, "E": {"C"}, "F": {"A"}}
		self.assertEqual(findCycles(graph), [["A", "B"], ["C", "D", "E"]])

	def test_missingTargets(self):
		self.assertEqual(findCycles({"A": {"Missing"}}), [])

	def test_deepGraphDoesNotRecurse(self):
		graph = {f"R{i}": {f"R{i + 1}"} for i in range(5000)}
		graph["R5000"] = {"R0"}
		self.assertEqual(len(findCycles(graph)), 1)

	def test_cyclePath(self):
		graph = {"A": {"B"}, "B": {"C"}, "C": {"A"}, "D": {"A"}}
		self.assertEqual(findCyclePath(graph, "A"), ["A", "B", "C", "A"])
		self.assertIsNone(findCyclePath(graph, "D"))
		self.assertEqual(findCyclePath({"A": {"A"}}, "A"), ["A", "A"])

	def test_cyclePathShortest(self):
		graph = {"A": {"B", "C"}, "B": {"D"}, "D": {"A"}, "C": {"A"}}
		self.assertEqual(findCyclePath(graph, "A"), ["A", "C", "A"])


class TestNames(unittest.TestCase):

	def test_valid(self):
		for name in ("Menu", "Main menu", "Price (€)", "A!", "Q&A?".replace("&", "and")):
			self.assertIsNone(getRuleNameError(name), name)

	def test_invalid(self):
		for name in ("", " ", " Menu", "Menu ", "A & B", "A|B", "!A"):
			self.assertIsNotNone(getRuleNameError(name), name)

	def test_caseInsensitiveHomonyms(self):
		self.assertEqual(findCaseInsensitiveHomonyms("Menu", ["menu", "MENU", "Menu", "Other"]), ["MENU", "menu"])
		self.assertEqual(findCaseInsensitiveHomonyms("Menu", ["Menu"]), [])


if __name__ == "__main__":
	unittest.main()
