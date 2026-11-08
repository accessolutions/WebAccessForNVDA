# tests/unit/test_searchMode.py
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

"""Tests for `ruleHandler.searchMode`."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.ruleHandler import ruleTypes
from webAccess.ruleHandler.properties import normalizeRuleData
from webAccess.ruleHandler.searchMode import SearchMode, getSearchMode, normalizeSelectorData


class TestNormalizeSelector(unittest.TestCase):
	
	def test_simpleIsDefault(self):
		data = {"tag": "li", "mode": "simple", "css": "li"}
		normalizeSelectorData(data)
		self.assertEqual(data, {"tag": "li"})
		self.assertIs(getSearchMode(data), SearchMode.SIMPLE)
	
	def test_sameNodeKeepsFields(self):
		data = {"tag": "li", "className": "toto", "mode": "sameNode", "css": "x"}
		normalizeSelectorData(data)
		self.assertEqual(data, {"tag": "li", "className": "toto", "mode": "sameNode"})
	
	def test_cssReplacesFields(self):
		data = {
			"tag": "li", "id": "x", "className": "toto", "src": "a.png",
			"text": "Contact", "role": 1, "mode": "css", "css": "  ul > li.toto ",
		}
		normalizeSelectorData(data)
		self.assertEqual(data, {"text": "Contact", "role": 1, "mode": "css", "css": "ul > li.toto"})
	
	def test_emptyCssDropped(self):
		data = {"mode": "css", "css": " "}
		normalizeSelectorData(data)
		self.assertEqual(data, {"mode": "css"})
	
	def test_labels(self):
		for mode in SearchMode:
			self.assertTrue(mode.displayString)


class TestNormalizeRuleData(unittest.TestCase):
	
	def test_allSelectors(self):
		data = {
			"name": "R",
			"type": ruleTypes.ZONE,
			"criteria": [
				{"selector": {"tag": "li", "mode": "simple"}},
				{"selector": {
					"start": {"tag": "h2", "mode": "css", "css": "h2.title"},
					"end": {"tag": "h2", "mode": "sameNode", "css": "h2"},
				}},
			],
		}
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["selector"], {"tag": "li"})
		self.assertEqual(data["criteria"][1]["selector"]["start"], {"mode": "css", "css": "h2.title"})
		self.assertEqual(data["criteria"][1]["selector"]["end"], {"tag": "h2", "mode": "sameNode"})


if __name__ == "__main__":
	unittest.main()
