"""Crash-safe, profile-scoped storage for the one active extraction draft."""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

try:
    from .paths import get_extraction_draft_path
except ImportError:
    from paths import get_extraction_draft_path  # type: ignore


_DRAFT_VERSION = 1
_MAX_FILE_BYTES = 2_100_000
_MAX_FIELDS = 32
_MAX_FIELD_CHARS = 500_000
_MAX_TAGS = 100
_MAX_TAG_CHARS = 200
_MAX_TEXT_CHARS = 10_000
_MAX_CONTAINER_ITEMS = 100
_MAX_NESTING = 4


def extraction_draft_path(addon_dir: str, profile: str) -> Path:
    return get_extraction_draft_path(addon_dir, profile)


def _bounded_json(value, *, depth: int = 0):
    if depth > _MAX_NESTING:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value[:_MAX_TEXT_CHARS]
    if isinstance(value, Mapping):
        result = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= _MAX_CONTAINER_ITEMS:
                break
            key = str(raw_key or "")[:128]
            if not key:
                continue
            result[key] = _bounded_json(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [
            _bounded_json(item, depth=depth + 1)
            for item in list(value)[:_MAX_CONTAINER_ITEMS]
        ]
    return str(value)[:_MAX_TEXT_CHARS]


def normalize_extraction_draft(
    draft: Mapping | None,
    *,
    now: float | None = None,
) -> dict | None:
    raw = dict(draft or {})
    try:
        version = int(raw.get("version", _DRAFT_VERSION) or _DRAFT_VERSION)
    except Exception:
        return None
    if version != _DRAFT_VERSION:
        return None

    fields = [
        str(value or "")[:_MAX_FIELD_CHARS]
        for value in list(raw.get("fields") or [])[:_MAX_FIELDS]
    ]
    if not fields or not any(value.strip() for value in fields):
        return None

    tags: list[str] = []
    seen_tags: set[str] = set()
    for value in list(raw.get("tags") or [])[:_MAX_TAGS]:
        tag = str(value or "").strip()[:_MAX_TAG_CHARS]
        key = tag.casefold()
        if tag and key not in seen_tags:
            seen_tags.add(key)
            tags.append(tag)

    raw_saved_at = time.time() if now is None else now
    if now is None and "saved_at" in raw:
        raw_saved_at = raw.get("saved_at")
    try:
        saved_at = float(raw_saved_at)
    except Exception:
        saved_at = time.time()
    if not math.isfinite(saved_at) or saved_at < 0:
        saved_at = time.time()

    return {
        "version": _DRAFT_VERSION,
        "saved_at": saved_at,
        "source": str(raw.get("source") or "").strip()[:32],
        "note_type": str(raw.get("note_type") or "").strip()[:200],
        "deck": str(raw.get("deck") or "").strip()[:200],
        "fields": fields,
        "tags": tags,
        "extract_options": _bounded_json(dict(raw.get("extract_options") or {})),
        "extract_context": _bounded_json(dict(raw.get("extract_context") or {})),
    }


def save_extraction_draft(
    addon_dir: str,
    profile: str,
    draft: Mapping,
    *,
    now: float | None = None,
) -> dict:
    normalized = normalize_extraction_draft(draft, now=now)
    if normalized is None:
        raise ValueError("An extraction draft needs at least one non-empty field.")
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > _MAX_FILE_BYTES:
        raise ValueError("The extraction draft is too large to autosave safely.")

    path = extraction_draft_path(addon_dir, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".extraction_draft-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_name = handle.name
            try:
                os.chmod(temporary_name, 0o600)
            except OSError:
                pass
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = ""
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except OSError:
                pass
    return normalized


def load_extraction_draft(addon_dir: str, profile: str) -> dict | None:
    path = extraction_draft_path(addon_dir, profile)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    return normalize_extraction_draft(payload)


def clear_extraction_draft(addon_dir: str, profile: str) -> bool:
    path = extraction_draft_path(addon_dir, profile)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
