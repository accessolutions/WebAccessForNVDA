# tests/unit/test_cssGenerator.py
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

"""Tests for the CSS selectors generation of `cssSelectors`."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.cssSelectors import (
	compileSelector,
	escapeIdentifier,
	findMatches,
	generateSelector,
	suggestSelectors,
)

from .test_cssSelectors import Elem, Format, Text


def build():
	"""
	<body>
	  <header><ul class="menu"><li class="item"><a>A</a></li><li class="item"><a>B</a></li></ul></header>
	  <main id="main">
	    <ul class="menu"><li class="item"><a>C</a></li><li class="item active"><a>D</a></li></ul>
	    <p>x</p><p>y</p>
	  </main>
	  <div id="123"><span class="md:flex">z</span></div>
	  <section id="dup"></section><section id="dup"><em>w</em></section>
	</body>
	"""
	nodes = {}

	def e(key, *args, **kwargs):
		node = Elem(*args, **kwargs)
		nodes[key] = node
		return node

	root = e(
		"body", "body",
		e("header", "header", e(
			"ul1", "ul",
			e("li1", "li", e("a1", "a", Text("A")), cls="item"),
			e("li2", "li", e("a2", "a", Text("B")), cls="item"),
			cls="menu",
		)),
		e(
			"main", "main",
			e(
				"ul2", "ul",
				e("li3", "li", e("a3", "a", Text("C")), cls="item"),
				Format(e("li4", "li", e("a4", "a", Text("D")), cls="item active")),
				cls="menu",
			),
			e("p1", "p", Text("x")),
			e("p2", "p", Text("y")),
			id="main",
		),
		e("d123", "div", e("span", "span", Text("z"), cls="md:flex"), id="123"),
		e("dup1", "section", id="dup"),
		e("dup2", "section", e("em", "em", Text("w")), id="dup"),
	)
	return root, nodes


class TestEscape(unittest.TestCase):

	def test_identifiers(self):
		self.assertEqual(escapeIdentifier("item"), "item")
		self.assertEqual(escapeIdentifier("md:flex"), r"md\:flex")
		self.assertEqual(escapeIdentifier("123"), r"\31 23")
		self.assertEqual(escapeIdentifier("-1a"), r"-\31 a")
		self.assertEqual(escapeIdentifier("a b"), r"a\ b")
		self.assertEqual(escapeIdentifier("é"), "é")

	def test_roundTrip(self):
		for value in ("md:flex", "123", "a.b", "x[y]", "-2", "_a", "a#b"):
			node = Elem("div", cls=value, id=value)
			self.assertTrue(compileSelector("." + escapeIdentifier(value))(node), value)
			self.assertTrue(compileSelector("#" + escapeIdentifier(value))(node), value)


class TestGenerate(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.root, cls.nodes = build()

	def assertDesignates(self, selector, keys):
		self.assertEqual(
			[node for node in findMatches(selector, self.root)],
			[self.nodes[key] for key in keys],
			selector,
		)

	def test_uniqueEachElement(self):
		# Whatever the element, the generated selector designates it only
		for key, node in self.nodes.items():
			selector = generateSelector(node)
			self.assertDesignates(selector, [key])

	def test_uniqueId(self):
		self.assertEqual(generateSelector(self.nodes["main"]), "#main")
		self.assertEqual(generateSelector(self.nodes["p2"]), "#main > p:nth-of-type(2)")
		# The ID is kept as an anchor, intermediate steps being dropped
		self.assertEqual(generateSelector(self.nodes["li4"]), "#main li.item.active")

	def test_idStartingWithDigit(self):
		self.assertEqual(generateSelector(self.nodes["span"]), r"#\31 23 > span.md\:flex")

	def test_duplicateIdNotUsed(self):
		selector = generateSelector(self.nodes["em"])
		self.assertNotIn("#dup", selector)
		self.assertDesignates(selector, ["em"])

	def test_shortened(self):
		# Without ID, leading steps are dropped while still designating the same element
		self.assertEqual(generateSelector(self.nodes["li2"]), "header > ul.menu > li.item:nth-of-type(2)")
		self.assertEqual(generateSelector(self.nodes["header"]), "header")

	def test_nthOfTypeWhenNeeded(self):
		self.assertEqual(generateSelector(self.nodes["a3"]), "#main li.item:nth-of-type(1) > a")

	def test_similar(self):
		# Similar elements: same tags and classes along the same path
		self.assertDesignates(generateSelector(self.nodes["a1"], unique=False), ["a1", "a2"])
		self.assertDesignates(generateSelector(self.nodes["a3"], unique=False), ["a3", "a4"])
		self.assertDesignates(generateSelector(self.nodes["p1"], unique=False), ["p1", "p2"])

	def test_relativeToAncestor(self):
		selector = generateSelector(self.nodes["a4"], ancestor=self.nodes["ul2"])
		self.assertEqual(selector, "li.item.active > a")
		selector = generateSelector(self.nodes["a3"], ancestor=self.nodes["ul2"])
		matches = [n for n in findMatches(selector, self.nodes["ul2"]) if n is not self.nodes["ul2"]]
		self.assertEqual(matches, [self.nodes["a3"]])

	def test_suggestions(self):
		suggestions = suggestSelectors(self.nodes["a3"].children[0])  # From a text node
		self.assertEqual(suggestions[0], generateSelector(self.nodes["a3"]))
		self.assertEqual(suggestions[1], generateSelector(self.nodes["a3"], unique=False))
		self.assertIn("#main", suggestions)
		self.assertEqual(len(suggestions), len(set(suggestions)))


if __name__ == "__main__":
	unittest.main()
