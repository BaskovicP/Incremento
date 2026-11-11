"""Links between documents for sync: PDF page and passage links, and EPUB connections.

One record per link, ``card:<source card>/<family>:<id>``. The id is a hash of the link's two ends, not its local row
id: two computers that made, or received, the same link agree on it, and editing the note, quote or passages of a
link changes the record, not its identity. Moving a link's end makes a different link (the old one disappears and
the new one appears). A link whose source card is not here yet waits for it, as every card record does.

The tables hold card ids (the same on every computer, as Anki syncs the cards), the documents' content ids when they
have one, and the places and words at both ends. ``document_links`` also carries web and card sources that older
versions made; they travel the same way.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

try:
    from .document_passages import normalize_passage
    from .sync_records import SyncScanError, card_key, split_card_key
except ImportError:
    from document_passages import normalize_passage  # type: ignore[no-redef]
    from sync_records import SyncScanError, card_key, split_card_key  # type: ignore[no-redef]

_ID = re.compile(r"^[0-9a-f]{32}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ANKI_ID = 2**63 - 1


def _is_int(value: Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _is_number(value: Any, low: float, high: float) -> bool:
    return type(value) in (int, float) and value == value and low <= value <= high


class _LinkFamily:
    """Shared reading, writing and checking; a subclass names the table, its columns and its identity."""

    name: str
    table: str
    #: Columns carried in a record (everything but the local row id), in table order.
    columns: tuple[str, ...]
    #: The columns that make two links the same link.
    identity: tuple[str, ...]
    passages: tuple[tuple[str, str], ...] = ()  # (column, passage kind)

    def _identity_values(self, value: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(value[column] for column in self.identity)

    def _id(self, value: dict[str, Any]) -> str:
        encoded = json.dumps([self._identity_values(value)], separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]

    def key(self, value: dict[str, Any]) -> str:
        return f"{card_key(value['source_card_id'])}/{self.name}:{self._id(value)}"

    def _parse_key(self, key: str) -> tuple[int, str]:
        card_id, link_id = split_card_key(key, self.name)
        if not _ID.match(link_id) or f"{card_key(card_id)}/{self.name}:{link_id}" != key:
            raise ValueError(f"not a {self.name} key: {key!r}")
        return card_id, link_id

    def _value(self, row: Sequence[Any]) -> dict[str, Any]:
        return dict(zip(self.columns, row))

    def _rows(self, conn: sqlite3.Connection, where: str = "", args: tuple[Any, ...] = ()) -> list[Sequence[Any]]:
        try:
            return conn.execute(f"SELECT {', '.join(self.columns)} FROM {self.table}{where} ORDER BY id", args).fetchall()
        except sqlite3.Error as exc:
            raise SyncScanError(f"{self.table}: {exc}") from exc

    # --- the Family interface ------------------------------------------------------

    def scan(self, conn: sqlite3.Connection) -> Iterable[tuple[str, dict[str, Any]]]:
        found: dict[str, dict[str, Any]] = {}
        for row in self._rows(conn):
            value = self._value(row)
            found.setdefault(self.key(value), value)  # duplicates of one link collapse to the first
        return list(found.items())

    def read(self, conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
        card_id, _ = self._parse_key(key)
        for row in self._rows(conn, " WHERE source_card_id = ?", (card_id,)):
            value = self._value(row)
            if self.key(value) == key:
                return value
        return None

    def card_id(self, key: str) -> int | None:
        return self._parse_key(key)[0]

    def write(self, conn: sqlite3.Connection, key: str, value: dict[str, Any]) -> None:
        """Update the link with this identity, or add it. Runs inside the caller's transaction."""
        self._parse_key(key)
        match = " AND ".join(f"{column} = ?" for column in self.identity)
        others = [column for column in self.columns if column not in self.identity]
        cursor = conn.execute(
            f"UPDATE {self.table} SET {', '.join(f'{column} = ?' for column in others)} WHERE {match}",
            (*(value[column] for column in others), *self._identity_values(value)))
        if cursor.rowcount == 0:
            conn.execute(f"INSERT INTO {self.table}({', '.join(self.columns)}) VALUES ({', '.join('?' * len(self.columns))})",
                         tuple(value[column] for column in self.columns))

    def delete(self, conn: sqlite3.Connection, key: str) -> None:
        card_id, _ = self._parse_key(key)
        for row in self._rows(conn, " WHERE source_card_id = ?", (card_id,)):
            value = self._value(row)
            if self.key(value) == key:
                match = " AND ".join(f"{column} = ?" for column in self.identity)
                conn.execute(f"DELETE FROM {self.table} WHERE {match}", self._identity_values(value))

    def validate(self, key: str, value: Any) -> None:
        card_id, _ = self._parse_key(key)
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != set(self.columns):
            raise ValueError(f"{self.name} fields")
        self._validate(value)
        if value["source_card_id"] != card_id or self.key(value) != key:
            raise ValueError(f"{self.name} key does not match the link")
        for column, kind in self.passages:
            text = value[column]
            if not isinstance(text, str) or len(text) > 16000:
                raise ValueError(f"{self.name} passage")
            try:
                if normalize_passage(json.loads(text), kind) != json.loads(text):
                    raise ValueError(f"{self.name} passage")
            except json.JSONDecodeError as exc:
                raise ValueError(f"{self.name} passage") from exc

    def _validate(self, value: dict[str, Any]) -> None:
        raise NotImplementedError

    @staticmethod
    def _check_ends(value: dict[str, Any]) -> None:
        for side in ("source", "target"):
            if not _is_int(value[f"{side}_card_id"], 1, MAX_ANKI_ID):
                raise ValueError("link card id")
            content = value[f"{side}_content_id"]
            if content is not None and not (isinstance(content, str) and _SAFE_ID.match(content)):
                raise ValueError("link content id")


class DocumentLinkFamily(_LinkFamily):
    name = "document_link"
    table = "document_links"
    columns = ("source_card_id", "source_content_id", "source_kind", "source_page", "quote", "target_card_id",
               "target_content_id", "target_page", "target_scroll", "source_y", "target_y", "connection_note",
               "source_passage", "target_passage")
    identity = ("source_card_id", "source_kind", "source_page", "target_card_id", "target_page", "target_scroll")
    passages = (("source_passage", "pdf"), ("target_passage", "pdf"))

    def _validate(self, value: dict[str, Any]) -> None:
        self._check_ends(value)
        if value["source_kind"] not in ("pdf", "web", "card"):
            raise ValueError("link source kind")
        if not _is_int(value["source_page"], 0, MAX_ANKI_ID) or not _is_int(value["target_page"], 1, MAX_ANKI_ID):
            raise ValueError("link page")
        if not _is_number(value["target_scroll"], 0, 1):
            raise ValueError("link scroll")
        for column in ("source_y", "target_y"):
            if value[column] is not None and not _is_number(value[column], 0, 1):
                raise ValueError("link position")
        for column in ("quote", "connection_note"):
            if not isinstance(value[column], str) or len(value[column]) > (2000):
                raise ValueError(f"link {column}")
        if "\x00" in value["quote"]:
            raise ValueError("link quote")


class EpubConnectionFamily(_LinkFamily):
    name = "epub_connection"
    table = "epub_connections"
    columns = ("source_card_id", "source_content_id", "source_section", "source_offset", "source_scroll", "target_card_id",
               "target_content_id", "target_section", "target_offset", "target_scroll", "quote", "source_passage",
               "target_passage")
    identity = ("source_card_id", "source_section", "source_offset", "target_card_id", "target_section", "target_offset")
    passages = (("source_passage", "epub"), ("target_passage", "epub"))

    def _validate(self, value: dict[str, Any]) -> None:
        self._check_ends(value)
        for side in ("source", "target"):
            if not _is_int(value[f"{side}_section"], 0, 1_000_000) or not _is_int(value[f"{side}_offset"], -1, 50_000_000):
                raise ValueError("connection place")
            if not _is_number(value[f"{side}_scroll"], 0, 1):
                raise ValueError("connection scroll")
        if not isinstance(value["quote"], str) or len(value["quote"]) > 2000 or "\x00" in value["quote"]:
            raise ValueError("connection quote")


#: Both families, to add to the families a service runs with.
LINK_FAMILIES = {family.name: family for family in (DocumentLinkFamily(), EpubConnectionFamily())}

__all__ = ["DocumentLinkFamily", "EpubConnectionFamily", "LINK_FAMILIES"]
