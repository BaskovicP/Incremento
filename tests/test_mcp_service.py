"""The MCP can read bounded live data and make exact, profile-scoped edits."""

from types import SimpleNamespace
from pathlib import Path
import sqlite3

import pytest

import db
import document_lists
from mcp_service import McpService, ToolError


class Collection:
    def __init__(self):
        self.sql = sqlite3.connect(":memory:")
        self.sql.executescript("CREATE TABLE notes(id INTEGER PRIMARY KEY, mid INTEGER, flds TEXT, tags TEXT);"
                               "CREATE TABLE cards(id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER);")
        self.db = SimpleNamespace(all=lambda sql, *args: self.sql.execute(sql, args).fetchall())
        self.models = SimpleNamespace(get=lambda mid: {
            "name": "Incremento PDF" if mid == 2 else "Basic",
            "type": 0, "tmpls": [{"ord": 0}],
            "flds": [{"name": name, "ord": i} for i, name in enumerate(
                ("Title", "PDF_Filename") if mid == 2 else ("Front", "Back"))]})
        self.updated = []
        self.tags = SimpleNamespace(bulk_add=lambda ids, tags: self._tags(ids, tags, True),
                                    bulk_remove=lambda ids, tags: self._tags(ids, tags, False))
        self.decks = SimpleNamespace(get=lambda did: {"id": did, "name": "Default", "dyn": 0})

    def add(self, cid, nid, title, *, filename=None, tags=" keep "):
        self.sql.execute("INSERT OR IGNORE INTO notes VALUES (?,?,?,?)",
                         (nid, 2 if filename else 1, title + "\x1f" + (filename or "Answer"), tags))
        self.sql.execute("INSERT INTO cards VALUES (?,?,1,0,0)", (cid, nid))

    def get_note(self, nid):
        row = self.sql.execute("SELECT mid,flds,tags FROM notes WHERE id=?", (nid,)).fetchone()
        if row is None:
            raise KeyError(nid)
        model = self.models.get(row[0])
        class Note:
            def __init__(self):
                self.id, self.tags, self.fields = nid, row[2].split(), row[1].split('\x1f')
            def note_type(self):
                return model
            def items(self):
                return [(field['name'], self.fields[i]) for i, field in enumerate(model['flds'])]
            def __getitem__(self, key):
                return dict(self.items())[key]
            def __setitem__(self, key, value):
                self.fields[next(i for i, field in enumerate(model['flds']) if field['name'] == key)] = value
        return Note()

    def get_card(self, cid):
        row = self.sql.execute("SELECT nid,did,odid FROM cards WHERE id=?", (cid,)).fetchone()
        if row is None:
            raise KeyError(cid)
        return SimpleNamespace(id=cid, nid=row[0], did=row[1], odid=row[2], note=lambda: self.get_note(row[0]))

    def update_notes(self, notes):
        self.updated.append([n.id for n in notes])
        for note in notes:
            self.sql.execute("UPDATE notes SET tags=?,flds=? WHERE id=?",
                (" " + " ".join(note.tags) + " ", '\x1f'.join(note.fields), note.id))
        return SimpleNamespace(note=True)

    def add_custom_undo_entry(self, name):
        self._tag_pending = []
        return 1

    def merge_undo_entries(self, entry):
        self.updated.append(list(dict.fromkeys(self._tag_pending)))
        return SimpleNamespace(note=True)

    def _tags(self, ids, tags, add):
        values = tags.split()
        for nid in ids:
            current = self.get_note(nid).tags
            if add:
                current += [tag for tag in values if tag.casefold() not in {value.casefold() for value in current}]
            else:
                current = [tag for tag in current if tag.casefold() not in {value.casefold() for value in values}]
            self.sql.execute("UPDATE notes SET tags=? WHERE id=?", (' '+ ' '.join(current)+' ', nid))
            self._tag_pending.append(nid)


@pytest.fixture
def service(tmp_path):
    col = Collection()
    col.add(11, 1, "<b>Decision making</b>", filename="one.pdf")
    col.add(12, 2, "Memory", filename="two.pdf")
    col.add(13, 3, "A decision card")
    col.add(14, 3, "A decision card")
    folder = tmp_path / "user_files" / "A" / "pdfs"
    folder.mkdir(parents=True)
    (folder / "one.pdf").write_bytes(b"%PDF-synthetic")
    (folder / "two.pdf").write_bytes(b"%PDF-synthetic")
    obj = McpService(str(tmp_path), "A", "session-A", config={}, alive=lambda: True)
    yield obj, col
    db.close_connection()
    col.sql.close()


def call(service, col, tool, **args):
    return service.call(col, tool, {"context_id": "session-A", **args})


def test_book_search_has_a_continuation_and_stable_document_identity(service):
    svc, col = service
    first = call(svc, col, "search", scope="books", limit=1)
    assert [(r["card_id"], r["title"], r["book_id"]) for r in first["items"]] == [
        ("11", "Decision making", "pdf:one.pdf")]
    second = call(svc, col, "search", scope="books", limit=1, cursor=first["next_cursor"])
    assert [r["card_id"] for r in second["items"]] == ["12"]
    assert second["next_cursor"] is None
    assert call(svc, col, "search", scope="cards", query="decision")["items"][0]["card_id"] == "11"


def test_document_reads_page_through_long_indexed_text_without_writes(service):
    svc, col = service
    db.replace_pdf_text_index(svc.addon_dir, "A", 11, ["0123456789", "Next page"])
    first = call(svc, col, "read_document", card_id="11", max_chars=6)
    assert first["text"] == "012345"
    assert first["position"] == 1
    second = call(svc, col, "read_document", card_id="11", max_chars=6, cursor=first["next_cursor"])
    assert second["text"] == "6789"
    third = call(svc, col, "read_document", card_id="11", cursor=second["next_cursor"])
    assert third["text"] == "Next page"
    assert third["next_cursor"] is None
    assert col.updated == []


def test_document_search_returns_evidence_and_does_not_claim_full_library_coverage(service):
    svc, col = service
    db.replace_pdf_text_index(svc.addon_dir, "A", 11, ["Judgment and decision making"])
    result = call(svc, col, "search", scope="document_text", query="decision")
    assert result["items"][0]["card_id"] == "11"
    assert result["items"][0]["position"] == 1
    assert "decision" in result["items"][0]["text"]
    assert result["coverage"] == "existing_indexes_only"
    assert call(svc, col, "search", scope="document_text", query="missing")["items"] == []


def test_add_books_preserves_other_memberships_and_acquisition_notes(service):
    svc, col = service
    old = document_lists.create_document_list(svc.addon_dir, "A", "Existing")
    document_lists.save_document_details(svc.addon_dir, "A", "pdf", "one.pdf",
        {"reason": "Read chapter 2", "source": "Friend", "list_ids": [old]})
    new = call(svc, col, "create_list", name="Decisions")["list_id"]
    result = call(svc, col, "update_list_members", list_id=new, add=["pdf:one.pdf", "pdf:one.pdf"], card_ids=["11"])
    assert result["changed"] == 1
    assert call(svc, col, "update_list_members", list_id=new, add=["pdf:one.pdf"], card_ids=["11"])["changed"] == 0
    details = document_lists.load_document_library(svc.addon_dir, "A")["books"][("pdf", "one.pdf")]
    assert details == {"reason": "Read chapter 2", "source": "Friend", "list_ids": [old, int(new)]}
    assert document_lists.load_document_library(svc.addon_dir, "B")["lists"] == []


def test_invalid_book_batch_does_not_partially_update_memberships(service):
    svc, col = service
    lid = call(svc, col, "create_list", name="Books")["list_id"]
    with pytest.raises(ToolError):
        call(svc, col, "update_list_members", list_id=lid, add=["pdf:one.pdf", "pdf:missing.pdf"], card_ids=["11"])
    assert document_lists.load_document_library(svc.addon_dir, "A")["books"] == {}


def test_tags_update_each_note_once_and_reject_stale_previews(service):
    svc, col = service
    preview = call(svc, col, "read_notes", note_ids=["3"])
    revision = preview["items"][0]["revision"]
    result = call(svc, col, "update_tags", note_ids=["3", "3"], add=["topic"], remove=["KEEP"],
                  expected_revisions={"3": revision})
    assert result["changed"] == 1
    assert col.get_note(3).tags == ["topic"]
    assert col.updated == [[3]]
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "update_tags", note_ids=["3"], add=["new"], expected_revisions={"3": revision})
    assert col.get_note(3).tags == ["topic"]


@pytest.mark.parametrize("args", [{"add": ["bad tag"]}, {"remove": ["*"]}, {"add": ["x\x00y"]},
                                    {"add": ["x"] * 65}, {"note_ids": [True]}])
def test_invalid_tag_batch_never_writes(service, args):
    svc, col = service
    revision = call(svc, col, "read_notes", note_ids=["3"])["items"][0]["revision"]
    with pytest.raises(ToolError):
        call(svc, col, "update_tags", **({"note_ids": ["3"], "add": ["tag"],
             "expected_revisions": {"3": revision}} | args))
    assert col.updated == []


def test_profile_generation_and_unknown_fields_fail_closed(service):
    svc, col = service
    with pytest.raises(ToolError):
        svc.call(col, "create_list", {"context_id": "other", "name": "Wrong profile"})
    with pytest.raises(ToolError):
        call(svc, col, "create_list", name="Books", arbitrary_sql="DROP TABLE notes")
    assert document_lists.get_document_lists(svc.addon_dir, "A") == []


def test_text_search_reaches_late_passages_and_all_highlights_on_a_page(service):
    svc, col = service
    db.replace_pdf_text_index(svc.addon_dir, "A", 11, ["x" * 20000 + " Late target"])
    assert "Late target" in call(svc, col, "search", scope="document_text", query="Late target")["items"][0]["text"]
    conn = db.get_connection(svc.addon_dir, "A")
    conn.executemany("INSERT INTO pdf_highlights(id,card_id,page,text) VALUES (?,11,1,?)",
                     [("one", "first target"), ("two", "second target")])
    conn.commit()
    first = call(svc, col, "search", scope="highlights", query="target", limit=1)
    second = call(svc, col, "search", scope="highlights", query="target", limit=1, cursor=first["next_cursor"])
    assert [first["items"][0]["text"], second["items"][0]["text"]] == ["first target ", "second target "]


def test_missing_or_replaced_document_cannot_return_old_indexed_content(service):
    svc, col = service
    db.replace_pdf_text_index(svc.addon_dir, "A", 11, ["private stale content"])
    path = Path(svc.addon_dir) / "user_files" / "A" / "pdfs" / "one.pdf"
    path.unlink()
    with pytest.raises(ToolError, match="unavailable"):
        call(svc, col, "read_document", card_id="11")
    assert call(svc, col, "search", scope="document_text", query="private")["items"] == []


def test_changed_signature_and_symlinked_documents_fail_closed(service):
    svc, col = service
    db.replace_pdf_text_index(svc.addon_dir, "A", 11, ["old text"])
    conn = db.get_connection(svc.addon_dir, "A")
    conn.execute("INSERT INTO document_index_state(kind,card_id,source_mtime_ns,source_size,status) VALUES ('pdf',11,1,1,'ready')")
    conn.commit()
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "read_document", card_id="11")
    path = Path(svc.addon_dir) / "user_files" / "A" / "pdfs" / "one.pdf"
    path.unlink()
    path.symlink_to(Path(svc.addon_dir) / "private.txt")
    with pytest.raises(ToolError):
        call(svc, col, "read_document", card_id="11")


def test_one_stale_note_rejects_the_whole_tag_batch_before_native_write(service):
    svc, col = service
    revisions = {r["note_id"]: r["revision"] for r in call(svc, col, "read_notes", note_ids=["1", "3"])["items"]}
    revisions["3"] = "stale"
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "update_tags", note_ids=["1", "3"], add=["topic"], expected_revisions=revisions)
    assert col.updated == []
    assert col.get_note(1).tags == ["keep"]
    assert col.get_note(3).tags == ["keep"]


def test_epub_sections_use_one_based_positions_and_bound_each_chunk(service):
    svc, col = service
    original = col.models.get
    col.models.get = lambda mid: {"name": "Incremento EPUB", "flds": [
        {"name": "Title", "ord": 0}, {"name": "EPUB_Filename", "ord": 1}]} if mid == 3 else original(mid)
    col.sql.execute("INSERT INTO notes VALUES (4,3,?,?)", ("An EPUB\x1fbook.epub", " keep "))
    col.sql.execute("INSERT INTO cards VALUES (15,4,1,0,0)")
    folder = Path(svc.addon_dir) / "user_files" / "A" / "epubs"
    folder.mkdir()
    (folder / "book.epub").write_bytes(b"synthetic")
    db.replace_epub_text_index(svc.addon_dir, "A", 15, [("Start", "0123456789"), ("End", "finish")])
    first = call(svc, col, "read_document", card_id="15", max_chars=6)
    assert (first["kind"], first["position"], first["text"]) == ("epub", 1, "012345")
    second = call(svc, col, "read_document", card_id="15", cursor=first["next_cursor"])
    assert (second["position"], second["text"]) == (1, "6789")
    last = call(svc, col, "read_document", card_id="15", cursor=second["next_cursor"])
    assert (last["position"], last["text"], last["next_cursor"]) == (2, "finish", None)


def test_priority_edits_validate_every_live_card_before_a_profile_scoped_batch(service):
    svc, col = service
    assert call(svc, col, "get_priorities", card_ids=["11"])["items"] == [{"card_id": "11", "priority": 50.0}]
    call(svc, col, "set_priorities", card_ids=["11", "13"], priority=17.25)
    with pytest.raises(ToolError):
        call(svc, col, "set_priorities", card_ids=["11", "999"], priority=90)
    assert call(svc, col, "get_priorities", card_ids=["11"])["items"][0]["priority"] == 17.25
    assert db.get_connection(svc.addon_dir, "B").execute("SELECT count(*) FROM priorities").fetchone()[0] == 0


def test_book_details_edit_preserves_memberships_and_rejects_stale_notes(service):
    svc, col = service
    lid = document_lists.create_document_list(svc.addon_dir, "A", "Keep")
    document_lists.save_document_details(svc.addon_dir, "A", "pdf", "one.pdf",
                                        {"reason": "Old", "source": "Friend", "list_ids": [lid]})
    before = call(svc, col, "get_book_details", card_id="11")
    after = call(svc, col, "update_book_details", card_id="11", reason="Read chapter 3", source="Library",
                 expected_revision=before["revision"])
    assert after["list_ids"] == [str(lid)]
    assert after["reason"] == "Read chapter 3"
    with pytest.raises(ToolError):
        call(svc, col, "update_book_details", card_id="11", reason="Wrong", expected_revision=before["revision"])


def test_bookmarks_are_paginated_scoped_and_support_comments_and_removal(service):
    svc, col = service
    bookmark = call(svc, col, "add_bookmark", card_id="11", location={"page": 3}, label="Important")
    call(svc, col, "update_bookmark_comment", card_id="11", bookmark_id=bookmark["id"], comment="Return here")
    page = call(svc, col, "get_bookmarks", card_id="11", limit=1)
    assert page["items"][0]["comment_text"] == "Return here"
    assert page["items"][0]["location"] == {"page": 3}
    assert call(svc, col, "get_bookmarks", card_id="12")["items"] == []
    call(svc, col, "delete_bookmark", card_id="11", bookmark_id=bookmark["id"])
    assert call(svc, col, "get_bookmarks", card_id="11")["items"] == []


def test_annotation_note_and_color_edits_keep_geometry_and_reject_stale_revision(service):
    svc, col = service
    import pdf_highlights
    pdf_highlights.add_highlight(svc.addon_dir, "A", 11,
        {"id": "passage", "page": 2, "text": "Original", "note": "Old note", "rects": [[1, 2, 3, 4]]})
    before = call(svc, col, "get_highlights", card_id="11")["items"][0]
    call(svc, col, "update_highlight", card_id="11", highlight_id="passage", note="New note", color="green",
         expected_revision=before["revision"])
    saved = pdf_highlights.load_highlights(svc.addon_dir, "A", 11)[0]
    assert (saved["note"], saved["color"], saved["text"], saved["rects"]) == (
        "New note", "green", "Original", [[1, 2, 3, 4]])
    with pytest.raises(ToolError):
        call(svc, col, "delete_highlight", card_id="11", highlight_id="passage", expected_revision=before["revision"])
    assert len(pdf_highlights.load_highlights(svc.addon_dir, "A", 11)) == 1


def test_tree_edits_are_card_backed_and_cycle_rejection_preserves_structure(service):
    svc, col = service
    before = call(svc, col, "get_knowledge_tree")
    call(svc, col, "update_knowledge_tree", action="add", card_id="11", expected_revision=before["revision"])
    before = call(svc, col, "get_knowledge_tree")
    call(svc, col, "update_knowledge_tree", action="add", card_id="13", parent_card_id="11",
         expected_revision=before["revision"])
    before = call(svc, col, "get_knowledge_tree")
    with pytest.raises(ToolError):
        call(svc, col, "update_knowledge_tree", action="move", card_id="11", parent_card_id="13",
             expected_revision=before["revision"])
    after = call(svc, col, "get_knowledge_tree")
    assert after == before
    assert [(item["card_id"], item["parent_card_id"]) for item in after["items"]] == [("11", None), ("13", "11")]


def test_statistics_and_goals_use_the_existing_profile_store(service):
    svc, col = service
    call(svc, col, "set_daily_goals", cards=25, pages=10, minutes=30)
    result = call(svc, col, "get_statistics", days=3, end_date="2026-10-30")
    assert result["goals"] == {"cards": 25.0, "pages": 10.0, "minutes": 30.0}
    assert len(result["history"]) == 3
    import statistics as stats
    assert stats.get_statistics_goals(svc.addon_dir, "B") == {"cards": 0.0, "pages": 0.0, "minutes": 0.0}


def test_custom_schedule_rules_keep_monotonic_revisions_across_clear_and_recreate(service):
    svc, col = service
    first = call(svc, col, "set_custom_schedule", card_id="13", mode="one_time", interval_value=5,
                 interval_unit="days", expected_revision=0)
    call(svc, col, "clear_custom_schedule", card_id="13", expected_revision=first["revision"])
    second = call(svc, col, "set_custom_schedule", card_id="13", mode="fixed_repeat", interval_value=2,
                  interval_unit="weeks", expected_revision=0)
    assert second["revision"] > first["revision"]
    assert call(svc, col, "get_custom_schedules", card_ids=["13"])["items"][0]["rule"]["interval_unit"] == "weeks"


def test_note_field_edits_use_content_revisions_and_preserve_tags(service):
    svc, col = service
    before = call(svc, col, "read_notes", note_ids=["3"])["items"][0]
    result = call(svc, col, "update_note_fields", note_id="3", fields={"Front": "A clearer question"},
                  expected_revision=before["content_revision"])
    assert result["changed"] is True
    assert col.get_note(3)["Front"] == "A clearer question"
    assert col.get_note(3).tags == ["keep"]
    with pytest.raises(ToolError):
        call(svc, col, "update_note_fields", note_id="3", fields={"Front": "Overwrite"},
             expected_revision=before["content_revision"])


def test_capability_inventory_lists_direct_and_interactive_workflows(service):
    svc, col = service
    capabilities = call(svc, col, "get_capabilities")
    assert {"priorities", "bookmarks", "annotations", "knowledge_tree", "statistics", "custom_schedules"} <= set(capabilities["direct"])
    assert "imports" in capabilities["direct"]
    assert "study_sessions" in capabilities["interactive"]
    assert capabilities["native_actions_tool"] == "list_actions"


@pytest.mark.parametrize("kind", ["list", "priority", "bookmark", "annotation", "tree", "goals", "rule", "tags", "fields"])
def test_each_mcp_data_change_can_be_undone_and_redone_without_cross_profile_writes(service, kind):
    svc, col = service
    if kind == "list":
        result = call(svc, col, "create_list", name="Undo me")
        read = lambda: call(svc, col, "get_lists")["items"]
        assert len(read()) == 1
        is_original = lambda: not read()
    elif kind == "priority":
        result = call(svc, col, "set_priorities", card_ids=["11"], priority=10)
        read = lambda: call(svc, col, "get_priorities", card_ids=["11"])["items"][0]["priority"]
        is_original = lambda: read() == 50
    elif kind == "bookmark":
        result = call(svc, col, "add_bookmark", card_id="11", location={"page": 2})
        read = lambda: call(svc, col, "get_bookmarks", card_id="11")["items"]
        is_original = lambda: not read()
    elif kind == "annotation":
        import pdf_highlights
        pdf_highlights.add_highlight(svc.addon_dir, "A", 11, {"id": "undo-hl", "text": "Quote", "note": "Old"})
        read = lambda: call(svc, col, "get_highlights", card_id="11")["items"][0]
        result = call(svc, col, "update_highlight", card_id="11", highlight_id="undo-hl", note="New",
                      expected_revision=read()["revision"])
        is_original = lambda: read()["note"] == "Old"
    elif kind == "tree":
        read = lambda: call(svc, col, "get_knowledge_tree")
        result = call(svc, col, "update_knowledge_tree", action="add", card_id="11", expected_revision=read()["revision"])
        is_original = lambda: not read()["items"]
    elif kind == "goals":
        result = call(svc, col, "set_daily_goals", cards=25)
        read = lambda: call(svc, col, "get_statistics", days=1)["goals"]["cards"]
        is_original = lambda: read() == 0
    elif kind == "rule":
        result = call(svc, col, "set_custom_schedule", card_id="13", mode="one_time", interval_value=5,
                      interval_unit="days", expected_revision=0)
        read = lambda: call(svc, col, "get_custom_schedules", card_ids=["13"])["items"][0]["rule"]
        is_original = lambda: read() is None
    elif kind == "tags":
        before = call(svc, col, "read_notes", note_ids=["3"])["items"][0]
        result = call(svc, col, "update_tags", note_ids=["3"], add=["topic"], expected_revisions={"3": before["revision"]})
        read = lambda: col.get_note(3).tags
        is_original = lambda: read() == ["keep"]
    else:
        before = call(svc, col, "read_notes", note_ids=["3"])["items"][0]
        result = call(svc, col, "update_note_fields", note_id="3", fields={"Front": "New"},
                      expected_revision=before["content_revision"])
        read = lambda: col.get_note(3)["Front"]
        is_original = lambda: read() == "A decision card"
    assert not is_original()
    svc = McpService(svc.addon_dir, "A", "session-A", config=svc.config, alive=lambda: True)
    undone = call(svc, col, "undo_change", undo_id=result["undo_id"])
    assert is_original()
    svc = McpService(svc.addon_dir, "A", "session-A", config=svc.config, alive=lambda: True)
    call(svc, col, "undo_change", undo_id=undone["undo_id"])
    assert not is_original()


def test_undo_refuses_to_clobber_a_later_manual_change(service):
    svc, col = service
    result = call(svc, col, "set_priorities", card_ids=["11"], priority=10)
    import priority_manager
    priority_manager.set_priority(svc.addon_dir, "A", 11, 90)
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "undo_change", undo_id=result["undo_id"])
    assert priority_manager.get_priority(svc.addon_dir, "A", 11) == 90


def test_undo_deleted_list_restores_memberships_and_retains_book_notes(service):
    svc, col = service
    lid = document_lists.create_document_list(svc.addon_dir, "A", "Reference")
    document_lists.save_document_details(svc.addon_dir, "A", "pdf", "one.pdf",
                                        {"reason": "Keep", "source": "Friend", "list_ids": [lid]})
    result = call(svc, col, "delete_list", list_id=str(lid))
    call(svc, col, "undo_change", undo_id=result["undo_id"])
    assert document_lists.get_document_lists(svc.addon_dir, "A") == [(lid, "Reference")]
    assert document_lists.load_document_library(svc.addon_dir, "A")["books"][("pdf", "one.pdf")]["list_ids"] == [lid]


def test_undo_history_capacity_refuses_new_writes_before_they_happen(service):
    svc, col = service
    svc.history.max_entries = 1
    first = call(svc, col, "create_list", name="Keep undo")
    with pytest.raises(ToolError, match="undo"):
        call(svc, col, "create_list", name="Must not be created")
    assert document_lists.get_document_lists(svc.addon_dir, "A") == [(int(first["list_id"]), "Keep undo")]


def test_undoing_list_creation_refuses_to_remove_newer_memberships(service):
    svc, col = service
    created = call(svc, col, "create_list", name="Keep newer additions")
    call(svc, col, "update_list_members", list_id=created["list_id"], add=["pdf:one.pdf"], card_ids=["11"])
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "undo_change", undo_id=created["undo_id"])
    assert call(svc, col, "get_lists", list_id=created["list_id"])["items"] == [{"book_id": "pdf:one.pdf"}]


def test_undoing_a_rename_retains_memberships_with_sqlite_foreign_keys_enabled(service):
    svc, col = service
    lid = document_lists.create_document_list(svc.addon_dir, "A", "Original")
    document_lists.save_document_details(svc.addon_dir, "A", "pdf", "one.pdf", {"list_ids": [lid]})
    conn = db.get_connection(svc.addon_dir, "A")
    conn.execute("PRAGMA foreign_keys=ON")
    renamed = call(svc, col, "rename_list", list_id=str(lid), name="New")
    call(svc, col, "undo_change", undo_id=renamed["undo_id"])
    assert call(svc, col, "get_lists", list_id=str(lid))["items"] == [{"book_id": "pdf:one.pdf"}]


def test_history_distinguishes_redo_from_earlier_undoable_changes(service):
    svc, col = service
    first = call(svc, col, "create_list", name="First")
    second = call(svc, col, "create_list", name="Second")
    reverted = call(svc, col, "undo_change", undo_id=second["undo_id"])
    history = call(svc, col, "get_undo_history")["items"]
    assert history[0]["direction"] == "redo"
    assert history[0]["undo_id"] == reverted["undo_id"]
    assert history[1]["direction"] == "undo"
    assert history[1]["undo_id"] == first["undo_id"]


def test_successive_rule_changes_can_be_undone_in_order_without_rewinding_versions(service):
    svc, col = service
    first = call(svc, col, "set_custom_schedule", card_id="13", mode="one_time", interval_value=5,
                 interval_unit="days", expected_revision=0)
    second = call(svc, col, "set_custom_schedule", card_id="13", mode="one_time", interval_value=10,
                  interval_unit="days", expected_revision=first["revision"])
    undone = call(svc, col, "undo_change", undo_id=second["undo_id"])
    rule = db.get_custom_schedule_rule(svc.addon_dir, "A", 13)
    assert rule["interval_value"] == 5
    assert rule["revision"] > second["revision"]
    call(svc, col, "undo_change", undo_id=first["undo_id"])
    assert db.get_custom_schedule_rule(svc.addon_dir, "A", 13) is None
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "undo_change", undo_id=undone["undo_id"])


def test_timeout_after_a_commit_still_retains_its_undo_reference(service, monkeypatch):
    import priority_manager
    svc, col = service
    original = priority_manager.set_priorities
    def commit_then_timeout(*args):
        original(*args)
        svc.alive = lambda: False
    monkeypatch.setattr(priority_manager, "set_priorities", commit_then_timeout)
    with pytest.raises(ToolError):
        call(svc, col, "set_priorities", card_ids=["11"], priority=10)
    svc.alive = lambda: True
    history = call(svc, col, "get_undo_history")["items"]
    assert len(history) == 1
    call(svc, col, "undo_change", undo_id=history[0]["undo_id"])
    assert priority_manager.get_priority(svc.addon_dir, "A", 11) == 50


def test_note_edits_reject_media_identity_and_escape_untrusted_markup(service):
    svc, col = service
    before = call(svc, col, "read_notes", note_ids=["1"])["items"][0]
    with pytest.raises(ToolError, match="protected"):
        call(svc, col, "update_note_fields", note_id="1", fields={"PDF_Filename": "other.pdf"},
             expected_revision=before["content_revision"])
    assert col.get_note(1)["PDF_Filename"] == "one.pdf"
    assert col.updated == []
    before = call(svc, col, "read_notes", note_ids=["3"])["items"][0]
    result = call(svc, col, "update_note_fields", note_id="3", fields={"Front": "<script>alert(1)</script>"},
                  expected_revision=before["content_revision"])
    assert "<script>" not in col.get_note(3)["Front"]
    call(svc, col, "undo_change", undo_id=result["undo_id"])
    assert col.get_note(3)["Front"] == "A decision card"


@pytest.mark.parametrize("action", ["membership", "book_details", "bookmark_comment", "delete_bookmark", "delete_highlight", "clear_rule"])
def test_remaining_edits_and_deletions_restore_the_original_data(service, action, monkeypatch):
    svc, col = service
    if action in {"membership", "book_details"}:
        lid = document_lists.create_document_list(svc.addon_dir, "A", "Reference")
        document_lists.save_document_details(svc.addon_dir, "A", "pdf", "one.pdf",
                                            {"reason": "Original", "source": "Friend", "list_ids": [lid]})
        read = lambda: {key: value for key, value in call(svc, col, "get_book_details", card_id="11").items() if key != "revision"}
        before = read()
        if action == "membership":
            result = call(svc, col, "update_list_members", list_id=str(lid), remove=["pdf:one.pdf"], card_ids=["11"])
        else:
            result = call(svc, col, "update_book_details", card_id="11", reason="New",
                          expected_revision=call(svc, col, "get_book_details", card_id="11")["revision"])
    elif action in {"bookmark_comment", "delete_bookmark"}:
        added = call(svc, col, "add_bookmark", card_id="11", location={"page": 4}, label="Original")
        read = lambda: call(svc, col, "get_bookmarks", card_id="11")["items"]
        before = read()
        args = {"card_id": "11", "bookmark_id": added["id"]}
        if action == "bookmark_comment":
            result = call(svc, col, "update_bookmark_comment", **args, comment="New")
        else:
            result = call(svc, col, "delete_bookmark", **args)
    elif action == "delete_highlight":
        import pdf_highlights
        pdf_highlights.add_highlight(svc.addon_dir, "A", 11, {"id": "deleted", "text": "Original", "note": "Keep"})
        read = lambda: call(svc, col, "get_highlights", card_id="11")["items"]
        before = read()
        result = call(svc, col, "delete_highlight", card_id="11", highlight_id="deleted", expected_revision=before[0]["revision"])
    else:
        clock=[100]
        monkeypatch.setattr(db.time,'time',lambda:clock[0])
        rule = call(svc, col, "set_custom_schedule", card_id="13", mode="one_time", interval_value=5,
                    interval_unit="days", expected_revision=0)
        clock[0]=200
        read = lambda: {key: value for key, value in (db.get_custom_schedule_rule(svc.addon_dir, "A", 13) or {}).items()
                        if key not in {"revision", "updated_at"}}
        before = read()
        result = call(svc, col, "clear_custom_schedule", card_id="13", expected_revision=rule["revision"])
    after = read()
    assert after != before
    undone = call(svc, col, "undo_change", undo_id=result["undo_id"])
    assert read() == before
    with pytest.raises(ToolError, match="already-used"):
        call(svc, col, "undo_change", undo_id=result["undo_id"])
    call(svc, col, "undo_change", undo_id=undone["undo_id"])
    assert read() == after


def test_undo_never_replaces_an_identical_newer_manual_scheduling_rule(service):
    svc, col = service
    rule = call(svc, col, "set_custom_schedule", card_id="13", mode="one_time", interval_value=5,
                interval_unit="days", expected_revision=0)
    manual = db.set_custom_schedule_rule(svc.addon_dir, "A", 13, mode="one_time", interval_value=5, interval_unit="days")
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "undo_change", undo_id=rule["undo_id"])
    assert db.get_custom_schedule_rule(svc.addon_dir, "A", 13) == manual


def test_text_edits_refuse_missing_card_templates_and_undo_protects_newer_card_layouts(service):
    svc, col = service
    before = call(svc, col, "read_notes", note_ids=["3"])["items"][0]
    original = col.models.get
    col.models.get = lambda mid: {**original(mid), "tmpls": [{"ord": 0}, {"ord": 1}]}
    with pytest.raises(ToolError, match="generate cards"):
        call(svc, col, "update_note_fields", note_id="3", fields={"Back": "New"}, expected_revision=before["content_revision"])
    assert col.updated == []
    col.models.get = original
    edited = call(svc, col, "update_note_fields", note_id="3", fields={"Front": "New"}, expected_revision=before["content_revision"])
    col.add(15, 3, "New")
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "undo_change", undo_id=edited["undo_id"])
    assert col.get_note(3)["Front"] == "New"
