# globalPlugins/webAccess/webModuleHandler/dataRecovery/__init__.py
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


__authors__ = (
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
)


from collections import OrderedDict
import datetime
import inspect
import os
from pprint import pformat

import addonHandler
addonHandler.initTranslation()
from logHandler import getCodePath, log

from ...lib.packaging import version


try:
	from six import string_types, text_type
except ImportError:
	# NVDA version < 2018.3
	string_types = str
	text_type = str


class NewerFormatVersion(version.InvalidVersion):
	pass


def recover(data):
	formatVersion = data.get("formatVersion")
	# Ensure compatibility with data files prior to format versioning
	if formatVersion is None:
		formatVersion = ""
		recoverFromLegacyTo_0_1(data)
	formatVersion = version.parse(formatVersion)
	if formatVersion < version.parse("0.2"):
		recoverFrom_0_1_to_0_2(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.3"):
		recoverFrom_0_2_to_0_3(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.4"):
		recoverFrom_0_3_to_0_4(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.5"):
		recoverFrom_0_4_to_0_5(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.6"):
		recoverFrom_0_5_to_0_6(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.7-dev"):
		recoverFrom_0_6_to_0_9(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.8-dev"):
		recoverFrom_0_7_to_0_8(data)
		formatVersion = version.parse(data["formatVersion"])
	if formatVersion < version.parse("0.9-dev"):
		recoverFrom_0_8_to_0_9(data)
		formatVersion = version.parse(data["formatVersion"])
	
	from ..webModule import WebModule
	if formatVersion > WebModule.FORMAT_VERSION:
		raise NewerFormatVersion(
			"WebModule format version not supported: {}".format(formatVersion)
		)


def logRecovery(data, level, msg):
	codePath = getCodePath(inspect.currentframe().f_back)
	data.setdefault(
		"log", []
	).append((level, codePath, datetime.datetime.now().isoformat(), msg))


def recoverFromLegacyTo_0_1(data):
	# Back to the "WebAppHandler" days
	if "WebModule" not in data and "WebApp" in data:
		data["WebModule"] = data.pop("WebApp")
	if "Rules" not in data and "PlaceMarkers" in data:
		data["Rules"] = data.pop("PlaceMarkers")
	# Earlier versions supported only a single URL trigger
	url = data.get("WebModule", {}).get("url", None)
	if isinstance(url, string_types):
		data["WebModule"]["url"] = [url]
	# Custom labels for certain fields are not supported anymore
	# TODO: Re-implement custom field labels?
	if "FieldLabels" in data:
		logRecovery(data, log.WARNING, "FieldLabels not supported")
	data["formatVersion"] = "0.1"


def recoverFrom_0_1_to_0_2(data):
	rules = data.get("Rules", [])
	for rule in rules:
		if "context" in rule:
			rule["requiresContext"] = rule.pop("context")
		if "isContext" in rule:
			if rule.get("isContext"):
				rule["definesContext"] = "pageId"
			del rule["isContext"]
	data["formatVersion"] = "0.2"


def recoverFrom_0_2_to_0_3(data):
	rules = data.get("Rules", [])
	for rule in rules:
		if rule.get("autoAction") == "noAction":
			del rule["autoAction"]
	data["formatVersion"] = "0.3"


def recoverFrom_0_3_to_0_4(data):
	logLevel = log.INFO
	logMsgs = []
	markerKeys = (
		"gestures", "autoAction", "skip",
		"multiple", "formMode", "sayName",
	)
	splitTitles = []
	splitMarkers = []
	rules = data.get("Rules", [])
	for rule in rules:
		rule.setdefault("type", "marker")
		if rule.get("definesContext") and rule.get("isPageTitle"):
				split = rule.copy()
				del rule["isPageTitle"]
				split["type"] = "pageTitle1"
				split["name"] = "{} (title)".format(rule["name"])
				for key in markerKeys:
					try:
						del split[key]
					except KeyError:
						pass
				splitTitles.append(split)
				logLevel = max(logLevel, log.WARNING)
				logMsgs.append(
					'Rule "{}": Splitting "isPageTitle" from "definesContext".'
					.format(rule.get("name"))
				)
		elif rule.get("definesContext"):
			if rule["definesContext"] in ("pageId", "pageType"):
				rule["type"] = "pageType"
			else:
				rule["type"] = "parent"
			reason = "definesContext"
		elif rule.get("isPageTitle"):
			rule["type"] = "pageTitle1"
			reason = "isPageTitle"
		else:
			reason = None
		if reason:
			if (
				rule.get("gestures")
				or rule.get("autoAction")
				or not rule.get("skip", False)
			):
				split = rule.copy()
				del split[reason]
				split["type"] = "marker"
				split["name"] = "{} (marker)".format(rule["name"])
				splitMarkers.append(split)
				logLevel = max(logLevel, log.WARNING)
				logMsgs.append('Rule "{}": Splitting "{}" from marker.'.format(rule.get("name"), reason))
			for key in markerKeys:
				try:
					del rule[key]
				except KeyError:
					pass

	rules.extend(splitTitles)
	rules.extend(splitMarkers)

	for rule in rules:
		if rule.get("requiresContext"):
			rule["contextPageType"] = rule["requiresContext"]
			logLevel = max(logLevel, log.WARNING)
			logMsgs.append(
				'Rule "{}": '
				'Property "requiresContext" has been copied to '
				'"contextPageType", which is probably not accurate. '
				'Please redefine the required context.'
				.format(rule.get("name"))
			)

		for key in (
			"definesContext",
			"requiresContext",
			"isPageTitle"
		):
			try:
				del rule[key]
			except KeyError:
				pass

		# If it is upper-case (as in non-normalized identifiers),
		# `keyboardHandler.KeyboardInputGesture.getDisplayTextForIdentifier`
		# does not properly handle the NVDA key.
		gestures = rule.get("gestures", {})
		# Get ready for Python 3: dict.items will return an iterator.
		for key, value in list(gestures.items()):
			if "NVDA" not in key:
				continue
			del gestures[key]
			key = key.replace("NVDA", "nvda")
			gestures[key] = value
	if logMsgs:
		logRecovery(data, logLevel, "\n".join(logMsgs))
	data["formatVersion"] = "0.4"


def recoverFrom_0_4_to_0_5(data):
	# Rules: New "states" criterion (#5)
	# Rules: Ignore more whitespace in criteria expressions (19f772b)
	# Rules: Support composition of the "role" criterion (#6)
	rules = data.get("Rules", [])
	for rule in rules:
		if "role" in rule:
			rule["role"] = text_type(rule["role"])
	data["formatVersion"] = "0.5"


def recoverFrom_0_5_to_0_6(data):
	# Browsers compatibility: Handle "tag" case inconsistency (da96341)
	# Mutate controls (#9)
	rules = data.get("Rules", [])
	for rule in rules:
		if rule.get("tag"):
			rule["tag"] = rule["tag"].lower()
	data["formatVersion"] = "0.6"


def recoverFrom_0_6_to_0_7(data):
	# Multi-criteria
	logLevel = log.INFO
	logMsgs = []
	rules = data.get("Rules", [])
	if isinstance(rules, dict):
		# Already converted to multi criteria
		return

	rulesDict = OrderedDict()
	for rule in rules:
		rulesDict[rule["name"]] = None  # Use it first as an ordered Set
		criteria = {}
		for key in (
			"comment",
			"contextPageTitle",
			"contextPageType",
			"contextParent",
			"text",
			"role",
			"tag",
			"id",
			"className",
			"states",
			"src",
			"relativePath",
			"index"
		):
			if key in rule:
				criteria[key] = rule.pop(key)
		rule["criteria"] = [criteria]
		properties = {}
		for key in (
			"autoAction",
			"customName",
			"customValue",
			"formMode",
			"multiple",
			"sayName",
			"skip",
			"mutation"
		):
			if key in rule:
				properties[key] = rule.pop(key)
		if properties:
			rule["properties"] = properties
		# The following three keys were long abandonned but not removed from earlier versions
		rule.pop("class", None)
		rule.pop("createWidget", None)
		rule.pop("user", None)
	#log.info("rulesDict: {}".format(list(rulesDict.keys())))

	extra = OrderedDict()
	for name in list(rulesDict.keys()):
		alternatives = [rule for rule in rules if rule["name"] == name]
		assert alternatives
		if len(alternatives) == 1:
			# Case 1 - Single set of criteria: Keep as-is
			rule = alternatives[0]
			rule.pop("priority", None)
			rulesDict[name] = rule
			continue
#		if not any((True for rule in alternatives if "priority" in rule)):
		noPriority = not any((True for rule in alternatives if "priority" in rule))
# 		for rule1 in alternatives:
# 			for rule2 in alternatives:
# 				if rule1 is rule2:
# 					continue
# 				if rule1.get("gestures") != rule2.get("gestures"):
# 					sameGestures = False
# 					break
# 			else:
# 				continue
# 			break
# 		else:
# 			sameGestures = True

		class HashableDict(dict):  # Utility class to help compare dictionaries
			def __sortedDump(self):
				return tuple((k, self[k]) for k in sorted(self))
			def __hash__(self):
				return hash(self.__sortedDump())
			def __eq__(self, other):
				return self.__sortedDump() == other.__sortedDump()
			@classmethod
			def areUnique(cls, dicts):
				dicts = [cls(dict) for dict in dicts]
				return len(dicts) == len(set(dicts))

		# Check gestures only if no priority
		sameGestures = noPriority and not HashableDict.areUnique([rule.get("gestures", {}) for rule in alternatives])
		if not sameGestures:
			log.warning(f"{[rule.get('gestures', {}) for rule in alternatives]}")
		if noPriority and not sameGestures:
			# Case 2 - No priority: Create a unique name by adding a suffix
			format = "{{}}_#{{:0{}}}".format(len(str(len(alternatives))))
			offset = 0
			for index, rule in enumerate(alternatives):
				while True:
					extraName = format.format(rule["name"], index + offset)
					if extraName not in rulesDict and extraName not in extra:
						break
					offset += 1
				rule["name"] = extraName
				logLevel = max(logLevel, log.WARNING)
				logMsgs.append('Rule "{}" #{}: Renamed to "{}".'.format(name, index, extraName))
				extra[extraName] = rule
			del rulesDict[name]
			continue
		# Case 3 - At least one alternative holds a priority
		# Step 1: Missing priority defaults to 0
		for index, rule in enumerate(alternatives):
			if "priority" not in rule:
				rule["priority"] = 0
				logLevel = max(logLevel, log.WARNING)
				logMsgs.append(
					'Rule "{}" #{}: '
					"Missing priority considered as 0."
					.format(rule["name"], index)
				)
		# Step 2: Sort alternatives by priority and index
		alternatives = [rule for (index, rule) in sorted(
			enumerate(alternatives),
			key=lambda item: (item[1]["priority"], index)
		)]
		# Step 3: Merge
		rule = alternatives.pop(0)
		rule.pop("priority", None)
		ruleComments = []
		for index, alternative in enumerate(alternatives):
			properties = OrderedDict()
			alternativeComments = []
			for key, value in rule.get("properties", {}).items():
				if key in ("criteria", "priority", "comment"):
					continue
				altValue = alternative.get("properties", {}).get(key)
				if altValue != value:
					missing = key not in alternative
					if altValue is not None and key in ("autoAction", "customName", "customValue", "formMode", "multiple", "sayName", "skip", "mutation"):
						if missing:
							properties[key] = altValue
						continue
					alternativeComments.append(
						"{!r} was {} instead of {!r}"
						.format(key, repr(altValue) if not missing else "missing", value)
					)
			for key, altValue in list(alternative.items()):
				if key in rule or key in (
					"criteria", "priority", "comment",
					"autoAction", "customName", "customValue", "formMode", "multiple", "sayName", "skip", "mutation"
				):
					continue
				alternativeComments.append(
					"{!r} was {!r} instead of missing"
					.format(key, altValue)
				)
			criteria = alternative["criteria"][0]
			if properties:
				criteria["properties"] = {}
				criteria["properties"].update(properties)
			if alternativeComments:
				if criteria.get("comment"):
					criteria["comment"] += "\n\n"
				else:
					criteria["comment"] = ""
				criteria["comment"] += (
					_("Recovered from format version {}").format("0.6")
					+ "\n"
					+ "\n".join(alternativeComments)
				)
				ruleComments.append(
					"Alternative {}:\n\t{}"
					.format(index + 1, "\n\t".join(alternativeComments))
				)
			rule["criteria"].append(criteria)
		if ruleComments:
			rule["comment"] = (
				_("Recovered from format version {}").format("0.6")
				+ "\n"
				+ "\n".join(ruleComments)
			)
			logLevel = max(logLevel, log.WARNING)
			logMsgs.append(
				'Rule "{}":\n\t{}'
				.format(rule["name"], "\n\t".join(ruleComments))
			)
		rulesDict[name] = rule
	rulesDict.update(extra)
	rules = data["Rules"] = rulesDict
	data["Rules"] = rules
	#log.info("after: {}".format(rules))
	if logMsgs:
		logRecovery(data, logLevel, "\n".join(logMsgs))
	data["formatVersion"] = "0.7-dev"


def recoverFrom_0_6_to_0_9(data):
	# Overridden properties and gestures
	from .from_0_6_to_0_9 import convert
	convert(data)


def recoverFrom_0_7_to_0_8(data):
	RULE_TYPE_FIELDS = {
		"marker": (
			"autoAction",
			"multiple",
			"formMode",
			"skip",
			"sayName",
			"customName",
			"customValue",
			"mutation"
		),
		"zone": (
			"autoAction",
			"formMode",
			"skip",
			"sayName",
			"customName",
			"customValue",
			"mutation"
		),
		"pageTitle1": ("customValue"),
		"pageTitle2": ("customValue")
	}
	validProperties = ("autoAction", "multiple", "formMode", "skip", "sayName", "customName", "customValue", "mutation")
	rules = data.get("Rules", [])
	for ruleData in rules.values():
		ruleType = ruleData.get("type")
		ruleTypeProperties = RULE_TYPE_FIELDS.get(ruleType, ())
		newRuleProperties = {}
		for key in validProperties:
			if key in ruleData and key not in ruleTypeProperties:
				ruleData.pop(key)
			elif key in ruleData:
				newRuleProperties[key] = ruleData.pop(key)
		if newRuleProperties:
			ruleData["properties"] = newRuleProperties
		for criterion in ruleData.get("criteria", []):
			newCriterionProperties = {}
			for key in validProperties:
				if key in criterion and key not in ruleTypeProperties:
					criterion.pop(key)
				elif key in criterion:
					newCriterionProperties[key] = criterion.pop(key)
			if newCriterionProperties:
				criterion["properties"] = newCriterionProperties
	data["formatVersion"] = "0.8-dev"


def recoverFrom_0_8_to_0_9(data):
	# Properties are only stored if they differ from the default value.
	# Choice properties default to None. Text properties default to the empty string.
	# These defaults may have been previously stored interchangeably.
	# A None or empty value in a Criteria Property now overrides a defined value
	# at Rule level.
	from collections import ChainMap
	DEFAULTS = {
		"autoAction": None,
		"multiple": False,
		"formMode": False,
		"skip": False,
		"sayName": False,
		"customName": "",
		"customValue": "",
		"mutation": None,
	}
	
	def process(container, chainMap):
		container["properties"] = {
			k: v
			for k, v in chainMap.items()
			if v not in (None, "") and v != chainMap.parents[k]
		}
		if not container["properties"]:
			del container["properties"]
	
	for rule in data.get("Rules", {}).values():
		ruleMap = ChainMap(rule.get("properties", {}), DEFAULTS)
		process(rule, ruleMap)
		for crit in rule.get("criteria", []):
			process(crit, ruleMap.new_child(crit.get("properties", {})))
	
	data["formatVersion"] = "0.9-dev"
