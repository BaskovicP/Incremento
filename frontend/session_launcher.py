"""Qt entry point for Incremento session construction."""

from __future__ import annotations

from aqt import mw
from aqt.qt import QDialog, QPushButton, QTextEdit, QVBoxLayout

try:
    from ..backend.i18n import t as _t
except ImportError:
    from backend.i18n import t as _t


try:
    from ..backend import session as _session
    from .learn_dialog import SchedulerConfigDialog, session_type_label, session_mode_label
except ImportError:
    import session as _session  # type: ignore
    from learn_dialog import SchedulerConfigDialog, session_type_label, session_mode_label  # type: ignore


def _show_scheduled_debug(selected_ids, picked_meta, branch_scope) -> None:
    dialog = QDialog(mw)
    branch_title = str((branch_scope or {}).get("root_title") or "").strip()
    title = _t("admin_session_debug_title", count=len(selected_ids))
    if branch_title:
        title += f" — {branch_title}"
    dialog.setWindowTitle(title)
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)
    text = QTextEdit()
    text.setReadOnly(True)
    text.setFontFamily("Courier")
    lines = [_t("admin_session_header"), "-" * 80]
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
            f"{index + 1:3}.  {session_type_label(meta.get('card_type', '?')):7}  "
            f"{session_mode_label(meta.get('mode', '?')):9}  "
            f"{(meta.get('tag') or _t("admin_session_no_tag")):20} {first_field}"
        )
    text.setPlainText("\n".join(lines))
    layout.addWidget(text)
    button = QPushButton(_t("admin_session_continue"))
    button.clicked.connect(dialog.accept)
    layout.addWidget(button)
    dialog.exec()


_session.register_session_debug_callback(_show_scheduled_debug)


def learnFunction(*, branch_scope: dict | None = None) -> None:
    _session.learnFunction(
        branch_scope=branch_scope,
        dialog_factory=SchedulerConfigDialog,
    )
