"""Include Incremento cover filenames that Anki cannot detect in plain fields."""

from __future__ import annotations

import os

from anki.exporting import AnkiPackageExporter

from .epub_manager import EPUB_COVER_FIELD, EPUB_NOTE_TYPE
from .pdf_manager import PDF_COVER_FIELD, PDF_NOTE_TYPE


def _safe_cover_filename(name: str) -> bool:
    return (
        bool(name) and len(name) <= 255 and name not in {".", ".."}
        and "/" not in name and "\\" not in name and ":" not in name
        and not any(ord(char) < 32 or ord(char) == 127 for char in name)
    )


class FullBackupPackageExporter(AnkiPackageExporter):
    """Export the normal Anki media plus referenced PDF and EPUB cover files."""

    def prepareMedia(self) -> None:
        if not self.includeMedia or not self.mediaDir:
            return
        included = set(self.mediaFiles)
        for model_name, cover_field in (
            (PDF_NOTE_TYPE, PDF_COVER_FIELD),
            (EPUB_NOTE_TYPE, EPUB_COVER_FIELD),
        ):
            model = self.src.models.by_name(model_name)
            if model is None:
                continue
            field_index = next(
                (index for index, field in enumerate(model["flds"])
                 if field["name"] == cover_field),
                None,
            )
            if field_index is None:
                continue
            for (fields,) in self.src.db.execute(
                "SELECT flds FROM notes WHERE mid = ?", model["id"]
            ):
                parts = fields.split("\x1f")
                if len(parts) <= field_index:
                    continue
                name = parts[field_index].strip()
                if not _safe_cover_filename(name) or name in included:
                    continue
                path = os.path.join(self.mediaDir, name)
                if os.path.isfile(path) and not os.path.islink(path):
                    self.mediaFiles.append(name)
                    included.add(name)
