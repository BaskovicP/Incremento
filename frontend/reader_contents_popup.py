"""A transient, keyboard-accessible contents picker shared by both readers."""
from __future__ import annotations

from aqt.qt import (
    QAbstractItemView, QBrush, QColor, QEvent, QFont, QFrame, QHBoxLayout,
    QHeaderView, QIcon, QInputDialog, QKeySequence, QLabel, QLineEdit,
    QPainter, QPainterPath, QPalette, QPen, QPixmap, QPoint, QPushButton,
    QShortcut, QSignalBlocker, QSize, QTimer, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, Qt,
)

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


def _blend(foreground, background, weight):
    return QColor(*(round(a * weight + b * (1 - weight)) for a, b in zip(
        foreground.getRgb()[:3], background.getRgb()[:3])))


def _contents_icon(glyph, color):
    """Small, theme-colored line icons, crisp on high-density displays."""
    pixmap = QPixmap(36, 36)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    if glyph in ("expand", "collapse"):
        for edge, tip in (((6, 3), (12, 15)) if glyph == "expand"
                          else ((3, 6), (15, 12))):
            path.moveTo(5, edge)
            path.lineTo(9, tip)
            path.lineTo(13, edge)
    elif glyph == "close":
        path.moveTo(5, 5)
        path.lineTo(13, 13)
        path.moveTo(13, 5)
        path.lineTo(5, 13)
    elif glyph == "search":
        painter.drawEllipse(3, 3, 9, 9)
        path.moveTo(11, 11)
        path.lineTo(15, 15)
    elif glyph == "bookmark":
        path.moveTo(5, 3)
        path.lineTo(13, 3)
        path.lineTo(13, 15)
        path.lineTo(9, 12)
        path.lineTo(5, 15)
        path.closeSubpath()
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class ReaderContentsPopup(QFrame):
    def __init__(self, parent, *, entries, bookmarks, current_position, kind,
                 is_current, open_entry, save_place):
        super().__init__(parent, Qt.WindowType.Popup)
        self._entries = entries
        self._bookmarks = bookmarks
        self._current_position = current_position
        self._kind = kind
        self._is_current = is_current
        self._open_entry = open_entry
        self._save_place = save_place
        self._query = None
        self._items = {}
        self._branches = []
        self._has_folds = False
        self._browse_state = None
        self.setObjectName("ReaderContentsPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName(t("reader_contents"))
        self.setAccessibleDescription(t("reader_contents_hint"))
        self._style_popup()
        self._icons = {glyph: _contents_icon(glyph, self.palette().color(QPalette.ColorRole.Text))
                       for glyph in ("expand", "collapse", "close", "search", "bookmark")}
        self.resize(400, 440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(self)
        panel.setObjectName("ReaderContentsSurface")
        outer.addWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        heading.setSpacing(4)
        title = QLabel(t("reader_contents"), self)
        title_font = title.font()
        title_font.setPointSizeF(max(10, title_font.pointSizeF()) + 1)
        title_font.setWeight(QFont.Weight.DemiBold)
        title.setFont(title_font)
        heading.addWidget(title)
        heading.addStretch()
        self._fold_button = self._icon_button("ReaderContentsFoldButton")
        self._fold_button.clicked.connect(self._toggle_all_folds)
        heading.addWidget(self._fold_button)
        close = self._icon_button("ReaderContentsCloseButton")
        close.setIcon(self._icons["close"])
        close.setText(t("reader_close"))
        close.setToolTip(t("reader_close"))
        close.setAccessibleName(t("reader_close"))
        close.clicked.connect(self.close)
        heading.addWidget(close)
        layout.addLayout(heading)
        self._search = QLineEdit(self)
        self._search.setObjectName("ReaderContentsSearch")
        self._search.setPlaceholderText(t("reader_contents_search"))
        self._search.setAccessibleName(t("reader_contents_search"))
        self._search.setMaxLength(240)
        self._search.setClearButtonEnabled(True)
        self._search.addAction(self._icons["search"], QLineEdit.ActionPosition.LeadingPosition)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)
        self._tree = QTreeWidget(self)
        self._tree.setObjectName("ReaderContentsTree")
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(2)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setAccessibleName(t("reader_contents"))
        self._tree.installEventFilter(self)
        self._tree.setWordWrap(True)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._tree.setIndentation(16)
        self._tree.setMouseTracking(True)
        self._tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._tree.itemClicked.connect(self._activate)
        self._tree.itemActivated.connect(self._activate)
        self._tree.itemExpanded.connect(self._update_fold_button)
        self._tree.itemCollapsed.connect(self._update_fold_button)
        body = QVBoxLayout()
        body.setSpacing(6)
        body.addWidget(self._tree, 1)
        self._hint = QLabel(t("reader_contents_empty"), self)
        self._hint.setObjectName("ReaderContentsHint")
        self._hint.setWordWrap(True)
        body.addWidget(self._hint)
        layout.addLayout(body, 1)
        footer = QFrame(self)
        footer.setObjectName("ReaderContentsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 10, 0, 0)
        save = QPushButton(t("reader_contents_save_place"), footer)
        save.setObjectName("ReaderContentsSaveButton")
        save.setIcon(self._icons["bookmark"])
        save.setIconSize(QSize(16, 16))
        save.setAccessibleName(t("reader_contents_save_place"))
        save.clicked.connect(self._save)
        footer_layout.addWidget(save)
        layout.addWidget(footer)
        self._search.textChanged.connect(self._refresh)
        self._search.returnPressed.connect(lambda: self._activate(self._tree.currentItem()))
        self._escape = QShortcut(QKeySequence("Escape"), self)
        self._escape.activated.connect(self.close)
        self._refresh("")

    def _style_popup(self):
        palette = self.palette()
        base = palette.color(QPalette.ColorRole.Base)
        text = palette.color(QPalette.ColorRole.Text)
        accent = palette.color(QPalette.ColorRole.Highlight)
        self._muted = _blend(text, base, .7)
        colors = {
            "BASE": base.name(), "TEXT": text.name(), "MUTED": self._muted.name(),
            "BORDER": _blend(text, base, .16).name(),
            "SCROLL": _blend(text, base, .24).name(),
            "SURFACE": _blend(text, base, .035).name(),
            "HOVER": _blend(text, base, .065).name(),
            "SELECTED": _blend(accent, base, .18).name(), "ACCENT": accent.name(),
        }
        style = """
            QFrame#ReaderContentsSurface {
                background: __BASE__; color: __TEXT__;
                border: 1px solid __BORDER__; border-radius: 12px;
            }
            QFrame#ReaderContentsPopup QLabel { background: transparent; color: __TEXT__; }
            QLineEdit#ReaderContentsSearch {
                background: __SURFACE__; color: __TEXT__;
                border: 1px solid __BORDER__; border-radius: 8px; padding: 7px 6px;
            }
            QLineEdit#ReaderContentsSearch:focus { border-color: __ACCENT__; }
            QTreeWidget#ReaderContentsTree {
                background: __BASE__; color: __TEXT__;
                border: 1px solid transparent; border-radius: 8px; outline: none;
            }
            QTreeWidget#ReaderContentsTree:focus { border-color: __ACCENT__; }
            QTreeWidget#ReaderContentsTree::item {
                border: none; padding: 6px 5px;
            }
            QTreeWidget#ReaderContentsTree::item:hover { background: __HOVER__; }
            QTreeWidget#ReaderContentsTree::item:selected {
                background: __SELECTED__; color: __TEXT__;
            }
            QTreeWidget#ReaderContentsTree QScrollBar:vertical {
                background: transparent; width: 8px; margin: 2px 0;
            }
            QTreeWidget#ReaderContentsTree QScrollBar::handle:vertical {
                background: __SCROLL__; border-radius: 4px; min-height: 28px;
            }
            QTreeWidget#ReaderContentsTree QScrollBar::handle:vertical:hover { background: __MUTED__; }
            QTreeWidget#ReaderContentsTree QScrollBar::add-line:vertical,
            QTreeWidget#ReaderContentsTree QScrollBar::sub-line:vertical { height: 0; }
            QTreeWidget#ReaderContentsTree QScrollBar::add-page:vertical,
            QTreeWidget#ReaderContentsTree QScrollBar::sub-page:vertical { background: transparent; }
            QToolButton#ReaderContentsFoldButton, QToolButton#ReaderContentsCloseButton {
                background: transparent; border: 1px solid transparent;
                border-radius: 7px; padding: 0;
            }
            QToolButton#ReaderContentsFoldButton:hover, QToolButton#ReaderContentsCloseButton:hover {
                background: __HOVER__;
            }
            QToolButton#ReaderContentsFoldButton:focus, QToolButton#ReaderContentsCloseButton:focus {
                border-color: __ACCENT__;
            }
            QToolButton#ReaderContentsFoldButton:pressed, QToolButton#ReaderContentsCloseButton:pressed {
                background: __SELECTED__;
            }
            QLabel#ReaderContentsHint { color: __MUTED__; padding: 6px; }
            QFrame#ReaderContentsFooter { border: none; border-top: 1px solid __BORDER__; }
            QPushButton#ReaderContentsSaveButton {
                background: transparent; color: __TEXT__; text-align: left;
                border: 1px solid transparent; border-radius: 7px; padding: 7px 8px;
            }
            QPushButton#ReaderContentsSaveButton:hover { background: __HOVER__; }
            QPushButton#ReaderContentsSaveButton:pressed { background: __SELECTED__; }
            QPushButton#ReaderContentsSaveButton:focus { border-color: __ACCENT__; }
        """
        for name, color in colors.items():
            style = style.replace(f"__{name}__", color)
        self.setStyleSheet(style)

    def _icon_button(self, name):
        button = QToolButton(self)
        button.setObjectName(name)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(30, 30)
        button.setIconSize(QSize(18, 18))
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return button

    def _refresh(self, query):
        query = str(query).strip().casefold()
        if query == self._query:
            return
        if query and self._query == "":
            self._browse_state = (
                {key for key, item in self._items.items() if item.isExpanded()},
                next((key for key, item in self._items.items()
                      if item == self._tree.currentItem()), None),
                self._tree.verticalScrollBar().value(),
            )
        self._query = query
        # A bulk rebuild or toggle must not rescan all branches for each signal.
        with QSignalBlocker(self._tree):
            self._populate_tree(query)
        self._update_fold_button()

    def _populate_tree(self, query):
        self._tree.clear()
        self._items = {}
        key = "page" if self._kind == "pdf" else "section_index"
        current = None
        eligible = [entry for entry in self._entries if entry[key] <= self._current_position]
        if eligible:
            current = max(eligible, key=lambda entry: entry[key])
        parents = []
        selected = None
        for index, entry in enumerate(self._entries):
            if query and query not in entry["title"].casefold():
                continue
            depth = min(int(entry.get("depth", 0)), len(parents)) if not query else 0
            parents = parents[:depth]
            position = int(entry[key])
            label = str(position if self._kind == "pdf" else position + 1)
            item = QTreeWidgetItem([entry["title"], label])
            self._items[("entry", index)] = item
            item.setToolTip(0, entry["title"])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            if parents:
                parents[-1].addChild(item)
            else:
                self._tree.addTopLevelItem(item)
            parents.append(item)
            if entry is current:
                item.setText(0, "• " + entry["title"])
                selected = item
        matches = [(index, b) for index, b in enumerate(self._bookmarks)
                   if not query or query in b["label"].casefold()]
        if matches:
            group = QTreeWidgetItem([t("reader_contents_saved_places"), ""])
            self._items[("places", 0)] = group
            self._tree.addTopLevelItem(group)
            for index, bookmark in matches:
                location = bookmark["location"]
                entry = {**location, "saved_place": True}
                item = QTreeWidgetItem([bookmark["label"], str(int(location.get(key, 1 if self._kind == "pdf" else 0)) + (0 if self._kind == "pdf" else 1))])
                self._items[("bookmark", index)] = item
                item.setToolTip(0, bookmark["label"])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                group.addChild(item)
            group.setExpanded(True)
            group.setForeground(0, QBrush(self._muted))
        for item in self._items.values():
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setForeground(1, QBrush(self._muted))
            if item.childCount() or item is selected:
                font = item.font(0)
                font.setWeight(QFont.Weight.DemiBold)
                item.setFont(0, font)
        self._hint.setText(t("reader_contents_no_matches") if query else t("reader_contents_empty"))
        has_rows = bool(self._tree.topLevelItemCount())
        self._tree.setVisible(has_rows)
        self._hint.setVisible(not has_rows or (not self._entries and not query))
        self._hint.setAlignment((Qt.AlignmentFlag.AlignLeft if has_rows else Qt.AlignmentFlag.AlignCenter)
                                | Qt.AlignmentFlag.AlignVCenter)
        restoring = not query and self._browse_state is not None
        if restoring:
            expanded, selected_key, _scroll = self._browse_state
            for item_key, item in self._items.items():
                item.setExpanded(item_key in expanded)
            selected = self._visible_ancestor(self._items.get(selected_key))
        elif selected:
            parent = selected.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()
        if selected:
            self._tree.setCurrentItem(selected)
            if not restoring:
                self._tree.scrollToItem(selected)
        elif self._tree.topLevelItemCount():
            first = self._tree.topLevelItem(0)
            self._tree.setCurrentItem(first.child(0) or first)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.resizeColumnToContents(1)
        if restoring:
            self._tree.verticalScrollBar().setValue(self._browse_state[2])
        self._branches = [item for item in self._items.values() if item.childCount()]
        if not query:
            self._has_folds = bool(self._branches)

    @staticmethod
    def _visible_ancestor(item):
        """Keep keyboard activation on a visible row after collapsing a branch."""
        visible = item
        while item and item.parent():
            item = item.parent()
            if not item.isExpanded():
                visible = item
        return visible

    def _update_fold_button(self, *_args):
        expanded = any(item.isExpanded() for item in self._branches)
        label = t("reader_contents_collapse_all") if expanded else t("reader_contents_expand_all")
        hint = t("reader_contents_folds_search_hint") if self._query else label
        self._fold_button.setText(label)
        self._fold_button.setIcon(self._icons["collapse" if expanded else "expand"])
        self._fold_button.setAccessibleName(label)
        self._fold_button.setAccessibleDescription(hint)
        self._fold_button.setToolTip(hint)
        self._fold_button.setVisible(self._has_folds)
        self._fold_button.setEnabled(not self._query)

    def _toggle_all_folds(self):
        if self._query or not self._branches:
            return
        collapse = any(item.isExpanded() for item in self._branches)
        with QSignalBlocker(self._tree):
            if collapse:
                self._tree.collapseAll()
                selected = self._visible_ancestor(self._tree.currentItem())
                if selected:
                    self._tree.setCurrentItem(selected)
                    self._tree.scrollToItem(selected)
            else:
                self._tree.expandAll()
        self._update_fold_button()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            if (watched is self._search and event.key() == Qt.Key.Key_Down
                    and self._tree.currentItem()):
                self._tree.setFocus()
                return True
            if watched is self._tree and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate(self._tree.currentItem())
                return True
        return super().eventFilter(watched, event)

    def _activate(self, item, *_args):
        if item is None or not self._is_current():
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return
        # Close before navigation can load a new reader document.
        self.close()
        self._open_entry(entry)

    def _save(self):
        self.close()

        def ask():
            if not self._is_current():
                return
            label, accepted = QInputDialog.getText(self.parentWidget(), t("reader_contents"), t("reader_contents_place_name"), text=t("reader_contents_page"))
            if accepted and label.strip() and self._is_current():
                self._save_place(label.strip()[:160])

        QTimer.singleShot(0, ask)

    def show_at(self, anchor):
        screen = anchor.screen().availableGeometry()
        self.resize(min(400, screen.width() - 24), min(440, screen.height() - 40))
        point = anchor.mapToGlobal(QPoint(10, anchor.height()))
        self.move(max(screen.left(), min(point.x(), screen.right() - self.width())),
                  max(screen.top(), min(point.y() - self.height(), screen.bottom() - self.height())))
        self.show()
        if self._tree.currentItem():
            self._tree.scrollToItem(self._tree.currentItem(), QAbstractItemView.ScrollHint.PositionAtCenter)
        self._search.setFocus()
