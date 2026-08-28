"""
session.py — learnFunction and session-scope statistics state.

Owns the in-memory session counts and the full card-picking / filtered-deck
creation logic that was previously inline in __init__.py.

Public API:
    INCREMENTO_DECK       — filtered deck name constant
    INCREMENTO_QUICK_OPEN_REVIEW_DECK — filtered deck for quick-open study
    incremento_session_deck_name() — map an optional dialog profile to a deck name
    is_incremento_session_deck_name() — predicate for Incremento session decks
    learnFunction()       — dialog-agnostic session orchestration entry point
    start_quick_open_review() — study one quick-open doc card in a filtered deck
    reset_session_counts() — clear in-memory session counts
    get_session_counts()  — return a copy of the current session counts
    diagnostic_session_snapshot() — privacy-safe active-session counters/flags
    register_diagnostic_event_callback() — install the optional event sink
"""

import copy
import os
import time
import types
from dataclasses import dataclass, field

from aqt import mw, gui_hooks
from aqt.utils import showInfo
from aqt.qt import QTimer
try:
    from anki.consts import DYN_DUE, DYN_OLDEST
except Exception:
    DYN_OLDEST = 0
    DYN_DUE = 6

from .scheduler import NO_TAGS_KEY
from .config_service import load_addon_config
from .statistics import StatsManager, _empty, _empty_time
from .session_selection import SessionPicker
from .paths import get_active_profile as _active_profile
from .topic_scheduler import resolve_topic_card_classifier
from .topic_postpone import release_expired_timed_postpones
from .anki_compat import install_one_shot_next_card_override

# Compatibility seam for callers/tests that inject a dialog factory. Shipped
# UI entry points pass SchedulerConfigDialog through frontend.session_launcher;
# backend never imports frontend.
SchedulerConfigDialog = None

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_ADDON_PKG = __name__.split(".")[0]  # "incremento"

INCREMENTO_DECK = "Incremento Session"
INCREMENTO_PDF_REVIEW_DECK = "Incremento PDF Review"
INCREMENTO_EPUB_REVIEW_DECK = "Incremento EPUB Review"
INCREMENTO_VIDEO_REVIEW_DECK = "Incremento Video Review"
INCREMENTO_QUICK_OPEN_REVIEW_DECK = "Incremento Quick Open Review"

# Most-recent reviewed session counts, updated as cards are answered.
# Accessed via get_session_counts() from __init__.py for the stats dialog.
_session_counts: dict = {"type": {}, "tags": {}, "mode": {}}
_session_times: dict = _empty_time()
_active_incremento_session_state = None
_diagnostic_event_callback = None
_session_debug_callback = None
_session_launch_generation = 0
_COLLECTION_UI_SETTLE_MS = 100


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


@dataclass
class _FilteredDeckBuildResult:
    deck_id: int | None
    changes: object


@dataclass
class _SessionSelectionOperationResult:
    picker: SessionPicker
    stats: StatsManager
    selected_ids: list[int]
    picked_meta: dict[int, dict]
    session_time_snapshot: dict


@dataclass
class _SessionBuildOperationResult:
    changes: object
    picker: SessionPicker
    stats: StatsManager
    selected_ids: list[int]
    picked_meta: dict[int, dict]
    session_time_snapshot: dict
    deck_id: int | None


@dataclass
class _RefillOperationResult:
    changes: object
    live_queue_ids: list[int]
    new_ids: list[int]
    outcome: str = "other"


@dataclass
class _ExplicitReviewOperationResult:
    changes: object
    requested_ids: list[int]
    selected_ids: list[int]
    unavailable_ids: list[int]
    deck_id: int | None


def _empty_op_changes():
    from anki.collection import OpChanges

    return OpChanges()


def _merge_op_changes(target, *operation_results) -> None:
    for result in operation_results:
        if result is None:
            continue
        changes = getattr(result, "changes", result)
        if changes is None:
            continue
        try:
            target.MergeFrom(changes)
        except (TypeError, ValueError):
            # Compatibility with older/mocked Anki APIs that do not expose
            # protobuf operation changes. The actual mutation still succeeds.
            continue


def _run_collection_operation(
    *,
    parent,
    op,
    success,
    failure=None,
    initiator=None,
) -> None:
    """Run a collection mutation without blocking Qt's main event loop."""
    from aqt.operations import CollectionOp

    operation = CollectionOp(parent, op).success(success)
    if failure is not None:
        operation = operation.failure(failure)
    operation.run_in_background(initiator=initiator)


def _run_collection_query(
    *,
    parent,
    op,
    success,
    failure=None,
) -> None:
    """Run a read-only collection query without application-modal progress.

    Session selection can be expensive on large collections, but it does not
    mutate Anki. A no-progress ``QueryOp`` keeps that work serialized with
    collection access without disabling every deck-browser click while it
    runs or waits behind another collection task.
    """
    from aqt.operations import QueryOp

    operation = QueryOp(parent=parent, op=op, success=success)
    if failure is not None:
        operation = operation.failure(failure)
    operation.run_in_background()


def _run_collection_mutation_without_progress(
    *,
    parent,
    op,
    success,
    failure=None,
    initiator=None,
) -> None:
    """Run a short collection mutation without an application-modal dialog.

    ``CollectionOp`` always creates an application-modal progress dialog, even
    when a filtered-deck rebuild completes in a few milliseconds.  Entering the
    reviewer while macOS is tearing down that native modal can leave the main
    window unable to accept clicks.  ``QueryOp`` uses the same serialized
    collection executor and background-operation hooks without creating that
    dialog.  Dispatching ``on_op_finished`` preserves the normal undo/UI change
    notifications expected from the returned ``OpChanges``.

    This helper is intentionally reserved for bounded, fast mutations such as
    the already-selected Incremento session deck build.
    """
    from aqt.operations import QueryOp, on_op_finished

    def _success_with_changes(result) -> None:
        try:
            success(result)
        finally:
            on_op_finished(mw, result, initiator)

    operation = QueryOp(parent=parent, op=op, success=_success_with_changes)
    if failure is not None:
        operation = operation.failure(failure)
    operation.run_in_background()


def _begin_session_launch() -> int:
    """Return a monotonically increasing token for the newest session request."""
    global _session_launch_generation
    _session_launch_generation += 1
    return _session_launch_generation


def _is_current_session_launch(token: int, profile: str) -> bool:
    """Reject results from a superseded request or a previous profile."""
    return (
        int(token) == int(_session_launch_generation)
        and str(profile or "") == str(_active_profile() or "")
    )


def _defer_collection_ui_action(callback) -> None:
    """Run UI work after the current CollectionOp and native modal UI settle.

    ``CollectionOp`` invokes its success callback immediately before it
    dispatches collection-change hooks.  Its application-modal progress dialog
    is closed before the callback, but on macOS the native modal state can take
    another event-loop turn to disappear.  A short, progress-independent delay
    avoids entering the reviewer underneath that stale native modal state.

    Do not use ``ProgressManager.single_shot()`` here: that helper retries
    forever while *any* Anki progress level is active, so an unrelated or stale
    nested progress level can prevent session activation indefinitely.
    """
    QTimer.singleShot(_COLLECTION_UI_SETTLE_MS, callback)


def _defer_profile_ui_action(profile: str, callback) -> None:
    """Defer UI work, dropping a stale callback after a profile switch."""
    def _run_if_current() -> None:
        if str(profile or "") != str(_active_profile() or ""):
            return
        callback()

    _defer_collection_ui_action(_run_if_current)


def _optional_col_kwargs(col) -> dict:
    return {"col": col} if col is not None else {}


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


def register_diagnostic_event_callback(callback) -> None:
    """Install a best-effort sink that receives only typed, content-free fields."""
    global _diagnostic_event_callback
    _diagnostic_event_callback = callback if callable(callback) else None


def register_session_debug_callback(callback) -> None:
    """Install the optional frontend renderer for scheduled-order debugging."""
    global _session_debug_callback
    _session_debug_callback = callback if callable(callback) else None


def _emit_diagnostic_event(event: str, **fields) -> None:
    callback = _diagnostic_event_callback
    if callback is None:
        return
    try:
        callback(str(event), dict(fields))
    except Exception:
        # Diagnostics must never alter scheduling or reviewer control flow.
        pass


def record_media_review_inspection_started(content_kind: str) -> None:
    _emit_diagnostic_event(
        "media_review_inspection_started",
        content_kind=content_kind,
    )


def record_media_review_inspection_finished(
    content_kind: str,
    candidate_count: int,
) -> None:
    _emit_diagnostic_event(
        "media_review_inspection_finished",
        content_kind=content_kind,
        candidate_count=candidate_count,
    )


def record_media_review_inspection_failed(
    content_kind: str,
    exc: Exception,
) -> None:
    _emit_diagnostic_event(
        "media_review_inspection_failed",
        content_kind=content_kind,
        error_type=type(exc).__name__,
    )


def diagnostic_session_snapshot() -> dict[str, object]:
    """Return counters/flags only; never expose card ids, tags, or deck names."""
    state = _active_incremento_session_state
    if state is None:
        return {
            "active": False,
            "selected_count": 0,
            "reviewed_count": 0,
            "window_size": 0,
            "auto_refill": False,
            "refill_pending": False,
            "closed": False,
        }
    return {
        "active": not bool(state.session_closed),
        "selected_count": len(state.selected_ids),
        "reviewed_count": len(state.reviewed_ids),
        "window_size": max(0, int(state.window_size or 0)),
        "auto_refill": bool(state.auto_refill_enabled),
        "refill_pending": bool(state.refill_retry_pending),
        "closed": bool(state.session_closed),
    }


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
    col=None,
    return_result: bool = False,
) -> int | _FilteredDeckBuildResult:
    collection = col if col is not None else mw.col
    changes = _empty_op_changes() if return_result else None
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

    existing = collection.decks.by_name(deck_name)
    if existing:
        if not existing.get("dyn"):
            raise RuntimeError(f"'{deck_name}' is a normal deck. Delete or rename it first.")
        did = existing["id"]
        empty_result = collection.sched.empty_filtered_deck(did)
        if changes is not None:
            _merge_op_changes(changes, empty_result)
    else:
        did = collection.decks.new_filtered(deck_name)

    fdu = collection.sched.get_or_create_filtered_deck(did)
    fdu.config.reschedule = True
    del fdu.config.search_terms[:]
    fdu.config.search_terms.add(
        search=search,
        limit=len(normalized_ids),
        order=DYN_DUE if preserve_order else DYN_OLDEST,
    )
    op = collection.sched.add_or_update_filtered_deck(fdu)
    rebuild_result = collection.sched.rebuild_filtered_deck(op.id)
    if changes is not None:
        _merge_op_changes(changes, op, rebuild_result)

    if preserve_order:
        position = 0
        cards_to_update = []
        for cid in normalized_ids:
            card = collection.get_card(cid)
            if int(getattr(card, "did", 0) or 0) != int(op.id):
                continue
            card.due = position
            cards_to_update.append(card)
            position += 1
        if cards_to_update:
            update_cards = getattr(collection, "update_cards", None)
            if callable(update_cards):
                try:
                    update_result = update_cards(cards_to_update, skip_undo_entry=True)
                except TypeError:
                    update_result = update_cards(cards_to_update)
                if changes is not None:
                    _merge_op_changes(changes, update_result)
            else:
                for card in cards_to_update:
                    try:
                        update_result = collection.update_card(card, skip_undo_entry=True)
                    except TypeError:
                        update_result = collection.update_card(card)
                    if changes is not None:
                        _merge_op_changes(changes, update_result)

    if select_deck:
        collection.decks.select(op.id)
    if return_result:
        return _FilteredDeckBuildResult(deck_id=int(op.id), changes=changes)
    return int(op.id)


def _empty_filtered_deck_by_name(
    deck_name: str,
    *,
    col=None,
    return_result: bool = False,
) -> bool | _FilteredDeckBuildResult:
    collection = col if col is not None else mw.col
    changes = _empty_op_changes() if return_result else None
    name = str(deck_name or "").strip()
    if not name:
        return _FilteredDeckBuildResult(None, changes) if return_result else False
    existing = collection.decks.by_name(name)
    if not existing or not existing.get("dyn"):
        return _FilteredDeckBuildResult(None, changes) if return_result else False
    empty_result = collection.sched.empty_filtered_deck(existing["id"])
    if changes is not None:
        _merge_op_changes(changes, empty_result)
        return _FilteredDeckBuildResult(int(existing["id"]), changes)
    return True


def _sync_filtered_deck_by_name(
    deck_name: str,
    selected_ids: list[int],
    *,
    preserve_order: bool,
    col=None,
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
        return bool(_empty_filtered_deck_by_name(deck_name, **_optional_col_kwargs(col)))

    _prepare_filtered_review_deck(
        normalized_ids,
        deck_name=deck_name,
        preserve_order=preserve_order,
        select_deck=False,
        **_optional_col_kwargs(col),
    )
    return True


def _session_deck_id_by_name(deck_name: str, *, col=None) -> int | None:
    collection = col if col is not None else mw.col
    name = str(deck_name or "").strip()
    if not name:
        return None
    existing = collection.decks.by_name(name)
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
    col=None,
) -> list[int]:
    collection = col if col is not None else mw.col
    try:
        queued = collection.sched.get_queued_cards(fetch_limit=fetch_limit)
    except TypeError:
        queued = collection.sched.get_queued_cards(fetch_limit)

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


def _live_queue_fetch_limit(state: _ActiveIncrementoSessionState) -> int:
    """Bound queue reads by cards actually admitted, not a huge requested cap."""
    selected_count = len(set(state.selected_ids or []))
    if selected_count <= 0:
        return max(20, min(max(0, int(state.window_size or 0)), 100))
    window_size = max(0, int(state.window_size or 0))
    active_capacity = min(selected_count, window_size) if window_size else selected_count
    return max(active_capacity * 3, active_capacity + 20)


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
    *,
    col=None,
    return_result: bool = False,
) -> bool | _FilteredDeckBuildResult:
    normalized_ids: list[int] = []
    for raw in ordered_ids or []:
        try:
            cid = int(raw)
        except Exception:
            continue
        if cid > 0:
            normalized_ids.append(cid)

    if not normalized_ids:
        kwargs = _optional_col_kwargs(col)
        if return_result:
            kwargs["return_result"] = True
        return _empty_filtered_deck_by_name(deck_name, **kwargs)

    if _has_duplicate_ordered_ids(normalized_ids):
        raise _DuplicateLiveQueueEntriesError(
            "Cannot rebuild a filtered deck from a live queue that contains duplicate card entries."
        )

    kwargs = _optional_col_kwargs(col)
    if return_result:
        kwargs["return_result"] = True
    result = _prepare_filtered_review_deck(
        normalized_ids,
        deck_name=deck_name,
        preserve_order=preserve_order,
        select_deck=False,
        **kwargs,
    )
    return result if return_result else True


def _maybe_auto_refill_active_session(
    state: _ActiveIncrementoSessionState,
    *,
    col=None,
    return_result: bool = False,
) -> dict[str, list[int]] | _RefillOperationResult | None:
    def _result(
        live_ids: list[int],
        new_ids: list[int],
        changes=None,
        *,
        outcome: str = "other",
    ):
        if return_result:
            return _RefillOperationResult(
                changes=changes if changes is not None else _empty_op_changes(),
                live_queue_ids=list(live_ids),
                new_ids=list(new_ids),
                outcome=str(outcome or "other"),
            )
        return {"live_queue_ids": list(live_ids), "new_ids": list(new_ids)}

    if not state.auto_refill_enabled:
        return _result([], [], outcome="disabled") if return_result else None
    if state.session_closed:
        return _result([], [], outcome="closed")

    deck_id = _session_deck_id_by_name(
        state.session_deck_name,
        **_optional_col_kwargs(col),
    )
    if deck_id is None:
        return _result([], [], outcome="missing_deck") if return_result else None

    fetch_limit = _live_queue_fetch_limit(state)
    live_queue_ids = _live_filtered_queue_ids(
        deck_id,
        fetch_limit=fetch_limit,
        scheduled_ids=set(state.selected_ids),
        **_optional_col_kwargs(col),
    )
    if _has_duplicate_ordered_ids(live_queue_ids):
        return _result(live_queue_ids, [], outcome="duplicate_queue")

    # Answered new cards often remain in Anki's queue as learning/relearning
    # repeats. Keep them in the filtered deck, but do not let them occupy the
    # live window reserved for not-yet-answered session cards.
    unreviewed_live_queue_ids = _unreviewed_live_queue_ids(
        live_queue_ids,
        state.reviewed_ids,
    )
    if len(unreviewed_live_queue_ids) >= state.window_size:
        return _result(live_queue_ids, [], outcome="window_full")

    missing = state.window_size - len(unreviewed_live_queue_ids)
    picker_snapshot = _snapshot_picker_state(state.picker)
    new_ids = state.picker.pick_until(len(state.picker.selected_ids) + missing)
    if not new_ids:
        return _result(live_queue_ids, [], outcome="exhausted")
    if state.session_closed:
        _restore_picker_state(state.picker, picker_snapshot)
        return _result(live_queue_ids, [], outcome="closed")
    combined_ids = list(live_queue_ids) + list(new_ids)
    try:
        rebuild_kwargs = _optional_col_kwargs(col)
        if return_result:
            rebuild_kwargs["return_result"] = True
        rebuild_result = _rebuild_filtered_deck_with_exact_ids(
            state.session_deck_name,
            combined_ids,
            preserve_order=state.preserve_order,
            **rebuild_kwargs,
        )
    except Exception:
        _restore_picker_state(state.picker, picker_snapshot)
        raise
    state.selected_ids = list(state.picker.selected_ids)
    state.picked_meta = copy.deepcopy(state.picker.picked_meta)
    changes = getattr(rebuild_result, "changes", None) if return_result else None
    return _result(live_queue_ids, new_ids, changes, outcome="added")


def _schedule_deferred_auto_refill(
    state: _ActiveIncrementoSessionState,
    *,
    reason: str,
) -> None:
    if not state.auto_refill_enabled:
        _emit_diagnostic_event(
            "incremento_session_refill_skipped",
            reason="disabled",
        )
        return
    if state.session_closed:
        _emit_diagnostic_event(
            "incremento_session_refill_skipped",
            reason="closed",
        )
        return
    if state.refill_retry_pending:
        _emit_diagnostic_event(
            "incremento_session_refill_skipped",
            reason="already_pending",
        )
        return
    state.refill_retry_pending = True
    diagnostic_reason = "card_answered" if reason == "card-answered" else "other"
    _emit_diagnostic_event(
        "incremento_session_refill_requested",
        reason=diagnostic_reason,
    )

    def _run() -> None:
        if state.session_closed:
            state.refill_retry_pending = False
            _emit_diagnostic_event(
                "incremento_session_refill_finished",
                live_count=0,
                added_count=0,
                outcome="closed",
            )
            return

        def _op(col):
            return _maybe_auto_refill_active_session(
                state,
                col=col,
                return_result=True,
            )

        def _success(result) -> None:
            state.refill_retry_pending = False
            _emit_diagnostic_event(
                "incremento_session_refill_finished",
                live_count=len(list(getattr(result, "live_queue_ids", []) or [])),
                added_count=len(list(getattr(result, "new_ids", []) or [])),
                outcome=str(getattr(result, "outcome", "other") or "other"),
            )
            if bool(getattr(state.cfg, "show_debug", False)):
                print(f"[Incremento] deferred auto-refill ({reason}): {result}")

        def _failure(exc: Exception) -> None:
            state.refill_retry_pending = False
            _emit_diagnostic_event(
                "incremento_session_refill_failed",
                reason=diagnostic_reason,
                error_type=type(exc).__name__,
            )
            print(f"[Incremento] deferred auto-refill error ({reason}): {exc}")

        try:
            _run_collection_operation(
                parent=mw,
                op=_op,
                success=_success,
                failure=_failure,
                initiator=state,
            )
        except Exception as exc:
            _failure(exc)

    QTimer.singleShot(0, _run)


def _defer_next_card_until_refill_finishes(
    state: _ActiveIncrementoSessionState,
    reviewer,
) -> bool:
    """Do not show the next card while refill may rebuild its filtered deck."""
    if reviewer is None or not state.auto_refill_enabled:
        return False

    def _replacement_factory(original_next, restore):
        def _wait_then_continue() -> None:
            if state.session_closed:
                return
            if state.refill_retry_pending:
                QTimer.singleShot(25, _wait_then_continue)
                return
            if str(getattr(mw, "state", "review") or "") != "review":
                return
            original_next()

        def _deferred_next() -> None:
            restore()
            QTimer.singleShot(0, _wait_then_continue)

        return _deferred_next

    return install_one_shot_next_card_override(
        reviewer,
        _replacement_factory,
    )


def _record_incremento_answer(
    state: _ActiveIncrementoSessionState,
    reviewer,
    card,
) -> None:
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

    return None


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


def _normalize_explicit_review_ids(selected_ids) -> list[int]:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for cid in selected_ids or []:
        try:
            value = int(cid)
        except Exception:
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized_ids.append(value)
    return normalized_ids


def _register_explicit_review_finished_callback(
    on_finished,
    *,
    diagnostic_source: str = "other",
    diagnostic_content_kind: str = "other",
) -> None:

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
        _emit_diagnostic_event(
            "explicit_review_ended",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
        )
        if on_finished is None:
            return
        try:
            on_finished()
        except Exception as e:
            _emit_diagnostic_event(
                "explicit_review_failed",
                source=diagnostic_source,
                content_kind=diagnostic_content_kind,
                stage="review",
                error_type=type(e).__name__,
            )
            print(f"[Incremento] explicit review finish callback error: {e}")

    def _on_reviewer_end() -> None:
        _finish_once()

    def _on_state_did_change(new_state: str, old_state: str) -> None:
        if old_state == "review" and new_state != "review":
            _finish_once()

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.state_did_change.append(_on_state_did_change)


def start_explicit_review(
    selected_ids: list[int],
    *,
    deck_name: str = INCREMENTO_DECK,
    preserve_order: bool = True,
    empty_message: str = "No cards available to review.",
    on_finished=None,
    diagnostic_source: str = "selected_cards",
    diagnostic_content_kind: str = "other",
) -> bool:
    normalized_ids = _normalize_explicit_review_ids(selected_ids)
    _emit_diagnostic_event(
        "explicit_review_requested",
        source=diagnostic_source,
        content_kind=diagnostic_content_kind,
        requested_count=len(normalized_ids),
        preserve_order=bool(preserve_order),
    )

    if not normalized_ids:
        _emit_diagnostic_event(
            "explicit_review_build_finished",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            requested_count=0,
            selected_count=0,
            unavailable_count=0,
        )
        if empty_message:
            showInfo(empty_message)
        return False

    try:
        _emit_diagnostic_event(
            "explicit_review_build_started",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
        )
        _prepare_filtered_review_deck(
            normalized_ids,
            deck_name=deck_name,
            preserve_order=preserve_order,
            select_deck=True,
        )
    except Exception as e:
        _emit_diagnostic_event(
            "explicit_review_failed",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            stage="deck_build",
            error_type=type(e).__name__,
        )
        showInfo(str(e))
        return False

    _emit_diagnostic_event(
        "explicit_review_build_finished",
        source=diagnostic_source,
        content_kind=diagnostic_content_kind,
        requested_count=len(normalized_ids),
        selected_count=len(normalized_ids),
        unavailable_count=0,
    )
    try:
        mw.moveToState("review")
    except Exception as exc:
        _emit_diagnostic_event(
            "explicit_review_failed",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            stage="activation",
            error_type=type(exc).__name__,
        )
        showInfo(f"Could not enter review:\n{exc}")
        return False
    _register_explicit_review_finished_callback(
        on_finished,
        diagnostic_source=diagnostic_source,
        diagnostic_content_kind=diagnostic_content_kind,
    )
    _emit_diagnostic_event(
        "explicit_review_started",
        source=diagnostic_source,
        content_kind=diagnostic_content_kind,
        selected_count=len(normalized_ids),
    )
    return True


def start_explicit_review_from_selector(
    select_ids,
    *,
    deck_name: str = INCREMENTO_DECK,
    preserve_order: bool = True,
    empty_message: str = "No cards available to review.",
    error_message: str = "Could not start review",
    on_finished=None,
    diagnostic_source: str = "selected_cards",
    diagnostic_content_kind: str = "other",
    diagnostic_media_order: str | None = None,
    diagnostic_media_card_kind: str | None = None,
    diagnostic_media_tree_scope: str | None = None,
    diagnostic_media_range: str | None = None,
    diagnostic_media_state: str | None = None,
    diagnostic_limit: int | None = None,
) -> bool:
    """Resolve and build an explicit review in a background collection operation."""
    if not callable(select_ids):
        _emit_diagnostic_event(
            "explicit_review_failed",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            stage="selection",
            error_type="TypeError",
        )
        showInfo(f"{error_message}: no card selector was provided.")
        return False

    profile = _active_profile()

    request_fields = {
        "source": diagnostic_source,
        "content_kind": diagnostic_content_kind,
        "requested_count": 0,
        "preserve_order": bool(preserve_order),
    }
    for key, value in (
        ("media_order", diagnostic_media_order),
        ("media_card_kind", diagnostic_media_card_kind),
        ("media_tree_scope", diagnostic_media_tree_scope),
        ("media_range", diagnostic_media_range),
        ("media_state", diagnostic_media_state),
        ("limit", diagnostic_limit),
    ):
        if value is not None:
            request_fields[key] = value
    _emit_diagnostic_event("explicit_review_requested", **request_fields)
    failure_stage = {"value": "selection"}

    def _build(col) -> _ExplicitReviewOperationResult:
        failure_stage["value"] = "selection"
        _emit_diagnostic_event(
            "explicit_review_build_started",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
        )
        normalized_ids = _normalize_explicit_review_ids(select_ids(col))
        if not normalized_ids:
            _emit_diagnostic_event(
                "explicit_review_build_finished",
                source=diagnostic_source,
                content_kind=diagnostic_content_kind,
                requested_count=0,
                selected_count=0,
                unavailable_count=0,
            )
            return _ExplicitReviewOperationResult(
                changes=_empty_op_changes(),
                requested_ids=[],
                selected_ids=[],
                unavailable_ids=[],
                deck_id=None,
            )
        failure_stage["value"] = "deck_build"
        deck_result = _prepare_filtered_review_deck(
            normalized_ids,
            deck_name=deck_name,
            preserve_order=preserve_order,
            select_deck=False,
            col=col,
            return_result=True,
        )
        included_ids: list[int] = []
        for card_id in normalized_ids:
            try:
                card = col.get_card(int(card_id))
                if int(getattr(card, "did", 0) or 0) == int(deck_result.deck_id):
                    included_ids.append(int(card_id))
            except Exception:
                continue
        included_id_set = set(included_ids)
        unavailable_ids = [
            card_id for card_id in normalized_ids if card_id not in included_id_set
        ]
        if included_ids:
            col.decks.select(int(deck_result.deck_id))
        _emit_diagnostic_event(
            "explicit_review_build_finished",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            requested_count=len(normalized_ids),
            selected_count=len(included_ids),
            unavailable_count=len(unavailable_ids),
        )
        return _ExplicitReviewOperationResult(
            changes=deck_result.changes,
            requested_ids=normalized_ids,
            selected_ids=included_ids,
            unavailable_ids=unavailable_ids,
            deck_id=deck_result.deck_id,
        )

    def _finish_success(result: _ExplicitReviewOperationResult) -> None:
        if not result.selected_ids or result.deck_id is None:
            message = str(empty_message or "").strip()
            if result.unavailable_ids:
                count = len(result.unavailable_ids)
                unavailable = (
                    f"{count} linked card{' was' if count == 1 else 's were'} "
                    "unavailable because Anki cannot move suspended, buried, or "
                    "already-filtered cards into this review deck."
                )
                message = f"{message}\n\n{unavailable}" if message else unavailable
            if message:
                showInfo(message)
            return
        if result.unavailable_ids:
            count = len(result.unavailable_ids)
            showInfo(
                f"{count} requested card{' was' if count == 1 else 's were'} not added. "
                "Anki cannot move suspended, buried, or already-filtered cards "
                "into this review deck. The remaining linked cards will be reviewed."
            )
        try:
            mw.moveToState("review")
        except Exception as exc:
            _emit_diagnostic_event(
                "explicit_review_failed",
                source=diagnostic_source,
                content_kind=diagnostic_content_kind,
                stage="activation",
                error_type=type(exc).__name__,
            )
            showInfo(f"{error_message}:\n{exc}")
            return
        _register_explicit_review_finished_callback(
            on_finished,
            diagnostic_source=diagnostic_source,
            diagnostic_content_kind=diagnostic_content_kind,
        )
        _emit_diagnostic_event(
            "explicit_review_started",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            selected_count=len(result.selected_ids),
        )

    def _success(result: _ExplicitReviewOperationResult) -> None:
        _defer_profile_ui_action(profile, lambda: _finish_success(result))

    def _failure(exc: Exception) -> None:
        _emit_diagnostic_event(
            "explicit_review_failed",
            source=diagnostic_source,
            content_kind=diagnostic_content_kind,
            stage=str(failure_stage.get("value") or "other"),
            error_type=type(exc).__name__,
        )
        _defer_profile_ui_action(
            profile,
            lambda: showInfo(f"{error_message}:\n{exc}")
        )

    try:
        _run_collection_operation(
            parent=mw,
            op=_build,
            success=_success,
            failure=_failure,
            initiator=select_ids,
        )
    except Exception as exc:
        _failure(exc)
        return False
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
        diagnostic_source="quick_open",
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


def _show_scheduled_debug(
    selected_ids: list[int],
    picked_meta: dict[int, dict],
    branch_scope: dict | None,
) -> None:
    callback = _session_debug_callback
    if callback is not None:
        callback(selected_ids, picked_meta, branch_scope)


def _activate_incremento_session(
    result: _SessionBuildOperationResult,
    *,
    cfg,
    branch_scope: dict | None,
    session_deck_name: str,
) -> None:
    global _active_incremento_session_state, _session_counts, _session_times

    # Selection counts are scheduler bookkeeping. The public session counts
    # intentionally track cards actually answered by the reviewer.
    _session_counts = _empty()
    _session_times = copy.deepcopy(result.session_time_snapshot)

    if not result.selected_ids:
        _emit_diagnostic_event(
            "incremento_session_not_started",
            reason="no_cards",
        )
        branch_title = str((branch_scope or {}).get("root_title") or "").strip()
        if branch_title:
            showInfo(f'No cards available to study in branch "{branch_title}".')
        else:
            showInfo("No cards available to study.")
        return

    if bool(getattr(cfg, "show_debug", False)):
        _show_scheduled_debug(result.selected_ids, result.picked_meta, branch_scope)

    state = _ActiveIncrementoSessionState(
        cfg=cfg,
        stats=result.stats,
        picker=result.picker,
        session_deck_name=session_deck_name,
        window_size=max(0, int(cfg.session_card_count or 0)),
        preserve_order=bool(cfg.preserve_order),
        picked_meta=copy.deepcopy(result.picked_meta),
        selected_ids=list(result.selected_ids),
        auto_refill_enabled=bool(getattr(cfg, "auto_refill_session", False)),
    )
    _active_incremento_session_state = state
    _emit_diagnostic_event(
        "incremento_session_phase",
        phase="activation_started",
        selected_count=len(state.selected_ids),
    )
    entered_review = False

    def _mark_entered_review() -> None:
        nonlocal entered_review
        if entered_review or state.session_closed:
            return
        if str(getattr(mw, "state", "") or "") != "review":
            return
        entered_review = True
        _emit_diagnostic_event(
            "incremento_session_phase",
            phase="entered_review",
            selected_count=len(state.selected_ids),
        )
        _emit_diagnostic_event(
            "incremento_session_started",
            selected_count=len(state.selected_ids),
            window_size=state.window_size,
            auto_refill=state.auto_refill_enabled,
            preserve_order=state.preserve_order,
        )

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
            _record_incremento_answer(state, reviewer, card)
        except Exception as e:
            _emit_diagnostic_event(
                "incremento_session_answer_tracking_failed",
                error_type=type(e).__name__,
            )
            print(f"[Incremento] _on_card_answered error: {e}")
        _emit_diagnostic_event(
            "incremento_session_card_answered",
            rating=ease,
            reviewed_count=len(state.reviewed_ids),
            selected_count=len(state.selected_ids),
        )
        if state.auto_refill_enabled:
            if _defer_next_card_until_refill_finishes(state, reviewer):
                _schedule_deferred_auto_refill(state, reason="card-answered")
            else:
                _emit_diagnostic_event(
                    "incremento_session_refill_skipped",
                    reason="advance_not_deferred",
                )
                print("[Incremento] auto-refill skipped: reviewer advance could not be deferred")

    gui_hooks.reviewer_did_show_question.append(_on_card_shown)
    gui_hooks.reviewer_did_show_answer.append(_on_answer_shown)
    gui_hooks.reviewer_did_answer_card.append(_on_card_answered)

    # One-shot hooks: clean up when reviewer is left.
    def _remove_session_hooks() -> None:
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

    def _on_reviewer_end() -> None:
        global _active_incremento_session_state
        try:
            _flush_unanswered_time_for_state(state)
        except Exception as e:
            _emit_diagnostic_event(
                "incremento_session_exit_tracking_failed",
                error_type=type(e).__name__,
            )
            print(f"[Incremento] _on_reviewer_end time-only stats error: {e}")

        _emit_diagnostic_event(
            "incremento_session_ended",
            reviewed_count=len(state.reviewed_ids),
            selected_count=len(state.selected_ids),
            refill_pending=bool(state.refill_retry_pending),
        )

        _remove_session_hooks()

        # Anki already returns completed cards to their home decks and keeps
        # unfinished learning/relearning cards in the filtered deck. Rebuilding
        # here would perform collection work inside reviewer_will_end, block the
        # UI, and race any auto-refill operation still finishing in the
        # background. Leave Anki's live filtered-deck queue untouched.
        if _active_incremento_session_state is state:
            _active_incremento_session_state = None

    def _on_state_did_change(new_state: str, old_state: str) -> None:
        if new_state == "review" and old_state != "review":
            _mark_entered_review()
        if old_state == "review" and new_state != "review":
            _on_reviewer_end()

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.state_did_change.append(_on_state_did_change)
    try:
        mw.moveToState("review")
        QTimer.singleShot(0, _mark_entered_review)
    except Exception as exc:
        state.session_closed = True
        _remove_session_hooks()
        if _active_incremento_session_state is state:
            _active_incremento_session_state = None
        _emit_diagnostic_event(
            "incremento_session_activation_failed",
            error_type=type(exc).__name__,
        )
        showInfo(f"Could not enter the Incremento review session:\n\n{exc}")


def learnFunction(
    *,
    branch_scope: dict | None = None,
    dialog_factory=None,
) -> None:
    """Configure and start a session using a frontend-supplied dialog factory."""
    try:
        release_expired_timed_postpones()
    except Exception:
        pass

    factory = dialog_factory or SchedulerConfigDialog
    if factory is None:
        showInfo("Incremento's scheduler dialog is unavailable in this Anki build.")
        return

    dlg = factory(
        mw,
        on_clear_session=reset_session_counts,
        branch_scope=branch_scope,
    )
    if not dlg.exec():
        return

    dlg.save_config()
    addon_config = load_addon_config(mw.addonManager, _ADDON_PKG)
    cfg = dlg.to_config()
    _emit_diagnostic_event(
        "incremento_session_requested",
        branch_scoped=bool(branch_scope),
        target_count=max(0, int(getattr(cfg, "session_card_count", 0) or 0)),
        auto_refill=bool(getattr(cfg, "auto_refill_session", False)),
        include_new=bool(getattr(cfg, "include_new", True)),
        include_learning=bool(getattr(cfg, "include_learning", True)),
        include_due=bool(getattr(cfg, "include_due", True)),
    )
    preview_override = (
        dlg.get_preview_override() if hasattr(dlg, "get_preview_override") else None
    )
    dialog_profile_name = (
        dlg.selected_dialog_profile_name()
        if hasattr(dlg, "selected_dialog_profile_name")
        else None
    )

    session_deck_name = incremento_session_deck_name(dialog_profile_name)
    branch_scope_copy = copy.deepcopy(branch_scope)
    preview_copy = copy.deepcopy(preview_override)
    profile = _active_profile()
    launch_token = _begin_session_launch()
    topic_classifier = resolve_topic_card_classifier(
        copy.deepcopy(addon_config),
        scheduler_config=cfg,
    )

    def _select_session(col) -> _SessionSelectionOperationResult:
        _emit_diagnostic_event(
            "incremento_session_phase",
            phase="selection_started",
            selected_count=0,
        )
        preview_snapshot = (preview_copy or {}).get("picker_snapshot")
        if preview_copy and preview_snapshot is None:
            preview_snapshot = {
                "scheduler_counts": copy.deepcopy(preview_copy.get("session_counts") or {}),
                "session_counts": copy.deepcopy(preview_copy.get("session_counts") or {}),
                "selected_ids": list(preview_copy.get("selected_ids") or []),
                "picked_meta": copy.deepcopy(preview_copy.get("picked_meta") or {}),
            }

        picker = SessionPicker(
            cfg,
            _ADDON_DIR,
            branch_scope=branch_scope_copy,
            snapshot=preview_snapshot,
            col=col,
            topic_classifier=topic_classifier,
            profile=profile,
        )
        if not preview_copy:
            picker.pick_until(cfg.session_card_count)

        selected_ids = list(picker.selected_ids)
        _emit_diagnostic_event(
            "incremento_session_phase",
            phase="selection_finished",
            selected_count=len(selected_ids),
        )
        picked_meta = copy.deepcopy(picker.picked_meta)
        session_time_snapshot = copy.deepcopy(
            (preview_copy or {}).get("session_time", picker.stats.session_time)
        )
        return _SessionSelectionOperationResult(
            picker=picker,
            stats=picker.stats,
            selected_ids=selected_ids,
            picked_meta=picked_meta,
            session_time_snapshot=session_time_snapshot,
        )

    def _build_session_deck(
        col,
        selection: _SessionSelectionOperationResult,
    ) -> _SessionBuildOperationResult:
        selected_ids = list(selection.selected_ids)
        _emit_diagnostic_event(
            "incremento_session_phase",
            phase="deck_build_started",
            selected_count=len(selected_ids),
        )
        deck_result = _prepare_filtered_review_deck(
            selected_ids,
            deck_name=session_deck_name,
            preserve_order=bool(cfg.preserve_order),
            select_deck=True,
            col=col,
            return_result=True,
        )
        _emit_diagnostic_event(
            "incremento_session_phase",
            phase="deck_build_finished",
            selected_count=len(selected_ids),
        )
        return _SessionBuildOperationResult(
            changes=deck_result.changes,
            picker=selection.picker,
            stats=selection.stats,
            selected_ids=selected_ids,
            picked_meta=copy.deepcopy(selection.picked_meta),
            session_time_snapshot=copy.deepcopy(selection.session_time_snapshot),
            deck_id=deck_result.deck_id,
        )

    def _activate_if_current(result: _SessionBuildOperationResult) -> None:
        if not _is_current_session_launch(launch_token, profile):
            return
        _activate_incremento_session(
            result,
            cfg=cfg,
            branch_scope=branch_scope_copy,
            session_deck_name=session_deck_name,
        )

    def _build_success(result: _SessionBuildOperationResult) -> None:
        if not _is_current_session_launch(launch_token, profile):
            return
        _emit_diagnostic_event(
            "incremento_session_build_succeeded",
            selected_count=len(result.selected_ids),
            auto_refill=bool(getattr(cfg, "auto_refill_session", False)),
        )
        _emit_diagnostic_event(
            "incremento_session_phase",
            phase="activation_scheduled",
            selected_count=len(result.selected_ids),
        )
        # The no-progress mutation helper dispatches normal collection-change
        # hooks immediately after this success callback. Enter review after
        # those hooks and native UI teardown have had time to settle.
        _defer_profile_ui_action(
            profile,
            lambda: _activate_if_current(result),
        )

    def _show_failure_if_current(exc: Exception) -> None:
        if not _is_current_session_launch(launch_token, profile):
            return
        showInfo(f"Could not start the Incremento session:\n\n{exc}")

    def _failure(exc: Exception) -> None:
        _emit_diagnostic_event(
            "incremento_session_build_failed",
            error_type=type(exc).__name__,
        )
        _defer_profile_ui_action(
            profile,
            lambda: _show_failure_if_current(exc),
        )

    def _selection_success(selection: _SessionSelectionOperationResult) -> None:
        if not _is_current_session_launch(launch_token, profile):
            return
        if not selection.selected_ids:
            _build_success(
                _SessionBuildOperationResult(
                    changes=_empty_op_changes(),
                    picker=selection.picker,
                    stats=selection.stats,
                    selected_ids=[],
                    picked_meta=copy.deepcopy(selection.picked_meta),
                    session_time_snapshot=copy.deepcopy(
                        selection.session_time_snapshot
                    ),
                    deck_id=None,
                )
            )
            return

        def _build(col) -> _SessionBuildOperationResult:
            return _build_session_deck(col, selection)

        try:
            _run_collection_mutation_without_progress(
                parent=mw,
                op=_build,
                success=_build_success,
                failure=_failure,
                initiator=_build,
            )
        except Exception as exc:
            _failure(exc)

    try:
        _run_collection_query(
            parent=mw,
            op=_select_session,
            success=_selection_success,
            failure=_failure,
        )
    except Exception as exc:
        _failure(exc)
