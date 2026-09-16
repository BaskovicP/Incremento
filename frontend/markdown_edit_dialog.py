"""Explicit source editing of a managed Markdown learning document."""

from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QFontDatabase,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTimer,
    Qt,
    QVBoxLayout,
    QWidget,
)

try:
    from ..backend import paths, markdown_manager
    from ..backend.i18n import t
    from .markdown_document_dialog import MarkdownPreview
except ImportError:
    from backend import paths, markdown_manager
    from backend.i18n import t
    from frontend.markdown_document_dialog import MarkdownPreview


class EditMarkdownDocumentDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        profile: str,
        card_id: int,
        filename: str,
        title: str,
        *,
        is_current,
        on_saved,
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir, self._profile = addon_dir, profile
        self._card_id, self._filename, self._title = card_id, filename, title
        self._collection = mw.col
        self._is_current, self._on_saved = is_current, on_saved
        self._snapshot = None
        self._closed = self._saving = False
        self._preview_generation = 0
        self.finished.connect(self._finished)
        self.setWindowTitle(t("imports_markdown_edit_title", title=title))
        self.resize(1120, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        intro = QLabel(t("imports_markdown_edit_description"))
        intro.setWordWrap(True)
        intro.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(intro)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        left, right = QWidget(splitter), QWidget(splitter)
        left_layout, right_layout = QVBoxLayout(left), QVBoxLayout(right)
        left_layout.setContentsMargins(0, 0, 8, 0)
        right_layout.setContentsMargins(8, 0, 0, 0)
        left_layout.addWidget(QLabel(t("imports_markdown_source")))
        self._editor = QPlainTextEdit(left)
        source_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        source_font.setPointSizeF(self.font().pointSizeF())
        self._editor.setFont(source_font)
        self._editor.setAccessibleName(t("imports_markdown_source"))
        self._editor.setEnabled(False)
        left_layout.addWidget(self._editor, 1)
        right_layout.addWidget(QLabel(t("imports_preview")))
        self._preview = MarkdownPreview(right)
        right_layout.addWidget(self._preview, 1)
        splitter.setSizes([560, 500])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self._status = QLabel(t("imports_markdown_edit_loading"))
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self._save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        self._save_btn.setText(t("imports_markdown_save"))
        self._save_btn.setEnabled(False)
        self._cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_btn.setText(t("imports_cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._render_preview)
        self._editor.textChanged.connect(self._changed)
        self._load()

    def _finished(self, _result):
        self._closed = True
        self._preview_timer.stop()
        self._preview_generation += 1

    def _current(self):
        return (
            not self._closed
            and paths.get_active_profile() == self._profile
            and mw.col is self._collection
            and self._is_current()
        )

    def _failure(self, exc):
        if self._current():
            self._saving = False
            self._cancel_btn.setEnabled(True)
            self._editor.setEnabled(self._snapshot is not None)
            self._save_btn.setEnabled(self._snapshot is not None)
            self._status.setText(t("imports_markdown_failed", error=str(exc)))

    def _load(self):
        addon, profile, filename = self._addon_dir, self._profile, self._filename

        def done(future):
            if not self._current():
                return
            try:
                self._snapshot = future.result()
                self._editor.setPlainText(self._snapshot.text)
                self._editor.setEnabled(True)
                self._status.clear()
                self._save_btn.setEnabled(False)
            except Exception as exc:
                self._failure(exc)

        try:
            mw.taskman.run_in_background(
                lambda: markdown_manager.load_markdown_document(addon, profile, filename), done, uses_collection=False
            )
        except Exception as exc:
            self._failure(exc)

    def _changed(self):
        self._preview_generation += 1
        self._save_btn.setEnabled(
            bool(
                self._snapshot
                and not self._saving
                and self._current()
                and self._editor.toPlainText() != self._snapshot.text
            )
        )
        self._preview_timer.start()

    def _render_preview(self):
        if not self._current() or self._saving:
            return
        text, generation = self._editor.toPlainText(), self._preview_generation

        def done(future):
            if not self._current() or generation != self._preview_generation:
                return
            try:
                self._preview.setHtml(future.result())
            except Exception as exc:
                self._preview.setPlainText(t("imports_markdown_failed", error=str(exc)))

        try:
            mw.taskman.run_in_background(
                lambda: markdown_manager.render_markdown_text_preview(text), done, uses_collection=False
            )
        except Exception as exc:
            self._preview.setPlainText(t("imports_markdown_failed", error=str(exc)))

    def _save(self):
        if self._saving or not self._snapshot or not self._current():
            return
        text = self._editor.toPlainText()
        addon, profile, cid, filename, title = (
            self._addon_dir,
            self._profile,
            self._card_id,
            self._filename,
            self._title,
        )
        revision = self._snapshot.revision
        self._saving = True
        self._preview_timer.stop()
        self._preview_generation += 1
        self._editor.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._status.setText(t("imports_markdown_edit_saving"))

        def save():
            if not self._current():
                raise markdown_manager.MarkdownImportError(t("imports_markdown_cancelled"))
            return markdown_manager.save_markdown_document(
                addon, profile, cid, filename, text, title=title, expected_revision=revision
            )

        def done(future):
            self._saving = False
            if not self._current():
                return
            try:
                future.result()
            except Exception as exc:
                self._failure(exc)
                return
            self._snapshot.text = text
            self.accept()
            self._on_saved()

        try:
            mw.taskman.run_in_background(save, done, uses_collection=False)
        except Exception as exc:
            self._failure(exc)

    def reject(self):
        if self._saving:
            return
        if self._snapshot and self._editor.toPlainText() != self._snapshot.text:
            answer = QMessageBox.question(
                self,
                t("imports_markdown_discard_title"),
                t("imports_markdown_discard_question"),
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                return
        super().reject()
