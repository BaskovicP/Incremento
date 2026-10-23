import os
import sqlite3
import tempfile

import pytest

import export_bundle


def test_profile_backup_never_copies_saved_simpletex_credentials_or_staged_writes(tmp_path):
    source, destination = tmp_path / "profile", tmp_path / "backup"
    source.mkdir()
    (source / "simpletex_credentials.json").write_text("private-secret")
    (source / ".simpletex_credentials-staged.tmp").write_text("private-secret")
    (source / "document.txt").write_text("content")
    stats = export_bundle.snapshot_tree(str(source), str(destination))
    assert sorted(p.name for p in destination.iterdir()) == ["document.txt"]
    assert stats["files_skipped"] == 2


def test_should_skip_transient_runtime_files():
    assert export_bundle.should_skip_user_file("video_profile/SingletonLock") is True
    assert export_bundle.should_skip_user_file("web_profile/lockfile") is True
    assert export_bundle.should_skip_user_file("__pycache__/module.pyc") is True
    assert export_bundle.should_skip_user_file("writing/note.md") is False


def test_snapshot_tree_copies_files_and_skips_transient_entries():
    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
        os.makedirs(os.path.join(src_dir, "writing"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "video_profile"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "__pycache__"), exist_ok=True)

        with open(os.path.join(src_dir, "writing", "note.md"), "w", encoding="utf-8") as fh:
            fh.write("hello")
        with open(os.path.join(src_dir, "incremento.db"), "w", encoding="utf-8") as fh:
            fh.write("db")
        with open(
            os.path.join(src_dir, "video_profile", "SingletonLock"), "w", encoding="utf-8"
        ) as fh:
            fh.write("lock")
        with open(os.path.join(src_dir, "__pycache__", "module.pyc"), "w", encoding="utf-8") as fh:
            fh.write("cache")

        stats = export_bundle.snapshot_tree(
            src_dir,
            dst_dir,
            skip_relpaths={"incremento.db"},
        )

        assert os.path.isfile(os.path.join(dst_dir, "writing", "note.md"))
        assert not os.path.exists(os.path.join(dst_dir, "incremento.db"))
        assert not os.path.exists(
            os.path.join(dst_dir, "video_profile", "SingletonLock")
        )
        assert not os.path.exists(os.path.join(dst_dir, "__pycache__", "module.pyc"))
        assert stats["files_copied"] == 1
        assert stats["files_skipped"] == 2


def test_snapshot_tree_does_not_follow_profile_symlinks(tmp_path):
    source = tmp_path / "profile"
    destination = tmp_path / "snapshot"
    outside = tmp_path / "outside.txt"
    source.mkdir()
    outside.write_text("private outside data", encoding="utf-8")
    try:
        (source / "linked.txt").symlink_to(outside)
    except OSError:
        return

    stats = export_bundle.snapshot_tree(str(source), str(destination))

    assert not (destination / "linked.txt").exists()
    assert stats["files_copied"] == 0
    assert stats["files_skipped"] == 1


def test_database_snapshot_includes_committed_wal_data_without_changing_source(tmp_path):
    source = tmp_path / "profile #1.db"
    destination = tmp_path / "snapshot.db"
    conn = sqlite3.connect(source)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE VIRTUAL TABLE documents USING fts5(text)")
        conn.execute("INSERT INTO documents VALUES('searchable example')")
        conn.execute("PRAGMA user_version=12")
        conn.commit()
        before = source.read_bytes()

        result = export_bundle.snapshot_database(source, destination)

        assert result == {"integrity_check": "ok", "schema_version": 12}
        assert source.read_bytes() == before
        with sqlite3.connect(destination) as copied:
            assert copied.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert copied.execute(
                "SELECT text FROM documents WHERE documents MATCH 'searchable'"
            ).fetchall() == [("searchable example",)]
    finally:
        conn.close()


def test_database_snapshot_rejects_real_integrity_error_without_creating_copy(tmp_path):
    source = tmp_path / "corrupt.db"
    destination = tmp_path / "snapshot.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE example(value INTEGER CHECK(value > 0))")
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute("INSERT INTO example VALUES(-1)")
    before = source.read_bytes()

    with pytest.raises(RuntimeError, match="integrity check failed"):
        export_bundle.snapshot_database(source, destination)

    assert source.read_bytes() == before
    assert not destination.exists()


def test_database_snapshot_rejects_missing_source_without_creating_database(tmp_path):
    source = tmp_path / "missing.db"
    destination = tmp_path / "snapshot.db"

    with pytest.raises(sqlite3.OperationalError):
        export_bundle.snapshot_database(source, destination)

    assert not source.exists()
    assert not destination.exists()


def test_database_snapshot_preserves_existing_destination(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "previous.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE example(value INTEGER)")
    destination.write_bytes(b"previous backup")

    with pytest.raises(FileExistsError):
        export_bundle.snapshot_database(source, destination)

    assert destination.read_bytes() == b"previous backup"


@pytest.mark.parametrize("failure", ["copy", "validation"])
def test_database_snapshot_removes_partial_copy_on_failure(monkeypatch, tmp_path, failure):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE example(value INTEGER CHECK(value > 0))")
        conn.execute("INSERT INTO example VALUES(1)")
    before = source.read_bytes()
    connect = sqlite3.connect

    class _InterruptedBackup(sqlite3.Connection):
        def backup(self, target, **kwargs):
            super().backup(target, **kwargs)
            if failure == "copy":
                raise sqlite3.OperationalError("interrupted copy")
            target.execute("PRAGMA ignore_check_constraints=ON")
            target.execute("INSERT INTO example VALUES(-1)")
            target.commit()
            target.execute("PRAGMA ignore_check_constraints=OFF")

    def open_connection(database, **kwargs):
        if kwargs.get("uri"):
            kwargs["factory"] = _InterruptedBackup
        return connect(database, **kwargs)

    monkeypatch.setattr(export_bundle.sqlite3, "connect", open_connection)
    error = sqlite3.OperationalError if failure == "copy" else RuntimeError
    with pytest.raises(error, match="interrupted copy|snapshot integrity check failed"):
        export_bundle.snapshot_database(source, destination)

    assert source.read_bytes() == before
    assert not destination.exists()
