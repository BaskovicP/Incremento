"""One ordered file writer with one replaceable pending immutable snapshot."""
from concurrent.futures import ThreadPoolExecutor
from threading import RLock


class OrderedWriter:
    def __init__(self, write, publish=None):
        self._write = write
        self._publish = publish
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="incremento-save")
        self._lock = RLock()
        self._pending = None
        self._future = None
        self._error = None

    def submit(self, snapshot):
        with self._lock:
            self._pending = snapshot
            if self._future is None:
                self._future = self._executor.submit(self._run)

    def _run(self):
        while True:
            with self._lock:
                snapshot = self._pending
                self._pending = None
            result = error = None
            try:
                result = self._write(snapshot)
            except Exception as exc:
                error = exc
            with self._lock:
                self._error = error
            if self._publish is not None:
                try:
                    self._publish(snapshot, result, error)
                except Exception:
                    pass
            with self._lock:
                if self._pending is None:
                    self._future = None
                    return

    def flush(self):
        while True:
            with self._lock:
                future, error = self._future, self._error
            if future is None:
                if error is not None:
                    raise error
                return
            future.result()

    def close(self):
        try:
            self.flush()
        finally:
            self._executor.shutdown(wait=True)
