# tests/unit/test_criteriaExpressions.py
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

"""Tests for `criteriaExpressions`."""


from itertools import chain, combinations
import unittest

from . import ADDON_PACKAGE_DIR  # noqa: F401 (installs the stubs)
from webAccess.criteriaExpressions import (
	And,
	ExpressionSyntaxError,
	ExpressionTooComplex,
	Not,
	Or,
	Value,
	buildSearchKwargs,
	evaluate,
	formatExpression,
	iterValues,
	mapValues,
	migrateLegacyContextExpression,
	migrateLegacyExpression,
	migrateLegacyRelativePath,
	migrateLegacyRules,
	parseExpression,
	parseLegacyContextExpression,
	parseLegacyExpression,
	toCnf,
)


def holds(values):
	"""A predicate for a node whose property has the given values (eg. classes)."""
	def predicate(value):
		if value.partial:
			return any(value.text in candidate for candidate in values)
		return value.text in values
	return predicate


def check(node, values):
	return evaluate(node, holds(values))


def subsets(universe):
	universe = list(universe)
	return chain.from_iterable(combinations(universe, r) for r in range(len(universe) + 1))


class TestParse(unittest.TestCase):

	def test_empty(self):
		self.assertIsNone(parseExpression(None))
		self.assertIsNone(parseExpression("  "))

	def test_precedence(self):
		# NOT, then AND, then OR
		self.assertEqual(
			parseExpression("a & b | !c & d"),
			Or((And((Value("a"), Value("b"))), And((Not(Value("c")), Value("d"))))),
		)

	def test_parentheses(self):
		self.assertEqual(
			parseExpression("(a & b) & (a & c)"),
			And((And((Value("a"), Value("b"))), And((Value("a"), Value("c"))))),
		)
		self.assertEqual(
			parseExpression("a & (b | (c & !(d | e)))"),
			And((Value("a"), Or((Value("b"), And((Value("c"), Not(Or((Value("d"), Value("e")))))))))),
		)

	def test_spacesInValues(self):
		self.assertEqual(parseExpression(" check box | link "), Or((Value("check box"), Value("link"))))

	def test_spaceIsAnd(self):
		self.assertEqual(
			parseExpression("a b | c", spaceIsAnd=True),
			Or((And((Value("a"), Value("b"))), Value("c"))),
		)
		self.assertEqual(
			parseExpression("a (b | c) !d", spaceIsAnd=True),
			And((Value("a"), Or((Value("b"), Value("c"))), Not(Value("d")))),
		)

	def test_partial(self):
		self.assertEqual(parseExpression("*foo*"), Value("foo", True))
		self.assertEqual(parseExpression("foo*"), Value("foo", True))
		self.assertEqual(parseExpression("foo*", partial=False), Value("foo*"))

	def test_escapes(self):
		self.assertEqual(parseExpression(r"image\(1\).png"), Value("image(1).png"))
		self.assertEqual(parseExpression(r"a\&b"), Value("a&b"))

	def test_errors(self):
		for text in ("(", "a)", "(a", "a &", "& a", "a | | b", "!", "a !b", "()", "a\\", "(a))"):
			with self.assertRaises(ExpressionSyntaxError, msg=text):
				parseExpression(text)

	def test_errorPosition(self):
		with self.assertRaises(ExpressionSyntaxError) as ctx:
			parseExpression("a & (b | c")
		self.assertEqual(ctx.exception.position, 4)


class TestFormat(unittest.TestCase):

	def test_minimalParentheses(self):
		for text, expected in (
			("a&b|c", "a & b | c"),
			("a&(b|c)", "a & (b | c)"),
			("(a|b)&c", "(a | b) & c"),
			("!(a|b)", "!(a | b)"),
			("!a&!b", "!a & !b"),
			("((a))", "a"),
		):
			self.assertEqual(formatExpression(parseExpression(text)), expected, text)

	def test_roundTripKeepsValuesAsWritten(self):
		self.assertEqual(formatExpression(parseExpression(r"x\(1\) | *foo")), r"x\(1\) | *foo")

	def test_mapValues(self):
		node = mapValues(parseExpression("a | !b"), lambda v: Value(v.text.upper()))
		self.assertEqual(formatExpression(node), "A | !B")
		self.assertEqual([v.text for v in iterValues(node)], ["A", "B"])


class TestEvaluate(unittest.TestCase):

	def test_examples(self):
		node = parseExpression("(a & b) | (c & !d)")
		self.assertTrue(check(node, {"a", "b"}))
		self.assertTrue(check(node, {"c"}))
		self.assertFalse(check(node, {"c", "d"}))
		self.assertFalse(check(node, {"a"}))

	def test_orMeansOr(self):
		node = parseExpression("a | !b")
		self.assertTrue(check(node, {"a", "b"}))
		self.assertTrue(check(node, set()))
		self.assertFalse(check(node, {"b"}))

	def test_empty(self):
		self.assertTrue(evaluate(None, holds(set())))


class TestCnf(unittest.TestCase):

	def test_equivalence(self):
		universe = ["a", "b", "c", "d"]
		for text in (
			"a", "!a", "a & b", "a | b", "a & (b | c)", "(a & b) | (c & d)", "!(a & b)",
			"!(a | (b & !c))", "a | !a", "(a | b) & (a | c) & !d",
		):
			node = parseExpression(text)
			cnf = toCnf(node)
			for values in subsets(universe):
				expected = check(node, set(values))
				actual = all(
					any(
						(value.text not in values) if negated else (value.text in values)
						for negated, value in clause
					)
					for clause in cnf
				)
				self.assertEqual(actual, expected, f"{text} on {values}")

	def test_tautologyDropped(self):
		self.assertEqual(toCnf(parseExpression("a | !a")), [])

	def test_tooComplex(self):
		text = " | ".join(f"(a{i} & b{i})" for i in range(8))  # 2^8 clauses
		with self.assertRaises(ExpressionTooComplex):
			toCnf(parseExpression(text))


class TestSearchKwargs(unittest.TestCase):

	def test_kinds(self):
		kwargs = buildSearchKwargs("className", parseExpression("(a | b) & !c & (d | *e*) & (f | !g)"))
		self.assertEqual(kwargs, {
			"eq_className#0": ["a", "b"],
			"notEq_className#1": ["c"],
			"any_className#2": [("eq", "d"), ("in", "e")],
			"any_className#3": [("eq", "f"), ("notEq", "g")],
		})

	def test_negatedPartial(self):
		self.assertEqual(buildSearchKwargs("src", parseExpression("!*.gif*")), {"notIn_src#0": [".gif"]})

	def test_convert(self):
		self.assertEqual(
			buildSearchKwargs("role", parseExpression("8 | 9"), convert=int),
			{"eq_role#0": [8, 9]},
		)


class TestLegacy(unittest.TestCase):

	UNIVERSE = ["a", "b", "c", "d", "xe"]

	def assertSameSelection(self, legacyText, spaceIsAnd=False):
		"""The migrated expression selects exactly what the legacy one did."""
		legacy = parseLegacyExpression(legacyText, spaceIsAnd)
		migrated = migrateLegacyExpression(legacyText, spaceIsAnd)
		current = parseExpression(migrated if migrated is not None else legacyText, spaceIsAnd=spaceIsAnd)
		for values in subsets(self.UNIVERSE):
			self.assertEqual(
				check(current, set(values)), check(legacy, set(values)),
				f"{legacyText!r} -> {migrated!r} on {values}"
			)
		return migrated

	def test_unchanged(self):
		for text in ("a", "a | b", "!a", "a & b", "a & !b", "*e*", "a & b & !c", " a |b "):
			self.assertIsNone(self.assertSameSelection(text), text)

	def test_rewritten(self):
		for text, expected in (
			("a | !b", "a & !b"),
			("!a | !b", "!a & !b"),
			("a | *e*", "a & *e*"),
			("a & b | c", "a & (b | c)"),
			("a | b & c", "(a | b) & c"),
			("a | b | *e* | !c", "(a | b) & *e* & !c"),
		):
			self.assertEqual(self.assertSameSelection(text), expected, text)

	def test_className(self):
		self.assertIsNone(self.assertSameSelection("a b", spaceIsAnd=True))
		self.assertEqual(self.assertSameSelection("a b|c", spaceIsAnd=True), "a & (b | c)")

	def test_specialCharsEscaped(self):
		self.assertEqual(migrateLegacyExpression("image(1).png"), r"image\(1\).png")
		self.assertEqual(parseExpression(r"image\(1\).png"), Value("image(1).png"))

	def test_context(self):
		self.assertIsNone(migrateLegacyContextExpression("A | B"))
		self.assertIsNone(migrateLegacyContextExpression("A & !B"))
		self.assertEqual(migrateLegacyContextExpression("!A | B"), "!(A | B)")
		self.assertEqual(migrateLegacyContextExpression("A | B & C"), "(A | B) & C")
		legacy = parseLegacyContextExpression("!A | B & C")
		self.assertEqual(legacy, And((Not(Or((Value("A"), Value("B")))), Value("C"))))

	def test_contextNamesAreNotPartial(self):
		self.assertIsNone(migrateLegacyContextExpression("Menu*"))


class TestMigrateRules(unittest.TestCase):
	
	def test_rules(self):
		rules = {
			"R": {"name": "R", "type": "marker", "criteria": [
				{"selector": {"tag": "li", "className": "a b|c", "role": "8|!9", "url": "a|!b", "text": "x | !y"}},
				{"selector": {
					"start": {"id": "x|!y", "states": 16},
					"end": {"relativePath": "u{'className': 'a|!b'}d"},
				}},
			]},
		}
		messages = migrateLegacyRules(rules)
		crit0 = rules["R"]["criteria"][0]["selector"]
		self.assertEqual(crit0["tag"], "li")
		self.assertEqual(crit0["className"], "a & (b | c)")
		self.assertEqual(crit0["role"], "8 & !9")
		# Not concerned: URL (own syntax) and text (a single string)
		self.assertEqual(crit0["url"], "a|!b")
		self.assertEqual(crit0["text"], "x | !y")
		start = rules["R"]["criteria"][1]["selector"]["start"]
		self.assertEqual(start["id"], "x & !y")
		self.assertEqual(start["states"], 16)
		end = rules["R"]["criteria"][1]["selector"]["end"]
		self.assertEqual(end["relativePath"], "u{'className': 'a & !b'}d")
		self.assertEqual(len(messages), 4)
		self.assertIn("alternative #2 (end), relativePath", messages[-1])
	
	def test_contexts(self):
		rules = {"R": {"criteria": [{"selector": {
			"contextParent": "!A | B", "contextPageType": "Home | Search & Results",
		}}, {"selector": {"contextParent": "A | B & !C"}}]}}
		messages = migrateLegacyRules(rules)
		self.assertEqual(rules["R"]["criteria"][0]["selector"]["contextParent"], "!(A | B)")
		self.assertEqual(rules["R"]["criteria"][0]["selector"]["contextPageType"], "(Home | Search) & Results")
		self.assertEqual(rules["R"]["criteria"][1]["selector"]["contextParent"], "(A | B) & !C")
		self.assertEqual(len(messages), 3)
	
	def test_nothingToMigrate(self):
		rules = {"R": {"criteria": [{"selector": {"className": "a b", "tag": "li|ul"}}]}}
		self.assertEqual(migrateLegacyRules(rules), [])
		self.assertEqual(rules["R"]["criteria"][0]["selector"], {"className": "a b", "tag": "li|ul"})
	
	def test_relativePathUnchanged(self):
		self.assertEqual(migrateLegacyRelativePath("u{'tag': 'li'}d"), "u{'tag': 'li'}d")


if __name__ == "__main__":
	unittest.main()
