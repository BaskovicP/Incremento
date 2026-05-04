"""Statistics viewer dialog for Incremento."""

from __future__ import annotations

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
        day_end_time: str = "00:00",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._day_end_time = day_end_time
        self._session_counts = _normalize_counts_block(session_counts or _empty())
        self._session_time = _normalize_time_block(session_time or _empty_time())
        self._raw = load_stats(addon_dir, _active_profile())

        self.setWindowTitle("Incremento — Statistics")
        self.setMinimumWidth(540)
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

    def _refresh(self) -> None:
        # Clear previous content
        while self._clayout.count():
            item = self._clayout.takeAt(0)
            if w := item.widget():
                w.deleteLater()

        checked = self._scope_group.checkedButton()
        scope = checked.property("scope_key") if checked else "session"
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
