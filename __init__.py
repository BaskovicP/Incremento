import os
import sys

import pydevd_pycharm
pydevd_pycharm.settrace('localhost', port=5678, suspend=False)

from aqt import mw
from aqt.utils import showInfo
from aqt.qt import QAction, QDialog, qconnect
from anki.cards import CardId

# Allow utils/scheduler.py to do `import cards` as a plain import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from .utils.scheduler import get_card_from_scheduler
from .utils.statistics import StatsManager
from .utils.learn_dialog import SchedulerConfigDialog
from .utils.scheduler_config import load_scheduler_config

_stats = StatsManager(os.path.dirname(__file__))


INCREMENTO_DECK = "Incremento Session"


def learnFunction() -> None:
    config = mw.addonManager.getConfig(__name__) or {}
    scope = config.get("scheduler_scope", "session")
    target_count = config.get("session_card_count", 50)

    dlg = SchedulerConfigDialog(mw)
    if not dlg.exec():
        return

    dlg.save_config()
    cfg = dlg.to_config()

    selected_ids: list[CardId] = []
    added_to_filtered: set[CardId] = set()

    def _pick(use_tags: bool, tag_weights: dict,
              force_card_type: str | None = None,
              force_mode: str | None = None) -> bool:
        """Attempt one card pick. Returns False when no card is available."""
        counts = _stats.counts_for(scope)
        result = get_card_from_scheduler(
            counts=counts,
            topics_rate=cfg.topics_rate,
            random_rate=cfg.random_rate,
            use_tags=use_tags,
            tag_weights=tag_weights,
            exclude_ids=added_to_filtered,
            force_card_type=force_card_type,
            force_mode=force_mode,
        )
        if result.card is None:
            return False
        counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
        counts["mode"][result.mode] = counts["mode"].get(result.mode, 0) + 1
        if result.tag:
            counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1
        _stats.record(result, scope)
        added_to_filtered.add(result.card)
        selected_ids.append(result.card)
        return True

    # Phase 1 — enforce the first priority dimension as a hard constraint.
    p1 = cfg.priority_order[0] if cfg.priority_order else "tags"

    if p1 == "tags" and cfg.use_tags:
        # Loop per-tag in descending weight order.
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
        # Loop per-type: topics quota first, then items quota.
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
        # Loop per-mode: priority-ordered cards first, then random.
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

    # Phase 2 — fill remaining slots (ungated for non-tags strategies;
    # gated on include_rest for tags-first).
    run_phase2 = (cfg.include_rest or not cfg.use_tags) if p1 == "tags" else True
    if run_phase2:
        for _ in range(target_count * 3):
            if len(selected_ids) >= target_count:
                break
            if not _pick(use_tags=False, tag_weights={}):
                break

    if not selected_ids:
        showInfo("No cards available to study.")
        return

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
    fdu.config.search_terms.add(search=search, limit=len(selected_ids))
    op = mw.col.sched.add_or_update_filtered_deck(fdu)

    mw.col.sched.rebuild_filtered_deck(op.id)
    mw.col.decks.select(op.id)
    mw.moveToState("review")


learnAction = QAction("Start Incremental Learning", mw)
qconnect(learnAction.triggered, learnFunction)
mw.form.menuTools.addAction(learnAction)
