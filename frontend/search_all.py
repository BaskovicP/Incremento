"""Search ALL dialog — searches PDF/EPUB highlights, sources, content, and cards."""

from __future__ import annotations

import os
import re
import threading
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
from PyQt6.QtCore import QTimer, QUrl

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.activity_log import (
        cancel_activity,
        fail_activity,
        finish_activity,
        start_activity,
        update_activity,
    )
except ImportError:
    from activity_log import (  # type: ignore
        cancel_activity,
        fail_activity,
        finish_activity,
        start_activity,
        update_activity,
    )

try:
    from ..backend.db import (
        search_note_ocr_index,
        search_epub_text_index,
        search_pdf_text_index,
        search_text_match_score,
        split_search_terms,
    )
    from ..backend.config_service import load_addon_config, save_addon_config
    from ..backend.search_indexer import index_pdf_documents
    from ..backend.search_repository import (
        epub_section_text,
        pdf_candidate_card_ids,
        pdf_page_text,
        search_excerpt_rows,
    )
    from ..backend.epub_manager import EPUB_NOTE_TYPE, load_epub_metadata
    from ..backend.pdf_manager import PDF_NOTE_TYPE, pdf_storage_abspath
except ImportError:
    from db import (  # type: ignore
        search_note_ocr_index,
        search_epub_text_index,
        search_pdf_text_index,
        search_text_match_score,
        split_search_terms,
    )
    from config_service import load_addon_config, save_addon_config  # type: ignore
    from search_indexer import index_pdf_documents  # type: ignore
    from search_repository import (  # type: ignore
        epub_section_text,
        pdf_candidate_card_ids,
        pdf_page_text,
        search_excerpt_rows,
    )
    from epub_manager import EPUB_NOTE_TYPE, load_epub_metadata  # type: ignore
    from pdf_manager import PDF_NOTE_TYPE, pdf_storage_abspath  # type: ignore


_ADDON_PKG = __name__.split(".")[0]
_MIN_SEARCH_CHARS = 3
_SEARCH_DEBOUNCE_MS = 250
_MAX_CARD_SEARCH_CANDIDATES = 1000
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
        return load_addon_config(mw.addonManager, _ADDON_PKG)
    except Exception:
        return {}


def configured_search_all_search_while_typing(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get(_SEARCH_WHILE_TYPING_CONFIG_KEY, True))


def _set_search_all_search_while_typing(enabled: bool) -> None:
    cfg = _config()
    cfg[_SEARCH_WHILE_TYPING_CONFIG_KEY] = bool(enabled)
    try:
        save_addon_config(mw.addonManager, _ADDON_PKG, cfg)
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
        save_addon_config(mw.addonManager, _ADDON_PKG, cfg)
    except Exception:
        return


class _SearchAllDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        addon_dir: str,
        open_pdf_card,
        open_epub_card,
        initial_query: str = "",
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._open_pdf_card = open_pdf_card
        self._open_epub_card = open_epub_card
        # Runtime data is already per-profile. Cache only the bounded card IDs
        # encountered in results instead of loading every card in the
        # collection when the dialog opens.
        self._live_card_cache: dict[int, bool] = {}
        self._pdf_index_cancel = threading.Event()
        self._pdf_index_running = False
        self._pdf_index_attempted = False
        self._pdf_index_generation = 0
        self._pdf_index_activity_id = ""
        self._closed = False
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(
            lambda: self._refresh(self._query_text())
            if self._query_ready() and self._cb_search_while_typing.isChecked()
            else None
        )
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

        index_row = QHBoxLayout()
        self._pdf_index_status = QLabel("")
        self._pdf_index_status.setVisible(False)
        index_row.addWidget(self._pdf_index_status, stretch=1)
        self._pdf_index_cancel_btn = QPushButton("Cancel PDF indexing")
        self._pdf_index_cancel_btn.setVisible(False)
        self._pdf_index_cancel_btn.clicked.connect(self._cancel_pdf_index)
        index_row.addWidget(self._pdf_index_cancel_btn)
        layout.addLayout(index_row)

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
        initial_query = str(initial_query or "").strip()
        if initial_query:
            self._search.setText(initial_query)
            self._run_search()
        else:
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
            self._search_debounce.stop()
            self._show_search_hint()
            return
        if self._cb_search_while_typing.isChecked():
            self._search_debounce.start()
        else:
            self._search_debounce.stop()
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
        self._search_debounce.stop()
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

    def _is_current_profile_card(self, card_id: int) -> bool:
        cid = int(card_id)
        if cid in self._live_card_cache:
            return self._live_card_cache[cid]
        try:
            is_live = mw.col.get_card(cid) is not None
        except Exception:
            is_live = False
        self._live_card_cache[cid] = is_live
        return is_live

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

    def _candidate_pdf_card_ids(self, collection, profile: str) -> list[int]:
        cids: set[int] = set()
        try:
            cids.update(collection.find_cards(f'note:"{PDF_NOTE_TYPE}"'))
        except Exception:
            pass
        try:
            cids.update(collection.find_cards("PDF_Filename:*"))
        except Exception:
            pass
        try:
            cids.update(
                pdf_candidate_card_ids(self._addon_dir, profile)
            )
        except Exception:
            pass
        return sorted(cids)

    def _candidate_pdf_documents(
        self,
        collection,
        profile: str,
    ) -> list[tuple[int, str]]:
        documents: list[tuple[int, str]] = []
        for card_id in self._candidate_pdf_card_ids(collection, profile):
            try:
                card = collection.get_card(card_id)
                note = collection.get_note(card.nid)
                filename = str(note["PDF_Filename"] or "").strip()
                if filename:
                    path = pdf_storage_abspath(filename, profile=profile)
                    if path and os.path.isfile(path):
                        documents.append((card_id, path))
            except Exception:
                continue
        return documents

    def _request_pdf_index_cancel(self) -> None:
        self._pdf_index_cancel.set()
        self._pdf_index_status.setText("Stopping PDF indexing after the current file…")
        self._pdf_index_cancel_btn.setEnabled(False)

    def _cancel_pdf_index(self) -> None:
        if self._pdf_index_activity_id and cancel_activity(
            self._pdf_index_activity_id
        ):
            return
        self._request_pdf_index_cancel()

    def _retry_pdf_index(self, activity_id: str) -> None:
        if self._closed:
            raise RuntimeError("Search ALL is closed.")
        self._pdf_index_running = False
        self._pdf_index_attempted = False
        self._pdf_index_activity_id = str(activity_id or "")
        self._start_pdf_index()

    def _update_pdf_index_progress(
        self,
        generation: int,
        completed: int,
        total: int,
    ) -> None:
        if self._closed or generation != self._pdf_index_generation:
            return
        if self._pdf_index_activity_id:
            update_activity(
                self._pdf_index_activity_id,
                progress=(completed / total) if total > 0 else None,
                detail=f"Indexed {completed} of {total} PDFs",
            )
        self._pdf_index_status.setText(
            f"Indexing PDF text in the background… {completed}/{total}"
        )

    def _start_pdf_index(self) -> None:
        if self._pdf_index_running or self._pdf_index_attempted or self._closed:
            return
        self._pdf_index_attempted = True
        profile = _active_profile()
        self._pdf_index_running = True
        self._pdf_index_generation += 1
        generation = self._pdf_index_generation
        self._pdf_index_cancel = threading.Event()
        self._pdf_index_status.setText("Preparing the PDF index in the background…")
        self._pdf_index_status.setVisible(True)
        self._pdf_index_cancel_btn.setEnabled(True)
        self._pdf_index_cancel_btn.setVisible(True)
        if self._pdf_index_activity_id:
            update_activity(
                self._pdf_index_activity_id,
                progress=0,
                detail="Preparing the PDF index",
            )
        else:
            activity_ref: dict[str, str] = {}
            activity_id = start_activity(
                "Index PDF text",
                category="Search",
                detail="Preparing the PDF index",
                progress=0,
                cancel=self._request_pdf_index_cancel,
                retry=lambda: self._retry_pdf_index(activity_ref["activity_id"]),
            )
            activity_ref["activity_id"] = activity_id
            self._pdf_index_activity_id = activity_id

        def collected(documents: list[tuple[int, str]]) -> None:
            if generation != self._pdf_index_generation:
                return
            if self._closed or _active_profile() != profile:
                self._pdf_index_running = False
                cancel_activity(self._pdf_index_activity_id)
                return
            if self._pdf_index_cancel.is_set():
                self._pdf_index_running = False
                self._pdf_index_cancel_btn.setVisible(False)
                self._pdf_index_status.setText("PDF indexing cancelled.")
                cancel_activity(self._pdf_index_activity_id)
                return
            if not documents:
                self._pdf_index_running = False
                self._pdf_index_cancel_btn.setVisible(False)
                self._pdf_index_status.setText("No readable PDFs need indexing.")
                finish_activity(
                    self._pdf_index_activity_id,
                    detail="No readable PDFs needed indexing.",
                )
                return

            self._pdf_index_status.setText(
                f"Indexing PDF text in the background… 0/{len(documents)}"
            )
            self._run_pdf_file_index(
                documents,
                profile=profile,
                generation=generation,
            )

        def collection_failed(_exc: Exception) -> None:
            if generation != self._pdf_index_generation:
                return
            self._pdf_index_running = False
            self._pdf_index_cancel_btn.setVisible(False)
            if not self._closed:
                self._pdf_index_status.setText(
                    "Could not prepare the PDF index; existing indexed search remains available."
                )
            fail_activity(
                self._pdf_index_activity_id,
                "Could not prepare the PDF index. Existing indexed search is still available.",
            )

        from aqt.operations import QueryOp

        QueryOp(
            parent=self,
            op=lambda col: self._candidate_pdf_documents(col, profile),
            success=collected,
        ).failure(collection_failed).run_in_background()

    def _run_pdf_file_index(
        self,
        documents: list[tuple[int, str]],
        *,
        profile: str,
        generation: int,
    ) -> None:

        def progress(completed: int, total: int) -> None:
            mw.taskman.run_on_main(
                lambda c=completed, t=total: self._update_pdf_index_progress(
                    generation, c, t
                )
            )

        def task():
            return index_pdf_documents(
                self._addon_dir,
                profile,
                documents,
                cancelled=self._pdf_index_cancel.is_set,
                progress=progress,
            )

        def done(future) -> None:
            if generation != self._pdf_index_generation:
                return
            self._pdf_index_running = False
            self._pdf_index_cancel_btn.setVisible(False)
            if self._closed:
                return
            if _active_profile() != profile:
                self._pdf_index_status.setText(
                    "PDF indexing finished for the previously open profile."
                )
                return
            try:
                result = future.result()
            except Exception:
                self._pdf_index_status.setText("PDF indexing failed; indexed search remains available.")
                fail_activity(
                    self._pdf_index_activity_id,
                    "PDF indexing failed. Existing indexed search is still available.",
                )
                return
            if result.cancelled:
                self._pdf_index_status.setText("PDF indexing cancelled.")
                cancel_activity(self._pdf_index_activity_id)
            else:
                self._pdf_index_status.setText(
                    f"PDF index ready ({result.indexed} updated, {result.failed} failed)."
                )
                finish_activity(
                    self._pdf_index_activity_id,
                    detail=(
                        f"PDF index ready: {result.indexed} updated, "
                        f"{result.failed} failed."
                    ),
                )
                if self._query_ready() and self._cb_content.isChecked():
                    self._refresh(self._query_text())

        mw.taskman.run_in_background(task, done, uses_collection=False)

    def _search_pdf_file_hits(
        self, q: str, limit: int = 120
    ) -> list[tuple[int, int, str]]:
        """Search indexed PDF text and start any missing extraction off-thread."""
        search_limit = limit * 10 if self._cb_current_profile.isChecked() else limit
        hits = search_pdf_text_index(self._addon_dir, _active_profile(), q, limit=search_limit)
        hits = self._filter_current_profile_rows(hits)
        if hits:
            return [
                (cid, page, self._snippet(text or "", q, max_len=180))
                for cid, page, text in hits[:limit]
            ]

        self._start_pdf_index()
        return []

    def closeEvent(self, event) -> None:
        self._closed = True
        self._search_debounce.stop()
        if self._pdf_index_running:
            self._cancel_pdf_index()
        super().closeEvent(event)

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

        # PDF highlights (go directly to page)
        if self._cb_highlights.isChecked():
            try:
                rows = search_excerpt_rows(
                    self._addon_dir,
                    _active_profile(),
                    "pdf_highlights",
                    q,
                )
                rows = self._filter_current_profile_rows(rows)
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
                rows = search_excerpt_rows(
                    self._addon_dir,
                    _active_profile(),
                    "pdf_sources",
                    q,
                )
                rows = self._filter_current_profile_rows(rows)
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
                rows = search_excerpt_rows(
                    self._addon_dir,
                    _active_profile(),
                    "epub_highlights",
                    q,
                )
                rows = self._filter_current_profile_rows(rows)
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
                rows = search_excerpt_rows(
                    self._addon_dir,
                    _active_profile(),
                    "epub_sources",
                    q,
                )
                rows = self._filter_current_profile_rows(rows)
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
            note_ids = self._safe_find_notes(q)[:_MAX_CARD_SEARCH_CANDIDATES]
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
            text = pdf_page_text(
                self._addon_dir,
                _active_profile(),
                cid,
                page,
            )
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
            section_title, text = epub_section_text(
                self._addon_dir,
                _active_profile(),
                cid,
                section_index,
            )
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
