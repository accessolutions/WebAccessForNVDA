# noqa: E402
import os
import sys
import typing
from unittest.mock import MagicMock
import unittest

# Set up mock NVDA environment before imports
NVDA_PREFIXES = (
	"wx", "addonHandler", "api", "baseObject", "browseMode",
	"controlTypes", "core", "eventHandler", "garbageHandler",
	"inputCore", "logHandler", "mouseHandler", "NVDAObjects",
	"queueHandler", "scriptHandler", "speech", "textInfos",
	"ui", "virtualBuffers", "winUser", "NVDAHelper",
	"globalPluginHandler", "versionInfo", "config", "gui"
)


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
		mod = MagicMock()
		mod.__name__ = spec.name
		mod.__path__ = []
		return mod

	def exec_module(self, module):
		pass


sys.meta_path.insert(0, NVDAMockFinder())

# Python 3.9 compatibility for typing.TypeAlias if needed
if not hasattr(typing, "TypeAlias"):
	typing.TypeAlias = typing.Any

# NVDA base classes
import baseObject  # noqa: E402
import garbageHandler  # noqa: E402

baseObject.AutoPropertyObject = type("AutoPropertyObject", (), {})
baseObject.ScriptableObject = type("ScriptableObject", (), {})
garbageHandler.TrackedObject = type("TrackedObject", (), {})

import builtins  # noqa: E402

builtins.pgettext = lambda ctx, text: text
builtins._ = lambda text: text

# Add plugin path
pluginPath = os.path.abspath(
	os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins")
)
if pluginPath not in sys.path:
	sys.path.insert(0, pluginPath)

from webAccess.ruleHandler import getSimpleSearchKwargs  # noqa: E402
from webAccess.nodeHandler import NodeField  # noqa: E402


class MockCriteriaWithDump:
	def __init__(self, data):
		self._data = data

	def dump(self):
		return self._data


class TestGetSimpleSearchKwargs(unittest.TestCase):
	def test_plain_dict(self):
		criteria = {"role": 8, "tag": "div"}
		kwargs = getSimpleSearchKwargs(criteria)
		self.assertEqual(kwargs.get("eq_role#0"), [8])
		self.assertEqual(kwargs.get("eq_tag#0"), ["div"])

	def test_object_with_dump(self):
		criteria = MockCriteriaWithDump({"role": 8, "tag": "button"})
		kwargs = getSimpleSearchKwargs(criteria)
		self.assertEqual(kwargs.get("eq_role#0"), [8])
		self.assertEqual(kwargs.get("eq_tag#0"), ["button"])

	def test_keyword_criteria(self):
		kwargs = getSimpleSearchKwargs(criteria={"tag": "span"})
		self.assertEqual(kwargs.get("eq_tag#0"), ["span"])

	def test_keyword_critData(self):
		kwargs = getSimpleSearchKwargs(critData={"tag": "a"})
		self.assertEqual(kwargs.get("eq_tag#0"), ["a"])

	def test_empty_criteria(self):
		self.assertEqual(getSimpleSearchKwargs({}), {})
		self.assertEqual(
			getSimpleSearchKwargs(MockCriteriaWithDump({})),
			{}
		)

	def test_raise_on_unsupported(self):
		with self.assertRaises(ValueError):
			getSimpleSearchKwargs(
				{"unsupportedAttr": "value"},
				raiseOnUnsupported=True
			)

		kwargs = getSimpleSearchKwargs(
			{"unsupportedAttr": "value", "tag": "div"},
			raiseOnUnsupported=False
		)
		self.assertEqual(kwargs, {"eq_tag#0": ["div"]})

	def test_invalid_type_raises_type_error(self):
		with self.assertRaises(TypeError):
			getSimpleSearchKwargs([1, 2, 3])

	def test_none_criteria_raises_value_error(self):
		with self.assertRaises(ValueError):
			getSimpleSearchKwargs(None)


class DummyNode(NodeField):
	def __init__(self, name, parent=None, role="8", tag="div"):
		self.name = name
		self._parent = parent
		self.role = role
		self.tag = tag
		self.children = []
		self.index = 0
		self.offset = 0

	@property
	def parent(self):
		return self._parent

	def searchNode(self, **kwargs):
		for key, val in kwargs.items():
			if key.startswith("eq_role"):
				if int(self.role) not in val:
					return []
			elif key.startswith("eq_tag"):
				if self.tag not in val:
					return []
		return [self]


class TestNodeFieldWalkWithCriteria(unittest.TestCase):
	def setUp(self):
		self.grandparent = DummyNode(
			"grandparent",
			role="10",
			tag="section"
		)
		self.parent = DummyNode(
			"parent",
			parent=self.grandparent,
			role="8",
			tag="div"
		)
		self.child = DummyNode(
			"child",
			parent=self.parent,
			role="0",
			tag="span"
		)

	def test_walk_uppercase_with_criteria_dict(self):
		result = self.child.walk('U{"role": 8}')
		self.assertEqual(result, self.parent)

	def test_walk_check_step_with_criteria_dict(self):
		result = self.parent.walk('c{"role": 8}')
		self.assertEqual(result, self.parent)

		result = self.child.walk('c{"role": 8}')
		self.assertIsNone(result)

	def test_walk_multiple_steps_with_criteria(self):
		result = self.child.walk('U{"role": 8}u')
		self.assertEqual(result, self.grandparent)

	def test_walk_malformed_criteria_returns_none(self):
		result = self.child.walk('U{not valid syntax}')
		self.assertIsNone(result)

	def test_walk_unsupported_criteria_returns_none(self):
		result = self.child.walk('U{"invalidAttribute": "test"}')
		self.assertIsNone(result)


if __name__ == "__main__":
	unittest.main()
