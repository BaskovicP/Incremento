from __future__ import annotations

from dataclasses import dataclass
from array import array

from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QTimer,
)
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor

try:
    from ..backend.i18n import t as _t
except ImportError:
    from backend.i18n import t as _t



@dataclass(frozen=True)
class TextMatch:
    start: int
    end: int


def normalize_plain_text_for_qt(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _casefold_with_offsets(text: str) -> tuple[str, array, array]:
    folded_parts: list[str] = []
    start_offsets = array("I")
    end_offsets = array("I", [0])

    for original_index, char in enumerate(text):
        folded = char.casefold()
        if not folded:
            continue
        folded_parts.append(folded)
        for _ in folded:
            start_offsets.append(original_index)
            end_offsets.append(original_index + 1)

    return "".join(folded_parts), start_offsets, end_offsets


def find_text_matches(text: str, query: str, *, case_sensitive: bool = False) -> list[TextMatch]:
    haystack = str(text or "")
    needle = str(query or "")
    if not needle:
        return []

    if case_sensitive:
        search_text = haystack
        search_query = needle
    else:
        search_text, start_offsets, end_offsets = _casefold_with_offsets(haystack)
        search_query = needle.casefold()
        if not search_query:
            return []

    matches: list[TextMatch] = []
    start = 0
    while True:
        index = search_text.find(search_query, start)
        if index < 0:
            return matches
        if case_sensitive:
            match = TextMatch(index, index + len(needle))
        else:
            match_end = index + len(search_query)
            match = TextMatch(start_offsets[index], end_offsets[match_end])
        matches.append(match)
        start = index + 1


def text_index_to_qt_position(text: str, index: int) -> int:
    normalized_index = max(0, min(int(index), len(text)))
    return len(text[:normalized_index].encode("utf-16-le")) // 2


def utf16_prefix_offsets(text: str) -> array:
    offsets = array("I", [0])
    for char in text:
        offsets.append(offsets[-1] + (2 if ord(char) > 0xffff else 1))
    return offsets


def advance_match_index(current_index: int, match_count: int, step: int) -> int:
    if match_count <= 0:
        return -1
    if current_index < 0:
        return 0 if step >= 0 else match_count - 1
    return (current_index + step) % match_count


class DatabaseEntriesDialog(QDialog):
    def __init__(self, parent, *, text: str, load_page=None):
        super().__init__(parent)
        self._text = normalize_plain_text_for_qt(text)
        self._matches: list[TextMatch] = []
        self._active_match_index = -1
        self._offsets = utf16_prefix_offsets(self._text)
        self._load_page = load_page
        self._page_cursors = [None]
        self._next_cursor = None

        self.setWindowTitle(_t("admin_entries_title"))
        self.resize(980, 700)

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText(_t("admin_entries_search"))
        self._previous_button = QPushButton(_t("admin_entries_previous"), self)
        self._next_button = QPushButton(_t("admin_entries_next"), self)
        self._count_label = QLabel("", self)
        controls.addWidget(self._search_edit, 1)
        controls.addWidget(self._previous_button)
        controls.addWidget(self._next_button)
        controls.addWidget(self._count_label)
        layout.addLayout(controls)
        if load_page is not None:
            pages = QHBoxLayout()
            self._previous_page = QPushButton(_t("reader_previous_page"), self)
            self._next_page = QPushButton(_t("reader_next_page"), self)
            self._previous_page.setEnabled(False)
            self._next_page.setEnabled(False)
            self._previous_page.clicked.connect(self._load_previous_page)
            self._next_page.clicked.connect(self._load_next_page)
            pages.addWidget(self._previous_page)
            pages.addWidget(self._next_page)
            layout.addLayout(pages)

        self._text_browser = QTextBrowser(self)
        self._text_browser.setReadOnly(True)
        self._text_browser.setPlainText(self._text)
        layout.addWidget(self._text_browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(_t("admin_entries_close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(160)
        self._search_timer.timeout.connect(self._refresh_search)
        self._search_edit.textChanged.connect(self._on_query_changed)
        self._search_edit.returnPressed.connect(self._select_next_match)
        self._previous_button.clicked.connect(self._select_previous_match)
        self._next_button.clicked.connect(self._select_next_match)

        self._refresh_search()

    def _on_query_changed(self, _text: str) -> None:
        self._search_timer.start()

    def set_page(self, text: str, next_cursor) -> None:
        self._text = normalize_plain_text_for_qt(text)
        self._offsets = utf16_prefix_offsets(self._text)
        self._text_browser.setPlainText(self._text)
        self._next_cursor = next_cursor
        self._previous_page.setEnabled(len(self._page_cursors) > 1)
        self._next_page.setEnabled(next_cursor is not None)
        self._refresh_search()

    def _load_next_page(self) -> None:
        if self._next_cursor is not None:
            self._page_cursors.append(self._next_cursor)
            self._load_page(self, self._next_cursor)

    def _load_previous_page(self) -> None:
        if len(self._page_cursors) > 1:
            self._page_cursors.pop()
            self._load_page(self, self._page_cursors[-1])

    def _refresh_search(self) -> None:
        query = self._search_edit.text()
        self._matches = find_text_matches(self._text, query, case_sensitive=False)
        self._active_match_index = 0 if self._matches else -1
        self._update_search_ui(refresh_highlights=True)

    def _select_next_match(self) -> None:
        self._active_match_index = advance_match_index(
            self._active_match_index,
            len(self._matches),
            1,
        )
        self._update_search_ui()

    def _select_previous_match(self) -> None:
        self._active_match_index = advance_match_index(
            self._active_match_index,
            len(self._matches),
            -1,
        )
        self._update_search_ui()

    def _update_search_ui(self, *, refresh_highlights=False) -> None:
        has_matches = bool(self._matches)
        has_query = bool(self._search_edit.text())
        self._previous_button.setEnabled(has_matches)
        self._next_button.setEnabled(has_matches)
        if not has_query:
            self._count_label.setText("")
        elif not has_matches:
            self._count_label.setText(_t("admin_entries_no_matches"))
        else:
            self._count_label.setText(_t("admin_entries_match_count", current=self._active_match_index + 1, total=len(self._matches)))
        self._apply_highlights(refresh_all=refresh_highlights)

    def _apply_highlights(self, *, refresh_all=True) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        all_match_color = QColor(245, 212, 86, 110)
        active_match_color = QColor(255, 166, 0, 170)

        for index, match in enumerate(self._matches[:1000] if refresh_all else []):
            selection = QTextEdit.ExtraSelection()
            cursor = self._text_browser.textCursor()
            cursor.setPosition(self._offsets[match.start])
            cursor.setPosition(
                self._offsets[match.end],
                QTextCursor.MoveMode.KeepAnchor,
            )
            selection.cursor = cursor
            fmt = QTextCharFormat()
            fmt.setBackground(all_match_color)
            selection.format = fmt
            selections.append(selection)

        if refresh_all:
            self._text_browser.setExtraSelections(selections)

        if 0 <= self._active_match_index < len(self._matches):
            active = self._matches[self._active_match_index]
            cursor = self._text_browser.textCursor()
            cursor.setPosition(self._offsets[active.start])
            cursor.setPosition(
                self._offsets[active.end],
                QTextCursor.MoveMode.KeepAnchor,
            )
            self._text_browser.setTextCursor(cursor)
            self._text_browser.ensureCursorVisible()
        elif not self._matches:
            cursor = self._text_browser.textCursor()
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._text_browser.setTextCursor(cursor)


def show_database_entries_dialog(parent, *, text: str, load_page=None, on_close=None) -> None:
    dlg = DatabaseEntriesDialog(parent, text=text, load_page=load_page)
    if on_close is not None:
        dlg.finished.connect(on_close)
    if load_page is not None:
        load_page(dlg, None)
    dlg.exec()
