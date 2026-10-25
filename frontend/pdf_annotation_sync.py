"""Captured-profile, coalesced background PDF annotation writes.

The queue is used only on the UI thread. Its workers receive immutable file
identities and an Event; no Qt objects or Anki collections cross that boundary.
"""
from threading import Event

try:
    from ..backend import activity_log
    from ..backend.i18n import t
    from ..backend.pdf_annotations import PdfAnnotationSyncError
    from ..backend.pdf_annotation_process import sync_pdf_annotations_in_process, clear_annotation_process_cache
    from ..backend.pdf_reading_priority import wait_for_pdf_reading
except ImportError:
    import activity_log
    from i18n import t
    from pdf_annotations import PdfAnnotationSyncError
    from pdf_annotation_process import sync_pdf_annotations_in_process, clear_annotation_process_cache
    from pdf_reading_priority import wait_for_pdf_reading


def sync_error_text(error):
    reason = getattr(error, 'reason', 'write_failed')
    key = {
        'dependency': 'reader_pdf_sync_dependency',
        'document_changed': 'reader_pdf_sync_mismatch',
        'protected_pdf': 'reader_pdf_sync_protected',
        'password_protected': 'reader_pdf_sync_password',
        'digitally_signed': 'reader_pdf_sync_signed',
        'annotation_restricted': 'reader_pdf_sync_restricted',
        'file_changed': 'reader_pdf_sync_file_changed',
        'cancelled': 'reader_pdf_sync_cancelled',
        'limits': 'reader_pdf_sync_limits',
        'unsafe_path': 'reader_pdf_sync_unsafe_path',
    }.get(reason, 'reader_pdf_sync_write_failed')
    return t(key)


def defer_annotation_sync(callback):
    from aqt.qt import QTimer
    timer = QTimer()
    timer.setSingleShot(True)
    def run():
        try:
            callback()
        finally:
            timer.deleteLater()
    timer.timeout.connect(run)
    timer.start(400)
    return timer


def cancel_deferred_annotation_sync(timer):
    timer.stop()
    timer.deleteLater()


class PdfAnnotationSyncQueue:
    def __init__(self, submit, sync=sync_pdf_annotations_in_process, *, defer=None, cancel_deferred=None):
        self.submit = submit
        self.sync = sync
        self.jobs = {}
        self.auto_suppressed = set()
        self.retained = {}
        self.defer, self.cancel_deferred = defer, cancel_deferred

    def retain(self, key):
        """An additional open pane still owns this document's pending writes."""
        self.retained[key] = self.retained.get(key, 0) + 1

    def release(self, key):
        count = self.retained.get(key, 0)
        if count <= 1:
            self.retained.pop(key, None)
        else:
            self.retained[key] = count - 1

    def reset(self):
        self.retained.clear()
        self.cancel_except(None)
        self.auto_suppressed.clear()
        clear_annotation_process_cache()

    def cancel_except(self, keep_key):
        """Cancel jobs that no longer belong to the PDF visible in the reader."""
        for key, job in list(self.jobs.items()):
            if key == keep_key or key in self.retained:
                continue
            job['cancel'].set()
            if job.get('timer') is not None and self.cancel_deferred:
                self.cancel_deferred(job['timer'])
            activity_log.cancel_activity(job['activity'])
            self.jobs.pop(key, None)

    def request(self, addon_dir, profile, card_id, filename, *, source_path=None,
                callback=None, callback_key=None, automatic=False, dirty=True, immediate=False):
        key = (addon_dir, profile, int(card_id), filename)
        if automatic and key in self.auto_suppressed:
            return False
        if not automatic:
            self.auto_suppressed.discard(key)
        job = self.jobs.get(key)
        if job is not None:
            job['pending'] = job['pending'] or dirty or source_path is not None
            job['immediate'] = job['immediate'] or immediate
            if source_path is not None:
                job['source'] = source_path
            if callback:
                job['callbacks'][callback_key if callback_key is not None else callback] = callback
            if not job['running']:
                self._schedule(key, job)
            return True
        if len(self.jobs) >= 16:
            if callback:
                callback(None, PdfAnnotationSyncError('limits'))
            return False
        cancel = Event()
        job = {'cancel': cancel, 'source': source_path,
               'callbacks': {callback_key if callback_key is not None else callback: callback} if callback else {},
               'pending': False, 'passes': 0, 'running': False, 'timer': None, 'immediate': immediate,
               'activity': activity_log.start_activity(t('reader_pdf_sync_title'), cancel=cancel.set)}
        self.jobs[key] = job
        self._schedule(key, job)
        return True

    def _schedule(self, key, job):
        if job['timer'] is not None and self.cancel_deferred:
            self.cancel_deferred(job['timer'])
        job['timer'] = None
        if self.defer is not None and not job['immediate']:
            job['timer'] = self.defer(lambda: self._start(key, job))
        else:
            self._start(key, job)

    def _start(self, key, job):
        if self.jobs.get(key) is not job:
            return
        job['timer'] = None
        if job['cancel'].is_set():
            self.jobs.pop(key, None)
            activity_log.cancel_activity(job['activity'])
            for callback in job['callbacks'].values():
                callback(None, PdfAnnotationSyncError('cancelled'))
            return
        job['running'] = True
        source = job['source']
        job['pending'] = False
        job['passes'] += 1
        def work():
            def cancelled():
                if self.sync is not sync_pdf_annotations_in_process:
                    wait_for_pdf_reading(job['cancel'])
                return job['cancel'].is_set()
            return self.sync(*key, source_path=source, cancel=cancelled)
        def done(future):
            if self.jobs.get(key) is not job:
                return
            job['running'] = False
            result, error = None, None
            try:
                result = future.result()
            except Exception as caught:
                error = caught
            if not job['cancel'].is_set() and not error and (job['pending'] or result.get('retry_needed')):
                if job['passes'] < 4:
                    self._schedule(key, job)
                    return
                error = PdfAnnotationSyncError('file_changed')
            self.jobs.pop(key, None)
            if error:
                if getattr(error, 'reason', None) == 'limits':
                    self.auto_suppressed.add(key)
                activity_log.fail_activity(job['activity'], sync_error_text(error))
            elif job['cancel'].is_set():
                error = PdfAnnotationSyncError('cancelled')
                activity_log.cancel_activity(job['activity'])
            else:
                self.auto_suppressed.discard(key)
                activity_log.finish_activity(job['activity'], detail=t('reader_pdf_sync_complete'))
            for callback in job['callbacks'].values():
                callback(result, error)
        try:
            self.submit(work, done)
        except Exception as error:
            from concurrent.futures import Future
            failed = Future()
            failed.set_exception(error)
            done(failed)
