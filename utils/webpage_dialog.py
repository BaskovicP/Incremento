import os
import tempfile

from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QApplication, Qt,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QEventLoop, QMarginsF
from PyQt6.QtGui import QPageLayout, QPageSize


class WebpageToPdfDialog(QDialog):
    """Load a URL in a headless webview and save it as a PDF for import."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Webpage to PDF")
        self.setMinimumWidth(420)

        self._pdf_path: str | None = None
        self._title: str | None = None
        self._view: QWebEngineView | None = None  # keep reference alive during async

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # URL
        layout.addWidget(QLabel("URL:"))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://example.com/article")
        layout.addWidget(self._url_edit)

        # Title
        layout.addWidget(QLabel("Card title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Article title")
        layout.addWidget(self._title_edit)

        # Status / progress
        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate spinner
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        self._import_btn = QPushButton("Import")
        self._import_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._import_btn.clicked.connect(self._on_import)
        cancel_btn.clicked.connect(self.reject)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_import(self):
        url = self._url_edit.text().strip()
        if not url:
            self._status_lbl.setText("Please enter a URL.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        title = self._title_edit.text().strip() or url

        self._import_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status_lbl.setText("Loading page…")
        QApplication.processEvents()

        pdf_path = os.path.join(tempfile.gettempdir(), "incremento_webpage.pdf")

        # Hidden webview — must be sized so Qt renders the page properly
        view = QWebEngineView()
        view.setFixedSize(1280, 960)
        view.hide()
        self._view = view   # prevent garbage collection during async chain

        loop = QEventLoop()

        def on_pdf_done(path: str, ok: bool):
            loop.quit()
            self._view = None
            if ok:
                self._pdf_path = path
                self._title = title
                self.accept()
            else:
                self._status_lbl.setText("Failed to generate PDF.")
                self._import_btn.setEnabled(True)
                self._progress.setVisible(False)

        def on_load_finished(ok: bool):
            if not ok:
                loop.quit()
                self._view = None
                self._status_lbl.setText("Failed to load page.")
                self._import_btn.setEnabled(True)
                self._progress.setVisible(False)
                return
            self._status_lbl.setText("Generating PDF…")
            QApplication.processEvents()
            layout = QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Portrait,
                QMarginsF(15, 15, 15, 15),
            )
            view.page().pdfPrintingFinished.connect(on_pdf_done)
            view.page().printToPdf(pdf_path, layout)

        view.loadFinished.connect(on_load_finished)
        view.load(QUrl(url))
        loop.exec()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def pdf_path(self) -> str | None:
        return self._pdf_path

    @property
    def title_text(self) -> str | None:
        return self._title
