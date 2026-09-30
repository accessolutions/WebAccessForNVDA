import os
import sys
import types
from unittest.mock import MagicMock

# Configure sys.path so webAccess is loaded as a package under globalPlugins
repoRoot = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
addonDir = os.path.join(repoRoot, "addon")
pluginsDir = os.path.join(addonDir, "globalPlugins")
webaccessDir = os.path.join(pluginsDir, "webAccess")

# Remove webaccessDir from sys.path if present, to avoid internal packages (e.g. gui, config)
# shadowing NVDA top-level modules
while webaccessDir in sys.path:
	sys.path.remove(webaccessDir)

if pluginsDir not in sys.path:
	sys.path.insert(0, pluginsDir)
if addonDir not in sys.path:
	sys.path.insert(0, addonDir)


class MockMeta(type):
	def __getattr__(cls, name):
		val = MagicMock()
		setattr(cls, name, val)
		return val

	def __iter__(cls):
		return iter([])

	def __getitem__(cls, key):
		return MagicMock()

	def __contains__(cls, item):
		return False


class MockBase(metaclass=MockMeta):
	def __init__(self, *args, **kwargs):
		pass

	def __getattr__(self, name):
		return MagicMock()

	def __call__(self, *args, **kwargs):
		if len(args) == 1 and callable(args[0]):
			return args[0]
		return MagicMock()

	def __iter__(self):
		return iter([])

	def __getitem__(self, key):
		return MagicMock()

	def __bool__(self):
		return True


class MockModule(types.ModuleType):
	def __init__(self, name):
		super().__init__(name)
		self.__path__ = []

	def __getattr__(self, item):
		cls = type(item, (MockBase,), {})
		setattr(self, item, cls)
		return cls


class NVDAMockFinder:
	def __init__(self):
		self._in_find = False

	def find_spec(self, fullname, path, target=None):
		if self._in_find:
			return None
		if fullname == "webAccess" or fullname.startswith("webAccess."):
			return None
		self._in_find = True
		try:
			for finder in sys.meta_path:
				if finder is self:
					continue
				if hasattr(finder, "find_spec"):
					spec = finder.find_spec(fullname, path, target)
					if spec is not None:
						return spec
			from importlib.machinery import ModuleSpec
			return ModuleSpec(fullname, self)
		finally:
			self._in_find = False

	def create_module(self, spec):
		return MockModule(spec.name)

	def exec_module(self, module):
		pass


if not any(isinstance(f, NVDAMockFinder) for f in sys.meta_path):
	sys.meta_path.insert(0, NVDAMockFinder())

import builtins  # noqa: E402
builtins.pgettext = lambda ctx, text: text
builtins._ = lambda text: text

import baseObject  # noqa: E402
import garbageHandler  # noqa: E402
import config  # noqa: E402

class AutoPropertyObject:
	def __getattr__(self, name):
		getter = getattr(type(self), f"_get_{name}", None)
		if getter is not None:
			return getter(self)
		raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

	def __setattr__(self, name, value):
		setter = getattr(type(self), f"_set_{name}", None)
		if setter is not None:
			setter(self, value)
		else:
			super().__setattr__(name, value)


baseObject.AutoPropertyObject = AutoPropertyObject
baseObject.ScriptableObject = type("ScriptableObject", (), {})
garbageHandler.TrackedObject = type("TrackedObject", (), {})

# Mock config.conf
class MockConf(dict):
	def __init__(self):
		super().__init__()
		self.spec = {}
		self.profiles = [{}]
		self.validator = MagicMock()

mockConfInstance = MockConf()
mockConfInstance["webAccess"] = {}
mockConfInstance["development"] = {}
config.conf = mockConfInstance
config.ConfigManager = MagicMock()
config.ConfigManager.BASE_ONLY_SECTIONS = set()
config.post_configReset = MagicMock()

import webAccess.ruleHandler  # noqa: E402
import webAccess.nodeHandler  # noqa: E402

# Support direct imports as ruleHandler and nodeHandler
if "ruleHandler" not in sys.modules:
	sys.modules["ruleHandler"] = webAccess.ruleHandler
if "nodeHandler" not in sys.modules:
	sys.modules["nodeHandler"] = webAccess.nodeHandler
