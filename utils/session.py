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
import types

from aqt import mw, gui_hooks
from aqt.utils import showInfo
from aqt.qt import QDialog, QVBoxLayout, QTextEdit, QPushButton, Qt

from .scheduler import get_card_from_scheduler, NO_TAGS_KEY
from .statistics import StatsManager
from .learn_dialog import SchedulerConfigDialog
from .scheduler_config import load_scheduler_config

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_ADDON_PKG = __name__.split(".")[0]  # "incremento"

INCREMENTO_DECK = "Incremento Session"

# Most-recent session counts — updated after each learnFunction picking loop.
# Accessed via get_session_counts() from __init__.py for the stats dialog.
_session_counts: dict = {"type": {}, "tags": {}, "mode": {}}


def reset_session_counts() -> None:
    global _session_counts
    _session_counts = {"type": {}, "tags": {}, "mode": {}}


def get_session_counts() -> dict:
    """Return the last session's counts (live reference — do not mutate)."""
    return _session_counts


def learnFunction() -> None:
    config = mw.addonManager.getConfig(_ADDON_PKG) or {}

    dlg = SchedulerConfigDialog(mw, on_clear_session=reset_session_counts)
    if not dlg.exec():
        return

    dlg.save_config()
    cfg = dlg.to_config()
    target_count = cfg.session_card_count

    stats = StatsManager(_ADDON_DIR, day_end_time=cfg.day_end_time)

    selected_ids = []
    added_to_filtered = set()
    # Metadata stored at pick-time; daily/lifetime are recorded on actual review.
    _picked_meta: dict[int, dict] = {}

    def _pick(use_tags: bool, tag_weights: dict,
              force_card_type=None, force_mode=None) -> bool:
        """Attempt one card pick. Returns False when no card is available."""
        counts = stats.counts_for(cfg.scheduler_scope)
        result = get_card_from_scheduler(
            counts=counts,
            topics_rate=cfg.topics_rate,
            random_rate=cfg.random_rate,
            use_tags=use_tags,
            tag_weights=tag_weights,
            exclude_ids=added_to_filtered,
            force_card_type=force_card_type,
            force_mode=force_mode,
            topics_filter=cfg.topics_filter,
            items_filter=cfg.items_filter,
            ready_filter=cfg.ready_filter,
            pdf_rate=cfg.pdf_rate,
        )
        if result.card is None:
            return False
        counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
        counts["mode"][result.mode] = counts["mode"].get(result.mode, 0) + 1
        if result.tag:
            counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1
        # Do NOT call stats.record() here — that would write picks to daily/lifetime.
        # Recording to daily/lifetime is deferred to the reviewer_did_answer_card hook
        # so that only actually reviewed cards count toward those scopes.
        _picked_meta[result.card] = {
            "card_type": result.card_type,
            "tag":       result.tag,
            "mode":      result.mode,
        }
        added_to_filtered.add(result.card)
        selected_ids.append(result.card)
        return True

    if cfg.enforce_priority:
        # Hard mode — Phase 1 exhausts the leading dimension's quota sequentially.
        p1 = cfg.priority_order[0] if cfg.priority_order else "tags"

        if p1 == "tags" and cfg.use_tags:
            ordered = sorted(cfg.tag_weights.items(), key=lambda x: x[1], reverse=True)
            for tag, weight in ordered:
                tag_target = round(weight * target_count)
                tag_picked = 0
                for _ in range(tag_target * 3):
                    if tag_picked >= tag_target or len(selected_ids) >= target_count:
                        break
                    if not _pick(use_tags=True, tag_weights={tag: 1.0}):
                        break
                    tag_picked += 1

        elif p1 == "type":
            topics_target = round(cfg.topics_rate * target_count)
            items_target = target_count - topics_target
            for forced_type, type_target in [("topics", topics_target), ("items", items_target)]:
                type_picked = 0
                for _ in range(type_target * 3):
                    if type_picked >= type_target or len(selected_ids) >= target_count:
                        break
                    if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights,
                                 force_card_type=forced_type):
                        break
                    type_picked += 1

        elif p1 == "mode":
            priority_target = round((1 - cfg.random_rate) * target_count)
            random_target = target_count - priority_target
            for forced_mode, mode_target in [("priority", priority_target), ("random", random_target)]:
                mode_picked = 0
                for _ in range(mode_target * 3):
                    if mode_picked >= mode_target or len(selected_ids) >= target_count:
                        break
                    if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights,
                                 force_mode=forced_mode):
                        break
                    mode_picked += 1

        # Phase 2 — fill remaining slots.
        run_phase2 = (cfg.include_rest or not cfg.use_tags) if p1 == "tags" else True
        if run_phase2:
            for _ in range(target_count * 3):
                if len(selected_ids) >= target_count:
                    break
                if not _pick(use_tags=False, tag_weights={}):
                    break

    else:
        # Soft mode — all dimensions handled by soft_pick (debt-based stochastic).
        for _ in range(target_count * 3):
            if len(selected_ids) >= target_count:
                break
            if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights):
                break
        if cfg.use_tags and cfg.include_rest and len(selected_ids) < target_count:
            for _ in range(target_count * 3):
                if len(selected_ids) >= target_count:
                    break
                if not _pick(use_tags=False, tag_weights={}):
                    break

    # Snapshot session counts so the statistics dialog can show them later.
    global _session_counts
    _session_counts = copy.deepcopy(stats.session)

    if not selected_ids:
        showInfo("No cards available to study.")
        return

    # DEBUG: show scheduled card order before building the filtered deck
    if cfg.show_debug:
        _debug_dlg = QDialog(mw)
        _debug_dlg.setWindowTitle(f"DEBUG — Scheduled order ({len(selected_ids)} cards)")
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
            _field = (_note.fields[0][:55].replace("\n", " ")) if _note.fields else str(_cid)
            _debug_lines.append(
                f"{_i+1:3}.  {_meta.get('card_type','?'):7}  {_meta.get('mode','?'):9}  "
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
            showInfo(f"'{INCREMENTO_DECK}' is a normal deck. Delete or rename it first.")
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

    def _on_card_answered(reviewer, card, ease: int) -> None:
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
            )
            stats.record(fake, cfg.scheduler_scope)
        except Exception as e:
            print(f"[Incremento] _on_card_answered error: {e}")

    gui_hooks.reviewer_did_answer_card.append(_on_card_answered)

    # One-shot hook: clean up when the reviewer is left.
    def _on_reviewer_end() -> None:
        gui_hooks.reviewer_will_end.remove(_on_reviewer_end)
        gui_hooks.reviewer_did_answer_card.remove(_on_card_answered)

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    mw.moveToState("review")
