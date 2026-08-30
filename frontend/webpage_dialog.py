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
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtCore import QUrl, QEventLoop, QMarginsF
from PyQt6.QtGui import QPageLayout, QPageSize

try:
    from ..backend.webpage_snapshot import (
        fetch_webpage_html as _fetch_webpage_html,
        offline_snapshot_resource_allowed as _offline_snapshot_resource_allowed,
    )
    from ..backend.network_safety import validate_public_http_url
    from .tag_edit import QuickTagEdit
except ImportError:
    from webpage_snapshot import (  # type: ignore
        fetch_webpage_html as _fetch_webpage_html,
        offline_snapshot_resource_allowed as _offline_snapshot_resource_allowed,
    )
    from network_safety import validate_public_http_url  # type: ignore
    from incremento.frontend.tag_edit import QuickTagEdit


class _SnapshotRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Keep captured HTML fully offline after its guarded server-side fetch."""

    def __init__(self, source_url: str, parent=None):
        super().__init__(parent)
        self._source_url = str(source_url or "")

    def interceptRequest(self, info) -> None:  # noqa: N802 - Qt API name
        try:
            candidate = info.requestUrl().toString()
        except Exception:
            info.block(True)
            return
        if not _offline_snapshot_resource_allowed(candidate):
            info.block(True)

def _disable_unneeded_web_capabilities(settings, *, allow_javascript: bool) -> None:
    values = {
        "JavascriptEnabled": bool(allow_javascript),
        "JavascriptCanOpenWindows": False,
        "JavascriptCanAccessClipboard": False,
        "JavascriptCanPaste": False,
        "LocalContentCanAccessFileUrls": False,
        "LocalContentCanAccessRemoteUrls": False,
        "PluginsEnabled": False,
        "FullScreenSupportEnabled": False,
        "ScreenCaptureEnabled": False,
        "HyperlinkAuditingEnabled": False,
    }
    for name, enabled in values.items():
        attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
        if attribute is not None:
            settings.setAttribute(attribute, enabled)


def render_webpage_to_pdf(
    pdf_path: str,
    *,
    url: str = "",
    html: str = "",
    wait_ms: int = 1200,
    timeout_ms: int = 45000,
) -> None:
    source_url = str(url or "").strip()
    html_text = str(html or "")
    if not source_url and not html_text:
        raise ValueError("Missing webpage source.")
    if source_url:
        source_url = validate_public_http_url(source_url)
    if not html_text:
        source_url, html_text = _fetch_webpage_html(
            source_url,
            timeout_sec=max(1.0, float(timeout_ms) / 1000.0),
        )

    view = QWebEngineView()
    view.setFixedSize(1280, 960)
    view.hide()
    profile = QWebEngineProfile(view)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    page = QWebEnginePage(profile, view)
    view.setPage(page)
    _disable_unneeded_web_capabilities(
        page.settings(),
        allow_javascript=False,
    )
    interceptor = _SnapshotRequestInterceptor(source_url, profile)
    profile.setUrlRequestInterceptor(interceptor)
    # Keep the isolated profile and interceptor alive until asynchronous printing ends.
    view._incremento_profile = profile
    view._incremento_interceptor = interceptor

    loop = QEventLoop()
    state: dict[str, object] = {"ok": False, "error": "", "done": False}

    def _finish(ok: bool, message: str = "") -> None:
        if state.get("done"):
            return
        state["done"] = True
        state["ok"] = bool(ok)
        state["error"] = str(message or "")
        loop.quit()

    def _finish_error(message: str) -> None:
        _finish(False, message)

    def _on_pdf_done(_path: str, ok: bool) -> None:
        if not ok:
            _finish_error("Failed to generate PDF.")
            return
        _finish(True)

    def _start_print() -> None:
        if state.get("done"):
            return
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
        if state.get("done"):
            return
        if not ok:
            _finish_error("Failed to load page.")
            return
        QTimer.singleShot(max(0, int(wait_ms)), _start_print)

    def _on_timeout() -> None:
        seconds = max(1, int(timeout_ms) // 1000)
        _finish_error(f"Timed out generating PDF after {seconds} seconds.")

    view.loadFinished.connect(_on_load_finished)
    QTimer.singleShot(max(1000, int(timeout_ms)), _on_timeout)
    view.setHtml(html_text, QUrl(source_url or "about:blank"))
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

        with tempfile.NamedTemporaryFile(
            prefix="incremento-webpage-",
            suffix=".pdf",
            delete=False,
        ) as temporary:
            pdf_path = temporary.name
        try:
            render_webpage_to_pdf(pdf_path, url=url)
        except Exception as exc:
            try:
                os.remove(pdf_path)
            except OSError:
                pass
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
