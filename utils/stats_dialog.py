"""Statistics viewer dialog for Incremento."""
from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, Qt,
    QButtonGroup, QRadioButton, QScrollArea, QPainter, QColor,
    QFrame, QSizePolicy, qconnect,
)

from .statistics import load_stats, _effective_date, _empty, _is_valid_counts_block

# ── colour palettes ────────────────────────────────────────────────────────────
_TYPE_COLORS = ["#4a90d9", "#7bc67e"]          # Topics, Items
_MODE_COLORS = ["#e0a020", "#8da0cb"]          # Priority, Random
_TAG_COLORS  = [                               # cycled for arbitrary tag lists
    "#4a90d9", "#7bc67e", "#e0a020", "#e05050",
    "#9b59b6", "#1abc9c", "#e67e22", "#c0392b",
]


# ── bar chart widget ───────────────────────────────────────────────────────────

class _BarChart(QWidget):
    """Draws a set of labelled horizontal bars with QPainter."""

    _LABEL_W = 120
    _RIGHT_W  = 90
    _BAR_H    = 14
    _ROW_H    = 28

    def __init__(self, items: list[tuple[str, int]], colors: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items  = items          # [(label, value), …]
        self._colors = [QColor(c) for c in colors]
        self._total  = sum(v for _, v in items) or 1
        self.setFixedHeight(self._ROW_H * max(1, len(items)) + 4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        if not self._items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w      = self.width()
        bar_x  = self._LABEL_W + 8
        bar_w  = max(10, w - bar_x - self._RIGHT_W - 8)
        text_c = self.palette().text().color()
        track_c = QColor(text_c.red(), text_c.green(), text_c.blue(), 30)
        af = Qt.AlignmentFlag

        for i, (label, value) in enumerate(self._items):
            row_y = i * self._ROW_H + 2
            bar_y = row_y + (self._ROW_H - self._BAR_H) // 2
            color = self._colors[i % len(self._colors)]

            # Label (left-aligned, ellide if needed)
            p.setPen(text_c)
            fm    = p.fontMetrics()
            elided = fm.elidedText(label, Qt.TextElideMode.ElideRight,
                                   self._LABEL_W - 4)
            p.drawText(0, row_y, self._LABEL_W - 4, self._ROW_H,
                       af.AlignVCenter | af.AlignLeft, elided)

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
            p.drawText(w - self._RIGHT_W, row_y, self._RIGHT_W, self._ROW_H,
                       af.AlignVCenter | af.AlignLeft,
                       f"{value}  ({pct}\u202f%)")

        p.end()


# ── section helper ─────────────────────────────────────────────────────────────

def _section(title: str, items: list[tuple[str, int]],
             colors: list[str], parent: QWidget) -> QWidget:
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
    lay.addWidget(_BarChart(visible, colors, container))
    return container


# ── main dialog ────────────────────────────────────────────────────────────────

class StatsDialog(QDialog):
    def __init__(self, addon_dir: str,
                 session_counts: dict | None = None,
                 day_end_time: str = "00:00",
                 parent=None) -> None:
        super().__init__(parent)
        self._addon_dir      = addon_dir
        self._day_end_time   = day_end_time
        self._session_counts = session_counts or _empty()
        self._raw            = load_stats(addon_dir)

        self.setWindowTitle("Incremento — Statistics")
        self.setMinimumWidth(540)
        self.setMinimumHeight(440)
        self._setup_ui()

    # ── data ──────────────────────────────────────────────────────────────────

    def _get_counts(self, scope: str) -> dict:
        if scope == "session":
            return self._session_counts

        if scope == "daily":
            daily_raw = self._raw.get("daily", {})
            if (isinstance(daily_raw, dict)
                    and daily_raw.get("date") == _effective_date(self._day_end_time)
                    and _is_valid_counts_block(daily_raw.get("counts"))):
                return daily_raw["counts"]
            return _empty()

        # lifetime
        lt = self._raw.get("lifetime")
        return lt if _is_valid_counts_block(lt) else _empty()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        # Scope radio buttons
        scope_row = QHBoxLayout()
        self._scope_group = QButtonGroup(self)
        for i, (key, label) in enumerate([
            ("session",  "This Session"),
            ("daily",    "Today"),
            ("lifetime", "All Time"),
        ]):
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
            if (w := item.widget()):
                w.deleteLater()

        checked = self._scope_group.checkedButton()
        scope   = checked.property("scope_key") if checked else "session"
        counts  = self._get_counts(scope)

        total = sum(counts["type"].values())

        # Total
        total_lbl = QLabel(f"<b>Total cards studied: {total}</b>")
        total_lbl.setStyleSheet("padding: 4px 0;")
        self._clayout.addWidget(total_lbl)

        if total == 0:
            hint = ("Start a learning session to record data here."
                    if scope == "session"
                    else "No data recorded yet for this scope.")
            note = QLabel(hint)
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setStyleSheet("color: gray; padding: 32px;")
            note.setWordWrap(True)
            self._clayout.addWidget(note)
            self._clayout.addStretch()
            return

        # Card types
        n_topics = counts["type"].get("topics", 0)
        n_items  = counts["type"].get("items",  0)
        if n_topics or n_items:
            self._clayout.addWidget(_section(
                "Card Types",
                [("Topics", n_topics), ("Items", n_items)],
                _TYPE_COLORS, self._content,
            ))

        # Mode
        n_prio   = counts["mode"].get("priority", 0)
        n_random = counts["mode"].get("random",   0)
        if n_prio or n_random:
            self._clayout.addWidget(_section(
                "Selection Mode",
                [("Priority", n_prio), ("Random", n_random)],
                _MODE_COLORS, self._content,
            ))

        # Tags (filter out synthetic internal keys like __no_tags__)
        tag_data = {k: v for k, v in counts["tags"].items() if not k.startswith("__")}
        if tag_data:
            sorted_tags = sorted(tag_data.items(), key=lambda x: x[1], reverse=True)
            self._clayout.addWidget(_section(
                "Tags", sorted_tags, _TAG_COLORS, self._content,
            ))

        self._clayout.addStretch()
