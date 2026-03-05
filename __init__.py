import os
import sys

from aqt import mw
from aqt.utils import showInfo
from aqt.qt import QAction, qconnect

# Allow utils/scheduler.py to do `import cards` as a plain import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from .utils.scheduler import get_card_from_scheduler
from .utils.statistics import StatsManager

_stats = StatsManager(os.path.dirname(__file__))


def learnFunction() -> None:
    config = mw.addonManager.getConfig(__name__) or {}
    scope = config.get("scheduler_scope", "session")

    counts = _stats.counts_for(scope)
    result = get_card_from_scheduler(counts=counts)
    _stats.record(result, scope)

    if result.card is None:
        showInfo("No cards available to study right now.")
        return

    card = mw.col.get_card(result.card)
    note = card.note()
    question = note.fields[0][:120].strip()

    msg = (
        f"Card:  {question}\n\n"
        f"Type: {result.card_type}  Tag: {result.tag or '—'}  Mode: {result.mode}\n"
        f"Scope: {scope}\n\n"
        f"Session   type={_stats.session['type']}  tags={_stats.session['tags']}  mode={_stats.session['mode']}\n"
        f"Daily     type={_stats.daily['type']}  tags={_stats.daily['tags']}  mode={_stats.daily['mode']}\n"
        f"Lifetime  type={_stats.lifetime['type']}  tags={_stats.lifetime['tags']}  mode={_stats.lifetime['mode']}\n"
    )
    showInfo(msg)


learnAction = QAction("Start Incremental Learning", mw)
qconnect(learnAction.triggered, learnFunction)
mw.form.menuTools.addAction(learnAction)
