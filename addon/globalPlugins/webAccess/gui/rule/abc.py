# globalPlugins/webAccess/gui/__init__.py
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


from gui import guiHelper

from .. import ContextualSettingsPanel


class RuleAwarePanelBase(ContextualSettingsPanel, metaclass=guiHelper.SIPABCMeta):
	
	def getRuleData(self):
		return self.context["data"].setdefault("rule", {})
	
	def getRuleManager(self):
		return self.context["webModule"].ruleManager
	
	def getRuleType(self):
		return self.getRuleData().get("type")
