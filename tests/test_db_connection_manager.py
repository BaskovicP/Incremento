from pathlib import Path
from threading import Event, Thread

from db_connection import ProfileConnectionManager


def test_initializing_one_profile_does_not_block_another_threads_ready_connection(tmp_path):
    manager = ProfileConnectionManager()
    ready, start_warm, returned, initializing, release = (Event() for _ in range(5))
    errors = []
    def warm():
        try:
            first = manager.get(cache_key="ready", db_path=tmp_path / "ready.db", initialize=lambda conn: None)
            ready.set()
            assert start_warm.wait(5)
            assert manager.get(cache_key="ready", db_path=tmp_path / "ready.db", initialize=lambda conn: None) is first
            returned.set()
        except Exception as error:
            errors.append(error)
    def slow():
        def initialize(conn):
            initializing.set()
            assert release.wait(5)
        try:
            manager.get(cache_key="slow", db_path=Path(tmp_path / "slow.db"), initialize=initialize)
        except Exception as error:
            errors.append(error)
    warm_thread, slow_thread = Thread(target=warm), Thread(target=slow)
    warm_thread.start()
    assert ready.wait(5)
    slow_thread.start()
    assert initializing.wait(5)
    try:
        start_warm.set()
        assert returned.wait(1), "unrelated initialization held the global connection lock"
    finally:
        release.set()
        warm_thread.join(5)
        slow_thread.join(5)
        manager.close_all()
    assert errors == []
