import config_service
import pytest


def test_legacy_document_mix_migrates_current_state_and_presets_once_without_mutating_input():
    from copy import deepcopy
    raw = {
        "config_schema_version": 2,
        "dialog": {"topics_slider": 100, "pdf_slider": 34, "future": {"keep": True}},
        "profiles": {"Half": {"topics_slider": 50, "pdf_slider": 50}},
    }
    original = deepcopy(raw)

    migrated = config_service.normalize_config(raw)

    assert migrated["dialog"] == {
        "topics_slider": 34, "pdf_slider": 0, "document_mix_version": 2, "future": {"keep": True},
    }
    assert migrated["scheduler_presets"]["Half"] == {
        "topics_slider": 25, "pdf_slider": 33, "document_mix_version": 2,
    }
    assert migrated["profiles"] == migrated["scheduler_presets"]
    assert config_service.normalize_config(migrated) == migrated
    assert raw == original


def test_new_topic_document_mix_is_not_reinterpreted_as_legacy():
    dialog = {"topics_slider": 40, "pdf_slider": 90, "document_mix_version": 2}
    normalized = config_service.normalize_config({"dialog": dialog, "scheduler_presets": {"New": dialog}})

    assert normalized["dialog"] == dialog
    assert normalized["scheduler_presets"]["New"] == dialog


@pytest.mark.parametrize("topics_slider", [0, 40, 100], ids=["all-topics", "mixed", "all-items"])
@pytest.mark.parametrize("pdf_slider", [0, 34, 50, 90, 100], ids=["all-docs", "screenshot", "half-docs", "few-docs", "no-docs"])
def test_document_mix_migration_preserves_legacy_three_way_targets_with_slider_rounding(topics_slider, pdf_slider):
    dialog = {"topics_slider": topics_slider, "pdf_slider": pdf_slider}
    migrated = config_service.normalize_config({"dialog": dialog})["dialog"]
    topics = 1 - migrated["topics_slider"] / 100
    docs = 1 - migrated["pdf_slider"] / 100
    actual = {"pdf": topics * docs, "topics": topics * (1 - docs), "items": 1 - topics}
    old_topics = 1 - topics_slider / 100
    old_docs = 1 - pdf_slider / 100

    assert actual == pytest.approx({
        "pdf": old_docs, "topics": old_topics * (1 - old_docs), "items": (1 - old_topics) * (1 - old_docs),
    }, abs=0.01)
    assert config_service.normalize_config({"dialog": migrated})["dialog"] == migrated


def test_future_document_mix_marker_and_unknown_preset_fields_are_preserved():
    dialog = {"topics_slider": 40, "pdf_slider": 90, "document_mix_version": 3, "future": {"keep": True}}
    result = config_service.normalize_config({"dialog": dialog, "scheduler_presets": {"Future": dialog}})

    assert result["dialog"] == dialog
    assert result["scheduler_presets"]["Future"] == dialog


@pytest.mark.parametrize("raw,expected", [(None,"auto"),("hr", "hr"),("zh_CN","zh-Hans"),
    ("en-US","en"),("invalid","auto"),([],"auto"),
    ("custom:pt_br", "custom:pt-BR"), ("custom:hr", "custom:hr"),
    ("custom:../../x", "auto")])
def test_ui_language_is_normalized_without_mutating_other_config(raw, expected):
    config = {"ui_language": raw, "future": {"kept": True}}
    assert config_service.normalize_config(config)["ui_language"] == expected
    assert config_service.normalize_config(config)["future"] == {"kept": True}
    assert config["ui_language"] == raw


def test_missing_ui_language_defaults_to_auto():
    assert config_service.normalize_config({})["ui_language"] == "auto"


@pytest.mark.parametrize(
    "raw_mode, expected_mode",
    [
        (None, "original"),
        ("original", "original"),
        ("dark", "dark"),
        ("night", "night"),
        (" DARK ", "dark"),
        ("sepia", "original"),
        ([], "original"),
    ],
)
def test_pdf_appearance_policy_is_normalized(raw_mode, expected_mode):
    normalized = config_service.normalize_config(
        {
            "pdf_default_appearance": raw_mode,
            "pdf_force_default_appearance": "yes",
            "future_setting": {"keep": True},
        }
    )

    assert normalized["pdf_default_appearance"] == expected_mode
    assert normalized["pdf_force_default_appearance"] is True
    assert normalized["future_setting"] == {"keep": True}


def test_missing_pdf_appearance_policy_defaults_to_original_without_force():
    normalized = config_service.normalize_config({})

    assert normalized["pdf_default_appearance"] == "original"
    assert normalized["pdf_force_default_appearance"] is False


def test_pdf_snapshot_field_preferences_are_bounded_and_normalized():
    normalized = config_service.normalize_config(
        {
            "pdf_snapshot_auto_field_enabled": "yes",
            "pdf_snapshot_auto_fields": {
                " Basic ": " Back ",
                "": "ignored",
                "Missing field": "",
                42: "ignored",
            },
        }
    )

    assert normalized["pdf_snapshot_auto_field_enabled"] is True
    assert normalized["pdf_snapshot_auto_fields"] == {"Basic": "Back"}


def test_pdf_snapshot_field_preferences_default_to_asking_each_time():
    normalized = config_service.normalize_config({})

    assert normalized["pdf_snapshot_auto_field_enabled"] is False
    assert normalized["pdf_snapshot_auto_fields"] == {}


@pytest.mark.parametrize("raw, expected", [
    ({}, "topic/done"),
    ({"topic_done_tag": "reading::finished"}, "reading::finished"),
    ({"topic_done_tag": "  topic/done  "}, "topic/done"),
    ({"topic_done_tag": ""}, "topic/done"),
    ({"topic_done_tag": None}, "topic/done"),
    ({"topic_done_tag": ["one", "two"]}, "topic/done"),
    ({"topic_done_tag": "two tags"}, "topic/done"),
    ({"topic_done_tag": "bad\u0000tag"}, "topic/done"),
    ({"topic_done_tag": "::"}, "topic/done"),
    ({"topic_done_tag": "x" * 256}, "topic/done"),
])
def test_done_tag_normalization_keeps_one_valid_tag_or_default(raw, expected):
    assert config_service.normalize_config(raw)["topic_done_tag"] == expected


def test_done_tag_round_trips_through_config_without_replacing_other_settings():
    from unittest.mock import Mock

    manager = Mock()
    config_service.save_addon_config(manager, "incremento", {
        "topic_done_tag": "  reading::finished  ", "future_setting": {"keep": True},
    })
    stored = manager.writeConfig.call_args.args[1]
    manager.getConfig.return_value = stored
    loaded = config_service.load_addon_config(manager, "incremento")
    assert loaded["topic_done_tag"] == "reading::finished"
    assert loaded["future_setting"] == {"keep": True}


def test_normalize_config_migrates_named_scheduler_profiles():
    result = config_service.normalize_config(
        {"profiles": {"Focus": {"session_card_count": 20}}}
    )

    assert result["config_schema_version"] == 3
    assert result["scheduler_presets"] == {
        "Focus": {"session_card_count": 20}
    }
    assert result["profiles"] == result["scheduler_presets"]


def test_normalize_config_clamps_high_risk_values_and_preserves_unknown():
    result = config_service.normalize_config(
        {
            "dialog": {
                "session_card_count": 100_000,
                "day_end_time": "99:99",
                "include_due": "false",
            },
            "topic_more_adjustment_percent": -5,
            "future_setting": {"keep": True},
        }
    )

    assert result["dialog"]["session_card_count"] == 9999
    assert result["dialog"]["day_end_time"] == "04:00"
    assert result["dialog"]["include_due"] is False
    assert result["topic_more_adjustment_percent"] == 0.0
    assert result["future_setting"] == {"keep": True}


def test_normalize_config_bounds_onboarding_and_session_setup_mode():
    result = config_service.normalize_config(
        {
            "onboarding_completed_version": "-4",
            "dialog": {"setup_mode": "expert"},
        }
    )

    assert result["onboarding_completed_version"] == 0
    assert result["dialog"]["setup_mode"] == "basic"

    advanced = config_service.normalize_config(
        {
            "onboarding_completed_version": "2",
            "dialog": {"setup_mode": " ADVANCED "},
        }
    )
    assert advanced["onboarding_completed_version"] == 2
    assert advanced["dialog"]["setup_mode"] == "advanced"


def test_normalize_config_repairs_reviewer_priority_badge_card_types():
    normalized = config_service.normalize_config(
        {
            "reviewer_priority_badge_card_types": {
                "topics": "false",
                "items": 0,
                "future_type": "keep",
            }
        }
    )

    assert normalized["reviewer_priority_badge_card_types"] == {
        "topics": False,
        "items": False,
        "future_type": "keep",
    }
    assert config_service.normalize_config(
        {"reviewer_priority_badge_card_types": "invalid"}
    )["reviewer_priority_badge_card_types"] == {
        "topics": True,
        "items": True,
    }


def test_reviewer_button_visibility_defaults_visible_and_preserves_one_disabled_choice():
    assert config_service.configured_reviewer_button_visibility({}) == {
        "done": True, "postpone": True, "extract": True,
    }
    normalized = config_service.normalize_config({
        "reviewer_button_visibility": {
            "done": "false", "postpone": True, "extract": 0, "future": "keep",
        },
        "other_setting": "untouched",
    })
    assert normalized["reviewer_button_visibility"] == {
        "done": False, "postpone": True, "extract": False, "future": "keep",
    }
    assert normalized["other_setting"] == "untouched"
    assert config_service.configured_reviewer_button_visibility(normalized) == {
        "done": False, "postpone": True, "extract": False,
    }


def test_reviewer_button_group_toggle_normalizes_without_changing_individual_choices():
    assert config_service.configured_reviewer_button_group_visible({}) is True
    normalized = config_service.normalize_config({
        "reviewer_button_group_visible": "false",
        "reviewer_button_visibility": {"done": False, "postpone": True, "extract": True},
    })
    assert normalized["reviewer_button_group_visible"] is False
    assert config_service.configured_reviewer_button_group_visible(normalized) is False
    assert config_service.configured_reviewer_button_visibility(normalized) == {
        "done": False, "postpone": True, "extract": True,
    }


def test_automatic_backup_config_is_profile_scoped_and_invalid_values_fail_closed():
    result = config_service.normalize_config({"automatic_backups": {
        "P": {"enabled": True, "directory": "/backup", "versions": 99,
              "on_close": True, "last_close_failed": True},
        "Q": {"enabled": True, "directory": "bad\x00path"},
    }})
    assert result["automatic_backups"]["P"]["enabled"] is True
    assert result["automatic_backups"]["P"]["versions"] == 20
    assert result["automatic_backups"]["P"]["on_close"] is True
    assert result["automatic_backups"]["P"]["last_close_failed"] is True
    assert result["automatic_backups"]["Q"]["enabled"] is False
    assert result["automatic_backups"]["Q"]["directory"] == ""


def test_migrate_persisted_config_writes_only_when_changed():
    class _Manager:
        def __init__(self):
            self.config = {"profiles": {}}
            self.writes = []

        def getConfig(self, _package):
            return self.config

        def writeConfig(self, _package, config):
            self.config = config
            self.writes.append(config)

    manager = _Manager()
    normalized, changed = config_service.migrate_persisted_config(manager, "incremento")
    assert changed is True
    assert len(manager.writes) == 1

    same, changed_again = config_service.migrate_persisted_config(manager, "incremento")
    assert changed_again is False
    assert same == normalized
    assert len(manager.writes) == 1
