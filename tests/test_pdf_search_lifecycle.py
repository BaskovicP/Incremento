"""Missing files are hidden; only confirmed Anki deletions purge derived text."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_missing_pdf_filter_and_real_delete_undo_redo_preserve_user_work(tmp_path):
    script = dedent(r'''
        import importlib, sys
        from pathlib import Path
        from types import ModuleType, SimpleNamespace
        from concurrent.futures import CancelledError
        from anki.collection import Collection
        from anki import hooks
        package=ModuleType('pdfsearch_addon'); package.__path__=[str(Path.cwd())]
        sys.modules[package.__name__]=package
        results=importlib.import_module('pdfsearch_addon.frontend.search_all_results')
        db=importlib.import_module('pdfsearch_addon.backend.db')
        paths=importlib.import_module('pdfsearch_addon.backend.paths')
        root=Path(sys.argv[1]); addon=str(root/'addon'); profile='PDFSearch'
        col=Collection(str(root/'collection.anki2'))
        events=importlib.import_module('pdfsearch_addon.frontend.pdf_search_lifecycle')
        jobs=[];main=[]
        class QueryOp:
            def __init__(self,*,parent,op,success):self.op,self.success=op,success
            def failure(self,callback):self.failed=callback;return self
            def run_in_background(self):jobs.append(self)
        events.QueryOp=QueryOp
        tracker=events.PdfSearchLifecycle(addon,profile,col,parent=None,
                    taskman=SimpleNamespace(run_on_main=main.append),valid=lambda:True)
        hooks.notes_will_be_deleted.append(tracker.notes_will_be_deleted)
        def settle(changes):
            tracker.collection_changed(changes)
            while main:main.pop(0)()
            while jobs:
                job=jobs.pop(0)
                try:job.success(job.op(col))
                except CancelledError:job.failed(CancelledError())
        try:
            model=col.models.by_name('Basic')
            col.models.add_field(model,col.models.new_field('PDF_Filename')); col.models.save(model)
            pdf=col.new_note(model);pdf.fields=['needle book','PDF body','book.pdf'];col.add_note(pdf,1)
            cid=col.card_ids_of_note(pdf.id)[0]
            child=col.new_note(col.models.by_name('Basic (and reversed card)'))
            child.fields=['needle extracted card','My answer'];col.add_note(child,1)
            folder=paths.get_pdf_dir(addon,profile);folder.mkdir(parents=True)
            file=folder/'book.pdf';file.write_bytes(b'%PDF-fixture')
            db.replace_pdf_text_index(addon,profile,cid,['needle page text'])
            conn=db.get_connection(addon,profile)
            conn.execute('INSERT INTO pdf_highlights(id,card_id,page,text,note) VALUES (?,?,?,?,?)',
                         ('saved',cid,1,'needle highlight','needle annotation'))
            conn.execute('INSERT INTO pdf_card_sources(pdf_card_id,page,note_id,excerpt) VALUES (?,?,?,?)',
                         (cid,1,child.id,'needle excerpt'))
            conn.commit()
            preserved={table:[tuple(row) for row in conn.execute('SELECT * FROM '+table)]
                       for table in ('pdf_highlights','pdf_card_sources')}
            filters=frozenset(('pdf_content','pdf_highlights','annotations','pdf_sources','cards'))
            def search():return results.run_search(addon,profile,col,'needle',filters)
            assert 'inc://pdf/' in search().html
            file.rename(folder/'moved.pdf')
            hidden=search()
            assert 'inc://pdf/' not in hidden.html, 'Missing PDF still offered as an openable result'
            assert f'inc://card/{pdf.id}' not in hidden.html, 'Missing PDF leaked through Cards'
            assert f'inc://card/{child.id}' in hidden.html
            assert db.search_pdf_text_index(addon,profile,'needle'), 'Missing file is not confirmed deletion'
            (folder/'moved.pdf').rename(file)
            assert 'inc://pdf/' in search().html
            lifecycle=importlib.import_module('pdfsearch_addon.backend.pdf_search')
            indexer=importlib.import_module('pdfsearch_addon.backend.search_indexer')
            old_job=lifecycle.prepare_pdf_index_documents(addon,profile,col,[cid])
            deletion=col.remove_notes([pdf.id])
            assert db.search_pdf_text_index(addon,profile,'needle'), 'Before-delete hook must not purge'
            settle(deletion.changes)
            assert db.search_pdf_text_index(addon,profile,'needle')==[]
            assert conn.execute("SELECT status FROM document_index_state WHERE kind='pdf' AND card_id=?",(cid,)).fetchone()[0]=='deleted'
            # An already queued index job cannot resurrect text after deletion.
            indexer.index_pdf_documents(addon,profile,old_job,extractor=lambda *a,**kw:['obsolete needle'])
            assert db.search_pdf_text_index(addon,profile,'needle')==[]
            assert 'inc://pdf/' not in search().html
            assert col.get_note(child.id).fields==['needle extracted card','My answer']
            settle(col.undo().changes)
            rebuild=results.run_search(addon,profile,col,'needle',filters,
                                       check_pdf_cache=True).pdf_reindex_documents
            assert len(rebuild)==1 and file.exists()
            indexer.index_pdf_documents(addon,profile,rebuild,extractor=lambda *a,**kw:['needle page text'])
            assert db.search_pdf_text_index(addon,profile,'needle')[0][2]=='needle page text'
            assert 'inc://pdf/' in search().html
            assert col.undo_status().redo, 'Cache maintenance must not consume Anki Redo'
            settle(col.redo().changes)
            assert db.search_pdf_text_index(addon,profile,'needle')==[]
            for table,rows in preserved.items():
                assert [tuple(row) for row in conn.execute('SELECT * FROM '+table)]==rows
            assert file.exists() and col.get_note(child.id).id==child.id
            print('PDF lifecycle: ok')
        finally:
            hooks.notes_will_be_deleted.remove(tracker.notes_will_be_deleted)
            tracker.close();col.close();db.close_connection()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
