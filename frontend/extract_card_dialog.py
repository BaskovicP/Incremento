from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTextEdit, QPushButton, QScrollArea, QWidget, Qt,
    QCheckBox, QDoubleSpinBox,
)

try:
    from ..backend.reviewer_extract import knowledge_tree_link_state
except ImportError:
    from reviewer_extract import knowledge_tree_link_state  # type: ignore


class ExtractCardDialog(QDialog):
    """Create a new card extracted from a parent card's content.

    Args:
        selected_text:        text selected by the user (may be empty)
        notetypes:            [{"name": str, "fields": [str, ...]}]
        deck_names:           [str]
        default_notetype:     name of the note type to pre-select
        default_deck:         name of the deck to pre-select
    """

    def __init__(self, selected_text: str,
                 notetypes: list, deck_names: list,
                 default_notetype: str = "", default_deck: str = "",
                 default_priority: float = 50.0,
                 default_mark_topic: bool = True,
                 lower_is_more_important: bool = True,
                 initial_field_values: dict[str, str] | None = None,
                 knowledge_tree_link_enabled: bool = False,
                 default_link_to_knowledge_tree: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extract Card")
        self.setMinimumWidth(500)
        self.setMinimumHeight(460)

        self._notetypes = notetypes
        self._selected_text = selected_text
        self._initial_field_values = {
            str(name or "").strip(): str(value or "")
            for name, value in dict(initial_field_values or {}).items()
            if str(name or "").strip()
        }
        self._field_widgets: list[QTextEdit] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Note type ─────────────────────────────────────────────────────────
        nt_row = QHBoxLayout()
        nt_row.addWidget(QLabel("Note type:"))
        self._nt_combo = QComboBox()
        for nt in notetypes:
            self._nt_combo.addItem(nt["name"])
        nt_row.addWidget(self._nt_combo, 1)
        layout.addLayout(nt_row)

        # ── Deck ──────────────────────────────────────────────────────────────
        dk_row = QHBoxLayout()
        dk_row.addWidget(QLabel("Deck:"))
        self._dk_combo = QComboBox()
        for d in deck_names:
            self._dk_combo.addItem(d)
        dk_row.addWidget(self._dk_combo, 1)
        layout.addLayout(dk_row)

        # ── Extract defaults ─────────────────────────────────────────────────
        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Priority:"))
        self._priority_spin = QDoubleSpinBox()
        self._priority_spin.setRange(0.0, 100.0)
        self._priority_spin.setDecimals(1)
        self._priority_spin.setSingleStep(1.0)
        try:
            priority = float(default_priority)
        except Exception:
            priority = 50.0
        self._priority_spin.setValue(max(0.0, min(100.0, priority)))
        important_end = "0" if lower_is_more_important else "100"
        self._priority_spin.setToolTip(
            f"Priority for the extracted card. {important_end} is the most important end."
        )
        options_row.addWidget(self._priority_spin)
        self._mark_topic_cb = QCheckBox("Topic")
        self._mark_topic_cb.setChecked(bool(default_mark_topic))
        self._mark_topic_cb.setToolTip("Add the configured topic tags to this extracted card.")
        options_row.addWidget(self._mark_topic_cb)
        tree_link_state = knowledge_tree_link_state(bool(knowledge_tree_link_enabled))
        self._knowledge_tree_link_cb = QCheckBox("Add to knowledge tree as child")
        self._knowledge_tree_link_cb.setChecked(
            bool(tree_link_state["checked"] and default_link_to_knowledge_tree)
        )
        self._knowledge_tree_link_cb.setEnabled(bool(tree_link_state["enabled"]))
        self._knowledge_tree_link_cb.setToolTip(str(tree_link_state["tooltip"] or ""))
        options_row.addWidget(self._knowledge_tree_link_cb)
        options_row.addStretch()
        layout.addLayout(options_row)

        # ── Scrollable fields area ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._fields_container = QWidget()
        self._fields_layout = QVBoxLayout(self._fields_container)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(4)
        scroll.setWidget(self._fields_container)
        layout.addWidget(scroll, 1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Create Card")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self._nt_combo.currentIndexChanged.connect(self._rebuild_fields)

        # ── Set defaults ──────────────────────────────────────────────────────
        if default_notetype:
            idx = self._nt_combo.findText(default_notetype)
            if idx >= 0:
                self._nt_combo.setCurrentIndex(idx)

        if default_deck:
            idx = self._dk_combo.findText(default_deck)
            if idx >= 0:
                self._dk_combo.setCurrentIndex(idx)

        self._rebuild_fields()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_fields(self):
        # Remove old widgets
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._field_widgets.clear()

        idx = self._nt_combo.currentIndex()
        if idx < 0 or idx >= len(self._notetypes):
            return

        fields = self._notetypes[idx]["fields"]
        for i, fname in enumerate(fields):
            self._fields_layout.addWidget(QLabel(f"{fname}:"))
            te = QTextEdit()
            te.setFixedHeight(100)
            te.setAcceptRichText(False)
            if fname in self._initial_field_values:
                te.setPlainText(self._initial_field_values.get(fname, ""))
            elif i == 0:
                te.setPlainText(self._selected_text)
            self._fields_layout.addWidget(te)
            self._field_widgets.append(te)

        self._fields_layout.addStretch()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def notetype_name(self) -> str:
        return self._nt_combo.currentText()

    @property
    def deck_name(self) -> str:
        return self._dk_combo.currentText()

    @property
    def field_values(self) -> dict[str, str]:
        """Return the plain-text field values entered by the user."""
        idx = self._nt_combo.currentIndex()
        if idx < 0:
            return {}
        fields = self._notetypes[idx]["fields"]
        result = {}
        for fname, widget in zip(fields, self._field_widgets):
            text = widget.toPlainText().strip()
            result[fname] = text
        return result

    @property
    def priority(self) -> float:
        return round(float(self._priority_spin.value()), 4)

    @property
    def mark_topic(self) -> bool:
        return bool(self._mark_topic_cb.isChecked())

    @property
    def link_to_knowledge_tree(self) -> bool:
        return bool(self._knowledge_tree_link_cb.isEnabled() and self._knowledge_tree_link_cb.isChecked())
