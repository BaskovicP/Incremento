"""
session.py — learnFunction and session-scope statistics state.

Owns the in-memory session counts and the full card-picking / filtered-deck
creation logic that was previously inline in __init__.py.

Public API:
    INCREMENTO_DECK       — filtered deck name constant
    learnFunction()       — main entry point; shows config dialog and starts review
    reset_session_counts() — clear in-memory session counts
    get_session_counts()  — return a copy of the current session counts
"""

import copy
import os
import time
import types

from aqt import mw, gui_hooks
from aqt.utils import showInfo
from aqt.qt import QDialog, QVBoxLayout, QTextEdit, QPushButton

from .scheduler import NO_TAGS_KEY
from .statistics import StatsManager, _empty_time
from .session_selection import select_session_cards
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

# Most-recent session counts — updated after each learnFunction picking loop.
# Accessed via get_session_counts() from __init__.py for the stats dialog.
_session_counts: dict = {"type": {}, "tags": {}, "mode": {}}
_session_times: dict = _empty_time()


def reset_session_counts() -> None:
    global _session_counts, _session_times
    _session_counts = {"type": {}, "tags": {}, "mode": {}}
    _session_times = _empty_time()


def get_session_counts() -> dict:
    """Return the last session's counts (live reference — do not mutate)."""
    return _session_counts


def get_session_times() -> dict:
    """Return review-time stats for the last/active session."""
    return _session_times


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
        stats = StatsManager(_ADDON_DIR, _active_profile(), day_end_time=cfg.day_end_time)
        selected_ids = preview_override.get("selected_ids", [])
        _picked_meta: dict[int, dict] = preview_override.get("picked_meta", {})
        session_counts_snapshot = preview_override.get("session_counts", {"type": {}, "tags": {}, "mode": {}})
        session_time_snapshot = preview_override.get("session_time", {"type": {}, "tags": {}})
    else:
        selection = select_session_cards(cfg, _ADDON_DIR, branch_scope=branch_scope)
        stats = selection.stats
        selected_ids = selection.selected_ids
        # Metadata stored at pick-time; daily/lifetime are recorded on actual review.
        _picked_meta = selection.picked_meta
        session_counts_snapshot = stats.session
        session_time_snapshot = stats.session_time

    # Snapshot session counts so the statistics dialog can show them later.
    global _session_counts, _session_times
    _session_counts = copy.deepcopy(session_counts_snapshot)
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

    search = " OR ".join(f"cid:{cid}" for cid in selected_ids)

    # Get or create the filtered deck
    existing = mw.col.decks.by_name(INCREMENTO_DECK)
    if existing:
        if not existing.get("dyn"):
            showInfo(
                f"'{INCREMENTO_DECK}' is a normal deck. Delete or rename it first."
            )
            return
        did = existing["id"]
        mw.col.sched.empty_filtered_deck(did)
    else:
        did = mw.col.decks.new_filtered(INCREMENTO_DECK)

    # Configure via protobuf API (Anki 2.1.45+)
    fdu = mw.col.sched.get_or_create_filtered_deck(did)
    fdu.config.reschedule = True
    del fdu.config.search_terms[:]
    # Always a single SearchTerm — Anki only processes the first 2 SearchTerms
    # so N-per-card terms silently truncate. order=0 when preserving order
    # (due values get stamped post-rebuild anyway); order=1 (RANDOM) otherwise.
    fdu.config.search_terms.add(
        search=search,
        limit=len(selected_ids),
        order=0 if cfg.preserve_order else 1,
    )
    op = mw.col.sched.add_or_update_filtered_deck(fdu)

    mw.col.sched.rebuild_filtered_deck(op.id)

    if cfg.preserve_order:
        # odue is already saved by rebuild — original scheduling is safe.
        # Stamp due = position so the scheduler presents cards in selected_ids order.
        for i, cid in enumerate(selected_ids):
            card = mw.col.get_card(cid)
            card.due = i
            mw.col.update_card(card)
    mw.col.decks.select(op.id)

    # Hook: record each card to daily/lifetime the first time it is answered.
    # This ensures only actually reviewed cards count — not just scheduled ones.
    _reviewed_ids: set[int] = set()
    _question_started_at: dict[int, float] = {}
    _measured_review_seconds: dict[int, float] = {}
    _last_shown_cid: int | None = None

    def _on_card_shown(card) -> None:
        nonlocal _last_shown_cid
        try:
            _last_shown_cid = card.id
            _question_started_at[card.id] = time.monotonic()
        except Exception:
            pass

    def _on_answer_shown(card) -> None:
        """Freeze duration at answer reveal (question -> answer shown)."""
        try:
            cid = card.id
            if cid in _measured_review_seconds:
                return
            started = _question_started_at.get(cid)
            if started is None:
                return
            _measured_review_seconds[cid] = max(0.0, time.monotonic() - started)
        except Exception:
            pass

    def _on_card_answered(reviewer, card, ease: int) -> None:
        global _session_times
        try:
            cid = card.id
            if cid not in _picked_meta or cid in _reviewed_ids:
                return
            _reviewed_ids.add(cid)
            meta = _picked_meta[cid]
            # NO_TAGS_KEY is a synthetic key for debt tracking — don't persist it.
            tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
            fake = types.SimpleNamespace(
                card=cid,
                card_type=meta["card_type"],
                tag=tag,
                mode=meta["mode"],
                review_seconds=_review_seconds(
                    reviewer,
                    card,
                    measured_seconds=_measured_review_seconds.pop(cid, None),
                ),
            )
            stats.record(fake, cfg.scheduler_scope)
            _session_times = copy.deepcopy(stats.session_time)
            _question_started_at.pop(cid, None)
        except Exception as e:
            print(f"[Incremento] _on_card_answered error: {e}")

    gui_hooks.reviewer_did_show_question.append(_on_card_shown)
    gui_hooks.reviewer_did_show_answer.append(_on_answer_shown)
    gui_hooks.reviewer_did_answer_card.append(_on_card_answered)

    _session_closed = False

    def _flush_unanswered_time() -> None:
        global _session_times
        nonlocal _session_closed
        if _session_closed:
            return
        _session_closed = True

        # If user exits while looking at a question and no answer was shown,
        # freeze elapsed time for that card at exit.
        cid = None
        try:
            cur = getattr(getattr(mw, "reviewer", None), "card", None)
            if cur is not None:
                cid = cur.id
            if cid is None:
                cid = _last_shown_cid
            if cid is None and _question_started_at:
                # Last fallback when reviewer.card is already cleared.
                cid = next(reversed(_question_started_at))
            if cid is not None and cid not in _measured_review_seconds:
                started = _question_started_at.get(cid)
                if started is not None:
                    _measured_review_seconds[cid] = max(0.0, time.monotonic() - started)
        except Exception:
            pass

        # Freeze any remaining in-flight cards as a final fallback.
        now = time.monotonic()
        for pending_cid, started in list(_question_started_at.items()):
            if pending_cid not in _measured_review_seconds:
                _measured_review_seconds[pending_cid] = max(0.0, now - started)

        # Persist elapsed time for any unreviewed picked cards as time-only.
        try:
            for pending_cid, seconds in list(_measured_review_seconds.items()):
                if pending_cid in _reviewed_ids:
                    continue
                if pending_cid not in _picked_meta:
                    continue
                meta = _picked_meta[pending_cid]
                tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
                fake = types.SimpleNamespace(
                    card=pending_cid,
                    card_type=meta["card_type"],
                    tag=tag,
                    mode=meta["mode"],
                )
                stats.record_time_only(fake, seconds)

            _session_times = copy.deepcopy(stats.session_time)
        except Exception as e:
            print(f"[Incremento] _on_reviewer_end time-only stats error: {e}")

    # One-shot hooks: clean up when reviewer is left.
    def _on_reviewer_end() -> None:
        _flush_unanswered_time()

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

    def _on_state_did_change(new_state: str, old_state: str) -> None:
        if old_state == "review" and new_state != "review":
            _on_reviewer_end()

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    gui_hooks.state_did_change.append(_on_state_did_change)
    mw.moveToState("review")
