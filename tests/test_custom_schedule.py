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


def test_topic_custom_schedule_precedence_is_explicit():
    fixed = custom_schedule.resolve_topic_custom_schedule(
        30,
        {
            "enabled": True,
            "mode": "fixed_repeat",
            "interval_value": 2,
            "interval_unit": "days",
        },
    )
    minimum = custom_schedule.resolve_topic_custom_schedule(
        30,
        {
            "enabled": True,
            "mode": "minimum_cadence",
            "interval_value": 1,
            "interval_unit": "weeks",
        },
    )
    one_time = custom_schedule.resolve_topic_custom_schedule(
        30,
        {
            "enabled": True,
            "mode": "one_time",
            "interval_value": 3,
            "interval_unit": "days",
        },
    )
    assert fixed["interval_days"] == 2
    assert minimum["interval_days"] == 7
    assert one_time["interval_days"] == 3
    assert one_time["consumed_one_time"] is True


def test_topic_custom_schedule_respects_maximum_interval():
    resolved = custom_schedule.resolve_topic_custom_schedule(
        90,
        {
            "enabled": True,
            "mode": "fixed_repeat",
            "interval_value": 100,
            "interval_unit": "days",
        },
        maximum_interval_days=45,
    )
    assert resolved["interval_days"] == 45


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


def test_apply_custom_schedule_after_answer_skips_topic_already_handled_by_topic_hook():
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
        patch.object(custom_schedule, "consume_handled_topic_answer", return_value=True),
        patch.object(custom_schedule, "sync_card_review_interval") as sync_interval,
        patch.object(custom_schedule, "get_topic_schedule", return_value=(1.8, 9)),
        patch.object(custom_schedule, "set_topic_schedule") as set_topic_schedule,
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
    ):
        custom_schedule.apply_custom_schedule_after_answer(None, fake_card, 3)

    fake_sched.set_due_date.assert_not_called()
    sync_interval.assert_not_called()
    set_topic_schedule.assert_not_called()


def test_apply_custom_schedule_after_answer_one_time_clears_rule():
    fake_card = SimpleNamespace(id=15, ivl=12)
    latest_card = SimpleNamespace(id=15, ivl=12)
    fake_sched = MagicMock()
    fake_col = MagicMock()
    fake_col.get_card.return_value = latest_card
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
        patch.object(custom_schedule, "consume_handled_topic_answer", return_value=False),
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
        patch.object(custom_schedule, "answer_revlog_snapshot", return_value=(True, 100)),
        patch.object(custom_schedule, "new_answer_revlog_id", return_value=200),
        patch.object(custom_schedule, "current_answer_undo_step", return_value=77),
        patch.object(custom_schedule, "card_schedule_snapshot", return_value={"ivl": 12}),
        patch.object(custom_schedule, "apply_review_interval") as apply_interval,
        patch.object(custom_schedule, "commit_custom_schedule_review") as commit_review,
        patch.object(custom_schedule._CUSTOM_SCHEDULE_REVLOG_TRACKER, "track") as track,
    ):
        custom_schedule.prepare_custom_schedule_answer(fake_card)
        custom_schedule.apply_custom_schedule_after_answer(None, fake_card, 3)

    fake_sched.set_due_date.assert_not_called()
    apply_interval.assert_called_once_with(
        15,
        7,
        answer_undo_step=77,
        collection=fake_col,
    )
    assert commit_review.call_args.kwargs["anki_revlog_id"] == 200
    assert commit_review.call_args.kwargs["consumed_one_time"] is True
    track.assert_called_once_with("TestProfile", 15, 200)


def test_preview_answer_does_not_apply_or_consume_custom_schedule():
    card = SimpleNamespace(id=18, did=9, odid=1, ivl=12)
    fake_col = MagicMock()
    fake_col.decks.get.return_value = {"dyn": 1, "resched": False}
    fake_mw = SimpleNamespace(col=fake_col)
    rule = {
        "enabled": True,
        "mode": "one_time",
        "interval_value": 2,
        "interval_unit": "days",
        "revision": 1,
    }
    with (
        patch.object(custom_schedule, "mw", fake_mw),
        patch.object(custom_schedule, "is_topic_card", return_value=False),
        patch.object(custom_schedule, "consume_handled_topic_answer", return_value=False),
        patch.object(custom_schedule, "get_custom_schedule_rule", return_value=rule),
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
        patch.object(custom_schedule, "answer_revlog_snapshot", return_value=(True, 100)),
        patch.object(custom_schedule, "apply_review_interval") as apply_interval,
        patch.object(custom_schedule, "commit_custom_schedule_review") as commit_review,
    ):
        custom_schedule.prepare_custom_schedule_answer(card)
        custom_schedule.apply_custom_schedule_after_answer(None, card, 3)

    apply_interval.assert_not_called()
    commit_review.assert_not_called()


def test_custom_schedule_after_answer_requires_a_new_revlog():
    card = SimpleNamespace(id=16, ivl=12)
    fake_col = MagicMock()
    fake_col.get_card.return_value = card
    fake_mw = SimpleNamespace(col=fake_col)
    rule = {
        "enabled": True,
        "mode": "fixed_repeat",
        "interval_value": 2,
        "interval_unit": "days",
    }
    with (
        patch.object(custom_schedule, "mw", fake_mw),
        patch.object(custom_schedule, "is_topic_card", return_value=False),
        patch.object(custom_schedule, "consume_handled_topic_answer", return_value=False),
        patch.object(custom_schedule, "get_custom_schedule_rule", return_value=rule),
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
        patch.object(custom_schedule, "answer_revlog_snapshot", return_value=(True, 100)),
        patch.object(custom_schedule, "new_answer_revlog_id", return_value=0),
        patch.object(custom_schedule, "current_answer_undo_step", return_value=77),
        patch.object(custom_schedule, "apply_review_interval") as apply_interval,
    ):
        custom_schedule.prepare_custom_schedule_answer(card)
        custom_schedule.apply_custom_schedule_after_answer(None, card, 3)

    apply_interval.assert_not_called()


def test_custom_schedule_commit_failure_restores_post_answer_card():
    card = SimpleNamespace(id=17, ivl=12)
    fake_col = MagicMock()
    fake_col.get_card.return_value = card
    fake_mw = SimpleNamespace(col=fake_col)
    rule = {
        "enabled": True,
        "mode": "fixed_repeat",
        "interval_value": 2,
        "interval_unit": "days",
    }
    with (
        patch.object(custom_schedule, "mw", fake_mw),
        patch.object(custom_schedule, "is_topic_card", return_value=False),
        patch.object(custom_schedule, "consume_handled_topic_answer", return_value=False),
        patch.object(custom_schedule, "get_custom_schedule_rule", return_value=rule),
        patch.object(custom_schedule, "_active_profile", return_value="TestProfile"),
        patch.object(custom_schedule, "answer_revlog_snapshot", return_value=(True, 100)),
        patch.object(custom_schedule, "new_answer_revlog_id", return_value=101),
        patch.object(custom_schedule, "current_answer_undo_step", return_value=77),
        patch.object(custom_schedule, "card_schedule_snapshot", return_value={"ivl": 12}),
        patch.object(custom_schedule, "apply_review_interval"),
        patch.object(
            custom_schedule,
            "commit_custom_schedule_review",
            side_effect=RuntimeError("db failed"),
        ),
        patch.object(custom_schedule, "restore_card_schedule") as restore,
        patch.object(custom_schedule._CUSTOM_SCHEDULE_REVLOG_TRACKER, "track") as track,
    ):
        custom_schedule.prepare_custom_schedule_answer(card)
        custom_schedule.apply_custom_schedule_after_answer(None, card, 3)

    restore.assert_called_once_with(
        17,
        {"ivl": 12},
        answer_undo_step=77,
        collection=fake_col,
    )
    track.assert_not_called()


def test_profile_reset_discards_pending_and_tracked_custom_schedule_state():
    custom_schedule._PENDING_CUSTOM_SCHEDULE_ANSWERS[42] = {"profile": "OldProfile"}
    custom_schedule._CUSTOM_SCHEDULE_REVLOG_TRACKER.track("OldProfile", 42, 100)

    custom_schedule.reset_custom_schedule_answer_runtime_state()

    assert custom_schedule._PENDING_CUSTOM_SCHEDULE_ANSWERS == {}
    assert custom_schedule._CUSTOM_SCHEDULE_REVLOG_TRACKER._cards == {}
