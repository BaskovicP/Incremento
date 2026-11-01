"""Basic book info stays visible; the editable details pane is opt-in."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("outcome", ["success", "failure", "profile-switch", "collection-switch", "close"])
def test_bookshelf_visible_summaries_and_click_only_details(tmp_path, outcome):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QMessageBox, Qt
        from PyQt6.QtTest import QTest
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import paths
        from incremento.frontend import pdf_bookshelf as shelf
        import aqt.operations
        app = QApplication([])
        root, outcome = sys.argv[1:]
        paths.set_active_profile('Captured')
        pending, reads = [], []
        class Query:
            def __init__(self, **options):
                self.options = options
                pending.append(self)
            def failure(self, callback): self.failed = callback; return self
            def run_in_background(self): pass
        aqt.operations.QueryOp = Query
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: None))
        shelf.configured_priority_lower_is_more_important = lambda: True
        def progress(col, addon, profile, **options):
            reads.append((col, addon, profile, options['card_ids']))
            return [{'card_id': cid, 'read': 26 if cid == 1 else 2,
                     'total': 120 if cid == 1 else 4,
                     'unit': 'pages' if cid == 1 else 'estimated_pages'} for cid in options['card_ids']]
        shelf.document_progress_from_collection = progress
        def counts(addon, profile, documents, *, col, metric, cancelled):
            assert metric == 'cards'
            return {cid: 3 if cid == 1 else 0 for cid, kind in documents}
        shelf.load_document_statistics = counts
        entries = [shelf._BookshelfEntry(f'Book {cid:03}', cid, 'PDF' if cid % 2 else 'EPUB',
            source_filename=f'{cid}.pdf', saved_reason='A private saved reason', saved_source='A private source')
            for cid in range(1, 121)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=entries)
        assert pending == [], 'Opening must not wait for summary collection work'
        dialog.show()
        for _ in range(10): app.processEvents()
        assert dialog._details_panel.isHidden()
        assert not dialog._details_button.isChecked()
        assert len(pending) == 1, 'Visible books share one bounded background request'
        query = pending[0]
        result = query.options['op'](shelf.mw.col)
        assert reads[0][:3] == (shelf.mw.col, root, 'Captured')
        assert 1 in reads[0][3] and 1 <= len(reads[0][3]) <= 40
        assert 120 not in reads[0][3], 'Offscreen books wait until scrolled into view'
        first = dialog._list.item(0)
        if outcome == 'profile-switch': paths.set_active_profile('Other')
        if outcome == 'collection-switch': shelf.mw.col = object()
        if outcome == 'close': dialog.reject()
        if outcome == 'failure': query.failed(RuntimeError('Synthetic failure'))
        else: query.options['success'](result)
        if outcome in {'profile-switch', 'collection-switch', 'close'}:
            assert '26' not in first.text(), 'Stale results must not change the UI'
            paths.set_active_profile('Captured')
            dialog.reject()
            sys.exit(0)
        if outcome == 'failure':
            assert 'Page count unavailable' in first.text()
            assert 'Cards created unavailable' in first.text()
            assert '0 cards created' not in first.text()
        else:
            assert 'Read to page 26' in first.text()
            assert '3 cards created' in first.text()
            assert 'Contains 120 pages' in first.text()
            assert 'About 4 pages' in dialog._list.item(1).text()
            assert '0 cards created' in dialog._list.item(1).text()
        assert 'private' not in first.text() and 'private' not in first.toolTip()
        QTest.mouseClick(dialog._list.viewport(), Qt.MouseButton.LeftButton,
                         pos=dialog._list.visualItemRect(first).center())
        assert dialog._details_panel.isHidden(), 'Selecting a book does not open its details'
        QTest.mouseClick(dialog._details_button, Qt.MouseButton.LeftButton)
        assert dialog._details_panel.isVisible()
        assert dialog._book_details._reason.toPlainText() == 'A private saved reason'
        dialog.resize(1000, 450)
        for _ in range(3): app.processEvents()
        assert dialog.height() == 450, 'Details must fit a small window without forcing it taller'
        dialog._details_panel.ensureWidgetVisible(dialog._save_book_button)
        assert dialog._details_panel.verticalScrollBar().maximum() > 0
        dialog._book_details._reason.setPlainText('An unsaved draft')
        QTest.mouseClick(dialog._details_button, Qt.MouseButton.LeftButton)
        assert dialog._details_panel.isHidden()
        QTest.mouseClick(dialog._details_button, Qt.MouseButton.LeftButton)
        assert dialog._book_details._reason.toPlainText() == 'An unsaved draft'
        dialog._view_combo.setCurrentIndex(dialog._view_combo.findData('reasons'))
        assert 'A private saved reason' in dialog._list.item(0).text()
        assert dialog._details_panel.isVisible(), 'Filtering and rebuilding tiles must preserve the open pane'
        QMessageBox.question = lambda *a, **kw: QMessageBox.StandardButton.Discard
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), outcome],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('field,expected_work', [
    ('', []), ('reason', []), ('cards_created', ['cards']),
    ('read_progress', ['progress']), ('page_count', ['progress']),
])
def test_bookshelf_only_loads_the_statistics_selected_for_display(tmp_path, field, expected_work):
    script = dedent('''
        import json, sys, types
        from pathlib import Path
        from aqt.qt import QApplication
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import paths
        from incremento.frontend import pdf_bookshelf as shelf
        import aqt.operations
        app = QApplication([])
        root, field, expected = sys.argv[1:]
        paths.set_active_profile('Captured')
        pending, work = [], []
        shelf.mw = types.SimpleNamespace(
            addonManager=types.SimpleNamespace(getConfig=lambda key: {'bookshelf_caption_fields': [field] if field else []}),
            col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: None))
        shelf.configured_priority_lower_is_more_important = lambda: True
        class Query:
            def __init__(self, **options): self.options=options; pending.append(self)
            def failure(self, callback): return self
            def run_in_background(self): pass
        aqt.operations.QueryOp = Query
        def progress(*args, **options):
            work.append('progress')
            return [{'card_id': 1, 'read': 26, 'total': 120, 'unit': 'pages'}]
        def cards(*args, **options):
            work.append('cards')
            return {1: 3}
        shelf.document_progress_from_collection = progress
        shelf.load_document_statistics = cards
        entry = shelf._BookshelfEntry('A book', 1, 'PDF', saved_reason='Practise maths')
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=[entry])
        dialog.show()
        for _ in range(5): app.processEvents()
        if json.loads(expected):
            assert len(pending) == 1
            result = pending[0].options['op'](shelf.mw.col)
            pending[0].options['success'](result)
        else:
            assert pending == []
        assert work == json.loads(expected)
        text = dialog._list.item(0).text()
        expected_text = {'': 'A book', 'reason': 'A book\\nPractise maths',
                         'cards_created': 'A book\\n3 cards created',
                         'read_progress': 'A book\\nRead to page 26',
                         'page_count': 'A book\\nContains 120 pages'}
        assert text == expected_text[field], text
        dialog.reject()
    ''')
    import json
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), field, json.dumps(expected_work)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('outcome', ['save', 'cancel', 'failure', 'profile-switch', 'collection-switch'])
def test_bookshelf_display_picker_saves_only_accepted_current_choices(tmp_path, outcome):
    script = dedent('''
        import copy, sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QDialogButtonBox, QTimer
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import config_service, paths
        from incremento.frontend import pdf_bookshelf as shelf
        from incremento.frontend.settings_dialog import BookshelfDisplayOptions
        import aqt.operations
        app = QApplication([])
        root, outcome = sys.argv[1:]
        paths.set_active_profile('Captured')
        saved = config_service.normalize_config({'future': {'keep': True}})
        original = copy.deepcopy(saved)
        writes, pending, errors = [], [], []
        def write(key, config):
            assert key == 'incremento'
            if outcome == 'failure': raise OSError('Synthetic save failure')
            writes.append(copy.deepcopy(config))
            saved.clear(); saved.update(copy.deepcopy(config))
        manager = types.SimpleNamespace(getConfig=lambda key: saved, writeConfig=write)
        shelf.mw = types.SimpleNamespace(addonManager=manager,
            col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: None))
        shelf.tooltip = lambda *a, **kw: None
        shelf.configured_priority_lower_is_more_important = lambda: True
        class Query:
            def __init__(self, **options): self.options=options; pending.append(self)
            def failure(self, callback): return self
            def run_in_background(self): pass
        aqt.operations.QueryOp = Query
        entry = shelf._BookshelfEntry('A book', 1, 'PDF', source_filename='one.pdf',
            saved_reason='Practise maths', saved_source='<img src="file:///should-not-load.png">',
            tags=('Maths',), list_names=('Reference',))
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=[entry])
        dialog.show()
        for _ in range(5): app.processEvents()
        assert saved == original and writes == []
        first_query = pending[0]
        def choose():
            picker = app.activeModalWidget()
            try:
                options = picker.findChild(BookshelfDisplayOptions)
                assert options.fields == ['read_progress', 'cards_created', 'page_count']
                for key, checkbox in options._checkboxes.items():
                    checkbox.setChecked(key in {'reason', 'source', 'tags'})
                if outcome == 'profile-switch': paths.set_active_profile('Other')
                if outcome == 'collection-switch': shelf.mw.col = object()
                button = QDialogButtonBox.StandardButton.Cancel if outcome == 'cancel' else QDialogButtonBox.StandardButton.Save
                picker.findChild(QDialogButtonBox).button(button).click()
            except BaseException as error:
                errors.append(error)
                picker.reject()
        QTimer.singleShot(0, choose)
        dialog._display_button.click()
        assert errors == [], errors
        if outcome == 'save':
            assert saved['bookshelf_caption_fields'] == ['reason', 'source', 'tags']
            assert saved['future'] == {'keep': True}
            text = dialog._list.item(0).text()
            assert 'Practise maths' in text and 'Maths' in text
            assert 'Reference' not in text and 'Read to' not in text
            assert 'Loading book info' not in text
            assert '<img src="file:///should-not-load.png">' in text
            assert '<img' not in dialog._list.item(0).toolTip(), 'Caption metadata must stay inert in tooltips'
            assert '&lt;img' in dialog._list.item(0).toolTip()
            assert len(writes) == 1
            assert len(pending) == 1, 'Metadata-only captions must not start statistics scans'
            first_query.options['success']({1: {'read': 99, 'cards': 7, 'total': 100}})
            assert dialog._list.item(0).text() == text
            dialog.reject()
            reopened = shelf._DocumentBookshelfDialog(addon_dir=root, entries=[entry])
            assert reopened._caption_fields == ['reason', 'source', 'tags']
            assert 'Practise maths' in reopened._list.item(0).text()
            reopened.reject()
        else:
            assert saved == original and writes == []
            assert 'Practise maths' not in dialog._list.item(0).text()
            dialog.reject()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), outcome],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
