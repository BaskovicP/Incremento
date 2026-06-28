"""PDF viewer dock (QWebEngineView + PDF.js / React).

All state globals, the _PdfDockPage class, and the lifecycle functions live here
so __init__.py is not the only place these reside.

Circular-import problem: the PDF dock needs _open_add_card_dock and _fill_dock_field
which live in __init__.py. These are registered after import via register_add_card_callbacks().
Until that function is called the callbacks are None — they are never called at module-load
time so there is no practical issue.
"""

import json
import os
import re
import time
from html import escape, unescape

from aqt import mw
from aqt.qt import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QShortcut,
    QKeySequence,
    QTimer,
    Qt,
    QDialog,
    QLabel,
    QPushButton,
    QPixmap,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    qconnect,
)
from aqt.utils import showInfo, tooltip
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import QEvent, QObject, QUrl

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.pdf_manager import (
        PDF_NOTE_TYPE,
        get_page,
        get_due_pdf_source_cards,
        get_pdf_daily_limit_settings,
        get_pdf_due_review_prompt_settings,
        get_pdf_daily_limit_status,
        get_pdf_limit_mode_label,
        get_zoom,
        get_scroll_ratio,
        get_read_anchor,
        get_read_page,
        pdf_storage_abspath,
        pdf_display_label_from_filename,
        regenerate_pdf_card_cover,
        repair_pdf_card_filename,
        replace_pdf_card_file,
        save_pdf_daily_limit_settings,
        save_pdf_due_review_prompt_settings,
        set_page,
        set_pdf_daily_limit_override,
        set_scroll_ratio,
        set_zoom,
        set_read_page,
    )
except ImportError:
    from pdf_manager import (
        PDF_NOTE_TYPE,
        get_page,
        get_due_pdf_source_cards,
        get_pdf_daily_limit_settings,
        get_pdf_due_review_prompt_settings,
        get_pdf_daily_limit_status,
        get_pdf_limit_mode_label,
        get_zoom,
        get_scroll_ratio,
        get_read_anchor,
        get_read_page,
        pdf_storage_abspath,
        pdf_display_label_from_filename,
        regenerate_pdf_card_cover,
        repair_pdf_card_filename,
        replace_pdf_card_file,
        save_pdf_daily_limit_settings,
        save_pdf_due_review_prompt_settings,
        set_page,
        set_pdf_daily_limit_override,
        set_scroll_ratio,
        set_zoom,
        set_read_page,
    )
try:
    from ..backend.pdf_highlights import load_highlights, add_highlight, remove_highlight, update_highlight_note
except ImportError:
    from pdf_highlights import load_highlights, add_highlight, remove_highlight, update_highlight_note
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
        add_pdf_card_source,
        delete_pdf_card_sources_for_note_ids,
        get_pdf_card_sources,
        get_pdf_document_source_note_ids,
        get_pdf_page_card_counts,
        search_pdf_text_index_for_card,
    )
except ImportError:
    from db import (  # type: ignore
        add_pdf_card_source,
        delete_pdf_card_sources_for_note_ids,
        get_pdf_card_sources,
        get_pdf_document_source_note_ids,
        get_pdf_page_card_counts,
        search_pdf_text_index_for_card,
    )
try:
    from ..backend.note_metadata import visible_field_names
except ImportError:
    from note_metadata import visible_field_names
try:
    from . import timer_widget as _timer_mod
except ImportError:
    import timer_widget as _timer_mod  # type: ignore
try:
    from ..backend.session import INCREMENTO_PDF_REVIEW_DECK, start_explicit_review
except ImportError:
    from session import INCREMENTO_PDF_REVIEW_DECK, start_explicit_review  # type: ignore

# ── Addon root ────────────────────────────────────────────────────────────────

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_ADDON_PKG = __name__.split(".")[0] if "." in __name__ else "incremento"

_DOCK_HTML = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, "web", "pdf_dock.html")
).toString()

_WORKER_URL = bytes(
    QUrl.fromLocalFile(
        os.path.join(_ADDON_DIR, "web", "pdfjs", "pdf.worker.min.js")
    ).toEncoded()
).decode()

# ── Module state ──────────────────────────────────────────────────────────────

_pdf_dock = None
_shortcuts_registered = False
_current_pdf_card_id = None
_current_pdf_filename = None
_current_pdf_search_query = ""
_current_pdf_search_hits: list[dict] = []
_current_pdf_search_hit_index = -1
_pdf_via_link = False  # True when dock was opened via a cross-reference link
_pdf_preserve_history = False
_suppress_due_review_prompt_card_id: int | None = None
_suppress_due_review_prompt_until = 0.0
_PDF_ADD_PROMPT_SUPPRESSION_SECONDS = 5.0
_PDF_REF_EXCERPT_MAX_CHARS = 320


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


def configured_scroll_to_top_on_page_change(config: dict | None = None) -> bool:
    cfg = _config(config)
    return bool(cfg.get("pdf_scroll_to_top_on_page_change", True))


def current_pdf_card_id() -> int | None:
    try:
        card_id = int(_current_pdf_card_id) if _current_pdf_card_id is not None else 0
        return card_id if card_id > 0 else None
    except Exception:
        return None


def _clear_current_pdf_context() -> int | None:
    global _current_pdf_card_id, _current_pdf_filename
    global _current_pdf_search_query, _current_pdf_search_hits, _current_pdf_search_hit_index
    global _pdf_via_link, _pdf_preserve_history
    previous_card_id = current_pdf_card_id()
    _current_pdf_card_id = None
    _current_pdf_filename = None
    _current_pdf_search_query = ""
    _current_pdf_search_hits = []
    _current_pdf_search_hit_index = -1
    _pdf_via_link = False
    _pdf_preserve_history = False
    return previous_card_id


def _stop_current_pdf_view() -> None:
    previous_card_id = _clear_current_pdf_context()
    if previous_card_id is None or not _cb_pdf_view_stopped:
        return
    try:
        _cb_pdf_view_stopped(previous_card_id)
    except Exception:
        pass


def _hide_pdf_dock_for_inactive_context() -> None:
    global _pdf_dock
    _stop_current_pdf_view()
    if _pdf_dock is None:
        return
    try:
        _pdf_dock.hide()
    except RuntimeError:
        _pdf_dock = None
_pdf_shortcuts = []
_pdf_key_filter = None


def _suppress_next_due_review_prompt_for_pdf_add(card_id: int) -> None:
    global _suppress_due_review_prompt_card_id, _suppress_due_review_prompt_until
    try:
        normalized_card_id = int(card_id)
    except Exception:
        normalized_card_id = 0
    if normalized_card_id <= 0:
        return
    _suppress_due_review_prompt_card_id = normalized_card_id
    _suppress_due_review_prompt_until = time.monotonic() + _PDF_ADD_PROMPT_SUPPRESSION_SECONDS


def _consume_due_review_prompt_suppression(card_id: int) -> bool:
    global _suppress_due_review_prompt_card_id, _suppress_due_review_prompt_until
    try:
        normalized_card_id = int(card_id)
    except Exception:
        normalized_card_id = 0
    now = time.monotonic()
    if (
        normalized_card_id <= 0
        or _suppress_due_review_prompt_card_id != normalized_card_id
        or now > float(_suppress_due_review_prompt_until or 0.0)
    ):
        if now > float(_suppress_due_review_prompt_until or 0.0):
            _suppress_due_review_prompt_card_id = None
            _suppress_due_review_prompt_until = 0.0
        return False
    _suppress_due_review_prompt_card_id = None
    _suppress_due_review_prompt_until = 0.0
    return True


def _browse_note_in_browser(note_id: int) -> None:
    _browse_note_ids_in_browser([note_id])


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


def _open_all_pdf_cards_in_browser(card_id: int) -> None:
    note_ids = _live_pdf_document_source_note_ids(int(card_id))
    _browse_note_ids_in_browser(
        note_ids,
        empty_message="No cards created from this PDF yet.",
    )


def _note_exists(note_id: int) -> bool:
    try:
        if int(note_id or 0) <= 0 or not getattr(mw, "col", None):
            return False
        note = mw.col.get_note(int(note_id))
    except Exception:
        return False
    return note is not None


def _reconcile_pdf_page_sources(
    pdf_card_id: int,
    page: int | None = None,
) -> tuple[list[dict], dict[int, int]]:
    if int(pdf_card_id or 0) <= 0:
        return [], {}

    if page is None:
        page = get_page(_ADDON_DIR, _active_profile(), int(pdf_card_id))

    cards = get_pdf_card_sources(_ADDON_DIR, _active_profile(), int(pdf_card_id), int(page))
    stale_note_ids = {
        int(row.get("note_id", 0) or 0)
        for row in cards
        if int(row.get("note_id", 0) or 0) > 0 and not _note_exists(int(row.get("note_id", 0) or 0))
    }
    if stale_note_ids:
        delete_pdf_card_sources_for_note_ids(
            _ADDON_DIR,
            _active_profile(),
            int(pdf_card_id),
            stale_note_ids,
        )
        cards = get_pdf_card_sources(_ADDON_DIR, _active_profile(), int(pdf_card_id), int(page))

    live_cards = [
        row
        for row in cards
        if int(row.get("note_id", 0) or 0) > 0 and _note_exists(int(row.get("note_id", 0) or 0))
    ]
    counts = get_pdf_page_card_counts(_ADDON_DIR, _active_profile(), int(pdf_card_id))
    return live_cards, counts


def _live_pdf_document_source_note_ids(pdf_card_id: int) -> list[int]:
    note_ids = get_pdf_document_source_note_ids(_ADDON_DIR, _active_profile(), int(pdf_card_id))
    stale_note_ids = [note_id for note_id in note_ids if not _note_exists(note_id)]
    if stale_note_ids:
        delete_pdf_card_sources_for_note_ids(
            _ADDON_DIR,
            _active_profile(),
            int(pdf_card_id),
            stale_note_ids,
        )
        note_ids = get_pdf_document_source_note_ids(_ADDON_DIR, _active_profile(), int(pdf_card_id))
    return [note_id for note_id in note_ids if _note_exists(note_id)]


def _load_pdf_page_note_preview(note_id: int) -> dict | None:
    try:
        nid = int(note_id)
    except Exception:
        return None
    if nid <= 0 or not getattr(mw, "col", None):
        return None

    try:
        note = mw.col.get_note(nid)
    except Exception:
        return None
    if note is None:
        return None

    try:
        model = note.note_type() or {}
        all_field_names = [
            str((field or {}).get("name") or "").strip()
            for field in list(model.get("flds") or [])
        ]
    except Exception:
        all_field_names = []

    field_names = visible_field_names(all_field_names)
    fields: list[dict[str, str]] = []
    for field_name in field_names:
        try:
            raw_value = str(note[field_name] or "")
        except Exception:
            raw_value = ""
        value = raw_value.strip()
        if not value:
            continue
        fields.append({"name": field_name, "value": value})

    title = ""
    if fields:
        title = fields[0]["value"].splitlines()[0].strip()
    if not title:
        title = f"Note {nid}"

    tags = []
    try:
        tags = [str(tag).strip() for tag in list(getattr(note, "tags", []) or []) if str(tag).strip()]
    except Exception:
        tags = []

    card_count = 0
    try:
        card_count = len(list(note.cards() or []))
    except Exception:
        card_count = 0

    return {
        "note_id": nid,
        "title": title,
        "fields": fields,
        "tags": tags,
        "card_count": int(card_count),
    }


def _render_pdf_page_note_preview_html(payload: dict) -> str:
    title = escape(str(payload.get("title") or ""))
    note_id = int(payload.get("note_id") or 0)
    fields = list(payload.get("fields") or [])
    tags = [str(tag).strip() for tag in list(payload.get("tags") or []) if str(tag).strip()]
    card_count = int(payload.get("card_count") or 0)

    parts = [
        f"<div style='font-size:15px; font-weight:600; margin-bottom:4px;'>{title}</div>",
        (
            "<div style='color:#8892a0; font-size:12px; margin-bottom:10px;'>"
            f"Note ID {note_id}"
            + (f" · {card_count} card{'s' if card_count != 1 else ''}" if card_count > 0 else "")
            + "</div>"
        ),
    ]
    if tags:
        parts.append(
            "<div style='margin-bottom:10px;'>"
            "<span style='color:#8892a0; font-size:12px;'>Tags:</span> "
            f"{escape(', '.join(tags))}</div>"
        )

    if fields:
        for field in fields:
            field_name = escape(str(field.get("name") or ""))
            value = escape(str(field.get("value") or "")).replace("\n", "<br>")
            parts.append(
                "<div style='margin-bottom:12px;'>"
                f"<div style='font-weight:600; margin-bottom:4px;'>{field_name}</div>"
                "<div style='white-space:normal; line-height:1.45; "
                "background:rgba(255,255,255,0.04); border:1px solid rgba(140,140,140,0.25); "
                f"border-radius:6px; padding:8px 10px;'>{value}</div>"
                "</div>"
            )
    else:
        parts.append("<div style='color:#8892a0;'>This note has no visible non-empty fields.</div>")
    return "".join(parts)


def show_pdf_page_card_preview(note_id: int) -> bool:
    payload = _load_pdf_page_note_preview(note_id)
    if not payload:
        return False

    dlg = QDialog(mw)
    dlg.setWindowTitle("PDF Page Card Preview")
    dlg.resize(780, 560)
    layout = QVBoxLayout(dlg)

    browser = QTextBrowser(dlg)
    browser.setReadOnly(True)
    browser.setOpenExternalLinks(True)
    browser.setHtml(_render_pdf_page_note_preview_html(payload))
    layout.addWidget(browser, 1)

    buttons = QDialogButtonBox(parent=dlg)
    open_btn = buttons.addButton("Open in Browser", QDialogButtonBox.ButtonRole.ActionRole)
    close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
    qconnect(
        open_btn.clicked,
        lambda _checked=False, nid=int(payload["note_id"]): _browse_note_in_browser(nid),
    )
    qconnect(close_btn.clicked, dlg.accept)
    layout.addWidget(buttons)
    dlg.exec()
    return True


class _PdfReadingLimitDialog(QDialog):
    def __init__(self, parent, *, settings: dict, status: dict):
        super().__init__(parent)
        self.setWindowTitle("PDF Reading Limit")
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

        self._enabled = QCheckBox("Limit pages read per day for this PDF")
        self._enabled.setChecked(bool(settings.get("enabled")))
        form.addRow("Enabled:", self._enabled)

        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        self._limit_spin = QSpinBox(self)
        self._limit_spin.setRange(1, 5000)
        self._limit_spin.setValue(max(1, int(settings.get("daily_page_limit", 10) or 10)))
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
            return "No daily reading limit is set for this PDF."
        limit = int(status.get("daily_page_limit", 0) or 0)
        used = int(status.get("pages_used", 0) or 0)
        remaining = int(status.get("pages_remaining", 0) or 0)
        mode_label = get_pdf_limit_mode_label(status.get("enforcement_mode"))
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
            "daily_page_limit": int(self._limit_spin.value()),
            "enforcement_mode": str(self._mode.currentData() or "warning"),
        }


def _summarize_due_review_pages(due_cards: list[dict]) -> str:
    pages = sorted({int(row.get("page", 0) or 0) for row in due_cards if int(row.get("page", 0) or 0) > 0})
    if not pages:
        return "earlier pages"
    if len(pages) <= 6:
        return ", ".join(str(page) for page in pages)
    preview = ", ".join(str(page) for page in pages[:6])
    return f"{preview}, +{len(pages) - 6} more"


class _PdfDueReviewPromptDialog(QDialog):
    def __init__(self, parent, *, due_cards: list[dict], settings: dict, current_page: int):
        super().__init__(parent)
        self._review_now = False
        self.setWindowTitle("Review Due PDF Cards")
        self.setModal(True)
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        count = len(due_cards)
        earlier_pages = _summarize_due_review_pages(due_cards)
        summary = QLabel(
            f"You have {count} due card{'s' if count != 1 else ''} from this PDF on pages up to {current_page}.\n"
            f"Pages: {earlier_pages}"
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

        self._offer_on_open = QCheckBox("Offer this due-card review automatically when opening this PDF")
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
            detail = f"p.{int(row.get('page', 0) or 0)} — {title} <span style='color:#8892a0;'>({state})</span>"
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

# ── Callback injection (breaks circular import with __init__.py) ──────────────

_cb_open_add_card_dock = None  # () -> None
_cb_fill_dock_field = None  # (idx: int, text: str) -> None
_cb_get_add_card_dock = None  # () -> QDockWidget | None
_cb_pdf_view_started = None  # (card_id: int) -> None
_cb_pdf_view_stopped = None  # (card_id: int | None) -> None
_cb_open_current_document_search = None  # () -> bool


def register_add_card_callbacks(open_fn, fill_fn, get_dock_fn) -> None:
    """Called by __init__.py after its own functions are defined.

    Must be called before any PDF card is reviewed.  In practice it is called
    at module-load time of __init__.py, which is always before the reviewer
    opens.
    """
    global _cb_open_add_card_dock, _cb_fill_dock_field, _cb_get_add_card_dock
    _cb_open_add_card_dock = open_fn
    _cb_fill_dock_field = fill_fn
    _cb_get_add_card_dock = get_dock_fn


def register_pdf_view_callbacks(start_fn, stop_fn) -> None:
    global _cb_pdf_view_started, _cb_pdf_view_stopped
    _cb_pdf_view_started = start_fn
    _cb_pdf_view_stopped = stop_fn


def register_current_document_search_callback(open_fn) -> None:
    global _cb_open_current_document_search
    _cb_open_current_document_search = open_fn


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


def _current_reviewer_card_id() -> int | None:
    try:
        reviewer = getattr(mw, "reviewer", None)
        card = getattr(reviewer, "card", None) if reviewer is not None else None
        card_id = int(card.id) if card is not None else 0
        return card_id if card_id > 0 else None
    except Exception:
        return None


# ── Citation helper (called by _fill_dock_field in __init__.py) ───────────────


def _normalize_pdf_reference_excerpt(text: str | None) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:_PDF_REF_EXCERPT_MAX_CHARS].strip()


def _pdf_search_snippet(text: str, query: str, max_len: int = 180) -> str:
    plain = " ".join(str(text or "").split())
    if not plain:
        return ""
    lowered = plain.lower()
    needle = str(query or "").strip().lower()
    idx = lowered.find(needle) if needle else -1
    if idx < 0:
        tokens = [tok for tok in re.findall(r"\w+", needle) if len(tok) >= 2]
        for token in tokens:
            idx = lowered.find(token)
            if idx >= 0:
                break
    if idx < 0:
        return plain[:max_len]
    start = max(0, idx - (max_len // 3))
    end = min(len(plain), start + max_len)
    snippet = plain[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(plain):
        snippet += "..."
    return snippet


def current_card_pdf_search_hits(card_id: int, query: str, *, limit: int = 250) -> list[dict]:
    try:
        normalized_card_id = int(card_id or 0)
    except Exception:
        normalized_card_id = 0
    normalized_query = str(query or "").strip()
    if normalized_card_id <= 0 or not normalized_query:
        return []
    rows = search_pdf_text_index_for_card(
        _ADDON_DIR,
        _active_profile(),
        normalized_card_id,
        normalized_query,
        limit=limit,
    )
    return [
        {
            "page": int(page),
            "snippet": _pdf_search_snippet(text or "", normalized_query),
            "excerpt": _pdf_search_snippet(text or "", normalized_query, max_len=260),
        }
        for page, text in rows
    ]


def current_pdf_search_context() -> dict | None:
    card_id = current_pdf_card_id()
    if card_id is None or _pdf_dock is None:
        return None
    try:
        if not _pdf_dock.isVisible():
            return None
    except Exception:
        return None
    return {
        "documentKind": "pdf",
        "documentLabel": pdf_display_label_from_filename(str(_current_pdf_filename or ""), fallback="PDF"),
        "cardId": int(card_id),
        "query": str(_current_pdf_search_query or ""),
        "hits": list(_current_pdf_search_hits or []),
    }


def _sync_pdf_search_state(
    query: str,
    hits: list[dict],
    active_index: int = -1,
) -> None:
    global _current_pdf_search_query, _current_pdf_search_hits, _current_pdf_search_hit_index
    _current_pdf_search_query = str(query or "")
    _current_pdf_search_hits = list(hits or [])
    _current_pdf_search_hit_index = int(active_index) if hits else -1
    if _current_pdf_search_hit_index < -1:
        _current_pdf_search_hit_index = -1


def _emit_pdf_search_state() -> None:
    if _pdf_dock is None:
        return
    payload = {
        "query": _current_pdf_search_query,
        "hits": _current_pdf_search_hits,
        "activeIndex": _current_pdf_search_hit_index,
    }
    js = (
        "window.incrementoReceivePdfSearchState && "
        f"window.incrementoReceivePdfSearchState({json.dumps(payload)});"
    )
    try:
        _pdf_dock._view.page().runJavaScript(js)
    except Exception:
        pass


def pdf_citation(excerpt_text: str | None = None) -> str:
    """Return an HTML link 'Page N. of name' that reopens the PDF dock at that page."""
    if not _current_pdf_card_id or not _current_pdf_filename:
        return ""
    page = get_page(_ADDON_DIR, _active_profile(), _current_pdf_card_id)
    name = pdf_display_label_from_filename(_current_pdf_filename)
    payload = {
        "card_id": int(_current_pdf_card_id),
        "filename": str(_current_pdf_filename or "").strip(),
        "page": int(page),
    }
    excerpt = _normalize_pdf_reference_excerpt(excerpt_text)
    if excerpt:
        payload["excerpt"] = excerpt
    cmd = "incremento_open_pdf_ref:" + json.dumps(payload, ensure_ascii=False)
    onclick = escape(f"pycmd({json.dumps(cmd)}); return false;", quote=True)
    return (
        f"<a onclick=\"{onclick}\" "
        f'style="cursor:pointer; color:#4a90d9; text-decoration:none;">'
        f"Page {page}. of {escape(name)}</a>"
    )


_LEGACY_PDF_REF_ANCHOR_RE = re.compile(
    r"(?P<open><a\b[^>]*incremento_open_pdf_ref:[^>]*>)(?P<label>.*?)(?P<close></a>)",
    re.IGNORECASE | re.DOTALL,
)


def repair_legacy_pdf_reference_links_html(html: str) -> str:
    """Repair old malformed PDF citation anchors when existing note HTML is rendered."""
    if not html or "incremento_open_pdf_ref:" not in html or 'onclick="pycmd("' not in html:
        return html

    def _replace(match: re.Match[str]) -> str:
        open_tag = match.group("open")
        label = match.group("label")

        card_id_match = re.search(r'card_id\\?":(?:\s*=""\s*)?(?P<card_id>\d+)', open_tag)
        filename_match = re.search(r'filename\\?":(?:\s*=""\s*)?\\?"(?P<filename>[^"]+)\\?"', open_tag)
        page_match = re.search(r'page\\?":(?:\s*=""\s*)?(?P<page>\d+)', open_tag)
        if not (card_id_match and filename_match and page_match):
            return match.group(0)

        cmd = "incremento_open_pdf_ref:" + json.dumps(
            {
                "card_id": int(card_id_match.group("card_id")),
                "filename": str(filename_match.group("filename")).strip(),
                "page": int(page_match.group("page")),
            },
            ensure_ascii=False,
        )
        onclick = escape(f"pycmd({json.dumps(cmd)}); return false;", quote=True)
        return (
            f"<a onclick=\"{onclick}\" "
            f'style="cursor:pointer; color:#4a90d9; text-decoration:none;">'
            f"{label}</a>"
        )

    return _LEGACY_PDF_REF_ANCHOR_RE.sub(_replace, html)


# ── pycmd message protocol constants ─────────────────────────────────────────
# All pycmd messages from the PDF viewer JS are prefixed with _PYCMD_BRIDGE.
# Each handler constant names one message type, making typos compile-time errors.

_PYCMD_BRIDGE = "__incremento_pycmd__:"
_MSG_NAV = "incremento_pdf_nav:"
_MSG_ZOOM = "incremento_pdf_zoom:"
_MSG_SCROLL = "incremento_pdf_scroll:"
_MSG_HL_ADD = "incremento_pdf_hl_add:"
_MSG_HL_DEL = "incremento_pdf_hl_del:"
_MSG_MARK_READ = "incremento_pdf_mark_read:"
_MSG_CMD1 = "incremento_pdf_cmd1:"
_MSG_OPEN_ADD_CARD = "incremento_open_add_card"
_MSG_FILL_FIELD = "incremento_fill_field:"
_MSG_SNAPSHOT = "incremento_pdf_snapshot:"
_MSG_FINISHED = "incremento_pdf_finished:"
_MSG_OPEN_CARD = "incremento_open_card:"
_MSG_OPEN_ALL_CARDS = "incremento_open_all_pdf_cards:"
_MSG_OPEN_PAGE_CARDS = "incremento_open_page_cards:"
_MSG_SELECTION_STATE = "incremento_selection_state:"
_MSG_LIMIT_SETTINGS = "incremento_pdf_limit_settings:"
_MSG_LIMIT_OVERRIDE = "incremento_pdf_limit_override:"
_MSG_DUE_REVIEW = "incremento_pdf_due_review:"
_MSG_REPAIR_MISSING = "incremento_pdf_repair_missing:"
_MSG_REGENERATE_COVER = "incremento_pdf_regenerate_cover:"
_MSG_HL_NOTE = "incremento_pdf_hl_note:"
_MSG_BOOKMARK_ADD = "incremento_pdf_bookmark_add:"
_MSG_BOOKMARK_DELETE = "incremento_pdf_bookmark_delete:"
_MSG_BOOKMARK_LIST = "incremento_pdf_bookmark_list:"
_MSG_FIND = "incremento_pdf_find:"
_MSG_FIND_NAV = "incremento_pdf_find_nav:"
_MSG_OPEN_FIND_DIALOG = "incremento_pdf_open_find_dialog"


def _current_pdf_limit_status(card_id: int, *, current_page: int | None = None) -> dict:
    try:
        return get_pdf_daily_limit_status(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            current_page=current_page,
        )
    except Exception:
        return {"enabled": False}


def _push_pdf_limit_status(status: dict) -> None:
    if _pdf_dock is None:
        return
    try:
        _pdf_dock._view.page().runJavaScript(
            "window.incrementoReceivePdfLimitStatus && "
            f"window.incrementoReceivePdfLimitStatus({json.dumps(status)});"
        )
    except Exception:
        pass


def _pdf_storage_path(filename: str) -> str:
    return pdf_storage_abspath(filename)


def _missing_pdf_html(filename: str, expected_path: str) -> str:
    escaped_name = escape(str(filename or "").strip() or "(missing filename)")
    escaped_path = escape(str(expected_path or "").strip())
    onclick = escape(f"pycmd({json.dumps(_MSG_REPAIR_MISSING)}); return false;", quote=True)
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
html, body {{
  margin: 0;
  min-height: 100%;
  background: #181818;
  color: #e7e7e7;
  font-family: sans-serif;
}}
.wrap {{
  max-width: 720px;
  margin: 48px auto;
  padding: 0 24px;
}}
.panel {{
  background: #232323;
  border: 1px solid #474747;
  border-radius: 12px;
  padding: 20px 22px;
}}
.title {{
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 10px;
}}
.copy {{
  line-height: 1.5;
  margin-bottom: 14px;
}}
.path {{
  font-family: monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  background: #111;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 16px;
}}
button {{
  background: #3f6db3;
  color: white;
  border: 0;
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 14px;
  cursor: pointer;
}}
button:hover {{
  background: #4b7bc7;
}}
</style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <div class="title">PDF file is missing</div>
      <div class="copy">
        This PDF card still exists, but its stored PDF file could not be found.
        Choose a replacement PDF to relink this card and reopen the viewer.
      </div>
      <div class="copy"><b>Expected file:</b> {escaped_name}</div>
      <div class="path">{escaped_path}</div>
      <button onclick="{onclick}">Choose Replacement PDF</button>
    </div>
  </div>
</body>
</html>
""".strip()


def _show_missing_pdf_screen(filename: str) -> None:
    if _pdf_dock is None:
        return
    expected_path = _pdf_storage_path(filename)
    _pdf_dock._view.setHtml(_missing_pdf_html(filename, expected_path), QUrl(_DOCK_HTML))


def _repair_missing_pdf() -> None:
    card_id = current_pdf_card_id()
    filename = str(_current_pdf_filename or "").strip()
    if card_id is None or not filename:
        showInfo("Could not determine which PDF card needs repairing.")
        return
    selected_path, _ = QFileDialog.getOpenFileName(
        mw,
        "Choose Replacement PDF",
        "",
        "PDF Files (*.pdf)",
    )
    if not selected_path:
        return
    try:
        new_filename = replace_pdf_card_file(_ADDON_DIR, mw.col, int(card_id), selected_path)
        page = get_page(_ADDON_DIR, _active_profile(), int(card_id))
        zoom = get_zoom(_ADDON_DIR, _active_profile(), int(card_id))
        read_page = get_read_page(_ADDON_DIR, _active_profile(), int(card_id))
        tooltip("PDF card relinked to the replacement file.")
        show_pdf_in_dock(
            int(card_id),
            new_filename,
            page,
            zoom,
            read_page=read_page,
            preserve_history=False,
            offer_due_review_prompt=False,
        )
    except Exception as exc:
        showInfo(f"Could not relink this PDF card.\n\n{exc}")


def _regenerate_pdf_cover() -> None:
    card_id = current_pdf_card_id()
    if card_id is None:
        showInfo("Could not determine which PDF card needs a cover refresh.")
        return
    try:
        cover_filename = regenerate_pdf_card_cover(_ADDON_DIR, mw.col, int(card_id))
    except FileNotFoundError as exc:
        showInfo(f"Could not regenerate this PDF cover.\n\n{exc}")
        return
    except Exception as exc:
        showInfo(f"Could not regenerate this PDF cover.\n\n{exc}")
        return

    mw.col.reset()
    reviewer = getattr(mw, "reviewer", None)
    current_card = getattr(reviewer, "card", None) if reviewer is not None else None
    try:
        current_card_id = int(getattr(current_card, "id", 0) or 0)
    except Exception:
        current_card_id = 0
    if reviewer is not None and current_card_id == int(card_id):
        try:
            reviewer.card.load()
        except Exception:
            pass
        try:
            reviewer._showQuestion()
        except Exception:
            pass
    if cover_filename:
        tooltip("PDF cover regenerated from page 1.")
    else:
        tooltip("PDF cover cleared because page 1 could not be rendered.")


def _edit_pdf_highlight_note(hl_id: str) -> None:
    card_id = current_pdf_card_id()
    if card_id is None:
        showInfo("Could not determine which PDF card owns this highlight.")
        return
    highlight = next(
        (
            row
            for row in load_highlights(_ADDON_DIR, _active_profile(), int(card_id))
            if str(row.get("id") or "") == str(hl_id or "")
        ),
        None,
    )
    if not highlight:
        showInfo("That PDF highlight could not be found.")
        return
    dialog = HighlightNoteDialog(
        mw,
        title="PDF Highlight Note",
        excerpt=str(highlight.get("text") or ""),
        current_note=str(highlight.get("note") or ""),
    )
    if not dialog.exec():
        return
    try:
        updated = update_highlight_note(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            str(highlight.get("id") or ""),
            dialog.note_text(),
        )
    except Exception as exc:
        showInfo(f"Could not save the PDF highlight note.\n\n{exc}")
        return
    if not updated:
        showInfo("That PDF highlight could not be updated.")
        return
    escaped_id = json.dumps(str(updated.get("id") or ""))
    escaped_note = json.dumps(str(updated.get("note") or ""))
    try:
        if _pdf_dock is not None:
            _pdf_dock._view.page().runJavaScript(
                "window.incrementoUpdatePdfHighlightNote && "
                f"window.incrementoUpdatePdfHighlightNote({escaped_id}, {escaped_note});"
            )
    except Exception:
        pass
    tooltip("PDF highlight note saved.")


def _pdf_bookmarks_payload(card_id: int) -> list[dict]:
    try:
        return list_reader_bookmarks(_ADDON_DIR, _active_profile(), int(card_id), "pdf")
    except Exception:
        return []


def _push_pdf_bookmarks(card_id: int | None = None) -> None:
    if _pdf_dock is None:
        return
    try:
        cid = int(card_id if card_id is not None else _current_pdf_card_id)
    except Exception:
        cid = 0
    if cid <= 0:
        return
    payload = json.dumps(_pdf_bookmarks_payload(cid))
    try:
        _pdf_dock._view.page().runJavaScript(
            f"window.incrementoReceivePdfBookmarks && window.incrementoReceivePdfBookmarks({payload});"
        )
    except Exception:
        pass


def _update_pdf_search(query: str, *, active_index: int = 0) -> None:
    card_id = current_pdf_card_id()
    normalized_query = str(query or "").strip()
    if card_id is None or not normalized_query:
        _sync_pdf_search_state("", [], -1)
        _emit_pdf_search_state()
        return
    hits = current_card_pdf_search_hits(card_id, normalized_query)
    resolved_index = -1
    if hits:
        resolved_index = max(0, min(int(active_index), len(hits) - 1))
    _sync_pdf_search_state(normalized_query, hits, resolved_index)
    _emit_pdf_search_state()


def _jump_to_first_pdf_search_hit(query: str) -> None:
    card_id = current_pdf_card_id()
    normalized_query = str(query or "").strip()
    if card_id is None or not normalized_query:
        return
    if not _current_pdf_search_hits:
        return
    _open_pdf_search_hit(0)


def _open_pdf_search_hit(hit_index: int) -> None:
    card_id = current_pdf_card_id()
    if card_id is None or not _current_pdf_search_hits:
        return
    resolved_index = max(0, min(int(hit_index), len(_current_pdf_search_hits) - 1))
    hit = _current_pdf_search_hits[resolved_index]
    _sync_pdf_search_state(_current_pdf_search_query, _current_pdf_search_hits, resolved_index)
    show_pdf_in_dock(
        int(card_id),
        str(_current_pdf_filename or ""),
        int(hit.get("page", 1) or 1),
        get_zoom(_ADDON_DIR, _active_profile(), int(card_id)),
        read_page=get_read_page(_ADDON_DIR, _active_profile(), int(card_id)),
        search_query=_current_pdf_search_query,
        jump_excerpt=str(hit.get("excerpt") or hit.get("snippet") or ""),
        search_hits=_current_pdf_search_hits,
        active_search_hit_index=resolved_index,
        preserve_history=True,
        offer_due_review_prompt=False,
    )


def _add_pdf_bookmark(card_id: int, page: int) -> None:
    try:
        add_reader_bookmark(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            "pdf",
            {"page": max(1, int(page))},
        )
    except Exception as exc:
        showInfo(f"Could not save PDF bookmark:\n{exc}")
        return
    _push_pdf_bookmarks(int(card_id))
    tooltip("PDF bookmark saved.")


def _delete_pdf_bookmark(card_id: int, bookmark_id: str) -> None:
    try:
        delete_reader_bookmark(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            "pdf",
            str(bookmark_id or ""),
        )
    except Exception as exc:
        showInfo(f"Could not delete PDF bookmark:\n{exc}")
        return
    _push_pdf_bookmarks(int(card_id))


def _open_pdf_limit_dialog(card_id: int) -> None:
    settings = get_pdf_daily_limit_settings(_ADDON_DIR, _active_profile(), int(card_id))
    status = _current_pdf_limit_status(
        int(card_id),
        current_page=get_page(_ADDON_DIR, _active_profile(), int(card_id)),
    )
    dlg = _PdfReadingLimitDialog(mw, settings=settings, status=status)
    if not dlg.exec():
        return
    new_settings = dlg.result_settings()
    save_pdf_daily_limit_settings(
        _ADDON_DIR,
        _active_profile(),
        int(card_id),
        enabled=bool(new_settings.get("enabled")),
        daily_page_limit=int(new_settings.get("daily_page_limit", 0) or 0),
        enforcement_mode=str(new_settings.get("enforcement_mode") or "warning"),
    )
    refreshed = _current_pdf_limit_status(
        int(card_id),
        current_page=get_page(_ADDON_DIR, _active_profile(), int(card_id)),
    )
    _push_pdf_limit_status(refreshed)
    if refreshed.get("enabled"):
        tooltip(
            f"PDF limit saved: {refreshed['daily_page_limit']} pages/day "
            f"({refreshed['enforcement_label']})."
        )
    else:
        tooltip("PDF daily reading limit disabled.")


def _start_due_pdf_review(card_id: int, *, current_page: int, due_cards: list[dict]) -> None:
    selected_ids = [int(row["card_id"]) for row in due_cards if int(row.get("card_id", 0) or 0) > 0]
    if not selected_ids:
        tooltip("No due extracted cards to review for this PDF.")
        return

    try:
        note = mw.col.get_note(mw.col.get_card(int(card_id)).nid)
        filename = str(note["PDF_Filename"])
    except Exception:
        filename = str(_current_pdf_filename or "")
    if not filename:
        showInfo("Could not reopen this PDF after review.")
        return

    zoom = get_zoom(_ADDON_DIR, _active_profile(), int(card_id))
    read_page = get_read_page(_ADDON_DIR, _active_profile(), int(card_id))

    current_deck = {}
    try:
        current_deck = mw.col.decks.current() or {}
    except Exception:
        current_deck = {}
    previous_did = current_deck.get("id")

    def _restore_pdf() -> None:
        try:
            if previous_did:
                mw.col.decks.select(previous_did)
        except Exception:
            pass
        QTimer.singleShot(
            0,
            lambda: show_pdf_in_dock(
                int(card_id),
                filename,
                int(current_page),
                zoom,
                read_page=read_page,
                preserve_history=False,
                offer_due_review_prompt=False,
            ),
        )

    started = start_explicit_review(
        selected_ids,
        deck_name=INCREMENTO_PDF_REVIEW_DECK,
        preserve_order=True,
        empty_message="No due extracted cards are available to review for this PDF.",
        on_finished=_restore_pdf,
    )
    if not started:
        return


def _offer_due_review_for_pdf(
    card_id: int,
    *,
    current_page: int | None = None,
    force: bool = False,
) -> None:
    page = max(1, int(current_page or get_page(_ADDON_DIR, _active_profile(), int(card_id)) or 1))
    settings = get_pdf_due_review_prompt_settings(_ADDON_DIR, _active_profile(), int(card_id))
    if not force and not settings.get("enabled", True):
        return

    due_cards = get_due_pdf_source_cards(
        _ADDON_DIR,
        _active_profile(),
        int(card_id),
        page,
    )
    if not due_cards:
        if force:
            tooltip("No due extracted cards from this PDF up to the current page.")
        return

    dlg = _PdfDueReviewPromptDialog(
        mw,
        due_cards=due_cards,
        settings=settings,
        current_page=page,
    )
    result = dlg.exec()
    new_enabled = dlg.offer_on_open_enabled()
    if new_enabled != bool(settings.get("enabled", True)):
        save_pdf_due_review_prompt_settings(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            enabled=new_enabled,
        )
    if result and dlg.review_requested():
        _start_due_pdf_review(int(card_id), current_page=page, due_cards=due_cards)


# ── pycmd bridge (console.log interceptor) ───────────────────────────────────


def _handle_pdf_js_message(msg: str) -> None:
    if msg.startswith(_MSG_NAV):
        parts = msg.split(":")
        if len(parts) == 3:
            try:
                cid = int(parts[1])
                pg = int(parts[2])
                if cid > 0:
                    current_pg = get_page(_ADDON_DIR, _active_profile(), cid)
                    status_before = _current_pdf_limit_status(cid, current_page=current_pg)
                    allowed_max = status_before.get("allowed_max_page")
                    is_blocking = bool(
                        status_before.get("enabled")
                        and status_before.get("enforcement_mode") in {"soft_lock", "hard_stop"}
                        and not status_before.get("override_enabled")
                        and allowed_max is not None
                        and pg > current_pg
                        and pg > int(allowed_max)
                    )
                    if is_blocking:
                        _push_pdf_limit_status(status_before)
                        return
                    if not _pdf_via_link and not _pdf_preserve_history:
                        set_page(_ADDON_DIR, _active_profile(), cid, pg)
                    _timer_mod.record_pdf_page_read(cid, pg)
                    _push_pdf_limit_status(_current_pdf_limit_status(cid, current_page=pg))
            except ValueError:
                pass
    elif msg.startswith(_MSG_ZOOM):
        parts = msg.split(":")
        if len(parts) == 3:
            try:
                if int(parts[1]) > 0 and not _pdf_preserve_history:
                    set_zoom(_ADDON_DIR, _active_profile(), int(parts[1]), float(parts[2]))
            except ValueError:
                pass
    elif msg.startswith(_MSG_SCROLL):
        try:
            payload = json.loads(msg[len(_MSG_SCROLL) :])
            cid = int(payload.get("cardId", 0) or 0)
            if cid > 0 and not _pdf_preserve_history:
                set_scroll_ratio(
                    _ADDON_DIR,
                    _active_profile(),
                    cid,
                    float(payload.get("scrollRatio", 0.0) or 0.0),
                )
        except Exception:
            pass
    elif msg.startswith(_MSG_HL_ADD):
        try:
            data = json.loads(msg[len(_MSG_HL_ADD) :])
            add_highlight(_ADDON_DIR, _active_profile(), int(data["cardId"]), data["highlight"])
        except Exception as e:
            print(f"[Incremento] pdf_dock: highlight add failed: {e}")
    elif msg.startswith(_MSG_HL_DEL):
        try:
            data = json.loads(msg[len(_MSG_HL_DEL) :])
            remove_highlight(_ADDON_DIR, _active_profile(), int(data["cardId"]), data["id"])
        except Exception as e:
            print(f"[Incremento] pdf_dock: highlight delete failed: {e}")
    elif msg.startswith(_MSG_MARK_READ):
        payload_raw = msg[len(_MSG_MARK_READ) :]
        try:
            if payload_raw.lstrip().startswith("{"):
                payload = json.loads(payload_raw)
                cid = int(payload.get("cardId", 0) or 0)
                read_page = int(payload.get("readPage", 0) or 0)
                read_anchor = payload.get("anchor")
            else:
                parts = msg.split(":")
                if len(parts) != 3:
                    raise ValueError
                cid = int(parts[1])
                read_page = int(parts[2])
                read_anchor = None
            if cid > 0:
                status = _current_pdf_limit_status(cid, current_page=max(1, read_page or 1))
                allowed_max = status.get("allowed_max_page")
                is_blocking = bool(
                    status.get("enabled")
                    and status.get("enforcement_mode") in {"soft_lock", "hard_stop"}
                    and not status.get("override_enabled")
                    and allowed_max is not None
                    and read_page > int(allowed_max)
                )
                if is_blocking:
                    _push_pdf_limit_status(status)
                    return
                if not _pdf_preserve_history:
                    set_read_page(
                        _ADDON_DIR,
                        _active_profile(),
                        cid,
                        read_page,
                        read_anchor if isinstance(read_anchor, dict) else None,
                    )
                _push_pdf_limit_status(status)
        except ValueError:
            pass
    elif msg.startswith(_MSG_CMD1):
        text = msg[len(_MSG_CMD1) :]
        if text:
            QTimer.singleShot(0, lambda t=text: _on_pdf_selection(0, t))
    elif msg == _MSG_OPEN_ADD_CARD:
        if _cb_open_add_card_dock:
            _cb_open_add_card_dock()
    elif msg.startswith(_MSG_FILL_FIELD):
        try:
            data = json.loads(msg[len(_MSG_FILL_FIELD) :])
            if _cb_fill_dock_field:
                _cb_fill_dock_field(int(data["idx"]), data["text"])
        except Exception:
            pass
    elif msg.startswith(_MSG_SELECTION_STATE):
        try:
            data = json.loads(msg[len(_MSG_SELECTION_STATE) :])
            from . import add_card_dock as _add_card_dock_mod

            _add_card_dock_mod.update_selection_state(
                "pdf",
                has_text=bool(data.get("hasText")),
            )
        except Exception:
            pass
    elif msg.startswith(_MSG_LIMIT_SETTINGS):
        try:
            cid = int(msg[len(_MSG_LIMIT_SETTINGS) :])
            if cid > 0:
                _open_pdf_limit_dialog(cid)
        except Exception as e:
            showInfo(f"Could not edit PDF reading limit:\n{e}")
    elif msg.startswith(_MSG_LIMIT_OVERRIDE):
        try:
            cid = int(msg[len(_MSG_LIMIT_OVERRIDE) :])
            if cid > 0:
                status = set_pdf_daily_limit_override(
                    _ADDON_DIR,
                    _active_profile(),
                    cid,
                    enabled=True,
                    current_page=get_page(_ADDON_DIR, _active_profile(), cid),
                )
                _push_pdf_limit_status(status)
                tooltip("PDF reading limit overridden for today.")
        except Exception as e:
            showInfo(f"Could not override PDF reading limit:\n{e}")
    elif msg.startswith(_MSG_DUE_REVIEW):
        try:
            parts = msg.split(":")
            if len(parts) == 3:
                cid = int(parts[1])
                if cid > 0:
                    _offer_due_review_for_pdf(
                        cid,
                        current_page=int(parts[2]),
                        force=True,
                    )
        except Exception as e:
            showInfo(f"Could not open PDF due-card review:\n{e}")
    elif msg.startswith(_MSG_HL_NOTE):
        try:
            payload = json.loads(msg[len(_MSG_HL_NOTE) :])
            _edit_pdf_highlight_note(str(payload.get("id") or ""))
        except Exception as e:
            showInfo(f"Could not edit PDF highlight note.\n\n{e}")
    elif msg.startswith(_MSG_BOOKMARK_ADD):
        try:
            payload = json.loads(msg[len(_MSG_BOOKMARK_ADD) :])
            cid = int(payload.get("cardId", 0) or 0)
            page = int(payload.get("page", 1) or 1)
            if cid > 0:
                _add_pdf_bookmark(cid, page)
        except Exception as e:
            showInfo(f"Could not save PDF bookmark:\n{e}")
    elif msg.startswith(_MSG_BOOKMARK_DELETE):
        try:
            payload = json.loads(msg[len(_MSG_BOOKMARK_DELETE) :])
            cid = int(payload.get("cardId", 0) or 0)
            if cid > 0:
                _delete_pdf_bookmark(cid, str(payload.get("id") or ""))
        except Exception as e:
            showInfo(f"Could not delete PDF bookmark:\n{e}")
    elif msg.startswith(_MSG_BOOKMARK_LIST):
        try:
            cid = int(msg[len(_MSG_BOOKMARK_LIST) :])
            if cid > 0:
                _push_pdf_bookmarks(cid)
        except Exception:
            pass
    elif msg.startswith(_MSG_FIND):
        try:
            payload = json.loads(msg[len(_MSG_FIND) :])
            query = str(payload.get("query") or "")
            _update_pdf_search(query)
            if query.strip():
                _jump_to_first_pdf_search_hit(query)
        except Exception:
            pass
    elif msg.startswith(_MSG_FIND_NAV):
        try:
            payload = json.loads(msg[len(_MSG_FIND_NAV) :])
            direction = int(payload.get("direction", 0) or 0)
            if not _current_pdf_search_hits:
                return
            if direction == 0:
                target_index = int(payload.get("index", _current_pdf_search_hit_index) or 0)
            else:
                base_index = _current_pdf_search_hit_index if _current_pdf_search_hit_index >= 0 else 0
                target_index = base_index + (1 if direction > 0 else -1)
            target_index = max(0, min(target_index, len(_current_pdf_search_hits) - 1))
            _open_pdf_search_hit(target_index)
        except Exception:
            pass
    elif msg == _MSG_OPEN_FIND_DIALOG:
        try:
            open_current_document_find()
        except Exception:
            pass
    elif msg.startswith(_MSG_REPAIR_MISSING):
        _repair_missing_pdf()
    elif msg.startswith(_MSG_REGENERATE_COVER):
        _regenerate_pdf_cover()
    elif msg.startswith(_MSG_SNAPSHOT):
        QTimer.singleShot(0, lambda m=msg: _handle_pdf_snapshot(m))
    elif msg.startswith(_MSG_FINISHED):
        try:
            card_id = int(msg[len(_MSG_FINISHED) :])
            if card_id > 0:
                mw.col.sched.suspend_cards([card_id])
                mw.col.reset()
                tooltip("PDF card suspended — it won't appear in future sessions.")
                if _pdf_dock:
                    _pdf_dock.hide()
        except Exception as e:
            showInfo(f"Could not suspend card:\n{e}")
    elif msg.startswith(_MSG_OPEN_CARD):
        try:
            note_id = int(msg[len(_MSG_OPEN_CARD) :])
            QTimer.singleShot(0, lambda nid=note_id: show_pdf_page_card_preview(nid))
        except Exception:
            pass
    elif msg.startswith(_MSG_OPEN_ALL_CARDS):
        try:
            card_id = int(msg[len(_MSG_OPEN_ALL_CARDS) :])
            if card_id > 0:
                QTimer.singleShot(0, lambda cid=card_id: _open_all_pdf_cards_in_browser(cid))
        except Exception:
            pass
    elif msg.startswith(_MSG_OPEN_PAGE_CARDS):
        try:
            payload = json.loads(msg[len(_MSG_OPEN_PAGE_CARDS) :])
            note_ids = payload if isinstance(payload, list) else []
            QTimer.singleShot(
                0,
                lambda ids=note_ids: _browse_note_ids_in_browser(
                    ids,
                    empty_message="No cards created on this page yet.",
                ),
            )
        except Exception:
            pass
    elif msg.startswith("incremento_get_page_cards:"):
        try:
            parts = msg.split(":")
            if len(parts) == 3:
                cid = int(parts[1])
                page = int(parts[2])
                if cid > 0:
                    cards, counts = _reconcile_pdf_page_sources(cid, page)
                else:
                    cards = []
                    counts = {}
                data = {"page": page, "cards": cards, "pageCounts": counts}
                js = (
                    "window.incrementoReceivePageCards && "
                    f"window.incrementoReceivePageCards({json.dumps(data)})"
                )
                QTimer.singleShot(
                    0,
                    lambda j=js: (
                        _pdf_dock._view.page().runJavaScript(j)
                        if _pdf_dock
                        else None
                    ),
                )
        except Exception:
            pass


class _PdfDockPage(QWebEnginePage):
    """Intercepts console.log to get pycmd messages from the PDF viewer JS."""

    def javaScriptConsoleMessage(self, level, message, line, source):
        if not message.startswith(_PYCMD_BRIDGE):
            return
        _handle_pdf_js_message(message[len(_PYCMD_BRIDGE) :])


class _PdfShortcutFilter(QObject):
    """Capture Cmd/Ctrl+1..4 before WebEngine or menu handling consumes them."""

    def eventFilter(self, watched, event):
        try:
            if event.type() not in (
                QEvent.Type.ShortcutOverride,
                QEvent.Type.KeyPress,
            ):
                return False

            if _pdf_dock is None or not _pdf_dock.isVisible():
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
                text_to_idx = {
                    "1": 0,
                    "!": 0,
                    "2": 1,
                    "@": 1,
                    "3": 2,
                    "#": 2,
                    "4": 3,
                    "$": 3,
                }
                idx = text_to_idx.get((event.text() or "")[:1])
            if idx is None:
                return False

            event.accept()

            if event.type() == QEvent.Type.ShortcutOverride:
                return True

            try:
                _pdf_dock._view.page().runJavaScript(
                    f"window.incrementoHandleExtractShortcut && window.incrementoHandleExtractShortcut({idx});"
                )
            except Exception:
                pass
            return True
        except Exception:
            return False


# ── Snapshot handler ──────────────────────────────────────────────────────────


def _handle_pdf_snapshot(msg: str) -> None:
    """Save snapshot image to media and fill a chosen field in the Add Card dock."""
    import base64 as _b64, tempfile as _tmp
    from PyQt6.QtGui import QImage

    try:
        data = json.loads(msg[len("incremento_pdf_snapshot:") :])
        img_b64 = data["image"]
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]
        img_bytes = _b64.b64decode(img_b64)

        with _tmp.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img_bytes)
            tmp_path = f.name
        try:
            media_filename = mw.col.media.add_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        # Open Add Card dock and read its current field names
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

        # Build pixmap preview
        pixmap = QPixmap.fromImage(QImage.fromData(img_bytes))
        scaled = pixmap.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
        if scaled.height() > 180:
            scaled = pixmap.scaledToHeight(
                180, Qt.TransformationMode.SmoothTransformation
            )

        # Dialog: image preview + one button per field name
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
            _cb_fill_dock_field(chosen_idx[0], f'<img src="{media_filename}">')
    except Exception as e:
        showInfo(f"Snapshot failed:\n{e}")


# ── Dock construction ─────────────────────────────────────────────────────────


def _build_pdf_dock():
    global _pdf_dock, _shortcuts_registered, _pdf_key_filter

    dock = QDockWidget("PDF Viewer", mw)
    dock.setObjectName("incremento_pdf_dock")
    dock.setMinimumWidth(550)

    page = _PdfDockPage(dock)
    # Allow file:// page to load other file:// resources (worker, PDF)
    s = page.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
    )

    view = QWebEngineView(dock)
    view.setPage(page)
    dock.setWidget(view)
    dock._view = view

    if _pdf_key_filter is None:
        _pdf_key_filter = _PdfShortcutFilter(mw)

    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_pdf_key_filter)
    mw.installEventFilter(_pdf_key_filter)
    view.installEventFilter(_pdf_key_filter)
    page.installEventFilter(_pdf_key_filter)

    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _on_visibility_changed(visible: bool) -> None:
        if visible:
            return
        _stop_current_pdf_view()

    dock.visibilityChanged.connect(_on_visibility_changed)

    # Inject fake pycmd bridge + Cmd+1 keydown listener after every page load
    def _on_load_finished(ok):
        if ok:
            view.page().runJavaScript(
                f"window.pycmd = function(msg) {{"
                f"  console.log('{_PYCMD_BRIDGE}' + msg);"
                f"}};"
                # Cache selection on change so the keydown handler can read it.
                "document.addEventListener('selectionchange', function() {"
                "  var s = window.getSelection();"
                "  var text = s ? s.toString().trim() : '';"
                "  if (text) {"
                "    window._lastPdfSelection = text;"
                "    window.pycmd('incremento_selection_state:' + JSON.stringify({source: 'pdf', hasText: true}));"
                "  }"
                "});"
                # Cmd/Ctrl+1 inside the webview.
                "document.addEventListener('keydown', function(e) {"
                "  var digit1 = (e.code === 'Digit1' || e.key === '1');"
                "  if ((e.metaKey || e.ctrlKey) && digit1) {"
                "    e.preventDefault();"
                "    e.stopPropagation();"
                "    var sel = window._lastPdfSelection || '';"
                "    if (sel) { window.pycmd('incremento_pdf_cmd1:' + sel); }"
                "  }"
                "}, true);"
            )

    view.loadFinished.connect(_on_load_finished)

    # Fallback app-level shortcuts in case WebEngine consumes the key event.
    if not _shortcuts_registered:

        def _act_extract_field1():
            if _pdf_dock is None:
                return
            try:
                _pdf_dock._view.page().runJavaScript(
                    "window.incrementoHandleExtractShortcut && window.incrementoHandleExtractShortcut(0);",
                )
            except Exception:
                pass

        for seq in ("Ctrl+1", "Meta+1"):
            sc = QShortcut(QKeySequence(seq), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(_act_extract_field1)
            _pdf_shortcuts.append(sc)

        globals()["_shortcuts_registered"] = True

    _pdf_dock = dock
    return dock


def _on_pdf_selection(idx: int, text: str) -> None:
    text = (text or "").strip()
    if text:
        if _cb_open_add_card_dock:
            _cb_open_add_card_dock()
        if _cb_fill_dock_field:
            QTimer.singleShot(150, lambda: _cb_fill_dock_field(idx, text))


def trigger_viewer_action(action: str) -> None:
    """Invoke a viewer action in the PDF dock if it is currently available."""
    if _pdf_dock is None:
        return
    try:
        view = _pdf_dock._view
        if not _pdf_dock.isVisible():
            return
    except Exception:
        return

    js_by_action = {
        "prev_page": "window.incrementoPdfNav && window.incrementoPdfNav(-1);",
        "next_page": "window.incrementoPdfNav && window.incrementoPdfNav(1);",
        "zoom_out": "window.incrementoPdfZoom && window.incrementoPdfZoom(-1);",
        "zoom_in": "window.incrementoPdfZoom && window.incrementoPdfZoom(1);",
        "mark_read": "window.incrementoPdfMarkRead && window.incrementoPdfMarkRead();",
        "open_find": "window.incrementoPdfOpenFind && window.incrementoPdfOpenFind();",
    }
    js = js_by_action.get(action)
    if not js:
        return
    try:
        view.page().runJavaScript(js)
    except Exception:
        pass


def open_current_document_find() -> bool:
    if _pdf_dock is None:
        return False
    try:
        if not _pdf_dock.isVisible():
            return False
        if _cb_open_current_document_search is not None:
            return bool(_cb_open_current_document_search())
    except Exception:
        pass
    try:
        _pdf_dock._view.page().runJavaScript(
            "window.incrementoPdfOpenFind && window.incrementoPdfOpenFind();",
        )
        return True
    except Exception:
        return False


def open_current_pdf_search_hit(hit: dict, index: int, query: str) -> bool:
    card_id = current_pdf_card_id()
    if card_id is None:
        return False
    page = int(hit.get("page", 1) or 1)
    hits = current_card_pdf_search_hits(int(card_id), query) if str(query or "").strip() else []
    resolved_index = int(index)
    if hits:
        matched = next(
            (
                idx
                for idx, candidate in enumerate(hits)
                if int(candidate.get("page", 0) or 0) == page
                and str(candidate.get("excerpt") or candidate.get("snippet") or "")
                == str(hit.get("excerpt") or hit.get("snippet") or "")
            ),
            -1,
        )
        if matched >= 0:
            resolved_index = matched
        elif resolved_index < 0 or resolved_index >= len(hits):
            resolved_index = 0
    show_pdf_in_dock(
        int(card_id),
        str(_current_pdf_filename or ""),
        page,
        get_zoom(_ADDON_DIR, _active_profile(), int(card_id)),
        read_page=get_read_page(_ADDON_DIR, _active_profile(), int(card_id)),
        search_query=str(query or ""),
        jump_excerpt=str(hit.get("excerpt") or hit.get("snippet") or ""),
        search_hits=hits,
        active_search_hit_index=resolved_index,
        preserve_history=True,
        offer_due_review_prompt=False,
    )
    return True


# ── Show PDF in dock ──────────────────────────────────────────────────────────


def show_pdf_in_dock(
    card_id,
    filename,
    page,
    zoom=1.0,
    via_link=False,
    read_page=0,
    search_query="",
    jump_excerpt="",
    search_hits: list[dict] | None = None,
    active_search_hit_index: int = -1,
    preserve_history=False,
    offer_due_review_prompt=True,
) -> None:
    global _pdf_dock, _current_pdf_card_id, _current_pdf_filename, _pdf_via_link, _pdf_preserve_history
    try:
        normalized_card_id = int(card_id)
    except Exception:
        normalized_card_id = 0
    resolved_filename = str(filename or "").strip()
    if normalized_card_id > 0:
        try:
            card = mw.col.get_card(normalized_card_id) if getattr(mw, "col", None) else None
            note = mw.col.get_note(card.nid) if card is not None else None
            note_filename = str(note["PDF_Filename"] or "").strip() if note is not None else ""
        except Exception:
            note_filename = ""
        if note_filename:
            resolved_filename = note_filename

    if normalized_card_id > 0 and resolved_filename and not os.path.exists(_pdf_storage_path(resolved_filename)):
        try:
            repaired_filename = repair_pdf_card_filename(
                _ADDON_DIR,
                _active_profile(),
                mw.col,
                normalized_card_id,
                missing_filename=resolved_filename,
            )
        except Exception:
            repaired_filename = ""
        if repaired_filename:
            resolved_filename = repaired_filename

    _current_pdf_card_id = normalized_card_id if normalized_card_id > 0 else 0
    _current_pdf_filename = resolved_filename
    _pdf_via_link = via_link
    _pdf_preserve_history = bool(preserve_history)
    if _pdf_dock is None:
        _build_pdf_dock()
    else:
        try:
            _pdf_dock.widget()
        except RuntimeError:
            _pdf_dock = None
            _build_pdf_dock()

    _pdf_dock.show()
    _pdf_dock.raise_()

    if _cb_pdf_view_started:
        try:
            _cb_pdf_view_started(_current_pdf_card_id)
        except Exception:
            pass

    if not os.path.exists(_pdf_storage_path(resolved_filename)):
        _show_missing_pdf_screen(resolved_filename)
        tooltip("Stored PDF file is missing. Choose a replacement PDF to repair this card.")
        return

    pdf_file_url = QUrl.fromLocalFile(_pdf_storage_path(resolved_filename)).toString()

    resolved_read_page = int(read_page or 0)
    if normalized_card_id > 0 and resolved_read_page <= 0:
        try:
            resolved_read_page = int(
                get_read_page(_ADDON_DIR, _active_profile(), normalized_card_id) or 0
            )
        except Exception:
            resolved_read_page = 0

    hls = load_highlights(_ADDON_DIR, _active_profile(), card_id)
    bookmarks = _pdf_bookmarks_payload(card_id)
    limit_status = _current_pdf_limit_status(card_id, current_page=page)
    read_anchor = get_read_anchor(_ADDON_DIR, _active_profile(), card_id)
    scroll_ratio = get_scroll_ratio(_ADDON_DIR, _active_profile(), card_id)
    normalized_jump_excerpt = _normalize_pdf_reference_excerpt(jump_excerpt)

    if search_hits is None:
        if str(search_query or "").strip():
            search_hits = current_card_pdf_search_hits(int(card_id), str(search_query or ""))
        else:
            search_hits = []
    resolved_search_index = int(active_search_hit_index)
    if resolved_search_index < 0 and search_hits:
        resolved_search_index = 0
    _sync_pdf_search_state(str(search_query or ""), list(search_hits or []), resolved_search_index)

    js = (
        f"window._pdfWorkerSrc    = {json.dumps(_WORKER_URL)};"
        f"window._pdfFileUrl      = {json.dumps(pdf_file_url)};"
        f"window._incPdfHighlights = {json.dumps(hls)};"
        f"window._incPdfBookmarks = {json.dumps(bookmarks)};"
        f"window._incPdfPending   = {{cardId: {card_id}, filename: {json.dumps(resolved_filename)}, page: {page}, zoom: {zoom}, scrollRatio: {scroll_ratio}, readPage: {resolved_read_page}, readAnchor: {json.dumps(read_anchor)}, searchQuery: {json.dumps(search_query or '')}, searchHits: {json.dumps(search_hits or [])}, activeSearchHitIndex: {int(resolved_search_index)}, jumpExcerpt: {json.dumps(normalized_jump_excerpt)}, scrollToReadAnchor: {json.dumps(bool(via_link))}, limitStatus: {json.dumps(limit_status)}, autoHighlightOnExtract: {json.dumps(configured_highlight_when_extracting())}, scrollToTopOnPageChange: {json.dumps(configured_scroll_to_top_on_page_change())}, bookmarks: {json.dumps(bookmarks)} }};"
        f"typeof incrementoPdfStart === 'function' && "
        f"(window._incPdfPending = null,"
        f" incrementoPdfStart({card_id}, {json.dumps(resolved_filename)}, {page}, {zoom}, {scroll_ratio}, {resolved_read_page}, {json.dumps(read_anchor)}, {json.dumps(search_query or '')}, {json.dumps(search_hits or [])}, {int(resolved_search_index)}, {json.dumps(normalized_jump_excerpt)}, {json.dumps(bool(via_link))}, {json.dumps(limit_status)}, {json.dumps(configured_highlight_when_extracting())}, {json.dumps(configured_scroll_to_top_on_page_change())}, {json.dumps(bookmarks)}));"
    )

    current = _pdf_dock._view.url().toString()
    if current != _DOCK_HTML:

        def _on_first_load(ok):
            _pdf_dock._view.loadFinished.disconnect(_on_first_load)
            if ok:
                _pdf_dock._view.page().runJavaScript(js)

        _pdf_dock._view.loadFinished.connect(_on_first_load)
        _pdf_dock._view.load(QUrl(_DOCK_HTML))
    else:
        _pdf_dock._view.page().runJavaScript(js)

    if offer_due_review_prompt and not _consume_due_review_prompt_suppression(int(card_id)):
        QTimer.singleShot(
            0,
            lambda cid=int(card_id), pg=int(page): _offer_due_review_for_pdf(
                cid,
                current_page=pg,
                force=False,
            ),
        )


# ── Reviewer hooks ────────────────────────────────────────────────────────────


def on_pdf_question_shown(card) -> None:
    global _pdf_dock
    try:
        if card is None:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != PDF_NOTE_TYPE:
            _hide_pdf_dock_for_inactive_context()
            return
        try:
            filename = note["PDF_Filename"]
        except (KeyError, TypeError):
            return
        page = get_page(_ADDON_DIR, _active_profile(), card.id)
        zoom = get_zoom(_ADDON_DIR, _active_profile(), card.id)
        read_page = get_read_page(_ADDON_DIR, _active_profile(), card.id)
        show_pdf_in_dock(card.id, filename, page, zoom, read_page=read_page)
    except Exception as e:
        print(f"[Incremento] on_pdf_question_shown error: {e}")


def on_pdf_reviewer_will_end() -> None:
    _hide_pdf_dock_for_inactive_context()


def on_add_cards_did_add_note(note) -> None:
    """When a card is saved in the AddCards dock, record it against the current PDF page."""
    try:
        tracked_pdf_card_id = int(_current_pdf_card_id or 0)
    except Exception:
        tracked_pdf_card_id = 0
    if tracked_pdf_card_id <= 0:
        return
    source = _add_card_source_for_new_note()
    if source:
        if source != "pdf":
            return
    else:
        reviewer_card_id = _current_reviewer_card_id()
        if reviewer_card_id is not None and reviewer_card_id != tracked_pdf_card_id:
            return
    _suppress_next_due_review_prompt_for_pdf_add(tracked_pdf_card_id)
    page = get_page(_ADDON_DIR, _active_profile(), tracked_pdf_card_id)
    import re as _re

    parts = []
    for field in (note.fields or [])[:2]:
        plain = _re.sub(r"<[^>]+>", "", field).strip()[:120]
        if plain:
            parts.append(plain)
    excerpt = " / ".join(parts)[:200]
    try:
        add_pdf_card_source(
            _ADDON_DIR,
            _active_profile(),
            tracked_pdf_card_id,
            page,
            note.id,
            excerpt,
            str(_current_pdf_filename or "").strip(),
        )
    except Exception:
        pass
    if _pdf_dock is None:
        return
    try:
        cards, counts = _reconcile_pdf_page_sources(tracked_pdf_card_id, page)
        data = {"page": page, "cards": cards, "pageCounts": counts}
        js = (
            "window.incrementoReceivePageCards && "
            f"window.incrementoReceivePageCards({json.dumps(data)})"
        )
        _pdf_dock._view.page().runJavaScript(js)
    except Exception:
        pass

    # Adding a note sets study_queues=True in OpChanges, which causes the reviewer
    # to call nextCard() via op_executed. If the next card is not a PDF card,
    # on_pdf_question_shown hides the PDF dock. Re-show it so the user can
    # continue reading without interruption.
    cid = tracked_pdf_card_id
    restore_filename = str(_current_pdf_filename or "").strip()

    def _restore_pdf_dock() -> None:
        global _current_pdf_card_id, _current_pdf_filename
        active_card_id = current_pdf_card_id()
        if active_card_id is not None and active_card_id != cid:
            return  # a different PDF card became active; don't interfere
        try:
            if _pdf_dock is not None and not _pdf_dock.isVisible():
                if active_card_id is None:
                    _current_pdf_card_id = cid
                    _current_pdf_filename = restore_filename
                _pdf_dock.show()
                if _cb_pdf_view_started:
                    try:
                        _cb_pdf_view_started(cid)
                    except Exception:
                        pass
        except RuntimeError:
            pass

    QTimer.singleShot(0, _restore_pdf_dock)


def get_selected_text(callback) -> None:
    if _pdf_dock is None:
        callback("")
        return
    try:
        _pdf_dock._view.page().runJavaScript(
            "(function(){ return (window._lastPdfSelection || '').trim(); })();",
            lambda text: callback(text or ""),
        )
    except Exception:
        callback("")
