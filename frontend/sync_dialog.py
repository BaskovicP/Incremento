"""Shared-folder sync for one profile: folder, status, Sync now, and conflicts to decide.

A thin view over a controller supplied by the composition root:
``status()``, ``conflicts()``, ``configure(folder)``, ``disable()``,
``sync(done)`` (runs in the background, calls ``done`` on the main thread)
and ``resolve(conflict_id, value)``. The rules live in backend/sync_service.py.
"""

import json
import time

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t

from aqt.qt import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, Qt, QVBoxLayout,
)
from aqt.utils import askUser, showInfo

MAX_VALUE_TEXT = 60


def _family_label(family: str, card: str) -> str:
    labels = {
        "priority": lambda: t("admin_sync_family_priority", card=card),
        "reader_bookmark": lambda: t("admin_sync_family_reader_bookmark", card=card),
        "reading_position": lambda: t("admin_sync_family_reading_position", card=card),
        "pdf_highlight": lambda: t("admin_sync_family_pdf_highlight", card=card),
        "epub_highlight": lambda: t("admin_sync_family_epub_highlight", card=card),
        "document": lambda: t("admin_sync_family_document", card=card),
    }
    return labels[family]() if family in labels else f"{family} {card}"


def describe_value(family: str, value) -> str:
    """A short, readable form of one side of a conflict."""
    if value is None:
        return t("admin_sync_deleted")
    if family == "priority":
        return f"{value['priority']:g}"
    if family == "reading_position":
        for field in ("page", "section_index", "position"):
            if field in value:
                return f"{field.split('_')[0]} {value[field]:g}"
    if family in ("reader_bookmark", "pdf_highlight", "epub_highlight"):
        text = value.get("comment_text") or value.get("note") or value.get("label") or value.get("text") or ""
        if text:
            return text if len(text) <= MAX_VALUE_TEXT else text[:MAX_VALUE_TEXT - 1] + "…"
    compact = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return compact if len(compact) <= MAX_VALUE_TEXT else compact[:MAX_VALUE_TEXT - 1] + "…"


def conflict_text(conflict) -> str:
    card = conflict.key.split("/")[0].partition(":")[2]
    mine = conflict.values[conflict.local_index]
    theirs = next(value for index, value in enumerate(conflict.values) if index != conflict.local_index)
    return t("admin_sync_conflict_row", what=_family_label(conflict.family, card),
             mine=describe_value(conflict.family, mine), theirs=describe_value(conflict.family, theirs))


class SyncDialog(QDialog):
    def __init__(self, profile: str, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._conflicts = []
        self.setWindowTitle(t("admin_sync_title", profile=profile))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        for message in ("admin_sync_explanation", "admin_sync_local_only"):
            label = QLabel(t(message))
            label.setWordWrap(True)
            layout.addWidget(label)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(t("admin_sync_folder")))
        self._folder = QLineEdit()
        self._folder.setReadOnly(True)
        self._folder.setAccessibleName(t("admin_sync_folder"))
        folder_row.addWidget(self._folder, 1)
        self._choose = QPushButton(t("admin_sync_choose"))
        self._choose.clicked.connect(self._choose_folder)
        folder_row.addWidget(self._choose)
        layout.addLayout(folder_row)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._status)
        self._discard = QPushButton(t("admin_sync_discard"))
        self._discard.clicked.connect(self._discard_stale)
        self._discard.setHidden(True)
        discard_row = QHBoxLayout()
        discard_row.addWidget(self._discard)
        discard_row.addStretch(1)
        layout.addLayout(discard_row)
        self._stale = 0

        layout.addWidget(QLabel(t("admin_sync_conflicts_heading")))
        self._list = QListWidget()
        self._list.setAccessibleName(t("admin_sync_conflicts_heading"))
        self._list.currentRowChanged.connect(lambda _row: self._update_buttons())
        layout.addWidget(self._list, 1)
        decide = QHBoxLayout()
        self._keep_mine = QPushButton(t("admin_sync_keep_mine"))
        self._keep_mine.clicked.connect(lambda: self._resolve(mine=True))
        self._use_theirs = QPushButton(t("admin_sync_use_theirs"))
        self._use_theirs.clicked.connect(lambda: self._resolve(mine=False))
        decide.addWidget(self._keep_mine)
        decide.addWidget(self._use_theirs)
        decide.addStretch(1)
        layout.addLayout(decide)

        actions = QDialogButtonBox()
        self._sync = actions.addButton(t("admin_sync_now"), QDialogButtonBox.ButtonRole.ActionRole)
        self._sync.clicked.connect(self._sync_now)
        self._stop = actions.addButton(t("admin_sync_stop"), QDialogButtonBox.ButtonRole.DestructiveRole)
        self._stop.clicked.connect(self._stop_syncing)
        close = actions.addButton(t("common_close"), QDialogButtonBox.ButtonRole.RejectRole)
        close.clicked.connect(self.reject)
        layout.addWidget(actions)
        self._running = False
        self.refresh()

    # --- state -------------------------------------------------------------------

    def refresh(self) -> None:
        status = self._controller.status()
        self._configured = bool(status.configured)
        self._folder.setText(status.folder if status.configured and status.folder else t("admin_sync_not_set_up"))
        lines = [t("admin_sync_last_synced", time=time.strftime("%Y-%m-%d %H:%M", time.localtime(status.last_sync)))
                 if status.last_sync else t("admin_sync_never_synced")]
        if status.waiting_for_anki:
            lines.append(t("admin_sync_waiting_for_anki", count=status.waiting_for_anki))
        if status.waiting_for_files:
            lines.append(t("admin_sync_waiting_for_files", count=status.waiting_for_files))
        self._stale = getattr(status, "stale_waiting", 0)
        if self._stale:
            lines.append(t("admin_sync_stale", count=self._stale))
        self._discard.setHidden(not self._stale)
        self._status.setText("\n".join(lines))
        self._conflicts = list(self._controller.conflicts())
        self._list.clear()
        for conflict in self._conflicts:
            item = QListWidgetItem(conflict_text(conflict))
            item.setData(Qt.ItemDataRole.UserRole, conflict.id)
            self._list.addItem(item)
        if not self._conflicts:
            placeholder = QListWidgetItem(t("admin_sync_no_conflicts"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)
        self._update_buttons()

    def _selected(self):
        row = self._list.currentRow()
        return self._conflicts[row] if self._conflicts and 0 <= row < len(self._conflicts) else None

    def _update_buttons(self) -> None:
        chosen = self._selected() is not None and not self._running
        self._keep_mine.setEnabled(chosen)
        self._use_theirs.setEnabled(chosen)
        self._sync.setEnabled(self._configured and not self._running)
        self._sync.setText(t("admin_sync_running") if self._running else t("admin_sync_now"))
        self._stop.setEnabled(self._configured and not self._running)
        self._choose.setEnabled(not self._running)

    # --- actions -----------------------------------------------------------------

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("admin_sync_choose_folder"), self._folder.text())
        if folder:
            self.use_folder(folder)

    def use_folder(self, folder: str) -> None:
        try:
            self._controller.configure(folder)
        except Exception as exc:  # the service explains why a folder cannot be used
            showInfo(t("admin_sync_setup_failed", error=exc), parent=self)
        self.refresh()

    def _sync_now(self) -> None:
        self._running = True
        self._update_buttons()
        self._controller.sync(self._synced)

    def _synced(self) -> None:
        self._running = False
        self.refresh()

    def _discard_stale(self) -> None:
        if askUser(t("admin_sync_discard_confirm", count=self._stale), parent=self):
            self._controller.discard_stale()
            self.refresh()

    def _stop_syncing(self) -> None:
        if askUser(t("admin_sync_stop_confirm"), parent=self):
            self._controller.disable()
            self.refresh()

    def _resolve(self, *, mine: bool) -> None:
        conflict = self._selected()
        if conflict is None:
            return
        if mine:
            value = conflict.values[conflict.local_index]
        else:
            value = next(v for index, v in enumerate(conflict.values) if index != conflict.local_index)
        self._controller.resolve(conflict.id, value)
        self.refresh()
