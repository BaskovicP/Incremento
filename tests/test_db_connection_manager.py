from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Event, Thread

from db_connection import ProfileConnectionManager


def test_reused_worker_reads_and_writes_restored_database_after_profile_directory_swap(tmp_path):
    manager = ProfileConnectionManager()
    runtime = tmp_path / "profile"
    staged = tmp_path / "staged"
    for directory, priority in ((runtime, 10), (staged, 85)):
        directory.mkdir()
        with sqlite3.connect(directory / "incremento.db") as connection:
            connection.execute("CREATE TABLE priorities (priority INTEGER)")
            connection.execute("INSERT INTO priorities VALUES (?)", (priority,))
    path = runtime / "incremento.db"

    def connection():
        return manager.get(cache_key=str(path), db_path=path, initialize=lambda _conn: None)

    with ThreadPoolExecutor(max_workers=1) as worker:
        try:
            connection()
            old_worker_connection = worker.submit(connection).result(timeout=5)
            manager.close_current(cache_key=str(path))
            runtime.rename(tmp_path / "previous")
            staged.rename(runtime)
            # Profile reopen creates the new main-thread handle first.
            reopened = connection()
            reopened.execute("UPDATE priorities SET priority=90")
            reopened.commit()

            def use_restored_database():
                restored = connection()
                priority = restored.execute("SELECT priority FROM priorities").fetchone()[0]
                restored.execute("UPDATE priorities SET priority=91")
                restored.commit()
                return restored, priority

            restored, priority = worker.submit(use_restored_database).result(timeout=5)
            assert priority == 90
            assert restored is not old_worker_connection
            assert reopened.execute("SELECT priority FROM priorities").fetchone() == (91,)
        finally:
            worker.submit(manager.close_current).result(timeout=5)
            manager.close_all()
    with sqlite3.connect(path) as persisted:
        assert persisted.execute("SELECT priority FROM priorities").fetchone() == (91,)


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
