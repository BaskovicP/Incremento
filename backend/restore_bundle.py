"""Validate and stage a full profile backup before a closed-profile restore."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_service import normalize_config
from .db import _SCHEMA_MIGRATIONS
from .paths import sanitize_profile_name


class BackupValidationError(ValueError):
    """The archive cannot safely replace an Anki profile."""


class RestoreRollbackError(RuntimeError):
    """A file swap failed and prior files need manual recovery from staging."""


_MAX_MEMBERS = 100_000
_MAX_MEMBER_BYTES = 64 * 1024**3
_MAX_TOTAL_BYTES = 512 * 1024**3
_MAX_JSON_BYTES = 4 * 1024**2


@dataclass(frozen=True)
class BackupReport:
    source_profile: str
    target_profile: str
    card_count: int
    media_count: int
    missing_cover_count: int
    profile_file_count: int
    uncompressed_bytes: int
    archive_size: int
    archive_mtime_ns: int

    @property
    def profile_mismatch(self) -> bool:
        return self.source_profile != self.target_profile


@dataclass
class StagedBackup:
    collection: Path
    media: Path
    runtime: Path
    config: dict[str, Any]
    profile_stage_dir: Path
    runtime_stage_dir: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.profile_stage_dir, ignore_errors=True)
        shutil.rmtree(self.runtime_stage_dir, ignore_errors=True)


@dataclass
class BackupSwap:
    changes: list[tuple[Path, Path | None]]

    def rollback(self) -> None:
        for target, previous in reversed(self.changes):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            if previous is not None:
                os.replace(previous, target)
        self.changes.clear()

    def commit(self) -> None:
        for _, previous in self.changes:
            if previous is None:
                continue
            if previous.is_dir():
                shutil.rmtree(previous)
            elif previous.exists():
                previous.unlink()
        self.changes.clear()


def _parts(name: str) -> tuple[str, ...]:
    if not name or "\\" in name or "\x00" in name or name.startswith("/"):
        raise BackupValidationError(f"Unsafe ZIP path: {name!r}")
    parts = tuple(name.rstrip("/").split("/"))
    if any(
        part in {"", ".", ".."} or ":" in part
        or any(ord(char) < 32 or ord(char) == 127 for char in part)
        for part in parts
    ):
        raise BackupValidationError(f"Unsafe ZIP path: {name!r}")
    return parts


def _members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > _MAX_MEMBERS:
        raise BackupValidationError("Backup has too many ZIP entries.")
    members = {}
    total = 0
    for info in infos:
        _parts(info.filename)
        if info.filename in members:
            raise BackupValidationError(f"Duplicate ZIP entry: {info.filename}")
        if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
            raise BackupValidationError("Backup contains a symbolic link.")
        if info.flag_bits & 1:
            raise BackupValidationError("Encrypted ZIP entries are unsupported.")
        if info.file_size > _MAX_MEMBER_BYTES:
            raise BackupValidationError("Backup contains an oversized file.")
        total += info.file_size
        if total > _MAX_TOTAL_BYTES:
            raise BackupValidationError("Backup expands beyond the restore limit.")
        members[info.filename] = info
    return members


def _json_member(
    archive: zipfile.ZipFile, members: dict, name: str, *, max_bytes: int = _MAX_JSON_BYTES
) -> Any:
    info = members.get(name)
    if info is None or info.file_size > max_bytes:
        raise BackupValidationError(f"Missing or oversized {name}.")
    try:
        return json.loads(archive.read(name).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RuntimeError, zipfile.BadZipFile) as exc:
        raise BackupValidationError(f"Invalid {name}.") from exc


def _copy_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as source, destination.open("xb") as output:
        remaining = info.file_size
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                raise BackupValidationError(f"Truncated ZIP entry: {info.filename}")
            output.write(chunk)
            remaining -= len(chunk)
        if source.read(1):
            raise BackupValidationError(f"Oversized ZIP entry: {info.filename}")


def _check_db(path: Path, *, anki: bool) -> tuple[int, int]:
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupValidationError("A backup database failed SQLite integrity check.")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if anki:
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                if not {"col", "cards", "notes", "revlog"}.issubset(tables):
                    raise BackupValidationError("Anki package is missing required tables.")
                for table, required_columns in (
                    ("col", {"id", "conf", "models", "decks", "dconf", "tags"}),
                    ("cards", {"id", "nid", "did", "queue", "due", "ivl"}),
                    ("notes", {"id", "mid", "flds", "tags"}),
                    ("revlog", {"id", "cid", "ease", "ivl"}),
                ):
                    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                    if not required_columns.issubset(columns):
                        raise BackupValidationError(f"Anki package has an incomplete {table} table.")
                if conn.execute("SELECT COUNT(*) FROM col").fetchone()[0] != 1:
                    raise BackupValidationError("Anki package has an invalid collection header.")
                header = conn.execute("SELECT conf, models, decks, dconf, tags FROM col").fetchone()
                if any(not isinstance(json.loads(value), dict) for value in header):
                    raise BackupValidationError("Anki package has invalid collection settings.")
                orphan = conn.execute(
                    "SELECT 1 FROM cards c LEFT JOIN notes n ON n.id=c.nid "
                    "WHERE n.id IS NULL LIMIT 1"
                ).fetchone()
                if orphan:
                    raise BackupValidationError("Anki package contains orphan cards.")
                return int(conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]), version
            if version > _SCHEMA_MIGRATIONS[-1][0]:
                raise BackupValidationError(
                    "Incremento database comes from a newer add-on version."
                )
            return 0, version
        finally:
            conn.close()
    except (sqlite3.DatabaseError, json.JSONDecodeError, TypeError) as exc:
        raise BackupValidationError("A backup database is invalid.") from exc


def _safe_media_name(name: object) -> bool:
    return (
        isinstance(name, str) and bool(name) and name not in {".", ".."}
        and len(name) <= 255 and "/" not in name and "\\" not in name
        and ":" not in name and not any(ord(char) < 32 for char in name)
    )


def _verify_anki_open(path: Path, expected_cards: int) -> None:
    """Ask the installed Anki runtime to open the disposable package database."""
    try:
        from anki.collection import Collection

        collection = Collection(str(path))
        try:
            if collection.card_count() != expected_cards:
                raise BackupValidationError("Anki opened a different card count than expected.")
        finally:
            collection.close()
    except BackupValidationError:
        raise
    except Exception as exc:
        raise BackupValidationError(
            "The installed Anki version cannot open this backup collection."
        ) from exc


def _missing_cover_count(path: Path, media_names: set[str]) -> int:
    """Find bare cover filenames that Anki's ordinary media scan may omit."""
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        models = json.loads(conn.execute("SELECT models FROM col").fetchone()[0])
        missing: set[str] = set()
        for model in models.values():
            if not isinstance(model, dict):
                continue
            cover_field = {
                "Incremento PDF": "PDF_Cover_Image",
                "Incremento EPUB": "EPUB_Cover_Image",
            }.get(model.get("name"))
            if cover_field is None:
                continue
            field_index = next(
                (index for index, field in enumerate(model.get("flds", []))
                 if isinstance(field, dict) and field.get("name") == cover_field),
                None,
            )
            if field_index is None:
                continue
            for (fields,) in conn.execute("SELECT flds FROM notes WHERE mid = ?", (model.get("id"),)):
                parts = fields.split("\x1f")
                if len(parts) > field_index:
                    name = parts[field_index].strip()
                    if name and name not in media_names:
                        missing.add(name)
        return len(missing)
    finally:
        conn.close()


def _validate_apkg(apkg: Path) -> tuple[int, int, int]:
    with zipfile.ZipFile(apkg) as archive:
        members = _members(archive)
        collection_name = "collection.anki21" if "collection.anki21" in members else "collection.anki2"
        if collection_name not in members:
            raise BackupValidationError("Anki package has no collection database.")
        media_map = _json_member(archive, members, "media", max_bytes=64 * 1024**2)
        if not isinstance(media_map, dict) or len(media_map) > _MAX_MEMBERS:
            raise BackupValidationError("Anki media map is invalid.")
        names = set()
        for key, name in media_map.items():
            if not isinstance(key, str) or not key.isdecimal() or key not in members or not _safe_media_name(name):
                raise BackupValidationError("Anki media map contains an unsafe or missing file.")
            if name in names:
                raise BackupValidationError("Anki media map has duplicate filenames.")
            names.add(name)
        if archive.testzip() is not None:
            raise BackupValidationError("Anki package contains a damaged file.")
        with tempfile.TemporaryDirectory(prefix="incremento-anki-check-") as temporary:
            db_path = Path(temporary) / "collection.anki2"
            _copy_member(archive, members[collection_name], db_path)
            count, _ = _check_db(db_path, anki=True)
            missing_covers = _missing_cover_count(db_path, names)
            _verify_anki_open(db_path, count)
        return count, len(media_map), missing_covers


def precheck_backup(path: str | Path, *, target_profile: str) -> BackupReport:
    """Read and verify the complete archive; never touch the live profile."""
    backup = Path(path)
    if not backup.is_file():
        raise BackupValidationError("Choose an existing full-backup ZIP.")
    archive_stat = backup.stat()
    try:
        with zipfile.ZipFile(backup) as archive:
            members = _members(archive)
            manifest = _json_member(archive, members, "manifest.json")
            config = _json_member(archive, members, "config.json")
            if not isinstance(config, dict):
                raise BackupValidationError("Backup configuration is invalid.")
            try:
                normalize_config(config)
            except Exception as exc:
                raise BackupValidationError("Backup configuration is incompatible.") from exc
            if not isinstance(manifest, dict) or manifest.get("addon") != "Incremento" or manifest.get("scope") != "current_profile" or manifest.get("schema_version") != 2:
                raise BackupValidationError("This is not a supported full Incremento backup.")
            source = manifest.get("profile_storage_key")
            if not isinstance(source, str) or source != sanitize_profile_name(source):
                raise BackupValidationError("Backup profile name is invalid.")
            required = {"anki/all_decks.apkg", f"user_files/{source}/incremento.db"}
            if not required.issubset(members):
                raise BackupValidationError("Backup is missing its Anki package or Incremento database.")
            profile_prefix = f"user_files/{source}/"
            profile_files = []
            for name, info in members.items():
                if info.is_dir():
                    raise BackupValidationError("Directory ZIP entries are unsupported.")
                if name.startswith(profile_prefix):
                    profile_files.append(name)
                elif name in {"anki/all_decks.apkg", "manifest.json", "config.json", "restore.txt"} or (name.startswith("data/") and name.endswith(".json") and len(_parts(name)) == 2):
                    continue
                else:
                    raise BackupValidationError(f"Unexpected ZIP entry: {name}")
            if archive.testzip() is not None:
                raise BackupValidationError("Backup contains a damaged file.")
            with tempfile.TemporaryDirectory(prefix="incremento-restore-check-") as temporary:
                apkg = Path(temporary) / "all_decks.apkg"
                database = Path(temporary) / "incremento.db"
                _copy_member(archive, members["anki/all_decks.apkg"], apkg)
                _copy_member(archive, members[f"user_files/{source}/incremento.db"], database)
                card_count, media_count, missing_cover_count = _validate_apkg(apkg)
                _, db_version = _check_db(database, anki=False)
            counts = manifest.get("counts")
            database_info = manifest.get("database")
            if not isinstance(counts, dict) or not isinstance(database_info, dict):
                raise BackupValidationError("Backup manifest counts or database metadata are invalid.")
            expected_cards = counts.get("anki_cards_exported")
            expected_version = database_info.get("schema_version")
            profile_bytes = sum(members[name].file_size for name in profile_files)
            if type(expected_cards) is not int or expected_cards != card_count:
                raise BackupValidationError("Anki card count does not match the backup manifest.")
            if type(counts.get("user_files_copied")) is not int or counts["user_files_copied"] != len(profile_files):
                raise BackupValidationError("Incremento file count does not match the manifest.")
            if type(counts.get("user_files_bytes")) is not int or counts["user_files_bytes"] != profile_bytes:
                raise BackupValidationError("Incremento file size does not match the manifest.")
            if type(expected_version) is not int or expected_version != db_version:
                raise BackupValidationError("Incremento database version does not match the manifest.")
            if database_info.get("integrity_check") != "ok":
                raise BackupValidationError("Backup manifest reports a damaged Incremento database.")
            final_stat = backup.stat()
            if (final_stat.st_size, final_stat.st_mtime_ns) != (
                archive_stat.st_size, archive_stat.st_mtime_ns
            ):
                raise BackupValidationError("Backup changed during its pre-check; try again.")
            return BackupReport(
                source_profile=source,
                target_profile=sanitize_profile_name(target_profile),
                card_count=card_count,
                media_count=media_count,
                missing_cover_count=missing_cover_count,
                profile_file_count=len(profile_files),
                uncompressed_bytes=sum(info.file_size for info in members.values()),
                archive_size=archive_stat.st_size,
                archive_mtime_ns=archive_stat.st_mtime_ns,
            )
    except OSError as exc:
        raise BackupValidationError(f"Could not read or check the backup: {exc}") from exc
    except (zipfile.BadZipFile, EOFError) as exc:
        raise BackupValidationError("Backup ZIP is unreadable or damaged.") from exc


def stage_backup(
    path: str | Path, report: BackupReport, collection: Path, runtime: Path
) -> StagedBackup:
    """Extract only validated members into hidden folders beside live targets."""
    backup = Path(path)
    archive_stat = backup.stat()
    if (archive_stat.st_size, archive_stat.st_mtime_ns) != (report.archive_size, report.archive_mtime_ns):
        raise BackupValidationError("Backup changed after its pre-check; check it again.")
    profile_stage_dir = Path(tempfile.mkdtemp(prefix=".incremento-restore-", dir=collection.parent))
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime_stage_dir = Path(tempfile.mkdtemp(prefix=".incremento-restore-", dir=runtime.parent))
    staged = StagedBackup(
        collection=profile_stage_dir / "collection.anki2",
        media=profile_stage_dir / "collection.media",
        runtime=runtime_stage_dir / runtime.name,
        config={}, profile_stage_dir=profile_stage_dir,
        runtime_stage_dir=runtime_stage_dir,
    )
    try:
        staged.media.mkdir()
        staged.runtime.mkdir()
        with zipfile.ZipFile(backup) as archive:
            members = _members(archive)
            prefix = f"user_files/{report.source_profile}/"
            _copy_member(archive, members["anki/all_decks.apkg"], profile_stage_dir / "package.apkg")
            for name, info in members.items():
                if name.startswith(prefix):
                    _copy_member(archive, info, staged.runtime / name[len(prefix):])
            staged.config = _json_member(archive, members, "config.json")
        with zipfile.ZipFile(profile_stage_dir / "package.apkg") as apkg:
            inner = _members(apkg)
            collection_name = "collection.anki21" if "collection.anki21" in inner else "collection.anki2"
            _copy_member(apkg, inner[collection_name], staged.collection)
            media_map = _json_member(apkg, inner, "media", max_bytes=64 * 1024**2)
            for key, name in media_map.items():
                if not _safe_media_name(name):
                    raise BackupValidationError("Anki media map changed after pre-check.")
                _copy_member(apkg, inner[key], staged.media / name)
        staged_count, _ = _check_db(staged.collection, anki=True)
        if staged_count != report.card_count or len(media_map) != report.media_count:
            raise BackupValidationError("Staged Anki package changed after pre-check.")
        _check_db(staged.runtime / "incremento.db", anki=False)
        final_stat = backup.stat()
        if (final_stat.st_size, final_stat.st_mtime_ns) != (
            report.archive_size, report.archive_mtime_ns
        ):
            raise BackupValidationError("Backup changed while it was being staged; try again.")
        return staged
    except Exception:
        staged.cleanup()
        raise


def swap_staged_backup(
    staged: StagedBackup, collection: Path, media: Path, runtime: Path
) -> BackupSwap:
    """Replace closed-profile paths, reverting every move if one fails."""
    anki_sidecars = (
        collection.parent / f"{collection.name}-wal",
        collection.parent / f"{collection.name}-shm",
        media.parent / "collection.media.db2",
        media.parent / "collection.media.db2-wal",
        media.parent / "collection.media.db2-shm",
    )
    targets = (collection, media, *anki_sidecars, runtime)
    if any(path.is_symlink() for path in targets) or collection.parent.is_symlink() or runtime.parent.is_symlink():
        raise BackupValidationError("A restore target is a symbolic link.")
    if not staged.collection.is_file() or not staged.media.is_dir() or not staged.runtime.is_dir():
        raise BackupValidationError("Staged backup is incomplete.")
    replacements = (
        (collection, staged.collection),
        (media, staged.media),
        *((path, None) for path in anki_sidecars),
        (runtime, staged.runtime),
    )
    swap = BackupSwap([])
    try:
        for index, (target, replacement) in enumerate(replacements):
            previous = None
            if target.exists():
                previous = (
                    staged.runtime_stage_dir if target == runtime else staged.profile_stage_dir
                ) / f"previous-{index}"
                os.replace(target, previous)
            try:
                if replacement is not None:
                    os.replace(replacement, target)
            except Exception:
                if previous is not None:
                    os.replace(previous, target)
                raise
            swap.changes.append((target, previous))
        return swap
    except Exception as exc:
        try:
            swap.rollback()
        except Exception as rollback_exc:
            raise RestoreRollbackError(
                f"File replacement failed ({exc}) and automatic rollback failed "
                f"({rollback_exc}). Prior files remain in the restore staging folders."
            ) from rollback_exc
        raise
