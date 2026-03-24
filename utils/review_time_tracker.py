"""Global review-time tracking for PDF cards outside Incremento sessions.

Tracks elapsed time for:
- Normal reviewer flow (question shown -> answer shown / leaving review)
- PDF dock usage outside reviewer state
"""

from __future__ import annotations

import os
import time
import types

from aqt import mw

from .pdf_manager import PDF_NOTE_TYPE
from .scheduler import NO_TAGS_KEY
from .session import INCREMENTO_DECK
from .statistics import StatsManager
from .scheduler_config import load_scheduler_config


_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_active_review_cid: int | None = None
_active_review_started: float | None = None

_active_dock_cid: int | None = None
_active_dock_started: float | None = None

_runtime_session_time = {"type": {}, "tags": {}}


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


def _primary_tag(note) -> str | None:
    tags = getattr(note, "tags", None) or []
    for t in tags:
        if t and t != NO_TAGS_KEY:
            return t
    return None


def _record_pdf_time(card_id: int, seconds: float) -> None:
    if seconds <= 0:
        return
    try:
        try:
            current_deck = (mw.col.decks.current() or {}).get("name", "")
        except Exception:
            current_deck = ""
        if mw.state == "review" and current_deck == INCREMENTO_DECK:
            # learnFunction/session.py already tracks review time in this mode.
            return

        card = mw.col.get_card(card_id)
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        if not model or model.get("name") != PDF_NOTE_TYPE:
            return

        cfg = load_scheduler_config()
        sm = StatsManager(_ADDON_DIR, day_end_time=cfg.day_end_time)
        fake = types.SimpleNamespace(
            card=card_id,
            card_type="topics",
            tag=_primary_tag(note),
            mode="random",
        )
        sm.record_time_only(fake, seconds)
        _add_runtime_time(fake.card_type, fake.tag, seconds)
    except Exception:
        pass


def _stop_active_review() -> None:
    global _active_review_cid, _active_review_started
    if _active_review_cid is None or _active_review_started is None:
        return
    elapsed = max(0.0, time.monotonic() - _active_review_started)
    _record_pdf_time(_active_review_cid, elapsed)
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
    _stop_active_review()


def on_state_did_change(new_state: str, old_state: str) -> None:
    if old_state == "review" and new_state != "review":
        _stop_active_review()


def on_pdf_view_started(card_id: int) -> None:
    global _active_dock_cid, _active_dock_started
    if mw.state == "review":
        return
    if _active_dock_cid == card_id and _active_dock_started is not None:
        return
    _stop_active_dock()
    _active_dock_cid = card_id
    _active_dock_started = time.monotonic()


def on_pdf_view_stopped(card_id: int | None = None) -> None:
    if mw.state == "review":
        return
    if (
        card_id is not None
        and _active_dock_cid is not None
        and _active_dock_cid != card_id
    ):
        return
    _stop_active_dock()
