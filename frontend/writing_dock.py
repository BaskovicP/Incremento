"""
writing_dock.py — Markdown writing dock with autosave and editor tools.

Shows a QTextEdit for Incremento Writing cards, writes markdown changes
to user_files/writing/<file>.md while typing, and remembers per-card
editor state such as cursor, scroll, zoom, wrap mode, and bookmark line.
"""

import datetime
import os
import re
from html import escape
from urllib.parse import quote, urlencode

from aqt import mw
from aqt.qt import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QBoxLayout,
    QFrame,
    QSizePolicy,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QTextBrowser,
    QSplitter,
    Qt,
    qconnect,
    QTimer,
    QTextCursor,
    QTextFormat,
    QTextOption,
    QShortcut,
    QScrollArea,
    QCheckBox,
    QFileDialog,
    QInputDialog,
    QMenu,
    QToolButton,
    QSaveFile,
    QIODevice,
    QTextDocument,
    QTabBar,
    QSignalBlocker,
    QEvent,
    QStyleFactory,
)
from aqt.utils import askUser, showInfo, tooltip
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QFontDatabase, QColor, QPalette, QTextCharFormat, QKeySequence

try:
    from ..backend.snapshot_writer import OrderedWriter
    from ..backend.i18n import format_date, t
    from .selection_search import install_selection_search_menu
    from ..backend.writing_links import marker as _excerpt_marker, sync_links as _sync_excerpt_links
    from ..backend.writing_links import strip_markers as _strip_excerpt_markers
    from ..backend.content_safety import external_plain_text_to_markdown
except ImportError:
    from snapshot_writer import OrderedWriter
    from backend.i18n import format_date, t  # type: ignore
    from frontend.selection_search import install_selection_search_menu
    from backend.writing_links import marker as _excerpt_marker, sync_links as _sync_excerpt_links
    from backend.writing_links import strip_markers as _strip_excerpt_markers
    from backend.content_safety import external_plain_text_to_markdown

try:
    from ..backend import paths as _paths
    from ..backend.config_service import load_addon_config
    from ..backend.workspace_layouts import MAX_WRITING_TABS as _MAX_WRITING_TABS
    from .file_shell import reveal_local_file
    from ..backend.db import (
        get_writing_progress,
        get_writing_word_stats,
        set_writing_progress,
        set_writing_word_stats,
    )
    from ..backend.writing_manager import (
        WRITING_NOTE_TYPE,
        WRITING_FILE_FIELD,
        ensure_writing_note_type,
        get_writing_dir,
        build_writing_relpath,
        ensure_writing_file,
        list_writing_backups,
        normalize_writing_backup_tiers,
        read_writing_text,
        restore_writing_backup,
        write_writing_text,
    )
    from ..backend.reader_bookmarks import (
        add_reader_bookmark,
        delete_reader_bookmark,
        list_reader_bookmarks,
    )
except ImportError:
    from config_service import load_addon_config  # type: ignore
    from workspace_layouts import MAX_WRITING_TABS as _MAX_WRITING_TABS
    import paths as _paths
    from file_shell import reveal_local_file  # type: ignore
    from db import (
        get_writing_progress,
        get_writing_word_stats,
        set_writing_progress,
        set_writing_word_stats,
    )
    from writing_manager import (
        WRITING_NOTE_TYPE,
        WRITING_FILE_FIELD,
        ensure_writing_note_type,
        get_writing_dir,
        build_writing_relpath,
        ensure_writing_file,
        list_writing_backups,
        normalize_writing_backup_tiers,
        read_writing_text,
        restore_writing_backup,
        write_writing_text,
    )
    from reader_bookmarks import add_reader_bookmark, delete_reader_bookmark, list_reader_bookmarks  # type: ignore

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_ADDON_PKG = __name__.split(".")[0] if "." in __name__ else "incremento"

_writing_dock = None
_writing_keep_open = False
_writing_profile = None
_current_writing_card_id: int | None = None
_current_writing_relpath: str = ""
_loading_editor = False
_autosave_timer = None
_state_save_timer = None
_writing_session_baseline_words = 0
_writing_current_word_count = 0
_writing_writer = None
_writing_save_serial = 0
_writing_saved_snapshot = None
_writing_saved_progress = None
_writing_persisted_state = {}
_writing_tab_actions = {}

_DEFAULT_FONT_SCALE = 1.0
_MIN_FONT_SCALE = 0.7
_MAX_FONT_SCALE = 2.4
_WRITING_PROGRESS_SCOPES = ("today", "session", "all_time")
_WRITING_WORD_COUNT_MODES = ("simple", "word_like")
_DEFAULT_WRITING_BACKUP_TIERS = ("1m", "30m", "1d")
_WORD_LIKE_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[’'`-][A-Za-z0-9]+)*", re.UNICODE)


def _active_profile() -> str:
    try:
        return str(_paths.get_active_profile() or "Default")
    except Exception:
        return "Default"


def _config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        return load_addon_config(mw.addonManager, _ADDON_PKG)
    except Exception:
        return {}


def configured_writing_wrap_enabled(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_wrap_enabled", True))


def configured_writing_focus_mode(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_focus_mode", False))


def configured_writing_preview_visible(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_preview_visible", True))


def configured_writing_highlight_current_line(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_highlight_current_line", True))


def configured_writing_restore_bookmark(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_restore_bookmark", True))


def configured_writing_backups_enabled(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_backups_enabled", True))


def configured_writing_backup_tiers(config: dict | None = None) -> tuple[str, ...]:
    cfg = _config(config)
    normalized = normalize_writing_backup_tiers(cfg.get("writing_backup_tiers"))
    return normalized or _DEFAULT_WRITING_BACKUP_TIERS


def configured_writing_progress_visible(config: dict | None = None) -> bool:
    return bool(_config(config).get("writing_progress_visible", True))


def configured_writing_progress_default_scope(config: dict | None = None) -> str:
    raw = str(_config(config).get("writing_progress_default_scope", "today") or "").strip().lower()
    return raw if raw in _WRITING_PROGRESS_SCOPES else "today"


def configured_writing_word_count_mode(config: dict | None = None) -> str:
    raw = str(_config(config).get("writing_word_count_mode", "simple") or "").strip().lower()
    return raw if raw in _WRITING_WORD_COUNT_MODES else "simple"


def _clamp_font_scale(value) -> float:
    try:
        scale = float(value)
    except Exception:
        scale = _DEFAULT_FONT_SCALE
    return max(_MIN_FONT_SCALE, min(_MAX_FONT_SCALE, scale))


def _normalize_selection_text(text: str | None) -> str:
    return str(text or "").replace("\u2029", "\n")


def _logical_today_text() -> str:
    return datetime.date.today().isoformat()


def _count_words_simple(text: str | None) -> int:
    body = str(text or "").strip()
    if not body:
        return 0
    return len([token for token in body.split() if token.strip()])


def _count_words_word_like(text: str | None) -> int:
    body = str(text or "")
    if not body.strip():
        return 0
    return len(_WORD_LIKE_TOKEN_RE.findall(body))


def _count_words(text: str | None, mode: str | None = None) -> int:
    text = _strip_excerpt_markers(str(text or ''))
    resolved_mode = str(mode or configured_writing_word_count_mode()).strip().lower()
    if resolved_mode == "word_like":
        return _count_words_word_like(text)
    return _count_words_simple(text)


def _scope_label(scope: str) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized == "session":
        return t("writing_words_session")
    if normalized == "all_time":
        return t("writing_words_total")
    return t("writing_words_today")


def _current_progress_scope() -> str:
    if _writing_dock is None:
        return configured_writing_progress_default_scope()
    try:
        raw = str(_writing_dock._progress_scope_combo.currentData() or "").strip().lower()
    except Exception:
        raw = ""
    return raw if raw in _WRITING_PROGRESS_SCOPES else configured_writing_progress_default_scope()


def _update_progress_display() -> None:
    if _writing_dock is None:
        return
    try:
        visible = bool(getattr(_writing_dock, "_progress_visible", True))
        _writing_dock._progress_scope_label.setVisible(False)
        _writing_dock._progress_scope_combo.setVisible(visible)
        _writing_dock._progress_value_lbl.setVisible(visible)
        if not visible:
            return
        today_total = max(
            0,
            int(getattr(_writing_dock, "_current_word_count", 0))
            - int(getattr(_writing_dock, "_daily_baseline_words", 0)),
        )
        session_total = max(
            0,
            int(getattr(_writing_dock, "_current_word_count", 0))
            - int(getattr(_writing_dock, "_session_baseline_words", 0)),
        )
        all_time_total = max(0, int(getattr(_writing_dock, "_current_word_count", 0)))
        scope = _current_progress_scope()
        if scope == "session":
            count = session_total
        elif scope == "all_time":
            count = all_time_total
        else:
            count = today_total
        _writing_dock._progress_value_lbl.setText(t("writing_scope_count", scope=_scope_label(scope), count=count))
    except Exception:
        pass


def _wrap_selection_text(text: str, prefix: str, suffix: str, placeholder: str) -> str:
    body = _normalize_selection_text(text).strip("\n")
    if not body:
        body = placeholder
    return f"{prefix}{body}{suffix}"


def _prefix_lines_text(text: str, prefix: str, placeholder: str) -> str:
    body = _normalize_selection_text(text)
    if not body.strip():
        return f"{prefix}{placeholder}"
    lines = body.splitlines()
    if not lines:
        lines = [placeholder]
    return "\n".join(f"{prefix}{line}" if line else prefix.rstrip() for line in lines)


def current_writing_card_id() -> int | None:
    try:
        return int(_current_writing_card_id) if _current_writing_card_id is not None else None
    except Exception:
        return None


def insert_linked_excerpt(source, anchor, *, cursor=None) -> bool:
    if _writing_dock is None or _writing_profile != _active_profile():
        return False
    cursor = QTextCursor(cursor or _writing_dock._editor.textCursor())
    if cursor.document() is not _writing_dock._editor.document():
        return False
    cursor.clearSelection()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.beginEditBlock()
    cursor.insertText('\n\n' + _excerpt_marker(anchor, start=True) + '\n'
                      + external_plain_text_to_markdown(source['quote'], max_chars=2000)
                      + '\n' + _excerpt_marker(anchor) + '\n\n')
    cursor.endEditBlock()
    _writing_dock._editor.setTextCursor(cursor)
    _writing_dock._editor.ensureCursorVisible()
    jump_to_excerpt(anchor, focus=False)
    return True


def jump_to_excerpt(anchor, *, focus=True) -> bool:
    if _writing_dock is None or _writing_profile != _active_profile():
        return False
    cursor = _writing_dock._editor.document().find(_excerpt_marker(anchor))
    if cursor.isNull():
        tooltip(t('writing_excerpt_missing'), parent=_writing_dock)
        return False
    end = max(0, cursor.selectionStart() - 1)
    start = cursor.document().find(_excerpt_marker(anchor, start=True))
    if start.isNull():
        # End-only anchors from earlier versions still navigate to their paragraph.
        cursor.setPosition(max(0, end))
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        beginning = cursor.position()
    else:
        beginning = min(start.selectionEnd() + 1, end)
    cursor.setPosition(min(beginning, end))
    _writing_dock._editor.setTextCursor(cursor)
    _writing_dock._editor.ensureCursorVisible()
    if focus:
        _writing_dock._editor.setFocus()
    cursor.setPosition(max(beginning, end), QTextCursor.MoveMode.KeepAnchor)
    _writing_dock._editor.reveal_excerpt(cursor)
    return True


def open_writing_card_ids() -> list[int]:
    """Include inactive tabs: their live editors must also block external edits."""
    if _writing_profile is not None and _writing_profile != _active_profile():
        return []
    tabs = getattr(_writing_dock, "_writing_tabs", None)
    if tabs is not None:
        return [int(tabs.tabData(index)) for index in range(tabs.count())]
    current = current_writing_card_id()
    return [current] if current is not None else []


def configure_writing_tab_actions(*, open_existing, new_writing, open_card=None) -> None:
    _writing_tab_actions.update(open_existing=open_existing, new_writing=new_writing, open_card=open_card)


def reorder_writing_tabs(card_ids: list[int]) -> None:
    if _writing_dock is None or _writing_profile != _active_profile():
        return
    tabs = _writing_dock._writing_tabs
    with QSignalBlocker(tabs):
        for position, card_id in enumerate(card_ids):
            index = next((i for i in range(tabs.count()) if tabs.tabData(i) == card_id), -1)
            if index >= 0:
                tabs.moveTab(index, position)


def _stash_writing_tab() -> None:
    if _writing_dock is None or _current_writing_card_id is None:
        return
    dock = _writing_dock
    document = dock._editor.document()
    previous = dock._open_writing_tabs.get(int(_current_writing_card_id))
    if previous is not None and previous['document'] is not document:
        previous['document'].deleteLater()
    # QTextEdit otherwise owns and deletes its previous document on setDocument().
    document.setParent(dock)
    dock._open_writing_tabs[int(_current_writing_card_id)] = dict(
        card_id=int(_current_writing_card_id), relpath=_current_writing_relpath,
        title=dock._title_lbl.text(), document=document, cursor=dock._editor.textCursor(),
        progress=_capture_writing_progress(), scope=_current_progress_scope(),
        session_baseline=dock._session_baseline_words,
        words=_count_words(dock._editor.toPlainText()),
        day=dock._daily_logical_date, daily_baseline=dock._daily_baseline_words,
        saved=dock._saved_lbl.text())
    tabs = dock._writing_tabs
    index = next((i for i in range(tabs.count()) if tabs.tabData(i) == _current_writing_card_id), -1)
    with QSignalBlocker(tabs):
        if index < 0:
            index = tabs.addTab(dock._title_lbl.text())
            tabs.setTabData(index, int(_current_writing_card_id))
        tabs.setTabText(index, dock._title_lbl.text())
        tabs.setTabToolTip(index, dock._title_lbl.text())
        tabs.setCurrentIndex(index)
    # The row was first laid out while empty; native macOS keeps that zero height.
    tabs.setMinimumHeight(tabs.sizeHint().height())


def _activate_writing_tab(state: dict) -> None:
    global _current_writing_card_id, _current_writing_relpath, _loading_editor
    global _writing_session_baseline_words, _writing_current_word_count
    dock = _writing_dock
    _current_writing_card_id, _current_writing_relpath = state['card_id'], state['relpath']
    _writing_session_baseline_words, _writing_current_word_count = state['session_baseline'], state['words']
    progress = state['progress']
    _loading_editor = True
    try:
        dock._editor.setDocument(state['document'])
        dock._title_lbl.setText(state['title'])
        dock._file_lbl.setText(state['relpath'])
        dock._session_baseline_words, dock._current_word_count = state['session_baseline'], state['words']
        dock._daily_logical_date, dock._daily_baseline_words = state['day'], state['daily_baseline']
        dock._progress_scope_combo.setCurrentIndex(dock._progress_scope_combo.findData(state['scope']))
        _apply_font_scale(progress['font_scale'])
        _apply_wrap_mode(progress['wrap_enabled'])
        _apply_focus_mode(progress['focus_mode'])
        _apply_preview_visibility(progress['preview_visible'])
        _apply_current_line_highlight(progress['highlight_current_line'])
        _restore_editor_progress(progress)
        dock._editor.setTextCursor(state['cursor'])
        _refresh_markdown_preview()
        dock._saved_lbl.setText(state['saved'])
    finally:
        _loading_editor = False
    with QSignalBlocker(dock._writing_tabs):
        for index in range(dock._writing_tabs.count()):
            if dock._writing_tabs.tabData(index) == state['card_id']:
                dock._writing_tabs.setCurrentIndex(index)
                break
    _update_editor_highlights()
    _refresh_writing_bookmarks_panel()
    dock._source_margin.reload()
    _set_status(t("writing_autosave_on_typing"))
    if state['saved']:
        dock._saved_lbl.show()
        dock._status_lbl.hide()


def _on_writing_tab_changed(index: int) -> None:
    if _loading_editor or _writing_dock is None or index < 0:
        return
    dock = _writing_dock
    state = dock._open_writing_tabs.get(dock._writing_tabs.tabData(index))
    if state is not None:
        show_writing_in_dock(state['card_id'], state['title'], state['relpath'])
    if _current_writing_card_id != dock._writing_tabs.tabData(index):
        with QSignalBlocker(dock._writing_tabs):
            for previous in range(dock._writing_tabs.count()):
                if dock._writing_tabs.tabData(previous) == _current_writing_card_id:
                    dock._writing_tabs.setCurrentIndex(previous)
                    break


def _close_writing_tab(index: int) -> None:
    global _current_writing_card_id, _current_writing_relpath, _loading_editor
    if _writing_dock is None or _writing_profile != _active_profile():
        return
    dock, tabs = _writing_dock, _writing_dock._writing_tabs
    if not 0 <= index < tabs.count():
        return
    card_id = tabs.tabData(index)
    active = card_id == _current_writing_card_id
    if active and not _flush_editor_state():
        return
    state = dock._open_writing_tabs.pop(card_id)
    with QSignalBlocker(tabs):
        tabs.removeTab(index)
    if active:
        if tabs.count():
            _activate_writing_tab(dock._open_writing_tabs[tabs.tabData(tabs.currentIndex())])
        else:
            _current_writing_card_id, _current_writing_relpath = None, ""
            _loading_editor = True
            try:
                dock._editor.setDocument(QTextDocument(dock))
                dock._preview.clear()
            finally:
                _loading_editor = False
            set_keep_open(False)
            dock.hide()
    state['document'].deleteLater()


def _refresh_markdown_preview(text: str | None = None) -> None:
    if _writing_dock is None:
        return
    if not bool(getattr(_writing_dock, "_preview_visible", True)):
        return
    preview = getattr(_writing_dock, "_preview", None)
    editor = getattr(_writing_dock, "_editor", None)
    if preview is None or editor is None:
        return
    md = editor.toPlainText() if text is None else str(text)
    md = _writing_dock._source_margin.preview_markdown(md)
    try:
        preview.setMarkdown(md)
        _writing_dock._source_margin.style_preview()
    except Exception:
        preview.setPlainText(md)


def _set_status(text: str) -> None:
    if _writing_dock is None:
        return
    try:
        _writing_dock._status_lbl.setText(text)
        _writing_dock._status_lbl.show()
        _writing_dock._saved_lbl.hide()
    except Exception:
        pass


def _set_saved_time() -> None:
    if _writing_dock is None:
        return
    now_txt = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        _writing_dock._saved_lbl.setText(t("writing_saved", time=now_txt))
        _writing_dock._saved_lbl.show()
        _writing_dock._status_lbl.hide()
    except Exception:
        pass


def _format_backup_timestamp(value) -> str:
    try:
        timestamp = datetime.datetime.fromtimestamp(float(value))
        return f"{format_date(timestamp)} {timestamp.strftime('%H:%M:%S')}"
    except Exception:
        return t("writing_unknown_time")


def _current_scroll_ratio() -> float:
    if _writing_dock is None:
        return 0.0
    try:
        scroll = _writing_dock._editor.verticalScrollBar()
        maximum = int(scroll.maximum() or 0)
        if maximum <= 0:
            return 0.0
        return max(0.0, min(float(scroll.value()) / float(maximum), 1.0))
    except Exception:
        return 0.0


def _line_column_text() -> str:
    if _writing_dock is None:
        return t("writing_line_column", line=1, column=1)
    try:
        cursor = _writing_dock._editor.textCursor()
        return t("writing_line_column", line=cursor.blockNumber() + 1, column=cursor.positionInBlock() + 1)
    except Exception:
        return t("writing_line_column", line=1, column=1)


def _bookmark_line_number() -> int | None:
    if _writing_dock is None:
        return None
    try:
        block = int(getattr(_writing_dock, "_bookmark_block_number", -1))
    except Exception:
        block = -1
    return None if block < 0 else (block + 1)


def _update_status_details() -> None:
    if _writing_dock is None:
        return
    try:
        zoom_percent = int(round(float(getattr(_writing_dock, "_font_scale", _DEFAULT_FONT_SCALE)) * 100.0))
        bookmark_line = _bookmark_line_number()
        bookmark_txt = t("writing_marker_line", line=bookmark_line) if bookmark_line is not None else t("writing_marker_off")
        wrap_txt = t("writing_wrap_on") if bool(getattr(_writing_dock, "_wrap_enabled", True)) else t("writing_wrap_off")
        details = t("writing_status_details", location=_line_column_text(), zoom=zoom_percent, marker=bookmark_txt, wrap=wrap_txt)
        _writing_dock._detail_lbl.setText(details)
        _writing_dock._status_lbl.setToolTip(details)
        _writing_dock._saved_lbl.setToolTip(details)
    except Exception:
        pass
    _update_progress_display()


def _apply_font_scale(scale: float) -> None:
    if _writing_dock is None:
        return
    clamped = _clamp_font_scale(scale)
    _writing_dock._font_scale = clamped
    try:
        font = QFont(getattr(_writing_dock, "_base_font"))
        base_size = float(getattr(_writing_dock, "_base_font_size", 12.0))
        font.setPointSizeF(max(7.0, base_size * clamped))
        _writing_dock._editor.setFont(font)
        _writing_dock._editor.document().setDefaultFont(font)
    except Exception:
        pass
    _update_status_details()


def _apply_wrap_mode(enabled: bool) -> None:
    if _writing_dock is None:
        return
    wrap_enabled = bool(enabled)
    _writing_dock._wrap_enabled = wrap_enabled
    try:
        mode = (
            QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
            if wrap_enabled
            else QTextOption.WrapMode.NoWrap
        )
        _writing_dock._editor.setWordWrapMode(mode)
        _writing_dock._editor.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth
            if wrap_enabled
            else QTextEdit.LineWrapMode.NoWrap
        )
        _writing_dock._wrap_btn.setChecked(wrap_enabled)
    except Exception:
        pass
    _update_status_details()


def _apply_focus_mode(enabled: bool) -> None:
    if _writing_dock is None:
        return
    focus_mode = bool(enabled)
    _writing_dock._focus_mode = focus_mode
    try:
        _writing_dock._focus_btn.setChecked(focus_mode)
        horizontal = _writing_dock._split.orientation() == Qt.Orientation.Horizontal
        _writing_dock._preview_host.setMaximumWidth(260 if focus_mode and horizontal else 16777215)
        _writing_dock._split.setSizes([860, 220] if focus_mode else [1, 1])
    except Exception:
        pass


def _apply_preview_visibility(visible: bool) -> None:
    if _writing_dock is None:
        return
    preview_visible = bool(visible)
    _writing_dock._preview_visible = preview_visible
    try:
        _writing_dock._preview_btn.setChecked(preview_visible)
        _writing_dock._preview_host.setVisible(preview_visible)
        if preview_visible:
            _apply_focus_mode(bool(getattr(_writing_dock, "_focus_mode", False)))
            _refresh_markdown_preview()
        else:
            _writing_dock._split.setSizes([1, 0])
    except Exception:
        pass


def _apply_current_line_highlight(enabled: bool) -> None:
    if _writing_dock is None:
        return
    _writing_dock._highlight_current_line = bool(enabled)
    try:
        _writing_dock._highlight_line_btn.setChecked(bool(enabled))
    except Exception:
        pass
    _update_editor_highlights()


def _make_full_width_selection(block_number: int, color: QColor):
    if _writing_dock is None or block_number < 0:
        return None
    try:
        document = _writing_dock._editor.document()
        block = document.findBlockByNumber(block_number)
        if not block.isValid():
            return None
        selection = QTextEdit.ExtraSelection()
        cursor = QTextCursor(block)
        selection.cursor = cursor
        selection.format = QTextCharFormat()
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        return selection
    except Exception:
        return None


def _update_editor_highlights() -> None:
    if _writing_dock is None:
        return
    selections = []
    try:
        if bool(getattr(_writing_dock, "_highlight_current_line", True)):
            current_selection = _make_full_width_selection(
                _writing_dock._editor.textCursor().blockNumber(),
                QColor(64, 96, 140, 70),
            )
            if current_selection is not None:
                selections.append(current_selection)
        bookmark_block = int(getattr(_writing_dock, "_bookmark_block_number", -1))
        if bookmark_block >= 0:
            bookmark_selection = _make_full_width_selection(
                bookmark_block,
                QColor(240, 190, 80, 95),
            )
            if bookmark_selection is not None:
                selections.append(bookmark_selection)
        excerpt = getattr(_writing_dock._editor, '_excerpt_selection', None)
        if excerpt is not None and excerpt.cursor.document() is _writing_dock._editor.document():
            selections.append(excerpt)
        _writing_dock._editor.setExtraSelections(selections)
    except Exception:
        pass
    _update_status_details()


def _schedule_state_save() -> None:
    if _writing_dock is None or _loading_editor or not _current_writing_relpath:
        return
    if _state_save_timer is not None:
        _state_save_timer.start()


def _capture_writing_progress() -> dict | None:
    if _writing_dock is None or _current_writing_card_id is None:
        return None
    cursor = _writing_dock._editor.textCursor()
    return dict(cursor_position=int(cursor.position()), scroll_ratio=_current_scroll_ratio(),
        font_scale=float(getattr(_writing_dock, "_font_scale", _DEFAULT_FONT_SCALE)),
        wrap_enabled=bool(getattr(_writing_dock, "_wrap_enabled", True)),
        focus_mode=bool(getattr(_writing_dock, "_focus_mode", False)),
        preview_visible=bool(getattr(_writing_dock, "_preview_visible", True)),
        highlight_current_line=bool(getattr(_writing_dock, "_highlight_current_line", True)),
        bookmark_block_number=int(getattr(_writing_dock, "_bookmark_block_number", -1)))


def _save_writing_progress() -> None:
    if not _loading_editor:
        _autosave_from_editor()


def _sync_writing_word_stats(*, text: str | None = None) -> None:
    global _writing_current_word_count
    if _writing_dock is None or _current_writing_card_id is None:
        return
    try:
        current_words = _count_words(
            _writing_dock._editor.toPlainText() if text is None else text
        )
        _writing_current_word_count = current_words
        _writing_dock._current_word_count = current_words
        today_key = _logical_today_text()
        stored_day = str(getattr(_writing_dock, "_daily_logical_date", "") or "").strip()
        stored_baseline = max(0, int(getattr(_writing_dock, "_daily_baseline_words", 0)))
        if stored_day != today_key:
            stored_day = today_key
            stored_baseline = current_words
        _writing_dock._daily_logical_date = stored_day
        _writing_dock._daily_baseline_words = stored_baseline
        set_writing_word_stats(
            _ADDON_DIR,
            _active_profile(),
            int(_current_writing_card_id),
            current_word_count=current_words,
            daily_logical_date=stored_day,
            daily_baseline_words=stored_baseline,
        )
    except Exception:
        pass
    _update_progress_display()


def _write_writing_snapshot(snapshot):
    global _writing_persisted_state
    profile, card_id, relpath, text, cfg, today, baseline_day, baseline, progress, serial = snapshot
    identity = (profile, card_id, relpath)
    previous = _writing_persisted_state if _writing_persisted_state.get("identity") == identity else {}
    changed_text = previous.get("text") != text
    if changed_text:
        write_writing_text(_ADDON_DIR, relpath, text, profile=profile,
                           backups_enabled=configured_writing_backups_enabled(cfg),
                           backup_tiers=configured_writing_backup_tiers(cfg))
        if card_id is not None:
            _sync_excerpt_links(_ADDON_DIR, profile, int(card_id), text)
    word_mode = configured_writing_word_count_mode(cfg)
    changed_count = changed_text or previous.get("word_mode") != word_mode
    words = _count_words(text, word_mode) if changed_count else previous["words"]
    if previous.get("day") == today:
        baseline = previous["baseline"]
    elif today != baseline_day:
        baseline = words
    if card_id is not None and (changed_count or previous.get("day") != today):
        set_writing_word_stats(_ADDON_DIR, profile, int(card_id), current_word_count=words,
                               daily_logical_date=today, daily_baseline_words=baseline)
    if card_id is not None and progress is not None and previous.get("progress") != progress:
        set_writing_progress(_ADDON_DIR, profile, int(card_id), **progress)
    _writing_persisted_state = {"identity": identity, "text": text, "words": words,
                                "day": today, "baseline": baseline, "word_mode": word_mode, "progress": progress}
    return words, today, baseline


def _publish_writing_save(snapshot, result, error):
    def show():
        global _writing_saved_snapshot, _writing_current_word_count
        profile, card_id, relpath, text, *_ = snapshot
        if (_writing_dock is None or snapshot[-1] != _writing_save_serial
                or profile != _writing_profile or profile != _active_profile()
                or card_id != _current_writing_card_id or relpath != _current_writing_relpath):
            return
        if error is not None:
            _writing_dock._workspace_dirty = True
            _writing_dock._workspace_failed = True
            _set_status(t("writing_autosave_failed"))
            return
        previous_text = _writing_saved_snapshot[3] if _writing_saved_snapshot else ''
        anchors_changed = (re.findall(r'<!-- incremento-excerpt:[a-f0-9]{32} -->', previous_text)
                           != re.findall(r'<!-- incremento-excerpt:[a-f0-9]{32} -->', text))
        _writing_saved_snapshot = (profile, card_id, relpath, text)
        _writing_dock._workspace_dirty = False
        _writing_dock._workspace_failed = False
        words, today, baseline = result
        _writing_current_word_count = words
        _writing_dock._current_word_count = words
        _writing_dock._daily_logical_date = today
        _writing_dock._daily_baseline_words = baseline
        _set_status(t("writing_autosave_on_typing"))
        _set_saved_time()
        _update_progress_display()
        if anchors_changed:
            _writing_dock._source_margin.reload()
            try:
                from .writing_excerpt_ui import refresh_readers
            except ImportError:
                from frontend.writing_excerpt_ui import refresh_readers
            refresh_readers()
    taskman = getattr(mw, "taskman", None)
    if taskman is not None and hasattr(taskman, "run_on_main"):
        taskman.run_on_main(show)


def _autosave_from_editor(*, wait: bool = False, captured_profile: bool = False) -> bool:
    global _writing_writer, _writing_save_serial
    if (_writing_dock is None or not _current_writing_relpath
            or (not captured_profile and _writing_profile != _active_profile())):
        return False
    text = _writing_dock._editor.toPlainText()
    identity = (_writing_profile, _current_writing_card_id, _current_writing_relpath, text)
    if _writing_writer is None:
        _writing_writer = OrderedWriter(_write_writing_snapshot, _publish_writing_save)
    _writing_save_serial += 1
    try:
        progress = _capture_writing_progress()
    except Exception:
        progress = None
    snapshot = (*identity, _config(), _logical_today_text(),
                str(getattr(_writing_dock, "_daily_logical_date", "")),
                int(getattr(_writing_dock, "_daily_baseline_words", 0)), progress, _writing_save_serial)
    _writing_writer.submit(snapshot)
    if wait:
        try:
            _writing_writer.flush()
        except Exception:
            _set_status(t("writing_autosave_failed"))
            return False
    return True


def _flush_editor_state(*, captured_profile: bool = False) -> bool:
    if _autosave_timer is not None:
        _autosave_timer.stop()
    if _state_save_timer is not None:
        _state_save_timer.stop()
    return _autosave_from_editor(wait=True, captured_profile=captured_profile)


def _restore_editor_progress(progress: dict) -> None:
    if _writing_dock is None:
        return
    editor = _writing_dock._editor
    document = editor.document()
    identity = _writing_identity()
    maximum_position = max(0, int(document.characterCount()) - 1)
    stored_position = max(0, min(int(progress.get("cursor_position", 0) or 0), maximum_position))

    cursor = editor.textCursor()
    cursor.setPosition(stored_position)
    editor.setTextCursor(cursor)

    max_block = max(0, int(document.blockCount()) - 1)
    bookmark_block = int(progress.get("bookmark_block_number", -1) or -1)
    if not configured_writing_restore_bookmark():
        bookmark_block = -1
    if bookmark_block > max_block:
        bookmark_block = max_block if max_block >= 0 else -1
    if bookmark_block < -1:
        bookmark_block = -1
    _writing_dock._bookmark_block_number = bookmark_block

    def _restore_scroll() -> None:
        if (not _writing_identity_is_current(identity)
                or _writing_dock._editor.document() is not document):
            return
        try:
            scroll = _writing_dock._editor.verticalScrollBar()
            maximum = int(scroll.maximum() or 0)
            ratio = max(0.0, min(float(progress.get("scroll_ratio", 0.0) or 0.0), 1.0))
            scroll.setValue(int(round(maximum * ratio)))
        except Exception:
            pass
        _update_editor_highlights()
        _update_status_details()

    QTimer.singleShot(0, _restore_scroll)


def _move_marker_to_cursor() -> None:
    if _writing_dock is None:
        return
    try:
        _writing_dock._bookmark_block_number = _writing_dock._editor.textCursor().blockNumber()
        _update_editor_highlights()
        _schedule_state_save()
    except Exception:
        pass


def _clear_marker() -> None:
    if _writing_dock is None:
        return
    _writing_dock._bookmark_block_number = -1
    _update_editor_highlights()
    _schedule_state_save()


def _jump_to_marker() -> None:
    if _writing_dock is None:
        return
    bookmark_block = int(getattr(_writing_dock, "_bookmark_block_number", -1))
    if bookmark_block < 0:
        tooltip(t("writing_no_marker"))
        return
    try:
        block = _writing_dock._editor.document().findBlockByNumber(bookmark_block)
        if not block.isValid():
            tooltip(t("writing_marker_unavailable"))
            return
        cursor = QTextCursor(block)
        _writing_dock._editor.setTextCursor(cursor)
        _writing_dock._editor.ensureCursorVisible()
        _update_editor_highlights()
        _schedule_state_save()
    except Exception:
        pass


def _writing_bookmarks() -> list[dict]:
    if _current_writing_card_id is None:
        return []
    try:
        return list_reader_bookmarks(
            _ADDON_DIR,
            _active_profile(),
            int(_current_writing_card_id),
            "writing",
        )
    except Exception:
        return []


def _refresh_writing_bookmarks_panel() -> None:
    if _writing_dock is None:
        return
    bookmarks = _writing_bookmarks()
    try:
        _writing_dock._bookmarks_btn.setText(t("writing_bookmarks_count", count=len(bookmarks)))
    except Exception:
        pass
    panel = getattr(_writing_dock, "_bookmarks_panel", None)
    if panel is None:
        return
    html = ["<div style='font-family:sans-serif;font-size:12px;line-height:1.45'>"]
    html.append(f"<b>{escape(t('reader_interesting_bookmarks'))}</b>")
    if bookmarks:
        html.append("<ul>")
        for bookmark in bookmarks:
            bookmark_id = escape(str(bookmark.get("id") or ""), quote=True)
            label = str(bookmark.get("label") or t("reader_bookmark"))
            safe_label = escape(label, quote=True)
            html.append(
                "<li>"
                f"{safe_label} "
                f"<a href='inc://writing-bookmark-open/{bookmark_id}'>{escape(t('reader_jump'))}</a> "
                f"<a href='inc://writing-bookmark-delete/{bookmark_id}' style='color:#c66'>{escape(t('reader_delete'))}</a>"
                "</li>"
            )
        html.append("</ul>")
    else:
        html.append(f"<div style='color:#888;padding:6px 0 0'>{escape(t('reader_no_bookmarks'))}</div>")
    html.append("</div>")
    panel.setHtml("".join(html))


def _add_current_writing_bookmark() -> None:
    if _writing_dock is None or _current_writing_card_id is None:
        return
    try:
        cursor = _writing_dock._editor.textCursor()
        add_reader_bookmark(
            _ADDON_DIR,
            _active_profile(),
            int(_current_writing_card_id),
            "writing",
            {
                "cursor_position": int(cursor.position()),
                "block_number": int(cursor.blockNumber()),
                "scroll_ratio": _current_scroll_ratio(),
            },
        )
    except Exception as exc:
        showInfo(t("writing_bookmark_save_failed", error=exc))
        return
    _refresh_writing_bookmarks_panel()
    try:
        _writing_dock._bookmarks_panel.setVisible(True)
    except Exception:
        pass
    tooltip(t("writing_bookmark_saved"))


def _toggle_writing_bookmarks_panel() -> None:
    if _writing_dock is None:
        return
    _refresh_writing_bookmarks_panel()
    try:
        _writing_dock._bookmarks_panel.setVisible(not _writing_dock._bookmarks_panel.isVisible())
    except Exception:
        pass


def _open_writing_bookmark_link(url: QUrl) -> None:
    if _writing_dock is None or _current_writing_card_id is None:
        return
    s = url.toString()
    bookmark_id = s.rsplit("/", 1)[-1]
    if s.startswith("inc://writing-bookmark-delete/"):
        try:
            delete_reader_bookmark(
                _ADDON_DIR,
                _active_profile(),
                int(_current_writing_card_id),
                "writing",
                bookmark_id,
            )
        except Exception as exc:
            showInfo(t("writing_bookmark_delete_failed", error=exc))
        _refresh_writing_bookmarks_panel()
        return
    if not s.startswith("inc://writing-bookmark-open/"):
        return
    bookmark = next((item for item in _writing_bookmarks() if str(item.get("id") or "") == bookmark_id), None)
    if not bookmark:
        return
    location = bookmark.get("location") or {}
    try:
        document = _writing_dock._editor.document()
        max_pos = max(0, int(document.characterCount()) - 1)
        cursor = _writing_dock._editor.textCursor()
        cursor.setPosition(max(0, min(int(location.get("cursor_position", 0) or 0), max_pos)))
        _writing_dock._editor.setTextCursor(cursor)
        _writing_dock._editor.ensureCursorVisible()
    except Exception:
        pass


def _apply_markdown_transform(kind: str) -> None:
    if _writing_dock is None:
        return
    editor = _writing_dock._editor
    cursor = editor.textCursor()
    selected = _normalize_selection_text(cursor.selectedText())

    if kind in {"h1", "h2", "h3", "paragraph"}:
        # Styles operate on complete blocks, including when only a word is selected.
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(max(start, end - 1))
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        end = cursor.position()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selected = _normalize_selection_text(cursor.selectedText())
        body = re.sub(r"(?m)^ {0,3}#{1,6} +", "", selected)
        prefix = "" if kind == "paragraph" else "#" * int(kind[1]) + " "
        replacement = body if kind == "paragraph" else _prefix_lines_text(body, prefix, t("writing_placeholder_heading"))
    elif kind == "bold":
        replacement = _wrap_selection_text(selected, "**", "**", t("writing_placeholder_bold"))
    elif kind == "italic":
        replacement = _wrap_selection_text(selected, "*", "*", t("writing_placeholder_italic"))
    elif kind == "strike":
        replacement = _wrap_selection_text(selected, "~~", "~~", t("writing_placeholder_text"))
    elif kind == "inline_code":
        body = selected or t("writing_placeholder_code")
        fence = "`" * (max((len(run) for run in re.findall(r"`+", body)), default=0) + 1)
        body = f" {body} " if body.startswith('`') or body.endswith('`') else body
        replacement = f"{fence}{body}{fence}"
    elif kind == "bullet":
        replacement = _prefix_lines_text(selected, "- ", t("writing_placeholder_list_item"))
    elif kind == "number":
        body = selected.strip()
        if not body:
            replacement = "1. " + t("writing_placeholder_list_item")
        else:
            lines = body.splitlines()
            replacement = "\n".join(f"{idx + 1}. {line}" if line else f"{idx + 1}." for idx, line in enumerate(lines))
    elif kind == "quote":
        replacement = _prefix_lines_text(selected, "> ", t("writing_placeholder_quote"))
    elif kind == "code":
        body = selected.strip("\n") or t("writing_placeholder_code")
        fence = "`" * max(3, max((len(run) for run in re.findall(r"`+", body)), default=0) + 1)
        replacement = f"\n\n{fence}\n{body}\n{fence}\n\n"
    elif kind == "rule":
        replacement = "\n\n---\n\n"
    elif kind == "table":
        heading = t("writing_placeholder_heading")
        cell = t("writing_placeholder_text")
        replacement = f"\n\n| {heading} | {heading} |\n| --- | --- |\n| {cell} | {cell} |\n\n"
    else:
        return

    cursor.beginEditBlock()
    try:
        cursor.insertText(replacement)
    finally:
        cursor.endEditBlock()
    editor.setTextCursor(cursor)
    editor.setFocus()


def _markdown_reference(label: str, target: str, *, image: bool = False) -> str:
    try:
        from ..backend.content_safety import normalize_external_http_url
    except ImportError:
        from content_safety import normalize_external_http_url
    if any(char in str(target) for char in '<>"'):
        raise ValueError("Invalid Markdown URL")
    url = normalize_external_http_url(target)
    try:
        url = quote(url, safe=":/?#[]@!$&'*+,;=%-._~")
    except UnicodeError as exc:
        raise ValueError("Invalid Markdown URL") from exc
    label = escape(_normalize_selection_text(label).replace("\n", " "), quote=False)
    label = re.sub(r"([\\`*_[\]])", r"\\\1", label)
    return f"{'!' if image else ''}[{label}](<{url}>)"


def _writing_identity() -> tuple:
    return (_writing_dock, _writing_profile, _current_writing_card_id, _current_writing_relpath)


def _writing_identity_is_current(identity: tuple) -> bool:
    return identity == _writing_identity() and identity[1] == _active_profile()


def _insert_writing_reference(*, image: bool = False) -> None:
    if _writing_dock is None:
        return
    identity = _writing_identity()
    editor = _writing_dock._editor
    cursor = editor.textCursor()
    title = t("writing_insert_image" if image else "writing_insert_link")
    target, accepted = QInputDialog.getText(_writing_dock, title, t("writing_url_prompt"))
    if not accepted or not _writing_identity_is_current(identity):
        return
    label = _normalize_selection_text(cursor.selectedText())
    if not label:
        label, accepted = QInputDialog.getText(_writing_dock, title, t("writing_reference_label"))
    if not accepted or not _writing_identity_is_current(identity):
        return
    try:
        replacement = _markdown_reference(label, target, image=image)
    except ValueError:
        showInfo(t("writing_invalid_url"), parent=_writing_dock)
        return
    cursor.beginEditBlock()
    cursor.insertText(replacement)
    cursor.endEditBlock()
    editor.setTextCursor(cursor)
    editor.setFocus()


def _export_writing(kind: str) -> None:
    if _writing_dock is None:
        return
    identity = _writing_identity()
    text = _writing_dock._editor.toPlainText()
    extension = "html" if kind == "html" else "md"
    title = _writing_dock._title_lbl.text()
    filename = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title).strip(". ")[:100] or "draft"
    filename = filename + "." + extension
    target, _ = QFileDialog.getSaveFileName(_writing_dock, t("writing_export"),
        filename, t("writing_html_filter" if kind == "html" else "writing_markdown_filter"))
    if not target or not _writing_identity_is_current(identity):
        return
    if kind == "html":
        document = QTextDocument()
        document.setMarkdown(text)
        document.setMetaInformation(QTextDocument.MetaInformation.DocumentTitle, title)
        text = document.toHtml().replace("</head>",
            "<style>body{max-width:720px;margin:48px auto;padding:0 24px;line-height:1.7}"
            "img{max-width:100%}pre{white-space:pre-wrap}</style></head>")
    data = text.encode("utf-8")
    output = QSaveFile(target)
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        showInfo(t("writing_export_failed"), parent=_writing_dock)
        return
    if output.write(data) != len(data):
        output.cancelWriting()
        showInfo(t("writing_export_failed"), parent=_writing_dock)
        return
    if not output.commit():
        showInfo(t("writing_export_failed"), parent=_writing_dock)
        return
    tooltip(t("writing_exported"), parent=_writing_dock)


def _writing_translation_url(text: str) -> str:
    if len(text) > 1000 or not text.strip():
        raise ValueError("Select 1–1000 characters")
    try:
        url = "https://translate.google.com/?" + urlencode({"sl": "auto", "tl": "en", "text": text, "op": "translate"})
    except UnicodeError as exc:
        raise ValueError("Invalid text") from exc
    if len(url) > 8192:
        raise ValueError("Encoded text is too long")
    return url


def _translate_writing() -> None:
    if _writing_dock is None:
        return
    identity = _writing_identity()
    text = _normalize_selection_text(_writing_dock._editor.textCursor().selectedText())
    if not text.strip():
        text = _writing_dock._editor.toPlainText()
    dialog = QDialog(_writing_dock)
    dialog.setWindowTitle(t("writing_translate"))
    dialog.resize(500, 360)
    layout = QVBoxLayout(dialog)
    hint = QLabel(t("writing_translate_hint"), dialog)
    hint.setWordWrap(True)
    layout.addWidget(hint)
    passage = QTextEdit(dialog)
    passage.setAcceptRichText(False)
    passage.setAccessibleName(t("writing_translate_passage"))
    passage.setPlainText(text)
    layout.addWidget(passage)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, dialog)
    open_button = buttons.addButton(t("writing_translate_open"), QDialogButtonBox.ButtonRole.AcceptRole)
    def validate():
        try:
            _writing_translation_url(passage.toPlainText())
            open_button.setEnabled(True)
        except ValueError:
            open_button.setEnabled(False)
    passage.textChanged.connect(validate)
    validate()
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() and _writing_identity_is_current(identity):
        from .file_shell import open_companion_url
        if not open_companion_url(_writing_translation_url(passage.toPlainText())):
            showInfo(t("writing_translate_failed"), parent=_writing_dock)


def _adjust_font_scale(delta: float) -> None:
    if _writing_dock is None:
        return
    _apply_font_scale(float(getattr(_writing_dock, "_font_scale", _DEFAULT_FONT_SCALE)) + float(delta))
    _schedule_state_save()


def _toggle_wrap() -> None:
    if _writing_dock is None:
        return
    _apply_wrap_mode(not bool(getattr(_writing_dock, "_wrap_enabled", True)))
    _schedule_state_save()


def _toggle_focus_mode() -> None:
    if _writing_dock is None:
        return
    _apply_focus_mode(not bool(getattr(_writing_dock, "_focus_mode", False)))
    _schedule_state_save()


def _toggle_preview() -> None:
    if _writing_dock is None:
        return
    _apply_preview_visibility(not bool(getattr(_writing_dock, "_preview_visible", True)))
    _schedule_state_save()


def _toggle_line_highlight() -> None:
    if _writing_dock is None:
        return
    _apply_current_line_highlight(not bool(getattr(_writing_dock, "_highlight_current_line", True)))
    _schedule_state_save()


def _refresh_writing_preview_snapshot() -> None:
    if _writing_dock is None or _loading_editor:
        return
    text = _writing_dock._editor.toPlainText()
    _writing_dock._current_word_count = _count_words(text)
    _refresh_markdown_preview(text)
    _writing_dock._source_margin.render()
    _update_progress_display()


def _on_editor_text_changed() -> None:
    if _writing_dock is None or _loading_editor or not _current_writing_relpath:
        return
    _writing_dock._workspace_dirty = True
    _writing_dock._preview_timer.start()
    _set_status(t("writing_saving"))
    if _autosave_timer is not None:
        _autosave_timer.start()
    _update_editor_highlights()
    _schedule_state_save()


def _on_progress_scope_changed() -> None:
    _update_progress_display()


def _on_editor_selection_changed() -> None:
    if _writing_dock is None:
        return
    _update_editor_highlights()
    try:
        selected = _strip_excerpt_markers(_writing_dock._editor.textCursor().selectedText())
        if not (selected or "").strip():
            return
        from . import add_card_dock as _add_card_dock_mod

        _add_card_dock_mod.update_selection_state("writing", text=selected)
    except Exception:
        pass


def _on_cursor_position_changed() -> None:
    if _writing_dock is None:
        return
    _update_editor_highlights()
    _schedule_state_save()


def _open_writing_folder() -> None:
    path = ""
    if _current_writing_relpath:
        path = ensure_writing_file(_ADDON_DIR, _current_writing_relpath)
    if not path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(get_writing_dir()))
        return
    if not reveal_local_file(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def _reload_current_writing_from_disk() -> None:
    global _loading_editor, _writing_session_baseline_words, _writing_current_word_count, _writing_persisted_state
    if _writing_dock is None or _current_writing_card_id is None or not _current_writing_relpath:
        return
    text = read_writing_text(_ADDON_DIR, _current_writing_relpath)
    _writing_persisted_state = {}
    current_words = _count_words(text)
    today_key = _logical_today_text()
    _writing_session_baseline_words = current_words
    _writing_current_word_count = current_words
    _loading_editor = True
    try:
        _writing_dock._editor.setPlainText(text)
        _writing_dock._current_word_count = current_words
        _writing_dock._session_baseline_words = current_words
        _writing_dock._daily_logical_date = today_key
        _writing_dock._daily_baseline_words = current_words
        _refresh_markdown_preview(text)
    finally:
        _loading_editor = False
    _sync_writing_word_stats(text=text)
    _save_writing_progress()
    _update_editor_highlights()
    _set_status(t("writing_backup_restored"))
    _set_saved_time()


class _WritingBackupDialog(QDialog):
    def __init__(self, parent, backups: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(t("writing_backups_title"))
        self.resize(520, 300)
        self._list = QListWidget(self)
        root = QVBoxLayout(self)
        hint = QLabel(t("writing_backups_hint"))
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addWidget(self._list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("writing_restore"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common_cancel"))
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        root.addWidget(buttons)
        for row in backups:
            item = QListWidgetItem(
                f"{row.get('label', row.get('tier_key', 'Backup'))}  •  {_format_backup_timestamp(row.get('created_at'))}"
            )
            item.setData(Qt.ItemDataRole.UserRole, row)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def selected_backup(self) -> dict | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)


def _open_backup_restore_dialog() -> None:
    if _current_writing_card_id is None or not _current_writing_relpath:
        tooltip(t("writing_no_card_open"))
        return
    if not _flush_editor_state():
        return
    backups = list_writing_backups(_ADDON_DIR, _current_writing_relpath)
    if not backups:
        showInfo(t("writing_no_backups"))
        return
    dlg = _WritingBackupDialog(mw, backups)
    if not dlg.exec():
        return
    selected = dlg.selected_backup()
    if not selected:
        return
    label = str(selected.get("label", selected.get("tier_key", "backup")))
    timestamp = _format_backup_timestamp(selected.get("created_at"))
    if not askUser(
        t("writing_restore_confirm", label=label, timestamp=timestamp)
    ):
        return
    try:
        restore_writing_backup(_ADDON_DIR, _current_writing_relpath, str(selected.get("tier_key", "")))
    except Exception as exc:
        showInfo(t("writing_restore_failed", error=exc))
        return
    _reload_current_writing_from_disk()


def _build_button(label: str, callback, *, tooltip_text: str = "", checkable: bool = False):
    btn = QToolButton()
    btn.setText(label)
    btn.setAutoRaise(True)
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    btn.setCheckable(checkable)
    btn.setAccessibleName(tooltip_text or label)
    if tooltip_text:
        btn.setToolTip(tooltip_text)
    qconnect(btn.clicked, lambda *_args: callback())
    return btn


def _style_writing_workspace(root) -> None:
    """Scope the quiet writing surfaces to this dock, in either Anki theme."""
    dark = root.parentWidget().palette().color(QPalette.ColorRole.Window).lightness() < 128
    background, paper, text, muted, border, hover, accent, selected = (
        ("#22252b", "#292d34", "#edf0f4", "#afb7c4", "#3e444f", "#353b45", "#a8d9c1", "#334a42")
        if dark else
        ("#f4f5f7", "#ffffff", "#252d38", "#5e6b7d", "#dce1e7", "#e9edf2", "#23684e", "#e1f0e8")
    )
    root.setStyleSheet(f"""
        QWidget#incremento_writing_workspace {{ background: {background}; color: {text}; font-size: 13pt; font-weight: 400; }}
        QWidget#incremento_writing_workspace QLabel {{ background: transparent; color: {muted}; font-size: 11px; font-weight: 400; }}
        QWidget#incremento_writing_workspace QToolButton {{
            background: transparent; color: {text}; border: 1px solid transparent;
            border-radius: 6px; padding: 4px 8px; min-height: 22px; font-size: 13pt; font-weight: 400;
        }}
        QWidget#incremento_writing_workspace QToolButton#writing_bold {{ font-weight: 700; }}
        QWidget#incremento_writing_workspace QToolButton:hover {{ background: {hover}; }}
        QWidget#incremento_writing_workspace QToolButton:checked {{ background: {selected}; color: {accent}; }}
        QWidget#incremento_writing_workspace QToolButton:disabled {{ color: {muted}; }}
        QWidget#incremento_writing_workspace QToolButton:focus {{ border: 1px solid {accent}; }}
        QWidget#incremento_writing_workspace QToolButton::menu-indicator {{ subcontrol-position: right center; }}
        QWidget#incremento_writing_workspace QToolButton[popupMode="2"] {{ padding-right: 16px; }}
        QTabBar#writing_tabs {{ background: transparent; font-size: 13pt; font-weight: 400; }}
        QTabBar#writing_tabs::tab {{
            background: transparent; color: {muted}; border: 1px solid transparent;
            border-radius: 6px; padding: 7px 12px; margin-right: 4px;
            min-width: 48px; max-width: 200px;
        }}
        QTabBar#writing_tabs::tab:selected {{ background: {paper}; color: {text}; border-color: {border}; }}
        QTabBar#writing_tabs::tab:hover {{ color: {text}; background: {hover}; }}
        QTabBar#writing_tabs QToolButton#writing_tab_close {{ padding: 0; min-height: 0; font-size: 16px; }}
        QWidget#writing_toolbar {{ background: transparent; }}
        QFrame#writing_toolbar_separator {{ background: {border}; border: none; }}
        QScrollArea#writing_tools {{ background: transparent; border: none; }}
        QWidget#writing_editor_pane, QWidget#writing_preview_pane {{
            background: {paper}; border: 1px solid {border}; border-radius: 10px;
        }}
        QTextEdit#incremento_writing_editor, QTextBrowser#writing_preview {{
            background: {paper}; color: {text}; border: none; padding: 16px 20px;
            selection-background-color: {selected}; selection-color: {text};
        }}
        QWidget#incremento_writing_workspace QSplitter::handle {{ background: {background}; image: none; width: 8px; height: 8px; }}
        QWidget#incremento_writing_workspace QSplitter::handle:hover {{ background: {border}; }}
        QWidget#incremento_writing_workspace QComboBox {{
            background: transparent; color: {muted}; border: 1px solid {border};
            border-radius: 5px; padding: 3px 8px; font-size: 11px; font-weight: 400;
        }}
        QWidget#incremento_writing_workspace QComboBox:focus {{ border-color: {accent}; }}
        QWidget#incremento_writing_workspace QCheckBox {{ color: {muted}; font-size: 11px; font-weight: 400; spacing: 6px; }}
        QWidget#incremento_writing_workspace QCheckBox::indicator {{
            width: 12px; height: 12px; background: {paper}; border: 1px solid {muted}; border-radius: 3px;
        }}
        QWidget#incremento_writing_workspace QCheckBox::indicator:checked {{ background: {selected}; border-color: {accent}; }}
        QWidget#incremento_writing_workspace QCheckBox::indicator:focus {{ border-color: {accent}; }}
        QWidget#incremento_writing_workspace QLabel#writing_word_count {{ color: {text}; font-weight: 600; }}
        QWidget#incremento_writing_workspace QLabel#writing_saved {{ color: {accent}; }}
        QWidget#incremento_writing_workspace QScrollBar:horizontal {{ height: 8px; background: transparent; }}
        QWidget#incremento_writing_workspace QScrollBar:vertical {{ width: 8px; background: transparent; }}
        QWidget#incremento_writing_workspace QScrollBar::handle {{ background: {border}; border-radius: 4px; }}
        QWidget#incremento_writing_workspace QScrollBar::handle:horizontal {{ min-width: 24px; }}
        QWidget#incremento_writing_workspace QScrollBar::handle:vertical {{ min-height: 24px; }}
        QWidget#incremento_writing_workspace QScrollBar::add-line,
        QWidget#incremento_writing_workspace QScrollBar::sub-line {{ width: 0; height: 0; }}
        QWidget#incremento_writing_workspace QScrollBar::add-page,
        QWidget#incremento_writing_workspace QScrollBar::sub-page {{ background: transparent; }}
    """)


def _add_editor_shortcuts(dock) -> None:
    shortcuts = [
        ("Ctrl+=", lambda: _adjust_font_scale(0.1)),
        ("Ctrl+-", lambda: _adjust_font_scale(-0.1)),
        ("Meta+=", lambda: _adjust_font_scale(0.1)),
        ("Meta+-", lambda: _adjust_font_scale(-0.1)),
        ("Alt+1", lambda: _apply_markdown_transform("h1")),
        ("Alt+B", lambda: _apply_markdown_transform("bold")),
        ("Alt+I", lambda: _apply_markdown_transform("italic")),
        ("Alt+L", _toggle_wrap),
        ("Alt+M", _move_marker_to_cursor),
        ("Alt+J", _jump_to_marker),
        ("Alt+Shift+M", _clear_marker),
        ("Ctrl+B", lambda: _apply_markdown_transform("bold")),
        ("Meta+B", lambda: _apply_markdown_transform("bold")),
        ("Ctrl+I", lambda: _apply_markdown_transform("italic")),
        ("Meta+I", lambda: _apply_markdown_transform("italic")),
        ("Ctrl+K", _insert_writing_reference),
        ("Meta+K", _insert_writing_reference),
        ("Ctrl+J", lambda: dock._source_margin.preview_at_cursor()),
        ("Meta+J", lambda: dock._source_margin.preview_at_cursor()),
    ]
    dock._shortcuts = []
    for sequence, callback in shortcuts:
        shortcut = QShortcut(QKeySequence(sequence), dock)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        qconnect(shortcut.activated, callback)
        dock._shortcuts.append(shortcut)


class _WritingTabs(QTabBar):
    def tabInserted(self, index):
        super().tabInserted(index)
        close = _build_button("×", lambda: self._request_close(close), tooltip_text=t("common_close"))
        close.setObjectName("writing_tab_close")
        close.setFixedSize(22, 22)
        self.setTabButton(index, QTabBar.ButtonPosition.RightSide, close)

    def _request_close(self, button):
        for index in range(self.count()):
            if self.tabButton(index, QTabBar.ButtonPosition.RightSide) is button:
                self.tabCloseRequested.emit(index)
                return


class _WritingDock(QDockWidget):
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self.widget() is not None:
            _style_writing_workspace(self.widget())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        split = getattr(self, "_split", None)
        if split is None:
            return
        orientation = Qt.Orientation.Vertical if self.width() < 720 else Qt.Orientation.Horizontal
        if split.orientation() != orientation:
            split.setOrientation(orientation)
            focus_mode = getattr(self, "_focus_mode", False)
            self._preview_host.setMaximumWidth(260 if focus_mode and orientation == Qt.Orientation.Horizontal else 16777215)
            split.setSizes([3, 1] if focus_mode else [1, 1])
        footer = getattr(self, "_footer_details", None)
        if footer is not None:
            footer.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 600 else QBoxLayout.Direction.LeftToRight)
            self._detail_lbl.setVisible(self.width() >= 600)
            self._export_btn.setVisible(self.width() >= 600)

    def closeEvent(self, event):
        if _current_writing_relpath and not _flush_editor_state():
            event.ignore()
            return
        set_keep_open(False)
        super().closeEvent(event)


def _build_writing_dock():
    global _writing_dock, _autosave_timer, _state_save_timer

    dock = _WritingDock(t("writing_title"), mw)
    dock.setObjectName("incremento_writing_dock")
    dock.setMinimumWidth(320)

    root = QWidget(dock)
    root.setObjectName("incremento_writing_workspace")
    _style_writing_workspace(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(6)

    tab_row = QHBoxLayout()
    tab_row.setSpacing(4)
    tabs = _WritingTabs(root)
    tabs.setObjectName("writing_tabs")
    tabs.setAccessibleName(t("writing_tabs"))
    tabs.setDocumentMode(True)
    tabs.setDrawBase(False)
    tabs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    tabs.setExpanding(False)
    tabs.setMovable(True)
    tabs.setTabsClosable(True)
    tabs.setUsesScrollButtons(True)
    tabs.setElideMode(Qt.TextElideMode.ElideRight)
    tab_row.addWidget(tabs, 1)
    add_tab = QToolButton(root)
    add_tab.setText("+")
    add_tab.setAutoRaise(True)
    add_tab.setAccessibleName(t("writing_add_tab"))
    add_tab.setToolTip(t("writing_add_tab"))
    add_tab.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    add_menu = QMenu(add_tab)
    for key, action_name in (("workspace_new_writing", "new_writing"), ("writing_open_tab", "open_existing")):
        action = add_menu.addAction(t(key))
        action.triggered.connect(lambda _checked=False, name=action_name:
            _writing_tab_actions[name]() if name in _writing_tab_actions else None)
    add_tab.setMenu(add_menu)
    tab_row.addWidget(add_tab)
    layout.addLayout(tab_row)
    dock._writing_tabs, dock._open_writing_tabs = tabs, {}
    tabs.currentChanged.connect(_on_writing_tab_changed)
    tabs.tabCloseRequested.connect(_close_writing_tab)

    def menu_button(name, key):
        button = QToolButton(root)
        button.setObjectName(name)
        button.setText(t(key))
        button.setAccessibleName(t(key))
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        menu = QMenu(button)
        button.setMenu(menu)
        return button, menu

    def menu_action(menu, key, callback, *, checkable=False):
        action = menu.addAction(t(key))
        action.setCheckable(checkable)
        qconnect(action.triggered, lambda *_args: callback())
        return action

    preview_btn = _build_button(t("common_preview"), _toggle_preview,
        tooltip_text=t("writing_preview_tooltip"), checkable=True)
    preview_btn.setChecked(True)
    export_btn, export_menu = menu_button("writing_export", "writing_export")
    export_menu.setTitle(t("writing_export"))
    menu_action(export_menu, "writing_export_markdown", lambda: _export_writing("markdown"))
    menu_action(export_menu, "writing_export_html", lambda: _export_writing("html"))
    tab_row.addWidget(export_btn)
    dock._export_btn = export_btn

    # Tabs provide the document title. Keep the existing per-tab state labels
    # parented and hidden instead of repeating that title above the draft.
    title_lbl = QLabel("", root)
    title_lbl.setTextFormat(Qt.TextFormat.PlainText)
    title_lbl.hide()
    file_lbl = QLabel("", root)
    file_lbl.hide()

    keep_open = QCheckBox(t("workspace_keep_open"), root)
    keep_open.setToolTip(t("workspace_keep_open_hint"))
    keep_open.toggled.connect(set_keep_open)
    dock._keep_open_checkbox = keep_open

    toolbar_host = QWidget(root)
    toolbar_host.setObjectName("writing_toolbar")
    toolbar = QHBoxLayout(toolbar_host)
    toolbar.setContentsMargins(0, 0, 0, 0)
    toolbar.setSpacing(2)

    def toolbar_separator():
        separator = QFrame(toolbar_host)
        separator.setObjectName("writing_toolbar_separator")
        separator.setFixedSize(1, 18)
        toolbar.addSpacing(6)
        toolbar.addWidget(separator)
        toolbar.addSpacing(6)

    undo_btn = _build_button("↶", lambda: editor.undo(), tooltip_text=t("writing_undo"))
    redo_btn = _build_button("↷", lambda: editor.redo(), tooltip_text=t("writing_redo"))
    undo_btn.setEnabled(False)
    redo_btn.setEnabled(False)
    style_btn, style_menu = menu_button("writing_style", "writing_style")
    for key, kind in (("writing_paragraph", "paragraph"), ("writing_heading_one", "h1"),
                      ("writing_heading_two", "h2"), ("writing_heading_three", "h3")):
        menu_action(style_menu, key, lambda kind=kind: _apply_markdown_transform(kind))
    toolbar.addWidget(style_btn)
    for label, kind, key in (("B", "bold", "writing_bold"), ("I", "italic", "writing_italic"),
                             ("S", "strike", "writing_strike")):
        button = _build_button(label, lambda kind=kind: _apply_markdown_transform(kind), tooltip_text=t(key))
        button.setObjectName(f"writing_{kind}")
        font = button.font()
        font.setBold(kind == "bold")
        font.setItalic(kind == "italic")
        font.setStrikeOut(kind == "strike")
        button.setFont(font)
        toolbar.addWidget(button)
    toolbar_separator()
    toolbar.addWidget(_build_button(t("writing_insert_link"), _insert_writing_reference))
    insert_btn, insert_menu = menu_button("writing_insert", "writing_insert")
    menu_action(insert_menu, "writing_insert_image", lambda: _insert_writing_reference(image=True))
    for key, kind in (("writing_bullet_list", "bullet"), ("writing_numbered_list", "number"),
                      ("writing_block_quote", "quote"), ("writing_inline_code", "inline_code"),
                      ("writing_code_block", "code"), ("writing_horizontal_rule", "rule"),
                      ("writing_table", "table")):
        menu_action(insert_menu, key, lambda kind=kind: _apply_markdown_transform(kind))
    toolbar.addWidget(insert_btn)
    toolbar.addWidget(_build_button("•", lambda: _apply_markdown_transform("bullet"), tooltip_text=t("writing_bullet_list")))
    toolbar_separator()
    toolbar.addWidget(undo_btn)
    toolbar.addWidget(redo_btn)
    more_btn, more_menu = menu_button("writing_more", "writing_more")
    menu_action(more_menu, "writing_translate", _translate_writing)
    more_menu.addSeparator()
    menu_action(more_menu, "writing_smaller_text", lambda: _adjust_font_scale(-0.1))
    menu_action(more_menu, "writing_larger_text", lambda: _adjust_font_scale(0.1))
    wrap_btn = menu_action(more_menu, "writing_wrap", _toggle_wrap, checkable=True)
    focus_btn = menu_action(more_menu, "writing_focus", _toggle_focus_mode, checkable=True)
    highlight_line_btn = menu_action(more_menu, "writing_line", _toggle_line_highlight, checkable=True)
    more_menu.addSeparator()
    menu_action(more_menu, "writing_set_marker", _move_marker_to_cursor)
    menu_action(more_menu, "writing_jump", _jump_to_marker)
    menu_action(more_menu, "writing_clear", _clear_marker)
    menu_action(more_menu, "writing_bookmark", _add_current_writing_bookmark)
    bookmarks_btn = more_menu.addAction(t("writing_bookmarks_button", count=0))
    qconnect(bookmarks_btn.triggered, lambda *_args: _toggle_writing_bookmarks_panel())
    more_menu.addSeparator()
    more_menu.addMenu(export_menu)
    menu_action(more_menu, "writing_backups", _open_backup_restore_dialog)
    menu_action(more_menu, "writing_reveal_file", _open_writing_folder)
    tab_row.addWidget(more_btn)
    toolbar.addStretch(1)
    toolbar_scroll = QScrollArea(root)
    toolbar_scroll.setObjectName("writing_tools")
    toolbar_scroll.setAccessibleName(t("workspace_writing_tools"))
    toolbar_scroll.setWidget(toolbar_host)
    toolbar_scroll.setWidgetResizable(True)
    toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    toolbar_scroll.setFrameShape(QFrame.Shape.NoFrame)
    toolbar_scroll.setFixedHeight(toolbar_host.sizeHint().height() + 8)
    formatting_row = QHBoxLayout()
    formatting_row.setSpacing(8)
    formatting_row.addWidget(toolbar_scroll, 1)
    formatting_row.addWidget(preview_btn, 0, Qt.AlignmentFlag.AlignTop)
    layout.addLayout(formatting_row)

    split = QSplitter(Qt.Orientation.Horizontal, root)
    split.setHandleWidth(8)
    split.setChildrenCollapsible(False)

    editor_host = QWidget(split)
    editor_host.setObjectName("writing_editor_pane")
    editor_layout = QVBoxLayout(editor_host)
    editor_layout.setContentsMargins(1, 10, 1, 8)
    editor_layout.setSpacing(0)
    editor_label = QLabel(t("writing_markdown"))
    editor_label.setContentsMargins(22, 0, 0, 0)
    editor_layout.addWidget(editor_label)

    try:
        from .writing_excerpt_ui import ExcerptEditor, SourceMargin
    except ImportError:
        from frontend.writing_excerpt_ui import ExcerptEditor, SourceMargin
    editor = ExcerptEditor(editor_host)
    editor.setObjectName("incremento_writing_editor")
    editor.setAccessibleName(t("writing_markdown"))
    install_selection_search_menu(editor)
    editor.setAcceptRichText(False)
    editor.setPlaceholderText(t("writing_placeholder"))
    base_font = QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    base_font.setPointSizeF(13.0)
    editor.setFont(base_font)
    editor.undoAvailable.connect(undo_btn.setEnabled)
    editor.redoAvailable.connect(redo_btn.setEnabled)
    editor_body = QHBoxLayout()
    editor_body.addWidget(editor, 1)
    source_margin = SourceMargin(dock, editor)
    editor_body.addWidget(source_margin)
    editor_layout.addLayout(editor_body, 1)
    split.addWidget(editor_host)

    preview_host = QWidget(split)
    preview_host.setObjectName("writing_preview_pane")
    preview_layout = QVBoxLayout(preview_host)
    preview_layout.setContentsMargins(1, 10, 1, 8)
    preview_layout.setSpacing(0)
    preview_label = QLabel(t("common_preview"))
    preview_label.setContentsMargins(22, 0, 0, 0)
    preview_layout.addWidget(preview_label)
    preview = QTextBrowser(preview_host)
    preview.setObjectName("writing_preview")
    preview.setAccessibleName(t("common_preview"))
    preview.setFont(base_font)
    preview.document().setDefaultStyleSheet("h1 { font-size: 26px; font-weight: 600; } h2 { font-size: 21px; } h3 { font-size: 17px; } p { line-height: 145%; }")
    install_selection_search_menu(preview)
    preview.setOpenExternalLinks(False)
    preview.setOpenLinks(False)
    preview.anchorClicked.connect(source_margin.follow_preview)
    preview.highlighted.connect(source_margin.preview_tooltip)
    preview_layout.addWidget(preview, 1)
    split.addWidget(preview_host)
    split.setStretchFactor(0, 1)
    split.setStretchFactor(1, 1)
    layout.addWidget(split, 1)

    bottom = QHBoxLayout()
    bottom.setSpacing(8)
    status_lbl = QLabel(t("writing_idle"))
    detail_lbl = QLabel(t("writing_line_column", line=1, column=1))
    # The scope picker and count label already explain progress without a heading.
    progress_scope_label = QLabel(t("writing_progress"), root)
    progress_scope_label.hide()
    progress_scope_combo = QComboBox()
    progress_scope_combo.setAccessibleName(t("writing_progress"))
    progress_scope_combo.addItem(t("writing_today"), "today")
    progress_scope_combo.addItem(t("writing_session"), "session")
    progress_scope_combo.addItem(t("writing_all_time"), "all_time")
    progress_scope_combo.setCurrentIndex(0)
    progress_value_lbl = QLabel(t("writing_words", scope=t("writing_today"), count=0))
    progress_value_lbl.setObjectName("writing_word_count")
    saved_lbl = QLabel("")
    saved_lbl.setObjectName("writing_saved")
    saved_lbl.hide()
    bottom.addWidget(status_lbl)
    bottom.addWidget(saved_lbl)
    bottom.addStretch(1)
    bottom.addWidget(progress_value_lbl)
    bottom.addWidget(progress_scope_combo)
    layout.addLayout(bottom)
    footer_details = QBoxLayout(QBoxLayout.Direction.LeftToRight)
    footer_details.setSpacing(4)
    detail_lbl.setWordWrap(True)
    detail_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    footer_details.addWidget(detail_lbl, 1)
    footer_details.addWidget(keep_open)
    layout.addLayout(footer_details)
    dock._footer_details = footer_details

    bookmarks_panel = QTextBrowser(root)
    bookmarks_panel.setOpenLinks(False)
    bookmarks_panel.setOpenExternalLinks(False)
    bookmarks_panel.anchorClicked.connect(_open_writing_bookmark_link)
    bookmarks_panel.setVisible(False)
    bookmarks_panel.setMaximumHeight(150)
    layout.addWidget(bookmarks_panel)

    # Native macOS controls use different arrows and metrics from the design.
    # Keep this workspace's controls consistent without changing Anki's style.
    root._control_style = QStyleFactory.create("Fusion")
    root._control_style.setParent(root)
    for control in root.findChildren(QWidget):
        if isinstance(control, (QToolButton, QTabBar, QComboBox, QCheckBox)):
            control.setStyle(root._control_style)

    dock.setWidget(root)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._title_lbl = title_lbl
    dock._file_lbl = file_lbl
    dock._editor = editor
    dock._source_margin = source_margin
    dock._preview = preview
    dock._preview_host = preview_host
    dock._split = split
    dock._status_lbl = status_lbl
    dock._detail_lbl = detail_lbl
    dock._progress_scope_label = progress_scope_label
    dock._progress_scope_combo = progress_scope_combo
    dock._progress_value_lbl = progress_value_lbl
    dock._saved_lbl = saved_lbl
    dock._base_font = base_font
    dock._base_font_size = float(base_font.pointSizeF() or 12.0)
    dock._font_scale = _DEFAULT_FONT_SCALE
    dock._wrap_enabled = True
    dock._focus_mode = False
    dock._preview_visible = True
    dock._highlight_current_line = True
    dock._bookmark_block_number = -1
    dock._current_word_count = 0
    dock._session_baseline_words = 0
    dock._daily_logical_date = ""
    dock._daily_baseline_words = 0
    dock._progress_visible = configured_writing_progress_visible()
    dock._wrap_btn = wrap_btn
    dock._focus_btn = focus_btn
    dock._preview_btn = preview_btn
    dock._highlight_line_btn = highlight_line_btn
    dock._bookmarks_btn = bookmarks_btn
    dock._bookmarks_panel = bookmarks_panel

    _autosave_timer = QTimer(dock)
    _autosave_timer.setSingleShot(True)
    _autosave_timer.setInterval(180)
    qconnect(_autosave_timer.timeout, _autosave_from_editor)
    dock._preview_timer = QTimer(dock)
    dock._preview_timer.setSingleShot(True)
    dock._preview_timer.setInterval(220)
    qconnect(dock._preview_timer.timeout, _refresh_writing_preview_snapshot)

    _state_save_timer = QTimer(dock)
    _state_save_timer.setSingleShot(True)
    _state_save_timer.setInterval(220)
    qconnect(_state_save_timer.timeout, _save_writing_progress)

    qconnect(editor.textChanged, _on_editor_text_changed)
    qconnect(editor.selectionChanged, _on_editor_selection_changed)
    qconnect(editor.cursorPositionChanged, _on_cursor_position_changed)
    qconnect(editor.verticalScrollBar().valueChanged, lambda _value: _schedule_state_save())
    qconnect(progress_scope_combo.currentIndexChanged, _on_progress_scope_changed)
    qconnect(dock.visibilityChanged, _on_writing_visibility_changed)

    _add_editor_shortcuts(dock)

    _writing_dock = dock
    return dock


def set_keep_open(enabled: bool) -> None:
    global _writing_keep_open
    _writing_keep_open = bool(enabled)
    checkbox = getattr(_writing_dock, '_keep_open_checkbox', None)
    if checkbox is not None and checkbox.isChecked() != _writing_keep_open:
        checkbox.setChecked(_writing_keep_open)


def _on_writing_visibility_changed(visible: bool) -> None:
    if not visible:
        _flush_editor_state()


def reset_for_profile_switch() -> None:
    global _writing_dock, _current_writing_card_id, _current_writing_relpath, _writing_profile
    global _autosave_timer, _state_save_timer
    global _writing_writer, _writing_saved_snapshot, _writing_saved_progress, _writing_persisted_state
    if _writing_profile is not None:
        _flush_editor_state(captured_profile=True)
    if _writing_writer is not None:
        try:
            _writing_writer.close()
        except Exception:
            _set_status(t("writing_autosave_failed"))
        _writing_writer = None
    _writing_saved_snapshot = _writing_saved_progress = None
    _writing_persisted_state = {}
    for timer in (_autosave_timer, _state_save_timer):
        if timer is not None:
            timer.stop()
    set_keep_open(False)
    dock, _writing_dock = _writing_dock, None
    _current_writing_card_id, _current_writing_relpath, _writing_profile = None, "", None
    _autosave_timer = _state_save_timer = None
    if dock is not None:
        try:
            dock.hide()
            mw.removeDockWidget(dock)
            dock.deleteLater()
        except RuntimeError:
            pass


def show_writing_in_dock(card_id: int, title: str, relpath: str, *, keep_open: bool = False) -> bool:
    global _writing_dock, _current_writing_card_id, _current_writing_relpath, _loading_editor
    global _writing_session_baseline_words, _writing_current_word_count, _writing_profile

    if _writing_profile is not None and _writing_profile != _active_profile():
        reset_for_profile_switch()
    if (_writing_dock is not None and _current_writing_card_id == int(card_id)
            and _current_writing_relpath == relpath):
        try:
            _writing_dock.widget()
            if keep_open:
                set_keep_open(True)
            _writing_dock.show()
            _writing_dock.raise_()
            return True
        except RuntimeError:
            _writing_dock = None
    if (_current_writing_card_id is not None
            and (int(card_id) != int(_current_writing_card_id) or relpath != _current_writing_relpath)):
        if not _flush_editor_state():
            return False
        _stash_writing_tab()

    cached = getattr(_writing_dock, '_open_writing_tabs', {}).get(int(card_id))
    if cached is not None and cached['relpath'] == relpath:
        _activate_writing_tab(cached)
        set_keep_open(keep_open or _writing_keep_open)
        _writing_dock.show()
        _writing_dock.raise_()
        return True
    if cached is None and len(getattr(_writing_dock, '_open_writing_tabs', {})) >= _MAX_WRITING_TABS:
        tooltip(t("writing_tab_limit", count=_MAX_WRITING_TABS), parent=_writing_dock)
        return False

    profile = _active_profile()

    if _writing_dock is None:
        _build_writing_dock()
    else:
        try:
            _writing_dock.widget()
        except RuntimeError:
            _writing_dock = None
            _build_writing_dock()

    ensure_writing_file(_ADDON_DIR, relpath, initial_text=f"# {title}\n\n", profile=profile)
    text = read_writing_text(_ADDON_DIR, relpath, profile=profile)
    progress = get_writing_progress(_ADDON_DIR, profile, int(card_id))
    word_stats = get_writing_word_stats(_ADDON_DIR, profile, int(card_id))
    has_saved_progress = int(progress.get("updated_at", 0) or 0) > 0
    current_words = _count_words(text)
    today_key = _logical_today_text()
    daily_logical_date = str(word_stats.get("daily_logical_date", "") or "").strip()
    daily_baseline_words = max(0, int(word_stats.get("daily_baseline_words", 0)))
    if daily_logical_date != today_key:
        daily_logical_date = today_key
        daily_baseline_words = current_words
    _writing_profile = profile
    _current_writing_card_id, _current_writing_relpath = int(card_id), relpath
    _writing_session_baseline_words = current_words
    _writing_current_word_count = current_words

    _loading_editor = True
    try:
        _writing_dock._title_lbl.setText(title or "Writing")
        _writing_dock._file_lbl.setText(relpath)
        try:
            from .writing_excerpt_ui import ExcerptMarkers
        except ImportError:
            from frontend.writing_excerpt_ui import ExcerptMarkers
        document = QTextDocument(_writing_dock)
        document._excerpt_markers = ExcerptMarkers(document)
        _writing_dock._editor.setDocument(document)
        _writing_dock._editor.setPlainText(text)
        _writing_dock._workspace_dirty = False
        _writing_dock._workspace_failed = False
        _writing_dock._current_word_count = current_words
        _writing_dock._session_baseline_words = _writing_session_baseline_words
        _writing_dock._daily_logical_date = daily_logical_date
        _writing_dock._daily_baseline_words = daily_baseline_words
        _writing_dock._progress_visible = configured_writing_progress_visible()
        default_scope = configured_writing_progress_default_scope()
        for idx in range(_writing_dock._progress_scope_combo.count()):
            if _writing_dock._progress_scope_combo.itemData(idx) == default_scope:
                _writing_dock._progress_scope_combo.setCurrentIndex(idx)
                break
        _refresh_markdown_preview(text)
        _apply_font_scale(progress.get("font_scale", _DEFAULT_FONT_SCALE))
        _apply_wrap_mode(
            progress.get("wrap_enabled", True)
            if has_saved_progress
            else configured_writing_wrap_enabled()
        )
        _apply_focus_mode(
            progress.get("focus_mode", False)
            if has_saved_progress
            else configured_writing_focus_mode()
        )
        _apply_preview_visibility(
            progress.get("preview_visible", True)
            if has_saved_progress
            else configured_writing_preview_visible()
        )
        _apply_current_line_highlight(
            progress.get("highlight_current_line", True)
            if has_saved_progress
            else configured_writing_highlight_current_line()
        )
        _restore_editor_progress(progress)
    finally:
        _loading_editor = False

    _update_editor_highlights()
    _update_progress_display()
    _refresh_writing_bookmarks_panel()
    _writing_dock._source_margin.reload()
    _set_status(t("writing_autosave_on_typing"))
    _writing_dock._saved_lbl.clear()
    _stash_writing_tab()
    set_keep_open(keep_open or _writing_keep_open)
    _writing_dock.show()
    _writing_dock.raise_()
    return True


def on_writing_question_shown(card) -> None:
    global _writing_dock
    try:
        if card is None or _writing_keep_open:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != WRITING_NOTE_TYPE:
            if _writing_dock is not None:
                try:
                    # After leaving Writing, later review cards must not keep
                    # serializing the hidden editor and rewriting its stats.
                    if _writing_dock.isVisible():
                        _flush_editor_state()
                        _writing_dock.hide()
                except RuntimeError:
                    _writing_dock = None
            return

        title = (note["Title"] or "").strip()
        relpath = (note[WRITING_FILE_FIELD] or "").strip()
        if not relpath:
            relpath = build_writing_relpath(title=title or f"writing-{card.id}")
            try:
                note[WRITING_FILE_FIELD] = relpath
                mw.col.update_note(note)
            except Exception:
                pass
        show_writing_in_dock(card.id, title, relpath)
    except Exception as e:
        print(f"[Incremento] on_writing_question_shown error: {e}")


def on_writing_reviewer_will_end() -> None:
    _flush_editor_state()
    if _writing_keep_open:
        return
    if _writing_dock is not None:
        try:
            _writing_dock.hide()
        except RuntimeError:
            pass


def get_selected_text() -> str:
    if _writing_dock is None:
        return ""
    try:
        return _strip_excerpt_markers(_normalize_selection_text(_writing_dock._editor.textCursor().selectedText()))
    except Exception:
        return ""


def sync_writing_note_type() -> None:
    try:
        ensure_writing_note_type(mw.col)
    except Exception:
        pass


def add_writing_function() -> None:
    """Legacy entry point kept for parity with other dock modules."""
    tooltip(t("writing_add_content_hint"))
