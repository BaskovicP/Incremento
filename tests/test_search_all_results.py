"""Search reads are bounded, cancellable, profile-scoped and independent of Qt."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_background_search_preserves_categories_live_filter_ranking_and_progress(tmp_path):
    script = dedent(r'''
        import sys
        from pathlib import Path
        from threading import Event
        from types import SimpleNamespace, ModuleType
        from concurrent.futures import CancelledError
        import importlib
        from anki.collection import Collection, AddNoteRequest
        package = ModuleType('query_addon'); package.__path__ = [str(Path.cwd())]
        sys.modules['query_addon'] = package
        results = importlib.import_module('query_addon.frontend.search_all_results')
        db = importlib.import_module('query_addon.backend.db')
        root = Path(sys.argv[1]); addon = str(root/'addon'); profile = 'SearchTest'
        col = Collection(str(root/'collection.anki2'))
        try:
            model = col.models.by_name('Basic')
            pdf_model=col.models.copy(model)
            col.models.add_field(pdf_model,col.models.new_field('PDF_Filename'))
            col.models.save(pdf_model)
            paths=importlib.import_module('query_addon.backend.paths')
            pdf_dir=paths.get_pdf_dir(addon,profile);pdf_dir.mkdir(parents=True)
            (pdf_dir/'book.pdf').write_bytes(b'%PDF-fixture')
            notes=[]
            for i in range(1005):
                note=col.new_note(pdf_model if i==0 else model)
                note.fields=[f'Faith document {i}', 'Answer <unsafe> & text'] + (['book.pdf'] if i==0 else [])
                notes.append(note)
            col.add_notes([AddNoteRequest(n,1) for n in notes])
            pairs = col.db.all('SELECT id,nid FROM cards ORDER BY id')
            cid,nid=pairs[0]; other=pairs[1][0]
            conn=db.get_connection(addon,profile)
            conn.executemany('INSERT INTO pdf_highlights(id,card_id,page,text,note) VALUES (?,?,?,?,?)',
                [(str(i),99,i,'faith','faith annotation') for i in range(120)] +
                [(f'live-{i}',cid,121+i,'faith','faith annotation') for i in range(121)])
            conn.execute('INSERT INTO epub_highlights(id,card_id,section_index,text) VALUES (?,?,?,?)',
                ('epub',other,0,'faith & saved text'))
            conn.executemany('INSERT INTO pdf_card_sources(pdf_card_id,page,note_id,excerpt) VALUES (?,?,?,?)',
                [(cid,3,nid,'faith source'),(cid,4,99,'faith deleted source')])
            conn.commit()
            db.replace_pdf_text_index(addon,profile,cid,['faith indexed PDF text'])
            db.replace_epub_text_index(addon,profile,other,[('Beginning','faith indexed EPUB text')])
            db.replace_note_ocr_index(addon,profile,nid,[cid],[('figure.png','faith OCR text')])
            calls=[]
            class BatchDb:
                def all(self, sql, *args):
                    assert len(args)<=900
                    calls.append((sql,len(args))); return col.db.all(sql,*args)
            # Worker needs no Note/Card object retrieval and no global mw.
            operation_col=SimpleNamespace(db=BatchDb(),models=col.models,find_notes=col.find_notes)
            filters=frozenset(['pdf_highlights','epub_highlights','annotations','pdf_sources',
                               'epub_sources','pdf_content','epub_content','image_ocr','cards','current_profile'])
            partial=[]
            result=results.run_search(addon,profile,operation_col,'faith',filters,progress=partial.append)
            assert result.html.count('<li>') == 120+120+1+1+1+1+1+160
            assert 'Page 121' in result.html and 'Page 241' not in result.html
            assert 'faith deleted source' not in result.html
            assert 'Section 1' in result.html
            assert len(result.highlight_previews)==241
            assert result.pdf_needs_index is False
            assert partial and len(partial[0].html)<len(result.html)
            assert len(partial[0].highlight_previews)<len(result.highlight_previews)
            assert len([c for c in calls if 'FROM notes' in c[0]]) <= 6
            assert any(c[1]==900 for c in calls), '1,000 candidate notes must be batched'
            # Disabled filters cannot leak their results; annotations remain independent.
            only=results.run_search(addon,profile,operation_col,'faith',frozenset(['annotations','current_profile']))
            assert only.html.count('<li>')==120
            assert 'Annotations (PDF)' in only.html and 'PDF Highlights' not in only.html
            foreign=results.run_search(addon,'Other',operation_col,'faith',frozenset(['pdf_highlights']))
            assert '<li>' not in foreign.html
            empty=results.run_search(addon,profile,operation_col,'absent',frozenset(['pdf_content']))
            assert empty.pdf_needs_index is True
            # Cancel after a partial category: later sections must not run.
            cancel=Event(); partial_cancel=[]
            def cancelled_partial(value):
                partial_cancel.append(value); cancel.set()
            try:
                results.run_search(addon,profile,operation_col,'faith',filters,
                                   cancel=cancel,progress=cancelled_partial)
                raise AssertionError('Cancelled search returned final results')
            except CancelledError:
                pass
            assert len(partial_cancel)==1
            calls.clear()
            try:
                results.run_search(addon,profile,operation_col,'faith',filters,cancel=cancel)
                raise AssertionError('Pre-cancelled search ran')
            except CancelledError:
                pass
            assert calls==[]
            print('background search: ok')
        finally:
            col.close(); db.close_connection()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'background search: ok' in result.stdout
