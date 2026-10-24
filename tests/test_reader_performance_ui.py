"""Responsiveness contracts using real Qt in an isolated process."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_bookshelf_analysis_and_math_encoding_are_deferred_and_stale_results_are_dropped():
    script = dedent('''
        import sys, os
        sys.path.insert(0, os.path.abspath("backend"))
        sys.path.insert(0, os.path.abspath("frontend"))
        from concurrent.futures import Future
        from types import SimpleNamespace
        from aqt.qt import QApplication, QPixmap
        from frontend import pdf_bookshelf as shelf, snapshot_math_dialog as math
        app = QApplication([])
        jobs = []
        profile = ['A']
        mw = SimpleNamespace(col=SimpleNamespace(media=SimpleNamespace(dir=lambda: '')),
            taskman=SimpleNamespace(run_in_background=lambda work, done, **kw: jobs.append((work, done))))
        shelf.mw = math.mw = mw
        shelf._active_profile = math._active_profile = lambda: profile[0]
        entries = [shelf._BookshelfEntry('Neuroscience Exploring the Brain' if i <= 2 else f'Independent volume {i}', i, 'PDF') for i in range(1, 121)]
        original = shelf._bookshelf_duplicate_matches
        analyzing = [False]
        def duplicates(values):
            assert analyzing[0], 'duplicate analysis must not run while constructing widgets'
            return original(values)
        shelf._bookshelf_duplicate_matches = duplicates
        dialog = shelf._DocumentBookshelfDialog(addon_dir='/tmp/unused', entries=entries)
        assert dialog._list.count() < len(entries), 'grid creation must yield between batches'
        assert jobs, 'duplicate analysis must be dispatched even without PDF filenames'
        work, done = jobs.pop(0)
        analyzing[0] = True
        result = work()
        analyzing[0] = False
        future = Future(); future.set_result(result)
        done(future)
        assert dialog._duplicate_matches[1] == (entries[1],)
        assert dialog._duplicate_matches[2] == (entries[0],)
        chosen = dialog._list.item(5)
        dialog._list.setCurrentItem(chosen)
        for _ in range(10):
            app.processEvents()
            if dialog._list.count() == len(entries): break
        assert dialog._list.count() == len(entries)
        assert dialog._list.currentItem() is chosen
        dialog._search.setText('Neuroscience')
        assert dialog._list.count() == 2
        dialog.reject()
        done(future)  # a late callback must be harmless

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            cover = QPixmap(1200, 1800); cover.fill()
            assert cover.save(str(Path(directory) / 'cover.png'))
            mw.col.media.dir = lambda: directory
            jobs.clear()
            cover_entry = shelf._BookshelfEntry('Cover', 501, 'EPUB', cover_filename='cover.png')
            cover_dialog = shelf._DocumentBookshelfDialog(addon_dir='/tmp/unused', entries=[cover_entry])
            cover_dialog.show()
            jobs.clear()
            cover_dialog._load_next_thumbnail(cover_dialog._thumbnail_generation)
            assert len(jobs) == 1
            work, done = jobs.pop()
            thumbnail = work()
            assert not thumbnail.isNull() and thumbnail.width() <= shelf._PREVIEW_WIDTH
            future = Future(); future.set_result(thumbnail); done(future)
            assert ('EPUB', 501) in cover_dialog._thumbnail_cache
            cover_dialog.reject()
            done(future)
        jobs.clear()

        image = QPixmap(600, 200); image.fill()
        math.is_ready = lambda: True
        encoded = []
        original_encode = math._encode_math_image
        def encode(image):
            encoded.append(True)
            return original_encode(image)
        math._encode_math_image = encode
        recognized = []
        math.recognize_snapshot = lambda data, **kw: recognized.append(data) or 'x^2'
        scanner = math.SnapshotMathDialog(None, image, is_current=lambda: True)
        scanner._start_scan()
        assert not encoded and scanner._running, 'PNG encoding must wait for the worker'
        work, done = jobs.pop()
        future = Future(); future.set_result(work()); done(future)
        assert encoded == [True] and recognized[0].startswith(b'\\x89PNG')
        assert scanner._recognized and scanner._result.toPlainText() == 'x^2'
        scanner._start_scan()
        work, done = jobs.pop()
        scanner.reject()
        future = Future(); future.set_result(work()); done(future)
        assert not scanner._recognized and not scanner._result.toPlainText()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_load_avoids_a_modal_progress_window():
    import ast
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / '__init__.py').read_text())
    opening = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == '_open_document_bookshelf')
    assert not any(isinstance(node, ast.Attribute) and node.attr == 'with_progress'
                   for node in ast.walk(opening))
