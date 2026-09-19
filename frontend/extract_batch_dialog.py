from __future__ import annotations

import re

from aqt.qt import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
)

try:
    from ..backend.i18n import t, tn
except ImportError:
    from backend.i18n import t, tn  # type: ignore

try:
    from ..backend.reviewer_extract import parse_batch_qa_text
except ImportError:
    from reviewer_extract import parse_batch_qa_text  # type: ignore


def validate_batch_preview_row(question: object, answer: object) -> dict[str, object]:
    question_text = str(question or "").strip()
    answer_text = str(answer or "").strip()
    if not question_text:
        return {
            "question": question_text,
            "answer": answer_text,
            "valid": False,
            "error": t("backend_extract_question_empty"),
        }
    if not answer_text:
        return {
            "question": question_text,
            "answer": answer_text,
            "valid": False,
            "error": t("backend_extract_answer_empty"),
        }
    return {
        "question": question_text,
        "answer": answer_text,
        "valid": True,
        "error": "",
    }


def normalize_batch_priority(value, default: float = 50.0) -> float:
    try:
        number = float(value)
    except Exception:
        try:
            number = float(default)
        except Exception:
            number = 50.0
    return round(max(0.0, min(100.0, number)), 4)


def normalize_batch_classification(value) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"topic", "item", "other"} else "other"


def normalize_batch_tags(value) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[\s,;]+", value)
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in values:
        tag = str(raw_tag or "").strip()
        key = tag.casefold()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def normalize_batch_preview_row(
    row: dict,
    *,
    default_priority: float = 50.0,
    default_classification: str = "other",
    default_tags=None,
) -> dict[str, object]:
    source = dict(row or {})
    normalized = validate_batch_preview_row(source.get("question"), source.get("answer"))
    source_error = str(source.get("error") or "").strip()
    if source.get("valid") is False and source_error:
        normalized["valid"] = False
        normalized["error"] = source_error
    normalized["priority"] = normalize_batch_priority(
        source.get("priority", default_priority),
        default_priority,
    )
    normalized["classification"] = normalize_batch_classification(
        source.get("classification", default_classification)
    )
    normalized["tags"] = normalize_batch_tags(
        source["tags"] if "tags" in source else default_tags
    )
    return normalized


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
        visible_fields = self._snapshot.get("visible_fields")
        if not isinstance(visible_fields, (list, tuple)):
            visible_fields = []
        self._visible_fields = [
            str(name or "").strip()
            for name in visible_fields
            if str(name or "").strip()
        ]
        self._rows: list[dict[str, object]] = []
        self._syncing_table = False

        raw_extract_options = self._snapshot.get("extract_options")
        extract_options = (
            dict(raw_extract_options)
            if isinstance(raw_extract_options, dict)
            else {}
        )
        self._default_priority = normalize_batch_priority(
            extract_options.get("priority", 50.0)
        )
        self._default_classification = normalize_batch_classification(
            self._snapshot.get("default_classification")
            or ("topic" if extract_options.get("mark_topic") else "item" if extract_options.get("mark_item") else "other")
        )
        self._default_tags = normalize_batch_tags(
            self._snapshot.get("default_tags") or []
        )

        self.setWindowTitle(t("extract_batch_title"))
        self.resize(920, 700)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        target = QLabel(
            t(
                "extract_batch_target",
                note_type=self._snapshot.get("note_type_name") or t("common_unknown"),
                deck=self._snapshot.get("deck_name") or t("session_topics"),
            )
        )
        target.setWordWrap(True)
        root.addWidget(target)

        hint = QLabel(t("extract_batch_hint"))
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._raw_edit = QPlainTextEdit(self)
        self._raw_edit.setPlaceholderText("Q: ...\nA: ...")
        self._raw_edit.setMinimumHeight(180)
        root.addWidget(self._raw_edit)

        fields_row = QHBoxLayout()
        fields_row.addWidget(QLabel(t("extract_batch_question_field")))
        self._question_combo = QComboBox(self)
        fields_row.addWidget(self._question_combo, 1)
        fields_row.addWidget(QLabel(t("extract_batch_answer_field")))
        self._answer_combo = QComboBox(self)
        fields_row.addWidget(self._answer_combo, 1)
        self._parse_btn = QPushButton(t("extract_batch_parse_preview"), self)
        fields_row.addWidget(self._parse_btn)
        root.addLayout(fields_row)

        bulk_row = QHBoxLayout()
        bulk_row.addWidget(QLabel(t("extract_batch_apply_all")))
        bulk_row.addWidget(QLabel(t("extract_batch_priority")))
        self._bulk_priority = self._priority_spin(self._default_priority, self)
        bulk_row.addWidget(self._bulk_priority)
        bulk_row.addWidget(QLabel(t("extract_batch_card_type")))
        self._bulk_classification = self._classification_combo(
            self._default_classification,
            self,
        )
        bulk_row.addWidget(self._bulk_classification)
        bulk_row.addWidget(QLabel(t("extract_batch_tags")))
        self._bulk_tags = QLineEdit(" ".join(self._default_tags), self)
        self._bulk_tags.setPlaceholderText(t("extract_batch_tags_hint"))
        bulk_row.addWidget(self._bulk_tags, 1)
        self._apply_all_btn = QPushButton(t("imports_reviewer_apply"), self)
        bulk_row.addWidget(self._apply_all_btn)
        root.addLayout(bulk_row)

        self._table = QTableWidget(0, 6, self)
        self._table.setHorizontalHeaderLabels(
            [
                t("common_status"),
                t("extract_batch_question"),
                t("extract_batch_answer"),
                t("extract_batch_priority"),
                t("extract_batch_card_type"),
                t("extract_batch_tags"),
            ]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

        actions_row = QHBoxLayout()
        self._delete_btn = QPushButton(t("extract_batch_delete_selected"), self)
        actions_row.addWidget(self._delete_btn)
        actions_row.addStretch(1)
        self._status_label = QLabel("", self)
        self._status_label.setWordWrap(True)
        actions_row.addWidget(self._status_label, 1)
        root.addLayout(actions_row)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self._create_btn = QPushButton(t("extract_batch_create_all"), self)
        self._cancel_btn = QPushButton(t("common_cancel"), self)
        buttons_row.addWidget(self._create_btn)
        buttons_row.addWidget(self._cancel_btn)
        root.addLayout(buttons_row)

        for field_name in self._visible_fields:
            self._question_combo.addItem(field_name)
            self._answer_combo.addItem(field_name)
        self._set_default_fields()

        self._parse_btn.clicked.connect(self._parse_preview)
        self._apply_all_btn.clicked.connect(self._apply_to_all_rows)
        self._delete_btn.clicked.connect(self._delete_selected_row)
        self._create_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        self._question_combo.currentIndexChanged.connect(self._update_create_state)
        self._answer_combo.currentIndexChanged.connect(self._update_create_state)

        self._update_create_state()

    def _priority_spin(self, value: float, parent) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(parent)
        spin.setRange(0.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        spin.setValue(normalize_batch_priority(value))
        return spin

    def _classification_combo(self, value: str, parent) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItem(t("extract_batch_other"), "other")
        combo.addItem(t("knowledge_tree_topic"), "topic")
        combo.addItem(t("knowledge_tree_item"), "item")
        index = combo.findData(normalize_batch_classification(value))
        combo.setCurrentIndex(max(0, index))
        return combo

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
        priority = normalize_batch_priority(self._bulk_priority.value())
        classification = normalize_batch_classification(
            self._bulk_classification.currentData()
        )
        tags = normalize_batch_tags(self._bulk_tags.text())
        self._rows = [
            normalize_batch_preview_row(
                dict(row),
                default_priority=priority,
                default_classification=classification,
                default_tags=tags,
            )
            for row in parse_batch_qa_text(self._raw_edit.toPlainText())
        ]
        self._rebuild_table()
        self._update_create_state()

    def _rebuild_table(self) -> None:
        self._syncing_table = True
        self._table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            normalized = normalize_batch_preview_row(row)
            if row.get("valid") is False and not normalized["error"]:
                normalized["error"] = t("extract_batch_invalid_row")
            self._rows[row_index] = normalized

            status_text = t("common_valid") if normalized["valid"] else str(normalized["error"] or t("common_invalid"))
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            question_item = QTableWidgetItem(str(normalized["question"] or ""))
            answer_item = QTableWidgetItem(str(normalized["answer"] or ""))
            self._table.setItem(row_index, 0, status_item)
            self._table.setItem(row_index, 1, question_item)
            self._table.setItem(row_index, 2, answer_item)

            priority_spin = self._priority_spin(
                normalize_batch_priority(normalized["priority"]),
                self._table,
            )
            priority_spin.valueChanged.connect(
                lambda value, row=row_index: self._set_row_priority(row, value)
            )
            self._table.setCellWidget(row_index, 3, priority_spin)

            classification_combo = self._classification_combo(
                str(normalized["classification"]),
                self._table,
            )
            classification_combo.currentIndexChanged.connect(
                lambda _index, row=row_index, combo=classification_combo: self._set_row_classification(
                    row,
                    combo.currentData(),
                )
            )
            self._table.setCellWidget(row_index, 4, classification_combo)

            tags_edit = QLineEdit(
                " ".join(normalize_batch_tags(normalized["tags"])),
                self._table,
            )
            tags_edit.setPlaceholderText(t("extract_batch_tags_hint"))
            tags_edit.textChanged.connect(
                lambda text, row=row_index: self._set_row_tags(row, text)
            )
            self._table.setCellWidget(row_index, 5, tags_edit)
        self._syncing_table = False

    def _set_row_priority(self, row_index: int, value) -> None:
        if self._syncing_table or not (0 <= row_index < len(self._rows)):
            return
        self._rows[row_index]["priority"] = normalize_batch_priority(value)

    def _set_row_classification(self, row_index: int, value) -> None:
        if self._syncing_table or not (0 <= row_index < len(self._rows)):
            return
        self._rows[row_index]["classification"] = normalize_batch_classification(value)

    def _set_row_tags(self, row_index: int, value) -> None:
        if self._syncing_table or not (0 <= row_index < len(self._rows)):
            return
        self._rows[row_index]["tags"] = normalize_batch_tags(value)

    def _apply_to_all_rows(self) -> None:
        priority = normalize_batch_priority(self._bulk_priority.value())
        classification = normalize_batch_classification(
            self._bulk_classification.currentData()
        )
        tags = normalize_batch_tags(self._bulk_tags.text())
        for row in self._rows:
            row["priority"] = priority
            row["classification"] = classification
            row["tags"] = list(tags)
        self._rebuild_table()
        self._update_create_state()

    def _on_item_changed(self, item) -> None:
        if self._syncing_table or item is None:
            return
        row_index = int(item.row())
        if row_index < 0 or row_index >= len(self._rows):
            return
        question = self._table.item(row_index, 1)
        answer = self._table.item(row_index, 2)
        existing = dict(self._rows[row_index])
        normalized = normalize_batch_preview_row(
            {
                "question": question.text() if question is not None else "",
                "answer": answer.text() if answer is not None else "",
                "priority": existing.get("priority"),
                "classification": existing.get("classification"),
                "tags": existing.get("tags"),
            }
        )
        self._rows[row_index] = normalized
        self._syncing_table = True
        status_item = self._table.item(row_index, 0)
        if status_item is not None:
            status_item.setText(t("common_valid") if normalized["valid"] else str(normalized["error"]))
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
            status = t("extract_batch_fields_different")
        elif invalid_rows:
            status = tn("extract_batch_fix_invalid_rows", invalid_rows)
        elif not self._rows:
            status = t("extract_batch_parse_one_block")
        else:
            status = tn("extract_batch_rows_ready", valid_rows)
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
    def preview_rows(self) -> list[dict[str, object]]:
        return [
            {
                "question": str(row.get("question") or "").strip(),
                "answer": str(row.get("answer") or "").strip(),
                "priority": normalize_batch_priority(row.get("priority")),
                "classification": normalize_batch_classification(
                    row.get("classification")
                ),
                "tags": normalize_batch_tags(row.get("tags")),
            }
            for row in self._rows
            if bool(row.get("valid"))
        ]
