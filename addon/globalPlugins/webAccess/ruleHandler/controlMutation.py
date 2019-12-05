# globalPlugins/webAccess/ruleHandler/controlMutation.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2019 Accessolutions (http://accessolutions.fr)
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

# Get ready for Python 3
from __future__ import absolute_import, division, print_function

__version__ = "2019.12.05"
__author__ = u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from collections import OrderedDict

import addonHandler
import controlTypes

from . import ruleTypes


addonHandler.initTranslation()


class Mutation(object):
	"""
	A template mutation to apply on a control as the result of a matched rule.
	"""
	__slots__ = ("attrs", "mutateName")
	
	def __init__(self, attrs, mutateName):
		self.attrs = attrs
		self.mutateName = mutateName


class MutatedControl(object):
	"""
	The effective mutations applied on a control as the result of matched rules.
	"""
	__slots__ = ("node", "attrs")
	
	def __init__(self, result):
		if not hasattr(result, "node"):
			raise TypeError("Only node results are supported")
		self.node = result.node
		self.attrs = {}
		self.apply(result)
	
	@property
	def controlId(self):
		return int(self.node.controlIdentifier)
	
	@property
	def start(self):
		return self.node.offset
	
	@property
	def end(self):
		return self.node.offset + self.node.size
	
	def apply(self, result):
		rule = result.rule
		mutation = rule.mutation
		if mutation is None:
			raise ValueError("No mutation defined for this rule: {}".format(
				rule.name
			))
		self.attrs.update(mutation.attrs)
		if mutation.mutateName:
			self.attrs["name"] = rule.label


MUTATIONS = {
	"button": Mutation({"role": controlTypes.ROLE_BUTTON}, False),
	# "level" is int in position info, but text in control field attributes...
	"heading.1": Mutation(
		{"role": controlTypes.ROLE_HEADING, "level": u"1"}, False
	),
	"heading.2": Mutation(
		{"role": controlTypes.ROLE_HEADING, "level": u"2"}, False
	),
	"heading.3": Mutation(
		{"role": controlTypes.ROLE_HEADING, "level": u"3"}, False
	),
	"heading.4": Mutation(
		{"role": controlTypes.ROLE_HEADING, "level": u"4"}, False
	),
	"heading.5": Mutation(
		{"role": controlTypes.ROLE_HEADING, "level": u"5"}, False
	),
	"heading.6": Mutation(
		{"role": controlTypes.ROLE_HEADING, "level": u"6"}, False
	),
	"labelled": Mutation({}, True),
	"landmark.region": Mutation({"landmark": "region"}, True),
	"landmark.nav.named": Mutation({"landmark": "navigation"}, True),
	"landmark.nav.unnamed": Mutation({"landmark": "navigation"}, False),
	"link": Mutation({"role": controlTypes.ROLE_LINK}, False),
	"section": Mutation({"role": controlTypes.ROLE_SECTION}),
	"table.data": Mutation({"table-layout": False}, False),
	"table.layout": Mutation({"table-layout": True}, False)
}

MUTATIONS_BY_RULE_TYPE = OrderedDict((
	(
		ruleTypes.MARKER, [
			"heading.1",
			"heading.2",
			"heading.3",
			"heading.4",
			"heading.5",
			"heading.6",
			"labelled",
			"section",
			"landmark.region",
			"landmark.nav.named",
			"landmark.nav.unnamed",
			"button",
			"link",
			"table.data",
			"table.layout",
		]
	),
	(
		ruleTypes.ZONE, [
			"labelled",
			"section",
			"landmark.region",
			"landmark.nav.named",
			"landmark.nav.unnamed",
			"table.data",
			"table.layout",
		]
	)
))

mutationLabels = OrderedDict((
	# Translators: The label for a control mutation.
	("button", pgettext("webAccess.controlMutation", "Button")),
	# Translators: The label for a control mutation.
	("heading.1", pgettext("webAccess.controlMutation", "Header level 1")),
	# Translators: The label for a control mutation.
	("heading.2", pgettext("webAccess.controlMutation", "Header level 2")),
	# Translators: The label for a control mutation.
	("heading.3", pgettext("webAccess.controlMutation", "Header level 3")),
	# Translators: The label for a control mutation.
	("heading.4", pgettext("webAccess.controlMutation", "Header level 4")),
	# Translators: The label for a control mutation.
	("heading.5", pgettext("webAccess.controlMutation", "Header level 5")),
	# Translators: The label for a control mutation.
	("heading.6", pgettext("webAccess.controlMutation", "Header level 6")),
	# Translators: The label for a control mutation.
	("labelled", pgettext("webAccess.controlMutation", "Add a label")),
	# Translators: The label for a control mutation.
	("section", pgettext("webAccess.controlMutation", "Section")),
	(
		"landmark.region",
		# Translators: The label for a control mutation.
		pgettext("webAccess.controlMutation", "Region")
	),
	(
		"landmark.nav.named",
		# Translators: The label for a control mutation.
		pgettext("webAccess.controlMutation", "Navigation (named)")
	),
	(
		"landmark.nav.unnamed",
		# Translators: The label for a control mutation.
		pgettext("webAccess.controlMutation", "Navigation (unnamed)")
	),
	# Translators: The label for a control mutation.
	("link", pgettext("webAccess.controlMutation", "Link")),
	(
		"table.data",
		pgettext(
			# Translators: The label for a control mutation.
			"webAccess.controlMutation", "Data table (Internet Explorer only)"
		)
	),
	# Translators: The label for a control mutation.
	("table.layout", pgettext("webAccess.controlMutation", "Layout table")),
))
