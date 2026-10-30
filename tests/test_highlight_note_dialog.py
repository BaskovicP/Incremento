"""Exercise the actual Qt editor in a clean, offscreen process."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_annotation_editor_formats_selection_roundtrips_lists_and_rejects_unsafe_links(tmp_path):
    result = subprocess.run([sys.executable, '-c', dedent('''
        import sys
        from pathlib import Path
        sys.path.extend([str(Path.cwd() / 'backend'), str(Path.cwd() / 'frontend')])
        from aqt.qt import QApplication, QTextCursor, QMimeData
        from frontend.highlight_note_dialog import HighlightNoteDialog
        app = QApplication([])
        dialog = HighlightNoteDialog(None, title='Note', excerpt='<b>literal source</b>', current_note='Rice theorem')
        editor = dialog._editor
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        for name in ('bold', 'italic', 'underline', 'strike'):
            dialog._actions[name].trigger()
        assert '<b>' in dialog.note_html() and '<i>' in dialog.note_html()
        assert '<u>' in dialog.note_html() and '<s>' in dialog.note_html()
        assert dialog.note_text() == 'Rice theorem'
        dialog._set_link('https://example.com/theorem')
        assert 'href="https://example.com/theorem"' in dialog.note_html()
        before = dialog.note_html()
        try:
            dialog._set_link('javascript:alert(1)')
            raise AssertionError('Unsafe URL was accepted')
        except ValueError:
            pass
        assert dialog.note_html() == before
        reopened = HighlightNoteDialog(None, title='Note', excerpt='', current_note=dialog.note_text(), current_note_html=before)
        assert reopened.note_html() == before
        cursor = reopened._editor.textCursor()
        cursor.setPosition(2)
        reopened._editor.setTextCursor(cursor)
        reopened._set_link('https://example.com/updated')
        assert reopened.note_text() == 'Rice theorem'
        assert 'https://example.com/updated' in reopened.note_html()
        assert 'https://example.com/theorem' not in reopened.note_html()
        cursor.setPosition(2)
        reopened._editor.setTextCursor(cursor)
        reopened._set_link('')
        assert '<a ' not in reopened.note_html()
        reopened._editor.selectAll()
        reopened._actions['clear'].trigger()
        assert '<b>' not in reopened.note_html() and '<a ' not in reopened.note_html()
        editor.setPlainText('First\\nSecond')
        editor.selectAll()
        dialog._actions['clear'].trigger()
        dialog._actions['bullets'].trigger()
        assert dialog.note_html() == '<ul><li>First</li><li>Second</li></ul>'
        dialog._actions['numbers'].trigger()
        assert dialog.note_html() == '<ol><li>First</li><li>Second</li></ol>'
        assert dialog.note_text() == 'First\\nSecond'
        editor.setPlainText('<b>old literal</b>')
        assert dialog.note_text() == '<b>old literal</b>'
        assert '&lt;b&gt;old literal&lt;/b&gt;' in dialog.note_html()
        editor.clear()
        mime = QMimeData()
        mime.setHtml('<b>pasted</b><img src="file:///tmp/private"><a href="javascript:bad()"> link</a>')
        editor.insertFromMimeData(mime)
        assert '<b>pasted</b>' in dialog.note_html()
        assert 'file:' not in dialog.note_html() and 'javascript:' not in dialog.note_html()
        from frontend import highlight_note_dialog as ui
        messages = []
        ui.showInfo = lambda message, **kwargs: messages.append(message)
        editor.setPlainText('x' * 65537)
        dialog.accept()
        assert dialog.result() == 0 and len(editor.toPlainText()) == 65537
        assert len(messages) == 1
        dialog.close()
        reopened.close()
    ''')], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
