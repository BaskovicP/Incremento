"""Statistics viewer dialog for Incremento."""

from __future__ import annotations

import math

from aqt import mw
from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    Qt,
    QButtonGroup,
    QRadioButton,
    QScrollArea,
    QPainter,
    QColor,
    QFrame,
    QSizePolicy,
    qconnect,
)

try:
    from ..backend.statistics import (
        load_stats,
        load_daily_history,
        _effective_date,
        _empty,
        _empty_time,
        _is_valid_counts_block,
        _is_valid_time_block,
        _normalize_counts_block,
        _normalize_time_block,
    )
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from statistics import (
        load_stats,
        load_daily_history,
        _effective_date,
        _empty,
        _empty_time,
        _is_valid_counts_block,
        _is_valid_time_block,
        _normalize_counts_block,
        _normalize_time_block,
    )
    from paths import get_active_profile as _active_profile  # type: ignore

# ── colour palettes ────────────────────────────────────────────────────────────
_TYPE_ORDER = ["topics", "items", "pdf", "epub", "youtube", "webpage"]
_TYPE_LABELS = {
    "topics": "Topics",
    "items": "Items",
    "pdf": "PDFs",
    "epub": "EPUBs",
    "youtube": "Videos",
    "webpage": "Web pages",
}
_TYPE_COLORS = ["#4a90d9", "#7bc67e", "#e0a020", "#8e6ad8", "#e05050", "#1abc9c"]
_MODE_COLORS = ["#e0a020", "#8da0cb"]  # Priority, Random
_MODE_LABELS = {
    "priority": "Priority",
    "random": "Random",
}
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

    def paintEvent(self, _event) -> None:
        if not self._labels:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().text().color()
        grid_color = QColor(
            text_color.red(), text_color.green(), text_color.blue(), 36
        )
        plot_w = max(1, self.width() - self._LEFT - self._RIGHT)
        plot_h = max(1, self.height() - self._TOP - self._BOTTOM)
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
            painter.drawLine(self._LEFT, y, self._LEFT + plot_w, y)
            painter.setPen(text_color)
            painter.drawText(
                0,
                y - 9,
                self._LEFT - 5,
                18,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._fmt(maximum * fraction),
            )

        slot_w = plot_w / max(1, len(self._labels))
        bar_w = max(2, int(slot_w * 0.62))
        for day_index, _label in enumerate(self._labels):
            x = self._LEFT + int(day_index * slot_w + (slot_w - bar_w) / 2)
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

        label_step = max(1, int(math.ceil(len(self._labels) / 7)))
        painter.setPen(text_color)
        for index, label in enumerate(self._labels):
            if index % label_step and index != len(self._labels) - 1:
                continue
            x = self._LEFT + int(index * slot_w)
            painter.drawText(
                x,
                self._TOP + plot_h + 5,
                max(24, int(slot_w * label_step)),
                self._BOTTOM - 5,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                label,
            )
        painter.end()


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
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


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
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


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
            items.append((_MODE_LABELS.get(key, key.replace("_", " ").title()), value))

    for key in ("priority", "random"):
        _append(key)
    for key in sorted(str(k) for k in mode_counts.keys()):
        if key not in seen:
            _append(key)

    return items


def _top_label(items: list[tuple[str, float]], empty: str = "None") -> str:
    if not items:
        return empty
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
        ("Cards studied", _format_count(total_cards)),
        ("Review time", _fmt_duration(total_seconds)),
        ("Avg/card", _fmt_duration(average_seconds)),
        ("Top type/tag", f"{top_type} / {top_tag}"),
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


def _history_summary_metrics(history: list[dict]) -> list[tuple[str, str]]:
    totals = [_history_row_totals(row) for row in history]
    cards = sum(item[0] for item in totals)
    pages = sum(item[1] for item in totals)
    seconds = sum(item[2] for item in totals)
    active_days = sum(1 for item in totals if any(value > 0 for value in item))
    return [
        ("Cards studied", _format_count(cards)),
        ("Pages read", _format_count(pages)),
        ("Study time", _fmt_duration(seconds)),
        ("Active days", f"{active_days} / {len(history)}"),
    ]


def _history_date_label(value) -> str:
    text = str(value or "")
    try:
        month = int(text[5:7])
        day = int(text[8:10])
    except Exception:
        return text[:10]
    return f"{month}/{day}"


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
            ("Topics", topics),
            ("Items", items),
            ("Other", other_cards),
        ],
        "pages": [("PDF", pdf_pages), ("EPUB", epub_pages)],
        "minutes": [("Minutes", minutes)],
    }


def _history_insight(history: list[dict]) -> str:
    totals = [_history_row_totals(row) for row in history]
    active = [item for item in totals if any(value > 0 for value in item)]
    if not active:
        return "No reading or study activity recorded in this range yet."

    index = len(totals) - 1
    if index >= 0 and not any(value > 0 for value in totals[index]):
        index -= 1
    streak = 0
    while index >= 0 and any(value > 0 for value in totals[index]):
        streak += 1
        index -= 1

    average_cards = sum(item[0] for item in active) / len(active)
    average_pages = sum(item[1] for item in active) / len(active)
    day_word = "day" if streak == 1 else "days"
    return (
        f"Current streak: {streak} {day_word} · Active-day average: "
        f"{_format_count(average_cards)} cards and "
        f"{_format_count(average_pages)} pages"
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
            items.append((_TYPE_LABELS.get(key, key.replace("_", " ").title()), value))

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
        profile = _active_profile()
        self._raw = load_stats(addon_dir, profile)
        try:
            self._history = load_daily_history(
                addon_dir,
                profile,
                days=30,
                day_end_time=day_end_time,
            )
        except Exception:
            self._history = []

        self.setWindowTitle("Incremento — Statistics")
        self.setMinimumWidth(650)
        self.setMinimumHeight(440)
        self._setup_ui()

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

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        # Scope radio buttons
        scope_row = QHBoxLayout()
        self._scope_group = QButtonGroup(self)
        for i, (key, label) in enumerate(
            [
                ("session", "This Session"),
                ("daily", "Today"),
                ("7d", "7 Days"),
                ("30d", "30 Days"),
                ("lifetime", "All Time"),
            ]
        ):
            rb = QRadioButton(label)
            rb.setProperty("scope_key", key)
            if i == 0:
                rb.setChecked(True)
            self._scope_group.addButton(rb, i)
            scope_row.addWidget(rb)
        scope_row.addStretch()
        outer.addLayout(scope_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.35); }")
        outer.addWidget(sep)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._clayout = QVBoxLayout(self._content)
        self._clayout.setContentsMargins(4, 4, 4, 4)
        self._clayout.setSpacing(6)
        scroll.setWidget(self._content)
        outer.addWidget(scroll, stretch=1)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        qconnect(close_btn.clicked, self.accept)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        qconnect(self._scope_group.buttonClicked, lambda _: self._refresh())
        self._refresh()

    def _refresh_history(self, days: int) -> None:
        history = list(self._history[-days:])
        summary = QWidget(self._content)
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 4)
        summary_layout.setSpacing(6)
        for label, value in _history_summary_metrics(history):
            summary_layout.addWidget(_metric_card(label, value, summary))
        self._clayout.addWidget(summary)

        insight = QLabel(_history_insight(history))
        insight.setWordWrap(True)
        insight.setStyleSheet(
            "color: gray; padding: 4px 2px 6px 2px; font-size: 9pt;"
        )
        self._clayout.addWidget(insight)

        chart_data = _history_chart_series(history)

        def has_values(series) -> bool:
            return any(
                any(float(value) > 0 for value in values)
                for _name, values in series
            )

        if has_values(chart_data["cards"]):
            self._clayout.addWidget(
                _trend_section(
                    "Cards Studied by Day",
                    chart_data["labels"],
                    chart_data["cards"],
                    _TREND_CARD_COLORS,
                    self._content,
                )
            )
        if has_values(chart_data["pages"]):
            self._clayout.addWidget(
                _trend_section(
                    "Pages Read by Day",
                    chart_data["labels"],
                    chart_data["pages"],
                    _TREND_PAGE_COLORS,
                    self._content,
                )
            )
        if has_values(chart_data["minutes"]):
            self._clayout.addWidget(
                _trend_section(
                    "Study Time by Day",
                    chart_data["labels"],
                    chart_data["minutes"],
                    _TREND_TIME_COLORS,
                    self._content,
                    value_formatter=lambda value: _fmt_duration(value * 60.0),
                )
            )

        if not any(
            has_values(chart_data[key]) for key in ("cards", "pages", "minutes")
        ):
            note = QLabel("No reading or study history recorded for this range yet.")
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setStyleSheet("color: gray; padding: 32px;")
            note.setWordWrap(True)
            self._clayout.addWidget(note)
        self._clayout.addStretch()

    def _refresh(self) -> None:
        # Clear previous content
        while self._clayout.count():
            item = self._clayout.takeAt(0)
            if w := item.widget():
                w.deleteLater()

        checked = self._scope_group.checkedButton()
        scope = checked.property("scope_key") if checked else "session"
        if scope in {"7d", "30d"}:
            self._refresh_history(7 if scope == "7d" else 30)
            return
        counts = self._get_counts(scope)
        time_stats = self._get_time(scope)

        total = float(sum(counts["type"].values()))
        type_seconds = float(sum(time_stats["type"].values()))
        tag_seconds = float(sum(time_stats["tags"].values()))
        total_seconds = type_seconds if type_seconds > 0 else tag_seconds

        summary = QWidget(self._content)
        summary_lay = QHBoxLayout(summary)
        summary_lay.setContentsMargins(0, 0, 0, 4)
        summary_lay.setSpacing(6)
        for label, value in _summary_metrics(counts, time_stats):
            summary_lay.addWidget(_metric_card(label, value, summary))
        self._clayout.addWidget(summary)

        if total == 0 and total_seconds <= 0:
            hint = (
                "No session statistics recorded yet."
                if scope == "session"
                else "No clean statistics data recorded for this scope."
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
                    "Card-Type Distribution",
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
                    "Mode Distribution",
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
                    "Tags",
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
                    "Review Time by Card Type",
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
                    "Review Time by Tag",
                    sorted_ttags,
                    _TAG_COLORS,
                    self._content,
                    value_formatter=_fmt_duration,
                )
            )

        self._clayout.addStretch()
