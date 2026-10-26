"""Exercise Search ALL dispatch/lifecycle with real offscreen Qt widgets."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.mark.parametrize("media", ["pdf", "epub"])
def test_real_result_link_hover_marks_annotation_source_instead_of_showing_plain_page(tmp_path, media):
    script = dedent(r'''
        import importlib, sys
        from pathlib import Path
        from types import ModuleType, SimpleNamespace
        from anki.collection import Collection
        from aqt.qt import QApplication, QTextBrowser, QPoint, QUrl
        from PyQt6.QtTest import QTest
        app = QApplication(['annotation-link-test'])
        package = ModuleType('hover_addon'); package.__path__ = [str(Path.cwd())]
        sys.modules['hover_addon'] = package
        ui = importlib.import_module('hover_addon.frontend.search_all')
        data = importlib.import_module('hover_addon.frontend.search_all_results')
        db = importlib.import_module('hover_addon.backend.db')
        paths = importlib.import_module('hover_addon.backend.paths')
        class Preview(QTextBrowser):
            def setHtml(self, html):
                self.last_html = html
                super().setHtml(html)
        ui.QWebEngineView = Preview
        root, media = Path(sys.argv[1]), sys.argv[2]
        addon, profile = str(root / 'addon'), 'Synthetic'
        ui._active_profile = lambda: profile
        col = Collection(str(root / 'collection.anki2'))
        try:
            model = col.models.copy(col.models.by_name('Basic'))
            col.models.add_field(model, col.models.new_field('PDF_Filename'))
            col.models.save(model)
            note = col.new_note(model)
            note.fields = ['Synthetic document', 'Body', 'book.pdf']
            col.add_note(note, 1)
            cid = col.db.scalar('SELECT id FROM cards WHERE nid=?', note.id)
            pdf_dir = paths.get_pdf_dir(addon, profile)
            pdf_dir.mkdir(parents=True)
            (pdf_dir / 'book.pdf').write_bytes(b'%PDF-fixture')
            position = 13 if media == 'pdf' else 0
            position_column = 'page' if media == 'pdf' else 'section_index'
            source = 'The original source passage.'
            context = 'Context before.\n' + source + '\nContext after.'
            conn = db.get_connection(addon, profile)
            conn.execute(f'INSERT INTO {media}_highlights(id,card_id,{position_column},text,note,color) '
                         'VALUES (?,?,?,?,?,?)', ('highlight-1', cid, position, source, 'Why this matters', 'green'))
            conn.commit()
            if media == 'pdf':
                db.replace_pdf_text_index(addon, profile, cid, [''] * 12 + [context])
            else:
                db.replace_epub_text_index(addon, profile, cid, [('Chapter', context)])
            ui.mw = SimpleNamespace(col=col)
            dialog = ui._SearchAllDialog(addon_dir=addon, open_pdf_card=lambda *a, **k: None,
                                         open_epub_card=lambda *a, **k: None)
            result = data.run_search(addon, profile, col, 'why', frozenset(['annotations']))
            dialog._search_progress({}, result)
            dialog.resize(1200, 700)
            dialog.show()
            app.processEvents()
            urls = []
            dialog._results.highlighted[QUrl].connect(lambda url: urls.append(url.toString()))
            cursor = dialog._results.document().find('Page 13' if media == 'pdf' else 'Section 1')
            assert not cursor.isNull()
            cursor.setPosition(cursor.selectionStart())
            point = dialog._results.cursorRect(cursor).center() + QPoint(12, 0)
            QTest.mouseMove(dialog._results.viewport(), QPoint(1, 1))
            QTest.mouseMove(dialog._results.viewport(), point)
            app.processEvents()
            assert any(url.startswith('inc://') for url in urls), urls
            html = dialog._preview.last_html
            assert 'id="incremento-search-source"' in html, (
                'Qt hover lost the annotation reference and showed an unmarked page', urls,
                dialog._preview_header.text(), html)
            assert 'rgba(0,200,80,' in html
            assert 'Context before.' in html and 'Context after.' in html
            assert 'The original source passage.' in html
            assert 'Why' in html and 'this matters' in html
            dialog.accept()
        finally:
            col.close()
            db.close_connection()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path), media], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_search_all_only_applies_current_worker_results_and_preserves_index_handoff(tmp_path):
    script = dedent(r'''
        import importlib
        import sys
        from pathlib import Path
        from types import ModuleType, SimpleNamespace
        from concurrent.futures import ThreadPoolExecutor, CancelledError
        from anki.collection import Collection
        from aqt.qt import QApplication, QTextBrowser
        import aqt.operations
        app=QApplication(['search-test'])
        package=ModuleType('background_addon');package.__path__=[str(Path.cwd())]
        sys.modules['background_addon']=package
        ui=importlib.import_module('background_addon.frontend.search_all')
        data=importlib.import_module('background_addon.frontend.search_all_results')
        # The preview renderer is unrelated to query scheduling; no Chromium process needed.
        ui.QWebEngineView=QTextBrowser
        root=Path(sys.argv[1]);col=Collection(str(root/'collection.anki2'))
        jobs=[];main_callbacks=[]
        class QueryOp:
            def __init__(self,*,parent,op,success):self.op,self.success=op,success
            def failure(self,callback):self.failed=callback;return self
            def run_in_background(self):jobs.append(self)
        aqt.operations.QueryOp=QueryOp
        current=['SearchTest']
        ui._active_profile=lambda:current[0]
        ui._set_search_all_filter_enabled=lambda *args:None
        ui._set_search_all_search_while_typing=lambda *args:None
        ui.mw=SimpleNamespace(col=col,taskman=SimpleNamespace(run_on_main=main_callbacks.append))
        try:
            note=col.new_note(col.models.by_name('Basic'));note.fields=['faith first','body']
            col.add_note(note,1)
            dialog=ui._SearchAllDialog(addon_dir=str(root/'addon'),open_pdf_card=lambda *a,**k:None,
                                       open_epub_card=lambda *a,**k:None)
            for name,checkbox in dialog._filter_checkboxes.items():
                checkbox.setChecked(name=='cards')
            dialog._search.setText('faith');dialog._run_search()
            assert len(jobs)==1
            assert 'faith first' not in dialog._results.toPlainText()
            with ThreadPoolExecutor(max_workers=1) as pool:
                def compute(job):return pool.submit(job.op,col).result(timeout=10)
                old=jobs[0];old_result=compute(old)
                # Typing invalidates both queued partials and completion before debounce fires.
                dialog._search.setText('absent')
                for callback in main_callbacks:callback()
                main_callbacks.clear()
                old.success(old_result)
                assert 'faith first' not in dialog._results.toPlainText()
                dialog._run_search();job=jobs[-1];job.success(compute(job))
                assert 'No matches' in dialog._results.toPlainText()
                dialog._search.setText('faith');dialog._run_search()
                job=jobs[-1];job.success(compute(job))
                assert 'faith first' in dialog._results.toPlainText()
                # Filter changes take effect even with automatic typing searches disabled.
                dialog._cb_search_while_typing.setChecked(False)
                previous=len(jobs);dialog._cb_cards.setChecked(False)
                assert len(jobs)==previous+1
                job=jobs[-1];job.success(compute(job))
                assert 'faith first' not in dialog._results.toPlainText()
                # A PDF query requests indexing from its current UI callback, never from the worker.
                indexed=[];dialog._start_pdf_index=lambda documents=None:indexed.append(documents or 'index')
                dialog._cb_content.setChecked(True)
                job=jobs[-1];value=compute(job)
                assert indexed==[]
                job.success(value);assert indexed==['index']
                # Undo rebuilds must hand off even when another PDF already matches.
                dialog._run_search()
                restored=SimpleNamespace(card_id=42,path='restored.pdf',generation=1)
                jobs[-1].success(data.SearchResults('<p>Other match</p>',{},False,(restored,)))
                assert indexed.pop()==[restored]
                # Explicit cancellation stops a queued query before any collection reads.
                dialog._run_search();job=jobs[-1]
                dialog._cancel_search()
                try:compute(job);raise AssertionError('cancelled query ran')
                except CancelledError:pass
                job.failed(CancelledError())
                assert not dialog._search_cancel_btn.isVisible()
                # A previously started PDF index must not resurrect a cancelled query.
                file_jobs=[]
                ui.mw.taskman.run_in_background=lambda task,done,**kw:file_jobs.append(done)
                dialog._run_pdf_file_index([],profile='SearchTest',generation=0)
                before=len(jobs)
                file_jobs[-1](SimpleNamespace(result=lambda:SimpleNamespace(
                    cancelled=False,indexed=1,failed=0)))
                assert len(jobs)==before, 'PDF indexing restarted a cancelled search'
                # Current errors remain visible, and stale failures never replace newer text.
                dialog._run_search();job=jobs[-1];job.failed(RuntimeError('database unavailable'))
                assert 'database unavailable' in dialog._results.toPlainText()
                dialog._run_search();job=jobs[-1];dialog._search.setText('new text')
                job.failed(RuntimeError('obsolete'))
                assert 'obsolete' not in dialog._results.toPlainText()
                # Closed/profile-switched dialogs discard results and don't start indexing.
                dialog._run_search();job=jobs[-1];value=compute(job)
                current[0]='Other';job.success(value);assert indexed==['index']
                current[0]='SearchTest';dialog._run_search();job=jobs[-1];value=compute(job)
                dialog.accept();job.success(value)
                assert dialog._closed and indexed==['index']
                another=ui._SearchAllDialog(addon_dir=str(root/'addon'),
                    open_pdf_card=lambda *a,**k:None, open_epub_card=lambda *a,**k:None)
                observed=[];follower=lambda:observed.append('closed')
                another._hooks.profile_will_close.append(follower)
                another._hooks.profile_will_close()
                assert another._closed and observed==['closed']
                another._hooks.profile_will_close.remove(follower)
                app.processEvents()
            print('search UI: ok')
        finally:
            col.close()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'search UI: ok' in result.stdout
