"""Native, searchable document completion and current memory-card stages."""

from __future__ import annotations

from aqt.qt import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPalette, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, Qt, QVBoxLayout,
)

try:
    from ..backend.i18n import format_number, t
except ImportError:
    from backend.i18n import format_number, t


def _label(text, parent, *, heading=False):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if heading:
        label.setStyleSheet("font-size: 13pt; font-weight: bold;")
    return label


def _percent(value):
    if value is None:
        return "—"
    # Only real completion can display 100%, even for very large documents.
    rounded = min(99.9, round(value, 1)) if value < 100 else 100
    return format_number(int(rounded) if rounded == int(rounded) else rounded) + "%"


def _bar_color(widget, kind):
    dark = widget.palette().window().color().lightness() < 128
    colors = {
        "pdf": ("#8a600f", "#e0b94c"), "epub": ("#6443a0", "#b49ade"),
        "new": ("#2766ac", "#85b5e5"), "learning": ("#8a600f", "#e0b94c"),
        "review": ("#176d5d", "#79c7b8"), "relearning": ("#8c3b61", "#d5a1b8"),
    }
    return colors[kind][0 if dark else 1]


class DocumentProgressPanel(QFrame):
    PAGE_SIZE = 50

    def __init__(self, rows, *, loading=False, query="", kind="all", on_filter=None, parent=None):
        super().__init__(parent)
        self.setObjectName("documentProgressPanel")
        self.rows = rows
        self.page = 0
        self.on_filter = on_filter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(_label(t("stats_documents_title"), self, heading=True))
        layout.addWidget(_label(t("stats_documents_basis"), self))
        if rows is None:
            layout.addWidget(_label(t("stats_documents_loading" if loading else "stats_documents_unavailable"), self))
            return
        complete = sum(row["percent"] == 100 for row in rows)
        started = sum(row["percent"] is not None and 0 < row["percent"] < 100 for row in rows)
        summary = _label(t("stats_documents_summary", total=format_number(len(rows)),
                           started=format_number(started), finished=format_number(complete)), self)
        layout.addWidget(summary)
        controls = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(t("stats_documents_search"))
        self.search.setAccessibleName(t("stats_documents_search"))
        self.search.setClearButtonEnabled(True)
        self.search.setText(query)
        controls.addWidget(self.search, 1)
        self.kind = QComboBox(self)
        for label, key in ((t("stats_documents_all"), "all"), ("PDF", "pdf"), ("EPUB", "epub")):
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(kind)))
        self.kind.setAccessibleName(t("stats_documents_format"))
        controls.addWidget(self.kind)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 6, self)
        self.table.setAccessibleName(t("stats_documents_title"))
        self.table.setHorizontalHeaderLabels([t(key) for key in (
            "stats_documents_document", "stats_documents_format", "stats_documents_read",
            "stats_documents_left", "stats_documents_total", "stats_documents_completion",
        )])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        palette = self.table.palette()
        base = palette.base().color()
        palette.setColor(QPalette.ColorRole.AlternateBase, base.lighter(118) if base.lightness() < 128 else base.darker(104))
        self.table.setPalette(palette)
        search_palette = self.search.palette()
        placeholder = search_palette.text().color()
        placeholder.setAlpha(175)
        search_palette.setColor(QPalette.ColorRole.PlaceholderText, placeholder)
        self.search.setPalette(search_palette)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(350)
        layout.addWidget(self.table, 1)
        self.empty_message = _label(t("stats_documents_no_matches"), self)
        layout.addWidget(self.empty_message)
        navigation = QHBoxLayout()
        self.page_label = _label("", self)
        navigation.addWidget(self.page_label, 1)
        self.previous_button = QPushButton(t("stats_documents_previous"), self)
        self.next_button = QPushButton(t("stats_documents_next"), self)
        self.previous_button.clicked.connect(lambda: self._move(-1))
        self.next_button.clicked.connect(lambda: self._move(1))
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        self.search.textChanged.connect(self._filter)
        self.kind.currentIndexChanged.connect(self._filter)
        self._render()

    def _filter(self, *_):
        self.page = 0
        if self.on_filter:
            self.on_filter(self.search.text(), self.kind.currentData())
        self._render()

    def _move(self, delta):
        self.page = max(0, self.page + delta)
        self._render()

    def _render(self):
        query = self.search.text().strip().casefold()
        kind = self.kind.currentData()
        filtered = sorted((row for row in self.rows if query in row["title"].casefold()
                           and (kind == "all" or row["kind"] == kind)),
                          key=lambda row: (row["title"].casefold(), row["card_id"]))
        start = self.page * self.PAGE_SIZE
        visible = filtered[start:start + self.PAGE_SIZE]
        self.table.setRowCount(len(visible))
        for index, row in enumerate(visible):
            kind_label = row["kind"].upper()
            if row["unit"] == "estimated_pages":
                kind_label += " · " + t("stats_documents_estimated")
            values = [row["title"], kind_label, *(
                format_number(row[key]) if row[key] is not None else "—" for key in ("read", "left", "total")
            )]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(index, column, item)
            bar = QProgressBar(self.table)
            bar.setRange(0, 1000)
            bar.setValue(int((row["percent"] or 0) * 10))
            bar.setFormat(_percent(row["percent"]))
            bar.setMinimumWidth(140)
            bar.setMinimumHeight(bar.fontMetrics().height() + 8)
            bar.setAccessibleName(row["title"] + ": " + t("stats_documents_completion"))
            bar.setAccessibleDescription(" · ".join(values[1:]) + " · " + bar.format())
            color = _bar_color(self, row["kind"])
            bar.setStyleSheet(f"QProgressBar {{border: 1px solid palette(mid); border-radius: 5px; text-align: center; min-height: {bar.fontMetrics().height() + 8}px;}}"
                             f"QProgressBar::chunk {{background-color: {color}; border-radius: 4px;}}")
            if row["percent"] is None:
                bar.setToolTip(t("stats_documents_unknown"))
            self.table.setCellWidget(index, 5, bar)
        self.table.resizeRowsToContents()
        self.empty_message.setVisible(not filtered)
        self.previous_button.setEnabled(self.page > 0)
        self.next_button.setEnabled(start + len(visible) < len(filtered))
        self.page_label.setText(t("stats_documents_page", start=format_number(start + 1 if visible else 0),
                                 end=format_number(start + len(visible)), total=format_number(len(filtered))))


class CardStagePanel(QFrame):
    def __init__(self, states, *, loading=False, parent=None):
        super().__init__(parent)
        self.setObjectName("cardStagePanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(_label(t("stats_card_stages_title"), self, heading=True))
        layout.addWidget(_label(t("stats_card_stages_hint"), self))
        if states is None:
            layout.addWidget(_label(t("stats_learning_results_loading" if loading else "stats_learning_results_unavailable"), self))
            return
        total = states["total"]
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        for column, (key, label) in enumerate((
            ("new", t("stats_card_stage_new")),
            ("learning", t("stats_learning_stage")),
            ("review", t("stats_review_stage")),
            ("relearning", t("stats_relearning_stage")),
        )):
            count = states[key]
            grid.addWidget(_label(label, self), 0, column)
            number = _label(format_number(count), self, heading=True)
            number.setObjectName("stage" + key.title() + "Count")
            grid.addWidget(number, 1, column)
            bar = QProgressBar(self)
            bar.setMinimumHeight(bar.fontMetrics().height() + 8)
            bar.setRange(0, 1000)
            bar.setValue(int(1000 * count / total) if total else 0)
            bar.setFormat(_percent(100 * count / total if total else None))
            bar.setAccessibleName(label)
            bar.setAccessibleDescription(t("stats_card_stage_count", count=format_number(count), total=format_number(total)))
            bar.setStyleSheet(f"QProgressBar {{border: 1px solid palette(mid); border-radius: 5px; text-align: center; min-height: {bar.fontMetrics().height() + 8}px;}}"
                             f"QProgressBar::chunk {{background: {_bar_color(self, key)}; border-radius: 4px;}}")
            grid.addWidget(bar, 2, column)
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        layout.addWidget(_label(t("stats_card_stages_scope", total=format_number(total),
                                 suspended=format_number(states["suspended"]), buried=format_number(states["buried"])), self))
