"""Remember explicit layout choices across visits, restarts, and profile changes."""
from tests.test_study_navigation_qt import run_scene


MANAGER = '''
import json
from pathlib import Path
class Manager:
    def getConfig(self, package):
        return json.loads(config_path.read_text()) if config_path.exists() else {}
    def writeConfig(self, package, config):
        config_path.write_text(json.dumps(config))
mw.addonManager = Manager()
def stored():
    return mw.addonManager.getConfig('incremento').get('study_layout_by_profile', {})
def ratio(w):
    sizes=w.splitter.sizes()
    return sizes[0]/sum(sizes)
def drag(w, fraction):
    w.splitter.moveSplitter(round(sum(w.splitter.sizes())*fraction), 1)
    app.processEvents()
'''


def scene(tmp_path, body):
    run_scene(f'from pathlib import Path\nconfig_path=Path({str(tmp_path / "config.json")!r})\n' + MANAGER + body)


def test_restarting_restores_textbook_focus_and_split_proportions_at_a_different_window_size(tmp_path):
    scene(tmp_path, '''
mw.resize(1400,950)
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
drag(w,.62)
w.focus_book.click(); app.processEvents()
assert mw.isFullScreen()
w.close(); app.processEvents()
assert not mw.isFullScreen()
assert stored()['Synthetic']['book']['focus'] is True
assert abs(stored()['Synthetic']['book']['horizontal']-.62)<.01
''')
    # A fresh interpreter and addon manager rule out an in-memory-only cache.
    scene(tmp_path, '''
mw.resize(1600,1000)
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert mw.isFullScreen() and w.focus_stage=='book'
assert not w.side.isVisible()
w.exit_focus.click(); app.processEvents()
assert not mw.isFullScreen() and abs(ratio(w)-.62)<.01
w.close()
assert stored()['Synthetic']['book']['focus'] is False
''')
    scene(tmp_path, '''
mw.resize(1400,950)
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert not mw.isFullScreen() and abs(ratio(w)-.62)<.01
w.close()
''')


def test_card_return_keeps_focus_preference_and_profiles_remain_independent(tmp_path):
    scene(tmp_path, '''
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
w.focus_book.click(); click(w,'card'); app.processEvents()
assert web.isVisible() and not mw.isFullScreen()
click(w,'book'); app.processEvents()
assert mw.isFullScreen() and w.focus_stage=='book'
profile[0]='Other'; w.poll_location(); app.processEvents()
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert not mw.isFullScreen() and w.focus_stage is None
w.close()
assert stored()['Synthetic']['book']['focus'] is True
assert 'Other' not in stored()
profile[0]='Synthetic'
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert mw.isFullScreen()
w.reject(); w.close()
assert stored()['Synthetic']['book']['focus'] is False
''')


def test_video_opening_does_not_apply_textbook_focus_during_its_intermediate_load(tmp_path):
    scene(tmp_path, '''
mw.addonManager.writeConfig('incremento', {'study_layout_by_profile': {'Synthetic': {
    'book': {'focus': True}, 'video': {'focus': False}}}})
ui.show_resources(); w=ui._window; drain()
click(w,'video'); drain(); app.processEvents()
assert w.reader is not None and w.player is not None
assert not mw.isFullScreen() and w.focus_stage is None
w.focus_video.click(); click(w,'card'); click(w,'video'); app.processEvents()
assert mw.isFullScreen() and w.focus_stage=='video'
assert w.player.pos==12 and w.player.loads==1
w.close()
assert stored()['Synthetic']['book']['focus'] is True
assert stored()['Synthetic']['video']['focus'] is True
''')


def test_pane_choices_are_separate_for_each_stage_and_orientation_and_resize_does_not_resave(tmp_path):
    scene(tmp_path, '''
mw.resize(1400,950)
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
drag(w,.61)
click(w,'video'); drain(); app.processEvents(); drag(w,.36)
mw.resize(750,1100); app.processEvents(); drag(w,.41)
click(w,'book'); app.processEvents(); drag(w,.57)
w.close()
prefs=stored()['Synthetic']
assert abs(prefs['book']['horizontal']-.61)<.01
assert abs(prefs['video']['horizontal']-.36)<.01
assert abs(prefs['video']['vertical']-.41)<.01
assert abs(prefs['book']['vertical']-.57)<.01
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert abs(ratio(w)-.57)<.01
mw.resize(1400,950); app.processEvents()
assert abs(ratio(w)-.61)<.01
click(w,'video'); drain(); app.processEvents()
assert abs(ratio(w)-.36)<.01
w.close()
assert stored()['Synthetic']==prefs, 'Programmatic resize and restoration must not replace saved choices'
''')


def test_profile_switch_discards_delayed_layout_saves_and_focus_restoration(tmp_path):
    scene(tmp_path, '''
mw.addonManager.writeConfig('incremento', {'study_layout_by_profile': {'Synthetic': {'book': {'focus': True}}}})
ui.show_resources(source); w=ui._window
profile[0]='Other'; drain(); app.processEvents()
assert not mw.isFullScreen() and w.focus_stage is None
w.close()
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
drag(w,.60)
profile[0]='Third'; w.poll_location(); app.processEvents()
assert stored()=={'Synthetic': {'book': {'focus': True}}}
''')


def test_failed_preference_write_keeps_focus_usable_and_does_not_mutate_saved_config(tmp_path):
    scene(tmp_path, '''
mw.addonManager.writeConfig('incremento', {'future_option': {'keep': True}})
messages=[]; sys.modules['aqt.utils'].tooltip=messages.append
def fail(*args): raise OSError('Synthetic failure')
mw.addonManager.writeConfig=fail
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
w.focus_book.click(); app.processEvents()
assert mw.isFullScreen()
w.exit_focus.click(); app.processEvents()
assert not mw.isFullScreen() and not w.visit.closed
assert mw.addonManager.getConfig('incremento')=={'future_option': {'keep': True}}
w.close()
assert messages==[ui.t('study_layout_save_failed')]
''')


def test_drag_saves_while_open_and_merges_the_latest_unrelated_preferences(tmp_path):
    scene(tmp_path, '''
mw.resize(1400,950)
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
drag(w,.62); drag(w,.67)
mw.addonManager.writeConfig('incremento', {'future_setting': {'keep': True},
    'study_layout_by_profile': {'Other': {'video': {'focus': True}}}})
loop=QtCore.QEventLoop(); poll=QtCore.QTimer(); timeout=QtCore.QTimer()
poll.timeout.connect(lambda: loop.quit() if 'Synthetic' in stored() else None)
timeout.setSingleShot(True); timeout.timeout.connect(loop.quit)
poll.start(10); timeout.start(2000); loop.exec(); poll.stop(); timeout.stop()
saved=mw.addonManager.getConfig('incremento')
assert abs(stored()['Synthetic']['book']['horizontal']-.67)<.01
assert stored()['Other']=={'video': {'focus': True}}
assert saved['future_setting']=={'keep': True}
assert w.isVisible() and not w.visit.closed
w.close()
''')


def test_standalone_reopening_restores_its_focus_without_fullscreening_anki(tmp_path):
    scene(tmp_path, '''
mw.state='deckBrowser'; ui.reviewer_shown()
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
w.focus_book.click(); app.processEvents(); w.close(); app.processEvents()
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert w.isWindow() and w.isFullScreen() and not mw.isFullScreen()
w.close(); app.processEvents()
assert not mw.isFullScreen() and stored()['Synthetic']['book']['focus'] is True
''')


def test_advancing_to_another_card_flushes_the_users_last_drag_before_the_visit_closes(tmp_path):
    scene(tmp_path, '''
mw.resize(1400,950)
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
drag(w,.64)
mw.reviewer.card=types.SimpleNamespace(id=42); ui.reviewer_shown(); app.processEvents()
assert w.visit.closed and abs(stored()['Synthetic']['book']['horizontal']-.64)<.01
ui.show_resources(source); w=ui._window; drain(); app.processEvents()
assert w.visit.card_id==42 and abs(ratio(w)-.64)<.01
w.close()
''')
