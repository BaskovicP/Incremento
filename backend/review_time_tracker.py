"""Global active-study tracking outside Incremento-owned session totals.

Tracks elapsed time for:
- Normal reviewer flow (question shown -> answer shown / leaving review)
- PDF dock usage outside reviewer state

It also records one Topic/Item + tag attribution for every review so the
statistics UI can compare where active study time was spent during free study.
"""

from __future__ import annotations

import os
import time
import types

from aqt import mw

from .pdf_manager import PDF_NOTE_TYPE
from .epub_manager import EPUB_NOTE_TYPE
from .scheduler import NO_TAGS_KEY
from .session import is_incremento_session_deck_name
from .statistics import StatsManager, UNTAGGED_STATS_TAG, record_tag_breakdown
from .scheduler_config import load_scheduler_config
from .paths import get_active_profile as _active_profile
from .topic_scheduler import is_topic_card, resolve_topic_card_classifier


_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_active_review_cid: int | None = None
_active_review_started: float | None = None

_active_dock_cid: int | None = None
_active_dock_started: float | None = None

_runtime_session_time: dict[str, dict[str, float]] = {"type": {}, "tags": {}}
_MEDIA_CARD_TYPES = {
    PDF_NOTE_TYPE: "pdf",
    EPUB_NOTE_TYPE: "epub",
    "Incremento Video": "youtube",
    "Incremento Web": "webpage",
    "Incremento Writing": "writing",
    "Incremento Local File": "local_file",
}


def _add_runtime_time(card_type: str, tag: str | None, seconds: float) -> None:
    _runtime_session_time["type"][card_type] = (
        _runtime_session_time["type"].get(card_type, 0.0) + seconds
    )
    if tag is not None:
        _runtime_session_time["tags"][tag] = (
            _runtime_session_time["tags"].get(tag, 0.0) + seconds
        )


def get_runtime_session_time() -> dict:
    return {
        "type": dict(_runtime_session_time["type"]),
        "tags": dict(_runtime_session_time["tags"]),
    }


def _primary_tag(note, classifier=None) -> str:
    tags = getattr(note, "tags", None) or []
    excluded = set(getattr(classifier, "topic_tags", ()) or ())
    excluded.update(getattr(classifier, "item_tags", ()) or ())
    for raw_tag in tags:
        tag = str(raw_tag or "").strip()
        if (
            tag
            and tag != NO_TAGS_KEY
            and not tag.startswith("__")
            and tag.casefold() not in excluded
        ):
            return tag
    return UNTAGGED_STATS_TAG


def _current_deck_is_incremento_session() -> bool:
    try:
        current_deck = (mw.col.decks.current() or {}).get("name", "")
    except Exception:
        current_deck = ""
    return bool(
        mw.state == "review" and is_incremento_session_deck_name(current_deck)
    )


def _card_stats_context(card_id: int, card=None):
    try:
        collection = mw.col
        resolved_card = card if card is not None else collection.get_card(card_id)
        try:
            note = resolved_card.note()
        except Exception:
            note = collection.get_note(resolved_card.nid)
        try:
            model = note.note_type()
        except Exception:
            model = collection.models.get(note.mid)
        model_name = str((model or {}).get("name") or "")
        classifier = resolve_topic_card_classifier()
        semantic_kind = (
            "topics"
            if is_topic_card(
                resolved_card,
                classifier=classifier,
                col=collection,
            )
            else "items"
        )
        card_type = _MEDIA_CARD_TYPES.get(model_name, semantic_kind)
        tag = _primary_tag(note, classifier)
        return types.SimpleNamespace(
            card=int(card_id),
            card_type=card_type,
            study_kind=semantic_kind,
            tag=tag,
            mode="random",
            review_seconds=0.0,
        )
    except Exception:
        return None


def _record_breakdown(result, *, include_count: bool, seconds: float, day_end: str) -> None:
    record_tag_breakdown(
        _ADDON_DIR,
        _active_profile(),
        study_kind=result.study_kind,
        tag=result.tag,
        include_count=include_count,
        seconds=seconds,
        day_end_time=day_end,
    )


def _record_review_time(card_id: int, seconds: float) -> None:
    if seconds <= 0:
        return
    try:
        result = _card_stats_context(card_id)
        if result is None:
            return
        cfg = load_scheduler_config()
        day_end = cfg.day_end_time
        if not _current_deck_is_incremento_session():
            sm = StatsManager(_ADDON_DIR, _active_profile(), day_end_time=day_end)
            sm.record_time_only(result, seconds, study_kind=result.study_kind)
            _add_runtime_time(result.card_type, result.tag, seconds)
        else:
            _record_breakdown(
                result,
                include_count=False,
                seconds=seconds,
                day_end=day_end,
            )
    except Exception:
        pass


def _record_pdf_time(card_id: int, seconds: float) -> None:
    """Compatibility wrapper for reader callers and older tests."""
    if seconds <= 0:
        return
    if _current_deck_is_incremento_session():
        return
    _record_review_time(card_id, seconds)


def _active_review_seconds(card, measured_seconds: float) -> float:
    """Use Anki's capped per-card timer so an idle question cannot dominate."""
    measured = max(0.0, float(measured_seconds or 0.0))
    if card is None:
        return measured
    try:
        try:
            milliseconds = card.time_taken()
        except TypeError:
            milliseconds = card.time_taken(capped=True)
        capped = max(0.0, float(milliseconds or 0.0) / 1000.0)
        if capped > 0:
            return min(measured, capped)
    except Exception:
        pass
    return measured


def _stop_active_review(card=None) -> None:
    global _active_review_cid, _active_review_started
    if _active_review_cid is None or _active_review_started is None:
        return
    elapsed = _active_review_seconds(
        card,
        max(0.0, time.monotonic() - _active_review_started),
    )
    _record_review_time(_active_review_cid, elapsed)
    _active_review_cid = None
    _active_review_started = None


def _stop_active_dock() -> None:
    global _active_dock_cid, _active_dock_started
    if _active_dock_cid is None or _active_dock_started is None:
        return
    elapsed = max(0.0, time.monotonic() - _active_dock_started)
    _record_pdf_time(_active_dock_cid, elapsed)
    _active_dock_cid = None
    _active_dock_started = None


def on_reviewer_question_shown(card) -> None:
    global _active_review_cid, _active_review_started
    _stop_active_review()
    if card is None:
        return
    _active_review_cid = card.id
    _active_review_started = time.monotonic()


def on_reviewer_answer_shown(card) -> None:
    _stop_active_review(card)


def on_reviewer_card_answered(_reviewer, card, _ease: int) -> None:
    """Count free-study answers and attribute every answer to one pie slice."""
    try:
        card_id = int(getattr(card, "id", 0) or 0)
        if card_id <= 0:
            return
        result = _card_stats_context(card_id, card=card)
        if result is None:
            return
        cfg = load_scheduler_config()
        day_end = cfg.day_end_time
        if not _current_deck_is_incremento_session():
            sm = StatsManager(_ADDON_DIR, _active_profile(), day_end_time=day_end)
            sm.record(result, "daily", study_kind=result.study_kind)
        else:
            _record_breakdown(
                result,
                include_count=True,
                seconds=0.0,
                day_end=day_end,
            )
    except Exception:
        pass


def on_state_did_change(new_state: str, old_state: str) -> None:
    if old_state == "review" and new_state != "review":
        active_card = getattr(getattr(mw, "reviewer", None), "card", None)
        _stop_active_review(active_card)


def on_pdf_view_started(card_id: int) -> None:
    global _active_dock_cid, _active_dock_started
    if mw.state == "review":
        return
    if int(card_id or 0) <= 0:
        _stop_active_dock()
        return
    if _active_dock_cid == card_id and _active_dock_started is not None:
        return
    _stop_active_dock()
    _active_dock_cid = card_id
    _active_dock_started = time.monotonic()


def on_pdf_view_stopped(card_id: int | None = None) -> None:
    if mw.state == "review":
        return
    if card_id is not None and int(card_id or 0) <= 0:
        _stop_active_dock()
        return
    if (
        card_id is not None
        and _active_dock_cid is not None
        and _active_dock_cid != card_id
    ):
        return
    _stop_active_dock()
