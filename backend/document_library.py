"""Batched, read-only document metadata from the operation's Anki collection."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass


_NOTE_BATCH_SIZE = 900


@dataclass(frozen=True)
class DocumentNote:
    note_id: int
    card_id: int
    fields: dict[str, str]
    first_field: str
    tags: tuple[str, ...]


def load_document_notes(col, note_ids: Iterable[int]) -> Iterator[DocumentNote]:
    """Project live document notes without constructing a Note/Card per entry.

    Search remains owned by the caller. Include suspended cards, omit notes
    without cards, and choose the lowest card id when a note has multiple cards.
    Field definitions are cached only for this read, so later schema changes
    and profile switches cannot reuse stale metadata.
    """
    ids = list(dict.fromkeys(int(note_id) for note_id in note_ids))
    field_maps: dict[int, dict[str, int]] = {}
    for offset in range(0, len(ids), _NOTE_BATCH_SIZE):
        chunk = ids[offset:offset + _NOTE_BATCH_SIZE]
        placeholders = ",".join("?" for _ in chunk)
        rows = col.db.all(
            "SELECT n.id, n.mid, n.flds, n.tags, MIN(c.id) "
            "FROM notes n JOIN cards c ON c.nid = n.id "
            f"WHERE n.id IN ({placeholders}) GROUP BY n.id",
            *chunk,
        )
        for note_id, model_id, raw_fields, raw_tags, card_id in rows:
            if model_id not in field_maps:
                model = col.models.get(model_id)
                field_maps[model_id] = {
                    field["name"]: int(field["ord"])
                    for field in (model or {}).get("flds", [])
                }
            field_map = field_maps[model_id]
            if not field_map:
                continue
            values = str(raw_fields or "").split("\x1f")
            yield DocumentNote(
                note_id=int(note_id),
                card_id=int(card_id),
                fields={name: values[index] for name, index in field_map.items()
                        if 0 <= index < len(values)},
                first_field=values[0],
                tags=tuple(str(raw_tags or "").split()),
            )
