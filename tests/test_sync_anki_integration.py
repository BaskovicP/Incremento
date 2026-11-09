"""Card references read from a real Anki collection (clean subprocess, like the other *_anki_integration tests)."""
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]


def test_card_refs_and_collection_usn_match_a_real_collection():
    script = dedent(r"""
        import sys, tempfile, os
        sys.path.insert(0, os.path.join(sys.argv[1], "backend"))
        from anki.collection import Collection
        import sync_anki

        with tempfile.TemporaryDirectory() as root:
            col = Collection(os.path.join(root, "collection.anki2"))
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"], note["Back"] = "question", "answer"
            col.add_note(note, col.decks.id("Default"))
            [card_id] = note.card_ids()

            refs = sync_anki.card_refs(col.db.all, [card_id, 999])
            usn = sync_anki.collection_usn(col.db.all)

            assert list(refs) == [card_id], refs
            ref = refs[card_id]
            assert (ref.note_id, ref.guid) == (note.id, note.guid), ref
            assert ref.uploaded_usn is None, "a card that was never synced is not uploaded"
            assert ref.collection_usn == usn == col.db.scalar("select usn from col")
            col.close()
        print("ok")
    """)
    result = subprocess.run([sys.executable, "-c", script, str(ROOT)], cwd=ROOT, capture_output=True, text=True,
                            timeout=120, env={**os.environ, "PYTHONPATH": ""})
    assert result.returncode == 0 and result.stdout.strip().endswith("ok"), result.stdout + result.stderr
