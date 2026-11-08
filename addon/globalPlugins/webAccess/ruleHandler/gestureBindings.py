# globalPlugins/webAccess/ruleHandler/gestureBindings.py
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

"""Resolution of the gesture bindings of a Rule and of its alternatives (Criteria).

Serialized form, both at Rule and Criteria level:

	"gestures": {
		"kb:control+shift+a": ["normal", "moveto"],  # Binding
		"kb:control+shift+b": null,                  # Criteria level only: Disabled
		"kb:control+shift+c": ["normal", "unavailable"],  # Criteria level only: Disabled, announced
	}

At Criteria level, a binding adds or replaces a Rule level binding, while a Rule level
binding can be disabled for this alternative either:
 - with `null`: The gesture then reaches the browser as if it were not bound.
 - with a binding to the `UNAVAILABLE_ACTION` action: The gesture is consumed and
   announced as unavailable here.

This module does not depend on NVDA (apart from translations), so that it can be
unit tested.
"""


from typing import Any, Callable, TypeVar

import addonHandler

from collections.abc import Iterable, Mapping


addonHandler.initTranslation()


T = TypeVar("T")


UNAVAILABLE_ACTION = "unavailable"
"""Built-in action announcing that a gesture is not available for the matched alternative.

Meant to disable a Rule level binding on an alternative, while letting the user know.
Not offered in the actions lists, as it is meaningless elsewhere.
"""

# Translators: The name of the action announcing a disabled gesture is unavailable
UNAVAILABLE_ACTION_LABEL = pgettext("webAccess.action", "Announce as unavailable")


def getActionLabel(actions: Mapping[str, str], action: str) -> str:
	"""The display label of an action, `actions` being the available actions labels."""
	if action in actions:
		return actions[action]
	if action == UNAVAILABLE_ACTION:
		return UNAVAILABLE_ACTION_LABEL
	return f"*{action}"


def isUnavailableBinding(binding: Any) -> bool:
	"""Whether the given serialized or loaded binding announces the gesture as unavailable."""
	return binding is not None and binding[1] == UNAVAILABLE_ACTION


def splitGestures(
	data: Mapping[str, Any],
) -> tuple[dict[str, Any], set[str]]:
	"""Split serialized Criteria level gestures into bindings and disabled identifiers."""
	bindings = {}
	disabled = set()
	for gestureId, binding in data.items():
		if binding is None:
			disabled.add(gestureId)
		else:
			bindings[gestureId] = binding
	return bindings, disabled


def joinGestures(
	bindings: Mapping[str, Any],
	disabled: Iterable[str],
) -> dict[str, Any]:
	"""Reverse of `splitGestures`, sorted by gesture identifier."""
	data = dict(bindings)
	data.update({gestureId: None for gestureId in disabled})
	return {gestureId: data[gestureId] for gestureId in sorted(data)}


def getEffectiveGestures(
	ruleGestures: Mapping[str, T],
	criteriaGestures: Mapping[str, T],
	disabled: Iterable[str] = (),
	normalize: Callable[[str], str] = lambda gestureId: gestureId,
) -> dict[str, T]:
	"""The bindings applying to the Results of an alternative, keyed by normalized identifier.

	The gesture identifiers are normalized before merging, so that a Criteria level
	binding replaces a Rule level binding for the same gesture whatever its spelling
	(eg. "kb:Control+A" vs. "kb:a+control").
	"""
	result = {normalize(gestureId): binding for gestureId, binding in ruleGestures.items()}
	for gestureId in disabled:
		result.pop(normalize(gestureId), None)
	for gestureId, binding in criteriaGestures.items():
		result[normalize(gestureId)] = binding
	return result
