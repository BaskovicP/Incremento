"""Brief cooperative pauses keep background PDF scans behind active reading."""
from threading import Lock
import time

_lock = Lock()
_reading_until = 0.0


def defer_for_pdf_reading(seconds=.4):
    global _reading_until
    with _lock:
        _reading_until = max(_reading_until, time.monotonic() + seconds)


def wait_for_pdf_reading(cancel):
    # Bound each checkpoint, even if another pane keeps requesting bytes.
    # Event.wait releases the interpreter and wakes immediately on cancellation.
    deadline = time.monotonic() + .25
    while not cancel.is_set():
        with _lock:
            until = min(_reading_until, deadline)
        remaining = until - time.monotonic()
        if remaining <= 0:
            return
        cancel.wait(min(remaining, .025))
