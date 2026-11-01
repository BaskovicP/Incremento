"""Bookshelf startup budgets through real Qt, without touching a live profile."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest


SETUP = """
import os, sys, types
from concurrent.futures import Future
from aqt.qt import QApplication, QPushButton
package = types.ModuleType('incremento')
package.__path__ = [os.getcwd()]
sys.modules['incremento'] = package
from incremento.frontend import pdf_bookshelf as shelf
app = QApplication([])
pending = []
profile = ['Captured']
shelf._active_profile = lambda: profile[0]
shelf.configured_priority_lower_is_more_important = lambda: True
shelf._document_lists.get_document_lists = lambda *args: []
shelf.tooltip = lambda *args, **kwargs: None
def run(worker, done, *, uses_collection):
    assert uses_collection is False
    pending.append((worker, done))
shelf.mw = types.SimpleNamespace(
    col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: '')),
    taskman=types.SimpleNamespace(run_in_background=run),
)
"""


def run_scenario(tmp_path, body):
    result = subprocess.run(
        [sys.executable, "-c", dedent(SETUP) + dedent(body), str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("completion", ["current", "closed", "profile"])
def test_metadata_and_attachment_scans_wait_for_advanced_filters(tmp_path, completion):
    run_scenario(tmp_path, """
        entries = [shelf._BookshelfEntry('Shared title', cid, 'PDF') for cid in (1, 2)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=sys.argv[1], entries=entries)
        assert pending == [], 'Opening the shelf must not scan every PDF'
        scanned = []
        def metadata(snapshot, *, profile, cancelled):
            scanned.append((snapshot, profile))
            return {1: 'Embedded title', 2: 'Embedded title'}
        shelf._load_pdf_metadata_titles = metadata
        more = next(button for button in dialog.findChildren(QPushButton)
                    if button.text() == shelf.t('reader_library_more_filters'))
        more.click()
        assert len(pending) == 1 and scanned == []
        more.click()
        more.click()
        assert len(pending) == 1, 'Reopening advanced filters must reuse the scan'
        future = Future()
        future.set_result(pending[0][0]())
        assert scanned == [(entries, 'Captured')]
        if 'COMPLETION' == 'closed':
            dialog.reject()
        elif 'COMPLETION' == 'profile':
            profile[0] = 'Other'
        pending[0][1](future)
        if 'COMPLETION' != 'current':
            assert dialog._entries == entries and not dialog._duplicate_matches
        else:
            assert dialog._duplicates_only_cb.isEnabled()
            assert dialog._entries[0].metadata_title == 'Embedded title'
            # Metadata now belongs to the click-open details pane.
            assert 'Embedded title' not in dialog._list.item(0).toolTip()
            dialog._details_button.click()
            assert 'Embedded title' in dialog._book_kind.text()
            # Badge counts still wait until duplicate mode is selected.
            import aqt.operations
            operations = []
            attachment_requests = []
            def counts(addon_dir, profile, candidates, *, col):
                attachment_requests.append((profile, [e.card_id for e in candidates], col))
                return {1: 3, 2: 0}
            shelf._bookshelf_attachment_counts = counts
            class Query:
                def __init__(self, **kwargs): operations.append(kwargs)
                def failure(self, callback): return self
                def run_in_background(self): pass
            aqt.operations.QueryOp = Query
            assert operations == []
            dialog._duplicates_only_cb.setChecked(True)
            assert len(operations) == 1 and attachment_requests == []
            operations[0]['success'](operations[0]['op'](shelf.mw.col))
            assert attachment_requests == [('Captured', [1, 2], shelf.mw.col)]
            assert dialog._list.item(0).data(shelf._ATTACHMENT_BADGE_ROLE) == 3
            assert dialog._list.item(1).data(shelf._ATTACHMENT_BADGE_ROLE) == 0
        dialog.reject()
    """.replace("COMPLETION", completion))


def test_first_cover_batch_is_scheduled_before_the_entire_grid_is_populated(tmp_path):
    run_scenario(tmp_path, """
        from aqt.qt import QImage, QColor
        cover = QImage(10, 20, QImage.Format.Format_RGB32)
        cover.fill(QColor('red'))
        assert cover.save(os.path.join(sys.argv[1], 'cover.png'))
        shelf.mw.col.media.dir = lambda: sys.argv[1]
        # Hold the zero-delay tile batches while exercising the thumbnail timer.
        deferred = []
        shelf.QTimer.singleShot = lambda interval, callback: deferred.append(callback)
        entries = [shelf._BookshelfEntry(f'Book {cid:03}', cid, 'EPUB', cover_filename='cover.png')
                   for cid in range(120)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=sys.argv[1], entries=entries)
        assert dialog._list.count() == 40  # Later batches yield to the event loop.
        immediate = next((callback for callback in deferred if callback == dialog._prioritize_thumbnails), None)
        assert immediate is not None, 'Initial covers must bypass the scroll debounce delay'
        placeholder = dialog._list.item(0).icon().cacheKey()
        dialog.show()
        immediate()
        assert len(pending) == 1
        future = Future()
        future.set_result(pending[0][0]())
        pending[0][1](future)
        assert dialog._list.item(0).icon().cacheKey() != placeholder
        assert dialog._list.count() == 40
        dialog.reject()
    """)


def test_large_shelf_populates_with_fewer_repaints_and_keeps_a_selection_made_during_loading(tmp_path):
    run_scenario(tmp_path, """
        from collections import deque
        from aqt.qt import QItemSelectionModel
        deferred = deque()
        shelf.QTimer.singleShot = lambda interval, callback: deferred.append(callback)
        entries = [shelf._BookshelfEntry(f'Book {cid:04}', cid, 'EPUB') for cid in range(1000)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=sys.argv[1], entries=entries,
                                               last_opened_card_id=999)
        assert dialog._list.count() == 40
        dialog._list.setCurrentRow(1, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        batches = []
        while deferred:
            before = dialog._list.count()
            deferred.popleft()()
            added = dialog._list.count() - before
            if added:
                batches.append(added)
        # At most five further bounded batches for a thousand-document shelf.
        assert len(batches) <= 5, batches
        assert max(batches) <= 200
        assert [dialog._list.item(i).data(shelf.Qt.ItemDataRole.UserRole).card_id
                for i in range(dialog._list.count())] == list(range(1000))
        assert dialog.selected_card_id == 1
        assert [e.card_id for e in dialog._selected_library_entries()] == [1]
        dialog.reject()
    """)


def test_restored_book_gets_an_immediate_cover_request_after_the_grid_finishes(tmp_path):
    run_scenario(tmp_path, """
        from collections import deque
        deferred, requests = deque(), []
        shelf.QTimer.singleShot = lambda interval, callback: deferred.append(callback)
        shelf._DocumentBookshelfDialog._prioritize_thumbnails = lambda self: requests.append(self.selected_card_id)
        entries = [shelf._BookshelfEntry(f'Book {cid:04}', cid, 'EPUB') for cid in range(1000)]
        dialog = shelf._DocumentBookshelfDialog(addon_dir=sys.argv[1], entries=entries,
                                               last_opened_card_id=999)
        while deferred:
            deferred.popleft()()
        assert dialog.selected_card_id == 999
        assert requests[-1] == 999, 'Restored covers must bypass the scroll debounce too'
        dialog.reject()
    """)


COVER_SETUP = """
from collections import deque
from pathlib import Path
from aqt.qt import QColor, QImage
from incremento.backend import pdf_manager
root = Path(sys.argv[1])
media = root / 'media'
media.mkdir()
shelf.mw.col.media.dir = lambda: str(media)
pdf_manager.get_pdf_dir = lambda selected: str(root / selected / 'pdfs')
for name in ('Captured', 'Other'):
    (root / name / 'pdfs').mkdir(parents=True)
deferred, reads = deque(), []
shelf.QTimer.singleShot = lambda interval, callback: deferred.append(callback)
def save_cover(path, color):
    image = QImage(40, 60, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path))
reader = shelf.QImageReader
def read(path):
    reads.append(path)
    return reader(path)
shelf.QImageReader = read
save_cover(media / 'cover.bmp', 'red')
entry = shelf._BookshelfEntry('Book', 1, 'EPUB', cover_filename='cover.bmp')
def create(entry=entry):
    return shelf._DocumentBookshelfDialog(addon_dir=str(root), entries=[entry])
def drain(dialog):
    for _ in range(100):
        if deferred:
            deferred.popleft()()
        elif pending:
            worker, done = pending.pop(0)
            future = Future()
            future.set_result(worker())
            done(future)
        else:
            dialog._thumbnail_timer.stop()
            return
    raise AssertionError('Cover loading did not settle')
def icon_key(dialog):
    return dialog._list.item(0).icon().cacheKey()
def color(dialog):
    return dialog._list.item(0).icon().pixmap(40, 60).toImage().pixelColor(20, 30).name()
"""


def run_cover_scenario(tmp_path, body):
    run_scenario(tmp_path, COVER_SETUP + dedent(body))


@pytest.mark.parametrize("kind", ["EPUB", "PDF", "legacy_pdf"])
def test_reopening_reuses_decoded_covers_before_showing_the_grid(tmp_path, kind):
    run_cover_scenario(tmp_path, """
        from dataclasses import replace
        if 'KIND' == 'legacy_pdf':
            source = root / 'Captured' / 'pdfs' / 'legacy.pdf'
            source.write_bytes(b'%PDF-synthetic decoder fixture')
            def render(path):
                reads.append(path)
                return QImage(str(media / 'cover.bmp'))
            shelf._render_pdf_first_page = render
            entry = replace(entry, kind='PDF', cover_filename='', source_filename='legacy.pdf')
        else:
            entry = replace(entry, kind='KIND')
        first = create(entry)
        first.show()
        drain(first)
        assert len(reads) == 1 and color(first) == '#ff0000'
        key = icon_key(first)
        first.reject()
        assert first.selected_card_id == entry.card_id  # The opener still needs its selection.
        assert first._list.item(0).icon().isNull(), 'Closed dialogs must release their image references'
        assert first._book_cover.pixmap().isNull()

        # A new dialog/card for the same source should use its decoded image.
        reopened = create(replace(entry, card_id=99))
        assert icon_key(reopened) == key, 'Warm covers must appear before the first decode callback'
        reopened.show()
        drain(reopened)
        assert len(reads) == 1 and pending == []
        assert reopened._thumbnail_cache.bytes_used <= 24 * 1024 * 1024
        reopened.reject()
        unshown = create(entry)
        assert not unshown._list.item(0).icon().isNull()
        unshown.reject()
        assert unshown._list.item(0).icon().isNull()
    """.replace('KIND', kind))


@pytest.mark.parametrize("change", ["replace", "missing", "symlink", "traversal", "profile", "media_dir"])
def test_cover_cache_revalidates_files_paths_and_profile_before_reuse(tmp_path, change):
    run_cover_scenario(tmp_path, """
        from dataclasses import replace
        first = create()
        first.show()
        drain(first)
        key = icon_key(first)
        first.reject()
        if 'CHANGE' == 'replace':
            before = (media / 'cover.bmp').stat()
            replacement = media / 'replacement.bmp'
            save_cover(replacement, 'blue')
            assert replacement.stat().st_size == before.st_size
            os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
            replacement.replace(media / 'cover.bmp')
        elif 'CHANGE' == 'missing':
            (media / 'cover.bmp').unlink()
        elif 'CHANGE' in ('symlink', 'traversal'):
            outside = root / 'outside.bmp'
            save_cover(outside, 'blue')
            if 'CHANGE' == 'symlink':
                (media / 'cover.bmp').unlink()
                (media / 'cover.bmp').symlink_to(outside)
            else:
                entry = replace(entry, cover_filename='../outside.bmp')
        elif 'CHANGE' == 'profile':
            profile[0] = 'Other'
        elif 'CHANGE' == 'media_dir':
            other = root / 'other_media'
            other.mkdir()
            save_cover(other / 'cover.bmp', 'blue')
            shelf.mw.col.media.dir = lambda: str(other)
        reopened = create(entry)
        assert icon_key(reopened) != key
        reopened.show()
        drain(reopened)
        if 'CHANGE' in ('missing', 'symlink', 'traversal'):
            assert len(reads) == 1 and icon_key(reopened) != key
        else:
            assert len(reads) == 2
            assert color(reopened) == ('#ff0000' if 'CHANGE' == 'profile' else '#0000ff')
        reopened.reject()
    """.replace('CHANGE', change))


def test_shared_cover_cache_evicts_old_images_within_its_byte_budget(tmp_path):
    run_cover_scenario(tmp_path, """
        from dataclasses import replace
        first = create()
        first._thumbnail_cache.max_bytes = 160 * 320 * 4  # One conservatively sized thumbnail.
        first.show()
        drain(first)
        first_key = icon_key(first)
        first.reject()
        save_cover(media / 'second.bmp', 'blue')
        second = create(replace(entry, cover_filename='second.bmp'))
        second.show()
        drain(second)
        assert second._thumbnail_cache.bytes_used <= second._thumbnail_cache.max_bytes
        second.reject()
        third = create()
        assert icon_key(third) != first_key  # Evicted from the one-image RAM cache.
        third.show()
        drain(third)
        # RAM eviction now falls back to disk instead of decoding the source again.
        assert reads == [str(media / name) for name in ('cover.bmp', 'second.bmp')]
        assert third._thumbnail_cache.bytes_used <= third._thumbnail_cache.max_bytes
        assert color(third) == '#ff0000'
        third.reject()
    """)


@pytest.mark.parametrize("completion", ["closed", "profile", "replaced"])
def test_late_cover_decode_cannot_fill_the_cache_with_a_stale_image(tmp_path, completion):
    run_cover_scenario(tmp_path, """
        first = create()
        first.show()
        while deferred:
            deferred.popleft()()
        worker, done = pending.pop()
        future = Future()
        future.set_result(worker())
        if 'COMPLETION' == 'closed':
            first.reject()
        elif 'COMPLETION' == 'profile':
            profile[0] = 'Other'
        else:
            save_cover(media / 'cover.bmp', 'blue')
        done(future)
        drain(first)
        if 'COMPLETION' == 'replaced':
            assert color(first) == '#0000ff'
        first.reject()
        profile[0] = 'Captured'
        if 'COMPLETION' != 'replaced':
            assert shelf._THUMBNAIL_CACHE.bytes_used == 0  # Stale callbacks still cannot warm RAM.
        reopened = create()
        reopened.show()
        drain(reopened)
        # Valid disk pixels were committed before closing/switching; a replaced
        # source gets a different key and must be decoded again.
        assert len(reads) == (2 if 'COMPLETION' == 'replaced' else 1)
        assert color(reopened) == ('#0000ff' if 'COMPLETION' == 'replaced' else '#ff0000')
        reopened.reject()
    """.replace('COMPLETION', completion))


@pytest.mark.parametrize("change", ["same", "replace", "after_prefetch", "missing_after_prefetch", "missing", "symlink", "profile", "renderer", "cover_field", "corrupt", "legacy_pdf", "legacy_pdf_changed"])
def test_first_open_after_process_restart_loads_valid_disk_covers_and_regenerates_changes(tmp_path, change):
    setup = COVER_SETUP.replace("media.mkdir()", "media.mkdir(exist_ok=True)").replace(
        ".mkdir(parents=True)", ".mkdir(parents=True, exist_ok=True)")
    legacy = """
        from dataclasses import replace
        entry = replace(entry, kind='PDF', cover_filename='', source_filename='legacy.pdf')
        def render(path):
            reads.append(path)
            return QImage(str(media / 'cover.bmp'))
        shelf._render_pdf_first_page = render
    """ if change.startswith("legacy_pdf") else ""
    run_scenario(tmp_path, setup + dedent(legacy) + dedent("""
        (root / 'Captured' / 'pdfs' / 'legacy.pdf').write_bytes(b'%PDF-synthetic decoder fixture')
        first = create(entry)
        first.show()
        drain(first)
        assert color(first) == '#ff0000'
        first.reject()
    """))
    # A new Python/Qt process has no shared memory cache or decoder state.
    setup = setup.replace("save_cover(media / 'cover.bmp', 'red')", "")
    run_scenario(tmp_path, setup + dedent(legacy) + dedent("""
        from dataclasses import replace
        if 'CHANGE' == 'replace':
            path = media / 'cover.bmp'
            before = path.stat()
            replacement = media / 'replacement.bmp'
            save_cover(replacement, 'blue')
            assert replacement.stat().st_size == before.st_size
            os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
            replacement.replace(path)
        elif 'CHANGE' == 'missing':
            (media / 'cover.bmp').unlink()
        elif 'CHANGE' == 'symlink':
            save_cover(root / 'outside.bmp', 'blue')
            (media / 'cover.bmp').unlink()
            (media / 'cover.bmp').symlink_to(root / 'outside.bmp')
        elif 'CHANGE' == 'profile':
            profile[0] = 'Other'
        elif 'CHANGE' == 'renderer':
            shelf._COVER_RENDER_VERSION += 1
        elif 'CHANGE' == 'cover_field':
            save_cover(media / 'new.bmp', 'blue')
            entry = replace(entry, cover_filename='new.bmp')
        elif 'CHANGE' == 'corrupt':
            for path in (root / 'user_files' / 'Captured' / 'bookshelf_cover_cache').glob('*.rgba'):
                path.write_bytes(b'broken cache')
        elif 'CHANGE' == 'legacy_pdf_changed':
            (root / 'Captured' / 'pdfs' / 'legacy.pdf').write_bytes(b'%PDF-updated document fixture')
            save_cover(media / 'cover.bmp', 'blue')
        shelf._load_bookshelf_entries = lambda *args, **kwargs: [entry]
        entries, counts, covers = shelf._load_bookshelf_snapshot(str(root), profile[0], collection=shelf.mw.col)
        if 'CHANGE' == 'after_prefetch':
            save_cover(media / 'cover.bmp', 'blue')
        elif 'CHANGE' == 'missing_after_prefetch':
            (media / 'cover.bmp').unlink()
        restarted = shelf._DocumentBookshelfDialog(addon_dir=str(root), entries=entries,
                                                   attachment_counts=counts, cached_covers=covers)
        if 'CHANGE' in ('same', 'legacy_pdf'):
            assert color(restarted) == '#ff0000', 'Disk covers must be ready before the first paint'
        if 'CHANGE' in ('missing', 'symlink', 'missing_after_prefetch'):
            assert shelf._THUMBNAIL_CACHE.bytes_used == 0, 'Unavailable sources must not seed stale pixels'
        restarted.show()
        drain(restarted)
        if 'CHANGE' in ('same', 'legacy_pdf', 'missing', 'symlink', 'missing_after_prefetch'):
            assert reads == [], 'Valid cached covers and unavailable sources must not be decoded'
        else:
            assert len(reads) == 1
            assert color(restarted) == ('#0000ff' if 'CHANGE' in ('replace', 'after_prefetch', 'cover_field', 'legacy_pdf_changed') else '#ff0000')
        restarted.reject()
    """.replace('CHANGE', change)))
