"""Bounded native-compatible exports and reversible full-profile restores."""

from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

try:
    from . import db, paths, mcp_checkpoint as checkpoint
    from .mcp_content_operations import McpContentOperations
    from .mcp_anki import AnkiToolError
    from .mcp_undo import atomic_bytes, encoded
    from .export_bundle import should_skip_user_file, snapshot_database
except ImportError:
    import db
    import paths
    import mcp_checkpoint as checkpoint
    from mcp_content_operations import McpContentOperations
    from mcp_anki import AnkiToolError
    from mcp_undo import atomic_bytes, encoded
    from export_bundle import should_skip_user_file, snapshot_database


def backup_operations(schema, text, patch):
    return {
        "backup_export": (13, schema({"path": text}, ["path"])),
        "backup_restore": (13, schema({"path": text}, ["path"])),
        "backup_policy": (13, schema({"policy": patch}, ["policy"])),
        "support_export": (13, schema({"path": text}, ["path"])),
    }


def runtime_file_allowed(relative):
    parts = Path(relative).parts
    return (
        not should_skip_user_file(str(relative))
        and not any(p.startswith(".incremento-restore-") for p in parts)
        and parts[0] not in {"mcp_undo_files", "mcp_history.json", "mcp_token", "mcp_runtime_state.json"}
        and str(relative) not in {"incremento.db", "incremento.db-wal", "incremento.db-shm"}
    )


class McpBackupOperations(McpContentOperations):
    def _prepare_backup(self, col, action, p):
        if action in {"backup_restore", "backup_policy"} and getattr(self, "save_config", None) is None:
            raise AnkiToolError("Settings persistence is unavailable; no change was made.")
        if action in {"backup_export", "support_export"}:
            path = checkpoint.checked_path(p["path"])
            if path.exists() or path.suffix.lower() != ".zip" or not path.parent.is_dir():
                raise AnkiToolError("Choose a new ZIP filename in an existing directory.")
        if action == "backup_restore":
            from .restore_bundle import precheck_backup, stage_backup

            report = precheck_backup(p["path"], target_profile=self.profile)
            if report.uncompressed_bytes > checkpoint.MAX_TOTAL or report.profile_file_count > checkpoint.MAX_FILES:
                raise AnkiToolError("Backup exceeds the 512 MiB/512-file persistent recovery budget.")
            if getattr(self, "runtime", None):
                self._runtime("check_full_restore")
            stage = stage_backup(
                p["path"], report, Path(col.path), paths.get_user_files_dir(self.addon_dir, self.profile)
            )
            try:
                p["_restore_targets"] = self._restore_file_targets(col, stage)
                p["_backup_report"] = {
                    "source_profile": report.source_profile,
                    "cards": report.card_count,
                    "media": report.media_count,
                }
            finally:
                stage.cleanup()
        if action == "backup_policy":
            from .backup_schedule import normalize_policy, validate_destination

            policy = normalize_policy(p["policy"])
            if policy["enabled"]:
                validate_destination(policy["directory"], paths.get_user_files_dir(self.addon_dir, self.profile))
            p["policy"] = policy
        return p

    def _backup_scope(self, col, action, p, scope):
        if action in {"backup_export", "support_export"}:
            scope["anki"] = False
            scope["files"] = [p["path"]]
        elif action == "backup_policy":
            scope["anki"] = False
            scope["settings"] = True
        elif action == "backup_restore":
            scope["anki"] = True
            scope["sqlite"] = True
            scope["settings"] = True
            root = paths.get_user_files_dir(self.addon_dir, self.profile)
            current = []
            for folder in (root, Path(col.media.dir())):
                for path in folder.rglob("*"):
                    checkpoint.checked_path(path)
                    if path.is_file() and (folder != root or runtime_file_allowed(path.relative_to(root))):
                        current.append(str(path))
                    if len(current) > checkpoint.MAX_FILES:
                        raise AnkiToolError("Current profile exceeds the full-restore file recovery budget.")
            scope["files"] = sorted(set(current) | set(p["_restore_targets"]))
        return scope

    def _restore_file_targets(self, col, stage):
        root = paths.get_user_files_dir(self.addon_dir, self.profile)
        pairs = []
        for source, destination in ((stage.media, Path(col.media.dir())), (stage.runtime, root)):
            for path in source.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(source)
                    if source == stage.runtime and not runtime_file_allowed(relative):
                        continue
                    pairs.append(str(destination / relative))
        return sorted(pairs)

    def _op_backup_policy(self, col, policy):
        cfg = dict(self.config)
        cfg["automatic_backups"] = {**cfg.get("automatic_backups", {}), self.profile: policy}
        self._save_operation_settings(cfg)
        return {"policy": policy}

    def _op_backup_export(self, col, path):
        from anki.import_export_pb2 import ExportLimit, ExportAnkiPackageOptions

        root = paths.get_user_files_dir(self.addon_dir, self.profile)
        db.get_connection(self.addon_dir, self.profile)
        selected = []
        total = 0
        for source in root.rglob("*"):
            relative = source.relative_to(root)
            if (
                not source.is_file()
                or should_skip_user_file(str(relative))
                or str(relative) in {"incremento.db", "incremento.db-wal", "incremento.db-shm"}
            ):
                continue
            raw = self._bounded_bytes(checkpoint.checked_path(source), checkpoint.MAX_FILE)
            total += len(raw)
            selected.append((source, relative))
            if total > checkpoint.MAX_TOTAL or len(selected) > checkpoint.MAX_FILES:
                raise AnkiToolError("Full backup exceeds the bounded export budget.")
        with tempfile.TemporaryDirectory(prefix="incremento-mcp-backup-") as temporary:
            temporary = Path(temporary)
            package = temporary / "all_decks.apkg"
            count = col.export_anki_package(
                out_path=str(package),
                options=ExportAnkiPackageOptions(
                    with_scheduling=True, with_media=True, with_deck_configs=True, legacy=True
                ),
                limit=ExportLimit(whole_collection={}),
            )
            database = snapshot_database(paths.get_db_path(self.addon_dir, self.profile), temporary / "incremento.db")
            output = temporary / "backup.zip"
            with ZipFile(output, "w", ZIP_DEFLATED) as archive:
                archive.write(package, "anki/all_decks.apkg")
                archive.write(temporary / "incremento.db", f"user_files/{self.profile}/incremento.db")
                for source, relative in selected:
                    archive.write(source, f"user_files/{self.profile}/{relative.as_posix()}")
                archive.writestr(
                    "config.json", encoded({k: v for k, v in self.config.items() if not k.startswith("_")})
                )
                profile_entries = [entry for entry in archive.infolist() if entry.filename.startswith("user_files/")]
                archive.writestr(
                    "manifest.json",
                    encoded(
                        {
                            "schema_version": 2,
                            "export_date": date.today().isoformat(),
                            "addon": "Incremento",
                            "scope": "current_profile",
                            "profile": self.profile,
                            "profile_storage_key": self.profile,
                            "database": database,
                            "counts": {
                                "anki_cards_exported": count,
                                "user_files_copied": len(profile_entries),
                                "user_files_bytes": sum(entry.file_size for entry in profile_entries),
                            },
                            "files": {},
                        }
                    ),
                )
            from .restore_bundle import precheck_backup

            precheck_backup(output, target_profile=self.profile)
            atomic_bytes(checkpoint.checked_path(path), self._bounded_bytes(output, checkpoint.MAX_FILE))
        return {"path": path, "cards": count, "native_restore_compatible": True}

    def _op_backup_restore(self, col, path, _input_sha256=None, _restore_targets=None, _backup_report=None):
        from anki.collection import Collection
        from .restore_bundle import precheck_backup, stage_backup
        from .config_service import normalize_config

        if getattr(self, "runtime", None):
            self._runtime("check_full_restore")

        report = precheck_backup(path, target_profile=self.profile)
        stage = stage_backup(path, report, Path(col.path), paths.get_user_files_dir(self.addon_dir, self.profile))
        try:
            if self._restore_file_targets(col, stage) != _restore_targets:
                raise AnkiToolError("The staged backup contents changed.")
            current = self._capture_advanced_action(col, self.history.get(self._active_change)["args"]["_advanced"])
            target = dict(current)
            isolated = Collection(str(stage.collection))
            try:
                target["anki"] = checkpoint.anki_state(self, isolated)
            finally:
                isolated.close()
            conn = sqlite3.connect(str(stage.runtime / "incremento.db"))
            try:
                tables = []
                for table in checkpoint.retained_json(self, current["sqlite"])["tables"]:
                    name = table["table"]
                    quoted = '"' + name.replace('"', '""') + '"'
                    columns = [r[1] for r in conn.execute(f"PRAGMA table_info({quoted})")]
                    if columns != table["columns"]:
                        raise AnkiToolError("Backup schema differs; migrate it in a separate profile first.")
                    rows = [list(row) for row in conn.execute(f"SELECT * FROM {quoted} LIMIT 100001")]
                    if len(rows) > 100000:
                        raise AnkiToolError("Backup table exceeds its restore budget.")
                    tables.append({**table, "rows": rows})
                target["sqlite"] = checkpoint.retain_json(self, {"tables": tables})
            finally:
                conn.close()
            files = []
            root = paths.get_user_files_dir(self.addon_dir, self.profile)
            for source, destination in ((stage.media, Path(col.media.dir())), (stage.runtime, root)):
                for source_file in source.rglob("*"):
                    if not source_file.is_file():
                        continue
                    relative = source_file.relative_to(source)
                    if source == stage.runtime and not runtime_file_allowed(relative):
                        continue
                    files.append(
                        {
                            "path": str(destination / relative),
                            "asset": checkpoint.retain(self, self._bounded_bytes(source_file, checkpoint.MAX_FILE)),
                        }
                    )
            target["files"] = files
            cfg = normalize_config(stage.config)
            for key in ("mcp_enabled", "mcp_allow_writes"):
                if key in self.config:
                    cfg[key] = self.config[key]
            target["settings"] = cfg
            checkpoint.restore(self, col, target, current)
            return {"restored": True, "cards": report.card_count, "connection_and_undo_history_preserved": True}
        finally:
            stage.cleanup()

    def _op_support_export(self, col, path):
        from .diagnostics import DiagnosticRecorder, build_support_bundle

        recorder = DiagnosticRecorder(self.addon_dir, self.profile)
        try:
            return build_support_bundle(
                path,
                addon_dir=self.addon_dir,
                profile=self.profile,
                recorder=recorder,
                config=self.config,
                default_config={},
                environment={},
                runtime_state={},
            )
        finally:
            recorder.close()
