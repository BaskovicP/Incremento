from __future__ import annotations

from html import escape

from aqt.qt import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)
try:
    from ..backend.i18n import t, tn
except ImportError:
    from backend.i18n import t, tn


def _bulk_row_status(row: dict[str, object]) -> str:
    if row.get("valid"):
        return t("reader_ready")
    if not str(row.get("text") or "").strip():
        return t("reader_bulk_empty_highlight")
    if row.get("linked_note_id"):
        return t("reader_bulk_already_linked")
    target = str(row.get("target_field") or "").strip() or t("reader_target")
    return t("reader_bulk_target_empty", field=target)


def normalize_pdf_highlight_bulk_row(
    row: dict | None,
    *,
    visible_fields: list[str] | tuple[str, ...],
    target_field: str,
) -> dict[str, object]:
    source = dict(row or {})
    stored_all_fields = {
        str(field_name or "").strip(): str(value or "")
        for field_name, value in dict(source.get("all_fields") or source.get("fields") or {}).items()
        if str(field_name or "").strip()
    }
    current_fields = {
        str(field_name or "").strip(): str(value or "")
        for field_name, value in dict(source.get("fields") or {}).items()
        if str(field_name or "").strip()
    }
    all_fields = dict(stored_all_fields)
    all_fields.update(current_fields)
    fields = {
        str(field_name or "").strip(): str(all_fields.get(field_name) or "")
        for field_name in list(visible_fields or [])
        if str(field_name or "").strip()
    }
    normalized_target = str(target_field or "").strip()
    target_text = str(fields.get(normalized_target) or "").strip()
    is_linked = bool(source.get("linked_note_id"))
    has_text = bool(str(source.get("text") or "").strip())
    valid = bool(has_text and not is_linked and bool(target_text))
    error = ""
    if not has_text:
        error = "Highlight text is empty."
    elif is_linked:
        error = "Card already linked."
    elif not target_text:
        error = f"{normalized_target or 'Target'} is empty."

    return {
        "highlight_id": str(source.get("highlight_id") or source.get("id") or "").strip(),
        "page": int(source.get("page", 0) or 0),
        "text": str(source.get("text") or "").strip(),
        "note": str(source.get("note") or "").strip(),
        "generated_text": str(source.get("generated_text") or "").strip(),
        "linked_note_id": int(source.get("linked_note_id", 0) or 0),
        "create": bool(source.get("create", valid)),
        "valid": valid,
        "error": error,
        "fields": fields,
        "all_fields": all_fields,
    }


def remap_pdf_highlight_bulk_row_fields(
    row: dict | None,
    *,
    visible_fields: list[str] | tuple[str, ...],
    target_field: str,
) -> dict[str, object]:
    source = dict(row or {})
    next_visible_fields = [
        str(field_name or "").strip()
        for field_name in list(visible_fields or [])
        if str(field_name or "").strip()
    ]
    all_fields = {
        str(field_name or "").strip(): str(value or "")
        for field_name, value in dict(source.get("all_fields") or source.get("fields") or {}).items()
        if str(field_name or "").strip()
    }
    generated_text = str(source.get("generated_text") or "").strip()
    normalized_target = str(target_field or "").strip()
    if normalized_target and normalized_target not in all_fields:
        all_fields[normalized_target] = generated_text
    source["all_fields"] = all_fields
    source["fields"] = {
        field_name: str(all_fields.get(field_name) or "")
        for field_name in next_visible_fields
    }
    return normalize_pdf_highlight_bulk_row(
        source,
        visible_fields=next_visible_fields,
        target_field=normalized_target,
    )


def can_create_pdf_highlight_bulk_rows(rows: list[dict]) -> bool:
    normalized_rows = list(rows or [])
    return any(bool(row.get("create")) and bool(row.get("valid")) for row in normalized_rows)


class PdfHighlightBulkDialog(QDialog):
    def __init__(self, snapshot: dict[str, object], rows: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._snapshot = dict(snapshot or {})
        self._note_type_specs = [
            {
                "name": str((spec or {}).get("name") or "").strip(),
                "visible_fields": [
                    str(name or "").strip()
                    for name in list((spec or {}).get("visible_fields") or [])
                    if str(name or "").strip()
                ],
                "target_field": str((spec or {}).get("target_field") or "").strip(),
                "target_field_index": int((spec or {}).get("target_field_index", 0) or 0),
            }
            for spec in list(self._snapshot.get("note_type_options") or [])
            if str((spec or {}).get("name") or "").strip()
        ]
        if not self._note_type_specs:
            self._note_type_specs = [
                {
                    "name": str(self._snapshot.get("note_type_name") or "").strip(),
                    "visible_fields": [
                        str(name or "").strip()
                        for name in list(self._snapshot.get("visible_fields") or [])
                        if str(name or "").strip()
                    ],
                    "target_field": str(self._snapshot.get("target_field") or "").strip(),
                    "target_field_index": int(self._snapshot.get("target_field_index", 0) or 0),
                }
            ]
        self._deck_names = [
            str(name or "").strip()
            for name in list(self._snapshot.get("deck_names") or [])
            if str(name or "").strip()
        ]
        if not self._deck_names and str(self._snapshot.get("deck_name") or "").strip():
            self._deck_names = [str(self._snapshot.get("deck_name") or "").strip()]
        self._visible_fields: list[str] = []
        self._target_field = ""
        self._rows = [dict(row or {}) for row in list(rows or [])]
        self._syncing_table = False

        self.setWindowTitle(t("reader_bulk_create_missing_title"))
        self.resize(1180, 760)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        chooser_row = QHBoxLayout()
        chooser_row.addWidget(QLabel(t("reader_note_type_label")))
        self._note_type_combo = QComboBox(self)
        for spec in self._note_type_specs:
            self._note_type_combo.addItem(spec["name"])
        chooser_row.addWidget(self._note_type_combo, 1)
        chooser_row.addWidget(QLabel(t("reader_deck_label")))
        self._deck_combo = QComboBox(self)
        for deck_name in self._deck_names:
            self._deck_combo.addItem(deck_name)
        chooser_row.addWidget(self._deck_combo, 1)
        root.addLayout(chooser_row)

        self._target_label = QLabel("")
        self._target_label.setWordWrap(True)
        root.addWidget(self._target_label)

        hint = QLabel(t("reader_bulk_hint"))
        hint.setWordWrap(True)
        root.addWidget(hint)

        column_labels = [t("reader_create"), t("reader_page"), t("reader_highlight"), t("reader_note"), t("reader_status"), *self._visible_fields]
        self._table = QTableWidget(0, len(column_labels), self)
        self._table.setHorizontalHeaderLabels(column_labels)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

        actions = QHBoxLayout()
        self._delete_btn = QPushButton(t("reader_delete_selected"), self)
        self._uncheck_btn = QPushButton(t("reader_uncheck_selected"), self)
        actions.addWidget(self._delete_btn)
        actions.addWidget(self._uncheck_btn)
        actions.addStretch(1)
        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)
        actions.addWidget(self._status_label, 1)
        root.addLayout(actions)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._create_btn = QPushButton(t("reader_create_selected"), self)
        self._cancel_btn = QPushButton(t("reader_cancel"), self)
        buttons.addWidget(self._create_btn)
        buttons.addWidget(self._cancel_btn)
        root.addLayout(buttons)

        self._delete_btn.clicked.connect(self._delete_selected_row)
        self._uncheck_btn.clicked.connect(self._uncheck_selected_row)
        self._create_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        self._note_type_combo.currentIndexChanged.connect(self._on_note_type_changed)
        self._deck_combo.currentIndexChanged.connect(self._update_target_summary)

        default_note_type = str(self._snapshot.get("note_type_name") or "").strip()
        note_type_index = self._note_type_combo.findText(default_note_type)
        if note_type_index >= 0:
            self._note_type_combo.setCurrentIndex(note_type_index)
        default_deck = str(self._snapshot.get("deck_name") or "").strip()
        deck_index = self._deck_combo.findText(default_deck)
        if deck_index >= 0:
            self._deck_combo.setCurrentIndex(deck_index)

        self._apply_note_type_spec(self._current_note_type_spec())
        self._rebuild_table()
        self._update_target_summary()
        self._update_create_state()

    def _current_note_type_spec(self) -> dict[str, object]:
        current_name = self._note_type_combo.currentText()
        for spec in self._note_type_specs:
            if spec["name"] == current_name:
                return spec
        return self._note_type_specs[0] if self._note_type_specs else {}

    def _apply_note_type_spec(self, spec: dict[str, object]) -> None:
        visible_fields = [
            str(name or "").strip()
            for name in list((spec or {}).get("visible_fields") or [])
            if str(name or "").strip()
        ]
        target_field = str((spec or {}).get("target_field") or "").strip()
        self._visible_fields = visible_fields
        self._target_field = target_field
        for row_index, row in enumerate(list(self._rows or [])):
            self._rows[row_index] = remap_pdf_highlight_bulk_row_fields(
                row,
                visible_fields=self._visible_fields,
                target_field=self._target_field,
            )

    def _on_note_type_changed(self, *_args) -> None:
        self._apply_note_type_spec(self._current_note_type_spec())
        self._rebuild_table()
        self._update_target_summary()
        self._update_create_state()

    def _update_target_summary(self, *_args) -> None:
        self._target_label.setText(t(
            "reader_bulk_target_summary",
            note_type=escape(self.note_type_name or t("reader_unknown")),
            deck=escape(self.deck_name or "Topics"),
            field=escape(self._target_field or t("reader_unknown_field")),
        ))

    def _rebuild_table(self) -> None:
        self._syncing_table = True
        column_labels = [t("reader_create"), t("reader_page"), t("reader_highlight"), t("reader_note"), t("reader_status"), *self._visible_fields]
        self._table.setColumnCount(len(column_labels))
        self._table.setHorizontalHeaderLabels(column_labels)
        self._table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            normalized = normalize_pdf_highlight_bulk_row(
                row,
                visible_fields=self._visible_fields,
                target_field=self._target_field,
            )
            self._rows[row_index] = normalized

            create_item = QTableWidgetItem("")
            create_item.setFlags(
                create_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            create_item.setCheckState(
                Qt.CheckState.Checked if normalized["create"] else Qt.CheckState.Unchecked
            )

            page_item = QTableWidgetItem(str(int(normalized.get("page", 0) or 0)))
            page_item.setFlags(page_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            text_item = QTableWidgetItem(str(normalized.get("text") or ""))
            text_item.setFlags(text_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            note_item = QTableWidgetItem(str(normalized.get("note") or ""))
            note_item.setFlags(note_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item = QTableWidgetItem(_bulk_row_status({**normalized, "target_field": self._target_field}))
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self._table.setItem(row_index, 0, create_item)
            self._table.setItem(row_index, 1, page_item)
            self._table.setItem(row_index, 2, text_item)
            self._table.setItem(row_index, 3, note_item)
            self._table.setItem(row_index, 4, status_item)

            for field_offset, field_name in enumerate(self._visible_fields, start=5):
                value_item = QTableWidgetItem(str(normalized["fields"].get(field_name) or ""))
                self._table.setItem(row_index, field_offset, value_item)
        self._syncing_table = False

    def _selected_row_index(self) -> int:
        indexes = self._table.selectionModel().selectedRows() if self._table.selectionModel() is not None else []
        if not indexes:
            return -1
        return int(indexes[0].row())

    def _delete_selected_row(self) -> None:
        row_index = self._selected_row_index()
        if row_index < 0 or row_index >= len(self._rows):
            return
        del self._rows[row_index]
        self._rebuild_table()
        self._update_create_state()

    def _uncheck_selected_row(self) -> None:
        row_index = self._selected_row_index()
        if row_index < 0 or row_index >= len(self._rows):
            return
        self._rows[row_index]["create"] = False
        self._rebuild_table()
        self._update_create_state()

    def _on_item_changed(self, item) -> None:
        if self._syncing_table or item is None:
            return
        row_index = int(item.row())
        if row_index < 0 or row_index >= len(self._rows):
            return

        row = dict(self._rows[row_index])
        if int(item.column()) == 0:
            row["create"] = item.checkState() == Qt.CheckState.Checked
        elif int(item.column()) >= 5:
            field_name = self._visible_fields[int(item.column()) - 5]
            fields = dict(row.get("fields") or {})
            fields[field_name] = item.text()
            all_fields = dict(row.get("all_fields") or fields)
            all_fields[field_name] = item.text()
            row["fields"] = fields
            row["all_fields"] = all_fields

        self._rows[row_index] = normalize_pdf_highlight_bulk_row(
            row,
            visible_fields=self._visible_fields,
            target_field=self._target_field,
        )
        self._syncing_table = True
        status_item = self._table.item(row_index, 4)
        if status_item is not None:
            status_item.setText(
                _bulk_row_status({**self._rows[row_index], "target_field": self._target_field})
            )
        self._syncing_table = False
        self._update_create_state()

    def _update_create_state(self) -> None:
        checked_count = sum(1 for row in self._rows if bool(row.get("create")))
        ready_count = sum(
            1 for row in self._rows if bool(row.get("create")) and bool(row.get("valid"))
        )
        invalid_checked = max(0, checked_count - ready_count)
        if not self._rows:
            status = t("reader_bulk_none_left")
        elif checked_count == 0:
            status = t("reader_bulk_check_one")
        elif invalid_checked:
            status = tn("reader_bulk_fix_invalid_count", invalid_checked)
        else:
            status = tn("reader_bulk_ready_count", ready_count)
        self._status_label.setText(status)
        self._create_btn.setEnabled(can_create_pdf_highlight_bulk_rows(self._rows))
        self._delete_btn.setEnabled(bool(self._rows))
        self._uncheck_btn.setEnabled(bool(self._rows))

    @property
    def selected_rows(self) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        for row in self._rows:
            if not bool(row.get("create")):
                continue
            normalized = normalize_pdf_highlight_bulk_row(
                row,
                visible_fields=self._visible_fields,
                target_field=self._target_field,
            )
            if bool(normalized.get("valid")):
                selected.append(normalized)
        return selected

    @property
    def note_type_name(self) -> str:
        return self._note_type_combo.currentText()

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    @property
    def selected_snapshot(self) -> dict[str, object]:
        selected = dict(self._snapshot)
        selected["note_type_name"] = self.note_type_name
        selected["deck_name"] = self.deck_name
        selected["deck_id"] = None
        selected["visible_fields"] = list(self._visible_fields)
        selected["target_field"] = self._target_field
        spec = self._current_note_type_spec()
        selected["target_field_index"] = int((spec or {}).get("target_field_index", 0) or 0)
        return selected
