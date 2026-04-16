import os
import tempfile

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QApplication,
    QTimer,
    Qt,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QEventLoop, QMarginsF
from PyQt6.QtGui import QPageLayout, QPageSize

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.tag_edit import QuickTagEdit


def render_webpage_to_pdf(
    pdf_path: str,
    *,
    url: str = "",
    html: str = "",
    wait_ms: int = 1200,
) -> None:
    source_url = str(url or "").strip()
    html_text = str(html or "")
    if not source_url and not html_text:
        raise ValueError("Missing webpage source.")

    view = QWebEngineView()
    view.setFixedSize(1280, 960)
    view.hide()

    loop = QEventLoop()
    state: dict[str, object] = {"ok": False, "error": ""}

    def _finish_error(message: str) -> None:
        state["ok"] = False
        state["error"] = message
        loop.quit()

    def _on_pdf_done(_path: str, ok: bool) -> None:
        if not ok:
            _finish_error("Failed to generate PDF.")
            return
        state["ok"] = True
        state["error"] = ""
        loop.quit()

    def _start_print() -> None:
        layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(15, 15, 15, 15),
        )
        try:
            view.page().pdfPrintingFinished.connect(_on_pdf_done)
            view.page().printToPdf(pdf_path, layout)
        except Exception as exc:
            _finish_error(str(exc))

    def _on_load_finished(ok: bool) -> None:
        if not ok:
            _finish_error("Failed to load page.")
            return
        QTimer.singleShot(max(0, int(wait_ms)), _start_print)

    view.loadFinished.connect(_on_load_finished)
    if html_text:
        view.setHtml(html_text, QUrl(source_url or "about:blank"))
    else:
        view.load(QUrl(source_url))
    loop.exec()
    view.deleteLater()

    if not state["ok"]:
        raise RuntimeError(str(state["error"] or "Failed to generate PDF."))


class WebpageToPdfDialog(QDialog):
    """Load a URL in a headless webview and save it as a PDF for import."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Webpage to PDF")
        self.setMinimumWidth(420)

        self._pdf_path: str | None = None
        self._title: str | None = None
        self._source_url: str | None = None
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

        self._tag_edit = QuickTagEdit()
        layout.addWidget(self._tag_edit)

        # Status / progress
        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate spinner
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
        self._status_lbl.setText("Generating PDF…")
        QApplication.processEvents()

        pdf_path = os.path.join(tempfile.gettempdir(), "incremento_webpage.pdf")
        try:
            render_webpage_to_pdf(pdf_path, url=url)
        except Exception as exc:
            self._status_lbl.setText(str(exc))
            self._import_btn.setEnabled(True)
            self._progress.setVisible(False)
            return

        self._pdf_path = pdf_path
        self._title = title
        self._source_url = url
        self.accept()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def pdf_path(self) -> str | None:
        return self._pdf_path

    @property
    def title_text(self) -> str | None:
        return self._title

    @property
    def source_url(self) -> str | None:
        return self._source_url

    @property
    def tags_to_apply(self) -> list[str]:
        return self._tag_edit.tags()
