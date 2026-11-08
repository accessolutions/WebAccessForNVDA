# tests/unit/test_nodeMatching.py
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

"""Tests for `nodeMatching` (the "same node" search mode)."""


from types import SimpleNamespace
import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.nodeMatching import matchesOnSameNode


def node(text="", **attrs):
	attrs.setdefault("role", 0)
	attrs.setdefault("states", set())
	n = SimpleNamespace(**attrs)
	n._text = text
	return n


def containsText(n, text):
	texts = text if isinstance(text, list) else [text]
	return any(t in n._text for t in texts)


def match(n, **criteria):
	return matchesOnSameNode(n, criteria, containsText)


class TestSameNode(unittest.TestCase):
	
	def test_allOnTheNode(self):
		li = node(tag="li", id=None, className="toto active")
		self.assertTrue(match(li, eq_tag=["li"], eq_className=["toto"]))
	
	def test_attributeMissingOnTheNode(self):
		# The class being on an ancestor does not count
		li = node(tag="li", id=None, className=None)
		self.assertFalse(match(li, eq_tag=["li"], eq_className=["toto"]))
	
	def test_classesAreTokens(self):
		li = node(tag="li", className="toto-titi")
		self.assertFalse(match(li, eq_className=["toto"]))
		self.assertTrue(match(li, in_className=["toto"]))
	
	def test_severalClassesAnd(self):
		li = node(tag="li", className="a b")
		self.assertTrue(match(li, **{"eq_className": ["a"], "eq_className#1": ["b"]}))
		self.assertFalse(match(li, **{"eq_className": ["a"], "eq_className#1": ["c"]}))
	
	def test_alternativesOr(self):
		self.assertTrue(match(node(tag="li"), eq_tag=["ul", "li"]))
	
	def test_negative(self):
		li = node(tag="li", className="toto")
		self.assertFalse(match(li, eq_tag=["li"], notEq_className=["toto"]))
		self.assertTrue(match(li, eq_tag=["li"], notEq_className=["titi"]))
		self.assertFalse(match(li, notIn_className=["to"]))
	
	def test_negativeOnMissingProperty(self):
		self.assertTrue(match(node(tag="li"), notEq_src=["x"]))
		self.assertFalse(match(node(tag="li"), eq_src=["x"]))
	
	def test_text(self):
		li = node("Contact us", tag="li")
		self.assertTrue(match(li, eq_tag=["li"], in_text="Contact"))
		self.assertFalse(match(li, eq_tag=["li"], in_text="Home"))
	
	def test_prevText(self):
		li = node(tag="li")
		li.previousTextNode = SimpleNamespace(text="Price:")
		self.assertTrue(match(li, in_prevText="Price"))
		self.assertFalse(match(li, in_prevText="Total"))
		self.assertFalse(match(node(tag="li"), in_prevText="Price"))
	
	def test_states(self):
		self.assertTrue(match(node(tag="input", states={1, 2}), eq_states=[2]))
		self.assertFalse(match(node(tag="input", states={1}), eq_states=[2]))
	
	def test_noCriteria(self):
		self.assertTrue(match(node(tag="li")))


class TestAnyClauses(unittest.TestCase):
	
	def test_mixedPositiveNegative(self):
		clause = [("eq", "a"), ("notEq", "b")]  # a | !b
		self.assertTrue(match(node(className="a b"), **{"any_className#0": clause}))
		self.assertTrue(match(node(className="c"), **{"any_className#0": clause}))
		self.assertFalse(match(node(className="b"), **{"any_className#0": clause}))
	
	def test_exactOrPartial(self):
		clause = [("eq", "a"), ("in", "xy")]  # a | *xy*
		self.assertTrue(match(node(className="axyz"), **{"any_className#0": clause}))
		self.assertTrue(match(node(className="a"), **{"any_className#0": clause}))
		self.assertFalse(match(node(className="b"), **{"any_className#0": clause}))
	
	def test_missingProperty(self):
		self.assertTrue(match(node(), **{"any_src#0": [("notEq", "x"), ("eq", "y")]}))
		self.assertFalse(match(node(), **{"any_src#0": [("eq", "x")]}))
	
	def test_fromExpression(self):
		from webAccess.criteriaExpressions import buildSearchKwargs, parseExpression
		criteria = buildSearchKwargs("className", parseExpression("(a & b) | (c & !d)", spaceIsAnd=True))
		self.assertTrue(match(node(className="a b"), **criteria))
		self.assertTrue(match(node(className="c"), **criteria))
		self.assertFalse(match(node(className="c d"), **criteria))
		self.assertFalse(match(node(className="a"), **criteria))


if __name__ == "__main__":
	unittest.main()
