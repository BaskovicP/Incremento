"""Non-modal, polling Activity Center for Incremento background work."""

from __future__ import annotations

import math
import time

try:
    from ..backend.i18n import t as _t, tn as _tn
except ImportError:
    from backend.i18n import t as _t, tn as _tn

try:
    from ..backend.activity_log import (
        cancel_activity,
        clear_finished_activities,
        retry_activity,
        snapshot_activities,
    )
except ImportError:
    from activity_log import (  # type: ignore
        cancel_activity,
        clear_finished_activities,
        retry_activity,
        snapshot_activities,
    )


_STATUS_LABELS = {
    "running": "imports_activity_running",
    "succeeded": "imports_activity_completed",
    "failed": "imports_activity_failed",
    "cancelled": "imports_activity_cancelled",
}


def activity_status_text(status: str) -> str:
    normalized = str(status or "").strip().lower()
    key = _STATUS_LABELS.get(normalized)
    return _t(key) if key else normalized.replace("_", " ").title() or _t("imports_activity_unknown")


def activity_progress_text(progress, status: str) -> str:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "succeeded":
        return _t("imports_activity_complete")
    try:
        value = float(progress)
    except Exception:
        value = math.nan
    if not math.isfinite(value):
        return _t("imports_activity_working") if normalized_status == "running" else "—"
    return f"{max(0, min(100, round(value * 100)))}%"


def _age_text(timestamp) -> str:
    try:
        seconds = max(0, int(time.time() - float(timestamp)))
    except Exception:
        return ""
    if seconds < 60:
        return _t("imports_activity_now")
    if seconds < 3600:
        return _tn("imports_activity_minutes_ago", seconds // 60)
    if seconds < 86400:
        return _tn("imports_activity_hours_ago", seconds // 3600)
    return _tn("imports_activity_days_ago", seconds // 86400)


def create_activity_center_dialog(parent):
    from aqt.qt import (
        QCheckBox,
        QDialog,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTimer,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        Qt,
    )

    class ActivityCenterDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle(_t("imports_activity_title"))
            self.setMinimumSize(760, 480)
            self.setModal(False)
            self._visible_rows: list[dict] = []

            root = QVBoxLayout(self)
            intro = QLabel(_t("imports_activity_intro"))
            intro.setWordWrap(True)
            root.addWidget(intro)

            controls = QHBoxLayout()
            self._show_finished = QCheckBox(_t("imports_activity_show_finished"), self)
            self._show_finished.setChecked(True)
            self._show_finished.setAccessibleName(_t("imports_activity_show_finished_accessible"))
            controls.addWidget(self._show_finished)
            controls.addStretch(1)
            self._clear_button = QPushButton(_t("imports_activity_clear_finished"), self)
            self._clear_button.setAccessibleName(_t("imports_activity_clear_finished_accessible"))
            controls.addWidget(self._clear_button)
            root.addLayout(controls)

            self._activity_tree = QTreeWidget(self)
            self._activity_tree.setColumnCount(5)
            self._activity_tree.setHeaderLabels(
                (_t("imports_activity_column_activity"), _t("imports_activity_column_category"), _t("imports_activity_column_status"), _t("imports_activity_column_progress"), _t("imports_activity_column_updated"))
            )
            self._activity_tree.setRootIsDecorated(False)
            self._activity_tree.setAlternatingRowColors(True)
            self._activity_tree.setAccessibleName(_t("imports_activity_tree_accessible"))
            root.addWidget(self._activity_tree, 1)

            self._detail_label = QLabel(_t("imports_activity_select_detail"), self)
            self._detail_label.setWordWrap(True)
            self._detail_label.setAccessibleName(_t("imports_activity_detail_accessible"))
            root.addWidget(self._detail_label)

            actions = QHBoxLayout()
            self._cancel_button = QPushButton(_t("imports_activity_cancel_task"), self)
            self._retry_button = QPushButton(_t("imports_activity_retry"), self)
            close_button = QPushButton(_t("imports_activity_close"), self)
            self._cancel_button.setAccessibleName(_t("imports_activity_cancel_accessible"))
            self._retry_button.setAccessibleName(_t("imports_activity_retry_accessible"))
            close_button.setAccessibleName(_t("imports_activity_close_accessible"))
            actions.addWidget(self._cancel_button)
            actions.addWidget(self._retry_button)
            actions.addStretch(1)
            actions.addWidget(close_button)
            root.addLayout(actions)

            self._show_finished.toggled.connect(self._refresh)
            self._clear_button.clicked.connect(self._clear_finished)
            self._activity_tree.currentItemChanged.connect(self._selection_changed)
            self._cancel_button.clicked.connect(self._cancel_selected)
            self._retry_button.clicked.connect(self._retry_selected)
            close_button.clicked.connect(self.reject)

            self._refresh_timer = QTimer(self)
            self._refresh_timer.setInterval(750)
            self._refresh_timer.timeout.connect(self._refresh)
            self._refresh_timer.start()
            self._refresh()

        def _selected_row(self) -> dict | None:
            item = self._activity_tree.currentItem()
            if item is None:
                return None
            activity_id = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
            return next(
                (row for row in self._visible_rows if row["activity_id"] == activity_id),
                None,
            )

        def _refresh(self, *_args) -> None:
            selected = self._selected_row()
            selected_id = str((selected or {}).get("activity_id") or "")
            self._visible_rows = snapshot_activities(
                include_finished=self._show_finished.isChecked()
            )
            self._activity_tree.clear()
            selected_item = None
            for row in self._visible_rows:
                item = QTreeWidgetItem(
                    [
                        str(row.get("title") or ""),
                        str(row.get("category") or ""),
                        activity_status_text(row.get("status")),
                        activity_progress_text(row.get("progress"), row.get("status")),
                        _age_text(row.get("updated_at")),
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, row["activity_id"])
                self._activity_tree.addTopLevelItem(item)
                if row["activity_id"] == selected_id:
                    selected_item = item
            if selected_item is not None:
                self._activity_tree.setCurrentItem(selected_item)
            elif self._activity_tree.topLevelItemCount():
                self._activity_tree.setCurrentItem(self._activity_tree.topLevelItem(0))
            else:
                self._detail_label.setText(_t("imports_activity_none"))
                self._cancel_button.setEnabled(False)
                self._retry_button.setEnabled(False)
            for column in range(1, 5):
                self._activity_tree.resizeColumnToContents(column)

        def _selection_changed(self, *_args) -> None:
            row = self._selected_row()
            if row is None:
                self._cancel_button.setEnabled(False)
                self._retry_button.setEnabled(False)
                return
            detail = str(row.get("detail") or _t("imports_activity_no_details"))
            self._detail_label.setText(detail)
            self._cancel_button.setEnabled(bool(row.get("can_cancel")))
            self._retry_button.setEnabled(bool(row.get("can_retry")))

        def _cancel_selected(self) -> None:
            row = self._selected_row()
            if row and cancel_activity(row["activity_id"]):
                self._refresh()

        def _retry_selected(self) -> None:
            row = self._selected_row()
            if row and retry_activity(row["activity_id"]):
                self._refresh()

        def _clear_finished(self) -> None:
            clear_finished_activities()
            self._refresh()

        def closeEvent(self, event) -> None:
            self._refresh_timer.stop()
            super().closeEvent(event)

    return ActivityCenterDialog()
