import config_service
import pytest


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

    assert result["config_schema_version"] == 2
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
