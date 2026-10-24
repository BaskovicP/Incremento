"""One active read and one replaceable pending request, owned by the UI thread."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event
from typing import Any


@dataclass(frozen=True)
class QueryTicket:
    generation: int
    payload: Any
    cancel: Event = field(default_factory=Event)


class LatestQuery:
    """Dispatch workers without allowing obsolete results to reach the UI.

    All methods and dispatch callbacks run on the UI thread. Workers may read
    the ticket and its cancellation event; they return only plain data. The
    owner supplies a profile/collection guard through ``accept``.
    """

    def __init__(self, *, dispatch, success, failure, progress=None, accept=None):
        self._dispatch = dispatch
        self._success = success
        self._failure = failure
        self._progress = progress
        self._accept = accept or (lambda payload: True)
        self._generation = 0
        self._active: QueryTicket | None = None
        self._pending: QueryTicket | None = None
        self._closed = False

    def invalidate(self) -> None:
        self._generation += 1
        if self._active is not None:
            self._active.cancel.set()
        if self._pending is not None:
            self._pending.cancel.set()
        self._pending = None

    def close(self) -> None:
        self._closed = True
        self.invalidate()

    def submit(self, payload) -> None:
        if self._closed:
            return
        self.invalidate()
        self._pending = QueryTicket(self._generation, payload)
        self._start_pending()

    def _current(self, ticket: QueryTicket) -> bool:
        return (
            not self._closed
            and ticket.generation == self._generation
            and not ticket.cancel.is_set()
            and self._accept(ticket.payload)
        )

    def _start_pending(self) -> None:
        if self._closed or self._active is not None or self._pending is None:
            return
        ticket = self._pending
        self._pending = None
        if not self._current(ticket):
            return
        self._active = ticket
        try:
            self._dispatch(
                ticket,
                lambda value: self._finish(ticket, value, failed=False),
                lambda error: self._finish(ticket, error, failed=True),
                lambda value: self._deliver_progress(ticket, value),
            )
        except Exception as error:
            self._finish(ticket, error, failed=True)

    def _deliver_progress(self, ticket: QueryTicket, value) -> None:
        if self._active is ticket and self._current(ticket) and self._progress is not None:
            self._progress(ticket.payload, value)

    def _finish(self, ticket: QueryTicket, value, *, failed: bool) -> None:
        if self._active is not ticket:
            return
        self._active = None
        try:
            if self._current(ticket):
                callback = self._failure if failed else self._success
                callback(ticket.payload, value)
        finally:
            self._start_pending()
