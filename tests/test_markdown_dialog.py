"""Real Qt import UI with fake task/collection boundaries and stale callbacks."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_markdown_dialog_imports_in_background_and_discards_closed_or_stale_results(tmp_path):
    script = dedent(r"""
        import sys
        from pathlib import Path
        from concurrent.futures import Future
        from types import SimpleNamespace
        from aqt.qt import QApplication
        import aqt
        import aqt.operations
        from backend import paths, epub_manager, priority_manager
        from backend.i18n import initialize_language
        from frontend.markdown_document_dialog import AddMarkdownDocumentDialog

        app = QApplication([])
        source = Path(sys.argv[1]) / 'lesson.md'
        source.write_text('# Lesson\n\nText', encoding='utf-8')
        jobs, operations, imports, priorities = [], [], [], []
        class Taskman:
            def run_in_background(self, task, callback, *, uses_collection):
                assert uses_collection is False
                jobs.append((task, callback))
        class Collection:
            def add_custom_undo_entry(self, label):
                return 17
            def merge_undo_entries(self, step):
                assert step == 17
                return SimpleNamespace(card=True)
        class Operation:
            def __init__(self, parent, op):
                self.op = op
            def success(self, callback):
                self.on_success = callback
                return self
            def failure(self, callback):
                self.on_failure = callback
                return self
            def run_in_background(self):
                operations.append(self)
        col = Collection()
        aqt.mw = SimpleNamespace(col=col, taskman=Taskman())
        # The dialog captures the owning main window when instantiated.
        import frontend.markdown_document_dialog as module
        module.mw = aqt.mw
        aqt.operations.CollectionOp = Operation
        epub_manager.add_epub_card = lambda *args, **kwargs: imports.append((args, kwargs)) or 41
        module.set_priority = lambda *args: priorities.append(args)
        paths.set_active_profile('Captured')
        initialize_language('en')
        def dialog():
            d = AddMarkdownDocumentDialog(str(source.parent), ['Topics', 'Other'])
            d._set_path(str(source))
            return d
        d = dialog()
        assert d._title_edit.text() == 'lesson'
        d._filename_title_cb.setChecked(False)  # Explicit custom-title mode.
        d._title_edit.setText('Custom title')
        d._priority_spin.setValue(23.5)
        d._start_import()
        d._start_import()  # Double-click cannot launch a second import.
        assert len(jobs) == 1 and not operations and not imports
        task, done = jobs.pop()
        future = Future()
        prepared = task()
        temporary = Path(prepared.path).parent
        future.set_result(prepared)
        done(future)
        assert len(operations) == 1 and not imports
        operation = operations.pop()
        result = operation.op(col)
        operation.on_success(result)
        assert d.created == [(str(source), 'Custom title')]
        assert imports[0][1]['profile'] == 'Captured'
        assert imports[0][1]['source_type'] == 'Markdown'
        assert priorities == [(str(source.parent), 'Captured', 41, 23.5)]
        assert not temporary.exists()

        for invalidate in ('close', 'profile'):
            paths.set_active_profile('Captured')
            d = dialog()
            d._start_import()
            task, done = jobs.pop()
            prepared = task()
            temporary = Path(prepared.path).parent
            if invalidate == 'close':
                d.reject()
            else:
                paths.set_active_profile('Other')
            future = Future()
            future.set_result(prepared)
            done(future)
            assert not operations and not temporary.exists() and not d.created
        paths.set_active_profile('Captured')
        d = dialog()
        d._start_import()
        task, done = jobs.pop()
        prepared = task()
        future = Future()
        future.set_result(prepared)
        done(future)
        operation = operations.pop()
        paths.set_active_profile('Other')
        try:
            operation.op(col)
        except RuntimeError as exc:
            operation.on_failure(exc)
        else:
            raise AssertionError('Stale operation modified collection')
        assert len(imports) == 1 and not Path(prepared.path).exists()

        paths.set_active_profile('Captured')
        second = source.parent / 'second.md'
        second.write_text('# Second\n\nStudy', encoding='utf-8')
        d = dialog()
        d._add_paths([str(second)])
        d._tag_edit.setTags(['shared'])
        d._table.cellWidget(0, 2).setTags(['first'])
        d._table.cellWidget(1, 2).setTags(['second'])
        d._start_import()
        d._tag_edit.setTags(['later'])  # Snapshot must not change while work is queued.
        for _ in range(2):
            task, done = jobs.pop()
            prepared = task()
            future = Future()
            future.set_result(prepared)
            done(future)
            operation = operations.pop()
            operation.on_success(operation.op(col))
            assert not Path(prepared.path).exists()
        assert d.created == [(str(source), 'lesson'), (str(second), 'second')]
        assert imports[1][1]['tags'] == ['shared', 'first']
        assert imports[2][1]['tags'] == ['shared', 'second']
        assert not jobs and not operations

        d = dialog()
        d._add_paths([str(second)])
        d._start_import()
        task, done = jobs.pop()
        future = Future()
        future.set_result(task())
        done(future)
        operation = operations.pop()
        operation.on_success(operation.op(col))
        assert d.created == [(str(source), 'lesson')] and len(jobs) == 1
        d.reject()  # Cancel during second conversion keeps only the first import.
        task, done = jobs.pop()
        prepared = task()
        future = Future()
        future.set_result(prepared)
        done(future)
        assert not operations and not Path(prepared.path).exists() and len(imports) == 4
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_markdown_batch_import_has_split_preview_filter_and_per_file_options(tmp_path):
    script = dedent(r"""
        from pathlib import Path
        from types import SimpleNamespace
        import sys, aqt
        from aqt.qt import QApplication, QSplitter, Qt
        from backend.i18n import initialize_language, t
        from frontend import markdown_document_dialog as module
        app = QApplication([])
        initialize_language('en')
        module.mw = SimpleNamespace(col=SimpleNamespace(tags=SimpleNamespace(all=lambda: [])))
        d = module.AddMarkdownDocumentDialog(sys.argv[1], ['Topics'])
        paths = [str(Path(sys.argv[1]) / name) for name in ('alpha.md', 'beta.markdown')]
        d._add_paths(paths + [paths[0], str(Path(sys.argv[1]) / 'not.txt')])
        assert d._table.rowCount() == 2
        assert d.findChild(QSplitter).count() == 2
        assert d._table.columnCount() == 4
        assert d._filename_title_cb.isChecked() and not d._title_edit.isEnabled()
        d._filter_edit.setText('BETA')
        assert d._table.isRowHidden(0) and not d._table.isRowHidden(1)
        d._select_all(False)
        assert d._table.item(0, 0).checkState() == Qt.CheckState.Checked
        assert d._table.item(1, 0).checkState() == Qt.CheckState.Unchecked
        d._filter_edit.clear()
        d._table.cellWidget(0, 2).setTags(['first'])
        d._table.cellWidget(0, 3).setValue(12.5)
        d._tag_edit.setTags(['shared'])
        assert d._import_requests() == [(paths[0], 'alpha', ['shared', 'first'], 12.5)]
        assert d._preview.toPlainText() == t('imports_preview_select_file')
        assert t('imports_add_markdown') == 'Add Markdown Writing'
        assert t('root_menu_add_markdown') == 'Add Markdown Writing…'
        d.reject()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_markdown_document_dialog_translations_fit_real_qt():
    script = dedent("""
        from types import SimpleNamespace
        import aqt
        from aqt.qt import QApplication, QFont, QLabel
        from backend.i18n import initialize_language
        from backend import paths
        from concurrent.futures import Future
        app = QApplication([])
        class Taskman:
            def run_in_background(self, task, callback, *, uses_collection):
                future = Future()
                future.set_result(SimpleNamespace(text='# Sample', revision='synthetic'))
                callback(future)
        aqt.mw = SimpleNamespace(col=SimpleNamespace(tags=SimpleNamespace(all=lambda: [])), taskman=Taskman())
        from frontend.markdown_document_dialog import AddMarkdownDocumentDialog
        from frontend.markdown_edit_dialog import EditMarkdownDocumentDialog
        for locale in ('en', 'hr', 'zh-Hans'):
            initialize_language(locale)
            for font_size in (13, 18):
                app.setFont(QFont('Arial', font_size))
                dialog = AddMarkdownDocumentDialog('.', ['Topics'])
                dialog.show()
                for _ in range(3):
                    app.processEvents()
                for label in dialog.findChildren(QLabel):
                    assert 'Translation unavailable' not in label.text()
                    if label.isVisible() and label.wordWrap():
                        assert label.height() >= label.heightForWidth(label.width()), (locale, font_size, label.text(), label.width(), label.height(), label.heightForWidth(label.width()))
                dialog.close()
                app.processEvents()
                editor = EditMarkdownDocumentDialog('.', paths.get_active_profile(), 41, 'synthetic.epub', 'Sample',
                    is_current=lambda: True, on_saved=lambda: None)
                editor.show()
                app.processEvents()
                for label in editor.findChildren(QLabel):
                    assert 'Translation unavailable' not in label.text()
                    if label.isVisible() and label.wordWrap():
                        assert label.height() >= label.heightForWidth(label.width()), (locale, font_size, label.text())
                assert editor._editor.font().pointSize() == font_size
                editor.close()
                app.processEvents()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_markdown_document_menu_and_palette_use_the_registered_action():
    root = Path(__file__).resolve().parents[1]
    source = (root / "__init__.py").read_text(encoding="utf-8")
    assert 'QAction(_t("root_menu_add_markdown_document")' in source
    assert "qconnect(_addMarkdownDocumentAction.triggered, addMarkdownDocumentFunction)" in source
    assert "_addContentMenu.addAction(_addMarkdownDocumentAction)" in source
    assert '_register_shortcut_action("add_markdown_document", _addMarkdownDocumentAction)' in source
    assert 'qconnect(_editMarkdownDocumentAction.triggered, _epub_dock_mod.edit_current_markdown_document)' in source
    assert '_register_shortcut_action("edit_markdown_document", _editMarkdownDocumentAction)' in source
    import_body = source.split("def addMarkdownDocumentFunction()", 1)[1].split(
        "def importNotebookCitationsFunction()", 1
    )[0]
    assert 'textFormat="plain"' in import_body


def test_current_markdown_editor_loads_and_saves_in_background_with_stale_guards():
    script = dedent(r"""
        from concurrent.futures import Future
        from types import SimpleNamespace
        import aqt
        from aqt.qt import QApplication
        from backend import paths
        from backend.i18n import initialize_language
        from frontend import markdown_edit_dialog as module
        app = QApplication([])
        initialize_language('en')
        jobs, saves, refreshed = [], [], []
        class Taskman:
            def run_in_background(self, task, callback, *, uses_collection):
                assert not uses_collection
                jobs.append((task, callback))
        col = object()
        module.mw = SimpleNamespace(col=col, taskman=Taskman())
        paths.set_active_profile('Captured')
        module.markdown_manager.load_markdown_document = lambda *args: SimpleNamespace(text='# Old', revision='revision')
        module.markdown_manager.save_markdown_document = lambda *args, **kwargs: saves.append((args, kwargs)) or {}
        current = [True]
        def dialog():
            return module.EditMarkdownDocumentDialog('.', 'Captured', 41, 'managed.epub', 'Lesson',
                is_current=lambda: current[0], on_saved=lambda: refreshed.append(True))
        def complete():
            task, done = jobs.pop(0)
            f = Future()
            f.set_result(task())
            done(f)
        d = dialog()
        assert not d._save_btn.isEnabled()
        complete()
        assert d._editor.toPlainText() == '# Old'
        d._editor.setPlainText('# Changed')
        d._save()
        d._save()
        assert len(jobs) == 1
        complete()
        assert saves[0][0] == ('.', 'Captured', 41, 'managed.epub', '# Changed')
        assert saves[0][1]['expected_revision'] == 'revision' and refreshed == [True]
        for stale in ('close', 'profile', 'card'):
            paths.set_active_profile('Captured')
            current[0] = True
            d = dialog()
            if stale == 'close':
                d.reject()
            elif stale == 'profile':
                paths.set_active_profile('Other')
            else:
                current[0] = False
            complete()
            assert not d._save_btn.isEnabled()
        paths.set_active_profile('Captured')
        current[0] = True
        d = dialog()
        complete()
        d._editor.setPlainText('# Not saved')
        d._save()
        current[0] = False  # Save queued behind another worker: do not write stale card.
        task, done = jobs.pop(0)
        try:
            task()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Stale editor saved')
        assert len(saves) == 1
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
