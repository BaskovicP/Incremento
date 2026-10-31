"""Advanced MCP changes retain native identities, schema and review state."""

import pytest

from tests.test_mcp_anki import native


def test_deck_creation_rename_and_merge_restore_exact_deck_and_card_identities(tmp_path):
    native(
        tmp_path,
        """
        made=call('create_deck',name='Practice')
        did=int(made['deck_id']);note,cid=seed()
        col.set_deck([cid],did)
        renamed=call('rename_deck',deck_id=str(did),name='Practice renamed',
            expected_revision=next(x['revision'] for x in call('get_decks')['items'] if x['deck_id']==str(did)))
        restart();reversed_rename=call('undo_change',undo_id=renamed['undo_id'])
        assert col.decks.get(did)['name']=='Practice'
        target=col.decks.id('Target')
        plan=call('preview_deck_merge',source_deck_ids=[str(did)],target_deck_id=str(target))
        assert col.get_card(cid).did==did
        merged=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert col.get_card(cid).did==target and not col.decks.have(did)
        restart();call('undo_change',undo_id=merged['undo_id'])
        assert col.decks.get(did)['name']=='Practice' and col.get_card(cid).did==did
        col.remove_notes([note.id])
        restart();call('undo_change',undo_id=made['undo_id'])
        assert not col.decks.have(did)
    """,
    )


def test_reversing_archive_keeps_an_earlier_multi_note_deck_merge_undoable(tmp_path):
    native(
        tmp_path,
        """
        deck=call('create_deck',name='Practice')
        created=call('create_cards',notes=[{'fields':{'Front':front,'Back':'Answer'}}
            for front in ('First','Second')],note_type_name='Basic',deck_name='Practice')
        ids=created['note_ids'];cards=col.find_cards('deck:Practice')
        plan=call('preview_deck_merge',source_deck_ids=[deck['deck_id']],target_deck_id='1')
        merged=call('apply_advanced_plan',plan_id=plan['plan_id'])
        plan=call('preview_note_removal',note_ids=[ids[0]],mode='archive')
        archived=call('apply_advanced_plan',plan_id=plan['plan_id'])
        restart();call('undo_change',undo_id=archived['undo_id'])
        restart();call('undo_change',undo_id=merged['undo_id'])
        assert col.find_cards('deck:Practice')==cards
        assert all(col.get_card(cid).did==int(deck['deck_id']) for cid in cards)
    """,
    )


@pytest.mark.parametrize(
    "action,extra",
    [("due", {"days": 12}), ("reset", {}), ("bury", {}), ("unbury", {}), ("ease", {"ease_factor": 2300})],
)
def test_direct_schedule_changes_restore_schedules_and_revlog_after_restart(tmp_path, action, extra):
    native(
        tmp_path,
        f"""
        note,cid=seed()
        col.sched.set_due_date([cid],'7')
        if {action!r}=='unbury': col.sched.bury_cards([cid])
        before=call('get_cards',card_ids=[str(cid)])['items'][0]
        history=col.db.all('select * from revlog where cid=? order by id',cid)
        changed=call('change_card_schedule',card_ids=[str(cid)],action={action!r},
            expected_revisions=revisions([cid]),**{extra!r})
        assert changed['undo_id']
        restart();undone=call('undo_change',undo_id=changed['undo_id'])
        restored=call('get_cards',card_ids=[str(cid)])['items'][0]
        for key in ('card_id','note_id','due','queue','type','interval_days','ease_factor','reviews','lapses'):
            assert restored[key]==before[key],(key,restored,before)
        actual_history=col.db.all('select * from revlog where cid=? order by id',cid)
        assert actual_history==history,(history,actual_history)
        restart();call('undo_change',undo_id=undone['undo_id'])
    """,
    )


def test_note_conversion_and_schema_edits_restore_dropped_cards_fields_and_native_ids(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed('{{c1::Memory}} improves with practice')
        old_model=note.mid
        plan=call('preview_note_type_conversion',note_ids=[str(note.id)],
            target_note_type_id=str(col.models.by_name('Cloze')['id']),field_map={'Text':'Front','Back Extra':'Back'})
        assert plan['requires_full_sync_acknowledgement']
        rejected(lambda:call('apply_advanced_plan',plan_id=plan['plan_id']))
        converted=call('apply_advanced_plan',plan_id=plan['plan_id'],acknowledge_full_sync=True)
        assert col.get_note(note.id).mid!=old_model
        restart();call('undo_change',undo_id=converted['undo_id'])
        assert col.get_note(note.id).mid==old_model and col.find_cards(f'nid:{note.id}')==[cid]
        plan=call('preview_note_type_edit',note_type_id=str(old_model),
            fields=[{'name':'Question','source':'Front'},{'name':'Answer','source':'Back'},{'name':'Extra'}],
            templates=[{'name':'Forward','front':'{{Question}}','back':'{{FrontSide}}<hr>{{Answer}}'},
                       {'name':'Reverse','front':'{{Answer}}','back':'{{Question}}'}],css='.card { color: navy; }')
        assert 'Memory' in plan['rendered_preview']['question_html']
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'],acknowledge_full_sync=True)
        assert 'Extra' in dict(col.get_note(note.id).items())
        assert len(col.find_cards(f'nid:{note.id}'))==2
        restart();inverse=call('undo_change',undo_id=changed['undo_id'])
        assert col.find_cards(f'nid:{note.id}')==[cid]
        assert dict(col.get_note(note.id).items())=={'Front':'{{c1::Memory}} improves with practice','Back':'Answer'}
        restart();call('undo_change',undo_id=inverse['undo_id'])
        assert len(col.find_cards(f'nid:{note.id}'))==2
    """,
    )


def test_deletion_and_archive_keep_media_and_restore_note_card_and_supplemental_state(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed();svc._set_priorities(col,[str(cid)],17)
        plan=call('preview_note_removal',note_ids=[str(note.id)],mode='delete')
        assert col.find_cards(f'nid:{note.id}')==[cid]
        removed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert col.find_cards(f'nid:{note.id}')==[]
        restart();again=call('undo_change',undo_id=removed['undo_id'])
        assert col.find_cards(f'nid:{note.id}')==[cid]
        assert call('get_priorities',card_ids=[str(cid)])['items'][0]['priority']==17
        archive=call('preview_note_removal',note_ids=[str(note.id)],mode='archive')
        archived=call('apply_advanced_plan',plan_id=archive['plan_id'])
        assert col.get_card(cid).queue==-1 and 'incremento::archived' in col.get_note(note.id).tags
        restart();call('undo_change',undo_id=archived['undo_id'])
        assert col.get_card(cid).queue==0 and col.get_note(note.id).tags==[]
    """,
    )


def test_rich_text_edits_and_media_attachments_preserve_formatting_and_originals(tmp_path):
    native(
        tmp_path,
        """
        import base64
        note,cid=seed()
        read=call('read_notes',note_ids=[str(note.id)])['items'][0]
        edit=call('update_note_html',note_id=str(note.id),fields={'Back':'<b>Bold</b> \\(x^2\\) <a href="https://example.com">link</a><img src="old.png"><script>alert(1)</script>'},expected_revision=read['content_revision'])
        value=col.get_note(note.id)['Back']
        assert '<b>Bold</b>' in value and 'old.png' in value and 'script' not in value and 'alert(1)' not in value
        source=root/'original.png'
        source.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9F0AAAAASUVORK5CYII='))
        read=call('read_notes',note_ids=[str(note.id)])['items'][0]
        attached=call('attach_media',note_id=str(note.id),field_name='Back',path=str(source),mode='append',expected_revision=read['content_revision'])
        media=Path(col.media.dir())/attached['filename']
        assert media.read_bytes()==source.read_bytes() and '<b>Bold</b>' in col.get_note(note.id)['Back']
        restart();redo=call('undo_change',undo_id=attached['undo_id'])
        assert source.is_file() and not media.exists() and col.get_note(note.id)['Back']==value
        restart();call('undo_change',undo_id=redo['undo_id'])
        assert media.read_bytes()==source.read_bytes()
        call('undo_change',undo_id=next(x['undo_id'] for x in call('get_undo_history')['items'] if x['action']=='attach_media' and x['direction']=='undo'))
        call('undo_change',undo_id=edit['undo_id'])
        assert col.get_note(note.id)['Back']=='Answer'
    """,
    )


def test_pdf_deletion_stays_undoable_after_normal_index_reconciliation(tmp_path):
    native(
        tmp_path,
        """
        from backend.pdf_manager import ensure_pdf_note_type
        from backend.pdf_search import reconcile_pdf_search_indexes
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Source';note['PDF_Filename']='source.pdf';col.add_note(note,1)
        cid=col.find_cards(f'nid:{note.id}')[0]
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True);(folder/'source.pdf').write_bytes(b'%PDF-synthetic')
        db.replace_pdf_text_index(str(root),'A',cid,['Saved source evidence'])
        plan=call('preview_note_removal',note_ids=[str(note.id)],mode='delete')
        removed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        reconcile_pdf_search_indexes(str(root),'A',col,card_ids=[cid])
        restart();call('undo_change',undo_id=removed['undo_id'])
        assert call('read_document',card_id=str(cid))['text']=='Saved source evidence'
    """,
    )


def test_schema_preview_rejects_a_newly_added_note_before_changing_any_layout(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed()
        plan=call('preview_note_type_edit',note_type_id=str(note.mid),css='.card { color: green; }')
        newer,other=seed('Added after preview')
        old=col.models.get(note.mid)
        rejected(lambda:call('apply_advanced_plan',plan_id=plan['plan_id'],acknowledge_full_sync=True))
        assert col.models.get(note.mid)==old and col.find_cards(f'nid:{newer.id}')==[other]
    """,
    )


def test_owned_incremento_formats_and_disguised_nonmedia_files_fail_without_data_changes(tmp_path):
    native(
        tmp_path,
        """
        made=call('create_cards',notes=[{'fields':{'Front':'Managed','Back':'Answer'}}])
        note=col.get_note(int(made['note_ids'][0]))
        rejected(lambda:call('preview_note_type_edit',note_type_id=str(note.mid),css='.card { color: red; }'))
        original=call('read_notes',note_ids=[str(note.id)])['items'][0]
        fake=root/'not-a-recording.mp3';fake.write_text('This is not media')
        rejected(lambda:call('attach_media',note_id=str(note.id),field_name='Back',path=str(fake),expected_revision=original['content_revision']))
        assert col.get_note(note.id)['Back']=='Answer'
        assert not list(Path(col.media.dir()).glob('incremento-mcp-*'))
    """,
    )


def test_undo_refuses_corrupt_current_recovery_package_before_touching_live_notes(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed()
        plan=call('preview_note_removal',note_ids=[str(note.id)],mode='archive')
        archived=call('apply_advanced_plan',plan_id=plan['plan_id'])
        record=svc.history.get(archived['undo_id'])
        archive=svc._profile_file(record['after']['recovery']['relative'])
        archive.write_bytes(b'corrupt retained package')
        before=col.db.all('SELECT * FROM notes WHERE id=?',note.id)
        rejected(lambda:call('undo_change',undo_id=archived['undo_id']))
        assert col.db.all('SELECT * FROM notes WHERE id=?',note.id)==before
        assert col.get_card(cid).queue==-1
    """,
    )


def test_new_schema_undo_preserves_older_creation_undo_references(tmp_path):
    native(
        tmp_path,
        """
        created=call('create_cards',note_type_name='Basic',notes=[{'fields':{'Front':'Original','Back':'Answer'}}])
        note=col.get_note(int(created['note_ids'][0]))
        plan=call('preview_note_type_edit',note_type_id=str(note.mid),css='.card { color: purple; }')
        edited=call('apply_advanced_plan',plan_id=plan['plan_id'],acknowledge_full_sync=True)
        restart();call('undo_change',undo_id=edited['undo_id'])
        call('undo_change',undo_id=created['undo_id'])
        assert col.find_cards(f'nid:{note.id}')==[]
    """,
    )
