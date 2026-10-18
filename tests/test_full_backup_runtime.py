"""Full-backup regressions at the SQLite/file boundary, without a live profile."""

import ast
import datetime
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import db
import export_bundle
import paths
from backend.i18n import Translator


class _StaleFTSConnection(sqlite3.Connection):
    """Reproduce the live worker's FTS error on an otherwise healthy database."""

    def execute(self, sql, parameters=()):
        if sql == "PRAGMA integrity_check":
            return super().execute(
                "SELECT 'malformed inverted index for FTS5 table main.pdf_text_fts'"
            )
        return super().execute(sql, parameters)


@pytest.mark.parametrize("automatic", [False, True], ids=["manual", "automatic"])
def test_full_backup_saves_healthy_database_despite_cached_connection_fts_error(
    tmp_path, automatic,
):
    addon_dir = str(tmp_path / "addon")
    source = paths.get_db_path(addon_dir, "P")
    source.parent.mkdir(parents=True)
    conn = sqlite3.connect(source, factory=_StaleFTSConnection)
    try:
        db._initialize_database(conn)
        conn.execute(
            "INSERT INTO pdf_text_index(card_id, page, text) VALUES(1, 1, 'searchable example')"
        )
        conn.commit()
        before = source.read_bytes()
        with sqlite3.connect(source) as fresh:
            assert fresh.execute("PRAGMA integrity_check").fetchall() == [("ok",)]

        class _PackageExporter:
            count = 1

            def __init__(self, _collection):
                pass

            def exportInto(self, path):
                Path(path).write_bytes(b"Anki package boundary")

        entrypoint = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
        start = next(
            node for node in ast.parse(entrypoint).body
            if isinstance(node, ast.FunctionDef) and node.name == "_start_full_backup"
        )
        task = next(
            node for node in start.body
            if isinstance(node, ast.FunctionDef) and node.name == "_task"
        )
        target = tmp_path / "backup.zip"
        work_file = tmp_path / "work.zip"
        namespace = {
            "_active_profile": lambda: "P",
            "profile": "P",
            "profile_display_name": "P",
            "_ADDON_DIR": addon_dir,
            "_paths": paths,
            "get_connection": lambda *_: conn,
            "sqlite3": sqlite3,
            "tempfile": tempfile,
            "Path": Path,
            "DB_NAME": db.DB_NAME,
            "_progress": lambda *_: None,
            "_t": Translator("en").t,
            "FullBackupPackageExporter": _PackageExporter,
            "collection": object(),
            "hooks": SimpleNamespace(media_files_did_export=[]),
            "snapshot_tree": export_bundle.snapshot_tree,
            "snapshot_database": getattr(export_bundle, "snapshot_database", None),
            "user_files_dir": str(source.parent),
            "zipfile": zipfile,
            "archive_tmp_path": str(work_file),
            "os": __import__("os"),
            "json": json,
            "config": {},
            "_restore_instructions": lambda: "Restore instructions",
            "today": datetime.date(2026, 1, 1).isoformat(),
            "mw": SimpleNamespace(pm=SimpleNamespace(meta={})),
            "path": str(target),
            "automatic_policy": {"versions": 3} if automatic else None,
            "_backup_schedule": __import__("backup_schedule"),
        }
        for name in ("priorities", "pdf_progress", "highlights", "stats"):
            namespace[f"export_{name}_json"] = lambda *_: "{}"
        exec(compile(ast.Module(body=[task], type_ignores=[]), "__init__.py", "exec"), namespace)

        result = namespace["_task"]()

        assert result["anki_cards_exported"] == 1
        assert not work_file.exists()
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["database"]["integrity_check"] == "ok"
            restored = tmp_path / "restored.db"
            restored.write_bytes(archive.read("user_files/P/incremento.db"))
        with sqlite3.connect(restored) as restored_conn:
            assert restored_conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert restored_conn.execute(
                "SELECT card_id, page FROM pdf_text_fts WHERE pdf_text_fts MATCH 'searchable'"
            ).fetchall() == [(1, 1)]
        assert source.read_bytes() == before
    finally:
        conn.close()
