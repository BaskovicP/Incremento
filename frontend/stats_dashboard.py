"""Native, offline progress overview for the statistics dialog."""

from __future__ import annotations

import math

from aqt.qt import (
    QColor, QFrame, QHBoxLayout, QLabel, QLayout, QPainter, QPainterPath,
    QPen, QPointF, QPushButton, QRectF, QSizePolicy, Qt, QVBoxLayout, QWidget,
)

try:
    from ..backend.i18n import format_date, format_number, t, tn
except ImportError:
    from backend.i18n import format_date, format_number, t, tn


_COLORS = {"pages": "#e0a020", "epub": "#8e6ad8", "minutes": "#1abc9c", "cards": "#4a90d9"}
_LIGHT_COLORS = {"pages": "#a56808", "epub": "#7652bb", "minutes": "#087f6e", "cards": "#2766ac"}


def _color(widget, metric):
    dark = widget.palette().window().color().lightness() < 128
    return QColor((_COLORS if dark else _LIGHT_COLORS)[metric])


def _metric_name(metric):
    return t({"pages": "stats_pages_read", "minutes": "stats_study_time", "cards": "stats_cards_studied"}[metric])


def _label(text, parent, *, style=""):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if style:
        label.setStyleSheet(style)
    return label


def _date_range(bucket):
    start = format_date(bucket["start"], format="short")
    end = format_date(bucket["end"], format="short")
    return start if bucket["start"] == bucket["end"] else f"{start} – {end}"


class ProgressChart(QWidget):
    """A zero-based graph with identical mouse, keyboard and text inspection."""

    def __init__(self, model, *, cumulative, format_value, on_selected, parent=None):
        super().__init__(parent)
        self.model = model
        self.cumulative = cumulative
        self.format_value = format_value
        self.on_selected = on_selected
        self.metric = "pages"
        self.goal = 0.0
        self.selected = len(model["buckets"]) - 1
        self.setMinimumHeight(194)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_metric(self, metric, goal):
        self.metric = metric
        # A weekly bucket must never be compared with a one-day target.
        self.goal = max(0.0, float(goal or 0)) if not self.cumulative and len(self.model["daily"]) <= 31 else 0
        title = t("stats_progress_cumulative") if self.cumulative else t("stats_progress_daily")
        self.setAccessibleName(t("stats_progress_chart_title", metric=_metric_name(metric), title=title))
        self.describe_selection()
        self.update()

    def describe_selection(self):
        detail = self.detail(self.selected)
        if not any(self.values()):
            detail = t("stats_progress_empty") + "\n" + detail
        if self.goal:
            detail += "\n" + t("stats_progress_goal_line", value=self.format_value(self.metric, self.goal))
        self.setAccessibleDescription(t("stats_progress_chart_accessible", details=detail))

    def values(self):
        return self.model["cumulative"][self.metric] if self.cumulative else [
            row[self.metric] for row in self.model["buckets"]
        ]

    def detail(self, index):
        row = self.model["buckets"][index]
        return t(
            "stats_progress_day_detail", date=_date_range(row),
            pages=self.format_value("pages", row["pages"]),
            pdf=self.format_value("pages", row["pdf_pages"]),
            epub=self.format_value("pages", row["epub_pages"]),
            duration=self.format_value("minutes", row["minutes"]),
            cards=self.format_value("cards", row["cards"]),
            total=self.format_value(self.metric, self.model["cumulative"][self.metric][index]),
            metric=_metric_name(self.metric),
        )

    def _plot(self):
        largest = max([self.goal, *self.values()], default=0)
        if largest > 0:
            unit = 10 ** math.floor(math.log10(largest))
            maximum = next(factor * unit for factor in (1, 2, 5, 10) if factor * unit >= largest)
        else:
            maximum = 5
        fm = self.fontMetrics()
        left = min(self.width() // 3, max(42, fm.horizontalAdvance(self.format_value(self.metric, maximum)) + 10))
        line_height = fm.height() + 2
        return QRectF(left, line_height + 2, max(1, self.width() - left - 14),
                      max(1, self.height() - 2 * line_height - 14)), maximum

    def _index_at(self, point):
        plot, _maximum = self._plot()
        if not plot.contains(point):
            return None
        return min(len(self.model["buckets"]) - 1, int((point.x() - plot.left()) / plot.width() * len(self.model["buckets"])))

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        self.setToolTip(self.detail(index) if index is not None else "")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position())
            if index is not None:
                self.setFocus()
                self.on_selected(index)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        last = len(self.model["buckets"]) - 1
        target = {Qt.Key.Key_Left: max(0, self.selected - 1),
                  Qt.Key.Key_Right: min(last, self.selected + 1),
                  Qt.Key.Key_Home: 0, Qt.Key.Key_End: last}.get(event.key())
        if target is not None:
            self.on_selected(target)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot, maximum = self._plot()
        text_color = self.palette().text().color()
        grid = QColor(text_color)
        grid.setAlpha(35)
        values = self.values()
        if not values:
            painter.end()
            return
        slot = plot.width() / len(values)
        color = _color(self, self.metric)
        line_height = painter.fontMetrics().height() + 2

        for fraction in (0, .5, 1):
            y = plot.bottom() - plot.height() * fraction
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(text_color)
            label = painter.fontMetrics().elidedText(self.format_value(self.metric, maximum * fraction),
                                                    Qt.TextElideMode.ElideRight, int(plot.left() - 8))
            painter.drawText(QRectF(0, y - line_height / 2, plot.left() - 8, line_height),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)

        selection = QColor(color)
        selection.setAlpha(16)
        painter.fillRect(QRectF(plot.left() + self.selected * slot, plot.top(), slot, plot.height()), selection)
        if self.cumulative:
            points = [QPointF(plot.left() + (index + .5) * slot,
                              plot.bottom() - plot.height() * value / maximum)
                      for index, value in enumerate(values)]
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            area = QPainterPath(path)
            area.lineTo(points[-1].x(), plot.bottom())
            area.lineTo(points[0].x(), plot.bottom())
            area.closeSubpath()
            fill = QColor(color)
            fill.setAlpha(28)
            painter.fillPath(area, fill)
            painter.setPen(QPen(color, 2.5))
            painter.drawPath(path)
            painter.setBrush(color)
            painter.drawEllipse(points[self.selected], 4, 4)
        else:
            for index, row in enumerate(self.model["buckets"]):
                x = plot.left() + (index + .18) * slot
                width = max(1, slot * .64)
                bottom = plot.bottom()
                parts = [(row["pdf_pages"], _color(self, "pages")), (row["epub_pages"], _color(self, "epub"))] if self.metric == "pages" else [(row[self.metric], color)]
                for value, shade in parts:
                    height = plot.height() * value / maximum
                    if height > 0:
                        painter.fillRect(QRectF(x, bottom - height, width, height), QColor(shade))
                        bottom -= height
            if self.goal > 0:
                y = plot.bottom() - plot.height() * self.goal / maximum
                painter.setPen(QPen(text_color, 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                goal_text = painter.fontMetrics().elidedText(
                    t("stats_progress_goal_line", value=self.format_value(self.metric, self.goal)),
                    Qt.TextElideMode.ElideLeft, int(plot.width()),
                )
                painter.drawText(QRectF(plot.left(), y - line_height - 2, plot.width(), line_height),
                                 Qt.AlignmentFlag.AlignRight, goal_text)

        # Fit whole localized dates and skip any labels that would overlap.
        painter.setPen(text_color)
        last_right = -1
        indices = sorted({0, len(values) // 2, len(values) - 1})
        for index in indices:
            label = format_date(self.model["buckets"][index]["end"], format="short")
            width = painter.fontMetrics().horizontalAdvance(label) + 4
            x = max(plot.left(), min(plot.right() - width, plot.left() + (index + .5) * slot - width / 2))
            if x < last_right + 8:
                continue
            painter.drawText(QRectF(x, plot.bottom() + 8, width, line_height), Qt.AlignmentFlag.AlignLeft, label)
            last_right = x + width
        if self.hasFocus():
            painter.setPen(QPen(self.palette().highlight().color(), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 5, 5)
        painter.end()


class ProgressDashboard(QWidget):
    """Prominent totals followed by selectable daily and cumulative graphs."""

    def __init__(self, model, *, totals, scope_label, graph_label, goals,
                 comparison, comparison_days, format_value, metric="pages",
                 on_metric_changed=None, parent=None):
        super().__init__(parent)
        self.setObjectName("progressDashboard")
        self.model, self.goals = model, goals
        self.format_value = format_value
        self.on_metric_changed = on_metric_changed
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setStyleSheet(
            "QFrame#progressMetric, QFrame#progressPlot { border: 1px solid rgba(128,128,128,0.28); border-radius: 10px; }"
            "QPushButton[progressSelector='true'] { padding: 5px 12px; border: 1px solid rgba(128,128,128,0.35); border-radius: 6px; }"
            "QPushButton[progressSelector='true']:checked { background: rgba(74,144,217,0.18); border: 1px solid #4a90d9; }"
            "QPushButton[progressSelector='true']:focus { border: 2px solid #4a90d9; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(12)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        heading = QHBoxLayout()
        heading.addWidget(_label(t("stats_progress_heading", scope=scope_label), self, style="font-size: 17pt; font-weight: bold;"), 1)
        streak = _label(tn("stats_progress_streak", model["reading_streak"]), self,
                        style="padding: 6px 10px; background: rgba(224,160,32,0.12); border-radius: 6px;")
        streak.setToolTip(t("stats_progress_streak_hint"))
        heading.addWidget(streak)
        layout.addLayout(heading)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        for key in ("pages", "minutes", "cards"):
            tile = QFrame(self)
            tile.setObjectName("progressMetric")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(14, 10, 14, 10)
            tile_layout.setSpacing(4)
            tile_layout.addWidget(_label(_metric_name(key), tile, style="font-weight: bold;"))
            value = _label(format_value(key, totals[key]), tile,
                           style=f"font-size: 28pt; font-weight: bold; color: {_color(self, key).name()};")
            value.setObjectName({"pages": "progressPagesValue", "minutes": "progressTimeValue", "cards": "progressCardsValue"}[key])
            tile_layout.addWidget(value)
            if key == "pages":
                hint = t("stats_progress_formats", pdf=format_value("pages", totals["pdf_pages"]),
                         epub=format_value("pages", totals["epub_pages"]))
            else:
                hint = t("stats_progress_time_hint" if key == "minutes" else "stats_progress_cards_hint")
            tile_layout.addWidget(_label(hint, tile, style="font-size: 9pt;"))
            if comparison is not None:
                before = comparison[key]
                if before["percent"] is None:
                    text = t("stats_progress_no_baseline")
                else:
                    percent = round(before["percent"])
                    change = ("+" if percent > 0 else "") + format_number(percent) + "%"
                    text = t("stats_progress_comparison", change=change, days=comparison_days)
                tile_layout.addWidget(_label(text, tile, style="font-size: 9pt;"))
            tiles.addWidget(tile, 1)
        layout.addLayout(tiles)

        toolbar = QHBoxLayout()
        toolbar.addWidget(_label(t("stats_progress_graph_window", period=graph_label), self,
                                 style="font-size: 10pt; font-weight: bold;"), 1)
        self._buttons = {}
        for key, title in (("pages", t("stats_pages")), ("minutes", t("stats_study_time")), ("cards", t("stats_cards"))):
            button = QPushButton(title, self)
            button.setCheckable(True)
            button.setProperty("metric", key)
            button.setProperty("progressSelector", True)
            button.setAccessibleName(t("stats_progress_show_metric", metric=title))
            button.clicked.connect(lambda _checked=False, key=key: self.set_metric(key))
            toolbar.addWidget(button)
            self._buttons[key] = button
        layout.addLayout(toolbar)
        layout.addWidget(_label(t("stats_progress_consistency",
            reading=model["reading_days"], active=model["active_days"], days=len(model["daily"]),
            average=format_number(round(model["totals"]["pages"] / len(model["daily"]), 1))),
            self, style="font-size: 9pt;"))

        graphs = QHBoxLayout()
        graphs.setSpacing(12)
        self.charts, self._chart_titles, self._chart_captions, self._empty_labels = [], [], [], []
        for cumulative in (False, True):
            panel = QFrame(self)
            panel.setObjectName("progressPlot")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(12, 10, 12, 8)
            panel_layout.setSpacing(4)
            title = _label("", panel, style="font-size: 11pt; font-weight: bold;")
            panel_layout.addWidget(title)
            caption = _label("", panel, style="font-size: 9pt;")
            panel_layout.addWidget(caption)
            empty = _label(t("stats_progress_empty"), panel, style="font-size: 9pt;")
            empty.setObjectName("progressEmptyMessage")
            panel_layout.addWidget(empty)
            self._empty_labels.append(empty)
            chart = ProgressChart(model, cumulative=cumulative, format_value=format_value,
                                  on_selected=self.select_day, parent=panel)
            panel_layout.addWidget(chart)
            self.charts.append(chart)
            self._chart_titles.append(title)
            self._chart_captions.append(caption)
            graphs.addWidget(panel, 1)
        layout.addLayout(graphs)
        self._detail = _label("", self, style="font-size: 9pt; padding: 4px 2px;")
        self._detail.setObjectName("progressDayDetail")
        self._detail.setAccessibleName(t("stats_selected_day_accessible"))
        layout.addWidget(self._detail)
        hint = _label(t("stats_progress_interaction_hint"), self, style="font-size: 8pt;")
        layout.addWidget(hint)
        self.set_metric(metric)

    def select_day(self, index):
        for chart in self.charts:
            chart.selected = index
            chart.describe_selection()
            chart.update()
        self._detail.setText(self.charts[0].detail(index))

    def set_metric(self, metric):
        metric = metric if metric in self._buttons else "pages"
        for key, button in self._buttons.items():
            button.setChecked(key == metric)
        for chart in self.charts:
            chart.set_metric(metric, self.goals.get(metric, 0))
        for chart, label in zip(self.charts, self._empty_labels):
            label.setVisible(not any(chart.values()))
        self._chart_titles[0].setText(t("stats_progress_weekly" if len(self.model["daily"]) > 31 else "stats_progress_daily"))
        self._chart_titles[1].setText(t("stats_progress_cumulative"))
        if metric == "pages":
            # Keep the legend's colors consistent with the stacked page bars.
            self._chart_captions[0].setTextFormat(Qt.TextFormat.RichText)
            self._chart_captions[0].setText(t("stats_progress_page_legend",
                pdf_color=_color(self, "pages").name(), epub_color=_color(self, "epub").name()))
        else:
            self._chart_captions[0].setTextFormat(Qt.TextFormat.PlainText)
            self._chart_captions[0].setText(_metric_name(metric))
        self._chart_captions[1].setText(t("stats_progress_cumulative_caption",
            value=self.format_value(metric, self.model["totals"][metric]), metric=_metric_name(metric)))
        self.select_day(self.charts[0].selected)
        if callable(self.on_metric_changed):
            self.on_metric_changed(metric)
