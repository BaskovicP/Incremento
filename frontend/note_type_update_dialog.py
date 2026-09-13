"""Consent dialog for Anki note-type schema updates."""

from __future__ import annotations

from html import escape

from aqt.qt import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    qconnect,
)

try:
    from ..backend.i18n import t as _t
except ImportError:
    from backend.i18n import t as _t


try:
    from ..backend.note_type_updates import PendingNoteTypeUpdate
except ImportError:
    from note_type_updates import PendingNoteTypeUpdate  # type: ignore


ACTION_LATER = "later"
ACTION_SYNC_FIRST = "sync_first"
ACTION_APPLY = "apply"


def format_note_type_update_html(
    updates: tuple[PendingNoteTypeUpdate, ...] | list[PendingNoteTypeUpdate],
) -> str:
    def display_change(change: str) -> str:
        if change.startswith("add fields: "):
            return _t("admin_note_update_add_fields", fields=escape(change[len("add fields: "):]))
        keys = {
            "repair field order": "admin_note_update_repair",
            "restore the card template": "admin_note_update_restore",
            "update the card template": "admin_note_update_template",
        }
        return _t(keys[change]) if change in keys else escape(change)

    rows = []
    for update in updates:
        changes = "<br>".join(f"• {display_change(change)}" for change in update.changes)
        rows.append(
            f"<li><b>{escape(update.note_type)}</b><br>{changes}</li>"
        )
    update_list = "".join(rows) or _t("admin_note_update_empty")
    return _t("admin_note_update_instructions", update_list=update_list).strip()


class IncrementoNoteTypeUpdateDialog(QDialog):
    def __init__(self, updates, parent=None) -> None:
        super().__init__(parent)
        self._selected_action = ACTION_LATER
        self.setWindowTitle(_t("admin_note_update_title"))
        self.resize(680, 600)

        layout = QVBoxLayout(self)
        details = QTextBrowser(self)
        details.setOpenExternalLinks(True)
        details.setHtml(format_note_type_update_html(list(updates or ())))
        layout.addWidget(details, 1)

        self._confirmation = QCheckBox(
            _t("admin_note_update_confirm"),
            self,
        )
        layout.addWidget(self._confirmation)

        buttons = QHBoxLayout()
        self._sync_button = QPushButton(_t("admin_note_update_sync"), self)
        self._apply_button = QPushButton(_t("admin_note_update_apply"), self)
        self._later_button = QPushButton(_t("admin_note_update_later"), self)
        self._apply_button.setEnabled(False)
        self._later_button.setDefault(True)
        buttons.addWidget(self._sync_button)
        buttons.addStretch(1)
        buttons.addWidget(self._apply_button)
        buttons.addWidget(self._later_button)
        layout.addLayout(buttons)

        qconnect(
            self._confirmation.toggled,
            lambda checked: self._apply_button.setEnabled(bool(checked)),
        )
        qconnect(
            self._sync_button.clicked,
            lambda: self._finish(ACTION_SYNC_FIRST),
        )
        qconnect(self._apply_button.clicked, lambda: self._finish(ACTION_APPLY))
        qconnect(self._later_button.clicked, self.reject)

    @property
    def selected_action(self) -> str:
        return self._selected_action

    def _finish(self, action: str) -> None:
        self._selected_action = str(action or ACTION_LATER)
        self.accept()
