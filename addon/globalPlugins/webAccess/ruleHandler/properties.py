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
import sys
from typing import Any, TypeAlias
import weakref

from . import ruleTypes

import addonHandler


if sys.version_info[1] < 9:
    from typing import Iterator, Mapping, Sequence
else:
    from collections.abc import Iterator, Mapping, Sequence


addonHandler.initTranslation()


# The `type` statement was only added in Python 3.12
PropertyValue: TypeAlias = bool | str | type(None)


@dataclass
class PropertySpecValue:
	"""Value type for the `PropertySpec` enum
	"""
	
	__slots__ = (
		"ruleTypes", "valueType", "default", "displayName", "displayValueIfUndefined", "isRestrictedChoice"
	)
	
	ruleTypes: Sequence[str]  # Rule types for which the property is supported
	valueType: type(PropertyValue)
	default: PropertyValue
	displayName: str | Mapping[Sequence[str], str]  # Can be different by rule type
	displayValueIfUndefined: str
	isRestrictedChoice: bool  # Currently applies only in the editor
	
	def getDisplayName(self, ruleType) -> str:
		displayName = self.displayName
		if isinstance(displayName, str):
			return displayName
		return next(v for k, v in displayName.items() if ruleType in k)


class PropertySpec(Enum):
	
	autoAction = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=str,
		default=None,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Auto Actions"),
		# Translators: Displayed if no value is set for the "Auto Actions" property
		displayValueIfUndefined=pgettext("webAccess.action", "No action"),
		isRestrictedChoice=True
	)
	multiple = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.PARENT, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Multiple results"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False
	)
	formMode = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Activate form mode"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False
	)
	skip = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Skip with Page Down"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False
	)
	sayName = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=bool,
		default=False,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Speak rule name"),
		displayValueIfUndefined=None,  # Does not apply as there is a sensible default
		isRestrictedChoice=False
	)
	customName = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=str,
		default="",
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Custom name"),
		# Translators: Displayed if no value is set for a given rule property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty", "<undefined>"),
		isRestrictedChoice=False
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
		isRestrictedChoice=False
	)
	mutation = PropertySpecValue(
		ruleTypes=(ruleTypes.MARKER, ruleTypes.ZONE),
		valueType=str,
		default=None,
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Transform"),
		# Translators: Displayed if no value is set for the "Transform" rule property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty.mutation", "None"),
		isRestrictedChoice=True
	)
	subModule = PropertySpecValue(
		ruleTypes=(ruleTypes.ZONE,),
		valueType=str,
		default="",
		# Translators: The display name for a rule property
		displayName=pgettext("webAccess.ruleProperty", "Load sub-module"),
		# Translators: The displayed text if there is no value for the "Load sub-module" property
		displayValueIfUndefined=pgettext("webAccess.ruleProperty.subModule", "No"),
		isRestrictedChoice=False
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
	
	def dump(self) -> Mapping[str, PropertyValue]:
		"""Includes only the properties set in the first map, in the same order as their
		`PropertySpec` definitions.
		"""
		map = self._map
		return {
			name: map[name]
			for name in self.getSupportedPropertiesName()
			if name in map.maps[0] and map[name] != map.parents[name]
		}
	
	def load(self, data: Mapping[str, PropertyValue]) -> None:
		data = data.copy()
		while data:
			name, value = data.popitem()
			if name not in PROPERTY_NAMES:
				raise ValueError(f"Unexpected property: {name}={value!r}")
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

