# tests/unit/test_normalizeRuleData.py
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

"""Tests for `ruleHandler.properties.normalizeRuleData`, used when saving a Rule."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.ruleHandler import ruleTypes
from webAccess.ruleHandler.properties import normalizeRuleData

from .test_ruleProperties import makeRuleAndCriteria


def makeData(ruleType=ruleTypes.MARKER, ruleProps=None, *critProps, **extra):
	data = {
		"name": "R",
		"type": ruleType,
		"criteria": [
			{"selector": {"tag": "div"}, **({"properties": props} if props is not None else {})}
			for props in (critProps or (None,))
		],
		**extra,
	}
	if ruleProps is not None:
		data["properties"] = ruleProps
	return data


class TestFalsyOverridesAreKept(unittest.TestCase):
	"""Regression tests: Overrides cancelling a Rule level value used to be dropped on save."""
	
	RULE_PROPS = {
		"autoAction": "moveto",
		"multiple": True,
		"formMode": True,
		"skip": True,
		"sayName": True,
		"customName": "Foo",
		"customValue": "Bar",
		"mutation": "heading.2",
		"profile": "someProfile",
	}
	CANCELLING_OVERRIDES = {
		"autoAction": None,
		"multiple": False,
		"formMode": False,
		"skip": False,
		"sayName": False,
		"customName": "",
		"customValue": "",
		"mutation": None,
		"profile": None,
	}
	
	def test_markerOverridesKept(self):
		data = makeData(ruleTypes.MARKER, dict(self.RULE_PROPS), dict(self.CANCELLING_OVERRIDES))
		normalizeRuleData(data)
		self.assertEqual(data["properties"], self.RULE_PROPS)
		self.assertEqual(data["criteria"][0]["properties"], self.CANCELLING_OVERRIDES)
	
	def test_subModuleOverrideKept(self):
		data = makeData(ruleTypes.ZONE, {"subModule": "Foo"}, {"subModule": ""})
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["properties"], {"subModule": ""})
	
	def test_effectiveValuesAfterReload(self):
		data = makeData(ruleTypes.MARKER, dict(self.RULE_PROPS), dict(self.CANCELLING_OVERRIDES))
		normalizeRuleData(data)
		rule, crit = makeRuleAndCriteria(
			ruleTypes.MARKER, data["properties"], data["criteria"][0]["properties"]
		)
		for name, value in self.CANCELLING_OVERRIDES.items():
			self.assertEqual(getattr(crit, name), value, name)
	
	def test_otherAlternativesStillInherit(self):
		data = makeData(ruleTypes.MARKER, {"autoAction": "moveto"}, {"autoAction": None}, None)
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["properties"], {"autoAction": None})
		self.assertNotIn("properties", data["criteria"][1])


class TestRedundantValuesAreDropped(unittest.TestCase):
	
	def test_ruleDefaultsDropped(self):
		data = makeData(ruleTypes.MARKER, {"autoAction": None, "sayName": False, "customName": ""})
		normalizeRuleData(data)
		self.assertNotIn("properties", data)
	
	def test_overrideEqualToRuleKept(self):
		# An explicit override keeps applying when the Rule level value changes
		data = makeData(ruleTypes.MARKER, {"sayName": True}, {"sayName": True, "skip": True})
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["properties"], {"sayName": True, "skip": True})
	
	def test_overrideEqualToDefaultKept(self):
		data = makeData(ruleTypes.MARKER, None, {"autoAction": None, "sayName": False})
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["properties"], {"autoAction": None, "sayName": False})
	
	def test_truthyOverrideOfDefaultKept(self):
		data = makeData(ruleTypes.MARKER, None, {"autoAction": "speak", "sayName": True})
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["properties"], {"autoAction": "speak", "sayName": True})
	
	def test_ruleDefaultDroppedOverrideKept(self):
		data = makeData(ruleTypes.MARKER, {"sayName": False}, {"sayName": False})
		normalizeRuleData(data)
		self.assertNotIn("properties", data)
		self.assertEqual(data["criteria"][0]["properties"], {"sayName": False})


class TestUnsupportedAreDropped(unittest.TestCase):
	
	def test_unsupportedPropertiesDropped(self):
		data = makeData(
			ruleTypes.PAGE_TITLE_1,
			{"customValue": "Title", "sayName": True},
			{"customValue": "", "skip": True},
		)
		normalizeRuleData(data)
		self.assertEqual(data["properties"], {"customValue": "Title"})
		self.assertEqual(data["criteria"][0]["properties"], {"customValue": ""})
	
	def test_gesturesDroppedForNonActionTypes(self):
		gestures = {"kb:a": ["normal", "moveto"]}
		data = makeData(ruleTypes.PAGE_TYPE, None, None, gestures=dict(gestures))
		data["criteria"][0]["gestures"] = dict(gestures)
		normalizeRuleData(data)
		self.assertNotIn("gestures", data)
		self.assertNotIn("gestures", data["criteria"][0])
	
	def test_gesturesKeptForActionTypes(self):
		gestures = {"kb:a": ["normal", "moveto"]}
		data = makeData(ruleTypes.MARKER, None, None, gestures=dict(gestures))
		data["criteria"][0]["gestures"] = dict(gestures)
		normalizeRuleData(data)
		self.assertEqual(data["gestures"], gestures)
		self.assertEqual(data["criteria"][0]["gestures"], gestures)
	
	def test_emptyGesturesDropped(self):
		data = makeData(ruleTypes.MARKER, None, None, gestures={})
		data["criteria"][0]["gestures"] = {}
		normalizeRuleData(data)
		self.assertNotIn("gestures", data)
		self.assertNotIn("gestures", data["criteria"][0])


class TestDisabledGestures(unittest.TestCase):
	
	def test_disabledKeptAtCriteriaLevel(self):
		data = makeData(ruleTypes.MARKER, None, None, gestures={"kb:a": ["normal", "moveto"]})
		data["criteria"][0]["gestures"] = {"kb:a": None}
		normalizeRuleData(data)
		self.assertEqual(data["criteria"][0]["gestures"], {"kb:a": None})
	
	def test_disabledDroppedAtRuleLevel(self):
		data = makeData(ruleTypes.MARKER, None, None, gestures={"kb:a": None})
		normalizeRuleData(data)
		self.assertNotIn("gestures", data)


class TestLoadTolerance(unittest.TestCase):
	
	def test_nullTextPropertyLoadsAsEmpty(self):
		rule, crit = makeRuleAndCriteria(
			ruleTypes.MARKER, {"customName": "Foo"}, {"customName": None}
		)
		self.assertEqual(crit.customName, "")


if __name__ == "__main__":
	unittest.main()
