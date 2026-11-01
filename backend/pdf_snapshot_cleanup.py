"""Explicit cleanup of unreferenced Incremento PDF screenshots in Anki media."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
from collections.abc import Callable, Iterable
from urllib.parse import unquote


_SNAPSHOT_NAME = re.compile(r"incremento-pdf-context-[0-9a-f]{24}\.png\Z")
_SNAPSHOT_REFERENCE = re.compile(r"incremento-pdf-context-[0-9a-f]{24}\.png")
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_IMAGE_SUFFIXES = frozenset((
    ".avif", ".bmp", ".gif", ".heic", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp",
))


@dataclass(frozen=True)
class PdfSnapshotCleanupResult:
    filenames: tuple[str, ...]
    total_bytes: int
    changes: object | None = None


@dataclass(frozen=True)
class AttachedImageCleanupResult:
    filenames: tuple[str, ...]
    total_bytes: int
    changes: object | None = None


class _ImageReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.names: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        source = next((value for key, value in attrs if key.lower() == "src"), "")
        name = unquote(str(source or "")).strip()
        if name and ":" not in name and "/" not in name and "\\" not in name:
            self.names.add(name)


def _protected_image_names(fields: Iterable[object]) -> set[str]:
    parser = _ImageReferenceParser()
    for field in fields:
        parser.feed(str(field or ""))
    parser.close()
    return parser.names


def _image_filename(name: object) -> str | None:
    value = str(name)
    if not value or Path(value).name != value or "\\" in value or Path(value).suffix.lower() not in _IMAGE_SUFFIXES:
        return None
    return value


def find_unused_attached_images(
    collection,
    *,
    protected_fields: Iterable[object] = (),
) -> AttachedImageCleanupResult:
    """List regular image files Anki reports as unused, excluding unsaved drafts."""
    unused = collection.media.check().unused
    protected = _protected_image_names(protected_fields)
    media_dir = Path(collection.media.dir())
    names: list[str] = []
    total_bytes = 0
    for item in sorted(set(str(value) for value in unused)):
        name = _image_filename(item)
        if name is None or name in protected:
            continue
        path = media_dir / name
        if path.is_symlink() or not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < 0:
            continue
        names.append(name)
        total_bytes += size
    return AttachedImageCleanupResult(tuple(names), total_bytes)


def trash_unused_attached_images(
    collection,
    approved_names: Iterable[str],
    *,
    protected_fields: Iterable[object] = (),
    empty_changes_factory: Callable[[], object] | None = None,
) -> AttachedImageCleanupResult:
    """Recheck Anki references before moving approved unused images to media trash."""
    changes = empty_changes_factory() if empty_changes_factory is not None else None
    approved = {name for item in approved_names if (name := _image_filename(item)) is not None}
    if not approved:
        return AttachedImageCleanupResult((), 0, changes)
    current = find_unused_attached_images(collection, protected_fields=protected_fields)
    names = tuple(name for name in current.filenames if name in approved)
    if not names:
        return AttachedImageCleanupResult((), 0, changes)
    media_dir = Path(collection.media.dir())
    try:
        total_bytes = sum((media_dir / name).stat().st_size for name in names)
    except OSError:
        return AttachedImageCleanupResult((), 0, changes)
    collection.media.trash_files(list(names))
    return AttachedImageCleanupResult(names, total_bytes, changes)


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
