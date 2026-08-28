"""Thread-aware SQLite connection lifecycle for Incremento.

SQLite connections are intentionally scoped to one worker thread and one
profile.  The manager keeps them open for the lifetime of that thread so the
existing small DB helper calls stay cheap, while preventing unrelated Anki
CollectionOp/QueryOp workers from interleaving transactions on one Python
connection object.
"""

from __future__ import annotations

import sqlite3
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class _ConnectionRecord:
    cache_key: str
    connection: sqlite3.Connection
    thread_ref: "weakref.ReferenceType[threading.Thread]"


class ProfileConnectionManager:
    """Own one reusable SQLite connection per live thread and profile."""

    def __init__(self, *, busy_timeout_ms: int = 5000) -> None:
        self._busy_timeout_ms = max(0, int(busy_timeout_ms))
        self._lock = threading.RLock()
        self._local = threading.local()
        self._records: dict[tuple[int, int], _ConnectionRecord] = {}

    @staticmethod
    def _thread_key() -> tuple[int, int]:
        thread = threading.current_thread()
        return int(thread.ident or 0), id(thread)

    def _close_record(self, key: tuple[int, int], record: _ConnectionRecord) -> None:
        self._records.pop(key, None)
        try:
            record.connection.close()
        except Exception:
            # Closing is best-effort during shutdown/profile transitions.  A
            # later connection still needs to be able to open successfully.
            pass

    def _prune_dead_threads(self) -> None:
        for key, record in list(self._records.items()):
            thread = record.thread_ref()
            if thread is None or not thread.is_alive():
                self._close_record(key, record)

    def get(
        self,
        *,
        cache_key: str,
        db_path: Path,
        initialize: Callable[[sqlite3.Connection], None],
    ) -> sqlite3.Connection:
        """Return this thread's connection, replacing it on profile change."""
        with self._lock:
            self._prune_dead_threads()
            thread_key = self._thread_key()
            current = self._records.get(thread_key)
            if current is not None and current.cache_key == cache_key:
                return current.connection
            if current is not None:
                self._close_record(thread_key, current)

            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(db_path),
                timeout=max(0.001, self._busy_timeout_ms / 1000.0),
                check_same_thread=False,
            )
            try:
                connection.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=NORMAL")
                initialize(connection)
            except Exception:
                connection.close()
                raise

            record = _ConnectionRecord(
                cache_key=cache_key,
                connection=connection,
                thread_ref=weakref.ref(threading.current_thread()),
            )
            self._records[thread_key] = record
            self._local.cache_key = cache_key
            return connection

    def close_current(self, *, cache_key: str | None = None) -> None:
        """Close only this caller thread's matching connection.

        Profile hooks run on Qt's main thread while file-index or QueryOp
        workers may still be completing. Closing another live thread's SQLite
        handle from the hook would invalidate an in-flight operation.
        """
        with self._lock:
            key = self._thread_key()
            record = self._records.get(key)
            if record is not None and (
                cache_key is None or record.cache_key == cache_key
            ):
                self._close_record(key, record)
            self._local.cache_key = None

    def close_all(self, *, cache_key: str | None = None) -> None:
        """Close all managed connections, optionally only one profile DB."""
        with self._lock:
            for key, record in list(self._records.items()):
                if cache_key is None or record.cache_key == cache_key:
                    self._close_record(key, record)
            self._local.cache_key = None

    def connection_count(self) -> int:
        """Testing/diagnostic count; does not expose connection objects."""
        with self._lock:
            self._prune_dead_threads()
            return len(self._records)
