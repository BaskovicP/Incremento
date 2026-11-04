"""Non-modal webpage capture with an inert preview and journaled EPUB import."""

import threading
from types import SimpleNamespace

from aqt import mw
from aqt.qt import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                    QPushButton, QSizePolicy, QStackedWidget, Qt, QVBoxLayout)

try:
    from ..backend import paths, epub_manager
    from ..backend.webpage_document import prepare_webpage_document
    from ..backend.note_metadata import build_incremento_metadata
    from ..backend.priority_manager import set_priority
    from ..backend.i18n import t
    from .markdown_document_dialog import MarkdownPreview
    from .tag_edit import QuickTagEdit
except ImportError:
    from backend import paths, epub_manager
    from backend.webpage_document import prepare_webpage_document
    from backend.note_metadata import build_incremento_metadata
    from backend.priority_manager import set_priority
    from backend.i18n import t
    from frontend.markdown_document_dialog import MarkdownPreview
    from frontend.tag_edit import QuickTagEdit


class WebpageDocumentDialog(QDialog):
    def __init__(self, addon_dir, deck_names, parent=None, *, on_open=None):
        super().__init__(parent)
        self._addon_dir, self._profile, self._collection = addon_dir, paths.get_active_profile(), mw.col
        self._closed = self._busy = self._saving = False
        self._generation, self._prepared = 0, None
        self._cancel = threading.Event()
        self.created_card_id = None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t("imports_webpage_document"))
        self.resize(820, 760)
        self.finished.connect(self._finished)
        layout = QVBoxLayout(self)
        description = QLabel(t("imports_webpage_document_description"))
        description.setWordWrap(True)
        description.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(description)
        form = QFormLayout()
        self._url_edit, self._title_edit = QLineEdit(), QLineEdit()
        self._url_edit.setPlaceholderText(t("imports_webpage_url_placeholder"))
        self._title_edit.setPlaceholderText(t("imports_article_title"))
        self._scope = QComboBox()
        self._scope.addItem(t("imports_webpage_main_content"), "main")
        self._scope.addItem(t("imports_webpage_entire_page"), "full")
        self._format = QComboBox()
        self._format.addItem(t("imports_webpage_html_snapshot"), "html")
        self._format.addItem(t("imports_webpage_reading_copy"), "markdown")
        self._scope.setCurrentIndex(self._scope.findData("full"))
        self._scope.setEnabled(False)
        self._deck = QComboBox()
        self._deck.addItems(deck_names or ["Topics"])
        index = self._deck.findText("Topics")
        if index >= 0:
            self._deck.setCurrentIndex(index)
        self._tags = QuickTagEdit(compact=True)
        self._priority = QDoubleSpinBox()
        self._priority.setRange(0, 100)
        self._priority.setValue(50)
        self._priority.setDecimals(4)
        for label, control in (("imports_url_label", self._url_edit), ("imports_title_label", self._title_edit),
                               ("imports_webpage_save_as", self._format),
                               ("imports_webpage_scope", self._scope), ("imports_deck_label", self._deck),
                               ("imports_table_tags", self._tags), ("imports_table_priority", self._priority)):
            control.setAccessibleName(t(label))
            form.addRow(t(label), control)
        layout.addLayout(form)
        self._url_edit.textChanged.connect(self._invalidate)
        self._title_edit.textChanged.connect(self._invalidate)
        self._scope.currentIndexChanged.connect(self._invalidate)
        self._format.currentIndexChanged.connect(self._format_changed)
        self._preview = MarkdownPreview(self)
        self._preview_stack = QStackedWidget(self)
        self._preview_stack.addWidget(self._preview)
        self._snapshot_preview = None
        layout.addWidget(self._preview_stack, 1)
        self._status = QLabel("")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._status)
        buttons = QHBoxLayout()
        self._capture_btn = QPushButton(t("imports_webpage_capture_preview"))
        self._save_btn = QPushButton(t("imports_markdown_save"))
        self._save_btn.setEnabled(False)
        self._open_btn = QPushButton(t("imports_webpage_open_document"))
        self._open_btn.hide()
        self._open_btn.clicked.connect(lambda: on_open(self.created_card_id)
            if self._current() and on_open and self.created_card_id else None)
        self._close_btn = QPushButton(t("imports_close"))
        self._capture_btn.clicked.connect(self._capture)
        self._save_btn.clicked.connect(self._save)
        self._close_btn.clicked.connect(self.reject)
        for button in (self._capture_btn, self._save_btn, self._open_btn, self._close_btn):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _current(self):
        return not self._closed and paths.get_active_profile() == self._profile and mw.col is self._collection

    def _invalidate(self, *_args):
        self._generation += 1
        self._cancel.set()
        if self._snapshot_preview is not None:
            self._snapshot_preview.clear()
        if self._prepared is not None:
            self._prepared.close()
            self._prepared = None
        self._save_btn.setEnabled(False)

    def _format_changed(self, *_args):
        self._invalidate()
        self._scope.setCurrentIndex(self._scope.findData("full" if self._format.currentData() == "html" else "main"))
        self._scope.setEnabled(not self._busy and self._format.currentData() == "markdown")

    def _finished(self, _result):
        self._closed = True
        self._invalidate()

    def reject(self):
        if not self._saving:
            super().reject()

    def _set_busy(self, busy):
        self._busy = busy
        for control in (self._url_edit, self._title_edit, self._format, self._deck, self._tags, self._priority, self._capture_btn):
            control.setEnabled(not busy)
        self._scope.setEnabled(not busy and self._format.currentData() == "markdown")
        self._save_btn.setEnabled(not busy and self._prepared is not None)
        self._close_btn.setEnabled(not self._saving)

    def _capture(self):
        if self._busy or not self._current():
            return
        self._invalidate()
        self._cancel = cancel = threading.Event()
        generation = self._generation
        url, title, scope = self._url_edit.text().strip(), self._title_edit.text().strip(), self._scope.currentData()
        capture_format = self._format.currentData()
        self._set_busy(True)
        self._open_btn.hide()
        self._preview.clear()
        self._status.setText(t("imports_webpage_capturing"))

        def done(future):
            try:
                prepared = future.result()
            except Exception as exc:
                if self._current() and generation == self._generation:
                    self._set_busy(False)
                    self._status.setText(t("imports_webpage_document_failed",
                        error=str(exc) or t("imports_webpage_browser_capture_required")))
                return
            if not self._current() or generation != self._generation:
                prepared.close()
                return
            self._prepared = prepared
            if prepared.preview_path:
                if self._snapshot_preview is None:
                    from .webpage_snapshot_preview import SnapshotPreview
                    self._snapshot_preview = SnapshotPreview(self)
                    self._preview_stack.addWidget(self._snapshot_preview)
                self._snapshot_preview.load_snapshot(prepared.preview_path)
                self._preview_stack.setCurrentWidget(self._snapshot_preview)
            else:
                self._preview.setHtml(prepared.preview)
                self._preview_stack.setCurrentWidget(self._preview)
            self._set_busy(False)
            key = "imports_webpage_snapshot_ready" if prepared.preview_path else "imports_webpage_capture_ready"
            self._status.setText(t(key, count=prepared.capture["omitted_images"]))

        try:
            mw.taskman.run_in_background(lambda: prepare_webpage_document(url, title=title, content_scope=scope,
                capture_format=capture_format, is_cancelled=cancel.is_set), done, uses_collection=False)
        except Exception as exc:
            self._set_busy(False)
            self._status.setText(t("imports_webpage_document_failed", error=str(exc)))

    def _save(self):
        if self._busy or self._prepared is None or not self._current():
            return
        from aqt.operations import CollectionOp
        prepared, self._prepared = self._prepared, None
        addon, profile, collection = self._addon_dir, self._profile, self._collection
        deck, tags, priority = self._deck.currentText(), self._tags.tags(), self._priority.value()
        self._saving = True
        self._set_busy(True)
        self._status.setText(t("imports_markdown_edit_saving"))

        def operation(col):
            if col is not collection or paths.get_active_profile() != profile or self._cancel.is_set():
                raise RuntimeError(t("imports_markdown_cancelled"))
            step = col.add_custom_undo_entry(t("imports_webpage_document"))
            source_type = "HTML" if prepared.capture.get("format") == "html" else "Markdown"
            cid = epub_manager.add_epub_card(addon, col, prepared.path, prepared.title, deck_name=deck, tags=tags,
                profile=profile, source_type=source_type, source_metadata=build_incremento_metadata(
                    source_type=source_type, source_title=prepared.title, source_link=prepared.capture["url"],
                    imported_at=prepared.capture["captured_at"]))
            set_priority(addon, profile, cid, priority)
            return SimpleNamespace(card_id=cid, changes=col.merge_undo_entries(step))

        def failure(error):
            prepared.close()
            self._saving = False
            if self._current():
                self._set_busy(False)
                self._status.setText(t("imports_markdown_failed", error=str(error)))

        def success(result):
            prepared.close()
            self._saving = False
            if self._current():
                self.created_card_id = result.card_id
                self._set_busy(False)
                self._open_btn.show()
                self._status.setText(t("imports_webpage_document_saved", title=prepared.title))

        try:
            CollectionOp(self, operation).success(success).failure(failure).run_in_background()
        except Exception as exc:
            failure(exc)
