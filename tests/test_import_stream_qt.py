"""Import-stream transitions with real Qt controls and synthetic documents."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_webpage_queue_keeps_per_page_tags_lists_and_retry_choices(tmp_path):
    script = dedent('''
        import importlib
        from pathlib import Path
        import sys
        from types import ModuleType, SimpleNamespace
        import aqt
        from aqt.qt import QApplication
        app = QApplication([])
        aqt.mw = SimpleNamespace(col=None)
        package = ModuleType('stream_fixture')
        package.__path__ = [str(Path.cwd())]
        sys.modules[package.__name__] = package
        module = importlib.import_module('stream_fixture.frontend.webpage_dialog')
        dialog = module.WebpageToPdfDialog(addon_dir=sys.argv[1])
        dialog._book_details.reload_lists([(1, 'Maths')])
        dialog._book_details.set_details({'list_ids': [1], 'reason': 'First reason'})
        dialog._url_edit.setText('https://example.org/first')
        dialog._title_edit.setText('First')
        dialog._tag_edit.setTags(['topic', 'maths'])
        dialog._pin_tags.setChecked(True)
        dialog._queue_current()
        dialog._url_edit.setText('https://example.org/second')
        dialog._title_edit.setText('Second')
        dialog._tag_edit.setTags(['topic', 'geometry'])
        dialog._queue_current()
        assert dialog._queue.count() == 2
        dialog._queue.setCurrentRow(0)
        assert dialog._tag_edit.tags() == ['topic', 'maths']
        assert dialog._title_edit.text() == 'First'
        dialog._style_combo.setCurrentIndex(1)
        dialog._set_busy(True)
        generation = dialog._import_generation
        dialog._cancel_or_close()
        assert dialog._capture_cancel.is_set()
        assert not dialog._import_current(generation, dialog._profile)
        assert dialog._import_btn.isEnabled()
        assert dialog._queue.count() == 2
        assert dialog._style_combo.currentData() == 'article'
        assert dialog._book_details.details()['list_ids'] == [1]
        assert dialog.prepare_next_import()
        assert dialog._queue.count() == 1
        assert dialog._url_edit.text() == 'https://example.org/second'
        assert dialog._tag_edit.tags() == ['topic', 'geometry']
        assert dialog._book_details.details()['list_ids'] == [1]
        assert dialog._book_details.details()['reason'] == ''
        dialog._pin_tags.setChecked(False)
        assert dialog.prepare_next_import()
        assert dialog._queue.count() == 0
        assert dialog._url_edit.text() == ''
        assert dialog._tag_edit.tags() == []
        assert dialog._book_details.details()['list_ids'] == [1]
        # List reuse has its own pin; tag pinning does not control it.
        dialog._book_details._pin_lists.setChecked(False)
        dialog.prepare_next_import()
        assert dialog._book_details.details()['list_ids'] == []
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_file_import_list_pin_reuses_lists_only_for_new_file_drafts(tmp_path):
    script = dedent('''
        import sys
        from aqt.qt import QApplication
        from frontend.document_details import ImportBookDetails
        app = QApplication([])
        editor = ImportBookDetails(sys.argv[1], 'Captured')
        editor.reload_lists([(1, 'Maths'), (2, 'Reference')])
        editor.set_path('first.pdf')
        editor.set_details({'list_ids': [1], 'reason': 'Only the first file'})
        editor._pin_lists.setChecked(True)
        assert editor.for_path('not-yet-selected.pdf') == {'list_ids': [1], 'reason': '', 'source': ''}
        editor.set_path('second.pdf')
        assert editor.details() == {'list_ids': [1], 'reason': '', 'source': ''}
        editor.set_details({'list_ids': [2]})
        editor.set_path('third.epub')
        assert editor.details()['list_ids'] == [2]
        editor._pin_lists.setChecked(False)
        assert editor.for_path('another-new.epub')['list_ids'] == []
        editor.set_path('fourth.epub')
        assert editor.details()['list_ids'] == []
        editor.set_path('second.pdf')
        assert editor.details()['list_ids'] == [2]
        editor.set_path('first.pdf')
        assert editor.details() == {'list_ids': [1], 'reason': 'Only the first file', 'source': ''}
        editor.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_loaded_pdf_with_existing_name_is_flagged_and_unchecked(tmp_path):
    script = dedent('''
        import sys
        from types import SimpleNamespace
        import aqt
        from aqt.qt import QApplication, Qt
        app = QApplication([])
        aqt.mw = SimpleNamespace(col=SimpleNamespace(tags=SimpleNamespace(all=lambda: [])),
            addonManager=SimpleNamespace(getConfig=lambda *args: {}),
            taskman=SimpleNamespace(run_in_background=lambda *args, **kwargs: None))
        from backend import priority_manager
        sys.modules['priority_manager'] = priority_manager
        from frontend.pdf_dialog import AddPdfDialog
        from backend.pdf_manager import pdf_import_name_key
        dialog = AddPdfDialog(sys.argv[1])
        dialog._set_duplicate_names({pdf_import_name_key('MY BOOK.pdf')})
        dialog._add_paths(['My_Book.pdf', 'Different.pdf'])
        row = dialog._find_row('My_Book.pdf')
        assert 'duplicate' in dialog._table.item(row, 1).text().lower()
        assert not dialog._import_checks['My_Book.pdf'].isChecked()
        assert dialog._import_checks['Different.pdf'].isChecked()
        # Import remains possible when the user explicitly selects the flagged row.
        dialog._import_checks['My_Book.pdf'].setChecked(True)
        dialog._set_duplicate_names({pdf_import_name_key('MY BOOK.pdf')})
        assert dialog._import_checks['My_Book.pdf'].isChecked()
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
