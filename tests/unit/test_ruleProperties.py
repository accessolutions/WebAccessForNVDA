# tests/unit/test_ruleProperties.py
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

"""Tests for the rule properties model (inheritance from Rule to Criteria)."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.ruleHandler import ruleTypes
from webAccess.ruleHandler.properties import DEFAULT_VALUES, PropertiesBase, suggestOverrideValue


class FakeProperties(PropertiesBase):
	
	__slots__ = ("_ruleType",)
	
	def __init__(self, ruleType, *maps):
		object.__setattr__(self, "_ruleType", ruleType)
		super().__init__(*maps)
	
	@property
	def ruleType(self):
		return self._ruleType


def makeRuleAndCriteria(ruleType=ruleTypes.MARKER, ruleData=None, critData=None):
	rule = FakeProperties(ruleType, {})
	rule.load(ruleData or {})
	crit = FakeProperties(ruleType)
	crit._map = rule._map.new_child()
	crit.load(critData or {})
	return rule, crit


class TestInheritance(unittest.TestCase):
	
	def test_defaults(self):
		rule, crit = makeRuleAndCriteria()
		for name, value in DEFAULT_VALUES.items():
			self.assertEqual(getattr(rule, name), value)
			self.assertEqual(getattr(crit, name), value)
	
	def test_inheritsFromRule(self):
		rule, crit = makeRuleAndCriteria(ruleData={"autoAction": "moveto", "sayName": True})
		self.assertEqual(crit.autoAction, "moveto")
		self.assertIs(crit.sayName, True)
	
	def test_falsyOverridesWin(self):
		rule, crit = makeRuleAndCriteria(
			ruleData={
				"autoAction": "moveto",
				"sayName": True,
				"customName": "Foo",
				"mutation": "heading.2",
			},
			critData={"autoAction": None, "sayName": False, "customName": "", "mutation": None},
		)
		self.assertIsNone(crit.autoAction)
		self.assertIs(crit.sayName, False)
		self.assertEqual(crit.customName, "")
		self.assertIsNone(crit.mutation)
	
	def test_ruleDumpOmitsDefaults(self):
		rule, crit = makeRuleAndCriteria(ruleData={"sayName": False, "skip": True})
		self.assertEqual(rule.dump(), {"skip": True})
	
	def test_criteriaDumpKeepsFalsyOverrides(self):
		rule, crit = makeRuleAndCriteria(
			ruleData={"autoAction": "moveto", "formMode": True},
			critData={"autoAction": None, "formMode": False},
		)
		self.assertEqual(crit.dump(), {"autoAction": None, "formMode": False})
	
	def test_criteriaDumpKeepsOverridesEqualToRule(self):
		rule, crit = makeRuleAndCriteria(
			ruleData={"autoAction": "moveto"},
			critData={"autoAction": "moveto", "sayName": False},
		)
		self.assertEqual(crit.dump(), {"autoAction": "moveto", "sayName": False})
		# Still applies once the Rule level value changes
		rule.autoAction = "speak"
		self.assertEqual(crit.autoAction, "moveto")
	
	def test_overrideIntrospection(self):
		rule, crit = makeRuleAndCriteria(
			ruleData={"autoAction": "moveto"},
			critData={"sayName": True},
		)
		self.assertFalse(rule.isOverride)
		self.assertTrue(crit.isOverride)
		self.assertTrue(crit.isOverridden("sayName"))
		self.assertFalse(crit.isOverridden("autoAction"))
		self.assertEqual(crit.getInheritedValue("autoAction"), "moveto")
		self.assertIs(crit.getInheritedValue("sayName"), False)
	
	def test_unsupportedPropertyRejected(self):
		with self.assertRaises(ValueError):
			makeRuleAndCriteria(ruleType=ruleTypes.PAGE_TITLE_1, ruleData={"skip": True})


class TestSuggestOverrideValue(unittest.TestCase):
	"""The initial value of a new override must differ from the inherited one."""
	
	ACTIONS = (None, "moveto", "sayall", "speak")
	
	def test_boolNegatesInherited(self):
		for name in ("multiple", "formMode", "skip", "sayName"):
			self.assertIs(suggestOverrideValue(name, True), False, name)
			self.assertIs(suggestOverrideValue(name, False), True, name)
	
	def test_choiceCancelsInherited(self):
		self.assertIsNone(suggestOverrideValue("autoAction", "moveto", self.ACTIONS))
		self.assertIsNone(suggestOverrideValue("mutation", "heading.2", (None, "heading.2")))
	
	def test_choiceDefaultsToFirstActualChoice(self):
		self.assertEqual(suggestOverrideValue("autoAction", None, self.ACTIONS), "moveto")
	
	def test_choiceWithoutActualChoice(self):
		self.assertIsNone(suggestOverrideValue("autoAction", None, (None,)))
		self.assertIsNone(suggestOverrideValue("autoAction", None, None))
	
	def test_textIsEmpty(self):
		for name in ("customName", "customValue", "subModule"):
			self.assertEqual(suggestOverrideValue(name, "Foo"), "", name)
			self.assertEqual(suggestOverrideValue(name, ""), "", name)


if __name__ == "__main__":
	unittest.main()
