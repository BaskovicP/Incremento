from __future__ import annotations

import math
import os
from typing import Callable, Hashable, Iterable

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
    Qt,
    qconnect,
)
from aqt.utils import showInfo
from PyQt6.QtCore import QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t  # type: ignore

try:
    from .knowledge_tree_mind_map_model import (
        SCOPE_SELECTED_BRANCH,
        SCOPE_WHOLE_TREE,
        MindMapLayout,
        MindMapNode,
        build_mind_map_layout,
        directional_node_key,
    )
except ImportError:
    from knowledge_tree_mind_map_model import (  # type: ignore
        SCOPE_SELECTED_BRANCH,
        SCOPE_WHOLE_TREE,
        MindMapLayout,
        MindMapNode,
        build_mind_map_layout,
        directional_node_key,
    )


_MIN_ZOOM = 0.35
_MAX_ZOOM = 2.4
_CANVAS_MARGIN_X = 250.0
_CANVAS_MARGIN_Y = 125.0


def _priority_text(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.0f}"


def _contrast_text(background: QColor) -> QColor:
    luminance = (
        0.2126 * background.redF()
        + 0.7152 * background.greenF()
        + 0.0722 * background.blueF()
    )
    return QColor("#17202a") if luminance > 0.58 else QColor("#ffffff")


class MindMapCanvas(QWidget):
    """Interactive, zoomable mind-map canvas backed by a pure layout model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout: MindMapLayout | None = None
        self._show_priorities = False
        self._zoom = 1.0
        self._base_width = 960.0
        self._base_height = 600.0
        self._offset_x = self._base_width / 2.0
        self._offset_y = self._base_height / 2.0
        self._selected_key: Hashable | None = None
        self._search_matches: set[Hashable] = set()
        self._node_hit_rects: dict[Hashable, QRectF] = {}
        self._fold_hit_rects: dict[int, QRectF] = {}
        self._hovered_key: Hashable | None = None
        self._panning = False
        self._last_pan_position: QPointF | None = None
        self._on_select: Callable[[int | None], None] | None = None
        self._on_toggle_branch: Callable[[int], None] | None = None
        self._on_activate: Callable[[int], None] | None = None
        self._on_pan: Callable[[float, float], None] | None = None
        self._on_scroll: Callable[[float, float], None] | None = None
        self._on_zoom_at: Callable[[float, QPointF], None] | None = None

        self.setObjectName("KnowledgeMindMapCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(t("knowledge_tree_mind_map_canvas"))

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def base_size(self) -> QSize:
        return QSize(round(self._base_width), round(self._base_height))

    @property
    def selected_key(self) -> Hashable | None:
        return self._selected_key

    @property
    def layout_model(self) -> MindMapLayout | None:
        return self._layout

    def set_interaction_handlers(
        self,
        *,
        on_select: Callable[[int | None], None],
        on_toggle_branch: Callable[[int], None],
        on_activate: Callable[[int], None],
        on_pan: Callable[[float, float], None],
        on_scroll: Callable[[float, float], None],
        on_zoom_at: Callable[[float, QPointF], None],
    ) -> None:
        self._on_select = on_select
        self._on_toggle_branch = on_toggle_branch
        self._on_activate = on_activate
        self._on_pan = on_pan
        self._on_scroll = on_scroll
        self._on_zoom_at = on_zoom_at

    def set_mind_map(
        self,
        layout: MindMapLayout,
        *,
        show_priorities: bool,
    ) -> None:
        self._layout = layout
        self._show_priorities = bool(show_priorities)
        xs = [node.x for node in layout.nodes] or [0.0]
        ys = [node.y for node in layout.nodes] or [0.0]
        left = min(xs) - _CANVAS_MARGIN_X
        right = max(xs) + _CANVAS_MARGIN_X
        top = min(ys) - _CANVAS_MARGIN_Y
        bottom = max(ys) + _CANVAS_MARGIN_Y
        self._base_width = max(960.0, right - left)
        self._base_height = max(600.0, bottom - top)
        self._offset_x = -left + max(0.0, (960.0 - (right - left)) / 2.0)
        self._offset_y = -top + max(0.0, (600.0 - (bottom - top)) / 2.0)
        if self._selected_key not in layout.nodes_by_key:
            self._selected_key = layout.center_key
        self._update_canvas_size()
        self.update()

    def set_selected_key(self, key: Hashable | None) -> None:
        if self._layout is None or key not in self._layout.nodes_by_key:
            key = self._layout.center_key if self._layout is not None else None
        self._selected_key = key
        self.update()

    def set_search_matches(self, keys: Iterable[Hashable]) -> None:
        self._search_matches = set(keys)
        self.update()

    def set_zoom(self, value: float) -> None:
        normalized = max(_MIN_ZOOM, min(_MAX_ZOOM, float(value)))
        if math.isclose(normalized, self._zoom, rel_tol=0.0, abs_tol=0.001):
            return
        self._zoom = normalized
        self._update_canvas_size()
        self.update()

    def canvas_position_for_key(self, key: Hashable) -> QPointF | None:
        if self._layout is None:
            return None
        node = self._layout.nodes_by_key.get(key)
        if node is None:
            return None
        x, y = self._point(node)
        return QPointF(x * self._zoom, y * self._zoom)

    def render_pixmap(self) -> QPixmap:
        pixmap = QPixmap(self.base_size)
        pixmap.fill(self.palette().color(QPalette.ColorRole.Base))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_content(painter)
        painter.end()
        return pixmap

    def _update_canvas_size(self) -> None:
        self.setFixedSize(
            max(1, round(self._base_width * self._zoom)),
            max(1, round(self._base_height * self._zoom)),
        )

    def _point(self, node: MindMapNode) -> tuple[float, float]:
        return node.x + self._offset_x, node.y + self._offset_y

    def _base_position(self, event) -> QPointF:
        position = event.position()
        return QPointF(position.x() / self._zoom, position.y() / self._zoom)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Base))
        painter.scale(self._zoom, self._zoom)
        self._paint_content(painter)
        painter.end()

    def _paint_content(self, painter: QPainter) -> None:
        self._node_hit_rects.clear()
        self._fold_hit_rects.clear()
        if self._layout is None:
            return

        nodes = self._layout.nodes_by_key
        for edge in self._layout.edges:
            parent = nodes[edge.parent_key]
            child = nodes[edge.child_key]
            start_x, start_y = self._point(parent)
            end_x, end_y = self._point(child)
            direction = 1 if child.side >= 0 else -1
            if parent.depth == 0:
                start_x += direction * 54.0
            bend = abs(end_x - start_x) * 0.48
            path = QPainterPath()
            path.moveTo(start_x, start_y)
            path.cubicTo(
                start_x + direction * bend,
                start_y,
                end_x - direction * bend,
                end_y,
                end_x,
                end_y,
            )
            pen = QPen(QColor(edge.color), max(1.6, 6.6 - edge.depth * 1.25))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        for node in self._layout.nodes:
            if node.depth > 0:
                self._draw_branch_label(painter, node)
        self._draw_center(painter, nodes[self._layout.center_key])

    def _draw_highlight(self, painter: QPainter, rect: QRectF, node: MindMapNode) -> None:
        if node.key in self._search_matches:
            match = QColor("#ffd54f")
            match.setAlpha(72)
            painter.setBrush(match)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(-4.0, -3.0, 4.0, 3.0), 6.0, 6.0)
        if node.key != self._selected_key:
            return
        dark_background = (
            self.palette().color(QPalette.ColorRole.Base).lightnessF() < 0.5
        )
        color = QColor("#64b5f6" if dark_background else "#1565c0")
        width = 3.0 if self.hasFocus() else 2.0
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, width))
        painter.drawRoundedRect(rect.adjusted(-6.0, -5.0, 6.0, 5.0), 8.0, 8.0)

    def _draw_center(self, painter: QPainter, node: MindMapNode) -> None:
        center_x, center_y = self._point(node)
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(14)
        painter.setFont(font)
        title = node.title
        if self._show_priorities and node.priority is not None:
            title += f"  ·  {t('knowledge_tree_priority_value', value=_priority_text(node.priority))}"
        metrics = painter.fontMetrics()
        width = min(330.0, max(172.0, metrics.horizontalAdvance(title) + 54.0))
        height = 88.0
        rect = QRectF(center_x - width / 2.0, center_y - height / 2.0, width, height)
        self._node_hit_rects[node.key] = rect
        self._draw_highlight(painter, rect, node)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#ffd166"))
        gradient.setColorAt(0.48, QColor("#f6a93b"))
        gradient.setColorAt(1.0, QColor("#e56b6f"))
        painter.setBrush(QBrush(gradient))
        outline = QPen(QColor("#c75b3f"), 3.0)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outline)
        painter.drawEllipse(rect)
        painter.setPen(_contrast_text(QColor("#f6a93b")))
        painter.drawText(
            rect.adjusted(16.0, 10.0, -16.0, -10.0),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            title,
        )
        if node.card_id is not None and node.child_count:
            self._draw_fold_badge(painter, node, rect.right() + 15.0, center_y)

    def _draw_branch_label(self, painter: QPainter, node: MindMapNode) -> None:
        x, y = self._point(node)
        font = QFont(self.font())
        font.setBold(node.depth <= 1)
        font.setPointSize(max(9, 13 - min(node.depth, 4)))
        painter.setFont(font)
        label = node.title
        if self._show_priorities and node.priority is not None:
            label += f"  ·  {t('knowledge_tree_priority_short', value=_priority_text(node.priority))}"
        metrics = painter.fontMetrics()
        text_width = float(metrics.horizontalAdvance(label))
        direction = 1 if node.side >= 0 else -1
        line_end = x + direction * (text_width + 22.0)
        label_x = x + 12.0 if direction > 0 else x - text_width - 12.0
        label_rect = QRectF(
            label_x,
            y - metrics.height() - 5.0,
            text_width + 2.0,
            metrics.height() + 5.0,
        )
        hit_rect = label_rect.united(QRectF(x - 10.0, y - 10.0, 20.0, 20.0))
        self._node_hit_rects[node.key] = hit_rect
        self._draw_highlight(painter, hit_rect, node)

        pen = QPen(QColor(node.color), max(1.4, 4.8 - node.depth * 0.75))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(round(x), round(y), round(line_end), round(y))

        marker_color = QColor("#2aa84a" if node.node_kind == "topic" else "#2d7ff9")
        painter.setBrush(marker_color)
        painter.setPen(QPen(_contrast_text(marker_color), 1.0))
        radius = max(5.0, 8.5 - node.depth * 0.8)
        painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2.0, radius * 2.0))
        marker_font = QFont(self.font())
        marker_font.setBold(True)
        marker_font.setPointSize(max(6, 8 - min(node.depth, 2)))
        painter.setFont(marker_font)
        painter.drawText(
            QRectF(x - radius, y - radius, radius * 2.0, radius * 2.0),
            int(Qt.AlignmentFlag.AlignCenter),
            "T" if node.node_kind == "topic" else "I",
        )

        painter.setFont(font)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(
            label_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label,
        )
        if node.card_id is not None and node.child_count:
            self._draw_fold_badge(painter, node, line_end + direction * 14.0, y)

    def _draw_fold_badge(
        self,
        painter: QPainter,
        node: MindMapNode,
        center_x: float,
        center_y: float,
    ) -> None:
        assert node.card_id is not None
        height = 18.0
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        text = str(node.hidden_descendant_count) if node.collapsed else "−"
        width = max(height, float(painter.fontMetrics().horizontalAdvance(text) + 8))
        rect = QRectF(
            center_x - width / 2.0,
            center_y - height / 2.0,
            width,
            height,
        )
        self._fold_hit_rects[int(node.card_id)] = rect.adjusted(-3.0, -3.0, 3.0, 3.0)
        background = self.palette().color(QPalette.ColorRole.Base)
        painter.setBrush(background)
        painter.setPen(QPen(QColor(node.color), 1.8))
        painter.drawRoundedRect(rect, height / 2.0, height / 2.0)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def _key_at(self, position: QPointF) -> Hashable | None:
        for key, rect in reversed(tuple(self._node_hit_rects.items())):
            if rect.contains(position):
                return key
        return None

    def _fold_card_at(self, position: QPointF) -> int | None:
        for card_id, rect in self._fold_hit_rects.items():
            if rect.contains(position):
                return card_id
        return None

    def _select_key(self, key: Hashable | None) -> None:
        self.set_selected_key(key)
        card_id: int | None = None
        if self._layout is not None and key in self._layout.nodes_by_key:
            card_id = self._layout.nodes_by_key[key].card_id
        if self._on_select is not None:
            self._on_select(card_id)

    def mousePressEvent(self, event) -> None:
        base_position = self._base_position(event)
        fold_card_id = self._fold_card_at(base_position)
        if event.button() == Qt.MouseButton.LeftButton and fold_card_id is not None:
            if self._on_toggle_branch is not None:
                self._on_toggle_branch(fold_card_id)
            event.accept()
            return
        key = self._key_at(base_position)
        if event.button() == Qt.MouseButton.LeftButton and key is not None:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._select_key(key)
            event.accept()
            return
        if event.button() in {Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton}:
            self._panning = True
            self._last_pan_position = event.globalPosition()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._last_pan_position is not None:
            current = event.globalPosition()
            delta = current - self._last_pan_position
            self._last_pan_position = current
            if self._on_pan is not None:
                self._on_pan(delta.x(), delta.y())
            event.accept()
            return

        key = self._key_at(self._base_position(event))
        if key != self._hovered_key:
            self._hovered_key = key
            tooltip_text = ""
            if self._layout is not None and key in self._layout.nodes_by_key:
                node = self._layout.nodes_by_key[key]
                tooltip_text = node.full_title
                if node.hidden_descendant_count:
                    tooltip_text += "\n" + t(
                        "knowledge_tree_mind_map_hidden_nodes",
                        count=node.hidden_descendant_count,
                    )
            self.setToolTip(tooltip_text)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning and event.button() in {
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        }:
            self._panning = False
            self._last_pan_position = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        key = self._key_at(self._base_position(event))
        if self._layout is not None and key in self._layout.nodes_by_key:
            card_id = self._layout.nodes_by_key[key].card_id
            if card_id is not None and self._on_activate is not None:
                self._on_activate(int(card_id))
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        modifiers = event.modifiers()
        zoom_modifier = (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        )
        if modifiers & zoom_modifier and self._on_zoom_at is not None:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self._on_zoom_at(factor, event.position())
            event.accept()
            return
        if modifiers & Qt.KeyboardModifier.ShiftModifier and self._on_scroll is not None:
            self._on_scroll(float(-event.angleDelta().y()), 0.0)
            event.accept()
            return
        event.ignore()

    def keyPressEvent(self, event) -> None:
        directions = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if event.key() in directions and self._layout is not None:
            dx, dy = directions[event.key()]
            current = self._selected_key or self._layout.center_key
            target = directional_node_key(self._layout, current, dx=dx, dy=dy)
            if target is not None:
                self._select_key(target)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Home and self._layout is not None:
            self._select_key(self._layout.center_key)
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Space, Qt.Key.Key_Slash}:
            if self._layout is not None and self._selected_key in self._layout.nodes_by_key:
                node = self._layout.nodes_by_key[self._selected_key]
                if node.card_id is not None and node.child_count and self._on_toggle_branch:
                    self._on_toggle_branch(int(node.card_id))
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if self._layout is not None and self._selected_key in self._layout.nodes_by_key:
                card_id = self._layout.nodes_by_key[self._selected_key].card_id
                if card_id is not None and self._on_activate is not None:
                    self._on_activate(int(card_id))
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()


class KnowledgeTreeMindMapDialog(QDialog):
    def __init__(
        self,
        rows: Iterable[dict],
        *,
        selected_card_id: int | None = None,
        initial_scope: str = SCOPE_WHOLE_TREE,
        on_card_activated: Callable[[int], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._rows = [dict(row) for row in rows]
        self._selected_card_id = (
            None if selected_card_id is None else int(selected_card_id)
        )
        self._map_selected_card_id = self._selected_card_id
        self._on_card_activated = on_card_activated
        self._collapsed_card_ids: set[int] = set()
        self._search_match_ids: list[int] = []
        self._search_index = -1
        self._parent_by_card_id = {
            int(row["card_id"]): (
                None
                if row.get("parent_card_id") is None
                else int(row["parent_card_id"])
            )
            for row in self._rows
            if row.get("card_id") is not None
        }

        self.setWindowTitle(t("knowledge_tree_mind_map_title"))
        self.setMinimumSize(780, 560)
        self.resize(1120, 760)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(9)

        principles = QLabel(t("knowledge_tree_mind_map_principles"), self)
        principles.setObjectName("KnowledgeMindMapPrinciples")
        principles.setWordWrap(True)
        principles.setAccessibleName(t("knowledge_tree_mind_map_principles_name"))
        outer.addWidget(principles)

        options = QHBoxLayout()
        options.setSpacing(8)
        scope_label = QLabel(t("knowledge_tree_mind_map_scope"), self)
        self._scope_combo = QComboBox(self)
        self._scope_combo.setAccessibleName(t("knowledge_tree_mind_map_scope"))
        self._scope_combo.addItem(t("knowledge_tree_mind_map_whole_tree"), SCOPE_WHOLE_TREE)
        self._scope_combo.addItem(
            t("knowledge_tree_mind_map_selected_branch"), SCOPE_SELECTED_BRANCH
        )
        selected_index = self._scope_combo.findData(SCOPE_SELECTED_BRANCH)
        if self._selected_card_id is None:
            selected_item = self._scope_combo.model().item(selected_index)
            if selected_item is not None:
                selected_item.setEnabled(False)
                selected_item.setToolTip(t("knowledge_tree_mind_map_select_branch_first"))

        requested_scope = (
            initial_scope
            if initial_scope in {SCOPE_WHOLE_TREE, SCOPE_SELECTED_BRANCH}
            else SCOPE_WHOLE_TREE
        )
        if requested_scope == SCOPE_SELECTED_BRANCH and self._selected_card_id is None:
            requested_scope = SCOPE_WHOLE_TREE
        self._scope_combo.setCurrentIndex(
            max(0, self._scope_combo.findData(requested_scope))
        )

        self._priority_toggle = QCheckBox(
            t("knowledge_tree_mind_map_show_priorities"), self
        )
        self._fit_btn = QPushButton(t("knowledge_tree_mind_map_fit"), self)
        self._actual_size_btn = QPushButton(
            t("knowledge_tree_mind_map_zoom_percent", percent=100), self
        )
        self._actual_size_btn.setToolTip(t("knowledge_tree_mind_map_actual_size"))
        self._zoom_out_btn = QToolButton(self)
        self._zoom_out_btn.setText("−")
        self._zoom_out_btn.setToolTip(t("knowledge_tree_mind_map_zoom_out"))
        self._zoom_label = QLabel(
            t("knowledge_tree_mind_map_zoom_percent", percent=100), self
        )
        self._zoom_label.setMinimumWidth(48)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setAccessibleName(t("knowledge_tree_mind_map_zoom_level"))
        self._zoom_in_btn = QToolButton(self)
        self._zoom_in_btn.setText("+")
        self._zoom_in_btn.setToolTip(t("knowledge_tree_mind_map_zoom_in"))

        for widget, message_id in (
            (self._fit_btn, "knowledge_tree_mind_map_fit"),
            (self._actual_size_btn, "knowledge_tree_mind_map_actual_size"),
            (self._zoom_out_btn, "knowledge_tree_mind_map_zoom_out"),
            (self._zoom_in_btn, "knowledge_tree_mind_map_zoom_in"),
        ):
            widget.setAccessibleName(t(message_id))

        options.addWidget(scope_label)
        options.addWidget(self._scope_combo)
        options.addWidget(self._priority_toggle)
        options.addStretch(1)
        options.addWidget(self._fit_btn)
        options.addWidget(self._actual_size_btn)
        options.addWidget(self._zoom_out_btn)
        options.addWidget(self._zoom_label)
        options.addWidget(self._zoom_in_btn)
        outer.addLayout(options)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_label = QLabel(t("knowledge_tree_mind_map_search"), self)
        self._search_edit = QLineEdit(self)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setPlaceholderText(t("knowledge_tree_mind_map_search_placeholder"))
        self._search_edit.setAccessibleName(t("knowledge_tree_mind_map_search"))
        self._find_next_btn = QPushButton(t("knowledge_tree_mind_map_find_next"), self)
        self._search_status = QLabel("", self)
        self._search_status.setMinimumWidth(74)
        self._search_status.setAccessibleName(t("knowledge_tree_mind_map_search_status"))
        search_row.addWidget(search_label)
        search_row.addWidget(self._search_edit, 1)
        search_row.addWidget(self._find_next_btn)
        search_row.addWidget(self._search_status)
        outer.addLayout(search_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._collapse_all_btn = QPushButton(t("knowledge_tree_mind_map_collapse_all"), self)
        self._expand_all_btn = QPushButton(t("knowledge_tree_mind_map_expand_all"), self)
        self._focus_btn = QPushButton(t("knowledge_tree_mind_map_focus_branch"), self)
        self._export_btn = QPushButton(t("knowledge_tree_mind_map_export_png"), self)
        keyboard_hint = QLabel(t("knowledge_tree_mind_map_keyboard_hint"), self)
        keyboard_hint.setObjectName("KnowledgeMindMapHint")
        keyboard_hint.setWordWrap(True)
        keyboard_hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        action_row.addWidget(self._collapse_all_btn)
        action_row.addWidget(self._expand_all_btn)
        action_row.addWidget(self._focus_btn)
        action_row.addWidget(self._export_btn)
        action_row.addStretch(1)
        outer.addLayout(action_row)
        outer.addWidget(keyboard_hint)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("KnowledgeMindMapScroll")
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas = MindMapCanvas(self._scroll)
        self._scroll.setWidget(self._canvas)
        self._canvas.set_interaction_handlers(
            on_select=self._on_canvas_selected,
            on_toggle_branch=self._toggle_branch,
            on_activate=self._activate_card,
            on_pan=self._pan_by,
            on_scroll=self._scroll_by,
            on_zoom_at=self._zoom_at,
        )
        outer.addWidget(self._scroll, 1)

        footer = QHBoxLayout()
        self._summary = QLabel("", self)
        self._summary.setObjectName("KnowledgeMindMapSummary")
        self._summary.setAccessibleName(t("knowledge_tree_mind_map_summary_name"))
        footer.addWidget(self._summary)
        footer.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(t("common_close"))
        footer.addWidget(buttons)
        outer.addLayout(footer)

        qconnect(self._scope_combo.currentIndexChanged, self._scope_changed)
        qconnect(self._priority_toggle.toggled, self._refresh_map)
        qconnect(self._fit_btn.clicked, self.fit_to_view)
        qconnect(self._actual_size_btn.clicked, self._actual_size)
        qconnect(self._zoom_out_btn.clicked, lambda _checked=False: self._zoom_by(1.0 / 1.2))
        qconnect(self._zoom_in_btn.clicked, lambda _checked=False: self._zoom_by(1.2))
        qconnect(self._search_edit.textChanged, self._search_changed)
        qconnect(self._search_edit.returnPressed, self._find_next)
        qconnect(self._find_next_btn.clicked, self._find_next)
        qconnect(self._collapse_all_btn.clicked, self._collapse_all)
        qconnect(self._expand_all_btn.clicked, self._expand_all)
        qconnect(self._focus_btn.clicked, self._toggle_focus_mode)
        qconnect(self._export_btn.clicked, self._export_png)
        qconnect(buttons.rejected, self.reject)

        self._refresh_map()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_to_view()

    def _scope_changed(self, *_args) -> None:
        if str(self._scope_combo.currentData()) == SCOPE_SELECTED_BRANCH:
            if self._map_selected_card_id is not None:
                self._selected_card_id = int(self._map_selected_card_id)
        self._refresh_map()

    def _refresh_map(self, *_args) -> None:
        scope = str(self._scope_combo.currentData() or SCOPE_WHOLE_TREE)
        layout = build_mind_map_layout(
            self._rows,
            scope=scope,
            selected_card_id=self._selected_card_id,
            center_title=t("knowledge_tree_mind_map_center"),
            collapsed_card_ids=self._collapsed_card_ids,
        )
        self._canvas.set_mind_map(
            layout, show_priorities=self._priority_toggle.isChecked()
        )
        selected_key: Hashable = layout.center_key
        if self._map_selected_card_id in layout.nodes_by_key:
            selected_key = int(self._map_selected_card_id)  # type: ignore[arg-type]
        self._canvas.set_selected_key(selected_key)
        self._canvas.set_search_matches(
            card_id
            for card_id in self._search_match_ids
            if card_id in layout.nodes_by_key
        )
        summary = t(
            "knowledge_tree_mind_map_summary",
            visible=layout.visible_card_count,
            total=layout.total_card_count,
            levels=layout.max_depth + 1,
        )
        self._summary.setText(summary)
        self._canvas.setAccessibleDescription(
            summary + ". " + t("knowledge_tree_mind_map_canvas_instructions")
        )
        self._update_controls()

    def _update_controls(self) -> None:
        layout = self._canvas.layout_model
        if layout is None:
            return
        selected_index = self._scope_combo.findData(SCOPE_SELECTED_BRANCH)
        selected_item = self._scope_combo.model().item(selected_index)
        if selected_item is not None:
            selected_item.setEnabled(self._map_selected_card_id is not None)
        in_focus_mode = str(self._scope_combo.currentData()) == SCOPE_SELECTED_BRANCH
        self._focus_btn.setText(
            t("knowledge_tree_mind_map_show_full")
            if in_focus_mode
            else t("knowledge_tree_mind_map_focus_branch")
        )
        self._focus_btn.setEnabled(in_focus_mode or self._map_selected_card_id is not None)
        self._collapse_all_btn.setEnabled(
            any(node.child_count and not node.collapsed for node in layout.nodes)
        )
        self._expand_all_btn.setEnabled(bool(self._collapsed_card_ids))
        self._find_next_btn.setEnabled(bool(self._search_match_ids))
        self._zoom_label.setText(
            t(
                "knowledge_tree_mind_map_zoom_percent",
                percent=round(self._canvas.zoom * 100),
            )
        )

    def _on_canvas_selected(self, card_id: int | None) -> None:
        self._map_selected_card_id = card_id
        self._update_controls()
        if self._canvas.selected_key is not None:
            self._center_key(self._canvas.selected_key)

    def _toggle_branch(self, card_id: int) -> None:
        card_id = int(card_id)
        if card_id in self._collapsed_card_ids:
            self._collapsed_card_ids.remove(card_id)
        else:
            self._collapsed_card_ids.add(card_id)
        self._map_selected_card_id = card_id
        self._refresh_map()
        self._canvas.set_selected_key(card_id)
        self._center_key(card_id)

    def _collapse_all(self, *_args) -> None:
        layout = self._canvas.layout_model
        if layout is None:
            return
        self._collapsed_card_ids.update(
            int(node.card_id)
            for node in layout.nodes
            if node.card_id is not None and node.child_count
        )
        self._refresh_map()
        self.fit_to_view()

    def _expand_all(self, *_args) -> None:
        self._collapsed_card_ids.clear()
        self._refresh_map()
        self.fit_to_view()

    def _search_changed(self, text: str) -> None:
        query = " ".join(str(text or "").casefold().split())
        self._search_index = -1
        self._search_match_ids = []
        if query:
            for row in self._rows:
                title = " ".join(str(row.get("title") or "").casefold().split())
                if query in title:
                    self._search_match_ids.append(int(row["card_id"]))
        layout = self._canvas.layout_model
        self._canvas.set_search_matches(
            card_id
            for card_id in self._search_match_ids
            if layout is not None and card_id in layout.nodes_by_key
        )
        self._search_status.setText(
            t("knowledge_tree_mind_map_match_count", count=len(self._search_match_ids))
            if query
            else ""
        )
        self._update_controls()

    def _find_next(self, *_args) -> None:
        if not self._search_match_ids:
            return
        self._search_index = (self._search_index + 1) % len(self._search_match_ids)
        card_id = int(self._search_match_ids[self._search_index])
        if (
            str(self._scope_combo.currentData()) == SCOPE_SELECTED_BRANCH
            and not self._is_descendant_of(card_id, self._selected_card_id)
        ):
            self._scope_combo.setCurrentIndex(
                self._scope_combo.findData(SCOPE_WHOLE_TREE)
            )
        current: int | None = card_id
        while current is not None:
            self._collapsed_card_ids.discard(current)
            current = self._parent_by_card_id.get(current)
        self._map_selected_card_id = card_id
        self._refresh_map()
        self._canvas.set_selected_key(card_id)
        self._center_key(card_id)
        self._search_status.setText(
            t(
                "knowledge_tree_mind_map_match_position",
                current=self._search_index + 1,
                count=len(self._search_match_ids),
            )
        )

    def _is_descendant_of(self, card_id: int, ancestor_id: int | None) -> bool:
        if ancestor_id is None:
            return False
        current: int | None = int(card_id)
        while current is not None:
            if current == int(ancestor_id):
                return True
            current = self._parent_by_card_id.get(current)
        return False

    def _toggle_focus_mode(self, *_args) -> None:
        if str(self._scope_combo.currentData()) == SCOPE_SELECTED_BRANCH:
            self._show_full_map()
        else:
            self._focus_selected_branch()

    def _focus_selected_branch(self) -> None:
        if self._map_selected_card_id is None:
            return
        self._selected_card_id = int(self._map_selected_card_id)
        selected_index = self._scope_combo.findData(SCOPE_SELECTED_BRANCH)
        if self._scope_combo.currentIndex() == selected_index:
            self._refresh_map()
        else:
            self._scope_combo.setCurrentIndex(selected_index)
        self.fit_to_view()

    def _show_full_map(self) -> None:
        whole_index = self._scope_combo.findData(SCOPE_WHOLE_TREE)
        if self._scope_combo.currentIndex() == whole_index:
            self._refresh_map()
        else:
            self._scope_combo.setCurrentIndex(whole_index)
        self.fit_to_view()

    def _activate_card(self, card_id: int) -> None:
        self.accept()
        if self._on_card_activated is not None:
            self._on_card_activated(int(card_id))

    def _pan_by(self, dx: float, dy: float) -> None:
        horizontal = self._scroll.horizontalScrollBar()
        vertical = self._scroll.verticalScrollBar()
        horizontal.setValue(horizontal.value() - round(dx))
        vertical.setValue(vertical.value() - round(dy))

    def _scroll_by(self, dx: float, dy: float) -> None:
        horizontal = self._scroll.horizontalScrollBar()
        vertical = self._scroll.verticalScrollBar()
        horizontal.setValue(horizontal.value() + round(dx))
        vertical.setValue(vertical.value() + round(dy))

    def _zoom_at(self, factor: float, canvas_position: QPointF) -> None:
        old_zoom = self._canvas.zoom
        viewport_position = self._canvas.mapTo(
            self._scroll.viewport(), canvas_position.toPoint()
        )
        base_x = canvas_position.x() / old_zoom
        base_y = canvas_position.y() / old_zoom
        self._canvas.set_zoom(old_zoom * float(factor))
        new_zoom = self._canvas.zoom
        self._scroll.horizontalScrollBar().setValue(
            round(base_x * new_zoom - viewport_position.x())
        )
        self._scroll.verticalScrollBar().setValue(
            round(base_y * new_zoom - viewport_position.y())
        )
        self._update_controls()

    def _zoom_by(self, factor: float) -> None:
        viewport_center = self._scroll.viewport().rect().center()
        canvas_position = self._canvas.mapFrom(
            self._scroll.viewport(), viewport_center
        )
        self._zoom_at(float(factor), QPointF(canvas_position))

    def _actual_size(self, *_args) -> None:
        self._canvas.set_zoom(1.0)
        self._update_controls()
        if self._canvas.selected_key is not None:
            self._center_key(self._canvas.selected_key)

    def fit_to_view(self, *_args) -> None:
        viewport = self._scroll.viewport().size()
        base = self._canvas.base_size
        if base.width() <= 0 or base.height() <= 0:
            return
        width_scale = max(1.0, viewport.width() - 16) / base.width()
        height_scale = max(1.0, viewport.height() - 16) / base.height()
        self._canvas.set_zoom(
            min(_MAX_ZOOM, max(_MIN_ZOOM, min(width_scale, height_scale)))
        )
        self._update_controls()

    def _center_key(self, key: Hashable) -> None:
        position = self._canvas.canvas_position_for_key(key)
        if position is None:
            return
        self._scroll.ensureVisible(round(position.x()), round(position.y()), 120, 90)

    def _export_png(self, *_args) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            t("knowledge_tree_mind_map_export_title"),
            "",
            t("knowledge_tree_mind_map_png_filter"),
        )
        if not path:
            return
        if not path.casefold().endswith(".png"):
            path += ".png"
        if not self._canvas.render_pixmap().save(os.path.abspath(path), "PNG"):
            showInfo(t("knowledge_tree_mind_map_export_failed"))
