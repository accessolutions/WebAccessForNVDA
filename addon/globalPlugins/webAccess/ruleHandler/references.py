# globalPlugins/webAccess/ruleHandler/references.py
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

"""References between rules, by name.

A rule refers to other rules through the context criteria of the selectors of its
alternatives (Criteria):

 - `contextPageType`: Page type rules (or any rule) that must (not) be matched.
 - `contextParent`: Rules whose Results must (not) contain the matched node.

Both are expressions of the form `term ('&' term)*`, where `term` is
`'!'? name ('|' name)*`:

 - `&`: All the terms must be satisfied.
 - `|`: Any of the names satisfies the term.
 - `!`: Negates the term: None of its names must be satisfied.

Names are compared case-sensitively, once stripped. There is no escaping: Rule names
cannot contain `&` nor `|`, nor start with `!` (see `getRuleNameError`).

This module operates on serialized data (as stored in WebModule files) and does not
depend on NVDA, so that it can be unit tested.
"""


from dataclasses import dataclass
from typing import Any

from collections.abc import Iterable, Iterator, Mapping, Sequence


CONTEXT_REFERENCE_FIELDS = ("contextPageType", "contextParent")
"""Selector fields referring to other rules by name."""


@dataclass(frozen=True)
class ContextTerm:
	"""A term of a context expression: `'!'? name ('|' name)*`."""

	names: tuple[str, ...]
	negated: bool = False


def parseContextExpression(expr: str | None) -> tuple[ContextTerm, ...]:
	"""Parse a context expression into its terms, ignoring empty terms and names.

	Spaces around operators and names are ignored, eg. "A | B & ! C".
	"""
	terms = []
	for part in (expr or "").split("&"):
		part = part.strip()
		negated = part.startswith("!")
		if negated:
			part = part[1:]
		names = tuple(name.strip() for name in part.split("|") if name.strip())
		if names:
			terms.append(ContextTerm(names, negated))
	return tuple(terms)


def formatContextExpression(terms: Iterable[ContextTerm]) -> str:
	"""The canonical form of a context expression, eg. "A | B & !C"."""
	return " & ".join(
		("!" if term.negated else "") + " | ".join(term.names)
		for term in terms
	)


def iterContextNames(expr: str | None) -> Iterator[str]:
	"""Yield the rule names referred to by a context expression, in order, with duplicates."""
	for term in parseContextExpression(expr):
		yield from term.names


def renameInContextExpression(expr: str | None, oldName: str, newName: str) -> str | None:
	"""Rename a rule in a context expression.

	Names are matched as whole tokens: Renaming "Menu" does not affect "Main menu".
	The expression is returned unchanged (same formatting) if it does not refer to
	`oldName`, in its canonical form otherwise.
	"""
	terms = parseContextExpression(expr)
	if not any(oldName in term.names for term in terms):
		return expr
	return formatContextExpression(
		ContextTerm(
			tuple(newName if name == oldName else name for name in term.names),
			term.negated,
		)
		for term in terms
	)


@dataclass(frozen=True)
class Reference:
	"""A reference to a rule, by name, from the selector of an alternative."""

	criteriaIndex: int
	"""0-based index of the alternative (Criteria) in its rule."""
	selectorKey: str | None
	"""`None` for a single node selector, `"start"` or `"end"` for a free zone."""
	field: str
	"""One of `CONTEXT_REFERENCE_FIELDS`."""
	name: str
	"""The name of the referred rule."""


def iterSelectorsData(critData: Mapping[str, Any]) -> Iterator[tuple[str | None, Mapping[str, Any]]]:
	"""Yield `(selectorKey, selectorData)` for each selector of serialized Criteria data."""
	selector = critData.get("selector") or {}
	if set(selector.keys()) == {"start", "end"}:
		yield "start", selector["start"] or {}
		yield "end", selector["end"] or {}
	else:
		yield None, selector


def iterReferences(ruleData: Mapping[str, Any]) -> Iterator[Reference]:
	"""Yield the references to other rules found in serialized rule data."""
	for criteriaIndex, critData in enumerate(ruleData.get("criteria") or ()):
		for selectorKey, selectorData in iterSelectorsData(critData):
			for field in CONTEXT_REFERENCE_FIELDS:
				for name in iterContextNames(selectorData.get(field)):
					yield Reference(criteriaIndex, selectorKey, field, name)


def renameReferences(ruleData: dict[str, Any], oldName: str, newName: str) -> bool:
	"""Rename, in place, the references to a rule in serialized rule data.

	Returns whether anything was changed.
	"""
	changed = False
	for critData in ruleData.get("criteria") or ():
		for selectorKey, selectorData in iterSelectorsData(critData):
			for field in CONTEXT_REFERENCE_FIELDS:
				expr = selectorData.get(field)
				newExpr = renameInContextExpression(expr, oldName, newName)
				if newExpr != expr:
					selectorData[field] = newExpr
					changed = True
	return changed


def buildDependencyGraph(rulesData: Mapping[str, Mapping[str, Any]]) -> dict[str, set[str]]:
	"""Map each rule name to the names of the rules it refers to.

	`rulesData` maps rule names to serialized rule data, eg. the rules of a layer.
	Names referred to but absent from `rulesData` are included as targets.
	"""
	return {
		name: {ref.name for ref in iterReferences(ruleData)}
		for name, ruleData in rulesData.items()
	}


def getDependents(
	rulesData: Mapping[str, Mapping[str, Any]],
	name: str,
) -> dict[str, list[Reference]]:
	"""The rules referring to the given rule name, with their references to it."""
	dependents = {}
	for ruleName, ruleData in rulesData.items():
		refs = [ref for ref in iterReferences(ruleData) if ref.name == name]
		if refs:
			dependents[ruleName] = refs
	return dependents


def findDanglingReferences(
	rulesData: Mapping[str, Mapping[str, Any]],
	knownNames: Iterable[str],
) -> dict[str, list[Reference]]:
	"""The references to rule names absent from `knownNames`, by referring rule name."""
	knownNames = set(knownNames)
	dangling = {}
	for ruleName, ruleData in rulesData.items():
		refs = [ref for ref in iterReferences(ruleData) if ref.name not in knownNames]
		if refs:
			dangling[ruleName] = refs
	return dangling


def findCycles(graph: Mapping[str, Iterable[str]]) -> list[list[str]]:
	"""The cycles of a dependency graph, as its strongly connected components.

	Returns the components with more than one rule, or a single rule referring to
	itself, each sorted, the list being sorted too (deterministic).
	Uses an iterative Tarjan's algorithm, so that deep graphs do not hit the
	recursion limit.
	"""
	index = {}
	lowlink = {}
	onStack = set()
	stack = []
	components = []
	counter = 0
	nodes = set(graph)
	for targets in graph.values():
		nodes.update(targets)
	for root in sorted(nodes):
		if root in index:
			continue
		work = [(root, iter(sorted(graph.get(root, ()))))]
		index[root] = lowlink[root] = counter
		counter += 1
		stack.append(root)
		onStack.add(root)
		while work:
			node, targets = work[-1]
			for target in targets:
				if target not in index:
					index[target] = lowlink[target] = counter
					counter += 1
					stack.append(target)
					onStack.add(target)
					work.append((target, iter(sorted(graph.get(target, ())))))
					break
				elif target in onStack:
					lowlink[node] = min(lowlink[node], index[target])
			else:
				work.pop()
				if work:
					parent = work[-1][0]
					lowlink[parent] = min(lowlink[parent], lowlink[node])
				if lowlink[node] == index[node]:
					component = []
					while True:
						member = stack.pop()
						onStack.discard(member)
						component.append(member)
						if member == node:
							break
					if len(component) > 1 or node in graph.get(node, ()):
						components.append(sorted(component))
	return sorted(components)


def findCyclePath(
	graph: Mapping[str, Iterable[str]],
	start: str,
) -> list[str] | None:
	"""A path from `start` back to itself, eg. `["A", "B", "A"]`, or `None` if none.

	Used to report how a rule would refer to itself, directly or not.
	"""
	# Breadth-first search, for the shortest cycle
	previous = {}
	queue = [start]
	visited = set()
	while queue:
		node = queue.pop(0)
		for target in sorted(graph.get(node, ())):
			if target == start:
				path = [node]
				while path[0] != start:
					path.insert(0, previous[path[0]])
				return path + [start]
			if target not in visited:
				visited.add(target)
				previous[target] = node
				queue.append(target)
	return None


def findCyclePathIfSaved(
	rulesData: Mapping[str, Mapping[str, Any]],
	name: str,
	ruleData: Mapping[str, Any],
	oldName: str | None = None,
) -> list[str] | None:
	"""The reference cycle the given rule would take part in once saved, or `None`.
	
	`rulesData` maps the names of the existing rules to their serialized data.
	`name` and `ruleData` are those of the rule being saved, `oldName` its name before
	being renamed, if any.
	"""
	rulesData = dict(rulesData)
	if oldName is not None:
		rulesData.pop(oldName, None)
	rulesData[name] = ruleData
	return findCyclePath(buildDependencyGraph(rulesData), name)


def iterSubModuleReferences(ruleData: Mapping[str, Any]) -> Iterator[str]:
	"""Yield the names of the WebModules loaded as sub-modules by serialized rule data.
	
	Both the Rule level and the alternatives (Criteria) level "Load sub-module"
	properties are considered.
	"""
	containers = [ruleData] + list(ruleData.get("criteria") or ())
	for container in containers:
		name = (container.get("properties") or {}).get("subModule")
		if name:
			yield name


def findSubModuleDependents(
	rulesData: Mapping[str, Mapping[str, Any]],
	webModuleName: str,
) -> list[str]:
	"""The names of the rules loading the given WebModule as a sub-module, sorted."""
	return sorted(
		name for name, ruleData in rulesData.items()
		if webModuleName in iterSubModuleReferences(ruleData)
	)


RULE_NAME_FORBIDDEN = ("&", "|")
"""Characters not allowed in rule names, as they are context expression operators."""


def getRuleNameError(name: str) -> str | None:
	"""Why the given rule name is not valid, or `None` if it is.

	The returned message is meant for logs and tests; the editors use their own,
	translated, messages.
	"""
	if not name or not name.strip():
		return "empty"
	if name != name.strip():
		return "leading or trailing spaces"
	for char in RULE_NAME_FORBIDDEN:
		if char in name:
			return f"contains {char!r}"
	if name.startswith("!"):
		return "starts with '!'"
	return None


def findCaseInsensitiveHomonyms(name: str, names: Iterable[str]) -> list[str]:
	"""The names differing from the given one only by case."""
	folded = name.casefold()
	return sorted(other for other in names if other != name and other.casefold() == folded)
