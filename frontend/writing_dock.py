"""
writing_dock.py — Markdown writing dock with autosave and editor tools.

Shows a QTextEdit for Incremento Writing cards, writes markdown changes
to user_files/writing/<file>.md while typing, and remembers per-card
editor state such as cursor, scroll, zoom, wrap mode, and bookmark line.
"""

import datetime
import os
import re
import subprocess
import sys

from aqt import mw
from aqt.qt import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
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
)
from aqt.utils import askUser, showInfo, tooltip
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QFontDatabase, QColor, QTextCharFormat, QKeySequence

try:
    from ..backend import paths as _paths
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
except ImportError:
    import paths as _paths
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

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_ADDON_PKG = __name__.split(".")[0] if "." in __name__ else "incremento"

_writing_dock = None
_current_writing_card_id: int | None = None
_current_writing_relpath: str = ""
_loading_editor = False
_autosave_timer = None
_state_save_timer = None
_writing_session_baseline_words = 0
_writing_current_word_count = 0

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
        return mw.addonManager.getConfig(_ADDON_PKG) or {}
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
    resolved_mode = str(mode or configured_writing_word_count_mode()).strip().lower()
    if resolved_mode == "word_like":
        return _count_words_word_like(text)
    return _count_words_simple(text)


def _scope_label(scope: str) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized == "session":
        return "Words this session"
    if normalized == "all_time":
        return "Words total"
    return "Words today"


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
        _writing_dock._progress_scope_label.setVisible(visible)
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
        _writing_dock._progress_value_lbl.setText(f"{_scope_label(scope)}: {count}")
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


def _refresh_markdown_preview(text: str | None = None) -> None:
    if _writing_dock is None:
        return
    preview = getattr(_writing_dock, "_preview", None)
    editor = getattr(_writing_dock, "_editor", None)
    if preview is None or editor is None:
        return
    md = editor.toPlainText() if text is None else str(text)
    try:
        preview.setMarkdown(md)
    except Exception:
        preview.setPlainText(md)


def _set_status(text: str) -> None:
    if _writing_dock is None:
        return
    try:
        _writing_dock._status_lbl.setText(text)
    except Exception:
        pass


def _set_saved_time() -> None:
    if _writing_dock is None:
        return
    now_txt = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        _writing_dock._saved_lbl.setText(f"Saved {now_txt}")
    except Exception:
        pass


def _format_backup_timestamp(value) -> str:
    try:
        return datetime.datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Unknown time"


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
        return "Ln 1, Col 1"
    try:
        cursor = _writing_dock._editor.textCursor()
        return f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}"
    except Exception:
        return "Ln 1, Col 1"


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
        bookmark_txt = f"Marker {bookmark_line}" if bookmark_line is not None else "Marker off"
        wrap_txt = "Wrap on" if bool(getattr(_writing_dock, "_wrap_enabled", True)) else "Wrap off"
        _writing_dock._detail_lbl.setText(
            f"{_line_column_text()}   •   {zoom_percent}%   •   {bookmark_txt}   •   {wrap_txt}"
        )
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
        _writing_dock._preview_host.setMaximumWidth(260 if focus_mode else 16777215)
        _writing_dock._split.setSizes([860, 220] if focus_mode else [620, 420])
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
        _writing_dock._editor.setExtraSelections(selections)
    except Exception:
        pass
    _update_status_details()


def _schedule_state_save() -> None:
    if _writing_dock is None or _loading_editor or not _current_writing_relpath:
        return
    if _state_save_timer is not None:
        _state_save_timer.start()


def _save_writing_progress() -> None:
    if _writing_dock is None or _loading_editor or _current_writing_card_id is None:
        return
    try:
        cursor = _writing_dock._editor.textCursor()
        set_writing_progress(
            _ADDON_DIR,
            _active_profile(),
            int(_current_writing_card_id),
            cursor_position=int(cursor.position()),
            scroll_ratio=_current_scroll_ratio(),
            font_scale=float(getattr(_writing_dock, "_font_scale", _DEFAULT_FONT_SCALE)),
            wrap_enabled=bool(getattr(_writing_dock, "_wrap_enabled", True)),
            focus_mode=bool(getattr(_writing_dock, "_focus_mode", False)),
            preview_visible=bool(getattr(_writing_dock, "_preview_visible", True)),
            highlight_current_line=bool(getattr(_writing_dock, "_highlight_current_line", True)),
            bookmark_block_number=int(getattr(_writing_dock, "_bookmark_block_number", -1)),
        )
    except Exception:
        pass


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


def _autosave_from_editor() -> None:
    if _writing_dock is None or not _current_writing_relpath:
        return
    try:
        text = _writing_dock._editor.toPlainText()
        write_writing_text(
            _ADDON_DIR,
            _current_writing_relpath,
            text,
            backups_enabled=configured_writing_backups_enabled(),
            backup_tiers=configured_writing_backup_tiers(),
        )
    except Exception:
        _set_status("Autosave failed")
        return
    _set_status("Autosave on typing")
    _set_saved_time()
    _sync_writing_word_stats(text=text)
    _save_writing_progress()


def _flush_editor_state() -> None:
    if _autosave_timer is not None:
        _autosave_timer.stop()
    if _state_save_timer is not None:
        _state_save_timer.stop()
    _autosave_from_editor()
    _save_writing_progress()


def _restore_editor_progress(progress: dict) -> None:
    if _writing_dock is None:
        return
    editor = _writing_dock._editor
    document = editor.document()
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
        if _writing_dock is None:
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
        tooltip("No marker set for this writing card.")
        return
    try:
        block = _writing_dock._editor.document().findBlockByNumber(bookmark_block)
        if not block.isValid():
            tooltip("Saved marker line is no longer available.")
            return
        cursor = QTextCursor(block)
        _writing_dock._editor.setTextCursor(cursor)
        _writing_dock._editor.ensureCursorVisible()
        _update_editor_highlights()
        _schedule_state_save()
    except Exception:
        pass


def _apply_markdown_transform(kind: str) -> None:
    if _writing_dock is None:
        return
    editor = _writing_dock._editor
    cursor = editor.textCursor()
    selected = _normalize_selection_text(cursor.selectedText())

    if kind == "h1":
        replacement = _prefix_lines_text(selected, "# ", "Heading")
    elif kind == "bold":
        replacement = _wrap_selection_text(selected, "**", "**", "bold")
    elif kind == "italic":
        replacement = _wrap_selection_text(selected, "*", "*", "italic")
    elif kind == "bullet":
        replacement = _prefix_lines_text(selected, "- ", "List item")
    elif kind == "number":
        body = selected.strip()
        if not body:
            replacement = "1. List item"
        else:
            lines = body.splitlines()
            replacement = "\n".join(f"{idx + 1}. {line}" if line else f"{idx + 1}." for idx, line in enumerate(lines))
    elif kind == "quote":
        replacement = _prefix_lines_text(selected, "> ", "Quote")
    elif kind == "code":
        body = selected.strip("\n") or "code"
        replacement = f"```\n{body}\n```"
    elif kind == "rule":
        replacement = "\n\n---\n\n"
    else:
        return

    cursor.beginEditBlock()
    try:
        cursor.insertText(replacement)
    finally:
        cursor.endEditBlock()
    editor.setTextCursor(cursor)
    editor.setFocus()


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


def _on_editor_text_changed() -> None:
    if _writing_dock is None or _loading_editor or not _current_writing_relpath:
        return
    _refresh_markdown_preview()
    _set_status("Saving…")
    if _autosave_timer is not None:
        _autosave_timer.start()
    try:
        current_words = _count_words(_writing_dock._editor.toPlainText())
        _writing_dock._current_word_count = current_words
    except Exception:
        pass
    _update_editor_highlights()
    _schedule_state_save()


def _on_progress_scope_changed() -> None:
    _update_progress_display()


def _on_editor_selection_changed() -> None:
    if _writing_dock is None:
        return
    _update_editor_highlights()
    try:
        selected = _writing_dock._editor.textCursor().selectedText()
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
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
            return
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
            return
    except Exception:
        pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def _reload_current_writing_from_disk() -> None:
    global _loading_editor, _writing_session_baseline_words, _writing_current_word_count
    if _writing_dock is None or _current_writing_card_id is None or not _current_writing_relpath:
        return
    text = read_writing_text(_ADDON_DIR, _current_writing_relpath)
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
    _set_status("Backup restored")
    _set_saved_time()


class _WritingBackupDialog(QDialog):
    def __init__(self, parent, backups: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Writing Backups")
        self.resize(520, 300)
        self._list = QListWidget(self)
        root = QVBoxLayout(self)
        hint = QLabel("Choose a backup snapshot for this writing card. Restoring replaces the current markdown file.")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addWidget(self._list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Restore")
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
        tooltip("No writing card is open.")
        return
    _flush_editor_state()
    backups = list_writing_backups(_ADDON_DIR, _current_writing_relpath)
    if not backups:
        showInfo("No writing backups are available for this card yet.")
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
        f"Restore the {label} backup from {timestamp}?\n\nThis replaces the current markdown file for this writing card."
    ):
        return
    try:
        restore_writing_backup(_ADDON_DIR, _current_writing_relpath, str(selected.get("tier_key", "")))
    except Exception as exc:
        showInfo(f"Could not restore writing backup.\n\n{exc}")
        return
    _reload_current_writing_from_disk()


def _build_button(label: str, callback, *, tooltip_text: str = "", checkable: bool = False):
    btn = QPushButton(label)
    btn.setCheckable(checkable)
    if tooltip_text:
        btn.setToolTip(tooltip_text)
    qconnect(btn.clicked, lambda *_args: callback())
    return btn


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
    ]
    dock._shortcuts = []
    for sequence, callback in shortcuts:
        shortcut = QShortcut(QKeySequence(sequence), dock)
        qconnect(shortcut.activated, callback)
        dock._shortcuts.append(shortcut)


def _build_writing_dock():
    global _writing_dock, _autosave_timer, _state_save_timer

    dock = QDockWidget("Writing", mw)
    dock.setObjectName("incremento_writing_dock")
    dock.setMinimumWidth(720)

    root = QWidget(dock)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(8, 6, 8, 8)
    layout.setSpacing(6)

    top = QVBoxLayout()
    title_lbl = QLabel("")
    title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
    file_lbl = QLabel("")
    file_lbl.setStyleSheet("font-family: monospace; color: #8a8f99;")
    file_lbl.setWordWrap(True)
    top.addWidget(title_lbl)
    top.addWidget(file_lbl)
    layout.addLayout(top)

    toolbar = QHBoxLayout()
    toolbar.setSpacing(6)

    toolbar.addWidget(_build_button("A-", lambda: _adjust_font_scale(-0.1), tooltip_text="Smaller text"))
    toolbar.addWidget(_build_button("A+", lambda: _adjust_font_scale(0.1), tooltip_text="Larger text"))

    wrap_btn = _build_button("Wrap", lambda _checked=False: _toggle_wrap(), tooltip_text="Toggle line wrap", checkable=True)
    toolbar.addWidget(wrap_btn)

    focus_btn = _build_button("Focus", lambda _checked=False: _toggle_focus_mode(), tooltip_text="Make preview less prominent", checkable=True)
    toolbar.addWidget(focus_btn)

    preview_btn = _build_button(
        "Preview",
        lambda _checked=False: _toggle_preview(),
        tooltip_text="Show or hide the markdown preview",
        checkable=True,
    )
    toolbar.addWidget(preview_btn)

    highlight_line_btn = _build_button(
        "Line",
        lambda _checked=False: _toggle_line_highlight(),
        tooltip_text="Toggle current-line highlight",
        checkable=True,
    )
    toolbar.addWidget(highlight_line_btn)

    toolbar.addSpacing(10)
    toolbar.addWidget(_build_button("H1", lambda: _apply_markdown_transform("h1"), tooltip_text="Insert heading"))
    toolbar.addWidget(_build_button("B", lambda: _apply_markdown_transform("bold"), tooltip_text="Bold"))
    toolbar.addWidget(_build_button("I", lambda: _apply_markdown_transform("italic"), tooltip_text="Italic"))
    toolbar.addWidget(_build_button("•", lambda: _apply_markdown_transform("bullet"), tooltip_text="Bullet list"))
    toolbar.addWidget(_build_button("1.", lambda: _apply_markdown_transform("number"), tooltip_text="Numbered list"))
    toolbar.addWidget(_build_button("Quote", lambda: _apply_markdown_transform("quote"), tooltip_text="Block quote"))
    toolbar.addWidget(_build_button("</>", lambda: _apply_markdown_transform("code"), tooltip_text="Code block"))
    toolbar.addWidget(_build_button("HR", lambda: _apply_markdown_transform("rule"), tooltip_text="Horizontal rule"))

    toolbar.addSpacing(10)
    toolbar.addWidget(_build_button("Set Marker", _move_marker_to_cursor, tooltip_text="Save the current line as a marker"))
    toolbar.addWidget(_build_button("Jump", _jump_to_marker, tooltip_text="Jump to the saved marker line"))
    toolbar.addWidget(_build_button("Clear", _clear_marker, tooltip_text="Clear the saved marker line"))
    toolbar.addStretch(1)
    toolbar.addWidget(_build_button("Backups", _open_backup_restore_dialog, tooltip_text="Restore one of the saved writing backups"))
    toolbar.addWidget(_build_button("Reveal File", _open_writing_folder, tooltip_text="Reveal markdown file in Finder/Explorer"))
    layout.addLayout(toolbar)

    split = QSplitter(Qt.Orientation.Horizontal, root)

    editor_host = QWidget(split)
    editor_layout = QVBoxLayout(editor_host)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    editor_layout.setSpacing(4)
    editor_label = QLabel("Markdown")
    editor_label.setStyleSheet("font-weight: 600;")
    editor_layout.addWidget(editor_label)

    editor = QTextEdit(editor_host)
    editor.setAcceptRichText(False)
    editor.setPlaceholderText("# Markdown writing\n\nThis note autosaves while you type.")
    mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    base_font = QFont(mono)
    if base_font.pointSizeF() <= 0:
        base_font.setPointSizeF(12.0)
    editor.setFont(base_font)
    editor_layout.addWidget(editor, 1)
    split.addWidget(editor_host)

    preview_host = QWidget(split)
    preview_layout = QVBoxLayout(preview_host)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_layout.setSpacing(4)
    preview_label = QLabel("Preview")
    preview_label.setStyleSheet("font-weight: 600;")
    preview_layout.addWidget(preview_label)
    preview = QTextBrowser(preview_host)
    preview.setOpenExternalLinks(True)
    preview_layout.addWidget(preview, 1)
    split.addWidget(preview_host)
    split.setStretchFactor(0, 4)
    split.setStretchFactor(1, 2)
    layout.addWidget(split, 1)

    bottom = QHBoxLayout()
    status_lbl = QLabel("Idle")
    status_lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    detail_lbl = QLabel("Ln 1, Col 1")
    detail_lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    progress_scope_label = QLabel("Progress")
    progress_scope_label.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    progress_scope_combo = QComboBox()
    progress_scope_combo.setMinimumContentsLength(8)
    progress_scope_combo.addItem("Today", "today")
    progress_scope_combo.addItem("Session", "session")
    progress_scope_combo.addItem("All-time", "all_time")
    progress_scope_combo.setCurrentIndex(0)
    progress_value_lbl = QLabel("Words today: 0")
    progress_value_lbl.setStyleSheet("font-size: 11px; color: #9aa0a6; font-weight: 600;")
    saved_lbl = QLabel("")
    saved_lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    bottom.addWidget(status_lbl, 1)
    bottom.addWidget(progress_scope_label, 0, Qt.AlignmentFlag.AlignCenter)
    bottom.addWidget(progress_scope_combo, 0, Qt.AlignmentFlag.AlignCenter)
    bottom.addWidget(progress_value_lbl, 0, Qt.AlignmentFlag.AlignCenter)
    bottom.addWidget(detail_lbl, 0, Qt.AlignmentFlag.AlignCenter)
    bottom.addWidget(saved_lbl, 0, Qt.AlignmentFlag.AlignRight)
    layout.addLayout(bottom)

    dock.setWidget(root)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._title_lbl = title_lbl
    dock._file_lbl = file_lbl
    dock._editor = editor
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

    _autosave_timer = QTimer(dock)
    _autosave_timer.setSingleShot(True)
    _autosave_timer.setInterval(180)
    qconnect(_autosave_timer.timeout, _autosave_from_editor)

    _state_save_timer = QTimer(dock)
    _state_save_timer.setSingleShot(True)
    _state_save_timer.setInterval(220)
    qconnect(_state_save_timer.timeout, _save_writing_progress)

    qconnect(editor.textChanged, _on_editor_text_changed)
    qconnect(editor.selectionChanged, _on_editor_selection_changed)
    qconnect(editor.cursorPositionChanged, _on_cursor_position_changed)
    qconnect(editor.verticalScrollBar().valueChanged, lambda _value: _schedule_state_save())
    qconnect(progress_scope_combo.currentIndexChanged, _on_progress_scope_changed)
    qconnect(dock.visibilityChanged, lambda visible: None if visible else _flush_editor_state())

    _add_editor_shortcuts(dock)

    _writing_dock = dock
    return dock


def show_writing_in_dock(card_id: int, title: str, relpath: str) -> None:
    global _writing_dock, _current_writing_card_id, _current_writing_relpath, _loading_editor
    global _writing_session_baseline_words, _writing_current_word_count

    if _current_writing_card_id is not None and int(card_id) != int(_current_writing_card_id):
        _flush_editor_state()

    _current_writing_card_id = int(card_id)
    _current_writing_relpath = relpath

    if _writing_dock is None:
        _build_writing_dock()
    else:
        try:
            _writing_dock.widget()
        except RuntimeError:
            _writing_dock = None
            _build_writing_dock()

    ensure_writing_file(_ADDON_DIR, relpath, initial_text=f"# {title}\n\n")
    text = read_writing_text(_ADDON_DIR, relpath)
    progress = get_writing_progress(_ADDON_DIR, _active_profile(), int(card_id))
    word_stats = get_writing_word_stats(_ADDON_DIR, _active_profile(), int(card_id))
    has_saved_progress = int(progress.get("updated_at", 0) or 0) > 0
    current_words = _count_words(text)
    today_key = _logical_today_text()
    daily_logical_date = str(word_stats.get("daily_logical_date", "") or "").strip()
    daily_baseline_words = max(0, int(word_stats.get("daily_baseline_words", 0)))
    if daily_logical_date != today_key:
        daily_logical_date = today_key
        daily_baseline_words = current_words
    _writing_session_baseline_words = current_words
    _writing_current_word_count = current_words

    _loading_editor = True
    try:
        _writing_dock._title_lbl.setText(title or "Writing")
        _writing_dock._file_lbl.setText(relpath)
        _writing_dock._editor.setPlainText(text)
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
    _set_status("Autosave on typing")
    _writing_dock.show()
    _writing_dock.raise_()


def on_writing_question_shown(card) -> None:
    global _writing_dock
    try:
        if card is None:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != WRITING_NOTE_TYPE:
            if _writing_dock is not None:
                _flush_editor_state()
                try:
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
    if _writing_dock is not None:
        try:
            _writing_dock.hide()
        except RuntimeError:
            pass


def get_selected_text() -> str:
    if _writing_dock is None:
        return ""
    try:
        return _normalize_selection_text(_writing_dock._editor.textCursor().selectedText())
    except Exception:
        return ""


def sync_writing_note_type() -> None:
    try:
        ensure_writing_note_type(mw.col)
    except Exception:
        pass


def add_writing_function() -> None:
    """Legacy entry point kept for parity with other dock modules."""
    tooltip("Use Incremento → Add Content → Add to Markdown.")
