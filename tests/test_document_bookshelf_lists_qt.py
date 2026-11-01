"""Real Qt interactions, entirely offscreen and in disposable profiles."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def test_typing_acquisition_source_does_not_rescan_lists_or_reason(tmp_path):
    # Source edits must do constant work, even with the maximum library size.
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication
        from PyQt6.QtTest import QTest
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.frontend.document_details import BookDetailsEditor
        app = QApplication([])
        editor = BookDetailsEditor(sys.argv[1], 'Captured',
            available_lists=[(i + 1, f'List {i}') for i in range(500)])
        editor._reason.setPlainText('Reason ' * 280)
        changes = []
        editor.changed.connect(lambda: changes.append(editor._source.text()))
        reads = []
        original = editor.raw_details
        def read_details():
            reads.append(True)
            return original()
        editor.raw_details = read_details

        source = 'https://discord.com/channels/123456789/987654321'
        QTest.keyClicks(editor._source, source)

        assert editor._source.text() == source
        assert len(changes) == len(source)
        assert reads == [], f'Source typing scanned the other fields {len(reads)} times'
        assert editor.details()['source'] == source
        editor.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pdf_source_typing_uses_loaded_shortcuts_and_refreshes_bindings_on_settings_change(tmp_path):
    # Exercise the app-wide shortcut filter as well as the actual import field.
    # Typing must never reread/normalize settings; explicit refreshes must do so.
    script = dedent('''
        import ast, json, sys, types
        from pathlib import Path
        import aqt
        from aqt.qt import QApplication, QAction, QEvent, QKeySequence, QObject, Qt
        from PyQt6.QtTest import QTest
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        app = QApplication([])
        root = sys.argv[1]
        from incremento.backend import paths
        paths.set_active_profile('Captured')
        aqt.mw = types.SimpleNamespace(col=types.SimpleNamespace(tags=types.SimpleNamespace(all=lambda: [])),
            addonManager=object(), taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: None))
        from incremento.frontend.pdf_dialog import AddPdfDialog
        from incremento.frontend.settings_dialog import resolved_runtime_shortcuts
        dialog = AddPdfDialog(root, deck_names=['Topics'])
        source_pdf = str(Path(root) / 'synthetic.pdf')
        Path(source_pdf).write_bytes(b'%PDF-1.7')
        dialog._add_paths([source_pdf])
        editor = dialog._book_details
        editor._reason.setPlainText('Practise mental arithmetic')
        dialog.show()
        editor._source.setFocus()
        app.processEvents()

        config = json.loads((Path.cwd() / 'config.json').read_text())
        config['shortcuts'] = {'open_settings': 'Alt+9'}
        reads = []
        def load_config(*_args):
            reads.append(True)
            return config
        settings_action = QAction('Settings', dialog)
        triggered = []
        settings_action.triggered.connect(lambda: triggered.append(True))
        actions = {key: [] for key in resolved_runtime_shortcuts({})}
        actions['open_settings'] = [settings_action]
        namespace = dict(globals(), mw=aqt.mw, _shortcut_actions=actions, _runtime_shortcuts={},
            _load_addon_config=load_config,
            _migrate_persisted_config=lambda *_args: (load_config(), False))
        names = {'_apply_shortcuts_from_config', '_configured_shortcut_text',
                 '_event_matches_shortcut_text', '_invoke_shortcut_action', '_ConfiguredShortcutFilter'}
        tree = ast.parse((Path.cwd() / '__init__.py').read_text())
        nodes = [node for node in tree.body if getattr(node, 'name', '') in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '__init__.py', 'exec'), namespace)
        namespace['_apply_shortcuts_from_config']()
        assert len(reads) == 1
        shortcut_filter = namespace['_ConfiguredShortcutFilter'](app)
        app.installEventFilter(shortcut_filter)
        reads.clear()

        source = 'https://discord.com/channels/123456789/987654321'
        QTest.keyClicks(editor._source, source)
        app.processEvents()
        assert editor._source.text() == source
        assert reads == [], f'Typing reloaded settings {len(reads)} times'
        assert triggered == []
        assert editor.for_path(source_pdf)['source'] == source

        QTest.keyClick(editor._source, Qt.Key.Key_9, Qt.KeyboardModifier.AltModifier)
        assert triggered == [True]
        config['shortcuts']['open_settings'] = 'Alt+8'
        namespace['_apply_shortcuts_from_config']()
        assert len(reads) == 1
        reads.clear()
        QTest.keyClick(editor._source, Qt.Key.Key_9, Qt.KeyboardModifier.AltModifier)
        assert triggered == [True]
        QTest.keyClick(editor._source, Qt.Key.Key_8, Qt.KeyboardModifier.AltModifier)
        assert triggered == [True, True]
        assert reads == []
        assert settings_action.shortcut() == QKeySequence('Alt+8')
        app.removeEventFilter(shortcut_filter)
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("view", ["covers", "reasons"])
def test_bookshelf_groups_a_selection_without_replacing_notes_or_other_lists(tmp_path, view):
    script = dedent('''
        import sys, types
        from concurrent.futures import Future
        from pathlib import Path
        from aqt.qt import QApplication, QInputDialog, QItemSelectionModel, QMenu, QMessageBox, Qt
        from PyQt6.QtTest import QTest
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import document_lists as library, paths
        from incremento.frontend import pdf_bookshelf as shelf
        app = QApplication([])
        root, view = sys.argv[1:]
        paths.set_active_profile('Captured')
        shelf.configured_priority_lower_is_more_important = lambda: True
        pending = []
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: pending.append((a, kw))))
        old = library.create_document_list(root, 'Captured', 'Reference')
        target = library.create_document_list(root, 'Captured', 'Maths')
        for kind, filename in [('pdf', 'one.pdf'), ('pdf', 'two.pdf'), ('epub', 'three.epub')]:
            library.save_document_details(root, 'Captured', kind, filename,
                {'reason': filename, 'source': 'A lecturer', 'list_ids': [old]})
        entries = [shelf._BookshelfEntry('One', 1, 'PDF', source_filename='one.pdf'),
                   shelf._BookshelfEntry('Two', 2, 'PDF', source_filename='two.pdf'),
                   shelf._BookshelfEntry('Three', 3, 'EPUB', source_filename='three.epub')]
        entries = shelf._with_library_details(entries, library.load_document_library(root, 'Captured'))
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=entries)
        dialog._view_combo.setCurrentIndex(dialog._view_combo.findData(view))
        dialog.show()
        app.processEvents()
        items = {dialog._list.item(i).data(Qt.ItemDataRole.UserRole).card_id: dialog._list.item(i)
                 for i in range(dialog._list.count())}
        QTest.mouseClick(dialog._list.viewport(), Qt.MouseButton.LeftButton,
                         pos=dialog._list.visualItemRect(items[1]).center())
        dialog._book_details._reason.setPlainText('An unsaved reason')
        QTest.mouseClick(dialog._list.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         pos=dialog._list.visualItemRect(items[3]).center())
        selected = lambda: {item.data(Qt.ItemDataRole.UserRole).card_id for item in dialog._list.selectedItems()}
        assert selected() == {1, 3}, selected()
        assert not dialog._book_details.isEnabled()
        assert not dialog._open_button.isEnabled()
        QTest.mouseClick(dialog._list.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         pos=dialog._list.visualItemRect(items[3]).center())
        assert selected() == {1}
        assert dialog.selected_card_id == 1
        assert dialog._book_current_key == ('pdf', 'one.pdf')
        assert dialog._book_details._reason.toPlainText() == 'An unsaved reason'
        QTest.mouseClick(dialog._list.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         pos=dialog._list.visualItemRect(items[3]).center())
        QInputDialog.getItem = lambda *a, **kw: ('Maths', True)
        pending.clear()
        before = library.load_document_library(root, 'Captured')
        if view == 'covers':
            dialog._add_to_list_button.click()
        else:
            menus = []
            QMenu.exec = lambda menu, _position: menus.append(menu)
            dialog._show_context_menu(dialog._list.visualItemRect(items[1]).center())
            assert selected() == {1, 3}
            assert len(menus[0].actions()) == 1
            menus[0].actions()[0].trigger()
        assert len(pending) == 1
        assert library.load_document_library(root, 'Captured') == before
        (work, done), options = pending.pop()
        assert options == {'uses_collection': False}
        future = Future()
        future.set_result(work())
        done(future)
        assert selected() == {1, 3}, selected()
        books = library.load_document_library(root, 'Captured')['books']
        assert books[('pdf', 'one.pdf')] == {'reason': 'one.pdf', 'source': 'A lecturer', 'list_ids': [old, target]}
        assert books[('epub', 'three.epub')]['list_ids'] == [old, target]
        assert books[('pdf', 'two.pdf')]['list_ids'] == [old]
        assert dialog._book_drafts[('pdf', 'one.pdf')] == {
            'reason': 'An unsaved reason', 'source': 'A lecturer', 'list_ids': [old, target]}
        dialog._list.clearSelection()
        dialog._list.setCurrentRow(0, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        dialog._save_book_details()
        assert library.load_document_library(root, 'Captured')['books'][('pdf', 'one.pdf')]['list_ids'] == [old, target]
        QMessageBox.question = lambda *a, **kw: QMessageBox.StandardButton.Discard
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), view],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("outcome", ["selection-change", "profile-switch", "close", "failure"])
def test_bulk_grouping_captures_selection_and_handles_stale_or_failed_callbacks(tmp_path, outcome):
    script = dedent('''
        import sys, types
        from concurrent.futures import Future
        from pathlib import Path
        from aqt.qt import QApplication, QInputDialog, QItemSelectionModel, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import document_lists as library, paths
        from incremento.frontend import pdf_bookshelf as shelf
        app = QApplication([])
        root, outcome = sys.argv[1:]
        paths.set_active_profile('Captured')
        shelf.configured_priority_lower_is_more_important = lambda: True
        notices = []
        shelf.tooltip = lambda message, **kw: notices.append(message)
        pending = []
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: pending.append(a)))
        target = library.create_document_list(root, 'Captured', 'Maths')
        entries = [shelf._BookshelfEntry(str(i), i, 'PDF', source_filename=f'{i}.pdf') for i in range(1, 4)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=entries)
        dialog._list.selectAll()
        dialog._list.item(2).setSelected(False)
        QInputDialog.getItem = lambda *a, **kw: ('Maths', True)
        pending.clear()
        dialog._add_to_list_button.click()
        work, done = pending.pop()
        if outcome == 'selection-change':
            dialog._list.setCurrentRow(2, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        elif outcome == 'profile-switch':
            paths.set_active_profile('Other')
        elif outcome == 'close':
            dialog.reject()
        else:
            library.delete_document_list(root, 'Captured', target)
        future = Future()
        try:
            future.set_result(work())
        except Exception as error:
            future.set_exception(error)
        done(future)
        books = library.load_document_library(root, 'Captured')['books']
        if outcome in ('close', 'failure'):
            assert books == {}
            assert all(entry.list_ids == () for entry in dialog._entries)
        else:
            assert set(books) == {('pdf', '1.pdf'), ('pdf', '2.pdf')}
        if outcome == 'selection-change':
            assert [item.data(Qt.ItemDataRole.UserRole).card_id for item in dialog._list.selectedItems()] == [3]
        if outcome == 'profile-switch':
            assert library.load_document_library(root, 'Other') == {'lists': [], 'books': {}}
            assert all(entry.list_ids == () for entry in dialog._entries)
        if outcome == 'failure':
            assert dialog._add_to_list_button.isEnabled()
            assert notices == [shelf.t('reader_library_group_error')]
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), outcome],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_preserves_multi_selection_across_batches_and_respects_a_new_selection(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QItemSelectionModel, Qt
        from PyQt6.QtTest import QTest
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.frontend import pdf_bookshelf as shelf
        app = QApplication([])
        root = sys.argv[1]
        shelf._active_profile = lambda: 'Captured'
        shelf.configured_priority_lower_is_more_important = lambda: True
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **kw: None))
        entries = [shelf._BookshelfEntry(f'{i:03}', i, 'PDF', source_filename=f'{i}.pdf') for i in range(80)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=entries)
        for _ in range(4): app.processEvents()
        dialog._list.clearSelection()
        for i in (5, 60): dialog._list.item(i).setSelected(True)
        selected = lambda: {item.data(Qt.ItemDataRole.UserRole).card_id for item in dialog._list.selectedItems()}
        dialog._refresh()
        dialog._refresh()  # A background result can refresh before the next batch mounts.
        for _ in range(4): app.processEvents()
        assert selected() == {5, 60}, selected()

        dialog._refresh()
        dialog._list.setCurrentRow(20, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        for _ in range(4): app.processEvents()
        assert selected() == {20}, selected()
        dialog._view_combo.setCurrentIndex(dialog._view_combo.findData('reasons'))
        for _ in range(4): app.processEvents()
        dialog._list.setCurrentRow(0, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        QTest.keyClick(dialog._list, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
        assert selected() == {0, 1}, selected()
        QTest.keyClick(dialog._list, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert len(selected()) == 80
        dialog.reject()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_webpage_pdf_import_exposes_shared_list_and_acquisition_details(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        import aqt
        from aqt.qt import QApplication, QTimer, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        app = QApplication([])
        aqt.mw = types.SimpleNamespace(col=None)
        from incremento.backend import document_lists as library, paths
        from incremento.frontend.webpage_dialog import WebpageToPdfDialog
        root = sys.argv[1]
        paths.set_active_profile('Captured')
        list_id = library.create_document_list(root, 'Captured', 'Mental maths')
        dialog = WebpageToPdfDialog(addon_dir=root)
        editor = dialog._book_details
        def choose_lists():
            picker = app.activeModalWidget()
            picker._lists.item(0).setCheckState(Qt.CheckState.Checked)
            picker.accept()
        QTimer.singleShot(0, choose_lists)
        editor._edit_lists.click()
        editor._reason.setPlainText('Practise multiplication')
        editor._source.setText('A mathematics blog')

        assert dialog.document_details == {'reason': 'Practise multiplication',
            'source': 'A mathematics blog', 'list_ids': [list_id]}
        editor._reason.setPlainText('x' * 2001)
        dialog._url_edit.setText('https://example.org/article')
        dialog._on_import()
        assert dialog._pdf_path is None
        assert dialog._import_btn.isEnabled()
        assert dialog._status_lbl.text()
        editor._reason.clear()
        dialog.reject()
        assert library.load_document_library(root, 'Captured')['books'] == {}
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_edits_shared_document_notes_filters_lists_and_keeps_import_drafts(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication, QInputDialog, QItemSelectionModel, QMessageBox, QTimer, Qt
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.backend import document_lists as library, paths
        from incremento.frontend import pdf_bookshelf as shelf
        from incremento.frontend.document_details import ImportBookDetails
        app = QApplication([])
        root = sys.argv[1]
        paths.set_active_profile('Captured')
        shelf._active_profile = paths.get_active_profile
        shelf.configured_priority_lower_is_more_important = lambda: True
        shelf._start = None
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda:root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **k:None))
        biology=library.create_document_list(root,'Captured','Biology')
        psychology=library.create_document_list(root,'Captured','Psychology')
        entries=[shelf._BookshelfEntry('Behave',1,'PDF',source_filename='shared.pdf'),
                 shelf._BookshelfEntry('A second card for Behave',2,'PDF',source_filename='shared.pdf'),
                 shelf._BookshelfEntry('An EPUB',3,'EPUB',source_filename='other.epub')]
        dialog=shelf._DocumentBookshelfDialog(addon_dir=root,entries=entries)
        editor=dialog._book_details
        assert dialog._splitter.count()==3
        editor._reason.setPlainText('ChatGPT suggested it for biology.')
        editor._source.setText('A blog I liked')
        def choose_lists():
            picker = app.activeModalWidget()
            for i in range(picker._lists.count()):
                picker._lists.item(i).setCheckState(Qt.CheckState.Checked)
            picker.accept()
        QTimer.singleShot(0, choose_lists)
        editor._edit_lists.click()
        dialog._save_book_details()
        details=library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]
        assert details['list_ids']==[biology,psychology]
        assert details['reason']=='ChatGPT suggested it for biology.'
        assert {e.saved_reason for e in dialog._entries if e.source_filename=='shared.pdf'}=={details['reason']}
        for i in range(dialog._list_sidebar.count()):
            if dialog._list_sidebar.item(i).data(Qt.ItemDataRole.UserRole)==biology:
                dialog._list_sidebar.setCurrentRow(i)
        assert dialog._list.count()==2
        dialog._search.setText('ChatGPT')
        dialog._filter_timer.timeout.emit()
        assert dialog._list.count()==2
        editor._reason.setPlainText('An unsaved edit')
        # A plain click replaces the selection; Ctrl/Cmd-click adds to it.
        dialog._list.setCurrentRow(1, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        assert editor._reason.toPlainText()=='An unsaved edit'
        paths.set_active_profile('Other')
        dialog._save_book_details()
        assert library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]==details
        paths.set_active_profile('Captured')
        dialog._save_book_details()
        assert dialog._list.count()==0  # The saved reason no longer matches ChatGPT.
        dialog._search.clear()
        dialog._filter_timer.timeout.emit()
        editor._reason.setPlainText('Keep this draft until I choose Save')
        QMessageBox.question=lambda *a,**kw:QMessageBox.StandardButton.Cancel
        dialog._accept_reference(beside=False)
        assert dialog.reference_mode=='main'
        assert not dialog._pdf_metadata_cancelled.is_set()
        assert library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]['reason']=='An unsaved edit'
        QMessageBox.question=lambda *a,**kw:QMessageBox.StandardButton.Save
        dialog.reject()
        assert library.load_document_library(root,'Captured')['books'][('pdf','shared.pdf')]['reason']=='Keep this draft until I choose Save'

        imports=ImportBookDetails(root,'Captured')
        imports.set_path('one.pdf')
        imports._reason.setPlainText('First reason')
        imports._source.setText('First source')
        imports.set_path('two.epub')
        assert imports._reason.toPlainText()==''
        imports._reason.setPlainText('Second reason')
        imports.set_path('one.pdf')
        assert imports._reason.toPlainText()=='First reason'
        assert imports.for_path('two.epub')['reason']=='Second reason'
        assert imports.for_path('one.pdf')['source']=='First source'
        imports.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ,"QT_QPA_PLATFORM":"offscreen"},
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_lists_pane_can_expand_right_and_shrink_with_the_divider(tmp_path):
    script = dedent('''
        import sys, types
        from pathlib import Path
        from aqt.qt import QApplication
        package = types.ModuleType('incremento')
        package.__path__ = [str(Path.cwd())]
        sys.modules['incremento'] = package
        from incremento.frontend import pdf_bookshelf as shelf
        app = QApplication([])
        root = sys.argv[1]
        shelf._active_profile = lambda: 'Captured'
        shelf.configured_priority_lower_is_more_important = lambda: True
        shelf.mw = types.SimpleNamespace(
            col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: root)),
            taskman=types.SimpleNamespace(run_in_background=lambda *a, **k: None),
        )
        dialog = shelf._DocumentBookshelfDialog(addon_dir=root, entries=[])
        dialog.resize(1800, 840)
        dialog.show()
        app.processEvents()

        sidebar = dialog._splitter.widget(0)
        initial_width = sidebar.width()
        dialog._splitter.moveSplitter(600, 1)
        app.processEvents()
        assert sidebar.width() >= 580, sidebar.width()
        assert dialog._list_sidebar.width() >= 560

        dialog._splitter.moveSplitter(initial_width, 1)
        app.processEvents()
        assert abs(sidebar.width() - initial_width) <= 2
        dialog.reject()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["pdf", "epub"])
def test_native_import_dialog_passes_each_files_details_to_its_manager(tmp_path, kind):
    script = dedent('''
        import importlib, sys, types
        from pathlib import Path
        import aqt
        from aqt.qt import QApplication, QTimer, Qt
        app=QApplication([])
        package=types.ModuleType('incremento')
        package.__path__=[str(Path.cwd())]
        sys.modules['incremento']=package
        root,kind=sys.argv[1:]
        from incremento.backend import paths, document_lists as library, priority_manager
        paths.set_active_profile('Captured')
        col=types.SimpleNamespace(tags=types.SimpleNamespace(all=lambda:[]))
        aqt.mw=types.SimpleNamespace(col=col,taskman=types.SimpleNamespace(run_in_background=lambda *a,**k:None))
        module=importlib.import_module('incremento.frontend.'+kind+'_dialog')
        manager=importlib.import_module('incremento.backend.'+kind+'_manager')
        calls=[]
        setattr(manager,'add_'+kind+'_card',lambda *args,**kwargs:calls.append((args,kwargs)) or len(calls))
        priority_manager.set_priority=lambda *a,**k:None
        cls=getattr(module,'Add'+('Pdf' if kind=='pdf' else 'Epub')+'Dialog')
        dialog=cls(root,deck_names=['Topics'])
        names=[str(Path(root)/('first.'+kind)),str(Path(root)/('second.'+kind))]
        for path in names:
            Path(path).touch()
            dialog._add_paths([path])
        dialog._table.setCurrentCell(0,1)
        editor=dialog._book_details
        editor._reason.setPlainText('Recommended by ChatGPT')
        editor._source.setText('Conversation about biology')
        list_id=library.create_document_list(root,'Captured','Biology')
        editor.reload_lists()
        def choose_lists():
            picker=app.activeModalWidget()
            picker._lists.item(0).setCheckState(Qt.CheckState.Checked)
            picker.accept()
        QTimer.singleShot(0,choose_lists)
        editor._edit_lists.click()
        dialog._table.setCurrentCell(1,1)
        assert editor._reason.toPlainText()==''
        editor._reason.setPlainText('Found on a favourite blog')
        editor._source.setText('A blog')
        dialog._start_add()
        for _ in range(10):app.processEvents()
        assert len(calls)==2
        assert [args[2] for args,kwargs in calls]==names
        assert [kwargs['profile'] for args,kwargs in calls]==['Captured','Captured']
        assert calls[0][1]['document_details']=={'reason':'Recommended by ChatGPT',
            'source':'Conversation about biology','list_ids':[list_id]}
        assert calls[1][1]['document_details']=={'reason':'Found on a favourite blog',
            'source':'A blog','list_ids':[]}
        dialog.close()
    ''')
    result=subprocess.run([sys.executable,"-c",script,str(tmp_path),kind],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ,"QT_QPA_PLATFORM":"offscreen"},capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,result.stdout+result.stderr
