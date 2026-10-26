"""Native Qt PDF fallback, real Anki, and captured-profile import in a worker."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_prepared_pdf_import_uses_native_qt_in_worker_and_keeps_captured_profile():
    script = dedent(r'''
        import os, sys, tempfile, types
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        from PyQt6.QtWidgets import QApplication
        from anki.collection import Collection
        import fitz
        app = QApplication([])
        with tempfile.TemporaryDirectory(prefix="incremento-pdf-worker-") as temporary:
            root = Path(temporary)
            source = root / "synthetic.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Synthetic searchable worker PDF")
            document.save(str(source))
            document.close()
            col = Collection(str(root / "collection.anki2"))
            aqt = types.ModuleType("aqt")
            aqt.mw = types.SimpleNamespace(col=col,
                addonManager=types.SimpleNamespace(getConfig=lambda name: {}))
            sys.modules['aqt'] = aqt
            from backend import browser_bridge, paths, pdf_manager, db
            from backend.card_projection import ReadCollection
            paths.set_active_profile("Other")
            browser_bridge._addon_dir = str(root)
            def directory(profile=None):
                target = paths.get_pdf_dir(str(root), profile or "Other")
                target.mkdir(parents=True, exist_ok=True)
                return str(target)
            pdf_manager.get_pdf_dir = directory
            item = browser_bridge.normalize_add_content_payload({
                "kind": "pdf", "url": "https://example.test/synthetic.pdf", "title": "Synthetic",
            })
            item[browser_bridge._PREPARED_PDF_PATH_KEY] = str(source)
            # Force the native Qt fallback; it must run inside the worker.
            sys.modules['fitz'] = None
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(browser_bridge.import_prepared_pdf_item, item,
                                         col=col, profile="Captured").result(timeout=30)
            cid = result['cardId']
            note = col.get_card(cid).note()
            assert note[pdf_manager.PDF_COVER_FIELD]
            assert list((root / 'user_files' / 'Captured' / 'pdfs').glob('*.pdf'))
            assert not (root / 'user_files' / 'Other').exists()
            assert db.search_pdf_text_index(str(root), 'Captured', 'searchable')[0][0] == cid
            assert db.get_connection(str(root), 'Captured').execute(
                "SELECT count(*) FROM import_journal WHERE state='pending'").fetchone()[0] == 0
            projection = ReadCollection(col)
            projection.load([cid])
            assert projection.get_card(cid).note().fields == note.fields
            assert projection.get_card(cid).note().tags == note.tags
            assert projection.get_card(cid).ivl == col.get_card(cid).ivl
            col.close()
            db.close_connection()
        print('native worker PDF import: ok')
    ''')
    result = subprocess.run([sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "native worker PDF import: ok" in result.stdout
