# globalPlugins/webAccess/gui/rule/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (http://accessolutions.fr)
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


from typing import Any

import wx

import addonHandler
import gui
from logHandler import log

from ...ruleHandler.properties import normalizeRuleData
from ...ruleHandler.references import renameReferences
from ... import webModuleHandler
from .. import ValidationError

from collections.abc import Mapping


addonHandler.initTranslation()


def createMissingSubModule(
		context: Mapping[str, Any],
		data: Mapping[str, Any],
		parent: wx.Window
	) -> bool:
	"""Create the missing SubModule from Rule or Criteria data
	
	If a SubModule is specified in the provided data, it is looked-up in the catalog.
	If it is missing from the catalog, the user is prompted for creating it.
	
	This function returns:
	 - `None` if no creation was necessary or if the user declined the prompt.
	 - `False` if the user canceled the prompt or if the creation failed or has been canceled.
	 - `True` if the creation succeeded.
	"""
	name = data.get("properties", {}).get("subModule")
	if not name:
		return None
	from ...webModuleHandler import getCatalog
	if any(meta["name"] == name for ref, meta in getCatalog()):
		return True
	res = gui.messageBox(
		message=(
			# Translators: A prompt for creation of a missing SubModule
			_(f"""SubModule {name} could not be found.

Do you want to create it now?""")
		),
		style=wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
		parent=parent,
	)
	if res is wx.NO:
		return None
	elif res is wx.CANCEL:
		return False
	context = context.copy()
	context["new"] = True
	context["data"] = {"webModule": {"name": name, "subModule": True}}
	from ..webModule.editor import show
	res = show(context, parent)
	if res:
		newName = context["webModule"].name
		if newName != name:
			data["properties"]["subModule"] = newName
	return res


def propagateRuleRename(
		mgr: "RuleManager",
		rule: "Rule",
		data: dict[str, Any],
		parent: wx.Window
	) -> bool | None:
	"""Offer to update the references to a rule being renamed.

	`data` is the new data of the rule, its name being the new name.
	The rules of the same layer referring to the old name are updated upon confirmation.
	The rules of other layers (eg. read-only add-on layers) are listed, but not updated.

	Returns:
	 - `None` if there is no reference to update or the user declined.
	 - `True` if the references have been updated.
	 - `False` if the user cancelled.
	"""
	oldName, newName = rule.name, data["name"]
	dependents = {
		dependent: refs
		for dependent, refs in mgr.getDependents(oldName).items()
		if dependent is not rule
	}
	if not dependents:
		return None
	sameLayer = sorted(
		(dependent for dependent in dependents if dependent.layer == rule.layer),
		key=lambda dependent: dependent.name
	)
	otherLayers = sorted(
		(dependent for dependent in dependents if dependent.layer != rule.layer),
		key=lambda dependent: (dependent.layer, dependent.name)
	)
	parts = []
	if sameLayer:
		parts.append(
			# Translators: A prompt upon renaming a rule referred to by other rules
			_('The rule "{oldName}" is referred to by the following rules:\n{rules}').format(
				oldName=oldName,
				rules="\n".join(f"  - {dependent.name}" for dependent in sameLayer),
			)
		)
	if otherLayers:
		parts.append(
			# Translators: A mention upon renaming a rule referred to by rules that cannot be updated
			_("Rules of other layers referring to it, which will not be updated:\n{rules}").format(
				rules="\n".join(
					f"  - {dependent.name} ({dependent.layer})" for dependent in otherLayers
				),
			)
		)
	if webModuleHandler.hasCustomModule(mgr.webModule.name):
		parts.append(
			# Translators: A mention upon renaming a rule of a WebModule having Python code
			_("The Python code of this WebModule may also refer to this rule by its name.")
		)
	if sameLayer:
		# Translators: A prompt upon renaming a rule referred to by other rules
		parts.append(_('Update these references to "{newName}"?').format(newName=newName))
		style = wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
	else:
		# Translators: A prompt upon renaming a rule referred to by other rules
		parts.append(_("Rename anyway? These references will be considered as not matched."))
		style = wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
	res = gui.messageBox(
		"\n\n".join(parts),
		# Translators: The title of a prompt upon renaming a rule
		caption=_("Rule renamed"),
		style=style,
		parent=parent,
	)
	if res == wx.CANCEL or (not sameLayer and res != wx.YES):
		return False
	if res != wx.YES or not sameLayer:
		return None
	# A rule referring to itself follows its own renaming
	renameReferences(data, oldName, newName)
	for dependent in sameLayer:
		dependentData = dependent.dump()
		renameReferences(dependentData, oldName, newName)
		mgr.removeRule(dependent)
		mgr.loadRule(dependent.layer, dependent.name, dependentData)
	return True


def saveRule(
		context: Mapping[str, Any],
		data: Mapping[str, Any],
		parent: wx.Window
	) -> bool:
	ruleMutation = data.get("properties", {}).get("mutation")
	if any(
		set(critData.get("selector", {}).keys()) == {"start", "end"}
		# The Transform property might be defined or cancelled by the alternative
		and critData.get("properties", {}).get("mutation", ruleMutation)
		for critData in data.get("criteria", [])
	):
		if gui.messageBox(
			# Translators: A warning message on the Rule editor
			_(
				'''The "Transform" property is not supported with free zones (two sets of criteria).

Do you want to proceed anyway?
'''
			),
			# Translators: The title of a message dialog
			caption=_("Warning"),
			style=wx.ICON_WARNING | wx.YES_NO | wx.CANCEL | wx.NO_DEFAULT
		) != wx.YES:
			raise ValidationError()  # Cancels closing of the dialog
	
	# Remove gesture bindings and properties not supported for the selected Rule Type.
	# This needs to be done here rather than
	#  - upon changing the Rule Type for easier non-destructive cycle-through
	#    the different types,
	#  - in the panel's doSave because the Rule Type might have been changed
	#    without even instantiating any other panel.
	# Criteria (alternative) level overrides are kept as is, even if falsy
	# (eg. "No action" cancelling the Rule level Auto Action).
	normalizeRuleData(data)

	mgr = context["webModule"].ruleManager
	if context.get("new"):
		layerName = None
	else:
		rule = context["rule"]
		layerName = rule.layer
	webModule = webModuleHandler.getEditableWebModule(mgr.webModule, layerName=layerName)
	if not webModule:
		raise ValidationError()  # Cancels closing of the dialog
	# The sub-module might be defined at Rule level or by any alternative
	for container in [data] + data.get("criteria", []):
		if createMissingSubModule(context, container, parent) is False:
			raise ValidationError()  # Cancels closing of the dialog
	if not context.get("new") and data["name"] != rule.name:
		if propagateRuleRename(mgr, rule, data, parent) is False:
			raise ValidationError()  # Cancels closing of the dialog
	if context.get("new"):
		layerName = webModule.getWritableLayer().name
	else:
		mgr.removeRule(rule)
	context["rule"] = mgr.loadRule(layerName, data["name"], data)
	webModule.getLayer(layerName, raiseIfMissing=True).dirty = True
	if not webModuleHandler.save(webModule, layerName=layerName):
		raise ValidationError()  # Cancels closing of the dialog


def showRuleWizardOrEditor(
		context: Mapping[str, Any],
		parent: wx.Window | None = None
	) -> bool:
	"""Open the rule wizard or editor according to the user's UI mode preference."""
	from . import editor, wizard
	from ...config import RuleWizardMode, UiMode, getUiMode
	canUseWizard = editor.supportsSimpleMode(context)
	if getUiMode(UiMode.RULE_WIZARD, canPrefer=canUseWizard) == RuleWizardMode.WIZARD:
		return wizard.show(context, parent=parent)
	return editor.show(context, parent=parent)
