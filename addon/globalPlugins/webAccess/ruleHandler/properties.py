# globalPlugins/webAccess/ruleHandler/properties.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (https://accessolutions.fr)
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


__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from abc import ABC, abstractmethod
from collections import ChainMap
from dataclasses import dataclass
from enum import Enum
from pprint import pformat
from typing import Any, TypeAlias
import weakref

from . import ruleTypes

import addonHandler


from collections.abc import Iterator, Mapping, Sequence


addonHandler.initTranslation()


# The `type` statement was only added in Python 3.12
PropertyValue: TypeAlias = bool | str | type(None)


@dataclass
class PropertySpecValue:
	"""Value type for the `PropertySpec` enum
	"""
	
	__slots__ = (
		"ruleTypes",
		"valueType",
		"default",
		"displayName",
		"displayValueIfUndefined",
		"isRestrictedChoice",
		"hasSuggestions",
	)
	
	ruleTypes: Sequence[str]  # Rule types for which the property is supported
	valueType: type(PropertyValue)
	default: PropertyValue
	displayName: str | Mapping[Sequence[str], str]  # Can be different by rule type
	displayValueIfUndefined: str
	isRestrictedChoice: bool  # Applies only in the editor
	hasSuggestions: bool      # Applies only in the editor
	
	def getDisplayName(self, ruleType) -> str:
		displayName = self.displayName
		if isinstance(displayName, str):
			return displayName
		return next(v for k, v in displayName.items() if ruleType in k)


class PropertySpec(Enum):
	
	autoAction = PropertySpecValue(
		ruleTypes=ruleTypes.ACTION_TYPES,
		valueType=str,
		default=None,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Auto Actions"),
		# Translators: Displayed if no value is set for the "Auto Actions" property
		displayValueIfUndefined=pgettext("webAccess.action", "No action"),
		isRestrictedChoice=True,
		hasSuggestions=False,
	)
	multiple = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.PARENT, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Multiple results"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False,
		hasSuggestions=False,
	)
	formMode = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Activate form mode"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False,
		hasSuggestions=False,
	)
	skip = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Skip with Page Down"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False,
		hasSuggestions=False,
	)
	sayName = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Speak rule name"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False,
		hasSuggestions=False,
	)
	customName = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=str,
		default="",
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Custom name"),
		# Translators: Displayed if no value is set for a given rule property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty", "<undefined>"),
		isRestrictedChoice=False,
		hasSuggestions=False,
	)
	customValue = PropertySpecValue(
		ruleTypes=(
			ruleTypes.MARKER,
			ruleTypes.PAGE_TITLE_1,
			ruleTypes.PAGE_TITLE_2,
			ruleTypes.ZONE
		),
		valueType=str,
		default="",
		displayName={
			(ruleTypes.MARKER, ruleTypes.ZONE):
				# Translators: The display name for a rule property
				pgettext("webAccess.ruleProperty", "Custom message"),
			("pageTitle1", "pageTitle2"):
				# Translators: The display name for a rule property
				pgettext("webAccess.ruleProperty", "Custom page title"),
		},
		# Translators: Displayed if no value is set for a given rule property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty", "<undefined>"),
		isRestrictedChoice=False,
		hasSuggestions=False,
	)
	mutation = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=str,
		default=None,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Transform"),
		# Translators: Displayed if no value is set for the "Transform" rule property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty.mutation", "None"),
		isRestrictedChoice=True,
		hasSuggestions=False,
	)
	profile = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.PAGE_TYPE, ruleTypes.PARENT, ruleTypes.ZONE),
		valueType=str,
		default=None,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Configuration profile"),
		# Translators: Displayed if no value is set for the "Configuration profile" rule property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty.profile", "None"),
		isRestrictedChoice=True,
		hasSuggestions=False,
	)
	subModule = PropertySpecValue(
		ruleTypes=(ruleTypes.ZONE,),
		valueType=str,
		default="",
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Load sub-module"),
		# Translators: The displayed text if there is no value for the "Load sub-module" property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty.subModule", "No"),
		isRestrictedChoice=False,
		hasSuggestions=True,
	)
	
	def __getattr__(self, name: str):
		"""Convenience method for easier reading of client code
		"""
		if name in (PropertySpecValue.__slots__ + ("getDisplayName",)):
			return getattr(self.value, name)
		return super().__getattribute__(name)
	
	@classmethod
	def forRuleType(cls, ruleType: str) -> Sequence["PropertySpec"]:
		return tuple(p for p in cls if ruleType in p.ruleTypes)


DEFAULT_VALUES = {p.name: p.default for p in PropertySpec}
PROPERTY_NAMES = tuple(p.name for p in PropertySpec)


def suggestOverrideValue(
	name: str,
	inherited: PropertyValue,
	choices: Sequence[PropertyValue] | None = None,
) -> PropertyValue:
	"""The initial value of a new override of the given property on an alternative.
	
	Overriding with the inherited value would be pointless, hence:
	 - Yes/No: The opposite of the inherited value.
	 - Restricted choice (eg. Auto Actions): "None" (eg. "No action") if a value
	   is inherited, so that it is cancelled. Otherwise, the first actual choice.
	 - Text: An empty text, either cancelling the inherited value or ready to be typed.
	"""
	spec = PropertySpec[name]
	if spec.valueType is bool:
		return not inherited
	if spec.isRestrictedChoice:
		if inherited is not None:
			return None
		return next((choice for choice in choices or () if choice is not None), None)
	return ""


def normalizeRuleData(data: dict[str, Any]) -> None:
	"""Normalize, in place, the properties and gestures of serialized rule data.

	 - Properties and gestures not supported for the rule type are dropped.
	 - The default alternatives mode ("first") is dropped.
	 - Rule level properties equal to their default value are dropped.
	 - Criteria (alternative) level properties are all kept, even if equal to the
	   value they would otherwise inherit from the Rule level: An explicit override
	   keeps applying when the Rule level value changes.
	   In particular, a falsy override (`None`, `False` or `""`) is how an
	   alternative cancels a value set at Rule level (eg. "No action" for
	   Auto Actions).
	"""
	ruleType = data["type"]
	supported = tuple(p.name for p in PropertySpec.forRuleType(ruleType))

	def normalizeGestures(container: dict[str, Any], allowDisabled: bool) -> None:
		if ruleType not in ruleTypes.ACTION_TYPES or not container.get("gestures"):
			container.pop("gestures", None)
			return
		if not allowDisabled:
			# Disabling a gesture (`None`) is meaningful only at Criteria level
			gestures = {k: v for k, v in container["gestures"].items() if v is not None}
			if gestures:
				container["gestures"] = gestures
			else:
				container.pop("gestures")

	def normalizeProperties(
		container: dict[str, Any],
		defaults: Mapping[str, PropertyValue] | None,
	) -> dict[str, PropertyValue]:
		"""Omits the values equal to `defaults`, if specified."""
		props = container.get("properties") or {}
		props = {
			name: props[name]
			for name in supported
			if name in props and (defaults is None or props[name] != defaults[name])
		}
		if props:
			container["properties"] = props
		else:
			container.pop("properties", None)
		return props

	if data.get("alternativesMode", "first") == "first":
		data.pop("alternativesMode", None)
	normalizeGestures(data, allowDisabled=False)
	normalizeProperties(data, DEFAULT_VALUES)
	for critData in data.get("criteria", ()):
		normalizeGestures(critData, allowDisabled=True)
		normalizeProperties(critData, None)


class PropertiesBase(ABC):
	"""ABC for property containers.
	
	Sub-classes must implement the `ruleType` property getter.
	"""
	
	__slots__ = ("_map",)
	
	def __init__(self, *maps: Mapping[str, PropertyValue]):
		self._map = ChainMap(*maps, DEFAULT_VALUES)
	
	def __delattr__(self, name):
		# Allow resetting properties that haven't been changed from their default
		self._map.pop(name, None)

	def __getattr__(self, name) -> PropertyValue:
		# Do not check if supported by the rule type to ease client code
		try:
			return self._map[name]
		except Exception as e:
			# An arbitrary exception would otherwise be trapped and None would be returned
			raise AttributeError(f"AttributeError: '{type(self)}' object has no attribute '{name}'") from e
	
	def __setattr__(self, name, value):
		if name not in PROPERTY_NAMES:
			super().__setattr__(name, value)
			return
		# Be more conservative regarding write operations
		if name not in self.getSupportedPropertiesName() and value != DEFAULT_VALUES[name]:
			raise ValueError(f"Property not supported for rule type {self.ruleType}: {name}")
		valueType = PropertySpec[name].valueType
		default = PropertySpec[name].default
		if not (isinstance(value, valueType) or value == default == None):
			raise ValueError(f"Property {name} only supports values of type {valueType}: {value!r}")
		self._map[name] = value
	
	@property
	@abstractmethod
	def ruleType(self) -> str:
		raise NotImplementedError
	
	def getSupportedPropertiesName(self) -> Sequence[str]:
		return tuple(p.name for p in PropertySpec.forRuleType(self.ruleType))
	
	@property
	def isOverride(self) -> bool:
		"""Whether this container overrides another one (eg. Criteria vs. Rule level).
		
		That is, whether it has parent maps other than the default values.
		"""
		return len(self._map.maps) > 2
	
	def isOverridden(self, name: str) -> bool:
		"""Whether the given property is set in the first map of this container."""
		return name in self._map.maps[0]
	
	def getInheritedValue(self, name: str) -> PropertyValue:
		"""The value the given property would have if not set in this container."""
		return self._map.parents[name]
	
	def dump(self) -> Mapping[str, PropertyValue]:
		"""Includes only the properties set in the first map, in the same order as their
		`PropertySpec` definitions.
		
		If this container overrides another one (see `isOverride`), all the supported
		overrides are included, even if equal to the inherited value: An explicit override
		keeps applying when the inherited value changes.
		Otherwise, the values equal to their default are omitted.
		"""
		map = self._map
		keepAll = self.isOverride
		return {
			name: map[name]
			for name in self.getSupportedPropertiesName()
			if name in map.maps[0] and (keepAll or map[name] != map.parents[name])
		}
	
	def load(self, data: Mapping[str, PropertyValue]) -> None:
		data = data.copy()
		while data:
			name, value = data.popitem()
			if name not in PROPERTY_NAMES:
				raise ValueError(f"Unexpected property: {name}={value!r}")
			if value is None and DEFAULT_VALUES[name] == "":
				# Tolerate `null` for text properties (eg. hand-edited JSON):
				# An empty text is the "no value" of these properties.
				value = ""
			setattr(self, name, value)


class RuleProperties(PropertiesBase):

	__slots__ = ("_rule",)

	def __init__(self, rule: "Rule"):
		self._rule = weakref.ref(rule)
		super().__init__({})

	@property
	def ruleType(self) -> str:
		rule = self._rule()
		if rule:
			return rule.type


class CriteriaProperties(RuleProperties):

	def __init__(self, criteria: "Criteria"):
		super().__init__(criteria.rule)
		self._map = criteria.rule.properties._map.new_child()
