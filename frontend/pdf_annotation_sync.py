"""Captured-profile, coalesced background PDF annotation writes.

The queue is used only on the UI thread. Its workers receive immutable file
identities and an Event; no Qt objects or Anki collections cross that boundary.
"""
from threading import Event

try:
    from ..backend import activity_log
    from ..backend.i18n import t
    from ..backend.pdf_annotations import PdfAnnotationSyncError, sync_pdf_annotations
except ImportError:
    import activity_log
    from i18n import t
    from pdf_annotations import PdfAnnotationSyncError, sync_pdf_annotations


def sync_error_text(error):
    reason = getattr(error, 'reason', 'write_failed')
    key = {
        'dependency': 'reader_pdf_sync_dependency',
        'document_changed': 'reader_pdf_sync_mismatch',
        'protected_pdf': 'reader_pdf_sync_protected',
        'file_changed': 'reader_pdf_sync_file_changed',
        'cancelled': 'reader_pdf_sync_cancelled',
        'limits': 'reader_pdf_sync_limits',
        'unsafe_path': 'reader_pdf_sync_unsafe_path',
    }.get(reason, 'reader_pdf_sync_write_failed')
    return t(key)


class PdfAnnotationSyncQueue:
    def __init__(self, submit, sync=sync_pdf_annotations):
        self.submit = submit
        self.sync = sync
        self.jobs = {}

    def reset(self):
        for job in self.jobs.values():
            job['cancel'].set()
            activity_log.cancel_activity(job['activity'])
        self.jobs.clear()

    def request(self, addon_dir, profile, card_id, filename, *, source_path=None, callback=None, callback_key=None):
        key = (addon_dir, profile, int(card_id), filename)
        job = self.jobs.get(key)
        if job is not None:
            job['pending'] = True
            if source_path is not None:
                job['source'] = source_path
            if callback:
                job['callbacks'][callback_key if callback_key is not None else callback] = callback
            return
        if len(self.jobs) >= 16:
            if callback:
                callback(None, PdfAnnotationSyncError('limits'))
            return
        cancel = Event()
        job = {'cancel': cancel, 'source': source_path,
               'callbacks': {callback_key if callback_key is not None else callback: callback} if callback else {},
               'pending': False, 'passes': 0,
               'activity': activity_log.start_activity(t('reader_pdf_sync_title'), cancel=cancel.set)}
        self.jobs[key] = job
        self._start(key, job)

    def _start(self, key, job):
        source = job['source']
        job['pending'] = False
        job['passes'] += 1
        def work():
            return self.sync(*key, source_path=source, cancel=job['cancel'].is_set)
        def done(future):
            if self.jobs.get(key) is not job:
                return
            result, error = None, None
            try:
                result = future.result()
            except Exception as caught:
                error = caught
            if not job['cancel'].is_set() and not error and (job['pending'] or result.get('retry_needed')):
                if job['passes'] < 4:
                    self._start(key, job)
                    return
                error = PdfAnnotationSyncError('file_changed')
            self.jobs.pop(key, None)
            if error:
                activity_log.fail_activity(job['activity'], sync_error_text(error))
            elif job['cancel'].is_set():
                error = PdfAnnotationSyncError('cancelled')
                activity_log.cancel_activity(job['activity'])
            else:
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
