"""Export managed reading documents using only their saved source and assets."""

import os
from pathlib import Path
import tempfile

from aqt import mw
from aqt.qt import QFileDialog
from aqt.utils import showInfo, tooltip

try:
    from ..backend import paths, markdown_manager
    from ..backend.i18n import t
except ImportError:
    from backend import paths, markdown_manager
    from backend.i18n import t


def export_document(addon_dir, profile, filename, title, *, parent=None, is_current=lambda: True):
    collection = mw.col
    choices = {t("imports_export_html_filter"): "html", t("imports_export_markdown_filter"): "md",
               t("imports_export_text_filter"): "txt"}
    suggested = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:80].strip() or "document"
    destination, selected = QFileDialog.getSaveFileName(parent or mw, t("imports_export_document"),
        suggested + ".html", ";;".join(choices))
    if not destination or paths.get_active_profile() != profile or mw.col is not collection or not is_current():
        return
    format = choices.get(selected, "html")
    target = Path(destination)
    if target.suffix.casefold() != "." + format:
        target = target.with_suffix("." + format)
        # Ask the native picker about overwriting the actual output filename.
        if target.exists():
            destination, _ = QFileDialog.getSaveFileName(parent or mw, t("imports_export_document"),
                str(target), next(key for key, value in choices.items() if value == format))
            if not destination:
                return
            target = Path(destination)

    def current():
        return paths.get_active_profile() == profile and mw.col is collection

    def write():
        data = markdown_manager.export_markdown_document(addon_dir, profile, filename, format, title=title)
        if not current():
            raise RuntimeError(t("imports_markdown_cancelled"))
        if target.is_symlink():
            raise ValueError(t("imports_markdown_invalid_file"))
        descriptor, temporary = tempfile.mkstemp(prefix=".incremento-export-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if not current():
                raise RuntimeError(t("imports_markdown_cancelled"))
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    def done(future):
        if not current() or not is_current():
            return
        try:
            future.result()
            tooltip(t("imports_export_document_saved"))
        except Exception as exc:
            showInfo(t("imports_markdown_failed", error=str(exc)), textFormat="plain")

    try:
        mw.taskman.run_in_background(write, done, uses_collection=False)
    except Exception as exc:
        showInfo(t("imports_markdown_failed", error=str(exc)), textFormat="plain")
