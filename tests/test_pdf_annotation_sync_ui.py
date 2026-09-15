"""Deterministic background queue and stale reader callback contracts."""
from concurrent.futures import Future

import pytest

import pdf_annotation_sync as ui


class Runner:
    def __init__(self):
        self.tasks = []

    def submit(self, work, done):
        self.tasks.append((work, done))

    def complete(self):
        work, done = self.tasks.pop(0)
        future = Future()
        try:
            future.set_result(work())
        except Exception as error:
            future.set_exception(error)
        done(future)


def test_annotation_edits_during_sync_are_coalesced_and_finish_after_the_latest_pass():
    runner = Runner()
    calls, results = [], []
    queue = ui.PdfAnnotationSyncQueue(runner.submit, lambda *args, **kw: calls.append((args, kw)) or {'retry_needed': False})
    queue.request('/addon', 'Profile A', 42, 'book.pdf', callback=lambda *value: results.append(value))
    queue.request('/addon', 'Profile A', 42, 'book.pdf', source_path='/original.pdf')
    queue.request('/addon', 'Profile A', 42, 'book.pdf')
    assert len(runner.tasks) == 1
    runner.complete()
    assert results == []
    assert len(runner.tasks) == 1
    runner.complete()
    assert len(calls) == 2
    assert calls[1][0] == ('/addon', 'Profile A', 42, 'book.pdf')
    assert calls[1][1]['source_path'] == '/original.pdf'
    assert len(results) == 1 and results[0][1] is None


def test_repeated_auto_sync_requests_deliver_only_the_latest_reader_refresh():
    runner = Runner()
    results = []
    queue = ui.PdfAnnotationSyncQueue(runner.submit, lambda *args, **kw: {'retry_needed': False})
    for value in ['old', 'middle', 'latest']:
        queue.request('/addon', 'Profile', 42, 'book.pdf', callback_key='reader-refresh',
                      callback=lambda *args, value=value: results.append(value))
    runner.complete()
    runner.complete()
    assert results == ['latest']


def test_profile_teardown_cancels_old_worker_and_discards_its_callbacks():
    runner = Runner()
    results = []
    def sync(*args, cancel, **kw):
        assert cancel()
        return {}
    queue = ui.PdfAnnotationSyncQueue(runner.submit, sync)
    queue.request('/addon', 'Old profile', 42, 'book.pdf', callback=lambda *args: results.append(args))
    queue.reset()
    runner.complete()
    assert results == []


def test_unchanged_request_retries_a_newer_sqlite_edit_before_delivering_success():
    runner = Runner()
    count, results = [], []
    queue = ui.PdfAnnotationSyncQueue(runner.submit, lambda *args, **kw: {'retry_needed': not count.append(1) and len(count) == 1})
    queue.request('/addon', 'Profile', 42, 'book.pdf', callback=lambda *args: results.append(args))
    runner.complete()
    assert results == []
    runner.complete()
    assert len(results) == 1 and len(count) == 2


def test_sync_failure_is_delivered_without_an_infinite_retry_loop():
    runner = Runner()
    results = []
    def fail(*args, **kw):
        raise OSError('read-only file')
    queue = ui.PdfAnnotationSyncQueue(runner.submit, fail)
    queue.request('/addon', 'Profile', 42, 'book.pdf', callback=lambda *args: results.append(args))
    runner.complete()
    assert isinstance(results[0][1], OSError)
    assert not runner.tasks
