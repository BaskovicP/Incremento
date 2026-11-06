"""Real Qt tab lifecycle over temporary writing files and supplemental databases."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def run_tabs(body):
    setup = '''
import sys, tempfile
sys.path[:0] = ['backend', 'frontend']
from aqt.qt import QApplication, QMainWindow, QWidget, QTextCursor, QTimer
from frontend import writing_dock as writing
from backend import paths
app = QApplication([])
writing.mw = QMainWindow()
writing.mw.setCentralWidget(QWidget())
writing.mw.taskman = type('Tasks', (), {'run_on_main': lambda self, cb: None})()
writing._config = lambda config=None: {}
temporary = tempfile.TemporaryDirectory()
writing._ADDON_DIR = temporary.name
paths.set_active_profile('Synthetic')
writing._active_profile = lambda: 'Synthetic'
def open_draft(cid, title):
    writing.show_writing_in_dock(cid, title, f'writing/{cid}.md', keep_open=True)
    return writing._writing_dock
'''
    result = subprocess.run([sys.executable, '-c', setup + dedent(body)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_tabs_preserve_live_documents_undo_cursor_and_per_card_session_and_progress():
    run_tabs('''
        dock = open_draft(11, 'First draft')
        first_document = dock._editor.document()
        dock._editor.setPlainText('First live draft')
        dock._editor.moveCursor(QTextCursor.MoveOperation.End)
        dock._editor.insertPlainText(' edited')
        cursor = dock._editor.textCursor().position()
        baseline = dock._session_baseline_words
        writing._apply_preview_visibility(False)
        writing._apply_font_scale(1.3)
        assert open_draft(22, 'Second draft') is dock
        dock._editor.setPlainText('Second live draft')
        second_document = dock._editor.document()
        assert second_document is not first_document
        assert writing.open_writing_card_ids() == [11, 22]
        dock._writing_tabs.setCurrentIndex(0)
        assert writing.current_writing_card_id() == 11
        assert dock._editor.document() is first_document
        assert dock._editor.toPlainText() == 'First live draft edited'
        assert dock._editor.textCursor().position() == cursor
        assert dock._session_baseline_words == baseline
        assert not dock._preview_visible and dock._font_scale == 1.3
        dock._editor.undo()
        assert dock._editor.toPlainText() == 'First live draft'
        open_draft(22, 'Second draft')
        assert dock._writing_tabs.count() == 2
        assert dock._editor.document() is second_document
        assert dock._editor.toPlainText() == 'Second live draft'
        from backend.db import get_writing_progress
        assert get_writing_progress(temporary.name, 'Synthetic', 11)['font_scale'] == 1.3
        assert writing.read_writing_text(temporary.name, 'writing/11.md', profile='Synthetic') == 'First live draft'
        writing.reset_for_profile_switch()
    ''')


def test_failed_save_blocks_tab_switch_and_close_without_losing_the_live_editor():
    run_tabs('''
        dock = open_draft(11, 'First')
        open_draft(22, 'Second')
        dock._editor.setPlainText('Unsaved second draft')
        real_write = writing.write_writing_text
        def fail(*args, **kwargs): raise OSError('Synthetic write failure')
        writing.write_writing_text = fail
        dock._writing_tabs.setCurrentIndex(0)
        assert writing.current_writing_card_id() == 22
        assert dock._writing_tabs.currentIndex() == 1
        assert dock._editor.toPlainText() == 'Unsaved second draft'
        dock._writing_tabs.tabCloseRequested.emit(1)
        assert dock._writing_tabs.count() == 2
        assert dock._editor.toPlainText() == 'Unsaved second draft'
        writing.write_writing_text = real_write
        writing.reset_for_profile_switch()
    ''')


def test_close_tabs_preserves_other_drafts_and_reopening_closed_tab_starts_a_new_session():
    run_tabs('''
        dock = open_draft(11, 'First')
        dock._editor.setPlainText('First live draft')
        open_draft(22, 'Second')
        dock._editor.setPlainText('Second live draft')
        dock._writing_tabs.tabCloseRequested.emit(0)
        assert writing.open_writing_card_ids() == [22]
        assert writing.current_writing_card_id() == 22
        assert dock._editor.toPlainText() == 'Second live draft'
        open_draft(11, 'First again')
        assert dock._session_baseline_words == 3
        assert dock._editor.toPlainText() == 'First live draft'
        dock._writing_tabs.tabCloseRequested.emit(1)
        assert writing.current_writing_card_id() == 22
        assert dock._editor.toPlainText() == 'Second live draft'
        dock._writing_tabs.tabCloseRequested.emit(0)
        assert writing.open_writing_card_ids() == []
        assert writing.current_writing_card_id() is None
        assert not dock.isVisible() and not writing._writing_keep_open
        writing.reset_for_profile_switch()
    ''')


def test_deferred_scroll_restore_from_another_tab_cannot_move_the_active_draft():
    run_tabs('''
        callbacks = []
        QTimer.singleShot = lambda delay, callback: callbacks.append(callback)
        dock = open_draft(11, 'First')
        open_draft(22, 'Second')
        dock._editor.setPlainText('Line\\n' * 400)
        dock.resize(800, 700)
        dock.show()
        app.processEvents()
        scroll = dock._editor.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        previous = scroll.value()
        assert previous > 0
        for callback in callbacks: callback()
        # Only the final tab's restore is allowed to run; the first callback is stale.
        scroll.setValue(previous)
        callbacks[0]()
        assert scroll.value() == previous
        writing.reset_for_profile_switch()
    ''')


def test_open_failure_keeps_the_previous_draft_identity_and_text_for_its_next_save():
    run_tabs('''
        dock = open_draft(11, 'First')
        dock._editor.setPlainText('Keep this draft')
        def fail_open(*args, **kwargs): raise OSError('Synthetic file-open failure')
        writing.ensure_writing_file = fail_open
        try:
            writing.show_writing_in_dock(22, 'Unavailable file', 'writing/22.md')
        except OSError:
            pass
        assert writing.current_writing_card_id() == 11
        assert dock._editor.toPlainText() == 'Keep this draft'
        assert writing._current_writing_relpath == 'writing/11.md'
        assert writing._flush_editor_state()
        assert writing.read_writing_text(temporary.name, 'writing/11.md', profile='Synthetic') == 'Keep this draft'
        writing.reset_for_profile_switch()
    ''')


def test_profile_switch_clears_all_tabs_and_late_save_callbacks_cannot_touch_the_new_editor():
    run_tabs('''
        callbacks = []
        writing.mw.taskman.run_on_main = callbacks.append
        dock = open_draft(11, 'First')
        dock._editor.setPlainText('First private draft')
        open_draft(22, 'Second')
        dock._editor.setPlainText('Second private draft')
        writing._active_profile = lambda: 'Other'
        writing.reset_for_profile_switch()
        assert writing.open_writing_card_ids() == []
        assert writing._writing_dock is None
        new_dock = open_draft(33, 'New profile')
        for callback in callbacks: callback()
        assert writing.open_writing_card_ids() == [33]
        assert 'private draft' not in new_dock._editor.toPlainText()
        assert writing.read_writing_text(temporary.name, 'writing/11.md', profile='Synthetic') == 'First private draft'
        assert writing.read_writing_text(temporary.name, 'writing/22.md', profile='Synthetic') == 'Second private draft'
        writing.reset_for_profile_switch()
    ''')


def test_saved_tab_order_keeps_extra_open_drafts_and_the_current_editor():
    run_tabs('''
        dock = open_draft(11, 'First')
        open_draft(22, 'Second')
        open_draft(33, 'Third')
        writing.reorder_writing_tabs([22, 11])
        assert writing.open_writing_card_ids() == [22, 11, 33]
        assert writing.current_writing_card_id() == 33
        assert dock._writing_tabs.tabData(dock._writing_tabs.currentIndex()) == 33
        writing.reset_for_profile_switch()
    ''')


def test_tab_limit_leaves_the_current_draft_active_and_open_tabs_reusable():
    run_tabs('''
        writing._MAX_WRITING_TABS = 2
        writing.tooltip = lambda *args, **kwargs: None
        dock = open_draft(11, 'First')
        open_draft(22, 'Second')
        assert writing.show_writing_in_dock(33, 'Third', 'writing/33.md') is False
        assert writing.open_writing_card_ids() == [11, 22]
        assert writing.current_writing_card_id() == 22
        assert writing.show_writing_in_dock(11, 'First', 'writing/11.md')
        assert writing.current_writing_card_id() == 11
        writing.reset_for_profile_switch()
    ''')


def test_tab_titles_have_visible_height_and_new_documents_keep_the_configured_text_scale():
    run_tabs('''
        dock = open_draft(11, 'First visible draft')
        open_draft(22, 'Second visible draft')
        dock.setFloating(True)
        dock.resize(1000, 800)
        dock.show()
        app.processEvents()
        bar = dock._writing_tabs
        assert bar.height() >= bar.tabRect(0).height() > 0
        assert dock._editor.document().defaultFont().pointSizeF() == dock._base_font_size * dock._font_scale
        writing.reset_for_profile_switch()
    ''')
