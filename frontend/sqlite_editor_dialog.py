from __future__ import annotations

import datetime as _dt
import sqlite3
from typing import Any

from aqt.qt import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
)

try:
    from ..backend.db import (
        list_database_checkpoints,
        open_database_editor_connection,
    )
except ImportError:
    from backend.db import (  # type: ignore
        list_database_checkpoints,
        open_database_editor_connection,
    )


def _format_timestamp(value: object) -> str:
    try:
        return _dt.datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Unknown"


def _format_size(size_bytes: object) -> str:
    try:
        size = float(size_bytes)
    except Exception:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


class SQLiteEditorDialog(QDialog):
    _ROW_LIMIT = 200
    _RESULT_LIMIT = 500
    _UNLOCK_PHRASE = "UNLOCK"

    def __init__(
        self,
        addon_dir: str,
        profile: str,
        *,
        checkpoint_info: dict[str, object] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._profile = profile
        self._checkpoint_info = checkpoint_info or {}
        self._conn: sqlite3.Connection | None = None
        self._read_only = True
        self._current_table = ""
        self._current_table_type = "table"
        self._row_offset = 0
        self._row_update_keys: list[dict[str, Any]] = []
        self._row_column_names: list[str] = []
        self._row_column_types: dict[str, str] = {}
        self._suspend_row_update = False
        self.setWindowTitle("Incremento Database Editor")
        self.resize(1220, 760)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        intro = QLabel(
            "Inspect the active profile's Incremento SQLite database. "
            "This editor starts read-only. Unlock writes only if you know exactly what SQL you intend to run."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._mode_label = QLabel()
        self._db_label = QLabel()
        self._checkpoint_label = QLabel()
        self._recent_checkpoints_label = QLabel()
        self._recent_checkpoints_label.setWordWrap(True)

        root.addWidget(self._mode_label)
        root.addWidget(self._db_label)
        root.addWidget(self._checkpoint_label)
        root.addWidget(self._recent_checkpoints_label)

        top_actions = QHBoxLayout()
        top_actions.setSpacing(8)
        self._unlock_btn = QPushButton("Unlock Writes...")
        self._unlock_btn.clicked.connect(self._unlock_writes)
        top_actions.addWidget(self._unlock_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_current_view)
        top_actions.addWidget(self._refresh_btn)
        top_actions.addStretch(1)
        root.addLayout(top_actions)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("Tables"))
        self._table_list = QListWidget()
        self._table_list.currentItemChanged.connect(self._on_table_changed)
        left_layout.addWidget(self._table_list, 1)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        self._table_title = QLabel("Rows")
        center_layout.addWidget(self._table_title)

        table_nav = QHBoxLayout()
        table_nav.setSpacing(8)
        self._prev_rows_btn = QPushButton("Previous")
        self._prev_rows_btn.clicked.connect(self._load_previous_rows)
        table_nav.addWidget(self._prev_rows_btn)
        self._next_rows_btn = QPushButton("Next")
        self._next_rows_btn.clicked.connect(self._load_next_rows)
        table_nav.addWidget(self._next_rows_btn)
        self._rows_page_label = QLabel()
        table_nav.addWidget(self._rows_page_label)
        table_nav.addStretch(1)
        center_layout.addLayout(table_nav)

        self._rows_table = QTableWidget()
        self._rows_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._rows_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._rows_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._rows_table.itemChanged.connect(self._on_row_item_changed)
        self._rows_table.verticalHeader().setVisible(False)
        self._rows_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._rows_table.horizontalHeader().setStretchLastSection(True)
        center_layout.addWidget(self._rows_table, 1)
        splitter.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(QLabel("Schema"))
        self._schema_text = QPlainTextEdit()
        self._schema_text.setReadOnly(True)
        self._schema_text.setMaximumBlockCount(2000)
        right_layout.addWidget(self._schema_text, 1)
        right_layout.addWidget(QLabel("SQL Console"))
        self._sql_edit = QPlainTextEdit()
        self._sql_edit.setPlaceholderText(
            "Read-only examples:\n"
            "SELECT * FROM priorities LIMIT 20;\n"
            "PRAGMA table_info(priorities);\n\n"
            "Mutating SQL requires Unlock Writes."
        )
        self._sql_edit.setMinimumHeight(160)
        right_layout.addWidget(self._sql_edit)

        sql_actions = QHBoxLayout()
        sql_actions.setSpacing(8)
        self._run_sql_btn = QPushButton("Run SQL")
        self._run_sql_btn.clicked.connect(self._run_sql)
        sql_actions.addWidget(self._run_sql_btn)
        sql_actions.addStretch(1)
        right_layout.addLayout(sql_actions)

        self._sql_status = QLabel()
        self._sql_status.setWordWrap(True)
        right_layout.addWidget(self._sql_status)

        self._result_table = QTableWidget()
        self._result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._result_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._result_table.verticalHeader().setVisible(False)
        self._result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._result_table.horizontalHeader().setStretchLastSection(True)
        right_layout.addWidget(self._result_table, 1)
        splitter.addWidget(right)
        splitter.setSizes([220, 460, 540])

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        close_row.addWidget(self._close_btn)
        root.addLayout(close_row)

        self._open_connection(read_only=True)
        self._refresh_header()
        self._refresh_schema()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._close_connection()
        super().closeEvent(event)

    def _close_connection(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _open_connection(self, *, read_only: bool) -> None:
        self._close_connection()
        self._conn = open_database_editor_connection(
            self._addon_dir,
            self._profile,
            read_only=read_only,
        )
        self._read_only = bool(read_only)
        self._refresh_mode_label()

    def _refresh_mode_label(self) -> None:
        mode = "Read-only" if self._read_only else "Unlocked for writes"
        warning = (
            "SQL writes and cell editing are disabled."
            if self._read_only
            else "SQL writes and cell editing are enabled for this editor session."
        )
        self._mode_label.setText(f"<b>Mode:</b> {mode} - {warning}")
        self._sync_row_editability()

    def _refresh_header(self) -> None:
        if self._conn is not None:
            try:
                db_path = self._conn.execute("PRAGMA database_list").fetchone()[2]
            except Exception:
                db_path = ""
        else:
            db_path = ""
        self._db_label.setText(f"<b>Database:</b> {db_path}")
        if self._checkpoint_info:
            self._checkpoint_label.setText(
                "<b>Automatic checkpoint:</b> "
                f"{self._checkpoint_info.get('path', '')} "
                f"({_format_timestamp(self._checkpoint_info.get('created_at'))}, "
                f"{_format_size(self._checkpoint_info.get('size_bytes'))})"
            )
        else:
            self._checkpoint_label.setText("<b>Automatic checkpoint:</b> unavailable")
        recent = list_database_checkpoints(self._addon_dir, self._profile, limit=3)
        if recent:
            text = "; ".join(
                f"{row['filename']} ({_format_timestamp(row['created_at'])})"
                for row in recent
            )
            self._recent_checkpoints_label.setText(f"<b>Recent checkpoints:</b> {text}")
        else:
            self._recent_checkpoints_label.setText("<b>Recent checkpoints:</b> none")

    def _refresh_schema(self) -> None:
        if self._conn is None:
            return
        current = self._current_table
        self._table_list.blockSignals(True)
        self._table_list.clear()
        rows = self._conn.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, lower(name)
            """
        ).fetchall()
        current_item = None
        for row in rows:
            item = QListWidgetItem(f"{row['name']} ({row['type']})")
            item.setData(Qt.ItemDataRole.UserRole, str(row["name"]))
            item.setData(Qt.ItemDataRole.UserRole + 1, str(row["type"]))
            self._table_list.addItem(item)
            if str(row["name"]) == current:
                current_item = item
        self._table_list.blockSignals(False)
        if current_item is not None:
            self._table_list.setCurrentItem(current_item)
        elif self._table_list.count():
            self._table_list.setCurrentRow(0)
        else:
            self._current_table = ""
            self._schema_text.setPlainText("No tables found.")
            self._clear_table_widget(self._rows_table)

    def _refresh_current_view(self) -> None:
        self._refresh_header()
        self._refresh_schema()
        self._load_table_rows()

    def _on_table_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._current_table = str(current.data(Qt.ItemDataRole.UserRole) or "") if current else ""
        self._current_table_type = (
            str(current.data(Qt.ItemDataRole.UserRole + 1) or "table") if current else "table"
        )
        self._row_offset = 0
        self._load_table_rows()

    def _load_previous_rows(self) -> None:
        if self._row_offset <= 0:
            return
        self._row_offset = max(0, self._row_offset - self._ROW_LIMIT)
        self._load_table_rows()

    def _load_next_rows(self) -> None:
        self._row_offset += self._ROW_LIMIT
        self._load_table_rows()

    def _load_table_rows(self) -> None:
        if self._conn is None or not self._current_table:
            self._table_title.setText("Rows")
            self._rows_page_label.setText("")
            self._schema_text.setPlainText("Select a table.")
            self._clear_table_widget(self._rows_table)
            return
        table_name = _quote_identifier(self._current_table)
        try:
            schema_rows = self._conn.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
            count = self._conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            has_primary_key = any(int(col["pk"] or 0) > 0 for col in schema_rows)
            select_sql = f"SELECT * FROM {table_name} LIMIT ? OFFSET ?"
            if self._current_table_type == "table" and not has_primary_key:
                select_sql = (
                    f"SELECT rowid AS __incremento_rowid, * FROM {table_name} LIMIT ? OFFSET ?"
                )
            rows = self._conn.execute(
                select_sql,
                (self._ROW_LIMIT, self._row_offset),
            ).fetchall()
        except Exception as exc:
            self._schema_text.setPlainText(f"Could not load schema:\n{exc}")
            self._sql_status.setText(f"Could not load rows for {self._current_table}: {exc}")
            self._clear_table_widget(self._rows_table)
            return

        schema_lines = [f"Table: {self._current_table}", ""]
        for column in schema_rows:
            schema_lines.append(
                f"{column['name']}  {column['type'] or 'TEXT'}"
                f"  notnull={column['notnull']}  default={column['dflt_value']}  pk={column['pk']}"
            )
        schema_lines.append("")
        if self._current_table_type != "table":
            schema_lines.append("Direct cell editing is disabled for views.")
        elif self._read_only:
            schema_lines.append("Direct cell editing is disabled until writes are unlocked.")
        elif has_primary_key:
            schema_lines.append("Direct cell editing uses the table primary key to update rows.")
        else:
            schema_lines.append("Direct cell editing uses SQLite rowid because this table has no declared primary key.")
        self._schema_text.setPlainText("\n".join(schema_lines))
        self._table_title.setText(f"Rows - {self._current_table} ({count} total)")
        start_row = self._row_offset + 1 if rows else 0
        end_row = self._row_offset + len(rows)
        self._rows_page_label.setText(f"Showing {start_row}-{end_row} of {count}")
        self._prev_rows_btn.setEnabled(self._row_offset > 0)
        self._next_rows_btn.setEnabled(end_row < count)
        self._populate_table_widget(self._rows_table, rows, schema_rows=schema_rows)

    def _run_sql(self) -> None:
        sql = self._sql_edit.toPlainText().strip()
        if not sql:
            self._sql_status.setText("Enter a SQL statement first.")
            return
        if self._conn is None:
            self._sql_status.setText("Database connection is not available.")
            return
        mutating = self._is_mutating_sql(sql)
        if mutating and self._read_only:
            self._sql_status.setText(
                "SQL writes are locked. Use Unlock Writes before running mutating SQL."
            )
            return
        try:
            if mutating:
                self._conn.executescript(sql)
                self._conn.commit()
                self._sql_status.setText("SQL write executed and committed.")
                self._clear_table_widget(self._result_table)
                self._refresh_current_view()
                return
            cur = self._conn.execute(sql)
            rows = cur.fetchmany(self._RESULT_LIMIT)
            self._populate_table_widget(self._result_table, rows)
            more_note = " (truncated)" if len(rows) >= self._RESULT_LIMIT else ""
            self._sql_status.setText(
                f"Query returned {len(rows)} row(s){more_note}."
            )
        except Exception as exc:
            self._sql_status.setText(f"SQL error: {exc}")

    def _unlock_writes(self) -> None:
        if not self._read_only:
            self._sql_status.setText("SQL writes are already unlocked for this session.")
            return
        text, accepted = QInputDialog.getText(
            self,
            "Unlock Database Writes",
            "This editor writes directly to the live Incremento profile database.\n\n"
            f"Type {self._UNLOCK_PHRASE} to enable SQL writes for this session:",
        )
        if not accepted:
            return
        if str(text or "").strip() != self._UNLOCK_PHRASE:
            self._sql_status.setText("Unlock cancelled. Confirmation phrase did not match.")
            return
        self._open_connection(read_only=False)
        self._refresh_header()
        self._refresh_current_view()
        self._sql_status.setText("SQL writes unlocked for this editor session.")

    def _sync_row_editability(self) -> None:
        editable = self._table_allows_direct_edit()
        trigger = (
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
            if editable
            else QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._rows_table.setEditTriggers(trigger)

    def _table_allows_direct_edit(self) -> bool:
        return (
            not self._read_only
            and bool(self._current_table)
            and self._current_table_type == "table"
            and bool(self._row_update_keys)
        )

    def _on_row_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_row_update:
            return
        if self._conn is None:
            return
        if not self._table_allows_direct_edit():
            return
        row_index = int(item.row())
        column_index = int(item.column())
        if row_index < 0 or row_index >= len(self._row_update_keys):
            return
        if column_index < 0 or column_index >= len(self._row_column_names):
            return
        key_info = self._row_update_keys[row_index]
        if not key_info.get("where"):
            self._sql_status.setText("This row cannot be edited safely from the grid.")
            return
        column_name = self._row_column_names[column_index]
        column_type = self._row_column_types.get(column_name, "")
        old_value = key_info.get("values", {}).get(column_name)
        new_value = self._coerce_cell_value(item.text(), column_type, old_value)
        if new_value == old_value:
            return
        try:
            self._update_table_cell(column_name, new_value, key_info)
        except Exception as exc:
            self._suspend_row_update = True
            try:
                item.setText("" if old_value is None else str(old_value))
            finally:
                self._suspend_row_update = False
            self._sql_status.setText(f"Cell update failed: {exc}")
            return
        key_info.setdefault("values", {})[column_name] = new_value
        self._sql_status.setText(
            f"Updated {self._current_table}.{column_name} at row {self._row_offset + row_index + 1}."
        )

    def _update_table_cell(self, column_name: str, new_value: object, key_info: dict[str, Any]) -> None:
        if self._conn is None:
            raise RuntimeError("Database connection is not available.")
        where_parts = [f"{_quote_identifier(name)} IS ?" if value is None else f"{_quote_identifier(name)} = ?" for name, value in key_info["where"]]
        sql = (
            f"UPDATE {_quote_identifier(self._current_table)} "
            f"SET {_quote_identifier(column_name)} = ? "
            f"WHERE {' AND '.join(where_parts)}"
        )
        params = [new_value] + [value for _, value in key_info["where"]]
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        if cur.rowcount == 0:
            raise RuntimeError("The selected row could not be matched for update.")

    @staticmethod
    def _coerce_cell_value(raw_text: str, declared_type: str, old_value: object) -> object:
        text = str(raw_text)
        stripped = text.strip()
        if stripped.upper() == "NULL":
            return None
        normalized_type = str(declared_type or "").upper()
        if old_value is None and stripped == "":
            return None
        if normalized_type and any(token in normalized_type for token in ("INT", "BOOL")):
            try:
                return int(stripped)
            except Exception:
                return text
        if normalized_type and any(token in normalized_type for token in ("REAL", "FLOA", "DOUB", "NUM")):
            try:
                return float(stripped)
            except Exception:
                return text
        return text

    @staticmethod
    def _row_identity_for_table(
        row: sqlite3.Row,
        schema_rows: list[sqlite3.Row],
        *,
        includes_rowid: bool,
    ) -> dict[str, Any]:
        values = {str(key): row[key] for key in row.keys() if str(key) != "__incremento_rowid"}
        pk_columns = [str(col["name"]) for col in schema_rows if int(col["pk"] or 0) > 0]
        if pk_columns and all(column in values for column in pk_columns):
            return {
                "where": [(column, values.get(column)) for column in pk_columns],
                "values": values,
            }
        if includes_rowid and "__incremento_rowid" in row.keys():
            return {
                "where": [("rowid", row["__incremento_rowid"])],
                "values": values,
            }
        return {
            "where": [],
            "values": values,
        }

    @staticmethod
    def _is_mutating_sql(sql: str) -> bool:
        stripped = str(sql or "").lstrip()
        while stripped.startswith("--"):
            parts = stripped.splitlines()
            stripped = "\n".join(parts[1:]).lstrip() if len(parts) > 1 else ""
        keyword = stripped.split(None, 1)[0].upper() if stripped else ""
        return keyword not in {"SELECT", "PRAGMA", "EXPLAIN"}

    @staticmethod
    def _clear_table_widget(widget: QTableWidget) -> None:
        widget.clear()
        widget.setRowCount(0)
        widget.setColumnCount(0)

    def _populate_table_widget(
        self,
        widget: QTableWidget,
        rows: list[sqlite3.Row],
        *,
        schema_rows: list[sqlite3.Row] | None = None,
    ) -> None:
        self._suspend_row_update = True
        self._clear_table_widget(widget)
        self._row_update_keys = []
        self._row_column_names = []
        self._row_column_types = {}
        if not rows:
            self._suspend_row_update = False
            return
        first = rows[0]
        all_columns = list(first.keys()) if hasattr(first, "keys") else [str(index) for index in range(len(first))]
        includes_rowid = "__incremento_rowid" in all_columns
        columns = [name for name in all_columns if name != "__incremento_rowid"]
        self._row_column_names = columns
        if schema_rows:
            self._row_column_types = {
                str(col["name"]): str(col["type"] or "")
                for col in schema_rows
            }
        widget.setColumnCount(len(columns))
        widget.setHorizontalHeaderLabels(columns)
        widget.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            if schema_rows:
                self._row_update_keys.append(
                    self._row_identity_for_table(row, schema_rows, includes_rowid=includes_rowid)
                )
            else:
                self._row_update_keys.append({"where": [], "values": {}})
            for column_index, column_name in enumerate(columns):
                try:
                    value = row[column_name] if hasattr(row, "keys") else row[column_index]
                except Exception:
                    value = ""
                item = QTableWidgetItem("" if value is None else str(value))
                widget.setItem(row_index, column_index, item)
        self._suspend_row_update = False
        self._sync_row_editability()
