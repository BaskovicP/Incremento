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
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t

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
                title = pdf_display_label_from_filename(stored_filename, fallback=t("reader_pdf_number", number=note_id))
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
    ) or t("reader_none")
    return "\n".join(
        [
            t("reader_notebook_highlights_count", count=int(counts.get('highlights') or 0)),
            t("reader_notebook_notes_count", count=int(counts.get('notes') or 0)),
            t("reader_notebook_page_entries_count", count=int(counts.get('page_entries') or 0)),
            t("reader_notebook_location_entries_count", count=int(counts.get('location_only_entries') or 0)),
            t("reader_notebook_colors", colors=color_summary),
        ]
    )


def _format_import_summary(report: dict[str, object]) -> str:
    def _entry_line(entry: dict[str, object]) -> str:
        parts = [f"#{int(entry.get('ordinal') or 0)}"]
        page = entry.get("page")
        location = entry.get("location")
        if page is not None:
            parts.append(t("reader_page_number", page=page))
        if location is not None:
            parts.append(t("reader_notebook_location", number=location))
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
    lines.append(t("reader_notebook_file", filename=os.path.basename(str(report.get('notebook_path') or ''))))
    lines.append(_format_preview_counts(counts))
    lines.append("")
    for pdf_report in report.get("pdfs") or []:
        title = str(pdf_report.get("title") or t("reader_card_number", number=pdf_report.get('card_id')))
        stored_filename = str(pdf_report.get("stored_filename") or "").strip()
        lines.append(f"{title}")
        if stored_filename:
            lines.append("  " + t("reader_notebook_pdf_file", filename=stored_filename))
        lines.append("  " + t("reader_notebook_created", count=int(pdf_report.get('created') or 0)))
        lines.append("  " + t("reader_notebook_updated", count=int(pdf_report.get('updated') or 0)))
        lines.append("  " + t("reader_notebook_notes_attached", count=int(pdf_report.get('notes_attached') or 0)))
        lines.append("  " + t("reader_notebook_unmatched", count=int(pdf_report.get('unmatched_highlights') or 0)))
        lines.append("  " + t("reader_notebook_unattached", count=int(pdf_report.get('unattached_notes') or 0)))
        unmatched_entries = list(pdf_report.get("unmatched_highlight_entries") or [])
        if unmatched_entries:
            lines.append("  " + t("reader_notebook_unmatched_heading"))
            for entry in unmatched_entries:
                lines.append(_entry_line(entry))
        unattached_entries = list(pdf_report.get("unattached_note_entries") or [])
        if unattached_entries:
            lines.append("  " + t("reader_notebook_unattached_heading"))
            for entry in unattached_entries:
                lines.append(_entry_line(entry))
        if pdf_report.get("no_searchable_text"):
            lines.append("  " + t("reader_notebook_no_pdf_text"))
        read_error = str(pdf_report.get("read_error") or "").strip()
        if read_error:
            lines.append("  " + t("reader_notebook_pdf_read_error", error=read_error))
        lines.append("")
    return "\n".join(lines).strip()


class NotebookCitationImportDialog(QDialog):
    def __init__(self, addon_dir: str, parent=None):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._notebook_path = ""
        self._parsed_entries: list[dict[str, object]] = []
        self._pdf_entries = _load_pdf_card_entries()

        self.setWindowTitle(t("reader_notebook_import_title"))
        self.resize(760, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        file_row = QHBoxLayout()
        file_label = QLabel(t("reader_notebook_html"))
        file_label.setMinimumWidth(96)
        self._path_edit = QLineEdit(self)
        self._path_edit.setReadOnly(True)
        browse_btn = QPushButton(t("reader_choose"), self)
        qconnect(browse_btn.clicked, self._choose_file)
        file_row.addWidget(file_label)
        file_row.addWidget(self._path_edit, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        self._counts_browser = QTextBrowser(self)
        self._counts_browser.setMaximumHeight(120)
        self._counts_browser.setPlainText(t("reader_notebook_choose_intro"))
        layout.addWidget(self._counts_browser)

        filter_row = QHBoxLayout()
        filter_label = QLabel(t("reader_pdf_cards"))
        filter_label.setMinimumWidth(96)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText(t("reader_notebook_filter_pdf_cards"))
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

        summary_label = QLabel(t("reader_notebook_import_summary"), self)
        summary_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(summary_label)

        self._summary_browser = QTextBrowser(self)
        self._summary_browser.setMinimumHeight(180)
        self._summary_browser.setPlainText(t("reader_notebook_no_import_yet"))
        layout.addWidget(self._summary_browser, 1)

        buttons = QDialogButtonBox(parent=self)
        self._import_btn = buttons.addButton(t("reader_import"), QDialogButtonBox.ButtonRole.AcceptRole)
        self._close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self._close_btn.setText(t("reader_close"))
        self._import_btn.setEnabled(False)
        qconnect(self._import_btn.clicked, self._run_import)
        qconnect(self._close_btn.clicked, self.reject)
        layout.addWidget(buttons)

        self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        for entry in self._pdf_entries:
            label = str(entry.get("title") or t("reader_card_number", number=entry.get('card_id')))
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
            t("reader_notebook_no_matching_pdf")
            if visible == 0 and self._pdf_entries
            else (t("reader_notebook_no_existing_pdf") if not self._pdf_entries else "")
        )

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("reader_notebook_choose_html"),
            "",
            t("reader_notebook_html_files") + ";;" + t("reader_all_files"),
        )
        if not path:
            return
        self._notebook_path = path
        self._path_edit.setText(path)
        try:
            self._parsed_entries = parse_notebook_file(path)
        except Exception as exc:
            self._parsed_entries = []
            self._counts_browser.setPlainText(t("reader_notebook_parse_failed", error=exc))
            self._import_btn.setEnabled(False)
            return
        counts = summarize_notebook_entries(self._parsed_entries)
        self._counts_browser.setPlainText(_format_preview_counts(counts))
        self._summary_browser.setPlainText(t("reader_notebook_ready"))
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
            showInfo(t("reader_notebook_choose_first"))
            return
        selected_cards = self._selected_cards()
        if not selected_cards:
            showInfo(t("reader_notebook_select_pdf_first"))
            return
        if not has_pymupdf():
            showInfo(t("reader_notebook_pymupdf_required"))
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
            showInfo(t("reader_notebook_import_failed", error=exc))
            return
        self._summary_browser.setPlainText(_format_import_summary(report))
