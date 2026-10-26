"""Click the journey controls in real Qt; replace file readers and decoders only."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


SCENE = '''
import sys, types
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
qt = types.ModuleType('aqt.qt')
for module in (QtCore, QtGui, QtWidgets):
    for name in dir(module): setattr(qt, name, getattr(module, name))
app = QtWidgets.QApplication([])
app.setQuitOnLastWindowClosed(False)
mw = QtWidgets.QMainWindow()
mw.col = object()
mw.state = 'review'
web = QtWidgets.QTextEdit('Original question')
scripts = []
web.eval = scripts.append
bottom = QtWidgets.QTextEdit('Answer controls')
mw.setCentralWidget(QtWidgets.QWidget())
layout = QtWidgets.QVBoxLayout(mw.centralWidget())
layout.addWidget(web); layout.addWidget(bottom)
mw.reviewer = types.SimpleNamespace(card=types.SimpleNamespace(id=41), state='question',
    web=web, bottom=types.SimpleNamespace(web=bottom), auto_advance_enabled=True)
advances = []
mw.reviewer.auto_advance_if_enabled = lambda: advances.append(mw.reviewer.auto_advance_enabled)
aqt = types.ModuleType('aqt'); aqt.mw = mw
sys.modules.update({'aqt': aqt, 'aqt.qt': qt})
pending = []
class Query:
    def __init__(self, parent, op, success): self.op, self.success = op, success
    def failure(self, callback): self.failed = callback; return self
    def run_in_background(self): pending.append(self)
sys.modules['aqt.operations'] = types.SimpleNamespace(QueryOp=Query)
sys.modules['aqt.utils'] = types.SimpleNamespace(tooltip=lambda *a, **kw: None)
from frontend import study_workspace as ui
profile = ['Synthetic']
ui.get_active_profile = lambda: profile[0]
source = dict(kind='pdf', card_id=12, page=6, scroll=.4, quote='Two parallel pairs')
row = dict(id=5, source=source, recording_card_id=23, start=12., end=18., label='Proof')
document = dict(location=source, title='Geometry', available=True)
recording = dict(row, available=True, recording=dict(title='Lecture', kind='video'))
ui.load_card_resources = lambda *a: dict(documents=[document], recordings=[recording])
ui.list_recording_links = lambda *a, **kw: [row]
ui.resolve_link_rows = lambda *a: [recording]
ui.resolve_document = lambda *a: dict(path='synthetic.pdf', max_page=20)
ui.resolve_recording = lambda *a: dict(title='Lecture', kind='video')
class Reader(QtWidgets.QWidget):
    def __init__(self, snapshot, **kw):
        super().__init__(kw['owner'])
        self.state = types.SimpleNamespace(card_id=12, page=6, scroll_ratio=.4, zoom=1.5)
        self.view = QtWidgets.QTextEdit('Original passage', self)
class Player(QtWidgets.QWidget):
    def __init__(self, parent): super().__init__(parent); self.paused=True; self.loads=0; self.pos=0
    def load(self, recording, **kw): self.loads+=1; self.pos=kw['start']; self.paused=True
    def pause(self): self.paused=True
    def dispose(self): self.pause()
sys.modules['frontend.pdf_reference_workspace'] = types.SimpleNamespace(ReferenceWindow=Reader, _windows=[])
sys.modules['frontend.pdf_page_links'] = types.SimpleNamespace(pdf_page_count=lambda path: 20)
ui.RecordingPlayer = Player
def drain():
    while pending:
        query = pending.pop(0)
        query.success(query.op(mw.col))
def click(w, stage):
    QtTest.QTest.mouseClick(w.stage_buttons[stage], QtCore.Qt.MouseButton.LeftButton)
def bridge(stage, context=None, token=None):
    return ui.on_js_message((False, None), 'incremento_study:' + (token or ui._review_token) + ':' + stage,
                            mw.reviewer if context is None else context)
mw.show()
ui.reviewer_shown()
'''


def run_scene(body):
    result = subprocess.run([sys.executable, '-c', dedent(SCENE) + '\n' + dedent(body)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_clicking_card_textbook_video_round_trip_retains_the_live_views_and_positions():
    run_scene('''
        ui.show_resources(); w=ui._window; drain()
        click(w, 'book'); drain()
        book=w.reader
        assert w.stage_buttons['book'].isChecked() and w.book_host.isVisible()
        book.state.scroll_ratio=.62
        w.poll_location()
        click(w, 'video'); drain()
        player=w.player; player.pos=16.75; player.paused=False
        assert w.stage_buttons['video'].isChecked() and w.play_host.isVisible()
        click(w, 'book')
        assert player.paused and w.play_host.isHidden() and w.book_host.isVisible()
        click(w, 'video')
        assert player.pos == 16.75 and player.loads == 1 and player.paused
        click(w, 'card')
        assert not w.isVisible() and not w.visit.closed and w.visit.stage == 'card'
        assert web.isEnabled() and bottom.isEnabled() and mw.reviewer.auto_advance_enabled
        assert web.toPlainText() == 'Original question'
        assert ui._window is w and w.reader is book
        assert 'incremento-study-navigation' in scripts[-1]
        bridge('book'); drain()
        assert w.isVisible() and w.reader is book and book.state.scroll_ratio == .62 and book.state.zoom == 1.5
        assert not web.isEnabled() and not mw.reviewer.auto_advance_enabled
        bridge('video'); drain()
        assert w.player is player and player.pos == 16.75 and player.loads == 1
        w.close()
        assert web.isEnabled() and bottom.isEnabled() and mw.reviewer.auto_advance_enabled
        assert mw.reviewer.card.id == 41 and mw.reviewer.state == 'question'
    ''')


def test_resource_views_share_the_main_workspace_without_moving_the_live_reviewer():
    run_scene('''
        parent=web.parentWidget(); original_index=layout.indexOf(web)
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        assert w.window() is mw, 'Resources must occupy the same Anki window'
        assert web.parentWidget() is parent and web.isHidden() and bottom.isHidden()
        assert layout.indexOf(w) < layout.indexOf(web)
        book=w.reader
        click(w,'video'); drain(); player=w.player; player.pos=16.5
        assert w.window() is mw and w.reader is book
        click(w,'card')
        assert web.isVisible() and bottom.isVisible() and not w.isVisible()
        assert web.parentWidget() is parent and not w.visit.closed
        bridge('video'); drain()
        assert w.window() is mw and w.player is player and player.pos==16.5
        # Late Anki show/fade callbacks cannot expose answer controls over a video.
        web.show(); bottom.show(); app.processEvents()
        assert web.isHidden() and bottom.isHidden()
        w.close(); app.processEvents()
        assert web.isVisible() and bottom.isVisible()
        assert layout.indexOf(web)==original_index and web.parentWidget() is parent
    ''')


def test_resource_workspace_adapts_its_panels_without_reloading_media():
    run_scene('''
        mw.resize(1200,850)
        ui.show_resources(); w=ui._window; drain(); click(w,'video'); drain()
        reader,player=w.reader,w.player
        app.processEvents()
        assert w.splitter.orientation()==QtCore.Qt.Orientation.Horizontal
        assert not w.resource_panel.isVisible(), 'Let the recording occupy its panel'
        assert w.player_title.text()=='Lecture'
        assert w.book_title.text()
        mw.resize(650,850); app.processEvents()
        assert w.splitter.orientation()==QtCore.Qt.Orientation.Vertical
        assert w.reader is reader and w.player is player and player.loads==1
        w.more_resources.click(); app.processEvents()
        assert w.resource_panel.isVisible()
        click(w,'book'); app.processEvents()
        assert w.resource_panel.isVisible() and not w.play_host.isVisible()
        assert w.reader is reader
        w.close()
    ''')


def test_return_to_card_button_keeps_the_same_passage_and_player_ready():
    run_scene('''
        bridge('video'); drain(); w=ui._window; reader,player=w.reader,w.player
        player.pos=17.25
        back=next(b for b in w.findChildren(QtWidgets.QPushButton) if b.text()==ui.t('study_return_card'))
        back.click()
        assert not w.visit.closed and w.visit.stage=='card'
        assert web.isVisible() and bottom.isVisible()
        bridge('video'); drain()
        assert ui._window is w and w.reader is reader and w.player is player and player.pos==17.25
        w.close()
    ''')


def test_resource_surface_retirement_keeps_grading_hidden_after_leaving_review():
    run_scene('''
        bridge('video'); drain(); w=ui._window
        mw.state='deckBrowser'; ui.reset(); app.processEvents()
        assert w.visit.closed and ui._window is None
        assert web.isVisible() and bottom.isHidden()
        assert web.isEnabled() and bottom.isEnabled()
        assert not mw.reviewer.auto_advance_enabled
    ''')


def test_embedded_resources_suspend_only_review_shortcuts_and_restore_their_prior_state():
    run_scene('''
        grades=[]
        grade=QtGui.QShortcut(QtGui.QKeySequence('1'),mw)
        grade.activated.connect(lambda: grades.append('graded'))
        disabled=QtGui.QShortcut(QtGui.QKeySequence('2'),mw); disabled.setEnabled(False)
        global_action=QtGui.QShortcut(QtGui.QKeySequence('Ctrl+K'),mw)
        mw.stateShortcuts=[grade,disabled]
        bridge('video'); drain(); w=ui._window
        assert not grade.isEnabled() and not disabled.isEnabled() and global_action.isEnabled()
        QtTest.QTest.keyClick(w,QtCore.Qt.Key.Key_1); app.processEvents()
        assert grades==[]
        click(w,'card')
        assert grade.isEnabled() and not disabled.isEnabled()
        bridge('video'); drain()
        mw.state='deckBrowser'; ui.reset()
        assert not grade.isEnabled(), 'Old review shortcuts must stay disabled after leaving review'
    ''')


def test_existing_focused_reader_uses_a_standalone_workspace_and_restores_visibility():
    run_scene('''
        web.hide(); bottom.hide()
        ui.show_resources(source); drain(); w=ui._window
        assert w.isWindow() and w.window() is w and w.reader is not None
        assert web.isHidden() and bottom.isHidden()
        w.close()
        assert web.isHidden() and bottom.isHidden() and web.isEnabled()
    ''')


def test_context_summary_bounds_multiline_content_and_rejects_an_old_card_side():
    run_scene('''
        captures=[]
        web.evalWithCallback=lambda script,callback: captures.append(callback)
        bridge('book'); drain(); w=ui._window
        old=captures[-1]; old(('A long question\\n' * 50) + '<img src=x>')
        assert '\\n' not in w.context_title.text() and len(w.context_title.text())<=240
        assert w.context_title.textFormat()==QtCore.Qt.TextFormat.PlainText
        click(w,'card'); mw.reviewer.state='answer'; ui.reviewer_shown()
        bridge('book'); drain(); captures[-1]('The answer')
        old('Outdated question')
        assert w.context_title.text()=='The answer'
        callback=captures[-1]; profile[0]='Another'; ui.reset()
        callback('Wrong profile')
        assert w.visit.closed
    ''')


def test_same_card_answer_reveal_keeps_the_visit_but_a_new_card_retires_it():
    run_scene('''
        ui.show_resources(); w=ui._window; drain(); click(w,'book'); drain()
        book=w.reader; click(w,'card')
        old_token=ui._review_token
        mw.reviewer.state='answer'; web.setPlainText('Original answer'); ui.reviewer_shown()
        assert ui._window is w and not w.visit.closed and w.visit.side == 'answer'
        bridge('book', token=old_token)
        assert not w.isVisible()
        bridge('book'); drain()
        assert w.isVisible() and w.reader is book
        click(w,'card'); mw.reviewer.card=types.SimpleNamespace(id=42); ui.reviewer_shown()
        assert w.visit.closed and ui._window is None
    ''')


@pytest.mark.parametrize('kind', ['video', 'audio'])
def test_opening_recording_tab_directly_loads_its_textbook_context_and_exact_start(kind):
    run_scene(f"ui.resolve_recording=lambda *a: dict(title='Lecture',kind={kind!r})\n" + dedent('''
        ui.show_resources(); w=ui._window; drain()
        click(w,'video'); drain()
        assert w.reader is not None and w.source['page']==6
        assert w.player.loads==1 and w.player.pos==12 and w.player.paused
        assert w.visit.stage=='video' and w.stage_buttons['video'].isChecked()
        assert w.stage_buttons['video'].text()==ui.t('study_tab_' + KIND)
        click(w,'card'); bridge('video'); drain()
        assert w.player.loads==1 and w.player.pos==12
        w.close()
    ''').replace('KIND', repr(kind)))


def test_empty_stages_show_contextual_linking_help_and_keep_navigation_clickable():
    run_scene('''
        ui.load_card_resources=lambda *a: dict(documents=[], recordings=[])
        mw.resize(1200,850)
        ui.show_resources(); w=ui._window; drain()
        click(w,'video'); drain()
        app.processEvents()
        assert w.stage_buttons['video'].isChecked() and w.resources.count()==0
        assert w.status.text()==ui.t('study_no_recordings')
        assert w.add_recording.isEnabled()
        assert w.resource_panel.width()<=640 and w.resource_panel.height()<400
        click(w,'book'); drain()
        assert w.stage_buttons['book'].isChecked() and w.link_book.isVisible()
        assert w.status.text()==ui.t('study_no_textbooks')
        click(w,'card'); assert web.isEnabled() and not w.visit.closed
        ui.reset()
    ''')


@pytest.mark.parametrize('retire', ['card', 'profile'])
def test_delayed_reader_open_cannot_override_a_new_navigation_choice(retire):
    run_scene(dedent('''
        ui.show_resources(); w=ui._window; drain()
        click(w,'book')
        assert pending
        operation=pending.pop(0); result=operation.op(mw.col)
    ''') + ("click(w,'card')\n" if retire == 'card' else "profile[0]='Other'; w.poll_location()\n") + dedent('''
        operation.success(result)
        assert not w.isVisible() and w.reader is None
        if not w.visit.closed: w.close()
        assert web.isEnabled() and bottom.isEnabled()
    '''))


def test_review_navigation_rejects_another_origin_bad_token_and_unknown_stage():
    run_scene('''
        ui.show_resources(); w=ui._window; drain(); click(w,'card')
        for stage, context, token in [('book', object(), None), ('video', None, 'wrong'),
                                       ('invalid', None, None), ('book', None, '非令牌')]:
            bridge(stage, context, token)
            assert not w.isVisible()
        bridge('book'); drain()
        assert w.isVisible() and w.reader is not None
        w.close()
    ''')


def test_multiple_recordings_offer_a_choice_and_textbook_only_visits_explain_missing_card():
    run_scene('''
        second=dict(recording, id=6, recording_card_id=24, label='Second explanation')
        ui.load_card_resources=lambda *a: dict(documents=[document], recordings=[recording, second])
        ui.show_resources(); w=ui._window; drain(); click(w,'video'); drain()
        assert w.resources.count()==2 and w.player is None and w.visit.stage=='video'
        w.close()
        mw.state='deckBrowser'; ui.reviewer_shown()
        ui.show_resources(source); w=ui._window; drain()
        assert not w.stage_buttons['card'].isEnabled()
        assert w.stage_buttons['card'].toolTip()==ui.t('study_no_active_card')
        assert w.reader is not None and w.stage_buttons['book'].isChecked()
        assert any(b.isVisible() and b.text()==ui.t('study_close') for b in w.findChildren(QtWidgets.QPushButton))
        w.close()
    ''')


def test_native_stage_bar_fits_large_text_and_translated_labels(tmp_path):
    run_scene(f"preview_dir={str(tmp_path)!r}\n" + dedent('''
        from backend.i18n import initialize_language
        from pathlib import Path
        app.setStyle('Fusion')
        font=app.font(); font.setPointSize(18); app.setFont(font)
        for dark in (False,True):
            palette=QtGui.QPalette()
            for role,color in ((QtGui.QPalette.ColorRole.Window,'#2b2b2b' if dark else '#fafafa'),
                               (QtGui.QPalette.ColorRole.Button,'#36383d' if dark else '#f3f4f6'),
                               (QtGui.QPalette.ColorRole.WindowText,'#eeeeee' if dark else '#30343a'),
                               (QtGui.QPalette.ColorRole.ButtonText,'#eeeeee' if dark else '#30343a')):
                palette.setColor(role,QtGui.QColor(color))
            app.setPalette(palette)
            for locale in ('en','hr','zh-Hans'):
                initialize_language(locale)
                ui.show_resources(source); w=ui._window; drain()
                w.resize(800,600); app.processEvents()
                assert w.width() <= 800, (locale,w.width())
                for button in w.stage_buttons.values():
                    assert not button.icon().isNull()
                    icon=button.icon().pixmap(32,32).toImage()
                    assert all(icon.pixelColor(icon.width()-1,y).alpha()==0 for y in range(icon.height())), 'Icon is clipped at its right edge'
                    assert all(icon.pixelColor(x,icon.height()-1).alpha()==0 for x in range(icon.width())), 'Icon is clipped at its lower edge'
                    assert button.isVisible()
                    assert button.width() >= button.fontMetrics().horizontalAdvance(button.text())+16
                    assert w.rect().contains(QtCore.QRect(button.mapTo(w,QtCore.QPoint(0,0)),button.size()))
                assert w.stage_buttons['book'].isChecked()
                assert w.grab(QtCore.QRect(0,0,w.width(),150)).save(str(Path(preview_dir)/f'native-{locale}-{dark}.png'))
                w.close(); app.processEvents()
    '''))


def test_reviewer_navigation_buttons_dispatch_from_real_webengine_without_replacing_the_card():
    script = dedent('''
        from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from frontend.study_navigation import reviewer_navigation_script
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app=QApplication(['study-navigation-test'])
        # A real WebEngine page exercises Qt's DOM/JS without requiring a macOS
        # compositor surface. Separate browser tests cover the visual viewport.
        profile=QWebEngineProfile(app)
        page=QWebEnginePage(profile,app)
        failures=[]
        def exercise():
            try:
                def wait(start):
                    loop=QEventLoop(); results=[]; timer=QTimer(); timer.setSingleShot(True)
                    timer.timeout.connect(loop.quit); timer.start(5000)
                    def done(value): results.append(value); loop.quit()
                    start(done)
                    if not results: loop.exec()
                    timer.stop()
                    assert results, 'WebEngine callback timed out'
                    return results[0]
                def load(done):
                    page.loadFinished.connect(done)
                    page.setHtml('<div id="qa"><p id="question">Original question</p></div>')
                assert wait(load)
                def js(source): return wait(lambda done: page.runJavaScript(source,done))
                js('window.commands=[]; window.pycmd=(message)=>commands.push(message);')
                routes=[dict(stage=stage,label=label,current=stage=='card',command='nonce:'+stage)
                        for stage,label in [('card','Card'),('book','Textbook'),('video','Video')]]
                script=reviewer_navigation_script(routes,'Study resources')
                js(script); js(script)
                assert js("document.querySelectorAll('#incremento-study-navigation').length") == 1
                assert js("Boolean(document.getElementById('incremento-study-navigation').compareDocumentPosition(document.getElementById('qa')) & Node.DOCUMENT_POSITION_FOLLOWING)"), 'Study navigation belongs above the card'
                assert js("Array.from(document.querySelectorAll('#incremento-study-navigation button'),b=>b.textContent)")==['Card','Textbook','Video']
                assert js("document.querySelector('[aria-current=step]').dataset.studyStage")=='card'
                for stage in ('card','book','video'):
                    js("document.querySelector('[data-study-stage="+stage+"]').click()")
                assert js('commands')==['nonce:card','nonce:book','nonce:video']
                assert js("document.getElementById('question').textContent")=='Original question'
                assert js("getComputedStyle(document.querySelector('[data-study-stage=book]')).height")=='32px'
                routes[0]['label']='<img src=x onerror=alert(1)>'
                js(reviewer_navigation_script(routes,'Study resources'))
                assert js("document.querySelectorAll('#incremento-study-navigation img').length")==0
                assert js("document.getElementById('question').textContent")=='Original question'
                page.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                profile.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            except BaseException:
                import traceback
                failures.append(traceback.format_exc())
            finally:
                app.quit()
        # Match Anki's outer event loop before nested JS callback waits.
        QTimer.singleShot(0,exercise)
        app.exec()
        assert not failures, failures
    ''')
    result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', script], cwd=Path(__file__).resolve().parents[1],
        # No rendered view is needed here; disable native graphics entirely.
        env={**os.environ, 'QT_QPA_PLATFORM': 'minimal', 'QTWEBENGINE_DISABLE_SANDBOX': '1',
             'QTWEBENGINE_CHROMIUM_FLAGS': '--disable-gpu --disable-gpu-compositing --disable-software-rasterizer --use-gl=disabled'},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
