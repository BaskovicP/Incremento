from __future__ import annotations

from aqt.qt import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QShortcut,
    QKeySequence,
    Qt,
    QVBoxLayout,
    QWidget,
)

try:
    from ..backend.reviewer_tags import filter_tags, normalize_tag_list
    from ..backend.i18n import t as _t
except ImportError:
    from backend.reviewer_tags import filter_tags, normalize_tag_list
    from backend.i18n import t as _t


def _tags_summary(tags: list[str], *, empty_text: str) -> str:
    cleaned = normalize_tag_list(tags)
    if not cleaned:
        return empty_text
    return "  ".join(f"#{tag}" for tag in cleaned)


class ReviewerTagDialog(QDialog):
    def __init__(
        self,
        *,
        current_tags,
        recent_tags,
        all_tags,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t("imports_reviewer_tags_title"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)

        self._current_tags = normalize_tag_list(current_tags)
        self._current_tag_keys = {tag.lower() for tag in self._current_tags}
        self._recent_tags = normalize_tag_list(recent_tags)
        self._all_tags = filter_tags(list(all_tags) + self._recent_tags)
        self._visible_tags = list(self._all_tags)
        self._pending_keys: set[str] = set()
        self._recent_buttons: dict[str, QPushButton] = {}
        self._quick_shortcuts: list[QShortcut] = []

        root = QVBoxLayout(self)
        root.setSpacing(10)

        intro = QLabel(
            _t("imports_reviewer_tags_intro")
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        current_wrap = self._build_info_card(
            _t("imports_reviewer_current_tags"),
            _tags_summary(self._current_tags, empty_text=_t("imports_reviewer_no_tags")),
        )
        root.addWidget(current_wrap)

        recent_card = QFrame(self)
        recent_card.setFrameShape(QFrame.Shape.StyledPanel)
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(10, 10, 10, 10)
        recent_layout.setSpacing(8)
        recent_title = QLabel(_t("imports_reviewer_latest_used"))
        recent_title.setStyleSheet("font-weight: 700;")
        recent_layout.addWidget(recent_title)
        self._recent_host = QWidget(recent_card)
        self._recent_grid = QGridLayout(self._recent_host)
        self._recent_grid.setContentsMargins(0, 0, 0, 0)
        self._recent_grid.setHorizontalSpacing(8)
        self._recent_grid.setVerticalSpacing(8)
        recent_layout.addWidget(self._recent_host)
        if self._recent_tags:
            self._populate_recent_buttons()
        else:
            recent_empty = QLabel(_t("imports_reviewer_no_recent"))
            recent_empty.setStyleSheet("color: palette(mid);")
            recent_layout.addWidget(recent_empty)
        root.addWidget(recent_card)

        search_row = QHBoxLayout()
        search_label = QLabel(_t("imports_reviewer_search"))
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(_t("imports_reviewer_search_placeholder"))
        self._search.textChanged.connect(self._apply_filter)
        self._search.returnPressed.connect(self._add_typed_tags)
        search_row.addWidget(search_label)
        search_row.addWidget(self._search, 1)
        self._add_typed_btn = QPushButton(_t("imports_reviewer_add_typed"))
        self._add_typed_btn.clicked.connect(self._add_typed_tags)
        search_row.addWidget(self._add_typed_btn)
        root.addLayout(search_row)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._list.itemSelectionChanged.connect(self._sync_pending_summary)
        self._list.itemDoubleClicked.connect(self._toggle_item_selection)
        root.addWidget(self._list, 1)

        pending_card = self._build_info_card(_t("imports_reviewer_will_add"), _t("imports_reviewer_choose_tags"), pending=True)
        self._pending_value = pending_card.findChild(QLabel, "incremento-reviewer-tag-pending")
        root.addWidget(pending_card)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        self._apply_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self._apply_btn is not None:
            self._apply_btn.setText(_t("imports_reviewer_apply"))
            self._apply_btn.setEnabled(False)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText(_t("imports_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._install_quick_shortcuts()
        self._rebuild_list()
        self._sync_pending_summary()
        self._search.setFocus()

    def _build_info_card(self, title: str, value_text: str, *, pending: bool = False) -> QFrame:
        card = QFrame(self)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-weight: 700;")
        value_lbl = QLabel(value_text)
        value_lbl.setWordWrap(True)
        if pending:
            value_lbl.setObjectName("incremento-reviewer-tag-pending")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        return card

    def _populate_recent_buttons(self) -> None:
        for idx, tag in enumerate(self._recent_tags):
            button = QPushButton(f"#{tag}", self._recent_host)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=tag: self._on_recent_tag_clicked(value))
            self._recent_grid.addWidget(button, idx // 3, idx % 3)
            self._recent_buttons[tag.lower()] = button

    def _install_quick_shortcuts(self) -> None:
        for idx in range(1, 10):
            for seq in (f"Meta+{idx}", f"Ctrl+{idx}"):
                shortcut = QShortcut(QKeySequence(seq), self)
                shortcut.activated.connect(lambda value=idx: self._toggle_visible_index(value - 1))
                self._quick_shortcuts.append(shortcut)

    def _typed_tags(self) -> list[str]:
        return [
            tag
            for tag in normalize_tag_list(self._search.text())
            if tag.lower() not in self._current_tag_keys
        ]

    def _ensure_tag_known(self, tag: str) -> None:
        cleaned = normalize_tag_list([tag])
        if not cleaned:
            return
        value = cleaned[0]
        key = value.lower()
        if key in {item.lower() for item in self._all_tags}:
            return
        self._all_tags.append(value)
        self._all_tags = filter_tags(self._all_tags)

    def _add_typed_tags(self) -> None:
        typed = self._typed_tags()
        if not typed:
            return
        for tag in typed:
            self._ensure_tag_known(tag)
            self._pending_keys.add(tag.lower())
        self._rebuild_list()
        self._sync_pending_summary()

    def _toggle_visible_index(self, index: int) -> None:
        if index < 0:
            return
        visible_items = [
            self._list.item(row)
            for row in range(self._list.count())
            if self._list.item(row).flags() & Qt.ItemFlag.ItemIsSelectable
        ]
        if 0 <= index < len(visible_items):
            item = visible_items[index]
            item.setSelected(not item.isSelected())
            self._sync_pending_summary()
            return
        if index == 0:
            self._add_typed_tags()

    def _rebuild_list(self) -> None:
        self._list.clear()
        for tag in self._visible_tags:
            item = QListWidgetItem(f"#{tag}")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            key = tag.lower()
            if key in self._current_tag_keys:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                item.setToolTip(_t("imports_reviewer_already_present"))
                item.setForeground(self.palette().mid())
            self._list.addItem(item)
            if key in self._pending_keys and key not in self._current_tag_keys:
                item.setSelected(True)

    def _sync_pending_from_visible_list(self) -> None:
        visible_keys = {
            str(self._list.item(row).data(Qt.ItemDataRole.UserRole) or "").strip().lower()
            for row in range(self._list.count())
        }
        self._pending_keys = {key for key in self._pending_keys if key and key not in visible_keys}
        for item in self._list.selectedItems():
            tag = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            key = tag.lower()
            if key and key not in self._current_tag_keys:
                self._pending_keys.add(key)

    def _toggle_item_selection(self, item: QListWidgetItem) -> None:
        if not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        item.setSelected(not item.isSelected())
        self._sync_pending_summary()

    def _on_recent_tag_clicked(self, tag: str) -> None:
        key = str(tag or "").strip().lower()
        if key in self._pending_keys:
            self._pending_keys.remove(key)
        elif key and key not in self._current_tag_keys:
            self._pending_keys.add(key)
        for row in range(self._list.count()):
            item = self._list.item(row)
            item_tag = str(item.data(Qt.ItemDataRole.UserRole) or "").strip().lower()
            if item_tag == key and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                item.setSelected(key in self._pending_keys)
                break
        self._sync_pending_summary()

    def _apply_filter(self, text: str) -> None:
        self._visible_tags = filter_tags(self._all_tags, text)
        self._rebuild_list()
        self._sync_pending_summary()

    def _sync_pending_summary(self) -> None:
        self._sync_pending_from_visible_list()
        pending = self.selected_tags()
        if self._pending_value is not None:
            self._pending_value.setText(
                _tags_summary(pending, empty_text=_t("imports_reviewer_choose_tags"))
            )
        can_apply = bool(pending)
        if self._apply_btn is not None:
            self._apply_btn.setEnabled(can_apply)
        self._add_typed_btn.setEnabled(bool(self._typed_tags()))
        selected_keys = {tag.lower() for tag in pending}
        for key, button in self._recent_buttons.items():
            block = button.blockSignals(True)
            button.setChecked(key in selected_keys)
            button.blockSignals(block)

    def selected_tags(self) -> list[str]:
        return [
            tag
            for tag in self._all_tags
            if tag.lower() in self._pending_keys and tag.lower() not in self._current_tag_keys
        ]
