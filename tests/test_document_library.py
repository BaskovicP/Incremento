"""Check the bookshelf projection against a real, temporary Anki collection."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_document_projection_matches_anki_fields_cards_and_refreshes():
    script = dedent(r"""
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from anki.collection import Collection
        from backend.document_library import load_document_notes

        with TemporaryDirectory(prefix="incremento-document-library-") as root:
            col = Collection(str(Path(root) / "collection.anki2"))
            try:
                model = col.models.by_name("Basic (and reversed card)")
                note = col.new_note(model)
                note["Front"] = "Document title"
                note["Back"] = "source.pdf"
                note.tags = ["Reading", "Study::Book"]
                col.add_note(note, col.decks.id("Default"))
                cards = col.find_cards(f"nid:{note.id}")
                assert len(cards) == 2
                col.sched.suspend_cards(cards)

                def check_projection():
                    rows = list(load_document_notes(col, [note.id, note.id, 999]))
                    assert len(rows) == 1
                    row = rows[0]
                    live_note = col.get_note(note.id)
                    assert row.card_id == cards[0] == min(cards)
                    assert row.note_id == note.id
                    assert row.fields == dict(live_note.items())
                    assert row.first_field == live_note.fields[0]
                    assert row.tags == tuple(live_note.tags)

                check_projection()
                note["Front"] = "Updated title"
                note.tags = ["NewTag"]
                col.update_note(note)
                check_projection()
                # Field ordinals change when users reorder an existing type.
                model = col.models.get(note.mid)
                col.models.reposition_field(model, model["flds"][1], 0)
                col.models.save(model)
                check_projection()
                assert list(load_document_notes(col, [])) == []
                col.remove_notes([note.id])
                assert list(load_document_notes(col, [note.id])) == []
            finally:
                col.close()
        print("document projection: ok")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "document projection: ok" in result.stdout
