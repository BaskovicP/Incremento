import importlib.util
import os
import sys
from types import SimpleNamespace


_SPEC = importlib.util.spec_from_file_location(
    "_incremento_learn_dialog",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "learn_dialog.py")),
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["_incremento_learn_dialog"] = _MOD
_SPEC.loader.exec_module(_MOD)

_write_named_scheduler_profile = _MOD._write_named_scheduler_profile
_rename_named_scheduler_profile = _MOD._rename_named_scheduler_profile


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
    def test_renames_profile_without_touching_dialog_config(self, monkeypatch):
        stored_config = {
            "dialog": {"session_card_count": 50, "topics_slider": 10},
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
        assert stored_config["dialog"] == {"session_card_count": 50, "topics_slider": 10}
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
