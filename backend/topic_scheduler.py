"""A-factor scheduler for topic cards (SuperMemo SM-15 spec for topics).

Topic cards (those in the Topics deck) are scheduled independently of FSRS
using the SuperMemo A-factor formula:

    next_interval = current_interval × A-factor   (spec: topics)

The ease button does NOT change the current interval — it only shifts the
A-factor to signal how urgently the topic should be reviewed in future:

  Again (1) — reset to 1 day; A-factor unchanged
  Hard  (2) — normal interval; A-factor ×0.9  (important → show sooner)
  Good  (3) — normal interval; A-factor unchanged
  Easy  (4) — normal interval; A-factor ×1.1  (less urgent → grow faster)

A-factor is clamped to [1.1, 100.0].  Default: 3.5.
"""

import os

from aqt import mw

try:
    from .db import get_topic_schedule, set_topic_schedule
    from .scheduler_config import load_scheduler_config
except ImportError:
    from db import get_topic_schedule, set_topic_schedule  # type: ignore
    from scheduler_config import load_scheduler_config  # type: ignore

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_A_MIN = 1.1
_A_MAX = 100.0


def _topics_deck_name() -> str:
    """Parse deck name from the configured topics_filter (e.g. 'deck:Topics')."""
    try:
        tf = (load_scheduler_config().topics_filter or "deck:Topics").strip()
        if tf.lower().startswith("deck:"):
            return tf[5:].strip('"').strip("'")
    except Exception:
        pass
    return "Topics"


def is_topic_card(card) -> bool:
    """Return True if *card* lives in the configured Topics deck.

    Uses card.odid (original deck) when the card is inside a filtered deck,
    so topic cards remain recognised during Incremento review sessions.
    """
    try:
        did = card.odid if card.odid else card.did
        deck = mw.col.decks.get(did)
        if not deck:
            return False
        name = deck["name"]
        target = _topics_deck_name()
        return name == target or name.startswith(target + "::")
    except Exception:
        return False


def _next_interval_and_afactor(
    last_interval: int, a_factor: float, ease: int
) -> tuple[int, float]:
    """Return (new_interval_days, new_a_factor).

    Interval formula matches SuperMemo spec for topics:
        next_interval = current_interval × A-factor

    Ease buttons only affect the A-factor for *future* reviews, not the
    current interval (except Again which resets to 1 day):
      Again (1) — reset to 1 day; A-factor unchanged
      Hard  (2) — normal interval; A-factor ×0.9  (topic is important → show sooner)
      Good  (3) — normal interval; A-factor unchanged
      Easy  (4) — normal interval; A-factor ×1.1  (topic less urgent → grow faster)
    """
    new_interval = max(1, round(last_interval * a_factor))

    if ease == 1:  # Again — reset interval, leave A-factor alone
        return 1, a_factor
    if ease == 2:  # Hard — signal topic is important, tighten future intervals
        return new_interval, max(_A_MIN, round(a_factor * 0.9, 3))
    if ease == 3:  # Good — pure spec formula, no A-factor change
        return new_interval, a_factor
    # Easy — topic less urgent, loosen future intervals
    return new_interval, min(_A_MAX, round(a_factor * 1.1, 3))


def on_topic_card_answered(reviewer, card, ease: int) -> None:
    """Hook: override FSRS scheduling with A-factor for topic cards."""
    if not is_topic_card(card):
        return
    try:
        a_factor, last_interval = get_topic_schedule(_ADDON_DIR, card.id)
        new_interval, new_a = _next_interval_and_afactor(last_interval, a_factor, ease)
        set_topic_schedule(_ADDON_DIR, card.id, new_a, new_interval)
        mw.col.sched.set_due_date([card.id], str(new_interval))
    except Exception as e:
        print(f"[Incremento] A-factor scheduling error: {e}")
