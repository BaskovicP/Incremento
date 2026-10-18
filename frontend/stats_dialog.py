"""Statistics viewer dialog for Incremento."""

from __future__ import annotations

import math
import threading
from datetime import date
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QGridLayout,
    QLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    Qt,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabBar,
    QPainter,
    QPen,
    QColor,
    QFrame,
    QSizePolicy,
    qconnect,
)

try:
    from .stats_dashboard import ProgressDashboard
    from .stats_progress import progress_model
    from .stats_library import DocumentProgressPanel, CardStagePanel
    from .learning_stats import (
        learning_outcome_display, learning_history_display,
        request_daily_learning_outcomes, request_learning_outcome_history,
        request_document_progress, request_learning_card_states,
    )
except ImportError:
    from frontend.stats_dashboard import ProgressDashboard
    from frontend.stats_progress import progress_model
    from frontend.stats_library import DocumentProgressPanel, CardStagePanel
    from frontend.learning_stats import (
        learning_outcome_display, learning_history_display,
        request_daily_learning_outcomes, request_learning_outcome_history,
        request_document_progress, request_learning_card_states,
    )

try:
    from ..backend.i18n import format_date, format_number, t, tn
except ImportError:
    from backend.i18n import format_date, format_number, t, tn  # type: ignore

try:
    from ..backend.statistics import (
        load_stats,
        load_daily_history,
        daily_history_csv,
        get_statistics_goals,
        load_media_activity,
        set_statistics_goals,
        _effective_date,
        _empty,
        _empty_time,
        _is_valid_counts_block,
        _is_valid_time_block,
        _normalize_counts_block,
        _normalize_time_block,
        _normalize_tag_breakdown_block,
        daily_tag_breakdown_from_collection,
        UNTAGGED_STATS_TAG,
    )
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from statistics import (
        load_stats,
        load_daily_history,
        daily_history_csv,
        get_statistics_goals,
        load_media_activity,
        set_statistics_goals,
        _effective_date,
        _empty,
        _empty_time,
        _is_valid_counts_block,
        _is_valid_time_block,
        _normalize_counts_block,
        _normalize_time_block,
        _normalize_tag_breakdown_block,
        daily_tag_breakdown_from_collection,
        UNTAGGED_STATS_TAG,
    )
    from paths import get_active_profile as _active_profile  # type: ignore

# ── colour palettes ────────────────────────────────────────────────────────────
_TYPE_ORDER = ["topics", "items", "pdf", "epub", "youtube", "webpage"]
_TYPE_COLORS = ["#4a90d9", "#7bc67e", "#e0a020", "#8e6ad8", "#e05050", "#1abc9c"]
_MODE_COLORS = ["#e0a020", "#8da0cb"]  # Priority, Random
_TAG_COLORS = [  # cycled for arbitrary tag lists
    "#4a90d9",
    "#7bc67e",
    "#e0a020",
    "#e05050",
    "#9b59b6",
    "#1abc9c",
    "#e67e22",
    "#c0392b",
]
_TREND_CARD_COLORS = ["#4a90d9", "#7bc67e", "#8a8f98"]
_TREND_PAGE_COLORS = ["#e0a020", "#8e6ad8"]
_TREND_TIME_COLORS = ["#1abc9c"]
_LEARNING_TREND_COLORS = ["#198b72", "#d26040"]
_HEATMAP_COLUMN_WIDTH = 28
_HEATMAP_ROW_HEIGHT = 26
_HEATMAP_MIN_WIDTH = 280
_HEATMAP_MAX_WIDTH = 840


def _type_label(key: str) -> str:
    return t(
        {
            "topics": "stats_type_topics",
            "items": "stats_type_items",
            "pdf": "stats_type_pdfs",
            "epub": "stats_type_epubs",
            "youtube": "stats_type_videos",
            "webpage": "stats_type_web_pages",
            "video": "ui_type_video", "writing": "ui_type_writing", "local_file": "ui_type_local_file",
        }.get(key, "stats_type_unknown"),
        type_name=key.replace("_", " ").title(),
    )


def _mode_label(key: str) -> str:
    return t(
        {
            "priority": "stats_mode_priority",
            "random": "stats_mode_random",
        }.get(key, "stats_mode_unknown"),
        mode_name=key.replace("_", " ").title(),
    )


def _accessible_chart_summary(
    title: str,
    items: list[tuple[str, float]],
    *,
    value_formatter=None,
    maximum_items: int = 8,
) -> str:
    """Return a concise text equivalent for a custom-painted chart."""
    formatter = value_formatter or _format_count
    normalized = [(str(label), max(0.0, float(value))) for label, value in items]
    if not normalized:
        return t("stats_accessible_no_data", title=title)
    visible = normalized[: max(1, int(maximum_items))]
    details = ", ".join(
        f"{label}: {formatter(value)}" for label, value in visible
    )
    remainder = len(normalized) - len(visible)
    suffix = tn("stats_accessible_more_values", remainder) if remainder > 0 else ""
    return t("stats_accessible_summary", title=title, details=details, suffix=suffix)


# ── bar chart widget ───────────────────────────────────────────────────────────


class _BarChart(QWidget):
    """Draws a set of labelled horizontal bars with QPainter."""

    _LABEL_W = 120
    _RIGHT_W = 90
    _BAR_H = 14
    _ROW_H = 28

    def __init__(
        self,
        items: list[tuple[str, float]],
        colors: list[str],
        value_formatter=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items = items  # [(label, value), …]
        self._colors = [QColor(c) for c in colors]
        self._total = sum(v for _, v in items) or 1.0
        self._fmt = value_formatter or (lambda v: str(int(round(v))))
        self.setFixedHeight(self._ROW_H * max(1, len(items)) + 4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(t("stats_bar_chart_accessible"))
        self.setAccessibleDescription(
            _accessible_chart_summary(
                t("stats_bar_chart_accessible"),
                self._items,
                value_formatter=self._fmt,
            )
        )

    def paintEvent(self, _event) -> None:
        if not self._items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        bar_x = self._LABEL_W + 8
        bar_w = max(10, w - bar_x - self._RIGHT_W - 8)
        text_c = self.palette().text().color()
        track_c = QColor(text_c.red(), text_c.green(), text_c.blue(), 30)
        af = Qt.AlignmentFlag

        for i, (label, value) in enumerate(self._items):
            row_y = i * self._ROW_H + 2
            bar_y = row_y + (self._ROW_H - self._BAR_H) // 2
            color = self._colors[i % len(self._colors)]

            # Label (left-aligned, ellide if needed)
            p.setPen(text_c)
            fm = p.fontMetrics()
            elided = fm.elidedText(
                label, Qt.TextElideMode.ElideRight, self._LABEL_W - 4
            )
            p.drawText(
                0,
                row_y,
                self._LABEL_W - 4,
                self._ROW_H,
                af.AlignVCenter | af.AlignLeft,
                elided,
            )

            # Track (faint rounded rect)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track_c)
            p.drawRoundedRect(bar_x, bar_y, bar_w, self._BAR_H, 4, 4)

            # Fill bar
            if value > 0:
                fill_w = max(8, int(bar_w * value / self._total))
                p.setBrush(color)
                p.drawRoundedRect(bar_x, bar_y, fill_w, self._BAR_H, 4, 4)

            # Right text: count  (pct%)
            pct = round(100 * value / self._total)
            p.setPen(text_c)
            p.drawText(
                w - self._RIGHT_W,
                row_y,
                self._RIGHT_W,
                self._ROW_H,
                af.AlignVCenter | af.AlignLeft,
                f"{self._fmt(value)}  ({pct}\u202f%)",
            )

        p.end()


class _PieChart(QWidget):
    """Draw a bounded pie whose slices and legend represent reviewed cards."""

    def __init__(
        self,
        title: str,
        items: list[tuple[str, float, float]],
        colors: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._items = list(items)
        self._colors = [QColor(color) for color in colors]
        self._total = sum(count for _label, _seconds, count in self._items)
        self._total_text = t("stats_pie_total", cards=_format_count(self._total))
        self.setMinimumHeight(max(234, len(self._items) * 24 + 52))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(title)
        self.setAccessibleDescription(
            _accessible_chart_summary(
                f"{title}. {self._total_text}",
                [(label, count) for label, _seconds, count in self._items],
                value_formatter=lambda count: (
                    f"{_format_count(count)} "
                    f"({_format_count(round(count / (self._total or 1) * 100, 1))}%)"
                ),
            )
        )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().text().color()
        weights = [count for _label, _seconds, count in self._items]
        total = sum(weights)
        painter.setPen(text_color)
        painter.drawText(
            0, 0, self.width(), 24,
            Qt.AlignmentFlag.AlignCenter,
            self._total_text,
        )
        if total <= 0:
            painter.setPen(text_color)
            painter.drawText(
                0,
                24,
                self.width(),
                self.height() - 24,
                Qt.AlignmentFlag.AlignCenter,
                t("stats_no_scope_statistics"),
            )
            painter.end()
            return

        diameter = max(90, min(180, self.height() - 52, int(self.width() * 0.38)))
        pie_x = 8
        pie_y = 24 + max(8, (self.height() - 24 - diameter) // 2)
        start_angle = 90 * 16
        consumed = 0
        slice_labels = []
        for index, weight in enumerate(weights):
            if index == len(weights) - 1:
                span = -(360 * 16 - consumed)
            else:
                span = -int(round(360 * 16 * weight / total))
                consumed += abs(span)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._colors[index % len(self._colors)])
            painter.drawPie(pie_x, pie_y, diameter, diameter, start_angle, span)
            slice_labels.append((start_angle + span / 2, weight / total * 100))
            start_angle += span

        painter.save()
        font = painter.font()
        font.setPixelSize(max(8, min(11, diameter // 14)))
        font.setBold(True)
        painter.setFont(font)
        for index, (midpoint, percentage) in enumerate(slice_labels):
            if percentage <= 0:
                continue
            angle = math.radians(midpoint / 16)
            radius = 0 if len(weights) == 1 else diameter * 0.34
            x = pie_x + diameter / 2 + radius * math.cos(angle)
            y = pie_y + diameter / 2 - radius * math.sin(angle)
            label = _format_count(round(percentage, 1)) + "%"
            fm = painter.fontMetrics()
            label_w = fm.horizontalAdvance(label) + 2
            painter.save()
            painter.translate(x, y)
            if percentage < 10:
                painter.rotate((-midpoint / 16 + 90) % 180 - 90)
            color = self._colors[index % len(self._colors)]
            painter.setPen(QColor("#202020" if color.lightness() > 150 else "#ffffff"))
            painter.drawText(
                -label_w // 2, -fm.height() // 2, label_w, fm.height(),
                Qt.AlignmentFlag.AlignCenter, label,
            )
            painter.restore()
        painter.restore()

        legend_x = pie_x + diameter + 16
        legend_w = max(40, self.width() - legend_x - 6)
        row_h = 24
        legend_y = 24 + max(4, (self.height() - 24 - len(self._items) * row_h) // 2)
        fm = painter.fontMetrics()
        for index, (label, _seconds, count) in enumerate(self._items):
            y = legend_y + index * row_h
            color = self._colors[index % len(self._colors)]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(legend_x, y + 6, 10, 10, 2, 2)
            value = t(
                "stats_pie_legend_value",
                cards=_format_count(count),
            )
            value_w = fm.horizontalAdvance(value) + 8
            label_w = max(30, legend_w - value_w - 18)
            painter.setPen(text_color)
            painter.drawText(
                legend_x + 16,
                y,
                label_w,
                row_h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                fm.elidedText(label, Qt.TextElideMode.ElideRight, label_w),
            )
            painter.drawText(
                legend_x + 16 + label_w,
                y,
                value_w,
                row_h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                value,
            )
        painter.end()


def _date_tick_layout(labels, metrics, left, right):
    """Prefer the endpoints; only place intermediate dates when they fit."""
    if not labels:
        return []
    slot = max(1, right - left) / len(labels)
    def tick(index):
        width = metrics.horizontalAdvance(labels[index]) + 4
        return index, max(left, min(right - width, left + int(index * slot))), width
    first, last = tick(0), tick(len(labels) - 1)
    if len(labels) == 1:
        return [first]
    if first[1] + first[2] + 8 > last[1]:
        return [last]
    result = [first]
    for index in range(1, len(labels) - 1):
        candidate = tick(index)
        if (candidate[1] >= result[-1][1] + result[-1][2] + 8
                and candidate[1] + candidate[2] + 8 <= last[1]):
            result.append(candidate)
    return [*result, last]


class _DailyStackedChart(QWidget):
    """Compact stacked vertical chart for zero-filled daily trend series."""

    _TOP = 16
    _BOTTOM = 32
    _LEFT = 44
    _RIGHT = 10

    def __init__(
        self,
        labels: list[str],
        series: list[tuple[str, list[float]]],
        colors: list[str],
        *,
        value_formatter=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._labels = list(labels)
        self._series = [(str(name), list(values)) for name, values in series]
        self._colors = [QColor(color) for color in colors]
        self._fmt = value_formatter or _format_count
        self.setMinimumHeight(205)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(t("stats_trend_chart_accessible"))
        totals = [(name, sum(values)) for name, values in self._series]
        date_range = (
            f" from {self._labels[0]} through {self._labels[-1]}"
            if self._labels
            else ""
        )
        self.setAccessibleDescription(
            _accessible_chart_summary(
                t("stats_trend_chart_title", date_range=date_range),
                totals,
                value_formatter=self._fmt,
            )
        )

    def plot_left(self):
        maximum = max((sum(max(0, values[i]) if i < len(values) else 0 for _, values in self._series)
                       for i in range(len(self._labels))), default=0)
        return max(self._LEFT, self.fontMetrics().horizontalAdvance(self._fmt(maximum)) + 8)

    def date_ticks(self):
        return _date_tick_layout(self._labels, self.fontMetrics(), self.plot_left(), self.width() - self._RIGHT)

    def paintEvent(self, _event) -> None:
        if not self._labels:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().text().color()
        grid_color = QColor(
            text_color.red(), text_color.green(), text_color.blue(), 36
        )
        plot_w = max(1, self.width() - self.plot_left() - self._RIGHT)
        plot_h = max(1, self.height() - self._TOP - max(self._BOTTOM, self.fontMetrics().height() + 12))
        totals = [
            sum(
                max(0.0, float(values[index] if index < len(values) else 0.0))
                for _name, values in self._series
            )
            for index in range(len(self._labels))
        ]
        maximum = max(totals, default=0.0) or 1.0

        for fraction in (0.0, 0.5, 1.0):
            y = self._TOP + plot_h - int(plot_h * fraction)
            painter.setPen(grid_color)
            painter.drawLine(self.plot_left(), y, self.plot_left() + plot_w, y)
            painter.setPen(text_color)
            painter.drawText(
                0,
                y - self.fontMetrics().height() // 2,
                self.plot_left() - 5,
                self.fontMetrics().height(),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._fmt(maximum * fraction),
            )

        slot_w = plot_w / max(1, len(self._labels))
        bar_w = max(2, int(slot_w * 0.62))
        for day_index, _label in enumerate(self._labels):
            x = self.plot_left() + int(day_index * slot_w + (slot_w - bar_w) / 2)
            stack_y = self._TOP + plot_h
            for series_index, (_name, values) in enumerate(self._series):
                value = max(
                    0.0,
                    float(values[day_index] if day_index < len(values) else 0.0),
                )
                if value <= 0:
                    continue
                height = max(1, int(plot_h * value / maximum))
                stack_y -= height
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._colors[series_index % len(self._colors)])
                painter.drawRoundedRect(x, stack_y, bar_w, height, 2, 2)

        painter.setPen(text_color)
        for index, x, label_width in self.date_ticks():
            painter.drawText(
                x, self._TOP + plot_h + 5, label_width, self.fontMetrics().height() + 2,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._labels[index],
            )
        painter.end()


class _RecallRateChart(QWidget):
    """A fixed 0–100% axis, with gaps instead of invented zero-answer rates."""

    _TOP, _BOTTOM, _LEFT, _RIGHT = 16, 32, 44, 10

    def __init__(self, labels, rates, daily_details, parent=None):
        super().__init__(parent)
        self._labels = list(labels)
        self._rates = list(rates)
        self._details = list(daily_details)
        self.setMinimumHeight(205)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setAccessibleName(t("stats_recall_rate_by_day"))
        self.setAccessibleDescription("\n".join(self._details))

    def mouseMoveEvent(self, event):
        width = max(1, self.width() - self.plot_left() - self._RIGHT)
        index = int((event.position().x() - self.plot_left()) * len(self._labels) / width)
        if event.position().x() < self.plot_left() or not 0 <= index < len(self._details):
            self.setToolTip("")
        else:
            self.setToolTip(self._details[index])
        super().mouseMoveEvent(event)

    def plot_left(self):
        return max(self._LEFT, self.fontMetrics().horizontalAdvance("100%") + 8)

    def date_ticks(self):
        return _date_tick_layout(self._labels, self.fontMetrics(), self.plot_left(), self.width() - self._RIGHT)

    def paintEvent(self, _event):
        if not self._labels:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self.palette().text().color()
        grid = QColor(text.red(), text.green(), text.blue(), 36)
        width = max(1, self.width() - self.plot_left() - self._RIGHT)
        height = max(1, self.height() - self._TOP - max(self._BOTTOM, self.fontMetrics().height() + 12))
        for percentage in (0, 25, 50, 75, 100):
            y = self._TOP + height - int(height * percentage / 100)
            painter.setPen(grid)
            painter.drawLine(self.plot_left(), y, self.plot_left() + width, y)
            painter.setPen(text)
            painter.drawText(
                0, y - self.fontMetrics().height() // 2, self.plot_left() - 5, self.fontMetrics().height(),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_number(percentage) + "%",
            )
        slot = width / len(self._labels)
        color = QColor(_LEARNING_TREND_COLORS[0])
        painter.setPen(QPen(color, 2))
        painter.setBrush(color)
        previous = None
        for index, rate in enumerate(self._rates):
            if rate is None:
                previous = None
                continue
            x = self.plot_left() + int((index + .5) * slot)
            y = self._TOP + height - int(height * max(0, min(100, rate)) / 100)
            if previous is not None:
                painter.drawLine(*previous, x, y)
            painter.drawEllipse(x - 3, y - 3, 6, 6)
            previous = (x, y)
        painter.setPen(text)
        for index, x, label_width in self.date_ticks():
            painter.drawText(
                x, self._TOP + height + 5, label_width, self.fontMetrics().height() + 2,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._labels[index],
            )
        painter.end()


def _heatmap_viewport_width(
    weeks: int, column_width: int = _HEATMAP_COLUMN_WIDTH,
) -> int:
    """Return a compact heatmap width with room for weekday labels."""
    natural_width = 72 + max(1, int(weeks or 1)) * max(1, int(column_width))
    return max(_HEATMAP_MIN_WIDTH, min(_HEATMAP_MAX_WIDTH, natural_width))


def _heatmap_month_labels(
    cells: list[dict],
    *,
    first_weekday: int,
    weeks: int,
) -> list[str]:
    """Place one readable header label at each visible month transition."""
    labels = ["" for _ in range(max(1, int(weeks or 1)))]
    previous_month = None
    for index, cell in enumerate(cells):
        try:
            parsed = date.fromisoformat(str(cell.get("date") or ""))
        except Exception:
            continue
        month = (parsed.year, parsed.month)
        if month == previous_month:
            continue
        week = (max(0, int(first_weekday)) + index) // 7
        while week < len(labels) and labels[week]:
            week += 1
        if week < len(labels):
            labels[week] = parsed.strftime("%b")
        previous_month = month
    return labels


class _ActivityHeatmap(QTableWidget):
    """Accessible calendar heatmap whose cells open a one-day drill-down."""

    _COLORS = ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39")

    def __init__(
        self,
        history: list[dict],
        *,
        metric: str = "activity",
        on_day_selected=None,
        parent=None,
    ) -> None:
        self._cells = _activity_heatmap_model(history, metric=metric)
        first_weekday = 0
        if self._cells:
            try:
                first_weekday = date.fromisoformat(self._cells[0]["date"]).weekday()
            except Exception:
                first_weekday = 0
        weeks = max(1, int(math.ceil((first_weekday + len(self._cells)) / 7)))
        super().__init__(7, weeks, parent)
        self._on_day_selected = on_day_selected
        self.setAccessibleName(t("stats_heatmap_accessible"))
        active_days = sum(
            1 for cell in self._cells if int(cell.get("intensity", 0) or 0) > 0
        )
        self.setAccessibleDescription(
            _accessible_chart_summary(
                t("stats_heatmap_accessible"),
                [
                    (t("stats_active_days"), float(active_days)),
                    (t("stats_shown_days"), float(len(self._cells))),
                ],
            )
        )
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.setShowGrid(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.verticalHeader().setVisible(True)
        self.verticalHeader().setDefaultSectionSize(_HEATMAP_ROW_HEIGHT)
        self.setVerticalHeaderLabels(
            tuple(t(f"stats_weekday_{day}") for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"))
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        month_labels = _heatmap_month_labels(
            self._cells, first_weekday=first_weekday, weeks=weeks,
        )
        header_metrics = self.horizontalHeader().fontMetrics()
        column_width = max(
            _HEATMAP_COLUMN_WIDTH,
            max((header_metrics.horizontalAdvance(label) + 12 for label in month_labels), default=0),
        )
        self.horizontalHeader().setDefaultSectionSize(column_width)
        self.setFixedWidth(_heatmap_viewport_width(weeks, column_width))
        self.setFixedHeight(7 * _HEATMAP_ROW_HEIGHT + 54)

        for index, cell in enumerate(self._cells):
            slot = first_weekday + index
            weekday = slot % 7
            week = slot // 7
            item = QTableWidgetItem("")
            intensity = int(cell.get("intensity", 0) or 0)
            item.setBackground(QColor(self._COLORS[max(0, min(4, intensity))]))
            detail = dict(cell.get("detail") or {})
            tooltip_text = t(
                "stats_heatmap_tooltip",
                date=cell.get("date"),
                cards=_format_count(float(detail.get("cards", 0))),
                pages=_format_count(float(detail.get("pages", 0))),
                duration=_fmt_duration(float(detail.get("seconds", 0))),
            )
            item.setToolTip(tooltip_text)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.setItem(weekday, week, item)
        self.setHorizontalHeaderLabels(month_labels)
        self.itemClicked.connect(self._open_cell)

    def _open_cell(self, item) -> None:
        try:
            index = int(item.data(Qt.ItemDataRole.UserRole))
            cell = self._cells[index]
        except Exception:
            return
        if callable(self._on_day_selected):
            self._on_day_selected(dict(cell.get("detail") or {}))


# ── section helper ─────────────────────────────────────────────────────────────


def _section(
    title: str,
    items: list[tuple[str, float]],
    colors: list[str],
    parent: QWidget,
    value_formatter=None,
) -> QWidget:
    """Return a titled chart widget."""
    container = QWidget(parent)
    lay = QVBoxLayout(container)
    lay.setSpacing(4)
    lay.setContentsMargins(0, 8, 0, 0)

    hdr = QLabel(title)
    hdr.setStyleSheet("font-weight: bold; font-size: 10pt;")
    lay.addWidget(hdr)

    # Filter out zero-value entries that would just waste vertical space
    visible = [(lbl, v) for lbl, v in items if v > 0] or items
    lay.addWidget(
        _BarChart(visible, colors, value_formatter=value_formatter, parent=container)
    )
    return container


def _trend_section(
    title: str,
    labels: list[str],
    series: list[tuple[str, list[float]]],
    colors: list[str],
    parent: QWidget,
    *,
    value_formatter=None,
) -> QWidget:
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setSpacing(4)
    layout.setContentsMargins(0, 10, 0, 0)

    heading = QLabel(title)
    heading.setStyleSheet("font-weight: bold; font-size: 10pt;")
    layout.addWidget(heading)

    legend_parts = [
        f'<span style="color:{colors[index % len(colors)]}">●</span> {name}'
        for index, (name, _values) in enumerate(series)
    ]
    legend = QLabel("&nbsp;&nbsp;".join(legend_parts))
    legend.setStyleSheet("color: gray; font-size: 8pt;")
    layout.addWidget(legend)
    layout.addWidget(
        _DailyStackedChart(
            labels,
            series,
            colors,
            value_formatter=value_formatter,
            parent=container,
        )
    )
    return container


def _fmt_duration(seconds: float) -> str:
    total = int(round(max(0.0, seconds)))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h:
        return t("stats_duration_hours_minutes", hours=h, minutes=m)
    if m:
        return t("stats_duration_minutes_seconds", minutes=m, seconds=s)
    return t("stats_duration_seconds", seconds=s)


def _positive_items(values: dict) -> list[tuple[str, float]]:
    if not isinstance(values, dict):
        return []
    items: list[tuple[str, float]] = []
    for key, value in values.items():
        try:
            numeric = float(value)
        except Exception:
            continue
        if numeric > 0:
            items.append((str(key), numeric))
    return items


def _format_count(value: float) -> str:
    numeric = float(value)
    return format_number(int(numeric) if numeric.is_integer() else numeric)


def _format_average(value: float) -> str:
    """Format a dashboard average without exposing floating-point noise."""
    return _format_count(round(max(0.0, float(value)), 1))


def _tag_items(tag_counts: dict) -> list[tuple[str, float]]:
    if not isinstance(tag_counts, dict):
        return []
    visible = {
        str(key): value
        for key, value in tag_counts.items()
        if str(key).strip() and not str(key).startswith("__")
    }
    return sorted(
        _positive_items(visible),
        key=lambda x: (-x[1], x[0].casefold()),
    )


def _topic_item_pie_items(
    breakdown: dict,
    kind: str,
    *,
    maximum_items: int = 8,
) -> list[tuple[str, float, float]]:
    clean = _normalize_tag_breakdown_block(breakdown)
    counts = clean["counts"].get(kind, {})
    seconds = clean["seconds"].get(kind, {})
    keys = set(counts)
    items = []
    for key in keys:
        duration = float(seconds.get(key, 0) or 0)
        count = float(counts.get(key, 0) or 0)
        if count <= 0:
            continue
        label = t("stats_untagged") if key == UNTAGGED_STATS_TAG else str(key)
        items.append((label, duration, count))
    items.sort(key=lambda item: (-item[2], -item[1], item[0].casefold()))

    limit = max(2, int(maximum_items or 2))
    if len(items) <= limit:
        return items
    visible = items[: limit - 1]
    remainder = items[limit - 1 :]
    visible.append(
        (
            t("stats_other_tags"),
            sum(item[1] for item in remainder),
            sum(item[2] for item in remainder),
        )
    )
    return visible


def _ordered_mode_items(mode_counts: dict) -> list[tuple[str, float]]:
    if not isinstance(mode_counts, dict):
        return []

    items: list[tuple[str, float]] = []
    seen: set[str] = set()

    def _append(key: str) -> None:
        seen.add(key)
        try:
            value = float(mode_counts.get(key, 0) or 0)
        except Exception:
            value = 0.0
        if value > 0:
            items.append((_mode_label(key), value))

    for key in ("priority", "random"):
        _append(key)
    for key in sorted(str(k) for k in mode_counts.keys()):
        if key not in seen:
            _append(key)

    return items


def _top_label(items: list[tuple[str, float]], empty: str | None = None) -> str:
    if not items:
        return empty if empty is not None else t("common_none")
    label, _value = max(items, key=lambda item: (item[1], item[0].casefold()))
    return label


def _summary_metrics(counts: dict, time_stats: dict) -> list[tuple[str, str]]:
    clean_counts = _normalize_counts_block(counts)
    clean_time = _normalize_time_block(time_stats)

    total_cards = float(sum(clean_counts["type"].values()))
    type_time = float(sum(clean_time["type"].values()))
    tag_time = float(sum(clean_time["tags"].values()))
    total_seconds = type_time if type_time > 0 else tag_time
    average_seconds = total_seconds / total_cards if total_cards > 0 else 0.0

    top_type = _top_label(_ordered_type_items(clean_counts["type"]))
    top_tag = _top_label(_tag_items(clean_counts["tags"]))

    return [
        (t("stats_cards_studied"), _format_count(total_cards)),
        (t("stats_review_time"), _fmt_duration(total_seconds)),
        (t("stats_average_per_card"), _fmt_duration(average_seconds)),
        (t("stats_top_type_tag"), f"{top_type} / {top_tag}"),
    ]


def _history_day_values(row: dict) -> tuple[dict, dict, dict]:
    if not isinstance(row, dict):
        return _empty(), _empty_time(), {}
    counts = _normalize_counts_block(row.get("counts"))
    seconds = _normalize_time_block(row.get("seconds"))
    reading = row.get("reading") if isinstance(row.get("reading"), dict) else {}
    return counts, seconds, reading


def _reading_value(reading: dict, key: str) -> float:
    try:
        value = float(reading.get(key, 0) or 0)
    except Exception:
        return 0.0
    return value if math.isfinite(value) and value > 0 else 0.0


def _history_total_seconds(seconds: dict) -> float:
    type_total = float(sum(seconds.get("type", {}).values()))
    tag_total = float(sum(seconds.get("tags", {}).values()))
    return type_total if type_total > 0 else tag_total


def _history_row_totals(row: dict) -> tuple[float, float, float]:
    counts, seconds, reading = _history_day_values(row)
    cards = float(sum(counts["type"].values()))
    pages = _reading_value(reading, "pdf_pages") + _reading_value(
        reading, "epub_pages"
    )
    return cards, pages, _history_total_seconds(seconds)


def _goal_recommendations(history: list[dict], days: int = 30) -> dict:
    """Suggest bounded targets from positive days in the recent history window."""
    values: dict[str, list[float]] = {"cards": [], "pages": [], "minutes": []}
    for row in history[-max(1, min(730, int(days))):]:
        cards, pages, seconds = _history_row_totals(row)
        for metric, value in (("cards", cards), ("pages", pages), ("minutes", seconds / 60)):
            if math.isfinite(value) and value > 0:
                values[metric].append(value)
    recommendations = {}
    for metric, samples in values.items():
        samples.sort()
        count = len(samples)
        median = (samples[(count - 1) // 2] + samples[count // 2]) / 2 if count else 0
        recommendations[metric] = {
            "target": max(1, min(1_000_000, int(round(median)))) if count else 0,
            "active_days": count,
        }
    return recommendations


def _history_summary_metrics(history: list[dict]) -> list[tuple[str, str]]:
    totals = [_history_row_totals(row) for row in history]
    cards = sum(item[0] for item in totals)
    pages = sum(item[1] for item in totals)
    seconds = sum(item[2] for item in totals)
    active_days = sum(1 for item in totals if any(value > 0 for value in item))
    return [
        (t("stats_cards_studied"), _format_count(cards)),
        (t("stats_pages_read"), _format_count(pages)),
        (t("stats_study_time"), _fmt_duration(seconds)),
        (t("stats_active_days"), f"{active_days} / {len(history)}"),
    ]


def _history_date_label(value) -> str:
    return format_date(value, format="short")


def _history_chart_series(history: list[dict]) -> dict:
    labels: list[str] = []
    topics: list[float] = []
    items: list[float] = []
    other_cards: list[float] = []
    pdf_pages: list[float] = []
    epub_pages: list[float] = []
    minutes: list[float] = []

    for row in history:
        counts, seconds, reading = _history_day_values(row)
        type_counts = counts["type"]
        topic_count = float(type_counts.get("topics", 0) or 0)
        item_count = float(type_counts.get("items", 0) or 0)
        labels.append(_history_date_label(row.get("date") if isinstance(row, dict) else ""))
        topics.append(topic_count)
        items.append(item_count)
        other_cards.append(
            max(0.0, float(sum(type_counts.values())) - topic_count - item_count)
        )
        pdf_pages.append(_reading_value(reading, "pdf_pages"))
        epub_pages.append(_reading_value(reading, "epub_pages"))
        minutes.append(_history_total_seconds(seconds) / 60.0)

    return {
        "labels": labels,
        "cards": [
            (t("stats_type_topics"), topics),
            (t("stats_type_items"), items),
            (t("stats_type_other"), other_cards),
        ],
        "pages": [(t("stats_type_pdf"), pdf_pages), (t("stats_type_epub"), epub_pages)],
        "minutes": [(t("stats_minutes"), minutes)],
    }


def _history_insight(history: list[dict]) -> str:
    totals = [_history_row_totals(row) for row in history]
    active = [item for item in totals if any(value > 0 for value in item)]
    if not active:
        return t("stats_no_history_activity")

    index = len(totals) - 1
    if index >= 0 and not any(value > 0 for value in totals[index]):
        index -= 1
    streak = 0
    while index >= 0 and any(value > 0 for value in totals[index]):
        streak += 1
        index -= 1

    average_cards = sum(item[0] for item in active) / len(active)
    average_pages = sum(item[1] for item in active) / len(active)
    return tn(
        "stats_history_insight",
        streak,
        cards=_format_average(average_cards),
        pages=_format_average(average_pages),
    )


def _history_day_detail(row: dict) -> dict[str, float | str]:
    counts, seconds, reading = _history_day_values(row)
    topic_count = float(counts["type"].get("topics", 0) or 0)
    item_count = float(counts["type"].get("items", 0) or 0)
    cards = float(sum(counts["type"].values()))
    pdf_pages = _reading_value(reading, "pdf_pages")
    epub_pages = _reading_value(reading, "epub_pages")
    return {
        "date": str(row.get("date") or "") if isinstance(row, dict) else "",
        "topics": topic_count,
        "items": item_count,
        "other_cards": max(0.0, cards - topic_count - item_count),
        "cards": cards,
        "pdf_pages": pdf_pages,
        "epub_pages": epub_pages,
        "pages": pdf_pages + epub_pages,
        "seconds": _history_total_seconds(seconds),
    }


def _daily_goal_progress(row: dict, goals: dict) -> dict[str, dict[str, float]]:
    detail = _history_day_detail(row)
    raw_values = {
        "cards": float(detail["cards"]),
        "pages": float(detail["pages"]),
        "minutes": float(detail["seconds"]) / 60.0,
    }
    result: dict[str, dict[str, float]] = {}
    for metric, value in raw_values.items():
        try:
            target = max(0.0, float((goals or {}).get(metric, 0) or 0))
        except Exception:
            target = 0.0
        ratio = min(1.0, value / target) if target > 0 else 0.0
        result[metric] = {"value": value, "target": target, "ratio": ratio}
    return result


def _period_totals(history: list[dict]) -> dict[str, float]:
    totals = [_history_row_totals(row) for row in list(history or [])]
    return {
        "cards": sum(row[0] for row in totals),
        "pages": sum(row[1] for row in totals),
        "seconds": sum(row[2] for row in totals),
    }


def _history_period_comparison(history: list[dict], days: int) -> dict:
    period = max(1, int(days or 1))
    rows = list(history or [])
    current = _period_totals(rows[-period:])
    previous = _period_totals(rows[-period * 2 : -period])
    result = {}
    for metric in ("cards", "pages", "seconds"):
        current_value = float(current[metric])
        previous_value = float(previous[metric])
        percent = (
            (current_value - previous_value) * 100.0 / previous_value
            if previous_value > 0
            else None
        )
        result[metric] = {
            "current": current_value,
            "previous": previous_value,
            "percent": percent,
        }
    return result


def _activity_heatmap_model(history: list[dict], *, metric: str = "activity") -> list[dict]:
    normalized_metric = str(metric or "activity").strip().lower()
    if normalized_metric not in {"activity", "cards", "pages", "minutes"}:
        normalized_metric = "activity"
    cells = []
    for row in list(history or []):
        detail = _history_day_detail(row)
        values = {
            "cards": float(detail["cards"]),
            "pages": float(detail["pages"]),
            "minutes": float(detail["seconds"]) / 60.0,
        }
        value = (
            sum(values.values())
            if normalized_metric == "activity"
            else values[normalized_metric]
        )
        cells.append(
            {
                "date": str(detail["date"]),
                "value": value,
                "intensity": 0,
                "detail": detail,
            }
        )
    maximum = max((float(cell["value"]) for cell in cells), default=0.0)
    if maximum > 0:
        for cell in cells:
            value = float(cell["value"])
            cell["intensity"] = (
                max(1, min(4, int(math.ceil(value * 4.0 / maximum))))
                if value > 0
                else 0
            )
    return cells


def _comparison_label(history: list[dict], days: int) -> str:
    comparison = _history_period_comparison(history, days)

    def change(metric: str, formatter) -> str:
        values = comparison[metric]
        percent = values["percent"]
        if percent is None:
            delta = t("stats_no_previous_activity")
        else:
            delta = f"{percent:+.0f}%"
        return f"{formatter(values['current'])} ({delta})"

    return t(
        "stats_period_comparison",
        days=days,
        cards=change("cards", _format_count),
        pages=change("pages", _format_count),
        study_time=change("seconds", _fmt_duration),
    )


def _ordered_type_items(type_counts: dict) -> list[tuple[str, float]]:
    if not isinstance(type_counts, dict):
        return []

    items: list[tuple[str, float]] = []
    seen: set[str] = set()

    def _append(key: str) -> None:
        seen.add(key)
        try:
            value = float(type_counts.get(key, 0) or 0)
        except Exception:
            value = 0.0
        if value > 0:
            items.append((_type_label(key), value))

    for key in _TYPE_ORDER:
        _append(key)

    for key in sorted(str(k) for k in type_counts.keys()):
        if key not in seen:
            _append(key)

    return items


def _metric_card(title: str, value: str, parent: QWidget) -> QFrame:
    frame = QFrame(parent)
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setStyleSheet(
        "QFrame { border: 1px solid rgba(128,128,128,0.28); border-radius: 6px; }"
        "QLabel { border: none; }"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(8, 6, 8, 6)
    lay.setSpacing(2)

    value_lbl = QLabel(value)
    value_lbl.setStyleSheet("font-weight: bold; font-size: 11pt;")
    value_lbl.setWordWrap(True)
    lay.addWidget(value_lbl)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("color: gray; font-size: 8pt;")
    title_lbl.setWordWrap(True)
    lay.addWidget(title_lbl)

    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return frame


# ── main dialog ────────────────────────────────────────────────────────────────


class StatisticsGoalsDialog(QDialog):
    """Stage explicit daily-goal choices until the user saves the dialog."""

    def __init__(self, goals: dict, history: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("stats_goal_setup_title"))
        self.setMinimumWidth(540)
        self._checks: dict[str, QCheckBox] = {}
        self._spins: dict[str, QSpinBox] = {}
        suggestions = _goal_recommendations(history)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)
        for key in (
            "stats_goal_setup_guidance", "stats_goal_intro", "stats_goal_recent_explanation",
        ):
            guidance = QLabel(t(key), self)
            guidance.setWordWrap(True)
            outer.addWidget(guidance)

        for metric, label in (
            ("cards", t("stats_cards")),
            ("pages", t("stats_pages")),
            ("minutes", t("stats_minutes")),
        ):
            panel = QFrame(self)
            panel.setFrameShape(QFrame.Shape.StyledPanel)
            layout = QVBoxLayout(panel)
            check = QCheckBox(label, panel)
            check.setAccessibleName(t("stats_daily_goal_accessible", label=label))
            self._checks[metric] = check
            layout.addWidget(check)
            description = QLabel(t(f"stats_goal_{metric}_description"), panel)
            description.setWordWrap(True)
            layout.addWidget(description)

            controls = QGridLayout()
            target_label = QLabel(t("stats_goal_daily_target"), panel)
            spin = QSpinBox(panel)
            spin.setRange(1, 1_000_000)
            spin.setAccessibleName(t("stats_daily_goal_accessible", label=label))
            target_label.setBuddy(spin)
            self._spins[metric] = spin
            current = min(1_000_000, int(round(_reading_value(goals, metric))))
            check.setChecked(current > 0)
            spin.setValue(max(1, current))
            spin.setEnabled(check.isChecked())
            qconnect(check.toggled, spin.setEnabled)
            controls.addWidget(target_label, 0, 0)
            controls.addWidget(spin, 0, 1)
            suggestion = suggestions[metric]
            if suggestion["active_days"]:
                target = suggestion["target"]
                use_suggestion = QPushButton(
                    t("stats_goal_use_suggestion", target=_format_count(target)), panel,
                )
                use_suggestion.setAccessibleName(t(
                    "stats_goal_use_suggestion_accessible", label=label,
                    target=_format_count(target),
                ))
                qconnect(
                    use_suggestion.clicked,
                    lambda _checked=False, metric=metric, target=target: self._use_suggestion(metric, target),
                )
                controls.addWidget(use_suggestion, 0, 2)
                basis = QLabel(tn("stats_goal_suggestion_basis", suggestion["active_days"]), panel)
                basis.setWordWrap(True)
                controls.addWidget(basis, 1, 0, 1, 3)
            controls.setColumnStretch(1, 1)
            layout.addLayout(controls)
            outer.addWidget(panel)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("stats_save_goals"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common_cancel"))
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        outer.addWidget(buttons)

    def _use_suggestion(self, metric: str, target: int) -> None:
        self._checks[metric].setChecked(True)
        self._spins[metric].setValue(target)

    def goals(self) -> dict[str, int]:
        return {
            metric: self._spins[metric].value() if check.isChecked() else 0
            for metric, check in self._checks.items()
        }


class StatsDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        session_counts: dict | None = None,
        session_time: dict | None = None,
        day_end_time: str = "04:00",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._day_end_time = day_end_time
        self._session_counts = _normalize_counts_block(session_counts or _empty())
        self._session_time = _normalize_time_block(session_time or _empty_time())
        self._profile = _active_profile()
        self._learning_outcomes = None
        self._learning_loading = True
        self._learning_generation = 0
        self._learning_date = _effective_date(day_end_time)
        self._learning_history = None
        self._learning_history_requested = False
        self._learning_history_loading = False
        self._closed = False
        self._progress_metric = "pages"
        self._view = "overview"
        self._learning_days = 30
        self._library_generation = 0
        self._library_cancel = threading.Event()
        self._documents = self._card_states = None
        self._documents_requested = self._card_states_requested = False
        self._documents_loading = self._card_states_loading = False
        self._document_query, self._document_kind = "", "all"
        self._media_cache: dict[tuple[str, str], dict] = {}
        self._raw = load_stats(addon_dir, self._profile)
        try:
            self._goals = get_statistics_goals(addon_dir, self._profile)
        except Exception:
            self._goals = {"cards": 0.0, "pages": 0.0, "minutes": 0.0}
        try:
            self._history = load_daily_history(
                addon_dir,
                self._profile,
                days=730,
                day_end_time=day_end_time,
            )
        except Exception:
            self._history = []

        self.setWindowTitle(t("stats_dialog_title"))
        self.setMinimumWidth(900)
        self.setMinimumHeight(640)
        self.resize(1100, 860)
        self._setup_ui()
        qconnect(self.finished, self._mark_closed)
        self._request_learning_outcomes()

    def _request_learning_outcomes(self) -> None:
        self._learning_generation += 1
        generation = self._learning_generation
        logical_date = _effective_date(self._day_end_time)
        self._learning_date = logical_date
        self._learning_outcomes = None
        self._learning_loading = True
        request_daily_learning_outcomes(
            self, self._profile, self._day_end_time, self._receive_learning_outcomes,
            is_current=lambda: not self._closed and self._learning_date == logical_date and self._learning_generation == generation,
        )

    def _mark_closed(self, *_args) -> None:
        self._closed = True
        self._library_cancel.set()

    def _request_library_data(self, kind):
        setattr(self, f"_{kind}_requested", True)
        setattr(self, f"_{kind}_loading", True)
        generation = self._library_generation
        cancelled = self._library_cancel.is_set

        def received(result):
            setattr(self, f"_{kind}", result)
            setattr(self, f"_{kind}_loading", False)
            self._refresh()

        kwargs = dict(is_current=lambda: not self._closed and generation == self._library_generation,
                      cancelled=cancelled)
        if kind == "documents":
            request_document_progress(self, self._addon_dir, self._profile, self._day_end_time, received, **kwargs)
        else:
            request_learning_card_states(self, self._profile, self._day_end_time, received, **kwargs)

    def _invalidate_library_data(self):
        self._library_cancel.set()
        self._library_cancel = threading.Event()
        self._library_generation += 1
        self._documents = self._card_states = None
        self._documents_requested = self._card_states_requested = False
        self._documents_loading = self._card_states_loading = False

    def _request_learning_history(self) -> None:
        self._learning_history_requested = True
        self._learning_history_loading = True
        logical_date = self._learning_date
        generation = self._learning_generation
        request_learning_outcome_history(
            self, self._profile, self._day_end_time, self._receive_learning_history,
            is_current=lambda: not self._closed and self._learning_date == logical_date and self._learning_generation == generation,
        )

    def _receive_learning_history(self, history) -> None:
        self._learning_history = history
        self._learning_history_loading = False
        self._refresh()

    def _receive_learning_outcomes(self, outcomes) -> None:
        self._learning_outcomes = outcomes
        self._learning_loading = False
        self._refresh()

    # ── data ──────────────────────────────────────────────────────────────────

    def _get_counts(self, scope: str) -> dict:
        if scope == "session":
            return _normalize_counts_block(self._session_counts)

        if scope == "daily":
            daily_raw = self._raw.get("daily", {})
            if (
                isinstance(daily_raw, dict)
                and daily_raw.get("date") == _effective_date(self._day_end_time)
                and _is_valid_counts_block(daily_raw.get("counts"))
            ):
                return _normalize_counts_block(daily_raw["counts"])
            return _empty()

        # lifetime
        lt = self._raw.get("lifetime")
        return _normalize_counts_block(lt)

    def _get_time(self, scope: str) -> dict:
        if scope == "session":
            return _normalize_time_block(self._session_time)

        time_raw = self._raw.get("time")
        if not isinstance(time_raw, dict):
            return _empty_time()

        if scope == "daily":
            daily = time_raw.get("daily", {})
            if (
                isinstance(daily, dict)
                and daily.get("date") == _effective_date(self._day_end_time)
                and _is_valid_time_block(daily.get("seconds"))
            ):
                return _normalize_time_block(daily["seconds"])
            return _empty_time()

        lt = time_raw.get("lifetime")
        return _normalize_time_block(lt)

    def _get_tag_breakdown(self, scope: str) -> dict:
        raw = self._raw.get("tag_breakdown")
        if not isinstance(raw, dict):
            raw = {}
        if scope == "daily":
            live = daily_tag_breakdown_from_collection(
                getattr(mw, "col", None),
                self._day_end_time,
            )
            if live is not None:
                return _normalize_tag_breakdown_block(live)
            daily = raw.get("daily")
            if (
                isinstance(daily, dict)
                and daily.get("date") == _effective_date(self._day_end_time)
            ):
                return _normalize_tag_breakdown_block(daily)
            return _normalize_tag_breakdown_block({})
        if scope == "lifetime":
            return _normalize_tag_breakdown_block(raw.get("lifetime"))
        return _normalize_tag_breakdown_block({})

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        self._view_tabs = QTabBar(self)
        self._view_tabs.setAccessibleName(t("stats_views"))
        self._view_tabs.setExpanding(True)
        for key in ("overview", "documents", "learning"):
            self._view_tabs.addTab(t("stats_view_" + key))
        outer.addWidget(self._view_tabs)

        # Scope radio buttons
        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(4, 0, 4, 0)
        scope_row.setSpacing(16)
        self._scope_group = QButtonGroup(self)
        for i, (key, label) in enumerate(
            [
                ("session", t("stats_scope_session")),
                ("daily", t("stats_scope_today")),
                ("7d", t("stats_scope_7_days")),
                ("30d", t("stats_scope_30_days")),
                ("365d", t("stats_scope_year")),
                ("lifetime", t("stats_scope_all_time")),
            ]
        ):
            rb = QRadioButton(label)
            rb.setProperty("scope_key", key)
            if key == "daily":
                rb.setChecked(True)
            self._scope_group.addButton(rb, i)
            scope_row.addWidget(rb, 1)
        self._scope_widget = QWidget(self)
        self._scope_widget.setLayout(scope_row)
        outer.addWidget(self._scope_widget)

        goals = QFrame(self)
        self._goals_widget = goals
        goals.setFrameShape(QFrame.Shape.StyledPanel)
        goals.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        goals_layout = QVBoxLayout(goals)
        goals_layout.setContentsMargins(14, 12, 14, 12)
        goals_layout.setSpacing(6)

        goal_heading_row = QHBoxLayout()
        goal_heading = QLabel(t("stats_daily_goals"))
        goal_heading.setStyleSheet("font-weight: bold; font-size: 11pt;")
        goal_heading_row.addWidget(goal_heading)
        goal_heading_row.addStretch(1)
        edit_goals = QPushButton(t("stats_edit_goals"))
        edit_goals.setAccessibleName(t("stats_edit_goals_accessible"))
        qconnect(edit_goals.clicked, self._edit_goals)
        goal_heading_row.addWidget(edit_goals)
        goals_layout.addLayout(goal_heading_row)

        self._goal_hint = QLabel(goals)
        self._goal_hint.setWordWrap(True)
        goals_layout.addWidget(self._goal_hint)
        progress_row = QHBoxLayout()
        progress_row.setSpacing(14)
        self._goal_progress_bars = {}
        for metric, label in (
            ("cards", t("stats_cards")),
            ("pages", t("stats_pages")),
            ("minutes", t("stats_minutes")),
        ):
            bar = QProgressBar(goals)
            bar.setRange(0, 100)
            bar.setAccessibleName(t("stats_goal_progress_accessible", label=label))
            self._goal_progress_bars[metric] = bar
            progress_row.addWidget(bar, 1)
        goals_layout.addLayout(progress_row)

        self._goal_status = QLabel("")
        self._goal_status.setWordWrap(True)
        self._goal_status.setAccessibleName(t("stats_status_accessible"))
        self._goal_status.hide()
        goals_layout.addWidget(self._goal_status)
        outer.addWidget(goals)
        self._refresh_goal_progress()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.35); }")
        outer.addWidget(sep)

        # Scrollable content
        scroll = QScrollArea()
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._clayout = QVBoxLayout(self._content)
        self._clayout.setContentsMargins(6, 6, 6, 6)
        self._clayout.setSpacing(14)
        scroll.setWidget(self._content)
        outer.addWidget(scroll, stretch=1)

        # Close button
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton(t("stats_progress_refresh"))
        qconnect(refresh_btn.clicked, self._reload_statistics)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        export_btn = QPushButton(t("stats_export_history_csv"))
        export_btn.setAccessibleName(t("stats_export_history_csv_accessible"))
        qconnect(export_btn.clicked, self._export_csv)
        btn_row.addWidget(export_btn)
        close_btn = QPushButton(t("common_close"))
        qconnect(close_btn.clicked, self.accept)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        qconnect(self._scope_group.buttonClicked, lambda _: self._refresh())
        qconnect(self._view_tabs.currentChanged, self._select_view)
        self._refresh()

    def _select_view(self, index):
        self._view = ("overview", "documents", "learning")[index]
        self._scope_widget.setVisible(index == 0)
        self._goals_widget.setVisible(index == 0)
        self._refresh()
        self._scroll.verticalScrollBar().setValue(0)

    def _edit_goals(self) -> None:
        dialog = StatisticsGoalsDialog(self._goals, self._history, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._save_goals(dialog.goals())

    def _save_goals(self, requested: dict) -> None:
        try:
            self._goals = set_statistics_goals(
                self._addon_dir,
                self._profile,
                requested,
            )
        except Exception:
            self._show_status(t("stats_save_goals_failed"))
            return
        self._show_status(t("stats_goals_saved"))
        self._refresh_goal_progress()
        self._refresh()

    def _reload_statistics(self) -> None:
        if self._closed or _active_profile() != self._profile:
            return
        self._reload_progress_data()
        self._invalidate_library_data()
        self._learning_history = None
        self._learning_history_requested = False
        self._request_learning_outcomes()
        self._refresh()

    def _reload_progress_data(self) -> None:
        self._media_cache.clear()
        self._raw = load_stats(self._addon_dir, self._profile)
        try:
            self._history = load_daily_history(
                self._addon_dir, self._profile, days=730, day_end_time=self._day_end_time,
            )
        except Exception:
            self._history = []
        self._refresh_goal_progress()

    def _show_status(self, message: str) -> None:
        self._goal_status.setText(message)
        self._goal_status.show()

    def _today_history_row(self) -> dict:
        logical_date = _effective_date(self._day_end_time)
        for row in reversed(self._history):
            if str(row.get("date") or "") == logical_date:
                return row
        return {
            "date": logical_date,
            "counts": _empty(),
            "seconds": _empty_time(),
            "reading": {},
        }

    def _refresh_goal_progress(self) -> None:
        progress = _daily_goal_progress(self._today_history_row(), self._goals)
        self._goal_hint.setText(t(
            "stats_goal_dashboard_hint" if any(values["target"] > 0 for values in progress.values())
            else "stats_goal_empty"
        ))
        labels = {
            "cards": t("stats_cards"),
            "pages": t("stats_pages"),
            "minutes": t("stats_minutes"),
        }
        for metric, values in progress.items():
            bar = self._goal_progress_bars[metric]
            target = float(values["target"])
            value = float(values["value"])
            bar.setVisible(target > 0)
            if target <= 0:
                bar.setValue(0)
                bar.setFormat(
                    t("stats_goal_off", label=labels[metric], value=_format_count(value))
                )
            else:
                bar.setValue(int(round(float(values["ratio"]) * 100)))
                bar.setFormat(
                    t(
                        "stats_goal_progress",
                        label=labels[metric],
                        value=_format_count(value),
                        target=_format_count(target),
                    )
                )

    def _export_csv(self) -> None:
        default_name = f"incremento-statistics-{_effective_date(self._day_end_time)}.csv"
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            t("stats_export_dialog_title"),
            default_name,
            t("stats_export_file_filter"),
        )
        if not path:
            return
        try:
            Path(path).write_text(
                daily_history_csv(self._history[-365:]),
                encoding="utf-8",
            )
        except Exception:
            self._show_status(t("stats_export_failed"))
            return
        self._show_status(t("stats_exported"))

    def _show_day_drilldown(self, detail: dict) -> None:
        text = t(
            "stats_day_detail",
            date=detail.get("date") or t("stats_selected_day"),
            cards=_format_count(float(detail.get("cards", 0))),
            topics=_format_count(float(detail.get("topics", 0))),
            items=_format_count(float(detail.get("items", 0))),
            other=_format_count(float(detail.get("other_cards", 0))),
            pdf_pages=_format_count(float(detail.get("pdf_pages", 0))),
            epub_pages=_format_count(float(detail.get("epub_pages", 0))),
            duration=_fmt_duration(float(detail.get("seconds", 0))),
        )
        try:
            self._day_drilldown_label.setText(text)
        except (AttributeError, RuntimeError):
            pass

    def _add_history_heatmap(self, history: list[dict]) -> None:
        container = QWidget(self._content)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 4)
        layout.setSpacing(10)
        heading_row = QHBoxLayout()
        heading_row.setSpacing(8)
        heading = QLabel(t("stats_activity_heatmap"))
        heading.setStyleSheet("font-weight: bold; font-size: 10pt;")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(QLabel(t("stats_color_by")))
        metric_combo = QComboBox(container)
        for label, metric in (
            (t("stats_all_activity"), "activity"),
            (t("stats_cards"), "cards"),
            (t("stats_pages"), "pages"),
            (t("stats_minutes"), "minutes"),
        ):
            metric_combo.addItem(label, metric)
        metric_combo.setAccessibleName(t("stats_heatmap_metric_accessible"))
        heading_row.addWidget(metric_combo)
        layout.addLayout(heading_row)

        heatmap_holder = QWidget(container)
        heatmap_layout = QVBoxLayout(heatmap_holder)
        heatmap_layout.setContentsMargins(0, 0, 0, 0)
        heatmap_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(heatmap_holder)
        self._day_drilldown_label = QLabel(
            t("stats_heatmap_select_day"),
            container,
        )
        self._day_drilldown_label.setWordWrap(True)
        self._day_drilldown_label.setAccessibleName(t("stats_selected_day_accessible"))
        layout.addWidget(self._day_drilldown_label)

        def rebuild(*_args) -> None:
            while heatmap_layout.count():
                item = heatmap_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            heatmap_layout.addWidget(
                _ActivityHeatmap(
                    history,
                    metric=str(metric_combo.currentData() or "activity"),
                    on_day_selected=self._show_day_drilldown,
                    parent=heatmap_holder,
                )
            )

        qconnect(metric_combo.currentIndexChanged, rebuild)
        rebuild()
        self._clayout.addWidget(container)

    def _refresh_history(self, days: int) -> None:
        self._add_progress_dashboard({7: "7d", 30: "30d", 365: "365d"}[days])
        if days in {7, 30}:
            self._add_learning_history(days)
        history = list(self._history[-days:])
        media_activity = self._add_media_activity({7: "7d", 30: "30d", 365: "365d"}[days])

        insight = QLabel(_history_insight(history))
        insight.setWordWrap(True)
        insight.setStyleSheet(
            "color: gray; padding: 6px 4px 8px 4px; font-size: 9pt;"
        )
        self._clayout.addWidget(insight)

        self._add_history_heatmap(history)

        chart_data = _history_chart_series(history)

        def has_values(series) -> bool:
            return any(
                any(float(value) > 0 for value in values)
                for _name, values in series
            )

        show_daily_charts = days <= 30
        if show_daily_charts and has_values(chart_data["cards"]):
            self._clayout.addWidget(
                _trend_section(
                    t("stats_cards_by_day"),
                    chart_data["labels"],
                    chart_data["cards"],
                    _TREND_CARD_COLORS,
                    self._content,
                )
            )
        if show_daily_charts and has_values(chart_data["pages"]):
            self._clayout.addWidget(
                _trend_section(
                    t("stats_pages_by_day"),
                    chart_data["labels"],
                    chart_data["pages"],
                    _TREND_PAGE_COLORS,
                    self._content,
                )
            )
        if show_daily_charts and has_values(chart_data["minutes"]):
            self._clayout.addWidget(
                _trend_section(
                    t("stats_time_by_day"),
                    chart_data["labels"],
                    chart_data["minutes"],
                    _TREND_TIME_COLORS,
                    self._content,
                    value_formatter=lambda value: _fmt_duration(value * 60.0),
                )
            )

        if not any(
            has_values(chart_data[key]) for key in ("cards", "pages", "minutes")
        ) and not any(media_activity.get(key, 0) for key in ("pages", "video_watch_seconds")) and not (days in {7, 30} and any(
            any(values) for _label, values in (learning_history_display(self._learning_history, days) or {}).get("series", [])
        )):
            note = QLabel(t("stats_no_history_activity"))
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setStyleSheet("color: gray; padding: 32px;")
            note.setWordWrap(True)
            self._clayout.addWidget(note)
        self._clayout.addStretch()

    def _add_learning_history(self, days: int, *, compact=False) -> None:
        container = QFrame(self._content)
        container.setObjectName("learningHistoryPanel")
        container.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        heading = QLabel(t("stats_learning_history_title", days=days), container)
        heading.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(heading)
        display = learning_history_display(self._learning_history, days)
        if display is None:
            message = QLabel(t(
                "stats_learning_results_loading" if self._learning_history_loading else "stats_learning_results_unavailable",
            ), container)
            message.setWordWrap(True)
            layout.addWidget(message)
        else:
            metrics = QHBoxLayout()
            for label, value in display["metrics"]:
                metrics.addWidget(_metric_card(label, value, container))
            layout.addLayout(metrics)
            comparison = QLabel(display["comparison"], container)
            comparison.setWordWrap(True)
            comparison.setAccessibleName(t("stats_comparison_accessible"))
            layout.addWidget(comparison)
            counts_chart = _trend_section(
                t("stats_learning_answers_by_day"), display["labels"],
                display["series"], _LEARNING_TREND_COLORS, container,
            )
            counts_chart.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            charts = QHBoxLayout() if compact else QVBoxLayout()
            charts.addWidget(counts_chart, 1)
            rate_panel = QWidget(container)
            rate_layout = QVBoxLayout(rate_panel)
            rate_layout.setContentsMargins(0, 10, 0, 0)
            rate_heading = QLabel(t("stats_recall_rate_by_day"), container)
            rate_heading.setStyleSheet("font-weight: bold; font-size: 10pt;")
            rate_layout.addWidget(rate_heading)
            rate_layout.addWidget(_RecallRateChart(
                display["labels"], display["rates"], display["daily_details"], container,
            ))
            charts.addWidget(rate_panel, 1)
            layout.addLayout(charts)
            if compact and display["daily_details"]:
                day_row = QHBoxLayout()
                selected_day = QComboBox(container)
                selected_day.setAccessibleName(t("stats_learning_inspect_day"))
                for label in display["labels"]:
                    selected_day.addItem(label)
                selected_day.setCurrentIndex(len(display["labels"]) - 1)
                detail = QLabel(display["daily_details"][-1], container)
                detail.setObjectName("learningDayDetail")
                detail.setWordWrap(True)
                selected_day.currentIndexChanged.connect(lambda index: detail.setText(display["daily_details"][index]))
                day_row.addWidget(selected_day)
                day_row.addWidget(detail, 1)
                layout.addLayout(day_row)
            hint = QLabel(t("stats_recall_chart_hint"), container)
            hint.setWordWrap(True)
            hint.setStyleSheet("font-size: 8pt;")
            layout.addWidget(hint)
        container.setMinimumHeight(layout.minimumSize().height())
        self._clayout.addWidget(container)

    def _add_learning_view(self):
        controls = QHBoxLayout()
        title = QLabel(t("stats_view_learning"), self._content)
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        controls.addWidget(title, 1)
        period = QComboBox(self._content)
        for days in (7, 30):
            period.addItem(tn("stats_progress_last_days", days), days)
        period.setAccessibleName(t("stats_learning_period"))
        period.setCurrentIndex(0 if self._learning_days == 7 else 1)
        def change_period(index):
            self._learning_days = period.itemData(index)
            self._refresh()
        period.currentIndexChanged.connect(change_period)
        controls.addWidget(period)
        # The content clearer owns widgets, so wrap the heading layout as well.
        header = QWidget(self._content)
        header.setLayout(controls)
        self._clayout.addWidget(header)
        self._clayout.addWidget(CardStagePanel(self._card_states, loading=self._card_states_loading, parent=self._content))
        self._add_learning_history(self._learning_days, compact=True)
        self._clayout.addStretch()

    def _add_learning_outcomes(self) -> None:
        container = QFrame(self._content)
        container.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        heading = QLabel(t("stats_learning_results_title"), container)
        heading.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(heading)
        display = learning_outcome_display(self._learning_outcomes)
        if display is None:
            message = QLabel(t(
                "stats_learning_results_loading" if self._learning_loading else "stats_learning_results_unavailable",
            ), container)
            message.setWordWrap(True)
            layout.addWidget(message)
        else:
            metrics = QHBoxLayout()
            for label, value in display["metrics"]:
                metrics.addWidget(_metric_card(label, value, container))
            layout.addLayout(metrics)
            table = QTableWidget(len(display["rows"]), len(display["headers"]), container)
            table.setAccessibleName(t("stats_learning_results_title"))
            table.setHorizontalHeaderLabels(display["headers"])
            table.verticalHeader().hide()
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for row_index, row in enumerate(display["rows"]):
                for column_index, value in enumerate(row):
                    table.setItem(row_index, column_index, QTableWidgetItem(value))
            table.resizeRowsToContents()
            table.setFixedHeight(table.horizontalHeader().height() + table.verticalHeader().length() + 12)
            layout.addWidget(table)
            hint = QLabel(display["hint"], container)
            hint.setWordWrap(True)
            hint.setStyleSheet("font-size: 8pt;")
            layout.addWidget(hint)
        self._clayout.addWidget(container)

    def _add_topic_item_tag_pies(self, breakdown: dict) -> None:
        container = QFrame(self._content)
        container.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(5)

        hint = QLabel(t("stats_topic_item_pie_hint"), container)
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        charts = QHBoxLayout()
        charts.setSpacing(14)
        for title, kind in (
            (t("stats_topic_tag_time"), "topics"),
            (t("stats_item_tag_time"), "items"),
        ):
            panel = QWidget(container)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            heading = QLabel(title, panel)
            heading.setStyleSheet("font-weight: bold; font-size: 10pt;")
            panel_layout.addWidget(heading)
            panel_layout.addWidget(
                _PieChart(
                    title,
                    _topic_item_pie_items(breakdown, kind),
                    _TAG_COLORS,
                    panel,
                )
            )
            charts.addWidget(panel, 1)
        layout.addLayout(charts)
        self._clayout.addWidget(container)

    def _add_media_activity(self, scope: str) -> dict:
        activity = self._get_media_activity(scope)

        container = QFrame(self._content)
        container.setObjectName("mediaActivityPanel")
        container.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        heading = QLabel(t("stats_reading_video_activity"), container)
        heading.setStyleSheet("font-weight: bold; font-size: 11pt;")
        layout.addWidget(heading)
        metrics = QHBoxLayout()
        for label, value in (
            (t("stats_pages_read"), _format_count(activity.get("pages", 0))),
            (t("stats_pdf_pages_read"), _format_count(activity.get("pdf_pages", 0))),
            (t("stats_epub_pages_read"), _format_count(activity.get("epub_pages", 0))),
            (t("stats_videos_watched"), _format_count(activity.get("videos_watched", 0))),
            (t("stats_video_watch_time"), _fmt_duration(float(activity.get("video_watch_seconds", 0)))),
        ):
            metrics.addWidget(_metric_card(label, value, container))
        layout.addLayout(metrics)
        hint = QLabel(t("stats_video_watch_hint"), container)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(hint)
        self._clayout.addWidget(container)
        return activity

    def _get_media_activity(self, scope: str) -> dict:
        days = {"daily": 1, "7d": 7, "30d": 30, "365d": 365, "lifetime": None}[scope]
        cache_key = (scope, _effective_date(self._day_end_time))
        if cache_key not in self._media_cache:
            try:
                self._media_cache[cache_key] = load_media_activity(
                    self._addon_dir, self._profile,
                    days=days, day_end_time=self._day_end_time,
                )
            except Exception:
                self._media_cache[cache_key] = {}
        return self._media_cache[cache_key]

    def _add_progress_dashboard(self, scope: str) -> None:
        days = {"daily": 7, "7d": 7, "30d": 30, "365d": 365, "lifetime": 30}[scope]
        model = progress_model(self._history, end_date=_effective_date(self._day_end_time), days=days)
        totals = dict(model["totals"])
        comparison = model["comparison"]
        comparison_days = days
        if scope in {"daily", "lifetime"}:
            activity = self._get_media_activity(scope)
            counts = self._get_counts(scope)
            totals = {
                "cards": float(sum(counts["type"].values())),
                "minutes": _history_total_seconds(self._get_time(scope)) / 60,
                **{metric: float(activity.get(metric, 0) or 0) for metric in ("pages", "pdf_pages", "epub_pages")},
            }
            comparison_days = 1
            comparison = None
            if scope == "daily":
                today = progress_model(self._history, end_date=_effective_date(self._day_end_time), days=1)
                # Keep the overview and goal meters on the same normalized row.
                if any(row.get("date") == _effective_date(self._day_end_time) for row in self._history):
                    totals["cards"] = today["totals"]["cards"]
                    totals["minutes"] = today["totals"]["minutes"]
                comparison = today["comparison"]
        scope_label = t({"daily": "stats_scope_today", "7d": "stats_scope_7_days", "30d": "stats_scope_30_days",
                         "365d": "stats_scope_year", "lifetime": "stats_scope_all_time"}[scope])
        graph_label = tn("stats_progress_last_days", days)
        self._clayout.addWidget(ProgressDashboard(
            model, totals=totals, scope_label=scope_label, graph_label=graph_label,
            goals=self._goals, comparison=comparison, comparison_days=comparison_days,
            format_value=lambda metric, value: _fmt_duration(value * 60) if metric == "minutes" else _format_count(value),
            metric=self._progress_metric, on_metric_changed=lambda metric: setattr(self, "_progress_metric", metric),
            parent=self._content,
        ))

    def _refresh(self) -> None:
        if self._closed or _active_profile() != self._profile:
            return
        if self._learning_date != _effective_date(self._day_end_time):
            self._reload_progress_data()
            self._invalidate_library_data()
            self._learning_history = None
            self._learning_history_requested = False
            self._request_learning_outcomes()
        # Clear previous content
        while self._clayout.count():
            item = self._clayout.takeAt(0)
            if w := item.widget():
                w.deleteLater()

        if self._view == "documents":
            request = not self._documents_requested
            if request:
                self._documents_loading = True
            def filter_changed(query, kind):
                self._document_query, self._document_kind = query, kind
            self._clayout.addWidget(DocumentProgressPanel(
                self._documents, loading=self._documents_loading, query=self._document_query,
                kind=self._document_kind, on_filter=filter_changed, parent=self._content,
            ), 1)
            if request:
                self._request_library_data("documents")
            return
        if self._view == "learning":
            request_states = not self._card_states_requested
            request_history = not self._learning_history_requested
            if request_states:
                self._card_states_loading = True
            if request_history:
                self._learning_history_loading = True
            self._add_learning_view()
            # Mark both before dispatch; an unavailable result may arrive synchronously.
            self._card_states_requested = self._learning_history_requested = True
            if request_states:
                self._request_library_data("card_states")
            if request_history:
                self._request_learning_history()
            return

        checked = self._scope_group.checkedButton()
        scope = checked.property("scope_key") if checked else "session"
        if scope in {"7d", "30d", "365d"}:
            request_history = scope in {"7d", "30d"} and not self._learning_history_requested
            if request_history:
                self._learning_history_requested = True
                self._learning_history_loading = True
            history_days = {"7d": 7, "30d": 30, "365d": 365}[scope]
            self._refresh_history(history_days)
            if request_history:
                self._request_learning_history()
            return
        counts = self._get_counts(scope)
        time_stats = self._get_time(scope)

        total = float(sum(counts["type"].values()))
        type_seconds = float(sum(time_stats["type"].values()))
        tag_seconds = float(sum(time_stats["tags"].values()))
        total_seconds = type_seconds if type_seconds > 0 else tag_seconds

        if scope in {"daily", "lifetime"}:
            self._add_progress_dashboard(scope)
        else:
            summary = QWidget(self._content)
            summary_lay = QHBoxLayout(summary)
            summary_lay.setContentsMargins(0, 0, 0, 4)
            summary_lay.setSpacing(6)
            for label, value in _summary_metrics(counts, time_stats):
                summary_lay.addWidget(_metric_card(label, value, summary))
            self._clayout.addWidget(summary)

        media_activity = (
            self._add_media_activity(scope)
            if scope in {"daily", "lifetime"} else {}
        )

        if scope == "daily":
            self._add_learning_outcomes()

        if scope in {"daily", "lifetime"}:
            self._add_topic_item_tag_pies(self._get_tag_breakdown(scope))

        if total == 0 and total_seconds <= 0 and not any(
            media_activity.get(key, 0) for key in ("pages", "video_watch_seconds")
        ):
            if scope == "daily" and (self._learning_outcomes or {}).get("cards", 0) > 0:
                self._clayout.addStretch()
                return
            hint = (
                t("stats_no_session_statistics")
                if scope == "session"
                else t("stats_no_scope_statistics")
            )
            note = QLabel(hint)
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setStyleSheet("color: gray; padding: 32px;")
            note.setWordWrap(True)
            self._clayout.addWidget(note)
            self._clayout.addStretch()
            return

        # Card types
        type_items = _ordered_type_items(counts["type"])
        if type_items:
            self._clayout.addWidget(
                _section(
                    t("stats_card_type_distribution"),
                    type_items,
                    _TYPE_COLORS,
                    self._content,
                )
            )

        # Mode
        mode_items = _ordered_mode_items(counts["mode"])
        if mode_items:
            self._clayout.addWidget(
                _section(
                    t("stats_mode_distribution"),
                    mode_items,
                    _MODE_COLORS,
                    self._content,
                )
            )

        # Tags
        sorted_tags = _tag_items(counts["tags"])
        if sorted_tags:
            self._clayout.addWidget(
                _section(
                    t("stats_tags"),
                    sorted_tags,
                    _TAG_COLORS,
                    self._content,
                )
            )

        # Time by card type
        time_type_items = _ordered_type_items(time_stats["type"])
        if time_type_items:
            self._clayout.addWidget(
                _section(
                    t("stats_review_time_by_type"),
                    time_type_items,
                    _TYPE_COLORS,
                    self._content,
                    value_formatter=_fmt_duration,
                )
            )

        # Time by tag
        sorted_ttags = _tag_items(time_stats["tags"])
        if sorted_ttags:
            self._clayout.addWidget(
                _section(
                    t("stats_review_time_by_tag"),
                    sorted_ttags,
                    _TAG_COLORS,
                    self._content,
                    value_formatter=_fmt_duration,
                )
            )

        self._clayout.addStretch()
