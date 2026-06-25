from __future__ import annotations

from aqt.qt import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)

try:
    from ..backend.reviewer_extract import parse_batch_qa_text
except ImportError:
    from reviewer_extract import parse_batch_qa_text  # type: ignore


def validate_batch_preview_row(question: str, answer: str) -> dict[str, object]:
    question_text = str(question or "").strip()
    answer_text = str(answer or "").strip()
    if not question_text:
        return {
            "question": question_text,
            "answer": answer_text,
            "valid": False,
            "error": "Question is empty.",
        }
    if not answer_text:
        return {
            "question": question_text,
            "answer": answer_text,
            "valid": False,
            "error": "Answer is empty.",
        }
    return {
        "question": question_text,
        "answer": answer_text,
        "valid": True,
        "error": "",
    }


def can_create_batch_preview(
    rows: list[dict],
    question_field: str,
    answer_field: str,
) -> bool:
    if str(question_field or "").strip() == str(answer_field or "").strip():
        return False
    normalized_rows = [validate_batch_preview_row(row.get("question"), row.get("answer")) for row in list(rows or [])]
    return bool(normalized_rows) and all(bool(row.get("valid")) for row in normalized_rows)


class ExtractBatchDialog(QDialog):
    def __init__(self, snapshot: dict[str, object], parent=None) -> None:
        super().__init__(parent)
        self._snapshot = dict(snapshot or {})
        self._visible_fields = [
            str(name or "").strip()
            for name in list(self._snapshot.get("visible_fields") or [])
            if str(name or "").strip()
        ]
        self._rows: list[dict[str, object]] = []
        self._syncing_table = False

        self.setWindowTitle("Batch Q/A Extract")
        self.resize(920, 700)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        target = QLabel(
            f"Target: <b>{self._snapshot.get('note_type_name') or 'Unknown'}</b>"
            f" in deck <b>{self._snapshot.get('deck_name') or 'Topics'}</b>"
        )
        target.setWordWrap(True)
        root.addWidget(target)

        hint = QLabel(
            "Paste one or more blocks separated by blank lines. Each block must start with "
            "<code>Q:</code> and contain a later <code>A:</code> line."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._raw_edit = QPlainTextEdit(self)
        self._raw_edit.setPlaceholderText("Q: ...\nA: ...")
        self._raw_edit.setMinimumHeight(180)
        root.addWidget(self._raw_edit)

        fields_row = QHBoxLayout()
        fields_row.addWidget(QLabel("Question field:"))
        self._question_combo = QComboBox(self)
        fields_row.addWidget(self._question_combo, 1)
        fields_row.addWidget(QLabel("Answer field:"))
        self._answer_combo = QComboBox(self)
        fields_row.addWidget(self._answer_combo, 1)
        self._parse_btn = QPushButton("Parse / Preview", self)
        fields_row.addWidget(self._parse_btn)
        root.addLayout(fields_row)

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Status", "Question", "Answer"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

        actions_row = QHBoxLayout()
        self._delete_btn = QPushButton("Delete Selected", self)
        actions_row.addWidget(self._delete_btn)
        actions_row.addStretch(1)
        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)
        actions_row.addWidget(self._status_label, 1)
        root.addLayout(actions_row)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self._create_btn = QPushButton("Create All", self)
        self._cancel_btn = QPushButton("Cancel", self)
        buttons_row.addWidget(self._create_btn)
        buttons_row.addWidget(self._cancel_btn)
        root.addLayout(buttons_row)

        for field_name in self._visible_fields:
            self._question_combo.addItem(field_name)
            self._answer_combo.addItem(field_name)
        self._set_default_fields()

        self._parse_btn.clicked.connect(self._parse_preview)
        self._delete_btn.clicked.connect(self._delete_selected_row)
        self._create_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        self._question_combo.currentIndexChanged.connect(self._update_create_state)
        self._answer_combo.currentIndexChanged.connect(self._update_create_state)

        self._update_create_state()

    def _set_default_fields(self) -> None:
        question_field = str(self._snapshot.get("question_field") or "")
        answer_field = str(self._snapshot.get("answer_field") or "")
        question_index = self._question_combo.findText(question_field)
        answer_index = self._answer_combo.findText(answer_field)
        if question_index >= 0:
            self._question_combo.setCurrentIndex(question_index)
        if answer_index >= 0:
            self._answer_combo.setCurrentIndex(answer_index)
        if self._answer_combo.currentIndex() == self._question_combo.currentIndex() and self._answer_combo.count() > 1:
            self._answer_combo.setCurrentIndex(1)

    def _parse_preview(self) -> None:
        self._rows = [dict(row) for row in parse_batch_qa_text(self._raw_edit.toPlainText())]
        self._rebuild_table()
        self._update_create_state()

    def _rebuild_table(self) -> None:
        self._syncing_table = True
        self._table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            normalized = validate_batch_preview_row(row.get("question"), row.get("answer"))
            normalized["error"] = str(row.get("error") or normalized["error"])
            if row.get("valid") is False and not normalized["error"]:
                normalized["error"] = "Invalid row."
            if normalized["error"] and normalized["valid"]:
                normalized["error"] = ""
            if str(row.get("error") or "").strip() and not bool(row.get("valid")):
                normalized["error"] = str(row.get("error") or "").strip()
            self._rows[row_index] = normalized

            status_text = "Valid" if normalized["valid"] else str(normalized["error"] or "Invalid")
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            question_item = QTableWidgetItem(str(normalized["question"] or ""))
            answer_item = QTableWidgetItem(str(normalized["answer"] or ""))
            self._table.setItem(row_index, 0, status_item)
            self._table.setItem(row_index, 1, question_item)
            self._table.setItem(row_index, 2, answer_item)
        self._syncing_table = False

    def _on_item_changed(self, item) -> None:
        if self._syncing_table or item is None:
            return
        row_index = int(item.row())
        if row_index < 0 or row_index >= len(self._rows):
            return
        question = self._table.item(row_index, 1)
        answer = self._table.item(row_index, 2)
        normalized = validate_batch_preview_row(
            question.text() if question is not None else "",
            answer.text() if answer is not None else "",
        )
        self._rows[row_index] = normalized
        self._syncing_table = True
        status_item = self._table.item(row_index, 0)
        if status_item is not None:
            status_item.setText("Valid" if normalized["valid"] else str(normalized["error"]))
        self._syncing_table = False
        self._update_create_state()

    def _delete_selected_row(self) -> None:
        indexes = self._table.selectionModel().selectedRows() if self._table.selectionModel() is not None else []
        if not indexes:
            return
        row_index = int(indexes[0].row())
        if row_index < 0 or row_index >= len(self._rows):
            return
        del self._rows[row_index]
        self._rebuild_table()
        self._update_create_state()

    def _update_create_state(self, *_args) -> None:
        valid_rows = sum(1 for row in self._rows if bool(row.get("valid")))
        invalid_rows = max(0, len(self._rows) - valid_rows)
        same_fields = self.question_field == self.answer_field
        if same_fields:
            status = "Question and answer fields must be different."
        elif invalid_rows:
            status = f"Fix or delete {invalid_rows} invalid row{'s' if invalid_rows != 1 else ''}."
        elif not self._rows:
            status = "Parse at least one Q/A block."
        else:
            status = f"{valid_rows} row{'s' if valid_rows != 1 else ''} ready."
        self._status_label.setText(status)
        self._create_btn.setEnabled(
            can_create_batch_preview(self._rows, self.question_field, self.answer_field)
        )
        self._delete_btn.setEnabled(bool(self._rows))

    @property
    def question_field(self) -> str:
        return self._question_combo.currentText()

    @property
    def answer_field(self) -> str:
        return self._answer_combo.currentText()

    @property
    def preview_rows(self) -> list[dict[str, str]]:
        return [
            {
                "question": str(row.get("question") or "").strip(),
                "answer": str(row.get("answer") or "").strip(),
            }
            for row in self._rows
            if bool(row.get("valid"))
        ]
