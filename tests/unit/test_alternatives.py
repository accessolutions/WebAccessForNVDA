# tests/unit/test_alternatives.py
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

"""Tests for `ruleHandler.alternatives`."""


from dataclasses import dataclass
import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.ruleHandler import ruleTypes
from webAccess.ruleHandler.alternatives import AlternativesMode, mergeResults
from webAccess.ruleHandler.properties import normalizeRuleData


@dataclass(eq=False)
class Node:
	offset: int


@dataclass(eq=False)
class SingleResult:
	alternative: int
	node: Node
	
	@property
	def startOffset(self):
		return self.node.offset


@dataclass(eq=False)
class DualResult(SingleResult):
	endNode: Node


class TestMergeResults(unittest.TestCase):
	
	def test_sortedByPosition(self):
		n1, n2, n3 = Node(10), Node(20), Node(30)
		merged = mergeResults([
			SingleResult(0, n3),
			SingleResult(1, n1),
			SingleResult(2, n2),
		])
		self.assertEqual([r.node for r in merged], [n1, n2, n3])
	
	def test_firstAlternativeWinsOnSameNode(self):
		n1, n2 = Node(10), Node(20)
		merged = mergeResults([
			SingleResult(0, n2),
			SingleResult(1, n1),
			SingleResult(1, n2),
		])
		self.assertEqual([(r.alternative, r.node) for r in merged], [(1, n1), (0, n2)])
	
	def test_samePositionKeepsAlternativeOrder(self):
		# Distinct nodes at the same offset (eg. nested elements)
		outer, inner = Node(10), Node(10)
		merged = mergeResults([SingleResult(0, inner), SingleResult(1, outer)])
		self.assertEqual([r.alternative for r in merged], [0, 1])
	
	def test_freeZonesIdentifiedByBothNodes(self):
		start, end1, end2 = Node(10), Node(20), Node(30)
		merged = mergeResults([
			DualResult(0, start, end1),
			DualResult(1, start, end2),
			DualResult(1, start, end1),
		])
		self.assertEqual([(r.alternative, r.endNode) for r in merged], [(0, end1), (1, end2)])
	
	def test_empty(self):
		self.assertEqual(mergeResults([]), [])


class TestAlternativesMode(unittest.TestCase):
	
	def test_serializedValues(self):
		self.assertEqual(AlternativesMode("first"), AlternativesMode.FIRST)
		self.assertEqual(AlternativesMode("all"), AlternativesMode.ALL)
	
	def test_displayStrings(self):
		for mode in AlternativesMode:
			self.assertTrue(mode.displayString)
	
	def test_normalizeDropsDefault(self):
		data = {"name": "R", "type": ruleTypes.MARKER, "criteria": [{}], "alternativesMode": "first"}
		normalizeRuleData(data)
		self.assertNotIn("alternativesMode", data)
	
	def test_normalizeKeepsAll(self):
		data = {"name": "R", "type": ruleTypes.MARKER, "criteria": [{}], "alternativesMode": "all"}
		normalizeRuleData(data)
		self.assertEqual(data["alternativesMode"], "all")


if __name__ == "__main__":
	unittest.main()
