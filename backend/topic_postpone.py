from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

from aqt import mw

try:
    from .db import get_connection
except ImportError:
    from db import get_connection

TOPIC_POSTPONE_EASE = 4
_DEFAULT_TOPIC_POSTPONE_ENABLED = False
_DEFAULT_TOPIC_POSTPONE_MODE: Literal["timed", "session"] = "timed"
_DEFAULT_TOPIC_POSTPONE_MINUTES = 30
_MIN_TOPIC_POSTPONE_MINUTES = 1
_MAX_TOPIC_POSTPONE_MINUTES = 24 * 60
_session_postponed_card_ids: set[int] = set()
_ADDON_DIR = str(Path(__file__).resolve().parent.parent)


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        return mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        return {}


def _db():
    return get_connection(_ADDON_DIR)


def configured_topic_postpone_enabled(config: dict | None = None) -> bool:
    cfg = _resolved_config(config)
    return bool(cfg.get("topic_postpone_enabled", _DEFAULT_TOPIC_POSTPONE_ENABLED))


def configured_topic_postpone_mode(
    config: dict | None = None,
) -> Literal["timed", "session"]:
    cfg = _resolved_config(config)
    raw = str(cfg.get("topic_postpone_mode", _DEFAULT_TOPIC_POSTPONE_MODE) or "").strip().lower()
    return "session" if raw == "session" else "timed"


def configured_topic_postpone_minutes(config: dict | None = None) -> int:
    cfg = _resolved_config(config)
    try:
        value = int(cfg.get("topic_postpone_minutes", _DEFAULT_TOPIC_POSTPONE_MINUTES))
    except Exception:
        value = _DEFAULT_TOPIC_POSTPONE_MINUTES
    return max(_MIN_TOPIC_POSTPONE_MINUTES, min(_MAX_TOPIC_POSTPONE_MINUTES, value))


def topic_postpone_due_label(config: dict | None = None) -> str:
    mode = configured_topic_postpone_mode(config)
    if mode == "session":
        return "Session"
    return f"{configured_topic_postpone_minutes(config)}m"


def _normalize_mode(mode: str | None) -> Literal["timed", "session"]:
    return "session" if str(mode or "").strip().lower() == "session" else "timed"


def _bury_card_ids(card_ids: list[int]) -> None:
    if not card_ids:
        return
    try:
        mw.col.sched.bury_cards(card_ids)
    except Exception:
        pass


def _unbury_card_ids(card_ids: list[int]) -> None:
    if not card_ids:
        return
    try:
        mw.col.sched.unbury_cards(card_ids)
    except Exception:
        pass


def postpone_topic_card(
    card,
    *,
    mode: str | None = None,
    minutes: int | None = None,
    now: float | None = None,
    bury: bool = True,
) -> Literal["timed", "session"]:
    resolved_mode = _normalize_mode(
        mode if mode is not None else configured_topic_postpone_mode()
    )
    if resolved_mode == "session":
        postpone_topic_card_for_session(card, bury=bury)
        return "session"
    store_timed_topic_postpone(card, minutes=minutes, now=now, bury=bury)
    return "timed"


def postpone_topic_card_for_session(card, *, bury: bool = True) -> None:
    if card is None:
        return
    try:
        _session_postponed_card_ids.add(int(card.id))
    except Exception:
        return
    if bury:
        _bury_card_ids([int(card.id)])


def has_session_postponed_cards() -> bool:
    return bool(_session_postponed_card_ids)


def release_session_postponed_cards() -> list[int]:
    card_ids = sorted(_session_postponed_card_ids)
    _session_postponed_card_ids.clear()
    _unbury_card_ids(card_ids)
    return card_ids


def store_timed_topic_postpone(
    card,
    *,
    minutes: int | None = None,
    now: float | None = None,
    bury: bool = True,
) -> int | None:
    if card is None:
        return None
    try:
        card_id = int(card.id)
    except Exception:
        return None

    resolved_minutes = (
        configured_topic_postpone_minutes()
        if minutes is None
        else max(_MIN_TOPIC_POSTPONE_MINUTES, min(_MAX_TOPIC_POSTPONE_MINUTES, int(minutes)))
    )
    until_ts = int((time.time() if now is None else float(now)) + (resolved_minutes * 60))
    try:
        conn = _db()
        conn.execute(
            "INSERT OR REPLACE INTO topic_postpones (card_id, until_ts) VALUES (?, ?)",
            (card_id, until_ts),
        )
        conn.commit()
    except Exception:
        return None
    if bury:
        _bury_card_ids([card_id])
    return until_ts


def release_expired_timed_postpones(
    now: float | None = None,
    *,
    unbury: bool = True,
) -> list[int]:
    now_ts = int(time.time() if now is None else float(now))
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT card_id FROM topic_postpones WHERE until_ts <= ? ORDER BY until_ts, card_id",
            (now_ts,),
        ).fetchall()
    except Exception:
        return []

    restored_ids = [int(row[0]) for row in rows]
    if not restored_ids:
        return []

    try:
        conn.executemany(
            "DELETE FROM topic_postpones WHERE card_id = ?",
            [(card_id,) for card_id in restored_ids],
        )
        conn.commit()
    except Exception:
        return []

    if unbury:
        _unbury_card_ids(restored_ids)
    return restored_ids


def next_timed_postpone_at(now: float | None = None) -> int | None:
    now_ts = int(time.time() if now is None else float(now))
    try:
        row = _db().execute(
            "SELECT MIN(until_ts) FROM topic_postpones WHERE until_ts > ?",
            (now_ts,),
        ).fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    try:
        return int(row[0])
    except Exception:
        return None
