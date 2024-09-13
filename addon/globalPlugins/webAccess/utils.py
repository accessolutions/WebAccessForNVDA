# globalPlugins/webAccess/utils.py
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


from functools import wraps

from logHandler import log


import addonHandler

try:
	from six import text_type
except ImportError:
	# NVDA version < 2018.3
	text_type = str


addonHandler.initTranslation()


def updateOrDrop(map, key, value, default=None):
	if (
		value == default
		or (isinstance(value, text_type) and not value.strip())
	):
		map.pop(key, None)
	else:
		map[key] = value


def notifyError(logMsg="", exc_info=True, stack_info=False):
	log.exception(logMsg, exc_info=exc_info, stack_info=stack_info)
	import gui
	import wx
	gui.messageBox(
		# Translators: A generic error message
		_("An error occured. See NVDA log for more details."),
		caption="WebAccess",
		style=wx.ICON_ERROR
	)


def guarded(func):
	"""Decorator to prevent exceptions raised by the decorated function to bubble up to the caller.
	
	Caught exceptions are notified and logged using `notifyError`.
	In most cases, this decorator should only be applied on wx event handlers to prevent further UI malfunction.
	"""

	@wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except Exception:
			notifyError(
				"Uncaught error while processing {!r}(args={!r}, kwargs={!r}".format(
					func, args, kwargs
				),
				stack_info=True
			)

	return wrapper


def logException(func):
	"""Decorator to log exceptions raised by the decorated function.
	
	Caught exceptions are re-raised after logging.
	This is just a convenience function to avoid cluttering code with loads of try/except wrapping blocks.
	It comes in especially handy to diagnose errors in property getters in conjunction with a custom
	`__getattr__`, where exceptions from the getters are silently trapped and interpreted as `AttributeError`.
	"""

	@wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except Exception:
			log.exception(stack_info=True)
			raise

	return wrapper

