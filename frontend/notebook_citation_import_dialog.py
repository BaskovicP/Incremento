from __future__ import annotations

import os

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    Qt,
    qconnect,
)
from aqt.utils import showInfo

try:
    from ..backend.deps import has_pymupdf
    from ..backend.notebook_citations import (
        import_notebook_citations,
        parse_notebook_file,
        summarize_notebook_entries,
    )
    from ..backend.paths import get_active_profile as _active_profile
    from ..backend.pdf_manager import PDF_NOTE_TYPE, pdf_display_label_from_filename
except ImportError:
    from deps import has_pymupdf  # type: ignore
    from notebook_citations import import_notebook_citations, parse_notebook_file, summarize_notebook_entries  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore
    from pdf_manager import PDF_NOTE_TYPE, pdf_display_label_from_filename  # type: ignore


def _load_pdf_card_entries(collection=None) -> list[dict[str, object]]:
    col = collection or mw.col
    entries: list[dict[str, object]] = []
    if col is None:
        return entries
    try:
        note_ids = col.find_notes(f'note:"{PDF_NOTE_TYPE}" -is:suspended')
    except Exception:
        return entries
    for note_id in note_ids:
        try:
            note = col.get_note(note_id)
            card_ids = col.find_cards(f"nid:{int(note_id)}")
            if not card_ids:
                continue
            title = str(note["Title"] or "").strip()
            stored_filename = str(note["PDF_Filename"] or "").strip()
            if not title:
                title = pdf_display_label_from_filename(stored_filename, fallback=f"PDF {note_id}")
            entries.append(
                {
                    "card_id": int(card_ids[0]),
                    "title": title,
                    "stored_filename": stored_filename,
                }
            )
        except Exception:
            continue
    return sorted(entries, key=lambda entry: str(entry.get("title") or "").casefold())


def _format_preview_counts(counts: dict[str, object]) -> str:
    colors = counts.get("colors") or {}
    color_summary = ", ".join(
        f"{name}: {value}" for name, value in sorted(colors.items())
    ) or "none"
    return "\n".join(
        [
            f"Highlights: {int(counts.get('highlights') or 0)}",
            f"Notes: {int(counts.get('notes') or 0)}",
            f"Page-backed entries: {int(counts.get('page_entries') or 0)}",
            f"Location-only entries: {int(counts.get('location_only_entries') or 0)}",
            f"Colors: {color_summary}",
        ]
    )


def _format_import_summary(report: dict[str, object]) -> str:
    def _entry_line(entry: dict[str, object]) -> str:
        parts = [f"#{int(entry.get('ordinal') or 0)}"]
        page = entry.get("page")
        location = entry.get("location")
        if page is not None:
            parts.append(f"Page {page}")
        if location is not None:
            parts.append(f"Location {location}")
        section = str(entry.get("section") or "").strip()
        if section:
            parts.append(section)
        label = " · ".join(parts)
        text = " ".join(str(entry.get("text") or "").split())
        if len(text) > 180:
            text = text[:180].rstrip() + "..."
        return f"    - {label}: {text}"

    lines = []
    counts = report.get("entry_counts") or {}
    lines.append(f"Notebook: {os.path.basename(str(report.get('notebook_path') or ''))}")
    lines.append(_format_preview_counts(counts))
    lines.append("")
    for pdf_report in report.get("pdfs") or []:
        title = str(pdf_report.get("title") or f"Card {pdf_report.get('card_id')}")
        stored_filename = str(pdf_report.get("stored_filename") or "").strip()
        lines.append(f"{title}")
        if stored_filename:
            lines.append(f"  File: {stored_filename}")
        lines.append(f"  Highlights created: {int(pdf_report.get('created') or 0)}")
        lines.append(f"  Highlights updated: {int(pdf_report.get('updated') or 0)}")
        lines.append(f"  Notes attached: {int(pdf_report.get('notes_attached') or 0)}")
        lines.append(f"  Highlights not matched: {int(pdf_report.get('unmatched_highlights') or 0)}")
        lines.append(f"  Notes not attached: {int(pdf_report.get('unattached_notes') or 0)}")
        unmatched_entries = list(pdf_report.get("unmatched_highlight_entries") or [])
        if unmatched_entries:
            lines.append("  Unmatched highlights:")
            for entry in unmatched_entries:
                lines.append(_entry_line(entry))
        unattached_entries = list(pdf_report.get("unattached_note_entries") or [])
        if unattached_entries:
            lines.append("  Unattached notes:")
            for entry in unattached_entries:
                lines.append(_entry_line(entry))
        if pdf_report.get("no_searchable_text"):
            lines.append("  No searchable PDF text was found.")
        read_error = str(pdf_report.get("read_error") or "").strip()
        if read_error:
            lines.append(f"  PDF read error: {read_error}")
        lines.append("")
    return "\n".join(lines).strip()


class NotebookCitationImportDialog(QDialog):
    def __init__(self, addon_dir: str, parent=None):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._notebook_path = ""
        self._parsed_entries: list[dict[str, object]] = []
        self._pdf_entries = _load_pdf_card_entries()

        self.setWindowTitle("Import Notebook Citations to PDF Highlights")
        self.resize(760, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        file_row = QHBoxLayout()
        file_label = QLabel("Notebook HTML")
        file_label.setMinimumWidth(96)
        self._path_edit = QLineEdit(self)
        self._path_edit.setReadOnly(True)
        browse_btn = QPushButton("Choose…", self)
        qconnect(browse_btn.clicked, self._choose_file)
        file_row.addWidget(file_label)
        file_row.addWidget(self._path_edit, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self._counts_browser = QTextBrowser(self)
        self._counts_browser.setMaximumHeight(120)
        self._counts_browser.setPlainText("Choose a Kindle Notebook HTML export to inspect its entries.")
        layout.addWidget(self._counts_browser)

        filter_row = QHBoxLayout()
        filter_label = QLabel("PDF cards")
        filter_label.setMinimumWidth(96)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText("Filter existing Incremento PDF cards…")
        qconnect(self._filter_edit.textChanged, self._apply_filter)
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self._filter_edit, 1)
        layout.addLayout(filter_row)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list, 1)

        self._empty_label = QLabel("", self)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: gray;")
        layout.addWidget(self._empty_label)

        summary_label = QLabel("Import summary", self)
        summary_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(summary_label)

        self._summary_browser = QTextBrowser(self)
        self._summary_browser.setMinimumHeight(180)
        self._summary_browser.setPlainText("No import has been run yet.")
        layout.addWidget(self._summary_browser, 1)

        buttons = QDialogButtonBox(parent=self)
        self._import_btn = buttons.addButton("Import", QDialogButtonBox.ButtonRole.AcceptRole)
        self._close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self._import_btn.setEnabled(False)
        qconnect(self._import_btn.clicked, self._run_import)
        qconnect(self._close_btn.clicked, self.reject)
        layout.addWidget(buttons)

        self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        for entry in self._pdf_entries:
            label = str(entry.get("title") or f"Card {entry.get('card_id')}")
            stored_filename = str(entry.get("stored_filename") or "").strip()
            item = QListWidgetItem(f"{label}  [{stored_filename}]")
            item.setData(Qt.ItemDataRole.UserRole, dict(entry))
            item.setToolTip(stored_filename)
            self._list.addItem(item)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = str(self._filter_edit.text() or "").strip().casefold()
        visible = 0
        for index in range(self._list.count()):
            item = self._list.item(index)
            entry = item.data(Qt.ItemDataRole.UserRole) or {}
            haystack = (
                f"{entry.get('title', '')} {entry.get('stored_filename', '')}"
            ).casefold()
            hide = bool(needle) and needle not in haystack
            item.setHidden(hide)
            if not hide:
                visible += 1
        self._empty_label.setText(
            "No Incremento PDF cards matched the current filter."
            if visible == 0 and self._pdf_entries
            else ("No existing Incremento PDF cards were found." if not self._pdf_entries else "")
        )

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Notebook HTML",
            "",
            "HTML files (*.html *.htm);;All files (*)",
        )
        if not path:
            return
        self._notebook_path = path
        self._path_edit.setText(path)
        try:
            self._parsed_entries = parse_notebook_file(path)
        except Exception as exc:
            self._parsed_entries = []
            self._counts_browser.setPlainText(f"Could not parse the selected Notebook HTML.\n\n{exc}")
            self._import_btn.setEnabled(False)
            return
        counts = summarize_notebook_entries(self._parsed_entries)
        self._counts_browser.setPlainText(_format_preview_counts(counts))
        self._summary_browser.setPlainText("Ready to import.")
        self._import_btn.setEnabled(bool(self._parsed_entries))

    def _selected_cards(self) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        for item in self._list.selectedItems():
            entry = item.data(Qt.ItemDataRole.UserRole) or {}
            if entry:
                selected.append(dict(entry))
        return selected

    def _run_import(self) -> None:
        if not self._notebook_path or not self._parsed_entries:
            showInfo("Choose a Notebook HTML export first.")
            return
        selected_cards = self._selected_cards()
        if not selected_cards:
            showInfo(
                "Select one or more existing Incremento PDF cards first. "
                "Import arbitrary PDFs separately as Incremento PDF cards, then run this import."
            )
            return
        if not has_pymupdf():
            showInfo("PyMuPDF is required for notebook citation import. Install it from Incremento -> Utils -> Check Dependencies…")
            return
        try:
            report = import_notebook_citations(
                self._addon_dir,
                _active_profile(),
                self._notebook_path,
                selected_cards,
                entries=self._parsed_entries,
            )
        except Exception as exc:
            showInfo(f"Could not import notebook citations.\n\n{exc}")
            return
        self._summary_browser.setPlainText(_format_import_summary(report))
