"""A rendered Markdown import uses real Anki and profile-isolated document state."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_markdown_import_in_real_anki_is_a_searchable_document_and_rolls_back_rejection(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = dedent(r"""
        from pathlib import Path
        import sys
        import zipfile
        from anki.collection import Collection
        from backend import db, paths, epub_manager, epub_highlights, reader_bookmarks
        from backend.markdown_manager import add_markdown_card, load_markdown_document, save_markdown_document
        from backend.cards import get_document_card_type

        addon = Path(sys.argv[1])
        source = addon / 'lesson.md'
        original = '# Lesson\n\nHello **κόσμος中文**.\n\n## Practice\n\nLearn from this.'
        source.write_text(original, encoding='utf-8')
        profile = 'Captured'
        paths.set_active_profile('Other')
        epub_dir = paths.get_epub_dir(addon, profile)
        epub_dir.mkdir(parents=True)
        epub_manager.get_epub_dir = lambda profile=None: str(paths.get_epub_dir(addon, profile))
        epub_manager.get_epub_extract_root = lambda profile=None: str(paths.get_epub_extract_root(addon, profile))
        # Cover drawing is a Qt/media boundary, not the import contract.
        epub_manager.render_epub_cover_media = lambda *args, **kwargs: ''
        col = Collection(str(addon / 'collection.anki2'))
        try:
            cid = add_markdown_card(str(addon), profile, col, str(source), 'Study <Book>', tags=['topic', 'study'])
            card = col.get_card(cid)
            note = card.note()
            assert note.note_type()['name'] == 'Incremento EPUB'
            assert get_document_card_type(cid, col=col) == 'epub'
            assert note['Incremento_Source_Type'] == 'Markdown'
            assert note['Incremento_Source_Title'] == 'Study <Book>'
            assert note['Incremento_Source_Link'] == 'epubs/' + note['EPUB_Filename']
            assert note['Title'] == 'Study &lt;Book&gt;'
            assert 'topic' in note.tags and 'study' in note.tags
            assert 'Incremento_Content_ID' not in note.keys()
            conn = db.get_connection(str(addon), profile)
            rows = conn.execute('SELECT section_index, text FROM epub_text_index WHERE card_id=? ORDER BY section_index', (cid,)).fetchall()
            assert len(rows) == 2 and 'κόσμος中文' in rows[0][1]
            assert conn.execute('SELECT state FROM import_journal').fetchall() == [('committed',)]
            assert conn.execute('SELECT kind, storage_key FROM content_items').fetchall() == [('epub', note['Incremento_Source_Link'])]
            with zipfile.ZipFile(epub_dir / note['EPUB_Filename']) as archive:
                assert archive.read('source.md').decode('utf-8') == original
            assert not paths.get_user_files_dir(addon, 'Other').exists()

            snapshot = load_markdown_document(str(addon), profile, note['EPUB_Filename'])
            epub_highlights.add_highlight(str(addon), profile, cid, {'id':'saved','sectionIndex':1,'text':'Learn','startOffset':0,'endOffset':5})
            reader_bookmarks.add_reader_bookmark(str(addon), profile, cid, 'epub', {'section_index':1,'scroll_ratio':0.25})
            epub_manager.set_epub_progress(str(addon), profile, cid, section_index=1, scroll_ratio=0.25)
            supplemental_before = {table: conn.execute('SELECT * FROM ' + table).fetchall()
                                   for table in ('epub_highlights','epub_progress','reader_bookmarks')}
            fields_before = list(note.fields)
            content_before = conn.execute('SELECT * FROM content_items').fetchall()
            edited = '# Revised\n\nNew searchable content.'
            save_markdown_document(str(addon), profile, cid, note['EPUB_Filename'], edited,
                                   title='Study <Book>', expected_revision=snapshot.revision)
            assert col.get_card(cid).note().fields == fields_before
            assert conn.execute('SELECT * FROM content_items').fetchall() == content_before
            assert {table: conn.execute('SELECT * FROM ' + table).fetchall()
                    for table in supplemental_before} == supplemental_before
            assert db.search_epub_text_index(str(addon), profile, 'searchable')[0][0] == cid
            assert load_markdown_document(str(addon), profile, note['EPUB_Filename']).text == edited
            assert paths.get_markdown_backup_path(str(addon), profile, note['EPUB_Filename']).is_file()
            assert source.read_text(encoding='utf-8') == original
            try:
                save_markdown_document(str(addon), profile, cid, note['EPUB_Filename'], '# Stale',
                                       title='Study <Book>', expected_revision=snapshot.revision)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Stale editor overwrote newer content')

            before = set(epub_dir.iterdir())
            extracts_before = set(paths.get_epub_extract_root(addon, profile).iterdir())
            original_add = col.add_note
            col.add_note = lambda *args: 0
            try:
                try:
                    add_markdown_card(str(addon), profile, col, str(source), 'Rejected')
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Rejected import succeeded')
            finally:
                col.add_note = original_add
            assert set(epub_dir.iterdir()) == before
            assert set(paths.get_epub_extract_root(addon, profile).iterdir()) == extracts_before
            assert conn.execute('SELECT COUNT(*) FROM content_items').fetchone()[0] == 1
            assert conn.execute('SELECT state FROM import_journal ORDER BY rowid').fetchall() == [('committed',), ('rolled_back',)]
            assert source.read_text(encoding='utf-8') == original
        finally:
            col.close()
            db.close_connection()
        print('Markdown document import in real Anki: ok')
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=root,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Markdown document import in real Anki: ok" in result.stdout
