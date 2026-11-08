# globalPlugins/webAccess/criteriaExpressions.py
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

"""Boolean expressions of the criteria fields (tag, ID, class, role, states…).

Syntax (standard boolean logic):

	expr  := and ('|' and)*        OR, lowest precedence
	and   := unary ('&' unary)*    AND
	unary := '!' unary | '(' expr ')' | value
	                               NOT, highest precedence

 - Spaces around operators and values are ignored. Values can contain spaces, except
   for the class field, where spaces separate class names, as an implicit AND.
 - A value starting or ending with `*` is a partial match ("contains"). Elsewhere, values
   are exact matches.
 - The `\\` character escapes the following one, eg. `image\\(1\\).png`.

Data saved before format 0.17 used another interpretation (see `parseLegacyExpression`),
converted upon loading (see `migrateLegacyExpression`).

This module does not depend on NVDA, so that it can be unit tested.
"""


from dataclasses import dataclass
from itertools import product
from typing import Any, Callable, Union

from collections.abc import Iterator


class ExpressionSyntaxError(ValueError):
	"""Raised when parsing an invalid expression."""

	def __init__(self, message: str, position: int):
		super().__init__(f"{message} (at position {position + 1})")
		self.message = message
		self.position = position


class ExpressionTooComplex(ValueError):
	"""Raised when an expression cannot be converted to a reasonable number of clauses."""


# Model ####################################################################################


SPECIAL_CHARS = "&|!()\\"


def escapeValue(text: str) -> str:
	return "".join("\\" + char if char in SPECIAL_CHARS else char for char in text)


@dataclass(frozen=True)
class Value:
	text: str
	"""The value, unescaped, without the `*` marking a partial match."""
	partial: bool = False
	raw: str | None = None
	"""The value as written, used for formatting, if known."""

	def format(self) -> str:
		if self.raw is not None:
			return self.raw
		text = escapeValue(self.text)
		return f"*{text}*" if self.partial else text

	def __eq__(self, other):
		return isinstance(other, Value) and (self.text, self.partial) == (other.text, other.partial)

	def __hash__(self):
		return hash((self.text, self.partial))


@dataclass(frozen=True)
class Not:
	operand: "Node"


@dataclass(frozen=True)
class And:
	operands: tuple["Node", ...]


@dataclass(frozen=True)
class Or:
	operands: tuple["Node", ...]


Node = Union[Value, Not, And, Or]


def makeAnd(operands) -> Node:
	operands = tuple(operands)
	return operands[0] if len(operands) == 1 else And(operands)


def makeOr(operands) -> Node:
	operands = tuple(operands)
	return operands[0] if len(operands) == 1 else Or(operands)


# Parser ###################################################################################


class _Parser:

	def __init__(self, text: str, spaceIsAnd: bool, partial: bool):
		self.text = text
		self.pos = 0
		self.spaceIsAnd = spaceIsAnd
		self.partial = partial

	def error(self, message: str, position: int | None = None):
		raise ExpressionSyntaxError(message, self.pos if position is None else position)

	def skipSpaces(self) -> bool:
		start = self.pos
		while self.pos < len(self.text) and self.text[self.pos].isspace():
			self.pos += 1
		return self.pos > start

	def peek(self) -> str:
		return self.text[self.pos] if self.pos < len(self.text) else ""

	def parse(self) -> Node | None:
		self.skipSpaces()
		if not self.peek():
			return None
		node = self.parseOr()
		self.skipSpaces()
		if self.peek():
			if self.peek() == ")":
				self.error("Unbalanced ')'")
			self.error(f"Unexpected {self.peek()!r}")
		return node

	def parseOr(self) -> Node:
		operands = [self.parseAnd()]
		while True:
			self.skipSpaces()
			if self.peek() != "|":
				return makeOr(operands)
			self.pos += 1
			operands.append(self.parseAnd())

	def parseAnd(self) -> Node:
		operands = [self.parseUnary()]
		while True:
			hadSpaces = self.skipSpaces()
			char = self.peek()
			if char == "&":
				self.pos += 1
				operands.append(self.parseUnary())
			elif self.spaceIsAnd and hadSpaces and char and char not in "|)":
				# Implicit AND between space-separated class names
				operands.append(self.parseUnary())
			else:
				return makeAnd(operands)

	def parseUnary(self) -> Node:
		self.skipSpaces()
		char = self.peek()
		if char == "!":
			self.pos += 1
			return Not(self.parseUnary())
		if char == "(":
			start = self.pos
			self.pos += 1
			node = self.parseOr()
			self.skipSpaces()
			if self.peek() != ")":
				self.error("Missing ')'", start)
			self.pos += 1
			return node
		if not char:
			self.error("Expected a value")
		if char in "&|)":
			self.error(f"Unexpected {char!r}")
		return self.parseValue()

	def parseValue(self) -> Value:
		start = self.pos
		chars = []
		rawEnd = start
		while self.pos < len(self.text):
			char = self.text[self.pos]
			if char == "\\":
				if self.pos + 1 >= len(self.text):
					self.error("Incomplete escape sequence")
				chars.append(self.text[self.pos + 1])
				self.pos += 2
				rawEnd = self.pos
			elif char in "&|!()":
				break
			elif char.isspace():
				if self.spaceIsAnd:
					break
				chars.append(char)
				self.pos += 1
			else:
				chars.append(char)
				self.pos += 1
				rawEnd = self.pos
		# Trailing spaces are not part of the value
		text = "".join(chars).rstrip()
		raw = self.text[start:rawEnd]
		self.pos = rawEnd
		partial = False
		if self.partial and (text.startswith("*") or text.endswith("*")):
			partial = True
			text = text.strip("*").strip()
		if not text:
			self.error("Empty value", start)
		return Value(text, partial, raw)


def parseExpression(text: str | None, spaceIsAnd: bool = False, partial: bool = True) -> Node | None:
	"""Parse an expression, `None` if empty. Raises `ExpressionSyntaxError`.

	`spaceIsAnd`: Spaces separate values as an implicit AND (class field).
	`partial`: Values starting or ending with `*` are partial matches (not for rule names).
	"""
	return _Parser(text or "", spaceIsAnd, partial).parse()


# Formatting and traversal #################################################################


PRECEDENCE = {Or: 1, And: 2, Not: 3, Value: 4}


def formatExpression(node: Node | None) -> str:
	"""Format an expression, with parentheses only where needed."""
	if node is None:
		return ""

	def fmt(node, parentPrecedence):
		precedence = PRECEDENCE[type(node)]
		if isinstance(node, Value):
			text = node.format()
		elif isinstance(node, Not):
			text = "!" + fmt(node.operand, precedence)
		else:
			separator = " | " if isinstance(node, Or) else " & "
			text = separator.join(fmt(operand, precedence) for operand in node.operands)
		if precedence < parentPrecedence:
			return f"({text})"
		return text

	return fmt(node, 0)


def iterValues(node: Node | None) -> Iterator[Value]:
	if node is None:
		return
	if isinstance(node, Value):
		yield node
	elif isinstance(node, Not):
		yield from iterValues(node.operand)
	else:
		for operand in node.operands:
			yield from iterValues(operand)


def mapValues(node: Node | None, func: Callable[[Value], Value]) -> Node | None:
	if node is None:
		return None
	if isinstance(node, Value):
		return func(node)
	if isinstance(node, Not):
		return Not(mapValues(node.operand, func))
	return type(node)(tuple(mapValues(operand, func) for operand in node.operands))


def evaluate(node: Node | None, predicate: Callable[[Value], bool]) -> bool:
	"""Evaluate an expression, `predicate` telling whether a value holds. Empty is true."""
	if node is None:
		return True
	if isinstance(node, Value):
		return predicate(node)
	if isinstance(node, Not):
		return not evaluate(node.operand, predicate)
	if isinstance(node, And):
		return all(evaluate(operand, predicate) for operand in node.operands)
	return any(evaluate(operand, predicate) for operand in node.operands)


# Conjunctive normal form ##################################################################


Literal = tuple[bool, Value]
"""`(negated, value)`"""


def toCnf(node: Node | None, maxClauses: int = 64) -> list[list[Literal]]:
	"""Convert to a conjunction (AND) of clauses, each a disjunction (OR) of literals.

	Raises `ExpressionTooComplex` beyond `maxClauses`.
	"""
	if node is None:
		return []

	def cnf(node, negated) -> list[list[Literal]]:
		if isinstance(node, Value):
			return [[(negated, node)]]
		if isinstance(node, Not):
			return cnf(node.operand, not negated)
		isAnd = isinstance(node, And) != negated  # De Morgan
		parts = [cnf(operand, negated) for operand in node.operands]
		if isAnd:
			clauses = [clause for part in parts for clause in part]
		else:
			count = 1
			for part in parts:
				count *= len(part)
			if count > maxClauses:
				raise ExpressionTooComplex(f"More than {maxClauses} clauses")
			clauses = [
				[literal for clause in combination for literal in clause]
				for combination in product(*parts)
			]
		if len(clauses) > maxClauses:
			raise ExpressionTooComplex(f"More than {maxClauses} clauses")
		return clauses

	result = []
	for clause in cnf(node, False):
		deduped = list(dict.fromkeys(clause))
		# A clause containing both a value and its negation is always true
		if any((not negated, value) in deduped for negated, value in deduped):
			continue
		if deduped not in result:
			result.append(deduped)
	return result


def getLiteralTest(literal: Literal) -> str:
	"""The search test of a literal: `eq`, `in`, `notEq` or `notIn`."""
	negated, value = literal
	test = "in" if value.partial else "eq"
	return "not" + test[0].upper() + test[1:] if negated else test


def buildSearchKwargs(
	prop: str,
	node: Node | None,
	convert: Callable[[str], Any] = lambda text: text,
	maxClauses: int = 64,
) -> dict[str, Any]:
	"""The search keyword arguments for `NodeField.searchNode` matching an expression.

	Each clause of the conjunctive normal form becomes an argument, which is satisfied
	(in the "simple" search mode, by the node or by any of its ancestors) when any of its
	literals holds:
	 - `eq_prop#i` / `in_prop#i`: Positive literals of the same kind (values list).
	 - `notEq_prop#i` / `notIn_prop#i`: A single negative literal, excluding the nodes
	   (and, in the "simple" search mode, their whole sub-tree) having this value.
	 - `any_prop#i`: Other clauses, as a list of `(test, value)` literals.

	`convert` converts the values (eg. to integers for roles and states).
	"""
	kwargs = {}
	for index, clause in enumerate(toCnf(node, maxClauses)):
		tests = {getLiteralTest(literal) for literal in clause}
		if len(tests) == 1 and (len(clause) == 1 or not clause[0][0]):
			test = tests.pop()
			kwargs[f"{test}_{prop}#{index}"] = [convert(value.text) for negated, value in clause]
		else:
			kwargs[f"any_{prop}#{index}"] = [
				(getLiteralTest(literal), convert(literal[1].text)) for literal in clause
			]
	return kwargs


# Legacy interpretation (data formats before 0.17) #########################################


def parseLegacyExpression(text: str | None, spaceIsAnd: bool = False) -> Node | None:
	"""Parse an expression as interpreted before format 0.17.

	The expression was split on `&` (and spaces, for the class field), then each part on
	`|`, without parentheses. Within a part, the values were grouped by kind, each group
	being required (AND): the exact values (OR), the partial values (OR), and the negated
	values (AND of negations). Hence, `a | !b` meant "a and not b", and `a & b | c` meant
	"a and (b or c)".
	"""
	text = text or ""
	if spaceIsAnd:
		text = text.replace(" ", "&")
	ands = []
	for part in text.split("&"):
		part = part.strip()
		eq, in_, notEq, notIn = [], [], [], []
		for item in part.split("|"):
			item = item.strip()
			if not item:
				continue
			negated = item[0] == "!"
			if negated:
				item = item[1:].strip()
				if not item:
					continue
			partial = "*" in (item[0], item[-1])
			stripped = item.strip("*").strip() if partial else item
			if not stripped:
				continue
			value = Value(stripped, partial, escapeValue(item))
			(notIn if negated and partial else notEq if negated else in_ if partial else eq).append(value)
		group = []
		if eq:
			group.append(makeOr(eq))
		if in_:
			group.append(makeOr(in_))
		group.extend(Not(value) for value in notEq + notIn)
		if group:
			ands.append(makeAnd(group))
	if not ands:
		return None
	# Flatten nested ANDs
	flat = []
	for node in ands:
		flat.extend(node.operands if isinstance(node, And) else (node,))
	return makeAnd(flat)


def parseLegacyContextExpression(text: str | None) -> Node | None:
	"""Parse a context expression (page type, parent element) as interpreted before 0.17.

	`term ('&' term)*`, `term` being `'!'? name ('|' name)*`, the `!` negating the whole
	term: `!A | B` meant "neither A nor B".
	"""
	terms = []
	for part in (text or "").split("&"):
		part = part.strip()
		negated = part.startswith("!")
		if negated:
			part = part[1:]
		names = [
			Value(name.strip(), False, escapeValue(name.strip()))
			for name in part.split("|") if name.strip()
		]
		if not names:
			continue
		term = makeOr(names)
		terms.append(Not(term) if negated else term)
	return makeAnd(terms) if terms else None


def _migrate(text: str | None, legacy: Node | None, **parseKwargs) -> str | None:
	if legacy is None:
		return None
	try:
		current = parseExpression(text, **parseKwargs)
	except ExpressionSyntaxError:
		current = None
	formatted = formatExpression(legacy)
	if current is not None and formatExpression(current) == formatted:
		return None
	return formatted


def migrateLegacyExpression(text: str | None, spaceIsAnd: bool = False) -> str | None:
	"""Rewrite an expression of a criteria field saved before format 0.17.

	Returns the expression in the current syntax, selecting exactly the same elements as
	before, or `None` if the expression has the same meaning in both syntaxes.
	"""
	return _migrate(text, parseLegacyExpression(text, spaceIsAnd), spaceIsAnd=spaceIsAnd)


def migrateLegacyContextExpression(text: str | None) -> str | None:
	"""Like `migrateLegacyExpression`, for the context criteria (rule names)."""
	return _migrate(text, parseLegacyContextExpression(text), partial=False)
