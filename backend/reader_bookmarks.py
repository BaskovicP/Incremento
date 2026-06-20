from __future__ import annotations

import json
import time
import uuid
from typing import Any

try:
    from .db import get_connection
except ImportError:
    from db import get_connection  # type: ignore


READER_TYPES = {"pdf", "epub", "web", "writing", "video"}
BOOKMARK_COMMENT_MAX_LEN = 240


def _reader_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in READER_TYPES:
        raise ValueError(f"Unsupported reader type: {value}")
    return normalized


def _clamp_ratio(value: Any) -> float:
    try:
        ratio = float(value or 0.0)
    except Exception:
        ratio = 0.0
    return max(0.0, min(ratio, 1.0))


def _nonnegative_int(value: Any, *, default: int = 0) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(0, number)


def _nonnegative_float(value: Any) -> float:
    try:
        number = float(value)
    except Exception:
        number = 0.0
    return max(0.0, number)


def _normalize_comment_text(value: Any) -> str:
    return str(value or "").strip()[:BOOKMARK_COMMENT_MAX_LEN]


def normalize_reader_location(reader_type: str, location: dict[str, Any] | None) -> dict[str, Any]:
    kind = _reader_type(reader_type)
    data = dict(location or {})

    if kind == "pdf":
        return {"page": max(1, _nonnegative_int(data.get("page"), default=1))}
    if kind == "epub":
        result = {
            "section_index": _nonnegative_int(data.get("section_index")),
            "scroll_ratio": _clamp_ratio(data.get("scroll_ratio")),
        }
        title = str(data.get("section_title") or "").strip()
        if title:
            result["section_title"] = title[:160]
        return result
    if kind == "web":
        result = {
            "url": str(data.get("url") or "").strip(),
            "scroll_ratio": _clamp_ratio(data.get("scroll_ratio")),
        }
        payload = data.get("bookmark_payload")
        if isinstance(payload, dict):
            result["bookmark_payload"] = payload
        text = str(data.get("text") or "").strip()
        if text:
            result["text"] = text[:240]
        return result
    if kind == "writing":
        return {
            "cursor_position": _nonnegative_int(data.get("cursor_position")),
            "block_number": _nonnegative_int(data.get("block_number")),
            "scroll_ratio": _clamp_ratio(data.get("scroll_ratio")),
        }
    if kind == "video":
        return {"seconds": round(_nonnegative_float(data.get("seconds")), 1)}
    raise ValueError(f"Unsupported reader type: {reader_type}")


def default_reader_bookmark_label(reader_type: str, location: dict[str, Any]) -> str:
    kind = _reader_type(reader_type)
    data = normalize_reader_location(kind, location)

    if kind == "pdf":
        return f"Page {int(data.get('page', 1))}"
    if kind == "epub":
        section = int(data.get("section_index", 0)) + 1
        title = str(data.get("section_title") or "").strip()
        return f"Section {section} - {title}" if title else f"Section {section}"
    if kind == "web":
        url = str(data.get("url") or "").strip()
        text = str(data.get("text") or "").strip()
        if text:
            return text[:48]
        if not url:
            return "Web bookmark"
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            label = f"{parsed.netloc}{parsed.path or ''}".strip("/")
        except Exception:
            label = url
        return (label or url)[:72]
    if kind == "writing":
        return f"Line {int(data.get('block_number', 0)) + 1}"
    if kind == "video":
        seconds = max(0, int(float(data.get("seconds", 0.0) or 0.0)))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"
    return "Bookmark"


def add_reader_bookmark(
    addon_dir: str,
    profile: str,
    card_id: int,
    reader_type: str,
    location: dict[str, Any] | None,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    kind = _reader_type(reader_type)
    normalized = normalize_reader_location(kind, location)
    clean_label = str(label or "").strip() or default_reader_bookmark_label(kind, normalized)
    location_json = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    conn = get_connection(addon_dir, profile)
    existing = conn.execute(
        "SELECT id, card_id, reader_type, label, comment_text, location_json, created_at, updated_at "
        "FROM reader_bookmarks "
        "WHERE card_id = ? AND reader_type = ? AND location_json = ? "
        "ORDER BY created_at, id LIMIT 1",
        (int(card_id), kind, location_json),
    ).fetchone()
    if existing:
        return _bookmark_from_row(kind, existing)

    now = int(time.time())
    bookmark_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO reader_bookmarks "
        "(id, card_id, reader_type, label, comment_text, location_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            bookmark_id,
            int(card_id),
            kind,
            clean_label[:160],
            "",
            location_json,
            now,
            now,
        ),
    )
    conn.commit()
    return {
        "id": bookmark_id,
        "card_id": int(card_id),
        "reader_type": kind,
        "label": clean_label[:160],
        "comment_text": "",
        "location": normalized,
        "created_at": now,
        "updated_at": now,
    }


def list_reader_bookmarks(
    addon_dir: str,
    profile: str,
    card_id: int,
    reader_type: str,
) -> list[dict[str, Any]]:
    kind = _reader_type(reader_type)
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT id, card_id, reader_type, label, comment_text, location_json, created_at, updated_at "
            "FROM reader_bookmarks WHERE card_id = ? AND reader_type = ?",
            (int(card_id), kind),
        )
        .fetchall()
    )
    bookmarks: list[dict[str, Any]] = []
    for row in rows:
        bookmarks.append(_bookmark_from_row(kind, row))
    return sorted(bookmarks, key=lambda item: _sort_key(kind, item))


def delete_reader_bookmark(
    addon_dir: str,
    profile: str,
    card_id: int,
    reader_type: str,
    bookmark_id: str,
) -> bool:
    kind = _reader_type(reader_type)
    conn = get_connection(addon_dir, profile)
    cur = conn.execute(
        "DELETE FROM reader_bookmarks WHERE id = ? AND card_id = ? AND reader_type = ?",
        (str(bookmark_id or ""), int(card_id), kind),
    )
    conn.commit()
    return cur.rowcount > 0


def update_reader_bookmark_comment(
    addon_dir: str,
    profile: str,
    card_id: int,
    reader_type: str,
    bookmark_id: str,
    comment_text: str | None,
) -> dict[str, Any] | None:
    kind = _reader_type(reader_type)
    clean_comment = _normalize_comment_text(comment_text)
    conn = get_connection(addon_dir, profile)
    now = int(time.time())
    cur = conn.execute(
        "UPDATE reader_bookmarks "
        "SET comment_text = ?, updated_at = ? "
        "WHERE id = ? AND card_id = ? AND reader_type = ?",
        (clean_comment, now, str(bookmark_id or ""), int(card_id), kind),
    )
    conn.commit()
    if cur.rowcount <= 0:
        return None
    row = conn.execute(
        "SELECT id, card_id, reader_type, label, comment_text, location_json, created_at, updated_at "
        "FROM reader_bookmarks WHERE id = ? AND card_id = ? AND reader_type = ?",
        (str(bookmark_id or ""), int(card_id), kind),
    ).fetchone()
    if not row:
        return None
    return _bookmark_from_row(kind, row)


def _sort_key(reader_type: str, item: dict[str, Any]) -> tuple:
    location = item.get("location") or {}
    if reader_type == "pdf":
        return (int(location.get("page", 1) or 1), int(item.get("created_at", 0) or 0))
    if reader_type == "epub":
        return (
            int(location.get("section_index", 0) or 0),
            float(location.get("scroll_ratio", 0.0) or 0.0),
            int(item.get("created_at", 0) or 0),
        )
    if reader_type == "writing":
        return (
            int(location.get("block_number", 0) or 0),
            int(location.get("cursor_position", 0) or 0),
            int(item.get("created_at", 0) or 0),
        )
    if reader_type == "video":
        return (float(location.get("seconds", 0.0) or 0.0), int(item.get("created_at", 0) or 0))
    return (int(item.get("created_at", 0) or 0),)


def _bookmark_from_row(reader_type: str, row) -> dict[str, Any]:
    try:
        location = json.loads(row[5] or "{}")
    except Exception:
        location = {}
    return {
        "id": str(row[0] or ""),
        "card_id": int(row[1] or 0),
        "reader_type": str(row[2] or ""),
        "label": str(row[3] or ""),
        "comment_text": _normalize_comment_text(row[4]),
        "location": normalize_reader_location(reader_type, location),
        "created_at": int(row[6] or 0),
        "updated_at": int(row[7] or 0),
    }
