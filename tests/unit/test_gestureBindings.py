# tests/unit/test_gestureBindings.py
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

"""Tests for `ruleHandler.gestureBindings`."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.ruleHandler.gestureBindings import (
	UNAVAILABLE_ACTION,
	getActionLabel,
	getEffectiveGestures,
	isUnavailableBinding,
	joinGestures,
	splitGestures,
)


def normalize(gestureId):
	"""Simplified stand-in for `inputCore.normalizeGestureIdentifier`."""
	source, main = gestureId.lower().split(":", 1)
	return f"{source}:{'+'.join(sorted(main.split('+')))}"


RULE = {
	"kb:control+a": ("normal", "moveto"),
	"kb:control+b": ("normal", "speak"),
}


class TestGetEffectiveGestures(unittest.TestCase):
	
	def test_inheritsRuleBindings(self):
		self.assertEqual(getEffectiveGestures(RULE, {}), RULE)
	
	def test_addsBinding(self):
		eff = getEffectiveGestures(RULE, {"kb:control+c": ("normal", "sayall")})
		self.assertEqual(eff["kb:control+c"], ("normal", "sayall"))
		self.assertEqual(len(eff), 3)
	
	def test_replacesBinding(self):
		eff = getEffectiveGestures(RULE, {"kb:control+a": ("normal", "speak")})
		self.assertEqual(eff["kb:control+a"], ("normal", "speak"))
	
	def test_replacesBindingAndScope(self):
		eff = getEffectiveGestures(RULE, {"kb:control+a": ("local", "moveto")})
		self.assertEqual(eff["kb:control+a"], ("local", "moveto"))
	
	def test_disablesBinding(self):
		eff = getEffectiveGestures(RULE, {}, {"kb:control+a"})
		self.assertEqual(eff, {"kb:control+b": ("normal", "speak")})
	
	def test_disablingUnknownGestureIsHarmless(self):
		self.assertEqual(getEffectiveGestures(RULE, {}, {"kb:control+z"}), RULE)
	
	def test_normalizesBeforeMerging(self):
		eff = getEffectiveGestures(
			{"kb:Control+A": ("normal", "moveto")},
			{"kb:a+control": ("normal", "speak")},
			normalize=normalize,
		)
		self.assertEqual(eff, {"kb:a+control": ("normal", "speak")})
	
	def test_normalizesDisabled(self):
		eff = getEffectiveGestures(RULE, {}, {"kb:A+Control"}, normalize=normalize)
		self.assertEqual(eff, {"kb:b+control": ("normal", "speak")})


class TestSerialization(unittest.TestCase):
	
	def test_split(self):
		bindings, disabled = splitGestures({
			"kb:control+a": ["normal", "moveto"],
			"kb:control+b": None,
		})
		self.assertEqual(bindings, {"kb:control+a": ["normal", "moveto"]})
		self.assertEqual(disabled, {"kb:control+b"})
	
	def test_roundTrip(self):
		data = {
			"kb:control+a": ["normal", "moveto"],
			"kb:control+b": None,
			"kb:control+c": ["local", "speak"],
		}
		self.assertEqual(joinGestures(*splitGestures(data)), data)
	
	def test_joinSorted(self):
		self.assertEqual(
			list(joinGestures({"kb:b": ("normal", "x")}, {"kb:a"})),
			["kb:a", "kb:b"],
		)


class TestUnavailable(unittest.TestCase):
	
	def test_replacesRuleBinding(self):
		eff = getEffectiveGestures(RULE, {"kb:control+a": ("normal", UNAVAILABLE_ACTION)})
		self.assertEqual(eff["kb:control+a"], ("normal", UNAVAILABLE_ACTION))
	
	def test_isUnavailableBinding(self):
		self.assertTrue(isUnavailableBinding(["normal", UNAVAILABLE_ACTION]))
		self.assertTrue(isUnavailableBinding(("local", UNAVAILABLE_ACTION)))
		self.assertFalse(isUnavailableBinding(["normal", "moveto"]))
		self.assertFalse(isUnavailableBinding(None))
	
	def test_roundTrip(self):
		data = {"kb:control+a": ["normal", UNAVAILABLE_ACTION], "kb:control+b": None}
		bindings, disabled = splitGestures(data)
		self.assertEqual(bindings, {"kb:control+a": ["normal", UNAVAILABLE_ACTION]})
		self.assertEqual(disabled, {"kb:control+b"})
		self.assertEqual(joinGestures(bindings, disabled), data)
	
	def test_actionLabel(self):
		actions = {"moveto": "Move to"}
		self.assertEqual(getActionLabel(actions, "moveto"), "Move to")
		self.assertEqual(getActionLabel(actions, UNAVAILABLE_ACTION), "Announce as unavailable")
		self.assertEqual(getActionLabel(actions, "custom"), "*custom")


if __name__ == "__main__":
	unittest.main()
