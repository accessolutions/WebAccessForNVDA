# tests/unit/test_migration_0_6.py
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

"""Tests for the conversion of WebModules from format 0.6 (same-name rules) to alternatives."""


import importlib.util
import os
import unittest

from . import ADDON_PACKAGE_DIR


def loadConverter():
	# Standalone module (also runnable as a script): Loaded by path to avoid importing
	# the `dataRecovery` package, which depends on NVDA.
	path = os.path.join(ADDON_PACKAGE_DIR, "webModuleHandler", "dataRecovery", "from_0_6_to_0_9.py")
	spec = importlib.util.spec_from_file_location("from_0_6_to_0_9", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class TestConvertAlternatives(unittest.TestCase):
	
	@classmethod
	def setUpClass(cls):
		cls.converter = loadConverter()
	
	def convert(self, rules):
		data = {"formatVersion": "0.6", "WebModule": {"name": "Test"}, "Rules": rules}
		self.converter.convert(data)
		self.assertEqual(data["formatVersion"], "0.9-dev")
		return data["Rules"]
	
	def test_cancellingAlternativeKept(self):
		rules = self.convert([
			{"name": "R", "type": "marker", "text": "a", "autoAction": "moveto", "customName": "Foo"},
			{"name": "R", "type": "marker", "text": "b", "autoAction": "moveto", "customName": "Foo"},
			{"name": "R", "type": "marker", "text": "c"},
		])
		rule = rules["R"]
		self.assertEqual(rule["properties"]["autoAction"], "moveto")
		self.assertEqual(rule["properties"]["customName"], "Foo")
		self.assertEqual(len(rule["criteria"]), 3)
		overrides = [crit.get("properties", {}) for crit in rule["criteria"]]
		# Exactly one alternative cancels the popular values
		cancelling = [props for props in overrides if props]
		self.assertEqual(len(cancelling), 1)
		self.assertIsNone(cancelling[0]["autoAction"])
		self.assertEqual(cancelling[0]["customName"], "")
	
	def test_ruleLevelDefaultsDropped(self):
		rules = self.convert([
			{"name": "R", "type": "marker", "text": "a"},
			{"name": "R", "type": "marker", "text": "b"},
		])
		rule = rules["R"]
		self.assertNotIn("autoAction", rule.get("properties", {}))
		self.assertNotIn("customName", rule.get("properties", {}))
		for crit in rule["criteria"]:
			self.assertNotIn("autoAction", crit.get("properties", {}))
			self.assertNotIn("customName", crit.get("properties", {}))


class TestConvertHomonymsOfDifferentTypes(unittest.TestCase):
	
	def test_keyAndNameConsistent(self):
		data = {
			"formatVersion": "0.6",
			"WebModule": {"name": "Test"},
			"Rules": [
				{"name": "Home", "type": "pageType", "text": "a"},
				{"name": "Home", "type": "marker", "text": "b"},
			],
		}
		loadConverter().convert(data)
		rules = data["Rules"]
		self.assertEqual(sorted(rules), ["Home", "Home (*marker)"])
		for key, rule in rules.items():
			self.assertEqual(rule["name"], key)


if __name__ == "__main__":
	unittest.main()
