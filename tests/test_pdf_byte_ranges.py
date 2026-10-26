"""Bounded, read-only PDF chunks and captured-reader replies."""
import base64
from concurrent.futures import Future
import os
from types import SimpleNamespace

import pytest

from pdf_byte_ranges import PdfByteRangeSource, PDF_RANGE_CHUNK_SIZE
from pdf_range_bridge import PdfRangeBridge
import paths


def source_file(tmp_path, profile='A', card_id=42):
    target = paths.get_pdf_dir(str(tmp_path), profile) / 'book.pdf'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'%PDF-' + bytes(range(256)) * 4096)
    return target, PdfByteRangeSource(str(tmp_path), profile, card_id, target)


def test_pdf_open_describes_the_file_without_reading_its_contents(tmp_path, monkeypatch):
    target, _ = source_file(tmp_path)
    monkeypatch.setattr(type(target), 'read_bytes', lambda *_: pytest.fail('no whole-file reads'))
    source = PdfByteRangeSource(str(tmp_path), 'A', 42, target)
    assert source.descriptor['length'] == target.stat().st_size
    assert source.descriptor['chunkSize'] == PDF_RANGE_CHUNK_SIZE
    assert source.descriptor['cardId'] == 42
    assert 'path' not in source.descriptor
    assert source.read(3, 11) == b'F-' + bytes(range(6))


def test_pdf_ranges_read_unchanged_file_when_windows_stat_and_fstat_ctimes_differ(tmp_path, monkeypatch):
    target, source = source_file(tmp_path)
    contents = target.read_bytes()
    real_fstat = os.fstat

    def windows_fstat(descriptor):
        info = real_fstat(descriptor)
        fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        # Reproduce the reported Windows path/handle timestamp discrepancy.
        fields['st_ctime_ns'] -= 9_472_317_500
        fields['st_ctime'] = fields['st_ctime_ns'] / 1_000_000_000
        return SimpleNamespace(**fields)

    monkeypatch.setattr(os, 'fstat', windows_fstat)

    assert source.read(0, 5) == b'%PDF-'
    assert source.read(len(contents) - 12, len(contents)) == contents[-12:]


@pytest.mark.parametrize(('change', 'during_read'), [
    pytest.param('size', False, id='size-before-read'),
    pytest.param('size', True, id='size-during-read'),
    pytest.param('mtime', False, id='mtime-before-read'),
    pytest.param('mtime', True, id='mtime-during-read'),
    pytest.param('replacement', False, id='same-size-and-mtime-replacement'),
])
def test_pdf_ranges_reject_modified_or_replaced_snapshots(tmp_path, monkeypatch, change, during_read):
    target, source = source_file(tmp_path)
    original = target.stat()

    def change_snapshot():
        if change == 'size':
            with target.open('ab') as stream:
                stream.write(b'changed')
            os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
        elif change == 'mtime':
            with target.open('r+b') as stream:
                stream.write(b'%PDF-modified')
            os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns + 2_000_000_000))
        else:
            replacement = target.with_name('replacement.pdf')
            replacement.write_bytes(b'x' * original.st_size)
            os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
            replacement.replace(target)

    if during_read:
        real_read = os.read

        def read_then_change(descriptor, length):
            data = real_read(descriptor, length)
            change_snapshot()
            return data

        monkeypatch.setattr(os, 'read', read_then_change)
    else:
        change_snapshot()

    with pytest.raises(OSError, match='PDF snapshot changed'):
        source.read(0, 5)


@pytest.mark.parametrize(('begin', 'end'), [(-1, 5), (1, 1), (4, 3), (True, 6),
    (0, PDF_RANGE_CHUNK_SIZE + 1), (0, 2_000_000), ('0', 5)])
def test_pdf_ranges_reject_invalid_and_oversized_reads(tmp_path, begin, end):
    _, source = source_file(tmp_path)
    with pytest.raises((ValueError, OSError)):
        source.read(begin, end)


def test_changed_files_and_symlinks_cannot_supply_bytes_for_an_old_document(tmp_path):
    target, source = source_file(tmp_path)
    replacement = target.with_name('replacement.pdf')
    replacement.write_bytes(b'%PDF-different')
    replacement.replace(target)
    with pytest.raises(OSError):
        source.read(0, 5)
    target.unlink()
    target.symlink_to(tmp_path / 'outside.pdf')
    with pytest.raises((ValueError, OSError)):
        PdfByteRangeSource(str(tmp_path), 'A', 42, target)


def test_pdf_ranges_allow_only_the_current_profile_and_its_exact_reader_copy(tmp_path):
    target, _ = source_file(tmp_path)
    with pytest.raises((ValueError, OSError)):
        PdfByteRangeSource(str(tmp_path), 'B', 42, target)
    reader = paths.get_pdf_annotation_reader_path(str(tmp_path), 'A', 42)
    reader.parent.mkdir(parents=True)
    reader.write_bytes(b'%PDF-reader')
    assert PdfByteRangeSource(str(tmp_path), 'A', 42, reader).read(0, 5) == b'%PDF-'
    with pytest.raises((ValueError, OSError)):
        PdfByteRangeSource(str(tmp_path), 'A', 43, reader)


def test_symlinked_storage_directory_cannot_redirect_a_profile_to_another_file_tree(tmp_path):
    target, _ = source_file(tmp_path)
    original = target.parent
    moved = original.with_name('moved')
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        PdfByteRangeSource(str(tmp_path), 'A', 42, original / target.name)


def test_changed_file_errors_do_not_expose_paths_or_partial_bytes_to_the_reader(tmp_path):
    import json
    target, _ = source_file(tmp_path)
    jobs, replies = [], []
    bridge = PdfRangeBridge(lambda *job: jobs.append(job), replies.append, lambda *_: True)
    metadata = bridge.open(str(tmp_path), 'A', 42, target)
    bridge.handle('incremento_pdf_range:' + json.dumps({**metadata, 'requestId': 1, 'begin': 0, 'end': 5}))
    target.unlink()
    work, done = jobs[0]
    future = Future()
    try:
        work()
    except OSError as error:
        future.set_exception(error)
    done(future)
    assert replies == [{'token': metadata['token'], 'requestId': 1, 'begin': 0, 'error': True}]


def test_range_bridge_runs_io_off_thread_and_discards_late_profile_and_document_replies(tmp_path):
    import json
    target, _ = source_file(tmp_path)
    jobs, replies = [], []
    active = ['A']
    bridge = PdfRangeBridge(lambda work, done: jobs.append((work, done)), replies.append,
        lambda profile, card: active[0] == profile and card == 42)
    metadata = bridge.open(str(tmp_path), 'A', 42, target)
    request = 'incremento_pdf_range:' + json.dumps({**metadata,
        'requestId': 1, 'begin': 0, 'end': 5})
    assert bridge.handle(request)
    assert len(jobs) == 1 and replies == []
    work, done = jobs.pop()
    result = Future()
    result.set_result(work())
    done(result)
    assert base64.b64decode(replies[0]['data']) == b'%PDF-'
    assert replies[0]['token'] == metadata['token']
    bridge.handle(request)
    work, done = jobs.pop()
    result = Future()
    result.set_result(work())
    bridge.open(str(tmp_path), 'A', 42, target)
    done(result)
    assert len(replies) == 1
    assert bridge.handle(request) and jobs == [], 'retired tokens must not enqueue disk reads'
    current = bridge.open(str(tmp_path), 'A', 42, target)
    bridge.handle('incremento_pdf_range:' + json.dumps({**current, 'requestId': 2, 'begin': 0, 'end': 5}))
    work, done = jobs.pop()
    result = Future()
    result.set_result(work())
    active[0] = 'B'
    done(result)
    assert len(replies) == 1


def test_range_bridge_bounds_concurrency_and_never_accepts_a_path_from_javascript(tmp_path):
    import json
    target, _ = source_file(tmp_path)
    jobs, replies = [], []
    bridge = PdfRangeBridge(lambda *job: jobs.append(job), replies.append, lambda *_: True)
    metadata = bridge.open(str(tmp_path), 'A', 42, target)
    for request_id in range(20):
        bridge.handle('incremento_pdf_range:' + json.dumps({**metadata, 'requestId': request_id,
            'begin': 0, 'end': 5, 'path': '/etc/passwd'}))
    assert len(jobs) == 4
    for work, done in jobs:
        result = Future()
        result.set_result(work())
        done(result)
    assert all(base64.b64decode(reply['data']) == b'%PDF-' for reply in replies if 'data' in reply)
