"""Publishing tools exercise real Qt without opening Anki or user data."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def run_qt(body):
    setup = '''
import sys, tempfile
sys.path[:0] = ['backend', 'frontend']
from aqt.qt import QApplication, QMainWindow, QWidget, QTextCursor
from frontend import writing_dock as writing
app = QApplication([])
writing.mw = QMainWindow()
writing.mw.setCentralWidget(QWidget())
writing._config = lambda config=None: {}
writing._flush_editor_state = lambda **kwargs: True
temporary = tempfile.TemporaryDirectory()
writing._ADDON_DIR = temporary.name
dock = writing._build_writing_dock()
writing._writing_profile = 'Synthetic'
writing._active_profile = lambda: 'Synthetic'
writing._current_writing_card_id = 7
writing._current_writing_relpath = 'writing/draft.md'
'''
    result = subprocess.run([sys.executable, '-c', setup + dedent(body)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_publishing_toolbar_preserves_source_and_formats_selected_blocks_with_one_undo():
    run_qt(r'''
        original = '# Draft\n\nOriginal **formatting** & <custom>\n'
        dock._editor.setPlainText(original)
        assert dock._editor.toPlainText() == original
        for name in ('writing_style', 'writing_insert', 'writing_more', 'writing_export'):
            button = dock.findChild(QWidget, name)
            assert button is not None and button.accessibleName()
        dock._editor.setPlainText('First\nSecond')
        dock._editor.selectAll()
        writing._apply_markdown_transform('h2')
        assert dock._editor.toPlainText() == '## First\n## Second'
        dock._editor.undo()
        assert dock._editor.toPlainText() == 'First\nSecond'
        dock._editor.setPlainText('Paragraph')
        dock._editor.moveCursor(QTextCursor.MoveOperation.End)
        writing._apply_markdown_transform('rule')
        assert dock._editor.toPlainText() == 'Paragraph\n\n---\n\n'
        dock.close()
    ''')


def test_export_uses_live_draft_and_cancel_or_profile_switch_writes_nothing():
    run_qt(r'''
        from pathlib import Path
        draft = '# Unsaved title\n\nLive **draft** & <script>alert(1)</script>'
        dock._editor.setPlainText(draft)
        target = Path(temporary.name) / 'export.md'
        writing.QFileDialog.getSaveFileName = lambda *args: (str(target), '')
        writing.tooltip = lambda *args, **kwargs: None
        writing._export_writing('markdown')
        assert target.read_text() == draft
        html = Path(temporary.name) / 'export.html'
        writing.QFileDialog.getSaveFileName = lambda *args: (str(html), '')
        writing._export_writing('html')
        rendered = html.read_text()
        assert '<html' in rendered and 'Live' in rendered and '<script>' not in rendered
        cancelled = Path(temporary.name) / 'cancelled.md'
        writing.QFileDialog.getSaveFileName = lambda *args: ('', '')
        writing._export_writing('markdown')
        assert not cancelled.exists()
        stale = Path(temporary.name) / 'stale.md'
        def switch_profile(*args):
            writing._active_profile = lambda: 'Other'
            return str(stale), ''
        writing.QFileDialog.getSaveFileName = switch_profile
        writing._export_writing('markdown')
        assert not stale.exists()
        dock.close()
    ''')


def test_narrow_preview_stacks_below_the_draft_without_changing_saved_visibility():
    run_qt('''
        from aqt.qt import Qt
        dock.setFloating(True)
        dock.resize(480, 720)
        dock.show()
        app.processEvents()
        assert dock._split.orientation() == Qt.Orientation.Vertical
        assert dock._preview_visible
        writing._apply_focus_mode(True)
        assert dock._preview_host.maximumWidth() >= dock.width()
        writing._apply_preview_visibility(False)
        dock.resize(1100, 800)
        app.processEvents()
        assert dock._split.orientation() == Qt.Orientation.Horizontal
        assert not dock._preview_visible and dock._preview_host.isHidden()
        assert dock._preview_host.maximumWidth() == 260
        dock.close()
    ''')


def test_translation_sends_only_reviewed_selection_after_acceptance_and_drops_stale_requests():
    run_qt('''
        from aqt.qt import QTextEdit
        from frontend import file_shell
        from urllib.parse import parse_qs, urlsplit
        opened = []
        file_shell.open_companion_url = lambda url: opened.append(url) or True
        original = 'Selected passage. Keep the rest private.'
        dock._editor.setPlainText(original)
        cursor = dock._editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(17, QTextCursor.MoveMode.KeepAnchor)
        dock._editor.setTextCursor(cursor)
        def cancel(dialog):
            assert dialog.findChild(QTextEdit).toPlainText() == 'Selected passage.'
            return 0
        writing.QDialog.exec = cancel
        writing._translate_writing()
        assert opened == []
        def accept(dialog):
            dialog.findChild(QTextEdit).setPlainText('Reviewed text')
            return 1
        writing.QDialog.exec = accept
        writing._translate_writing()
        assert len(opened) == 1
        assert parse_qs(urlsplit(opened[0]).query)['text'] == ['Reviewed text']
        def stale(dialog):
            writing._current_writing_card_id = 99
            return 1
        writing.QDialog.exec = stale
        writing._translate_writing()
        assert len(opened) == 1
        assert dock._editor.toPlainText() == original
        dock.close()
    ''')


def test_link_dialog_rejects_unsafe_targets_without_editing_and_safe_insert_is_undoable():
    run_qt('''
        dock._editor.setPlainText('A label')
        dock._editor.selectAll()
        errors = []
        writing.showInfo = lambda *args, **kwargs: errors.append(args)
        writing.QInputDialog.getText = lambda *args: ('javascript:alert(1)', True)
        writing._insert_writing_reference()
        assert errors and dock._editor.toPlainText() == 'A label'
        writing.QInputDialog.getText = lambda *args: ('https://example.test/path', True)
        writing._insert_writing_reference()
        assert dock._editor.toPlainText() == '[A label](<https://example.test/path>)'
        dock._editor.undo()
        assert dock._editor.toPlainText() == 'A label'
        dock._editor.selectAll()
        def stale(*args):
            writing._active_profile = lambda: 'Other'
            return 'https://example.test/path', True
        writing.QInputDialog.getText = stale
        writing._insert_writing_reference()
        assert dock._editor.toPlainText() == 'A label'
        dock.close()
    ''')


def test_failed_export_cancels_atomic_write_and_does_not_claim_success():
    run_qt('''
        from pathlib import Path
        target = Path(temporary.name) / 'existing.md'
        target.write_text('Previous export')
        dock._editor.setPlainText('Live draft')
        writing.QFileDialog.getSaveFileName = lambda *args: (str(target), '')
        calls, errors, success = [], [], []
        class ShortWrite:
            def __init__(self, path): pass
            def open(self, mode): return True
            def write(self, data): return len(data) - 1
            def cancelWriting(self): calls.append('cancel')
            def commit(self): raise AssertionError('Failed write must never commit')
        writing.QSaveFile = ShortWrite
        writing.showInfo = lambda *args, **kwargs: errors.append(args)
        writing.tooltip = lambda *args, **kwargs: success.append(args)
        writing._export_writing('markdown')
        assert calls == ['cancel'] and len(errors) == 1 and success == []
        assert target.read_text() == 'Previous export'
        assert dock._editor.toPlainText() == 'Live draft'
        dock.close()
    ''')
