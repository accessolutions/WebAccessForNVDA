# globalPlugins/webAccess/webModuleHandler/dataRecovery/recoveryFrom_0_6_to_0_8.py

# This file is part of Web Access for NVDA.
# Copyright (C) 2024 Accessolutions (https://accessolutions.fr)
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

"""
Script for upgrading a JSON-based WebModule from format version 0.6 to version 0.8.
"""


__version__ = "2024.08.24"
__authors__ = (
	"André-Abush Clause <a.clause@accessolutions.fr>",
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
)


from collections import Counter
from glob import glob
from copy import deepcopy
from typing import List, Dict, Any, Tuple
import json
import os


MARKER = "marker"
ZONE = "zone"
PAGE_TYPE = "pageType"
PARENT = "parent"
PAGE_TITLE_1 = "pageTitle1"
PAGE_TITLE_2 = "pageTitle2"
PRIORITY_TYPE = [PAGE_TYPE, PARENT, PAGE_TITLE_1, PAGE_TITLE_2, MARKER, ZONE]
RULE_TYPE_FIELDS: Dict[str, Tuple[str]] = {
	MARKER: (
		"autoAction",
		"multiple",
		"formMode",
		"skip",
		"sayName",
		"customName",
		"customValue",
		"mutation"
	),
	ZONE: (
		"autoAction",
		"formMode",
		"skip",
		"sayName",
		"customName",
		"customValue",
		"mutation"
	),
	PAGE_TITLE_1: ("customValue",),
	PAGE_TITLE_2: ("customValue",)
}
OVERRIDABLE_PROPERTIES: Dict[str, Any] = {
	"formMode": False,
	"multiple": False,
	"sayName": True,
	"skip": False,
	"autoAction": None,
	"mutation": None,
	"customName": None,
	"customValue": None,
	"gestures": {}
}

log_msgs = []


def merge_popular_structures(list_of_dicts):
	"""Merge a list of dictionaries by finding the most common value for each key.
	"""
	merged = {}
	keys = set(k for d in list_of_dicts for k in d.keys())
	for key in keys:
		# Assuming values are simple types; if complex types like lists or other dicts are included, further merging logic would be needed
		common_value, _ = Counter(d.get(key) for d in list_of_dicts if key in d).most_common(1)[0]
		merged[key] = common_value
	return merged


def get_popular_values(alternatives: List[Dict[str, Any]]) -> Dict[str, Any]:
	"""Compute the most frequent values for each property from a provided list of alternative configurations.
	
	When a property isn't present in an alternative, its value defaults to defined common defaults.

	Args:
		alternatives (list of dict): List of alternative property dictionaries.
	return:
		dict: Dictionary mapping property names to their most frequent values.
	"""
	popular_values: Dict[str, Any] = {}
	for prop, default_value in OVERRIDABLE_PROPERTIES.items():
		if prop in ("gestures"):
			continue
		counts: Counter = Counter(alt.get(prop, default_value) for alt in alternatives)
		popular_values[prop], _ = counts.most_common(1)[0]
	# Merge gestures
	gestures = merge_popular_structures([alt.get("gestures", {}) for alt in alternatives])
	if gestures:
		popular_values["gestures"] = gestures
	return popular_values


def process_alternatives(
	original_alternatives: List[Dict[str, Any]]
) -> Dict[str, Any]:
	"""
	Processes a list of rule alternatives, consolidating common properties and enforcing rules regarding
	acceptable properties based on the rule type.

	Args:
		alternatives (List[Dict[str, Any]]): List of rule alternatives to process.
	Returns:
		Dict[str, Any]: Consolidated rule configuration.
	"""
	alternatives = deepcopy(original_alternatives)
	if not alternatives:
		return {}

	# Ensure alternatives have all properties defined
	for alternative in alternatives:
		for prop in OVERRIDABLE_PROPERTIES:
			if prop not in alternative:
				alternative[prop] = OVERRIDABLE_PROPERTIES[prop]

	new_rule: Dict[str, Any] = {}
	rule_allowed_keys = ["name", "type", "comment", "gestures"]

	# Extract common properties to the rule level
	keep_keys = ("comment", "gestures")
	for rule_allowed_key in rule_allowed_keys:
		for alternative in alternatives:
			if rule_allowed_key in alternative and rule_allowed_key not in keep_keys:
				new_rule[rule_allowed_key] = alternative[rule_allowed_key]
				del alternative[rule_allowed_key]

	overridable_properties = list(RULE_TYPE_FIELDS.get(new_rule["type"], []))
	popular_values = get_popular_values(alternatives)
	new_rule.update(popular_values)

	# Remove properties that are not allowed in the rule level
	to_remove = []
	rule_allowed_keys.extend(overridable_properties)
	for prop in new_rule:
		if prop not in rule_allowed_keys:
			to_remove.append(prop)
	for k in to_remove:
		del new_rule[k]

	# Remove keys that have the same value as the most popular value from alternatives
	keys_to_remove = []
	for key, value in popular_values.items():
		for alternative in alternatives:
			if key in alternative and alternative.get(key) == value:
				keys_to_remove.append((alternative, key))

	for alternative, key in keys_to_remove:
		del alternative[key]

	# Remove invalid properties from alternatives
	old_keys = ["class", "createWidget", "name", "type", "user", "priority"]
	old_keys.extend([prop for prop in OVERRIDABLE_PROPERTIES if prop not in overridable_properties])
	for key in old_keys:
		for alternative in alternatives:
			if key in alternative:
				del alternative[key]

	# Move properties to a separate dictionary
	for container in [new_rule] + alternatives:
		properties = {}
		keys_to_move = [key for key in container if key in overridable_properties]
		for key in keys_to_move:
			properties[key] = container[key]
			del container[key]
		if properties:
			container["properties"] = properties

	# Check if remaining invalid properties exist in alternatives
	known_fields = [
		"role", "tag", "className", "id", "text", "states", "relativePath", "index", "src", "properties",
		"contextPageType", "contextParent", "contextPageTitle"
	]
	known_fields.extend(rule_allowed_keys)
	known_fields.extend(overridable_properties)

	for alternative in alternatives:
		for key in list(alternative.keys()):
			if key not in known_fields:
				raise ValueError(f"Unknown property: {key} in {alternative}")

	new_rule["criteria"] = alternatives
	return new_rule


def process_rules(old_rules: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
	"""Convert a list of previous version rules into a structured format following the new version's specifications.

	Args:
		old_rules (list of dict): List of old rule configurations.

	Returns:
		dict: Dictionary of new rule configurations, indexed by rule identifiers.
	"""
	old_rules.sort(key=lambda rule: (PRIORITY_TYPE.index(rule.get("type", "marker")), rule["name"], rule.get("priority", 0)))

	new_rules: Dict[str, Dict[str, Any]] = {}

	rules_done = []
	for old_rule in old_rules:
		if not all(k in old_rule for k in ("name", "type")):
			log_msgs.append(f"! Skipping rule without name or type: {old_rule}")
			continue

		if old_rule in rules_done:
			continue
		rule_name = old_rule["name"]
		rule_type = old_rule["type"]
		rule_id = rule_name
		for rule in rules_done:
			if rule["name"] == rule_name:
				rule_id = f"{rule_name} (*{rule_type})"
				log_msgs.append(f"! Duplicate rule name and type: {rule_name} {rule_type}, using ID: {rule_id}")
				break
		alternatives = [alt for alt in old_rules if alt.get("name") == rule_name and alt.get("type") == rule_type]
		new_rules[rule_id] = process_alternatives(alternatives)
		rules_done.extend(alternatives)
	return new_rules


def convert(data: dict):
	"""Convert in-place the provided data from the 0.6 format to the 0.8 format.
	
	Update the format version and process the rules.

	Args:
		data (dict): The original data dictionary to convert.
	"""
	for key, value in data.items():
		if key == "formatVersion":
			data[key] = "0.8-dev"
		elif key == "Rules":
			if not isinstance(value, list):
				if __name__ == "__main__":
					print("=> already done, skipping")
				return data

			expected_nb_rules = len(value)
			data[key] = process_rules(value)
		elif key not in ["WebModule", "log"]:
			raise ValueError(f"Unknown key: {key}")

	key_order = ["formatVersion", "WebModule", "Rules"]
	data = dict(sorted(data.items(), key=lambda k: key_order.index(k[0]) if k[0] in key_order else len(key_order)))
	nb_rules = 0
	for k, v in data["Rules"].items():
		nb_rules += len(v["criteria"])
	nb_missing_rules = expected_nb_rules - nb_rules
	if nb_missing_rules:
		log_msgs.append(f"! Missing {nb_missing_rules} rules (converted {nb_rules})")
	if log_msgs:
		comment = data.get("WebModule", {}).get("comment", "")
		if comment:
			comment += "\n\n"
		data["WebModule"]["comment"] = comment + "Migration report from 0.6 to 0.8:\n" + "\n".join(log_msgs)
		if __name__ == "__main__":
			print('\n'.join(log_msgs))
	
	recoverFrom_0_8_to_0_9(data)


# Copied rather than imported to support running this module as a script
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


def process_file(file: str) -> None:
	print(f"Processing file: {file}")
	with open(file, "r") as f:
		data = json.load(f)

	convert(data)

	with open(file, "w", encoding="UTF-8") as f:
		json.dump(data, f, indent=2)


def main():
	"""Load, convert, and save JSON data from a file.
	
	The input file is read, converted, and the result is written to the same file.
	"""
	path = args.path
	if os.path.isdir(path):
		files = glob(os.path.join(path, "*.json"))
		for file in files:
			process_file(file)
	elif os.path.isfile(path) and path.endswith(".json"):
		process_file(path)
	else:
		raise ValueError("Invalid input path.")

if __name__ == "__main__":
	import argparse
	parser = argparse.ArgumentParser(description="Convert a JSON-based web module from version 0.6 to version 0.8.")
	parser.add_argument("path", help="Path to the JSON file or directory containing JSON files to convert.")
	args = parser.parse_args()

	main()
