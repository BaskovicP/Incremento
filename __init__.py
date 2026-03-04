import os
import sys

from aqt import mw
from aqt.utils import showInfo
from aqt.qt import QAction, qconnect

# Allow utils/scheduler.py to do `import cards` as a plain import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from .utils.scheduler import get_card_from_scheduler

# Counts persist for the whole Anki session (resets on restart)
_counts = {"type": {}, "tags": {}, "mode": {}}


def learnFunction() -> None:
    result = get_card_from_scheduler(counts=_counts)

    if result.card is None:
        showInfo("No cards available to study right now.")
        return

    card = mw.col.get_card(result.card)
    note = card.note()
    question = note.fields[0][:120].strip()

    msg = (
        f"Card:  {question}\n"
        f"\n"
        f"Type:  {result.card_type}\n"
        f"Tag:   {result.tag or '(none — tag fallback)'}\n"
        f"Mode:  {result.mode}\n"
        f"\n"
        f"Session counts:\n"
        f"  type  {_counts['type']}\n"
        f"  tags  {_counts['tags']}\n"
        f"  mode  {_counts['mode']}\n"
    )
    showInfo(msg)


learnAction = QAction("Start Incremental Learning", mw)
qconnect(learnAction.triggered, learnFunction)
mw.form.menuTools.addAction(learnAction)
