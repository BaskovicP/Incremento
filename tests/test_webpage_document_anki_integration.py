"""Real Anki: a Companion snapshot is a searchable, journaled EPUB document."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
import pytest


@pytest.mark.parametrize("capture_format", ["markdown", "html"])
def test_offline_webpage_import_uses_captured_profile_and_rolls_back_rejected_note(tmp_path, capture_format):
    script = dedent(r'''
        from pathlib import Path
        import sys
        import zipfile
        from anki.collection import Collection
        from backend import paths, epub_manager, browser_bridge, db, markdown_manager
        from backend.priority_manager import get_priority

        addon = Path(sys.argv[1])
        profile = 'Captured'
        capture_format = sys.argv[2]
        paths.set_active_profile('Other')
        browser_bridge._addon_dir = str(addon)
        paths.get_epub_dir(addon, profile).mkdir(parents=True)
        epub_manager.get_epub_dir = lambda profile=None: str(paths.get_epub_dir(addon, profile))
        epub_manager.get_epub_extract_root = lambda profile=None: str(paths.get_epub_extract_root(addon, profile))
        epub_manager.render_epub_cover_media = lambda *args, **kwargs: ''
        col = Collection(str(addon / 'collection.anki2'))
        # Legacy installations may already have the optional identity field.
        epub_manager.ensure_epub_note_type(col)
        model = col.models.by_name('Incremento EPUB')
        col.models.add_field(model, col.models.new_field('Incremento_Content_ID'))
        col.models.save(model)
        request = browser_bridge.prepare_add_content_request_off_main({
            'kind': 'document', 'url': 'https://example.com/article', 'title': 'Frozen article',
            'tags': ['reading'], 'priority': 23,
            'html': '<html><head><style>.article{color:#123456}</style></head><body><article class="article"><h1>Article</h1><p>Searchable frozen passage.</p></article></body></html>',
            'documentFormat': capture_format,
        })
        try:
            result = browser_bridge.import_prepared_pdf_item(request['items'][0], col=col, profile=profile)
            cid = result['cardId']; note = col.get_card(cid).note()
            assert result['kind'] == 'document'
            assert note.note_type()['name'] == 'Incremento EPUB'
            assert note['Incremento_Source_Type'] == ('HTML' if capture_format == 'html' else 'Markdown')
            assert note['Incremento_Source_Link'] == 'https://example.com/article'
            assert 'reading' in note.tags
            assert get_priority(str(addon), profile, cid) == 23
            assert not paths.get_user_files_dir(addon, 'Other').exists()
            conn = db.get_connection(str(addon), profile)
            assert note['Incremento_Content_ID'] == conn.execute('SELECT content_id FROM content_items').fetchone()[0]
            assert conn.execute('SELECT state FROM import_journal').fetchall() == [('committed',)]
            stored = paths.get_epub_dir(addon, profile) / note['EPUB_Filename']
            assert conn.execute('SELECT kind, storage_key FROM content_items').fetchall() == [('epub', 'epubs/' + stored.name)]
            assert any('Searchable frozen passage' in row[0] for row in conn.execute('SELECT text FROM epub_text_index'))
            before = stored.read_bytes()
            for format in ('html', 'md', 'txt'):
                exported = markdown_manager.export_markdown_document(str(addon), profile, stored.name, format)
                assert b'Searchable frozen passage' in exported and b'https://example.com/article' in exported
            assert stored.read_bytes() == before
            snapshot = markdown_manager.load_markdown_document(str(addon), profile, stored.name)
            if capture_format == 'markdown':
                markdown_manager.save_markdown_document(str(addon), profile, cid, stored.name, '# Edited\n\nNew passage',
                    title='Frozen article', expected_revision=snapshot.revision)
            else:
                meta = epub_manager.load_epub_metadata(str(addon), stored.name, profile=profile)
                assert len(meta['sections']) == 1
                cached = next(paths.get_epub_extract_root(addon, profile).rglob('section-1.html'))
                assert '.article{color:#123456}' in cached.read_text()
                assert 'class="article"' in cached.read_text()
            with zipfile.ZipFile(stored) as archive:
                assert b'Searchable frozen passage' in archive.read('original_source.md')
                if capture_format == 'markdown':
                    assert archive.read('source.md') == b'# Edited\n\nNew passage'
                else:
                    assert b'.article{color:#123456}' in archive.read('OEBPS/section-1.html')

            files = set(paths.get_epub_dir(addon, profile).iterdir())
            extracts = set(paths.get_epub_extract_root(addon, profile).iterdir())
            original_add = col.add_note
            col.add_note = lambda *args: 0
            try:
                try:
                    browser_bridge.import_prepared_pdf_item(request['items'][0], col=col, profile=profile)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Rejected capture succeeded')
            finally:
                col.add_note = original_add
            assert set(paths.get_epub_dir(addon, profile).iterdir()) == files
            assert set(paths.get_epub_extract_root(addon, profile).iterdir()) == extracts
            assert conn.execute('SELECT state FROM import_journal ORDER BY rowid').fetchall() == [('committed',), ('rolled_back',)]
        finally:
            browser_bridge.cleanup_prepared_add_content_request(request)
            col.close(); db.close_connection()
        print('offline webpage in real Anki: ok')
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path), capture_format],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "offline webpage in real Anki: ok" in result.stdout
