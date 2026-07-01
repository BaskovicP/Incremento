import importlib.util
import os
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


custom_schedule = _load("_incremento_custom_schedule", "backend/custom_schedule.py")


def test_configured_custom_schedule_defaults():
    assert custom_schedule.configured_custom_schedule_default_mode({}) == "minimum_cadence"
    presets = custom_schedule.configured_custom_schedule_presets({})
    assert any(preset["label"] == "Every 2 days" for preset in presets)
    assert any(preset["interval_unit"] == "months" for preset in presets)


def test_add_calendar_months_clamps_to_end_of_month():
    assert custom_schedule.add_calendar_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert custom_schedule.rule_days_from_today(1, "months", today=date(2026, 1, 31)) == 28


def test_format_custom_schedule_rule_uses_preset_label_when_present():
    label = custom_schedule.format_custom_schedule_rule(
        {
            "enabled": True,
            "mode": "minimum_cadence",
            "interval_value": 2,
            "interval_unit": "days",
            "preset_label": "Every 2 days",
        }
    )
    assert label == "Every 2 days · Minimum cadence"


def test_format_custom_schedule_rule_returns_empty_for_missing_rule():
    assert custom_schedule.format_custom_schedule_rule(None) == ""


def test_apply_rule_now_skips_minimum_cadence_when_card_is_already_sooner():
    fake_card = SimpleNamespace(id=10, ivl=1)
    fake_sched = MagicMock()
    fake_col = MagicMock()
    fake_col.get_card.return_value = fake_card
    fake_col.sched = fake_sched
    fake_mw = SimpleNamespace(col=fake_col)
    with patch.object(custom_schedule, "mw", fake_mw):
        changed = custom_schedule.apply_rule_now_to_card(
            10,
            {
                "enabled": True,
                "mode": "minimum_cadence",
                "interval_value": 2,
                "interval_unit": "days",
            },
            today=date(2026, 4, 23),
        )
    assert changed is False
    fake_sched.set_due_date.assert_not_called()


def test_apply_custom_schedule_after_answer_fixed_repeat_updates_topic_interval():
    fake_card = SimpleNamespace(id=12, ivl=9)
    fake_sched = MagicMock()
    fake_col = MagicMock()
    fake_col.get_card.return_value = fake_card
    fake_col.sched = fake_sched
    fake_mw = SimpleNamespace(col=fake_col)
    with (
        patch.object(custom_schedule, "mw", fake_mw),
        patch.object(
            custom_schedule,
            "get_custom_schedule_rule",
            return_value={
                "enabled": True,
                "mode": "fixed_repeat",
                "interval_value": 2,
                "interval_unit": "days",
            },
        ),
        patch.object(custom_schedule, "is_topic_card", return_value=True),
        patch.object(custom_schedule, "sync_card_review_interval") as sync_interval,
        patch.object(custom_schedule, "get_topic_schedule", return_value=(1.8, 9)),
        patch.object(custom_schedule, "set_topic_schedule") as set_topic_schedule,
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
    ):
        custom_schedule.apply_custom_schedule_after_answer(None, fake_card, 3)

    fake_sched.set_due_date.assert_called_once_with([12], "2")
    sync_interval.assert_called_once_with(12, 2)
    set_topic_schedule.assert_called_once_with(
        custom_schedule._ADDON_DIR,
        "TestProfile",
        12,
        1.8,
        2,
    )


def test_apply_custom_schedule_after_answer_one_time_clears_rule():
    fake_card = SimpleNamespace(id=15, ivl=12)
    fake_sched = MagicMock()
    fake_col = MagicMock()
    fake_col.get_card.return_value = fake_card
    fake_col.sched = fake_sched
    fake_mw = SimpleNamespace(col=fake_col)
    with (
        patch.object(custom_schedule, "mw", fake_mw),
        patch.object(
            custom_schedule,
            "get_custom_schedule_rule",
            return_value={
                "enabled": True,
                "mode": "one_time",
                "interval_value": 1,
                "interval_unit": "weeks",
            },
        ),
        patch.object(custom_schedule, "is_topic_card", return_value=False),
        patch.object(custom_schedule, "clear_custom_schedule_rule") as clear_rule,
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
    ):
        custom_schedule.apply_custom_schedule_after_answer(None, fake_card, 3)

    fake_sched.set_due_date.assert_called_once_with([15], "7")
    clear_rule.assert_called_once_with(custom_schedule._ADDON_DIR, "TestProfile", 15)
