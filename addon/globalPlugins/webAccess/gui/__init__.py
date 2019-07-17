# globalPlugins/webAccess/gui/__init__.py
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

"""Web Access GUI."""

# Get ready for Python 3
from __future__ import absolute_import, division, print_function

__version__ = "2019.07.07"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import wx


try:
	import wx.lib.mixins.listctrl as listmix
except ImportError:
	# NVDA < 2016.4
	from . import wx_lib_mixins_listctrl as listmix


class ListCtrlAutoWidth(
		wx.ListCtrl,
		listmix.ListCtrlAutoWidthMixin):
	def __init__(self, *args, **kwargs):
		wx.ListCtrl.__init__(self, *args, **kwargs)
		listmix.ListCtrlAutoWidthMixin.__init__(self)
