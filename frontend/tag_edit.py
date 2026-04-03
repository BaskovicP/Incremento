"""QuickTagEdit — chip-style tag editor with Anki tag autocomplete."""

from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QCompleter,
    QEvent,
    QFrame,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QRect,
    QSize,
    QSizePolicy,
    Qt,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _TagFlowLayout(QLayout):
    """Simple wrapping layout so tag chips stay readable instead of shrinking."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, max(0, width), 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(),
            margins.top(),
            -margins.right(),
            -margins.bottom(),
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        max_right = effective.right()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if line_height > 0 and next_x > max_right and effective.width() > 0:
                x = effective.x()
                y += line_height + self.spacing()
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x + self.spacing()
            line_height = max(line_height, hint.height())

        used_height = (y - effective.y()) + line_height
        return used_height + margins.top() + margins.bottom()


class QuickTagEdit(QWidget):
    """Tag editor with removable chips and Tab-driven autocomplete."""

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self._compact = compact
        self._tags: list[str] = []
        self._all_tags = self._load_all_tags()
        self._cycle_matches: list[str] = []
        self._cycle_index: int = -1
        self._cycle_prefix: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4 if compact else 6)

        self._title_lbl: QLabel | None = None
        if not compact:
            self._title_lbl = QLabel("0 Tags")
            self._title_lbl.setStyleSheet("font-size: 20px; font-weight: 600;")
            root.addWidget(self._title_lbl)

        self._frame = QFrame(self)
        self._frame.setObjectName("incTagFrame")
        self._frame.setStyleSheet(
            """
            QFrame#incTagFrame {
                border: 1px solid #4b4f57;
                border-radius: 10px;
                padding: 4px;
            }
            """
        )
        root.addWidget(self._frame)

        row = QHBoxLayout(self._frame)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)

        icon = QLabel("\N{LABEL}")
        icon.setStyleSheet("color: #b7b7b7;")
        icon.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        icon.setFixedWidth(16)
        row.addWidget(icon)

        self._chip_host = QWidget(self._frame)
        self._chip_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        if compact:
            self._chip_layout = QHBoxLayout(self._chip_host)
        else:
            self._chip_layout = _TagFlowLayout(self._chip_host)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(6)
        row.addWidget(self._chip_host, 1)

        self._input = QLineEdit(self._chip_host)
        self._input.setObjectName("incTagInput")
        self._input.setFrame(False)
        self._input.setMinimumWidth(90 if compact else 120)
        self._input.setPlaceholderText("add tags")
        self._input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._input.setStyleSheet(
            """
            QLineEdit#incTagInput {
                border: none;
                background: transparent;
                min-height: 24px;
            }
            """
        )
        if compact:
            self._chip_layout.addWidget(self._input, 1)
        else:
            self._chip_layout.addWidget(self._input)

        self._completer = QCompleter(self._all_tags, self._input)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._input.setCompleter(self._completer)

        self._input.textEdited.connect(self._on_text_edited)
        self._input.editingFinished.connect(self._commit_input_tokens)
        self._input.installEventFilter(self)
        popup = self._completer.popup()
        if popup:
            popup.installEventFilter(self)
            if popup.viewport():
                popup.viewport().installEventFilter(self)

        self._update_title()

    def _load_all_tags(self) -> list[str]:
        try:
            return sorted(mw.col.tags.all()) if mw and mw.col else []
        except Exception:
            return []

    def _split_tokens(self, text: str) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []
        try:
            if mw and mw.col:
                return [t.lstrip("#") for t in mw.col.tags.split(raw) if t.strip()]
        except Exception:
            pass
        return [t.lstrip("#") for t in raw.split() if t.strip()]

    def _update_title(self) -> None:
        if self._title_lbl is None:
            return
        n = len(self._tags)
        self._title_lbl.setText(f"{n} Tag" if n == 1 else f"{n} Tags")

    def _reset_cycle(self) -> None:
        self._cycle_matches = []
        self._cycle_index = -1
        self._cycle_prefix = ""

    def _hide_popup(self) -> None:
        popup = self._completer.popup()
        if popup:
            popup.hide()

    def _matching_tags(self, prefix: str) -> list[str]:
        q = prefix.lower()
        return [t for t in self._all_tags if q in t.lower()]

    def _rebuild_chips(self) -> None:
        while self._chip_layout.count() > 0:
            item = self._chip_layout.takeAt(0)
            w = item.widget()
            if w and w is not self._input:
                w.deleteLater()

        for idx, tag in enumerate(self._tags):
            btn = QToolButton(self._chip_host)
            btn.setText(f"{tag}  \N{WASTEBASKET}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setStyleSheet(
                """
                QToolButton {
                    border: 1px solid #5e6169;
                    border-radius: 9px;
                    padding: 2px 8px;
                    background: #3a3d43;
                }
                QToolButton:hover { background: #454952; }
                """
            )
            btn.clicked.connect(lambda _=False, i=idx: self._remove_tag_index(i))
            self._chip_layout.addWidget(btn)

        if self._compact:
            self._chip_layout.addWidget(self._input, 1)
        else:
            self._chip_layout.addWidget(self._input)

        self._update_title()
        self._chip_host.updateGeometry()
        self._frame.updateGeometry()
        self.updateGeometry()

    def _add_tag(self, tag: str) -> bool:
        t = tag.strip().lstrip("#")
        if not t:
            return False
        if any(existing.lower() == t.lower() for existing in self._tags):
            return False
        self._tags.append(t)
        self._rebuild_chips()
        return True

    def _remove_tag_index(self, idx: int) -> None:
        if 0 <= idx < len(self._tags):
            self._tags.pop(idx)
            self._rebuild_chips()

    def _commit_input_tokens(self) -> bool:
        text = self._input.text().strip()
        if not text:
            return False
        added = False
        for token in self._split_tokens(text):
            added = self._add_tag(token) or added
        self._input.clear()
        self._hide_popup()
        self._reset_cycle()
        return added

    def _on_text_edited(self, text: str) -> None:
        self._reset_cycle()
        prefix = text.strip()
        if not prefix:
            self._hide_popup()
            return
        self._completer.setCompletionPrefix(prefix)
        self._completer.complete()

    def _set_input_candidate(self, candidate: str) -> None:
        self._input.setText(candidate)
        self._input.setCursorPosition(len(candidate))

    def _highlight_popup_candidate(self, candidate: str) -> None:
        self._completer.setCompletionPrefix(self._cycle_prefix)
        self._completer.complete()
        popup = self._completer.popup()
        if not popup:
            return
        model = popup.model()
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            if str(model.data(idx)) == candidate:
                popup.setCurrentIndex(idx)
                break

    def _handle_tab(self, forward: bool) -> None:
        prefix = self._input.text().strip()
        if not prefix:
            self._reset_cycle()
            self.focusNextPrevChild(forward)
            return

        if self._cycle_matches:
            step = 1 if forward else -1
            self._cycle_index = (self._cycle_index + step) % len(self._cycle_matches)
            candidate = self._cycle_matches[self._cycle_index]
            self._set_input_candidate(candidate)
            self._highlight_popup_candidate(candidate)
            return

        matches = self._matching_tags(prefix)
        if not matches:
            return
        if len(matches) == 1:
            self._add_tag(matches[0])
            self._input.clear()
            self._hide_popup()
            return

        self._cycle_prefix = prefix
        self._cycle_matches = matches
        self._cycle_index = 0 if forward else len(matches) - 1
        candidate = self._cycle_matches[self._cycle_index]
        self._set_input_candidate(candidate)
        self._highlight_popup_candidate(candidate)

    def _accept_cycle(self) -> bool:
        if not self._cycle_matches:
            return False
        chosen = self._input.text().strip()
        if not chosen:
            chosen = self._cycle_matches[self._cycle_index]
        self._add_tag(chosen)
        self._input.clear()
        self._hide_popup()
        self._reset_cycle()
        return True

    def eventFilter(self, obj, event):
        popup = self._completer.popup()
        popup_view = popup.viewport() if popup else None
        is_input = obj is self._input
        is_popup = obj is popup or obj is popup_view
        if not (is_input or is_popup):
            return super().eventFilter(obj, event)

        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            key = event.key()
            is_tab = key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            is_enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            is_commit_sep = key in (Qt.Key.Key_Space, Qt.Key.Key_Comma, Qt.Key.Key_Semicolon)
            has_text = bool(self._input.text().strip())
            should_handle_enter = is_enter and (bool(self._cycle_matches) or has_text)
            should_handle_sep = is_commit_sep and has_text
            if is_tab or should_handle_enter or should_handle_sep:
                if event.type() == QEvent.Type.KeyPress:
                    if is_tab:
                        self._handle_tab(key == Qt.Key.Key_Tab)
                    elif should_handle_enter:
                        if not self._accept_cycle():
                            self._commit_input_tokens()
                    elif should_handle_sep:
                        self._commit_input_tokens()
                event.accept()
                return True

            if key == Qt.Key.Key_Backspace and event.type() == QEvent.Type.KeyPress:
                if not self._input.text().strip() and self._tags:
                    self._remove_tag_index(len(self._tags) - 1)
                    event.accept()
                    return True

        return super().eventFilter(obj, event)

    def setPlaceholderText(self, text: str) -> None:
        self._input.setPlaceholderText(text)

    def tags(self) -> list[str]:
        self._commit_input_tokens()
        return list(self._tags)
