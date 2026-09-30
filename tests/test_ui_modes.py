import os
import sys
import types
from unittest.mock import MagicMock, patch
import unittest

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
		mod = MockModule(spec.name)
		return mod

	def exec_module(self, module):
		pass


if not any(isinstance(f, NVDAMockFinder) for f in sys.meta_path):
	sys.meta_path.insert(0, NVDAMockFinder())

# NVDA base classes and builtins
import builtins  # noqa: E402

builtins.pgettext = lambda ctx, text: text
builtins._ = lambda text: text

import baseObject  # noqa: E402
import garbageHandler  # noqa: E402
import wx  # noqa: E402
import winUser  # noqa: E402
import config  # noqa: E402

baseObject.AutoPropertyObject = type("AutoPropertyObject", (), {})
baseObject.ScriptableObject = type("ScriptableObject", (), {})
garbageHandler.TrackedObject = type("TrackedObject", (), {})

wx.ID_OK = 5100
wx.ID_CANCEL = 5101
wx.ID_MORE = 5102
wx.ID_CONVERT = 5103
wx.ID_ANY = -1
wx.VERTICAL = 1
wx.EXPAND = 2
wx.ACC_OK = 0
wx.ACC_STATE_SYSTEM_INVISIBLE = 0x8000
winUser.CHILDID_SELF = 0


class MockAccessible:
	def __init__(self, win):
		self.Window = win

	def GetName(self, childId):
		return (wx.ACC_OK, self.Window.GetLabel() if hasattr(self.Window, "GetLabel") else "")

	def GetState(self, childId):
		return (wx.ACC_OK, 0)


wx.Accessible = MockAccessible

from gui import guiHelper, settingsDialogs  # noqa: E402
guiHelper.SIPABCMeta = type
guiHelper.AutoWidthColumnListCtrl = MockBase
guiHelper.BoxSizerHelper = MockBase
settingsDialogs.SettingsPanel = MockBase
settingsDialogs.SettingsDialog = MockBase

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

# Add addon and plugin paths
addonPath = os.path.abspath(
	os.path.join(os.path.dirname(__file__), "..", "addon")
)
pluginPath = os.path.abspath(
	os.path.join(addonPath, "globalPlugins")
)
if addonPath not in sys.path:
	sys.path.insert(0, addonPath)
if pluginPath not in sys.path:
	sys.path.insert(0, pluginPath)

from webAccess import config as waConfig  # noqa: E402
from webAccess.config import (  # noqa: E402
	EditorMode,
	InspectorMode,
	RuleWizardMode,
	UiMode,
	UiModePref,
	UiModeSetting,
	UI_MODES,
	_REMEMBERS_LAST_USED,
	CONFIG_SPEC,
	getUiMode,
	getUiModePref,
	resolveUiMode,
	setUiModeLastUsed,
	setUiModePref,
)
from webAccess.gui.rule import editor, criteriaEditor, showRuleWizardOrEditor  # noqa: E402


class TestUiModeConfigSpec(unittest.TestCase):
	"""Test configuration specs and default mode settings."""

	def test_config_spec_structure(self):
		self.assertIn("uiModes", CONFIG_SPEC)
		uiModesSpec = CONFIG_SPEC["uiModes"]

		for mode in (UiMode.RULE_WIZARD, UiMode.RULE_EDITOR, UiMode.CRITERIA_EDITOR, UiMode.INSPECTOR):
			self.assertIn(str(mode), uiModesSpec)
			self.assertIn(str(UiModeSetting.MODE), uiModesSpec[str(mode)])

	def test_config_spec_defaults(self):
		uiModesSpec = CONFIG_SPEC["uiModes"]

		# Rule wizard: 'wizard', 'editor', default='wizard'
		self.assertIn("default='wizard'", uiModesSpec[str(UiMode.RULE_WIZARD)][str(UiModeSetting.MODE)])
		# Rule editor: 'simple', 'full', default='simple'
		self.assertIn("default='simple'", uiModesSpec[str(UiMode.RULE_EDITOR)][str(UiModeSetting.MODE)])
		# Criteria editor: 'simple', 'full', default='simple'
		self.assertIn("default='simple'", uiModesSpec[str(UiMode.CRITERIA_EDITOR)][str(UiModeSetting.MODE)])
		# Inspector: 'last_used', 'single', 'ancestors', default='single'
		self.assertIn("default='single'", uiModesSpec[str(UiMode.INSPECTOR)][str(UiModeSetting.MODE)])

	def test_last_used_spec_only_for_inspector(self):
		uiModesSpec = CONFIG_SPEC["uiModes"]

		self.assertIn(str(UiModeSetting.LAST_USED), uiModesSpec[str(UiMode.INSPECTOR)])
		self.assertIn("default='single'", uiModesSpec[str(UiMode.INSPECTOR)][str(UiModeSetting.LAST_USED)])

		self.assertNotIn(str(UiModeSetting.LAST_USED), uiModesSpec[str(UiMode.RULE_WIZARD)])
		self.assertNotIn(str(UiModeSetting.LAST_USED), uiModesSpec[str(UiMode.RULE_EDITOR)])
		self.assertNotIn(str(UiModeSetting.LAST_USED), uiModesSpec[str(UiMode.CRITERIA_EDITOR)])
		self.assertEqual(_REMEMBERS_LAST_USED, frozenset({UiMode.INSPECTOR}))


class TestUiModeResolution(unittest.TestCase):
	"""Test UI mode resolution and preferences."""

	def setUp(self):
		mockConfInstance["webAccess"] = {
			"uiModes": {
				str(UiMode.RULE_WIZARD): {},
				str(UiMode.RULE_EDITOR): {},
				str(UiMode.CRITERIA_EDITOR): {},
				str(UiMode.INSPECTOR): {},
			}
		}

	def test_implicit_defaults_resolution(self):
		self.assertEqual(resolveUiMode(UiMode.RULE_WIZARD), RuleWizardMode.WIZARD)
		self.assertEqual(resolveUiMode(UiMode.RULE_EDITOR), EditorMode.SIMPLE)
		self.assertEqual(resolveUiMode(UiMode.CRITERIA_EDITOR), EditorMode.SIMPLE)
		self.assertEqual(resolveUiMode(UiMode.INSPECTOR), InspectorMode.SINGLE)

		self.assertEqual(getUiModePref(UiMode.RULE_WIZARD), RuleWizardMode.WIZARD)
		self.assertEqual(getUiModePref(UiMode.RULE_EDITOR), EditorMode.SIMPLE)
		self.assertEqual(getUiModePref(UiMode.CRITERIA_EDITOR), EditorMode.SIMPLE)
		self.assertEqual(getUiModePref(UiMode.INSPECTOR), InspectorMode.SINGLE)

	def test_set_and_get_preferences(self):
		setUiModePref(UiMode.RULE_WIZARD, RuleWizardMode.EDITOR)
		self.assertEqual(getUiModePref(UiMode.RULE_WIZARD), RuleWizardMode.EDITOR)
		self.assertEqual(resolveUiMode(UiMode.RULE_WIZARD), RuleWizardMode.EDITOR)

		setUiModePref(UiMode.RULE_EDITOR, EditorMode.FULL)
		self.assertEqual(getUiModePref(UiMode.RULE_EDITOR), EditorMode.FULL)
		self.assertEqual(resolveUiMode(UiMode.RULE_EDITOR), EditorMode.FULL)

		setUiModePref(UiMode.CRITERIA_EDITOR, EditorMode.FULL)
		self.assertEqual(getUiModePref(UiMode.CRITERIA_EDITOR), EditorMode.FULL)
		self.assertEqual(resolveUiMode(UiMode.CRITERIA_EDITOR), EditorMode.FULL)

		setUiModePref(UiMode.INSPECTOR, InspectorMode.ANCESTORS)
		self.assertEqual(getUiModePref(UiMode.INSPECTOR), InspectorMode.ANCESTORS)
		self.assertEqual(resolveUiMode(UiMode.INSPECTOR), InspectorMode.ANCESTORS)

	def test_invalid_mode_coercion(self):
		mockConfInstance["webAccess"]["uiModes"][str(UiMode.RULE_WIZARD)][str(UiModeSetting.MODE)] = "nonexistent"
		self.assertEqual(getUiModePref(UiMode.RULE_WIZARD), RuleWizardMode.WIZARD)
		self.assertEqual(resolveUiMode(UiMode.RULE_WIZARD), RuleWizardMode.WIZARD)


class TestFallbackBehavior(unittest.TestCase):
	"""Test fallback when simpler mode is not supported by the data."""

	def setUp(self):
		mockConfInstance["webAccess"] = {
			"uiModes": {
				str(UiMode.RULE_WIZARD): {str(UiModeSetting.MODE): str(RuleWizardMode.WIZARD)},
				str(UiMode.RULE_EDITOR): {str(UiModeSetting.MODE): str(EditorMode.SIMPLE)},
				str(UiMode.CRITERIA_EDITOR): {str(UiModeSetting.MODE): str(EditorMode.SIMPLE)},
				str(UiMode.INSPECTOR): {str(UiModeSetting.MODE): str(InspectorMode.SINGLE)},
			}
		}

	def test_editor_supports_simple_mode(self):
		# No criteria / empty criteria -> supports simple mode
		self.assertTrue(editor.supportsSimpleMode({}))
		self.assertTrue(editor.supportsSimpleMode({"data": {"rule": {"criteria": []}}}))
		self.assertTrue(editor.supportsSimpleMode({"data": {"rule": {"criteria": [{"selector": {}}]}}}))

		# Multiple criteria sets -> does not support simple mode
		self.assertFalse(editor.supportsSimpleMode({
			"data": {"rule": {"criteria": [{"selector": {}}, {"selector": {}}]}}
		}))

	def test_criteria_editor_supports_simple_mode(self):
		# Simple criteria without gestures or properties
		self.assertTrue(criteriaEditor.supportsSimpleMode({}))
		self.assertTrue(criteriaEditor.supportsSimpleMode({"role": 8, "tag": "div"}))

		# Has gestures -> cannot be simple
		self.assertFalse(criteriaEditor.supportsSimpleMode({"gestures": ["kb:control+f"]}))

		# Has properties -> cannot be simple
		self.assertFalse(criteriaEditor.supportsSimpleMode({"properties": {"skip": True}}))

	def test_get_ui_mode_can_prefer_fallback(self):
		# Even though user preference is WIZARD/SIMPLE, canPrefer=False must return the fallback
		self.assertEqual(getUiMode(UiMode.RULE_WIZARD, canPrefer=False), RuleWizardMode.EDITOR)
		self.assertEqual(getUiMode(UiMode.RULE_EDITOR, canPrefer=False), EditorMode.FULL)
		self.assertEqual(getUiMode(UiMode.CRITERIA_EDITOR, canPrefer=False), EditorMode.FULL)

	def test_show_rule_wizard_or_editor_routes_correctly(self):
		context_simple = {"data": {"rule": {"criteria": [{}]}}}
		context_complex = {"data": {"rule": {"criteria": [{}, {}]}}}

		with patch("webAccess.gui.rule.wizard.show", return_value=True) as mock_wizard_show, \
		     patch("webAccess.gui.rule.editor.show", return_value=True) as mock_editor_show:

			# 1. Wizard preferred, simple data -> opens wizard
			setUiModePref(UiMode.RULE_WIZARD, RuleWizardMode.WIZARD)
			showRuleWizardOrEditor(context_simple)
			mock_wizard_show.assert_called_once()
			mock_editor_show.assert_not_called()

			mock_wizard_show.reset_mock()
			mock_editor_show.reset_mock()

			# 2. Wizard preferred, complex data (>1 criteria sets) -> falls back to editor
			showRuleWizardOrEditor(context_complex)
			mock_wizard_show.assert_not_called()
			mock_editor_show.assert_called_once()

			mock_wizard_show.reset_mock()
			mock_editor_show.reset_mock()

			# 3. Always editor preferred, simple data -> opens editor directly
			setUiModePref(UiMode.RULE_WIZARD, RuleWizardMode.EDITOR)
			showRuleWizardOrEditor(context_simple)
			mock_wizard_show.assert_not_called()
			mock_editor_show.assert_called_once()


class TestInspectorLastUsedTracking(unittest.TestCase):
	"""Test inspector last-used tracking and persistence."""

	def setUp(self):
		mockConfInstance["webAccess"] = {
			"uiModes": {
				str(UiMode.RULE_WIZARD): {},
				str(UiMode.RULE_EDITOR): {},
				str(UiMode.CRITERIA_EDITOR): {},
				str(UiMode.INSPECTOR): {},
			}
		}

	def test_inspector_last_used_preference_resolution(self):
		setUiModePref(UiMode.INSPECTOR, UiModePref.LAST_USED)
		self.assertEqual(getUiModePref(UiMode.INSPECTOR), UiModePref.LAST_USED)

		# Initial default last-used is SINGLE
		self.assertEqual(resolveUiMode(UiMode.INSPECTOR), InspectorMode.SINGLE)
		self.assertEqual(getUiMode(UiMode.INSPECTOR), InspectorMode.SINGLE)

		# Change last-used to ANCESTORS
		setUiModeLastUsed(UiMode.INSPECTOR, InspectorMode.ANCESTORS)
		self.assertEqual(resolveUiMode(UiMode.INSPECTOR), InspectorMode.ANCESTORS)
		self.assertEqual(getUiMode(UiMode.INSPECTOR), InspectorMode.ANCESTORS)

		# Change last-used back to SINGLE
		setUiModeLastUsed(UiMode.INSPECTOR, InspectorMode.SINGLE)
		self.assertEqual(resolveUiMode(UiMode.INSPECTOR), InspectorMode.SINGLE)
		self.assertEqual(getUiMode(UiMode.INSPECTOR), InspectorMode.SINGLE)

	def test_non_inspector_surfaces_do_not_persist_last_used(self):
		# Calling setUiModeLastUsed on wizard or editors must do nothing
		setUiModeLastUsed(UiMode.RULE_WIZARD, RuleWizardMode.EDITOR)
		setUiModeLastUsed(UiMode.RULE_EDITOR, EditorMode.FULL)
		setUiModeLastUsed(UiMode.CRITERIA_EDITOR, EditorMode.FULL)

		uiModesSection = mockConfInstance["webAccess"]["uiModes"]
		self.assertNotIn(str(UiModeSetting.LAST_USED), uiModesSection[str(UiMode.RULE_WIZARD)])
		self.assertNotIn(str(UiModeSetting.LAST_USED), uiModesSection[str(UiMode.RULE_EDITOR)])
		self.assertNotIn(str(UiModeSetting.LAST_USED), uiModesSection[str(UiMode.CRITERIA_EDITOR)])

	def test_inspector_switch_view_updates_last_used(self):
		from webAccess.gui import inspector

		dlg = inspector.InspectorDialog.__new__(inspector.InspectorDialog)
		dlg.showAncestors = False
		dlg.message = MagicMock()
		dlg.inspect = MagicMock()
		dlg.node = MagicMock()
		dlg.root = MagicMock()
		dlg.identifier = MagicMock()

		# Switch view from False -> True
		dlg.switchView()
		self.assertTrue(dlg.showAncestors)
		self.assertEqual(
			mockConfInstance["webAccess"]["uiModes"][str(UiMode.INSPECTOR)][str(UiModeSetting.LAST_USED)],
			str(InspectorMode.ANCESTORS)
		)

		# Switch view from True -> False
		dlg.switchView()
		self.assertFalse(dlg.showAncestors)
		self.assertEqual(
			mockConfInstance["webAccess"]["uiModes"][str(UiMode.INSPECTOR)][str(UiModeSetting.LAST_USED)],
			str(InspectorMode.SINGLE)
		)

	def test_inspector_show_initializes_view_from_mode(self):
		from webAccess.gui import inspector

		mock_dlg = MagicMock()
		mock_dlg.IsShown.return_value = False

		with patch.object(inspector.InspectorDialog, "getInstance", return_value=mock_dlg):
			# Mode set to ANCESTORS
			setUiModePref(UiMode.INSPECTOR, InspectorMode.ANCESTORS)
			inspector.show()
			self.assertTrue(mock_dlg.showAncestors)

			# Mode set to SINGLE
			setUiModePref(UiMode.INSPECTOR, InspectorMode.SINGLE)
			inspector.show()
			self.assertFalse(mock_dlg.showAncestors)


class TestSettingsPanelUiModes(unittest.TestCase):
	"""Test Settings Panel UI choices and onSave logic."""

	def setUp(self):
		mockConfInstance["webAccess"] = {
			"devMode": False,
			"disableUserConfig": False,
			"writeInAddons": False,
			"uiModes": {
				str(UiMode.RULE_WIZARD): {str(UiModeSetting.MODE): str(RuleWizardMode.WIZARD)},
				str(UiMode.RULE_EDITOR): {str(UiModeSetting.MODE): str(EditorMode.SIMPLE)},
				str(UiMode.CRITERIA_EDITOR): {str(UiModeSetting.MODE): str(EditorMode.SIMPLE)},
				str(UiMode.INSPECTOR): {str(UiModeSetting.MODE): str(InspectorMode.SINGLE)},
			}
		}

	def test_settings_panel_saves_preferences(self):
		from webAccess.gui.settings import WebAccessSettingsPanel

		panel = WebAccessSettingsPanel.__new__(WebAccessSettingsPanel)
		panel.devMode = MagicMock(GetValue=MagicMock(return_value=True))
		panel.disableUserConfig = MagicMock(GetValue=MagicMock(return_value=False))
		panel.writeInAddons = MagicMock(GetValue=MagicMock(return_value=False))

		# Mock choices for mode settings
		mock_ctrl_wizard = MagicMock(GetSelection=MagicMock(return_value=1))  # Always editor
		mock_ctrl_editor = MagicMock(GetSelection=MagicMock(return_value=1))  # Always full
		mock_ctrl_criteria = MagicMock(GetSelection=MagicMock(return_value=0))  # Simple
		mock_ctrl_inspector = MagicMock(GetSelection=MagicMock(return_value=1))  # Last used

		panel._modeChoices = [
			(UiMode.RULE_WIZARD, mock_ctrl_wizard, (RuleWizardMode.WIZARD, RuleWizardMode.EDITOR)),
			(UiMode.RULE_EDITOR, mock_ctrl_editor, (EditorMode.SIMPLE, EditorMode.FULL)),
			(UiMode.CRITERIA_EDITOR, mock_ctrl_criteria, (EditorMode.SIMPLE, EditorMode.FULL)),
			(UiMode.INSPECTOR, mock_ctrl_inspector, (InspectorMode.SINGLE, UiModePref.LAST_USED, InspectorMode.ANCESTORS)),
		]

		panel.onSave()

		self.assertEqual(getUiModePref(UiMode.RULE_WIZARD), RuleWizardMode.EDITOR)
		self.assertEqual(getUiModePref(UiMode.RULE_EDITOR), EditorMode.FULL)
		self.assertEqual(getUiModePref(UiMode.CRITERIA_EDITOR), EditorMode.SIMPLE)
		self.assertEqual(getUiModePref(UiMode.INSPECTOR), UiModePref.LAST_USED)


class TestOneWayShortcutsDoNotStick(unittest.TestCase):
	"""Test that pressing F12 in wizard or editors does not stick/persist last-used."""

	def setUp(self):
		mockConfInstance["webAccess"] = {
			"uiModes": {
				str(UiMode.RULE_WIZARD): {str(UiModeSetting.MODE): str(RuleWizardMode.WIZARD)},
				str(UiMode.RULE_EDITOR): {str(UiModeSetting.MODE): str(EditorMode.SIMPLE)},
				str(UiMode.CRITERIA_EDITOR): {str(UiModeSetting.MODE): str(EditorMode.SIMPLE)},
				str(UiMode.INSPECTOR): {str(UiModeSetting.MODE): str(InspectorMode.SINGLE)},
			}
		}

	def test_editor_f12_switch_does_not_persist(self):
		context = {"new": True}
		with patch("webAccess.gui.rule.editor.showContextualDialog", side_effect=[wx.ID_MORE, wx.ID_OK]) as mock_dialog:
			res = editor.show(context)
			self.assertTrue(res)
			self.assertEqual(mock_dialog.call_count, 2)
			self.assertEqual(mock_dialog.call_args_list[0][1]["simpleMode"], True)
			self.assertEqual(mock_dialog.call_args_list[1][1]["simpleMode"], False)

		self.assertEqual(getUiModePref(UiMode.RULE_EDITOR), EditorMode.SIMPLE)
		self.assertNotIn(str(UiModeSetting.LAST_USED), mockConfInstance["webAccess"]["uiModes"][str(UiMode.RULE_EDITOR)])

	def test_criteria_editor_f12_switch_does_not_persist(self):
		with patch("webAccess.gui.rule.criteriaEditor.showContextualDialog", side_effect=[wx.ID_MORE, wx.ID_OK]) as mock_dialog:
			res = criteriaEditor.show({})
			self.assertTrue(res)
			self.assertEqual(mock_dialog.call_count, 2)
			self.assertEqual(mock_dialog.call_args_list[0][1]["simpleMode"], True)
			self.assertEqual(mock_dialog.call_args_list[1][1]["simpleMode"], False)

		self.assertEqual(getUiModePref(UiMode.CRITERIA_EDITOR), EditorMode.SIMPLE)
		self.assertNotIn(str(UiModeSetting.LAST_USED), mockConfInstance["webAccess"]["uiModes"][str(UiMode.CRITERIA_EDITOR)])

	def test_wizard_f12_switch_does_not_persist(self):
		from webAccess.gui.rule.wizard import Wizard

		wiz = Wizard.__new__(Wizard)
		wiz.context = {"data": {}}
		wiz.CurrentPage = MagicMock()
		wiz.Hide = MagicMock()
		wiz.EndModal = MagicMock()

		with patch("webAccess.gui.rule.editor.show", return_value=True) as mock_editor_show:
			wiz.switchToEditor()
			mock_editor_show.assert_called_once()
			wiz.EndModal.assert_called_once_with(wx.ID_OK)

		self.assertEqual(getUiModePref(UiMode.RULE_WIZARD), RuleWizardMode.WIZARD)
		self.assertNotIn(str(UiModeSetting.LAST_USED), mockConfInstance["webAccess"]["uiModes"][str(UiMode.RULE_WIZARD)])


class TestMenuAndManagerIntegration(unittest.TestCase):
	"""Test menu and manager rule creation honoring UI mode preference."""

	def test_menu_on_rule_create_calls_show_rule_wizard_or_editor(self):
		import globalPlugins
		import webAccess
		globalPlugins.webAccess = webAccess
		sys.modules["globalPlugins.webAccess"] = webAccess

		from globalPlugins.webAccess.gui.menu import Menu

		menu = Menu.__new__(Menu)
		menu.context = {"data": {"rule": {"name": "test"}}}

		with patch("globalPlugins.webAccess.gui.rule.showRuleWizardOrEditor", return_value=True) as mock_show:
			menu.onRuleCreate(None)
			mock_show.assert_called_once()
			called_context = mock_show.call_args[0][0]
			self.assertTrue(called_context["new"])
			self.assertNotIn("rule", called_context.get("data", {}))

	def test_rules_manager_on_rule_new_and_edit_honor_setting(self):
		from webAccess.gui.rule.manager import Dialog as RulesManagerDialog

		mgr = RulesManagerDialog.__new__(RulesManagerDialog)
		mgr.context = {}
		mgr.tree = MagicMock()
		mgr.disableGroupByPosition = MagicMock(return_value=False)
		mgr.refreshRuleList = MagicMock()

		with patch("webAccess.gui.rule.manager.showRuleWizardOrEditor", return_value=True) as mock_show:
			# Test onRuleNew
			mgr.onRuleNew()
			mock_show.assert_called_once()
			called_context = mock_show.call_args[0][0]
			self.assertTrue(called_context["new"])

		with patch("webAccess.gui.rule.manager.showRuleWizardOrEditor", return_value=True) as mock_show:
			# Test onRuleEdit
			mock_rule = MagicMock()
			mock_rule.ruleManager.webModule = MagicMock()
			mock_rule.dump.return_value = {"name": "existingRule"}
			mgr.getSelectedRule = MagicMock(return_value=mock_rule)

			mgr.onRuleEdit(None)
			mock_show.assert_called_once()
			called_context = mock_show.call_args[0][0]
			self.assertFalse(called_context["new"])
			self.assertEqual(called_context["data"]["rule"], {"name": "existingRule"})


class TestAccessibilityHelpers(unittest.TestCase):
	"""Test accessible name and presentation-only helpers in settings."""

	def test_grouping_name_accessible(self):
		from webAccess.gui.settings import _GroupingNameAccessible

		mock_win = MagicMock()
		mock_win.GetLabel.return_value = "Default UI modes"

		acc = _GroupingNameAccessible(mock_win, "In these dialogs, press F12 to switch mode.")
		status, name = acc.GetName(winUser.CHILDID_SELF)
		self.assertEqual(status, wx.ACC_OK)
		self.assertEqual(name, "Default UI modes. In these dialogs, press F12 to switch mode.")

	def test_presentation_only_accessible(self):
		from webAccess.gui.settings import _PresentationOnlyAccessible

		mock_win = MagicMock()
		acc = _PresentationOnlyAccessible(mock_win)
		status, state = acc.GetState(winUser.CHILDID_SELF)
		self.assertEqual(status, wx.ACC_OK)
		self.assertEqual(state, wx.ACC_STATE_SYSTEM_INVISIBLE)


if __name__ == "__main__":
	unittest.main()
