import importlib.util
import os
import sys
from types import SimpleNamespace
import types


def _dummy_class(name):
    return type(name, (), {"__init__": lambda self, *args, **kwargs: None})


_qt_module = types.ModuleType("aqt.qt")
for _name in (
    "QDialog", "QDialogButtonBox", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QLabel", "QSlider", "QCheckBox", "QComboBox", "QPushButton", "QWidget",
    "QTimeEdit", "QTime", "QSpinBox", "QLineEdit", "QMessageBox", "QFileDialog",
    "QFrame", "QInputDialog", "QScrollArea", "QObject", "QEvent",
    "QGraphicsOpacityEffect", "QSplitter", "QTextBrowser", "QTableWidget",
    "QTableWidgetItem", "QHeaderView", "QTimer", "QColor",
):
    setattr(_qt_module, _name, _dummy_class(_name))

_qt_module.QMessageBox.StandardButton = SimpleNamespace(Yes=1, No=2)
_qt_module.QMessageBox.warning = staticmethod(lambda *args, **kwargs: None)
_qt_module.QMessageBox.question = staticmethod(lambda *args, **kwargs: _qt_module.QMessageBox.StandardButton.No)
_qt_module.QInputDialog.getText = staticmethod(lambda *args, **kwargs: ("", False))
_qt_module.qconnect = lambda *args, **kwargs: None
_qt_module.Qt = SimpleNamespace(
    Orientation=SimpleNamespace(Horizontal=1),
    AlignmentFlag=SimpleNamespace(AlignCenter=0),
    ItemDataRole=SimpleNamespace(UserRole=0),
    FocusPolicy=SimpleNamespace(NoFocus=0),
)

_utils_module = types.ModuleType("aqt.utils")
_utils_module.showInfo = lambda *args, **kwargs: None
_utils_module.tooltip = lambda *args, **kwargs: None

_aqt_module = types.ModuleType("aqt")
_aqt_module.mw = SimpleNamespace(addonManager=None)
_aqt_module.qt = _qt_module

sys.modules["aqt"] = _aqt_module
sys.modules["aqt.qt"] = _qt_module
sys.modules["aqt.utils"] = _utils_module


_SPEC = importlib.util.spec_from_file_location(
    "_incremento_learn_dialog",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "learn_dialog.py")),
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["_incremento_learn_dialog"] = _MOD
_SPEC.loader.exec_module(_MOD)

_normalize_selected_scheduler_profile = _MOD._normalize_selected_scheduler_profile
_write_named_scheduler_profile = _MOD._write_named_scheduler_profile
_rename_named_scheduler_profile = _MOD._rename_named_scheduler_profile
SchedulerConfigDialog = _MOD.SchedulerConfigDialog


class _FakeButton:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)


class _FakeComboBox:
    def __init__(self):
        self.items = []
        self.current_index = -1

    def blockSignals(self, _blocked):
        return None

    def clear(self):
        self.items = []
        self.current_index = -1

    def addItem(self, label, data=None):
        self.items.append((label, data))

    def findText(self, text):
        for index, (label, _data) in enumerate(self.items):
            if label == text:
                return index
        return -1

    def setCurrentIndex(self, index):
        self.current_index = index

    def currentData(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][1]
        return None

    def currentText(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][0]
        return ""


def _build_dialog_for_profile_tests(profiles, selected_name=None, current_data=None):
    dialog = SchedulerConfigDialog.__new__(SchedulerConfigDialog)
    dialog._profiles = dict(profiles)
    dialog._selected_profile_name = selected_name
    dialog._profile_combo = _FakeComboBox()
    dialog._profile_load_btn = _FakeButton()
    dialog._profile_save_btn = _FakeButton()
    dialog._profile_rename_btn = _FakeButton()
    dialog._profile_delete_btn = _FakeButton()
    dialog._build_current_dict = lambda *, include_selected_profile=False: dict(current_data or {})
    return dialog


class TestWriteNamedSchedulerProfile:
    def test_overwrites_selected_profile_only(self, monkeypatch):
        stored_config = {
            "dialog": {"session_card_count": 50, "topics_slider": 10},
            "profiles": {
                "Focus": {"session_card_count": 20, "topics_slider": 80},
                "Spare": {"session_card_count": 99, "topics_slider": 1},
            },
        }
        write_calls = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))

        updated_profiles = _write_named_scheduler_profile(
            "Focus",
            {"session_card_count": 42, "topics_slider": 33},
            stored_config["profiles"],
        )

        assert updated_profiles == {
            "Focus": {"session_card_count": 42, "topics_slider": 33},
            "Spare": {"session_card_count": 99, "topics_slider": 1},
        }
        assert stored_config["dialog"] == {"session_card_count": 50, "topics_slider": 10}
        assert stored_config["profiles"] == updated_profiles
        assert write_calls == [stored_config]

    def test_adds_new_profile_without_mutating_input_mapping(self, monkeypatch):
        stored_config = {"dialog": {"session_card_count": 50}, "profiles": {"Focus": {"session_card_count": 20}}}
        original_profiles = dict(stored_config["profiles"])
        write_calls = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))

        updated_profiles = _write_named_scheduler_profile(
            "Fresh",
            {"session_card_count": 12},
            original_profiles,
        )

        assert original_profiles == {"Focus": {"session_card_count": 20}}
        assert updated_profiles == {
            "Focus": {"session_card_count": 20},
            "Fresh": {"session_card_count": 12},
        }
        assert stored_config["profiles"] == updated_profiles
        assert write_calls == [stored_config]


class TestRenameNamedSchedulerProfile:
    def test_renames_profile_and_updates_selected_dialog_profile(self, monkeypatch):
        stored_config = {
            "dialog": {"session_card_count": 50, "topics_slider": 10, "selected_profile": "Writing"},
            "profiles": {
                "Writing": {"session_card_count": 20, "topics_slider": 80},
                "Spare": {"session_card_count": 99, "topics_slider": 1},
            },
        }
        write_calls = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))

        updated_profiles = _rename_named_scheduler_profile(
            "Writing",
            "Deep Writing",
            stored_config["profiles"],
        )

        assert updated_profiles == {
            "Deep Writing": {"session_card_count": 20, "topics_slider": 80},
            "Spare": {"session_card_count": 99, "topics_slider": 1},
        }
        assert stored_config["dialog"] == {
            "session_card_count": 50,
            "topics_slider": 10,
            "selected_profile": "Deep Writing",
        }
        assert stored_config["profiles"] == updated_profiles
        assert write_calls == [stored_config]

    def test_renames_profile_without_mutating_input_mapping(self, monkeypatch):
        stored_config = {"dialog": {"session_card_count": 50}, "profiles": {"Old": {"session_card_count": 20}}}
        original_profiles = dict(stored_config["profiles"])
        write_calls = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))

        updated_profiles = _rename_named_scheduler_profile(
            "Old",
            "New",
            original_profiles,
        )

        assert original_profiles == {"Old": {"session_card_count": 20}}
        assert updated_profiles == {"New": {"session_card_count": 20}}
        assert stored_config["profiles"] == updated_profiles
        assert write_calls == [stored_config]


class TestSelectedSchedulerProfile:
    def test_restores_known_selected_profile(self):
        assert _normalize_selected_scheduler_profile(
            "Focus",
            {"Focus": {"session_card_count": 20}, "Writing": {"session_card_count": 30}},
        ) == "Focus"

    def test_unknown_or_blank_selected_profile_restores_as_none(self):
        profiles = {"Focus": {"session_card_count": 20}}

        assert _normalize_selected_scheduler_profile(None, profiles) is None
        assert _normalize_selected_scheduler_profile("", profiles) is None
        assert _normalize_selected_scheduler_profile("Missing", profiles) is None


class TestPriorityOrderState:
    def test_priority_order_map_prefers_new_entries(self):
        mapping = SchedulerConfigDialog._priority_order_map_from_dict(
            {
                "priority_order_entries": [
                    {"kind": "tag", "value": "Writing", "order": "2"},
                    {"kind": "content_type", "value": "PDF", "order": 1},
                ],
                "prioritized_tags_first": ["Legacy"],
            }
        )

        assert mapping == {
            ("tag", "writing"): 2,
            ("content_type", "pdf"): 1,
        }

    def test_priority_order_map_migrates_legacy_prioritized_tags(self):
        mapping = SchedulerConfigDialog._priority_order_map_from_dict(
            {"prioritized_tags_first": ["alpha", "beta"]}
        )

        assert mapping == {
            ("tag", "alpha"): 1,
            ("tag", "beta"): 2,
        }


class TestSchedulerConfigDialogProfiles:
    def test_add_profile_persists_new_preset_under_config_profiles(self, monkeypatch):
        stored_config = {"dialog": {"session_card_count": 50}, "profiles": {"Focus": {"session_card_count": 20}}}
        write_calls = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        dialog = _build_dialog_for_profile_tests(
            stored_config["profiles"],
            selected_name="Focus",
            current_data={"session_card_count": 42, "topics_slider": 33},
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))
        monkeypatch.setattr(_MOD.QInputDialog, "getText", lambda *args, **kwargs: ("Fresh", True))
        monkeypatch.setattr(_MOD.QMessageBox, "warning", lambda *args, **kwargs: None)
        monkeypatch.setattr(_MOD, "tooltip", lambda _message: None)

        dialog._add_profile()

        assert stored_config["profiles"] == {
            "Focus": {"session_card_count": 20},
            "Fresh": {"session_card_count": 42, "topics_slider": 33},
        }
        assert dialog._profiles == stored_config["profiles"]
        assert dialog.selected_dialog_profile_name() == "Fresh"
        assert write_calls == [stored_config]

    def test_add_profile_does_not_overwrite_duplicate_name(self, monkeypatch):
        stored_config = {"dialog": {"session_card_count": 50}, "profiles": {"Focus": {"session_card_count": 20}}}
        write_calls = []
        warnings = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        dialog = _build_dialog_for_profile_tests(
            stored_config["profiles"],
            selected_name="Focus",
            current_data={"session_card_count": 99},
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))
        monkeypatch.setattr(_MOD.QInputDialog, "getText", lambda *args, **kwargs: ("Focus", True))
        monkeypatch.setattr(_MOD.QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))
        monkeypatch.setattr(_MOD, "tooltip", lambda _message: None)

        dialog._add_profile()

        assert stored_config["profiles"] == {"Focus": {"session_card_count": 20}}
        assert dialog._profiles == {"Focus": {"session_card_count": 20}}
        assert dialog.selected_dialog_profile_name() == "Focus"
        assert warnings == ['Preset "Focus" already exists.']
        assert write_calls == []

    def test_add_profile_selects_new_preset_and_enables_profile_actions(self, monkeypatch):
        stored_config = {"dialog": {}, "profiles": {}}
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: None,
        )
        dialog = _build_dialog_for_profile_tests(
            stored_config["profiles"],
            selected_name=None,
            current_data={"session_card_count": 12},
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))
        monkeypatch.setattr(_MOD.QInputDialog, "getText", lambda *args, **kwargs: ("Writing", True))
        monkeypatch.setattr(_MOD.QMessageBox, "warning", lambda *args, **kwargs: None)
        monkeypatch.setattr(_MOD, "tooltip", lambda _message: None)

        dialog._add_profile()

        assert dialog._profile_combo.currentText() == "Writing"
        assert dialog._profile_load_btn.enabled is True
        assert dialog._profile_save_btn.enabled is True
        assert dialog._profile_rename_btn.enabled is True
        assert dialog._profile_delete_btn.enabled is True

    def test_save_profile_only_overwrites_selected_preset(self, monkeypatch):
        stored_config = {
            "dialog": {"session_card_count": 50},
            "profiles": {
                "Focus": {"session_card_count": 20, "topics_slider": 80},
                "Spare": {"session_card_count": 99, "topics_slider": 1},
            },
        }
        write_calls = []
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: write_calls.append(config),
        )
        dialog = _build_dialog_for_profile_tests(
            stored_config["profiles"],
            selected_name="Focus",
            current_data={"session_card_count": 42, "topics_slider": 33},
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))
        monkeypatch.setattr(_MOD, "tooltip", lambda _message: None)

        dialog._save_profile()

        assert stored_config["profiles"] == {
            "Focus": {"session_card_count": 42, "topics_slider": 33},
            "Spare": {"session_card_count": 99, "topics_slider": 1},
        }
        assert dialog.selected_dialog_profile_name() == "Focus"
        assert dialog._profile_combo.currentText() == "Focus"
        assert write_calls == [stored_config]

    def test_current_settings_selection_keeps_save_disabled(self):
        dialog = _build_dialog_for_profile_tests(
            {"Focus": {"session_card_count": 20}},
            selected_name=None,
        )

        dialog._refresh_profile_combo()

        assert dialog._profile_combo.currentText() == SchedulerConfigDialog._CURRENT_SETTINGS_LABEL
        assert dialog._profile_save_btn.enabled is False
