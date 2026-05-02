from __future__ import annotations

import json
import os
from html import escape

from aqt import mw
from aqt.qt import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QPixmap,
    QPushButton,
    QShortcut,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    QUrl,
    QEvent,
    qconnect,
)
from aqt.utils import showInfo, tooltip
from PyQt6.QtCore import QObject
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.epub_manager import (
        EPUB_FILE_FIELD,
        EPUB_NOTE_TYPE,
        get_due_epub_source_cards,
        get_epub_daily_limit_settings,
        get_epub_due_review_prompt_settings,
        get_epub_font_scale,
        get_epub_daily_limit_status,
        get_epub_limit_mode_label,
        get_epub_progress,
        get_read_section_index,
        get_epub_section_path,
        load_epub_metadata,
        save_epub_daily_limit_settings,
        save_epub_due_review_prompt_settings,
        set_epub_progress,
        set_epub_daily_limit_override,
        set_epub_font_scale,
        set_read_section_index,
        ensure_epub_note_type,
    )
except ImportError:
    from epub_manager import (  # type: ignore
        EPUB_FILE_FIELD,
        EPUB_NOTE_TYPE,
        get_due_epub_source_cards,
        get_epub_daily_limit_settings,
        get_epub_due_review_prompt_settings,
        get_epub_font_scale,
        get_epub_daily_limit_status,
        get_epub_limit_mode_label,
        get_epub_progress,
        get_read_section_index,
        get_epub_section_path,
        load_epub_metadata,
        save_epub_daily_limit_settings,
        save_epub_due_review_prompt_settings,
        set_epub_progress,
        set_epub_daily_limit_override,
        set_epub_font_scale,
        set_read_section_index,
        ensure_epub_note_type,
    )
try:
    from ..backend.epub_highlights import load_highlights, add_highlight, remove_highlight, update_highlight_note
except ImportError:
    from epub_highlights import load_highlights, add_highlight, remove_highlight, update_highlight_note  # type: ignore
try:
    from ..backend.reader_bookmarks import (
        add_reader_bookmark,
        delete_reader_bookmark,
        list_reader_bookmarks,
    )
except ImportError:
    from reader_bookmarks import add_reader_bookmark, delete_reader_bookmark, list_reader_bookmarks  # type: ignore
try:
    from .highlight_note_dialog import HighlightNoteDialog
except ImportError:
    from highlight_note_dialog import HighlightNoteDialog  # type: ignore
try:
    from ..backend.db import (
        add_epub_card_source,
        get_epub_card_sources,
        get_epub_document_source_note_ids,
        get_epub_section_card_counts,
    )
except ImportError:
    from db import (  # type: ignore
        add_epub_card_source,
        get_epub_card_sources,
        get_epub_document_source_note_ids,
        get_epub_section_card_counts,
    )
try:
    from ..backend.session import start_explicit_review
except ImportError:
    from session import start_explicit_review  # type: ignore


_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_epub_dock = None
_current_epub_card_id: int | None = None
_current_epub_filename: str | None = None
_current_epub_section_index = 0
_current_epub_scroll_ratio = 0.0
_current_epub_finished = False
_current_epub_font_scale = 1.0
_last_selection_meta: dict[str, object] = {}
_pending_focus_offset = -1
_pending_restore_ratio = 0.0
_pending_search_query = ""
_pending_explicit_navigation = False

_cb_open_add_card_dock = None
_cb_fill_dock_field = None
_cb_get_add_card_dock = None
_cb_epub_view_started = None
_cb_epub_view_stopped = None
_epub_shortcuts_registered = False
_epub_shortcuts = []
_epub_key_filter = None

_PYCMD_BRIDGE = "__incremento_epub__:"
_MSG_FILL_FIELD = "incremento_epub_fill_field:"
_MSG_HL_ADD = "incremento_epub_hl_add:"
_MSG_HL_DEL = "incremento_epub_hl_del:"
_MSG_PROGRESS = "incremento_epub_progress:"
_MSG_SECTION_NAV = "incremento_epub_section_nav:"
_MSG_SNAPSHOT = "incremento_epub_snapshot:"
_MSG_SELECTION_STATE = "incremento_selection_state:"

_current_epub_page_index = 0
_current_epub_total_pages = 0
_current_epub_section_page = 1
_current_epub_section_pages = 1


def current_epub_card_id() -> int | None:
    try:
        return int(_current_epub_card_id) if _current_epub_card_id is not None else None
    except Exception:
        return None


def register_add_card_callbacks(open_fn, fill_fn, get_dock_fn) -> None:
    global _cb_open_add_card_dock, _cb_fill_dock_field, _cb_get_add_card_dock
    _cb_open_add_card_dock = open_fn
    _cb_fill_dock_field = fill_fn
    _cb_get_add_card_dock = get_dock_fn


def register_epub_view_callbacks(start_fn, stop_fn) -> None:
    global _cb_epub_view_started, _cb_epub_view_stopped
    _cb_epub_view_started = start_fn
    _cb_epub_view_stopped = stop_fn


def epub_citation() -> str:
    if not _current_epub_card_id or not _current_epub_filename:
        return ""
    try:
        meta = load_epub_metadata(_ADDON_DIR, _current_epub_filename)
        sections = meta.get("sections") or []
        section = sections[_current_epub_section_index] if 0 <= _current_epub_section_index < len(sections) else None
        title = str((section or {}).get("title") or f"Section {_current_epub_section_index + 1}")
    except Exception:
        title = f"Section {_current_epub_section_index + 1}"
    start_offset = int(_last_selection_meta.get("startOffset", -1) or -1)
    cmd = f"incremento_open_epub:{int(_current_epub_card_id)}:{int(_current_epub_section_index)}:{start_offset}"
    return (
        f"<a onclick=\"pycmd('{cmd}'); return false;\" "
        f"style=\"cursor:pointer; color:#4a90d9; text-decoration:none;\">"
        f"{title}</a>"
    )


class _EpubReadingLimitDialog(QDialog):
    def __init__(self, parent, *, settings: dict, status: dict):
        super().__init__(parent)
        self.setWindowTitle("EPUB Reading Limit")
        self.setModal(True)
        self.resize(430, 220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        summary = QLabel(self._summary_text(status))
        summary.setWordWrap(True)
        summary.setStyleSheet(
            "QLabel { background: rgba(74,144,217,0.10); border: 1px solid rgba(74,144,217,0.35); "
            "border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(summary)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        self._enabled = QCheckBox("Limit pages read per day for this EPUB")
        self._enabled.setChecked(bool(settings.get("enabled")))
        form.addRow("Enabled:", self._enabled)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        self._limit_spin = QSpinBox(self)
        self._limit_spin.setRange(1, 5000)
        self._limit_spin.setValue(max(1, int(settings.get("daily_page_limit", settings.get("daily_section_limit", 5)) or 5)))
        row_layout.addWidget(self._limit_spin)

        self._mode = QComboBox(self)
        self._mode.addItem("Warning only", "warning")
        self._mode.addItem("Soft lock + override", "soft_lock")
        self._mode.addItem("Hard stop", "hard_stop")
        idx = self._mode.findData(str(settings.get("enforcement_mode") or "warning"))
        self._mode.setCurrentIndex(max(0, idx))
        row_layout.addWidget(self._mode, 1)
        form.addRow("Limit:", row)

        hint = QLabel("Uses Incremento's day-end setting for daily reset.")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        hint.setWordWrap(True)
        form.addRow("", hint)
        layout.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        qconnect(self._buttons.accepted, self.accept)
        qconnect(self._buttons.rejected, self.reject)
        layout.addWidget(self._buttons)

        qconnect(self._enabled.toggled, self._sync_enabled_state)
        self._sync_enabled_state()

    @staticmethod
    def _summary_text(status: dict) -> str:
        if not status.get("enabled"):
            return "No daily reading limit is set for this EPUB."
        limit = int(status.get("daily_page_limit", status.get("daily_section_limit", 0)) or 0)
        used = int(status.get("pages_used", status.get("sections_used", 0)) or 0)
        remaining = int(status.get("pages_remaining", status.get("sections_remaining", 0)) or 0)
        mode_label = get_epub_limit_mode_label(status.get("enforcement_mode"))
        return (
            f"Today: {used}/{limit} pages used, {remaining} remaining. "
            f"Mode: {mode_label}."
        )

    def _sync_enabled_state(self) -> None:
        enabled = self._enabled.isChecked()
        self._limit_spin.setEnabled(enabled)
        self._mode.setEnabled(enabled)

    def result_settings(self) -> dict:
        return {
            "enabled": self._enabled.isChecked(),
            "daily_section_limit": int(self._limit_spin.value()),
            "enforcement_mode": str(self._mode.currentData() or "warning"),
        }


def _summarize_due_review_sections(due_cards: list[dict]) -> str:
    sections = sorted(
        {
            int(row.get("section_index", 0) or 0) + 1
            for row in due_cards
            if int(row.get("section_index", 0) or 0) >= 0
        }
    )
    if not sections:
        return "earlier sections"
    if len(sections) <= 6:
        return ", ".join(str(section) for section in sections)
    preview = ", ".join(str(section) for section in sections[:6])
    return f"{preview}, +{len(sections) - 6} more"


class _EpubDueReviewPromptDialog(QDialog):
    def __init__(self, parent, *, due_cards: list[dict], settings: dict, current_section_index: int):
        super().__init__(parent)
        self._review_now = False
        self.setWindowTitle("Review Due EPUB Cards")
        self.setModal(True)
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        count = len(due_cards)
        earlier_sections = _summarize_due_review_sections(due_cards)
        summary = QLabel(
            f"You have {count} due card{'s' if count != 1 else ''} from this EPUB near this reading point.\n"
            f"Source sections: {earlier_sections}"
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(
            "QLabel { background: rgba(74,144,217,0.10); border: 1px solid rgba(74,144,217,0.35); "
            "border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(summary)

        detail_label = QLabel("Reviewing them first can refresh earlier context before you continue reading.")
        detail_label.setWordWrap(True)
        layout.addWidget(detail_label)

        details = QTextEdit(self)
        details.setReadOnly(True)
        details.setMinimumHeight(180)
        details.setHtml(self._details_html(due_cards))
        layout.addWidget(details, 1)

        self._offer_on_open = QCheckBox("Offer this due-card review automatically when opening this EPUB")
        self._offer_on_open.setChecked(bool(settings.get("enabled", True)))
        layout.addWidget(self._offer_on_open)

        buttons = QDialogButtonBox(parent=self)
        self._review_btn = buttons.addButton("Review Now", QDialogButtonBox.ButtonRole.AcceptRole)
        self._skip_btn = buttons.addButton("Not Now", QDialogButtonBox.ButtonRole.RejectRole)
        qconnect(self._review_btn.clicked, self._accept_review)
        qconnect(self._skip_btn.clicked, self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _details_html(due_cards: list[dict]) -> str:
        lines = []
        for row in due_cards[:20]:
            title = str(row.get("title") or f"Card {row.get('card_id')}")
            excerpt = str(row.get("excerpt") or "").strip()
            state = str(row.get("due_state") or "due").capitalize()
            detail = (
                f"section {int(row.get('section_index', 0) or 0) + 1} — {title} "
                f"<span style='color:#8892a0;'>({state})</span>"
            )
            if excerpt:
                detail += f"<br><span style='color:#8892a0;'>{excerpt}</span>"
            lines.append(f"<div style='margin-bottom:8px;'>{detail}</div>")
        if len(due_cards) > 20:
            lines.append(
                f"<div style='color:#8892a0;'>…and {len(due_cards) - 20} more due card"
                f"{'s' if len(due_cards) - 20 != 1 else ''}.</div>"
            )
        return "".join(lines)

    def _accept_review(self) -> None:
        self._review_now = True
        self.accept()

    def review_requested(self) -> bool:
        return self._review_now

    def offer_on_open_enabled(self) -> bool:
        return bool(self._offer_on_open.isChecked())


class _EpubSoftLimitDialog(QDialog):
    def __init__(self, parent, *, status: dict, target_page_index: int):
        super().__init__(parent)
        self._override = False
        self.setWindowTitle("EPUB Reading Limit")
        self.setModal(True)
        self.resize(420, 180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        allowed = int(status.get("allowed_max_page", status.get("allowed_max_section", 0)) or 0) + 1
        target = int(target_page_index) + 1
        summary = QLabel(
            f"You reached this EPUB's daily page limit.\n"
            f"Allowed today: up to page {allowed}. Target: page {target}."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        details = QLabel("You can stop here or override the limit for today.")
        details.setWordWrap(True)
        details.setStyleSheet("color: gray;")
        layout.addWidget(details)

        buttons = QDialogButtonBox(parent=self)
        self._override_btn = buttons.addButton("Override Today", QDialogButtonBox.ButtonRole.AcceptRole)
        self._cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        qconnect(self._override_btn.clicked, self._accept_override)
        qconnect(self._cancel_btn.clicked, self.reject)
        layout.addWidget(buttons)

    def _accept_override(self) -> None:
        self._override = True
        self.accept()

    def override_requested(self) -> bool:
        return self._override


def _current_epub_limit_status(
    card_id: int,
    *,
    current_section_index: int | None = None,
    current_page_index: int | None = None,
) -> dict:
    try:
        return get_epub_daily_limit_status(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            current_section_index=current_section_index,
            current_page_index=current_page_index,
        )
    except Exception:
        return {"enabled": False}


def _open_epub_limit_dialog(card_id: int) -> None:
    settings = get_epub_daily_limit_settings(_ADDON_DIR, _active_profile(), int(card_id))
    status = _current_epub_limit_status(
        int(card_id),
        current_section_index=_current_epub_section_index,
        current_page_index=_current_epub_page_index,
    )
    dlg = _EpubReadingLimitDialog(mw, settings=settings, status=status)
    if not dlg.exec():
        return
    new_settings = dlg.result_settings()
    refreshed = save_epub_daily_limit_settings(
        _ADDON_DIR,
        _active_profile(),
        int(card_id),
        enabled=bool(new_settings.get("enabled")),
        daily_section_limit=int(new_settings.get("daily_section_limit", 0) or 0),
        enforcement_mode=str(new_settings.get("enforcement_mode") or "warning"),
    )
    if refreshed.get("enabled"):
        tooltip(
            f"EPUB limit saved: {refreshed['daily_page_limit']} pages/day "
            f"({refreshed['enforcement_label']})."
        )
    else:
        tooltip("EPUB daily reading limit disabled.")


def _start_due_epub_review(card_id: int, *, current_section_index: int, due_cards: list[dict]) -> None:
    selected_ids = [int(row["card_id"]) for row in due_cards if int(row.get("card_id", 0) or 0) > 0]
    if not selected_ids:
        tooltip("No due extracted cards to review for this EPUB.")
        return

    try:
        note = mw.col.get_note(mw.col.get_card(int(card_id)).nid)
        filename = str(note[EPUB_FILE_FIELD])
    except Exception:
        filename = str(_current_epub_filename or "")
    if not filename:
        showInfo("Could not reopen this EPUB after review.")
        return

    current_deck = {}
    try:
        current_deck = mw.col.decks.current() or {}
    except Exception:
        current_deck = {}
    previous_did = current_deck.get("id")

    scroll_ratio = _current_epub_scroll_ratio
    read_section_index = get_read_section_index(_ADDON_DIR, _active_profile(), int(card_id))

    def _restore_epub() -> None:
        try:
            if previous_did:
                mw.col.decks.select(previous_did)
        except Exception:
            pass

        def _restore() -> None:
            show_epub_in_dock(
                int(card_id),
                filename,
                section_index=int(current_section_index),
                scroll_ratio=scroll_ratio,
                offer_due_review_prompt=False,
            )
            try:
                set_read_section_index(_ADDON_DIR, _active_profile(), int(card_id), read_section_index)
            except Exception:
                pass

        QTimer.singleShot(0, _restore)

    started = start_explicit_review(
        selected_ids,
        deck_name="Incremento EPUB Review",
        preserve_order=True,
        empty_message="No due extracted cards are available to review for this EPUB.",
        on_finished=_restore_epub,
    )
    if not started:
        return


def _offer_due_review_for_epub(
    card_id: int,
    *,
    current_section_index: int | None = None,
    force: bool = False,
) -> None:
    section_index = max(
        0,
        int(current_section_index if current_section_index is not None else _current_epub_section_index),
    )
    settings = get_epub_due_review_prompt_settings(_ADDON_DIR, _active_profile(), int(card_id))
    if not force and not settings.get("enabled", True):
        return

    due_cards = get_due_epub_source_cards(
        _ADDON_DIR,
        _active_profile(),
        int(card_id),
        section_index,
    )
    if not due_cards:
        if force:
            tooltip("No due extracted cards from this EPUB up to the current section.")
        return

    dlg = _EpubDueReviewPromptDialog(
        mw,
        due_cards=due_cards,
        settings=settings,
        current_section_index=section_index,
    )
    result = dlg.exec()
    new_enabled = dlg.offer_on_open_enabled()
    if new_enabled != bool(settings.get("enabled", True)):
        save_epub_due_review_prompt_settings(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            enabled=new_enabled,
        )
    if result and dlg.review_requested():
        _start_due_epub_review(int(card_id), current_section_index=section_index, due_cards=due_cards)


def _check_epub_limit_before_navigation(target_page_index: int) -> bool:
    if _current_epub_card_id is None:
        return True
    status = _current_epub_limit_status(
        int(_current_epub_card_id),
        current_section_index=_current_epub_section_index,
        current_page_index=_current_epub_page_index,
    )
    allowed_max = status.get("allowed_max_page", status.get("allowed_max_section"))
    is_blocking = bool(
        status.get("enabled")
        and status.get("enforcement_mode") in {"soft_lock", "hard_stop"}
        and not status.get("override_enabled")
        and allowed_max is not None
        and int(target_page_index) > int(allowed_max)
    )
    if not is_blocking:
        return True
    if status.get("enforcement_mode") == "soft_lock" and status.get("can_override"):
        dlg = _EpubSoftLimitDialog(
            mw,
            status=status,
            target_page_index=int(target_page_index),
        )
        if dlg.exec() and dlg.override_requested():
            set_epub_daily_limit_override(
                _ADDON_DIR,
                _active_profile(),
                int(_current_epub_card_id),
                enabled=True,
                current_section_index=_current_epub_section_index,
                current_page_index=_current_epub_page_index,
            )
            tooltip("EPUB reading limit overridden for today.")
            return True
    return False


class _EpubDockPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        del level, line, source
        if not message.startswith(_PYCMD_BRIDGE):
            return
        msg = message[len(_PYCMD_BRIDGE) :]
        if msg.startswith(_MSG_SELECTION_STATE):
            try:
                data = json.loads(msg[len(_MSG_SELECTION_STATE) :])
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.update_selection_state(
                    str(data.get("source") or "epub"),
                    has_text=bool(data.get("hasText")),
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_FILL_FIELD):
            try:
                data = json.loads(msg[len(_MSG_FILL_FIELD) :])
                _on_epub_selection(
                    int(data.get("idx", 0)),
                    str(data.get("text") or ""),
                    int(data.get("startOffset", -1) or -1),
                    int(data.get("endOffset", -1) or -1),
                )
            except Exception as exc:
                print(f"[Incremento] epub_dock fill failed: {exc}")
            return
        if msg.startswith(_MSG_HL_ADD):
            try:
                data = json.loads(msg[len(_MSG_HL_ADD) :])
                add_highlight(_ADDON_DIR, _active_profile(), int(data["cardId"]), data["highlight"])
                _update_sources_panel()
            except Exception as exc:
                print(f"[Incremento] epub_dock highlight add failed: {exc}")
            return
        if msg.startswith(_MSG_HL_DEL):
            try:
                data = json.loads(msg[len(_MSG_HL_DEL) :])
                remove_highlight(_ADDON_DIR, _active_profile(), int(data["cardId"]), str(data["id"]))
                _update_sources_panel()
            except Exception as exc:
                print(f"[Incremento] epub_dock highlight remove failed: {exc}")
            return
        if msg.startswith(_MSG_PROGRESS):
            try:
                data = json.loads(msg[len(_MSG_PROGRESS) :])
                _record_progress(
                    int(data.get("sectionIndex", _current_epub_section_index) or 0),
                    float(data.get("scrollRatio", 0.0) or 0.0),
                    page_index=int(data.get("pageIndex", _current_epub_page_index) or 0),
                    total_pages=int(data.get("totalPages", _current_epub_total_pages) or 0),
                    section_page=int(data.get("sectionPage", _current_epub_section_page) or 1),
                    section_pages=int(data.get("sectionPages", _current_epub_section_pages) or 1),
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_SECTION_NAV):
            try:
                data = json.loads(msg[len(_MSG_SECTION_NAV) :])
                _jump_section_boundary(int(data.get("delta", 0) or 0))
            except Exception:
                pass
            return
        if msg.startswith(_MSG_SNAPSHOT):
            QTimer.singleShot(0, lambda m=msg: _handle_epub_snapshot(m))


def _build_page_script(
    *,
    card_id: int,
    section_index: int,
    scroll_ratio: float,
    text_scale: float,
    focus_offset: int,
    search_query: str,
    highlights: list[dict],
) -> str:
    sections = _current_sections()
    section_lengths = [max(1, len(str(section.get("text") or ""))) for section in sections]
    state = {
        "cardId": int(card_id),
        "sectionIndex": int(section_index),
        "scrollRatio": max(0.0, min(float(scroll_ratio), 1.0)),
        "textScale": max(0.7, min(float(text_scale), 2.2)),
        "focusOffset": int(focus_offset),
        "searchQuery": str(search_query or ""),
        "highlights": highlights,
        "sectionLengths": section_lengths,
    }
    return f"""
    (function() {{
      const STATE = {json.dumps(state)};
      const BRIDGE = {json.dumps(_PYCMD_BRIDGE)};
      function send(msg) {{
        console.log(BRIDGE + msg);
      }}
      function normText(text) {{
        return String(text || '').replace(/\\s+/g, ' ').trim();
      }}
      function ensureStyle() {{
        if (document.getElementById('incremento-epub-style')) return;
        const style = document.createElement('style');
        style.id = 'incremento-epub-style';
        style.textContent = `
          html.incremento-epub-scaled {{
            overflow-x: hidden !important;
          }}
          html.incremento-epub-scaled body {{
            font-size: var(--incremento-epub-font-size, 100%) !important;
            box-sizing: border-box !important;
            min-width: 0 !important;
            max-width: 100% !important;
            width: auto !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            padding-left: max(24px, env(safe-area-inset-left)) !important;
            padding-right: max(36px, env(safe-area-inset-right)) !important;
            overflow-x: hidden !important;
            overflow-wrap: break-word;
            word-break: normal;
          }}
          html.incremento-epub-scaled body * {{
            box-sizing: border-box !important;
            max-width: 100% !important;
          }}
          html.incremento-epub-scaled img,
          html.incremento-epub-scaled svg,
          html.incremento-epub-scaled video,
          html.incremento-epub-scaled canvas,
          html.incremento-epub-scaled table {{
            max-width: 100% !important;
            height: auto !important;
          }}
          html.incremento-epub-scaled h1,
          html.incremento-epub-scaled h2,
          html.incremento-epub-scaled h3,
          html.incremento-epub-scaled h4,
          html.incremento-epub-scaled h5,
          html.incremento-epub-scaled h6,
          html.incremento-epub-scaled p,
          html.incremento-epub-scaled li,
          html.incremento-epub-scaled blockquote {{
            white-space: normal !important;
          }}
          html.incremento-epub-scaled pre {{
            white-space: pre-wrap !important;
          }}
          span.incremento-epub-highlight {{
            background: rgba(255, 225, 120, 0.75);
            border-radius: 2px;
            cursor: pointer;
          }}
        `;
        document.head.appendChild(style);
      }}
      function applyTextScale(scale) {{
        const clamped = Math.max(0.7, Math.min(Number(scale) || 1, 2.2));
        document.documentElement.classList.add('incremento-epub-scaled');
        document.documentElement.style.setProperty(
          '--incremento-epub-font-size',
          (clamped * 100).toFixed(0) + '%'
        );
        window._incrementoEpubTextScale = clamped;
      }}
      function textNodes() {{
        const root = document.body || document.documentElement;
        if (!root) return [];
        const walker = document.createTreeWalker(
          root,
          NodeFilter.SHOW_TEXT,
          {{
            acceptNode(node) {{
              return node.nodeValue && node.nodeValue.length
                ? NodeFilter.FILTER_ACCEPT
                : NodeFilter.FILTER_REJECT;
            }},
          }}
        );
        const nodes = [];
        while (walker.nextNode()) {{
          nodes.push(walker.currentNode);
        }}
        return nodes;
      }}
      function pointFromOffset(target) {{
        let remain = Math.max(0, Number(target) || 0);
        const nodes = textNodes();
        for (const node of nodes) {{
          const len = node.nodeValue.length;
          if (remain <= len) {{
            return {{ node, offset: remain }};
          }}
          remain -= len;
        }}
        if (nodes.length) {{
          const last = nodes[nodes.length - 1];
          return {{ node: last, offset: last.nodeValue.length }};
        }}
        return null;
      }}
      function offsetFromPoint(node, offset) {{
        let total = 0;
        for (const textNode of textNodes()) {{
          if (textNode === node) {{
            return total + Math.max(0, Math.min(Number(offset) || 0, textNode.nodeValue.length));
          }}
          total += textNode.nodeValue.length;
        }}
        return total;
      }}
      function unwrapHighlight(node) {{
        if (!node || !node.parentNode) return;
        while (node.firstChild) {{
          node.parentNode.insertBefore(node.firstChild, node);
        }}
        node.remove();
      }}
      function applyHighlight(hl) {{
        const start = pointFromOffset(hl.startOffset);
        const end = pointFromOffset(hl.endOffset);
        if (!start || !end) return false;
        if (hl.endOffset <= hl.startOffset) return false;
        const range = document.createRange();
        range.setStart(start.node, Math.min(start.offset, start.node.nodeValue.length));
        range.setEnd(end.node, Math.min(end.offset, end.node.nodeValue.length));
        if (range.collapsed) return false;
        const wrapper = document.createElement('span');
        wrapper.className = 'incremento-epub-highlight';
        wrapper.dataset.id = String(hl.id || '');
        wrapper.dataset.color = String(hl.color || 'yellow');
        wrapper.title = 'Click to remove highlight';
        const fragment = range.extractContents();
        wrapper.appendChild(fragment);
        range.insertNode(wrapper);
        return true;
      }}
      function selectionMeta() {{
        const sel = window.getSelection ? window.getSelection() : null;
        if (!sel || !sel.rangeCount) return null;
        const range = sel.getRangeAt(0);
        if (range.collapsed) return null;
        const text = normText(sel.toString());
        if (!text) return null;
        return {{
          text,
          startOffset: offsetFromPoint(range.startContainer, range.startOffset),
          endOffset: offsetFromPoint(range.endContainer, range.endOffset),
        }};
      }}
      function selectionRect() {{
        const sel = window.getSelection ? window.getSelection() : null;
        if (!sel || !sel.rangeCount) return null;
        const range = sel.getRangeAt(0);
        if (range.collapsed) return null;
        const rect = range.getBoundingClientRect();
        if (!rect || rect.width <= 1 || rect.height <= 1) return null;
        return {{
          x: Math.max(0, Math.round(rect.left)),
          y: Math.max(0, Math.round(rect.top)),
          width: Math.max(1, Math.round(rect.width)),
          height: Math.max(1, Math.round(rect.height)),
        }};
      }}
      function reportSelection() {{
        const meta = selectionMeta();
        if (!meta) return;
        window._lastEpubSelection = meta.text;
        window._lastEpubSelectionMeta = meta;
        send('incremento_selection_state:' + JSON.stringify({{ source: 'epub', hasText: true }}));
      }}
      function pageStep() {{
        return Math.max(1, Math.floor(window.innerHeight * 0.92));
      }}
      function maxScroll() {{
        const doc = document.documentElement || document.body;
        return Math.max(0, ((doc && doc.scrollHeight) || 0) - window.innerHeight);
      }}
      function sectionPageCount() {{
        return Math.max(1, Math.ceil(maxScroll() / pageStep()) + 1);
      }}
      function currentSectionPage() {{
        return Math.max(1, Math.min(sectionPageCount(), Math.floor(window.scrollY / pageStep()) + 1));
      }}
      function estimatedSectionPages() {{
        const lengths = Array.isArray(STATE.sectionLengths) ? STATE.sectionLengths : [];
        const currentLength = Math.max(1, Number(lengths[STATE.sectionIndex]) || 1);
        const charsPerPage = Math.max(300, currentLength / sectionPageCount());
        return lengths.map(function(length) {{
          return Math.max(1, Math.ceil(Math.max(1, Number(length) || 1) / charsPerPage));
        }});
      }}
      function pageMetrics() {{
        const pages = estimatedSectionPages();
        let before = 0;
        for (let i = 0; i < Math.min(STATE.sectionIndex, pages.length); i += 1) {{
          before += pages[i];
        }}
        const total = Math.max(1, pages.reduce(function(sum, value) {{ return sum + value; }}, 0));
        const sectionPage = currentSectionPage();
        const sectionPages = sectionPageCount();
        return {{
          sectionPage: sectionPage,
          sectionPages: sectionPages,
          pageIndex: Math.max(0, before + sectionPage - 1),
          totalPages: total,
        }};
      }}
      function reportProgress() {{
        const doc = document.documentElement || document.body;
        const scrollMax = maxScroll();
        const ratio = scrollMax > 0 ? Math.max(0, Math.min(window.scrollY / scrollMax, 1)) : 0;
        const metrics = pageMetrics();
        send('incremento_epub_progress:' + JSON.stringify({{
          cardId: STATE.cardId,
          sectionIndex: STATE.sectionIndex,
          scrollRatio: ratio,
          sectionPage: metrics.sectionPage,
          sectionPages: metrics.sectionPages,
          pageIndex: metrics.pageIndex,
          totalPages: metrics.totalPages,
        }}));
      }}
      function clearSelection() {{
        const sel = window.getSelection ? window.getSelection() : null;
        if (sel) {{
          sel.removeAllRanges();
        }}
      }}
      window.incrementoAddEpubHighlight = function() {{
        const meta = selectionMeta();
        if (!meta) return false;
        const hl = {{
          id: 'hl-' + Date.now().toString(16) + '-' + Math.random().toString(16).slice(2, 8),
          sectionIndex: STATE.sectionIndex,
          color: 'yellow',
          text: meta.text,
          startOffset: meta.startOffset,
          endOffset: meta.endOffset,
        }};
        clearSelection();
        if (!applyHighlight(hl)) return false;
        send('incremento_epub_hl_add:' + JSON.stringify({{ cardId: STATE.cardId, highlight: hl }}));
        window._lastEpubSelectionMeta = meta;
        window._lastEpubSelection = meta.text;
        return true;
      }};
      window.incrementoSnapshotEpubSelection = function() {{
        const meta = selectionMeta();
        const rect = selectionRect();
        if (!meta || !rect) return false;
        send('incremento_epub_snapshot:' + JSON.stringify({{
          cardId: STATE.cardId,
          text: meta.text,
          rect,
        }}));
        return true;
      }};
      window.incrementoEpubPageNav = function(delta) {{
        const dir = Number(delta) < 0 ? -1 : 1;
        const step = pageStep();
        const scrollMax = maxScroll();
        const currentY = Math.max(0, window.scrollY || 0);
        if (dir > 0) {{
          if (currentY + step >= scrollMax - 2) {{
            send('incremento_epub_section_nav:' + JSON.stringify({{ delta: 1 }}));
          }} else {{
            window.scrollTo(0, Math.min(scrollMax, currentY + step));
            setTimeout(reportProgress, 40);
          }}
          return;
        }}
        if (currentY <= 2) {{
          send('incremento_epub_section_nav:' + JSON.stringify({{ delta: -1 }}));
        }} else {{
          window.scrollTo(0, Math.max(0, currentY - step));
          setTimeout(reportProgress, 40);
        }}
      }};
      ensureStyle();
      applyTextScale(STATE.textScale);
      document.querySelectorAll('span.incremento-epub-highlight').forEach(unwrapHighlight);
      const highlights = Array.isArray(STATE.highlights) ? STATE.highlights.slice() : [];
      highlights.sort(function(a, b) {{ return Number(a.startOffset || 0) - Number(b.startOffset || 0); }});
      for (const hl of highlights) {{
        try {{ applyHighlight(hl); }} catch (err) {{}}
      }}
      document.removeEventListener('selectionchange', window._incrementoEpubSelectionListener, true);
      window._incrementoEpubSelectionListener = reportSelection;
      document.addEventListener('selectionchange', window._incrementoEpubSelectionListener, true);

      document.removeEventListener('keydown', window._incrementoEpubKeyListener, true);
      window._incrementoEpubKeyListener = function(event) {{
        const key = String(event.key || '');
        if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && /^[1-4]$/.test(key)) {{
          const meta = selectionMeta();
          if (!meta) return;
          event.preventDefault();
          send('incremento_epub_fill_field:' + JSON.stringify({{
            idx: Number(key) - 1,
            text: meta.text,
            startOffset: meta.startOffset,
            endOffset: meta.endOffset,
          }}));
          return;
        }}
        if (event.altKey && !event.metaKey && !event.ctrlKey && /^h$/i.test(key)) {{
          if (window.incrementoAddEpubHighlight()) {{
            event.preventDefault();
          }}
          return;
        }}
        if (event.altKey && !event.metaKey && !event.ctrlKey && /^s$/i.test(key)) {{
          if (window.incrementoSnapshotEpubSelection && window.incrementoSnapshotEpubSelection()) {{
            event.preventDefault();
          }}
        }}
      }};
      document.addEventListener('keydown', window._incrementoEpubKeyListener, true);

      document.removeEventListener('click', window._incrementoEpubClickListener, true);
      window._incrementoEpubClickListener = function(event) {{
        const target = event.target && event.target.closest
          ? event.target.closest('span.incremento-epub-highlight')
          : null;
        if (!target) return;
        event.preventDefault();
        event.stopPropagation();
        const id = String(target.dataset.id || '');
        unwrapHighlight(target);
        send('incremento_epub_hl_del:' + JSON.stringify({{ cardId: STATE.cardId, id }}));
      }};
      document.addEventListener('click', window._incrementoEpubClickListener, true);

      if (window._incrementoEpubScrollTimer) {{
        clearTimeout(window._incrementoEpubScrollTimer);
      }}
      document.removeEventListener('scroll', window._incrementoEpubScrollListener, true);
      window._incrementoEpubScrollListener = function() {{
        clearTimeout(window._incrementoEpubScrollTimer);
        window._incrementoEpubScrollTimer = setTimeout(reportProgress, 140);
      }};
      document.addEventListener('scroll', window._incrementoEpubScrollListener, true);

      setTimeout(function() {{
        if (Number(STATE.focusOffset) >= 0) {{
          const point = pointFromOffset(STATE.focusOffset);
          if (point && point.node && point.node.parentElement && point.node.parentElement.scrollIntoView) {{
            point.node.parentElement.scrollIntoView({{ block: 'center' }});
          }}
        }} else if (Number(STATE.scrollRatio) > 0) {{
          window.scrollTo(0, maxScroll() * Number(STATE.scrollRatio));
        }}
        if (STATE.searchQuery) {{
          try {{
            window.find(STATE.searchQuery, false, false, true, false, false, false);
          }} catch (err) {{}}
        }}
        reportProgress();
      }}, 60);
    }})();
    """


def _build_epub_dock() -> None:
    global _epub_dock, _epub_shortcuts_registered, _epub_key_filter

    dock = QDockWidget("EPUB", mw)
    dock.setObjectName("incremento_epub_dock")
    dock.setMinimumWidth(430)

    container = QWidget(dock)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)

    if _epub_key_filter is None:
        _epub_key_filter = _EpubShortcutFilter(mw)
    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_epub_key_filter)
    mw.installEventFilter(_epub_key_filter)

    toolbar = QHBoxLayout()
    dock._prev_btn = QPushButton("Prev")
    dock._next_btn = QPushButton("Next")
    dock._title_lbl = QLabel("EPUB")
    dock._title_lbl.setWordWrap(True)
    dock._title_lbl.setStyleSheet("font-weight: bold;")
    dock._source_lbl = QLabel("")
    dock._source_lbl.setStyleSheet("font-size: 11px; color: gray;")
    dock._add_card_btn = QPushButton("Add Card")
    dock._browser_btn = QPushButton("Browser")
    dock._all_cards_btn = QPushButton("All Cards")
    dock._due_review_btn = QPushButton("Review Due")
    dock._limit_btn = QPushButton("Limit")
    dock._text_smaller_btn = QPushButton("A-")
    dock._text_larger_btn = QPushButton("A+")
    dock._highlight_btn = QPushButton("Highlight")
    dock._snapshot_btn = QPushButton("Snapshot")
    dock._bookmark_add_btn = QPushButton("Bookmark")
    dock._bookmarks_btn = QPushButton("Bookmarks")
    dock._finished_btn = QPushButton("Finished")
    dock._finished_btn.setCheckable(True)
    toolbar.addWidget(dock._prev_btn)
    toolbar.addWidget(dock._next_btn)
    toolbar.addWidget(dock._title_lbl, 1)
    toolbar.addWidget(dock._source_lbl)
    toolbar.addWidget(dock._add_card_btn)
    toolbar.addWidget(dock._browser_btn)
    toolbar.addWidget(dock._all_cards_btn)
    toolbar.addWidget(dock._due_review_btn)
    toolbar.addWidget(dock._limit_btn)
    toolbar.addWidget(dock._text_smaller_btn)
    toolbar.addWidget(dock._text_larger_btn)
    toolbar.addWidget(dock._highlight_btn)
    toolbar.addWidget(dock._snapshot_btn)
    toolbar.addWidget(dock._bookmark_add_btn)
    toolbar.addWidget(dock._bookmarks_btn)
    toolbar.addWidget(dock._finished_btn)
    layout.addLayout(toolbar)

    page = _EpubDockPage(dock)
    s = page.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    view = QWebEngineView(dock)
    view.setPage(page)
    view.installEventFilter(_epub_key_filter)
    page.installEventFilter(_epub_key_filter)
    dock._view = view
    layout.addWidget(view, stretch=1)

    dock._sources = QTextBrowser()
    dock._sources.setMaximumHeight(120)
    dock._sources.setOpenLinks(False)
    dock._sources.setOpenExternalLinks(False)
    dock._sources.anchorClicked.connect(_open_source_link)
    layout.addWidget(dock._sources)

    dock._bookmarks_panel = QTextBrowser()
    dock._bookmarks_panel.setMaximumHeight(150)
    dock._bookmarks_panel.setOpenLinks(False)
    dock._bookmarks_panel.setOpenExternalLinks(False)
    dock._bookmarks_panel.anchorClicked.connect(_open_epub_bookmark_link)
    dock._bookmarks_panel.setVisible(False)
    layout.addWidget(dock._bookmarks_panel)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _on_visibility_changed(visible: bool) -> None:
        if visible:
            return
        if _cb_epub_view_stopped:
            try:
                _cb_epub_view_stopped(_current_epub_card_id)
            except Exception:
                pass

    dock.visibilityChanged.connect(_on_visibility_changed)

    qconnect(dock._prev_btn.clicked, lambda: _jump_relative(-1))
    qconnect(dock._next_btn.clicked, lambda: _jump_relative(1))
    qconnect(dock._add_card_btn.clicked, lambda: _cb_open_add_card_dock and _cb_open_add_card_dock())
    qconnect(dock._browser_btn.clicked, _browse_current_epub_note)
    qconnect(dock._all_cards_btn.clicked, _open_all_epub_cards_in_browser)
    qconnect(dock._due_review_btn.clicked, lambda: _current_epub_card_id and _offer_due_review_for_epub(int(_current_epub_card_id), force=True))
    qconnect(dock._limit_btn.clicked, lambda: _current_epub_card_id and _open_epub_limit_dialog(int(_current_epub_card_id)))
    qconnect(dock._text_smaller_btn.clicked, lambda: _adjust_epub_text_scale(-0.1))
    qconnect(dock._text_larger_btn.clicked, lambda: _adjust_epub_text_scale(0.1))
    qconnect(dock._highlight_btn.clicked, _request_highlight)
    qconnect(dock._snapshot_btn.clicked, _request_snapshot)
    qconnect(dock._bookmark_add_btn.clicked, _add_current_epub_bookmark)
    qconnect(dock._bookmarks_btn.clicked, _toggle_epub_bookmarks_panel)
    qconnect(dock._finished_btn.clicked, _toggle_finished)
    qconnect(view.loadFinished, _on_load_finished)
    qconnect(view.urlChanged, _on_view_url_changed)

    if not _epub_shortcuts_registered:
        for idx in range(4):
            def _make_handler(field_idx: int):
                return lambda: _trigger_epub_extract_shortcut(field_idx)

            for seq in (f"Ctrl+{idx + 1}", f"Meta+{idx + 1}"):
                sc = QShortcut(QKeySequence(seq), mw)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(_make_handler(idx))
                _epub_shortcuts.append(sc)
        for seq, delta in (("Ctrl+-", -0.1), ("Meta+-", -0.1), ("Ctrl+=", 0.1), ("Meta+=", 0.1)):
            sc = QShortcut(QKeySequence(seq), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda d=delta: _adjust_epub_text_scale(d))
            _epub_shortcuts.append(sc)
        _epub_shortcuts_registered = True

    _epub_dock = dock


def _current_epub_section_title() -> str:
    sections = _current_sections()
    if 0 <= int(_current_epub_section_index) < len(sections):
        return str(sections[int(_current_epub_section_index)].get("title") or "").strip()
    return f"Section {int(_current_epub_section_index) + 1}"


def _epub_bookmarks() -> list[dict]:
    if _current_epub_card_id is None:
        return []
    try:
        return list_reader_bookmarks(
            _ADDON_DIR,
            _active_profile(),
            int(_current_epub_card_id),
            "epub",
        )
    except Exception:
        return []


def _refresh_epub_bookmarks_panel() -> None:
    if _epub_dock is None:
        return
    bookmarks = _epub_bookmarks()
    _epub_dock._bookmarks_btn.setText(f"Bookmarks {len(bookmarks)}")
    if not getattr(_epub_dock, "_bookmarks_panel", None):
        return
    html = ["<div style='font-family:sans-serif;font-size:12px'>"]
    html.append("<b>Interesting-place bookmarks</b>")
    if bookmarks:
        html.append("<ul>")
        for bookmark in bookmarks:
            bookmark_id = escape(str(bookmark.get("id") or ""))
            label = escape(str(bookmark.get("label") or "Bookmark"))
            location = bookmark.get("location") or {}
            section = int(location.get("section_index", 0) or 0) + 1
            html.append(
                "<li>"
                f"<span>{label}</span> <span style='color:#888'>section {section}</span> "
                f"<a href='inc://epub-bookmark-open/{bookmark_id}'>Jump</a> "
                f"<a href='inc://epub-bookmark-delete/{bookmark_id}' style='color:#c66'>Delete</a>"
                "</li>"
            )
        html.append("</ul>")
    else:
        html.append("<div style='color:#888;padding:6px 0 0'>No bookmarks yet.</div>")
    html.append("</div>")
    _epub_dock._bookmarks_panel.setHtml("".join(html))


def _add_current_epub_bookmark() -> None:
    if _current_epub_card_id is None:
        return
    try:
        add_reader_bookmark(
            _ADDON_DIR,
            _active_profile(),
            int(_current_epub_card_id),
            "epub",
            {
                "section_index": int(_current_epub_section_index),
                "scroll_ratio": float(_current_epub_scroll_ratio),
                "section_title": _current_epub_section_title(),
            },
        )
    except Exception as exc:
        showInfo(f"Could not save EPUB bookmark:\n{exc}")
        return
    if _epub_dock is not None:
        _epub_dock._bookmarks_panel.setVisible(True)
    _refresh_epub_bookmarks_panel()
    tooltip("EPUB bookmark saved.")


def _toggle_epub_bookmarks_panel() -> None:
    if _epub_dock is None:
        return
    _refresh_epub_bookmarks_panel()
    _epub_dock._bookmarks_panel.setVisible(not _epub_dock._bookmarks_panel.isVisible())


def _open_epub_bookmark_link(url: QUrl) -> None:
    if _current_epub_card_id is None or _current_epub_filename is None:
        return
    s = url.toString()
    bookmark_id = s.rsplit("/", 1)[-1]
    if s.startswith("inc://epub-bookmark-delete/"):
        try:
            delete_reader_bookmark(
                _ADDON_DIR,
                _active_profile(),
                int(_current_epub_card_id),
                "epub",
                bookmark_id,
            )
        except Exception as exc:
            showInfo(f"Could not delete EPUB bookmark:\n{exc}")
        _refresh_epub_bookmarks_panel()
        return
    if not s.startswith("inc://epub-bookmark-open/"):
        return
    bookmark = next((item for item in _epub_bookmarks() if str(item.get("id") or "") == bookmark_id), None)
    if not bookmark:
        return
    location = bookmark.get("location") or {}
    show_epub_in_dock(
        int(_current_epub_card_id),
        _current_epub_filename,
        section_index=int(location.get("section_index", 0) or 0),
        scroll_ratio=float(location.get("scroll_ratio", 0.0) or 0.0),
        offer_due_review_prompt=False,
    )


def _open_source_link(url: QUrl) -> None:
    try:
        s = url.toString()
        if s.startswith("inc://card/"):
            note_id = int(s.rsplit("/", 1)[1])
            _browse_note_ids_in_browser([note_id])
        elif s.startswith("inc://epub-highlight-note/"):
            _edit_current_epub_highlight_note(s.rsplit("/", 1)[1])
        elif s.startswith("inc://epub-highlight-delete/"):
            _delete_current_epub_highlight(s.rsplit("/", 1)[1])
    except Exception:
        pass


def _browse_note_ids_in_browser(note_ids: list[int], *, empty_message: str = "") -> bool:
    ordered: list[int] = []
    seen: set[int] = set()
    for raw_note_id in list(note_ids or []):
        try:
            note_id = int(raw_note_id or 0)
        except Exception:
            note_id = 0
        if note_id <= 0 or note_id in seen:
            continue
        seen.add(note_id)
        ordered.append(note_id)

    if not ordered:
        if empty_message:
            tooltip(empty_message)
        return False

    try:
        from aqt import dialogs

        browser = dialogs.open("Browser", mw)
        browser.search_for(" OR ".join(f"nid:{note_id}" for note_id in ordered))
        return True
    except Exception:
        return False


def _open_all_epub_cards_in_browser() -> None:
    if _current_epub_card_id is None:
        return
    note_ids = get_epub_document_source_note_ids(
        _ADDON_DIR,
        _active_profile(),
        int(_current_epub_card_id),
    )
    _browse_note_ids_in_browser(note_ids, empty_message="No cards created from this EPUB yet.")


def _current_section_highlights() -> list[dict]:
    if _current_epub_card_id is None:
        return []
    return [
        row
        for row in load_highlights(_ADDON_DIR, _active_profile(), int(_current_epub_card_id))
        if int(row.get("sectionIndex", -1)) == int(_current_epub_section_index)
    ]


def _edit_current_epub_highlight_note(hl_id: str) -> None:
    if _current_epub_card_id is None:
        return
    highlight = next(
        (row for row in _current_section_highlights() if str(row.get("id") or "") == str(hl_id or "")),
        None,
    )
    if not highlight:
        showInfo("That EPUB highlight could not be found.")
        return
    dialog = HighlightNoteDialog(
        mw,
        title="EPUB Highlight Note",
        excerpt=str(highlight.get("text") or ""),
        current_note=str(highlight.get("note") or ""),
    )
    if not dialog.exec():
        return
    try:
        updated = update_highlight_note(
            _ADDON_DIR,
            _active_profile(),
            int(_current_epub_card_id),
            str(highlight.get("id") or ""),
            dialog.note_text(),
        )
    except Exception as exc:
        showInfo(f"Could not save the EPUB highlight note.\n\n{exc}")
        return
    if not updated:
        showInfo("That EPUB highlight could not be updated.")
        return
    _update_sources_panel()
    tooltip("EPUB highlight note saved.")


def _delete_current_epub_highlight(hl_id: str) -> None:
    if _current_epub_card_id is None:
        return
    try:
        remove_highlight(_ADDON_DIR, _active_profile(), int(_current_epub_card_id), str(hl_id or ""))
    except Exception as exc:
        showInfo(f"Could not remove that EPUB highlight.\n\n{exc}")
        return
    try:
        _load_current_section()
    except Exception:
        _update_sources_panel()
    tooltip("EPUB highlight removed.")


def _browse_current_epub_note() -> None:
    if _current_epub_card_id is None:
        return
    try:
        card = mw.col.get_card(int(_current_epub_card_id))
        note_id = int(card.nid)
        _browse_note_ids_in_browser([note_id])
    except Exception:
        pass


def _trigger_epub_extract_shortcut(idx: int) -> None:
    if _epub_dock is None or not _epub_dock.isVisible():
        return
    try:
        _epub_dock._view.page().runJavaScript(
            """
            (function(idx) {
              var meta = window._lastEpubSelectionMeta || null;
              if (!meta || !meta.text) { return false; }
              console.log('__incremento_epub__:' + 'incremento_epub_fill_field:' + JSON.stringify({
                idx: idx,
                text: meta.text,
                startOffset: Number(meta.startOffset || -1),
                endOffset: Number(meta.endOffset || -1)
              }));
              return true;
            })(%d);
            """
            % int(idx)
        )
    except Exception:
        pass


class _EpubShortcutFilter(QObject):
    def eventFilter(self, watched, event):
        try:
            if event.type() not in (
                QEvent.Type.ShortcutOverride,
                QEvent.Type.KeyPress,
            ):
                return False
            if _epub_dock is None or not _epub_dock.isVisible():
                return False
            mods = event.modifiers()
            if not (
                mods
                & (
                    Qt.KeyboardModifier.MetaModifier
                    | Qt.KeyboardModifier.ControlModifier
                )
            ):
                return False
            key_to_idx = {
                Qt.Key.Key_1: 0,
                Qt.Key.Key_Exclam: 0,
                Qt.Key.Key_2: 1,
                Qt.Key.Key_At: 1,
                Qt.Key.Key_3: 2,
                Qt.Key.Key_NumberSign: 2,
                Qt.Key.Key_4: 3,
                Qt.Key.Key_Dollar: 3,
            }
            idx = key_to_idx.get(event.key())
            if idx is None:
                return False
            event.accept()
            if event.type() == QEvent.Type.KeyPress:
                _trigger_epub_extract_shortcut(idx)
            return True
        except Exception:
            return False


def _handle_epub_snapshot(msg: str) -> None:
    import tempfile as _tmp

    if _epub_dock is None:
        return
    try:
        data = json.loads(msg[len(_MSG_SNAPSHOT) :])
        rect = data.get("rect") or {}
        x = max(0, int(rect.get("x", 0) or 0))
        y = max(0, int(rect.get("y", 0) or 0))
        width = max(1, int(rect.get("width", 0) or 0))
        height = max(1, int(rect.get("height", 0) or 0))

        view_pixmap = _epub_dock._view.grab()
        if view_pixmap.isNull():
            raise RuntimeError("Could not capture EPUB snapshot.")

        max_width = max(0, view_pixmap.width() - x)
        max_height = max(0, view_pixmap.height() - y)
        width = min(width, max_width)
        height = min(height, max_height)
        if width <= 1 or height <= 1:
            raise RuntimeError("Selected text is outside the visible EPUB viewport.")

        snapshot = view_pixmap.copy(x, y, width, height)
        if snapshot.isNull():
            raise RuntimeError("Could not crop EPUB snapshot.")

        with _tmp.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        try:
            if not snapshot.save(tmp_path, "PNG"):
                raise RuntimeError("Could not encode EPUB snapshot.")
            media_filename = mw.col.media.add_file(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        if _cb_open_add_card_dock:
            _cb_open_add_card_dock()

        field_names = []
        try:
            dock = _cb_get_add_card_dock() if _cb_get_add_card_dock else None
            if dock:
                note = dock.widget().editor.note
                if note:
                    field_names = [f["name"] for f in note.note_type()["flds"]]
        except Exception:
            pass
        if not field_names:
            field_names = [f"Field {i + 1}" for i in range(4)]

        scaled = snapshot.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
        if scaled.height() > 180:
            scaled = snapshot.scaledToHeight(180, Qt.TransformationMode.SmoothTransformation)

        picker = QDialog(mw)
        picker.setWindowTitle("Insert snapshot into field")
        picker.setFixedWidth(340)
        layout = QVBoxLayout(picker)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        preview_lbl = QLabel()
        preview_lbl.setPixmap(scaled)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview_lbl)

        layout.addSpacing(14)
        layout.addWidget(QLabel("Insert image into:"))
        layout.addSpacing(8)

        chosen_idx = [-1]

        def _make_handler(idx):
            def _handler():
                chosen_idx[0] = idx
                picker.accept()

            return _handler

        for i, name in enumerate(field_names):
            btn = QPushButton(name)
            btn.setStyleSheet("text-align: left; padding: 7px 12px;")
            btn.clicked.connect(_make_handler(i))
            layout.addWidget(btn)
            layout.addSpacing(4)

        layout.addSpacing(8)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(picker.reject)
        layout.addWidget(cancel_btn)

        if not picker.exec() or chosen_idx[0] < 0:
            return

        if _cb_fill_dock_field:
            _cb_fill_dock_field(
                chosen_idx[0],
                f'<img src="{media_filename}">',
                include_pdf_citation=False,
                source_link_kind="epub",
            )
    except Exception as exc:
        showInfo(f"EPUB snapshot failed:\n{exc}")


def _current_metadata() -> dict:
    if not _current_epub_filename:
        return {}
    return load_epub_metadata(_ADDON_DIR, _current_epub_filename)


def _current_sections() -> list[dict]:
    return list((_current_metadata().get("sections") or []))


def _update_title_and_buttons() -> None:
    if _epub_dock is None:
        return
    sections = _current_sections()
    count = len(sections)
    if count:
        idx = max(0, min(_current_epub_section_index, count - 1))
        section = sections[idx]
        if _current_epub_total_pages > 0:
            _epub_dock._title_lbl.setText(
                f"Page {_current_epub_page_index + 1} / {_current_epub_total_pages} — "
                f"{section.get('title') or f'Section {idx + 1}'}"
            )
        else:
            _epub_dock._title_lbl.setText(
                f"{section.get('title') or f'Section {idx + 1}'} ({idx + 1}/{count})"
            )
        _epub_dock._prev_btn.setEnabled(idx > 0 or _current_epub_scroll_ratio > 0.001)
        _epub_dock._next_btn.setEnabled(idx + 1 < count or _current_epub_scroll_ratio < 0.999)
    else:
        _epub_dock._title_lbl.setText("EPUB")
        _epub_dock._prev_btn.setEnabled(False)
        _epub_dock._next_btn.setEnabled(False)
    has_card = _current_epub_card_id is not None
    _epub_dock._browser_btn.setEnabled(has_card)
    _epub_dock._due_review_btn.setEnabled(has_card)
    _epub_dock._limit_btn.setEnabled(has_card)
    _epub_dock._text_smaller_btn.setEnabled(has_card)
    _epub_dock._text_larger_btn.setEnabled(has_card)
    _epub_dock._snapshot_btn.setEnabled(has_card)
    _epub_dock._bookmark_add_btn.setEnabled(has_card)
    _epub_dock._bookmarks_btn.setEnabled(has_card)
    _epub_dock._finished_btn.blockSignals(True)
    _epub_dock._finished_btn.setChecked(bool(_current_epub_finished))
    _epub_dock._finished_btn.blockSignals(False)
    _refresh_epub_bookmarks_panel()


def _update_sources_panel() -> None:
    if _epub_dock is None or _current_epub_card_id is None:
        return
    cards = get_epub_card_sources(_ADDON_DIR, _active_profile(), _current_epub_card_id, _current_epub_section_index)
    counts = get_epub_section_card_counts(_ADDON_DIR, _active_profile(), _current_epub_card_id)
    count = int(counts.get(_current_epub_section_index, 0) or 0)
    highlights = _current_section_highlights()
    _epub_dock._source_lbl.setText(f"Cards here: {count}  •  Highlights: {len(highlights)}")
    html = ["<div style='font-family:sans-serif;font-size:12px'>"]
    if cards:
        html.append("<b>Cards from this section</b><ul>")
        for item in cards:
            note_id = int(item.get("note_id") or 0)
            excerpt = escape(str(item.get("excerpt") or ""))
            html.append(
                f"<li><a href='inc://card/{note_id}'>note {note_id}</a>"
                f" <span style='color:#888'>{excerpt}</span></li>"
            )
        html.append("</ul>")
    else:
        html.append("<div style='color:#888;padding:2px 0 10px'>No cards created from this section yet.</div>")

    if highlights:
        html.append("<b>Highlights in this section</b><ul>")
        for highlight in highlights:
            highlight_id = escape(str(highlight.get("id") or ""))
            text = escape(str(highlight.get("text") or "").strip() or "(no text)")
            note = escape(str(highlight.get("note") or "").strip())
            action_label = "Edit note" if note else "Add note"
            html.append(
                "<li>"
                f"<span>{text}</span>"
                f" <a href='inc://epub-highlight-note/{highlight_id}'>{action_label}</a>"
                f" <a href='inc://epub-highlight-delete/{highlight_id}' style='color:#c66'>Delete</a>"
            )
            if note:
                html.append(
                    f"<div style='color:#9ec4ff;padding-top:2px'>Note: {note}</div>"
                )
            html.append("</li>")
        html.append("</ul>")
    else:
        html.append("<div style='color:#888;padding:6px 0 0'>No highlights in this section yet.</div>")
    html.append("</div>")
    _epub_dock._sources.setHtml("".join(html))


def _record_progress(
    section_index: int,
    scroll_ratio: float,
    *,
    page_index: int | None = None,
    total_pages: int | None = None,
    section_page: int | None = None,
    section_pages: int | None = None,
) -> None:
    global _current_epub_section_index, _current_epub_scroll_ratio
    global _current_epub_page_index, _current_epub_total_pages, _current_epub_section_page, _current_epub_section_pages
    if _current_epub_card_id is None:
        return
    _current_epub_section_index = max(0, int(section_index))
    _current_epub_scroll_ratio = max(0.0, min(float(scroll_ratio), 1.0))
    if page_index is not None:
        _current_epub_page_index = max(0, int(page_index))
    if total_pages is not None:
        _current_epub_total_pages = max(0, int(total_pages))
    if section_page is not None:
        _current_epub_section_page = max(1, int(section_page))
    if section_pages is not None:
        _current_epub_section_pages = max(1, int(section_pages))
    try:
        set_epub_progress(
            _ADDON_DIR,
            _active_profile(),
            _current_epub_card_id,
            section_index=_current_epub_section_index,
            scroll_ratio=_current_epub_scroll_ratio,
            is_finished=_current_epub_finished,
        )
        get_epub_daily_limit_status(
            _ADDON_DIR,
            _active_profile(),
            _current_epub_card_id,
            current_section_index=_current_epub_section_index,
            current_page_index=_current_epub_page_index,
        )
    except Exception:
        pass
    _update_title_and_buttons()
    _update_sources_panel()


def _section_index_from_path(local_path: str) -> int | None:
    if not _current_epub_filename:
        return None
    normalized = os.path.normpath(local_path or "")
    for idx, _section in enumerate(_current_sections()):
        section_path = os.path.normpath(get_epub_section_path(_ADDON_DIR, _current_epub_filename, idx))
        if section_path == normalized:
            return idx
    return None


def _on_view_url_changed(url: QUrl) -> None:
    global _current_epub_section_index, _pending_focus_offset, _pending_restore_ratio, _pending_search_query, _pending_explicit_navigation
    idx = _section_index_from_path(url.toLocalFile())
    if idx is None:
        return
    _current_epub_section_index = idx
    if not _pending_explicit_navigation:
        _pending_focus_offset = -1
        _pending_restore_ratio = 0.0
        _pending_search_query = ""
    _pending_explicit_navigation = False
    _record_progress(_current_epub_section_index, 0.0 if _pending_focus_offset >= 0 else _current_epub_scroll_ratio)


def _on_load_finished(ok: bool) -> None:
    global _pending_focus_offset, _pending_restore_ratio, _pending_search_query
    if not ok or _epub_dock is None or _current_epub_card_id is None:
        return
    highlights = [
        hl
        for hl in load_highlights(_ADDON_DIR, _active_profile(), _current_epub_card_id)
        if int(hl.get("sectionIndex", -1)) == int(_current_epub_section_index)
    ]
    js = _build_page_script(
        card_id=_current_epub_card_id,
        section_index=_current_epub_section_index,
        scroll_ratio=_pending_restore_ratio if _pending_focus_offset < 0 else 0.0,
        text_scale=_current_epub_font_scale,
        focus_offset=_pending_focus_offset,
        search_query=_pending_search_query,
        highlights=highlights,
    )
    _epub_dock._view.page().runJavaScript(js)
    _pending_focus_offset = -1
    _pending_restore_ratio = _current_epub_scroll_ratio
    _pending_search_query = ""
    _update_title_and_buttons()
    _update_sources_panel()


def _load_current_section() -> None:
    if _epub_dock is None or _current_epub_filename is None:
        return
    try:
        path = get_epub_section_path(_ADDON_DIR, _current_epub_filename, _current_epub_section_index)
    except Exception as exc:
        showInfo(f"Could not open EPUB section:\n{exc}")
        return
    _epub_dock._view.load(QUrl.fromLocalFile(path))


def show_epub_in_dock(
    card_id: int,
    filename: str,
    *,
    section_index: int,
    scroll_ratio: float = 0.0,
    focus_offset: int = -1,
    search_query: str = "",
    offer_due_review_prompt: bool = True,
) -> None:
    global _epub_dock, _current_epub_card_id, _current_epub_filename, _current_epub_section_index
    global _current_epub_scroll_ratio, _current_epub_finished, _current_epub_font_scale, _pending_focus_offset, _pending_restore_ratio
    global _current_epub_page_index, _current_epub_total_pages, _current_epub_section_page, _current_epub_section_pages
    global _pending_search_query, _pending_explicit_navigation, _last_selection_meta

    if _epub_dock is None:
        _build_epub_dock()

    _current_epub_card_id = int(card_id)
    _current_epub_filename = str(filename or "").strip()
    _current_epub_section_index = max(0, int(section_index))
    _current_epub_scroll_ratio = max(0.0, min(float(scroll_ratio), 1.0))
    _current_epub_page_index = max(0, _current_epub_section_index)
    _current_epub_total_pages = 0
    _current_epub_section_page = 1
    _current_epub_section_pages = 1
    _pending_focus_offset = int(focus_offset)
    _pending_restore_ratio = _current_epub_scroll_ratio
    _pending_search_query = str(search_query or "")
    _pending_explicit_navigation = True
    _last_selection_meta = {}
    _, _, _current_epub_finished = get_epub_progress(_ADDON_DIR, _active_profile(), _current_epub_card_id)
    _current_epub_font_scale = get_epub_font_scale(_ADDON_DIR, _active_profile(), _current_epub_card_id)

    _update_title_and_buttons()
    _update_sources_panel()
    _epub_dock.show()
    _epub_dock.raise_()
    if _cb_epub_view_started:
        try:
            _cb_epub_view_started(int(card_id))
        except Exception:
            pass
    _load_current_section()
    if offer_due_review_prompt:
        QTimer.singleShot(
            0,
            lambda cid=int(card_id), idx=int(section_index): _offer_due_review_for_epub(
                cid,
                current_section_index=idx,
                force=False,
            ),
        )


def open_epub_location(
    card_id: int,
    section_index: int | None = None,
    *,
    focus_offset: int = -1,
    search_query: str = "",
) -> None:
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note[EPUB_FILE_FIELD]
    current_section, current_ratio, _is_finished = get_epub_progress(_ADDON_DIR, _active_profile(), card_id)
    show_epub_in_dock(
        card_id,
        filename,
        section_index=current_section if section_index is None else int(section_index),
        scroll_ratio=current_ratio,
        focus_offset=focus_offset,
        search_query=search_query,
    )


def _on_epub_selection(idx: int, text: str, start_offset: int, end_offset: int) -> None:
    global _last_selection_meta
    cleaned = str(text or "").strip()
    if not cleaned or _cb_fill_dock_field is None:
        return
    _last_selection_meta = {
        "text": cleaned,
        "startOffset": int(start_offset),
        "endOffset": int(end_offset),
    }
    if _cb_open_add_card_dock:
        _cb_open_add_card_dock()
    _cb_fill_dock_field(
        idx,
        cleaned,
        include_pdf_citation=False,
        citation_html=epub_citation(),
        source_link_kind="epub",
    )


def _jump_relative(delta: int) -> None:
    if _epub_dock is None or _current_epub_card_id is None:
        return
    if int(delta) > 0 and not _check_epub_limit_before_navigation(_current_epub_page_index + 1):
        return
    _record_progress(_current_epub_section_index, _current_epub_scroll_ratio)
    _epub_dock._view.page().runJavaScript(
        f"window.incrementoEpubPageNav && window.incrementoEpubPageNav({1 if int(delta) > 0 else -1});"
    )


def _jump_section_boundary(delta: int) -> None:
    sections = _current_sections()
    if not sections or _current_epub_filename is None or _current_epub_card_id is None:
        return
    next_idx = max(0, min(_current_epub_section_index + int(delta), len(sections) - 1))
    if next_idx == _current_epub_section_index:
        return
    if next_idx > _current_epub_section_index and not _check_epub_limit_before_navigation(_current_epub_page_index + 1):
        return
    _record_progress(_current_epub_section_index, _current_epub_scroll_ratio)
    if next_idx > _current_epub_section_index:
        try:
            set_read_section_index(
                _ADDON_DIR,
                _active_profile(),
                int(_current_epub_card_id),
                int(next_idx),
            )
        except Exception:
            pass
    show_epub_in_dock(
        _current_epub_card_id,
        _current_epub_filename,
        section_index=next_idx,
        scroll_ratio=0.0 if int(delta) > 0 else 1.0,
        offer_due_review_prompt=False,
    )


def _request_highlight() -> None:
    if _epub_dock is None:
        return
    _epub_dock._view.page().runJavaScript(
        "window.incrementoAddEpubHighlight && window.incrementoAddEpubHighlight();"
    )


def _request_snapshot() -> None:
    if _epub_dock is None:
        return
    _epub_dock._view.page().runJavaScript(
        "window.incrementoSnapshotEpubSelection && window.incrementoSnapshotEpubSelection();"
    )


def _adjust_epub_text_scale(delta: float) -> None:
    global _current_epub_font_scale
    if _current_epub_card_id is None:
        return
    try:
        _current_epub_font_scale = set_epub_font_scale(
            _ADDON_DIR,
            _active_profile(),
            int(_current_epub_card_id),
            float(_current_epub_font_scale) + float(delta),
        )
        _load_current_section()
    except Exception as exc:
        showInfo(f"Could not change EPUB text size:\n{exc}")


def _toggle_finished(checked: bool) -> None:
    global _current_epub_finished
    _current_epub_finished = bool(checked)
    if _current_epub_card_id is None:
        return
    try:
        set_epub_progress(
            _ADDON_DIR,
            _active_profile(),
            _current_epub_card_id,
            section_index=_current_epub_section_index,
            scroll_ratio=_current_epub_scroll_ratio,
            is_finished=_current_epub_finished,
        )
    except Exception:
        pass


def on_epub_question_shown(card) -> None:
    global _epub_dock
    try:
        if card is None:
            return
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        if model is None or model.get("name") != EPUB_NOTE_TYPE:
            if _epub_dock is not None:
                try:
                    _epub_dock.hide()
                    if _cb_epub_view_stopped:
                        _cb_epub_view_stopped(_current_epub_card_id)
                except RuntimeError:
                    _epub_dock = None
            return
        filename = note[EPUB_FILE_FIELD]
        section_index, scroll_ratio, _is_finished = get_epub_progress(_ADDON_DIR, _active_profile(), card.id)
        show_epub_in_dock(
            card.id,
            filename,
            section_index=section_index,
            scroll_ratio=scroll_ratio,
        )
    except Exception as exc:
        print(f"[Incremento] on_epub_question_shown error: {exc}")


def on_epub_reviewer_will_end() -> None:
    global _epub_dock
    if _epub_dock is not None:
        try:
            _epub_dock.hide()
            if _cb_epub_view_stopped:
                _cb_epub_view_stopped(_current_epub_card_id)
        except RuntimeError:
            _epub_dock = None


def on_add_cards_did_add_note(note) -> None:
    if _current_epub_card_id is None:
        return
    try:
        from . import add_card_dock as _add_card_dock_mod

        source = _add_card_dock_mod.recent_fill_source()
        if source and source != "epub":
            return
    except Exception:
        pass
    import re as _re

    parts = []
    for field in (note.fields or [])[:2]:
        plain = _re.sub(r"<[^>]+>", "", field).strip()[:120]
        if plain:
            parts.append(plain)
    excerpt = " / ".join(parts)[:200]
    try:
        add_epub_card_source(
            _ADDON_DIR,
            _active_profile(),
            _current_epub_card_id,
            _current_epub_section_index,
            note.id,
            excerpt,
        )
    except Exception:
        pass
    _update_sources_panel()

    cid = _current_epub_card_id

    def _restore_epub_dock() -> None:
        if _current_epub_card_id != cid:
            return
        try:
            if _epub_dock is not None and not _epub_dock.isVisible():
                _epub_dock.show()
        except RuntimeError:
            pass

    QTimer.singleShot(0, _restore_epub_dock)


def get_selected_text(callback) -> None:
    if _epub_dock is None:
        callback("")
        return
    try:
        _epub_dock._view.page().runJavaScript(
            "(function(){ return (window._lastEpubSelection || '').trim(); })();",
            lambda text: callback(str(text or "").strip()),
        )
    except Exception:
        callback("")


def sync_epub_note_type() -> None:
    try:
        ensure_epub_note_type(mw.col)
    except Exception:
        pass
