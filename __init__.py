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

_stats = StatsManager(os.path.dirname(__file__))


INCREMENTO_DECK = "Incremento Session"


def learnFunction() -> None:
    config = mw.addonManager.getConfig(__name__) or {}
    scope = config.get("scheduler_scope", "session")
    target_count = config.get("session_card_count", 50)



    # Collect up to target_count unique card IDs via scheduler
    selected_ids: list[CardId] = []
    added_to_filtered: set[CardId] = set()

    for _ in range(target_count * 3):
        counts = _stats.counts_for(scope)
        if len(selected_ids) >= target_count:
            break
        result = get_card_from_scheduler(counts=counts, topics_rate=0.9, random_rate=0.99, exclude_ids=added_to_filtered)
        if result.card is None:
            break
        counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
        counts["mode"][result.mode] = counts["mode"].get(result.mode, 0) + 1
        if result.tag:
            counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1

        _stats.record(result, scope)
        added_to_filtered.add(result.card)
        selected_ids.append(result.card)

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
