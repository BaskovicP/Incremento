"""Deck options, queued work and explicit UI controls share durable undo."""

from tests.test_mcp_anki import native


def test_reviewer_restore_reloads_exact_card_side_and_scheduling_context(tmp_path):
    native(
        tmp_path,
        """
        from types import SimpleNamespace
        from aqt.reviewer import V3CardInfo
        from backend.anki_compat import mcp_reviewer_state,mcp_restore_reviewer
        note,cid=seed();card=col.get_card(cid)
        reviewer=SimpleNamespace(card=card,state='answer',_answeredIds=[91],_v3=V3CardInfo.from_queue(col.sched.get_queued_cards()))
        reviewer._showQuestion=lambda:setattr(reviewer,'state','question')
        reviewer._showAnswer=lambda:setattr(reviewer,'state','answer')
        mw=SimpleNamespace(col=col,state='review',reviewer=reviewer)
        saved=mcp_reviewer_state(mw,include_runtime=True)
        reviewer.card=None;reviewer.state='question';reviewer._answeredIds=[]
        mcp_restore_reviewer(mw,saved)
        assert reviewer.card.id==cid and reviewer.state=='answer' and reviewer._answeredIds==[91]
        assert reviewer._v3.top_card().card.id==cid
    """,
    )


def test_deck_options_and_fixed_tag_sets_restore_after_restart(tmp_path):
    native(
        tmp_path,
        """
        before=call('get_deck_options',deck_id='1')['preset']
        plan=call('preview_operation',action='deck_options',parameters={'deck_id':'1','patch':{'new':{'perDay':7},'desiredRetention':0.85,'fsrs_enabled':True}})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert call('get_deck_options',deck_id='1')['preset']['new']['perDay']==7
        assert call('get_deck_options',deck_id='1')['fsrs_enabled'] is True
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert call('get_deck_options',deck_id='1')['preset']==before
        assert call('get_deck_options',deck_id='1')['fsrs_enabled'] is False
        from frontend.tag_colors import tag_chip_palette_size,tag_chip_reserved_indexes,tag_chip_color_for_index
        def palette(action,p):
            assert action=='tag_palette'
            return {'size':tag_chip_palette_size(),'reserved':tag_chip_reserved_indexes(),
                'colors':{str(i):tag_chip_color_for_index(i) for i in p.get('indexes',[])}}
        def service():return McpService(str(root),'A','context',config={},alive=lambda:True,runtime=palette)
        svc=service()
        groups=[['one'],['two']]+[[] for _ in range(7)]
        plan=call('preview_operation',action='quick_tag_settings',parameters={'use_fixed_sets':True,'fixed_tag_groups':groups})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert call('get_incremento_settings')['quick_tags']['fixed_tag_groups']==groups
        assert set(db.get_browser_tag_color_indexes(str(root),'A'))=={'one','two'}
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert not call('get_incremento_settings')['quick_tags']['use_fixed_sets']
    """,
    )


def test_owned_jobs_can_cancel_retry_and_reverse_after_restart(tmp_path):
    native(
        tmp_path,
        """
        queued=[]
        def service():return McpService(str(root),'A','context',config={},alive=lambda:True,runtime=lambda action,p:queued.append((action,p)))
        svc=service();note,cid=seed()
        plan=call('preview_operation',action='filtered_build',parameters={'name':'Queued study','anki_query':f'cid:{cid}'})
        first=call('start_operation_job',plan_id=plan['plan_id'],request_id='native-job-request-0001')
        cancelled=call('cancel_operation_job',job_id=first['job_id'],request_id='native-job-cancel-0001')
        assert cancelled['cancelled'] and col.decks.by_name('Queued study') is None
        restart()
        assert call('cancel_operation_job',job_id=first['job_id'],request_id='native-job-cancel-0001')==cancelled
        second=call('retry_operation_job',job_id=first['job_id'])
        svc.execute_operation_job(col,second['job_id'])
        assert col.decks.by_name('Queued study') is not None
        status=call('get_background_tasks')['mcp_jobs']
        assert next(job for job in status if job['job_id']==second['job_id'])['status']=='completed'
        restart();undone=call('cancel_operation_job',job_id=second['job_id'])
        assert col.decks.by_name('Queued study') is None
        restart();call('undo_change',undo_id=undone['undo_id'])
        assert col.decks.by_name('Queued study') is not None
    """,
    )


def test_stale_queued_job_never_claims_unrelated_edits_as_its_undo(tmp_path):
    native(
        tmp_path,
        """
        def service():return McpService(str(root),'A','context',config={},alive=lambda:True,runtime=lambda action,p:{})
        svc=service();note,cid=seed()
        plan=call('preview_operation',action='filtered_build',parameters={'name':'Stale study','anki_query':f'cid:{cid}'})
        job=call('start_operation_job',plan_id=plan['plan_id'])
        note['Front']='Edited while queued';col.update_note(note)
        svc.execute_operation_job(col,job['job_id'])
        status=next(j for j in call('get_background_tasks')['mcp_jobs'] if j['job_id']==job['job_id'])
        assert status['status']=='failed' and status['undo_id'] is None
        assert col.get_note(note.id)['Front']=='Edited while queued'
        assert col.decks.by_name('Stale study') is None
    """,
    )


def test_session_start_freezes_scheduler_selection_and_supplies_native_tracking(tmp_path):
    native(
        tmp_path,
        """
        from copy import deepcopy
        calls=[]
        def runtime(action,p):
            if action=='snapshot':return {'screen':'deckBrowser','deck_id':'1','side':'question','card_id':None}
            if action=='session':calls.append(deepcopy(p));return {'screen':'review','deck_id':p['deck_id'],'session':p['session']}
            return {}
        def service():return McpService(str(root),'A','context',config={'dialog':{'topics_slider':100}},alive=lambda:True,runtime=runtime)
        svc=service()
        first,cid=seed();second,other=seed('Second')
        plan=call('preview_operation',action='session_start',parameters={'count':2,'anki_query':f'cid:{cid},{other}'})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        state=calls[0]['session']
        assert set(state['picker']['selected_ids'])=={cid,other}
        assert state['config']['session_card_count']==2
        assert state['deck_name']=='Incremento Session'
        assert len(col.find_cards('did:'+calls[0]['deck_id']))==2
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert col.decks.by_name('Incremento Session') is None
    """,
    )


def test_reviewer_side_and_timer_control_restore_preceding_state_after_restart(tmp_path):
    native(
        tmp_path,
        """
        from copy import deepcopy
        note,cid=seed()
        initial={'screen':'review','card_id':str(cid),'deck_id':'1','side':'question'}
        bus={'reviewer':deepcopy(initial),'timer':{'minutes':30,'remaining':120,'running':False,'counters':{}}}
        def runtime(action,p):
            if action=='snapshot':return deepcopy(bus[p['area']])
            if action=='reviewer_side':bus['reviewer']['side']=p['side'];return deepcopy(bus['reviewer'])
            if action=='timer':bus['timer']['running']=p['command'] in ('start','resume');return deepcopy(bus['timer'])
            if action=='check_restore':return {}
            if action=='restore_checkpoint':
                target=p['state'];bus[target['scope']['ui']['area']]=deepcopy(target['runtime']);return {}
            raise AssertionError(action)
        def service():return McpService(str(root),'A','context',config={},alive=lambda:True,runtime=runtime)
        svc=service()
        plan=call('preview_operation',action='reviewer_show_answer',parameters={'card_id':str(cid)})
        shown=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert bus['reviewer']['side']=='answer'
        restart();bus['reviewer']={'screen':'deckBrowser'}
        call('undo_change',undo_id=shown['undo_id'])
        assert bus['reviewer']==initial
        plan=call('preview_operation',action='timer',parameters={'command':'resume'})
        started=call('apply_advanced_plan',plan_id=plan['plan_id'])
        restart();bus['timer']={}
        call('undo_change',undo_id=started['undo_id'])
        assert bus['timer']=={'minutes':30,'remaining':120,'running':False,'counters':{}}
    """,
    )
