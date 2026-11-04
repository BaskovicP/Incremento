"""Read-only HTML snapshot preview; no page scripts or remote/local resources."""

from aqt.qt import QUrl, QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.webpage_snapshot import offline_snapshot_resource_allowed
    from ..backend.i18n import t
except ImportError:
    from backend.webpage_snapshot import offline_snapshot_resource_allowed
    from backend.i18n import t


class _SnapshotRequests(QWebEngineUrlRequestInterceptor):
    document_url = "about:blank"

    def interceptRequest(self, info):
        if not offline_snapshot_resource_allowed(info.requestUrl().toString(), document_url=self.document_url):
            info.block(True)


class _SnapshotPage(QWebEnginePage):
    document_url = "about:blank"

    def acceptNavigationRequest(self, url, _kind, main_frame):
        return bool(main_frame and url.toString() == self.document_url)


class SnapshotPreview(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName(t("imports_preview"))
        self._profile = QWebEngineProfile(self)
        self._requests = _SnapshotRequests(self._profile)
        self._profile.setUrlRequestInterceptor(self._requests)
        self._page = _SnapshotPage(self._profile, self)
        self.setPage(self._page)
        settings = self._page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)

    def load_snapshot(self, path):
        self.stop()
        url = QUrl.fromLocalFile(path)
        self._requests.document_url = self._page.document_url = url.toString()
        self.load(url)

    def clear(self):
        self.stop()
        self._requests.document_url = self._page.document_url = "about:blank"
        self.setUrl(QUrl("about:blank"))
