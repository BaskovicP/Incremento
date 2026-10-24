"""Reconcile only captured PDF deletions after Anki's collection operation.

Undo leaves a rebuild marker; Search ALL reconstructs derived text on demand.
This adapter never changes Anki's undo stack or scans a profile at startup.
"""

from concurrent.futures import CancelledError
from threading import Lock

from aqt.operations import QueryOp

from .latest_query import LatestQuery

try:
    from ..backend.pdf_search import (
        invalidate_pdf_index_jobs,
        pdf_cards_for_notes,
        reconcile_pdf_search_indexes,
    )
except ImportError:
    from pdf_search import (
        invalidate_pdf_index_jobs,
        pdf_cards_for_notes,
        reconcile_pdf_search_indexes,
    )


class PdfSearchLifecycle:
    def __init__(self, addon_dir, profile, col, *, parent, taskman, valid):
        self.addon_dir, self.profile, self.col = addon_dir, profile, col
        self.parent, self.taskman, self.valid = parent, taskman, valid
        self._closed = False
        self._lock = Lock()
        self._tracked: set[int] = set()
        self._queries = LatestQuery(
            dispatch=self._dispatch,
            accept=lambda _: not self._closed and self.valid(),
            success=lambda *_: None,
            failure=lambda *_: None,
        )

    def notes_will_be_deleted(self, col, note_ids):
        # Anki invokes this on its collection worker before the actual deletion.
        if self._closed or col is not self.col:
            return
        try:
            candidates = pdf_cards_for_notes(col, note_ids)
        except Exception:
            # A failed read is not evidence of deletion; explicit search retries.
            return
        with self._lock:
            if self._closed:
                return
            self._tracked.update(candidates)
        if candidates:
            self.taskman.run_on_main(self.request)

    def collection_changed(self, changes, _handler=None):
        # Note deletion and its Undo/Redo change notes; routine card reviews do not.
        if getattr(changes, "note", False):
            self.request()

    def request(self):
        if self._closed or not self.valid():
            return
        with self._lock:
            ids = tuple(sorted(self._tracked))
        if ids:
            self._queries.submit(ids)

    def _dispatch(self, ticket, success, failure, _progress):
        def reconcile(col):
            if ticket.cancel.is_set() or col is not self.col:
                raise CancelledError()
            return reconcile_pdf_search_indexes(
                self.addon_dir,
                self.profile,
                col,
                card_ids=ticket.payload,
                cancel=ticket.cancel,
            )

        QueryOp(parent=self.parent, op=reconcile, success=success).failure(failure).run_in_background()

    def close(self):
        with self._lock:
            self._closed = True
        self._queries.close()
        invalidate_pdf_index_jobs(self.addon_dir, self.profile)
