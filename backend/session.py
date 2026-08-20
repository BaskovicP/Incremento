"""
session.py — learnFunction and session-scope statistics state.

Owns the in-memory session counts and the full card-picking / filtered-deck
creation logic that was previously inline in __init__.py.

Public API:
    INCREMENTO_DECK       — filtered deck name constant
    INCREMENTO_QUICK_OPEN_REVIEW_DECK — filtered deck for quick-open study
    incremento_session_deck_name() — map an optional dialog profile to a deck name
    is_incremento_session_deck_name() — predicate for Incremento session decks
    learnFunction()       — main entry point; shows config dialog and starts review
    start_quick_open_review() — study one quick-open doc card in a filtered deck
    reset_session_counts() — clear in-memory session counts
    get_session_counts()  — return a copy of the current session counts
"""

import copy
import os
import time
import types
from dataclasses import dataclass, field

from aqt import mw, gui_hooks
from aqt.utils import showInfo
from aqt.qt import QDialog, QVBoxLayout, QTextEdit, QPushButton, QTimer
try:
    from anki.consts import DYN_DUE, DYN_OLDEST
except Exception:
    DYN_OLDEST = 0
    DYN_DUE = 6

from .scheduler import NO_TAGS_KEY
from .statistics import StatsManager, _empty, _empty_time
from .session_selection import SessionPicker, select_session_cards
from .paths import get_active_profile as _active_profile
from .topic_postpone import release_expired_timed_postpones
try:
    from ..frontend.learn_dialog import SchedulerConfigDialog
except ImportError:
    from learn_dialog import SchedulerConfigDialog  # tests add frontend/ to sys.path

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_ADDON_PKG = __name__.split(".")[0]  # "incremento"

INCREMENTO_DECK = "Incremento Session"
INCREMENTO_PDF_REVIEW_DECK = "Incremento PDF Review"
INCREMENTO_QUICK_OPEN_REVIEW_DECK = "Incremento Quick Open Review"

# Most-recent reviewed session counts, updated as cards are answered.
# Accessed via get_session_counts() from __init__.py for the stats dialog.
_session_counts: dict = {"type": {}, "tags": {}, "mode": {}}
_session_times: dict = _empty_time()
_active_incremento_session_state = None


class _DuplicateLiveQueueEntriesError(RuntimeError):
    """Raised when Anki's live queue contains duplicate entries for one card."""


@dataclass
class _ActiveIncrementoSessionState:
    cfg: object
    stats: StatsManager
    picker: SessionPicker
    session_deck_name: str
    window_size: int
    preserve_order: bool
    picked_meta: dict[int, dict]
    selected_ids: list[int]
    reviewed_ids: set[int] = field(default_factory=set)
    question_started_at: dict[int, float] = field(default_factory=dict)
    measured_review_seconds: dict[int, float] = field(default_factory=dict)
    last_shown_cid: int | None = None
    auto_refill_enabled: bool = False
    session_closed: bool = False
    refill_retry_pending: bool = False


def incremento_session_deck_name(dialog_profile_name: str | None = None) -> str:
    name = str(dialog_profile_name or "").strip()
    if not name:
        return INCREMENTO_DECK
    return f"{INCREMENTO_DECK} ({name})"


def is_incremento_session_deck_name(deck_name: str | None) -> bool:
    name = str(deck_name or "").strip()
    if not name:
        return False
    if name == INCREMENTO_DECK:
        return True
    prefix = f"{INCREMENTO_DECK} ("
    return name.startswith(prefix) and name.endswith(")") and len(name) > len(prefix) + 1


def reset_session_counts() -> None:
    global _session_counts, _session_times
    _session_counts = _empty()
    _session_times = _empty_time()


def get_session_counts() -> dict:
    """Return the last session's counts (live reference — do not mutate)."""
    return _session_counts


def get_session_times() -> dict:
    """Return review-time stats for the last/active session."""
    return _session_times


def _record_session_count(card_type: str, tag: str | None, mode: str) -> None:
    """Track cards actually answered in the current Incremento session."""
    _session_counts["type"][card_type] = _session_counts["type"].get(card_type, 0) + 1
    _session_counts["mode"][mode] = _session_counts["mode"].get(mode, 0) + 1
    if tag is not None:
        _session_counts["tags"][tag] = _session_counts["tags"].get(tag, 0) + 1


def _prepare_filtered_review_deck(
    selected_ids: list[int],
    *,
    deck_name: str,
    preserve_order: bool,
    select_deck: bool = True,
) -> int:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw in selected_ids or []:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid <= 0 or cid in seen:
            continue
        seen.add(cid)
        normalized_ids.append(cid)
    if not normalized_ids:
        raise ValueError("Cannot build a filtered deck without valid card IDs.")

    # Anki supports a comma-separated cid list.  Keeping this as one search
    # node avoids constructing/parsing thousands of OR expressions for large
    # sessions (for example a user-configured 9,999-card catch-up session).
    search = "cid:" + ",".join(str(cid) for cid in normalized_ids)

    existing = mw.col.decks.by_name(deck_name)
    if existing:
        if not existing.get("dyn"):
            raise RuntimeError(f"'{deck_name}' is a normal deck. Delete or rename it first.")
        did = existing["id"]
        mw.col.sched.empty_filtered_deck(did)
    else:
        did = mw.col.decks.new_filtered(deck_name)

    fdu = mw.col.sched.get_or_create_filtered_deck(did)
    fdu.config.reschedule = True
    del fdu.config.search_terms[:]
    fdu.config.search_terms.add(
        search=search,
        limit=len(normalized_ids),
        order=DYN_DUE if preserve_order else DYN_OLDEST,
    )
    op = mw.col.sched.add_or_update_filtered_deck(fdu)
    mw.col.sched.rebuild_filtered_deck(op.id)

    if preserve_order:
        position = 0
        cards_to_update = []
        for cid in normalized_ids:
            card = mw.col.get_card(cid)
            if int(getattr(card, "did", 0) or 0) != int(op.id):
                continue
            card.due = position
            cards_to_update.append(card)
            position += 1
        if cards_to_update:
            update_cards = getattr(mw.col, "update_cards", None)
            if callable(update_cards):
                try:
                    update_cards(cards_to_update, skip_undo_entry=True)
                except TypeError:
                    update_cards(cards_to_update)
            else:
                for card in cards_to_update:
                    try:
                        mw.col.update_card(card, skip_undo_entry=True)
                    except TypeError:
                        mw.col.update_card(card)

    if select_deck:
        mw.col.decks.select(op.id)
    return int(op.id)


def _empty_filtered_deck_by_name(deck_name: str) -> bool:
    name = str(deck_name or "").strip()
    if not name:
        return False
    existing = mw.col.decks.by_name(name)
    if not existing or not existing.get("dyn"):
        return False
    mw.col.sched.empty_filtered_deck(existing["id"])
    return True


def _sync_filtered_deck_by_name(
    deck_name: str,
    selected_ids: list[int],
    *,
    preserve_order: bool,
) -> bool:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw in selected_ids or []:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid <= 0 or cid in seen:
            continue
        seen.add(cid)
        normalized_ids.append(cid)

    if not normalized_ids:
        return _empty_filtered_deck_by_name(deck_name)

    _prepare_filtered_review_deck(
        normalized_ids,
        deck_name=deck_name,
        preserve_order=preserve_order,
        select_deck=False,
    )
    return True


def _session_deck_id_by_name(deck_name: str) -> int | None:
    name = str(deck_name or "").strip()
    if not name:
        return None
    existing = mw.col.decks.by_name(name)
    if not existing or not existing.get("dyn"):
        return None
    try:
        return int(existing["id"])
    except Exception:
        return None


def _queue_entry_card_id(entry) -> int | None:
    candidates = []
    if isinstance(entry, int):
        candidates.append(entry)
    for attr in ("id", "card_id", "cid"):
        candidates.append(getattr(entry, attr, None))

    nested_card = getattr(entry, "card", None)
    if nested_card is not None:
        if isinstance(nested_card, int):
            candidates.append(nested_card)
        for attr in ("id", "card_id", "cid"):
            candidates.append(getattr(nested_card, attr, None))

    for raw in candidates:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0:
            return cid
    return None


def _queue_entry_matches_deck(entry, deck_id: int) -> bool:
    try:
        wanted = int(deck_id)
    except Exception:
        return True
    if wanted <= 0:
        return True

    seen_deck_metadata = False
    for raw in (
        getattr(entry, "did", None),
        getattr(entry, "deck_id", None),
        getattr(getattr(entry, "card", None), "did", None),
        getattr(getattr(entry, "card", None), "deck_id", None),
    ):
        try:
            did = int(raw)
        except Exception:
            continue
        if did <= 0:
            continue
        seen_deck_metadata = True
        if did == wanted:
            return True

    # When Anki omits deck metadata on a queue entry, keep the card rather than
    # accidentally hiding a real session card from refill accounting.
    return not seen_deck_metadata


def _live_filtered_queue_ids(
    deck_id: int,
    fetch_limit: int,
    *,
    scheduled_ids: set[int] | None = None,
) -> list[int]:
    try:
        queued = mw.col.sched.get_queued_cards(fetch_limit=fetch_limit)
    except TypeError:
        queued = mw.col.sched.get_queued_cards(fetch_limit)

    entries = getattr(queued, "cards", queued)
    ordered_ids: list[int] = []
    scheduled: set[int] = set()
    for raw in (scheduled_ids or set()):
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0:
            scheduled.add(cid)
    for entry in list(entries or []):
        cid = _queue_entry_card_id(entry)
        if cid is None:
            continue
        if scheduled:
            if cid in scheduled:
                ordered_ids.append(cid)
            continue
        if _queue_entry_matches_deck(entry, deck_id):
            ordered_ids.append(cid)
    return ordered_ids


def _has_duplicate_ordered_ids(ordered_ids: list[int]) -> bool:
    seen: set[int] = set()
    for raw in ordered_ids or []:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid <= 0:
            continue
        if cid in seen:
            return True
        seen.add(cid)
    return False


def _unreviewed_live_queue_ids(
    live_queue_ids: list[int],
    reviewed_ids: set[int],
) -> list[int]:
    reviewed: set[int] = set()
    for raw in reviewed_ids or set():
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0:
            reviewed.add(cid)
    if not reviewed:
        return list(live_queue_ids)
    return [cid for cid in live_queue_ids if cid not in reviewed]


def _snapshot_picker_state(picker) -> object:
    snapshot = getattr(picker, "snapshot", None)
    if callable(snapshot):
        return ("picker_snapshot", snapshot())
    return (
        "basic",
        {
            "selected_ids": list(getattr(picker, "selected_ids", []) or []),
            "picked_meta": copy.deepcopy(getattr(picker, "picked_meta", {}) or {}),
            "picked_ids": set(getattr(picker, "picked_ids", set()) or set()),
        },
    )


def _restore_picker_state(picker, snapshot: object) -> None:
    kind, payload = snapshot
    if kind == "picker_snapshot":
        restore = getattr(picker, "_restore_snapshot", None)
        if callable(restore):
            restore(payload)
            return
    if not isinstance(payload, dict):
        return
    selected_ids = list(payload.get("selected_ids") or [])
    picked_meta = copy.deepcopy(payload.get("picked_meta") or {})
    setattr(picker, "selected_ids", selected_ids)
    setattr(picker, "picked_meta", picked_meta)
    if hasattr(picker, "picked_ids"):
        picked_ids = payload.get("picked_ids")
        if isinstance(picked_ids, set):
            setattr(picker, "picked_ids", set(picked_ids))
        else:
            setattr(picker, "picked_ids", set(selected_ids))


def _rebuild_filtered_deck_with_exact_ids(
    deck_name: str,
    ordered_ids: list[int],
    preserve_order: bool,
) -> bool:
    normalized_ids: list[int] = []
    for raw in ordered_ids or []:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0:
            normalized_ids.append(cid)

    if not normalized_ids:
        return _empty_filtered_deck_by_name(deck_name)

    if _has_duplicate_ordered_ids(normalized_ids):
        raise _DuplicateLiveQueueEntriesError(
            "Cannot rebuild a filtered deck from a live queue that contains duplicate card entries."
        )

    _prepare_filtered_review_deck(
        normalized_ids,
        deck_name=deck_name,
        preserve_order=preserve_order,
        select_deck=False,
    )
    return True


def _maybe_auto_refill_active_session(
    state: _ActiveIncrementoSessionState,
) -> dict[str, list[int]] | None:
    if not state.auto_refill_enabled:
        return None

    deck_id = _session_deck_id_by_name(state.session_deck_name)
    if deck_id is None:
        return None

    fetch_limit = max(state.window_size * 3, state.window_size + 20)
    live_queue_ids = _live_filtered_queue_ids(
        deck_id,
        fetch_limit=fetch_limit,
        scheduled_ids=set(state.selected_ids),
    )
    if _has_duplicate_ordered_ids(live_queue_ids):
        return {"live_queue_ids": list(live_queue_ids), "new_ids": []}

    # Answered new cards often remain in Anki's queue as learning/relearning
    # repeats. Keep them in the filtered deck, but do not let them occupy the
    # live window reserved for not-yet-answered session cards.
    unreviewed_live_queue_ids = _unreviewed_live_queue_ids(
        live_queue_ids,
        state.reviewed_ids,
    )
    if len(unreviewed_live_queue_ids) >= state.window_size:
        return {"live_queue_ids": list(live_queue_ids), "new_ids": []}

    missing = state.window_size - len(unreviewed_live_queue_ids)
    picker_snapshot = _snapshot_picker_state(state.picker)
    new_ids = state.picker.pick_until(len(state.picker.selected_ids) + missing)
    if not new_ids:
        return {"live_queue_ids": list(live_queue_ids), "new_ids": []}
    combined_ids = list(live_queue_ids) + list(new_ids)
    try:
        _rebuild_filtered_deck_with_exact_ids(
            state.session_deck_name,
            combined_ids,
            preserve_order=state.preserve_order,
        )
    except Exception:
        _restore_picker_state(state.picker, picker_snapshot)
        raise
    state.selected_ids = list(state.picker.selected_ids)
    state.picked_meta = copy.deepcopy(state.picker.picked_meta)
    return {"live_queue_ids": list(live_queue_ids), "new_ids": list(new_ids)}


def _schedule_deferred_auto_refill(
    state: _ActiveIncrementoSessionState,
    *,
    reason: str,
) -> None:
    if not state.auto_refill_enabled or state.session_closed or state.refill_retry_pending:
        return
    state.refill_retry_pending = True

    def _run() -> None:
        state.refill_retry_pending = False
        if state.session_closed:
            return
        try:
            result = _maybe_auto_refill_active_session(state)
            if bool(getattr(state.cfg, "show_debug", False)):
                print(f"[Incremento] deferred auto-refill ({reason}): {result}")
        except Exception as exc:
            print(f"[Incremento] deferred auto-refill error ({reason}): {exc}")

    QTimer.singleShot(0, _run)


def _sync_session_cleanup_deck(state: _ActiveIncrementoSessionState) -> None:
    try:
        deck_id = _session_deck_id_by_name(state.session_deck_name)
        if deck_id is not None:
            live_queue_ids = _live_filtered_queue_ids(
                deck_id,
                fetch_limit=max(state.window_size * 3, state.window_size + 20),
                scheduled_ids=set(state.selected_ids),
            )
            if _has_duplicate_ordered_ids(live_queue_ids):
                raise _DuplicateLiveQueueEntriesError(
                    "Cannot clean up a filtered deck from a live queue that contains duplicate card entries."
                )
            _rebuild_filtered_deck_with_exact_ids(
                state.session_deck_name,
                live_queue_ids,
                preserve_order=state.preserve_order,
            )
            return
    except Exception:
        pass

    remaining_ids = [cid for cid in state.selected_ids if cid not in state.reviewed_ids]
    _sync_filtered_deck_by_name(
        state.session_deck_name,
        remaining_ids,
        preserve_order=state.preserve_order,
    )


def _record_incremento_answer(
    state: _ActiveIncrementoSessionState,
    reviewer,
    card,
) -> dict[str, list[int]] | None:
    global _session_times

    cid = card.id
    if cid in state.picked_meta and cid not in state.reviewed_ids:
        state.reviewed_ids.add(cid)
        meta = state.picked_meta[cid]
        tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
        fake = types.SimpleNamespace(
            card=cid,
            card_type=meta["card_type"],
            tag=tag,
            mode=meta["mode"],
            review_seconds=_review_seconds(
                reviewer,
                card,
                measured_seconds=state.measured_review_seconds.pop(cid, None),
            ),
        )
        state.stats.record(fake, state.cfg.scheduler_scope)
        _record_session_count(fake.card_type, fake.tag, fake.mode)
        _session_times = copy.deepcopy(state.stats.session_time)
        state.question_started_at.pop(cid, None)

    if not state.auto_refill_enabled:
        return None

    return _maybe_auto_refill_active_session(state)


def _flush_unanswered_time_for_state(state: _ActiveIncrementoSessionState) -> None:
    global _session_times
    if state.session_closed:
        return
    state.session_closed = True

    cid = None
    try:
        cur = getattr(getattr(mw, "reviewer", None), "card", None)
        if cur is not None:
            cid = cur.id
        if cid is None:
            cid = state.last_shown_cid
        if cid is None and state.question_started_at:
            cid = next(reversed(state.question_started_at))
        if cid is not None and cid not in state.measured_review_seconds:
            started = state.question_started_at.get(cid)
            if started is not None:
                state.measured_review_seconds[cid] = max(0.0, time.monotonic() - started)
    except Exception:
        pass

    now = time.monotonic()
    for pending_cid, started in list(state.question_started_at.items()):
        if pending_cid not in state.measured_review_seconds:
            state.measured_review_seconds[pending_cid] = max(0.0, now - started)

    for pending_cid, seconds in list(state.measured_review_seconds.items()):
        if pending_cid in state.reviewed_ids:
            continue
        if pending_cid not in state.picked_meta:
            continue
        meta = state.picked_meta[pending_cid]
        tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
        fake = types.SimpleNamespace(
            card=pending_cid,
            card_type=meta["card_type"],
            tag=tag,
            mode=meta["mode"],
        )
        state.stats.record_time_only(fake, seconds)

    _session_times = copy.deepcopy(state.stats.session_time)


def start_explicit_review(
    selected_ids: list[int],
    *,
    deck_name: str = INCREMENTO_DECK,
    preserve_order: bool = True,
    empty_message: str = "No cards available to review.",
    on_finished=None,
) -> bool:
    normalized_ids: list[int] = []
    for cid in selected_ids or []:
        try:
            value = int(cid)
        except Exception:
            continue
        if value > 0:
            normalized_ids.append(value)

    if not normalized_ids:
        if empty_message:
            showInfo(empty_message)
        return False

    try:
        _prepare_filtered_review_deck(
            normalized_ids,
            deck_name=deck_name,
            preserve_order=preserve_order,
            select_deck=True,
        )
    except Exception as e:
        showInfo(str(e))
        return False

    if on_finished is not None:
        finished = False

        def _finish_once() -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            for hook_list, fn in (
                (gui_hooks.reviewer_will_end, _on_reviewer_end),
                (gui_hooks.state_did_change, _on_state_did_change),
            ):
                try:
                    hook_list.remove(fn)
                except ValueError:
                    pass
            try:
                on_finished()
            except Exception as e:
                print(f"[Incremento] explicit review finish callback error: {e}")

        def _on_reviewer_end() -> None:
            _finish_once()

        def _on_state_did_change(new_state: str, old_state: str) -> None:
            if old_state == "review" and new_state != "review":
                _finish_once()

        gui_hooks.reviewer_will_end.append(_on_reviewer_end)
        gui_hooks.state_did_change.append(_on_state_did_change)

    mw.moveToState("review")
    return True


def start_quick_open_review(card_id: int) -> bool:
    try:
        normalized_id = int(card_id)
    except Exception:
        showInfo("No selected card is available to study.")
        return False

    if normalized_id <= 0:
        showInfo("No selected card is available to study.")
        return False

    return start_explicit_review(
        [normalized_id],
        deck_name=INCREMENTO_QUICK_OPEN_REVIEW_DECK,
        preserve_order=True,
        empty_message="No selected card is available to study.",
    )


def _review_seconds(reviewer, card, measured_seconds: float | None = None) -> float:
    """Best-effort extraction of review duration in seconds.

    Prefer a pre-measured duration (question shown -> answer shown / exit),
    then fall back to Anki's time_taken API.
    """
    if measured_seconds is not None:
        try:
            return max(0.0, float(measured_seconds))
        except Exception:
            pass

    try:
        if hasattr(card, "time_taken"):
            try:
                ms = card.time_taken()  # Anki card API (ms)
            except TypeError:
                ms = card.time_taken(capped=False)
            if ms:
                return max(0.0, float(ms) / 1000.0)
    except Exception:
        pass

    try:
        rc = getattr(reviewer, "card", None)
        if rc is not None and hasattr(rc, "time_taken"):
            try:
                ms = rc.time_taken()
            except TypeError:
                ms = rc.time_taken(capped=False)
            if ms:
                return max(0.0, float(ms) / 1000.0)
    except Exception:
        pass

    return 0.0


def learnFunction(*, branch_scope: dict | None = None) -> None:
    global _active_incremento_session_state
    try:
        release_expired_timed_postpones()
    except Exception:
        pass

    config = mw.addonManager.getConfig(_ADDON_PKG) or {}

    dlg = SchedulerConfigDialog(
        mw,
        on_clear_session=reset_session_counts,
        branch_scope=branch_scope,
    )
    if not dlg.exec():
        return

    dlg.save_config()
    cfg = dlg.to_config()
    preview_override = dlg.get_preview_override() if hasattr(dlg, "get_preview_override") else None
    if preview_override:
        preview_snapshot = preview_override.get("picker_snapshot")
        picker = SessionPicker(
            cfg,
            _ADDON_DIR,
            branch_scope=branch_scope,
            snapshot=preview_snapshot,
        )
        stats = picker.stats
        selected_ids = (
            list(picker.selected_ids)
            if preview_snapshot is not None
            else list(preview_override.get("selected_ids", []))
        )
        _picked_meta: dict[int, dict] = (
            copy.deepcopy(picker.picked_meta)
            if preview_snapshot is not None
            else copy.deepcopy(preview_override.get("picked_meta", {}))
        )
        session_time_snapshot = preview_override.get("session_time", {"type": {}, "tags": {}})
    else:
        selection = select_session_cards(cfg, _ADDON_DIR, branch_scope=branch_scope)
        picker = SessionPicker(
            cfg,
            _ADDON_DIR,
            branch_scope=branch_scope,
            snapshot=selection.picker_snapshot,
        )
        stats = selection.stats
        selected_ids = list(selection.selected_ids)
        _picked_meta = copy.deepcopy(selection.picked_meta)
        session_time_snapshot = stats.session_time

    # The picker uses session-shaped counts to build the deck, but the
    # statistics dialog should show cards actually reviewed.
    global _session_counts, _session_times
    _session_counts = _empty()
    _session_times = copy.deepcopy(session_time_snapshot)

    if not selected_ids:
        branch_title = str((branch_scope or {}).get("root_title") or "").strip()
        if branch_title:
            showInfo(f'No cards available to study in branch "{branch_title}".')
        else:
            showInfo("No cards available to study.")
        return

    # DEBUG: show scheduled card order before building the filtered deck
    if cfg.show_debug:
        _debug_dlg = QDialog(mw)
        branch_title = str((branch_scope or {}).get("root_title") or "").strip()
        debug_title = f"DEBUG — Scheduled order ({len(selected_ids)} cards)"
        if branch_title:
            debug_title += f" — {branch_title}"
        _debug_dlg.setWindowTitle(debug_title)
        _debug_dlg.resize(700, 500)
        _debug_layout = QVBoxLayout(_debug_dlg)
        _debug_txt = QTextEdit()
        _debug_txt.setReadOnly(True)
        _debug_txt.setFontFamily("Courier")
        _debug_lines = ["#    type     mode       tag                  first field"]
        _debug_lines.append("-" * 80)
        for _i, _cid in enumerate(selected_ids):
            _meta = _picked_meta.get(_cid, {})
            _card = mw.col.get_card(_cid)
            _note = mw.col.get_note(_card.nid)
            _field = (
                (_note.fields[0][:55].replace("\n", " ")) if _note.fields else str(_cid)
            )
            _debug_lines.append(
                f"{_i + 1:3}.  {_meta.get('card_type', '?'):7}  {_meta.get('mode', '?'):9}  "
                f"{(_meta.get('tag') or 'no-tag'):20} {_field}"
            )
        _debug_txt.setPlainText("\n".join(_debug_lines))
        _debug_layout.addWidget(_debug_txt)
        _debug_btn = QPushButton("Continue")
        _debug_btn.clicked.connect(_debug_dlg.accept)
        _debug_layout.addWidget(_debug_btn)
        _debug_dlg.exec()

    dialog_profile_name = (
        dlg.selected_dialog_profile_name()
        if hasattr(dlg, "selected_dialog_profile_name")
        else None
    )
    session_deck_name = incremento_session_deck_name(dialog_profile_name)
    try:
        _prepare_filtered_review_deck(
            selected_ids,
            deck_name=session_deck_name,
            preserve_order=cfg.preserve_order,
            select_deck=True,
        )
    except Exception as e:
        showInfo(str(e))
        return

    state = _ActiveIncrementoSessionState(
        cfg=cfg,
        stats=stats,
        picker=picker,
        session_deck_name=session_deck_name,
        window_size=max(0, int(cfg.session_card_count or 0)),
        preserve_order=bool(cfg.preserve_order),
        picked_meta=copy.deepcopy(_picked_meta),
        selected_ids=list(selected_ids),
        auto_refill_enabled=bool(getattr(cfg, "auto_refill_session", False)),
    )
    _active_incremento_session_state = state

    def _on_card_shown(card) -> None:
        try:
            state.last_shown_cid = card.id
            state.question_started_at[card.id] = time.monotonic()
        except Exception:
            pass

    def _on_answer_shown(card) -> None:
        """Freeze duration at answer reveal (question -> answer shown)."""
        try:
            cid = card.id
            if cid in state.measured_review_seconds:
                return
            started = state.question_started_at.get(cid)
            if started is None:
                return
            state.measured_review_seconds[cid] = max(0.0, time.monotonic() - started)
        except Exception:
            pass

    def _on_card_answered(reviewer, card, ease: int) -> None:
        try:
            result = _record_incremento_answer(state, reviewer, card)
            if state.auto_refill_enabled and (not result or not result.get("new_ids")):
                _schedule_deferred_auto_refill(state, reason="no-immediate-new-cards")
        except Exception as e:
            print(f"[Incremento] _on_card_answered error: {e}")
            _schedule_deferred_auto_refill(state, reason="immediate-error")

    gui_hooks.reviewer_did_show_question.append(_on_card_shown)
    gui_hooks.reviewer_did_show_answer.append(_on_answer_shown)
    gui_hooks.reviewer_did_answer_card.append(_on_card_answered)

    # One-shot hooks: clean up when reviewer is left.
    def _on_reviewer_end() -> None:
        global _active_incremento_session_state
        try:
            _flush_unanswered_time_for_state(state)
        except Exception as e:
            print(f"[Incremento] _on_reviewer_end time-only stats error: {e}")

        for hook_list, fn in (
            (gui_hooks.reviewer_will_end, _on_reviewer_end),
            (gui_hooks.state_did_change, _on_state_did_change),
            (gui_hooks.reviewer_did_show_question, _on_card_shown),
            (gui_hooks.reviewer_did_show_answer, _on_answer_shown),
            (gui_hooks.reviewer_did_answer_card, _on_card_answered),
        ):
            try:
                hook_list.remove(fn)
            except ValueError:
                pass

        try:
            _sync_session_cleanup_deck(state)
        except Exception as e:
            print(f"[Incremento] session deck cleanup error: {e}")
        finally:
            if _active_incremento_session_state is state:
                _active_incremento_session_state = None

    def _on_state_did_change(new_state: str, old_state: str) -> None:
        if old_state == "review" and new_state != "review":
            _on_reviewer_end()

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.state_did_change.append(_on_state_did_change)
    mw.moveToState("review")
