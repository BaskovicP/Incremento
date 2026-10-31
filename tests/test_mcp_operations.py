"""Native workflows retain their complete affected state across restarts."""

from tests.test_mcp_anki import native


def test_checkpoint_refuses_foreign_file_and_sql_ownership_before_any_restore(tmp_path):
    native(
        tmp_path,
        """
        from backend import mcp_checkpoint as checkpoint
        from copy import deepcopy
        def refused_restore(target,current):
            try:checkpoint.restore(svc,col,target,current)
            except checkpoint.AnkiToolError:return
            raise AssertionError('Unsafe checkpoint was accepted')
        note,cid=seed()
        plan=call('preview_operation',action='filtered_build',parameters={'name':'Ownership','anki_query':f'cid:{cid}'})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        record=svc.history.get(changed['undo_id']);before=deepcopy(record['before']);after=deepcopy(record['after'])
        foreign=root/'unrelated.txt';foreign.write_bytes(b'keep')
        before['files'].append({'path':str(foreign),'asset':None})
        refused_restore(before,after)
        assert foreign.read_bytes()==b'keep' and col.decks.by_name('Ownership') is not None
        before=deepcopy(record['before']);before['sqlite']=checkpoint.retain_json(svc,{'tables':[
            {'table':'schema_migrations','columns':['version'],'predicate':'1','params':[],'rows':[]}]})
        refused_restore(before,after)
        assert col.decks.by_name('Ownership') is not None
    """,
    )


def test_native_checkpoint_undo_allows_harmless_deck_navigation(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed();other=col.decks.id('Other')
        plan=call('preview_operation',action='filtered_build',parameters={'name':'Temporary','anki_query':f'cid:{cid}'})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        col.decks.select(other)
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert col.decks.by_name('Temporary') is None
        assert col.decks.selected()==other
    """,
    )


def test_native_checkpoint_undo_composes_with_later_card_creation_undo(tmp_path):
    native(
        tmp_path,
        """
        seed()
        plan=call('preview_operation',action='deck_options',parameters={'deck_id':'1','patch':{'new':{'perDay':12}}})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        created=call('create_cards',notes=[{'fields':{'Front':'Later','Back':'Answer'}}],note_type_name='Basic')
        call('undo_change',undo_id=created['undo_id'])
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert call('get_deck_options',deck_id='1')['preset']['new']['perDay']==20
    """,
    )


def test_settings_presets_and_reader_progress_are_restart_reversible(tmp_path):
    native(
        tmp_path,
        """
        from backend.pdf_manager import ensure_pdf_note_type
        settings_store={}
        def save_settings(value):
            settings_store.clear();settings_store.update(value)
        def service():
            return McpService(str(root),'A','context',config=dict(settings_store),alive=lambda:True,save_config=save_settings)
        svc=service()
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'))
        note['Title']='Book';note['PDF_Filename']='book.pdf';col.add_note(note,1)
        cid=str(col.find_cards(f'nid:{note.id}')[0])
        def apply(action,**parameters):
            plan=call('preview_operation',action=action,parameters=parameters)
            return call('apply_advanced_plan',plan_id=plan['plan_id'])
        original=call('get_incremento_settings')['settings']
        changed=apply('settings',patch={'topic_maximum_interval_days':123})
        assert call('get_incremento_settings')['settings']['topic_maximum_interval_days']==123
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert call('get_incremento_settings')['settings']==original
        moved=apply('reader_progress',card_id=cid,position=7,read_position=5,scroll_ratio=0.4)
        assert call('get_reader_progress',card_id=cid)['position']==7
        restart();call('undo_change',undo_id=moved['undo_id'])
        assert call('get_reader_progress',card_id=cid)['position']==1
    """,
    )


def test_new_annotations_and_note_type_lifecycle_have_durable_undo(tmp_path):
    native(
        tmp_path,
        """
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'))
        note['Title']='Book';note['PDF_Filename']='book.pdf';col.add_note(note,1)
        cid=str(col.find_cards(f'nid:{note.id}')[0])
        plan=call('preview_operation',action='highlight_create',parameters={'card_id':cid,'position':1,
            'text':'Passage','rects':[{'x':10,'y':10,'w':20,'h':12}]})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert len(call('get_highlights',card_id=cid)['items'])==1
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert call('get_highlights',card_id=cid)['items']==[]
        plan=call('preview_operation',action='note_type_clone',parameters={'note_type_id':str(col.models.by_name('Basic')['id']),'name':'Practice type'})
        cloned=call('apply_advanced_plan',plan_id=plan['plan_id'],acknowledge_full_sync=True)
        mid=col.models.by_name('Practice type')['id']
        restart();redo=call('undo_change',undo_id=cloned['undo_id'])
        assert col.models.by_name('Practice type') is None
        restart();call('undo_change',undo_id=redo['undo_id'])
        assert col.models.by_name('Practice type')['id']==mid
    """,
    )


def test_filtered_queue_and_answer_restore_exact_native_history_after_restart(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed()
        original=col.db.all('select * from revlog where cid=?',cid)
        previous_undo=col.undo_status().undo
        call('preview_operation',action='filtered_build',parameters={'name':'Unused preview','anki_query':f'cid:{cid}'})
        assert col.undo_status().undo==previous_undo
        def apply(action,**parameters):
            plan=call('preview_operation',action=action,parameters=parameters)
            return call('apply_advanced_plan',plan_id=plan['plan_id'])
        queued=apply('filtered_build',name='MCP practice',anki_query=f'cid:{cid}',limit=10,reschedule=True)
        assert col.get_card(cid).odid==1
        answered=apply('answer_card',card_id=str(cid),rating=3)
        assert col.db.scalar('select count(*) from revlog where cid=?',cid)==1
        restart();call('undo_change',undo_id=answered['undo_id'])
        assert col.db.all('select * from revlog where cid=?',cid)==original
        assert col.get_card(cid).odid==1
        restart();call('undo_change',undo_id=queued['undo_id'])
        assert col.get_card(cid).did==1 and col.get_card(cid).odid==0
        assert col.decks.by_name('MCP practice') is None
    """,
    )


def test_strict_administration_refuses_irreversible_actions_before_changes(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed()
        before=col.db.all('select * from cards')
        for action in ('sync','switch_profile','install_addon','remove_addon'):
            rejected(lambda:call('preview_operation',action=action,parameters={}))
        status=call('get_administration_status')
        assert status['strict_undo'] and not status['irreversible_actions_enabled']
        assert col.db.all('select * from cards')==before
        assert call('get_undo_history')['items']==[]
    """,
    )
