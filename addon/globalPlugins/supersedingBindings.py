# globalPlugins/supersedingBindings.py
# -*- coding: utf-8 -*-

# This file is part of Superseding Bindings for NVDA.
# Copyright (C) 2021 Accessolutions (https://accessolutions.fr)
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

"""Handle user customization of superseding default gesture script bindings

In NVDA, when two base classes of the same given type bind the same default
gesture to different scripts, the user is unable to remove the superseding
binding and use the superseded one.

For example, the WebAccess add-on binds its Global Results Quick Navigation
scripts to `PageUp`/`PageDown` on its overlay to
`BrowseModeDocumentTreeInterceptor`.
These default bindings supersede the default bindings on `CursorManager`
to scripts handling navigation by page.
Because `CursorManager` is a base class of `BrowseModeDocumentTreeInterceptor`,
if the user removes the superseding bindings using the Input Gestures dialog,
both default bindings are effectively canceled.

The corresponding entries in the user's `gestures.ini` file look like:
```
[globalPlugins.webAccess.overlay.WebAccessBmdti]
None = kb:pageup
None = kb:pagedown
```

While the user most likely expected:
```
[globalPlugins.webAccess.overlay.WebAccessBmdti]
moveByPage_back = kb:pageup
moveByPage_forward = kb:pagedown
```

This Global Plugin handles reaching this result.

It does so by adding support to a new `supersedes` script attribute which
holds a mapping of gesture normalized identifiers to the name of the
scripts whose default binding are being superseded.

```
script_quickNavToNextResultLevel2.supersedes = {"kb:pagedown": "moveByPage_forward"}
```
"""


__version__ = "2021.03.29"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"
__license__ = "GPL"


import sys

import globalPluginHandler
import inputCore
from logHandler import log


MONKEY_PATCH_ATTR_NAME = "_supersedingBindings__monkeyPatched"


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super().__init__()
		# Monkey-patch the User Global Gesture Map
		userGestureMap = inputCore.manager.userGestureMap
		userGestureMap_add.super = userGestureMap.add
		userGestureMap_remove.super = userGestureMap.remove
		if not getattr(userGestureMap, MONKEY_PATCH_ATTR_NAME, False):		
			userGestureMap.add = userGestureMap_add.__get__(userGestureMap)
			userGestureMap.remove = userGestureMap_remove.__get__(userGestureMap)
			# Mark the object as patched to avoid reapplying on plugins reload
			setattr(userGestureMap, MONKEY_PATCH_ATTR_NAME, True)


def getSupersededBinding(moduleName, className, scriptName, gestureIdentifier):
	try:
		module = sys.modules[moduleName]
		cls = getattr(module, className)
		func = getattr(cls, "script_{}".format(scriptName))
		return getattr(func, "supersedes", {}).get(gestureIdentifier)
	except (KeyError, AttributeError):
		log.exception()
		return None


def userGestureMap_add(self, gesture, module, className, script, replace=False):
	# Remove the eventual previous entry to support default bindings being updated upstream
	if not (replace or script is None):
		superseded = getSupersededBinding(module, className, script, gesture)
		if superseded:
			try:
				self.remove(gesture, module, className, superseded)
			except ValueError:
				pass
	userGestureMap_add.super(gesture, module, className, script, replace=replace)


def userGestureMap_remove(self, gesture, module, className, script):
	try:
		userGestureMap_remove.super(gesture, module, className, script)
	except ValueError:
		# This entry was not in the map
		if script is None:
			raise
		superseded = getSupersededBinding(module, className, script, gesture)
		if superseded:
			# Add the superseded script name. The Input Gestures dialog would
			# add None instead if the ValueError was not caught.
			self.add(gesture, module, className, superseded)
		else:
			raise
