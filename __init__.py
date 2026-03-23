import json
import os
import sys
import zipfile

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
    QShortcut,
    QKeySequence,
    QApplication,
    QListWidget,
    QListWidgetItem,
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
from .utils.pdf_manager import PDF_NOTE_TYPE, get_page, get_zoom, get_read_page
from .utils.video_manager import extract_video_id, add_video_card
from .utils.priority_manager import get_priority, set_priority, get_all_priorities
from .utils.priority_dialog import PriorityDialog
from .utils import timer_widget as _timer_mod
from .utils.timer_widget import (
    build_timer_toolbar,
    on_timer_question_shown as _on_timer_question_shown,
    timer_on_card_answered as _timer_on_card_answered,
)
from .utils import pdf_dock as _pdf_dock_mod
from .utils import video_dock as _video_dock_mod
from .utils import web_dock as _web_dock_mod
from .utils import add_card_dock as _add_card_dock_mod
from .utils.session import learnFunction, reset_session_counts, get_session_counts

_ADDON_DIR = os.path.dirname(__file__)

mw.addonManager.setWebExports(__name__, r"user_files/.*")

# Last PDF card opened via the Quick Open dialog (used by Ctrl+L).
_last_opened_pdf_cid: int | None = None


# Wire add_card_dock callbacks to pdf_dock.
_pdf_dock_mod.register_add_card_callbacks(
    _add_card_dock_mod.open_add_card_dock,
    _add_card_dock_mod.fill_dock_field,
    _add_card_dock_mod.get_add_card_dock,
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
gui_hooks.reviewer_did_show_question.append(_pdf_dock_mod.on_pdf_question_shown)
gui_hooks.reviewer_did_show_question.append(_video_dock_mod.on_video_question_shown)
gui_hooks.reviewer_did_show_question.append(_web_dock_mod.on_web_question_shown)
gui_hooks.reviewer_did_answer_card.append(_timer_on_card_answered)
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
        card = mw.col.get_card(cid)
        note = mw.col.get_note(card.nid)
        filename = note["PDF_Filename"]
        page = get_page(_ADDON_DIR, cid)
        zoom = get_zoom(_ADDON_DIR, cid)
        read_page = get_read_page(_ADDON_DIR, cid)
        _last_opened_pdf_cid = cid
        _pdf_dock_mod.show_pdf_in_dock(cid, filename, page, zoom, read_page=read_page)
    except Exception as e:
        showInfo(f"Could not open PDF:\n{e}")


_pdf_jump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), mw)
_pdf_jump_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_pdf_jump_shortcut.activated, _open_pdf_quick_jump)


def showStatsFunction() -> None:
    cfg = load_scheduler_config()
    dlg = StatsDialog(
        addon_dir=os.path.dirname(__file__),
        session_counts=get_session_counts(),
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
        for pdf_path, title in entries:
            try:
                add_pdf_card(_ADDON_DIR, mw.col, pdf_path, title)
                created += 1
            except Exception as e:
                failed.append((pdf_path, str(e)))
    except Exception as e:
        showInfo(f"Failed to add PDF card(s):\n{e}")
        return

    if not failed:
        if created == 1:
            showInfo(f'PDF card "{entries[0][1]}" added to the Topics deck.')
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
    media_dir = mw.col.media.dir()

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
                pdf_path = os.path.join(media_dir, fname)
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
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        showInfo("No card is currently being reviewed.")
        return

    current = get_priority(_ADDON_DIR, card.id)
    # Build a short label: first 60 chars of the front field
    note = card.note()
    label_text = ""
    if note.fields:
        label_text = note.fields[0][:80].strip()

    dlg = PriorityDialog(current_priority=current, card_label=label_text, parent=mw)
    if dlg.exec():
        set_priority(_ADDON_DIR, card.id, dlg.priority)
        tooltip(f"Priority set to {dlg.priority:.0f}")


_priority_shortcut = QShortcut(QKeySequence("Alt+P"), mw)
_priority_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_priority_shortcut.activated, _open_priority_dialog)

_extract_shortcut = QShortcut(QKeySequence("Alt+X"), mw)
_extract_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_extract_shortcut.activated, _extract_card)


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
        add_video_card(mw.col, url, title)
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
        add_pdf_card(_ADDON_DIR, mw.col, dlg.pdf_path, dlg.title_text)
        showInfo(f'PDF card "{dlg.title_text}" added to the Topics deck.')
    except Exception as e:
        showInfo(f"Failed to import webpage as PDF:\n{e}")


# ── Incremento top-level menu ─────────────────────────────────────────────────

_menu = QMenu("Incremento", mw)
mw.menuBar().addMenu(_menu)

_startAction = QAction("Start Incremental Learning", mw)
qconnect(_startAction.triggered, learnFunction)
_menu.addAction(_startAction)

_menu.addSeparator()

_addContentMenu = QMenu("Add Content", mw)
_menu.addMenu(_addContentMenu)

_addPdfAction = QAction("Add PDF", mw)
qconnect(_addPdfAction.triggered, addPdfFunction)
_addContentMenu.addAction(_addPdfAction)

_addWebpageAction = QAction("Webpage to PDF", mw)
qconnect(_addWebpageAction.triggered, addWebpageFunction)
_addContentMenu.addAction(_addWebpageAction)

_addVideoAction = QAction("YouTube Video", mw)
qconnect(_addVideoAction.triggered, addVideoFunction)
_addContentMenu.addAction(_addVideoAction)

_addWebAction = QAction("Web Page", mw)
qconnect(_addWebAction.triggered, _web_dock_mod.add_web_function)
_addContentMenu.addAction(_addWebAction)

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

_menu.addSeparator()

_statsAction = QAction("Statistics", mw)
qconnect(_statsAction.triggered, showStatsFunction)
_menu.addAction(_statsAction)

_exportAction = QAction("Export User Data", mw)
qconnect(_exportAction.triggered, exportFunction)
_menu.addAction(_exportAction)
