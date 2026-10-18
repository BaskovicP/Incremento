"""Explicit cleanup of unreferenced Incremento PDF screenshots in Anki media."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from collections.abc import Callable, Iterable


_SNAPSHOT_NAME = re.compile(r"incremento-pdf-context-[0-9a-f]{24}\.png\Z")
_SNAPSHOT_REFERENCE = re.compile(r"incremento-pdf-context-[0-9a-f]{24}\.png")
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class PdfSnapshotCleanupResult:
    filenames: tuple[str, ...]
    total_bytes: int
    changes: object | None = None


def _protected_names(fields: Iterable[object]) -> set[str]:
    protected: set[str] = set()
    for field in fields:
        protected.update(_SNAPSHOT_REFERENCE.findall(str(field or "")))
    return protected


def find_unused_pdf_snapshots(
    collection,
    *,
    protected_fields: Iterable[object] = (),
) -> PdfSnapshotCleanupResult:
    """Use Anki's media reference check, then narrow to safe generated files."""
    unused = collection.media.check().unused
    protected = _protected_names(protected_fields)
    media_dir = Path(collection.media.dir())
    names: list[str] = []
    total_bytes = 0
    for name in sorted(set(str(item) for item in unused)):
        if not _SNAPSHOT_NAME.fullmatch(name) or name in protected:
            continue
        path = media_dir / name
        if path.is_symlink() or not path.is_file():
            continue
        try:
            size = path.stat().st_size
            if size <= 0 or size > _MAX_SNAPSHOT_BYTES:
                continue
            image = path.read_bytes()
        except OSError:
            continue
        digest = name.removeprefix("incremento-pdf-context-").removesuffix(".png")
        if len(image) != size or sha256(image).hexdigest()[:24] != digest:
            continue
        names.append(name)
        total_bytes += size
    return PdfSnapshotCleanupResult(tuple(names), total_bytes)


def trash_unused_pdf_snapshots(
    collection,
    approved_names: Iterable[str],
    *,
    protected_fields: Iterable[object] = (),
    empty_changes_factory: Callable[[], object] | None = None,
) -> PdfSnapshotCleanupResult:
    """Recheck references just before moving approved files to Anki trash."""
    changes = empty_changes_factory() if empty_changes_factory is not None else None
    approved = {str(name) for name in approved_names if _SNAPSHOT_NAME.fullmatch(str(name))}
    if not approved:
        return PdfSnapshotCleanupResult((), 0, changes)
    current = find_unused_pdf_snapshots(collection, protected_fields=protected_fields)
    names = tuple(name for name in current.filenames if name in approved)
    if not names:
        return PdfSnapshotCleanupResult((), 0, changes)
    media_dir = Path(collection.media.dir())
    total_bytes = sum((media_dir / name).stat().st_size for name in names)
    collection.media.trash_files(list(names))
    return PdfSnapshotCleanupResult(names, total_bytes, changes)
