"""Selected-text web search, with optional isolated persistent website storage."""

from aqt.qt import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, Qt, QUrl
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.content_safety import normalize_external_http_url
    from ..backend.i18n import t
except ImportError:
    from backend.content_safety import normalize_external_http_url
    from backend.i18n import t

from .file_shell import open_companion_url
from .browser_profiles import create_browser_profile, destroy_browser


def _http_url(url) -> bool:
    try:
        # The default display form decodes %20 into spaces, causing valid
        # search-result requests and links to fail the whitespace check.
        normalize_external_http_url(url.toString(QUrl.ComponentFormattingOption.FullyEncoded))
        return True
    except (TypeError, ValueError):
        return False


class _SearchRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info) -> None:  # noqa: N802 - Qt API
        scheme = info.requestUrl().scheme().casefold()
        # Embedded data/blob resources cannot access local files or Anki's bridge.
        if scheme not in {"data", "blob"} and not _http_url(info.requestUrl()):
            info.block(True)


class _SearchPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, _navigation_type, _is_main_frame) -> bool:  # noqa: N802
        return _http_url(url)

    def createWindow(self, _window_type):  # noqa: N802
        # User-clicked result links with target=_blank stay in this small window.
        return self

    def chooseFiles(self, _mode, _old_files, _accepted_types):  # noqa: N802
        return []


class GoogleSearchDialog(QDialog):
    def __init__(self, parent=None, *, anki_profile, addon_dir=None, remember_logins=False):
        super().__init__(parent)
        self.anki_profile = anki_profile
        # Keep a remembered browser alive when hidden so rapidly reopening it
        # cannot create two profiles writing to the same Chromium database.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, not remember_logins)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowTitle(t("selection_search_title"))
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self._back = QPushButton(t("reader_back"))
        toolbar.addWidget(self._back)
        external = QPushButton(t("reader_open_in_browser"))
        toolbar.addWidget(external)
        toolbar.addStretch(1)
        close = QPushButton(t("common_close"))
        toolbar.addWidget(close)
        layout.addLayout(toolbar)

        self._view = QWebEngineView(self)
        self._view.setAccessibleName(t("selection_search_results"))
        # Search never shares cookies or the reader's bridge with the Web dock.
        self._profile = (create_browser_profile(addon_dir, anki_profile, search=True)
                         if remember_logins else QWebEngineProfile())
        # The view was added first and owns the page. Parenting the profile after
        # it also guarantees ordered cleanup if the originating editor closes.
        self._profile.setParent(self)
        self._profile.downloadRequested.connect(lambda download: download.cancel())
        self._requests = _SearchRequests(self._profile)
        self._profile.setUrlRequestInterceptor(self._requests)
        self._page = _SearchPage(self._profile, self._view)
        self._view.setPage(self._page)
        for name in (
            "JavascriptCanOpenWindows", "JavascriptCanAccessClipboard", "JavascriptCanPaste",
            "LocalContentCanAccessFileUrls", "LocalContentCanAccessRemoteUrls",
            "PluginsEnabled", "FullScreenSupportEnabled", "ScreenCaptureEnabled",
            "HyperlinkAuditingEnabled", "AllowWindowActivationFromJavaScript", "NavigateOnDropEnabled",
        ):
            attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
            if attribute is not None:
                self._page.settings().setAttribute(attribute, False)
        if hasattr(self._page, "permissionRequested"):
            self._page.permissionRequested.connect(lambda permission: permission.deny())
        else:
            self._page.featurePermissionRequested.connect(
                lambda origin, feature: self._page.setFeaturePermission(
                    origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
                )
            )
        if hasattr(self._page, "fileSystemAccessRequested"):
            self._page.fileSystemAccessRequested.connect(lambda request: request.reject())
        layout.addWidget(self._view, 1)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._status)
        self._view.loadStarted.connect(lambda: self._status.setText(t("selection_search_loading")))
        self._view.loadFinished.connect(self._loaded)
        self._view.urlChanged.connect(self._update_back)
        self._back.clicked.connect(self._view.back)
        self._back.setEnabled(False)
        external.clicked.connect(self._open_browser)
        close.clicked.connect(self.close)
        # Prevent Enter in the web view from activating a dialog button.
        for button in (self._back, external, close):
            button.setAutoDefault(False)

    def search(self, url: str) -> None:
        if _http_url(QUrl(url)):
            self._view.load(QUrl(url))

    def _update_back(self, *_args) -> None:
        self._back.setEnabled(self._view.history().canGoBack())

    def _loaded(self, ok: bool) -> None:
        self._status.setText("" if ok else t("selection_search_failed"))
        self._update_back()

    def _open_browser(self) -> None:
        url = self._view.url()
        if _http_url(url):
            open_companion_url(url.toString(QUrl.ComponentFormattingOption.FullyEncoded))

    def done(self, result: int) -> None:
        self._view.stop()
        super().done(result)

    def dispose(self) -> None:
        destroy_browser(self, self._profile)
