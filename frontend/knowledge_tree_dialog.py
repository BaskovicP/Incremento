from __future__ import annotations

import html
from typing import Callable

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QAction,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
    qconnect,
)
from aqt.utils import showInfo, tooltip
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

try:
    from ..backend.priority_manager import configured_priority_lower_is_more_important
except ImportError:
    from priority_manager import configured_priority_lower_is_more_important  # type: ignore

try:
    from ..backend.note_metadata import build_incremento_metadata
except ImportError:
    from note_metadata import build_incremento_metadata  # type: ignore

try:
    from .knowledge_tree_priority_dialog import (
        KnowledgeTreePriorityDialog,
        OP_FADE_CHILDREN,
        OP_FOCUS_BRANCH,
        OP_LINEAR_SPREAD,
        OP_RANDOMIZE,
        OP_SET_SELECTED,
        OP_SHIFT_SUBTREE,
    )
except ImportError:
    from knowledge_tree_priority_dialog import (  # type: ignore
        KnowledgeTreePriorityDialog,
        OP_FADE_CHILDREN,
        OP_FOCUS_BRANCH,
        OP_LINEAR_SPREAD,
        OP_RANDOMIZE,
        OP_SET_SELECTED,
        OP_SHIFT_SUBTREE,
    )

try:
    from .knowledge_tree_postpone_dialog import (
        KnowledgeTreePostponeDialog,
        resolve_current_browser_card_ids,
    )
except ImportError:
    from knowledge_tree_postpone_dialog import (  # type: ignore
        KnowledgeTreePostponeDialog,
        resolve_current_browser_card_ids,
    )

try:
    from .knowledge_tree_subset_dialog import KnowledgeTreeSubsetDialog
except ImportError:
    from knowledge_tree_subset_dialog import KnowledgeTreeSubsetDialog  # type: ignore

try:
    from ..backend.knowledge_tree import (
        LINK_PLACEMENT_CHILDREN,
        LINK_PLACEMENT_SIBLINGS,
        NODE_KIND_ITEM,
        NODE_KIND_TOPIC,
        active_profile,
        ancestor_card_ids,
        available_deck_names,
        available_note_types,
        describe_branch_summary,
        create_card_for_node,
        default_deck_name,
        default_note_type_name,
        delete_knowledge_tree_node,
        fade_child_priorities,
        focus_subtree_priorities,
        get_card_metadata,
        get_card_priority_context,
        get_parent_card_id,
        link_card_to_tree,
        link_cards_to_tree,
        load_knowledge_tree_nodes,
        normalize_node_kind,
        randomize_subtree_priorities,
        rename_card_title,
        save_knowledge_tree_rows,
        search_linkable_cards,
        set_selected_card_priority,
        shift_subtree_priorities,
        spread_subtree_priorities,
        subtree_priority_stats,
    )
except ImportError:
    from knowledge_tree import (  # type: ignore
        LINK_PLACEMENT_CHILDREN,
        LINK_PLACEMENT_SIBLINGS,
        NODE_KIND_ITEM,
        NODE_KIND_TOPIC,
        active_profile,
        ancestor_card_ids,
        available_deck_names,
        available_note_types,
        describe_branch_summary,
        create_card_for_node,
        default_deck_name,
        default_note_type_name,
        delete_knowledge_tree_node,
        fade_child_priorities,
        focus_subtree_priorities,
        get_card_metadata,
        get_card_priority_context,
        get_parent_card_id,
        link_card_to_tree,
        link_cards_to_tree,
        load_knowledge_tree_nodes,
        normalize_node_kind,
        randomize_subtree_priorities,
        rename_card_title,
        save_knowledge_tree_rows,
        search_linkable_cards,
        set_selected_card_priority,
        shift_subtree_priorities,
        spread_subtree_priorities,
        subtree_priority_stats,
    )


_ROLE_CARD_ID = int(Qt.ItemDataRole.UserRole)
_ROLE_NODE_KIND = _ROLE_CARD_ID + 1
_ROLE_BASE_TITLE = _ROLE_CARD_ID + 2
_KEEP_FOCUS = object()
_KEEP_SELECTION = object()
_ICON_CACHE: dict[str, QIcon] = {}
_COMPACT_TOOLBAR_WIDTH = 900
_VERTICAL_SPLITTER_WIDTH = 760
_STACKED_INSPECTOR_ACTION_WIDTH = 900
_DISPLAY_TITLE_LIMIT = 180


def _priority_text(value) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.0f}"
    except Exception:
        return ""


def _kind_label(node_kind: str) -> str:
    return "Topic" if normalize_node_kind(node_kind) == NODE_KIND_TOPIC else "Item"


def _kind_icon(node_kind: str) -> QIcon:
    kind = normalize_node_kind(node_kind)
    cached = _ICON_CACHE.get(kind)
    if cached is not None:
        return cached

    letter = "T" if kind == NODE_KIND_TOPIC else "I"
    bg = QColor("#2aa84a" if kind == NODE_KIND_TOPIC else "#2d7ff9")
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bg)
    painter.drawRoundedRect(1, 1, 18, 18, 5, 5)

    font = QFont()
    font.setBold(True)
    font.setPointSize(9)
    painter.setFont(font)
    painter.setPen(QPen(QColor("#ffffff")))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, letter)
    painter.end()

    icon = QIcon(pixmap)
    _ICON_CACHE[kind] = icon
    return icon


def _set_badge_style(
    label: QLabel,
    text: str,
    *,
    background: str,
    foreground: str = "#ffffff",
    border: str | None = None,
) -> None:
    label.setText(text)
    label.setVisible(bool(text))
    border_css = border or background
    label.setStyleSheet(
        "QLabel {"
        f"background: {background};"
        f"color: {foreground};"
        f"border: 1px solid {border_css};"
        "border-radius: 10px;"
        "padding: 2px 8px;"
        "font-size: 11px;"
        "font-weight: 600;"
        "}"
    )


def _set_optional_label_text(label: QLabel, text: str) -> None:
    value = str(text or "")
    label.setText(value)
    label.setVisible(bool(value))


def _allow_label_shrink(label: QLabel) -> QLabel:
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


def _row_title(row: dict | None, card_id: int | None = None) -> str:
    if row:
        title = str(row.get("title") or "").strip()
        if title:
            return title
        row_card_id = row.get("card_id")
        if row_card_id is not None:
            return f"Card {int(row_card_id)}"
    if card_id is not None:
        return f"Card {int(card_id)}"
    return "Unknown card"


def _compact_display_text(text: str, *, limit: int = _DISPLAY_TITLE_LIMIT) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


class _KnowledgeTreeWidget(QTreeWidget):
    def __init__(self, on_drop_persist: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_drop_persist = on_drop_persist

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self._on_drop_persist()


class _CreateNodeDialog(QDialog):
    def __init__(self, node_kind: str, parent_card_id: int | None = None, parent=None):
        super().__init__(parent)
        self._node_kind = normalize_node_kind(node_kind)
        self._note_type_specs = available_note_types()
        self._field_widgets: dict[str, QTextEdit] = {}
        self.setWindowTitle(f"Create {_kind_label(self._node_kind)}")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        summary = QLabel(
            f"Create a new {_kind_label(self._node_kind).lower()} card and insert it into the knowledge tree. "
            "The first field becomes the tree label."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addWidget(QLabel("Note type:"))
        self._note_type_combo = QComboBox()
        for spec in self._note_type_specs:
            self._note_type_combo.addItem(spec["name"])
        layout.addWidget(self._note_type_combo)

        layout.addWidget(QLabel("Deck:"))
        self._deck_combo = QComboBox()
        for name in available_deck_names():
            self._deck_combo.addItem(name)
        layout.addWidget(self._deck_combo)

        self._fields_scroll = QScrollArea()
        self._fields_scroll.setWidgetResizable(True)
        self._fields_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._fields_host = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_host)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(6)
        self._fields_scroll.setWidget(self._fields_host)
        layout.addWidget(self._fields_scroll, 1)

        self._hint = QLabel(
            f"The created note will be tagged as {_kind_label(self._node_kind).lower()} and linked to this tree."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color:#666;font-size:11px;")
        layout.addWidget(self._hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("Create")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        qconnect(ok_btn.clicked, self.accept)
        qconnect(cancel_btn.clicked, self.reject)
        qconnect(self._note_type_combo.currentIndexChanged, self._rebuild_fields)

        default_note_type = default_note_type_name(parent_card_id)
        if default_note_type:
            idx = self._note_type_combo.findText(default_note_type)
            if idx >= 0:
                self._note_type_combo.setCurrentIndex(idx)

        default_deck = default_deck_name(parent_card_id)
        if default_deck:
            idx = self._deck_combo.findText(default_deck)
            if idx >= 0:
                self._deck_combo.setCurrentIndex(idx)

        self._rebuild_fields()

    def accept(self) -> None:
        if not self.title:
            showInfo("Knowledge-tree cards need content in the first field.")
            return
        if not self.note_type_name:
            showInfo("Choose a note type for the new knowledge-tree card.")
            return
        if not self.deck_name:
            showInfo("Choose a deck for the new knowledge-tree card.")
            return
        super().accept()

    def _current_spec(self) -> dict | None:
        current_name = self.note_type_name
        for spec in self._note_type_specs:
            if spec["name"] == current_name:
                return spec
        return None

    def _rebuild_fields(self, *_args) -> None:
        existing_values = self.field_values if self._field_widgets else {}
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._field_widgets.clear()

        spec = self._current_spec()
        field_names = list((spec or {}).get("fields") or [])
        if not field_names:
            label = QLabel("This note type does not expose editable fields.")
            label.setWordWrap(True)
            self._fields_layout.addWidget(label)
            return

        for index, field_name in enumerate(field_names):
            label = QLabel(f"{field_name}:")
            self._fields_layout.addWidget(label)
            editor = QTextEdit()
            editor.setAcceptRichText(False)
            editor.setFixedHeight(90 if index == 0 else 110)
            if index == 0:
                editor.setPlaceholderText(f"New {_kind_label(self._node_kind)}")
            existing_text = str(existing_values.get(field_name) or "")
            if existing_text:
                editor.setPlainText(existing_text)
            self._fields_layout.addWidget(editor)
            self._field_widgets[field_name] = editor

        self._fields_layout.addStretch()
        first_field = field_names[0]
        self._field_widgets[first_field].setFocus()

    @property
    def title(self) -> str:
        field_names = list((self._current_spec() or {}).get("fields") or [])
        if not field_names:
            return ""
        editor = self._field_widgets.get(field_names[0])
        if editor is None:
            return ""
        return editor.toPlainText().strip()

    @property
    def note_type_name(self) -> str:
        return self._note_type_combo.currentText().strip()

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText().strip()

    @property
    def field_values(self) -> dict[str, str]:
        return {
            field_name: editor.toPlainText().strip()
            for field_name, editor in self._field_widgets.items()
        }


class _LinkExistingDialog(QDialog):
    def __init__(
        self,
        exclude_card_ids: set[int],
        *,
        has_selected_node: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._exclude_card_ids = {int(card_id) for card_id in exclude_card_ids}
        self._has_selected_node = bool(has_selected_node)
        self.setWindowTitle("Link Existing Card")
        self.setMinimumWidth(640)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        summary = QLabel("Search existing cards and link one or more into the knowledge tree.")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by card title...")
        layout.addWidget(self._search_edit)

        self._results_label = QLabel("")
        self._results_label.setStyleSheet("color:#666;font-size:11px;")
        layout.addWidget(self._results_label)

        layout.addWidget(QLabel("Placement:"))
        self._placement_combo = QComboBox()
        self._placement_combo.addItem(
            "As children of selected node",
            LINK_PLACEMENT_CHILDREN,
        )
        self._placement_combo.addItem(
            "At same level as selected node",
            LINK_PLACEMENT_SIBLINGS,
        )
        sibling_index = self._placement_combo.findData(LINK_PLACEMENT_SIBLINGS)
        if sibling_index >= 0:
            sibling_item = self._placement_combo.model().item(sibling_index)
            if sibling_item is not None and not self._has_selected_node:
                sibling_item.setEnabled(False)
                sibling_item.setToolTip("Select a node first to link cards beside it.")
        layout.addWidget(self._placement_combo)

        self._placement_hint = QLabel("")
        self._placement_hint.setStyleSheet("color:#666;font-size:11px;")
        self._placement_hint.setWordWrap(True)
        layout.addWidget(self._placement_hint)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("Link")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        qconnect(self._search_edit.textChanged, self._refresh_results)
        qconnect(self._list.itemDoubleClicked, lambda _item: self.accept())
        qconnect(self._placement_combo.currentIndexChanged, self._refresh_placement_hint)
        qconnect(ok_btn.clicked, self.accept)
        qconnect(cancel_btn.clicked, self.reject)

        self._refresh_results()
        self._refresh_placement_hint()
        self._search_edit.setFocus()

    def _refresh_placement_hint(self) -> None:
        placement = self.placement_mode
        if placement == LINK_PLACEMENT_SIBLINGS:
            self._placement_hint.setText(
                "Selected cards will be linked beside the selected node, under the same parent."
            )
        elif self._has_selected_node:
            self._placement_hint.setText(
                "Selected cards will be linked under the selected node as siblings of each other."
            )
        else:
            self._placement_hint.setText(
                "No node is selected, so selected cards will be linked at the root level."
            )

    def _refresh_results(self) -> None:
        query = self._search_edit.text().strip()
        results = search_linkable_cards(
            query,
            exclude_card_ids=self._exclude_card_ids,
            limit=200,
        )
        self._list.clear()
        for result in results:
            title = str(result.get("title") or "").strip() or f"Card {result['card_id']}"
            deck = str(result.get("deck_name") or "").strip()
            note_type = str(result.get("note_type_name") or "").strip()
            extra_parts = [part for part in [deck, note_type, f"card {result['card_id']}"] if part]
            item = QListWidgetItem(f"{title}  |  " + "  ·  ".join(extra_parts))
            item.setData(_ROLE_CARD_ID, int(result["card_id"]))
            self._list.addItem(item)

        count = self._list.count()
        self._results_label.setText(f"{count} result{'s' if count != 1 else ''} shown.")
        if count:
            self._list.setCurrentRow(0)

    def accept(self) -> None:
        if not self.selected_card_ids:
            showInfo("Choose one or more existing cards to link into the knowledge tree.")
            return
        super().accept()

    @property
    def selected_card_ids(self) -> list[int]:
        card_ids: list[int] = []
        for item in self._list.selectedItems():
            value = item.data(_ROLE_CARD_ID)
            if value is None:
                continue
            card_ids.append(int(value))
        return card_ids

    @property
    def placement_mode(self) -> str:
        value = self._placement_combo.currentData()
        if not value:
            return LINK_PLACEMENT_CHILDREN
        return str(value)


class KnowledgeTreeDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        *,
        profile: str | None = None,
        select_card_id: int | None = None,
        focus_card_id: int | None = None,
        open_priority_for_card=None,
        open_branch_study=None,
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._profile = str(profile or active_profile()).strip() or active_profile()
        self._open_priority_for_card = open_priority_for_card
        self._open_branch_study = open_branch_study
        self._building = False
        self._initial_select_card_id = None if select_card_id is None else int(select_card_id)
        self._focus_card_id = (
            int(focus_card_id)
            if focus_card_id is not None
            else self._initial_select_card_id
        )
        self._rows_cache: list[dict] = []
        self._row_by_card_id: dict[int, dict] = {}
        self._subset_review_dialogs: list[KnowledgeTreeSubsetDialog] = []
        self._toolbar_buttons: list[QToolButton] = []
        self._toolbar_button_labels: dict[QToolButton, str] = {}
        self._toolbar_button_tooltips: dict[QToolButton, str] = {}
        self._toolbar_compact: bool | None = None
        self._inspector_actions_stacked: bool | None = None
        self._splitter_vertical: bool | None = None
        self._responsive_ready = False

        self.setWindowTitle("Incremento — Knowledge tree")
        self.resize(1120, 720)
        self._apply_style()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self._build_toolbar(outer)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setChildrenCollapsible(True)
        self._splitter.setHandleWidth(8)
        outer.addWidget(self._splitter, 1)

        self._tree_panel = self._build_tree_panel()
        self._inspector_panel = self._build_inspector_panel()
        self._splitter.addWidget(self._tree_panel)
        self._splitter.addWidget(self._inspector_panel)
        self._splitter.setStretchFactor(0, 5)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([770, 350])

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("KnowledgeActionButton")
        close_btn.setIcon(self._standard_icon(QStyle.StandardPixmap.SP_DialogCloseButton))
        close_row.addWidget(close_btn)
        outer.addLayout(close_row)

        qconnect(close_btn.clicked, self.accept)
        qconnect(self._tree.itemSelectionChanged, self._refresh_selection_ui)
        qconnect(self._tree.itemChanged, self._on_item_changed)
        qconnect(self._tree.itemActivated, lambda item, _column: self._start_edit(item))

        self._install_context_menu()
        self._responsive_ready = True
        self._update_responsive_layout()
        self.reload(select_card_id=self._initial_select_card_id, focus_card_id=self._focus_card_id)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _update_responsive_layout(self) -> None:
        if not getattr(self, "_responsive_ready", False):
            return

        width = max(1, self.width())
        compact_toolbar = width < _COMPACT_TOOLBAR_WIDTH
        if compact_toolbar != self._toolbar_compact:
            self._toolbar_compact = compact_toolbar
            style = (
                Qt.ToolButtonStyle.ToolButtonIconOnly
                if compact_toolbar
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            for button in self._toolbar_buttons:
                button.setToolButtonStyle(style)
                label = self._toolbar_button_labels.get(button, button.toolTip())
                tool_tip = self._toolbar_button_tooltips.get(button, label)
                if compact_toolbar:
                    button.setMinimumWidth(34)
                    button.setToolTip(tool_tip)
                else:
                    button.setMinimumWidth(0)
                    button.setToolTip(tool_tip)

        stacked_actions = width < _STACKED_INSPECTOR_ACTION_WIDTH
        if stacked_actions != self._inspector_actions_stacked:
            self._set_inspector_actions_stacked(stacked_actions)

        vertical_splitter = width < _VERTICAL_SPLITTER_WIDTH
        if vertical_splitter != self._splitter_vertical:
            self._splitter_vertical = vertical_splitter
            self._splitter.setOrientation(
                Qt.Orientation.Vertical
                if vertical_splitter
                else Qt.Orientation.Horizontal
            )
            self._splitter.setSizes([430, 290] if vertical_splitter else [770, 350])

        self._tree.setIndentation(16 if compact_toolbar else 22)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#KnowledgePanel, QFrame#KnowledgeInspector, QFrame#KnowledgeSectionCard {
              background: palette(base);
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 10px;
            }
            QFrame#KnowledgeToolbar {
              border: none;
            }
            QFrame#KnowledgeSeparator {
              background: rgba(128,128,128,0.25);
              min-width: 1px;
              max-width: 1px;
            }
            QLabel#KnowledgeTitle {
              font-size: 16px;
              font-weight: 600;
            }
            QLabel#KnowledgeInspectorTitle {
              font-size: 18px;
              font-weight: 600;
            }
            QScrollArea#KnowledgeTitleScroll {
              background: transparent;
              border: none;
            }
            QLabel#KnowledgeMeta {
              color: palette(mid);
              font-size: 11px;
            }
            QLabel#KnowledgeHint {
              color: palette(mid);
              font-size: 11px;
              line-height: 1.3em;
            }
            QLabel#KnowledgeSummaryLine {
              font-size: 12px;
              line-height: 1.35em;
            }
            QTreeWidget#KnowledgeTreeView {
              background: palette(base);
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 10px;
              alternate-background-color: rgba(128,128,128,0.06);
              padding: 4px;
            }
            QTreeWidget#KnowledgeTreeView::item {
              padding: 4px 2px;
            }
            QTreeWidget#KnowledgeTreeView::item:selected {
              background: rgba(74,122,181,0.40);
            }
            QHeaderView::section {
              background: rgba(128,128,128,0.08);
              padding: 6px 8px;
              border: none;
              border-bottom: 1px solid rgba(128,128,128,0.18);
              font-weight: 600;
            }
            QToolButton#KnowledgeToolbarButton, QPushButton#KnowledgeActionButton {
              background: rgba(128,128,128,0.04);
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 8px;
              padding: 6px 10px;
            }
            QToolButton#KnowledgeToolbarButton[popupMode="1"] {
              padding-right: 34px;
            }
            QToolButton#KnowledgeToolbarButton::menu-button {
              width: 30px;
              border-left: 1px solid rgba(128,128,128,0.22);
              border-top-right-radius: 8px;
              border-bottom-right-radius: 8px;
            }
            QToolButton#KnowledgeToolbarButton::menu-button:hover {
              background: rgba(74,122,181,0.16);
            }
            QToolButton#KnowledgeToolbarButton::menu-arrow {
              width: 12px;
              height: 12px;
            }
            QToolButton#KnowledgeToolbarButton:hover, QPushButton#KnowledgeActionButton:hover {
              background: rgba(74,122,181,0.10);
            }
            QPushButton#KnowledgeDangerAction, QToolButton#KnowledgeDangerAction {
              background: rgba(176,64,64,0.08);
              border: 1px solid rgba(176,64,64,0.28);
            }
            QPushButton#KnowledgeDangerAction:hover, QToolButton#KnowledgeDangerAction:hover {
              background: rgba(176,64,64,0.14);
            }
            """
        )

    def _build_toolbar(self, outer: QVBoxLayout) -> None:
        toolbar = QFrame(self)
        toolbar.setObjectName("KnowledgeToolbar")
        toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        primary_row = QHBoxLayout()
        primary_row.setContentsMargins(0, 0, 0, 0)
        primary_row.setSpacing(8)
        secondary_row = QHBoxLayout()
        secondary_row.setContentsMargins(0, 0, 0, 0)
        secondary_row.setSpacing(8)

        self._topic_btn = self._build_add_button(
            label="Topic",
            node_kind=NODE_KIND_TOPIC,
            create_label="Create New Topic…",
            link_label="Link Existing Topic…",
            create_slot=lambda: self._create_node(NODE_KIND_TOPIC),
            link_slot=lambda: self._link_node(NODE_KIND_TOPIC),
        )
        self._item_btn = self._build_add_button(
            label="Item",
            node_kind=NODE_KIND_ITEM,
            create_label="Create New Item…",
            link_label="Link Existing Item…",
            create_slot=lambda: self._create_node(NODE_KIND_ITEM),
            link_slot=lambda: self._link_node(NODE_KIND_ITEM),
        )
        self._rename_btn = self._build_toolbar_button(
            "Rename",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self._rename_selected_node,
            tool_tip="Rename the selected knowledge-tree node.",
        )
        self._priority_btn = self._build_toolbar_button(
            "Priority",
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowRight),
            self._change_selected_priority,
            tool_tip="Open branch-priority tools for the selected node.",
        )
        self._study_btn = self._build_toolbar_button(
            "Study",
            self._standard_icon(QStyle.StandardPixmap.SP_MediaPlay),
            self._study_selected_branch,
            tool_tip="Open the learning dialog and study only this subtree.",
        )
        self._subset_btn = self._build_toolbar_button(
            "Subset",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogListView),
            self._open_subset_review_dialog,
            tool_tip="Open a detailed subset table for the selected node and its descendants.",
        )
        self._postpone_btn = self._build_toolbar_button(
            "Postpone",
            self._standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),
            self._open_postpone_dialog,
            tool_tip="Open bulk postpone tools for all outstanding cards, this branch, or the current Browser.",
        )
        self._browser_btn = self._build_toolbar_button(
            "Browser",
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            self._open_selected_in_browser,
            tool_tip="Open the selected node in Anki Browser.",
        )
        self._parent_btn = self._build_toolbar_button(
            "Parent",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogToParent),
            self._go_to_parent,
            tool_tip="Select the parent node in the knowledge tree.",
        )
        self._remove_btn = self._build_toolbar_button(
            "Remove",
            self._standard_icon(QStyle.StandardPixmap.SP_TrashIcon),
            self._remove_selected_node,
            tool_tip="Remove the selected node from the tree without deleting the card.",
            object_name="KnowledgeDangerAction",
        )
        self._refresh_btn = self._build_toolbar_button(
            "Refresh",
            self._standard_icon(QStyle.StandardPixmap.SP_BrowserReload),
            lambda: self.reload(),
            tool_tip="Reload the tree and keep the current selection when possible.",
        )
        self._expand_btn = self._build_toolbar_button(
            "Expand",
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowDown),
            self._tree_expand_all,
            tool_tip="Expand every branch in the knowledge tree.",
        )
        self._collapse_btn = self._build_toolbar_button(
            "Collapse",
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowUp),
            self._tree_collapse_all,
            tool_tip="Collapse every branch in the knowledge tree.",
        )

        for widget in [
            self._topic_btn,
            self._item_btn,
            self._toolbar_separator(),
            self._rename_btn,
            self._browser_btn,
            self._parent_btn,
            self._remove_btn,
        ]:
            primary_row.addWidget(widget)

        for widget in [
            self._study_btn,
            self._subset_btn,
            self._priority_btn,
            self._postpone_btn,
            self._toolbar_separator(),
            self._refresh_btn,
            self._expand_btn,
            self._collapse_btn,
        ]:
            secondary_row.addWidget(widget)

        primary_row.addStretch(1)
        secondary_row.addStretch(1)
        toolbar_layout.addLayout(primary_row)
        toolbar_layout.addLayout(secondary_row)
        outer.addWidget(toolbar)

    def _build_tree_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("KnowledgePanel")
        panel.setMinimumWidth(0)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro = QFrame(panel)
        intro.setObjectName("KnowledgeSectionCard")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(12, 10, 12, 10)
        intro_layout.setSpacing(4)

        intro_title = QLabel("Branch Workspace")
        intro_title.setObjectName("KnowledgeTitle")
        intro_layout.addWidget(intro_title)

        intro_hint = QLabel(
            "Drag to reorder. Drop onto another node to reparent. Double-click a title to rename. "
            "Cmd/Ctrl-click or Shift-click to multi-select. Right-click a node for branch actions."
        )
        intro_hint.setObjectName("KnowledgeHint")
        intro_hint.setWordWrap(True)
        _allow_label_shrink(intro_hint)
        intro_layout.addWidget(intro_hint)

        self._workspace_summary = QLabel("")
        self._workspace_summary.setObjectName("KnowledgeMeta")
        self._workspace_summary.setWordWrap(True)
        _allow_label_shrink(self._workspace_summary)
        intro_layout.addWidget(self._workspace_summary)

        self._workspace_context = QLabel("")
        self._workspace_context.setObjectName("KnowledgeHint")
        self._workspace_context.setWordWrap(True)
        _allow_label_shrink(self._workspace_context)
        intro_layout.addWidget(self._workspace_context)

        self._workspace_focus = QLabel("")
        self._workspace_focus.setObjectName("KnowledgeHint")
        self._workspace_focus.setWordWrap(True)
        _allow_label_shrink(self._workspace_focus)
        intro_layout.addWidget(self._workspace_focus)

        layout.addWidget(intro)

        self._tree = _KnowledgeTreeWidget(self._persist_tree_after_drop, panel)
        self._tree.setObjectName("KnowledgeTreeView")
        self._tree.setMinimumWidth(0)
        self._tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Knowledge", "Priority"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._tree.setEditTriggers(
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.DoubleClicked
        )
        self._tree.setUniformRowHeights(True)
        self._tree.setAnimated(True)
        self._tree.setIconSize(QSize(20, 20))
        self._tree.setIndentation(22)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setMinimumSectionSize(24)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setColumnWidth(1, 74)
        layout.addWidget(self._tree, 1)
        return panel

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("KnowledgeInspector")
        panel.setMinimumWidth(0)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        hero = QFrame(panel)
        hero.setObjectName("KnowledgeSectionCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(12, 12, 12, 12)
        hero_layout.setSpacing(8)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)
        self._kind_badge = QLabel("")
        self._focus_badge = QLabel("")
        self._focus_badge.setVisible(False)
        badge_row.addWidget(self._kind_badge)
        badge_row.addWidget(self._focus_badge)
        badge_row.addStretch(1)
        hero_layout.addLayout(badge_row)

        self._selection_title = QLabel("No node selected")
        self._selection_title.setObjectName("KnowledgeInspectorTitle")
        self._selection_title.setTextFormat(Qt.TextFormat.PlainText)
        self._selection_title.setWordWrap(True)
        _allow_label_shrink(self._selection_title)
        self._selection_title_scroll = QScrollArea(hero)
        self._selection_title_scroll.setObjectName("KnowledgeTitleScroll")
        self._selection_title_scroll.setWidgetResizable(True)
        self._selection_title_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._selection_title_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._selection_title_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._selection_title_scroll.setMinimumHeight(54)
        self._selection_title_scroll.setMaximumHeight(156)
        self._selection_title_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._selection_title_scroll.setWidget(self._selection_title)
        hero_layout.addWidget(self._selection_title_scroll)

        self._selection_meta = QLabel(
            "Select a topic or item to inspect its branch, open priority tools, or add children."
        )
        self._selection_meta.setObjectName("KnowledgeMeta")
        self._selection_meta.setWordWrap(True)
        _allow_label_shrink(self._selection_meta)
        hero_layout.addWidget(self._selection_meta)

        self._selection_note = QLabel(
            "Use the toolbar to add root topics/items, or select an existing node to append children."
        )
        self._selection_note.setObjectName("KnowledgeHint")
        self._selection_note.setWordWrap(True)
        _allow_label_shrink(self._selection_note)
        hero_layout.addWidget(self._selection_note)

        layout.addWidget(hero)

        branch_card = QFrame(panel)
        branch_card.setObjectName("KnowledgeSectionCard")
        branch_layout = QVBoxLayout(branch_card)
        branch_layout.setContentsMargins(12, 12, 12, 12)
        branch_layout.setSpacing(8)

        branch_title = QLabel("Branch Summary")
        branch_title.setObjectName("KnowledgeTitle")
        branch_layout.addWidget(branch_title)

        self._parent_value = QLabel("Parent branch: Select a node first.")
        self._parent_value.setObjectName("KnowledgeSummaryLine")
        self._parent_value.setWordWrap(True)
        _allow_label_shrink(self._parent_value)
        branch_layout.addWidget(self._parent_value)

        self._lineage_value = QLabel("Lineage: Select a node first.")
        self._lineage_value.setObjectName("KnowledgeSummaryLine")
        self._lineage_value.setWordWrap(True)
        _allow_label_shrink(self._lineage_value)
        self._lineage_value.setTextFormat(Qt.TextFormat.RichText)
        self._lineage_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._lineage_value.setOpenExternalLinks(False)
        qconnect(self._lineage_value.linkActivated, self._on_lineage_link_activated)
        branch_layout.addWidget(self._lineage_value)

        self._branch_size_value = QLabel("Select a topic or item to inspect this branch.")
        self._branch_size_value.setObjectName("KnowledgeSummaryLine")
        self._branch_size_value.setWordWrap(True)
        _allow_label_shrink(self._branch_size_value)
        branch_layout.addWidget(self._branch_size_value)

        self._branch_children_value = QLabel("")
        self._branch_children_value.setObjectName("KnowledgeSummaryLine")
        self._branch_children_value.setWordWrap(True)
        _allow_label_shrink(self._branch_children_value)
        self._branch_children_value.setVisible(False)
        branch_layout.addWidget(self._branch_children_value)

        self._branch_depth_value = QLabel("")
        self._branch_depth_value.setObjectName("KnowledgeSummaryLine")
        self._branch_depth_value.setWordWrap(True)
        _allow_label_shrink(self._branch_depth_value)
        self._branch_depth_value.setVisible(False)
        branch_layout.addWidget(self._branch_depth_value)

        self._branch_priority_value = QLabel("")
        self._branch_priority_value.setObjectName("KnowledgeSummaryLine")
        self._branch_priority_value.setWordWrap(True)
        _allow_label_shrink(self._branch_priority_value)
        self._branch_priority_value.setVisible(False)
        branch_layout.addWidget(self._branch_priority_value)

        self._branch_range_value = QLabel("")
        self._branch_range_value.setObjectName("KnowledgeSummaryLine")
        self._branch_range_value.setWordWrap(True)
        _allow_label_shrink(self._branch_range_value)
        self._branch_range_value.setVisible(False)
        branch_layout.addWidget(self._branch_range_value)

        self._branch_hint = QLabel("")
        self._branch_hint.setObjectName("KnowledgeHint")
        self._branch_hint.setWordWrap(True)
        _allow_label_shrink(self._branch_hint)
        branch_layout.addWidget(self._branch_hint)
        layout.addWidget(branch_card)

        add_card = QFrame(panel)
        add_card.setObjectName("KnowledgeSectionCard")
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(12, 12, 12, 12)
        add_layout.setSpacing(8)
        add_title = QLabel("Add To Tree")
        add_title.setObjectName("KnowledgeTitle")
        add_layout.addWidget(add_title)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(8)
        self._inspector_topic_btn = self._build_action_button(
            "Add Root Topic",
            _kind_icon(NODE_KIND_TOPIC),
            lambda: self._create_node(NODE_KIND_TOPIC),
        )
        self._inspector_item_btn = self._build_action_button(
            "Add Root Item",
            _kind_icon(NODE_KIND_ITEM),
            lambda: self._create_node(NODE_KIND_ITEM),
        )
        add_row.addWidget(self._inspector_topic_btn)
        add_row.addWidget(self._inspector_item_btn)
        add_layout.addLayout(add_row)

        self._insert_target_label = QLabel("")
        self._insert_target_label.setObjectName("KnowledgeHint")
        self._insert_target_label.setWordWrap(True)
        _allow_label_shrink(self._insert_target_label)
        add_layout.addWidget(self._insert_target_label)
        layout.addWidget(add_card)

        action_card = QFrame(panel)
        action_card.setObjectName("KnowledgeSectionCard")
        action_card.setMinimumHeight(300)
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(12, 12, 12, 12)
        action_layout.setSpacing(8)
        action_title = QLabel("Selected Node")
        action_title.setObjectName("KnowledgeTitle")
        action_layout.addWidget(action_title)

        self._inspector_study_btn = self._build_action_button(
            "Study Branch…",
            self._standard_icon(QStyle.StandardPixmap.SP_MediaPlay),
            self._study_selected_branch,
        )
        self._inspector_subset_btn = self._build_action_button(
            "Subset Review…",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogListView),
            self._open_subset_review_dialog,
        )
        self._inspector_postpone_btn = self._build_action_button(
            "Postpone…",
            self._standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),
            self._open_postpone_dialog,
        )
        self._inspector_priority_btn = self._build_action_button(
            "Priority…",
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowRight),
            self._change_selected_priority,
        )
        self._inspector_browser_btn = self._build_action_button(
            "Browser",
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            self._open_selected_in_browser,
        )
        self._inspector_parent_btn = self._build_action_button(
            "Go To Parent",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogToParent),
            self._go_to_parent,
        )
        self._inspector_rename_btn = self._build_action_button(
            "Rename",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self._rename_selected_node,
        )
        self._inspector_remove_btn = self._build_action_button(
            "Remove",
            self._standard_icon(QStyle.StandardPixmap.SP_TrashIcon),
            self._remove_selected_node,
            object_name="KnowledgeDangerAction",
        )

        self._inspector_action_buttons = [
            self._inspector_rename_btn,
            self._inspector_browser_btn,
            self._inspector_parent_btn,
            self._inspector_remove_btn,
            self._inspector_study_btn,
            self._inspector_subset_btn,
            self._inspector_priority_btn,
            self._inspector_postpone_btn,
        ]
        self._inspector_action_grid = QGridLayout()
        self._inspector_action_grid.setContentsMargins(0, 0, 0, 0)
        self._inspector_action_grid.setHorizontalSpacing(10)
        self._inspector_action_grid.setVerticalSpacing(8)
        action_layout.addLayout(self._inspector_action_grid)

        self._action_hint = QLabel(
            "Study Branch opens the normal Incremento learning dialog, but limits scheduling to this subtree. "
            "Subset Review opens a detailed table for this node and every descendant. "
            "Postpone opens SuperMemo-style bulk delay tools for this branch, all outstanding cards, or the current Browser. "
            "Browser opens the linked note for editing."
        )
        self._action_hint.setObjectName("KnowledgeHint")
        self._action_hint.setWordWrap(True)
        _allow_label_shrink(self._action_hint)
        action_layout.addWidget(self._action_hint)
        layout.addWidget(action_card)

        layout.addStretch(1)
        return panel

    def _set_inspector_actions_stacked(self, stacked: bool) -> None:
        if not hasattr(self, "_inspector_action_grid"):
            return
        self._inspector_actions_stacked = stacked
        for button in self._inspector_action_buttons:
            self._inspector_action_grid.removeWidget(button)

        if stacked:
            for row, button in enumerate(self._inspector_action_buttons):
                self._inspector_action_grid.addWidget(button, row, 0)
            self._inspector_action_grid.setColumnStretch(0, 1)
            self._inspector_action_grid.setColumnStretch(1, 0)
            return

        for index, button in enumerate(self._inspector_action_buttons):
            row = index % 4
            column = 0 if index < 4 else 1
            self._inspector_action_grid.addWidget(button, row, column)
        self._inspector_action_grid.setColumnStretch(0, 1)
        self._inspector_action_grid.setColumnStretch(1, 1)

    def _build_add_button(
        self,
        *,
        label: str,
        node_kind: str,
        create_label: str,
        link_label: str,
        create_slot: Callable[[], None],
        link_slot: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("KnowledgeToolbarButton")
        button.setText(label)
        button.setIcon(_kind_icon(node_kind))
        button.setIconSize(QSize(20, 20))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button.setToolTip(f"Create or link a {_kind_label(node_kind).lower()} in the knowledge tree.")
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        qconnect(button.clicked, lambda _checked=False: create_slot())

        menu = QMenu(button)
        create_action = QAction(_kind_icon(node_kind), create_label, menu)
        link_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            link_label,
            menu,
        )
        qconnect(create_action.triggered, lambda _checked=False: create_slot())
        qconnect(link_action.triggered, lambda _checked=False: link_slot())
        menu.addAction(create_action)
        menu.addAction(link_action)
        button.setMenu(menu)
        self._register_toolbar_button(button, label)
        return button

    def _build_toolbar_button(
        self,
        text: str,
        icon: QIcon,
        slot: Callable[[], None],
        *,
        tool_tip: str = "",
        object_name: str = "KnowledgeToolbarButton",
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setText(text)
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip(tool_tip or text)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        qconnect(button.clicked, lambda _checked=False: slot())
        self._register_toolbar_button(button, text)
        return button

    def _register_toolbar_button(self, button: QToolButton, label: str) -> None:
        self._toolbar_buttons.append(button)
        self._toolbar_button_labels[button] = label
        self._toolbar_button_tooltips[button] = button.toolTip() or label

    def _build_action_button(
        self,
        text: str,
        icon: QIcon,
        slot: Callable[[], None],
        *,
        object_name: str = "KnowledgeActionButton",
    ) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(object_name)
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))
        button.setFixedHeight(42)
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        qconnect(button.clicked, lambda _checked=False: slot())
        return button

    def _toolbar_separator(self) -> QFrame:
        line = QFrame(self)
        line.setObjectName("KnowledgeSeparator")
        line.setFrameShape(QFrame.Shape.VLine)
        return line

    def _standard_icon(self, pixmap: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(pixmap)

    def _install_context_menu(self) -> None:
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        qconnect(self._tree.customContextMenuRequested, self._show_context_menu)

    def _show_context_menu(self, pos) -> None:
        clicked_item = self._tree.itemAt(pos)
        if clicked_item is not None and not clicked_item.isSelected():
            self._tree.clearSelection()
            clicked_item.setSelected(True)
            self._tree.setCurrentItem(clicked_item)

        selected_count = len(self._selected_items())
        has_selection = selected_count > 0
        has_single_selection = selected_count == 1
        has_parent = bool(has_single_selection and get_parent_card_id(
            self._addon_dir,
            self._profile,
            int(self._selected_card_id() or 0),
        ) is not None)

        menu = QMenu(self)

        create_topic = QAction(_kind_icon(NODE_KIND_TOPIC), "Create Topic…", menu)
        link_topic = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "Link Topic…",
            menu,
        )
        create_item = QAction(_kind_icon(NODE_KIND_ITEM), "Create Item…", menu)
        link_item = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "Link Item…",
            menu,
        )
        rename_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "Rename",
            menu,
        )
        priority_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowRight),
            "Priority…",
            menu,
        )
        postpone_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "Postpone…",
            menu,
        )
        study_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_MediaPlay),
            "Study Branch…",
            menu,
        )
        subset_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogListView),
            "Subset Review…",
            menu,
        )
        browser_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "Edit In Browser",
            menu,
        )
        parent_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogToParent),
            "Go To Parent",
            menu,
        )
        expand_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowDown),
            "Expand Branch",
            menu,
        )
        collapse_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_ArrowUp),
            "Collapse Branch",
            menu,
        )
        remove_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_TrashIcon),
            "Remove",
            menu,
        )

        qconnect(create_topic.triggered, lambda _checked=False: self._create_node(NODE_KIND_TOPIC))
        qconnect(link_topic.triggered, lambda _checked=False: self._link_node(NODE_KIND_TOPIC))
        qconnect(create_item.triggered, lambda _checked=False: self._create_node(NODE_KIND_ITEM))
        qconnect(link_item.triggered, lambda _checked=False: self._link_node(NODE_KIND_ITEM))
        qconnect(rename_action.triggered, lambda _checked=False: self._rename_selected_node())
        qconnect(priority_action.triggered, lambda _checked=False: self._change_selected_priority())
        qconnect(postpone_action.triggered, lambda _checked=False: self._open_postpone_dialog())
        qconnect(study_action.triggered, lambda _checked=False: self._study_selected_branch())
        qconnect(subset_action.triggered, lambda _checked=False: self._open_subset_review_dialog())
        qconnect(browser_action.triggered, lambda _checked=False: self._open_selected_in_browser())
        qconnect(parent_action.triggered, lambda _checked=False: self._go_to_parent())
        qconnect(expand_action.triggered, lambda _checked=False: self._expand_selected_branch())
        qconnect(collapse_action.triggered, lambda _checked=False: self._collapse_selected_branch())
        qconnect(remove_action.triggered, lambda _checked=False: self._remove_selected_node())

        rename_action.setEnabled(has_single_selection)
        priority_action.setEnabled(has_single_selection)
        study_action.setEnabled(has_single_selection)
        subset_action.setEnabled(has_single_selection)
        browser_action.setEnabled(has_single_selection)
        parent_action.setEnabled(has_parent)
        expand_action.setEnabled(has_selection)
        collapse_action.setEnabled(has_selection)
        remove_action.setEnabled(has_selection)

        menu.addAction(create_topic)
        menu.addAction(link_topic)
        menu.addAction(create_item)
        menu.addAction(link_item)
        menu.addSeparator()
        menu.addAction(rename_action)
        menu.addAction(browser_action)
        menu.addAction(parent_action)
        menu.addAction(remove_action)
        menu.addSeparator()
        menu.addAction(study_action)
        menu.addAction(subset_action)
        menu.addAction(priority_action)
        menu.addAction(postpone_action)
        menu.addSeparator()
        menu.addAction(expand_action)
        menu.addAction(collapse_action)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _selected_items(self) -> list[QTreeWidgetItem]:
        return list(self._tree.selectedItems())

    def _selected_item(self) -> QTreeWidgetItem | None:
        current = self._tree.currentItem()
        if current is not None and current.isSelected():
            return current
        items = self._selected_items()
        return items[0] if items else None

    def _selected_card_ids(self) -> list[int]:
        card_ids: list[int] = []
        seen: set[int] = set()
        for item in self._selected_items():
            value = item.data(0, _ROLE_CARD_ID)
            if value is None:
                continue
            card_id = int(value)
            if card_id in seen:
                continue
            seen.add(card_id)
            card_ids.append(card_id)
        return card_ids

    def _selected_card_ids_in_tree_order(self) -> list[int]:
        selected = set(self._selected_card_ids())
        ordered: list[int] = []
        if not selected:
            return ordered

        def visit(item: QTreeWidgetItem) -> None:
            card_id = int(item.data(0, _ROLE_CARD_ID))
            if card_id in selected:
                ordered.append(card_id)
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(index))
        return ordered

    def _selected_card_id(self) -> int | None:
        item = self._selected_item()
        if item is None:
            return None
        value = item.data(0, _ROLE_CARD_ID)
        return None if value is None else int(value)

    def _single_selected_card_id(self) -> int | None:
        card_ids = self._selected_card_ids()
        if len(card_ids) != 1:
            return None
        return int(card_ids[0])

    def _selected_parent_card_id_for_insert(self) -> int | None:
        return self._selected_card_id()

    def _current_tree_rows(self) -> list[dict]:
        rows: list[dict] = []

        def visit(item: QTreeWidgetItem, parent_card_id: int | None) -> None:
            card_id = item.data(0, _ROLE_CARD_ID)
            node_kind = item.data(0, _ROLE_NODE_KIND)
            rows.append(
                {
                    "card_id": int(card_id),
                    "parent_card_id": parent_card_id,
                    "node_kind": normalize_node_kind(node_kind),
                    "sort_order": (
                        item.parent().indexOfChild(item)
                        if item.parent() is not None
                        else self._tree.indexOfTopLevelItem(item)
                    ),
                }
            )
            for index in range(item.childCount()):
                visit(item.child(index), int(card_id))

        for index in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(index), None)
        return rows

    def _expanded_card_ids(self) -> set[int]:
        expanded: set[int] = set()

        def visit(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                expanded.add(int(item.data(0, _ROLE_CARD_ID)))
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(index))
        return expanded

    def _persist_tree_after_drop(self) -> None:
        try:
            save_knowledge_tree_rows(
                self._addon_dir,
                self._profile,
                self._current_tree_rows(),
            )
            self.reload(
                select_card_id=self._selected_card_id(),
                select_card_ids=self._selected_card_ids(),
            )
        except Exception as exc:
            showInfo(f"Failed to move knowledge-tree node:\n{exc}")
            self.reload()

    def _item_for_row(self, row: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        card_id = int(row["card_id"])
        item.setText(0, _row_title(row, card_id))
        item.setText(1, _priority_text(row.get("priority")))
        item.setTextAlignment(1, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        item.setIcon(0, _kind_icon(row.get("node_kind") or NODE_KIND_TOPIC))
        item.setData(0, _ROLE_CARD_ID, card_id)
        item.setData(0, _ROLE_NODE_KIND, normalize_node_kind(row["node_kind"]))
        item.setData(0, _ROLE_BASE_TITLE, str(row.get("title") or ""))
        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        tip_parts = [
            _kind_label(row["node_kind"]),
            f"card {card_id}",
        ]
        if row.get("deck_name"):
            tip_parts.append(str(row["deck_name"]))
        if row.get("note_type_name"):
            tip_parts.append(str(row["note_type_name"]))
        if self._focus_card_id is not None and card_id == self._focus_card_id:
            tip_parts.append("focused in current workspace")
            highlight = QColor("#4a7ab5")
            highlight.setAlpha(44)
            item.setBackground(0, highlight)
            item.setBackground(1, highlight)
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            item.setFont(1, font)
        item.setToolTip(0, "  ·  ".join(tip_parts))
        item.setToolTip(1, "  ·  ".join(tip_parts))
        return item

    def reload(
        self,
        *,
        select_card_id: int | None = None,
        select_card_ids: list[int] | tuple[int, ...] | set[int] | object = _KEEP_SELECTION,
        focus_card_id: int | None | object = _KEEP_FOCUS,
    ) -> None:
        if focus_card_id is not _KEEP_FOCUS:
            self._focus_card_id = (
                None if focus_card_id is None else int(focus_card_id)
            )

        requested_card_id = (
            int(select_card_id)
            if select_card_id is not None
            else self._selected_card_id()
        )
        if select_card_ids is _KEEP_SELECTION:
            requested_card_ids = self._selected_card_ids()
        else:
            requested_card_ids = [
                int(card_id)
                for card_id in list(select_card_ids or [])
                if card_id is not None
            ]
        if requested_card_id is not None and requested_card_id not in requested_card_ids:
            requested_card_ids.insert(0, requested_card_id)
        expanded_card_ids = self._expanded_card_ids()

        try:
            rows = load_knowledge_tree_nodes(self._addon_dir, self._profile)
        except Exception as exc:
            showInfo(f"Failed to load the knowledge tree:\n{exc}")
            return

        self._rows_cache = list(rows)
        self._row_by_card_id = {int(row["card_id"]): row for row in rows}

        self._building = True
        try:
            self._tree.clear()
            item_by_card_id: dict[int, QTreeWidgetItem] = {}
            for row in rows:
                item_by_card_id[int(row["card_id"])] = self._item_for_row(row)

            for row in rows:
                item = item_by_card_id[int(row["card_id"])]
                parent_card_id = row.get("parent_card_id")
                if parent_card_id is None:
                    self._tree.addTopLevelItem(item)
                else:
                    parent_item = item_by_card_id.get(int(parent_card_id))
                    if parent_item is None:
                        self._tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)

            if expanded_card_ids:
                for card_id in expanded_card_ids:
                    self._set_item_expanded(card_id, True)
            else:
                self._tree.expandToDepth(1)
        finally:
            self._building = False

        if requested_card_ids:
            self._apply_selection(requested_card_ids, anchor_card_id=requested_card_id)
        elif requested_card_id is not None:
            self._select_card_id(requested_card_id)
        elif self._tree.topLevelItemCount():
            self._tree.setCurrentItem(self._tree.topLevelItem(0))
        self._refresh_selection_ui()

    def _set_item_expanded(self, card_id: int, expanded: bool) -> None:
        def visit(item: QTreeWidgetItem) -> bool:
            if int(item.data(0, _ROLE_CARD_ID)) == int(card_id):
                item.setExpanded(expanded)
                return True
            for index in range(item.childCount()):
                if visit(item.child(index)):
                    return True
            return False

        for index in range(self._tree.topLevelItemCount()):
            if visit(self._tree.topLevelItem(index)):
                return

    def _select_card_id(self, card_id: int) -> None:
        self._apply_selection([int(card_id)], anchor_card_id=int(card_id))

    def _apply_selection(
        self,
        card_ids: list[int] | tuple[int, ...] | set[int],
        *,
        anchor_card_id: int | None = None,
    ) -> None:
        normalized_ids: list[int] = []
        seen: set[int] = set()
        for raw_card_id in list(card_ids):
            card_id = int(raw_card_id)
            if card_id in seen:
                continue
            seen.add(card_id)
            normalized_ids.append(card_id)
        if not normalized_ids and anchor_card_id is None:
            return

        self._tree.clearSelection()

        anchor_id = (
            int(anchor_card_id)
            if anchor_card_id is not None
            else int(normalized_ids[0])
        )

        def visit(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if int(item.data(0, _ROLE_CARD_ID)) == int(card_id):
                return item
            for index in range(item.childCount()):
                found = visit(item.child(index))
                if found is not None:
                    return found
            return None

        selected_anchor: QTreeWidgetItem | None = None
        fallback_anchor: QTreeWidgetItem | None = None
        for selected_id in normalized_ids:
            card_id = int(selected_id)
            for index in range(self._tree.topLevelItemCount()):
                found = visit(self._tree.topLevelItem(index))
                if found is None:
                    continue
                parent = found.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                found.setSelected(True)
                if fallback_anchor is None:
                    fallback_anchor = found
                if card_id == anchor_id:
                    selected_anchor = found
                break

        anchor_item = selected_anchor or fallback_anchor
        if anchor_item is not None:
            self._tree.setCurrentItem(anchor_item)
            self._tree.scrollToItem(
                anchor_item,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )

    def _title_for_card_id(self, card_id: int | None) -> str:
        if card_id is None:
            return "Root level"
        row = self._row_by_card_id.get(int(card_id))
        if row is not None:
            return _row_title(row, int(card_id))
        meta = get_card_metadata(
            int(card_id),
            addon_dir=self._addon_dir,
            profile=self._profile,
        ) or {}
        return str(meta.get("title") or f"Card {int(card_id)}")

    def _lineage_text_for_card_id(self, card_id: int | None) -> str:
        if card_id is None:
            return "Lineage: Select a node first."
        lineage_card_ids = ancestor_card_ids(self._rows_cache, int(card_id))
        if not lineage_card_ids:
            return "Lineage: Root level"
        parts = []
        for ancestor_card_id in lineage_card_ids:
            title = html.escape(
                _compact_display_text(self._title_for_card_id(int(ancestor_card_id)))
            )
            parts.append(f'<a href="card:{int(ancestor_card_id)}">{title}</a>')
        return "Lineage: " + " &rarr; ".join(parts)

    def _on_lineage_link_activated(self, href: str) -> None:
        value = str(href or "").strip()
        if not value.startswith("card:"):
            return
        try:
            card_id = int(value.split(":", 1)[1])
        except Exception:
            return
        self._select_card_id(card_id)
        tooltip("Selected ancestor node.")

    def _tree_collapse_all(self) -> None:
        self._tree.collapseAll()
        selected = self._selected_item()
        if selected is not None:
            parent = selected.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()

    def _tree_expand_all(self) -> None:
        self._tree.expandAll()

    def _expand_selected_branch(self) -> None:
        items = self._selected_items()
        if not items:
            return

        def visit(node: QTreeWidgetItem) -> None:
            node.setExpanded(True)
            for index in range(node.childCount()):
                visit(node.child(index))

        for item in items:
            visit(item)

    def _collapse_selected_branch(self) -> None:
        items = self._selected_items()
        if not items:
            return
        anchor = self._selected_item()
        for item in items:
            for index in range(item.childCount()):
                self._collapse_branch_children(item.child(index))
            item.setExpanded(False)
        if anchor is not None:
            self._tree.scrollToItem(anchor, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _collapse_branch_children(self, item: QTreeWidgetItem) -> None:
        for index in range(item.childCount()):
            self._collapse_branch_children(item.child(index))
        item.setExpanded(False)

    def _refresh_selection_ui(self) -> None:
        selected_card_ids = self._selected_card_ids_in_tree_order()
        selected_count = len(selected_card_ids)
        card_id = self._selected_card_id()
        selected_title = self._title_for_card_id(card_id) if card_id is not None else ""
        selected_display_title = _compact_display_text(selected_title)
        parent_card_id = (
            get_parent_card_id(self._addon_dir, self._profile, int(card_id))
            if selected_count == 1 and card_id is not None
            else None
        )
        has_selection = card_id is not None
        has_single_selection = selected_count == 1
        has_parent = parent_card_id is not None

        self._rename_btn.setEnabled(has_single_selection)
        self._remove_btn.setEnabled(has_selection)
        self._priority_btn.setEnabled(has_single_selection)
        self._study_btn.setEnabled(has_single_selection)
        self._subset_btn.setEnabled(has_single_selection)
        self._browser_btn.setEnabled(has_single_selection)
        self._parent_btn.setEnabled(has_parent)
        self._postpone_btn.setEnabled(True)

        self._inspector_study_btn.setEnabled(has_single_selection)
        self._inspector_subset_btn.setEnabled(has_single_selection)
        self._inspector_postpone_btn.setEnabled(True)
        self._inspector_priority_btn.setEnabled(has_single_selection)
        self._inspector_browser_btn.setEnabled(has_single_selection)
        self._inspector_parent_btn.setEnabled(has_parent)
        self._inspector_rename_btn.setEnabled(has_single_selection)
        self._inspector_remove_btn.setEnabled(has_selection)

        self._update_insert_buttons(selected_display_title, selected_count)
        self._update_workspace_summary(selected_display_title, card_id)

        if not has_selection:
            _set_badge_style(
                self._kind_badge,
                "Selection",
                background="rgba(128,128,128,0.14)",
                foreground="palette(text)",
                border="rgba(128,128,128,0.18)",
            )
            self._focus_badge.setVisible(False)
            self._selection_title.setToolTip("")
            self._selection_title.setText("No node selected")
            self._selection_title_scroll.verticalScrollBar().setValue(0)
            self._selection_meta.setText(
                "Select a topic or item to inspect its branch, study that subtree, open priority tools, or add children."
            )
            self._selection_note.setText(
                "Use the toolbar or the add buttons here to create root topics/items. "
                "Once a node is selected, new cards are appended beneath it and you can study or inspect that whole branch."
            )
            empty_summary = describe_branch_summary({})
            self._parent_value.setText("Parent branch: Select a node first.")
            self._lineage_value.setText("Lineage: Select a node first.")
            _set_optional_label_text(
                self._branch_size_value,
                str(empty_summary.get("size_line") or ""),
            )
            _set_optional_label_text(
                self._branch_children_value,
                str(empty_summary.get("children_line") or ""),
            )
            _set_optional_label_text(
                self._branch_depth_value,
                str(empty_summary.get("levels_line") or ""),
            )
            _set_optional_label_text(
                self._branch_priority_value,
                str(empty_summary.get("selected_priority_line") or ""),
            )
            _set_optional_label_text(
                self._branch_range_value,
                str(empty_summary.get("range_line") or ""),
            )
            self._branch_hint.setText(str(empty_summary.get("impact_line") or ""))
            return

        if selected_count > 1:
            topic_count = 0
            item_count = 0
            for selected_card_id in selected_card_ids:
                row = self._row_by_card_id.get(int(selected_card_id), {})
                if normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC) == NODE_KIND_TOPIC:
                    topic_count += 1
                else:
                    item_count += 1

            _set_badge_style(
                self._kind_badge,
                f"{selected_count} Selected",
                background="rgba(74,122,181,0.18)",
                foreground="palette(text)",
                border="rgba(74,122,181,0.30)",
            )
            if self._focus_card_id is not None and int(self._focus_card_id) in set(selected_card_ids):
                _set_badge_style(
                    self._focus_badge,
                    "Focused Included",
                    background="rgba(74,122,181,0.18)",
                    foreground="palette(text)",
                    border="rgba(74,122,181,0.30)",
                )
            else:
                self._focus_badge.setVisible(False)

            anchor_title = _compact_display_text(self._title_for_card_id(card_id))
            self._selection_title.setText(f"{selected_count} nodes selected")
            self._selection_title.setToolTip("")
            self._selection_title_scroll.verticalScrollBar().setValue(0)
            meta_parts = []
            if topic_count:
                meta_parts.append(f"{topic_count} topic{'' if topic_count == 1 else 's'}")
            if item_count:
                meta_parts.append(f"{item_count} item{'' if item_count == 1 else 's'}")
            meta_parts.append(f"anchor: {anchor_title}")
            self._selection_meta.setText("  ·  ".join(meta_parts))
            self._selection_note.setText(
                "Multi-selection is enabled. Remove, expand, and collapse apply to every selected node. "
                "Single-node actions like Rename, Priority, Study Branch, Subset Review, Browser, and Parent require exactly one selection."
            )
            self._parent_value.setText("Parent branch: Single-node actions require exactly one selected node.")
            self._lineage_value.setText(f"Anchor lineage: {self._lineage_text_for_card_id(card_id).replace('Lineage: ', '')}")
            _set_optional_label_text(
                self._branch_size_value,
                f"Selected nodes: {selected_count}"
            )
            _set_optional_label_text(
                self._branch_children_value,
                f"Topics: {topic_count}  ·  Items: {item_count}"
            )
            _set_optional_label_text(
                self._branch_depth_value,
                "Branch depth and priority summaries are shown for a single selected branch."
            )
            _set_optional_label_text(self._branch_priority_value, "")
            _set_optional_label_text(self._branch_range_value, "")
            self._branch_hint.setText(
                "Use Cmd/Ctrl-click or Shift-click to refine the selection, or keep one node selected to inspect a single branch in detail."
            )
            return

        meta = get_card_metadata(
            int(card_id),
            addon_dir=self._addon_dir,
            profile=self._profile,
        ) or {}
        row = self._row_by_card_id.get(int(card_id), {})
        node_kind = normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC)
        stats = subtree_priority_stats(
            self._addon_dir,
            self._profile,
            int(card_id),
        )

        if node_kind == NODE_KIND_TOPIC:
            _set_badge_style(self._kind_badge, "Topic", background="#2aa84a")
        else:
            _set_badge_style(self._kind_badge, "Item", background="#2d7ff9")

        if self._focus_card_id is not None and int(card_id) == int(self._focus_card_id):
            _set_badge_style(
                self._focus_badge,
                "Focused Card",
                background="rgba(74,122,181,0.18)",
                foreground="palette(text)",
                border="rgba(74,122,181,0.30)",
            )
        else:
            self._focus_badge.setVisible(False)

        full_title = str(meta.get("title") or selected_title or f"Card {card_id}")
        self._selection_title.setText(full_title)
        self._selection_title.setToolTip(full_title)
        self._selection_title_scroll.verticalScrollBar().setValue(0)
        meta_parts = [f"card {card_id}"]
        if meta.get("deck_name"):
            meta_parts.append(str(meta["deck_name"]))
        if meta.get("note_type_name"):
            meta_parts.append(str(meta["note_type_name"]))
        self._selection_meta.setText("  ·  ".join(meta_parts))

        current_priority = stats.get("selected_priority")
        if current_priority is None:
            current_priority = meta.get("priority")
        priority_summary = _priority_text(current_priority) or "Default"
        self._selection_note.setText(
            f"{_kind_label(node_kind)} node with priority {priority_summary}. "
            "Use Study Branch to review only this subtree, Subset Review to inspect every card in detail, "
            "Postpone to delay cards in this branch, or branch tools to spread, randomize, or focus its priority."
        )

        parent_text = (
            _compact_display_text(self._title_for_card_id(parent_card_id))
            if has_parent
            else "Root level"
        )
        summary = describe_branch_summary(stats)
        self._parent_value.setText(f"Parent branch: {parent_text}")
        self._lineage_value.setText(self._lineage_text_for_card_id(card_id))
        _set_optional_label_text(
            self._branch_size_value,
            str(summary.get("size_line") or ""),
        )
        _set_optional_label_text(
            self._branch_children_value,
            str(summary.get("children_line") or ""),
        )
        _set_optional_label_text(
            self._branch_depth_value,
            str(summary.get("levels_line") or ""),
        )
        _set_optional_label_text(
            self._branch_priority_value,
            str(summary.get("selected_priority_line") or ""),
        )
        _set_optional_label_text(
            self._branch_range_value,
            str(summary.get("range_line") or ""),
        )
        self._branch_hint.setText(str(summary.get("impact_line") or ""))

    def _update_insert_buttons(self, selected_title: str, selected_count: int) -> None:
        if selected_title:
            self._inspector_topic_btn.setText("Add Topic Child")
            self._inspector_item_btn.setText("Add Item Child")
            if selected_count > 1:
                self._insert_target_label.setText(
                    f"New cards will be inserted under the anchor node: {selected_title}"
                )
            else:
                self._insert_target_label.setText(
                    f"New cards will be inserted under: {selected_title}"
                )
            self._topic_btn.setToolTip(
                f"Create or link a topic under {selected_title}. Use the menu arrow to link an existing card."
            )
            self._item_btn.setToolTip(
                f"Create or link an item under {selected_title}. Use the menu arrow to link an existing card."
            )
        else:
            self._inspector_topic_btn.setText("Add Root Topic")
            self._inspector_item_btn.setText("Add Root Item")
            self._insert_target_label.setText(
                "No node selected. New topics/items will be inserted at the root level."
            )
            self._topic_btn.setToolTip(
                "Create or link a root topic in the knowledge tree."
            )
            self._item_btn.setToolTip(
                "Create or link a root item in the knowledge tree."
            )

    def _update_workspace_summary(self, selected_title: str, selected_card_id: int | None) -> None:
        total = len(self._rows_cache)
        root_count = sum(1 for row in self._rows_cache if row.get("parent_card_id") is None)
        if total:
            self._workspace_summary.setText(
                f"{total} linked card{'s' if total != 1 else ''} across "
                f"{root_count} root branch{'' if root_count == 1 else 'es'}."
            )
        else:
            self._workspace_summary.setText(
                "The tree is empty. Start by adding a root topic or item."
            )

        if selected_title:
            self._workspace_context.setText(
                f"Insertion target: {selected_title}. New nodes from the toolbar will become children of the current selection."
            )
        else:
            self._workspace_context.setText(
                "Insertion target: root level. Select an existing node if you want to append children instead."
            )

        if self._focus_card_id is None:
            self._workspace_focus.setText("")
            return

        focus_title = _compact_display_text(self._title_for_card_id(self._focus_card_id))
        if selected_card_id is not None and int(selected_card_id) == int(self._focus_card_id):
            self._workspace_focus.setText("Focused card is currently selected.")
        else:
            self._workspace_focus.setText(f"Focused card in this workspace: {focus_title}")

    def _start_edit(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        self._tree.editItem(item, 0)

    def _rename_selected_node(self) -> None:
        if self._single_selected_card_id() is None:
            tooltip("Select exactly one knowledge-tree node to rename it.")
            return
        item = self._selected_item()
        if item is None:
            return
        self._start_edit(item)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._building or column != 0:
            return
        card_id = item.data(0, _ROLE_CARD_ID)
        if card_id is None:
            return
        previous_title = str(item.data(0, _ROLE_BASE_TITLE) or "").strip()
        new_title = item.text(0).strip()

        if not new_title:
            self._building = True
            try:
                item.setText(0, previous_title)
            finally:
                self._building = False
            tooltip("Knowledge-tree titles cannot be empty.")
            return

        if new_title == previous_title:
            return

        try:
            saved_title = rename_card_title(int(card_id), new_title)
        except Exception as exc:
            self._building = True
            try:
                item.setText(0, previous_title)
            finally:
                self._building = False
            showInfo(f"Failed to rename the linked card:\n{exc}")
            return

        item.setData(0, _ROLE_BASE_TITLE, saved_title)
        tooltip("Knowledge-tree node renamed.")
        self.reload(select_card_id=int(card_id))

    def _create_node(self, node_kind: str) -> None:
        kind = normalize_node_kind(node_kind)
        parent_card_id = self._selected_parent_card_id_for_insert()
        dlg = _CreateNodeDialog(kind, parent_card_id=parent_card_id, parent=self)
        if not dlg.exec():
            return

        parent_label = ""
        if parent_card_id is not None:
            parent_label = self._title_for_card_id(parent_card_id)
        metadata = build_incremento_metadata(
            source_type="Knowledge Tree",
            source_title=dlg.title,
            parent=parent_label,
            parent_card_id=parent_card_id,
        )

        try:
            card_id = create_card_for_node(
                dlg.note_type_name,
                dlg.deck_name,
                dlg.title,
                kind,
                field_values=dlg.field_values,
                metadata=metadata,
            )
            link_card_to_tree(
                self._addon_dir,
                self._profile,
                card_id,
                kind,
                parent_card_id=parent_card_id,
            )
        except Exception as exc:
            showInfo(f"Failed to create the knowledge-tree card:\n{exc}")
            return

        self.reload(select_card_id=card_id)
        tooltip(f"{_kind_label(kind)} created and linked into the knowledge tree.")

    def _link_node(self, node_kind: str) -> None:
        kind = normalize_node_kind(node_kind)
        selected_card_id = self._selected_card_id()
        existing = {
            int(row["card_id"])
            for row in load_knowledge_tree_nodes(
                self._addon_dir,
                self._profile,
                cleanup_missing=False,
            )
        }
        dlg = _LinkExistingDialog(
            existing,
            has_selected_node=selected_card_id is not None,
            parent=self,
        )
        if not dlg.exec():
            return

        card_ids = dlg.selected_card_ids
        if not card_ids:
            return

        placement_mode = dlg.placement_mode
        parent_card_id = selected_card_id
        insert_after_card_id = None
        if placement_mode == LINK_PLACEMENT_SIBLINGS:
            if selected_card_id is None:
                showInfo("Select a node before linking existing cards at the same level.")
                return
            parent_card_id = get_parent_card_id(
                self._addon_dir,
                self._profile,
                int(selected_card_id),
            )
            insert_after_card_id = int(selected_card_id)

        try:
            result = link_cards_to_tree(
                self._addon_dir,
                self._profile,
                card_ids,
                kind,
                parent_card_id=parent_card_id,
                insert_after_card_id=insert_after_card_id,
            )
        except Exception as exc:
            showInfo(f"Failed to link the selected cards:\n{exc}")
            return

        linked_card_ids = list(result.get("linked_card_ids") or [])
        if linked_card_ids:
            self.reload(select_card_id=int(linked_card_ids[0]))
        else:
            self.reload(select_card_id=selected_card_id)

        linked_count = int(result.get("linked_count") or 0)
        error_count = int(result.get("error_count") or 0)
        kind_label = _kind_label(kind).lower()
        if linked_count and not error_count:
            noun = kind_label if linked_count == 1 else f"{kind_label}s"
            tooltip(f"{linked_count} existing {noun} linked.")
            return
        if linked_count and error_count:
            noun = kind_label if linked_count == 1 else f"{kind_label}s"
            showInfo(
                f"Linked {linked_count} existing {noun}, but {error_count} selection"
                f"{'' if error_count == 1 else 's'} could not be linked.\n\n"
                + "\n".join(
                    f"Card {int(error.get('card_id') or 0)}: {error.get('error') or 'Unknown error'}"
                    for error in list(result.get('errors') or [])[:10]
                )
            )
            return
        errors = list(result.get("errors") or [])
        details = "\n".join(
            f"Card {int(error.get('card_id') or 0)}: {error.get('error') or 'Unknown error'}"
            for error in errors[:10]
        )
        showInfo("No selected cards could be linked." + (f"\n\n{details}" if details else ""))

    def _remove_selected_node(self) -> None:
        card_ids = self._selected_card_ids_in_tree_order()
        if not card_ids:
            return

        try:
            removed_count = 0
            for card_id in reversed(card_ids):
                if delete_knowledge_tree_node(self._addon_dir, self._profile, int(card_id)):
                    removed_count += 1
        except Exception as exc:
            showInfo(f"Failed to remove the selected node from the knowledge tree:\n{exc}")
            return

        if not removed_count:
            return
        self.reload()
        tooltip(
            f"Removed {removed_count} node{'' if removed_count == 1 else 's'} from the knowledge tree."
        )

    def _change_selected_priority(self) -> None:
        card_id = self._single_selected_card_id()
        if card_id is None:
            tooltip("Select exactly one knowledge-tree node to change its priority.")
            return
        meta = get_card_metadata(
            int(card_id),
            addon_dir=self._addon_dir,
            profile=self._profile,
        ) or {}
        priority_context = get_card_priority_context(
            self._addon_dir,
            self._profile,
            int(card_id),
        )
        stats = subtree_priority_stats(
            self._addon_dir,
            self._profile,
            int(card_id),
        )
        dlg = KnowledgeTreePriorityDialog(
            card_label=str(meta.get("title") or f"Card {card_id}"),
            current_priority=float(priority_context.get("priority") or 50.0),
            subtree_stats=stats,
            current_a_factor=priority_context.get("a_factor"),
            current_interval=priority_context.get("interval"),
            lower_is_more_important=configured_priority_lower_is_more_important(),
            parent=self,
        )
        if not dlg.exec():
            return

        changed_count = 0
        try:
            if dlg.operation == OP_SET_SELECTED:
                set_selected_card_priority(
                    self._addon_dir,
                    self._profile,
                    int(card_id),
                    dlg.selected_priority,
                    a_factor=dlg.selected_a_factor,
                )
                changed_count = 1
            elif dlg.operation == OP_SHIFT_SUBTREE:
                changed_count = shift_subtree_priorities(
                    self._addon_dir,
                    self._profile,
                    int(card_id),
                    dlg.operation_payload.get("delta", 0.0),
                    include_root=True,
                )
            elif dlg.operation == OP_LINEAR_SPREAD:
                changed_count = spread_subtree_priorities(
                    self._addon_dir,
                    self._profile,
                    int(card_id),
                    dlg.operation_payload.get("start_priority", 50.0),
                    dlg.operation_payload.get("end_priority", 50.0),
                    include_root=bool(dlg.operation_payload.get("include_root")),
                )
            elif dlg.operation == OP_RANDOMIZE:
                changed_count = randomize_subtree_priorities(
                    self._addon_dir,
                    self._profile,
                    int(card_id),
                    dlg.operation_payload.get("minimum_priority", 0.0),
                    dlg.operation_payload.get("maximum_priority", 100.0),
                    include_root=bool(dlg.operation_payload.get("include_root")),
                )
            elif dlg.operation == OP_FOCUS_BRANCH:
                changed_count = focus_subtree_priorities(
                    self._addon_dir,
                    self._profile,
                    int(card_id),
                    lower_is_more_important=configured_priority_lower_is_more_important(),
                )
            elif dlg.operation == OP_FADE_CHILDREN:
                changed_count = fade_child_priorities(
                    self._addon_dir,
                    self._profile,
                    int(card_id),
                    lower_is_more_important=configured_priority_lower_is_more_important(),
                )
        except Exception as exc:
            showInfo(f"Failed to update knowledge-tree priorities:\n{exc}")
            return

        self.reload(select_card_id=int(card_id))
        if changed_count:
            tooltip(
                f"Updated priority on {changed_count} knowledge-tree "
                f"card{'' if changed_count == 1 else 's'}."
            )

    def _study_selected_branch(self) -> None:
        card_id = self._single_selected_card_id()
        if card_id is None:
            tooltip("Select exactly one knowledge-tree node to study its branch.")
            return

        handler = self._open_branch_study
        if handler is None:
            try:
                from ..backend.knowledge_tree import build_branch_study_scope
                from ..backend.session import learnFunction
            except ImportError:
                from knowledge_tree import build_branch_study_scope  # type: ignore
                from session import learnFunction  # type: ignore

            def _default_branch_study(target_card_id: int) -> None:
                branch_scope = build_branch_study_scope(
                    self._addon_dir,
                    self._profile,
                    int(target_card_id),
                )
                if not branch_scope:
                    raise RuntimeError("Could not resolve the selected subtree.")
                learnFunction(branch_scope=branch_scope)

            handler = _default_branch_study

        try:
            handler(int(card_id))
        except Exception as exc:
            showInfo(f"Could not open the branch study session:\n{exc}")

    def _open_subset_review_dialog(self) -> None:
        card_id = self._single_selected_card_id()
        if card_id is None:
            tooltip("Select exactly one knowledge-tree node to open subset review.")
            return

        dlg = KnowledgeTreeSubsetDialog(
            self._addon_dir,
            profile=self._profile,
            root_card_id=int(card_id),
            reveal_in_tree=self._reveal_card_from_subset,
            parent=self,
        )

        def _forget_dialog(*_args) -> None:
            try:
                self._subset_review_dialogs.remove(dlg)
            except ValueError:
                pass

        self._subset_review_dialogs.append(dlg)
        qconnect(dlg.finished, _forget_dialog)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _reveal_card_from_subset(self, card_id: int) -> None:
        self.reload(select_card_id=int(card_id), focus_card_id=int(card_id))
        self.show()
        self.raise_()
        self.activateWindow()

    def _open_postpone_dialog(self) -> None:
        browser_card_ids = resolve_current_browser_card_ids()
        dlg = KnowledgeTreePostponeDialog(
            self._addon_dir,
            profile=self._profile,
            branch_root_card_id=self._selected_card_id(),
            browser_card_ids=browser_card_ids,
            parent=self,
        )
        if dlg.exec():
            self.reload(select_card_id=self._selected_card_id())

    def _go_to_parent(self) -> None:
        card_id = self._single_selected_card_id()
        if card_id is None:
            tooltip("Select exactly one knowledge-tree node to jump to its parent.")
            return
        parent_card_id = get_parent_card_id(
            self._addon_dir,
            self._profile,
            int(card_id),
        )
        if parent_card_id is None:
            tooltip("Selected node is already at the top of the knowledge tree.")
            return
        self._select_card_id(int(parent_card_id))
        tooltip("Selected the parent node.")

    def _open_selected_in_browser(self) -> None:
        card_id = self._single_selected_card_id()
        if card_id is None:
            tooltip("Select exactly one knowledge-tree node to open it in Browser.")
            return
        meta = get_card_metadata(
            int(card_id),
            addon_dir=self._addon_dir,
            profile=self._profile,
        ) or {}
        note_id = int(meta.get("note_id") or 0)
        if not note_id:
            showInfo("Could not find the linked note for this knowledge-tree node.")
            return
        try:
            from aqt import dialogs

            browser = dialogs.open("Browser", mw)
            browser.search_for(f"nid:{note_id}")
        except Exception as exc:
            showInfo(f"Could not open the Browser for this node:\n{exc}")
