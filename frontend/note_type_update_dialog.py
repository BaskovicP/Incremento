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
    from ..backend.note_type_updates import PendingNoteTypeUpdate
except ImportError:
    from note_type_updates import PendingNoteTypeUpdate  # type: ignore


ACTION_LATER = "later"
ACTION_SYNC_FIRST = "sync_first"
ACTION_APPLY = "apply"


def format_note_type_update_html(
    updates: tuple[PendingNoteTypeUpdate, ...] | list[PendingNoteTypeUpdate],
) -> str:
    rows = []
    for update in updates:
        changes = "<br>".join(f"• {escape(change)}" for change in update.changes)
        rows.append(
            f"<li><b>{escape(update.note_type)}</b><br>{changes}</li>"
        )
    update_list = "".join(rows) or "<li>No pending updates.</li>"
    return f"""
    <h2>Incremento card-format update</h2>
    <p><b>Incremento has not changed your Anki collection yet.</b></p>
    <p>The following Incremento note types need a field or card-template update:</p>
    <ul>{update_list}</ul>
    <p>Anki may require a one-way full sync after a note-type change because it
    cannot merge every schema change automatically.</p>
    <h3>Recommended safe order</h3>
    <ol>
      <li>Sync this device normally before applying the update, and make sure
      your other devices have also synced.</li>
      <li>Return here, confirm that this device contains the collection you want
      to keep, and apply the update.</li>
      <li>When Anki asks which version to keep, choose <b>Upload to AnkiWeb</b>
      from this device. On other devices, choose <b>Download</b>.</li>
    </ol>
    <p>You may choose <b>Later</b>; no note-type changes will be made.</p>
    """.strip()


class IncrementoNoteTypeUpdateDialog(QDialog):
    def __init__(self, updates, parent=None) -> None:
        super().__init__(parent)
        self._selected_action = ACTION_LATER
        self.setWindowTitle("Incremento Card Format Update")
        self.resize(680, 600)

        layout = QVBoxLayout(self)
        details = QTextBrowser(self)
        details.setOpenExternalLinks(True)
        details.setHtml(format_note_type_update_html(list(updates or ())))
        layout.addWidget(details, 1)

        self._confirmation = QCheckBox(
            "I have synced first, and this device has the collection I want to keep.",
            self,
        )
        layout.addWidget(self._confirmation)

        buttons = QHBoxLayout()
        self._sync_button = QPushButton("Sync Before Updating", self)
        self._apply_button = QPushButton("Apply Update", self)
        self._later_button = QPushButton("Later", self)
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
