import json
import os
import re
import sys
import zipfile
from html import escape
from urllib.parse import quote, urlparse, parse_qs

from aqt import mw, gui_hooks
from aqt.utils import showInfo, tooltip
from aqt.qt import (
    QAction,
    QMenu,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QDockWidget,
    QLabel,
    QWidget,
    QLineEdit,
    QCheckBox,
    QShortcut,
    QKeySequence,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QColor,
    QToolBar,
    qconnect,
    QTimer,
    Qt,
    QObject,
    QEvent,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

# Allow utils/scheduler.py to do `import cards` as a plain import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from .utils.stats_dialog import StatsDialog
from .utils.scheduler_config import load_scheduler_config
from .utils.pdf_manager import (
    PDF_NOTE_TYPE,
    get_page,
    get_zoom,
    get_read_page,
    extract_pdf_pages_text,
)
from .utils.video_manager import extract_video_id, add_video_card
from .utils.priority_manager import get_priority, set_priority, get_all_priorities
from .utils.priority_dialog import PriorityDialog
from .utils import timer_widget as _timer_mod
from .utils.topic_scheduler import on_topic_card_answered as _on_topic_card_answered
from .utils.timer_widget import (
    build_timer_toolbar,
    on_timer_question_shown as _on_timer_question_shown,
    timer_on_card_answered as _timer_on_card_answered,
)
from .utils import pdf_dock as _pdf_dock_mod
from .utils import video_dock as _video_dock_mod
from .utils import web_dock as _web_dock_mod
from .utils import add_card_dock as _add_card_dock_mod
from .utils import review_time_tracker as _review_time_mod
from .utils.db import get_connection, replace_pdf_text_index, search_pdf_text_index
from .utils.session import (
    learnFunction,
    reset_session_counts,
    get_session_counts,
    get_session_times,
)
from .utils.settings_dialog import IncrementoSettingsDialog, default_shortcuts

_ADDON_DIR = os.path.dirname(__file__)

_shortcut_actions: dict[str, object] = {}


def _register_shortcut_action(action_id: str, action_obj) -> None:
    _shortcut_actions[action_id] = action_obj


def _apply_shortcuts_from_config() -> None:
    cfg = mw.addonManager.getConfig(__name__) or {}
    defaults = default_shortcuts()
    user_shortcuts = cfg.get("shortcuts") or {}

    for action_id, action_obj in _shortcut_actions.items():
        shortcut_text = user_shortcuts.get(action_id, defaults.get(action_id, ""))
        seq = QKeySequence(shortcut_text) if shortcut_text else QKeySequence()
        if hasattr(action_obj, "setShortcut"):
            action_obj.setShortcut(seq)
        elif hasattr(action_obj, "setKey"):
            action_obj.setKey(seq)


mw.addonManager.setWebExports(__name__, r"user_files/.*")

# Last PDF card opened via the Quick Open dialog (used by Ctrl+L).
_last_opened_pdf_cid: int | None = None


# Wire add_card_dock callbacks to pdf_dock.
_pdf_dock_mod.register_add_card_callbacks(
    _add_card_dock_mod.open_add_card_dock,
    _add_card_dock_mod.fill_dock_field,
    _add_card_dock_mod.get_add_card_dock,
)
_pdf_dock_mod.register_pdf_view_callbacks(
    _review_time_mod.on_pdf_view_started,
    _review_time_mod.on_pdf_view_stopped,
)


def _on_js_message(handled, message, context) -> tuple:
    if not isinstance(message, str) or not message.startswith("incremento_"):
        return handled

    if message == "incremento_open_add_card":
        _add_card_dock_mod.open_add_card_dock()
        return (True, None)

    if message.startswith("incremento_fill_field:"):
        try:
            data = json.loads(message[len("incremento_fill_field:") :])
            _add_card_dock_mod.fill_dock_field(int(data["idx"]), data["text"])
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_card:"):
        try:
            note_id = int(message[len("incremento_open_card:") :])
            from aqt import dialogs

            def _browse(nid=note_id):
                b = dialogs.open("Browser", mw)
                b.search_for(f"nid:{nid}")

            QTimer.singleShot(0, _browse)
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_pdf:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                page = int(parts[2])
                card = mw.col.get_card(card_id)
                note = mw.col.get_note(card.nid)
                filename = note["PDF_Filename"]
                zoom = get_zoom(_ADDON_DIR, card_id)
                _pdf_dock_mod.show_pdf_in_dock(
                    card_id, filename, page, zoom, via_link=True
                )
            except Exception:
                pass
        return (True, None)

    if message.startswith("incremento_open_video:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                position = float(parts[2])
                card = mw.col.get_card(card_id)
                note = mw.col.get_note(card.nid)
                url = note["YouTube_URL"]
                QTimer.singleShot(
                    0,
                    lambda: _video_dock_mod.show_video_in_dock(card_id, url, position),
                )
            except Exception:
                pass
        return (True, None)

    return handled


gui_hooks.add_cards_did_add_note.append(_pdf_dock_mod.on_add_cards_did_add_note)

gui_hooks.reviewer_did_show_question.append(_on_timer_question_shown)
gui_hooks.reviewer_did_show_question.append(_review_time_mod.on_reviewer_question_shown)
gui_hooks.reviewer_did_show_question.append(_pdf_dock_mod.on_pdf_question_shown)
gui_hooks.reviewer_did_show_question.append(_video_dock_mod.on_video_question_shown)
gui_hooks.reviewer_did_show_question.append(_web_dock_mod.on_web_question_shown)
gui_hooks.reviewer_did_show_answer.append(_review_time_mod.on_reviewer_answer_shown)
gui_hooks.state_did_change.append(_review_time_mod.on_state_did_change)
gui_hooks.reviewer_did_answer_card.append(_timer_on_card_answered)
gui_hooks.reviewer_did_answer_card.append(_on_topic_card_answered)
gui_hooks.reviewer_will_end.append(_pdf_dock_mod.on_pdf_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_video_dock_mod.on_video_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_web_dock_mod.on_web_reviewer_will_end)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)


def _sync_pdf_note_type() -> None:
    """Update the PDF card template to the current code version on startup."""
    from .utils.pdf_manager import ensure_pdf_note_type

    def _run() -> None:
        try:
            ensure_pdf_note_type(mw.col)
        except Exception:
            pass

    mw.taskman.run_in_background(_run)


gui_hooks.main_window_did_init.append(_sync_pdf_note_type)
gui_hooks.main_window_did_init.append(_video_dock_mod.sync_video_note_type)
gui_hooks.main_window_did_init.append(_web_dock_mod.sync_web_note_type)


def _build_timer_toolbar() -> None:
    build_timer_toolbar(_timerToggleAction)


gui_hooks.main_window_did_init.append(_build_timer_toolbar)


# ── Option+P quick-jump to PDF ────────────────────────────────────────────────


class _PdfQuickJumpDialog(QDialog):
    """Quick Open dialog: fuzzy-search PDF cards by title with priority display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Open")
        self.resize(860, 580)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Search box ─────────────────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setStyleSheet(
            "QLineEdit { border: 2px solid #2979ff; border-radius: 3px;"
            " padding: 6px 10px; font-size: 15px; }"
        )
        layout.addWidget(self._search)
        layout.addSpacing(10)

        # ── Results table ──────────────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Title", "Type", "Prio", ""])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 52)
        self._table.setColumnWidth(2, 48)
        self._table.setColumnWidth(3, 28)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(True)
        self._table.setWordWrap(True)
        layout.addWidget(self._table)
        layout.addSpacing(10)

        # ── Keyboard shortcut hints ────────────────────────────────────────────
        for key, desc in [
            ("Ctrl + F", "Open First in Queue"),
            ("Ctrl + R", "Open Random Note"),
            ("Ctrl + L", "Open Last Opened Note"),
        ]:
            lbl = QLabel(f"<b>{key}</b>: {desc}")
            lbl.setStyleSheet("font-size: 13px; padding: 2px 0;")
            layout.addWidget(lbl)
        layout.addSpacing(10)

        # ── Cancel button ──────────────────────────────────────────────────────
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #2979ff; color: white; border: none;"
            " padding: 10px; font-size: 14px; border-radius: 3px; }"
            " QPushButton:hover { background: #1565c0; }"
        )
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        # ── Load data ──────────────────────────────────────────────────────────
        self._all_entries: list[tuple[str, int, int, float | None]] = []
        self._load_entries()
        self._refresh("")

        qconnect(self._search.textChanged, self._refresh)
        self._search.returnPressed.connect(self._accept_current)
        self._table.itemDoubleClicked.connect(lambda _: self._accept_current())
        self._search.installEventFilter(self)

        # In-dialog shortcuts (Ctrl+F/R/L)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._open_first)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._open_random)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._open_last)

    def _load_entries(self) -> None:
        all_prios = get_all_priorities(_ADDON_DIR)  # {cid: priority}
        try:
            note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}" -is:suspended')
            for nid in note_ids:
                try:
                    note = mw.col.get_note(nid)
                    title = note.fields[0] if note.fields else str(nid)
                    cids = mw.col.find_cards(f"nid:{nid}")
                    if cids:
                        cid = cids[0]
                        page = get_page(_ADDON_DIR, cid)
                        prio = all_prios.get(cid)  # None = not explicitly set
                        self._all_entries.append((title, cid, page, prio))
                except Exception:
                    pass
        except Exception:
            pass
        self._all_entries.sort(key=lambda e: e[0].lower())

    @staticmethod
    def _prio_bg(p) -> QColor:
        if p is None:
            return QColor(80, 80, 80)
        if p >= 75:
            return QColor(160, 20, 20)
        if p >= 55:
            return QColor(150, 80, 0)
        if p >= 35:
            return QColor(110, 100, 0)
        return QColor(50, 110, 35)

    def _refresh(self, query: str) -> None:
        self._table.setRowCount(0)
        q = query.lower()
        n = 0
        for title, cid, page, prio in self._all_entries:
            if q in title.lower():
                n += 1
                row = self._table.rowCount()
                self._table.insertRow(row)

                title_item = QTableWidgetItem(f"{n}.  {title}")
                title_item.setData(Qt.ItemDataRole.UserRole, cid)
                self._table.setItem(row, 0, title_item)

                type_item = QTableWidgetItem("PDF")
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 1, type_item)

                if prio is not None:
                    prio_item = QTableWidgetItem(str(int(round(prio))))
                    prio_item.setBackground(self._prio_bg(prio))
                    prio_item.setForeground(QColor("white"))
                else:
                    prio_item = QTableWidgetItem("-")
                    prio_item.setForeground(QColor("#888888"))
                prio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 2, prio_item)

                self._table.setItem(row, 3, QTableWidgetItem(""))

        self._table.resizeRowsToContents()
        if self._table.rowCount():
            self._table.selectRow(0)

    def _open_first(self) -> None:
        """Open the highest-priority entry (lowest priority value = most important)."""
        if not self._all_entries:
            return
        best = min(self._all_entries, key=lambda e: e[3] if e[3] is not None else 50.0)
        self._select_cid_and_accept(best[1])

    def _open_random(self) -> None:
        import random as _random

        if self._all_entries:
            self._select_cid_and_accept(_random.choice(self._all_entries)[1])

    def _open_last(self) -> None:
        if _last_opened_pdf_cid is not None:
            self._select_cid_and_accept(_last_opened_pdf_cid)

    def _select_cid_and_accept(self, cid: int) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == cid:
                self._table.selectRow(row)
                break
        self.accept()

    def eventFilter(self, obj, event):
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._table.selectRow(
                    min(self._table.currentRow() + 1, self._table.rowCount() - 1)
                )
                return True
            if key == Qt.Key.Key_Up:
                self._table.selectRow(max(self._table.currentRow() - 1, 0))
                return True
        return super().eventFilter(obj, event)

    def _accept_current(self) -> None:
        if self._table.currentRow() >= 0:
            self.accept()

    @property
    def selected_card_id(self) -> int | None:
        item = self._table.item(self._table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None


def _open_pdf_quick_jump() -> None:
    global _last_opened_pdf_cid
    dlg = _PdfQuickJumpDialog(mw)
    if not dlg.exec():
        return
    cid = dlg.selected_card_id
    if cid is None:
        return
    try:
        _open_pdf_card(cid)
    except Exception as e:
        showInfo(f"Could not open PDF:\n{e}")


def _open_pdf_card(
    card_id: int, page: int | None = None, search_query: str = ""
) -> None:
    global _last_opened_pdf_cid
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note["PDF_Filename"]
    open_page = page if page is not None else get_page(_ADDON_DIR, card_id)
    zoom = get_zoom(_ADDON_DIR, card_id)
    read_page = get_read_page(_ADDON_DIR, card_id)
    _last_opened_pdf_cid = card_id
    _pdf_dock_mod.show_pdf_in_dock(
        card_id,
        filename,
        open_page,
        zoom,
        read_page=read_page,
        search_query=search_query,
    )


class _SearchAllDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search ALL")
        self.resize(1280, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search PDFs and cards...")
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
                get_connection(_ADDON_DIR)
                .execute("SELECT DISTINCT card_id FROM pdf_highlights")
                .fetchall()
            )
            cids.update(int(r[0]) for r in rows)
        except Exception:
            pass
        try:
            rows = (
                get_connection(_ADDON_DIR)
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
        hits = search_pdf_text_index(_ADDON_DIR, q, limit=limit)
        if hits:
            return [
                (cid, page, self._snippet(text or "", q, max_len=180))
                for cid, page, text in hits
            ]

        from .utils.pdf_manager import get_pdf_dir
        pdf_dir = get_pdf_dir()
        for cid in self._candidate_pdf_card_ids():
            try:
                card = mw.col.get_card(cid)
                note = mw.col.get_note(card.nid)
                filename = note["PDF_Filename"]
                pdf_path = os.path.join(pdf_dir, filename)
                page_texts = extract_pdf_pages_text(pdf_path)
                replace_pdf_text_index(_ADDON_DIR, cid, page_texts)
            except Exception:
                continue

        hits = search_pdf_text_index(_ADDON_DIR, q, limit=limit)
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
                    get_connection(_ADDON_DIR)
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
                    get_connection(_ADDON_DIR)
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
                get_connection(_ADDON_DIR)
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
                    _open_pdf_card(cid, page, search_query=q)
                return
            if s.startswith("inc://card/"):
                nid = int(s.rsplit("/", 1)[1])
                from aqt import dialogs

                b = dialogs.open("Browser", mw)
                b.search_for(f"nid:{nid}")
                return
        except Exception as e:
            showInfo(f"Could not open result:\n{e}")


def _open_search_all() -> None:
    _SearchAllDialog(mw).exec()


def _trigger_pdf_viewer_action(action: str) -> None:
    _pdf_dock_mod.trigger_viewer_action(action)


_pdf_jump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), mw)
_pdf_jump_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_pdf_jump_shortcut.activated, _open_pdf_quick_jump)
_register_shortcut_action("quick_open_pdf", _pdf_jump_shortcut)


def showStatsFunction() -> None:
    base_time = get_session_times() or {"type": {}, "tags": {}}
    runtime_time = _review_time_mod.get_runtime_session_time() or {
        "type": {},
        "tags": {},
    }
    merged_time = {"type": {}, "tags": {}}
    for key in ("type", "tags"):
        for src in (base_time.get(key, {}), runtime_time.get(key, {})):
            for name, value in src.items():
                merged_time[key][name] = merged_time[key].get(name, 0.0) + float(value)

    cfg = load_scheduler_config()
    dlg = StatsDialog(
        addon_dir=os.path.dirname(__file__),
        session_counts=get_session_counts(),
        session_time=merged_time,
        day_end_time=cfg.day_end_time,
        parent=mw,
    )
    dlg.exec()


def addPdfFunction() -> None:
    from .utils.pdf_dialog import AddPdfDialog
    from .utils.pdf_manager import add_pdf_card

    dlg = AddPdfDialog(mw)
    if not dlg.exec():
        return
    entries = dlg.selected_entries()
    if not entries:
        return

    created = 0
    failed: list[tuple[str, str]] = []
    try:
        for pdf_path, title, tags in entries:
            try:
                add_pdf_card(_ADDON_DIR, mw.col, pdf_path, title, tags=tags)
                created += 1
            except Exception as e:
                failed.append((pdf_path, str(e)))
    except Exception as e:
        showInfo(f"Failed to add PDF card(s):\n{e}")
        return

    if not failed:
        if created == 1:
            showInfo(f'PDF card "{entries[0][1]}" added to the Topics deck.')  # noqa: E501
        else:
            showInfo(f"Added {created} PDF cards to the Topics deck.")
        return

    failed_names = "\n".join(
        f"- {os.path.basename(path)}: {msg}" for path, msg in failed[:10]
    )
    extra = ""
    if len(failed) > 10:
        extra = f"\n...and {len(failed) - 10} more failures."
    showInfo(
        f"Added {created} PDF card(s). Failed: {len(failed)}\n\n{failed_names}{extra}"
    )


def exportFunction() -> None:
    import datetime
    from aqt.qt import QFileDialog
    from .utils.db import (
        get_connection,
        DB_NAME,
        export_priorities_json,
        export_pdf_progress_json,
        export_highlights_json,
        export_stats_json,
    )

    today = datetime.date.today().isoformat()
    default_name = os.path.expanduser(f"~/incremento_export_{today}.zip")

    path, _ = QFileDialog.getSaveFileName(
        mw,
        "Export Incremento User Data",
        default_name,
        "ZIP files (*.zip)",
    )
    if not path:
        return

    user_files_dir = os.path.join(_ADDON_DIR, "user_files")
    from .utils.pdf_manager import get_pdf_dir
    pdf_dir = get_pdf_dir()

    # Gather PDF filenames from all Incremento PDF notes
    pdf_filenames = []
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
        for nid in note_ids:
            try:
                fname = mw.col.get_note(nid)["PDF_Filename"]
                if fname:
                    pdf_filenames.append(fname)
            except Exception:
                pass
    except Exception:
        pass

    try:
        # Snapshot counts before opening the ZIP
        conn = get_connection(_ADDON_DIR)
        priority_count = conn.execute("SELECT COUNT(*) FROM priorities").fetchone()[0]

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            # ── data/incremento.db — main SQLite database (direct restore) ──
            db_path = os.path.join(user_files_dir, DB_NAME)
            if os.path.exists(db_path):
                zf.write(db_path, f"data/{DB_NAME}")

            # ── data/*.json — human-readable copies of each dataset ──────────
            zf.writestr("data/priorities.json", export_priorities_json(_ADDON_DIR))
            zf.writestr("data/pdf_progress.json", export_pdf_progress_json(_ADDON_DIR))
            zf.writestr("data/highlights.json", export_highlights_json(_ADDON_DIR))
            zf.writestr("data/stats.json", export_stats_json(_ADDON_DIR))

            # ── config.json — scheduler settings ─────────────────────────────
            config = mw.addonManager.getConfig(__name__) or {}
            zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))

            # ── pdfs/ — PDF media files ───────────────────────────────────────
            pdf_count = 0
            pdf_missing = []
            for fname in pdf_filenames:
                pdf_path = os.path.join(pdf_dir, fname)
                if os.path.exists(pdf_path):
                    zf.write(pdf_path, f"pdfs/{fname}")
                    pdf_count += 1
                else:
                    pdf_missing.append(fname)

            # ── manifest.json — export metadata ──────────────────────────────
            manifest = {
                "export_date": today,
                "addon": "Incremento",
                "anki_version": getattr(mw.pm, "meta", {}).get(
                    "ankiVersion", "unknown"
                ),
                "counts": {
                    "pdf_notes": len(pdf_filenames),
                    "pdfs_exported": pdf_count,
                    "pdfs_missing": len(pdf_missing),
                    "priorities": priority_count,
                },
                "files": {
                    f"data/{DB_NAME}": "All user data (SQLite, for direct restore)",
                    "data/priorities.json": "Card priorities (human-readable copy)",
                    "data/pdf_progress.json": "PDF reading positions and zoom levels",
                    "data/highlights.json": "PDF text highlights",
                    "data/stats.json": "Session, daily and lifetime statistics",
                    "config.json": "Scheduler and session settings",
                    "pdfs/": "PDF files referenced by Incremento cards",
                },
            }
            if pdf_missing:
                manifest["pdfs_missing_filenames"] = pdf_missing

            zf.writestr(
                "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
            )

        # ── Success dialog ────────────────────────────────────────────────────
        missing_note = (
            f"\n\n  ⚠ {len(pdf_missing)} PDF file(s) not found in media folder"
            if pdf_missing
            else ""
        )
        showInfo(
            f"Export complete.\n\n"
            f"  • {pdf_count} of {len(pdf_filenames)} PDF file(s)\n"
            f"  • {priority_count} card priorit{'y' if priority_count == 1 else 'ies'}\n"
            f"  • Statistics, highlights, progress, config"
            f"{missing_note}\n\n"
            f"Saved to:\n{path}"
        )
    except Exception as e:
        showInfo(f"Export failed:\n{e}")


def _extract_card() -> None:
    """Option+X: grab the reviewer's selected text, open the extract-card dialog."""
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        return
    mw.reviewer.web.page().runJavaScript(
        "window.getSelection()?.toString() || ''",
        lambda text: _on_extract_selection(text.strip(), card),
    )


def _on_extract_selection(selected_text: str, parent_card) -> None:
    from .utils.extract_card_dialog import ExtractCardDialog

    # Build note-type list
    notetypes = [
        {"name": m["name"], "fields": [f["name"] for f in m["flds"]]}
        for m in mw.col.models.all()
    ]

    # Build deck list
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]

    # Defaults: same note type and deck as the parent card
    parent_note = parent_card.note()
    default_notetype = parent_note.note_type()["name"]
    parent_deck = mw.col.decks.get(parent_card.did)
    default_deck = parent_deck["name"] if parent_deck else ""

    # Parent card link (appended to field 0 of the new card)
    parent_label = (
        parent_note.fields[0][:60].strip()
        if parent_note.fields
        else f"Card {parent_card.id}"
    )
    parent_link = (
        f'<a href="#" onclick="pycmd(\'incremento_open_card:{parent_card.id}\')" '
        f'style="font-size:0.85em;color:#888;">↩ {parent_label}</a>'
    )

    dlg = ExtractCardDialog(
        selected_text=selected_text,
        parent_link_html=parent_link,
        notetypes=notetypes,
        deck_names=deck_names,
        default_notetype=default_notetype,
        default_deck=default_deck,
        parent=mw,
    )
    if not dlg.exec():
        return

    try:
        model = mw.col.models.by_name(dlg.notetype_name)
        if model is None:
            showInfo(f"Note type '{dlg.notetype_name}' not found.")
            return
        deck = mw.col.decks.by_name(dlg.deck_name)
        deck_id = (
            mw.col.decks.add_normal_deck_with_name(dlg.deck_name).id
            if deck is None
            else deck["id"]
        )
        note = mw.col.new_note(model)
        for fname, val in dlg.field_values.items():
            if fname in note:
                note[fname] = val
        mw.col.add_note(note, deck_id)
        showInfo(f"Card created in '{dlg.deck_name}'.")
    except Exception as e:
        showInfo(f"Failed to create card:\n{e}")


def _open_priority_dialog() -> None:
    """Open the priority assignment dialog for the currently reviewed card."""
    from .utils.topic_scheduler import is_topic_card
    from .utils.db import get_topic_schedule, set_topic_schedule

    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        showInfo("No card is currently being reviewed.")
        return

    current = get_priority(_ADDON_DIR, card.id)
    note = card.note()
    label_text = note.fields[0][:80].strip() if note.fields else ""

    a_factor = None
    interval = None
    if is_topic_card(card):
        a_factor, interval = get_topic_schedule(_ADDON_DIR, card.id)

    dlg = PriorityDialog(
        current_priority=current,
        card_label=label_text,
        current_a_factor=a_factor,
        current_interval=interval,
        parent=mw,
    )
    if dlg.exec():
        set_priority(_ADDON_DIR, card.id, dlg.priority)
        msg = f"Priority set to {dlg.priority:.0f}"
        if dlg.a_factor is not None:
            set_topic_schedule(_ADDON_DIR, card.id, dlg.a_factor, interval or 1)
            msg += f"  ·  A-Factor {dlg.a_factor:.3f}"
        tooltip(msg)


_priority_shortcut = QShortcut(QKeySequence("Alt+P"), mw)
_priority_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_priority_shortcut.activated, _open_priority_dialog)
_register_shortcut_action("set_priority", _priority_shortcut)

_extract_shortcut = QShortcut(QKeySequence("Alt+X"), mw)
_extract_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_extract_shortcut.activated, _extract_card)
_register_shortcut_action("extract_card", _extract_shortcut)

_pdf_prev_page_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Left"), mw)
_pdf_prev_page_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_prev_page_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("prev_page"),
)
_register_shortcut_action("pdf_prev_page", _pdf_prev_page_shortcut)

_pdf_next_page_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Right"), mw)
_pdf_next_page_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_next_page_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("next_page"),
)
_register_shortcut_action("pdf_next_page", _pdf_next_page_shortcut)

_pdf_zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+Alt+-"), mw)
_pdf_zoom_out_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_zoom_out_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("zoom_out"),
)
_register_shortcut_action("pdf_zoom_out", _pdf_zoom_out_shortcut)

_pdf_zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+Alt+="), mw)
_pdf_zoom_in_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_zoom_in_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("zoom_in"),
)
_register_shortcut_action("pdf_zoom_in", _pdf_zoom_in_shortcut)

_pdf_mark_read_shortcut = QShortcut(QKeySequence("Ctrl+Alt+M"), mw)
_pdf_mark_read_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_mark_read_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("mark_read"),
)
_register_shortcut_action("pdf_mark_read", _pdf_mark_read_shortcut)


def addVideoFunction() -> None:
    """Incremento -> Add Content -> YouTube Video"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .utils.add_video_dialog import AddVideoDialog

    dlg = AddVideoDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return
    url = dlg.youtube_url
    if not url:
        showInfo("Please enter a YouTube URL.")
        return
    if not extract_video_id(url):
        showInfo("Could not find a valid YouTube video ID in that URL.")
        return
    title = dlg.title or url
    try:
        add_video_card(mw.col, url, title, tags=dlg.tags)
        mw.col.reset()
        tooltip(f"Video card '{title}' added to Topics.")
    except Exception as e:
        showInfo(f"Failed to add video card:\n{e}")


def addWebpageFunction() -> None:
    from .utils.webpage_dialog import WebpageToPdfDialog
    from .utils.pdf_manager import add_pdf_card

    dlg = WebpageToPdfDialog(mw)
    if not dlg.exec():
        return
    try:
        add_pdf_card(
            _ADDON_DIR,
            mw.col,
            dlg.pdf_path,
            dlg.title_text,
            tags=dlg.tags_to_apply,
        )
        showInfo(f'PDF card "{dlg.title_text}" added to the Topics deck.')
    except Exception as e:
        showInfo(f"Failed to import webpage as PDF:\n{e}")


def reindexPdfTextFunction() -> None:
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
    except Exception as e:
        showInfo(f"Could not list PDF cards:\n{e}")
        return

    if not note_ids:
        showInfo("No PDF cards found to reindex.")
        return

    updated = 0
    unchanged = 0
    failed: list[tuple[int, str]] = []
    from .utils.pdf_manager import get_pdf_dir
    pdf_dir = get_pdf_dir()

    mw.progress.start(label="Reindexing PDF text...", immediate=True)
    try:
        total = len(note_ids)
        for i, nid in enumerate(note_ids, start=1):
            try:
                mw.progress.update(label=f"Reindexing PDF text... ({i}/{total})")
            except Exception:
                pass

            try:
                note = mw.col.get_note(nid)
                filename = note["PDF_Filename"]
                pdf_path = os.path.join(pdf_dir, filename)
                if not os.path.exists(pdf_path):
                    failed.append((nid, f"file not found: {pdf_path}"))
                    continue
                page_texts = extract_pdf_pages_text(pdf_path)
                if not any(page_texts):
                    failed.append((nid, f"no text extracted from {filename} ({len(page_texts)} pages)"))
                    continue
                new_text = "\n\n".join([p for p in page_texts if p]).strip()
                old_text = (note["Content"] or "") if "Content" in note else ""

                for cid in mw.col.find_cards(f"nid:{nid}"):
                    try:
                        replace_pdf_text_index(_ADDON_DIR, cid, page_texts)
                    except Exception:
                        pass

                if new_text != old_text:
                    note["Content"] = new_text
                    note.flush()
                    updated += 1
                else:
                    unchanged += 1
            except Exception as e:
                failed.append((nid, str(e)))
    finally:
        mw.progress.finish()

    if not failed:
        showInfo(
            f"PDF text reindex complete.\n\n"
            f"Updated: {updated}\nUnchanged: {unchanged}\nTotal: {len(note_ids)}"
        )
        return

    failed_preview = "\n".join(f"- nid:{nid}: {msg}" for nid, msg in failed[:10])
    extra = ""
    if len(failed) > 10:
        extra = f"\n...and {len(failed) - 10} more failures."
    showInfo(
        f"PDF text reindex finished with issues.\n\n"
        f"Updated: {updated}\nUnchanged: {unchanged}\nFailed: {len(failed)}\n\n"
        f"{failed_preview}{extra}"
    )


def openSettingsFunction() -> None:
    cfg = mw.addonManager.getConfig(__name__) or {}
    dlg = IncrementoSettingsDialog(cfg.get("shortcuts") or {}, parent=mw)
    if not dlg.exec():
        return

    cfg["shortcuts"] = dlg.shortcuts_map
    mw.addonManager.writeConfig(__name__, cfg)
    _apply_shortcuts_from_config()
    tooltip("Incremento shortcuts updated.")


def _ensure_settings_menu_action() -> None:
    for act in _menu.actions():
        if act.text() == "Settings":
            return

    action = QAction("Settings", mw)
    action.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(action.triggered, openSettingsFunction)

    inserted = False
    for act in _menu.actions():
        if act.isSeparator():
            _menu.insertAction(act, action)
            inserted = True
            break
    if not inserted:
        _menu.addAction(action)

    _register_shortcut_action("open_settings", action)
    _apply_shortcuts_from_config()


# ── Incremento top-level menu ─────────────────────────────────────────────────

_menu = QMenu("Incremento", mw)
mw.menuBar().addMenu(_menu)

_startAction = QAction("Start Incremental Learning", mw)
qconnect(_startAction.triggered, learnFunction)
_menu.addAction(_startAction)
_register_shortcut_action("start_learning", _startAction)

_settingsAction = QAction("Settings", mw)
_settingsAction.setMenuRole(QAction.MenuRole.NoRole)
qconnect(_settingsAction.triggered, openSettingsFunction)
_menu.addAction(_settingsAction)
_register_shortcut_action("open_settings", _settingsAction)

_menu.addSeparator()

_addContentMenu = QMenu("Add Content", mw)
_menu.addMenu(_addContentMenu)

_addPdfAction = QAction("Add PDF", mw)
qconnect(_addPdfAction.triggered, addPdfFunction)
_addContentMenu.addAction(_addPdfAction)
_register_shortcut_action("add_pdf", _addPdfAction)

_addWebpageAction = QAction("Webpage to PDF", mw)
qconnect(_addWebpageAction.triggered, addWebpageFunction)
_addContentMenu.addAction(_addWebpageAction)
_register_shortcut_action("webpage_to_pdf", _addWebpageAction)

_addVideoAction = QAction("YouTube Video", mw)
qconnect(_addVideoAction.triggered, addVideoFunction)
_addContentMenu.addAction(_addVideoAction)
_register_shortcut_action("youtube_video", _addVideoAction)

_addWebAction = QAction("Web Page", mw)
qconnect(_addWebAction.triggered, _web_dock_mod.add_web_function)
_addContentMenu.addAction(_addWebAction)
_register_shortcut_action("add_web_page", _addWebAction)

_menu.addSeparator()

_timerToggleAction = QAction("Show Focus Timer", mw)
_timerToggleAction.setCheckable(True)
_timerToggleAction.setChecked(True)  # default; corrected by _build_timer_toolbar


def _on_timer_toggle(checked: bool) -> None:
    if _timer_mod._timer_toolbar is not None:
        _timer_mod._timer_toolbar.setVisible(checked)
    cfg = mw.addonManager.getConfig(__name__) or {}
    cfg["show_timer"] = checked
    mw.addonManager.writeConfig(__name__, cfg)


qconnect(_timerToggleAction.triggered, _on_timer_toggle)
_menu.addAction(_timerToggleAction)
_register_shortcut_action("toggle_focus_timer", _timerToggleAction)

_menu.addSeparator()

_utilsMenu = QMenu("Utils", mw)
_menu.addMenu(_utilsMenu)

_reindexPdfTextAction = QAction("Reindex PDF Text (Existing Cards)", mw)
qconnect(_reindexPdfTextAction.triggered, reindexPdfTextFunction)
_utilsMenu.addAction(_reindexPdfTextAction)

_statsAction = QAction("Statistics", mw)
qconnect(_statsAction.triggered, showStatsFunction)
_menu.addAction(_statsAction)
_register_shortcut_action("statistics", _statsAction)

_searchAllAction = QAction("Search ALL", mw)
qconnect(_searchAllAction.triggered, _open_search_all)
_menu.addAction(_searchAllAction)
_register_shortcut_action("search_all", _searchAllAction)

_exportAction = QAction("Export User Data", mw)
qconnect(_exportAction.triggered, exportFunction)
_menu.addAction(_exportAction)
_register_shortcut_action("export_user_data", _exportAction)

_apply_shortcuts_from_config()
_ensure_settings_menu_action()
