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
from .session_selection import SessionPicker
from .paths import get_active_profile as _active_profile
from .topic_scheduler import resolve_topic_card_classifier
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


@dataclass
class _FilteredDeckBuildResult:
    deck_id: int | None
    changes: object


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


def _defer_collection_ui_action(callback) -> None:
    """Run UI work after CollectionOp hooks and its modal progress UI settle."""
    progress = getattr(mw, "progress", None)
    single_shot = getattr(progress, "single_shot", None)
    if callable(single_shot):
        single_shot(0, callback, True)
        return
    QTimer.singleShot(0, callback)


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
    def _result(live_ids: list[int], new_ids: list[int], changes=None):
        if return_result:
            return _RefillOperationResult(
                changes=changes if changes is not None else _empty_op_changes(),
                live_queue_ids=list(live_ids),
                new_ids=list(new_ids),
            )
        return {"live_queue_ids": list(live_ids), "new_ids": list(new_ids)}

    if not state.auto_refill_enabled:
        return _result([], []) if return_result else None
    if state.session_closed:
        return _result([], [])

    deck_id = _session_deck_id_by_name(
        state.session_deck_name,
        **_optional_col_kwargs(col),
    )
    if deck_id is None:
        return _result([], []) if return_result else None

    fetch_limit = _live_queue_fetch_limit(state)
    live_queue_ids = _live_filtered_queue_ids(
        deck_id,
        fetch_limit=fetch_limit,
        scheduled_ids=set(state.selected_ids),
        **_optional_col_kwargs(col),
    )
    if _has_duplicate_ordered_ids(live_queue_ids):
        return _result(live_queue_ids, [])

    # Answered new cards often remain in Anki's queue as learning/relearning
    # repeats. Keep them in the filtered deck, but do not let them occupy the
    # live window reserved for not-yet-answered session cards.
    unreviewed_live_queue_ids = _unreviewed_live_queue_ids(
        live_queue_ids,
        state.reviewed_ids,
    )
    if len(unreviewed_live_queue_ids) >= state.window_size:
        return _result(live_queue_ids, [])

    missing = state.window_size - len(unreviewed_live_queue_ids)
    picker_snapshot = _snapshot_picker_state(state.picker)
    new_ids = state.picker.pick_until(len(state.picker.selected_ids) + missing)
    if not new_ids:
        return _result(live_queue_ids, [])
    if state.session_closed:
        _restore_picker_state(state.picker, picker_snapshot)
        return _result(live_queue_ids, [])
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
    return _result(live_queue_ids, new_ids, changes)


def _schedule_deferred_auto_refill(
    state: _ActiveIncrementoSessionState,
    *,
    reason: str,
) -> None:
    if not state.auto_refill_enabled or state.session_closed or state.refill_retry_pending:
        return
    state.refill_retry_pending = True

    def _run() -> None:
        if state.session_closed:
            state.refill_retry_pending = False
            return

        def _op(col):
            return _maybe_auto_refill_active_session(
                state,
                col=col,
                return_result=True,
            )

        def _success(result) -> None:
            state.refill_retry_pending = False
            if bool(getattr(state.cfg, "show_debug", False)):
                print(f"[Incremento] deferred auto-refill ({reason}): {result}")

        def _failure(exc: Exception) -> None:
            state.refill_retry_pending = False
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
    try:
        original_next = reviewer.nextCard
        instance_dict = getattr(reviewer, "__dict__", {})
        had_instance_override = "nextCard" in instance_dict
        previous_instance_value = instance_dict.get("nextCard")
    except Exception:
        return False

    def _restore() -> None:
        try:
            if had_instance_override:
                reviewer.nextCard = previous_instance_value
            else:
                delattr(reviewer, "nextCard")
        except Exception:
            try:
                reviewer.nextCard = original_next
            except Exception:
                pass

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
        _restore()
        QTimer.singleShot(0, _wait_then_continue)

    try:
        reviewer.nextCard = _deferred_next
    except Exception:
        return False
    return True


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


def _show_scheduled_debug(
    selected_ids: list[int],
    picked_meta: dict[int, dict],
    branch_scope: dict | None,
) -> None:
    debug_dlg = QDialog(mw)
    branch_title = str((branch_scope or {}).get("root_title") or "").strip()
    debug_title = f"DEBUG — Scheduled order ({len(selected_ids)} cards)"
    if branch_title:
        debug_title += f" — {branch_title}"
    debug_dlg.setWindowTitle(debug_title)
    debug_dlg.resize(700, 500)
    debug_layout = QVBoxLayout(debug_dlg)
    debug_txt = QTextEdit()
    debug_txt.setReadOnly(True)
    debug_txt.setFontFamily("Courier")
    debug_lines = ["#    type     mode       tag                  first field", "-" * 80]
    for index, card_id in enumerate(selected_ids):
        meta = picked_meta.get(card_id, {})
        card = mw.col.get_card(card_id)
        note = mw.col.get_note(card.nid)
        first_field = note.fields[0][:55].replace("\n", " ") if note.fields else str(card_id)
        debug_lines.append(
            f"{index + 1:3}.  {meta.get('card_type', '?'):7}  {meta.get('mode', '?'):9}  "
            f"{(meta.get('tag') or 'no-tag'):20} {first_field}"
        )
    debug_txt.setPlainText("\n".join(debug_lines))
    debug_layout.addWidget(debug_txt)
    debug_btn = QPushButton("Continue")
    debug_btn.clicked.connect(debug_dlg.accept)
    debug_layout.addWidget(debug_btn)
    debug_dlg.exec()


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
            print(f"[Incremento] _on_card_answered error: {e}")
        if state.auto_refill_enabled:
            if _defer_next_card_until_refill_finishes(state, reviewer):
                _schedule_deferred_auto_refill(state, reason="card-answered")
            else:
                print("[Incremento] auto-refill skipped: reviewer advance could not be deferred")

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

        # Anki already returns completed cards to their home decks and keeps
        # unfinished learning/relearning cards in the filtered deck. Rebuilding
        # here would perform collection work inside reviewer_will_end, block the
        # UI, and race any auto-refill operation still finishing in the
        # background. Leave Anki's live filtered-deck queue untouched.
        if _active_incremento_session_state is state:
            _active_incremento_session_state = None

    def _on_state_did_change(new_state: str, old_state: str) -> None:
        if old_state == "review" and new_state != "review":
            _on_reviewer_end()

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.state_did_change.append(_on_state_did_change)
    mw.moveToState("review")


def learnFunction(*, branch_scope: dict | None = None) -> None:
    """Configure and start an Incremento session without blocking Anki's UI."""
    try:
        release_expired_timed_postpones()
    except Exception:
        pass

    dlg = SchedulerConfigDialog(
        mw,
        on_clear_session=reset_session_counts,
        branch_scope=branch_scope,
    )
    if not dlg.exec():
        return

    dlg.save_config()
    addon_config = mw.addonManager.getConfig(_ADDON_PKG) or {}
    cfg = dlg.to_config()
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
    topic_classifier = resolve_topic_card_classifier(
        copy.deepcopy(addon_config),
        scheduler_config=cfg,
    )

    def _build_session(col) -> _SessionBuildOperationResult:
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
        picked_meta = copy.deepcopy(picker.picked_meta)
        session_time_snapshot = copy.deepcopy(
            (preview_copy or {}).get("session_time", picker.stats.session_time)
        )
        if not selected_ids:
            return _SessionBuildOperationResult(
                changes=_empty_op_changes(),
                picker=picker,
                stats=picker.stats,
                selected_ids=[],
                picked_meta=picked_meta,
                session_time_snapshot=session_time_snapshot,
                deck_id=None,
            )

        deck_result = _prepare_filtered_review_deck(
            selected_ids,
            deck_name=session_deck_name,
            preserve_order=bool(cfg.preserve_order),
            select_deck=True,
            col=col,
            return_result=True,
        )
        return _SessionBuildOperationResult(
            changes=deck_result.changes,
            picker=picker,
            stats=picker.stats,
            selected_ids=selected_ids,
            picked_meta=picked_meta,
            session_time_snapshot=session_time_snapshot,
            deck_id=deck_result.deck_id,
        )

    def _success(result: _SessionBuildOperationResult) -> None:
        # CollectionOp invokes success before dispatching its change hooks, and
        # its application-modal progress window may remain alive briefly. Wait
        # for both before entering review so Anki's main window cannot remain
        # blocked behind a hidden progress dialog.
        _defer_collection_ui_action(
            lambda: _activate_incremento_session(
                result,
                cfg=cfg,
                branch_scope=branch_scope_copy,
                session_deck_name=session_deck_name,
            ),
        )

    def _failure(exc: Exception) -> None:
        _defer_collection_ui_action(
            lambda: showInfo(f"Could not start the Incremento session:\n\n{exc}")
        )

    _run_collection_operation(
        parent=mw,
        op=_build_session,
        success=_success,
        failure=_failure,
    )
