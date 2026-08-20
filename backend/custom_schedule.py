"""Custom recurring schedule rules for browser-selected cards."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from calendar import monthrange

from aqt import mw

try:
    from .answer_schedule import (
        ReviewRevlogTracker,
        answer_revlog_snapshot,
        apply_review_interval,
        card_schedule_snapshot,
        current_answer_undo_step,
        is_nonrescheduling_filtered_card,
        new_answer_revlog_id,
        restore_card_schedule,
    )
    from .db import (
        clear_custom_schedule_rule,
        commit_custom_schedule_review,
        get_custom_schedule_rule,
        get_topic_schedule,
        reconcile_custom_schedule_review_state,
        set_custom_schedule_rule,
        set_topic_schedule,
    )
    from .paths import get_active_profile as _active_profile
    from .topic_scheduler import (
        consume_handled_topic_answer,
        effective_topic_maximum_interval_days,
        is_topic_card,
        sync_card_review_interval,
    )
except ImportError:
    from answer_schedule import (  # type: ignore
        ReviewRevlogTracker,
        answer_revlog_snapshot,
        apply_review_interval,
        card_schedule_snapshot,
        current_answer_undo_step,
        is_nonrescheduling_filtered_card,
        new_answer_revlog_id,
        restore_card_schedule,
    )
    from db import (  # type: ignore
        clear_custom_schedule_rule,
        commit_custom_schedule_review,
        get_custom_schedule_rule,
        get_topic_schedule,
        reconcile_custom_schedule_review_state,
        set_custom_schedule_rule,
        set_topic_schedule,
    )
    from paths import get_active_profile as _active_profile  # type: ignore
    from topic_scheduler import (  # type: ignore
        consume_handled_topic_answer,
        effective_topic_maximum_interval_days,
        is_topic_card,
        sync_card_review_interval,
    )

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_PENDING_CUSTOM_SCHEDULE_ANSWERS: dict[int, dict] = {}
_CUSTOM_SCHEDULE_REVLOG_TRACKER = ReviewRevlogTracker()

MODE_FIXED_REPEAT = "fixed_repeat"
MODE_MINIMUM_CADENCE = "minimum_cadence"
MODE_ONE_TIME = "one_time"
VALID_MODES = {MODE_FIXED_REPEAT, MODE_MINIMUM_CADENCE, MODE_ONE_TIME}

UNIT_DAYS = "days"
UNIT_WEEKS = "weeks"
UNIT_MONTHS = "months"
VALID_UNITS = {UNIT_DAYS, UNIT_WEEKS, UNIT_MONTHS}

_DEFAULT_MODE = MODE_MINIMUM_CADENCE
_DEFAULT_PRESETS = [
    {"label": "Daily", "interval_value": 1, "interval_unit": UNIT_DAYS},
    {"label": "Every 2 days", "interval_value": 2, "interval_unit": UNIT_DAYS},
    {"label": "Every 3 days", "interval_value": 3, "interval_unit": UNIT_DAYS},
    {"label": "Weekly", "interval_value": 1, "interval_unit": UNIT_WEEKS},
    {"label": "Every 2 weeks", "interval_value": 2, "interval_unit": UNIT_WEEKS},
    {"label": "Monthly", "interval_value": 1, "interval_unit": UNIT_MONTHS},
]


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        resolved = mw.addonManager.getConfig(addon_name) or {}
        return resolved if isinstance(resolved, dict) else {}
    except Exception:
        return {}


def normalize_custom_schedule_mode(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_MODES:
        return raw
    return _DEFAULT_MODE


def normalize_custom_schedule_unit(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_UNITS:
        return raw
    return UNIT_DAYS


def normalize_custom_schedule_interval_value(value) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 2
    return max(1, min(999, parsed))


def normalize_custom_schedule_preset(raw: dict | None, index: int = 0) -> dict:
    raw = raw or {}
    interval_value = normalize_custom_schedule_interval_value(raw.get("interval_value"))
    interval_unit = normalize_custom_schedule_unit(raw.get("interval_unit"))
    label = str(raw.get("label") or "").strip()
    if not label:
        label = format_custom_schedule_value(interval_value, interval_unit)
    return {
        "label": label[:120],
        "interval_value": interval_value,
        "interval_unit": interval_unit,
        "sort_order": max(0, int(raw.get("sort_order", index) or index)),
    }


def configured_custom_schedule_default_mode(config: dict | None = None) -> str:
    cfg = _resolved_config(config)
    return normalize_custom_schedule_mode(cfg.get("custom_schedule_default_mode"))


def configured_custom_schedule_presets(config: dict | None = None) -> list[dict]:
    cfg = _resolved_config(config)
    raw = cfg.get("custom_schedule_presets")
    if not isinstance(raw, list):
        raw = list(_DEFAULT_PRESETS)
    normalized: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        preset = normalize_custom_schedule_preset(item, index=index)
        key = (
            str(preset["label"]).strip().lower(),
            int(preset["interval_value"]),
            str(preset["interval_unit"]),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(preset)
    if not normalized:
        normalized = [normalize_custom_schedule_preset(item, index=i) for i, item in enumerate(_DEFAULT_PRESETS)]
    normalized.sort(key=lambda item: (int(item["sort_order"]), str(item["label"]).lower()))
    return normalized


def normalize_custom_schedule_rule(rule: dict | None) -> dict:
    base = rule or {}
    return {
        "card_id": int(base.get("card_id") or 0),
        "enabled": bool(base.get("enabled", True)),
        "mode": normalize_custom_schedule_mode(base.get("mode")),
        "interval_value": normalize_custom_schedule_interval_value(base.get("interval_value")),
        "interval_unit": normalize_custom_schedule_unit(base.get("interval_unit")),
        "preset_label": str(base.get("preset_label") or "").strip()[:120],
        "created_at": int(base.get("created_at") or 0),
        "updated_at": int(base.get("updated_at") or 0),
        "revision": max(0, int(base.get("revision") or 0)),
    }


def format_custom_schedule_value(interval_value: int, interval_unit: str) -> str:
    interval_value = normalize_custom_schedule_interval_value(interval_value)
    interval_unit = normalize_custom_schedule_unit(interval_unit)
    singular = {
        UNIT_DAYS: "day",
        UNIT_WEEKS: "week",
        UNIT_MONTHS: "month",
    }[interval_unit]
    plural = singular + "s"
    noun = singular if interval_value == 1 else plural
    return f"Every {interval_value} {noun}"


def format_custom_schedule_mode(mode: str) -> str:
    mode = normalize_custom_schedule_mode(mode)
    if mode == MODE_FIXED_REPEAT:
        return "Repeat exactly"
    if mode == MODE_ONE_TIME:
        return "One-time set due"
    return "Minimum cadence"


def format_custom_schedule_rule(rule: dict | None) -> str:
    if not rule:
        return ""
    normalized = normalize_custom_schedule_rule(rule)
    if not normalized.get("enabled"):
        return ""
    label = str(normalized.get("preset_label") or "").strip()
    if not label:
        label = format_custom_schedule_value(
            int(normalized["interval_value"]),
            str(normalized["interval_unit"]),
        )
    return f"{label} · {format_custom_schedule_mode(str(normalized['mode']))}"


def add_calendar_months(start: date, months: int) -> date:
    months = max(1, int(months))
    total_month = (start.month - 1) + months
    year = start.year + total_month // 12
    month = (total_month % 12) + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def anki_logical_today(*, collection=None) -> date:
    """Return the calendar date at the start of Anki's current logical day."""
    try:
        col = collection or mw.col
        next_day_at = int(col.sched.day_cutoff)
        if next_day_at > 0:
            next_rollover_date = datetime.fromtimestamp(next_day_at).date()
            return next_rollover_date - timedelta(days=1)
    except Exception:
        pass
    return date.today()


def rule_days_from_today(
    interval_value: int,
    interval_unit: str,
    *,
    today: date | None = None,
) -> int:
    today = today or anki_logical_today()
    interval_value = normalize_custom_schedule_interval_value(interval_value)
    interval_unit = normalize_custom_schedule_unit(interval_unit)
    if interval_unit == UNIT_DAYS:
        return interval_value
    if interval_unit == UNIT_WEEKS:
        return interval_value * 7
    target = add_calendar_months(today, interval_value)
    return max(1, (target - today).days)


def resolve_topic_custom_schedule(
    requested_days: int,
    rule: dict | None,
    *,
    today: date | None = None,
    maximum_interval_days: int = 36500,
) -> dict:
    """Resolve one final topic interval before either scheduler writes state.

    Topic A-factor scheduling supplies ``requested_days``. An enabled custom
    rule then has explicit precedence: exact and one-time rules replace it,
    while minimum cadence only pulls a later topic interval closer.
    """
    maximum = max(1, min(36500, int(maximum_interval_days or 36500)))
    requested = max(1, min(maximum, int(requested_days or 1)))
    if not rule or not bool(rule.get("enabled")):
        return {
            "interval_days": requested,
            "mode": "",
            "rule": None,
            "consumed_one_time": False,
        }

    normalized = normalize_custom_schedule_rule(rule)
    target_days = min(
        maximum,
        rule_days_from_today(
            int(normalized["interval_value"]),
            str(normalized["interval_unit"]),
            today=today,
        ),
    )
    mode = str(normalized["mode"])
    if mode == MODE_MINIMUM_CADENCE:
        final_days = min(requested, target_days)
    else:
        final_days = target_days
    return {
        "interval_days": max(1, min(maximum, int(final_days))),
        "mode": mode,
        "rule": normalized,
        "consumed_one_time": mode == MODE_ONE_TIME,
    }


def _current_card_interval_days(card) -> int | None:
    try:
        interval = int(getattr(card, "ivl", 0) or 0)
    except Exception:
        interval = 0
    if interval > 0:
        return interval
    return None


def apply_rule_now_to_card(card_id: int, rule: dict | None = None, *, today: date | None = None) -> bool:
    normalized = normalize_custom_schedule_rule(
        rule or get_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card_id))
    )
    if not normalized.get("enabled"):
        return False
    try:
        card = mw.col.get_card(int(card_id))
    except Exception:
        card = None
    if card is None:
        return False

    target_days = rule_days_from_today(
        int(normalized["interval_value"]),
        str(normalized["interval_unit"]),
        today=today,
    )
    mode = str(normalized["mode"])
    topic_card = is_topic_card(card)
    if topic_card:
        target_days = min(target_days, effective_topic_maximum_interval_days(card))
    if mode == MODE_MINIMUM_CADENCE:
        current_days = _current_card_interval_days(card)
        if current_days is not None and current_days <= target_days:
            return False

    mw.col.sched.set_due_date([int(card_id)], str(target_days))
    if topic_card:
        sync_card_review_interval(int(card_id), target_days)
    if mode == MODE_FIXED_REPEAT and topic_card:
        try:
            a_factor, _interval = get_topic_schedule(_ADDON_DIR, _active_profile(), int(card_id))
            set_topic_schedule(_ADDON_DIR, _active_profile(), int(card_id), a_factor, target_days)
        except Exception:
            pass
    if mode == MODE_ONE_TIME:
        clear_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card_id))
    return True


def prepare_custom_schedule_answer(card) -> None:
    """Capture the rule and pre-answer revlog for a non-topic review."""
    if card is None:
        return
    try:
        card_id = int(card.id)
    except Exception:
        return
    _PENDING_CUSTOM_SCHEDULE_ANSWERS.pop(card_id, None)
    try:
        if is_topic_card(card):
            return
        profile = _active_profile()
        rule = get_custom_schedule_rule(_ADDON_DIR, profile, card_id)
    except Exception as exc:
        print(f"[Incremento] custom schedule preparation error: {exc}")
        return
    if not rule or not bool(rule.get("enabled")):
        return
    snapshot_valid, previous_revlog_id = answer_revlog_snapshot(
        card_id,
        collection=getattr(mw, "col", None),
    )
    if not snapshot_valid:
        print("[Incremento] custom schedule preparation error: revlog query failed")
        return
    _PENDING_CUSTOM_SCHEDULE_ANSWERS[card_id] = {
        "profile": profile,
        "rule": normalize_custom_schedule_rule(rule),
        "previous_revlog_id": previous_revlog_id,
        "preview_only": is_nonrescheduling_filtered_card(
            card,
            collection=getattr(mw, "col", None),
        ),
    }


def reset_custom_schedule_answer_runtime_state() -> None:
    _PENDING_CUSTOM_SCHEDULE_ANSWERS.clear()
    _CUSTOM_SCHEDULE_REVLOG_TRACKER.clear()


def reconcile_custom_schedule_state_after_anki_operation(undo_info=None) -> None:
    transitions = _CUSTOM_SCHEDULE_REVLOG_TRACKER.transitions(
        undo_info,
        collection=getattr(mw, "col", None),
    )
    for profile, card_id, current, previous in transitions:
        try:
            reconcile_custom_schedule_review_state(
                _ADDON_DIR,
                profile,
                card_id,
                current,
                previous,
            )
        except Exception as exc:
            print(f"[Incremento] custom schedule undo/redo reconciliation error: {exc}")


def apply_custom_schedule_after_answer(reviewer, card, ease: int) -> None:
    del reviewer, ease
    if card is None:
        return
    # Topic scheduling resolves custom-rule precedence and persists both
    # results atomically in topic_scheduler.on_topic_card_answered(). Running
    # this hook as well would create a second due-date operation and history.
    if consume_handled_topic_answer(int(card.id)) or is_topic_card(card):
        return
    try:
        card_id = int(card.id)
    except Exception:
        return
    pending = _PENDING_CUSTOM_SCHEDULE_ANSWERS.pop(card_id, None)
    if not isinstance(pending, dict):
        return
    if bool(pending.get("preview_only")):
        return
    profile = str(pending.get("profile") or _active_profile())
    normalized = normalize_custom_schedule_rule(pending.get("rule"))
    previous_revlog_id = max(0, int(pending.get("previous_revlog_id") or 0))
    target_days = rule_days_from_today(
        int(normalized["interval_value"]),
        str(normalized["interval_unit"]),
    )
    mode = str(normalized["mode"])
    try:
        latest_card = mw.col.get_card(card_id)
    except Exception:
        latest_card = card

    if mode == MODE_MINIMUM_CADENCE:
        current_days = _current_card_interval_days(latest_card)
        if current_days is not None and current_days <= target_days:
            return

    answer_undo_step = current_answer_undo_step(
        collection=getattr(mw, "col", None)
    )
    if answer_undo_step <= 0:
        print("[Incremento] custom schedule error: Anki answer undo step is unavailable")
        return
    revlog_id = new_answer_revlog_id(
        card_id,
        previous_revlog_id,
        collection=getattr(mw, "col", None),
    )
    if revlog_id <= 0:
        print("[Incremento] custom schedule error: Anki did not create a new answer revlog")
        return

    post_answer_snapshot = card_schedule_snapshot(latest_card)
    try:
        apply_review_interval(
            card_id,
            target_days,
            answer_undo_step=answer_undo_step,
            collection=getattr(mw, "col", None),
        )
        commit_custom_schedule_review(
            _ADDON_DIR,
            profile,
            card_id,
            anki_revlog_id=revlog_id,
            scheduled_interval=target_days,
            custom_schedule_mode=mode,
            custom_schedule_rule=normalized,
            consumed_one_time=mode == MODE_ONE_TIME,
        )
    except Exception as exc:
        try:
            restore_card_schedule(
                card_id,
                post_answer_snapshot,
                answer_undo_step=answer_undo_step,
                collection=getattr(mw, "col", None),
            )
        except Exception as restore_error:
            print(
                "[Incremento] failed to restore Anki schedule after custom error: "
                f"{restore_error}"
            )
        print(f"[Incremento] custom schedule error: {exc}")
        return
    _CUSTOM_SCHEDULE_REVLOG_TRACKER.track(profile, card_id, revlog_id)


def save_custom_schedule_rule(
    card_ids: list[int] | tuple[int, ...] | set[int],
    *,
    mode: str,
    interval_value: int,
    interval_unit: str,
    preset_label: str = "",
) -> int:
    normalized_ids = sorted({int(card_id) for card_id in (card_ids or [])})
    if not normalized_ids:
        return 0
    for card_id in normalized_ids:
        set_custom_schedule_rule(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            enabled=True,
            mode=mode,
            interval_value=interval_value,
            interval_unit=interval_unit,
            preset_label=preset_label,
        )
    return len(normalized_ids)


def clear_custom_schedule_rules(card_ids: list[int] | tuple[int, ...] | set[int]) -> int:
    deleted = 0
    for card_id in sorted({int(card_id) for card_id in (card_ids or [])}):
        if clear_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card_id)):
            deleted += 1
    return deleted
