"""Explicit, undoable bulk repair for syncable PDF context blocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PdfContextRebuildResult:
    scanned_notes: int
    changed_notes: int
    updated_contexts: int
    skipped_contexts: int
    changes: object | None = None


def rebuild_all_pdf_context_cards(
    collection,
    transform_field: Callable[[str], tuple[str, int, int]],
    *,
    undo_label: str,
    empty_changes_factory: Callable[[], object] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> PdfContextRebuildResult:
    """Rebuild PDF contexts on candidate notes using Anki's note API."""
    note_ids = collection.db.list(
        "SELECT id FROM notes WHERE flds LIKE ? ESCAPE '\\' ORDER BY id",
        "%incremento\\_open\\_pdf\\_ref:%",
    )
    changed_notes = 0
    notes_to_update = []
    updated_contexts = 0
    skipped_contexts = 0
    total_notes = len(note_ids)
    if progress is not None:
        progress(0, total_notes)

    for completed, note_id in enumerate(note_ids, start=1):
        note = collection.get_note(int(note_id))
        changed = False
        for index, raw_field in enumerate(list(note.fields)):
            field = str(raw_field or "")
            if "incremento_open_pdf_ref:" not in field:
                continue
            rebuilt, updated, skipped = transform_field(field)
            updated_contexts += max(0, int(updated))
            skipped_contexts += max(0, int(skipped))
            if rebuilt == field:
                continue
            note.fields[index] = rebuilt
            changed = True
        if changed:
            notes_to_update.append(note)
            changed_notes += 1
        if progress is not None:
            progress(completed, total_notes)

    if notes_to_update:
        undo_step = collection.add_custom_undo_entry(str(undo_label))
        collection.update_notes(notes_to_update)
        changes = collection.merge_undo_entries(undo_step)
    else:
        changes = empty_changes_factory() if empty_changes_factory is not None else None
    return PdfContextRebuildResult(
        scanned_notes=len(note_ids),
        changed_notes=changed_notes,
        updated_contexts=updated_contexts,
        skipped_contexts=skipped_contexts,
        changes=changes,
    )
