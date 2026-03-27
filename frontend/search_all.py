"""Search ALL dialog — searches PDF highlights, sources, content, and cards."""

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
    from ..backend.db import get_connection, replace_pdf_text_index, search_pdf_text_index
    from ..backend.pdf_manager import PDF_NOTE_TYPE, extract_pdf_pages_text, get_pdf_dir
except ImportError:
    from db import get_connection, replace_pdf_text_index, search_pdf_text_index  # type: ignore
    from pdf_manager import PDF_NOTE_TYPE, extract_pdf_pages_text, get_pdf_dir  # type: ignore


class _SearchAllDialog(QDialog):
    def __init__(self, parent=None, *, addon_dir: str, open_pdf_card):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._open_pdf_card = open_pdf_card
        self.setWindowTitle("Search ALL")
        self.resize(1280, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._search = self.__class__._make_search_box()
        layout.addWidget(self._search)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(16)
        self._cb_highlights = QCheckBox("PDF Highlights")
        self._cb_sources = QCheckBox("PDF Sources")
        self._cb_content = QCheckBox("PDF Content")
        self._cb_cards = QCheckBox("Cards")
        for cb in (self._cb_highlights, self._cb_sources, self._cb_content, self._cb_cards):
            cb.setChecked(True)
            cb.toggled.connect(lambda _: self._refresh(self._search.text()))
            filter_row.addWidget(cb)
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

        self._search.textChanged.connect(self._refresh)
        self._refresh("")
        self._show_placeholder()

    @staticmethod
    def _make_search_box():
        from aqt.qt import QLineEdit
        w = QLineEdit()
        w.setPlaceholderText("Search PDFs and cards...")
        return w

    @staticmethod
    def _snippet(text: str, q: str, max_len: int = 120) -> str:
        if not text:
            return ""
        plain = " ".join(text.split())
        if not q:
            return plain[:max_len]
        i = plain.lower().find(q.lower())
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
                get_connection(self._addon_dir)
                .execute("SELECT DISTINCT card_id FROM pdf_highlights")
                .fetchall()
            )
            cids.update(int(r[0]) for r in rows)
        except Exception:
            pass
        try:
            rows = (
                get_connection(self._addon_dir)
                .execute("SELECT DISTINCT card_id FROM pdf_progress")
                .fetchall()
            )
            cids.update(int(r[0]) for r in rows)
        except Exception:
            pass
        return sorted(cids)

    def _search_pdf_file_hits(
        self, q: str, limit: int = 120
    ) -> list[tuple[int, int, str]]:
        """Search SQLite-backed PDF page-text index; build missing index on demand."""
        hits = search_pdf_text_index(self._addon_dir, q, limit=limit)
        if hits:
            return [
                (cid, page, self._snippet(text or "", q, max_len=180))
                for cid, page, text in hits
            ]

        pdf_dir = get_pdf_dir()
        for cid in self._candidate_pdf_card_ids():
            try:
                card = mw.col.get_card(cid)
                note = mw.col.get_note(card.nid)
                filename = note["PDF_Filename"]
                pdf_path = os.path.join(pdf_dir, filename)
                page_texts = extract_pdf_pages_text(pdf_path)
                replace_pdf_text_index(self._addon_dir, cid, page_texts)
            except Exception:
                continue

        hits = search_pdf_text_index(self._addon_dir, q, limit=limit)
        return [
            (cid, page, self._snippet(text or "", q, max_len=180))
            for cid, page, text in hits
        ]

    def _refresh(self, query: str) -> None:
        q = (query or "").strip()
        if len(q) < 2:
            self._results.setHtml(
                "<div style='color:#888;padding:10px'>Type at least 2 characters to search.</div>"
            )
            return

        html = ["<div style='font-family:sans-serif'>"]
        total = 0

        def _normalize(s: str) -> str:
            return " ".join((s or "").casefold().split())

        q_norm = _normalize(q)
        q_tokens = [t for t in q_norm.split(" ") if len(t) >= 2]

        def _matches(text: str) -> bool:
            norm = _normalize(text)
            if q_norm and q_norm in norm:
                return True
            if not q_tokens:
                return False
            return all(tok in norm for tok in q_tokens)

        # PDF highlights (go directly to page)
        if self._cb_highlights.isChecked():
            try:
                rows = (
                    get_connection(self._addon_dir)
                    .execute(
                        "SELECT card_id, page, text FROM pdf_highlights ORDER BY card_id, page"
                    )
                    .fetchall()
                )
                rows = [r for r in rows if _matches(r[2] or "")][:120]
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
                    get_connection(self._addon_dir)
                    .execute(
                        "SELECT pdf_card_id, page, excerpt FROM pdf_card_sources ORDER BY id DESC"
                    )
                    .fetchall()
                )
                rows = [r for r in rows if _matches(r[2] or "")][:120]
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

        # All cards/notes (open in Browser)
        if self._cb_cards.isChecked():
            note_ids = self._safe_find_notes(q)
            if note_ids:
                html.append("<h3>Cards</h3><ul>")
                for nid in note_ids[:160]:
                    try:
                        note = mw.col.get_note(nid)
                        model = mw.col.models.get(note.mid)
                        model_name = model.get("name") if model else "Note"
                        text = " ".join((note.fields or [])[:2])
                        snippet = escape(self._snippet(text, q))
                        html.append(
                            f"<li><a href='inc://card/{nid}'>{escape(model_name)} — note {nid}</a>"
                            f"<br><span style='color:#888'>{snippet}</span></li>"
                        )
                        total += 1
                    except Exception:
                        pass
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
        for tok in q.split():
            if len(tok) >= 2:
                out = re.sub(
                    f"(?i)({re.escape(escape(tok))})",
                    r"<mark style='background:#ffe08a'>\1</mark>",
                    out,
                )
        return out

    def _preview_pdf_page(self, cid: int, page: int, q: str) -> None:
        title = self._pdf_title(cid)
        try:
            row = (
                get_connection(self._addon_dir)
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
            if s.startswith("inc://card/"):
                nid = int(s.rsplit("/", 1)[1])
                from aqt import dialogs

                b = dialogs.open("Browser", mw)
                b.search_for(f"nid:{nid}")
                return
        except Exception as e:
            from aqt.utils import showInfo
            showInfo(f"Could not open result:\n{e}")
