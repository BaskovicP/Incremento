"""Focus timer widget and related session-state helpers.

All timer globals live here so __init__.py doesn't need to own them.
__init__.py imports the public API (build_timer_toolbar, on_timer_question_shown,
timer_on_card_answered) and accesses live state via the module reference.
"""

import os

from aqt import mw
from aqt.qt import (QWidget, QHBoxLayout, QPushButton, QLabel, QTimer,
                    QDialog, QVBoxLayout, Qt, QToolBar, QSizePolicy,
                    QApplication, qconnect)

# Addon root — same derivation used by learn_dialog.py and scheduler_config.py
_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

# ── Timer session state ───────────────────────────────────────────────────────

_timer_running:        bool = False
_timer_duration_min:   int  = 30
_timer_cards_answered: int  = 0
_timer_pdf_pages:      set  = set()   # {(card_id, page)} unique pages seen since the last timer report
_timer_epub_pages:     set  = set()   # {(card_id, page)} unique EPUB pages seen since the last timer report
_timer_toolbar               = None   # QToolBar instance, set by build_timer_toolbar
_timer_widget                = None   # _TimerWidget instance, set by build_timer_toolbar

_DEFAULT_AUTO_TIMER_CARD_TYPES = {
    "pdf": True,
    "epub": True,
    "video": False,
    "web": False,
    "writing": False,
    "local_file": False,
}
_AUTO_TIMER_TYPE_NOTE_TYPES = {
    "pdf": {"Incremento PDF"},
    "epub": {"Incremento EPUB"},
    "video": {"Incremento Video"},
    "web": {"Incremento Web"},
    "writing": {"Incremento Writing"},
    "local_file": {"Incremento Local File"},
}


def _timer_running_set(val: bool) -> None:
    global _timer_running
    _timer_running = val


def reset_activity_counters() -> None:
    """Clear card/page activity collected for the next timer report."""
    global _timer_cards_answered, _timer_pdf_pages, _timer_epub_pages
    _timer_cards_answered = 0
    _timer_pdf_pages = set()
    _timer_epub_pages = set()


def record_card_answered() -> None:
    """Count an answered card regardless of whether the focus timer is running."""
    global _timer_cards_answered
    _timer_cards_answered += 1


def record_pdf_page_read(card_id: int, page: int) -> None:
    """Count a PDF page view regardless of whether the focus timer is running."""
    try:
        cid = int(card_id)
        pg = int(page)
    except Exception:
        return
    if cid <= 0 or pg <= 0:
        return
    _timer_pdf_pages.add((cid, pg))


def record_epub_page_read(card_id: int, page_index: int) -> None:
    """Count an EPUB page view regardless of whether the focus timer is running."""
    try:
        cid = int(card_id)
        pg = int(page_index) + 1
    except Exception:
        return
    if cid <= 0 or pg <= 0:
        return
    _timer_epub_pages.add((cid, pg))


def begin_timer_session(duration_min: int) -> None:
    """Start a timer period without clearing already collected activity."""
    global _timer_running, _timer_duration_min
    _timer_running = True
    _timer_duration_min = int(duration_min or 0)


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        return mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        return {}


def _normalize_tag_list(raw: list[str] | str | tuple[str, ...] | set[str] | None) -> list[str]:
    if isinstance(raw, str):
        parts = raw.replace("\n", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        parts = []

    tags: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item or "").strip()
        if not tag:
            continue
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
    return tags


def configured_auto_timer_enabled(config: dict | None = None) -> bool:
    return bool(_resolved_config(config).get("auto_timer_enabled", False))


def configured_auto_timer_card_types(config: dict | None = None) -> dict[str, bool]:
    raw = _resolved_config(config).get("auto_timer_card_types")
    resolved = dict(_DEFAULT_AUTO_TIMER_CARD_TYPES)
    if isinstance(raw, dict):
        for key in resolved:
            if key in raw:
                resolved[key] = bool(raw.get(key))
    return resolved


def configured_auto_timer_tags(config: dict | None = None) -> list[str]:
    return _normalize_tag_list(_resolved_config(config).get("auto_timer_tags"))


def configured_auto_timer_minutes(config: dict | None = None) -> int:
    raw = _resolved_config(config).get("auto_timer_minutes", 30)
    try:
        minutes = int(raw)
    except Exception:
        minutes = 30
    return max(1, min(1440, minutes))


def configured_timer_completion_beep_enabled(config: dict | None = None) -> bool:
    return bool(_resolved_config(config).get("timer_completion_beep", True))


def _card_note_type_name(card) -> str:
    try:
        note = card.note()
    except Exception:
        note = None

    if note is not None:
        try:
            note_type = note.note_type()
            if isinstance(note_type, dict):
                return str(note_type.get("name") or "").strip()
        except Exception:
            pass
        try:
            model = getattr(note, "_model", None)
            if isinstance(model, dict):
                return str(model.get("name") or "").strip()
        except Exception:
            pass

    try:
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        if isinstance(model, dict):
            return str(model.get("name") or "").strip()
    except Exception:
        pass

    return ""


def _card_tags(card) -> set[str]:
    try:
        note = card.note()
    except Exception:
        note = None
    if note is None:
        try:
            note = mw.col.get_note(card.nid)
        except Exception:
            note = None
    if note is None:
        return set()
    try:
        return {
            str(tag or "").strip().lower()
            for tag in (getattr(note, "tags", None) or [])
            if str(tag or "").strip()
        }
    except Exception:
        return set()


def card_matches_auto_timer_config(card, config: dict | None = None) -> bool:
    if card is None or not configured_auto_timer_enabled(config):
        return False

    enabled_types = configured_auto_timer_card_types(config)
    note_type_name = _card_note_type_name(card)
    for key, enabled in enabled_types.items():
        if enabled and note_type_name in _AUTO_TIMER_TYPE_NOTE_TYPES.get(key, set()):
            return True

    wanted_tags = {
        tag.lower()
        for tag in configured_auto_timer_tags(config)
        if str(tag or "").strip()
    }
    return bool(wanted_tags and (_card_tags(card) & wanted_tags))


def auto_start_timer_for_card(card) -> bool:
    """Start the toolbar timer for a matching card if it is currently idle."""
    if _timer_running or not card_matches_auto_timer_config(card):
        return False
    widget = _timer_widget
    if widget is None:
        return False
    try:
        widget.start_if_idle(configured_auto_timer_minutes())
        return True
    except Exception:
        return False


def play_timer_completion_tone() -> None:
    """Play a lightweight completion tone when the focus timer finishes."""
    if not configured_timer_completion_beep_enabled():
        return
    try:
        QApplication.beep()
    except Exception:
        pass


def finish_timer(widget) -> None:
    """Finalize timer state, play the completion tone, and show the summary."""
    widget._qt_timer.stop()
    widget._running = False
    widget._start_btn.setText("▶  Start")
    _timer_running_set(False)
    play_timer_completion_tone()
    QTimer.singleShot(0, show_timer_summary)


# ── Timer widget ──────────────────────────────────────────────────────────────

class _TimerWidget(QWidget):
    """Compact focus timer embedded in the Anki toolbar (never overlaps cards)."""

    _PRESETS = [5, 10, 15, 25, 30, 45, 60]
    _NORMAL_SS = (
        "QLabel { font-size: 18px; font-weight: bold; font-family: monospace;"
        " min-width: 72px; qproperty-alignment: AlignCenter; }"
    )
    _URGENT_SS = (
        "QLabel { font-size: 18px; font-weight: bold; font-family: monospace;"
        " min-width: 72px; color: #ff4444; qproperty-alignment: AlignCenter; }"
    )
    _PRESET_SS = (
        "QPushButton { padding: 2px 7px; border-radius: 3px; }"
        " QPushButton:checked { color: #ff8c00; font-weight: bold; }"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sel = 30
        self._rem = 30 * 60
        self._running = False
        self._qt_timer = QTimer(self)
        self._qt_timer.setInterval(1000)
        self._qt_timer.timeout.connect(self._tick)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 2, 10, 2)
        row.setSpacing(5)

        self._preset_btns: dict[int, QPushButton] = {}
        for m in self._PRESETS:
            b = QPushButton(str(m))
            b.setCheckable(True)
            b.setFixedHeight(22)
            b.setStyleSheet(self._PRESET_SS)
            b.clicked.connect(lambda _, mins=m: self._pick(mins))
            row.addWidget(b)
            self._preset_btns[m] = b

        row.addSpacing(8)

        self._display = QLabel("30:00")
        self._display.setStyleSheet(self._NORMAL_SS)
        row.addWidget(self._display)

        row.addSpacing(4)

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.setFixedHeight(22)
        self._start_btn.clicked.connect(self._toggle)
        row.addWidget(self._start_btn)

        reset_btn = QPushButton("↺")
        reset_btn.setFixedHeight(22)
        reset_btn.setFixedWidth(26)
        reset_btn.setToolTip("Reset timer (double-click display also resets)")
        reset_btn.clicked.connect(self._reset)
        row.addWidget(reset_btn)

        self._display.mouseDoubleClickEvent = lambda _: self._reset()
        self._pick(30, init=True)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _fmt(self, s: int) -> str:
        return f"{s // 60:02d}:{s % 60:02d}"

    def _render(self) -> None:
        self._display.setText(self._fmt(self._rem))
        urgent = self._running and self._rem <= 60
        self._display.setStyleSheet(self._URGENT_SS if urgent else self._NORMAL_SS)

    def _pick(self, mins: int, init: bool = False) -> None:
        if self._running and not init:
            return
        self._sel = mins
        self._rem = mins * 60
        for m, b in self._preset_btns.items():
            b.setChecked(m == mins)
        self._render()

    # ── actions ───────────────────────────────────────────────────────────────

    def _toggle(self) -> None:
        if self._running:
            self._pause()
        else:
            self._start()

    def _start(self) -> None:
        if self._rem <= 0:
            self._rem = self._sel * 60
        self._running = True
        self._start_btn.setText("⏸  Pause")
        self._render()
        self._begin_session()
        self._qt_timer.start()

    def start_if_idle(self, mins: int | None = None) -> None:
        if not self._running:
            if mins is not None:
                try:
                    self._pick(max(1, min(1440, int(mins))))
                except Exception:
                    pass
            self._start()

    def _pause(self) -> None:
        self._qt_timer.stop()
        self._running = False
        self._start_btn.setText("▶  Resume")
        self._render()
        _timer_running_set(False)

    def _reset(self) -> None:
        self._qt_timer.stop()
        self._running = False
        self._rem = self._sel * 60
        self._start_btn.setText("▶  Start")
        self._render()
        _timer_running_set(False)
        reset_activity_counters()

    def _tick(self) -> None:
        self._rem = max(0, self._rem - 1)
        self._render()
        if self._rem == 0:
            finish_timer(self)

    # ── session state helpers (write to module globals) ───────────────────────

    def _begin_session(self) -> None:
        begin_timer_session(self._sel)


# ── Summary dialog ────────────────────────────────────────────────────────────

def show_timer_summary() -> None:
    """Show the end-of-timer summary dialog."""
    dur   = _timer_duration_min
    cards = _timer_cards_answered
    pdf_pages = set(_timer_pdf_pages)
    epub_pages = set(_timer_epub_pages)
    reset_activity_counters()

    dlg = QDialog(mw)
    dlg.setWindowTitle("Session Complete")
    dlg.setMinimumWidth(320)

    layout = QVBoxLayout(dlg)
    layout.setSpacing(14)
    layout.setContentsMargins(24, 24, 24, 20)

    title_lbl = QLabel(f"⏱  {dur}-minute session complete")
    title_lbl.setStyleSheet("font-size: 17px; font-weight: bold;")
    layout.addWidget(title_lbl)

    cards_lbl = QLabel(f"<b>{cards}</b> card{'s' if cards != 1 else ''} reviewed")
    cards_lbl.setStyleSheet("font-size: 14px;")
    layout.addWidget(cards_lbl)

    if pdf_pages:
        by_pdf: dict[int, set] = {}
        for cid, page in pdf_pages:
            by_pdf.setdefault(cid, set()).add(page)
        total_pages = sum(len(v) for v in by_pdf.values())
        n_pdfs = len(by_pdf)
        pdf_lbl = QLabel(
            f"<b>{total_pages}</b> PDF page{'s' if total_pages != 1 else ''} read"
            f" across {n_pdfs} book{'s' if n_pdfs != 1 else ''}"
        )
        pdf_lbl.setStyleSheet("font-size: 14px;")
        layout.addWidget(pdf_lbl)

    if epub_pages:
        by_epub: dict[int, set] = {}
        for cid, page in epub_pages:
            by_epub.setdefault(cid, set()).add(page)
        total_pages = sum(len(v) for v in by_epub.values())
        n_epubs = len(by_epub)
        epub_lbl = QLabel(
            f"<b>{total_pages}</b> EPUB page{'s' if total_pages != 1 else ''} read"
            f" across {n_epubs} book{'s' if n_epubs != 1 else ''}"
        )
        epub_lbl.setStyleSheet("font-size: 14px;")
        layout.addWidget(epub_lbl)

    layout.addSpacing(4)

    ok_btn = QPushButton("Done")
    ok_btn.setStyleSheet(
        "QPushButton { background: #2979ff; color: white; border: none;"
        " padding: 9px; font-size: 14px; border-radius: 4px; }"
        " QPushButton:hover { background: #1565c0; }"
    )
    ok_btn.clicked.connect(dlg.accept)
    layout.addWidget(ok_btn)

    dlg.exec()


# ── Reviewer hooks ────────────────────────────────────────────────────────────

def on_timer_question_shown(card) -> None:
    """Records the current PDF page for timer stats."""
    if card is None:
        return
    auto_start_timer_for_card(card)
    try:
        try:
            from ..backend.pdf_manager import PDF_NOTE_TYPE, get_page
            from ..backend.paths import get_active_profile as _active_profile
        except Exception:
            from pdf_manager import PDF_NOTE_TYPE, get_page
            from paths import get_active_profile as _active_profile
        note  = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        if model and model.get("name") == PDF_NOTE_TYPE:
            page = get_page(_ADDON_DIR, _active_profile(), card.id)
            record_pdf_page_read(card.id, page)
    except Exception:
        pass


def timer_on_card_answered(reviewer, card, ease: int) -> None:
    """Global hook: counts every answered card for the next timer report."""
    record_card_answered()


# ── Toolbar construction ──────────────────────────────────────────────────────

def build_timer_toolbar(timer_toggle_action) -> None:
    """Create and dock the focus timer toolbar; restore saved visibility.

    Called from __init__.py via gui_hooks.main_window_did_init.
    timer_toggle_action is the QAction in the Incremento menu — passed in to
    avoid importing __init__ from here (which would be circular).
    """
    global _timer_toolbar, _timer_widget
    tb = QToolBar("Focus Timer", mw)
    tb.setObjectName("incremento_timer_toolbar")
    tb.setMovable(False)
    tb.setFloatable(False)
    spacer = QWidget(tb)
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    tb.addWidget(spacer)
    _timer_widget = _TimerWidget(tb)
    tb.addWidget(_timer_widget)
    mw.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
    _timer_toolbar = tb

    # Restore saved visibility and sync the menu action checkmark
    _addon_pkg = __name__.split(".")[0]   # "incremento"
    cfg = mw.addonManager.getConfig(_addon_pkg) or {}
    visible = cfg.get("show_timer", True)
    tb.setVisible(visible)
    timer_toggle_action.setChecked(visible)
