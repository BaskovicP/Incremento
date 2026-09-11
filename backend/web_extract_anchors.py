"""Bounded, deterministic markers for tracked Web extractions and snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping

try:
    from .content_safety import normalize_external_http_url
except ImportError:
    from content_safety import normalize_external_http_url  # type: ignore


WEB_EXTRACT_ANCHOR_VERSION = 1
MAX_WEB_EXTRACT_EXACT_CHARS = 4_000
MAX_WEB_EXTRACT_CONTEXT_CHARS = 96
MAX_WEB_EXTRACT_PATH_DEPTH = 64
MAX_WEB_EXTRACT_PATH_INDEX = 1_000_000
MAX_WEB_EXTRACT_OFFSET = 1_000_000
MIN_WEB_SNAPSHOT_DIMENSION = 6
MAX_WEB_SNAPSHOT_DIMENSION = 100_000
MAX_WEB_SNAPSHOT_COORDINATE = 10_000_000
MAX_WEB_SNAPSHOT_ANCHOR_RATIO = 1_000_000
MAX_PENDING_WEB_EXTRACT_RECORDS = 64
MAX_STORED_WEB_EXTRACT_ANCHORS = 48
MAX_WEB_EXTRACT_ANCHORS_JSON_CHARS = 262_144
_WEB_SNAPSHOT_TAG_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def _strict_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    # QWebEngine converts JavaScript Number values through QVariant and may
    # deliver even whole numbers as Python floats. Accept only exact finite
    # integers; fractional and non-finite input still fails closed.
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _bounded_text(value: object, *, max_chars: int, allow_empty: bool) -> str | None:
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(raw) > max_chars:
        return None
    if any(char not in {"\n", "\t"} and ord(char) < 0x20 for char in raw):
        return None
    if not allow_empty and not raw.strip():
        return None
    return raw


def _normalize_path(value: object, *, allow_empty: bool = False) -> list[int] | None:
    if not isinstance(value, (list, tuple)):
        return None
    raw_path = list(value)
    if (not raw_path and not allow_empty) or len(raw_path) > MAX_WEB_EXTRACT_PATH_DEPTH:
        return None
    path: list[int] = []
    for raw_index in raw_path:
        index = _strict_int(raw_index)
        if index is None:
            return None
        if index < 0 or index > MAX_WEB_EXTRACT_PATH_INDEX:
            return None
        path.append(index)
    return path


def _normalize_offset(value: object) -> int | None:
    offset = _strict_int(value)
    if offset is None:
        return None
    if offset < 0 or offset > MAX_WEB_EXTRACT_OFFSET:
        return None
    return offset


def _normalize_bounded_int(
    value: object,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    normalized = _strict_int(value)
    if normalized is None or normalized < minimum or normalized > maximum:
        return None
    return normalized


def _normalize_snapshot_anchor(value: Mapping) -> dict | None:
    page_x = _normalize_bounded_int(
        value.get("pageX"),
        minimum=0,
        maximum=MAX_WEB_SNAPSHOT_COORDINATE,
    )
    page_y = _normalize_bounded_int(
        value.get("pageY"),
        minimum=0,
        maximum=MAX_WEB_SNAPSHOT_COORDINATE,
    )
    width = _normalize_bounded_int(
        value.get("width"),
        minimum=MIN_WEB_SNAPSHOT_DIMENSION,
        maximum=MAX_WEB_SNAPSHOT_DIMENSION,
    )
    height = _normalize_bounded_int(
        value.get("height"),
        minimum=MIN_WEB_SNAPSHOT_DIMENSION,
        maximum=MAX_WEB_SNAPSHOT_DIMENSION,
    )
    document_width = _normalize_bounded_int(
        value.get("documentWidth"),
        minimum=1,
        maximum=MAX_WEB_SNAPSHOT_COORDINATE,
    )
    document_height = _normalize_bounded_int(
        value.get("documentHeight"),
        minimum=1,
        maximum=MAX_WEB_SNAPSHOT_COORDINATE,
    )
    anchor_path = _normalize_path(value.get("anchorPath"), allow_empty=True)
    anchor_x_ratio = _normalize_bounded_int(
        value.get("anchorXRatio"),
        minimum=0,
        maximum=MAX_WEB_SNAPSHOT_ANCHOR_RATIO,
    )
    anchor_y_ratio = _normalize_bounded_int(
        value.get("anchorYRatio"),
        minimum=0,
        maximum=MAX_WEB_SNAPSHOT_ANCHOR_RATIO,
    )
    anchor_tag = str(value.get("anchorTag") or "").strip().casefold()
    if anchor_tag and _WEB_SNAPSHOT_TAG_RE.fullmatch(anchor_tag) is None:
        return None
    if anchor_path and not anchor_tag:
        return None
    if (
        page_x is None
        or page_y is None
        or width is None
        or height is None
        or document_width is None
        or document_height is None
        or anchor_path is None
        or anchor_x_ratio is None
        or anchor_y_ratio is None
    ):
        return None

    identity_payload = {
        "version": WEB_EXTRACT_ANCHOR_VERSION,
        "kind": "snapshot",
        "pageX": page_x,
        "pageY": page_y,
        "width": width,
        "height": height,
        "documentWidth": document_width,
        "documentHeight": document_height,
        "anchorPath": anchor_path,
        "anchorTag": anchor_tag,
        "anchorXRatio": anchor_x_ratio,
        "anchorYRatio": anchor_y_ratio,
    }
    encoded = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": WEB_EXTRACT_ANCHOR_VERSION,
        "id": hashlib.sha256(encoded).hexdigest()[:24],
        "kind": "snapshot",
        "pageX": page_x,
        "pageY": page_y,
        "width": width,
        "height": height,
        "documentWidth": document_width,
        "documentHeight": document_height,
        "anchorPath": anchor_path,
        "anchorTag": anchor_tag,
        "anchorXRatio": anchor_x_ratio,
        "anchorYRatio": anchor_y_ratio,
    }


def normalize_web_extract_anchor(value: object) -> dict | None:
    """Validate one untrusted text/region anchor and assign a stable identity."""
    if not isinstance(value, Mapping):
        return None
    version = _strict_int(value.get("version"))
    if version != WEB_EXTRACT_ANCHOR_VERSION:
        return None
    kind = value.get("kind")
    if kind == "snapshot":
        return _normalize_snapshot_anchor(value)
    if kind not in (None, "", "text"):
        return None

    exact = _bounded_text(
        value.get("exact"),
        max_chars=MAX_WEB_EXTRACT_EXACT_CHARS,
        allow_empty=False,
    )
    prefix = _bounded_text(
        value.get("prefix"),
        max_chars=MAX_WEB_EXTRACT_CONTEXT_CHARS,
        allow_empty=True,
    )
    suffix = _bounded_text(
        value.get("suffix"),
        max_chars=MAX_WEB_EXTRACT_CONTEXT_CHARS,
        allow_empty=True,
    )
    start_path = _normalize_path(value.get("startPath"))
    end_path = _normalize_path(value.get("endPath"))
    start_offset = _normalize_offset(value.get("startOffset"))
    end_offset = _normalize_offset(value.get("endOffset"))
    if (
        exact is None
        or prefix is None
        or suffix is None
        or start_path is None
        or end_path is None
        or start_offset is None
        or end_offset is None
    ):
        return None
    if start_path == end_path and end_offset <= start_offset:
        return None

    identity_payload = {
        "version": WEB_EXTRACT_ANCHOR_VERSION,
        "exact": exact,
        "prefix": prefix,
        "suffix": suffix,
        "startPath": start_path,
        "startOffset": start_offset,
        "endPath": end_path,
        "endOffset": end_offset,
    }
    encoded = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "version": WEB_EXTRACT_ANCHOR_VERSION,
        "id": hashlib.sha256(encoded).hexdigest()[:24],
        "exact": exact,
        "prefix": prefix,
        "suffix": suffix,
        "startPath": start_path,
        "startOffset": start_offset,
        "endPath": end_path,
        "endOffset": end_offset,
    }


def normalize_web_extract_url(value: object) -> str:
    try:
        return normalize_external_http_url(value)
    except (TypeError, ValueError):
        return ""


def normalize_web_extract_record(value: object) -> dict | None:
    """Validate one profile-local Web-card/URL/anchor association."""
    if not isinstance(value, Mapping):
        return None
    version = _strict_int(value.get("version", WEB_EXTRACT_ANCHOR_VERSION))
    web_card_id = _strict_int(value.get("webCardId"))
    if (
        version != WEB_EXTRACT_ANCHOR_VERSION
        or web_card_id is None
        or web_card_id <= 0
    ):
        return None
    url = normalize_web_extract_url(value.get("url"))
    anchor = normalize_web_extract_anchor(value.get("anchor"))
    if not url or anchor is None:
        return None
    return {
        "version": WEB_EXTRACT_ANCHOR_VERSION,
        "webCardId": web_card_id,
        "url": url,
        "anchor": anchor,
    }


def normalize_web_extract_anchors(
    values: object,
    *,
    limit: int = MAX_STORED_WEB_EXTRACT_ANCHORS,
) -> list[dict]:
    if not isinstance(values, (list, tuple)):
        return []
    bounded_limit = max(0, min(int(limit), MAX_STORED_WEB_EXTRACT_ANCHORS))
    if bounded_limit == 0:
        return []
    anchors: list[dict] = []
    seen: set[str] = set()
    for value in values:
        anchor = normalize_web_extract_anchor(value)
        if anchor is None or anchor["id"] in seen:
            continue
        seen.add(anchor["id"])
        anchors.append(anchor)
        if len(anchors) >= bounded_limit:
            break
    return anchors


def normalize_web_extract_records(
    values: object,
    *,
    limit: int = MAX_PENDING_WEB_EXTRACT_RECORDS,
) -> list[dict]:
    if not isinstance(values, (list, tuple)):
        return []
    bounded_limit = max(0, min(int(limit), MAX_PENDING_WEB_EXTRACT_RECORDS))
    if bounded_limit == 0:
        return []
    records: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    for value in values:
        record = normalize_web_extract_record(value)
        if record is None:
            continue
        key = (
            int(record["webCardId"]),
            str(record["url"]),
            str(record["anchor"]["id"]),
        )
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
        if len(records) >= bounded_limit:
            break
    return records


def merge_web_extract_anchors(
    *collections: Iterable[object],
    limit: int = MAX_STORED_WEB_EXTRACT_ANCHORS,
) -> list[dict]:
    combined: list[object] = []
    for collection in collections:
        combined.extend(list(collection or []))
    return normalize_web_extract_anchors(combined, limit=limit)


def merge_latest_web_extract_anchors(
    *collections: Iterable[object],
    limit: int = MAX_STORED_WEB_EXTRACT_ANCHORS,
) -> list[dict]:
    """Return the newest unique anchors while preserving chronological order."""
    bounded_limit = max(0, min(int(limit), MAX_STORED_WEB_EXTRACT_ANCHORS))
    if bounded_limit == 0:
        return []
    newest_first: list[dict] = []
    seen: set[str] = set()
    for collection in reversed(collections):
        for value in reversed(list(collection or [])):
            anchor = normalize_web_extract_anchor(value)
            if anchor is None or anchor["id"] in seen:
                continue
            seen.add(anchor["id"])
            newest_first.append(anchor)
            if len(newest_first) >= bounded_limit:
                return list(reversed(newest_first))
    return list(reversed(newest_first))
