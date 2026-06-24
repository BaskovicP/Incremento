from __future__ import annotations

from dataclasses import dataclass

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
)
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor


@dataclass(frozen=True)
class TextMatch:
    start: int
    end: int


def normalize_plain_text_for_qt(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n")


def _casefold_with_offsets(text: str) -> tuple[str, list[int], list[int]]:
    folded_parts: list[str] = []
    start_offsets: list[int] = []
    end_offsets: list[int] = [0]

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


def advance_match_index(current_index: int, match_count: int, step: int) -> int:
    if match_count <= 0:
        return -1
    if current_index < 0:
        return 0 if step >= 0 else match_count - 1
    return (current_index + step) % match_count


class DatabaseEntriesDialog(QDialog):
    def __init__(self, parent, *, text: str):
        super().__init__(parent)
        self._text = normalize_plain_text_for_qt(text)
        self._matches: list[TextMatch] = []
        self._active_match_index = -1

        self.setWindowTitle("Incremento Database Entries")
        self.resize(980, 700)

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Search entries")
        self._previous_button = QPushButton("Previous", self)
        self._next_button = QPushButton("Next", self)
        self._count_label = QLabel("", self)
        controls.addWidget(self._search_edit, 1)
        controls.addWidget(self._previous_button)
        controls.addWidget(self._next_button)
        controls.addWidget(self._count_label)
        layout.addLayout(controls)

        self._text_browser = QTextBrowser(self)
        self._text_browser.setReadOnly(True)
        self._text_browser.setPlainText(self._text)
        layout.addWidget(self._text_browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._search_edit.textChanged.connect(self._on_query_changed)
        self._search_edit.returnPressed.connect(self._select_next_match)
        self._previous_button.clicked.connect(self._select_previous_match)
        self._next_button.clicked.connect(self._select_next_match)

        self._refresh_search()

    def _on_query_changed(self, _text: str) -> None:
        self._refresh_search()

    def _refresh_search(self) -> None:
        query = self._search_edit.text()
        self._matches = find_text_matches(self._text, query, case_sensitive=False)
        self._active_match_index = 0 if self._matches else -1
        self._update_search_ui()

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

    def _update_search_ui(self) -> None:
        has_matches = bool(self._matches)
        has_query = bool(self._search_edit.text())
        self._previous_button.setEnabled(has_matches)
        self._next_button.setEnabled(has_matches)
        if not has_query:
            self._count_label.setText("")
        elif not has_matches:
            self._count_label.setText("No matches")
        else:
            self._count_label.setText(f"{self._active_match_index + 1} of {len(self._matches)}")
        self._apply_highlights()

    def _apply_highlights(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        all_match_color = QColor(245, 212, 86, 110)
        active_match_color = QColor(255, 166, 0, 170)

        for index, match in enumerate(self._matches):
            selection = QTextEdit.ExtraSelection()
            cursor = self._text_browser.textCursor()
            cursor.setPosition(text_index_to_qt_position(self._text, match.start))
            cursor.setPosition(
                text_index_to_qt_position(self._text, match.end),
                QTextCursor.MoveMode.KeepAnchor,
            )
            selection.cursor = cursor
            fmt = QTextCharFormat()
            fmt.setBackground(active_match_color if index == self._active_match_index else all_match_color)
            selection.format = fmt
            selections.append(selection)

        self._text_browser.setExtraSelections(selections)

        if 0 <= self._active_match_index < len(self._matches):
            active = self._matches[self._active_match_index]
            cursor = self._text_browser.textCursor()
            cursor.setPosition(text_index_to_qt_position(self._text, active.start))
            cursor.setPosition(
                text_index_to_qt_position(self._text, active.end),
                QTextCursor.MoveMode.KeepAnchor,
            )
            self._text_browser.setTextCursor(cursor)
            self._text_browser.ensureCursorVisible()
        elif not self._matches:
            cursor = self._text_browser.textCursor()
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._text_browser.setTextCursor(cursor)


def show_database_entries_dialog(parent, *, text: str) -> None:
    dlg = DatabaseEntriesDialog(parent, text=text)
    dlg.exec()
