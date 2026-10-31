"""Native Anki contracts for MCP card authoring, management and OCR access."""
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def native(tmp_path, body):
    script = dedent('''
        import sys
        from pathlib import Path
        from anki.collection import Collection
        from backend.mcp_service import McpService, ToolError, TOOLS
        from backend import db
        root=Path(sys.argv[1])
        def protect_real_profiles(event,args):
            if event in {'open','os.mkdir','os.remove','os.rename','os.rmdir','os.listdir','os.scandir'}:
                for value in args[:2] if event=='os.rename' else args[:1]:
                    if isinstance(value,(str,bytes)):
                        candidate=Path(value.decode() if isinstance(value,bytes) else value)
                        if 'user_files' in candidate.parts and not candidate.resolve().is_relative_to(root.resolve()):
                            raise AssertionError('Native test attempted to access a non-test profile')
        sys.addaudithook(protect_real_profiles)
        col=Collection(str(root/'collection.anki2'))
        def service():
            return McpService(str(root),'A','context',config={},alive=lambda: True)
        svc=service()
        def call(tool_name, **args):
            return svc.call(col,tool_name,{'context_id':'context',**args})
        def restart():
            global col,svc
            db.close_connection();col.close()
            col=Collection(str(root/'collection.anki2'));svc=service()
        def seed(front='Original', model_name='Basic'):
            note=col.new_note(col.models.by_name(model_name))
            note.fields[0]=front;note.fields[1]='Answer'
            col.add_note(note,1)
            return note,col.find_cards(f'nid:{note.id}')[0]
        def revisions(ids):
            return {item['card_id']:item['revision'] for item in call('get_cards',card_ids=list(map(str,ids)))['items']}
        def rejected(fn):
            try: fn()
            except ToolError: return
            raise AssertionError('Expected a safe refusal')
        try:
    ''')
    script += '\n'.join('    '+line for line in dedent(body).splitlines())
    script += '\nfinally:\n    db.close_connection();col.close()\n'
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=45)
    assert result.returncode==0, result.stdout+result.stderr


def test_new_tools_are_discoverable_and_creation_cloning_preserve_identity_after_restart(tmp_path):
    native(tmp_path, '''
        expected={'get_cards','get_note_types','get_decks','create_cards','clone_cards','move_cards',
            'set_card_flags','suspend_cards','unsuspend_cards','read_ocr','search_ocr',
            'update_ocr_text','preview_field_replacements','find_duplicate_notes','get_review_history'}
        assert expected <= {tool['name'] for tool in TOOLS}
        assert any(item['name']=='Basic' for item in call('get_note_types')['items'])
        basic=col.models.by_name('Basic')
        detail=call('get_note_types',note_type_id=str(basic['id']))
        assert [item['name'] for item in detail['fields']]==['Front','Back']
        assert call('get_decks')['items'][0]['deck_id']=='1'
        created=call('create_cards',notes=[{'fields':{'Front':'A < B','Back':'Answer'}}],
            note_type_name='Basic',tags=['new'],request_id='standalone-create-001')
        nid=int(created['note_ids'][0]);ids=col.find_cards(f'nid:{nid}')
        assert col.get_note(nid)['Front']=='A &lt; B'
        assert len(ids)==1
        cloned=call('clone_cards',card_ids=list(map(str,ids)),expected_revisions=revisions(ids),add_tags=['clone'])
        copy_id=int(cloned['note_ids'][0]);copy_cards=col.find_cards(f'nid:{copy_id}')
        assert col.get_note(copy_id)['Front']==col.get_note(nid)['Front']
        assert set(col.get_note(copy_id).tags)=={'new','clone'}
        assert col.get_card(copy_cards[0]).reps==0
        restart()
        undone=call('undo_change',undo_id=cloned['undo_id'])
        assert col.find_cards(f'nid:{copy_id}')==[]
        restart();call('undo_change',undo_id=undone['undo_id'])
        assert col.find_cards(f'nid:{copy_id}')==copy_cards
        assert call('create_cards',notes=[{'fields':{'Front':'A < B','Back':'Answer'}}],
            note_type_name='Basic',tags=['new'],request_id='standalone-create-001')==created
    ''')


@pytest.mark.parametrize('tool,extra', [
    ('set_card_flags', {'flag':3}), ('suspend_cards', {}), ('unsuspend_cards', {}),
    ('move_cards', {'deck_id':'TARGET'}),
])
def test_card_mutations_are_native_reversible_and_reject_stale_bulk_targets(tmp_path,tool,extra):
    native(tmp_path, f'''
        tool={tool!r};extra={extra!r}
        first,cid=seed();second,other=seed('Second')
        if tool=='unsuspend_cards': col.sched.suspend_cards([cid,other])
        target=col.decks.id('Destination')
        if extra.get('deck_id')=='TARGET': extra['deck_id']=str(target)
        ids=[cid,other]
        before={{c: (col.get_card(c).did,col.get_card(c).queue,col.get_card(c).flags) for c in ids}}
        revs=revisions(ids)
        card=col.get_card(other);card.flags=7;col.update_card(card)
        rejected(lambda: call(tool,card_ids=list(map(str,ids)),expected_revisions=revs,**extra))
        assert (col.get_card(cid).did,col.get_card(cid).queue,col.get_card(cid).flags)==before[cid]
        card.flags=before[other][2];col.update_card(card)
        result=call(tool,card_ids=list(map(str,ids)),expected_revisions=revisions(ids),**extra)
        after={{c: (col.get_card(c).did,col.get_card(c).queue,col.get_card(c).flags) for c in ids}}
        assert after!=before
        assert col.db.scalar('select count(*) from revlog')==0
        restart();undone=call('undo_change',undo_id=result['undo_id'])
        assert {{c: (col.get_card(c).did,col.get_card(c).queue,col.get_card(c).flags) for c in ids}}==before
        restart();call('undo_change',undo_id=undone['undo_id'])
        assert {{c: (col.get_card(c).did,col.get_card(c).queue,col.get_card(c).flags) for c in ids}}==after
    ''')


def test_ocr_reads_search_and_corrections_preserve_native_type_and_restore_index(tmp_path):
    native(tmp_path, '''
        model=col.models.by_name('Basic')
        field=col.models.new_field('Incremento_OCR_Text');col.models.add_field(model,field);col.models.update_dict(model)
        note,cid=seed();note['Incremento_OCR_Text']='Old OCR evidence';col.update_note(note)
        db.replace_note_ocr_index(str(root),'A',note.id,[cid],[('image.png','Old OCR evidence')])
        before_model=col.models.get(note.mid)
        read=call('read_ocr',note_id=str(note.id),max_chars=7)
        assert read['text']=='Old OCR' and read['next_cursor']
        assert call('read_ocr',note_id=str(note.id),cursor=read['next_cursor'])['text']==' evidence'
        assert call('search_ocr',query='evidence')['items'][0]['note_id']==str(note.id)
        updated=call('update_ocr_text',note_id=str(note.id),text='Corrected memory evidence',expected_revision=read['revision'])
        assert 'Corrected' in col.get_note(note.id)['Incremento_OCR_Text']
        assert col.models.get(note.mid)==before_model
        assert call('search_ocr',query='memory')['items']
        restart();call('undo_change',undo_id=updated['undo_id'])
        assert col.get_note(note.id)['Incremento_OCR_Text']=='Old OCR evidence'
        rows=db.get_connection(str(root),'A').execute('select image_name,text from note_ocr_index where note_id=?',(note.id,)).fetchall()
        assert rows==[('image.png','Old OCR evidence')]
        plain,plain_cid=seed('No hidden field')
        # A separate existing type without OCR must never be changed implicitly.
        basic=col.models.by_name('Basic (and reversed card)')
        fresh=col.new_note(basic);fresh.fields[0]='No OCR';col.add_note(fresh,1)
        no_ocr=call('read_ocr',note_id=str(fresh.id))
        rejected(lambda: call('update_ocr_text',note_id=str(fresh.id),text='text',expected_revision=no_ocr['revision']))
        assert 'Incremento_OCR_Text' not in dict(col.get_note(fresh.id).items())
    ''')


def test_cloze_edits_keep_card_identities_and_bulk_replacement_is_previewed_and_reversible(tmp_path):
    native(tmp_path, '''
        made=call('create_cards',notes=[{'fields':{'Text':'The {{c1::heart}} pumps {{c2::blood}}.','Back Extra':'Extra'}}],note_type_name='Cloze')
        nid=int(made['note_ids'][0]);ids=col.find_cards(f'nid:{nid}')
        assert len(ids)==2
        clone=call('clone_cards',card_ids=list(map(str,ids)),expected_revisions=revisions(ids))
        assert len(clone['note_ids'])==1
        assert len(col.find_cards(f"nid:{clone['note_ids'][0]}"))==2
        preview=call('preview_field_replacements',note_ids=[str(nid)],field_names=['Text'],find='heart',replace='cardiac muscle')
        assert 'heart' in col.get_note(nid)['Text']
        assert preview['changes'][0]['before']!=preview['changes'][0]['after']
        edited=call('apply_plan',plan_id=preview['plan_id'])
        assert 'cardiac muscle' in col.get_note(nid)['Text']
        assert col.find_cards(f'nid:{nid}')==ids
        read=call('read_notes',note_ids=[str(nid)])['items'][0]
        rejected(lambda: call('update_note_fields',note_id=str(nid),fields={'Text':'{{c3::New layout}}'},expected_revision=read['content_revision']))
        assert col.find_cards(f'nid:{nid}')==ids
        restart();call('undo_change',undo_id=edited['undo_id'])
        assert 'heart' in col.get_note(nid)['Text']
        assert col.find_cards(f'nid:{nid}')==ids
    ''')


def test_duplicate_and_history_inspection_are_bounded_and_read_only(tmp_path):
    native(tmp_path, '''
        first,cid=seed('<b>Same</b>');second,other=seed(' same ')
        before=col.db.all('select * from cards order by id')
        matches=call('find_duplicate_notes',note_ids=[str(first.id),str(second.id)],field_name='Front')
        assert set(matches['groups'][0]['note_ids'])=={str(first.id),str(second.id)}
        assert call('get_review_history',card_ids=[str(cid)])['items']==[]
        assert col.db.all('select * from cards order by id')==before
        assert call('get_undo_history')['items']==[]
    ''')


def test_card_state_batches_share_native_undo_and_persist_one_complete_reversal(tmp_path):
    native(tmp_path, '''
        note,cid=seed()
        revs=revisions([cid])
        plan=call('preview_changes',actions=[
            {'tool':'set_card_flags','arguments':{'card_ids':[str(cid)],'flag':4,'expected_revisions':revs}},
            {'tool':'suspend_cards','arguments':{'card_ids':[str(cid)],'expected_revisions':revs}}])
        applied=call('apply_plan',plan_id=plan['plan_id'])
        assert col.get_card(cid).flags&7==4 and col.get_card(cid).queue==-1
        col.undo()
        assert col.get_card(cid).flags&7==0 and col.get_card(cid).queue==0
        col.redo()
        restart();undone=call('undo_change',undo_id=applied['undo_id'])
        assert col.get_card(cid).flags&7==0 and col.get_card(cid).queue==0
        call('undo_change',undo_id=undone['undo_id'])
        assert col.get_card(cid).flags&7==4 and col.get_card(cid).queue==-1
    ''')


def test_card_state_undo_refuses_reviews_and_filtered_targets_before_mutation(tmp_path):
    native(tmp_path, '''
        note,cid=seed()
        changed=call('set_card_flags',card_ids=[str(cid)],flag=2,expected_revisions=revisions([cid]))
        card=col.get_card(cid);card.reps=1;col.update_card(card)
        rejected(lambda: call('undo_change',undo_id=changed['undo_id']))
        assert col.get_card(cid).flags&7==2
        rejected(lambda: call('move_cards',card_ids=[str(cid)],deck_id='99999999',expected_revisions=revisions([cid])))
        assert col.get_card(cid).did==1
        card=col.get_card(cid);card.odid=1;col.update_card(card)
        rejected(lambda: call('suspend_cards',card_ids=[str(cid)],expected_revisions=revisions([cid])))
        assert col.get_card(cid).queue==0
    ''')


def test_creation_undo_still_works_after_a_later_text_edit_was_itself_undone(tmp_path):
    native(tmp_path, '''
        created=call('create_cards',notes=[{'fields':{'Front':'Original','Back':'Answer'}}],note_type_name='Basic')
        nid=created['note_ids'][0]
        col.db.execute('UPDATE notes SET mod=1 WHERE id=?',int(nid))
        read=call('read_notes',note_ids=[nid])['items'][0]
        edited=call('update_note_fields',note_id=nid,fields={'Back':'New answer'},expected_revision=read['content_revision'])
        restart();call('undo_change',undo_id=edited['undo_id'])
        assert col.get_note(int(nid))['Back']=='Answer'
        call('undo_change',undo_id=created['undo_id'])
        assert col.find_cards(f'nid:{nid}')==[]
    ''')


def test_managed_audio_identity_cannot_be_rewritten_or_cloned_as_plain_text(tmp_path):
    native(tmp_path, '''
        model=col.models.new('Incremento Audio')
        for name in ('Title','Audio_Filename'):
            col.models.add_field(model,col.models.new_field(name))
        template=col.models.new_template('Audio');template['qfmt']='{{Title}}';template['afmt']='{{Audio_Filename}}'
        col.models.add_template(model,template);col.models.add(model)
        note=col.new_note(model);note['Title']='Recording';note['Audio_Filename']='recording.mp3';col.add_note(note,1)
        cid=col.find_cards(f'nid:{note.id}')[0]
        read=call('read_notes',note_ids=[str(note.id)])['items'][0]
        rejected(lambda: call('update_note_fields',note_id=str(note.id),fields={'Audio_Filename':'other.mp3'},expected_revision=read['content_revision']))
        rejected(lambda: call('clone_cards',card_ids=[str(cid)],expected_revisions=revisions([cid])))
        assert col.get_note(note.id)['Audio_Filename']=='recording.mp3'
        assert len(col.find_cards(''))==1
    ''')


def test_ocr_index_can_be_read_without_a_populated_hidden_field_and_stale_corrections_fail(tmp_path):
    native(tmp_path, '''
        model=col.models.by_name('Basic')
        col.models.add_field(model,col.models.new_field('Incremento_OCR_Text'));col.models.update_dict(model)
        note,cid=seed()
        db.replace_note_ocr_index(str(root),'A',note.id,[cid],[('scan.png','Indexed evidence only')])
        read=call('read_ocr',note_id=str(note.id))
        assert read['text']=='Indexed evidence only'
        db.replace_note_ocr_index(str(root),'A',note.id,[cid],[('scan.png','A newer OCR result')])
        rejected(lambda: call('update_ocr_text',note_id=str(note.id),text='Stale correction',expected_revision=read['revision']))
        assert col.get_note(note.id)['Incremento_OCR_Text']==''
        assert call('read_ocr',note_id=str(note.id))['text']=='A newer OCR result'
    ''')


def test_flags_preserve_internal_bits_and_unsuspend_leaves_buried_cards_alone(tmp_path):
    native(tmp_path, '''
        note,cid=seed()
        card=col.get_card(cid);card.flags=16;col.update_card(card)
        marked=call('set_card_flags',card_ids=[str(cid)],flag=5,expected_revisions=revisions([cid]))
        assert col.get_card(cid).flags==21
        call('undo_change',undo_id=marked['undo_id'])
        assert col.get_card(cid).flags==16
        card=col.get_card(cid);card.queue=-2;col.update_card(card)
        before=col.db.all('select * from cards where id=?',cid)
        result=call('unsuspend_cards',card_ids=[str(cid)],expected_revisions=revisions([cid]))
        assert result['undo_id'] is None
        assert col.db.all('select * from cards where id=?',cid)==before
    ''')


def test_creation_undo_from_the_previous_history_format_survives_this_upgrade(tmp_path):
    native(tmp_path, '''
        made=call('create_cards',notes=[{'fields':{'Front':'Legacy creation','Back':'Answer'}}],note_type_name='Basic')
        nid=int(made['note_ids'][0])
        record=svc.history.get(made['undo_id'])
        record['args']['_creation'].pop('snapshot_version',None)
        # Version 1.2 retained modification timestamps and did not snapshot OCR rows.
        for snapshot in (record['before'],record['after']):
            snapshot['tables']=[item for item in snapshot['tables'] if item['table']!='note_ocr_index']
            for saved in snapshot['notes']:
                saved['row']=list(col.db.all('SELECT * FROM notes WHERE id=?',saved['id'])[0])
                columns=[row[1] for row in col.db.all('PRAGMA table_info(notes)')]
                saved['row'][columns.index('usn')]=0
                saved['cards']=[list(row) for row in col.db.all('SELECT * FROM cards WHERE nid=? ORDER BY id',saved['id'])]
                columns=[row[1] for row in col.db.all('PRAGMA table_info(cards)')]
                for row in saved['cards']: row[columns.index('usn')]=0
        svc.history.persist()
        restart();call('undo_change',undo_id=made['undo_id'])
        assert col.find_cards(f'nid:{nid}')==[]
    ''')
