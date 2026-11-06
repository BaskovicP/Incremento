"""Real Qt capture UI: preview first, serialized save, stale work discarded."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_webpage_document_preview_save_and_stale_capture_lifecycle(tmp_path):
    script = dedent(r'''
        from concurrent.futures import Future
        from types import SimpleNamespace
        from pathlib import Path
        import sys
        import aqt
        import aqt.operations
        from aqt.qt import QApplication
        from backend import paths, webpage_document
        from backend.i18n import initialize_language
        from frontend import webpage_document_dialog as module

        app = QApplication([])
        initialize_language('en')
        paths.set_active_profile('Captured')
        jobs, queued, saved = [], [], []
        class Taskman:
            def run_in_background(self, task, done, *, uses_collection):
                assert uses_collection is False
                jobs.append((task, done))
        class Collection:
            def add_custom_undo_entry(self, label): return 7
            def merge_undo_entries(self, step): return SimpleNamespace(card=True)
        class Operation:
            def __init__(self, parent, operation): self.operation = operation
            def success(self, callback): self.done = callback; return self
            def failure(self, callback): self.failed = callback; return self
            def run_in_background(self): queued.append(self)
        col = Collection()
        module.mw = SimpleNamespace(col=col, taskman=Taskman())
        aqt.operations.CollectionOp = Operation
        module.epub_manager.add_epub_card = lambda *args, **kwargs: saved.append((args, kwargs)) or 41
        module.set_priority = lambda *args: None
        html = '<article><h1>Snapshot</h1><p>Frozen text for reading.</p></article>'
        module.prepare_webpage_document = lambda url, **kwargs: webpage_document.prepare_webpage_document(url, html=html, title=kwargs['title'])

        def dialog():
            d = module.WebpageDocumentDialog(sys.argv[1], ['Topics', 'Other'])
            assert d._format.currentData() == 'html'
            d._format.setCurrentIndex(d._format.findData('markdown'))
            d._url_edit.setText('https://example.com/article')
            return d
        def complete():
            task, done = jobs.pop(0)
            value = task()
            f = Future(); f.set_result(value); done(f)
            return value
        d = dialog()
        assert not d._save_btn.isEnabled()
        d._capture(); d._capture()
        assert len(jobs) == 1 and not queued
        prepared = complete()
        assert 'Frozen text' in d._preview.toPlainText()
        assert d._save_btn.isEnabled() and not saved
        d._save(); d._save()
        assert len(queued) == 1
        op = queued.pop(); result = op.operation(col); op.done(result)
        assert saved[0][1]['profile'] == 'Captured'
        assert saved[0][1]['source_type'] == 'Markdown'
        assert not Path(prepared.path).exists()
        assert d.created_card_id == 41

        for invalidate in ('close', 'profile', 'url'):
            paths.set_active_profile('Captured')
            d = dialog(); d._capture()
            task, done = jobs.pop(0); prepared = task()
            if invalidate == 'close': d.reject()
            elif invalidate == 'profile': paths.set_active_profile('Other')
            else: d._invalidate()
            f = Future(); f.set_result(prepared); done(f)
            assert not Path(prepared.path).exists()
            assert not queued and not d._save_btn.isEnabled()
        print('offline capture UI: ok')
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "offline capture UI: ok" in result.stdout


def test_document_export_is_atomic_and_drops_stale_profile_work(tmp_path):
    script = dedent(r'''
        from concurrent.futures import Future
        from types import SimpleNamespace
        from pathlib import Path
        import sys
        from aqt.qt import QApplication
        from backend import paths
        from backend.i18n import initialize_language
        from frontend import markdown_export as module
        app = QApplication([])
        initialize_language('en')
        jobs, messages = [], []
        class Taskman:
            def run_in_background(self, task, done, *, uses_collection):
                assert uses_collection is False
                jobs.append((task, done))
        module.mw = SimpleNamespace(col=object(), taskman=Taskman())
        module.tooltip = messages.append
        module.showInfo = lambda text, **kwargs: messages.append(text)
        module.markdown_manager.export_markdown_document = lambda *args, **kwargs: b'Offline source'
        root = Path(sys.argv[1])
        for format, key in [('html', 'imports_export_html_filter'), ('md', 'imports_export_markdown_filter'), ('txt', 'imports_export_text_filter')]:
            paths.set_active_profile('Captured')
            target = root / ('saved.' + format)
            target.write_bytes(b'Previous file')
            module.QFileDialog.getSaveFileName = lambda *args: (str(target), module.t(key))
            module.export_document(str(root), 'Captured', 'article.epub', 'Article')
            assert target.read_bytes() == b'Previous file'
            task, done = jobs.pop(); future = Future(); future.set_result(task()); done(future)
            assert target.read_bytes() == b'Offline source'
            assert not list(root.glob('.incremento-export-*'))
        target = root / 'stale.html'
        module.QFileDialog.getSaveFileName = lambda *args: (str(target), module.t('imports_export_html_filter'))
        module.export_document(str(root), 'Captured', 'article.epub', 'Article')
        task, done = jobs.pop()
        paths.set_active_profile('Other')
        try: task()
        except RuntimeError: pass
        else: raise AssertionError('Export continued in a different profile')
        assert not target.exists()
        paths.set_active_profile('Captured')
        protected = root / 'protected.html'; protected.write_bytes(b'Keep this')
        target.symlink_to(protected)
        module.export_document(str(root), 'Captured', 'article.epub', 'Article')
        task, done = jobs.pop()
        try: task()
        except ValueError: pass
        else: raise AssertionError('Export followed a symlink')
        assert protected.read_bytes() == b'Keep this'
        print('offline export UI: ok')
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "offline export UI: ok" in result.stdout


def test_snapshot_choice_loads_html_preview_and_saves_html_provenance(tmp_path):
    script = dedent(r'''
        from concurrent.futures import Future
        from pathlib import Path
        from types import SimpleNamespace
        import sys
        import aqt.operations
        from aqt.qt import QApplication, QTextBrowser, pyqtSignal
        from backend import paths, webpage_document
        from backend.i18n import initialize_language
        from frontend import webpage_document_dialog as module
        app = QApplication(['snapshot-dialog-test'])
        initialize_language('en'); paths.set_active_profile('Captured')
        jobs, operations, imports, imported_text = [], [], [], []
        class Preview(QTextBrowser):
            loadFinished = pyqtSignal(bool)
            is_ready = False
            def load_snapshot(self, path):
                self.loaded_path = path
                self.setPlainText(Path(path).read_text())
                self.is_ready = True
                self.loadFinished.emit(True)
            def snapshot_html(self, callback):
                from bs4 import BeautifulSoup
                edited = BeautifulSoup(self.toPlainText(), 'html.parser')
                edited.aside.decompose()
                callback(str(edited))
            def set_editable(self, enabled): self.editable = enabled
            def clear(self):
                self.is_ready = False
                super().clear()
        # The real script-disabled WebEngine page is covered separately.
        sys.modules['frontend.webpage_snapshot_preview'] = SimpleNamespace(SnapshotPreview=Preview)
        class Taskman:
            def run_in_background(self, task, done, *, uses_collection):
                assert not uses_collection
                jobs.append((task, done))
        class Collection:
            def add_custom_undo_entry(self, label): return 7
            def merge_undo_entries(self, step): return SimpleNamespace(card=True)
        class Operation:
            def __init__(self, parent, op): self.operation = op
            def success(self, callback): self.done = callback; return self
            def failure(self, callback): self.failed = callback; return self
            def run_in_background(self): operations.append(self)
        col = Collection(); module.mw = SimpleNamespace(col=col, taskman=Taskman())
        aqt.operations.CollectionOp = Operation
        def add(*args, **kwargs):
            import zipfile
            with zipfile.ZipFile(args[2]) as archive:
                imported_text.append((archive.read('snapshot.html').decode(),archive.read('source.md').decode()))
            imports.append(kwargs)
            return 42
        module.epub_manager.add_epub_card = add
        module.set_priority = lambda *args: None
        original_prepare = webpage_document.prepare_webpage_document
        module.prepare_webpage_document = lambda url, **kwargs: original_prepare(url,
            html='<html><head><style>.layout{display:grid}</style></head><body><aside>Unwanted sidebar</aside><main class="layout">Website appearance</main></body></html>', **kwargs)
        d = module.WebpageDocumentDialog(sys.argv[1], ['Topics'])
        assert d._format.currentData() == 'html' and d._scope.currentData() == 'full'
        assert not d._scope.isEnabled()
        d._url_edit.setText('https://example.com/article'); d._capture()
        task, done = jobs.pop(); prepared = task(); f = Future(); f.set_result(prepared); done(f)
        assert d._preview_stack.currentWidget() is d._snapshot_preview
        assert '.layout{display:grid}' in d._snapshot_preview.toPlainText()
        assert d._save_btn.isEnabled()
        captured_at = prepared.capture['captured_at']
        d._save(); d._save()
        assert len(jobs) == 1 and not operations
        task, done = jobs.pop(); revised = task(); f = Future(); f.set_result(revised); done(f)
        assert not Path(prepared.path).exists()
        op = operations.pop()
        op.failed(RuntimeError('Collection temporarily unavailable'))
        assert d._prepared is revised and Path(revised.path).exists() and d._save_btn.isEnabled()
        # Retrying must keep the existing edited archive and original capture time.
        d._save(); task, done = jobs.pop(); final = task(); f = Future(); f.set_result(final); done(f)
        assert not Path(revised.path).exists()
        op = operations.pop(); op.done(op.operation(col))
        assert imports[0]['source_type'] == 'HTML'
        assert imports[0]['source_metadata']['Incremento_Source_Type'] == 'HTML'
        assert imports[0]['source_metadata']['Incremento_Imported_At'] == captured_at
        assert all('Unwanted sidebar' not in text and 'Website appearance' in text for text in imported_text[0])
        assert not d._snapshot_preview.editable
        assert not Path(prepared.path).exists() and not Path(prepared.preview_path).exists()
        d._format.setCurrentIndex(d._format.findData('markdown'))
        assert d._scope.isEnabled() and d._scope.currentData() == 'main'
        d.reject()
        for phase in ('serialization', 'preparation'):
            paths.set_active_profile('Captured')
            d = module.WebpageDocumentDialog(sys.argv[1], ['Topics'])
            d._url_edit.setText('https://example.com/article'); d._capture()
            task, done = jobs.pop(); original = task(); f = Future(); f.set_result(original); done(f)
            if phase == 'serialization':
                callbacks = []
                d._snapshot_preview.snapshot_html = callbacks.append
            d._save()
            if phase == 'preparation':
                task, done = jobs.pop(); stale = task()
            paths.set_active_profile('Other')
            if phase == 'serialization':
                callbacks.pop()(d._snapshot_preview.toPlainText())
                assert not jobs
            else:
                f = Future(); f.set_result(stale); done(f)
                assert not Path(stale.path).exists()
            assert not operations and len(imports) == 1
            assert not Path(original.path).exists()
            d.reject()
        print('HTML snapshot dialog: ok')
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HTML snapshot dialog: ok" in result.stdout


def test_snapshot_reader_scale_preserves_site_typography_and_uses_page_zoom():
    from types import SimpleNamespace
    previous = sys.modules.get('session')
    sys.modules['session'] = SimpleNamespace(INCREMENTO_EPUB_REVIEW_DECK='Test', start_explicit_review=lambda *a, **k: None)
    try:
        import epub_dock
    finally:
        if previous is None:
            sys.modules.pop('session', None)
        else:
            sys.modules['session'] = previous
    script = epub_dock._build_page_script(card_id=42, section_index=0, scroll_ratio=0,
        text_scale=1, read_anchor=None, focus_offset=-1, search_query='', highlights=[],
        bridge_nonce='test', sections=[{'text':'Snapshot'}], preserve_layout=True)
    start = script.index('      function applyTextScale(')
    end = script.index('      window.incrementoSetEpubTextScale', start)
    result = subprocess.run(['node', '-e', '''
        const assert = require('node:assert/strict');
        const changed = [], props = [];
        const root = {classList:{add:value=>changed.push(value),remove:()=>{}},style:{setProperty:(...args)=>props.push(args)}};
        const document = {documentElement:root};
        const window = {getComputedStyle:()=>({zoom:'1'})};
        const STATE = {preserveLayout:true};
    ''' + script[start:end] + '''
        applyTextScale(1);
        assert.deepEqual(changed,[]);
        assert.deepEqual(props,[]);
        applyTextScale(1.2);
        assert.equal(root.style.zoom,'1.2');
        STATE.preserveLayout=false;
        applyTextScale(1);
        assert.deepEqual(changed,['incremento-epub-scaled']);
        assert.deepEqual(props,[['--incremento-epub-font-size','100%']]);
    '''],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0,result.stdout+result.stderr
