"""Availability is visible before opening resources and scoped to the current card."""
from textwrap import dedent

from tests.test_study_navigation_qt import run_scene


CAPTURE = '''
rendered=[]
original=ui.reviewer_navigation_script
def capture(routes,label,**kwargs):
    rendered.append((routes,kwargs.get('workspace')))
    return original(routes,label,**kwargs)
ui.reviewer_navigation_script=capture
ui.refresh_reviewer_navigation()
def routes(): return {r['stage']:r for r in rendered[-1][0]}
def tiles(): return {r['stage']:r for r in rendered[-1][1]['tiles']}
'''


def test_review_checks_resources_in_background_without_opening_a_workspace():
    run_scene(CAPTURE + dedent('''
        assert ui._window is None and pending
        assert routes()['book']['disabled'] and routes()['book']['availability']=='loading'
        assert not routes()['card']['disabled']
        drain()
        assert ui._window is None and web.isEnabled() and mw.reviewer.auto_advance_enabled
        assert routes()['book']['availability']=='ready' and routes()['book']['status']==ui.t('study_linked_count',count=1)
        assert not routes()['video']['disabled']
        assert tiles()['book']['title']=='Geometry'
    '''), resolve_availability=False)


def test_empty_and_missing_resources_disable_navigation_but_offer_explicit_link_or_manage_actions():
    run_scene(CAPTURE + dedent('''
        ui.load_card_resources=lambda *a: dict(documents=[],recordings=[dict(recording,available=False,recording=None)])
        drain()
        assert routes()['book']['availability']=='empty' and routes()['book']['disabled']
        assert routes()['video']['availability']=='unavailable' and routes()['video']['disabled']
        assert tiles()['book']['command'].endswith(':link_book')
        assert tiles()['video']['command'].endswith(':manage')
        bridge('book'); bridge('video')
        assert ui._window is None, 'Disabled navigation must not open an empty resource view'
        linked=[]
        ui.StudyWorkspace.link_textbook=lambda self: linked.append(self.source['card_id'])
        bridge('link_book'); drain()
        assert linked==[41] and ui._window is not None
        ui._window.close()
    '''), resolve_availability=False)


def test_late_check_cannot_update_another_card_and_answer_reveal_reuses_the_current_result():
    run_scene(CAPTURE + dedent('''
        old=pending.pop(0)
        mw.reviewer.card=types.SimpleNamespace(id=42); ui.reviewer_shown()
        ui.load_card_resources=lambda *a: dict(documents=[],recordings=[])
        drain()
        count=len(rendered)
        old.success(dict(documents=[document],recordings=[recording]))
        assert len(rendered)==count and routes()['book']['availability']=='empty'
        mw.reviewer.state='answer'; ui.reviewer_shown()
        assert not pending and routes()['book']['availability']=='empty'
        assert rendered[-1][1]['state']==ui.t('study_answer_revealed')
    '''), resolve_availability=False)


def test_check_failure_is_not_reported_as_no_links_and_retry_recovers():
    run_scene(CAPTURE + dedent('''
        pending.pop(0).failed(RuntimeError('Synthetic failure'))
        assert routes()['book']['availability']=='error'
        assert tiles()['book']['command'].endswith(':retry')
        bridge('retry'); drain()
        assert routes()['book']['availability']=='ready' and ui._window is None
    '''), resolve_availability=False)


def test_native_tabs_show_passage_availability_and_update_after_link_refresh():
    run_scene(CAPTURE + dedent('''
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        assert w.stage_status['book'].text()==ui.t('study_linked_count',count=1)
        assert w.stage_buttons['video'].isEnabled()
        ui.list_recording_links=lambda *a,**kw: []
        ui.resolve_link_rows=lambda *a: []
        w.refresh(); drain()
        assert not w.stage_buttons['video'].isEnabled()
        assert w.stage_status['video'].text()==ui.t('study_not_linked')
        assert w.add_recording.isEnabled()
        ui.resolve_link_rows=lambda *a: [recording]
        w.refresh(); drain()
        assert w.stage_buttons['video'].isEnabled()
        click(w,'video'); drain(); player=w.player
        w.reader.state.page=7; w.poll_location(); drain()
        click(w,'card'); drain()
        assert ui._window is w and w.player is player
        assert tiles()['book']['detail']==ui.source_label(w.source)
        w.close()
    '''))


def test_profile_change_discards_pending_availability_and_audio_is_identified_before_opening():
    run_scene(CAPTURE + dedent('''
        old=pending.pop(0)
        profile[0]='Other'; ui.reset(); ui.reviewer_shown()
        ui.load_card_resources=lambda *a: dict(documents=[],recordings=[dict(recording,recording=dict(title='Lecture',kind='audio'))])
        drain()
        assert routes()['video']['label']==ui.t('study_tab_audio') and routes()['video']['availability']=='ready'
        count=len(rendered)
        old.failed(RuntimeError('Outdated'))
        old.success(dict(documents=[document],recordings=[]))
        assert len(rendered)==count and ui._window is None
    '''), resolve_availability=False)


def test_changing_passage_does_not_advertise_the_previous_pages_recordings():
    run_scene('''
        ui.list_recording_links=lambda *a,**kw: [row] if kw['source'].get('page')==6 else []
        ui.resolve_link_rows=lambda *args: [recording] if args[-1] else []
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        assert w.stage_buttons['video'].isEnabled()
        w.reader.state.page=7; w.poll_location()
        assert not w.stage_buttons['video'].isEnabled()
        assert w.stage_status['video'].text()==ui.t('study_checking')
        drain()
        assert w.stage_status['video'].text()==ui.t('study_not_linked')
        click(w,'video'); assert w.player is None
        w.close()
    ''')
