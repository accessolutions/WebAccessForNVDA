import os
import sys
import unittest
from unittest.mock import MagicMock

from tests.test_py2_removal import (
	webModule,
	storeWebModule,
	presenter,
	overlay,
	nodeHandler,
	webAppScheduler,
	ruleTypes,
	controlMutation,
	builtinRuleActions,
)


class TestWebModuleRecoveryAndMethods(unittest.TestCase):
	def test_recover_from_legacy_url_as_string(self):
		data = {"WebModule": {"url": "https://example.com"}}
		webModule.recoverFrom_legacy(data)
		self.assertEqual(data["WebModule"]["url"], ["https://example.com"])
		self.assertIs(type(data["WebModule"]["url"]), list)

	def test_recover_from_0_5_role_text_type(self):
		data = {"Rules": [{"name": "rule1", "role": 8}]}
		webModule.recoverFrom_0_5(data)
		self.assertEqual(data["Rules"][0]["role"], "8")
		self.assertIs(type(data["Rules"][0]["role"]), str)

	def test_web_module_data_store_catalog(self):
		class DummyParentStore:
			def catalog(self, errors=None):
				return [
					("ref1", {"name": "mod1"}),
					("ref2", {"name": "mod2"}),
				]

		class TestStore(storeWebModule.WebModuleStore):
			def __init__(self):
				pass

			def _getKeyRef(self, storeRef):
				return storeRef

			def _isUserConfig(self, storeRef):
				return False

			def catalog(self, errors=None):
				full = {}
				for storeRef, meta in DummyParentStore().catalog(errors=errors):
					full[storeRef] = meta
				uniqueKeyRefs = set()
				consolidated = {}
				for storeRef, meta in full.items():
					keyRef = self._getKeyRef(storeRef)
					if keyRef in uniqueKeyRefs:
						continue
					if not self._isUserConfig(storeRef):
						uniqueKeyRefs.add(keyRef)
						consolidated[storeRef] = meta
				return consolidated

		store = TestStore()
		cat = store.catalog()
		self.assertIs(type(cat), dict)
		self.assertEqual(len(cat), 2)
		self.assertIn("ref1", cat)

	def test_overlay_mutate_obj_range(self):
		class Base1:
			pass

		class Base2(Base1):
			pass

		clsList = [Base2, Base1]
		bases = []
		for index in range(len(clsList)):
			if index == 0 or not issubclass(clsList[index - 1], clsList[index]):
				bases.append(clsList[index])
		self.assertEqual(bases, [Base2])

	def test_web_app_scheduler_queue(self):
		import queue
		self.assertIs(webAppScheduler.queue, queue)
		q = queue.Queue()
		q.put("item1")
		self.assertEqual(q.get_nowait(), "item1")

	def test_overlay_criteria_dict_items(self):
		criteria = [{"tag": "button", "role": "pushbutton"}]
		extracted = []
		for alternative in criteria:
			for key, val in alternative.items():
				extracted.append((key, val))
		self.assertEqual(extracted, [("tag", "button"), ("role", "pushbutton")])

	def test_rule_type_labels_mapping(self):
		self.assertEqual(ruleTypes.ruleTypeLabels[ruleTypes.MARKER], "Marker")
		self.assertEqual(ruleTypes.ruleTypeLabels[ruleTypes.ZONE], "Zone")

	def test_control_mutation_labels_mapping(self):
		self.assertEqual(controlMutation.mutationLabels["button"], "Button")
		self.assertIn("heading.1", controlMutation.mutationLabels)


if __name__ == "__main__":
	unittest.main()
