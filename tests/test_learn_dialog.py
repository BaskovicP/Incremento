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
_initial_scheduler_dialog_state = _MOD._initial_scheduler_dialog_state
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


class _FakeCheckBox:
    def __init__(self, checked=False):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = bool(checked)


class _FakeValueWidget:
    def __init__(self, value=0):
        self._value = value
        self.enabled = True

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)


class _FakeLineEdit:
    def __init__(self, text=""):
        self._text = str(text)

    def text(self):
        return self._text

    def setText(self, text):
        self._text = str(text)


class _FakeDataCombo:
    def __init__(self, items, current_data=None):
        self.items = list(items)
        self.current_index = 0 if self.items else -1
        if current_data is not None:
            for index, (_label, data) in enumerate(self.items):
                if data == current_data:
                    self.current_index = index
                    break

    def currentData(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][1]
        return None

    def count(self):
        return len(self.items)

    def itemData(self, index):
        return self.items[index][1]

    def setCurrentIndex(self, index):
        self.current_index = index


class _FakeFunnel:
    def __init__(self, order=None, enabled=None):
        self._order = list(order or [])
        self._enabled = dict(enabled or {})

    def get_order(self):
        return list(self._order)

    def get_enabled(self):
        return dict(self._enabled)

    def set_order(self, order, enabled=None):
        self._order = list(order)
        self._enabled = dict(enabled or {})


class _FakePreviewDialog:
    def __init__(self):
        self.synced = False

    def sync_use_preview_checkbox(self):
        self.synced = True


def _build_dialog_for_profile_tests(profiles, selected_name=None, current_data=None):
    dialog = SchedulerConfigDialog.__new__(SchedulerConfigDialog)
    dialog._profiles = dict(profiles)
    dialog._selected_profile_name = selected_name
    dialog._profile_combo = _FakeComboBox()
    dialog._profile_load_btn = _FakeButton()
    dialog._profile_save_btn = _FakeButton()
    dialog._profile_rename_btn = _FakeButton()
    dialog._profile_delete_btn = _FakeButton()
    def _build_current_dict(*, include_selected_profile=False):
        data = dict(current_data or {})
        if include_selected_profile:
            data["selected_profile"] = dialog.selected_dialog_profile_name()
        return data
    dialog._build_current_dict = _build_current_dict
    return dialog


def _build_dialog_for_state_tests():
    dialog = SchedulerConfigDialog.__new__(SchedulerConfigDialog)
    dialog._linked_rows = [
        {
            "tag": "writing",
            "slider": _FakeValueWidget(35),
            "lock_cb": _FakeCheckBox(True),
            "group_edit": _FakeLineEdit("focus"),
            "order_edit": _FakeLineEdit("2"),
        },
        {
            "tag": _MOD.NO_TAGS_KEY,
            "slider": _FakeValueWidget(15),
            "lock_cb": _FakeCheckBox(False),
            "group_edit": _FakeLineEdit("tags"),
        },
    ]
    dialog._ct_rows = [
        {
            "type": "pdf",
            "cb": _FakeCheckBox(True),
            "slider": _FakeValueWidget(25),
            "pct_label": SimpleNamespace(setText=lambda _text: None),
            "order_edit": _FakeLineEdit("1"),
        }
    ]
    dialog._count_spin = _FakeValueWidget(42)
    dialog._topics_slider = _FakeValueWidget(20)
    dialog._random_slider = _FakeValueWidget(70)
    dialog._pdf_slider = _FakeValueWidget(25)
    dialog._topics_lock_cb = _FakeCheckBox(True)
    dialog._pdf_lock_cb = _FakeCheckBox(False)
    dialog._priority_lock_cb = _FakeCheckBox(True)
    dialog._topics_group_edit = _FakeLineEdit("topics")
    dialog._pdf_group_edit = _FakeLineEdit("docs")
    dialog._priority_group_edit = _FakeLineEdit("pace")
    dialog._enforce_cb = _FakeCheckBox(False)
    dialog._auto_refill_session_cb = _FakeCheckBox(True)
    dialog._scope_combo = _FakeDataCombo([("Session", "session"), ("Daily", "daily")], current_data="daily")
    dialog._day_end_preset = _FakeDataCombo([("04:00", "04:00"), ("Custom", None)], current_data="04:00")
    dialog._priority_order_cb = _FakeCheckBox(True)
    dialog._funnel = _FakeFunnel(order=["tags", "mode"], enabled={"tags": True, "mode": False})
    dialog._topics_filter_edit = _FakeLineEdit("deck:Science")
    dialog._items_filter_edit = _FakeLineEdit("-deck:Science")
    dialog._cb_new = _FakeCheckBox(False)
    dialog._cb_learning = _FakeCheckBox(True)
    dialog._cb_due = _FakeCheckBox(False)
    dialog._preserve_order_cb = _FakeCheckBox(False)
    dialog._show_debug_cb = _FakeCheckBox(True)
    dialog._use_live_preview_enabled = True
    dialog._selected_profile_name = "Focus"
    dialog._profiles = {"Focus": {}}
    dialog._branch_scope = None
    dialog._current_include_rest_from_other_slider = lambda: True
    dialog._current_priority_order_entries = lambda: [
        {"kind": "tag", "value": "writing", "order": 2},
        {"kind": "content_type", "value": "pdf", "order": 1},
    ]
    dialog._parse_order_value = SchedulerConfigDialog._parse_order_value
    dialog._get_day_end_time = lambda: "04:00"
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

    def test_uses_addon_package_config_key(self, monkeypatch):
        stored_config = {"dialog": {}, "profiles": {}}
        seen_names = []
        addon_manager = SimpleNamespace(
            getConfig=lambda name: seen_names.append(("get", name)) or stored_config,
            writeConfig=lambda name, config: seen_names.append(("write", name, config)),
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))

        _write_named_scheduler_profile(
            "Focus",
            {"session_card_count": 42},
            stored_config["profiles"],
        )

        assert seen_names == [
            ("get", _MOD._ADDON_PKG),
            ("write", _MOD._ADDON_PKG, stored_config),
        ]

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


class TestInitialSchedulerDialogState:
    def test_selected_profile_overrides_dialog_values_on_restore(self):
        state = _initial_scheduler_dialog_state(
            {
                "session_card_count": 50,
                "topics_slider": 10,
                "include_due": False,
                "selected_profile": "Focus",
            },
            {
                "Focus": {
                    "session_card_count": 20,
                    "topics_slider": 80,
                }
            },
            "Focus",
        )

        assert state == {
            "session_card_count": 20,
            "topics_slider": 80,
            "include_due": False,
            "selected_profile": "Focus",
        }

    def test_unknown_selected_profile_keeps_dialog_state(self):
        state = _initial_scheduler_dialog_state(
            {"session_card_count": 50, "selected_profile": "Missing"},
            {"Focus": {"session_card_count": 20}},
            "Missing",
        )

        assert state == {
            "session_card_count": 50,
            "selected_profile": "Missing",
        }


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
        assert stored_config["dialog"] == {
            "session_card_count": 42,
            "topics_slider": 33,
            "selected_profile": "Fresh",
        }
        assert dialog._profiles == stored_config["profiles"]
        assert dialog.selected_dialog_profile_name() == "Fresh"
        assert write_calls == [stored_config, stored_config]

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
        assert stored_config["dialog"] == {
            "session_card_count": 42,
            "topics_slider": 33,
            "selected_profile": "Focus",
        }
        assert dialog.selected_dialog_profile_name() == "Focus"
        assert dialog._profile_combo.currentText() == "Focus"
        assert write_calls == [stored_config, stored_config]

    def test_current_settings_selection_keeps_save_disabled(self):
        dialog = _build_dialog_for_profile_tests(
            {"Focus": {"session_card_count": 20}},
            selected_name=None,
        )

        dialog._refresh_profile_combo()

        assert dialog._profile_combo.currentText() == SchedulerConfigDialog._CURRENT_SETTINGS_LABEL
        assert dialog._profile_save_btn.enabled is False


class TestSchedulerConfigDialogPersistence:
    def test_save_config_writes_dialog_to_addon_package(self, monkeypatch):
        stored_config = {"dialog": {"session_card_count": 10}, "profiles": {"Main": {"session_card_count": 20}}}
        seen_names = []
        addon_manager = SimpleNamespace(
            getConfig=lambda name: seen_names.append(("get", name)) or stored_config,
            writeConfig=lambda name, config: seen_names.append(("write", name, config)),
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))

        dialog = SchedulerConfigDialog.__new__(SchedulerConfigDialog)
        dialog._build_current_dict = lambda *, include_selected_profile=True: {
            "session_card_count": 42,
            "selected_profile": "Main" if include_selected_profile else None,
        }

        dialog.save_config()

        assert stored_config["dialog"] == {
            "session_card_count": 42,
            "selected_profile": "Main",
        }
        assert stored_config["profiles"] == {"Main": {"session_card_count": 20}}
        assert seen_names == [
            ("get", _MOD._ADDON_PKG),
            ("write", _MOD._ADDON_PKG, stored_config),
        ]


class TestSchedulerConfigDialogState:
    def test_build_current_dict_includes_auto_refill_session(self):
        dialog = _build_dialog_for_state_tests()

        data = dialog._build_current_dict()

        assert data["auto_refill_session"] is True

    def test_to_config_forwards_auto_refill_session(self):
        dialog = _build_dialog_for_state_tests()

        cfg = dialog.to_config()

        assert cfg.auto_refill_session is True

    def test_selection_signature_changes_when_auto_refill_changes(self):
        dialog = _build_dialog_for_state_tests()

        before = dialog._selection_signature_payload()
        dialog._auto_refill_session_cb.setChecked(False)
        after = dialog._selection_signature_payload()

        assert before["auto_refill_session"] is True
        assert after["auto_refill_session"] is False
        assert before != after

    def test_live_preview_cache_stores_picker_snapshot(self):
        dialog = _build_dialog_for_state_tests()
        dialog._live_preview_cache = None
        dialog._live_preview_signature = None
        dialog._selection_signature = lambda: "sig-1"
        dialog._use_live_preview_enabled = True
        snapshot = SimpleNamespace(selected_ids=[1], ordered_priority_picked={"tag:writing": 1})
        result = SimpleNamespace(
            selected_ids=[101, 102],
            picked_meta={101: {"card_type": "topics"}},
            stats=SimpleNamespace(
                session={"type": {"topics": 1}, "tags": {}, "mode": {}},
                session_time={"type": {}, "tags": {}},
            ),
            picker_snapshot=snapshot,
        )

        dialog._cache_live_preview_result(result)
        cached = dialog.get_preview_override()

        assert dialog._live_preview_cache["picker_snapshot"].ordered_priority_picked == {"tag:writing": 1}
        assert cached["picker_snapshot"].selected_ids == [1]

    def test_load_profile_dict_restores_auto_refill_checkbox_state(self):
        dialog = SchedulerConfigDialog.__new__(SchedulerConfigDialog)
        dialog._count_spin = _FakeValueWidget()
        dialog._topics_slider = _FakeValueWidget()
        dialog._topics_left_lbl = SimpleNamespace(setText=lambda _text: None)
        dialog._topics_right_lbl = SimpleNamespace(setText=lambda _text: None)
        dialog._pdf_slider = _FakeValueWidget()
        dialog._pdf_left_lbl = SimpleNamespace(setText=lambda _text: None)
        dialog._pdf_right_lbl = SimpleNamespace(setText=lambda _text: None)
        dialog._random_slider = _FakeValueWidget()
        dialog._random_left_lbl = SimpleNamespace(setText=lambda _text: None)
        dialog._random_right_lbl = SimpleNamespace(setText=lambda _text: None)
        dialog._topics_lock_cb = _FakeCheckBox()
        dialog._pdf_lock_cb = _FakeCheckBox()
        dialog._priority_lock_cb = _FakeCheckBox()
        dialog._topics_group_edit = _FakeLineEdit()
        dialog._pdf_group_edit = _FakeLineEdit()
        dialog._priority_group_edit = _FakeLineEdit()
        dialog._rebalance_main_pool = lambda changed_key=None: None
        dialog._cb_new = _FakeCheckBox()
        dialog._cb_learning = _FakeCheckBox()
        dialog._cb_due = _FakeCheckBox()
        dialog._no_tags_cb = _FakeCheckBox()
        dialog._enforce_cb = _FakeCheckBox()
        dialog._auto_refill_session_cb = _FakeCheckBox()
        dialog._scope_combo = _FakeDataCombo([("Session", "session"), ("Daily", "daily")], current_data="session")
        dialog._day_end_preset = _FakeDataCombo([("04:00", "04:00"), ("Custom", None)], current_data="04:00")
        dialog._day_end_edit = SimpleNamespace(setTime=lambda _time: None)
        dialog._update_day_end_visibility = lambda: None
        dialog._saved_priority_order_map = {}
        dialog._priority_order_cb = _FakeCheckBox()
        dialog._funnel = _FakeFunnel()
        dialog._topics_filter_edit = _FakeLineEdit()
        dialog._items_filter_edit = _FakeLineEdit()
        dialog._preserve_order_cb = _FakeCheckBox()
        dialog._show_debug_cb = _FakeCheckBox()
        dialog._live_preview_dialog = _FakePreviewDialog()
        dialog._linked_rows = []
        dialog._ct_rows = []
        dialog._normalized_saved_filter = lambda key, source=None: str((source or {}).get(key, "") or "")
        dialog._priority_order_map_from_dict = SchedulerConfigDialog._priority_order_map_from_dict
        dialog._resolve_tag_for_current_profile = lambda tag: tag
        dialog._priority_order_for = lambda kind, value: None
        dialog._add_tag_row = lambda *args, **kwargs: None
        dialog._ensure_other_tag_row = lambda **kwargs: None
        dialog._finalize_tag_row_batch_restore = lambda: None
        dialog._update_other_label = lambda: None
        dialog._sync_priority_order_visibility = lambda: None
        dialog._refresh_expected_mix_preview = lambda: None
        dialog._refresh_counts = lambda: None
        dialog._schedule_live_preview_refresh = lambda: None
        dialog._remove_row = lambda row, allow_other=False: None

        dialog._load_profile_dict({"auto_refill_session": True, "use_live_preview": True})

        assert dialog._auto_refill_session_cb.isChecked() is True
        assert dialog._live_preview_dialog.synced is True

    def test_named_profile_save_load_preserves_auto_refill_session(self, monkeypatch):
        stored_config = {"dialog": {}, "profiles": {"Focus": {"session_card_count": 20}}}
        addon_manager = SimpleNamespace(
            getConfig=lambda _name: stored_config,
            writeConfig=lambda _name, config: None,
        )
        dialog = _build_dialog_for_profile_tests(
            stored_config["profiles"],
            selected_name="Focus",
            current_data={"session_card_count": 42, "auto_refill_session": True},
        )
        monkeypatch.setattr(_MOD, "mw", SimpleNamespace(addonManager=addon_manager))
        monkeypatch.setattr(_MOD, "tooltip", lambda _message: None)

        dialog._save_profile()

        assert stored_config["profiles"]["Focus"]["auto_refill_session"] is True
