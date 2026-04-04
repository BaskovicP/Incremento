from __future__ import annotations

import json
import time
from typing import Literal

from aqt import mw

TOPIC_POSTPONE_EASE = 4
_TOPIC_POSTPONE_CUSTOM_KEY = "_incremento_topic_postpone"
_DEFAULT_TOPIC_POSTPONE_ENABLED = False
_DEFAULT_TOPIC_POSTPONE_MODE: Literal["timed", "session"] = "timed"
_DEFAULT_TOPIC_POSTPONE_MINUTES = 30
_MIN_TOPIC_POSTPONE_MINUTES = 1
_MAX_TOPIC_POSTPONE_MINUTES = 24 * 60
_session_postponed_card_ids: set[int] = set()


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        return mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        return {}


def configured_topic_postpone_enabled(config: dict | None = None) -> bool:
    cfg = _resolved_config(config)
    return bool(
        cfg.get("topic_postpone_enabled", _DEFAULT_TOPIC_POSTPONE_ENABLED)
    )


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


def _load_custom_data(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _write_custom_data(card, payload: dict) -> None:
    if payload:
        card.custom_data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    else:
        card.custom_data = ""


def _update_cards(cards: list) -> None:
    if not cards:
        return
    try:
        mw.col.update_cards(cards)
        return
    except Exception:
        pass
    for card in cards:
        try:
            mw.col.update_card(card)
        except Exception:
            pass


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


def _postpone_payload_until(payload) -> int | None:
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("until"))
    except Exception:
        return None


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
    resolved_minutes = (
        configured_topic_postpone_minutes()
        if minutes is None
        else max(_MIN_TOPIC_POSTPONE_MINUTES, min(_MAX_TOPIC_POSTPONE_MINUTES, int(minutes)))
    )
    until_ts = int((time.time() if now is None else float(now)) + (resolved_minutes * 60))
    try:
        payload = _load_custom_data(getattr(card, "custom_data", ""))
        payload[_TOPIC_POSTPONE_CUSTOM_KEY] = {
            "mode": "timed",
            "until": until_ts,
        }
        _write_custom_data(card, payload)
        mw.col.update_card(card)
    except Exception:
        return None
    if bury:
        _bury_card_ids([int(card.id)])
    return until_ts


def release_expired_timed_postpones(now: float | None = None) -> list[int]:
    now_ts = int(time.time() if now is None else float(now))
    try:
        rows = mw.col.db.all(
            "SELECT id, custom_data FROM cards WHERE custom_data LIKE ?",
            f'%"{_TOPIC_POSTPONE_CUSTOM_KEY}"%',
        )
    except Exception:
        return []

    restored_ids: list[int] = []
    changed_cards: list = []
    for card_id, raw in rows:
        payload = _load_custom_data(raw)
        postpone = payload.get(_TOPIC_POSTPONE_CUSTOM_KEY)
        until_ts = _postpone_payload_until(postpone)
        if until_ts is not None and until_ts > now_ts:
            continue
        payload.pop(_TOPIC_POSTPONE_CUSTOM_KEY, None)
        try:
            card = mw.col.get_card(int(card_id))
        except Exception:
            continue
        _write_custom_data(card, payload)
        changed_cards.append(card)
        restored_ids.append(int(card_id))

    _update_cards(changed_cards)
    _unbury_card_ids(restored_ids)
    return restored_ids
