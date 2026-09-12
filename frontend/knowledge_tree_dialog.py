from __future__ import annotations

import html
import math
import os
import re
from typing import Callable, cast

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
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
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTabWidget,
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
from PyQt6.QtCore import QRect, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

try:
    from ..backend.priority_manager import configured_priority_lower_is_more_important
except ImportError:
    from priority_manager import configured_priority_lower_is_more_important  # type: ignore

try:
    from ..backend.note_metadata import build_incremento_metadata, visible_field_names
except ImportError:
    from note_metadata import build_incremento_metadata, visible_field_names  # type: ignore

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
        resolve_card_pdf_target,
        save_knowledge_tree_rows,
        search_knowledge_tree_nodes,
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
        resolve_card_pdf_target,
        save_knowledge_tree_rows,
        search_knowledge_tree_nodes,
        search_linkable_cards,
        set_selected_card_priority,
        shift_subtree_priorities,
        spread_subtree_priorities,
        subtree_priority_stats,
    )


_ROLE_CARD_ID = int(Qt.ItemDataRole.UserRole)
_ROLE_NODE_KIND = _ROLE_CARD_ID + 1
_ROLE_BASE_TITLE = _ROLE_CARD_ID + 2
_ROLE_PRIORITY_VALUE = _ROLE_CARD_ID + 3
_KEEP_FOCUS = object()
_KEEP_SELECTION = object()
_ICON_CACHE: dict[str, QIcon] = {}
_COMPACT_TOOLBAR_WIDTH = 560
_VERTICAL_SPLITTER_WIDTH = 760
_DISPLAY_TITLE_LIMIT = 180
_DEFAULT_PRIORITY_THRESHOLDS = (33.0, 67.0)


def _priority_text(value) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.0f}"
    except Exception:
        return ""


def _secondary_text_color(palette: QPalette) -> str:
    """Keep supporting labels readable against the active panel background."""
    foreground = palette.color(QPalette.ColorRole.Text)
    background = palette.color(QPalette.ColorRole.Base)
    weight = 0.8
    return QColor(
        round(foreground.red() * weight + background.red() * (1 - weight)),
        round(foreground.green() * weight + background.green() * (1 - weight)),
        round(foreground.blue() * weight + background.blue() * (1 - weight)),
    ).name()


def _readable_icon(icon: QIcon, palette: QPalette) -> QIcon:
    """Tint monochrome action icons to the current theme's text color."""
    original = icon.pixmap(20, 20)
    if original.isNull():
        return icon
    pixmap = QPixmap(original.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.drawPixmap(0, 0, original)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), palette.color(QPalette.ColorRole.Text))
    painter.end()
    return QIcon(pixmap)


def _toolbar_glyph_icon(glyph: str, palette: QPalette) -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = palette.color(QPalette.ColorRole.Text)
    if glyph == "play":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        path = QPainterPath()
        path.moveTo(6, 4)
        path.lineTo(16, 10)
        path.lineTo(6, 16)
        path.closeSubpath()
        painter.drawPath(path)
    elif glyph == "add":
        pen = QPen(color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(10, 4, 10, 16)
        painter.drawLine(4, 10, 16, 10)
    painter.end()
    return QIcon(pixmap)


def _priority_indicator(
    value,
    *,
    lower_is_more_important: bool,
    thresholds: tuple[float, float] = _DEFAULT_PRIORITY_THRESHOLDS,
) -> tuple[int, str] | None:
    low, high = thresholds
    if not 0 <= low < high <= 100:
        raise ValueError("Priority thresholds must be ordered within 0–100.")
    try:
        priority = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(priority):
        return None
    urgency = max(0, min(100, 100 - priority if lower_is_more_important else priority))
    color = (
        "#2aa84a" if urgency < low else
        "#d49a35" if urgency < high else
        "#d85b55"
    )
    return round(urgency), color


def _plain_card_field(value: str) -> str:
    raw = re.sub(r"(?i)<br\s*/?>|</p\s*>|</div\s*>", "\n", str(value or ""))
    raw = re.sub(r"<[^>]*>", " ", raw)
    return "\n".join(
        " ".join(html.unescape(line).split()) for line in raw.splitlines()
    ).strip()


def _card_detail_text_and_source(note, pdf_target: dict | None) -> tuple[str, str]:
    try:
        fields = list((note.note_type() or {}).get("flds") or [])
    except Exception:
        fields = []
    names = visible_field_names([
        str(field.get("name") or "") for field in fields if isinstance(field, dict)
    ])
    values = []
    for name in names:
        try:
            value = _plain_card_field(note[name])
        except Exception:
            value = ""
        if value:
            values.append(value)

    def provenance(name: str) -> str:
        try:
            return _plain_card_field(note[name])
        except Exception:
            return ""

    source_title = (
        provenance("Incremento_Source_Title") or provenance("Incremento_Source_Link")
    )
    author = provenance("Incremento_Source_Author")
    source = " — ".join(part for part in (source_title, author) if part)
    if source and pdf_target and pdf_target.get("has_inline_citation") and pdf_target.get("page"):
        source += f", p. {pdf_target['page']}"
    if not source and pdf_target and pdf_target.get("kind") == "pdf":
        filename = os.path.basename(str(pdf_target.get("filename") or ""))
        page = pdf_target.get("page")
        source = f"{filename}, p. {page}" if filename and page else filename
    return "\n\n".join(values), source or "—"


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


def _open_pdf_action_state(
    selected_count: int,
    pdf_target: dict[str, str | int | bool] | None,
) -> tuple[bool, str]:
    if int(selected_count) <= 0:
        return False, "Select exactly one knowledge-tree node to open its linked PDF."
    if int(selected_count) != 1:
        return False, "Open PDF is available only when exactly one knowledge-tree node is selected."
    if not pdf_target or str(pdf_target.get("kind") or "").strip() != "pdf":
        return False, "Selected node does not link to a PDF."
    return True, "Open the linked PDF in the existing PDF dock."


class _KnowledgeTreeWidget(QTreeWidget):
    def __init__(self, on_drop_persist: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_drop_persist = on_drop_persist

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self._on_drop_persist()


class _PriorityDelegate(QStyledItemDelegate):
    def __init__(
        self,
        *,
        lower_is_more_important: bool,
        thresholds: tuple[float, float],
        parent=None,
    ):
        super().__init__(parent)
        self._lower_is_more_important = lower_is_more_important
        self._thresholds = thresholds

    def paint(self, painter, option, index) -> None:
        background_option = QStyleOptionViewItem(option)
        self.initStyleOption(background_option, index)
        background_option.text = ""
        style = (
            background_option.widget.style()
            if background_option.widget else QApplication.style()
        )
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            background_option,
            painter,
            background_option.widget,
        )
        value = index.data(_ROLE_PRIORITY_VALUE)
        indicator = _priority_indicator(
            value,
            lower_is_more_important=self._lower_is_more_important,
            thresholds=self._thresholds,
        )
        if indicator is None:
            return
        urgency, color = indicator
        painter.save()
        rect = option.rect
        bar_width = 58
        bar_rect = QRect(rect.left() + 8, rect.center().y() - 3, bar_width, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#454545"))
        painter.drawRoundedRect(bar_rect, 3, 3)
        if urgency > 0:
            fill = QRect(bar_rect)
            fill.setWidth(max(2, round(bar_width * urgency / 100)))
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(fill, 3, 3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        text_color = option.palette.highlightedText() if selected else option.palette.text()
        painter.setPen(text_color.color())
        number_rect = QRect(
            bar_rect.right() + 8,
            rect.top(),
            max(30, rect.right() - bar_rect.right() - 14),
            rect.height(),
        )
        painter.drawText(
            number_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""),
        )
        painter.restore()


class _ToolbarMenuButton(QToolButton):
    """Draw a centered menu cue instead of Qt's platform-dependent corner arrow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_menu: QMenu | None = None
        qconnect(self.clicked, self._show_popup_menu)

    def setMenu(self, menu: QMenu) -> None:
        self._popup_menu = menu

    def menu(self) -> QMenu | None:
        return self._popup_menu

    def _show_popup_menu(self) -> None:
        if self._popup_menu is not None:
            self._popup_menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.palette().color(QPalette.ColorRole.ButtonText), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        center_x, center_y = self.width() - 15, self.height() // 2
        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)
        painter.end()


class _SearchLineEdit(QLineEdit):
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


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
        priority_thresholds: tuple[float, float] = _DEFAULT_PRIORITY_THRESHOLDS,
        open_priority_for_card=None,
        open_branch_study=None,
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._profile = str(profile or active_profile()).strip() or active_profile()
        self._open_priority_for_card = open_priority_for_card
        self._open_branch_study = open_branch_study
        _priority_indicator(50, lower_is_more_important=True, thresholds=priority_thresholds)
        self._priority_thresholds = priority_thresholds
        self._building = False
        self._initial_select_card_id = None if select_card_id is None else int(select_card_id)
        self._focus_card_id = (
            int(focus_card_id)
            if focus_card_id is not None
            else self._initial_select_card_id
        )
        self._rows_cache: list[dict] = []
        self._row_by_card_id: dict[int, dict] = {}
        self._search_results_cache: list[dict] = []
        self._updating_search_results = False
        self._subset_review_dialogs: list[KnowledgeTreeSubsetDialog] = []
        self._toolbar_buttons: list[QToolButton] = []
        self._toolbar_button_labels: dict[QToolButton, str] = {}
        self._toolbar_button_tooltips: dict[QToolButton, str] = {}
        self._toolbar_compact: bool | None = None
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
        close_btn.setIcon(_readable_icon(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogCloseButton),
            self.palette(),
        ))
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
        self._update_breadcrumb()

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
        style = (
            """
            QFrame#KnowledgePanel, QFrame#KnowledgeInspector, QFrame#KnowledgeSectionCard {
              background: palette(base);
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 10px;
            }
            QFrame#KnowledgeToolbar {
              border: none;
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
              color: __SECONDARY_TEXT__;
              font-size: 11px;
            }
            QLabel#KnowledgeBreadcrumb {
              color: __SECONDARY_TEXT__;
              font-size: 12px;
              padding: 2px 4px;
            }
            QFrame#KnowledgeDetailDivider {
              color: rgba(128,128,128,0.25);
            }
            QTabWidget#KnowledgeTabs::pane {
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 8px;
            }
            QTabBar::tab {
              padding: 7px 14px;
            }
            QLabel#KnowledgeHint {
              color: __SECONDARY_TEXT__;
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
            QListWidget#KnowledgeSearchResults {
              background: palette(base);
              border: 1px solid rgba(128,128,128,0.20);
              border-radius: 10px;
              padding: 4px;
            }
            QListWidget#KnowledgeSearchResults::item {
              padding: 6px 8px;
            }
            QListWidget#KnowledgeSearchResults::item:selected {
              background: rgba(74,122,181,0.24);
            }
            QLineEdit#KnowledgeSearchEdit {
              padding: 6px 8px;
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
            QToolButton#KnowledgeToolbarButton[hasPopup="true"] {
              padding-right: 29px;
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
        self.setStyleSheet(style.replace("__SECONDARY_TEXT__", _secondary_text_color(self.palette())))

    def _build_toolbar(self, outer: QVBoxLayout) -> None:
        toolbar = QFrame(self)
        toolbar.setObjectName("KnowledgeToolbar")
        toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        self._study_btn = self._build_toolbar_button(
            "Study",
            _toolbar_glyph_icon("play", self.palette()),
            self._study_selected_branch,
            tool_tip="Open the learning dialog and study only this subtree.",
        )
        self._add_btn = _ToolbarMenuButton(toolbar)
        self._add_btn.setObjectName("KnowledgeToolbarButton")
        self._add_btn.setProperty("hasPopup", True)
        self._add_btn.setText("Add")
        self._add_btn.setIcon(_toolbar_glyph_icon("add", self.palette()))
        self._add_btn.setIconSize(QSize(18, 18))
        self._add_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._add_btn.setToolTip("Add a topic or item under the selected node.")
        add_menu = QMenu(self._add_btn)
        self._add_topic_action = QAction(_kind_icon(NODE_KIND_TOPIC), "Add Topic Child", add_menu)
        self._add_item_action = QAction(_kind_icon(NODE_KIND_ITEM), "Add Item Child", add_menu)
        qconnect(self._add_topic_action.triggered, lambda _checked=False: self._create_node(NODE_KIND_TOPIC))
        qconnect(self._add_item_action.triggered, lambda _checked=False: self._create_node(NODE_KIND_ITEM))
        add_menu.addAction(self._add_topic_action)
        add_menu.addAction(self._add_item_action)
        self._add_btn.setMenu(add_menu)
        self._register_toolbar_button(self._add_btn, "Add")

        self._search_edit = _SearchLineEdit(toolbar)
        self._search_edit.setObjectName("KnowledgeSearchEdit")
        self._search_edit.setPlaceholderText("Search this tree…")
        search_palette = self._search_edit.palette()
        search_palette.setColor(
            QPalette.ColorRole.PlaceholderText,
            QColor(_secondary_text_color(self.palette())),
        )
        self._search_edit.setPalette(search_palette)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._refresh_btn = self._build_toolbar_button(
            "Refresh",
            _readable_icon(
                self._standard_icon(QStyle.StandardPixmap.SP_BrowserReload),
                self.palette(),
            ),
            lambda: self.reload(),
            tool_tip="Reload the tree and keep the current selection when possible.",
        )
        toolbar_layout.addWidget(self._study_btn)
        toolbar_layout.addWidget(self._add_btn)
        toolbar_layout.addWidget(self._search_edit, 1)
        toolbar_layout.addWidget(self._refresh_btn)
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
        intro.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(12, 10, 12, 10)
        intro_layout.setSpacing(4)

        intro_content = QWidget(intro)
        intro_content_layout = QVBoxLayout(intro_content)
        intro_content_layout.setContentsMargins(0, 0, 0, 0)
        intro_content_layout.setSpacing(4)

        intro_hint = QLabel(
            "Drag to reorder. Drop onto another node to reparent. Double-click a title to rename. "
            "Cmd/Ctrl-click or Shift-click to multi-select. Right-click a node for branch actions."
        )
        intro_hint.setObjectName("KnowledgeHint")
        intro_hint.setWordWrap(True)
        _allow_label_shrink(intro_hint)
        intro_content_layout.addWidget(intro_hint)

        self._workspace_summary = QLabel("")
        self._workspace_summary.setObjectName("KnowledgeMeta")
        self._workspace_summary.setWordWrap(False)
        self._workspace_summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _allow_label_shrink(self._workspace_summary)

        self._workspace_context = QLabel("")
        self._workspace_context.setObjectName("KnowledgeHint")
        self._workspace_context.setWordWrap(True)
        _allow_label_shrink(self._workspace_context)
        intro_content_layout.addWidget(self._workspace_context)

        self._workspace_focus = QLabel("")
        self._workspace_focus.setObjectName("KnowledgeHint")
        self._workspace_focus.setWordWrap(True)
        _allow_label_shrink(self._workspace_focus)
        intro_content_layout.addWidget(self._workspace_focus)

        intro_layout.addWidget(intro_content)

        search_panel = self._build_search_panel(panel)
        self._tabs = QTabWidget(panel)
        self._tabs.setObjectName("KnowledgeTabs")
        self._tabs.addTab(intro, "Workspace")
        self._tabs.addTab(search_panel, "Search")
        self._tabs.setCornerWidget(self._workspace_summary, Qt.Corner.TopRightCorner)
        layout.addWidget(self._tabs)

        self._breadcrumb = QLabel("Select a node to see its path", panel)
        self._breadcrumb.setObjectName("KnowledgeBreadcrumb")
        self._breadcrumb.setTextFormat(Qt.TextFormat.PlainText)
        self._breadcrumb.setMinimumWidth(0)
        self._breadcrumb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._breadcrumb)

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
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tree.setItemDelegateForColumn(
            1,
            _PriorityDelegate(
                lower_is_more_important=configured_priority_lower_is_more_important(),
                thresholds=self._priority_thresholds,
                parent=self._tree,
            ),
        )
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(1, 122)
        layout.addWidget(self._tree, 1)
        return panel

    def _build_search_panel(self, parent: QWidget) -> QWidget:
        card = QFrame(parent)
        card.setObjectName("KnowledgeSectionCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search_content = QWidget(card)
        search_content_layout = QVBoxLayout(search_content)
        search_content_layout.setContentsMargins(0, 0, 0, 0)
        search_content_layout.setSpacing(8)

        hint = QLabel(
            "Jump to linked cards by title first, then optionally include metadata or visible card text."
        )
        hint.setObjectName("KnowledgeHint")
        hint.setWordWrap(True)
        _allow_label_shrink(hint)
        search_content_layout.addWidget(hint)

        self._search_clear_btn = QPushButton("Clear", card)
        self._search_clear_btn.setObjectName("KnowledgeActionButton")
        self._search_clear_btn.setFixedHeight(34)

        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.setSpacing(12)
        self._search_titles_toggle = QCheckBox("Titles", card)
        self._search_titles_toggle.setChecked(True)
        self._search_metadata_toggle = QCheckBox("Metadata", card)
        self._search_note_text_toggle = QCheckBox("Card text", card)
        scope_row.addWidget(self._search_titles_toggle)
        scope_row.addWidget(self._search_metadata_toggle)
        scope_row.addWidget(self._search_note_text_toggle)
        scope_row.addStretch(1)
        scope_row.addWidget(self._search_clear_btn)
        search_content_layout.addLayout(scope_row)

        self._search_results_label = QLabel("Search is limited to cards already linked into this tree.")
        self._search_results_label.setObjectName("KnowledgeMeta")
        self._search_results_label.setWordWrap(True)
        _allow_label_shrink(self._search_results_label)
        search_content_layout.addWidget(self._search_results_label)

        self._search_results_list = QListWidget(card)
        self._search_results_list.setObjectName("KnowledgeSearchResults")
        self._search_results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._search_results_list.setWordWrap(True)
        self._search_results_list.setUniformItemSizes(False)
        self._search_results_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._search_results_list.setMinimumHeight(0)
        self._search_results_list.setMaximumHeight(120)
        self._search_results_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        search_content_layout.addWidget(self._search_results_list)
        layout.addWidget(search_content)

        qconnect(self._search_edit.textChanged, self._refresh_search_results)
        qconnect(self._search_edit.textEdited, lambda _text: self._tabs.setCurrentIndex(1))
        qconnect(self._search_edit.returnPressed, self._open_first_search_result)
        qconnect(self._search_clear_btn.clicked, self._clear_search)
        qconnect(self._search_titles_toggle.toggled, self._refresh_search_results)
        qconnect(self._search_metadata_toggle.toggled, self._refresh_search_results)
        qconnect(self._search_note_text_toggle.toggled, self._refresh_search_results)
        qconnect(
            self._search_results_list.currentItemChanged,
            lambda current, _previous: self._select_search_result_item(current),
        )
        qconnect(
            self._search_results_list.itemActivated,
            lambda item: self._select_search_result_item(item, focus_tree=True),
        )
        return card

    def _build_inspector_panel(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setObjectName("KnowledgeInspectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        panel = QFrame()
        panel.setObjectName("KnowledgeInspector")
        panel.setMinimumSize(0, 0)
        scroll.setWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        self._kind_badge = QLabel("")
        self._priority_badge = QLabel("")
        self._focus_badge = QLabel("")
        badge_row.addWidget(self._kind_badge)
        badge_row.addWidget(self._priority_badge)
        badge_row.addWidget(self._focus_badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        self._selection_text = QLabel("Select a topic or item to inspect its card text.")
        self._selection_text.setObjectName("KnowledgeInspectorTitle")
        self._selection_text.setTextFormat(Qt.TextFormat.PlainText)
        self._selection_text.setWordWrap(True)
        _allow_label_shrink(self._selection_text)
        layout.addWidget(self._selection_text)
        layout.addStretch(1)

        divider = QFrame(panel)
        divider.setObjectName("KnowledgeDetailDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        metadata = QGridLayout()
        metadata.setContentsMargins(0, 0, 0, 0)
        metadata.setHorizontalSpacing(12)
        metadata.setVerticalSpacing(6)
        card_label = QLabel("Card ID", panel)
        source_label = QLabel("Source", panel)
        card_label.setObjectName("KnowledgeMeta")
        source_label.setObjectName("KnowledgeMeta")
        self._meta_card_id = QLabel("—", panel)
        self._meta_source = QLabel("—", panel)
        self._meta_card_id.setTextFormat(Qt.TextFormat.PlainText)
        self._meta_source.setTextFormat(Qt.TextFormat.PlainText)
        self._meta_source.setWordWrap(True)
        _allow_label_shrink(self._meta_source)
        metadata.addWidget(card_label, 0, 0)
        metadata.addWidget(self._meta_card_id, 0, 1)
        metadata.addWidget(source_label, 1, 0)
        metadata.addWidget(self._meta_source, 1, 1)
        metadata.setColumnStretch(1, 1)
        layout.addLayout(metadata)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._inspect_btn = self._build_action_button(
            "Inspect",
            self._standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
            self._open_selected_in_browser,
        )
        self._more_btn = self._build_action_button(
            "More",
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            self._show_more_menu,
        )
        footer.addWidget(self._inspect_btn)
        footer.addWidget(self._more_btn)
        layout.addLayout(footer)
        return scroll

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

    def _standard_icon(self, pixmap: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(pixmap)

    def _install_context_menu(self) -> None:
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        qconnect(self._tree.customContextMenuRequested, self._show_context_menu)

    def _show_more_menu(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        self._show_context_menu(
            self._tree.visualItemRect(item).center(),
            global_pos=self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()),
        )

    def _show_context_menu(self, pos, *, global_pos=None) -> None:
        clicked_item = self._tree.itemAt(pos)
        if clicked_item is not None and not clicked_item.isSelected():
            self._tree.clearSelection()
            clicked_item.setSelected(True)
            self._tree.setCurrentItem(clicked_item)

        selected_count = len(self._selected_items())
        has_selection = selected_count > 0
        has_single_selection = selected_count == 1
        pdf_target = self._selected_pdf_target(quiet=True) if has_single_selection else None
        open_pdf_enabled, open_pdf_tool_tip = _open_pdf_action_state(selected_count, pdf_target)
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
        open_pdf_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            "Open PDF",
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
        qconnect(open_pdf_action.triggered, lambda _checked=False: self._open_selected_pdf())
        qconnect(parent_action.triggered, lambda _checked=False: self._go_to_parent())
        qconnect(expand_action.triggered, lambda _checked=False: self._expand_selected_branch())
        qconnect(collapse_action.triggered, lambda _checked=False: self._collapse_selected_branch())
        qconnect(remove_action.triggered, lambda _checked=False: self._remove_selected_node())

        rename_action.setEnabled(has_single_selection)
        priority_action.setEnabled(has_single_selection)
        study_action.setEnabled(has_single_selection)
        subset_action.setEnabled(has_single_selection)
        browser_action.setEnabled(has_single_selection)
        open_pdf_action.setEnabled(open_pdf_enabled)
        open_pdf_action.setToolTip(open_pdf_tool_tip)
        open_pdf_action.setStatusTip(open_pdf_tool_tip)
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
        menu.addAction(open_pdf_action)
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
        menu.exec(global_pos or self._tree.viewport().mapToGlobal(pos))

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

    def _selected_pdf_target(
        self,
        *,
        quiet: bool = True,
    ) -> dict[str, str | int | bool] | None:
        card_id = self._single_selected_card_id()
        if card_id is None:
            return None
        try:
            target = resolve_card_pdf_target(
                int(card_id),
                addon_dir=self._addon_dir,
                profile=self._profile,
            )
        except Exception as exc:
            if not quiet:
                showInfo(f"Could not resolve the linked PDF for this knowledge-tree node:\n{exc}")
            return None
        if str((target or {}).get("kind") or "").strip() != "pdf":
            return None
        return target

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
        item.setData(1, _ROLE_PRIORITY_VALUE, row.get("priority"))
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
                None if focus_card_id is None else int(cast(int, focus_card_id))
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
                for card_id in list(cast(list[int] | tuple[int, ...] | set[int], select_card_ids))
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
        self._refresh_search_results()
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

    def _clear_search(self) -> None:
        self._search_edit.clear()

    def _search_scope_options(self) -> dict[str, bool]:
        return {
            "include_title": self._search_titles_toggle.isChecked(),
            "include_metadata": self._search_metadata_toggle.isChecked(),
            "include_note_text": self._search_note_text_toggle.isChecked(),
        }

    def _search_result_secondary_text(self, result: dict) -> str:
        parts = [
            str(result.get("match_reason") or "").strip(),
            str(result.get("deck_name") or "").strip(),
            str(result.get("note_type_name") or "").strip(),
            f"card {int(result['card_id'])}",
        ]
        return "  ·  ".join(part for part in parts if part)

    def _refresh_search_results(self, *_args) -> None:
        query = self._search_edit.text().strip()
        scope = self._search_scope_options()
        if not query:
            self._search_results_cache = []
            self._updating_search_results = True
            try:
                self._search_results_list.clear()
            finally:
                self._updating_search_results = False
            self._search_results_label.setText(
                "Search is limited to cards already linked into this tree."
            )
            self._search_clear_btn.setEnabled(False)
            return

        if not any(scope.values()):
            self._search_results_cache = []
            self._updating_search_results = True
            try:
                self._search_results_list.clear()
            finally:
                self._updating_search_results = False
            self._search_results_label.setText("Enable at least one scope to search the tree.")
            self._search_clear_btn.setEnabled(True)
            return

        try:
            results = search_knowledge_tree_nodes(
                self._addon_dir,
                self._profile,
                query,
                **scope,
                limit=100,
            )
        except Exception as exc:
            self._search_results_cache = []
            self._updating_search_results = True
            try:
                self._search_results_list.clear()
            finally:
                self._updating_search_results = False
            self._search_results_label.setText(f"Search failed: {exc}")
            self._search_clear_btn.setEnabled(True)
            return

        self._search_results_cache = list(results)
        self._updating_search_results = True
        try:
            self._search_results_list.clear()
            for result in results:
                title = str(result.get("title") or "").strip() or f"Card {int(result['card_id'])}"
                secondary = self._search_result_secondary_text(result)
                item = QListWidgetItem(
                    f"{title}  ·  {_kind_label(result.get('node_kind') or NODE_KIND_TOPIC)}\n{secondary}"
                )
                item.setData(_ROLE_CARD_ID, int(result["card_id"]))
                item.setIcon(_kind_icon(result.get("node_kind") or NODE_KIND_TOPIC))
                item.setToolTip(secondary)
                item.setSizeHint(QSize(0, 42))
                self._search_results_list.addItem(item)
        finally:
            self._updating_search_results = False

        count = len(results)
        self._search_results_label.setText(
            f'{count} result{"s" if count != 1 else ""} for "{query}".'
        )
        self._search_clear_btn.setEnabled(True)

    def _select_search_result_item(
        self,
        item: QListWidgetItem | None,
        *,
        focus_tree: bool = False,
    ) -> None:
        if self._updating_search_results or item is None:
            return
        value = item.data(_ROLE_CARD_ID)
        if value is None:
            return
        self._select_card_id(int(value))
        if focus_tree:
            self._tree.setFocus(Qt.FocusReason.OtherFocusReason)

    def _open_first_search_result(self) -> None:
        if not self._search_results_cache:
            return
        first_item = self._search_results_list.item(0)
        if first_item is None:
            return
        self._search_results_list.setCurrentItem(first_item)
        self._select_search_result_item(first_item, focus_tree=True)

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
        selected_count = len(self._selected_card_ids())
        card_id = self._selected_card_id()
        single = selected_count == 1 and card_id is not None
        self._study_btn.setEnabled(single)
        self._inspect_btn.setEnabled(single)
        self._more_btn.setEnabled(selected_count > 0)
        self._add_topic_action.setText("Add Topic Child" if card_id is not None else "Add Root Topic")
        self._add_item_action.setText("Add Item Child" if card_id is not None else "Add Root Item")
        selected_title = self._title_for_card_id(card_id) if card_id is not None else ""
        self._add_btn.setToolTip(
            f"Add a topic or item under {selected_title}."
            if selected_title else "Add a root topic or item."
        )
        self._update_workspace_summary(_compact_display_text(selected_title), card_id)
        self._update_breadcrumb()

        if not single:
            label = f"{selected_count} nodes selected" if selected_count else "No node selected"
            _set_badge_style(
                self._kind_badge,
                "Selection" if not selected_count else f"{selected_count} Selected",
                background="rgba(74,122,181,0.18)",
                foreground="palette(text)",
                border="rgba(74,122,181,0.30)",
            )
            self._priority_badge.setVisible(False)
            self._focus_badge.setVisible(False)
            self._selection_text.setText(label)
            self._meta_card_id.setText("—")
            self._meta_source.setText("—")
            return

        assert card_id is not None
        row = self._row_by_card_id.get(int(card_id), {})
        node_kind = normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC)
        _set_badge_style(
            self._kind_badge,
            _kind_label(node_kind),
            background="#2aa84a" if node_kind == NODE_KIND_TOPIC else "#2d7ff9",
        )
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

        priority = row.get("priority")
        if priority is None:
            meta = get_card_metadata(int(card_id), addon_dir=self._addon_dir, profile=self._profile) or {}
            priority = meta.get("priority")
        indicator = _priority_indicator(
            priority,
            lower_is_more_important=configured_priority_lower_is_more_important(),
            thresholds=self._priority_thresholds,
        )
        _set_badge_style(
            self._priority_badge,
            f"Priority {_priority_text(priority) or '—'}",
            background=indicator[1] if indicator else "rgba(128,128,128,0.28)",
        )

        text, source = "", "—"
        try:
            note = mw.col.get_card(int(card_id)).note()
            text, source = _card_detail_text_and_source(note, self._selected_pdf_target(quiet=True))
        except Exception:
            pass
        self._selection_text.setText(text or selected_title or f"Card {card_id}")
        self._meta_card_id.setText(str(card_id))
        self._meta_source.setText(source)

    def _update_breadcrumb(self) -> None:
        if not hasattr(self, "_breadcrumb"):
            return
        item = self._selected_item()
        if item is None:
            self._breadcrumb.setText("Select a node to see its path")
            self._breadcrumb.setToolTip("")
            return
        labels = []
        while item is not None:
            labels.append(item.text(0))
            item = item.parent()
        labels.reverse()
        full = " › ".join(labels)
        metrics = self._breadcrumb.fontMetrics()
        available = max(100, self._breadcrumb.width() - 24)
        separator_width = metrics.horizontalAdvance(" › ") * max(0, len(labels) - 1)
        segment_width = max(56, (available - separator_width - 28) // max(1, len(labels)))
        segments = [metrics.elidedText(label, Qt.TextElideMode.ElideRight, segment_width) for label in labels]
        self._breadcrumb.setText("📁 " + " › ".join(segments))
        self._breadcrumb.setToolTip(full)

    def _update_workspace_summary(self, selected_title: str, selected_card_id: int | None) -> None:
        total = len(self._rows_cache)
        root_count = sum(1 for row in self._rows_cache if row.get("parent_card_id") is None)
        self._workspace_summary.setText(
            f"{total} card{'s' if total != 1 else ''} · "
            f"{root_count} branch{'es' if root_count != 1 else ''}"
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
                from .session_launcher import learnFunction
            except ImportError:
                from knowledge_tree import build_branch_study_scope  # type: ignore
                from session_launcher import learnFunction  # type: ignore

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

    def _open_selected_pdf(self) -> None:
        selected_count = len(self._selected_card_ids())
        card_id = self._single_selected_card_id()
        pdf_target = self._selected_pdf_target(quiet=False) if card_id is not None else None
        enabled, tool_tip = _open_pdf_action_state(selected_count, pdf_target)
        if not enabled:
            tooltip(tool_tip)
            return

        filename = os.path.basename(str((pdf_target or {}).get("filename") or "").strip())
        if not filename:
            showInfo("Could not resolve the linked PDF for this knowledge-tree node.")
            return

        open_card_id = int((pdf_target or {}).get("card_id") or 0)
        open_page = max(1, int((pdf_target or {}).get("page") or 1))
        has_inline_citation = bool((pdf_target or {}).get("has_inline_citation"))

        try:
            from ..backend.pdf_manager import get_zoom
        except ImportError:
            from pdf_manager import get_zoom  # type: ignore
        try:
            from . import pdf_dock as _pdf_dock_mod
        except ImportError:
            import pdf_dock as _pdf_dock_mod  # type: ignore

        try:
            zoom = float(get_zoom(self._addon_dir, self._profile, open_card_id))
        except Exception:
            zoom = 1.0

        try:
            _pdf_dock_mod.show_pdf_in_dock(
                open_card_id,
                filename,
                open_page,
                zoom,
                via_link=has_inline_citation,
                offer_due_review_prompt=open_card_id > 0,
            )
        except Exception as exc:
            showInfo(f"Could not open the linked PDF:\n{exc}")

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
