"""Content imports and generated exports keep originals and persistent undo."""

from tests.test_mcp_anki import native


def test_caption_language_cannot_be_an_external_engine_option(tmp_path):
    native(
        tmp_path,
        """
        from backend.video_manager import add_video_card
        cid=add_video_card(col,'https://www.youtube.com/watch?v=dQw4w9WgXcQ','Video')
        rejected(lambda:call('preview_operation',action='caption_download',parameters={
            'card_id':str(cid),'language':'--exec=unexpected','track':'target'}))
        assert col.note_count()==1
    """,
    )


def test_media_job_prepares_off_collection_and_preserves_intervening_edits(tmp_path):
    native(
        tmp_path,
        """
        from backend import video_manager as video
        from backend.paths import get_videos_dir
        from unittest.mock import patch
        cid=video.add_video_card(col,'https://www.youtube.com/watch?v=dQw4w9WgXcQ','Video')
        other,other_id=seed()
        def service():return McpService(str(root),'A','context',config={},alive=lambda:True,runtime=lambda action,p:{})
        svc=service()
        def download(addon_dir,profile,url,*,output_directory,**kwargs):
            assert not list(get_videos_dir(addon_dir,profile).glob('*'))
            path=Path(output_directory)/'prepared.mp4';path.write_bytes(b'bounded video output')
            return 'videos/'+path.name
        plan=call('preview_operation',action='video_download',parameters={'card_id':str(cid)})
        job=call('start_operation_job',plan_id=plan['plan_id'])
        with patch.object(video,'download_and_compress_video',download):
            svc.prepare_operation_job(job['job_id'])
        other['Front']='Studied during preparation';col.update_note(other)
        svc.execute_operation_job(col,job['job_id'])
        note=col.get_note(col.get_card(cid).nid)
        relative=video.get_video_note_media(note)['local_video_file']
        assert relative and (get_videos_dir(str(root),'A')/Path(relative).name).read_bytes()==b'bounded video output'
        status=next(j for j in call('get_background_tasks')['mcp_jobs'] if j['job_id']==job['job_id'])
        assert status['status']=='completed'
        restart();call('undo_change',undo_id=status['undo_id'])
        assert col.get_note(other.id)['Front']=='Studied during preparation'
        assert not video.get_video_note_media(col.get_note(col.get_card(cid).nid))['local_video_file']
        assert not (get_videos_dir(str(root),'A')/Path(relative).name).exists()
    """,
    )


def test_quarantine_protects_encoded_references_and_unsaved_drafts(tmp_path):
    native(
        tmp_path,
        """
        from backend.paths import get_extraction_draft_path
        note,cid=seed();media=Path(col.media.dir())/'a b.png';media.write_bytes(b'picture')
        note['Front']='<img src="a%20b.png">';col.update_note(note)
        rejected(lambda:call('preview_operation',action='quarantine_files',parameters={'paths':[str(media)]}))
        assert media.exists()
        note['Front']='No image';col.update_note(note)
        draft=get_extraction_draft_path(str(root),'A');draft.parent.mkdir(parents=True,exist_ok=True)
        draft.write_text('{"text":"<img src=a%20b.png>"}')
        rejected(lambda:call('preview_operation',action='quarantine_files',parameters={'paths':[str(media)]}))
        assert media.exists()
        draft.unlink()
        plan=call('preview_operation',action='quarantine_files',parameters={'paths':[str(media)]})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert not media.exists()
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert media.read_bytes()==b'picture'
    """,
    )


def test_apkg_import_preflights_package_and_is_restart_reversible(tmp_path):
    native(
        tmp_path,
        """
        from anki.import_export_pb2 import ExportAnkiPackageOptions
        source=Collection(str(root/'source.anki2'))
        try:
            note=source.new_note(source.models.by_name('Basic'));note['Front']='Imported';note['Back']='Answer';source.add_note(note,1)
            package=root/'input.apkg';source.export_anki_package(out_path=str(package),options=ExportAnkiPackageOptions(with_scheduling=True,with_media=True),limit=None)
        finally:source.close()
        plan=call('preview_operation',action='import_content',parameters={'kind':'apkg','path':str(package),'title':'Package'})
        assert plan['requires_full_sync_acknowledgement']
        rejected(lambda:call('apply_advanced_plan',plan_id=plan['plan_id']))
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'],acknowledge_full_sync=True)
        assert col.note_count()==1
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert col.note_count()==0 and package.exists()
    """,
    )


def test_writing_markdown_and_local_file_imports_undo_and_redo_after_restart(tmp_path):
    native(
        tmp_path,
        """
        source=root/'source.md';source.write_text('# Evidence\\n\\nA useful passage.')
        original=source.read_bytes()
        for kind in ('writing','markdown','local_file'):
            plan=call('preview_operation',action='import_content',parameters={'kind':kind,
                'path':str(source),'title':'Imported '+kind,'deck_name':'Default','initial_markdown':'Draft text'})
            made=call('apply_advanced_plan',plan_id=plan['plan_id'])
            cid=int(made['card_id']);nid=col.get_card(cid).nid
            assert col.get_note(nid).fields
            restart();redo=call('undo_change',undo_id=made['undo_id'])
            assert col.find_cards(f'nid:{nid}')==[] and source.read_bytes()==original
            restart();inverse=call('undo_change',undo_id=redo['undo_id'])
            assert col.find_cards(f'nid:{nid}')==[cid]
            call('undo_change',undo_id=inverse['undo_id'])
    """,
    )


def test_supermemo_zip_import_reverses_cards_reviews_and_supplemental_state(tmp_path):
    from tests.test_supermemo_format import _write_fixture
    from zipfile import ZipFile

    source = tmp_path / "source"
    source.mkdir()
    _write_fixture(source)
    with ZipFile(tmp_path / "supermemo.zip", "w") as archive:
        for path in source.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    native(
        tmp_path,
        """
        original=col.db.scalar('select count(*) from revlog')
        plan=call('preview_operation',action='import_content',parameters={'kind':'supermemo','path':str(root/'supermemo.zip'),'title':'Archive'})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert changed['created']==2 and col.note_count()==2
        assert col.db.scalar('select count(*) from revlog')>original
        restart();redo=call('undo_change',undo_id=changed['undo_id'])
        assert col.note_count()==0 and col.db.scalar('select count(*) from revlog')==original
        restart();call('undo_change',undo_id=redo['undo_id'])
        assert col.note_count()==2
    """,
    )


def test_image_occlusion_uses_native_masks_and_restores_generated_cards_after_restart(tmp_path):
    native(
        tmp_path,
        """
        import base64
        image=root/'source.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9F0AAAAASUVORK5CYII='))
        original=image.read_bytes()
        plan=call('preview_operation',action='image_occlusion_create',parameters={'path':str(image),'masks':[
            {'group':1,'shape':'rect','left':0.1,'top':0.1,'width':0.2,'height':0.2},
            {'group':2,'shape':'ellipse','left':0.5,'top':0.5,'width':0.2,'height':0.2}]})
        made=call('apply_advanced_plan',plan_id=plan['plan_id'])
        ids=col.find_cards('note:"Image Occlusion"')
        assert len(ids)==2
        restart();redo=call('undo_change',undo_id=made['undo_id'])
        assert col.find_cards('note:"Image Occlusion"')==[] and image.read_bytes()==original
        restart();call('undo_change',undo_id=redo['undo_id'])
        assert col.find_cards('note:"Image Occlusion"')==ids
    """,
    )


def test_markdown_preview_freezes_local_resources_before_publishing(tmp_path):
    native(
        tmp_path,
        """
        import struct,zlib
        from zipfile import ZipFile
        def png(rgb):
            def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
            return bytes.fromhex('89504e470d0a1a0a')+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(bytes([0,*rgb])))+chunk(b'IEND',b'')
        image=root/'image.png';image.write_bytes(png([255,0,0]));original=image.read_bytes()
        source=root/'image.md';source.write_text('# Page\\n![Local](image.png)')
        plan=call('preview_operation',action='import_content',parameters={'kind':'markdown','title':'Local images','path':str(source)})
        image.write_bytes(png([0,0,255]))
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        item=call('get_cards',card_ids=[changed['card_id']])['items'][0]
        filename=col.get_note(int(item['note_id']))['EPUB_Filename']
        from backend.paths import get_epub_dir
        with ZipFile(get_epub_dir(str(root),'A')/filename) as archive:
            assert original in [archive.read(name) for name in archive.namelist() if name.endswith('.png')]
    """,
    )


def test_package_and_csv_exports_are_reversible_without_overwriting_existing_files(tmp_path):
    native(
        tmp_path,
        """
        note,cid=seed()
        for format in ('apkg','csv'):
            path=root/('selected.'+format)
            plan=call('preview_operation',action='export_cards',parameters={'path':str(path),'format':format,'card_ids':[str(cid)]})
            made=call('apply_advanced_plan',plan_id=plan['plan_id'])
            original=path.read_bytes();assert original
            restart();redo=call('undo_change',undo_id=made['undo_id'])
            assert not path.exists() and col.find_cards(f'nid:{note.id}')==[cid]
            restart();call('undo_change',undo_id=redo['undo_id'])
            assert path.read_bytes()==original
            rejected(lambda:call('preview_operation',action='export_cards',parameters={'path':str(path),'format':format,'card_ids':[str(cid)]}))
    """,
    )


def test_source_relink_and_pdf_snapshot_restore_prior_content_and_owned_files(tmp_path):
    native(
        tmp_path,
        """
        import fitz
        source=root/'source.pdf'
        with fitz.open() as document:
            page=document.new_page();page.insert_text((72,72),'A memorable source passage');document.save(source)
        imported=call('import_documents',documents=[{'kind':'pdf','path':str(source),'title':'Book'}])
        nid=int(imported['note_ids'][0]);cid=str(col.find_cards(f'nid:{nid}')[0])
        note,other=seed('A question')
        before=col.get_note(note.id)['Back']
        plan=call('preview_operation',action='pdf_snapshot',parameters={'source_card_id':cid,'note_id':str(note.id),'field_name':'Back','position':1,'excerpt':'memorable source passage'})
        changed=call('apply_advanced_plan',plan_id=plan['plan_id'])
        assert '<img' in col.get_note(note.id)['Back']
        restart();call('undo_change',undo_id=changed['undo_id'])
        assert col.get_note(note.id)['Back']==before and source.is_file()
        old_filename=col.get_note(nid)['PDF_Filename']
        replacement=root/'replacement.pdf'
        with fitz.open() as document:
            page=document.new_page();page.insert_text((72,72),'Replacement source evidence');document.save(replacement)
        plan=call('preview_operation',action='source_relink',parameters={'card_id':cid,'path':str(replacement)})
        relinked=call('apply_advanced_plan',plan_id=plan['plan_id'])
        new_filename=col.get_note(nid)['PDF_Filename']
        assert new_filename!=old_filename
        assert 'Replacement source evidence' in call('read_document',card_id=cid,position=1)['text']
        restart();call('undo_change',undo_id=relinked['undo_id'])
        assert col.get_note(nid)['PDF_Filename']==old_filename
        assert (root/'user_files/A/pdfs'/old_filename).is_file()
        assert not (root/'user_files/A/pdfs'/new_filename).exists()
        assert replacement.is_file() and source.is_file()
    """,
    )
