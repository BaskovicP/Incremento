"""Real-Anki DjVu imports retain text, captured profile, and journal safety."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.skipif(not shutil.which("ddjvu") or not shutil.which("djvutxt"), reason="DjVuLibre is optional")
def test_djvu_pdf_import_in_real_anki_uses_captured_profile_and_rolls_back_rejected_note(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = dedent('''
        from pathlib import Path
        import sys
        from anki.collection import Collection
        from backend import db, paths, pdf_manager
        from backend.djvu_manager import prepare_djvu_pdf
        from backend.priority_manager import set_priority, get_priority

        addon = Path(sys.argv[1])
        source = Path(sys.argv[2])
        profile = 'Captured'
        paths.set_active_profile('Other')
        pdf_dir = paths.get_pdf_dir(addon, profile)
        pdf_dir.mkdir(parents=True)
        pdf_manager.get_pdf_dir = lambda profile=None: str(paths.get_pdf_dir(addon, profile))
        col = Collection(str(addon / 'collection.anki2'))
        prepared = prepare_djvu_pdf(str(source))
        try:
            step = col.add_custom_undo_entry('Import DjVu')
            cid = pdf_manager.add_pdf_card(str(addon), col, prepared.path, 'DjVu Book',
                profile=profile, tags=['topic'], precomputed_page_texts=prepared.page_texts)
            set_priority(str(addon), profile, cid, 23.5)
            changes = col.merge_undo_entries(step)
            assert changes.card
            note = col.get_card(cid).note()
            assert note.note_type()['name'] == 'Incremento PDF'
            assert note['Title'] == 'DjVu Book'
            assert 'topic' in note.tags
            assert note['Incremento_Source_Link'] == 'pdfs/' + note['PDF_Filename']
            assert 'Incremento_Content_ID' not in note.keys()
            assert get_priority(str(addon), profile, cid) == 23.5
            assert (pdf_dir / note['PDF_Filename']).is_file()
            conn = db.get_connection(str(addon), profile)
            rows = conn.execute('SELECT page, text FROM pdf_text_index WHERE card_id=?', (cid,)).fetchall()
            assert [(page, text.split()) for page, text in rows] == [(2, ['Hello', 'κόσμος中文'])]
            assert conn.execute('SELECT state FROM import_journal').fetchall() == [('committed',)]
            assert not paths.get_user_files_dir(addon, 'Other').exists()

            # Anki's rejection must not leave a managed PDF or content item.
            before = set(pdf_dir.iterdir())
            original_add = col.add_note
            col.add_note = lambda *args: 0
            try:
                try:
                    pdf_manager.add_pdf_card(str(addon), col, prepared.path, 'Rejected',
                        profile=profile, precomputed_page_texts=prepared.page_texts)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Rejected note succeeded')
            finally:
                col.add_note = original_add
            assert set(pdf_dir.iterdir()) == before
            assert conn.execute('SELECT COUNT(*) FROM content_items').fetchone()[0] == 1
            assert conn.execute('SELECT state FROM import_journal ORDER BY rowid').fetchall() == [('committed',), ('rolled_back',)]
        finally:
            prepared.close()
            col.close()
            db.close_connection()
        print('DjVu import in real Anki: ok')
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path),
                             str(root / 'tests/fixtures/djvu/text_and_blank.djvu')],
                            cwd=root, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'DjVu import in real Anki: ok' in result.stdout
