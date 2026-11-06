"""Offline HTML preview with reversible cleanup in an isolated script world."""

import json
import secrets

from aqt.qt import (QCheckBox, QHBoxLayout, QLabel, QPushButton, QShortcut, QKeySequence,
                    Qt, QTimer, QUrl, QVBoxLayout, QWidget, QWebEnginePage, QWebEngineProfile,
                    QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor, pyqtSignal)
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.webpage_snapshot import offline_snapshot_resource_allowed
    from ..backend.markdown_manager import MAX_SNAPSHOT_HTML_BYTES
    from ..backend.i18n import t
    from .webpage_cleanup import CLEANUP_SCRIPT, install_cleanup_input
except ImportError:
    from backend.webpage_snapshot import offline_snapshot_resource_allowed
    from backend.markdown_manager import MAX_SNAPSHOT_HTML_BYTES
    from backend.i18n import t
    from frontend.webpage_cleanup import CLEANUP_SCRIPT, install_cleanup_input


class _SnapshotRequests(QWebEngineUrlRequestInterceptor):
    document_url = "about:blank"

    def interceptRequest(self, info):
        if not offline_snapshot_resource_allowed(info.requestUrl().toString(), document_url=self.document_url):
            info.block(True)


class _SnapshotPage(QWebEnginePage):
    cleanupChanged = pyqtSignal(int, bool)
    document_url = "about:blank"
    state_prefix = ""

    def acceptNavigationRequest(self, url, _kind, main_frame):
        return bool(main_frame and url.toString() == self.document_url)

    def javaScriptConsoleMessage(self, _level, message, _line, _source):
        # Presentation state only; no collection or file commands cross this seam.
        if (not self.state_prefix or not message.startswith(self.state_prefix)
                or self.url().toString() != self.document_url or len(message) > 256):
            return
        try:
            state = json.loads(message[len(self.state_prefix):])
            if (type(state.get('count')) is int and 0 <= state['count'] <= 1_000_000
                    and type(state.get('enabled')) is bool):
                self.cleanupChanged.emit(state['count'], state['enabled'])
        except (ValueError, TypeError, AttributeError):
            pass


class SnapshotPreview(QWidget):
    loadFinished = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation, self.is_ready, self.removal_count = 0, False, 0
        self._exports = []
        self._editable = True
        self.setAccessibleName(t("imports_preview"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        self.zap_button = QCheckBox(t("imports_webpage_cleanup_zap"))
        self.zap_button.setToolTip(t("imports_webpage_cleanup_help"))
        self.zap_button.toggled.connect(self._toggle_zap)
        controls.addWidget(self.zap_button)
        self.undo_button = QPushButton(t("imports_webpage_cleanup_undo"))
        self.reset_button = QPushButton(t("imports_webpage_cleanup_reset"))
        self.undo_button.clicked.connect(lambda: self._command('undo()'))
        self.reset_button.clicked.connect(lambda: self._command('reset()'))
        controls.addWidget(self.undo_button)
        controls.addWidget(self.reset_button)
        controls.addStretch()
        self._count_label = QLabel()
        self._count_label.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self._count_label)
        layout.addLayout(controls)
        help_label = QLabel(t("imports_webpage_cleanup_help"))
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self._view = QWebEngineView(self)
        self._view.setAccessibleName(t("imports_preview"))
        layout.addWidget(self._view, 1)
        self._profile = QWebEngineProfile(self)
        self._requests = _SnapshotRequests(self._profile)
        self._profile.setUrlRequestInterceptor(self._requests)
        # The view is created before the profile and owns the page, so Qt
        # destroys every page before destroying the profile during teardown.
        self._page = _SnapshotPage(self._profile, self._view)
        self._view.setPage(self._page)
        self._input = install_cleanup_input(self._page, self._view,
            lambda: self.is_ready and self._editable and self.zap_button.isChecked(),
            lambda: self.zap_button.setChecked(False))
        self._page.cleanupChanged.connect(self._cleanup_changed)
        self._view.loadFinished.connect(self._loaded)
        settings = self._page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        self._undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._undo_shortcut.activated.connect(lambda: self._command('undo()'))
        self._escape_shortcut = QShortcut(QKeySequence('Escape'), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._escape_shortcut.activated.connect(lambda: self.zap_button.setChecked(False))
        self._update_controls()

    def page(self):
        return self._page

    def _update_controls(self):
        active = self.is_ready and self._editable
        self.zap_button.setEnabled(active)
        for button in (self.undo_button, self.reset_button):
            button.setEnabled(active and self.removal_count > 0)
        self._undo_shortcut.setEnabled(active and self.removal_count > 0)
        self._escape_shortcut.setEnabled(active and self.zap_button.isChecked())
        self._input.refresh()
        self._count_label.setText(t('imports_webpage_cleanup_count', count=self.removal_count))

    def _cleanup_changed(self, count, enabled):
        self.removal_count = count
        self.zap_button.blockSignals(True)
        self.zap_button.setChecked(enabled)
        self.zap_button.blockSignals(False)
        self._update_controls()

    def _command(self, command):
        if self.is_ready:
            self._page.runJavaScript('globalThis.incrementoCleanup && incrementoCleanup.' + command,
                                    QWebEngineScript.ScriptWorldId.ApplicationWorld)

    def _toggle_zap(self, enabled):
        self._command('setEnabled(' + ('true' if enabled else 'false') + ')')
        self._update_controls()
        if enabled:
            self._view.setFocus()

    def _loaded(self, ok):
        if self._page.url().toString() != self._page.document_url or self._page.document_url == 'about:blank':
            return
        self.is_ready = bool(ok)
        self._update_controls()
        self.loadFinished.emit(bool(ok))

    def load_snapshot(self, path):
        self.clear()
        self._editable = True
        url = QUrl.fromLocalFile(path)
        self._requests.document_url = self._page.document_url = url.toString()
        self._page.state_prefix = 'incremento-zap:' + secrets.token_hex(16) + ':'
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setSourceCode(CLEANUP_SCRIPT + '\n' +
            'incrementoCleanup.setEnabled(false);incrementoCleanup.observe(state => console.info(' +
            json.dumps(self._page.state_prefix) + '+JSON.stringify(state)));')
        self._page.scripts().insert(script)
        self._view.load(url)

    def set_editable(self, enabled):
        self._editable = bool(enabled)
        if not enabled:
            self.zap_button.setChecked(False)
            self._command('finish()')
        self._update_controls()

    def snapshot_html(self, callback):
        if not self.is_ready:
            callback(None)
            return
        generation = self._generation
        timer = QTimer(self)
        timer.setSingleShot(True)
        def done(html):
            if done not in self._exports:
                return
            self._exports.remove(done)
            timer.stop()
            timer.deleteLater()
            valid = (generation == self._generation and self.is_ready and isinstance(html, str)
                     and len(html.encode('utf-8')) <= MAX_SNAPSHOT_HTML_BYTES)
            callback(html if valid else None)
        self._exports.append(done)
        timer.timeout.connect(lambda: done(None))
        timer.start(8000)
        self._page.runJavaScript('globalThis.incrementoCleanup && incrementoCleanup.serialize()',
                                QWebEngineScript.ScriptWorldId.ApplicationWorld, done)

    def clear(self):
        self._generation += 1
        self.is_ready = False
        for done in list(self._exports):
            done(None)
        self._view.stop()
        self._page.scripts().clear()
        self._page.state_prefix = ''
        self._requests.document_url = self._page.document_url = "about:blank"
        self._cleanup_changed(0, False)
        self._view.setUrl(QUrl("about:blank"))
