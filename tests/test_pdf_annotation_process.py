"""The native annotation worker owns its interpreter and captured profile."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

import pdf_annotation_process as worker
from pdf_annotations import PdfAnnotationSyncError


def make_pdf(root):
    target = root / 'user_files' / 'Synthetic' / 'pdfs' / 'book.pdf'
    target.parent.mkdir(parents=True)
    result = subprocess.run([sys.executable, '-I', '-c',
        'import pymupdf,sys; d=pymupdf.open(); p=d.new_page(); '
        'p.insert_text((40,40),"Synthetic passage"); d.save(sys.argv[1]); d.close()', str(target)],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return target


def test_isolated_sync_creates_a_reader_copy_without_importing_native_work_into_the_caller(tmp_path, monkeypatch):
    import pdf_annotations
    make_pdf(tmp_path)
    monkeypatch.setattr(worker, '_python', lambda: sys.executable)
    monkeypatch.setattr(pdf_annotations, 'sync_pdf_annotations',
        lambda *args, **kwargs: pytest.fail('native processing must run in a child interpreter'))
    result = worker.sync_pdf_annotations_in_process(str(tmp_path), 'Synthetic', 42, 'book.pdf')
    assert Path(result['reader_path']).is_file()
    assert result['reader_path'] == str(tmp_path / 'user_files' / 'Synthetic' / 'pdf_annotations' / '42' / 'reader.pdf')
    assert result['changed'] is False and result['retry_needed'] is False
    assert result['reader_changed'] is True
    assert not list(tmp_path.rglob('.incremento-worker-*'))


def test_cancelled_job_never_launches_or_mutates_the_pdf(tmp_path, monkeypatch):
    target = make_pdf(tmp_path)
    before = target.read_bytes()
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *args, **kw: pytest.fail('already cancelled'))
    with pytest.raises(PdfAnnotationSyncError, match='cancelled'):
        worker.sync_pdf_annotations_in_process(str(tmp_path), 'Synthetic', 42, 'book.pdf', cancel=lambda: True)
    assert target.read_bytes() == before


def test_worker_result_rejects_foreign_paths_and_raw_error_messages(tmp_path):
    expected = tmp_path / 'reader.pdf'
    payload = {'ok': True, 'result': {'reader_path': '/etc/passwd', 'changed': False,
        'appearance_changed': False, 'retry_needed': False, 'conflicts': 0, 'imported': 0}}
    with pytest.raises(PdfAnnotationSyncError):
        worker._decode_result(json.dumps(payload).encode(), expected)
    with pytest.raises(PdfAnnotationSyncError, match='write_failed'):
        worker._decode_result(json.dumps({'ok': False, 'error': 'private path and contents'}).encode(), expected)


def test_annotation_output_symlink_is_rejected_before_allocating_any_files(tmp_path, monkeypatch):
    make_pdf(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    parent = tmp_path / 'user_files' / 'Synthetic' / 'pdf_annotations'
    parent.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(worker, '_python', lambda: sys.executable)
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *args, **kw: pytest.fail('unsafe output'))
    with pytest.raises(PdfAnnotationSyncError, match='unsafe_path'):
        worker.sync_pdf_annotations_in_process(str(tmp_path), 'Synthetic', 42, 'book.pdf')
    assert list(outside.iterdir()) == []
    assert not list(tmp_path.rglob('.incremento-worker-*'))


def test_cancellation_signals_the_child_and_cleans_only_its_owned_temporary_files(tmp_path, monkeypatch):
    target = make_pdf(tmp_path)
    before = target.read_bytes()
    unrelated = target.parent / '.incremento-worker-unrelated.pdf'
    unrelated.write_bytes(b'preserve')
    calls = []
    class Child:
        returncode = None
        def communicate(self, data, timeout):
            if data:
                self.request = json.loads(data)
                calls.append('running')
                raise subprocess.TimeoutExpired('worker', timeout)
            assert Path(self.request['cancel_path']).exists()
            self.returncode = 0
        def poll(self):
            return self.returncode
    monkeypatch.setattr(worker, '_python', lambda: sys.executable)
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *args, **kw: Child())
    with pytest.raises(PdfAnnotationSyncError, match='cancelled'):
        worker.sync_pdf_annotations_in_process(str(tmp_path), 'Synthetic', 42, 'book.pdf', cancel=lambda: bool(calls))
    assert list(tmp_path.rglob('.incremento-worker-*')) == [unrelated]
    assert target.read_bytes() == before


def test_a_worker_deadline_terminates_the_child_and_preserves_the_original(tmp_path, monkeypatch):
    target = make_pdf(tmp_path)
    before = target.read_bytes()
    stopped = []
    class Child:
        returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            stopped.append(True)
            self.returncode = -15
        def wait(self, timeout):
            return self.returncode
    monkeypatch.setattr(worker, '_python', lambda: sys.executable)
    monkeypatch.setattr(worker, 'MAX_SYNC_PROCESSING_SECONDS', -10)
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *args, **kw: Child())
    with pytest.raises(PdfAnnotationSyncError, match='limits'):
        worker.sync_pdf_annotations_in_process(str(tmp_path), 'Synthetic', 42, 'book.pdf')
    assert stopped == [True]
    assert target.read_bytes() == before
    assert not list(tmp_path.rglob('.incremento-worker-*'))


def test_profile_reset_cannot_be_undone_by_a_late_worker_fingerprint_result(tmp_path, monkeypatch):
    make_pdf(tmp_path)
    class Child:
        returncode = 0
        def communicate(self, data, timeout):
            request = json.loads(data)
            result = {'reader_path': str(tmp_path / 'user_files' / 'Synthetic' / 'pdf_annotations' / '42' / 'reader.pdf'),
                'source_path': '', 'changed': False, 'reader_changed': False, 'appearance_changed': False,
                'retry_needed': False, 'conflicts': 0, 'imported': 0}
            Path(request['output']).write_text(json.dumps({'ok': True, 'result': result,
                'fingerprints': {'a' * 64: 'b' * 64}}))
            worker.clear_annotation_process_cache()
        def poll(self):
            return 0
    monkeypatch.setattr(worker, '_python', lambda: sys.executable)
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *args, **kw: Child())
    worker.sync_pdf_annotations_in_process(str(tmp_path), 'Synthetic', 42, 'book.pdf')
    assert not worker._cache
