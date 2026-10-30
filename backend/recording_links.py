"""Profile-scoped passage/recording associations; never change an Anki card."""
from __future__ import annotations

import json
import math
from contextlib import nullcontext

try:
    from .db import get_connection
    from .document_links import _identity
except ImportError:
    from db import get_connection
    from document_links import _identity

MAX_LINKS = 200
MAX_SECONDS = 604800


def _integer(value, minimum=1, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid resource identity or position")
    return value


def _number(value, maximum=1):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError("Invalid resource position")
    return float(value)


def _text(value, maximum, *, required=False):
    if not isinstance(value, str) or len(value) > maximum or "\0" in value or (required and not value.strip()):
        raise ValueError("Invalid resource label")
    return value.strip()


def normalize_source(source):
    if not isinstance(source, dict) or source.get("kind") not in ("card", "pdf", "epub"):
        raise ValueError("Invalid resource source")
    result = dict(kind=source["kind"], card_id=_integer(source.get("card_id")),
                  quote=_text(source.get("quote", ""), 2000))
    if result["kind"] != "card":
        result["scroll"] = _number(source.get("scroll", 0))
    if result["kind"] == "pdf":
        result["page"] = _integer(source.get("page"), 1, 1_000_000)
        if source.get("page_y") is not None:
            result["page_y"] = _number(source["page_y"])
    elif result["kind"] == "epub":
        result["section"] = _integer(source.get("section"), 0, 1_000_000)
        result["offset"] = _integer(source.get("offset", -1), -1, 50_000_000)
    return result


def validate_segment(start, end=None, *, duration=None):
    start = _number(start, MAX_SECONDS)
    end = None if end is None else _number(end, MAX_SECONDS)
    if end is not None and end <= start:
        raise ValueError("Segment end must follow its start")
    if duration is not None:
        duration = _number(duration, MAX_SECONDS)
        if start >= duration or (end is not None and end > duration):
            raise ValueError("Segment lies outside the recording")
    return start, end


def _match(side, prefix=""):
    return f"({prefix}{side}_content_id=? OR ({prefix}{side}_content_id IS NULL AND {prefix}{side}_card_id=?))"


def _source_position(source):
    return source.get("page", source.get("section", 0))


def add_recording_link(addon_dir, profile, source, recording_card_id, *, start, end=None, label, _connection=None):
    source = normalize_source(source)
    recording_card_id = _integer(recording_card_id)
    start, end = validate_segment(start, end)
    label = _text(label, 240, required=True)
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    conn = _connection if _connection is not None else get_connection(addon_dir, profile)
    with nullcontext() if _connection is not None else conn:
        src_id, rec_id = _identity(conn, source["card_id"]), _identity(conn, recording_card_id)
        params = (src_id, source["card_id"], rec_id, recording_card_id, start, end, MAX_LINKS)
        candidates = conn.execute(
            "SELECT id,source_json FROM recording_links WHERE " + _match("source") +
            " AND " + _match("recording") + " AND start=? AND end IS ? LIMIT ?", params,
        ).fetchall()
        position = {key: value for key, value in source.items() if key != 'card_id'}
        for link_id, saved in candidates:
            try:
                previous = normalize_source(json.loads(saved))
            except (ValueError, TypeError):
                continue
            previous.pop('card_id')
            if previous == position:
                return link_id
        count = conn.execute("SELECT count(*) FROM recording_links WHERE " + _match("source"),
                             (src_id, source["card_id"])).fetchone()[0]
        if count >= MAX_LINKS:
            raise ValueError("Recording link limit reached")
        return conn.execute(
            "INSERT INTO recording_links(source_card_id,source_content_id,source_kind,source_position,"
            "source_json,recording_card_id,recording_content_id,start,end,label) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (source["card_id"], src_id, source["kind"], _source_position(source), encoded,
             recording_card_id, rec_id, start, end, label),
        ).lastrowid


def list_recording_links(addon_dir, profile, *, source=None, recording_card_id=None):
    if (source is None) == (recording_card_id is None):
        raise ValueError("Choose one resource endpoint")
    conn = get_connection(addon_dir, profile)
    if source is not None:
        source = normalize_source(source)
        where = _match("source", "l.") + " AND l.source_kind=? AND l.source_position=?"
        params = (_identity(conn, source["card_id"]), source["card_id"], source["kind"], _source_position(source))
    else:
        recording_card_id = _integer(recording_card_id)
        where = _match("recording", "l.")
        params = (_identity(conn, recording_card_id), recording_card_id)
    rows = conn.execute(
        "SELECT l.id,l.source_json,CASE WHEN l.source_content_id IS NULL THEN l.source_card_id "
        "ELSE coalesce(s.card_id,0) END,CASE WHEN l.recording_content_id IS NULL THEN l.recording_card_id "
        "ELSE coalesce(r.card_id,0) END,l.start,l.end,l.label FROM recording_links l "
        "LEFT JOIN content_items s ON s.content_id=l.source_content_id "
        "LEFT JOIN content_items r ON r.content_id=l.recording_content_id WHERE " + where +
        " ORDER BY l.id LIMIT ?", (*params, MAX_LINKS),
    ).fetchall()
    result = []
    for link_id, encoded, src, rec, start, end, label in rows:
        try:
            location = normalize_source(json.loads(encoded))
            location["card_id"] = src
            start, end = validate_segment(start, end)
            label = _text(label, 240, required=True)
        except (ValueError, TypeError):
            continue
        result.append(dict(id=link_id, source=location, recording_card_id=rec,
                           start=start, end=end, label=label))
    return result


def _owner(conn, owner_card_id):
    owner_card_id = _integer(owner_card_id)
    identity = _identity(conn, owner_card_id)
    return "(" + _match("source") + " OR " + _match("recording") + ")", (identity, owner_card_id) * 2


def remove_recording_link(addon_dir, profile, link_id, *, owner_card_id):
    link_id = _integer(link_id)
    conn = get_connection(addon_dir, profile)
    predicate, params = _owner(conn, owner_card_id)
    with conn:
        return conn.execute("DELETE FROM recording_links WHERE id=? AND " + predicate,
                            (link_id, *params)).rowcount > 0


def replace_recording_link(addon_dir, profile, link_id, *, owner_card_id, recording_card_id,
                           start, end=None, label):
    link_id, recording_card_id = _integer(link_id), _integer(recording_card_id)
    start, end = validate_segment(start, end)
    label = _text(label, 240, required=True)
    conn = get_connection(addon_dir, profile)
    predicate, params = _owner(conn, owner_card_id)
    with conn:
        return conn.execute("UPDATE recording_links SET recording_card_id=?,recording_content_id=?,"
            "start=?,end=?,label=? WHERE id=? AND " + predicate,
            (recording_card_id, _identity(conn, recording_card_id), start, end, label, link_id, *params)).rowcount > 0
