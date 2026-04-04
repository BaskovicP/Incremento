"""A-factor scheduler for topic cards (SuperMemo SM-15 spec for topics).

Topic cards are scheduled independently of FSRS using the SuperMemo A-factor
formula:

    next_interval = current_interval × A-factor   (spec: topics)

The ease button does NOT change the current interval — it only shifts the
A-factor to signal how urgently the topic should be reviewed in future:

  Again (1) — reset to 1 day; A-factor unchanged
  Hard  (2) — normal interval; A-factor ×0.9  (important → show sooner)
  Good  (3) — normal interval; A-factor unchanged
  Easy  (4) — normal interval; A-factor ×1.1  (less urgent → grow faster)

A-factor is clamped to [1.1, 100.0]. Default: 3.5.
"""

import os

from aqt import mw

try:
    from .db import get_topic_schedule, set_topic_schedule
    from .scheduler_config import load_scheduler_config
    from .paths import get_active_profile as _active_profile
except ImportError:
    from db import get_topic_schedule, set_topic_schedule  # type: ignore
    from scheduler_config import load_scheduler_config  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_A_MIN = 1.1
_A_MAX = 100.0
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


def is_topic_card(card) -> bool:
    """Return True if *card* should use topic-card A-factor scheduling."""
    if card is None:
        return False
    try:
        enabled_types = configured_topic_card_types()
        topic_tags = configured_topic_card_tags()
        return (
            _card_matches_enabled_type(card, enabled_types)
            or _card_matches_topic_tags(card, topic_tags)
            or _card_in_topics_deck(card)
        )
    except Exception:
        return False


def _next_interval_and_afactor(
    last_interval: int, a_factor: float, ease: int
) -> tuple[int, float]:
    """Return (new_interval_days, new_a_factor).

    Interval formula matches SuperMemo spec for topics:
        next_interval = current_interval × A-factor

    Ease buttons only affect the A-factor for *future* reviews, not the
    current interval (except Again which resets to 1 day):
      Again (1) — reset to 1 day; A-factor unchanged
      Hard  (2) — normal interval; A-factor ×0.9  (topic is important → show sooner)
      Good  (3) — normal interval; A-factor unchanged
      Easy  (4) — normal interval; A-factor ×1.1  (topic less urgent → grow faster)
    """
    new_interval = max(1, round(last_interval * a_factor))

    if ease == 1:  # Again — reset interval, leave A-factor alone
        return 1, a_factor
    if ease == 2:  # Hard — signal topic is important, tighten future intervals
        return new_interval, max(_A_MIN, round(a_factor * 0.9, 3))
    if ease == 3:  # Good — pure spec formula, no A-factor change
        return new_interval, a_factor
    # Easy — topic less urgent, loosen future intervals
    return new_interval, min(_A_MAX, round(a_factor * 1.1, 3))


def topic_due_label(card, review_button_ease: int) -> str:
    if card is None:
        return ""
    try:
        a_factor, last_interval = get_topic_schedule(_ADDON_DIR, _active_profile(), card.id)
        new_interval, _ = _next_interval_and_afactor(
            last_interval,
            a_factor,
            remap_topic_review_ease(review_button_ease),
        )
    except Exception:
        return ""
    return f"{new_interval}d"


def on_topic_card_answered(reviewer, card, ease: int) -> None:
    """Hook: override FSRS scheduling with A-factor for topic cards."""
    if not is_topic_card(card):
        return
    try:
        a_factor, last_interval = get_topic_schedule(_ADDON_DIR, _active_profile(), card.id)
        new_interval, new_a = _next_interval_and_afactor(
            last_interval,
            a_factor,
            remap_topic_review_ease(ease),
        )
        set_topic_schedule(_ADDON_DIR, _active_profile(), card.id, new_a, new_interval)
        mw.col.sched.set_due_date([card.id], str(new_interval))
    except Exception as e:
        print(f"[Incremento] A-factor scheduling error: {e}")
