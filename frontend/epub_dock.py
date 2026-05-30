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
    QFrame,
    QFormLayout,
    QFontMetrics,
    QHBoxLayout,
    QKeySequence,
    QLayout,
    QLabel,
    QPixmap,
    QPoint,
    QPushButton,
    QRect,
    QShortcut,
    QSize,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QTextBrowser,
    QTextEdit,
    QTimer,
    QToolButton,
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
        get_read_anchor,
        get_read_section_index,
        get_epub_section_path,
        load_epub_metadata,
        regenerate_epub_card_cover,
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
        get_read_anchor,
        get_read_section_index,
        get_epub_section_path,
        load_epub_metadata,
        regenerate_epub_card_cover,
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
_ADDON_PKG = __name__.split(".")[0] if "." in __name__ else "incremento"

_epub_dock = None
_current_epub_card_id: int | None = None
_current_epub_filename: str | None = None
_current_epub_section_index = 0
_current_epub_scroll_ratio = 0.0
_current_epub_finished = False
_current_epub_font_scale = 1.0
_current_epub_read_anchor: dict | None = None
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
_MSG_HL_NOTE = "incremento_epub_hl_note:"
_MSG_PROGRESS = "incremento_epub_progress:"
_MSG_MARK_READ = "incremento_epub_mark_read:"
_MSG_SECTION_NAV = "incremento_epub_section_nav:"
_MSG_SNAPSHOT = "incremento_epub_snapshot:"
_MSG_SELECTION_STATE = "incremento_selection_state:"

_current_epub_page_index = 0
_current_epub_total_pages = 0
_current_epub_section_page = 1
_current_epub_section_pages = 1


def _config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        return mw.addonManager.getConfig(_ADDON_PKG) or {}
    except Exception:
        return {}


def configured_highlight_when_extracting(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get("highlight_when_extracting", True))


def _set_highlight_when_extracting(enabled: bool) -> None:
    cfg = _config()
    cfg["highlight_when_extracting"] = bool(enabled)
    try:
        mw.addonManager.writeConfig(_ADDON_PKG, cfg)
    except Exception:
        return


def _record_timer_epub_page_read(card_id: int | None, page_index: int | None) -> None:
    if card_id is None or page_index is None:
        return
    try:
        try:
            from . import timer_widget as _timer_mod
        except Exception:
            import timer_widget as _timer_mod  # type: ignore
        _timer_mod.record_epub_page_read(int(card_id), int(page_index))
    except Exception:
        pass


class _ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = str(text or "")
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._apply_elision()

    def set_full_text(self, text: str) -> None:
        self._full_text = str(text or "")
        self._apply_elision()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        text = metrics.elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            max(24, self.contentsRect().width()),
        )
        super().setText(text)
        self.setToolTip(self._full_text if text != self._full_text else "")


class _FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = area.x()
        y = area.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if line_height > 0 and next_x > area.right() + 1:
                x = area.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h_spacing
            line_height = max(line_height, hint.height())

        return (y - rect.y()) + line_height + margins.bottom()


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


def _add_card_source_for_new_note() -> str:
    try:
        try:
            from . import add_card_dock as _add_card_dock_mod
        except Exception:
            import add_card_dock as _add_card_dock_mod  # type: ignore

        pending = _add_card_dock_mod.pending_extract_options()
        pending_source = str((pending or {}).get("source") or "").strip()
        if pending_source:
            return pending_source
        return str(_add_card_dock_mod.recent_fill_source() or "").strip()
    except Exception:
        return ""


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
        if msg.startswith(_MSG_HL_NOTE):
            try:
                data = json.loads(msg[len(_MSG_HL_NOTE) :])
                _edit_current_epub_highlight_note(str(data.get("id") or ""))
            except Exception as exc:
                print(f"[Incremento] epub_dock highlight note failed: {exc}")
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
        if msg.startswith(_MSG_MARK_READ):
            try:
                data = json.loads(msg[len(_MSG_MARK_READ) :])
                _set_epub_read_marker(
                    int(data.get("cardId", _current_epub_card_id or 0) or 0),
                    int(data.get("sectionIndex", _current_epub_section_index) or 0),
                    data.get("anchor"),
                )
            except Exception as exc:
                print(f"[Incremento] epub_dock read marker failed: {exc}")
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
    read_anchor: dict | None,
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
        "readAnchor": read_anchor if isinstance(read_anchor, dict) else None,
        "autoHighlightOnExtract": configured_highlight_when_extracting(),
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
          span.incremento-epub-highlight[data-note-present="1"] {{
            box-shadow: inset 0 -1px 0 rgba(37, 99, 235, 0.55);
          }}
          #incremento-epub-highlight-actions {{
            position: absolute;
            z-index: 2147483200;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px;
            border-radius: 999px;
            background: rgba(20, 24, 31, 0.96);
            border: 1px solid rgba(255,255,255,0.14);
            box-shadow: 0 10px 24px rgba(0,0,0,0.28);
          }}
          #incremento-epub-highlight-actions button {{
            width: 24px;
            height: 24px;
            border: none;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            padding: 0;
          }}
          #incremento-epub-highlight-actions button svg {{
            width: 13px;
            height: 13px;
            display: block;
          }}
          #incremento-epub-highlight-note-btn {{
            background: rgba(55, 65, 81, 0.94);
            color: #f8fafc;
          }}
          #incremento-epub-highlight-note-btn[data-has-note="1"] {{
            background: rgba(37, 99, 235, 0.96);
            color: #eff6ff;
            box-shadow: 0 0 0 1px rgba(191, 219, 254, 0.22);
          }}
          #incremento-epub-highlight-delete-btn {{
            background: rgba(127, 29, 29, 0.96);
            color: #fee2e2;
          }}
          #incremento-epub-read-marker {{
            position: absolute;
            z-index: 2147483000;
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 10px 12px 10px 10px;
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(8,145,178,0.96), rgba(14,116,144,0.96));
            color: #ecfeff;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            border: 1px solid rgba(103,232,249,0.6);
            box-shadow: 0 10px 24px rgba(0,0,0,0.28);
            pointer-events: none;
          }}
          #incremento-epub-read-marker .incremento-epub-read-marker-arrow {{
            font-size: 26px;
            line-height: 1;
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
              if (!node.nodeValue || !node.nodeValue.length) return NodeFilter.FILTER_REJECT;
              const parent = node.parentElement;
              if (!parent) return NodeFilter.FILTER_REJECT;
              if (/^(SCRIPT|STYLE|NOSCRIPT)$/i.test(parent.tagName || '')) return NodeFilter.FILTER_REJECT;
              if (parent.closest && parent.closest('#incremento-epub-read-marker')) return NodeFilter.FILTER_REJECT;
              return NodeFilter.FILTER_ACCEPT;
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
      function iconSvg(kind) {{
        if (kind === 'delete') {{
          return (
            '<svg aria-hidden="true" viewBox="0 0 16 16">' +
            '<path d="M4.2 4.2l7.6 7.6M11.8 4.2l-7.6 7.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>' +
            '</svg>'
          );
        }}
        return (
          '<svg aria-hidden="true" viewBox="0 0 16 16">' +
          '<path d="M3 2.5h6.5L13 6v7a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 3 13z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>' +
          '<path d="M9.5 2.5V6H13" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>' +
          '<path d="M5.2 8.1h5.2M5.2 10.2h4" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>' +
          '</svg>'
        );
      }}
      function removeHighlightActionMenu() {{
        const existing = document.getElementById('incremento-epub-highlight-actions');
        if (existing && existing.parentNode) {{
          existing.parentNode.removeChild(existing);
        }}
        window._incrementoEpubHighlightActionTarget = null;
      }}
      function positionHighlightActionMenu(target, menu) {{
        if (!target || !menu) return;
        const rect = target.getBoundingClientRect();
        const menuWidth = menu.offsetWidth || 58;
        const menuHeight = menu.offsetHeight || 32;
        const left = Math.min(
          window.scrollX + window.innerWidth - menuWidth - 8,
          Math.max(window.scrollX + 8, window.scrollX + rect.right - menuWidth)
        );
        const preferredTop = window.scrollY + rect.top - menuHeight - 10;
        const fallbackTop = window.scrollY + rect.bottom + 8;
        const top = preferredTop > window.scrollY + 8 ? preferredTop : fallbackTop;
        menu.style.left = Math.round(left) + 'px';
        menu.style.top = Math.round(top) + 'px';
      }}
      function syncHighlightActionMenu(target) {{
        const menu = document.getElementById('incremento-epub-highlight-actions');
        if (!menu || !target) return;
        const noteButton = document.getElementById('incremento-epub-highlight-note-btn');
        const deleteButton = document.getElementById('incremento-epub-highlight-delete-btn');
        const hasNote = String(target.dataset.note || '').trim().length > 0;
        if (noteButton) {{
          noteButton.dataset.hasNote = hasNote ? '1' : '0';
          noteButton.title = hasNote ? 'Edit highlight note' : 'Add highlight note';
          noteButton.setAttribute('aria-label', noteButton.title);
        }}
        if (deleteButton) {{
          deleteButton.title = 'Delete highlight';
          deleteButton.setAttribute('aria-label', 'Delete highlight');
        }}
        positionHighlightActionMenu(target, menu);
      }}
      function updateHighlightNodeNote(target, note) {{
        if (!target) return;
        const trimmed = String(note || '').trim();
        target.dataset.note = String(note || '');
        target.dataset.notePresent = trimmed ? '1' : '0';
        target.title = trimmed || 'Highlight actions';
      }}
      function openHighlightActionMenu(target) {{
        if (!target) return;
        let menu = document.getElementById('incremento-epub-highlight-actions');
        if (!menu) {{
          menu = document.createElement('div');
          menu.id = 'incremento-epub-highlight-actions';
          const noteButton = document.createElement('button');
          noteButton.type = 'button';
          noteButton.id = 'incremento-epub-highlight-note-btn';
          noteButton.innerHTML = iconSvg('note');
          noteButton.addEventListener('click', function(event) {{
            event.preventDefault();
            event.stopPropagation();
            const currentTarget = window._incrementoEpubHighlightActionTarget;
            if (!currentTarget) return;
            send('incremento_epub_hl_note:' + JSON.stringify({{
              cardId: STATE.cardId,
              id: String(currentTarget.dataset.id || ''),
            }}));
            removeHighlightActionMenu();
          }});
          const deleteButton = document.createElement('button');
          deleteButton.type = 'button';
          deleteButton.id = 'incremento-epub-highlight-delete-btn';
          deleteButton.innerHTML = iconSvg('delete');
          deleteButton.addEventListener('click', function(event) {{
            event.preventDefault();
            event.stopPropagation();
            const currentTarget = window._incrementoEpubHighlightActionTarget;
            if (!currentTarget) return;
            const id = String(currentTarget.dataset.id || '');
            unwrapHighlight(currentTarget);
            removeHighlightActionMenu();
            send('incremento_epub_hl_del:' + JSON.stringify({{ cardId: STATE.cardId, id }}));
          }});
          menu.appendChild(noteButton);
          menu.appendChild(deleteButton);
          document.body.appendChild(menu);
        }}
        window._incrementoEpubHighlightActionTarget = target;
        syncHighlightActionMenu(target);
      }}
      window.incrementoUpdateEpubHighlightNote = function(id, note) {{
        const selector = 'span.incremento-epub-highlight[data-id="' + String(id || '').replace(/"/g, '\\"') + '"]';
        const target = document.querySelector(selector);
        if (!target) return;
        updateHighlightNodeNote(target, note);
        if (window._incrementoEpubHighlightActionTarget === target) {{
          syncHighlightActionMenu(target);
        }}
      }};
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
        updateHighlightNodeNote(wrapper, hl.note || '');
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
      function rangeRect(range) {{
        if (!range) return null;
        const rects = Array.from(range.getClientRects()).filter(function(rect) {{
          return rect && rect.width >= 0 && rect.height > 0;
        }});
        return rects.length ? rects[rects.length - 1] : null;
      }}
      function rectForOffset(offset) {{
        const point = pointFromOffset(offset);
        if (!point || !point.node) return null;
        const len = point.node.nodeValue.length;
        const startOffset = Math.max(0, Math.min(point.offset, len));
        const endOffset = Math.max(startOffset, Math.min(startOffset + 1, len));
        const range = document.createRange();
        range.setStart(point.node, startOffset);
        range.setEnd(point.node, endOffset);
        let rect = rangeRect(range);
        if ((!rect || rect.height <= 0) && startOffset > 0) {{
          range.setStart(point.node, startOffset - 1);
          range.setEnd(point.node, startOffset);
          rect = rangeRect(range);
        }}
        return rect;
      }}
      function currentCaretRange() {{
        const x = Math.max(24, Math.floor(window.innerWidth * 0.5));
        const y = Math.max(24, Math.floor(window.innerHeight * 0.48));
        if (document.caretRangeFromPoint) {{
          return document.caretRangeFromPoint(x, y);
        }}
        if (document.caretPositionFromPoint) {{
          const pos = document.caretPositionFromPoint(x, y);
          if (pos && pos.offsetNode) {{
            const range = document.createRange();
            range.setStart(pos.offsetNode, pos.offset);
            range.collapse(true);
            return range;
          }}
        }}
        return null;
      }}
      function bestVisibleTextAnchor() {{
        const nodes = textNodes();
        if (!nodes.length) return null;
        const viewportMid = window.innerHeight / 2;
        let best = null;
        let bestDistance = Infinity;
        for (const node of nodes) {{
          const range = document.createRange();
          range.selectNodeContents(node);
          const rects = Array.from(range.getClientRects()).filter(function(rect) {{
            return rect && rect.width > 0 && rect.height > 0 && rect.bottom >= 0 && rect.top <= window.innerHeight;
          }});
          for (const rect of rects) {{
            const distance = Math.abs((rect.top + (rect.height / 2)) - viewportMid);
            if (distance < bestDistance) {{
              best = {{ node, rect }};
              bestDistance = distance;
            }}
          }}
        }}
        if (!best) return null;
        return {{
          sectionIndex: STATE.sectionIndex,
          offset: offsetFromPoint(best.node, best.node.nodeValue.length),
          text: normText(best.node.nodeValue).slice(0, 240),
        }};
      }}
      function buildReadAnchor() {{
        const sel = window.getSelection ? window.getSelection() : null;
        if (sel && !sel.isCollapsed && sel.rangeCount) {{
          const meta = selectionMeta();
          if (meta) {{
            return {{
              sectionIndex: STATE.sectionIndex,
              offset: Math.max(0, Number(meta.endOffset) || 0),
              text: meta.text.slice(0, 240),
            }};
          }}
        }}
        const caret = currentCaretRange();
        if (caret && caret.startContainer) {{
          const offset = offsetFromPoint(caret.startContainer, caret.startOffset);
          if (Number.isFinite(offset) && offset >= 0) {{
            return {{
              sectionIndex: STATE.sectionIndex,
              offset,
              text: normText(caret.startContainer.nodeValue || '').slice(0, 240),
            }};
          }}
        }}
        return bestVisibleTextAnchor();
      }}
      function removeReadMarker() {{
        const old = document.getElementById('incremento-epub-read-marker');
        if (old) old.remove();
      }}
      function renderReadMarker() {{
        removeReadMarker();
        const anchor = STATE.readAnchor;
        if (!anchor || Number(anchor.sectionIndex) !== Number(STATE.sectionIndex)) return;
        const rect = rectForOffset(anchor.offset);
        if (!rect) return;
        const marker = document.createElement('div');
        marker.id = 'incremento-epub-read-marker';
        marker.title = anchor.text ? ('You stopped at: ' + anchor.text) : 'You marked this as your current stopping point';
        const arrow = document.createElement('span');
        arrow.className = 'incremento-epub-read-marker-arrow';
        arrow.textContent = '↦';
        const label = document.createElement('span');
        label.textContent = 'Read Up Until Here';
        marker.appendChild(arrow);
        marker.appendChild(label);
        document.body.appendChild(marker);
        const left = Math.max(12, rect.left + window.scrollX - 178);
        const top = Math.max(8, rect.top + window.scrollY + (rect.height / 2) - 18);
        marker.style.left = left.toFixed(0) + 'px';
        marker.style.top = top.toFixed(0) + 'px';
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
      window.incrementoSetAutoHighlightOnExtract = function(value) {{
        STATE.autoHighlightOnExtract = !!value;
      }};
      window.incrementoSetEpubReadAnchor = function(anchor) {{
        STATE.readAnchor = anchor || null;
        renderReadMarker();
      }};
      window.incrementoToggleEpubReadMarker = function() {{
        const anchor = buildReadAnchor();
        if (!anchor) return false;
        STATE.readAnchor = anchor;
        renderReadMarker();
        send('incremento_epub_mark_read:' + JSON.stringify({{
          cardId: STATE.cardId,
          sectionIndex: STATE.sectionIndex,
          anchor,
        }}));
        return true;
      }};
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
      renderReadMarker();
      document.removeEventListener('selectionchange', window._incrementoEpubSelectionListener, true);
      window._incrementoEpubSelectionListener = reportSelection;
      document.addEventListener('selectionchange', window._incrementoEpubSelectionListener, true);

      window.removeEventListener('resize', window._incrementoEpubResizeListener, true);
      window._incrementoEpubResizeListener = function() {{
        setTimeout(renderReadMarker, 40);
      }};
      window.addEventListener('resize', window._incrementoEpubResizeListener, true);

      document.removeEventListener('keydown', window._incrementoEpubKeyListener, true);
      window._incrementoEpubKeyListener = function(event) {{
        const key = String(event.key || '');
        if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && /^[1-4]$/.test(key)) {{
          const meta = selectionMeta();
          if (!meta) return;
          event.preventDefault();
          if (STATE.autoHighlightOnExtract) {{
            window.incrementoAddEpubHighlight();
          }}
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
        const actionMenu = document.getElementById('incremento-epub-highlight-actions');
        if (actionMenu && actionMenu.contains(event.target)) {{
          return;
        }}
        const target = event.target && event.target.closest
          ? event.target.closest('span.incremento-epub-highlight')
          : null;
        if (!target) {{
          removeHighlightActionMenu();
          return;
        }}
        event.preventDefault();
        event.stopPropagation();
        if (window._incrementoEpubHighlightActionTarget === target) {{
          removeHighlightActionMenu();
          return;
        }}
        openHighlightActionMenu(target);
      }};
      document.addEventListener('click', window._incrementoEpubClickListener, true);

      if (window._incrementoEpubScrollTimer) {{
        clearTimeout(window._incrementoEpubScrollTimer);
      }}
      document.removeEventListener('scroll', window._incrementoEpubScrollListener, true);
      window._incrementoEpubScrollListener = function() {{
        clearTimeout(window._incrementoEpubScrollTimer);
        if (window._incrementoEpubHighlightActionTarget) {{
          syncHighlightActionMenu(window._incrementoEpubHighlightActionTarget);
        }}
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
        renderReadMarker();
        reportProgress();
      }}, 60);
    }})();
    """


def _standard_icon(pixmap: QStyle.StandardPixmap):
    try:
        return mw.style().standardIcon(pixmap)
    except Exception:
        return None


def _make_epub_button(
    dock,
    text: str,
    tooltip_text: str,
    *,
    icon=None,
    checkable: bool = False,
    icon_only: bool = False,
    accent: str = "",
) -> QToolButton:
    btn = QToolButton(dock)
    btn.setText(text)
    btn.setToolTip(tooltip_text)
    btn.setAutoRaise(False)
    btn.setCheckable(checkable)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolButtonStyle(
        Qt.ToolButtonStyle.ToolButtonIconOnly if icon_only else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    )
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    if icon is not None:
        btn.setIcon(icon)
    base_style = (
        "QToolButton {"
        " padding: 4px 8px;"
        " border-radius: 7px;"
        " border: 1px solid rgba(255,255,255,0.12);"
        " background: rgba(255,255,255,0.04);"
        " color: #d9dee7;"
        " }"
        "QToolButton:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.22); }"
        "QToolButton:pressed { background: rgba(255,255,255,0.12); }"
        "QToolButton:disabled { color: #717885; background: rgba(255,255,255,0.02); }"
    )
    if checkable:
        base_style += (
            "QToolButton:checked {"
            " background: rgba(74,144,217,0.24);"
            " border-color: rgba(74,144,217,0.65);"
            " color: #eef5ff;"
            " }"
        )
    if accent:
        base_style += accent
    btn.setStyleSheet(base_style)
    return btn


def _make_epub_chip(parent, text: str) -> QLabel:
    label = QLabel(text, parent)
    label.setStyleSheet(
        "QLabel {"
        " color: #9ca6b4;"
        " background: rgba(255,255,255,0.04);"
        " border: 1px solid rgba(255,255,255,0.10);"
        " border-radius: 9px;"
        " padding: 2px 8px;"
        " font-size: 11px;"
        " }"
    )
    return label


def _make_epub_toggle(parent, text: str, *, checked: bool = False) -> QCheckBox:
    toggle = QCheckBox(text, parent)
    toggle.setChecked(bool(checked))
    toggle.setCursor(Qt.CursorShape.PointingHandCursor)
    toggle.setStyleSheet(
        "QCheckBox {"
        " color: #d9dee7;"
        " spacing: 6px;"
        " padding: 2px 0;"
        " }"
        "QCheckBox::indicator {"
        " width: 14px;"
        " height: 14px;"
        " border-radius: 4px;"
        " border: 1px solid rgba(255,255,255,0.18);"
        " background: rgba(255,255,255,0.04);"
        " }"
        "QCheckBox::indicator:checked {"
        " border-color: rgba(74,144,217,0.75);"
        " background: rgba(74,144,217,0.30);"
        " }"
    )
    return toggle


def _make_epub_group(parent, title: str, *widgets: QWidget) -> QWidget:
    frame = QFrame(parent)
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    frame.setStyleSheet(
        "QFrame {"
        " background: rgba(255,255,255,0.03);"
        " border: 1px solid rgba(255,255,255,0.08);"
        " border-radius: 10px;"
        " }"
    )
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 6, 8, 6)
    row.setSpacing(5)

    tag = QLabel(title, frame)
    tag.setStyleSheet("color: #8a93a1; font-size: 10px; font-weight: 600; letter-spacing: 0.04em;")
    row.addWidget(tag)
    for widget in widgets:
        row.addWidget(widget)
    return frame


def _build_epub_dock() -> None:
    global _epub_dock, _epub_shortcuts_registered, _epub_key_filter

    dock = QDockWidget("EPUB", mw)
    dock.setObjectName("incremento_epub_dock")
    dock.setMinimumWidth(300)

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

    dock._prev_btn = _make_epub_button(
        dock,
        "",
        "Previous page or previous section",
        icon=_standard_icon(QStyle.StandardPixmap.SP_ArrowBack),
        icon_only=True,
    )
    dock._next_btn = _make_epub_button(
        dock,
        "",
        "Next page or next section",
        icon=_standard_icon(QStyle.StandardPixmap.SP_ArrowForward),
        icon_only=True,
    )
    dock._title_lbl = _ElidedLabel("EPUB", dock)
    dock._title_lbl.setStyleSheet("font-weight: 600; color: #edf2f7;")
    dock._cards_chip = _make_epub_chip(dock, "Cards 0")
    dock._highlights_chip = _make_epub_chip(dock, "Highlights 0")
    dock._highlight_extract_cb = _make_epub_toggle(
        dock,
        "Highlight when extracting",
        checked=configured_highlight_when_extracting(),
    )

    dock._add_card_btn = _make_epub_button(
        dock,
        "Add Card",
        "Add a card from the current selection",
        icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
    )
    dock._browser_btn = _make_epub_button(
        dock,
        "Browser",
        "Open this EPUB note in the browser",
        icon=_standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
    )
    dock._all_cards_btn = _make_epub_button(
        dock,
        "Open All",
        "Open all cards created from this EPUB",
        icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogListView),
    )
    dock._due_review_btn = _make_epub_button(
        dock,
        "Review Due",
        "Review due cards from this EPUB",
        icon=_standard_icon(QStyle.StandardPixmap.SP_MediaPlay),
    )
    dock._limit_btn = _make_epub_button(
        dock,
        "Reading Limit",
        "Adjust this EPUB's daily reading limit",
        icon=_standard_icon(QStyle.StandardPixmap.SP_MessageBoxWarning),
    )
    dock._text_smaller_btn = _make_epub_button(
        dock,
        "A-",
        "Decrease text size",
        icon=_standard_icon(QStyle.StandardPixmap.SP_ArrowDown),
    )
    dock._text_larger_btn = _make_epub_button(
        dock,
        "A+",
        "Increase text size",
        icon=_standard_icon(QStyle.StandardPixmap.SP_ArrowUp),
    )
    dock._highlight_btn = _make_epub_button(
        dock,
        "Highlight",
        "Highlight the current selection (Alt+H)",
        icon=_standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),
    )
    dock._snapshot_btn = _make_epub_button(
        dock,
        "Snapshot",
        "Capture the current selection as an image (Alt+S)",
        icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogContentsView),
    )
    dock._cover_btn = _make_epub_button(
        dock,
        "Cover",
        "Regenerate this EPUB card's cover image",
        icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
    )
    dock._bookmark_add_btn = _make_epub_button(
        dock,
        "Bookmark",
        "Add a bookmark for this reading position",
        icon=_standard_icon(QStyle.StandardPixmap.SP_DialogYesButton),
    )
    dock._read_marker_btn = _make_epub_button(
        dock,
        "↦ Marker",
        "Place or remove the exact READ UP UNTIL HERE marker",
        checkable=True,
        accent=(
            "QToolButton:checked { background: rgba(14,165,233,0.24);"
            " border-color: rgba(14,165,233,0.72); color: #ecfeff; }"
        ),
    )
    dock._bookmarks_btn = _make_epub_button(
        dock,
        "Bookmarks",
        "Show or hide EPUB bookmarks",
        icon=_standard_icon(QStyle.StandardPixmap.SP_DirOpenIcon),
        checkable=True,
    )
    dock._sources_btn = _make_epub_button(
        dock,
        "Details",
        "Show or hide cards and highlights for this section",
        icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        checkable=True,
    )
    dock._finished_btn = _make_epub_button(
        dock,
        "Finished Reading",
        "Mark this EPUB as finished or unfinished",
        icon=_standard_icon(QStyle.StandardPixmap.SP_DialogApplyButton),
        checkable=True,
        accent=(
            "QToolButton { border-color: rgba(178,79,79,0.35); background: rgba(140,48,48,0.10); }"
            "QToolButton:hover { background: rgba(140,48,48,0.16); border-color: rgba(178,79,79,0.55); }"
            "QToolButton:checked { background: rgba(77,156,92,0.22); border-color: rgba(77,156,92,0.60); }"
        ),
    )

    header = QWidget(dock)
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(5)

    nav_row = QHBoxLayout()
    nav_row.setContentsMargins(0, 0, 0, 0)
    nav_row.setSpacing(6)
    nav_row.addWidget(dock._prev_btn)
    nav_row.addWidget(dock._next_btn)
    nav_row.addWidget(dock._title_lbl, 1)
    header_layout.addLayout(nav_row)

    status_row = QHBoxLayout()
    status_row.setContentsMargins(0, 0, 0, 0)
    status_row.setSpacing(6)
    status_row.addWidget(dock._cards_chip)
    status_row.addWidget(dock._highlights_chip)
    status_row.addStretch(1)
    header_layout.addLayout(status_row)
    layout.addWidget(header)

    groups_host = QWidget(dock)
    groups_flow = _FlowLayout(groups_host, margin=0, h_spacing=6, v_spacing=6)
    groups_host.setLayout(groups_flow)
    groups_flow.addWidget(
        _make_epub_group(
            groups_host,
            "Reader",
            dock._text_smaller_btn,
            dock._text_larger_btn,
            dock._highlight_extract_cb,
        )
    )
    groups_flow.addWidget(
        _make_epub_group(
            groups_host,
            "Capture",
            dock._highlight_btn,
            dock._snapshot_btn,
            dock._cover_btn,
            dock._read_marker_btn,
            dock._bookmark_add_btn,
            dock._bookmarks_btn,
            dock._sources_btn,
        )
    )
    groups_flow.addWidget(
        _make_epub_group(
            groups_host,
            "Review",
            dock._due_review_btn,
            dock._limit_btn,
        )
    )
    groups_flow.addWidget(
        _make_epub_group(
            groups_host,
            "Cards",
            dock._add_card_btn,
            dock._browser_btn,
            dock._all_cards_btn,
        )
    )
    groups_flow.addWidget(
        _make_epub_group(
            groups_host,
            "Status",
            dock._finished_btn,
        )
    )
    layout.addWidget(groups_host)

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
    dock._sources.setVisible(False)
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
    qconnect(dock._cover_btn.clicked, _regenerate_epub_cover)
    qconnect(dock._read_marker_btn.clicked, _request_read_marker)
    qconnect(dock._bookmark_add_btn.clicked, _add_current_epub_bookmark)
    qconnect(dock._bookmarks_btn.clicked, _toggle_epub_bookmarks_panel)
    qconnect(dock._sources_btn.clicked, _toggle_epub_sources_panel)
    qconnect(dock._finished_btn.clicked, _toggle_finished)
    qconnect(dock._highlight_extract_cb.toggled, _on_extract_highlight_toggle_changed)
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
    _epub_dock._bookmarks_btn.setToolTip(
        f"Show or hide EPUB bookmarks ({len(bookmarks)} saved)"
    )
    _epub_dock._bookmarks_btn.blockSignals(True)
    _epub_dock._bookmarks_btn.setChecked(bool(_epub_dock._bookmarks_panel.isVisible()))
    _epub_dock._bookmarks_btn.blockSignals(False)
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


def _regenerate_epub_cover() -> None:
    if _current_epub_card_id is None:
        showInfo("Could not determine which EPUB card needs a cover refresh.")
        return
    try:
        cover_filename = regenerate_epub_card_cover(_ADDON_DIR, mw.col, int(_current_epub_card_id))
    except FileNotFoundError as exc:
        showInfo(f"Could not regenerate this EPUB cover.\n\n{exc}")
        return
    except Exception as exc:
        showInfo(f"Could not regenerate this EPUB cover.\n\n{exc}")
        return

    try:
        mw.col.reset()
    except Exception:
        pass
    reviewer = getattr(mw, "reviewer", None)
    current_card = getattr(reviewer, "card", None) if reviewer is not None else None
    try:
        current_card_id = int(getattr(current_card, "id", 0) or 0)
    except Exception:
        current_card_id = 0
    if reviewer is not None and current_card_id == int(_current_epub_card_id):
        try:
            reviewer.card.load()
        except Exception:
            pass
        try:
            reviewer._showQuestion()
        except Exception:
            pass
    if cover_filename:
        tooltip("EPUB cover regenerated from book metadata.")
    else:
        tooltip("EPUB cover cleared because the book has no cover image.")


def _read_marker_on_current_section() -> bool:
    if not isinstance(_current_epub_read_anchor, dict):
        return False
    try:
        return int(_current_epub_read_anchor.get("sectionIndex", -1)) == int(_current_epub_section_index)
    except Exception:
        return False


def _push_epub_read_anchor() -> None:
    if _epub_dock is None:
        return
    _epub_dock._view.page().runJavaScript(
        f"window.incrementoSetEpubReadAnchor && window.incrementoSetEpubReadAnchor({json.dumps(_current_epub_read_anchor)});"
    )


def _set_epub_read_marker(card_id: int, section_index: int, anchor) -> None:
    global _current_epub_read_anchor
    if int(card_id or 0) <= 0 or _current_epub_card_id is None or int(card_id) != int(_current_epub_card_id):
        return
    if anchor is not None and not isinstance(anchor, dict):
        anchor = None
    try:
        set_read_section_index(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            int(section_index),
            anchor,
        )
        _current_epub_read_anchor = get_read_anchor(_ADDON_DIR, _active_profile(), int(card_id))
    except Exception as exc:
        showInfo(f"Could not save EPUB read marker:\n{exc}")
        return
    _push_epub_read_anchor()
    _update_title_and_buttons()
    tooltip("EPUB read marker updated." if _current_epub_read_anchor else "EPUB read marker cleared.")


def _request_read_marker() -> None:
    if _epub_dock is None or _current_epub_card_id is None:
        return
    if _read_marker_on_current_section():
        _set_epub_read_marker(int(_current_epub_card_id), int(_current_epub_section_index), None)
        return
    _epub_dock._view.page().runJavaScript(
        "window.incrementoToggleEpubReadMarker && window.incrementoToggleEpubReadMarker();"
    )


def _toggle_epub_bookmarks_panel() -> None:
    if _epub_dock is None:
        return
    _refresh_epub_bookmarks_panel()
    visible = not _epub_dock._bookmarks_panel.isVisible()
    _epub_dock._bookmarks_panel.setVisible(visible)
    _epub_dock._bookmarks_btn.blockSignals(True)
    _epub_dock._bookmarks_btn.setChecked(visible)
    _epub_dock._bookmarks_btn.blockSignals(False)


def _toggle_epub_sources_panel() -> None:
    if _epub_dock is None:
        return
    visible = not _epub_dock._sources.isVisible()
    _epub_dock._sources.setVisible(visible)
    _epub_dock._sources_btn.blockSignals(True)
    _epub_dock._sources_btn.setChecked(visible)
    _epub_dock._sources_btn.blockSignals(False)


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
    escaped_id = json.dumps(str(updated.get("id") or ""))
    escaped_note = json.dumps(str(updated.get("note") or ""))
    try:
        if _epub_dock is not None:
            _epub_dock._view.page().runJavaScript(
                "window.incrementoUpdateEpubHighlightNote && "
                f"window.incrementoUpdateEpubHighlightNote({escaped_id}, {escaped_note});"
            )
    except Exception:
        pass
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
    title_text = "EPUB"
    if count:
        idx = max(0, min(_current_epub_section_index, count - 1))
        section = sections[idx]
        if _current_epub_total_pages > 0:
            title_text = (
                f"Page {_current_epub_page_index + 1} / {_current_epub_total_pages} — "
                f"{section.get('title') or f'Section {idx + 1}'}"
            )
        else:
            title_text = (
                f"{section.get('title') or f'Section {idx + 1}'} ({idx + 1}/{count})"
            )
        _epub_dock._prev_btn.setEnabled(idx > 0 or _current_epub_scroll_ratio > 0.001)
        _epub_dock._next_btn.setEnabled(idx + 1 < count or _current_epub_scroll_ratio < 0.999)
    else:
        _epub_dock._prev_btn.setEnabled(False)
        _epub_dock._next_btn.setEnabled(False)
    _epub_dock._title_lbl.set_full_text(title_text)
    has_card = _current_epub_card_id is not None
    _epub_dock._browser_btn.setEnabled(has_card)
    _epub_dock._due_review_btn.setEnabled(has_card)
    _epub_dock._limit_btn.setEnabled(has_card)
    _epub_dock._text_smaller_btn.setEnabled(has_card)
    _epub_dock._text_larger_btn.setEnabled(has_card)
    _epub_dock._highlight_btn.setEnabled(has_card)
    _epub_dock._add_card_btn.setEnabled(has_card)
    _epub_dock._all_cards_btn.setEnabled(has_card)
    _epub_dock._snapshot_btn.setEnabled(has_card)
    _epub_dock._cover_btn.setEnabled(has_card)
    _epub_dock._read_marker_btn.setEnabled(has_card)
    _epub_dock._bookmark_add_btn.setEnabled(has_card)
    _epub_dock._bookmarks_btn.setEnabled(has_card)
    _epub_dock._sources_btn.setEnabled(has_card)
    _epub_dock._finished_btn.blockSignals(True)
    _epub_dock._finished_btn.setChecked(bool(_current_epub_finished))
    _epub_dock._finished_btn.blockSignals(False)
    _epub_dock._read_marker_btn.blockSignals(True)
    _epub_dock._read_marker_btn.setChecked(bool(_read_marker_on_current_section()))
    _epub_dock._read_marker_btn.blockSignals(False)
    _epub_dock._bookmarks_btn.blockSignals(True)
    _epub_dock._bookmarks_btn.setChecked(bool(_epub_dock._bookmarks_panel.isVisible()))
    _epub_dock._bookmarks_btn.blockSignals(False)
    _epub_dock._sources_btn.blockSignals(True)
    _epub_dock._sources_btn.setChecked(bool(_epub_dock._sources.isVisible()))
    _epub_dock._sources_btn.blockSignals(False)
    _refresh_epub_bookmarks_panel()


def _update_sources_panel() -> None:
    if _epub_dock is None or _current_epub_card_id is None:
        return
    cards = get_epub_card_sources(_ADDON_DIR, _active_profile(), _current_epub_card_id, _current_epub_section_index)
    counts = get_epub_section_card_counts(_ADDON_DIR, _active_profile(), _current_epub_card_id)
    count = int(counts.get(_current_epub_section_index, 0) or 0)
    highlights = _current_section_highlights()
    _epub_dock._cards_chip.setText(f"Cards {count}")
    _epub_dock._cards_chip.setToolTip(f"{count} cards created from this section")
    _epub_dock._highlights_chip.setText(f"Highlights {len(highlights)}")
    _epub_dock._highlights_chip.setToolTip(f"{len(highlights)} highlights in this section")
    _epub_dock._sources_btn.setToolTip(
        f"Show or hide cards and highlights for this section ({count} cards, {len(highlights)} highlights)"
    )
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
        _record_timer_epub_page_read(_current_epub_card_id, _current_epub_page_index)
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
        read_anchor=_current_epub_read_anchor,
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
    global _current_epub_scroll_ratio, _current_epub_finished, _current_epub_font_scale, _current_epub_read_anchor, _pending_focus_offset, _pending_restore_ratio
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
    _record_timer_epub_page_read(_current_epub_card_id, _current_epub_page_index)
    _pending_focus_offset = int(focus_offset)
    _pending_restore_ratio = _current_epub_scroll_ratio
    _pending_search_query = str(search_query or "")
    _pending_explicit_navigation = True
    _last_selection_meta = {}
    _, _, _current_epub_finished = get_epub_progress(_ADDON_DIR, _active_profile(), _current_epub_card_id)
    _current_epub_font_scale = get_epub_font_scale(_ADDON_DIR, _active_profile(), _current_epub_card_id)
    _current_epub_read_anchor = get_read_anchor(_ADDON_DIR, _active_profile(), _current_epub_card_id)

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


def _on_extract_highlight_toggle_changed(checked: bool) -> None:
    _set_highlight_when_extracting(bool(checked))
    if _epub_dock is None:
        return
    _epub_dock._view.page().runJavaScript(
        f"window.incrementoSetAutoHighlightOnExtract && window.incrementoSetAutoHighlightOnExtract({json.dumps(bool(checked))});"
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
    source = _add_card_source_for_new_note()
    if source and source != "epub":
        return
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
