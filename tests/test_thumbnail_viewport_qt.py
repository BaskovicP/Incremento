import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_bookshelf_decodes_only_near_viewport_and_covers_visible_rows_after_scrolling():
    script = dedent("""
        import os, sys, tempfile, time
        from pathlib import Path
        from types import SimpleNamespace
        from concurrent.futures import Future
        sys.path.insert(0, str(Path.cwd() / 'backend'))
        sys.path.insert(0, str(Path.cwd() / 'frontend'))
        from aqt.qt import QApplication, QPixmap
        import pdf_bookshelf as shelf
        app = QApplication([])
        jobs, decoded = [], []
        with tempfile.TemporaryDirectory() as temporary:
            image = QPixmap(120, 180); image.fill()
            image.save(str(Path(temporary) / 'cover.png'))
            shelf.mw = SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(dir=lambda: temporary)),
                taskman=SimpleNamespace(run_in_background=lambda work, done, **kwargs: jobs.append((work, done, kwargs))))
            shelf._active_profile = lambda: 'A'
            shelf._DocumentBookshelfDialog._start_pdf_metadata_scan = lambda self: None
            original = shelf._DocumentBookshelfDialog._set_thumbnail
            def record(self, item, entry, icon, generation):
                decoded.append(entry.card_id)
                original(self, item, entry, icon, generation)
            shelf._DocumentBookshelfDialog._set_thumbnail = record
            entries = [shelf._BookshelfEntry('Book ' + str(i), i, 'EPUB', cover_filename='cover.png') for i in range(1, 2001)]
            dialog = shelf._DocumentBookshelfDialog(addon_dir=temporary, entries=entries)
            dialog.resize(800, 700)
            dialog.show()
            deadline = time.monotonic() + 10
            while dialog._list.count() < len(entries) and time.monotonic() < deadline:
                app.processEvents()
            assert dialog._list.count() == len(entries)
            def drain():
                dialog._thumbnail_timer.stop()
                dialog._prioritize_thumbnails()
                for _ in range(200):
                    app.processEvents()
                    if jobs:
                        work, done, options = jobs.pop(0)
                        assert options['uses_collection'] is False
                        future = Future(); future.set_result(work()); done(future)
                    elif not dialog._thumbnail_busy:
                        break
            def visible_ids():
                viewport = dialog._list.viewport().rect()
                return {dialog._list.item(i).data(shelf.Qt.ItemDataRole.UserRole).card_id
                    for i in range(dialog._list.count())
                    if dialog._list.visualItemRect(dialog._list.item(i)).intersects(viewport)}
            drain()
            assert visible_ids() <= set(decoded), (visible_ids(), set(decoded))
            assert len(decoded) < 80, len(decoded)
            decoded.clear()
            scrollbar = dialog._list.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum() // 2)
            drain()
            assert visible_ids() <= set(decoded), (visible_ids(), set(decoded))
            assert len(decoded) < 80, len(decoded)
            assert dialog._thumbnail_cache.bytes_used <= 24 * 1024 * 1024
            dialog.reject()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
