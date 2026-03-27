from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTextEdit, QPushButton, QScrollArea, QWidget, Qt,
)


class ExtractCardDialog(QDialog):
    """Create a new card extracted from a parent card's content.

    Args:
        selected_text:        text selected by the user (may be empty)
        parent_link_html:     HTML anchor linking back to the parent card
        notetypes:            [{"name": str, "fields": [str, ...]}]
        deck_names:           [str]
        default_notetype:     name of the note type to pre-select
        default_deck:         name of the deck to pre-select
    """

    def __init__(self, selected_text: str, parent_link_html: str,
                 notetypes: list, deck_names: list,
                 default_notetype: str = "", default_deck: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extract Card")
        self.setMinimumWidth(500)
        self.setMinimumHeight(460)

        self._notetypes = notetypes
        self._selected_text = selected_text
        self._parent_link_html = parent_link_html
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
            if i == 0:
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
        """Return {field_name: html_content}. Parent link is appended to field 0."""
        idx = self._nt_combo.currentIndex()
        if idx < 0:
            return {}
        fields = self._notetypes[idx]["fields"]
        result = {}
        for i, (fname, widget) in enumerate(zip(fields, self._field_widgets)):
            text = widget.toPlainText().strip()
            if i == 0 and self._parent_link_html:
                sep = "<br><br>" if text else ""
                text = text + sep + self._parent_link_html
            result[fname] = text
        return result
