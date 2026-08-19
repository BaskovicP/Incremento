"""A-factor scheduler for topic cards (SuperMemo SM-15 spec for topics).

Topic cards are scheduled independently of FSRS using the SuperMemo A-factor
formula:

    next_interval = current_interval × A-factor   (spec: topics)

The ease button changes both the immediate next interval and the persistent
A-factor to signal how urgently the topic should be reviewed. The percentages
below are defaults and can be changed independently in Topics settings:

  Again (1) — reset to 1 day; A-factor unchanged
  Hard  (2) — 90% of normal interval; A-factor ×0.9  (important → show sooner)
  Good  (3) — normal interval; A-factor unchanged
  Easy  (4) — 110% of normal interval; A-factor ×1.1  (less urgent → grow faster)

A-factor is clamped to [1.1, 100.0]. Default: 3.5.
"""

import math
import os

from aqt import mw

try:
    from .db import get_topic_schedule, get_topic_schedule_state, set_topic_schedule
    from .knowledge_tree import configured_topic_tags as configured_add_card_topic_tags
    from .knowledge_tree import configured_item_tags as configured_add_card_item_tags
    from .scheduler_config import load_scheduler_config
    from .paths import get_active_profile as _active_profile
except ImportError:
    from db import get_topic_schedule, get_topic_schedule_state, set_topic_schedule  # type: ignore
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
TOPIC_REVIEW_BUTTONS: tuple[tuple[int, str], ...] = (
    (1, "More"),
    (2, "Same"),
    (3, "Less"),
)
TOPIC_REVIEW_EASE_MAP: dict[int, int] = {
    1: 2,
    2: 3,
    3: 4,
}
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


def _topics_deck_name() -> str:
    """Parse deck name from the configured topics_filter (e.g. 'deck:Topics')."""
    try:
        tf = (load_scheduler_config().topics_filter or "deck:Topics").strip()
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
        return _mw.addonManager.getConfig(addon_name) or {}
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


def remap_topic_review_ease(ease: int) -> int:
    try:
        value = int(ease)
    except Exception:
        return 3
    return TOPIC_REVIEW_EASE_MAP.get(value, value)


def _card_in_topics_deck(card) -> bool:
    """Return True if *card* lives in the configured Topics deck."""
    try:
        did = card.odid if card.odid else card.did
        deck = mw.col.decks.get(did)
        if not deck:
            return False
        name = deck["name"]
        target = _topics_deck_name()
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

    try:
        raw_tags = getattr(note, "tags", None) or []
        return {
            str(tag or "").strip().lower()
            for tag in raw_tags
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


def is_topic_card(card) -> bool:
    """Return True if *card* should use topic-card A-factor scheduling."""
    if card is None:
        return False
    try:
        enabled_types = configured_topic_card_types()
        topic_tags = configured_effective_topic_tags()
        item_tags = configured_effective_item_tags()
        if _card_matches_item_tags(card, item_tags):
            return False
        return (
            _card_matches_enabled_type(card, enabled_types)
            or _card_matches_topic_tags(card, topic_tags)
            or _card_in_topics_deck(card)
        )
    except Exception:
        return False


def _next_interval_and_afactor(
    last_interval: float,
    a_factor: float,
    ease: int,
    *,
    more_adjustment_percent: float = _DEFAULT_TOPIC_MORE_ADJUSTMENT_PERCENT,
    less_adjustment_percent: float = _DEFAULT_TOPIC_LESS_ADJUSTMENT_PERCENT,
) -> tuple[int, float, float]:
    """Return (new_interval_days, new_a_factor, new_precise_interval).

    Interval formula matches SuperMemo spec for topics:
        next_interval = current_interval × A-factor

    Ease buttons affect both the interval scheduled now and the A-factor used
    for future reviews:
      Again (1) — reset to 1 day; A-factor unchanged
      Hard  (2) — 90% of normal interval; A-factor ×0.9
      Good  (3) — normal interval; A-factor unchanged
      Easy  (4) — 110% of normal interval; A-factor ×1.1
    """
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

    if ease == 1:  # Again — reset interval, leave A-factor alone
        return 1, a_factor, 1.0
    if ease == 2:  # Hard/More — shorten this interval and future growth
        new_precise_interval = max(1.0, normal_precise_interval * more_multiplier)
        return (
            max(1, round(new_precise_interval)),
            max(_A_MIN, round(a_factor * more_multiplier, 3)),
            new_precise_interval,
        )
    if ease == 3:  # Good — pure spec formula, no A-factor change
        return (
            max(1, round(normal_precise_interval)),
            a_factor,
            normal_precise_interval,
        )
    # Easy/Less — lengthen this interval and future growth
    new_precise_interval = max(1.0, normal_precise_interval * less_multiplier)
    return (
        max(1, round(new_precise_interval)),
        min(_A_MAX, round(a_factor * less_multiplier, 3)),
        new_precise_interval,
    )


def topic_due_label(card, review_button_ease: int) -> str:
    if card is None:
        return ""
    try:
        a_factor, precise_interval, _last_interval = get_topic_schedule_state(
            _ADDON_DIR,
            _active_profile(),
            card.id,
            default_a_factor=configured_default_topic_a_factor(),
        )
        new_interval, _new_a_factor, _new_precise_interval = _next_interval_and_afactor(
            precise_interval,
            a_factor,
            remap_topic_review_ease(review_button_ease),
            more_adjustment_percent=configured_topic_more_adjustment_percent(),
            less_adjustment_percent=configured_topic_less_adjustment_percent(),
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


def on_topic_card_answered(reviewer, card, ease: int) -> None:
    """Hook: override FSRS scheduling with A-factor for topic cards.

    The reviewer_will_answer_card hook has already remapped More/Same/Less
    to Hard/Good/Easy by the time Anki calls reviewer_did_answer_card.
    """
    if not is_topic_card(card):
        return
    try:
        a_factor, precise_interval, _last_interval = get_topic_schedule_state(
            _ADDON_DIR,
            _active_profile(),
            card.id,
            default_a_factor=configured_default_topic_a_factor(),
        )
        new_interval, new_a, new_precise_interval = _next_interval_and_afactor(
            precise_interval,
            a_factor,
            ease,
            more_adjustment_percent=configured_topic_more_adjustment_percent(),
            less_adjustment_percent=configured_topic_less_adjustment_percent(),
        )
        set_topic_schedule(
            _ADDON_DIR,
            _active_profile(),
            card.id,
            new_a,
            new_interval,
            precise_interval=new_precise_interval,
        )
        mw.col.sched.set_due_date([card.id], str(new_interval))
        sync_card_review_interval(card.id, new_interval)
    except Exception as e:
        print(f"[Incremento] A-factor scheduling error: {e}")
