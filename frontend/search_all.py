"""Search ALL dialog — searches PDF/EPUB highlights, sources, content, and cards."""

from __future__ import annotations

import os
import re
from html import escape
from urllib.parse import parse_qs, quote, urlparse

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    Qt,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.db import (
        get_connection,
        search_note_ocr_index,
        search_epub_text_index,
        replace_pdf_text_index,
        search_pdf_text_index,
        search_text_match_score,
        split_search_terms,
    )
    from ..backend.epub_manager import EPUB_NOTE_TYPE, load_epub_metadata
    from ..backend.pdf_manager import PDF_NOTE_TYPE, extract_pdf_pages_text, pdf_storage_abspath
except ImportError:
    from db import (  # type: ignore
        get_connection,
        search_note_ocr_index,
        search_epub_text_index,
        replace_pdf_text_index,
        search_pdf_text_index,
        search_text_match_score,
        split_search_terms,
    )
    from epub_manager import EPUB_NOTE_TYPE, load_epub_metadata  # type: ignore
    from pdf_manager import PDF_NOTE_TYPE, extract_pdf_pages_text, pdf_storage_abspath  # type: ignore


_ADDON_PKG = __name__.split(".")[0]
_MIN_SEARCH_CHARS = 3
_SEARCH_WHILE_TYPING_CONFIG_KEY = "search_all_search_while_typing"
_SEARCH_ALL_FILTER_CONFIG_KEYS = {
    "pdf_highlights": "search_all_filter_pdf_highlights",
    "epub_highlights": "search_all_filter_epub_highlights",
    "pdf_sources": "search_all_filter_pdf_sources",
    "epub_sources": "search_all_filter_epub_sources",
    "pdf_content": "search_all_filter_pdf_content",
    "epub_content": "search_all_filter_epub_content",
    "image_ocr": "search_all_filter_image_ocr",
    "cards": "search_all_filter_cards",
    "current_profile": "search_all_filter_current_profile",
}
_SEARCH_ALL_FILTER_DEFAULTS = {
    "pdf_highlights": True,
    "epub_highlights": True,
    "pdf_sources": True,
    "epub_sources": True,
    "pdf_content": False,
    "epub_content": True,
    "image_ocr": True,
    "cards": True,
    "current_profile": True,
}


def _config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        return mw.addonManager.getConfig(_ADDON_PKG) or {}
    except Exception:
        return {}


def configured_search_all_search_while_typing(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get(_SEARCH_WHILE_TYPING_CONFIG_KEY, True))


def _set_search_all_search_while_typing(enabled: bool) -> None:
    cfg = _config()
    cfg[_SEARCH_WHILE_TYPING_CONFIG_KEY] = bool(enabled)
    try:
        mw.addonManager.writeConfig(_ADDON_PKG, cfg)
    except Exception:
        return


def configured_search_all_filter_enabled(
    filter_id: str,
    config: dict | None = None,
) -> bool:
    cfg = _config(config)
    key = _SEARCH_ALL_FILTER_CONFIG_KEYS.get(filter_id)
    default = _SEARCH_ALL_FILTER_DEFAULTS.get(filter_id, True)
    if not key:
        return bool(default)
    return bool(cfg.get(key, default))


def _set_search_all_filter_enabled(filter_id: str, enabled: bool) -> None:
    key = _SEARCH_ALL_FILTER_CONFIG_KEYS.get(filter_id)
    if not key:
        return
    cfg = _config()
    cfg[key] = bool(enabled)
    try:
        mw.addonManager.writeConfig(_ADDON_PKG, cfg)
    except Exception:
        return


class _SearchAllDialog(QDialog):
    def __init__(self, parent=None, *, addon_dir: str, open_pdf_card, open_epub_card):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._open_pdf_card = open_pdf_card
        self._open_epub_card = open_epub_card
        self._current_profile_card_ids = self._load_current_profile_card_ids()
        self.setWindowTitle("Search ALL")
        self.resize(1280, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._search = self.__class__._make_search_box()
        search_row.addWidget(self._search, stretch=1)
        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._run_search)
        search_row.addWidget(self._search_btn)
        self._cb_search_while_typing = QCheckBox("Search while typing")
        self._cb_search_while_typing.setChecked(configured_search_all_search_while_typing())
        self._cb_search_while_typing.toggled.connect(self._on_search_while_typing_toggled)
        search_row.addWidget(self._cb_search_while_typing)
        layout.addLayout(search_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(16)
        self._cb_highlights = QCheckBox("PDF Highlights")
        self._cb_epub_highlights = QCheckBox("EPUB Highlights")
        self._cb_sources = QCheckBox("PDF Sources")
        self._cb_epub_sources = QCheckBox("EPUB Sources")
        self._cb_content = QCheckBox("PDF Content")
        self._cb_epub_content = QCheckBox("EPUB Content")
        self._cb_ocr = QCheckBox("Image OCR")
        self._cb_cards = QCheckBox("Cards")
        self._cb_current_profile = QCheckBox("Current Anki Profile Only")
        self._filter_checkboxes = {
            "pdf_highlights": self._cb_highlights,
            "epub_highlights": self._cb_epub_highlights,
            "pdf_sources": self._cb_sources,
            "epub_sources": self._cb_epub_sources,
            "pdf_content": self._cb_content,
            "epub_content": self._cb_epub_content,
            "image_ocr": self._cb_ocr,
            "cards": self._cb_cards,
        }
        for filter_id, cb in self._filter_checkboxes.items():
            cb.setChecked(configured_search_all_filter_enabled(filter_id))
            cb.toggled.connect(
                lambda checked, fid=filter_id: self._on_filter_toggled(fid, checked)
            )
            filter_row.addWidget(cb)
        self._cb_current_profile.setChecked(
            configured_search_all_filter_enabled("current_profile")
        )
        self._cb_current_profile.toggled.connect(
            lambda checked: self._on_filter_toggled("current_profile", checked)
        )
        filter_row.addWidget(self._cb_current_profile)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── Splitter: results (left) | preview (right) ────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._results = QTextBrowser()
        self._results.setOpenLinks(False)
        self._results.anchorClicked.connect(self._open_link)
        self._results.highlighted[QUrl].connect(self._on_hover)
        splitter.addWidget(self._results)

        # Right: preview panel
        preview_container = QWidget()
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        pc_layout.setSpacing(0)
        self._preview_header = QLabel("Preview")
        self._preview_header.setStyleSheet(
            "font-size:11px;color:#888;padding:4px 8px;"
            "background:#f5f5f5;border-bottom:1px solid #ddd;"
        )
        pc_layout.addWidget(self._preview_header)
        self._preview = QWebEngineView()
        pc_layout.addWidget(self._preview, stretch=1)
        splitter.addWidget(preview_container)

        splitter.setSizes([620, 560])
        layout.addWidget(splitter, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._search.textChanged.connect(self._on_search_text_changed)
        self._search.returnPressed.connect(self._run_search)
        self._update_search_button()
        self._show_search_hint()
        self._show_placeholder()

    @staticmethod
    def _make_search_box():
        from aqt.qt import QLineEdit
        w = QLineEdit()
        w.setPlaceholderText("Search PDFs, EPUBs, and cards...")
        return w

    def _query_text(self) -> str:
        return (self._search.text() or "").strip()

    def _query_ready(self) -> bool:
        return len(self._query_text()) >= _MIN_SEARCH_CHARS

    def _update_search_button(self) -> None:
        self._search_btn.setEnabled(self._query_ready())

    def _show_search_hint(self) -> None:
        self._results.setHtml(
            "<div style='color:#888;padding:10px'>"
            f"Type at least {_MIN_SEARCH_CHARS} characters to search.</div>"
        )

    def _show_manual_search_hint(self) -> None:
        self._results.setHtml(
            "<div style='color:#888;padding:10px'>Press Search to run the query.</div>"
        )

    def _on_search_text_changed(self, _text: str) -> None:
        self._update_search_button()
        if not self._query_ready():
            self._show_search_hint()
            return
        if self._cb_search_while_typing.isChecked():
            self._refresh(self._search.text())
        else:
            self._show_manual_search_hint()

    def _on_search_while_typing_toggled(self, enabled: bool) -> None:
        _set_search_all_search_while_typing(enabled)
        self._maybe_refresh_from_controls()

    def _on_filter_toggled(self, filter_id: str, enabled: bool) -> None:
        _set_search_all_filter_enabled(filter_id, enabled)
        self._maybe_refresh_from_controls()

    def _maybe_refresh_from_controls(self) -> None:
        self._update_search_button()
        if not self._query_ready():
            self._show_search_hint()
            return
        if self._cb_search_while_typing.isChecked():
            self._refresh(self._search.text())

    def _run_search(self) -> None:
        self._update_search_button()
        if not self._query_ready():
            self._show_search_hint()
            return
        self._refresh(self._search.text())

    @staticmethod
    def _snippet(text: str, q: str, max_len: int = 120) -> str:
        if not text:
            return ""
        plain = " ".join(text.split())
        if not q:
            return plain[:max_len]
        i = plain.lower().find(q.lower())
        if i < 0:
            for tok in split_search_terms(q):
                match = re.search(rf"(?i)\b{re.escape(tok)}\w*", plain)
                if match is not None:
                    i = match.start()
                    break
        if i < 0:
            return plain[:max_len]
        start = max(0, i - max_len // 3)
        end = min(len(plain), start + max_len)
        s = plain[start:end]
        if start > 0:
            s = "..." + s
        if end < len(plain):
            s = s + "..."
        return s

    @staticmethod
    def _load_current_profile_card_ids() -> set[int]:
        try:
            return {int(cid) for cid in mw.col.db.list("SELECT id FROM cards")}
        except Exception:
            return set()

    def _is_current_profile_card(self, card_id: int) -> bool:
        return int(card_id) in self._current_profile_card_ids

    def _filter_current_profile_rows(self, rows: list[tuple]) -> list[tuple]:
        if not self._cb_current_profile.isChecked():
            return rows
        out: list[tuple] = []
        for row in rows:
            try:
                if self._is_current_profile_card(row[0]):
                    out.append(row)
            except Exception:
                continue
        return out

    def _safe_find_notes(self, query: str) -> list[int]:
        try:
            return mw.col.find_notes(query)
        except Exception:
            pass
        escaped = query.replace('"', r"\"")
        try:
            return mw.col.find_notes(f'"{escaped}"')
        except Exception:
            return []

    def _pdf_title(self, card_id: int) -> str:
        try:
            card = mw.col.get_card(card_id)
            note = mw.col.get_note(card.nid)
            return note.fields[0] if note.fields else f"PDF card {card_id}"
        except Exception:
            return f"PDF card {card_id}"

    def _epub_title(self, card_id: int) -> str:
        try:
            card = mw.col.get_card(card_id)
            note = mw.col.get_note(card.nid)
            return note.fields[0] if note.fields else f"EPUB card {card_id}"
        except Exception:
            return f"EPUB card {card_id}"

    def _candidate_pdf_card_ids(self) -> list[int]:
        cids: set[int] = set()
        try:
            cids.update(mw.col.find_cards(f'note:"{PDF_NOTE_TYPE}"'))
        except Exception:
            pass
        try:
            cids.update(mw.col.find_cards("PDF_Filename:*"))
        except Exception:
            pass
        try:
            rows = (
                get_connection(self._addon_dir, _active_profile())
                .execute("SELECT DISTINCT card_id FROM pdf_highlights")
                .fetchall()
            )
            cids.update(int(r[0]) for r in rows)
        except Exception:
            pass
        try:
            rows = (
                get_connection(self._addon_dir, _active_profile())
                .execute("SELECT DISTINCT card_id FROM pdf_progress")
                .fetchall()
            )
            cids.update(int(r[0]) for r in rows)
        except Exception:
            pass
        if self._cb_current_profile.isChecked():
            cids = {cid for cid in cids if self._is_current_profile_card(cid)}
        return sorted(cids)

    def _search_pdf_file_hits(
        self, q: str, limit: int = 120
    ) -> list[tuple[int, int, str]]:
        """Search SQLite-backed PDF page-text index; build missing index on demand."""
        search_limit = limit * 10 if self._cb_current_profile.isChecked() else limit
        hits = search_pdf_text_index(self._addon_dir, _active_profile(), q, limit=search_limit)
        hits = self._filter_current_profile_rows(hits)
        if hits:
            return [
                (cid, page, self._snippet(text or "", q, max_len=180))
                for cid, page, text in hits[:limit]
            ]

        for cid in self._candidate_pdf_card_ids():
            try:
                card = mw.col.get_card(cid)
                note = mw.col.get_note(card.nid)
                filename = note["PDF_Filename"]
                pdf_path = pdf_storage_abspath(filename)
                page_texts = extract_pdf_pages_text(pdf_path)
                replace_pdf_text_index(self._addon_dir, _active_profile(), cid, page_texts)
            except Exception:
                continue

        hits = search_pdf_text_index(self._addon_dir, _active_profile(), q, limit=search_limit)
        hits = self._filter_current_profile_rows(hits)
        return [
            (cid, page, self._snippet(text or "", q, max_len=180))
            for cid, page, text in hits[:limit]
        ]

    def _search_epub_file_hits(
        self, q: str, limit: int = 120
    ) -> list[tuple[int, int, str, str]]:
        search_limit = limit * 10 if self._cb_current_profile.isChecked() else limit
        hits = search_epub_text_index(self._addon_dir, _active_profile(), q, limit=search_limit)
        hits = self._filter_current_profile_rows(hits)
        return [
            (cid, section_index, title, self._snippet(text or title or "", q, max_len=180))
            for cid, section_index, title, text in hits[:limit]
        ]

    def _refresh(self, query: str) -> None:
        q = (query or "").strip()
        if len(q) < _MIN_SEARCH_CHARS:
            self._show_search_hint()
            return

        html = ["<div style='font-family:sans-serif'>"]
        total = 0

        def _score_text(text: str):
            return search_text_match_score(text or "", q)

        def _rank_rows(rows: list[tuple], *, text_index: int, limit: int = 120) -> list[tuple]:
            ranked: list[tuple[tuple[int, int, int, int], tuple]] = []
            for row in rows:
                score = _score_text(row[text_index] or "")
                if score is None:
                    continue
                ranked.append((score, row))
            ranked.sort(key=lambda item: (item[0],) + tuple(item[1][:2]))
            return [row for _, row in ranked[:limit]]

        # PDF highlights (go directly to page)
        if self._cb_highlights.isChecked():
            try:
                rows = (
                    get_connection(self._addon_dir, _active_profile())
                    .execute(
                        "SELECT card_id, page, text FROM pdf_highlights ORDER BY card_id, page"
                    )
                    .fetchall()
                )
                rows = self._filter_current_profile_rows(rows)
                rows = _rank_rows(rows, text_index=2)
            except Exception:
                rows = []

            if rows:
                html.append("<h3>PDF Highlights</h3>")
                by_file: dict = {}
                for cid, page, text in rows:
                    by_file.setdefault(cid, []).append((page, text))
                for cid, pages in by_file.items():
                    title = escape(self._pdf_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for page, text in pages:
                        snippet = escape(self._snippet(text or "", q))
                        html.append(
                            f"<li><a href='inc://pdf/{cid}/{int(page)}?q={quote(q)}'>Page {int(page)}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        # Cards created from PDF pages (go to page)
        if self._cb_sources.isChecked():
            try:
                rows = (
                    get_connection(self._addon_dir, _active_profile())
                    .execute(
                        "SELECT pdf_card_id, page, excerpt FROM pdf_card_sources ORDER BY id DESC"
                    )
                    .fetchall()
                )
                rows = self._filter_current_profile_rows(rows)
                rows = _rank_rows(rows, text_index=2)
            except Exception:
                rows = []

            if rows:
                html.append("<h3>PDF Sources</h3>")
                by_file: dict = {}
                for cid, page, excerpt in rows:
                    by_file.setdefault(cid, []).append((page, excerpt))
                for cid, pages in by_file.items():
                    title = escape(self._pdf_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for page, excerpt in pages:
                        snippet = escape(self._snippet(excerpt or "", q))
                        html.append(
                            f"<li><a href='inc://pdf/{cid}/{int(page)}?q={quote(q)}'>Page {int(page)}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        if self._cb_epub_highlights.isChecked():
            try:
                rows = (
                    get_connection(self._addon_dir, _active_profile())
                    .execute(
                        "SELECT card_id, section_index, text FROM epub_highlights ORDER BY card_id, section_index"
                    )
                    .fetchall()
                )
                rows = self._filter_current_profile_rows(rows)
                rows = _rank_rows(rows, text_index=2)
            except Exception:
                rows = []

            if rows:
                html.append("<h3>EPUB Highlights</h3>")
                by_file: dict = {}
                for cid, section_index, text in rows:
                    by_file.setdefault(cid, []).append((section_index, text))
                for cid, entries in by_file.items():
                    title = escape(self._epub_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for section_index, text in entries:
                        snippet = escape(self._snippet(text or "", q))
                        html.append(
                            f"<li><a href='inc://epub/{cid}/{int(section_index)}?q={quote(q)}'>Section {int(section_index) + 1}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        if self._cb_epub_sources.isChecked():
            try:
                rows = (
                    get_connection(self._addon_dir, _active_profile())
                    .execute(
                        "SELECT epub_card_id, section_index, excerpt FROM epub_card_sources ORDER BY id DESC"
                    )
                    .fetchall()
                )
                rows = self._filter_current_profile_rows(rows)
                rows = _rank_rows(rows, text_index=2)
            except Exception:
                rows = []

            if rows:
                html.append("<h3>EPUB Sources</h3>")
                by_file: dict = {}
                for cid, section_index, excerpt in rows:
                    by_file.setdefault(cid, []).append((section_index, excerpt))
                for cid, entries in by_file.items():
                    title = escape(self._epub_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for section_index, excerpt in entries:
                        snippet = escape(self._snippet(excerpt or "", q))
                        html.append(
                            f"<li><a href='inc://epub/{cid}/{int(section_index)}?q={quote(q)}'>Section {int(section_index) + 1}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        # Actual PDF file text (page-level)
        if self._cb_content.isChecked():
            pdf_page_hits = self._search_pdf_file_hits(q, limit=120)
            if pdf_page_hits:
                html.append("<h3>PDF File Content</h3>")
                by_file: dict = {}
                for cid, page, snippet_text in pdf_page_hits:
                    by_file.setdefault(cid, []).append((page, snippet_text))
                for cid, pages in by_file.items():
                    title = escape(self._pdf_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for page, snippet_text in pages:
                        snippet = escape(snippet_text)
                        html.append(
                            f"<li><a href='inc://pdf/{cid}/{int(page)}?q={quote(q)}'>Page {int(page)}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        if self._cb_epub_content.isChecked():
            epub_section_hits = self._search_epub_file_hits(q, limit=120)
            if epub_section_hits:
                html.append("<h3>EPUB File Content</h3>")
                by_file: dict = {}
                for cid, section_index, title, snippet_text in epub_section_hits:
                    by_file.setdefault(cid, []).append((section_index, title, snippet_text))
                for cid, entries in by_file.items():
                    title = escape(self._epub_title(cid))
                    html.append(f"<div style='margin:6px 0 2px'><b>{title}</b></div><ul style='margin:0 0 6px 16px'>")
                    for section_index, section_title, snippet_text in entries:
                        snippet = escape(snippet_text)
                        section_label = escape(section_title or f"Section {int(section_index) + 1}")
                        html.append(
                            f"<li><a href='inc://epub/{cid}/{int(section_index)}?q={quote(q)}'>{section_label}</a>"
                            f" — <span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    html.append("</ul>")

        if self._cb_ocr.isChecked():
            search_limit = 1200 if self._cb_current_profile.isChecked() else 120
            ocr_hits = search_note_ocr_index(
                self._addon_dir,
                _active_profile(),
                q,
                limit=search_limit,
            )
            if self._cb_current_profile.isChecked():
                ocr_hits = [
                    row for row in ocr_hits if self._is_current_profile_card(int(row[1]))
                ]
            if ocr_hits:
                html.append("<h3>Image OCR</h3><ul>")
                for note_id, card_id, image_name, text in ocr_hits[:120]:
                    try:
                        note = mw.col.get_note(note_id)
                        model = mw.col.models.get(note.mid)
                        model_name = escape(model.get("name", "Note") if model else "Note")
                    except Exception:
                        model_name = "Note"
                    snippet = escape(self._snippet(text or "", q, max_len=180))
                    image_label = escape(image_name or "OCR text")
                    html.append(
                        f"<li><a href='inc://card/{note_id}'>{model_name} — note {int(note_id)}</a>"
                        f"<br><span style='color:#888'>{image_label}: {snippet}</span></li>"
                    )
                    total += 1
                html.append("</ul>")

        # All cards/notes (open in Browser)
        if self._cb_cards.isChecked():
            note_ids = self._safe_find_notes(q)
            if note_ids:
                ranked_notes: list[tuple[tuple[int, int, int, int], int, object, str]] = []
                for nid in note_ids:
                    try:
                        note = mw.col.get_note(nid)
                        model = mw.col.models.get(note.mid)
                        model_name = model.get("name") if model else "Note"
                        text = " ".join(note.fields or [])
                        score = _score_text(text)
                        if score is None:
                            continue
                        ranked_notes.append((score, int(nid), note, model_name))
                    except Exception:
                        continue
                ranked_notes.sort(key=lambda item: (item[0], item[1]))
                html.append("<h3>Cards</h3><ul>")
                for _, nid, note, model_name in ranked_notes[:160]:
                    text = " ".join((note.fields or [])[:2])
                    snippet = escape(self._snippet(text, q))
                    html.append(
                        f"<li><a href='inc://card/{nid}'>{escape(model_name)} — note {nid}</a>"
                        f"<br><span style='color:#888'>{snippet}</span></li>"
                    )
                    total += 1
                html.append("</ul>")

        if total == 0:
            html.append("<div style='color:#888;padding:8px'>No matches found.</div>")
        html.append("</div>")
        self._results.setHtml("".join(html))

    # ── Preview panel ─────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        self._preview_header.setText("Preview")
        self._preview.setHtml(
            "<html><body style='font-family:sans-serif;color:#aaa;"
            "padding:24px;font-size:13px'>Hover over a result to preview.</body></html>"
        )

    def _on_hover(self, url) -> None:
        # Qt6: highlighted emits QUrl; Qt5 emits str — handle both
        url_str = url.toString() if hasattr(url, "toString") else str(url)
        if not url_str:
            return
        try:
            if url_str.startswith("inc://pdf/"):
                parsed = urlparse(url_str)
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    cid, page = int(parts[0]), int(parts[1])
                    q = (parse_qs(parsed.query).get("q") or [""])[0]
                    self._preview_pdf_page(cid, page, q)
            elif url_str.startswith("inc://epub/"):
                parsed = urlparse(url_str)
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    cid, section_index = int(parts[0]), int(parts[1])
                    q = (parse_qs(parsed.query).get("q") or [""])[0]
                    self._preview_epub_section(cid, section_index, q)
            elif url_str.startswith("inc://card/"):
                nid = int(url_str.rsplit("/", 1)[1])
                self._preview_card(nid)
        except Exception:
            pass

    def _highlight_terms(self, text: str, q: str) -> str:
        """Return HTML-escaped text with query tokens wrapped in <mark>."""
        out = escape(text)
        if not q:
            return out
        for tok in split_search_terms(q):
            out = re.sub(
                rf"(?i)\b({re.escape(escape(tok))}\w*)",
                r"<mark style='background:#ffe08a'>\1</mark>",
                out,
            )
        return out

    def _preview_pdf_page(self, cid: int, page: int, q: str) -> None:
        title = self._pdf_title(cid)
        try:
            row = (
                get_connection(self._addon_dir, _active_profile())
                .execute(
                    "SELECT text FROM pdf_text_index WHERE card_id=? AND page=?",
                    (cid, page),
                )
                .fetchone()
            )
            text = (row[0] or "") if row else ""
        except Exception:
            text = ""

        body = self._highlight_terms(text, q) if text else "<i style='color:#aaa'>No text index for this page.</i>"
        self._preview_header.setText(f"PDF: {title} — Page {page}")
        self._preview.setHtml(
            f"<html><body style='font-family:sans-serif;font-size:13px;"
            f"padding:14px;line-height:1.6;white-space:pre-wrap'>{body}</body></html>"
        )

    def _preview_card(self, nid: int) -> None:
        try:
            note = mw.col.get_note(nid)
            model = mw.col.models.get(note.mid)
            model_name = escape(model.get("name", "Note") if model else "Note")
            fld_names = [f.get("name", "") for f in (model.get("flds") or [])] if model else []
            rows = ""
            for i, fval in enumerate(note.fields):
                fname = escape(fld_names[i]) if i < len(fld_names) else f"Field {i}"
                rows += (
                    f"<div style='margin-bottom:10px'>"
                    f"<div style='font-size:11px;color:#888;margin-bottom:2px'>{fname}</div>"
                    f"<div>{fval}</div></div>"
                )
            self._preview_header.setText(f"Card: {model_name} — note {nid}")
            self._preview.setHtml(
                f"<html><body style='font-family:sans-serif;font-size:13px;padding:14px'>"
                f"{rows}</body></html>"
            )
        except Exception:
            pass

    def _preview_epub_section(self, cid: int, section_index: int, q: str) -> None:
        title = self._epub_title(cid)
        try:
            row = (
                get_connection(self._addon_dir, _active_profile())
                .execute(
                    "SELECT title, text FROM epub_text_index WHERE card_id=? AND section_index=?",
                    (cid, section_index),
                )
                .fetchone()
            )
            section_title = str((row[0] or "") if row else "")
            text = str((row[1] or "") if row else "")
        except Exception:
            section_title = ""
            text = ""

        body = self._highlight_terms(text or section_title, q) if (text or section_title) else "<i style='color:#aaa'>No text index for this section.</i>"
        label = section_title or f"Section {section_index + 1}"
        self._preview_header.setText(f"EPUB: {title} — {label}")
        self._preview.setHtml(
            f"<html><body style='font-family:sans-serif;font-size:13px;"
            f"padding:14px;line-height:1.6;white-space:pre-wrap'>{body}</body></html>"
        )

    def _open_link(self, qurl) -> None:
        s = qurl.toString()
        try:
            if s.startswith("inc://pdf/"):
                parsed = urlparse(s)
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    cid = int(parts[0])
                    page = int(parts[1])
                    q = (parse_qs(parsed.query).get("q") or [""])[0]
                    self._open_pdf_card(cid, page, search_query=q)
                return
            if s.startswith("inc://epub/"):
                parsed = urlparse(s)
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    cid = int(parts[0])
                    section_index = int(parts[1])
                    q = (parse_qs(parsed.query).get("q") or [""])[0]
                    self._open_epub_card(cid, section_index, search_query=q)
                return
            if s.startswith("inc://card/"):
                nid = int(s.rsplit("/", 1)[1])
                from aqt import dialogs

                b = dialogs.open("Browser", mw)
                b.search_for(f"nid:{nid}")
                return
        except Exception as e:
            from aqt.utils import showInfo
            showInfo(f"Could not open result:\n{e}")
