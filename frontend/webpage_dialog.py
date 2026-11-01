import os
import tempfile
import time
import threading
from collections.abc import Callable
from urllib.error import HTTPError

from PyQt6 import sip
try:
    from .file_shell import open_companion_url
except ImportError:
    from file_shell import open_companion_url
from aqt.qt import (
    QDialog,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QComboBox,
    QCheckBox,
    QApplication,
    QTimer,
    Qt,
)
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
        copy_browser_saved_pdf,
        fetch_webpage_html as _fetch_webpage_html,
        fetch_wikipedia_article_pdf as _fetch_wikipedia_article_pdf,
        offline_snapshot_resource_allowed as _offline_snapshot_resource_allowed,
    )
    from ..backend.network_safety import validate_public_http_url
    from ..backend.content_safety import normalize_external_http_url
    from ..backend.webpage_resources import build_offline_webpage_html
    from ..backend.webpage_export import prepare_export_html
    from ..backend.webpage_browser import browser_runtime, install_browser_runtime, render_browser_pdf, capture_browser_html
    from ..backend.webpage_handoff import HANDOFF_PATH, browser_pdf_handoffs, WebpageVerificationRequired, requires_verification
    from ..backend.paths import get_active_profile as _active_profile
    from .tag_edit import QuickTagEdit
except ImportError:
    from webpage_snapshot import (  # type: ignore
        copy_browser_saved_pdf,
        fetch_webpage_html as _fetch_webpage_html,
        fetch_wikipedia_article_pdf as _fetch_wikipedia_article_pdf,
        offline_snapshot_resource_allowed as _offline_snapshot_resource_allowed,
    )
    from network_safety import validate_public_http_url  # type: ignore
    from content_safety import normalize_external_http_url
    from webpage_resources import build_offline_webpage_html
    from webpage_export import prepare_export_html
    from webpage_browser import browser_runtime, install_browser_runtime, render_browser_pdf, capture_browser_html
    from webpage_handoff import HANDOFF_PATH, browser_pdf_handoffs, WebpageVerificationRequired, requires_verification
    from paths import get_active_profile as _active_profile
    from incremento.frontend.tag_edit import QuickTagEdit


try:
    from ..backend.i18n import t as _t
except ImportError:
    from backend.i18n import t as _t


class _SnapshotRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Keep captured HTML fully offline after its guarded server-side fetch."""

    def __init__(self, document_url: str, parent=None):
        super().__init__(parent)
        self._document_url = document_url

    def interceptRequest(self, info) -> None:  # noqa: N802 - Qt API name
        try:
            candidate = info.requestUrl().toString()
        except Exception:
            info.block(True)
            return
        if not _offline_snapshot_resource_allowed(candidate, document_url=self._document_url):
            info.block(True)


class _SnapshotPage(QWebEnginePage):
    def __init__(self, profile, parent, document_url: str):
        super().__init__(profile, parent)
        self._document_url = document_url

    def acceptNavigationRequest(self, url, _navigation_type, is_main_frame):  # noqa: N802 - Qt API
        return bool(is_main_frame and url.toString() == self._document_url)


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


def _prepare_webpage(source_url: str, html_text: str, timeout_sec: float,
                     style: str = "print", dynamic: bool = False, include_links: bool = False,
                     cancel_event=None, prefer_snapshot: bool = False, capture_html: bool = False) -> tuple[str, bytes | None]:
    if style not in {"print", "website", "article"}:
        raise ValueError(_t("imports_webpage_invalid_style"))
    if prefer_snapshot:
        if not html_text.strip():
            raise ValueError(_t("imports_webpage_missing_source"))
        dynamic = False
    deadline = time.monotonic() + timeout_sec
    if source_url:
        # A browser snapshot already supplies the document. Its URL is only
        # provenance and a resource base; the downloader validates each actual
        # resource request independently before connecting.
        source_url = (normalize_external_http_url(source_url) if prefer_snapshot
                      else validate_public_http_url(source_url))
        if not prefer_snapshot and style == "print" and not include_links:
            try:
                wikipedia_pdf = _fetch_wikipedia_article_pdf(source_url, timeout_sec=max(1.0, deadline - time.monotonic()))
            except Exception:
                wikipedia_pdf = None
            if wikipedia_pdf is not None:
                return "", wikipedia_pdf
    if dynamic:
        try:
            if capture_html:
                source_url, html_text = capture_browser_html(source_url, html_text, timeout_sec=max(1.0, deadline-time.monotonic()),
                                                            cancel_event=cancel_event)
            else:
                return "", render_browser_pdf(source_url, html_text, style=style, include_links=include_links,
                                               links_heading=_t("imports_webpage_links_heading"), timeout_sec=max(1.0, deadline-time.monotonic()), cancel_event=cancel_event)
        except InterruptedError:
            raise RuntimeError(_t("imports_webpage_cancelled")) from None
        except TimeoutError:
            raise RuntimeError(_t("imports_webpage_pdf_timeout", seconds=max(1, int(timeout_sec)))) from None
        except WebpageVerificationRequired:
            raise
        except RuntimeError:
            raise RuntimeError(_t("imports_webpage_browser_capture_failed")) from None
    if not html_text:
        source_url, html_text = _fetch_webpage_html(
            source_url,
            timeout_sec=max(1.0, deadline - time.monotonic()),
        )
    if requires_verification(html_text):
        raise WebpageVerificationRequired()
    html_text = prepare_export_html(html_text, source_url, style=style, include_links=include_links,
                                    links_heading=_t("imports_webpage_links_heading"))
    return build_offline_webpage_html(
        # Leave time for the final in-memory HTML expansion and Qt callback.
        html_text, source_url, timeout_sec=max(0.0, deadline - time.monotonic() - 3.0)
    ), None


def _prepare_in_background(source_url: str, html_text: str, timeout_ms: int,
                           style: str = "print", dynamic: bool = False, include_links: bool = False,
                           cancel_event=None, prefer_snapshot: bool = False, capture_html: bool = False) -> tuple[str, bytes | None]:
    """Retain the synchronous bridge API while leaving Qt responsive to cancellation."""
    from aqt import mw

    cancel_event = cancel_event or threading.Event()
    loop = QEventLoop()
    captured_profile = _active_profile()
    state = {"done": False, "value": None, "error": None}

    def complete(future):
        if state["done"]:
            return
        state["done"] = True
        try:
            state["value"] = future.result()
        except Exception as exc:
            state["error"] = exc
        loop.quit()

    def expired():
        if state["done"]:
            return
        state["done"] = True
        cancel_event.set()
        state["error"] = RuntimeError(_t("imports_webpage_pdf_timeout", seconds=max(1, timeout_ms // 1000)))
        loop.quit()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(expired)
    timer.start(max(1000, timeout_ms))
    cancelled = QTimer()
    def check_cancelled():
        switched = _active_profile() != captured_profile
        if switched and cancel_event is not None:
            cancel_event.set()
        if (switched or (cancel_event is not None and cancel_event.is_set())) and not state["done"]:
            state["done"] = True
            state["error"] = RuntimeError(_t("imports_topic_profile_changed") if switched else _t("imports_webpage_cancelled"))
            loop.quit()
    cancelled.timeout.connect(check_cancelled)
    cancelled.start(100)
    try:
        mw.taskman.run_in_background(
            lambda: _prepare_webpage(source_url, html_text, max(1.0, timeout_ms / 1000.0), style, dynamic, include_links, cancel_event, prefer_snapshot, capture_html),
            complete,
            uses_collection=False,
        )
        if not state["done"]:
            loop.exec()
    finally:
        timer.stop()
        cancelled.stop()
    if state["error"] is not None:
        raise state["error"]
    return state["value"]


def render_webpage_to_pdf(
    pdf_path: str,
    *,
    url: str = "",
    html: str = "",
    wait_ms: int = 1200,
    timeout_ms: int = 45000,
    style: str = "print",
    dynamic: bool = False,
    include_links: bool = False,
    cancel_event=None,
    prefer_snapshot: bool = False,
    edit_before_save: bool = False,
) -> None:
    source_url = str(url or "").strip()
    html_text = str(html or "")
    if not source_url and not html_text:
        raise ValueError(_t("imports_webpage_missing_source"))
    profile = _active_profile()
    edit_before_save = bool(edit_before_save and style == "website")
    html_text, wikipedia_pdf = _prepare_in_background(source_url, html_text, timeout_ms, style, dynamic, include_links, cancel_event, prefer_snapshot, edit_before_save)
    if _active_profile() != profile:
        raise RuntimeError(_t("imports_topic_profile_changed"))
    if wikipedia_pdf is not None:
        with open(pdf_path, "wb") as output:
            output.write(wikipedia_pdf)
        return

    # Embedded photos can exceed Qt's 2 MiB setHtml/data-URL limit. Load only
    # this private temporary document; every other file/network request is denied.
    snapshot_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            prefix="incremento-snapshot-", suffix=".html", mode="w", encoding="utf-8", delete=False,
        ) as snapshot:
            snapshot_path = snapshot.name
            snapshot.write(html_text)
        options = {"edit_before_save": True, "cancel_event": cancel_event} if edit_before_save else {}
        _print_offline_snapshot(pdf_path, snapshot_path, wait_ms=wait_ms, timeout_ms=timeout_ms, screen_media=style == "website", **options)
    finally:
        try:
            os.remove(snapshot_path)
        except OSError:
            pass
    if _active_profile() != profile:
        raise RuntimeError(_t("imports_topic_profile_changed"))


def _print_offline_snapshot(pdf_path: str, snapshot_path: str, *, wait_ms: int, timeout_ms: int, screen_media: bool = False,
                            edit_before_save: bool = False, cancel_event=None) -> None:
    document_url = QUrl.fromLocalFile(os.path.realpath(snapshot_path)).toString()

    profile = QWebEngineProfile()
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    page = _SnapshotPage(profile, None, document_url)
    _disable_unneeded_web_capabilities(
        page.settings(),
        allow_javascript=False,
    )
    interceptor = _SnapshotRequestInterceptor(document_url, profile)
    profile.setUrlRequestInterceptor(interceptor)
    preview = None
    if edit_before_save:
        from PyQt6.QtWebEngineCore import QWebEngineScript
        from .webpage_cleanup import CLEANUP_SCRIPT, create_cleanup_preview
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setSourceCode(CLEANUP_SCRIPT)
        page.scripts().insert(script)
        preview = create_cleanup_preview(page, QApplication.activeWindow())
    if screen_media:
        # Emulate screen CSS without executing any script from the webpage.
        from PyQt6.QtWebEngineCore import QWebEngineScript
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setSourceCode("""(() => {
          const rewrite = rules => { for (const rule of rules) {
            if (rule.media) { let text = rule.media.mediaText;
              text = text.replace(/\\bprint\\b/gi, 'not all').replace(/\\bscreen\\b/gi, 'all');
              rule.media.mediaText = text; }
            if (rule.cssRules) rewrite(rule.cssRules);
          }};
          for (const sheet of document.styleSheets) { try { rewrite(sheet.cssRules); } catch (_) {} }
        })();""")
        page.scripts().insert(script)
    # The isolated page/profile stay alive here until asynchronous printing ends.

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
            _finish_error(_t("imports_webpage_pdf_failed"))
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
            page.pdfPrintingFinished.connect(_on_pdf_done)
            page.printToPdf(pdf_path, layout)
        except Exception as exc:
            _finish_error(str(exc))

    def _on_load_finished(ok: bool) -> None:
        if state.get("done"):
            return
        if not ok:
            _finish_error(_t("imports_webpage_load_failed"))
            return
        # Qt can signal loadFinished before its native PDF frame is ready.
        # Preserve the normal settling period even for a caller requesting zero.
        QTimer.singleShot(max(1200, int(wait_ms)), _ready)

    def _ready() -> None:
        if state.get("done"):
            return
        if preview is None:
            _start_print()
        else:
            # The capture deadline must not limit the user's editing time.
            timeout.stop()
            preview.show()

    def _save_preview() -> None:
        if state.get("done") or state.get("saving"):
            return
        state["saving"] = True
        # Keep the native view attached and visible until printToPdf completes.
        # Hiding it with QDialog.accept() can invalidate Qt's print frame.
        preview.setEnabled(False)
        timeout.start(max(1000, int(timeout_ms)))
        page.runJavaScript("globalThis.incrementoCleanup && incrementoCleanup.finish()",
                           QWebEngineScript.ScriptWorldId.ApplicationWorld, lambda _result: _start_print())

    captured_profile = _active_profile() if edit_before_save else None
    def _check_cancelled() -> None:
        if _active_profile() != captured_profile:
            _finish_error(_t("imports_topic_profile_changed"))
        elif cancel_event is not None and cancel_event.is_set():
            _finish_error(_t("imports_webpage_cancelled"))

    cancellation = QTimer(page)
    if preview is not None:
        preview.save_button.clicked.connect(_save_preview)
        preview.rejected.connect(lambda: _finish_error(_t("imports_webpage_cancelled")))
        cancellation.timeout.connect(_check_cancelled)
        cancellation.start(100)

    def _on_timeout() -> None:
        seconds = max(1, int(timeout_ms) // 1000)
        _finish_error(_t("imports_webpage_pdf_timeout", seconds=seconds))

    page.loadFinished.connect(_on_load_finished)
    timeout = QTimer(page)
    timeout.setSingleShot(True)
    timeout.timeout.connect(_on_timeout)
    timeout.start(max(1000, int(timeout_ms)))
    try:
        page.load(QUrl(document_url))
        loop.exec()
    finally:
        state["done"] = True
        timeout.stop()
        cancellation.stop()
        # Qt requires every page to be destroyed before its profile.
        if preview is not None:
            sip.delete(preview)
        sip.delete(page)
        sip.delete(profile)

    if not state["ok"]:
        raise RuntimeError(str(state["error"] or _t("imports_webpage_pdf_failed")))


class WebpagePdfResultDialog(QDialog):
    """Offer the saved PDF without blocking Anki or opening it automatically."""

    def __init__(self, parent, title: str, profile: str, open_pdf: Callable[[], None]):
        super().__init__(parent)
        self.setWindowTitle(_t("imports_webpage_to_pdf"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(420)
        self._profile = profile
        self._open_pdf = open_pdf

        layout = QVBoxLayout(self)
        message = QLabel(_t("root_webpage_pdf_added", title=title))
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        message.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(message)
        self._status_lbl = QLabel("")
        self._status_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._status_lbl)

        buttons = QHBoxLayout()
        buttons.addStretch()
        open_button = QPushButton(_t("knowledge_tree_open_pdf"))
        open_button.clicked.connect(self._on_open)
        buttons.addWidget(open_button)
        close_button = QPushButton(_t("reader_close"))
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _on_open(self) -> None:
        if _active_profile() != self._profile:
            self.reject()
            return
        try:
            self._open_pdf()
        except Exception as exc:
            self._status_lbl.setText(_t("root_document_open_failed", error=exc))
            return
        self.accept()


class WebpageToPdfDialog(QDialog):
    """Capture a public URL as an offline PDF for import."""

    def __init__(self, parent=None, *, addon_dir: str):
        super().__init__(parent)
        self.setWindowTitle(_t("imports_webpage_to_pdf"))
        self.setMinimumWidth(760)
        self._profile = _active_profile()
        self._document_details = None

        self._pdf_path: str | None = None
        self._title: str | None = None
        self._source_url: str | None = None
        self._import_generation = 0
        self._capture_cancel = threading.Event()
        self._handoff_ticket = None
        self._handoff_timer = None
        self._browser_handoff_completed = False

        content = QHBoxLayout(self)
        layout = QVBoxLayout()
        content.addLayout(layout, 1)
        layout.setSpacing(8)
        from .document_details import BookDetailsEditor
        self._book_details = BookDetailsEditor(addon_dir, self._profile, self)
        self._book_details.setMinimumWidth(270)
        content.addWidget(self._book_details, 1, Qt.AlignmentFlag.AlignTop)

        # URL
        layout.addWidget(QLabel(_t("imports_url_label")))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(_t("imports_webpage_url_placeholder"))
        layout.addWidget(self._url_edit)

        # Title
        layout.addWidget(QLabel(_t("imports_webpage_card_title_label")))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText(_t("imports_article_title"))
        layout.addWidget(self._title_edit)

        layout.addWidget(QLabel(_t("imports_webpage_style_label")))
        self._style_combo = QComboBox()
        self._style_combo.setAccessibleName(_t("imports_webpage_style_label"))
        self._style_combo.addItem(_t("imports_webpage_style_website"), "website")
        self._style_combo.addItem(_t("imports_webpage_style_article"), "article")
        self._style_combo.addItem(_t("imports_webpage_style_print"), "print")
        layout.addWidget(self._style_combo)
        self._cleanup_check = QCheckBox(_t("imports_webpage_cleanup_option"))
        self._cleanup_check.setToolTip(_t("imports_webpage_cleanup_help"))
        self._style_combo.currentIndexChanged.connect(
            lambda _index: self._cleanup_check.setEnabled(self._style_combo.currentData() == "website"))
        layout.addWidget(self._cleanup_check)
        self._dynamic_check = QCheckBox(_t("imports_webpage_dynamic"))
        ready = browser_runtime() is not None
        self._dynamic_check.setChecked(ready)
        self._dynamic_check.setEnabled(ready)
        layout.addWidget(self._dynamic_check)
        self._setup_btn = QPushButton(_t("imports_webpage_browser_setup"))
        self._setup_btn.setVisible(not ready)
        self._setup_btn.clicked.connect(self._setup_browser)
        layout.addWidget(self._setup_btn)
        self._links_check = QCheckBox(_t("imports_webpage_link_appendix"))
        layout.addWidget(self._links_check)

        self._tag_edit = QuickTagEdit()
        layout.addWidget(self._tag_edit)

        # Status / progress
        self._status_lbl = QLabel("")
        self._status_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._status_lbl)

        browser_help = QLabel(_t("imports_webpage_browser_help"))
        browser_help.setWordWrap(True)
        browser_help.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(browser_help)
        browser_row = QHBoxLayout()
        self._open_browser_btn = QPushButton(_t("imports_webpage_open_browser"))
        self._open_browser_btn.clicked.connect(self._open_in_browser)
        self._saved_pdf_btn = QPushButton(_t("imports_webpage_saved_pdf"))
        self._saved_pdf_btn.setToolTip(_t("imports_webpage_saved_pdf_help"))
        self._saved_pdf_btn.clicked.connect(self._on_saved_pdf)
        browser_row.addWidget(self._open_browser_btn)
        browser_row.addWidget(self._saved_pdf_btn)
        layout.addLayout(browser_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate spinner
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        self._import_btn = QPushButton(_t("imports_import"))
        self._import_btn.setDefault(True)
        cancel_btn = QPushButton(_t("imports_cancel"))
        btn_row.addStretch()
        btn_row.addWidget(self._import_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._import_btn.clicked.connect(self._on_import)
        cancel_btn.clicked.connect(self.reject)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        for button in (self._import_btn, self._open_browser_btn, self._saved_pdf_btn, self._setup_btn):
            button.setEnabled(not busy)
        self._progress.setVisible(busy)
        self._cleanup_check.setEnabled(not busy and self._style_combo.currentData() == "website")
        self._book_details.setEnabled(not busy)

    def _capture_document_details(self) -> bool:
        if _active_profile() != self._profile:
            self._status_lbl.setText(_t("imports_topic_profile_changed"))
            return False
        try:
            self._document_details = self._book_details.details()
        except ValueError:
            self._status_lbl.setText(_t("reader_library_invalid_details"))
            return False
        return True

    def _browser_source_url(self) -> str:
        url = self._url_edit.text().strip()
        if not url:
            raise ValueError(_t("imports_webpage_enter_url"))
        if ":" not in url.split("/", 1)[0]:
            url = "https://" + url
        return normalize_external_http_url(url)

    def _open_in_browser(self) -> None:
        try:
            url = self._browser_source_url()
        except ValueError:
            self._status_lbl.setText(_t("imports_webpage_browser_url_invalid"))
            return
        if not open_companion_url(url):
            self._status_lbl.setText(_t("imports_companion_browser_unavailable"))
            return
        self._status_lbl.setText("")

    def _on_saved_pdf(self) -> None:
        from aqt import mw

        if not self._capture_document_details():
            return
        self._browser_handoff_tags = None
        self._browser_handoff_completed = False

        try:
            url = self._browser_source_url()
        except ValueError:
            self._status_lbl.setText(_t("imports_webpage_browser_url_invalid"))
            return
        profile = _active_profile()
        generation = self._import_generation
        source_path, _filter = QFileDialog.getOpenFileName(
            self, _t("imports_webpage_saved_pdf"), "", _t("imports_pdf_file_filter"),
        )
        if not source_path or not self._import_current(generation, profile):
            return
        title = self._title_edit.text().strip() or url
        self._capture_cancel = threading.Event()
        cancel_event = self._capture_cancel
        self._import_generation += 1
        generation = self._import_generation
        self._set_busy(True)
        self._status_lbl.setText(_t("imports_webpage_saved_pdf_loading"))

        def complete(future):
            try:
                pdf_path = future.result()
            except Exception:
                if self._import_current(generation, profile):
                    self._set_busy(False)
                    self._status_lbl.setText(_t("imports_webpage_saved_pdf_failed"))
                return
            if not self._import_current(generation, profile):
                try:
                    os.remove(pdf_path)
                except OSError:
                    pass
                return
            self._pdf_path = pdf_path
            self._title = title
            self._source_url = url
            self.accept()

        try:
            mw.taskman.run_in_background(
                lambda: copy_browser_saved_pdf(source_path, cancel_event=cancel_event),
                complete,
                uses_collection=False,
            )
        except Exception:
            self._set_busy(False)
            self._status_lbl.setText(_t("imports_webpage_saved_pdf_failed"))

    def _setup_browser(self) -> None:
        from aqt import mw
        generation = self._import_generation
        profile = _active_profile()
        self._set_busy(True)
        self._status_lbl.setText(_t("imports_webpage_browser_installing"))
        def complete(future):
            if not self._import_current(generation, profile):
                return
            try:
                ready = bool(future.result())
            except Exception:
                ready = False
            self._set_busy(False)
            self._setup_btn.setVisible(not ready)
            self._dynamic_check.setEnabled(ready)
            self._dynamic_check.setChecked(ready)
            self._status_lbl.setText(_t("imports_webpage_browser_ready") if ready else _t("imports_webpage_browser_setup_failed"))
        mw.taskman.run_in_background(install_browser_runtime, complete, uses_collection=False)

    def reject(self) -> None:
        self._stop_browser_handoff()
        self._capture_cancel.set()
        self._import_generation += 1
        super().reject()

    def _import_current(self, generation: int, profile: str) -> bool:
        return self._import_generation == generation and _active_profile() == profile

    def _stop_browser_handoff(self) -> None:
        timer = getattr(self, "_handoff_timer", None)
        if timer is not None:
            timer.stop()
        ticket = getattr(self, "_handoff_ticket", None)
        if ticket:
            browser_pdf_handoffs.cancel(ticket)
        self._handoff_ticket = None

    def _start_browser_handoff(self, url, title, style, include_links, generation, profile) -> None:
        self._stop_browser_handoff()
        self._handoff_ticket = browser_pdf_handoffs.create(url, profile)
        self._handoff_context = (url, title, style, include_links, generation, profile,
                                 bool(getattr(self, "_requested_cleanup", False)))
        self._browser_handoff_tags = list(self._tag_edit.tags())
        self._status_lbl.setText(_t("imports_webpage_browser_waiting"))
        self._handoff_timer = QTimer(self)
        self._handoff_timer.timeout.connect(self._poll_browser_handoff)
        self._handoff_timer.start(500)
        try:
            if not open_companion_url(f"http://127.0.0.1:8766{HANDOFF_PATH}#{self._handoff_ticket}"):
                raise OSError(_t("imports_companion_browser_unavailable"))
        except Exception:
            self._stop_browser_handoff()
            raise

    def _poll_browser_handoff(self) -> None:
        ticket = getattr(self, "_handoff_ticket", None)
        if not ticket:
            return
        url, title, style, include_links, generation, profile, cleanup = self._handoff_context
        if not self._import_current(generation, profile):
            self._stop_browser_handoff()
            self._set_busy(False)
            self._status_lbl.setText(_t("imports_topic_profile_changed"))
            return
        try:
            html = browser_pdf_handoffs.take(ticket, profile)
        except ValueError:
            self._stop_browser_handoff()
            self._set_busy(False)
            self._status_lbl.setText(_t("imports_webpage_browser_handoff_failed"))
            return
        if html is None:
            return
        self._stop_browser_handoff()
        self._status_lbl.setText(_t("imports_webpage_generating_pdf"))
        with tempfile.NamedTemporaryFile(prefix="incremento-webpage-", suffix=".pdf", delete=False) as temporary:
            pdf_path = temporary.name
        try:
            render_webpage_to_pdf(pdf_path, url=url, html=html, style=style, include_links=include_links,
                                  prefer_snapshot=True, cancel_event=self._capture_cancel,
                                  edit_before_save=cleanup)
            if not self._import_current(generation, profile):
                os.remove(pdf_path)
                return
        except Exception:
            try:
                os.remove(pdf_path)
            except OSError:
                pass
            if self._import_current(generation, profile):
                self._set_busy(False)
                self._status_lbl.setText(_t("imports_webpage_browser_handoff_failed"))
            return
        self._pdf_path = pdf_path
        self._title = title
        self._source_url = url
        self._browser_handoff_completed = True
        self.accept()

    def _on_import(self):
        self._stop_browser_handoff()
        self._browser_handoff_tags = None
        self._browser_handoff_completed = False
        url = self._url_edit.text().strip()
        if not url:
            self._status_lbl.setText(_t("imports_webpage_enter_url"))
            return
        if not self._capture_document_details():
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        title = self._title_edit.text().strip() or url
        style = self._style_combo.currentData()
        dynamic = self._dynamic_check.isChecked()
        include_links = self._links_check.isChecked()
        self._requested_cleanup = bool(style == "website" and getattr(self, "_cleanup_check", None) is not None
                                       and self._cleanup_check.isChecked())
        self._capture_cancel = threading.Event()
        cancel_event = self._capture_cancel
        self._import_generation += 1
        generation = self._import_generation
        profile = _active_profile()

        self._set_busy(True)
        self._status_lbl.setText(_t("imports_webpage_generating_pdf"))
        QApplication.processEvents()

        with tempfile.NamedTemporaryFile(
            prefix="incremento-webpage-",
            suffix=".pdf",
            delete=False,
        ) as temporary:
            pdf_path = temporary.name
        try:
            render_webpage_to_pdf(pdf_path, url=url, style=style, dynamic=dynamic, include_links=include_links,
                                  cancel_event=cancel_event, timeout_ms=90000 if dynamic else 45000,
                                  edit_before_save=self._requested_cleanup)
        except Exception as exc:
            try:
                os.remove(pdf_path)
            except OSError:
                pass
            if not self._import_current(generation, profile):
                return
            if isinstance(exc, WebpageVerificationRequired) or (isinstance(exc, HTTPError) and exc.code in {403, 429}):
                try:
                    self._start_browser_handoff(url, title, style, include_links, generation, profile)
                    return
                except Exception:
                    self._status_lbl.setText(_t("imports_webpage_browser_handoff_failed"))
                    self._set_busy(False)
                    return
            message = (_t("imports_webpage_access_blocked", status=exc.code)
                       if isinstance(exc, HTTPError) and exc.code in {403, 429} else str(exc))
            self._status_lbl.setText(message)
            self._set_busy(False)
            return

        if not self._import_current(generation, profile):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
            return
        self._pdf_path = pdf_path
        self._title = title
        self._source_url = url
        self.accept()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def document_details(self) -> dict:
        return self._document_details if self._document_details is not None else self._book_details.details()

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
        captured = getattr(self, "_browser_handoff_tags", None)
        return list(captured) if captured is not None else self._tag_edit.tags()

    @property
    def browser_handoff_completed(self) -> bool:
        return bool(getattr(self, "_browser_handoff_completed", False))
