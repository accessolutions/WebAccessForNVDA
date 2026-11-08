# tests/unit/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2026 Accessolutions (https://accessolutions.fr)
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

"""Unit tests runnable without NVDA.

Only the add-on modules that do not depend on NVDA at import time (apart from
`addonHandler` and the translation builtins, stubbed here) can be tested this way.

The add-on packages are registered in `sys.modules` without executing their
`__init__` modules (which require a running NVDA), so that their pure sub-modules
can be imported with regular import statements, e.g.:

	from webAccess.ruleHandler import properties

Run from the repository root:

	python -m unittest discover -s tests -t .
"""


import builtins
import os
import sys
import types


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ADDON_PACKAGE_DIR = os.path.join(ROOT, "addon", "globalPlugins", "webAccess")

# Sub-packages whose `__init__` must not be executed
_STUB_PACKAGES = (
	"webAccess",
	"webAccess.ruleHandler",
	"webAccess.webModuleHandler",
)


def _installNvdaStubs():
	if "addonHandler" not in sys.modules:
		addonHandler = types.ModuleType("addonHandler")
		addonHandler.initTranslation = lambda: None
		sys.modules["addonHandler"] = addonHandler
	if "logHandler" not in sys.modules:
		import logging
		logHandler = types.ModuleType("logHandler")
		logHandler.log = logging.getLogger("webAccess.tests")
		sys.modules["logHandler"] = logHandler
	for name, func in (
		("_", lambda s: s),
		("pgettext", lambda ctx, s: s),
		("ngettext", lambda s, p, n: s if n == 1 else p),
		("npgettext", lambda ctx, s, p, n: s if n == 1 else p),
	):
		if not hasattr(builtins, name):
			setattr(builtins, name, func)


def _installPackageStubs():
	for name in _STUB_PACKAGES:
		if name in sys.modules:
			continue
		path = os.path.join(ADDON_PACKAGE_DIR, *name.split(".")[1:])
		pkg = types.ModuleType(name)
		pkg.__path__ = [path]
		pkg.__package__ = name
		sys.modules[name] = pkg
		parent, _sep, child = name.rpartition(".")
		if parent:
			setattr(sys.modules[parent], child, pkg)


sys.dont_write_bytecode = True
_installNvdaStubs()
_installPackageStubs()
