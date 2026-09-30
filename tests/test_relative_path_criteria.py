import unittest
import weakref
from unittest.mock import MagicMock

from webAccess.ruleHandler import getSimpleSearchKwargs, Selector
from webAccess.nodeHandler import NodeField, DeepCopyWeakRef


class CriteriaWithDump:
	"""A criteria-like object providing a dump() method."""

	def __init__(self, data):
		self._data = data

	def dump(self):
		return self._data


class TestGetSimpleSearchKwargs(unittest.TestCase):
	"""Unit tests verifying getSimpleSearchKwargs supports both dicts and criteria objects."""

	def test_plain_dict_empty(self):
		self.assertEqual(getSimpleSearchKwargs({}), {})

	def test_plain_dict_single_criterion(self):
		result = getSimpleSearchKwargs({"role": 8})
		self.assertEqual(result, {"eq_role#0": [8]})

	def test_plain_dict_multiple_criteria(self):
		result = getSimpleSearchKwargs({
			"role": 8,
			"tag": "button",
			"id": "my-btn",
		})
		self.assertEqual(result["eq_role#0"], [8])
		self.assertEqual(result["eq_tag#0"], ["button"])
		self.assertEqual(result["eq_id#0"], ["my-btn"])

	def test_plain_dict_text_criteria(self):
		result = getSimpleSearchKwargs({"text": "Hello"})
		self.assertEqual(result, {"in_text": "Hello"})

		result_prev = getSimpleSearchKwargs({"text": "<Previous"})
		self.assertEqual(result_prev, {"in_prevText": "Previous"})

	def test_plain_dict_relative_path(self):
		result = getSimpleSearchKwargs({"relativePath": "u"})
		self.assertEqual(result, {"relativePath": "u"})

	def test_plain_dict_ignored_context_properties(self):
		result = getSimpleSearchKwargs({
			"contextPageTitle": "Title",
			"contextPageType": "Type",
			"contextParent": "Parent",
			"role": 8,
		})
		self.assertEqual(result, {"eq_role#0": [8]})

	def test_plain_dict_unsupported_property(self):
		with self.assertRaises(ValueError):
			getSimpleSearchKwargs({"invalidProp": "val"}, raiseOnUnsupported=True)

		# When raiseOnUnsupported is False, unsupported prop is ignored
		result = getSimpleSearchKwargs({"invalidProp": "val"}, raiseOnUnsupported=False)
		self.assertEqual(result, {})

	def test_plain_dict_keyword_args(self):
		# Verify both criteria= and critData= keyword argument forms work
		res1 = getSimpleSearchKwargs(criteria={"role": 8})
		self.assertEqual(res1, {"eq_role#0": [8]})

		res2 = getSimpleSearchKwargs(critData={"role": 8})
		self.assertEqual(res2, {"eq_role#0": [8]})

	def test_none_criteria(self):
		self.assertEqual(getSimpleSearchKwargs(None), {})
		self.assertEqual(getSimpleSearchKwargs(), {})

	def test_criteria_object_with_dump_method(self):
		crit_obj = CriteriaWithDump({"role": 8, "tag": "div"})
		result = getSimpleSearchKwargs(crit_obj)
		self.assertEqual(result["eq_role#0"], [8])
		self.assertEqual(result["eq_tag#0"], ["div"])

	def test_criteria_object_keyword_args(self):
		crit_obj = CriteriaWithDump({"role": 8})
		res = getSimpleSearchKwargs(criteria=crit_obj)
		self.assertEqual(res, {"eq_role#0": [8]})

	def test_selector_object_dump(self):
		# Selector has a dump() method
		dummy_criteria = MagicMock()
		selector = Selector(dummy_criteria, {"role": 8, "tag": "div"})
		result = getSimpleSearchKwargs(selector)
		self.assertEqual(result["eq_role#0"], [8])
		self.assertEqual(result["eq_tag#0"], ["div"])

	def test_mock_criteria_dump(self):
		mock_crit = MagicMock()
		mock_crit.dump.return_value = {"role": 8, "tag": "button"}
		result = getSimpleSearchKwargs(mock_crit)
		mock_crit.dump.assert_called_once()
		self.assertEqual(result["eq_role#0"], [8])
		self.assertEqual(result["eq_tag#0"], ["button"])

	def test_plain_dict_has_no_dump_attribute(self):
		# Explicitly verify plain dict does NOT have dump attribute,
		# but getSimpleSearchKwargs succeeds without AttributeError
		crit_dict = {"role": 8, "tag": "div"}
		self.assertFalse(hasattr(crit_dict, "dump"))
		result = getSimpleSearchKwargs(crit_dict)
		self.assertEqual(result["eq_role#0"], [8])
		self.assertEqual(result["eq_tag#0"], ["div"])

	def test_selector_iter_matches_calls_get_simple_search_kwargs(self):
		dummy_criteria = MagicMock()
		dummy_criteria.properties.multiple = True
		dummy_criteria.rule.layer = "web"
		dummy_criteria.rule.ruleManager.parentZone = None
		dummy_criteria.rule.ruleManager.subModules._results = []
		dummy_criteria.rule.ruleManager._getPageTitle.return_value = ""
		root_mock = MagicMock()
		root_mock.searchNode.return_value = []
		dummy_criteria.rule.ruleManager.nodeManager.mainNode = root_mock

		selector = Selector(dummy_criteria, {"role": 8, "tag": "div"})
		from unittest.mock import patch
		with patch("webAccess.ruleHandler.getSimpleSearchKwargs", wraps=getSimpleSearchKwargs) as mock_fn:
			list(selector.iterMatches())
			mock_fn.assert_called_once()
			called_arg = mock_fn.call_args[0][0]
			self.assertIs(called_arg, selector)
			self.assertTrue(hasattr(called_arg, "dump"))


class DummyTreeNode(NodeField):
	"""Test node implementation extending NodeField."""

	def __init__(self, name, role=None, tag=None, parent=None, size=1):
		self.name = name
		self.role = role
		self.tag = tag
		self._parent = DeepCopyWeakRef(parent) if parent is not None else None
		self.children = []
		self.offset = 0
		self.size = size
		self.index = 0
		self._previousTextNode = None

	def add_child(self, child):
		child.index = len(self.children)
		self.children.append(child)
		return child


class TestRelativePathCriteriaParsing(unittest.TestCase):
	"""Unit tests verifying relative path parsing with dict criteria succeeds without AttributeError."""

	def setUp(self):
		# Build a simple tree hierarchy:
		# grandparent (role=1, tag="div")
		#   parent (role=8, tag="form")
		#     child1 (role=10, tag="span")
		#     child2 (role=10, tag="button")
		self.grandparent = DummyTreeNode("grandparent", role=1, tag="div")
		self.parent = self.grandparent.add_child(DummyTreeNode("parent", role=8, tag="form", parent=self.grandparent))
		self.child1 = self.parent.add_child(DummyTreeNode("child1", role=10, tag="span", parent=self.parent))
		self.child2 = self.parent.add_child(DummyTreeNode("child2", role=10, tag="button", parent=self.parent))

	def test_walk_up_with_dict_criteria_succeeds(self):
		# Walk up from child1 until node with role 8 (parent)
		result = self.child1.walk("U{'role': 8}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.parent)

	def test_walk_up_with_string_role_criteria(self):
		# Walk up from child1 with string role criteria
		result = self.child1.walk("U{'role': '8'}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.parent)

	def test_walk_up_to_grandparent(self):
		# Walk up from child1 until node with role 1 (grandparent)
		result = self.child1.walk("U{'role': 1}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.grandparent)

	def test_walk_up_with_tag_criteria(self):
		# Walk up from child1 until tag "div" (grandparent)
		result = self.child1.walk("U{'tag': 'div'}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.grandparent)

	def test_walk_check_criteria_step_c(self):
		# Check on current node: child2 has tag 'button'
		result = self.child2.walk("c{'tag': 'button'}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.child2)

		# Check on current node fails if criteria not met
		result_fail = self.child2.walk("c{'tag': 'span'}")
		self.assertIsNone(result_fail)

	def test_walk_down_with_criteria(self):
		# Walk down from grandparent to child matching tag 'form'
		result = self.grandparent.walk("D{'tag': 'form'}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.parent)

	def test_walk_sibling_with_criteria(self):
		# Walk right from child1 until tag 'button' (child2)
		result = self.child1.walk("R{'tag': 'button'}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.child2)

		# Walk left from child2 until tag 'span' (child1)
		result_left = self.child2.walk("L{'tag': 'span'}")
		self.assertIsNotNone(result_left)
		self.assertIs(result_left, self.child1)

	def test_walk_no_match_returns_none(self):
		# Walking up for non-existent role returns None without error
		result = self.child1.walk("U{'role': 999}")
		self.assertIsNone(result)

	def test_walk_compound_path(self):
		# Walk up to parent
		result = self.child1.walk("U{'role': 8}")
		self.assertIs(result, self.parent)

	def test_walk_compound_multiple_steps(self):
		# From child1, walk right to child2, then up to parent
		result = self.child1.walk("rU{'role': 8}")
		self.assertIsNotNone(result)
		self.assertIs(result, self.parent)

