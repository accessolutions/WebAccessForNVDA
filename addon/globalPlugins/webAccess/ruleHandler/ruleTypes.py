# globalPlugins/webAccess/ruleHandler/ruleTypes.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2018 Accessolutions (http://accessolutions.fr)
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

# Keep compatible with Python 2
from __future__ import absolute_import, division, print_function

__version__ = "2018.12.14"
__author__ = u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from collections import OrderedDict

import addonHandler


addonHandler.initTranslation()


MARKER = "marker"
PAGE_TITLE_1 = "pageTitle1"
PAGE_TITLE_2 = "pageTitle2"
PAGE_TYPE = "pageType"
PARENT = "parent"
ZONE = "zone"


ruleTypeLabels = OrderedDict((
	# Translators: The label for a rule type.
	(PAGE_TITLE_1, _("Page main title")),
	# Translators: The label for a rule type.
	(PAGE_TITLE_2, _("Page secondary title")),
	# Translators: The label for a rule type.
	(PAGE_TYPE, _("Page type")),
	# Translators: The label for a rule type.
	(ZONE, _("Zone")),
	# Translators: The label for a rule type.
	(PARENT, _("Parent element")),
	# Translators: The label for a rule type.
	(MARKER, _("Marker")),
))
