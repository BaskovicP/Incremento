"""Local source processing, semantic retrieval and smart-library contracts."""

from tests.test_mcp_anki import native


def test_ocr_runs_on_local_images_without_schema_changes_and_is_durably_reversible(tmp_path):
    native(
        tmp_path,
        """
        import base64
        from backend import mcp_library
        note,cid=seed('<img src="scan.png">')
        image=Path(col.media.dir())/'scan.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9F0AAAAASUVORK5CYII='))
        original=col.models.get(note.mid)
        # The executable is the external boundary; all path/index/reversal logic is real.
        mcp_library.recognize_image=lambda data,language: 'Recognized local image evidence'
        result=call('run_image_ocr',note_ids=[str(note.id)],language='eng')
        assert call('read_ocr',note_id=str(note.id))['text']=='Recognized local image evidence'
        assert col.models.get(note.mid)==original and image.is_file()
        restart();call('undo_change',undo_id=result['undo_id'])
        assert call('read_ocr',note_id=str(note.id))['text']==''
        assert col.models.get(note.mid)==original and image.is_file()
    """,
    )


def test_pdf_ocr_updates_only_selected_index_pages_and_restores_previous_text(tmp_path):
    native(
        tmp_path,
        """
        import fitz
        from backend import mcp_library
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Scanned source';note['PDF_Filename']='scan.pdf';col.add_note(note,1)
        cid=col.find_cards(f'nid:{note.id}')[0]
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True)
        pdf=folder/'scan.pdf'
        with fitz.open() as document:
            document.new_page();document.new_page();document.save(pdf)
        original=pdf.read_bytes()
        db.replace_pdf_text_index(str(root),'A',cid,['First page','Old second page'])
        mcp_library.recognize_image=lambda data,language:'Scanned second page evidence'
        changed=call('run_pdf_ocr',card_id=str(cid),pages=[2],language='eng')
        assert call('read_document',card_id=str(cid),position=1)['text']=='First page'
        assert 'Scanned second' in call('read_document',card_id=str(cid),position=2)['text']
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert call('read_document',card_id=str(cid),position=2)['text']=='Old second page'
        assert pdf.read_bytes()==original
    """,
    )


def test_semantic_index_retrieves_related_wording_and_undo_restores_previous_index(tmp_path):
    native(
        tmp_path,
        """
        seed('Heart circulation','Basic')
        related,cid=seed('Blood pump vessels')
        bridge,bid=seed('Heart circulation blood pump vessels')
        seed('Banana orchard fruit')
        built=call('build_semantic_index',reset=True)
        while built.get('next_cursor'):
            built=call('build_semantic_index',cursor=built['next_cursor'])
        result=call('search_meaning',query='heart circulation')
        match=next(item for item in result['items'] if item['card_id']==str(cid))
        assert 'heart' not in match['text'].casefold() and match['score']>0
        restart();assert call('search_meaning',query='heart')['items']
        call('undo_change',undo_id=built['undo_id'])
        assert call('get_semantic_status')['documents']==0
    """,
    )


def test_smart_list_rules_preview_membership_refresh_and_undo_after_restart(tmp_path):
    native(
        tmp_path,
        """
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Neuroscience';note['PDF_Filename']='neuro.pdf';note.tags=['neuro'];col.add_note(note,1)
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True);(folder/'neuro.pdf').write_bytes(b'%PDF-synthetic')
        created=call('create_list',name='Unread neuroscience')
        current=call('get_smart_lists')
        saved=call('manage_smart_list',action='save',list_id=created['list_id'],name='Neuroscience rule',
                   anki_query='tag:neuro',expected_revision=current['revision'])
        plan=call('preview_smart_list_refresh',list_id=created['list_id'])
        assert call('get_lists',list_id=created['list_id'])['items']==[]
        applied=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert call('get_lists',list_id=created['list_id'])['items']==[{'book_id':'pdf:neuro.pdf'}]
        restart();call('undo_change',undo_id=applied['undo_id'])
        assert call('get_lists',list_id=created['list_id'])['items']==[]
        call('undo_change',undo_id=saved['undo_id'])
        assert call('get_smart_lists')['items']==[]
    """,
    )


def test_library_duplicate_search_finds_notes_across_decks_and_merge_has_persistent_undo(tmp_path):
    native(
        tmp_path,
        """
        first,cid=seed('Memory retrieval practice')
        second,other=seed('<b>Memory retrieval practice</b>')
        col.set_deck([other],col.decks.id('Another deck'))
        scanned=call('find_library_duplicates',minimum_similarity=0.8)
        assert any(set(item['note_ids'])=={str(first.id),str(second.id)} for item in scanned['pairs'])
        plan=call('preview_duplicate_merge',note_ids=[str(first.id),str(second.id)],survivor_note_id=str(first.id),fields={'Back':'Merged answer'})
        applied=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert col.find_cards(f'nid:{second.id}')==[] and col.get_note(first.id)['Back']=='Merged answer'
        restart();call('undo_change',undo_id=applied['undo_id'])
        assert col.find_cards(f'nid:{first.id}')==[cid] and col.find_cards(f'nid:{second.id}')==[other]
        assert col.get_note(first.id)['Back']=='Answer'
    """,
    )


def test_library_health_reports_missing_media_empty_fields_and_broken_parent_links_without_writes(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed('<img src="missing.png">')
        note['Back']='';col.update_note(note)
        before=col.db.all('SELECT * FROM notes ORDER BY id')
        report=call('audit_library')
        assert any(item['note_id']==str(note.id) and item['issue']=='missing_media' for item in report['issues'])
        assert any(item['note_id']==str(note.id) and item['issue']=='empty_field' for item in report['issues'])
        assert col.db.all('SELECT * FROM notes ORDER BY id')==before
        assert call('get_undo_history')['items']==[]
    """,
    )


def test_smart_refresh_keeps_foreign_keys_and_other_list_memberships_consistent(tmp_path):
    native(
        tmp_path,
        """
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Book';note['PDF_Filename']='book.pdf';col.add_note(note,1)
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True);(folder/'book.pdf').write_bytes(b'%PDF-synthetic')
        first=call('create_list',name='Smart')
        other=call('create_list',name='Other')
        conn=db.get_connection(str(root),'A');conn.execute('PRAGMA foreign_keys=ON')
        call('manage_smart_list',action='save',list_id=first['list_id'],name='All books',anki_query='note:"Incremento PDF"',expected_revision=call('get_smart_lists')['revision'])
        preview=call('preview_smart_list_refresh',list_id=first['list_id'])
        applied=call('apply_advanced_plan',plan_id=preview['plan_id'])
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        restart();call('undo_change',undo_id=applied['undo_id'])
        assert call('get_lists',list_id=first['list_id'])['items']==[]
        assert call('get_lists',list_id=other['list_id'])['items']==[]
    """,
    )


def test_background_pdf_reindex_preserves_matching_ocr_and_discards_it_for_changed_source(tmp_path):
    native(
        tmp_path,
        """
        import fitz
        from backend import mcp_library,search_indexer
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Scan';note['PDF_Filename']='scan.pdf';col.add_note(note,1)
        cid=col.find_cards(f'nid:{note.id}')[0]
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True);pdf=folder/'scan.pdf'
        with fitz.open() as doc: doc.new_page();doc.save(pdf)
        mcp_library.recognize_image=lambda data,language:'Retained OCR evidence'
        call('run_pdf_ocr',card_id=str(cid),pages=[1])
        search_indexer.index_pdf_documents(str(root),'A',[(cid,str(pdf))],extractor=lambda *_a,**_k:[''],force=True)
        assert call('read_document',card_id=str(cid))['text']=='Retained OCR evidence'
        with fitz.open() as doc: doc.new_page(width=600);doc.save(pdf)
        search_indexer.index_pdf_documents(str(root),'A',[(cid,str(pdf))],extractor=lambda *_a,**_k:['New source text'],force=True)
        assert call('read_document',card_id=str(cid))['text']=='New source text'
    """,
    )


def test_changed_smart_query_matches_are_rejected_before_any_membership_write(tmp_path):
    native(
        tmp_path,
        """
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Book';note['PDF_Filename']='book.pdf';note.tags=['selected'];col.add_note(note,1)
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True);(folder/'book.pdf').write_bytes(b'%PDF-synthetic')
        booklist=call('create_list',name='Smart list')
        call('manage_smart_list',action='save',list_id=booklist['list_id'],name='Selected',anki_query='tag:selected',expected_revision=call('get_smart_lists')['revision'])
        plan=call('preview_smart_list_refresh',list_id=booklist['list_id'])
        note.tags=[];col.update_note(note)
        rejected(lambda:call('apply_advanced_plan',plan_id=plan['plan_id']))
        assert call('get_lists',list_id=booklist['list_id'])['items']==[]
    """,
    )


def test_semantic_results_exclude_stale_note_contents_and_malformed_rules_fail_closed(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed('Heart circulation')
        call('build_semantic_index',reset=True)
        note['Front']='Changed source';col.update_note(note)
        results=call('search_meaning',query='heart')
        assert results['items']==[] and results['stale_passages_skipped']==1
        path=svc._store_path('smart_lists');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('{"version":1,"rules":[]}')
        rejected(lambda:call('get_smart_lists'))
        assert path.read_text()=='{"version":1,"rules":[]}'
    """,
    )


def test_semantic_progress_resumes_after_restart_and_rejects_a_cursor_from_an_undone_build(tmp_path):
    native(
        tmp_path,
        """
        for index in range(25): seed('Heart circulation evidence '+('vessels '*1200)+str(index))
        first=call('build_semantic_index',reset=True)
        assert first['next_cursor'] and not first['complete']
        restart()
        second=call('build_semantic_index')
        assert second['documents']>first['documents']
        call('undo_change',undo_id=second['undo_id'])
        call('undo_change',undo_id=first['undo_id'])
        rejected(lambda:call('build_semantic_index',cursor=first['next_cursor']))
        assert call('get_semantic_status')['documents']==0
    """,
    )


def test_duplicate_group_pagination_uses_bounded_identity_cursors_for_long_fields(tmp_path):
    native(
        tmp_path,
        """
        for index in range(3):
            text=('Long field '+('x'*2500)+str(index))
            seed(text);seed(text)
        first=call('find_library_duplicates',limit=1)
        assert first['next_cursor'] and len(first['next_cursor'])<=2048
        second=call('find_library_duplicates',limit=1,cursor=first['next_cursor'])
        assert any(item['kind']=='exact_first_field' for item in second['pairs'])
    """,
    )


def test_partial_pdf_ocr_does_not_hide_later_document_pages_from_semantic_indexing(tmp_path):
    native(
        tmp_path,
        """
        import fitz
        from backend import mcp_library
        from backend.pdf_manager import ensure_pdf_note_type
        ensure_pdf_note_type(col)
        note=col.new_note(col.models.by_name('Incremento PDF'));note['Title']='Scan';note['PDF_Filename']='scan.pdf';col.add_note(note,1)
        cid=col.find_cards(f'nid:{note.id}')[0]
        folder=root/'user_files/A/pdfs';folder.mkdir(parents=True);pdf=folder/'scan.pdf'
        with fitz.open() as doc:
            doc.new_page();doc.new_page();page=doc.new_page();page.insert_text((40,40),'Later unique hippocampus material');doc.save(pdf)
        mcp_library.recognize_image=lambda data,language:'Scanned second page'
        call('run_pdf_ocr',card_id=str(cid),pages=[2])
        call('build_semantic_index',reset=True)
        results=call('search_meaning',query='hippocampus')
        assert any(item['card_id']==str(cid) and item['position']==3 for item in results['items'])
    """,
    )
