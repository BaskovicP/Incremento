from __future__ import annotations

import time
from pathlib import Path

from aqt import mw

try:
    from .config_service import load_addon_config
    from .db import get_connection
    from .paths import get_active_profile as _active_profile
except ImportError:
    from config_service import load_addon_config  # type: ignore
    from db import get_connection  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

_DEFAULT_ITEM_SKIP_ENABLED = False
_DEFAULT_ITEM_SKIP_MINUTES = 30
_MIN_ITEM_SKIP_MINUTES = 1
_MAX_ITEM_SKIP_MINUTES = 24 * 60
_ADDON_DIR = str(Path(__file__).resolve().parent.parent)


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        return load_addon_config(mw.addonManager, addon_name)
    except Exception:
        return {}


def _db():
    return get_connection(_ADDON_DIR, _active_profile())


def configured_item_skip_enabled(config: dict | None = None) -> bool:
    cfg = _resolved_config(config)
    return bool(cfg.get("item_skip_enabled", _DEFAULT_ITEM_SKIP_ENABLED))


def configured_item_skip_minutes(config: dict | None = None) -> int:
    cfg = _resolved_config(config)
    try:
        value = int(cfg.get("item_skip_minutes", _DEFAULT_ITEM_SKIP_MINUTES))
    except Exception:
        value = _DEFAULT_ITEM_SKIP_MINUTES
    return max(_MIN_ITEM_SKIP_MINUTES, min(_MAX_ITEM_SKIP_MINUTES, value))


def item_skip_due_label(config: dict | None = None) -> str:
    return f"{configured_item_skip_minutes(config)}m"


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


def store_timed_item_skip(
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
        configured_item_skip_minutes()
        if minutes is None
        else max(_MIN_ITEM_SKIP_MINUTES, min(_MAX_ITEM_SKIP_MINUTES, int(minutes)))
    )
    until_ts = int((time.time() if now is None else float(now)) + (resolved_minutes * 60))
    try:
        conn = _db()
        conn.execute(
            "INSERT OR REPLACE INTO item_postpones (card_id, until_ts) VALUES (?, ?)",
            (card_id, until_ts),
        )
        conn.commit()
    except Exception:
        return None
    if bury:
        _bury_card_ids([card_id])
    return until_ts


def release_expired_timed_item_skips(
    now: float | None = None,
    *,
    unbury: bool = True,
) -> list[int]:
    now_ts = int(time.time() if now is None else float(now))
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT card_id FROM item_postpones WHERE until_ts <= ? ORDER BY until_ts, card_id",
            (now_ts,),
        ).fetchall()
    except Exception:
        return []

    restored_ids = [int(row[0]) for row in rows]
    if not restored_ids:
        return []

    try:
        conn.executemany(
            "DELETE FROM item_postpones WHERE card_id = ?",
            [(card_id,) for card_id in restored_ids],
        )
        conn.commit()
    except Exception:
        return []

    if unbury:
        _unbury_card_ids(restored_ids)
    return restored_ids


def next_timed_item_skip_at(now: float | None = None) -> int | None:
    now_ts = int(time.time() if now is None else float(now))
    try:
        row = _db().execute(
            "SELECT MIN(until_ts) FROM item_postpones WHERE until_ts > ?",
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
