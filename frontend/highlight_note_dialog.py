from __future__ import annotations

from aqt.qt import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout, qconnect
try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


class HighlightNoteDialog(QDialog):
    def __init__(self, parent, *, title: str, excerpt: str, current_note: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(480, 320)

        layout = QVBoxLayout(self)
        excerpt_label = QLabel(t("reader_selected_text_label"))
        excerpt_label.setStyleSheet("font-weight: bold;")
        excerpt_label.setWordWrap(True)
        layout.addWidget(excerpt_label)

        excerpt_preview = QLabel(str(excerpt or "").strip() or t("reader_no_text_parenthesized"))
        excerpt_preview.setWordWrap(True)
        excerpt_preview.setStyleSheet(
            "QLabel { background: rgba(74,144,217,0.08); border: 1px solid rgba(74,144,217,0.25); border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(excerpt_preview)

        note_label = QLabel(t("reader_text_note_label"))
        note_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(note_label)

        self._editor = QTextEdit(self)
        self._editor.setPlaceholderText(t("reader_highlight_note_placeholder"))
        self._editor.setPlainText(str(current_note or ""))
        layout.addWidget(self._editor, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("reader_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("reader_cancel"))
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

    def note_text(self) -> str:
        return self._editor.toPlainText().strip()
