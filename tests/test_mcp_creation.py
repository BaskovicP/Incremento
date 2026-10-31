"""Real Anki verifies durable, identity-preserving source creation and imports."""
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_source_card_creation_and_document_import_undo_after_restart(tmp_path):
    script = dedent('''
        import sys
        from pathlib import Path
        from zipfile import ZipFile
        from anki.collection import Collection
        from backend.mcp_service import McpService
        from backend import db
        from backend.pdf_manager import ensure_pdf_note_type
        root = Path(sys.argv[1])
        col = Collection(str(root/'collection.anki2'))
        def service():
            return McpService(str(root), 'A', 'context', config={}, alive=lambda: True)
        svc = service()
        def call(tool_name, **args):
            return svc.call(col, tool_name, {'context_id':'context', **args})
        try:
            ensure_pdf_note_type(col)
            note = col.new_note(col.models.by_name('Incremento PDF'))
            note['Title']='Original source';note['PDF_Filename']='source.pdf'
            col.add_note(note,col.decks.id('Default'))
            source_id = col.find_cards(f'nid:{note.id}')[0]
            folder=root/'user_files/A/pdfs';folder.mkdir(parents=True)
            (folder/'source.pdf').write_bytes(b'%PDF-synthetic')
            db.replace_pdf_text_index(str(root),'A',source_id,['Evidence about memory.'])
            created=call('create_source_cards',cards=[{'front':'Question','back':'Answer',
                'source_card_id':str(source_id),'position':1,'quote':'Evidence about memory.'}], request_id='create-source-001')
            ids = created['note_ids']
            assert len(ids)==1
            card_ids = col.find_cards(f'nid:{ids[0]}')
            assert col.get_note(int(ids[0]))['Incremento_Parent_Card_ID']==str(source_id)
            # Normal sync changes transport counters without changing user data.
            col.db.execute('UPDATE notes SET usn=9 WHERE id=?',int(ids[0]))
            col.db.execute('UPDATE cards SET usn=9 WHERE nid=?',int(ids[0]))
            col.db.execute('UPDATE notetypes SET usn=9')
            col.close()
            col = Collection(str(root/'collection.anki2'))
            svc=service()
            assert call('create_source_cards',cards=[{'front':'Question','back':'Answer',
                'source_card_id':str(source_id),'position':1,'quote':'Evidence about memory.'}], request_id='create-source-001')==created
            undone=call('undo_change',undo_id=created['undo_id'])
            assert col.find_cards(f'nid:{ids[0]}')==[]
            col.close()
            col = Collection(str(root/'collection.anki2'))
            svc=service()
            call('undo_change',undo_id=undone['undo_id'])
            assert col.find_cards(f'nid:{ids[0]}')==card_ids
            assert col.get_note(int(ids[0]))['Front']=='Question'
            svc.config['dialog']={'topics_slider':100,'random_slider':0,'enforce_priority':False,'pdf_slider':100}
            schedule_before=col.db.all('SELECT * FROM cards ORDER BY id')
            preview=call('preview_session',count=1,anki_query=f'nid:{ids[0]}')
            assert preview['selected']==1, preview
            assert col.db.all('SELECT * FROM cards ORDER BY id')==schedule_before
            epub=root/'original.epub'
            with ZipFile(epub,'w') as archive:
                archive.writestr('mimetype','application/epub+zip')
                archive.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>')
                archive.writestr('content.opf','<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="one" href="one.xhtml"/></manifest><spine><itemref idref="one"/></spine></package>')
                archive.writestr('one.xhtml','<html><body>Imported evidence</body></html>')
            original=epub.read_bytes()
            library_list=call('create_list',name='Imported documents')
            imported=call('import_documents',documents=[{'kind':'epub','path':str(epub),'title':'Imported book'}],list_id=library_list['list_id'])
            imported_id=imported['note_ids'][0]
            stored=col.get_note(int(imported_id))['EPUB_Filename']
            copy=root/'user_files/A/epubs'/stored
            assert copy.read_bytes()==original
            svc=service()
            reversed_import=call('undo_change',undo_id=imported['undo_id'])
            assert not copy.exists()
            assert epub.read_bytes()==original
            assert col.find_cards(f'nid:{imported_id}')==[]
            deleted_list=call('delete_list',list_id=library_list['list_id'])
            from backend.mcp_service import ToolError
            try:
                call('undo_change',undo_id=reversed_import['undo_id'])
            except ToolError:
                pass
            else:
                raise AssertionError('Redo restored into a deleted list')
            assert col.find_cards(f'nid:{imported_id}')==[]
            assert not copy.exists()
            call('undo_change',undo_id=deleted_list['undo_id'])
            svc=service()
            call('undo_change',undo_id=reversed_import['undo_id'])
            assert copy.read_bytes()==original
            assert col.get_note(int(imported_id))['EPUB_Filename']==stored
            assert epub.read_bytes()==original
            from unittest.mock import patch
            with patch('backend.webpage_markdown.fetch_webpage_markdown',return_value={
                'title':'Saved article','url':'https://example.test/article',
                'markdown_document':'# Saved article\\n\\nSaved webpage evidence.'}):
                captured=call('import_documents',documents=[{'kind':'web','url':'https://example.test/article'}])
            web_id=captured['note_ids'][0]
            assert col.get_note(int(web_id))['Incremento_Source_Link']=='https://example.test/article'
            assert 'Saved webpage evidence' in call('read_source',card_id=str(col.find_cards(f'nid:{web_id}')[0]))['text']
            captured_undo=call('undo_change',undo_id=captured['undo_id'])
            svc=service()
            with patch('backend.webpage_markdown.fetch_webpage_markdown',side_effect=AssertionError('Redo refetched original webpage')):
                call('undo_change',undo_id=captured_undo['undo_id'])
            assert col.get_note(int(web_id))['Title']=='Saved article'
            import fitz
            pdf=root/'original.pdf'
            document=fitz.open();page=document.new_page();page.insert_text((72,72),'PDF import evidence');document.save(pdf);document.close()
            original_pdf=pdf.read_bytes()
            pdf_import=call('import_documents',documents=[{'kind':'pdf','path':str(pdf),'title':'Imported PDF'}])
            pdf_note=col.get_note(int(pdf_import['note_ids'][0]))
            pdf_copy=root/'user_files/A/pdfs'/pdf_note['PDF_Filename']
            assert pdf_copy.read_bytes()==original_pdf
            assert 'PDF import evidence' in call('read_source',card_id=str(col.find_cards(f'nid:{pdf_note.id}')[0]))['text']
            svc=service()
            call('undo_change',undo_id=pdf_import['undo_id'])
            assert not pdf_copy.exists()
            assert pdf.read_bytes()==original_pdf
            card=col.get_card(card_ids[0]);card.reps=1;col.update_card(card)
            from backend.mcp_service import ToolError
            try:
                call('undo_change',undo_id=next(item['undo_id'] for item in call('get_undo_history')['items']
                     if item['action']=='create_source_cards' and item['direction']=='undo'))
            except ToolError:
                pass
            else:
                raise AssertionError('Undo deleted a card whose scheduling had changed')
            assert col.get_note(int(ids[0]))['Front']=='Question'
            print('durable creation and imports: ok')
        finally:
            db.close_connection()
            col.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr + result.stdout
    assert 'durable creation and imports: ok' in result.stdout
