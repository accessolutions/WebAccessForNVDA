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


__authors__ = (
	"Julien Cochuyt <j.cochuyt@accessolutions.fr>",
	"Frédéric Brugnot <f.brugnot@accessolutions.fr>",
	"André-Abush Clause <a.clause@accessolutions.fr>",
)


from functools import wraps

from logHandler import log


import addonHandler


addonHandler.initTranslation()


def updateOrDrop(map, key, value, default=None):
	if (
		value == default
		or (isinstance(value, str) and not value.strip())
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


def translate(text):
	"""
	Use translation from NVDA core.
	
	When this function is used instead of the usual `_` gettext function,
	SCons ignores it and does not create a new entry in the generated `.pot`
	file.
	"""
	# `addonHandler.initTranslation` stores `_` as a module attribute.
	# `builtins` contains the one used by NVDA itself.
	import builtins
	return builtins._(text)


def tryInt(value):
	"""Try to convert the given value to `int`
	
	If the conversion fails, the value is returned unchanged.
	"""
	try:
		return int(value)
	except ValueError:
		return value


def getCharFromKeyEvent(evt):
	import ctypes
	import wx
	
	vkCode = evt.RawKeyCode
	scanCode = ctypes.windll.user32.MapVirtualKeyW(vkCode, 0)  # MAPVK_VK_TO_VSC
	
	mods = evt.GetModifiers()
	state = (ctypes.c_ubyte * 256)()
	if (mods | wx.MOD_SHIFT) == mods:
		state[0x10] = 0x80 # VK_SHIFT
	if (mods | wx.MOD_CONTROL) == mods:
		state[0x11] = 0x80 # VK_CONTROL
	if (mods | wx.MOD_ALT) == mods:
		state[0x12] = 0x80 # VK_MENU (Alt key)
	if (mods | wx.MOD_WIN) == mods:
		state[0x5B] = 0x80 # VK_LWIN

	buffer = ctypes.create_unicode_buffer(2)
	if ctypes.windll.user32.ToUnicode(vkCode, scanCode, state, buffer, len(buffer), 0) > 0:
		return buffer.value
	else:
		return None
