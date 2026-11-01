"""Reviewed plans and file-backed content share the durable reversal boundary."""
from pathlib import Path
import pytest

from tests.test_mcp_service import service, call  # noqa: F401
from mcp_service import McpService, ToolError


def test_reviewed_batch_changes_nothing_until_apply_and_one_undo_survives_restart(service):
    svc, col = service
    before = call(svc, col, "read_notes", note_ids=["3"])["items"][0]
    plan = call(svc, col, "preview_changes", actions=[
        {"tool": "set_priorities", "arguments": {"card_ids": ["13"], "priority": 15}},
        {"tool": "update_tags", "arguments": {"note_ids": ["3"], "add": ["topic"], "expected_revisions": {"3": before["revision"]}}}])
    assert col.get_note(3).tags == ["keep"]
    assert call(svc, col, "get_priorities", card_ids=["13"])["items"][0]["priority"] == 50
    applied = call(svc, col, "apply_plan", plan_id=plan["plan_id"], request_id="apply-test-001")
    assert col.get_note(3).tags == ["keep", "topic"]
    reopened = McpService(svc.addon_dir, "A", "session-A", config={}, alive=lambda: True)
    assert call(reopened, col, "apply_plan", plan_id=plan["plan_id"], request_id="apply-test-001") == applied
    undone = call(reopened, col, "undo_change", undo_id=applied["undo_id"])
    assert col.get_note(3).tags == ["keep"]
    assert call(reopened, col, "get_priorities", card_ids=["13"])["items"][0]["priority"] == 50
    again = McpService(svc.addon_dir, "A", "session-A", config={}, alive=lambda: True)
    call(again, col, "undo_change", undo_id=undone["undo_id"])
    assert col.get_note(3).tags == ["keep", "topic"]


def test_writing_edits_have_content_revisions_and_durable_undo(service):
    svc, col = service
    original = col.models.get
    col.models.get = lambda mid: {**original(mid), "name": "Incremento Writing",
        "flds": [{"name": "Title", "ord": 0}, {"name": "Markdown_File", "ord": 1}]}
    col.sql.execute("UPDATE notes SET flds=? WHERE id=3", ("Writing\x1fwriting/draft.md",))
    path = Path(svc.addon_dir)/"user_files/A/writing/draft.md"
    path.parent.mkdir(parents=True)
    path.write_text("Original markdown")
    read = call(svc, col, "read_source", card_id="13")
    edited = call(svc, col, "update_writing", card_id="13", text="Edited markdown", expected_revision=read["revision"])
    assert path.read_text() == "Edited markdown"
    with pytest.raises(ToolError):
        call(svc, col, "update_writing", card_id="13", text="Stale", expected_revision=read["revision"])
    reopened = McpService(svc.addon_dir, "A", "session-A", config={}, alive=lambda: True)
    call(reopened, col, "undo_change", undo_id=edited["undo_id"])
    assert path.read_text() == "Original markdown"


def test_plan_rejects_intervening_edits_before_any_step(service):
    svc, col = service
    plan = call(svc, col, "preview_changes", actions=[{"tool": "set_priorities", "arguments": {"card_ids": ["13"], "priority": 5}}])
    call(svc, col, "set_priorities", card_ids=["13"], priority=80)
    with pytest.raises(ToolError, match="changed"):
        call(svc, col, "apply_plan", plan_id=plan["plan_id"])
    assert call(svc, col, "get_priorities", card_ids=["13"])["items"][0]["priority"] == 80


def test_book_organization_can_create_a_list_and_undo_the_whole_batch(service):
    import db
    svc, col = service
    db.get_connection(svc.addon_dir,'A').execute('PRAGMA foreign_keys=ON')
    proposal = call(svc, col, "preview_changes", actions=[
        {"tool": "create_list", "arguments": {"name": "New organized list"}},
        {"tool": "update_list_members", "arguments": {"list_id": "$0.list_id", "card_ids": ["11"], "add": ["pdf:one.pdf"]}}])
    applied = call(svc, col, "apply_plan", plan_id=proposal["plan_id"])
    lid = applied["results"][0]["list_id"]
    assert call(svc, col, "get_lists", list_id=lid)["items"] == [{"book_id": "pdf:one.pdf"}]
    reopened = McpService(svc.addon_dir, "A", "session-A", config={}, alive=lambda: True)
    undone=call(reopened, col, "undo_change", undo_id=applied["undo_id"])
    assert call(reopened, col, "get_lists")["items"] == []
    assert (Path(svc.addon_dir)/"user_files/A/pdfs/one.pdf").is_file()
    call(reopened,col,'undo_change',undo_id=undone['undo_id'])
    assert call(reopened,col,'get_lists',list_id=lid)['items']==[{'book_id':'pdf:one.pdf'}]


def test_failed_batch_compensates_earlier_changes(service):
    svc, col = service
    plan = call(svc, col, "preview_changes", actions=[
        {"tool": "set_priorities", "arguments": {"card_ids": ["13"], "priority": 5}},
        {"tool": "rename_list", "arguments": {"list_id": "999", "name": "Missing"}}])
    with pytest.raises(ToolError):
        call(svc, col, "apply_plan", plan_id=plan["plan_id"])
    assert call(svc, col, "get_priorities", card_ids=["13"])["items"][0]["priority"] == 50


def test_undo_membership_removal_rejects_a_deleted_parent_without_orphaning_rows(service):
    svc,col=service
    created=call(svc,col,'create_list',name='Parent')
    call(svc,col,'update_list_members',list_id=created['list_id'],card_ids=['11'],add=['pdf:one.pdf'])
    removed=call(svc,col,'update_list_members',list_id=created['list_id'],card_ids=['11'],remove=['pdf:one.pdf'])
    deleted=call(svc,col,'delete_list',list_id=created['list_id'])
    with pytest.raises(ToolError):
        call(svc,col,'undo_change',undo_id=removed['undo_id'])
    assert call(svc,col,'get_book_details',card_id='11')['list_ids']==[]
    assert next(item for item in call(svc,col,'get_undo_history')['items'] if item['undo_id']==removed['undo_id'])['direction']=='undo'
    call(svc,col,'undo_change',undo_id=deleted['undo_id'])
    call(svc,col,'undo_change',undo_id=removed['undo_id'])
    assert call(svc,col,'get_book_details',card_id='11')['list_ids']==[created['list_id']]


def test_tag_cleanup_is_a_reviewed_exact_mapping_with_one_durable_undo(service):
    svc, col = service
    col.sql.execute("UPDATE notes SET tags=' old old::child keep ' WHERE id=3")
    proposal = call(svc, col, "preview_tag_changes", note_ids=["3"], mappings=[{"from": "old", "to": "merged"}])
    assert col.get_note(3).tags == ["old", "old::child", "keep"]
    applied = call(svc, col, "apply_plan", plan_id=proposal["plan_id"])
    assert set(col.get_note(3).tags) == {"merged", "old::child", "keep"}
    call(svc, col, "undo_change", undo_id=applied["undo_id"])
    assert set(col.get_note(3).tags) == {"old", "old::child", "keep"}


def test_source_search_covers_later_epub_sections_without_extracting_files(service):
    from zipfile import ZipFile
    svc, col = service
    original = col.models.get
    col.models.get = lambda mid: {**original(mid), "name": "Incremento EPUB",
        "flds": [{"name": "Title", "ord": 0}, {"name": "EPUB_Filename", "ord": 1}]}
    col.sql.execute("UPDATE notes SET flds='Book\x1fsource.epub' WHERE id=3")
    folder = Path(svc.addon_dir)/"user_files/A/epubs"
    folder.mkdir(parents=True)
    with ZipFile(folder/'source.epub', 'w') as archive:
        archive.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
        archive.writestr('book.opf','<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="a" href="a.xhtml"/><item id="b" href="folder/../%62.xhtml#part"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
        archive.writestr('a.xhtml','<html><body>Earlier material</body></html>')
        archive.writestr('b.xhtml','<html><body>Memory evidence<script>UNTRUSTED_SCRIPT</script></body></html>')
    result = call(svc, col, "search_sources", query="memory")
    matches = [item for item in result["items"] if item["card_id"] == "13"]
    assert matches[0]["position"] == 2
    assert 'UNTRUSTED_SCRIPT' not in matches[0]["text"]
    assert not (folder.parent/'epub_extracted').exists()


def test_local_transcript_text_is_read_and_searched_without_network_access(service):
    svc, col = service
    original = col.models.get
    col.models.get = lambda mid: {**original(mid), "name": "Incremento Video",
        "flds": [{"name": "Title", "ord": 0}, {"name": "Target_Subtitle_File", "ord": 1}]}
    col.sql.execute("UPDATE notes SET flds='Lecture\x1flecture.srt' WHERE id=3")
    path=Path(svc.addon_dir)/"user_files/A/videos/lecture.srt"
    path.parent.mkdir(parents=True)
    path.write_text('1\n00:00:01,000 --> 00:00:03,000\nTranscript evidence\n')
    assert 'Transcript evidence' in call(svc, col, 'read_source', card_id='13')['text']
    assert any(item['card_id']=='13' for item in call(svc, col, 'search_sources', query='transcript evidence')['items'])


def test_pdf_resource_links_are_reversible_after_restart_and_do_not_delete_files(service, monkeypatch):
    import card_resource_links
    svc, col = service
    path=Path(svc.addon_dir)/"user_files/A/pdfs/one.pdf"
    monkeypatch.setattr(card_resource_links, 'resolve_document', lambda *args: {'path':str(path), 'max_page':10})
    monkeypatch.setattr(card_resource_links, 'pdf_page_count', lambda path: 10)
    before=call(svc,col,'get_resource_links',card_id='13')
    added=call(svc,col,'update_resource_links',card_id='13',expected_revision=before['revision'],
               add=[{'kind':'pdf','card_id':'11','page':3,'label':'Evidence'}])
    assert added['items'][0]['target_page']==3
    reopened=McpService(svc.addon_dir,'A','session-A',config={},alive=lambda:True)
    call(reopened,col,'undo_change',undo_id=added['undo_id'])
    assert call(reopened,col,'get_resource_links',card_id='13')['items']==[]
    assert path.is_file()


def test_interrupted_write_requires_state_review_then_can_be_undone_after_reopen(service):
    svc, col = service
    args={'card_ids':['13'],'priority':5}
    before=svc._capture_change(col,'set_priorities',args)
    identifier=svc.history.prepare('set_priorities',args,before)
    svc._set_priorities(col,**args)  # Simulate process exit before finalizing the write-ahead slot.
    reopened=McpService(svc.addon_dir,'A','session-A',config={},alive=lambda:True)
    with pytest.raises(ToolError,match='interrupted'):
        call(reopened,col,'undo_change',undo_id=identifier)
    inspection=call(reopened,col,'recover_change',undo_id=identifier)
    recovered=call(reopened,col,'recover_change',undo_id=identifier,state_revision=inspection['state_revision'])
    call(reopened,col,'undo_change',undo_id=recovered['undo_id'])
    assert call(reopened,col,'get_priorities',card_ids=['13'])['items'][0]['priority']==50


def test_retry_after_an_interrupted_write_cannot_duplicate_it_after_restart(service):
    from mcp_service import state_revision
    svc,col=service
    args={'card_ids':['13'],'priority':5}
    request_id='pending-write-001'
    identifier=svc.history.prepare('set_priorities',args,svc._capture_change(col,'set_priorities',args),
        request=(request_id,state_revision(['set_priorities',args])))
    svc._set_priorities(col,**args)
    reopened=McpService(svc.addon_dir,'A','session-A',config={},alive=lambda:True)
    with pytest.raises(ToolError,match='uncertain'):
        call(reopened,col,'set_priorities',request_id=request_id,**args)
    assert list(reopened.history.records)==[identifier]
    assert call(reopened,col,'get_priorities',card_ids=['13'])['items'][0]['priority']==5


def test_interrupted_reversal_recovers_an_inverse_without_reusing_the_consumed_reference(service):
    svc,col=service
    applied=call(svc,col,'set_priorities',card_ids=['13'],priority=5)
    record=svc.history.get(applied['undo_id'])
    original=record['before']
    record.update(before=record['after'],after=None,desired=original,pending=True,redo=True)
    svc.history.persist()
    svc._restore_change(col,original)
    reopened=McpService(svc.addon_dir,'A','session-A',config={},alive=lambda:True)
    inspection=call(reopened,col,'recover_change',undo_id=applied['undo_id'])
    result=call(reopened,col,'recover_change',undo_id=applied['undo_id'],state_revision=inspection['state_revision'])
    assert result['undo_id']!=applied['undo_id']
    with pytest.raises(ToolError,match='already-used'):
        call(reopened,col,'undo_change',undo_id=applied['undo_id'])
    call(reopened,col,'undo_change',undo_id=result['undo_id'])
    assert call(reopened,col,'get_priorities',card_ids=['13'])['items'][0]['priority']==5


def test_history_tampering_cannot_turn_undo_into_arbitrary_sql(service):
    import json
    svc,col=service
    changed=call(svc,col,'set_priorities',card_ids=['13'],priority=5)
    path=Path(svc.addon_dir)/'user_files/A/mcp_history.json'
    stored=json.loads(path.read_text())
    stored['records'][changed['undo_id']]['before']['tables'][0]['table']='document_library_lists'
    path.write_text(json.dumps(stored))
    reopened=McpService(svc.addon_dir,'A','session-A',config={},alive=lambda:True)
    with pytest.raises(ToolError,match='ownership'):
        call(reopened,col,'undo_change',undo_id=changed['undo_id'])
    assert call(reopened,col,'get_priorities',card_ids=['13'])['items'][0]['priority']==5


def test_writing_paths_cannot_escape_to_another_file_through_symlinks(service):
    svc,col=service
    original=col.models.get
    col.models.get=lambda mid:{**original(mid),'name':'Incremento Writing',
        'flds':[{'name':'Title','ord':0},{'name':'Markdown_File','ord':1}]}
    col.sql.execute("UPDATE notes SET flds='Writing\x1fwriting/escape.md' WHERE id=3")
    other=Path(svc.addon_dir)/'other.txt'
    other.write_text('Keep private')
    path=Path(svc.addon_dir)/'user_files/A/writing/escape.md'
    path.parent.mkdir(parents=True)
    path.symlink_to(other)
    with pytest.raises(ToolError,match='symlink'):
        call(svc,col,'read_source',card_id='13')
    assert other.read_text()=='Keep private'
