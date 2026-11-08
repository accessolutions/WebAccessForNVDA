# tests/unit/test_cssSelectors.py
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

"""Tests for `cssSelectors`."""


import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.cssSelectors import CssSyntaxError, Nth, compileSelector, parseNth


class Node:

	def __init__(self, *children):
		self.parent = None
		self.children = list(children)
		for child in children:
			child.parent = self


class Elem(Node):

	def __init__(self, tag, *children, id=None, cls=None, src=None, **attrs):
		super().__init__(*children)
		self.tag = tag
		self.id = id
		self.className = cls
		self.src = src
		self.control = {f"IAccessible2::attribute_{k.replace('_', '-')}": v for k, v in attrs.items()}

	def __repr__(self):
		return f"<{self.tag}#{self.id}.{self.className}>"


class Text(Node):

	def __init__(self, text):
		super().__init__()
		self.text = text


class Format(Node):
	"""A formatting node, transparent for CSS."""


def build():
	"""
	<body id="body">
	  <nav id="nav">
	    <ul id="menu" class="menu">
	      <li id="li1" class="item first"><a id="a1" class="active" href="/home">Home</a></li>
	      <li id="li2" class="item toto"><a id="a2" href="/news" lang="en-US">News</a></li>
	      <li id="li3" class="item"><span id="s3">Contact</span></li>
	      (formatting node wrapping li4)
	      <li id="li4" class="item toto last"></li>
	    </ul>
	  </nav>
	  <div id="main" class="toto">
	    <h2 id="h2">Title</h2>
	    <p id="p1">Text</p>
	    <p id="p2"></p>
	    <li id="li5"></li>
	  </div>
	</body>
	"""
	tree = Elem(
		"body",
		Elem(
			"nav",
			Elem(
				"ul",
				Elem("li", Elem("a", Text("Home"), id="a1", cls="active", href="/home"), id="li1", cls="item first"),
				Elem("li", Elem("a", Text("News"), id="a2", href="/news", lang="en-US"), id="li2", cls="item toto"),
				Elem("li", Elem("span", Text("Contact"), id="s3"), id="li3", cls="item"),
				Format(Elem("li", id="li4", cls="item toto last")),
				id="menu", cls="menu",
			),
			id="nav",
		),
		Elem(
			"div",
			Elem("h2", Text("Title"), id="h2"),
			Elem("p", Text("Text"), id="p1"),
			Elem("p", Text(""), id="p2"),
			Elem("li", id="li5"),
			id="main", cls="toto",
		),
		id="body",
	)
	return tree


def walk(node):
	if hasattr(node, "control"):
		yield node
	for child in node.children:
		yield from walk(child)


class Base(unittest.TestCase):

	@classmethod
	def setUpClass(cls):
		cls.tree = build()

	def select(self, selector):
		compiled = compileSelector(selector)
		return [node.id for node in walk(self.tree) if compiled(node)]

	def assertSelects(self, selector, ids):
		self.assertEqual(self.select(selector), ids, selector)


class TestSimpleSelectors(Base):

	def test_type(self):
		self.assertSelects("li", ["li1", "li2", "li3", "li4", "li5"])
		self.assertSelects("LI", ["li1", "li2", "li3", "li4", "li5"])

	def test_universal(self):
		self.assertEqual(len(self.select("*")), 15)

	def test_id(self):
		self.assertSelects("#main", ["main"])
		self.assertSelects("div#main", ["main"])
		self.assertSelects("p#main", [])

	def test_class(self):
		self.assertSelects(".toto", ["li2", "li4", "main"])
		self.assertSelects("li.toto", ["li2", "li4"])
		self.assertSelects(".item.toto", ["li2", "li4"])
		self.assertSelects(".TOTO", [])

	def test_attributes(self):
		self.assertSelects("[href]", ["a1", "a2"])
		self.assertSelects("[href='/news']", ["a2"])
		self.assertSelects('[href="/news"]', ["a2"])
		self.assertSelects("[href^='/h']", ["a1"])
		self.assertSelects("[href$=ws]", ["a2"])
		self.assertSelects("[href*=e]", ["a1", "a2"])
		self.assertSelects("[class~=item]", ["li1", "li2", "li3", "li4"])
		self.assertSelects("[class~=ite]", [])
		self.assertSelects("[lang|=en]", ["a2"])
		self.assertSelects("[lang|=en-US]", ["a2"])
		self.assertSelects("[href='/NEWS' i]", ["a2"])
		self.assertSelects("[href='/NEWS']", [])
		self.assertSelects("[id=li1]", ["li1"])
		self.assertSelects("[href^='']", [])


class TestCombinators(Base):

	def test_descendant(self):
		self.assertSelects("nav a", ["a1", "a2"])
		self.assertSelects("#main li", ["li5"])
		self.assertSelects("body li", ["li1", "li2", "li3", "li4", "li5"])

	def test_child(self):
		self.assertSelects("ul > li", ["li1", "li2", "li3", "li4"])
		self.assertSelects("nav > li", [])
		self.assertSelects("li > a.active", ["a1"])

	def test_childThroughFormattingNode(self):
		self.assertSelects("ul > li.last", ["li4"])

	def test_siblings(self):
		self.assertSelects("h2 + p", ["p1"])
		self.assertSelects("h2 ~ p", ["p1", "p2"])
		self.assertSelects("li.first + li", ["li2"])
		self.assertSelects("li.first ~ li", ["li2", "li3", "li4"])

	def test_mixed(self):
		self.assertSelects("nav ul > li.toto > a", ["a2"])
		self.assertSelects("body > div > h2 + p", ["p1"])

	def test_spacesAroundCombinators(self):
		self.assertSelects("ul>li.toto", ["li2", "li4"])
		self.assertSelects("  ul  >  li.toto  ", ["li2", "li4"])

	def test_list(self):
		self.assertSelects("h2, p#p1", ["h2", "p1"])


class TestPseudoClasses(Base):

	def test_structural(self):
		self.assertSelects("li:first-child", ["li1"])
		self.assertSelects("li:last-child", ["li4", "li5"])
		self.assertSelects("a:only-child", ["a1", "a2"])
		self.assertSelects("p:first-of-type", ["p1"])
		self.assertSelects("p:last-of-type", ["p2"])
		self.assertSelects("h2:only-of-type", ["h2"])
		self.assertSelects("body:root", ["body"])
		self.assertSelects("li:empty", ["li4", "li5"])
		self.assertSelects("p:empty", ["p2"])

	def test_nth(self):
		self.assertSelects("ul > li:nth-child(2)", ["li2"])
		self.assertSelects("ul > li:nth-child(odd)", ["li1", "li3"])
		self.assertSelects("ul > li:nth-child(even)", ["li2", "li4"])
		self.assertSelects("ul > li:nth-child(2n+1)", ["li1", "li3"])
		self.assertSelects("ul > li:nth-child(-n+2)", ["li1", "li2"])
		self.assertSelects("ul > li:nth-last-child(1)", ["li4"])
		self.assertSelects("p:nth-of-type(2)", ["p2"])
		self.assertSelects("p:nth-last-of-type(2)", ["p1"])

	def test_logical(self):
		self.assertSelects("ul > li:not(.toto)", ["li1", "li3"])
		self.assertSelects("li:not(.toto, .first)", ["li3", "li5"])
		self.assertSelects(":is(h2, p):not(:empty)", ["h2", "p1"])
		self.assertSelects("li:where(.first)", ["li1"])

	def test_has(self):
		self.assertSelects("li:has(> a.active)", ["li1"])
		self.assertSelects("li:has(a)", ["li1", "li2"])
		self.assertSelects("ul:has(> li.toto)", ["menu"])
		self.assertSelects("h2:has(+ p)", ["h2"])
		self.assertSelects("h2:has(~ li)", ["h2"])
		self.assertSelects("div:has(> h2 + p)", ["main"])
		self.assertSelects("li:has(span, a.active)", ["li1", "li3"])


class TestParsing(unittest.TestCase):

	def test_nth(self):
		self.assertEqual(parseNth("odd"), Nth(2, 1))
		self.assertEqual(parseNth("even"), Nth(2, 0))
		self.assertEqual(parseNth("3"), Nth(0, 3))
		self.assertEqual(parseNth("n"), Nth(1, 0))
		self.assertEqual(parseNth("-n+3"), Nth(-1, 3))
		self.assertEqual(parseNth("2n + 1"), Nth(2, 1))
		self.assertEqual(parseNth("+3n-2"), Nth(3, -2))

	def test_escapes(self):
		node = Elem("div", cls="md:flex")
		self.assertTrue(compileSelector(r".md\:flex")(node))

	def test_errors(self):
		for selector in (
			"", " ", "ul >", "> li", "ul,", "li:hover", "p::before", "[href", "[href=]",
			"[href=='x']", "li:nth-child(foo)", "li:not(", "li:not(.a", "svg|a", "#", ".", "li $",
			"'x'", "[href='x]",
		):
			with self.assertRaises(CssSyntaxError, msg=selector):
				compileSelector(selector)

	def test_errorPosition(self):
		with self.assertRaises(CssSyntaxError) as ctx:
			compileSelector("ul > li:hover")
		self.assertEqual(ctx.exception.position, 7)

	def test_textAndFormattingNodesNeverMatch(self):
		self.assertFalse(compileSelector("*")(Text("x")))
		self.assertFalse(compileSelector("*")(Format()))


if __name__ == "__main__":
	unittest.main()
