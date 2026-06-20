from __future__ import annotations

from aqt.qt import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout, qconnect


class BookmarkCommentDialog(QDialog):
    def __init__(self, parent, *, title: str, context_label: str, current_comment: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(480, 320)

        layout = QVBoxLayout(self)

        context_title = QLabel("Bookmark:")
        context_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(context_title)

        context_preview = QLabel(str(context_label or "").strip() or "Bookmark")
        context_preview.setWordWrap(True)
        context_preview.setStyleSheet(
            "QLabel { background: rgba(74,144,217,0.08); border: 1px solid rgba(74,144,217,0.25); border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(context_preview)

        comment_label = QLabel("Comment:")
        comment_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(comment_label)

        self._editor = QTextEdit(self)
        self._editor.setPlaceholderText("Write an optional note about why this moment matters…")
        self._editor.setPlainText(str(current_comment or ""))
        layout.addWidget(self._editor, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

    def comment_text(self) -> str:
        return self._editor.toPlainText().strip()
