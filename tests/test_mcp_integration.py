"""Real Anki proves that MCP tag edits participate in native Undo/Redo."""

from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_mcp_tag_batch_uses_one_native_undo_and_rolls_back_stale_edits():
    result = subprocess.run([sys.executable, "-c", dedent('''
        import tempfile
        from pathlib import Path
        from anki.collection import Collection
        from backend.mcp_service import McpService, ToolError
        root = Path(tempfile.mkdtemp())
        col = Collection(str(root / "collection.anki2"))
        try:
            ids = []
            for front in ("One", "Two"):
                note = col.new_note(col.models.by_name("Basic"))
                note["Front"] = front
                note.tags = ["keep", "old"]
                col.add_note(note, col.decks.id("Default"))
                ids.append(str(note.id))
            svc = McpService(str(root), "A", "context", config={}, alive=lambda: True)
            def call(name, **args):
                return svc.call(col, name, dict(context_id="context", **args))
            revisions = {r["note_id"]: r["revision"] for r in call("read_notes", note_ids=ids)["items"]}
            result = call("update_tags", note_ids=ids, add=["topic"], remove=["old"], expected_revisions=revisions)
            assert result["changed"] == 2
            assert svc.changes.note
            assert all(set(col.get_note(int(n)).tags) == {"keep", "topic"} for n in ids)
            col.undo()
            assert all(set(col.get_note(int(n)).tags) == {"keep", "old"} for n in ids)
            col.redo()
            assert all(set(col.get_note(int(n)).tags) == {"keep", "topic"} for n in ids)
            try:
                call("update_tags", note_ids=ids, add=["wrong"], expected_revisions=revisions)
            except ToolError:
                pass
            else:
                raise AssertionError("stale edit accepted")
            assert all("wrong" not in col.get_note(int(n)).tags for n in ids)
            inverse = call("undo_change", undo_id=result["undo_id"])
            assert all(set(col.get_note(int(n)).tags) == {"keep", "old"} for n in ids)
            col.undo()
            assert all(set(col.get_note(int(n)).tags) == {"keep", "topic"} for n in ids)
            col.redo()
            call("undo_change", undo_id=inverse["undo_id"])
            fresh = call("read_notes", note_ids=[ids[0]])["items"][0]
            edited = call("update_note_fields", note_id=ids[0], fields={"Front": "A clearer question"},
                          expected_revision=fresh["content_revision"])
            assert col.get_note(int(ids[0]))["Front"] == "A clearer question"
            col.undo()
            assert col.get_note(int(ids[0]))["Front"] == "One"
            col.redo()
            call("undo_change", undo_id=edited["undo_id"])
            assert col.get_note(int(ids[0]))["Front"] == "One"
            # A bounded native Anki search also works with the MCP candidate filter.
            assert len(call("search", scope="cards", anki_query="tag:topic")["items"]) == 2
            cloze = col.new_note(col.models.by_name("Cloze"))
            cloze["Text"] = "{{c1::First}} and {{c2::Second}}"
            cloze.tags = ["Parent", "Parent::Child"]
            col.add_note(cloze, col.decks.id("Default"))
            second_card = col.db.scalar("select id from cards where nid=? and ord=1", cloze.id)
            col.remove_cards_and_orphaned_notes([second_card])
            card_ids = col.db.list("select id from cards where nid=?", cloze.id)
            fresh = call("read_notes", note_ids=[str(cloze.id)])["items"][0]
            tagged = call("update_tags", note_ids=[str(cloze.id)], add=["topic"], remove=["Parent"],
                          expected_revisions={str(cloze.id): fresh["revision"]})
            assert col.db.list("select id from cards where nid=?", cloze.id) == card_ids, 'Tag edits regenerated a deleted cloze card'
            assert set(col.get_note(cloze.id).tags) == {"Parent::Child", "topic"}, 'Literal tag removal deleted descendants'
            call("undo_change", undo_id=tagged["undo_id"])
            assert set(col.get_note(cloze.id).tags) == {"Parent", "Parent::Child"}
            assert col.db.list("select id from cards where nid=?", cloze.id) == card_ids
            try:
                call("update_note_fields", note_id=str(cloze.id), fields={"Text": "{{c1::First}} and {{c3::Third}}"},
                     expected_revision=fresh["content_revision"])
            except ToolError as error:
                assert 'card' in str(error).lower()
            else:
                raise AssertionError('Accepted a text edit with irreversible card generation')
            assert col.get_note(cloze.id)["Text"] == "{{c1::First}} and {{c2::Second}}"
            assert col.db.list("select id from cards where nid=?", cloze.id) == card_ids
            print("native MCP undo: ok")
        finally:
            col.close()
    ''')], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "native MCP undo: ok" in result.stdout
