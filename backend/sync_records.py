"""Normalized records for shared-folder sync.

See docs/architecture/shared-folder-sync.md §2 and §4. A family adapter turns
one kind of saved Incremento state into ``(key, value)`` records whose values
are canonical JSON: allowlisted fields only, fixed float precision, and no
incidental timestamps or caches, so that a save that changes nothing durable
never produces a revision. Pure: no Anki, no Qt; the caller passes the
connection and owns the transaction.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from urllib.parse import quote, unquote

try:
    from .annotation_notes import normalize_note
    from .annotation_styles import ANNOTATION_STYLES
    from .highlight_colors import normalize_highlight_color
    from .reader_bookmarks import BOOKMARK_COMMENT_MAX_LEN, READER_TYPES, normalize_reader_location
except ImportError:
    from annotation_notes import normalize_note  # type: ignore[no-redef]
    from annotation_styles import ANNOTATION_STYLES  # type: ignore[no-redef]
    from highlight_colors import normalize_highlight_color  # type: ignore[no-redef]
    from reader_bookmarks import (  # type: ignore[no-redef]
        BOOKMARK_COMMENT_MAX_LEN, READER_TYPES, normalize_reader_location,
    )

#: Version of the exchanged record and revision format. Independent of the
#: SQLite schema version: a schema change need not change the format, and a
#: format change must fail clearly on older devices.
SYNC_FORMAT = 1

#: Decimal places kept for floating-point fields.
FLOAT_PLACES = 6


class SyncScanError(RuntimeError):
    """A family could not be read completely. Never treated as an empty family."""


@dataclass(frozen=True)
class CardRef:
    """The Anki card a record belongs to, as AnkiWeb identifies it.

    ``uploaded_usn`` is the card's update sequence number once AnkiWeb has it,
    or ``None`` while the card is still pending upload (``usn == -1``).
    ``collection_usn`` is the collection's usn when the record was captured:
    a later sync by the same device raises it, which proves the upload.
    """

    card_id: int
    note_id: int
    guid: str
    uploaded_usn: int | None
    collection_usn: int | None = None
    #: The collection's schema-modified time: a full sync or schema change
    #: alters it, and usns are only compared within one value.
    collection_scm: int | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(value: Any) -> str:
    """The one encoding used for hashing and exchange."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def value_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def record_hash(family: Any, value: dict[str, Any] | None) -> str:
    """What the baseline remembers of a value; a deleted record hashes to ''.

    A family may define ``fingerprint(value)`` to say which fields make a
    change (documents: their version, not their current bytes).
    """
    if value is None:
        return ""
    fingerprint = getattr(family, "fingerprint", None)
    return fingerprint(value) if fingerprint is not None else value_hash(value)


def record_blobs(family: Any, value: dict[str, Any] | None) -> list[str]:
    """Blobs a value needs on the receiving device (documents: the file)."""
    blobs = getattr(family, "blobs", None)
    return sorted(blobs(value)) if blobs is not None and value is not None else []


def rows_digest(conn: sqlite3.Connection, *queries: str) -> str:
    """A cheap fingerprint of raw rows, to skip normalizing a family whose rows did not change."""
    digest = hashlib.sha256()
    try:
        for query in queries:
            for row in conn.execute(query):
                digest.update(repr(row).encode("utf-8"))
            digest.update(b"\x00")
    except sqlite3.Error as exc:
        raise SyncScanError(str(exc)) from exc
    return digest.hexdigest()


def normalized_float(value: Any, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise SyncScanError(f"{field} is not a finite number")
    return round(number, FLOAT_PLACES) + 0.0  # + 0.0 folds -0.0 into 0.0


class Family(Protocol):
    name: str

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        """Every record, completely, or raise SyncScanError."""

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        """The live value of one record, or None if it does not exist."""

    def card_id(self, key: str) -> int | None:
        """The Anki card the record depends on, if any."""

    def validate(self, key: str, value: Any) -> None:
        """Reject an incoming key or value that this family could not have produced (ValueError)."""

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        """Save a value. Never commits: runs inside the caller's transaction."""

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        """Remove a record. Never commits: runs inside the caller's transaction."""


#: Anki ids are positive signed 64-bit integers.
_MAX_ANKI_ID = 2**63 - 1


def card_key(card_id: int) -> str:
    return f"card:{int(card_id)}"


def card_id_from_key(key: str) -> int:
    prefix, _, number = key.partition(":")
    if prefix != "card" or not number.isdigit() or len(number) > 19:
        raise ValueError(f"not a card key: {key!r}")
    card_id = int(number)
    if not 0 < card_id <= _MAX_ANKI_ID or card_key(card_id) != key:
        raise ValueError(f"not a card key: {key!r}")
    return card_id


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_card_deps(card_id: int, deps: Any) -> None:
    """``{"card": CardRef}`` naming the card a record depends on."""
    if not isinstance(deps, dict) or not isinstance(deps.get("card"), dict):
        raise ValueError("deps must name the card")
    card = deps["card"]
    if set(card) != {"card_id", "note_id", "guid", "uploaded_usn", "collection_usn", "collection_scm"}:
        raise ValueError("deps card fields")
    if card["card_id"] != card_id:
        raise ValueError("deps card does not match the key")
    if not (isinstance(card["note_id"], int) and not isinstance(card["note_id"], bool)
            and 0 < card["note_id"] <= _MAX_ANKI_ID):
        raise ValueError("deps note id")
    if not isinstance(card["guid"], str) or not 0 < len(card["guid"]) <= 128:
        raise ValueError("deps guid")
    for field in ("uploaded_usn", "collection_usn", "collection_scm"):
        usn = card[field]
        if usn is not None and not (isinstance(usn, int) and not isinstance(usn, bool) and 0 <= usn <= _MAX_ANKI_ID):
            raise ValueError(f"deps {field}")


class PriorityFamily:
    """``priorities``: one record per card, ``{"priority": float}``."""

    name = "priority"

    @staticmethod
    def _value(priority: Any) -> dict[str, Any]:
        return {"priority": normalized_float(priority, "priority")}

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        try:
            rows = conn.execute("SELECT card_id, priority FROM priorities ORDER BY card_id").fetchall()
        except sqlite3.Error as exc:
            raise SyncScanError(f"priorities: {exc}") from exc
        return [(card_key(card_id), self._value(priority)) for card_id, priority in rows]

    def raw_digest(self, conn: sqlite3.Connection) -> str:
        return rows_digest(conn, "SELECT card_id, priority FROM priorities ORDER BY card_id")

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        try:
            row = conn.execute("SELECT priority FROM priorities WHERE card_id=?",
                               (card_id_from_key(key),)).fetchone()
        except sqlite3.Error as exc:
            raise SyncScanError(f"priorities: {exc}") from exc
        return None if row is None else self._value(row[0])

    def card_id(self, key: str) -> int | None:
        return card_id_from_key(key)

    def validate(self, key: str, value: Any) -> None:
        card_id_from_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != {"priority"}:
            raise ValueError("priority value fields")
        priority = value["priority"]
        if not _is_number(priority) or not 0 <= priority <= 100:
            raise ValueError("priority value range")
        if self._value(priority) != value:
            raise ValueError("priority value is not normalized")

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        conn.execute("INSERT OR REPLACE INTO priorities(card_id, priority) VALUES (?, ?)",
                     (card_id_from_key(key), value["priority"]))

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        conn.execute("DELETE FROM priorities WHERE card_id=?", (card_id_from_key(key),))


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return normalized_float(value, "number")
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    return value


def split_card_key(key: str, kind: str) -> tuple[int, str]:
    """``card:<id>/<kind>`` or ``card:<id>/<kind>:<name>`` -> (card id, name or '')."""
    card_part, slash, rest = key.partition("/")
    if not slash:
        raise ValueError(f"not a {kind} key: {key!r}")
    card_id = card_id_from_key(card_part)
    name, colon, suffix = rest.partition(":")
    if name != kind:
        raise ValueError(f"not a {kind} key: {key!r}")
    return card_id, suffix if colon else ""


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LOCATION_CHARS = 16 * 1024


class BookmarkFamily:
    """``reader_bookmarks`` except writing bookmarks: one record per bookmark.

    ``updated_at`` is incidental and stays local; a remote write keeps the
    device's own value (or the creation time for a new bookmark).
    """

    name = "reader_bookmark"
    reader_types = frozenset(READER_TYPES) - {"writing"}

    @staticmethod
    def key(card_id: int, bookmark_id: str) -> str:
        return f"{card_key(card_id)}/bookmark:{bookmark_id}"

    def _parse_key(self, key: str) -> tuple[int, str]:
        card_id, bookmark_id = split_card_key(key, "bookmark")
        if not _SAFE_ID.match(bookmark_id) or self.key(card_id, bookmark_id) != key:
            raise ValueError(f"not a bookmark key: {key!r}")
        return card_id, bookmark_id

    @staticmethod
    def _value(row: Sequence[Any]) -> dict[str, Any]:
        reader_type, label, comment, location_json, created_at = row
        try:
            location = json.loads(location_json or "{}")
        except json.JSONDecodeError as exc:
            raise SyncScanError(f"reader_bookmarks: unreadable location: {exc}") from exc
        return {"reader_type": reader_type, "label": label, "comment_text": comment,
                "location": _round_floats(location), "created_at": int(created_at)}

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        try:
            rows = conn.execute("SELECT id, card_id, reader_type, label, comment_text, location_json, created_at "
                                "FROM reader_bookmarks WHERE reader_type <> 'writing' ORDER BY card_id, id").fetchall()
        except sqlite3.Error as exc:
            raise SyncScanError(f"reader_bookmarks: {exc}") from exc
        return [(self.key(card_id, bookmark_id), self._value(rest)) for bookmark_id, card_id, *rest in rows]

    def raw_digest(self, conn: sqlite3.Connection) -> str:
        return rows_digest(conn, "SELECT id, card_id, reader_type, label, comment_text, location_json, created_at "
                                 "FROM reader_bookmarks WHERE reader_type <> 'writing' ORDER BY card_id, id")

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        card_id, bookmark_id = self._parse_key(key)
        try:
            row = conn.execute("SELECT reader_type, label, comment_text, location_json, created_at "
                               "FROM reader_bookmarks WHERE id=? AND card_id=? AND reader_type <> 'writing'",
                               (bookmark_id, card_id)).fetchone()
        except sqlite3.Error as exc:
            raise SyncScanError(f"reader_bookmarks: {exc}") from exc
        return None if row is None else self._value(row)

    def card_id(self, key: str) -> int | None:
        return self._parse_key(key)[0]

    def validate(self, key: str, value: Any) -> None:
        self._parse_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != {"reader_type", "label", "comment_text", "location",
                                                         "created_at"}:
            raise ValueError("bookmark value fields")
        if value["reader_type"] not in self.reader_types:
            raise ValueError("bookmark reader type")
        if not isinstance(value["label"], str) or not 0 < len(value["label"]) <= 160:
            raise ValueError("bookmark label")
        comment = value["comment_text"]
        if not isinstance(comment, str) or len(comment) > BOOKMARK_COMMENT_MAX_LEN or comment != comment.strip():
            raise ValueError("bookmark comment")
        created = value["created_at"]
        if not isinstance(created, int) or isinstance(created, bool) or created < 0:
            raise ValueError("bookmark creation time")
        location = value["location"]
        if not isinstance(location, dict) or len(canonical_json(location)) > MAX_LOCATION_CHARS:
            raise ValueError("bookmark location size")
        if _round_floats(normalize_reader_location(value["reader_type"], location)) != location:
            raise ValueError("bookmark location is not normalized")

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        card_id, bookmark_id = self._parse_key(key)
        existing = conn.execute("SELECT updated_at FROM reader_bookmarks WHERE id=?", (bookmark_id,)).fetchone()
        conn.execute("INSERT OR REPLACE INTO reader_bookmarks(id, card_id, reader_type, label, comment_text, "
                     "location_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (bookmark_id, card_id, value["reader_type"], value["label"], value["comment_text"],
                      json.dumps(value["location"], ensure_ascii=False, sort_keys=True), value["created_at"],
                      existing[0] if existing else value["created_at"]))

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        card_id, bookmark_id = self._parse_key(key)
        conn.execute("DELETE FROM reader_bookmarks WHERE id=? AND card_id=?", (bookmark_id, card_id))


def _ratio(value: Any) -> bool:
    return _is_number(value) and 0 <= value <= 1


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _anchor(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > MAX_LOCATION_CHARS:
        return False
    if not value:
        return True
    try:
        return isinstance(json.loads(value), (dict, list))
    except json.JSONDecodeError:
        return False


def _text(limit: int) -> Callable[[Any], bool]:
    return lambda value: isinstance(value, str) and len(value) <= limit


#: Per reader: its table, and each synced column with (how to read it, check).
_POSITION_COLUMNS: Mapping[str, tuple[str, tuple[tuple[str, str, Callable[[Any], bool]], ...]]] = {
    "pdf": ("pdf_progress", (
        ("page", "int", lambda v: _nonnegative_int(v) and v >= 1),
        ("scroll_ratio", "float", _ratio),
        ("read_page", "int", _nonnegative_int),
        ("read_anchor_json", "str", _anchor))),
    "epub": ("epub_progress", (
        ("section_index", "int", _nonnegative_int),
        ("scroll_ratio", "float", _ratio),
        ("is_finished", "bool", lambda v: isinstance(v, bool)),
        ("read_section_index", "int", _nonnegative_int),
        ("read_anchor_json", "str", _anchor))),
    "video": ("video_progress", (
        ("position", "float", lambda v: _is_number(v) and v >= 0),)),
    "web": ("web_progress", (
        ("url", "str", _text(4096)),
        ("scroll_ratio", "float", _ratio),
        ("bookmark_url", "str", _text(4096)),
        ("bookmark_payload", "str", _text(65536)),
        ("media_url", "str", _text(4096)),
        ("media_title", "str", _text(1000)),
        ("media_seconds", "float", lambda v: _is_number(v) and v >= 0))),
}


class PositionFamily:
    """Where reading stopped, per card and reader; display preferences stay local."""

    name = "reading_position"

    @staticmethod
    def _parse_key(key: str) -> tuple[int, str]:
        card_part, slash, reader = key.partition("/")
        card_id = card_id_from_key(card_part)
        if not slash or reader not in _POSITION_COLUMNS:
            raise ValueError(f"not a reading position key: {key!r}")
        return card_id, reader

    @staticmethod
    def _value(reader: str, row: Sequence[Any]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for (column, kind, _), raw in zip(_POSITION_COLUMNS[reader][1], row):
            try:
                if kind == "int":
                    value[column] = int(raw)
                elif kind == "float":
                    value[column] = normalized_float(raw, column)
                elif kind == "bool":
                    value[column] = bool(raw)
                else:
                    value[column] = "" if raw is None else str(raw)
            except (TypeError, ValueError) as exc:
                raise SyncScanError(f"{_POSITION_COLUMNS[reader][0]}.{column}: {exc}") from exc
        return value

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        records = []
        for reader, (table, columns) in _POSITION_COLUMNS.items():
            names = ", ".join(column for column, _, _ in columns)
            try:
                rows = conn.execute(f"SELECT card_id, {names} FROM {table} ORDER BY card_id").fetchall()
            except sqlite3.Error as exc:
                raise SyncScanError(f"{table}: {exc}") from exc
            records += [(f"{card_key(card_id)}/{reader}", self._value(reader, rest)) for card_id, *rest in rows]
        return records

    def raw_digest(self, conn: sqlite3.Connection) -> str:
        return rows_digest(conn, *(
            f"SELECT card_id, {', '.join(column for column, _, _ in columns)} FROM {table} ORDER BY card_id"
            for table, columns in _POSITION_COLUMNS.values()))

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        card_id, reader = self._parse_key(key)
        table, columns = _POSITION_COLUMNS[reader]
        names = ", ".join(column for column, _, _ in columns)
        try:
            row = conn.execute(f"SELECT {names} FROM {table} WHERE card_id=?", (card_id,)).fetchone()
        except sqlite3.Error as exc:
            raise SyncScanError(f"{table}: {exc}") from exc
        return None if row is None else self._value(reader, row)

    def card_id(self, key: str) -> int | None:
        return self._parse_key(key)[0]

    def validate(self, key: str, value: Any) -> None:
        _, reader = self._parse_key(key)
        if value is None:
            return
        columns = _POSITION_COLUMNS[reader][1]
        if not isinstance(value, dict) or set(value) != {column for column, _, _ in columns}:
            raise ValueError("position value fields")
        for column, kind, check in columns:
            if not check(value[column]):
                raise ValueError(f"position {column}")
            if kind == "float" and normalized_float(value[column], column) != value[column]:
                raise ValueError(f"position {column} is not normalized")

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        card_id, reader = self._parse_key(key)
        table, columns = _POSITION_COLUMNS[reader]
        names = [column for column, _, _ in columns]
        updates = ", ".join(f"{column}=excluded.{column}" for column in names)
        conn.execute(f"INSERT INTO {table}(card_id, {', '.join(names)}) VALUES ({', '.join('?' * (len(names) + 1))}) "
                     f"ON CONFLICT(card_id) DO UPDATE SET {updates}",
                     (card_id, *(int(value[c]) if isinstance(value[c], bool) else value[c] for c in names)))

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        card_id, reader = self._parse_key(key)
        conn.execute(f"DELETE FROM {_POSITION_COLUMNS[reader][0]} WHERE card_id=?", (card_id,))


MAX_HIGHLIGHT_ID = 512
MAX_HIGHLIGHT_TEXT = 65_536
MAX_ANNOTATION_CHARS = 64 * 1024
MAX_RECTS = 2000


def _rects_ok(rects: Any) -> bool:
    return (isinstance(rects, list) and len(rects) <= MAX_RECTS and all(
        isinstance(rect, dict) and set(rect) == {"x", "y", "w", "h"}
        and all(_is_number(rect[axis]) for axis in "xywh") and rect["w"] > 0 and rect["h"] > 0
        for rect in rects))


def _note_ok(note: Any, note_html: Any) -> bool:
    if not isinstance(note, str) or not isinstance(note_html, str):
        return False
    try:
        return normalize_note(note, note_html) == (note, note_html)
    except ValueError:
        return False


class _HighlightFamily:
    """A reader's highlights: one record per highlight, keyed by card and encoded id."""

    name: str
    table: str
    columns: tuple[str, ...]

    def key(self, card_id: int, highlight_id: str) -> str:
        return f"{card_key(card_id)}/{self.name}:{quote(highlight_id, safe='')}"

    def _parse_key(self, key: str) -> tuple[int, str]:
        card_id, encoded = split_card_key(key, self.name)
        highlight_id = unquote(encoded)
        if not 0 < len(highlight_id) <= MAX_HIGHLIGHT_ID or self.key(card_id, highlight_id) != key:
            raise ValueError(f"not a {self.name} key: {key!r}")
        return card_id, highlight_id

    def _value(self, row: Sequence[Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _row(self, value: dict[str, Any]) -> tuple[Any, ...]:
        raise NotImplementedError

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        try:
            rows = conn.execute(f"SELECT card_id, id, {', '.join(self.columns)} FROM {self.table} "
                                "ORDER BY card_id, id").fetchall()
        except sqlite3.Error as exc:
            raise SyncScanError(f"{self.table}: {exc}") from exc
        return [(self.key(card_id, highlight_id), self._value(rest)) for card_id, highlight_id, *rest in rows]

    def raw_digest(self, conn: sqlite3.Connection) -> str:
        return rows_digest(conn, f"SELECT card_id, id, {', '.join(self.columns)} FROM {self.table} ORDER BY card_id, id")

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        card_id, highlight_id = self._parse_key(key)
        try:
            row = conn.execute(f"SELECT {', '.join(self.columns)} FROM {self.table} WHERE card_id=? AND id=?",
                               (card_id, highlight_id)).fetchone()
        except sqlite3.Error as exc:
            raise SyncScanError(f"{self.table}: {exc}") from exc
        return None if row is None else self._value(row)

    def card_id(self, key: str) -> int | None:
        return self._parse_key(key)[0]

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        card_id, highlight_id = self._parse_key(key)
        conn.execute(f"INSERT OR REPLACE INTO {self.table}(card_id, id, {', '.join(self.columns)}) "
                     f"VALUES ({', '.join('?' * (len(self.columns) + 2))})",
                     (card_id, highlight_id, *self._row(value)))

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        card_id, highlight_id = self._parse_key(key)
        conn.execute(f"DELETE FROM {self.table} WHERE card_id=? AND id=?", (card_id, highlight_id))


class PdfHighlightFamily(_HighlightFamily):
    name = "pdf_highlight"
    table = "pdf_highlights"
    columns = ("page", "color", "text", "note", "note_html", "rects", "annotation_json")
    fields = frozenset({"page", "color", "text", "note", "note_html", "rects", "annotation"})

    def _value(self, row: Sequence[Any]) -> dict[str, Any]:
        page, color, text, note, note_html, rects, annotation = row
        try:
            return {"page": int(page), "color": color, "text": text, "note": note, "note_html": note_html or "",
                    "rects": _round_floats(json.loads(rects or "[]")),
                    "annotation": _round_floats(json.loads(annotation or "{}"))}
        except (TypeError, ValueError) as exc:
            raise SyncScanError(f"pdf_highlights: unreadable row: {exc}") from exc

    def _row(self, value: dict[str, Any]) -> tuple[Any, ...]:
        return (value["page"], value["color"], value["text"], value["note"], value["note_html"],
                json.dumps(value["rects"]), json.dumps(value["annotation"]))

    def validate(self, key: str, value: Any) -> None:
        self._parse_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != self.fields:
            raise ValueError("pdf highlight fields")
        if not (_nonnegative_int(value["page"]) and value["page"] >= 1):
            raise ValueError("pdf highlight page")
        if not isinstance(value["color"], str) or normalize_highlight_color(value["color"],
                                                                             allow_snapshot=True) != value["color"]:
            raise ValueError("pdf highlight color")
        if not isinstance(value["text"], str) or len(value["text"]) > MAX_HIGHLIGHT_TEXT:
            raise ValueError("pdf highlight text")
        if not _note_ok(value["note"], value["note_html"]):
            raise ValueError("pdf highlight note")
        if not _rects_ok(value["rects"]) or _round_floats(value["rects"]) != value["rects"]:
            raise ValueError("pdf highlight rects")
        annotation = value["annotation"]
        if not isinstance(annotation, dict) or len(canonical_json(annotation)) > MAX_ANNOTATION_CHARS:
            raise ValueError("pdf highlight annotation")
        if _round_floats(annotation) != annotation:
            raise ValueError("pdf highlight annotation is not normalized")


class EpubHighlightFamily(_HighlightFamily):
    name = "epub_highlight"
    table = "epub_highlights"
    columns = ("section_index", "color", "text", "note", "note_html", "start_offset", "end_offset", "style")
    fields = frozenset(columns)

    def _value(self, row: Sequence[Any]) -> dict[str, Any]:
        section, color, text, note, note_html, start, end, style = row
        return {"section_index": int(section), "color": color, "text": text, "note": note,
                "note_html": note_html or "", "start_offset": int(start), "end_offset": int(end), "style": style}

    def _row(self, value: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(value[column] for column in self.columns)

    def validate(self, key: str, value: Any) -> None:
        self._parse_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != self.fields:
            raise ValueError("epub highlight fields")
        if not (_nonnegative_int(value["section_index"]) and _nonnegative_int(value["start_offset"])
                and _nonnegative_int(value["end_offset"]) and value["end_offset"] >= value["start_offset"]):
            raise ValueError("epub highlight position")
        if not isinstance(value["color"], str) or normalize_highlight_color(value["color"]) != value["color"]:
            raise ValueError("epub highlight color")
        if value["style"] not in ANNOTATION_STYLES:
            raise ValueError("epub highlight style")
        if not isinstance(value["text"], str) or len(value["text"]) > MAX_HIGHLIGHT_TEXT:
            raise ValueError("epub highlight text")
        if not _note_ok(value["note"], value["note_html"]):
            raise ValueError("epub highlight note")


FAMILIES: Mapping[str, Family] = {
    "priority": PriorityFamily(),
    "reader_bookmark": BookmarkFamily(),
    "reading_position": PositionFamily(),
    "pdf_highlight": PdfHighlightFamily(),
    "epub_highlight": EpubHighlightFamily(),
}


# --- What enters the exchange -------------------------------------------------
#
# Every table is classified. ``synced`` tables also list each column as synced
# or local. A test fails when a migration adds an unclassified table or column,
# so nothing enters or silently stays out of the exchange.

TABLE_CLASSIFICATION: Mapping[str, str] = {
    # MVP: synced as records.
    "priorities": "synced",
    "reader_bookmarks": "synced",
    "pdf_progress": "synced",
    "epub_progress": "synced",
    "video_progress": "synced",
    "web_progress": "synced",
    "pdf_highlights": "synced",
    "epub_highlights": "synced",
    "content_items": "synced",
    "document_links": "synced",
    "epub_connections": "synced",
    # Machinery, derived indexes, history, per-day usage, browser and UI memory.
    "schema_migrations": "local",
    "sqlite_sequence": "local",
    "import_journal": "local",
    "reconciliation_runs": "local",
    "pdf_annotation_sync": "local",
    "document_index_state": "local",
    "pdf_text_index": "local",
    "epub_text_index": "local",
    "note_ocr_index": "local",
    "reading_page_history": "local",
    "video_watch_history": "local",
    "topic_review_history": "local",
    "custom_schedule_review_history": "local",
    "stats": "local",
    "stats_daily_history": "local",
    "pdf_daily_limit_usage": "local",
    "epub_daily_limit_usage": "local",
    "browser_media_refs": "local",
    "browser_quick_tag_settings": "local",
    "browser_recent_tag_groups": "local",
    "browser_tag_colors": "local",
    "browser_website_tags": "local",
    "reviewer_recent_tags": "local",
    "sync_meta": "local",
    "sync_revisions": "local",
    "sync_baseline": "local",
    "sync_outbox": "local",
    "sync_inbox": "local",
    "sync_receipts": "local",
    "sync_conflicts": "local",
    "sync_peers": "local",
    "sync_seen_packs": "local",
    # Later: each needs its own contract first.
    "topic_schedule": "later",
    "topic_postpones": "later",
    "item_postpones": "later",
    "custom_schedule_rules": "later",
    "custom_schedule_rule_versions": "later",
    "knowledge_tree_nodes": "later",
    "knowledge_tree_postpone_presets": "later",
    "writing_progress": "later",
    "writing_word_stats": "later",
    "recording_links": "later",
    "pdf_card_sources": "later",
    "epub_card_sources": "later",
    "web_card_sources": "later",
    "pdf_daily_limits": "later",
    "epub_daily_limits": "later",
    "pdf_due_review_prompts": "later",
    "epub_due_review_prompts": "later",
    "document_library_books": "later",
    "document_library_lists": "later",
    "document_library_memberships": "later",
    "statistics_goals": "later",
    "reader_custom_colors": "later",
    "writing_links": "later",
    "document_coverage": "later",
}

#: Full-text search tables and their SQLite shadow tables: derived, local.
_LOCAL_TABLE_PREFIXES = ("pdf_text_fts", "epub_text_fts", "note_ocr_fts")

SYNCED_COLUMNS: Mapping[str, frozenset[str]] = {
    "priorities": frozenset({"card_id", "priority"}),
    "reader_bookmarks": frozenset({"id", "card_id", "reader_type", "label", "comment_text", "location_json",
                                   "created_at"}),
    "pdf_progress": frozenset({"card_id", "page", "scroll_ratio", "read_page", "read_anchor_json"}),
    "epub_progress": frozenset({"card_id", "section_index", "scroll_ratio", "is_finished", "read_section_index",
                                "read_anchor_json"}),
    "video_progress": frozenset({"card_id", "position"}),
    "web_progress": frozenset({"card_id", "url", "scroll_ratio", "bookmark_url", "bookmark_payload", "media_url",
                               "media_title", "media_seconds"}),
    "pdf_highlights": frozenset({"id", "card_id", "page", "color", "text", "note", "rects", "annotation_json",
                                 "note_html"}),
    "epub_highlights": frozenset({"id", "card_id", "section_index", "color", "text", "note", "start_offset",
                                  "end_offset", "note_html", "style"}),
    "content_items": frozenset({"content_id", "kind", "card_id", "note_id", "storage_key"}),
    "document_links": frozenset({"source_card_id", "source_content_id", "source_kind", "source_page", "quote",
                                 "target_card_id", "target_content_id", "target_page", "target_scroll", "source_y",
                                 "target_y", "connection_note", "source_passage", "target_passage"}),
    "epub_connections": frozenset({"source_card_id", "source_content_id", "source_section", "source_offset",
                                   "source_scroll", "target_card_id", "target_content_id", "target_section",
                                   "target_offset", "target_scroll", "quote", "source_passage", "target_passage"}),
}

#: Columns of synced tables that stay on the device: display preferences and
#: incidental timestamps.
LOCAL_COLUMNS: Mapping[str, frozenset[str]] = {
    "reader_bookmarks": frozenset({"updated_at"}),
    "pdf_progress": frozenset({"zoom", "appearance_mode"}),
    "epub_progress": frozenset({"font_scale", "appearance_mode"}),
    "web_progress": frozenset({"media_updated_at"}),
    "content_items": frozenset({"created_at", "updated_at"}),
    # The local row id: links are identified by their two ends.
    "document_links": frozenset({"id"}),
    "epub_connections": frozenset({"id"}),
}


def table_classification(table: str) -> str | None:
    """``synced``, ``local`` or ``later``; None for a table nobody classified."""
    if table in TABLE_CLASSIFICATION:
        return TABLE_CLASSIFICATION[table]
    if table.startswith(_LOCAL_TABLE_PREFIXES):
        return "local"
    return None
