"""A-factor scheduler for topic cards (SuperMemo SM-15 spec for topics).

Topic cards are scheduled independently of FSRS using the SuperMemo A-factor
formula:

    next_interval = current_interval × A-factor   (spec: topics)

The topic choice changes both the immediate next interval and the persistent
A-factor to signal how urgently the topic should be reviewed. More, Same, and
Less are frequency preferences rather than recall grades, so all three submit
Anki Good while Incremento retains the original choice independently. The
percentages below are defaults and can be changed in Topics settings:

  More — 90% of normal interval; A-factor ×0.9  (important → show sooner)
  Same — normal interval; A-factor unchanged
  Less — 110% of normal interval; A-factor ×1.1  (less urgent → grow faster)

A-factor is clamped to [1.1, 100.0]. Default: 3.5.
"""

import math
import os
from dataclasses import dataclass
from typing import Literal

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
        commit_topic_review,
        get_custom_schedule_rule,
        get_topic_schedule_state,
        reconcile_topic_review_state,
        topic_schedule_exists,
    )
    from .knowledge_tree import configured_topic_tags as configured_add_card_topic_tags
    from .knowledge_tree import configured_item_tags as configured_add_card_item_tags
    from .scheduler_config import load_scheduler_config
    from .paths import get_active_profile as _active_profile
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
        commit_topic_review,
        get_custom_schedule_rule,
        get_topic_schedule_state,
        reconcile_topic_review_state,
        topic_schedule_exists,
    )
    from knowledge_tree import configured_topic_tags as configured_add_card_topic_tags  # type: ignore
    from knowledge_tree import configured_item_tags as configured_add_card_item_tags  # type: ignore
    from scheduler_config import load_scheduler_config  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_A_MIN = 1.1
_A_MAX = 100.0
_DEFAULT_TOPIC_A_FACTOR = 3.5
_DEFAULT_TOPIC_MORE_ADJUSTMENT_PERCENT = 10.0
_DEFAULT_TOPIC_LESS_ADJUSTMENT_PERCENT = 10.0
_DEFAULT_TOPIC_MAXIMUM_INTERVAL_DAYS = 36500
TOPIC_REVIEW_BUTTONS: tuple[tuple[int, str], ...] = (
    (1, "More"),
    (2, "Same"),
    (3, "Less"),
)
TopicChoice = Literal["more", "same", "less"]
TOPIC_BUTTON_CHOICE_MAP: dict[int, TopicChoice] = {
    1: "more",
    2: "same",
    3: "less",
}
TOPIC_ANKI_EASE = 3
_PENDING_TOPIC_CHOICES: dict[int, dict[str, float | int | str]] = {}
_TOPIC_REVLOG_TRACKER = ReviewRevlogTracker()
_HANDLED_TOPIC_ANSWER_IDS: set[int] = set()
_diagnostic_event_callback = None
_DEFAULT_TOPIC_CARD_TYPES = {
    "pdf_epub": True,
    "video": True,
    "writing": True,
    "web": False,
}
_TOPIC_TYPE_NOTE_TYPES = {
    "pdf_epub": {"Incremento PDF", "Incremento EPUB"},
    "video": {"Incremento Video"},
    "writing": {"Incremento Writing"},
    "web": {"Incremento Web"},
}


def register_diagnostic_event_callback(callback) -> None:
    """Install the privacy-safe event sink supplied by the add-on entry point."""
    global _diagnostic_event_callback
    _diagnostic_event_callback = callback if callable(callback) else None


def _emit_diagnostic_event(event: str, **fields) -> None:
    callback = _diagnostic_event_callback
    if callback is None:
        return
    try:
        callback(str(event), dict(fields))
    except Exception:
        pass


@dataclass(frozen=True)
class TopicCardClassifier:
    """Resolved topic/item rules that are safe to reuse for a whole scan."""

    enabled_note_type_names: frozenset[str]
    topic_tags: frozenset[str]
    item_tags: frozenset[str]
    topics_deck_name: str

    @property
    def cache_key(self) -> tuple:
        return (
            tuple(sorted(self.enabled_note_type_names)),
            tuple(sorted(self.topic_tags)),
            tuple(sorted(self.item_tags)),
            self.topics_deck_name,
        )


def _topics_deck_name(scheduler_config=None) -> str:
    """Parse deck name from the configured topics_filter (e.g. 'deck:Topics')."""
    try:
        resolved = scheduler_config if scheduler_config is not None else load_scheduler_config()
        tf = (getattr(resolved, "topics_filter", "") or "deck:Topics").strip()
        if tf.lower().startswith("deck:"):
            return tf[5:].strip('"').strip("'")
    except Exception:
        pass
    return "Topics"


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        from aqt import mw as _mw

        addon_name = __name__.split(".")[0]
        resolved = _mw.addonManager.getConfig(addon_name) or {}
        return resolved if isinstance(resolved, dict) else {}
    except Exception:
        return {}


def configured_topic_card_types(config: dict | None = None) -> dict[str, bool]:
    cfg = _resolved_config(config)
    raw = cfg.get("topic_card_types")
    if not isinstance(raw, dict):
        return dict(_DEFAULT_TOPIC_CARD_TYPES)

    resolved = dict(_DEFAULT_TOPIC_CARD_TYPES)
    for key in resolved:
        if key in raw:
            resolved[key] = bool(raw.get(key))
    return resolved


def configured_topic_card_tags(config: dict | None = None) -> list[str]:
    cfg = _resolved_config(config)
    raw = cfg.get("topic_card_tags")

    if isinstance(raw, str):
        parts = raw.replace("\n", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item or "").strip()
        if not tag:
            continue
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(tag)
    return out


def configured_default_topic_a_factor(config: dict | None = None) -> float:
    cfg = _resolved_config(config)
    try:
        value = float(cfg.get("default_topic_a_factor", _DEFAULT_TOPIC_A_FACTOR))
    except Exception:
        value = _DEFAULT_TOPIC_A_FACTOR
    return round(max(_A_MIN, min(_A_MAX, value)), 3)


def _normalize_topic_adjustment_percent(value, default: float = 10.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if not math.isfinite(parsed):
        parsed = float(default)
    return round(max(0.0, min(100.0, parsed)), 3)


def configured_topic_more_adjustment_percent(config: dict | None = None) -> float:
    cfg = _resolved_config(config)
    if not isinstance(cfg, dict):
        cfg = {}
    return _normalize_topic_adjustment_percent(
        cfg.get("topic_more_adjustment_percent"),
        _DEFAULT_TOPIC_MORE_ADJUSTMENT_PERCENT,
    )


def configured_topic_less_adjustment_percent(config: dict | None = None) -> float:
    cfg = _resolved_config(config)
    if not isinstance(cfg, dict):
        cfg = {}
    return _normalize_topic_adjustment_percent(
        cfg.get("topic_less_adjustment_percent"),
        _DEFAULT_TOPIC_LESS_ADJUSTMENT_PERCENT,
    )


def configured_topic_maximum_interval_days(config: dict | None = None) -> int:
    cfg = _resolved_config(config)
    try:
        value = int(cfg.get("topic_maximum_interval_days", _DEFAULT_TOPIC_MAXIMUM_INTERVAL_DAYS))
    except Exception:
        value = _DEFAULT_TOPIC_MAXIMUM_INTERVAL_DAYS
    return max(1, min(_DEFAULT_TOPIC_MAXIMUM_INTERVAL_DAYS, value))


def effective_topic_maximum_interval_days(card, config: dict | None = None) -> int:
    """Return the stricter of Incremento's and the deck preset's interval cap."""
    maximum = configured_topic_maximum_interval_days(config)
    try:
        deck_id = int(getattr(card, "odid", 0) or getattr(card, "did", 0) or 0)
        deck_config = mw.col.decks.config_dict_for_deck_id(deck_id)
        if not isinstance(deck_config, dict):
            return maximum
        deck_maximum = int((deck_config.get("rev") or {}).get("maxIvl") or maximum)
        if deck_maximum > 0:
            maximum = min(maximum, deck_maximum)
    except Exception:
        pass
    return max(1, maximum)


def configured_effective_topic_tags(config: dict | None = None) -> list[str]:
    combined: list[str] = []
    seen: set[str] = set()
    for source in (
        configured_topic_card_tags(config),
        configured_add_card_topic_tags(config),
    ):
        for raw_tag in source:
            tag = str(raw_tag or "").strip()
            if not tag:
                continue
            normalized = tag.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            combined.append(tag)
    return combined


def configured_effective_item_tags(config: dict | None = None) -> list[str]:
    return configured_add_card_item_tags(config)


def resolve_topic_card_classifier(
    config: dict | None = None,
    *,
    scheduler_config=None,
) -> TopicCardClassifier:
    """Resolve config-backed topic rules once instead of once per candidate card."""
    resolved_config = _resolved_config(config)
    enabled_types = configured_topic_card_types(resolved_config)
    enabled_note_type_names: set[str] = set()
    for key, enabled in enabled_types.items():
        if enabled:
            enabled_note_type_names.update(_TOPIC_TYPE_NOTE_TYPES.get(key, set()))

    return TopicCardClassifier(
        enabled_note_type_names=frozenset(enabled_note_type_names),
        topic_tags=frozenset(
            str(tag or "").strip().casefold()
            for tag in configured_effective_topic_tags(resolved_config)
            if str(tag or "").strip()
        ),
        item_tags=frozenset(
            str(tag or "").strip().casefold()
            for tag in configured_effective_item_tags(resolved_config)
            if str(tag or "").strip()
        ),
        topics_deck_name=_topics_deck_name(scheduler_config),
    )


def topic_choice_for_button(button_ease: int) -> TopicChoice:
    try:
        value = int(button_ease)
    except Exception:
        return "same"
    return TOPIC_BUTTON_CHOICE_MAP.get(value, "same")


def prepare_topic_answer(card, button_ease: int) -> int:
    """Remember the frequency choice and return neutral Anki Good.

    Anki must receive a real answer to preserve its normal review transaction,
    timing, and revlog behavior. The topic choice itself is consumed after the
    answer and remains independent from Anki's Hard/Good/Easy memory grades.
    """
    try:
        card_id = int(card.id)
    except Exception:
        return TOPIC_ANKI_EASE
    try:
        seed_interval = float(getattr(card, "ivl", 0) or 0)
    except Exception:
        seed_interval = 0.0
    if not math.isfinite(seed_interval) or seed_interval < 1.0:
        seed_interval = 1.0
    revlog_snapshot_valid, previous_revlog_id = _answer_revlog_snapshot(card_id)
    _PENDING_TOPIC_CHOICES[card_id] = {
        "choice": topic_choice_for_button(button_ease),
        "seed_interval": seed_interval,
        "previous_revlog_id": previous_revlog_id,
        "revlog_snapshot_valid": 1 if revlog_snapshot_valid else 0,
        "preview_only": 1
        if is_nonrescheduling_filtered_card(
            card,
            collection=getattr(mw, "col", None),
        )
        else 0,
    }
    return TOPIC_ANKI_EASE


def consume_pending_topic_choice(card) -> TopicChoice:
    try:
        card_id = int(card.id)
    except Exception:
        return "same"
    pending = _PENDING_TOPIC_CHOICES.pop(card_id, None)
    if not isinstance(pending, dict):
        return "same"
    choice = str(pending.get("choice") or "same").lower()
    return choice if choice in {"more", "same", "less"} else "same"  # type: ignore[return-value]


def _consume_pending_topic_answer(
    card,
) -> tuple[TopicChoice, float, int, bool, bool]:
    try:
        card_id = int(card.id)
    except Exception:
        return "same", 1.0, 0, False, False
    pending = _PENDING_TOPIC_CHOICES.pop(card_id, None)
    if not isinstance(pending, dict):
        return "same", 1.0, 0, False, False
    raw_choice = str(pending.get("choice") or "same").lower()
    choice: TopicChoice = (
        raw_choice if raw_choice in {"more", "same", "less"} else "same"
    )  # type: ignore[assignment]
    try:
        seed_interval = max(1.0, float(pending.get("seed_interval") or 1.0))
    except Exception:
        seed_interval = 1.0
    try:
        previous_revlog_id = max(0, int(pending.get("previous_revlog_id") or 0))
    except Exception:
        previous_revlog_id = 0
    revlog_snapshot_valid = bool(pending.get("revlog_snapshot_valid"))
    preview_only = bool(pending.get("preview_only"))
    return (
        choice,
        seed_interval,
        previous_revlog_id,
        revlog_snapshot_valid,
        preview_only,
    )


def consume_handled_topic_answer(card_id: int) -> bool:
    """Return whether the preceding topic hook handled this answer."""
    try:
        normalized_card_id = int(card_id)
    except Exception:
        return False
    if normalized_card_id not in _HANDLED_TOPIC_ANSWER_IDS:
        return False
    _HANDLED_TOPIC_ANSWER_IDS.discard(normalized_card_id)
    return True


def _card_in_topics_deck(
    card,
    *,
    col=None,
    topics_deck_name: str | None = None,
) -> bool:
    """Return True if *card* lives in the configured Topics deck."""
    try:
        collection = col if col is not None else mw.col
        did = card.odid if card.odid else card.did
        deck = collection.decks.get(did)
        if not deck:
            return False
        name = deck["name"]
        target = str(topics_deck_name or _topics_deck_name()).strip() or "Topics"
        return name == target or name.startswith(target + "::")
    except Exception:
        return False


def _card_note_type_name(card) -> str:
    try:
        note = card.note()
    except Exception:
        return ""

    try:
        note_type = note.note_type()
        if isinstance(note_type, dict):
            return str(note_type.get("name") or "").strip()
    except Exception:
        pass

    try:
        model = getattr(note, "_model", None)
        if isinstance(model, dict):
            return str(model.get("name") or "").strip()
    except Exception:
        pass

    return ""


def _card_tags(card) -> set[str]:
    try:
        note = card.note()
    except Exception:
        return set()
    return _normalized_note_tags(note)


def _note_type_name(note) -> str:
    if note is None:
        return ""
    try:
        note_type = note.note_type()
        if isinstance(note_type, dict):
            return str(note_type.get("name") or "").strip()
    except Exception:
        pass
    try:
        model = getattr(note, "_model", None)
        if isinstance(model, dict):
            return str(model.get("name") or "").strip()
    except Exception:
        pass
    return ""


def _normalized_note_tags(note) -> set[str]:
    if note is None:
        return set()
    try:
        return {
            str(tag or "").strip().casefold()
            for tag in (getattr(note, "tags", None) or [])
            if str(tag or "").strip()
        }
    except Exception:
        return set()


def _card_matches_enabled_type(card, enabled_types: dict[str, bool]) -> bool:
    note_type_name = _card_note_type_name(card)
    if not note_type_name:
        return False
    for key, enabled in enabled_types.items():
        if enabled and note_type_name in _TOPIC_TYPE_NOTE_TYPES.get(key, set()):
            return True
    return False


def _card_matches_topic_tags(card, topic_tags: list[str]) -> bool:
    if not topic_tags:
        return False
    card_tags = _card_tags(card)
    if not card_tags:
        return False
    wanted = {tag.lower() for tag in topic_tags if str(tag or "").strip()}
    return bool(card_tags & wanted)


def _card_matches_item_tags(card, item_tags: list[str]) -> bool:
    if not item_tags:
        return False
    card_tags = _card_tags(card)
    if not card_tags:
        return False
    wanted = {tag.lower() for tag in item_tags if str(tag or "").strip()}
    return bool(card_tags & wanted)


def is_topic_card(
    card,
    *,
    classifier: TopicCardClassifier | None = None,
    col=None,
) -> bool:
    """Return True if *card* should use topic-card A-factor scheduling."""
    if card is None:
        return False
    try:
        resolved = classifier or resolve_topic_card_classifier()
        try:
            note = card.note()
        except Exception:
            note = None
        card_tags = _normalized_note_tags(note)
        if card_tags & resolved.item_tags:
            return False
        return (
            _note_type_name(note) in resolved.enabled_note_type_names
            or bool(card_tags & resolved.topic_tags)
            or _card_in_topics_deck(
                card,
                col=col,
                topics_deck_name=resolved.topics_deck_name,
            )
        )
    except Exception:
        return False


def _next_interval_and_afactor(
    last_interval: float,
    a_factor: float,
    choice: TopicChoice,
    *,
    more_adjustment_percent: float = _DEFAULT_TOPIC_MORE_ADJUSTMENT_PERCENT,
    less_adjustment_percent: float = _DEFAULT_TOPIC_LESS_ADJUSTMENT_PERCENT,
    maximum_interval_days: int = _DEFAULT_TOPIC_MAXIMUM_INTERVAL_DAYS,
) -> tuple[int, float, float]:
    """Return (new_interval_days, new_a_factor, new_precise_interval).

    Interval formula matches SuperMemo spec for topics:
        next_interval = current_interval × A-factor

    Frequency choices affect both the interval scheduled now and the A-factor
    used for future topic reviews:
      More — 90% of normal interval; A-factor ×0.9
      Same — normal interval; A-factor unchanged
      Less — 110% of normal interval; A-factor ×1.1
    """
    maximum_interval = max(
        1,
        min(_DEFAULT_TOPIC_MAXIMUM_INTERVAL_DAYS, int(maximum_interval_days or 1)),
    )
    normal_precise_interval = max(
        1.0,
        float(last_interval) * float(a_factor),
    )
    more_multiplier = 1.0 - (
        _normalize_topic_adjustment_percent(more_adjustment_percent) / 100.0
    )
    less_multiplier = 1.0 + (
        _normalize_topic_adjustment_percent(less_adjustment_percent) / 100.0
    )

    normalized_choice = choice if choice in {"more", "same", "less"} else "same"
    if normalized_choice == "more":
        new_precise_interval = min(
            float(maximum_interval),
            max(1.0, normal_precise_interval * more_multiplier),
        )
        return (
            max(1, round(new_precise_interval)),
            max(_A_MIN, round(a_factor * more_multiplier, 3)),
            new_precise_interval,
        )
    if normalized_choice == "same":
        new_precise_interval = min(
            float(maximum_interval),
            normal_precise_interval,
        )
        return (
            max(1, round(new_precise_interval)),
            a_factor,
            new_precise_interval,
        )
    # Less — lengthen this interval and future growth.
    new_precise_interval = min(
        float(maximum_interval),
        max(1.0, normal_precise_interval * less_multiplier),
    )
    return (
        max(1, round(new_precise_interval)),
        min(_A_MAX, round(a_factor * less_multiplier, 3)),
        new_precise_interval,
    )


def topic_due_label(card, review_button_ease: int) -> str:
    if card is None:
        return ""
    if is_nonrescheduling_filtered_card(
        card,
        collection=getattr(mw, "col", None),
    ):
        return ""
    try:
        a_factor, precise_interval, last_interval = get_topic_schedule_state(
            _ADDON_DIR,
            _active_profile(),
            card.id,
            default_a_factor=configured_default_topic_a_factor(),
            default_interval=max(1.0, float(getattr(card, "ivl", 0) or 1.0)),
        )
        maximum_interval = effective_topic_maximum_interval_days(card)
        new_interval, _new_a_factor, _new_precise_interval = _next_interval_and_afactor(
            precise_interval,
            a_factor,
            topic_choice_for_button(review_button_ease),
            more_adjustment_percent=configured_topic_more_adjustment_percent(),
            less_adjustment_percent=configured_topic_less_adjustment_percent(),
            maximum_interval_days=maximum_interval,
        )
        try:
            from .custom_schedule import resolve_topic_custom_schedule
        except ImportError:
            from custom_schedule import resolve_topic_custom_schedule  # type: ignore
        rule = get_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card.id))
        new_interval = int(
            resolve_topic_custom_schedule(
                new_interval,
                rule,
                maximum_interval_days=maximum_interval,
            )["interval_days"]
        )
    except Exception:
        return ""
    return f"{new_interval}d"


def sync_card_review_interval(card_id: int, interval_days: int) -> None:
    """Keep Anki's card interval aligned after manually setting a due date.

    Anki's set_due_date() reliably moves the due day, but on existing review
    cards it can leave card.ivl at the scheduler/FSRS-computed value.
    """
    try:
        normalized_card_id = int(card_id)
        normalized_interval = max(1, int(interval_days))
    except Exception:
        return

    try:
        card = mw.col.get_card(normalized_card_id)
    except Exception:
        card = None
    if card is None:
        return

    try:
        if int(getattr(card, "ivl", 0) or 0) != normalized_interval:
            card.ivl = normalized_interval
            mw.col.update_card(card)
    except Exception:
        pass


def _current_answer_undo_step() -> int:
    return current_answer_undo_step(collection=getattr(mw, "col", None))


def _apply_topic_interval_to_anki_card(
    card_id: int,
    interval_days: int,
    *,
    answer_undo_step: int = 0,
):
    """Compatibility wrapper around the shared atomic answer override."""
    return apply_review_interval(
        card_id,
        interval_days,
        answer_undo_step=answer_undo_step,
        collection=getattr(mw, "col", None),
    )


def _card_schedule_snapshot(card) -> dict[str, int]:
    return card_schedule_snapshot(card)


def _restore_anki_card_schedule(
    card_id: int,
    snapshot: dict[str, int],
    *,
    answer_undo_step: int = 0,
) -> None:
    restore_card_schedule(
        card_id,
        snapshot,
        answer_undo_step=answer_undo_step,
        collection=getattr(mw, "col", None),
    )


def _answer_revlog_snapshot(card_id: int) -> tuple[bool, int]:
    return answer_revlog_snapshot(card_id, collection=getattr(mw, "col", None))


def _new_answer_revlog_id(card_id: int, previous_revlog_id: int) -> int:
    return new_answer_revlog_id(
        card_id,
        previous_revlog_id,
        collection=getattr(mw, "col", None),
    )


def _track_topic_review_state(card_id: int, revlog_id: int) -> None:
    _TOPIC_REVLOG_TRACKER.track(_active_profile(), card_id, revlog_id)


def reset_topic_answer_runtime_state() -> None:
    """Discard pending and undo state before or after a profile switch."""
    _PENDING_TOPIC_CHOICES.clear()
    _HANDLED_TOPIC_ANSWER_IDS.clear()
    _TOPIC_REVLOG_TRACKER.clear()


def reconcile_topic_state_after_anki_operation(undo_info=None) -> None:
    """Reconcile Incremento state when Anki removes/restores linked revlogs."""
    try:
        transitions = _TOPIC_REVLOG_TRACKER.transitions(
            undo_info,
            collection=getattr(mw, "col", None),
        )
    except Exception as exc:
        _emit_diagnostic_event(
            "topic_schedule_reconcile_failed",
            error_type=type(exc).__name__,
        )
        print(f"[Incremento] topic undo/redo tracking error: {exc}")
        return
    for profile, card_id, current, previous in transitions:
        try:
            reconcile_topic_review_state(
                _ADDON_DIR,
                profile,
                card_id,
                current,
                previous,
            )
        except Exception as exc:
            _emit_diagnostic_event(
                "topic_schedule_reconcile_failed",
                error_type=type(exc).__name__,
            )
            print(f"[Incremento] topic undo/redo reconciliation error: {exc}")


def on_topic_card_answered(reviewer, card, ease: int) -> None:
    """Hook: override FSRS scheduling with A-factor for topic cards.

    The reviewer_will_answer_card hook saved the original More/Same/Less
    choice and submitted neutral Good to Anki before this hook runs.
    """
    try:
        card_id = int(card.id)
    except Exception:
        return
    if card_id not in _PENDING_TOPIC_CHOICES and not is_topic_card(card):
        return
    _HANDLED_TOPIC_ANSWER_IDS.add(card_id)
    choice, seed_interval, previous_revlog_id, revlog_snapshot_valid, preview_only = (
        _consume_pending_topic_answer(card)
    )
    if preview_only:
        _emit_diagnostic_event(
            "topic_schedule_skipped",
            choice=choice,
            reason="preview",
        )
        return
    if not revlog_snapshot_valid:
        _emit_diagnostic_event(
            "topic_schedule_failed",
            choice=choice,
            stage="revlog_snapshot",
            error_type="RuntimeError",
            restore_failed=False,
        )
        print("[Incremento] A-factor scheduling error: pre-answer revlog query failed")
        return
    failure_stage = "load_state"
    restore_failed = False
    try:
        profile = _active_profile()
        previous_schedule_exists = topic_schedule_exists(
            _ADDON_DIR,
            profile,
            card_id,
        )
        a_factor, precise_interval, last_interval = get_topic_schedule_state(
            _ADDON_DIR,
            profile,
            card_id,
            default_a_factor=configured_default_topic_a_factor(),
            default_interval=seed_interval,
        )
        failure_stage = "resolve"
        maximum_interval = effective_topic_maximum_interval_days(card)
        requested_interval, new_a, requested_precise_interval = _next_interval_and_afactor(
            precise_interval,
            a_factor,
            choice,
            more_adjustment_percent=configured_topic_more_adjustment_percent(),
            less_adjustment_percent=configured_topic_less_adjustment_percent(),
            maximum_interval_days=maximum_interval,
        )
        try:
            from .custom_schedule import resolve_topic_custom_schedule
        except ImportError:
            from custom_schedule import resolve_topic_custom_schedule  # type: ignore
        custom_rule = get_custom_schedule_rule(
            _ADDON_DIR,
            profile,
            card_id,
        )
        resolved = resolve_topic_custom_schedule(
            requested_interval,
            custom_rule,
            maximum_interval_days=maximum_interval,
        )
        new_interval = int(resolved["interval_days"])
        custom_mode = str(resolved["mode"] or "")
        if custom_mode in {"fixed_repeat", "one_time"} or (
            custom_mode and new_interval != requested_interval
        ):
            new_precise_interval = float(new_interval)
        else:
            new_precise_interval = requested_precise_interval
        failure_stage = "undo_step"
        answer_undo_step = _current_answer_undo_step()
        if answer_undo_step <= 0:
            raise RuntimeError("Anki answer undo step is unavailable")
        failure_stage = "revlog"
        revlog_id = _new_answer_revlog_id(card_id, previous_revlog_id)
        if revlog_id <= 0:
            raise RuntimeError("Anki did not create a new answer revlog")
        post_good_card = mw.col.get_card(card_id)
        post_good_snapshot = _card_schedule_snapshot(post_good_card)
        try:
            failure_stage = "apply"
            _apply_topic_interval_to_anki_card(
                card_id,
                new_interval,
                answer_undo_step=answer_undo_step,
            )
            failure_stage = "commit"
            commit_topic_review(
                _ADDON_DIR,
                profile,
                card_id,
                choice,
                anki_revlog_id=revlog_id,
                anki_ease=ease,
                previous_schedule_exists=previous_schedule_exists,
                previous_a_factor=a_factor,
                new_a_factor=new_a,
                previous_precise_interval=precise_interval,
                previous_interval=last_interval,
                requested_precise_interval=requested_precise_interval,
                new_precise_interval=new_precise_interval,
                requested_interval=requested_interval,
                scheduled_interval=new_interval,
                custom_schedule_mode=custom_mode,
                custom_schedule_rule=resolved["rule"],
                consumed_one_time=bool(resolved["consumed_one_time"]),
            )
        except Exception:
            try:
                _restore_anki_card_schedule(
                    card_id,
                    post_good_snapshot,
                    answer_undo_step=answer_undo_step,
                )
            except Exception as restore_error:
                print(
                    "[Incremento] failed to restore Anki schedule after topic error: "
                    f"{restore_error}"
                )
                restore_failed = True
            raise
        if revlog_id > 0:
            try:
                _track_topic_review_state(card_id, revlog_id)
            except Exception as track_error:
                _emit_diagnostic_event(
                    "topic_schedule_reconcile_failed",
                    error_type=type(track_error).__name__,
                )
                print(f"[Incremento] topic review tracking error: {track_error}")
        _emit_diagnostic_event(
            "topic_schedule_applied",
            choice=choice,
            anki_rating=ease,
            previous_interval_days=last_interval,
            requested_interval_days=requested_interval,
            scheduled_interval_days=new_interval,
            previous_a_factor=a_factor,
            new_a_factor=new_a,
            custom_mode=custom_mode or "none",
        )
    except Exception as e:
        _emit_diagnostic_event(
            "topic_schedule_failed",
            choice=choice,
            stage=failure_stage,
            error_type=type(e).__name__,
            restore_failed=restore_failed,
        )
        print(f"[Incremento] A-factor scheduling error: {e}")
