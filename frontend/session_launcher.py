"""Qt entry point for Incremento session construction."""

from __future__ import annotations

from aqt import mw
from aqt.qt import QDialog, QPushButton, QTextEdit, QVBoxLayout

try:
    from ..backend import session as _session
    from .learn_dialog import SchedulerConfigDialog
except ImportError:
    import session as _session  # type: ignore
    from learn_dialog import SchedulerConfigDialog  # type: ignore


def _show_scheduled_debug(selected_ids, picked_meta, branch_scope) -> None:
    dialog = QDialog(mw)
    branch_title = str((branch_scope or {}).get("root_title") or "").strip()
    title = f"DEBUG — Scheduled order ({len(selected_ids)} cards)"
    if branch_title:
        title += f" — {branch_title}"
    dialog.setWindowTitle(title)
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)
    text = QTextEdit()
    text.setReadOnly(True)
    text.setFontFamily("Courier")
    lines = ["#    type     mode       tag                  first field", "-" * 80]
    for index, card_id in enumerate(selected_ids):
        meta = picked_meta.get(card_id, {})
        card = mw.col.get_card(card_id)
        note = mw.col.get_note(card.nid)
        first_field = (
            note.fields[0][:55].replace("\n", " ")
            if note.fields
            else str(card_id)
        )
        lines.append(
            f"{index + 1:3}.  {meta.get('card_type', '?'):7}  "
            f"{meta.get('mode', '?'):9}  "
            f"{(meta.get('tag') or 'no-tag'):20} {first_field}"
        )
    text.setPlainText("\n".join(lines))
    layout.addWidget(text)
    button = QPushButton("Continue")
    button.clicked.connect(dialog.accept)
    layout.addWidget(button)
    dialog.exec()


_session.register_session_debug_callback(_show_scheduled_debug)


def learnFunction(*, branch_scope: dict | None = None) -> None:
    _session.learnFunction(
        branch_scope=branch_scope,
        dialog_factory=SchedulerConfigDialog,
    )
