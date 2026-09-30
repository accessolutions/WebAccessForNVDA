import ast
import builtins
import os
import sys
import types
import unittest
from unittest.mock import MagicMock


# Set up NVDA mock environment
class MockMeta(type):
	def __getattr__(cls, name):
		res = MockMeta(name, (MockBase,), {})
		setattr(cls, name, res)
		return res


class MockBase(metaclass=MockMeta):
	def __init__(self, *args, **kwargs):
		pass

	def __getattr__(self, name):
		return MockBase()


class MockModule(types.ModuleType):
	def __getattr__(self, name):
		res = MockMeta(name, (MockBase,), {})
		setattr(self, name, res)
		return res


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
		mod = MockModule(spec.name)
		mod.__path__ = []
		return mod

	def exec_module(self, module):
		pass


if not any(isinstance(f, NVDAMockFinder) for f in sys.meta_path):
	sys.meta_path.insert(0, NVDAMockFinder())

builtins.pgettext = lambda ctx, text: text
builtins._ = lambda text: text

pluginPath = os.path.abspath(
	os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins")
)
if pluginPath not in sys.path:
	sys.path.insert(0, pluginPath)

import versionInfo  # noqa: E402
versionInfo.version_year = 2024
versionInfo.version_major = 1
versionInfo.version_minor = 0
versionInfo.version_build = 0

from webAccess.ruleHandler import ruleTypes, controlMutation  # noqa: E402
from webAccess.ruleHandler import builtinRuleActions  # noqa: E402
from webAccess.gui import ruleEditor  # noqa: E402
from webAccess.webModuleHandler import webModule  # noqa: E402
from webAccess import nodeHandler  # noqa: E402
from webAccess import ast as wa_ast  # noqa: E402
from webAccess import presenter  # noqa: E402
from webAccess import overlay  # noqa: E402
from webAccess import webAppScheduler  # noqa: E402
from webAccess.store import webModule as storeWebModule  # noqa: E402


class TestPython2ConstructsRemoval(unittest.TestCase):
	def test_no_six_imports_in_webaccess(self):
		addon_dir = os.path.abspath(
			os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "webAccess")
		)
		six_usages = []
		for root, dirs, files in os.walk(addon_dir):
			# Skip binary wx directories
			if "python-2.7.16" in root or "python-3.7.5" in root or "__pycache__" in root:
				continue
			for file in files:
				if file.endswith(".py"):
					file_path = os.path.join(root, file)
					with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
						tree = ast.parse(f.read(), filename=file_path)
					for node in ast.walk(tree):
						if isinstance(node, ast.Import):
							for alias in node.names:
								if alias.name == "six" or alias.name.startswith("six."):
									six_usages.append((file_path, node.lineno, alias.name))
						elif isinstance(node, ast.ImportFrom):
							if node.module and (node.module == "six" or node.module.startswith("six.") or "six" in node.module.split(".")):
								six_usages.append((file_path, node.lineno, node.module))
		self.assertEqual(six_usages, [], f"Found six imports: {six_usages}")

	def test_no_ordereddict_in_webaccess_plugins(self):
		addon_dir = os.path.abspath(
			os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "webAccess")
		)
		ordered_dict_usages = []
		for root, dirs, files in os.walk(addon_dir):
			if "python-2.7.16" in root or "python-3.7.5" in root or "lib/json" in root or "__pycache__" in root:
				continue
			for file in files:
				if file.endswith(".py"):
					file_path = os.path.join(root, file)
					with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
						tree = ast.parse(f.read(), filename=file_path)
					for node in ast.walk(tree):
						if isinstance(node, ast.ImportFrom):
							if node.module == "collections":
								for alias in node.names:
									if alias.name == "OrderedDict":
										ordered_dict_usages.append((file_path, node.lineno))
		self.assertEqual(ordered_dict_usages, [], f"Found OrderedDict imports: {ordered_dict_usages}")

	def test_rule_type_labels_is_plain_dict(self):
		self.assertIs(type(ruleTypes.ruleTypeLabels), dict)
		self.assertIn(ruleTypes.MARKER, ruleTypes.ruleTypeLabels)
		self.assertIn(ruleTypes.PAGE_TITLE_1, ruleTypes.ruleTypeLabels)
		self.assertIn(ruleTypes.ZONE, ruleTypes.ruleTypeLabels)

	def test_control_mutation_labels_is_plain_dict(self):
		self.assertIs(type(controlMutation.MUTATIONS_BY_RULE_TYPE), dict)
		self.assertIs(type(controlMutation.mutationLabels), dict)
		self.assertIn("button", controlMutation.mutationLabels)
		self.assertIn("link", controlMutation.mutationLabels)
		self.assertIn(ruleTypes.MARKER, controlMutation.MUTATIONS_BY_RULE_TYPE)
		self.assertIn(ruleTypes.ZONE, controlMutation.MUTATIONS_BY_RULE_TYPE)

	def test_builtin_rule_actions_is_plain_dict(self):
		self.assertIs(type(builtinRuleActions), dict)
		self.assertIn("moveto", builtinRuleActions)
		self.assertIn("speak", builtinRuleActions)

	def test_rule_editor_fields_are_plain_dicts(self):
		self.assertIs(type(ruleEditor.RuleContextEditor.FIELDS), dict)
		self.assertIs(type(ruleEditor.RuleCriteriaEditor.FIELDS), dict)
		self.assertIs(type(ruleEditor.RulePropertiesEditor.FIELDS), dict)
		self.assertIs(type(ruleEditor.RulePropertiesEditor.RULE_TYPE_FIELDS), dict)

	def test_web_module_data_layer_dict(self):
		layer = webModule.WebModuleDataLayer("test", {"WebModule": {"name": "testModule"}}, "ref")
		self.assertEqual(layer.name, "test")
		self.assertIs(type(layer.data), dict)

	def test_literal_eval_with_python3_str(self):
		self.assertEqual(wa_ast.literal_eval("{'a': 1, 'b': [2, 3]}"), {'a': 1, 'b': [2, 3]})
		self.assertEqual(wa_ast.literal_eval("'hello'"), 'hello')
		self.assertEqual(wa_ast.literal_eval("123"), 123)

	def test_node_handler_chr_handling(self):
		self.assertEqual(chr(65), 'A')
		self.assertEqual(chr(0x20ac), '€')


if __name__ == "__main__":
	unittest.main()
