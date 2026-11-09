"""What sync needs to know about the Anki collection.

See docs/architecture/shared-folder-sync.md §7. Takes a query function with
the shape of Anki's ``col.db.all(sql, *args)`` so this module imports
neither Anki nor Qt and can be tested against a plain SQLite collection.

Anki's sync (rslib/src/sync/collection): a locally changed card has
``usn = -1``; uploading gives it the server usn of that sync, and afterwards
the collection's own usn is that server usn + 1.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

try:
    from .sync_records import CardRef
except ImportError:
    from sync_records import CardRef  # type: ignore[no-redef]

Query = Callable[..., Sequence[Sequence[Any]]]

#: Stay well below SQLite's bound-parameter limit.
MAX_SQL_VARIABLES = 500


def collection_usn(query: Query) -> int:
    """The collection's usn: the server usn of its last completed sync, plus one."""
    return int(query("SELECT usn FROM col")[0][0])


def collection_scm(query: Query) -> int:
    """The collection's schema-modified time; full syncs and schema changes alter it."""
    return int(query("SELECT scm FROM col")[0][0])


def card_refs(query: Query, card_ids: Iterable[int]) -> dict[int, CardRef]:
    """References for the cards present in the collection; absent ids are left out."""
    ids = sorted({int(card_id) for card_id in card_ids})
    if not ids:
        return {}
    usn, scm = query("SELECT usn, scm FROM col")[0]
    refs: dict[int, CardRef] = {}
    for start in range(0, len(ids), MAX_SQL_VARIABLES):
        chunk = ids[start:start + MAX_SQL_VARIABLES]
        marks = ",".join("?" for _ in chunk)
        for card_id, note_id, guid, card_usn in query(
                f"SELECT c.id, c.nid, n.guid, c.usn FROM cards c JOIN notes n ON n.id = c.nid WHERE c.id IN ({marks})",
                *chunk):
            refs[int(card_id)] = CardRef(int(card_id), int(note_id), str(guid),
                                         uploaded_usn=None if int(card_usn) < 0 else int(card_usn),
                                         collection_usn=int(usn), collection_scm=int(scm))
    return refs


def deleted_after(card: dict[str, Any], sender_anki_usn: int | None, *, sender_anki_scm: int | None = None,
                  receiver_scm: int | None = None) -> int | None:
    """The collection usn beyond which a receiver must already have this card.

    A receiver whose collection usn is greater than the result, and which
    still lacks the card, has it deleted. None means it cannot be decided yet.
    Usns are only compared within one collection schema (``scm``): across a
    full sync or schema change the numbering may not line up, so the card
    keeps waiting rather than risk declaring it deleted.
    """
    captured_scm = card.get("collection_scm")
    if captured_scm is None or captured_scm != receiver_scm:
        return None
    uploaded = card.get("uploaded_usn")
    if uploaded is not None:
        return int(uploaded)
    captured_at = card.get("collection_usn")
    if (captured_at is not None and sender_anki_usn is not None and sender_anki_scm == captured_scm
            and sender_anki_usn > captured_at):
        # The sender synced after capturing; that sync uploaded the card at server usn sender_anki_usn - 1.
        return sender_anki_usn - 1
    return None
