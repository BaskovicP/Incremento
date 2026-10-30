import io
import ssl
import ast
import os
import tempfile
import threading
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

import network_safety
import webpage_snapshot
from webpage_handoff import BrowserPdfHandoffs, WebpageVerificationRequired, requires_verification, HANDOFF_PATH
from content_safety import normalize_external_http_url


def _offline_webpage_preparer():
    """Run the real preparation pipeline without importing native Qt widgets."""
    import time
    from webpage_export import prepare_export_html
    from webpage_resources import build_offline_webpage_html

    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_prepare_webpage")
    namespace = {
        "time": time, "_t": lambda key: key,
        "normalize_external_http_url": normalize_external_http_url,
        "validate_public_http_url": network_safety.validate_public_http_url,
        "requires_verification": requires_verification,
        "WebpageVerificationRequired": WebpageVerificationRequired,
        "prepare_export_html": prepare_export_html,
        "build_offline_webpage_html": build_offline_webpage_html,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_prepare_webpage"], namespace


@pytest.mark.parametrize("style", ["print", "website", "article"])
def test_opened_archive_snapshot_survives_unsafe_source_dns_without_fetching_private_assets(monkeypatch, style):
    import base64
    import socket
    from bs4 import BeautifulSoup
    import webpage_resources

    source = "https://archive.ph/20260821073428/https://medium.com/example-article"
    requests = []
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1kAAAAASUVORK5CYII=")

    def resolver(host, port, **_kwargs):
        address = "93.184.216.34" if host == "images.example.test" else "127.0.0.2"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    def validate(url):
        return network_safety.validate_public_http_url(url, resolver=resolver)

    def fetch(request, *, timeout):
        requests.append(request.full_url)
        assert request.full_url == "https://images.example.test/photo.png"
        response = io.BytesIO(png)
        response.headers = {"Content-Type": "image/png"}
        response.geturl = lambda: request.full_url
        return response

    prepare, namespace = _offline_webpage_preparer()
    namespace["validate_public_http_url"] = validate
    monkeypatch.setattr(webpage_resources, "validate_public_http_url", validate)
    monkeypatch.setattr(webpage_resources, "open_public_http", fetch)
    html = '''<html><body><article><h1>Verified archived article</h1><p>Captured in the browser.</p>
        <img src="/blocked-photo.png"><img src="http://169.254.169.254/latest/meta-data/">
        <img src="file:///private/secret"><img src="https://images.example.test/photo.png">
        <script>fetch('http://127.0.0.1/secret')</script><iframe src="http://127.0.0.1/"></iframe>
        </article></body></html>'''

    result, pdf = prepare(source, html, 10, style=style, prefer_snapshot=True)

    soup = BeautifulSoup(result, "html.parser")
    assert pdf is None
    assert soup.h1.get_text() == "Verified archived article"
    assert soup.p.get_text() == "Captured in the browser."
    assert requests == ["https://images.example.test/photo.png"]
    assert [image.get("src") for image in soup.find_all("img")] == [
        None, None, None, "data:image/png;base64," + base64.b64encode(png).decode(),
    ]
    assert not soup.find_all(["script", "iframe"])
    assert "default-src 'none'" in soup.find("meta", attrs={"http-equiv": "Content-Security-Policy"})["content"]


@pytest.mark.parametrize("url", [
    "file:///private/article.html", "javascript:alert(1)",
    "https://user:secret@archive.ph/article", "https://archive.ph/article\nprivate",
])
def test_opened_snapshot_still_rejects_unsafe_source_urls_before_resource_capture(url):
    prepare, _namespace = _offline_webpage_preparer()
    with pytest.raises(ValueError):
        prepare(url, "<article>Captured article</article>", 10, prefer_snapshot=True)


@pytest.mark.parametrize("dynamic", [False, True])
def test_regular_webpage_export_still_rejects_unsafe_source_dns(dynamic):
    import socket

    prepare, namespace = _offline_webpage_preparer()
    namespace["validate_public_http_url"] = lambda url: network_safety.validate_public_http_url(
        url, resolver=lambda *_a, **_kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.2", 443))],
    )
    with pytest.raises(network_safety.UnsafeNetworkTargetError, match="private or special address"):
        prepare("https://archive.ph/article", "", 10, dynamic=dynamic)


@pytest.mark.parametrize("style", ["print", "website", "article"])
def test_browser_snapshot_is_used_without_fetching_the_article_again(style):
    import time
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_prepare_webpage")
    namespace = {
        "time": time, "_t": lambda key: key, "validate_public_http_url": lambda url: url,
        "normalize_external_http_url": normalize_external_http_url,
        "requires_verification": requires_verification, "WebpageVerificationRequired": WebpageVerificationRequired,
        "_fetch_wikipedia_article_pdf": lambda *_a, **_kw: pytest.fail("Captured article must not be replaced by a new download"),
        "_fetch_webpage_html": lambda *_a, **_kw: pytest.fail("Do not refetch a browser-verified article"),
        "render_browser_pdf": lambda *_a, **_kw: pytest.fail("Do not reload the page in a different browser"),
        "prepare_export_html": lambda html, *_a, **_kw: html,
        "build_offline_webpage_html": lambda html, *_a, **_kw: html,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    assert namespace["_prepare_webpage"]("https://example.org/verified", "<p>Verified article</p>", 10, style,
                                         dynamic=True, prefer_snapshot=True) == (
        "<p>Verified article</p>", None,
    )


def test_regular_print_export_still_uses_official_wikipedia_pdf():
    import time
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_prepare_webpage")
    namespace = {
        "time": time, "_t": lambda key: key, "validate_public_http_url": lambda url: url,
        "_fetch_wikipedia_article_pdf": lambda *_a, **_kw: b"%PDF-official",
        "prepare_export_html": lambda *_a, **_kw: pytest.fail("Regular print export should use the official PDF"),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    assert namespace["_prepare_webpage"]("https://en.wikipedia.org/wiki/Example", "<p>Browser article</p>", 10) == (
        "", b"%PDF-official",
    )


def test_browser_saved_pdf_is_copied_without_changing_the_original(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    source = tmp_path / "browser.pdf"
    source.write_bytes(b"%PDF-1.7\nBrowser-verified article")

    result = Path(webpage_snapshot.copy_browser_saved_pdf(str(source)))

    assert result != source
    assert result.read_bytes() == source.read_bytes()
    assert result.stat().st_mode & 0o077 == 0
    result.unlink()
    assert source.read_bytes() == b"%PDF-1.7\nBrowser-verified article"


@pytest.mark.parametrize("kind", ["html", "oversized", "symlink", "directory", "cancelled"])
def test_browser_saved_pdf_rejects_invalid_input_without_leaving_a_copy(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(webpage_snapshot, "MAX_WEBPAGE_PDF_BYTES", 32)
    source = tmp_path / "browser.pdf"
    source.write_bytes(b"<html>CAPTCHA</html>" if kind == "html" else b"%PDF-1.7\nArticle")
    if kind == "oversized":
        source.write_bytes(b"%PDF-" + b"x" * 28)
    elif kind == "symlink":
        link = tmp_path / "link.pdf"
        link.symlink_to(source)
        source = link
    elif kind == "directory":
        source = tmp_path
    cancel = threading.Event()
    if kind == "cancelled":
        cancel.set()
    original_entries = sorted(tmp_path.iterdir())

    with pytest.raises((ValueError, OSError, InterruptedError)):
        webpage_snapshot.copy_browser_saved_pdf(str(source), cancel_event=cancel)

    assert sorted(tmp_path.iterdir()) == original_entries


def test_browser_saved_pdf_accepts_the_exact_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(webpage_snapshot, "MAX_WEBPAGE_PDF_BYTES", 32)
    source = tmp_path / "browser.pdf"
    source.write_bytes(b"%PDF-" + b"x" * 27)

    result = Path(webpage_snapshot.copy_browser_saved_pdf(str(source)))

    assert result.read_bytes() == source.read_bytes()
    result.unlink()


@pytest.mark.parametrize("failure", ["cancel", "write-error"])
def test_browser_saved_pdf_cleans_up_a_partial_copy(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    source = tmp_path / "browser.pdf"
    source.write_bytes(b"%PDF-1.7\nArticle")
    cancel = threading.Event()
    original_temporary = tempfile.NamedTemporaryFile

    def interrupted_output(**kwargs):
        output = original_temporary(**kwargs)
        original_write = output.write
        def write(data):
            original_write(data)
            if failure == "cancel":
                cancel.set()
            else:
                raise OSError("Synthetic disk write failure")
        output.write = write
        return output
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", interrupted_output)

    with pytest.raises(InterruptedError if failure == "cancel" else OSError):
        webpage_snapshot.copy_browser_saved_pdf(str(source), cancel_event=cancel)

    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == b"%PDF-1.7\nArticle"


def _browser_fallback_dialog(monkeypatch, tmp_path):
    """Exercise dialog callbacks without starting WebEngine or an Anki profile."""
    from concurrent.futures import Future
    from backend.i18n import Translator
    from aqt import mw

    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    dialog = next(node for node in ast.parse(path.read_text()).body
                  if isinstance(node, ast.ClassDef) and node.name == "WebpageToPdfDialog")
    dialog.bases = []
    dialog.body = [node for node in dialog.body
                   if not isinstance(node, ast.FunctionDef) or node.name != "__init__"]
    profile = {"name": "First"}
    opened, accepted, pending = [], [], []
    class Timer:
        timeout = SimpleNamespace(connect=lambda _callback: None)
        def __init__(self, *_args):
            pass
        def start(self, _interval):
            pass
        def stop(self):
            pass
    namespace = {
        "os": os, "tempfile": tempfile, "threading": threading, "HTTPError": HTTPError,
        "normalize_external_http_url": normalize_external_http_url,
        "copy_browser_saved_pdf": webpage_snapshot.copy_browser_saved_pdf,
        "browser_pdf_handoffs": BrowserPdfHandoffs(), "HANDOFF_PATH": HANDOFF_PATH,
        "WebpageVerificationRequired": WebpageVerificationRequired, "QTimer": Timer,
        "_active_profile": lambda: profile["name"], "_t": Translator("en").t,
        "open_companion_url": lambda url: opened.append(url) or True,
        "openLink": lambda _url: pytest.fail("must use selected Companion browser"), "QApplication": SimpleNamespace(processEvents=lambda: None),
        "QFileDialog": SimpleNamespace(getOpenFileName=lambda *_a: (str(tmp_path / "browser.pdf"), "")),
    }
    exec(compile(ast.Module(body=[dialog], type_ignores=[]), str(path), "exec"), namespace)
    state = namespace["WebpageToPdfDialog"]()

    class Control:
        def __init__(self):
            self.text_value = ""
            self.enabled = True
            self.visible = False

        def setText(self, text):
            self.text_value = text

        def setEnabled(self, enabled):
            self.enabled = enabled

        def setVisible(self, visible):
            self.visible = visible

    for name in ("_import_btn", "_saved_pdf_btn", "_open_browser_btn", "_setup_btn", "_status_lbl", "_progress"):
        setattr(state, name, Control())
    state._url_edit = SimpleNamespace(text=lambda: "https://example.org/article")
    state._title_edit = SimpleNamespace(text=lambda: "My article")
    state._tag_edit = SimpleNamespace(tags=lambda: ["topic", "reading"])
    state._style_combo = SimpleNamespace(currentData=lambda: "article")
    state._dynamic_check = SimpleNamespace(isChecked=lambda: False)
    state._links_check = SimpleNamespace(isChecked=lambda: False)
    state._cleanup_check = Control()
    state._cleanup_check.isChecked = lambda: False
    state._import_generation = 0
    state._capture_cancel = threading.Event()
    state._pdf_path = None
    state.accept = lambda: accepted.append(True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(mw.taskman, "run_in_background", lambda work, done, **kwargs: pending.append((work, done, kwargs)))

    def finish():
        work, done, kwargs = pending.pop(0)
        assert kwargs == {"uses_collection": False}
        result = Future()
        try:
            result.set_result(work())
        except Exception as exc:
            result.set_exception(exc)
        done(result)

    return state, namespace, profile, opened, accepted, pending, finish


def test_blocked_webpage_automatically_opens_browser_and_waits_for_verification(monkeypatch, tmp_path):
    state, namespace, _profile, opened, accepted, pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    def blocked(*_a, **_kw):
        raise HTTPError("https://example.org/article", 429, "Too Many Requests", {}, None)
    namespace["render_webpage_to_pdf"] = blocked

    state._on_import()

    assert "browser" in state._status_lbl.text_value
    # The intended workflow now continues automatically instead of requiring
    # the user to start a second import or choose a saved PDF.
    assert not state._import_btn.enabled and state._progress.visible
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:8766/incremento/webpage-pdf#")
    assert accepted == pending == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("outcome", ["success", "closed", "profile-switch", "render-failed"])
def test_browser_verification_automatically_finishes_the_original_import(monkeypatch, tmp_path, outcome):
    state, namespace, profile, opened, accepted, _pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    def blocked(*_a, **_kw):
        raise WebpageVerificationRequired()
    namespace["render_webpage_to_pdf"] = blocked
    state._on_import()
    ticket = opened[0].split("#", 1)[1]
    namespace["browser_pdf_handoffs"].submit(ticket, "https://example.org/article", "<article>Verified article</article>")
    calls = []
    def render(path, **options):
        calls.append(options)
        Path(path).write_bytes(b"%PDF-1.7\nArticle")
        if outcome == "render-failed":
            raise RuntimeError("Synthetic render error")
    namespace["render_webpage_to_pdf"] = render
    if outcome == "closed":
        state._import_generation += 1
    elif outcome == "profile-switch":
        profile["name"] = "Second"
    state._poll_browser_handoff()
    assert accepted == ([True] if outcome == "success" else [])
    if outcome == "success":
        assert calls == [{"url": "https://example.org/article", "html": "<article>Verified article</article>",
                          "style": "article", "include_links": False, "prefer_snapshot": True,
                          "cancel_event": state._capture_cancel, "edit_before_save": False}]
        assert state.browser_handoff_completed
        assert state.title_text == "My article" and state.tags_to_apply == ["topic", "reading"]
        Path(state.pdf_path).unlink()
    elif outcome in {"closed", "profile-switch"}:
        assert calls == []
    else:
        assert state._import_btn.enabled
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("outcome", ["success", "closed", "profile-switch", "invalid"])
def test_saved_pdf_fallback_keeps_metadata_and_discards_stale_results(monkeypatch, tmp_path, outcome):
    state, _namespace, profile, _opened, accepted, pending, finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    source = tmp_path / "browser.pdf"
    content = b"<html>CAPTCHA</html>" if outcome == "invalid" else b"%PDF-1.7\nArticle"
    source.write_bytes(content)

    state._on_saved_pdf()
    assert len(pending) == 1
    assert not state._import_btn.enabled and not state._saved_pdf_btn.enabled
    if outcome == "closed":
        state._import_generation += 1
    elif outcome == "profile-switch":
        profile["name"] = "Second"
    finish()

    assert source.read_bytes() == content
    assert accepted == ([True] if outcome == "success" else [])
    if outcome == "success":
        assert Path(state.pdf_path) != source
        assert Path(state.pdf_path).read_bytes() == content
        assert state.title_text == "My article"
        assert state.source_url == "https://example.org/article"
        assert state.tags_to_apply == ["topic", "reading"]
        Path(state.pdf_path).unlink()
    else:
        assert state.pdf_path is None
    assert list(tmp_path.iterdir()) == [source]
    if outcome == "invalid":
        assert state._import_btn.enabled and state._saved_pdf_btn.enabled
        assert "PDF" in state._status_lbl.text_value


@pytest.mark.parametrize("url,allowed", [
    ("example.org/article", True), ("https://example.org/article", True),
    ("file:///etc/passwd", False), ("javascript:alert(1)", False),
    ("https://user:secret@example.org", False), ("https://example.org/\nattack", False),
])
def test_browser_fallback_opens_only_uncredentialed_http_urls(monkeypatch, tmp_path, url, allowed):
    state, _namespace, _profile, opened, accepted, pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    state._url_edit = SimpleNamespace(text=lambda: url)

    state._open_in_browser()

    assert opened == (["https://example.org/article"] if allowed else [])
    assert accepted == pending == []


@pytest.mark.parametrize("outcome", ["success", "close", "open-failed", "profile-switch"])
def test_completed_webpage_pdf_action_is_optional_profile_scoped_and_retryable(outcome):
    script = dedent('''
        import gc
        import importlib
        from pathlib import Path
        import sys
        from types import ModuleType, SimpleNamespace
        import aqt
        from aqt.qt import QApplication, QLabel, QPushButton, QWidget, Qt
        package = ModuleType('webpage_result_fixture')
        package.__path__ = [str(Path.cwd())]
        sys.modules[package.__name__] = package
        aqt.mw = SimpleNamespace(col=None)
        module = importlib.import_module('webpage_result_fixture.frontend.webpage_dialog')
        i18n = importlib.import_module('webpage_result_fixture.backend.i18n')
        app = QApplication([])
        app.setStyle('Fusion')
        owner = QWidget()
        profile = ['First']
        module._active_profile = lambda: profile[0]
        opened = []
        outcome = sys.argv[1]
        fail_open = [outcome == 'open-failed']
        for language in ('en', 'hr', 'zh-Hans'):
            i18n.initialize_language(language)
            for font_size in (13, 18):
                from aqt.qt import QFont
                app.setFont(QFont('Arial', font_size))
                profile[0] = 'First'
                opened.clear()
                fail_open[0] = outcome == 'open-failed'
                def open_pdf():
                    opened.append(123)
                    if fail_open[0]:
                        raise ValueError('Missing PDF')
                def show_result():
                    module.WebpagePdfResultDialog(owner, '<b>Article</b>', 'First', open_pdf).show()
                show_result()
                gc.collect()
                app.processEvents()
                dialog = next(child for child in owner.findChildren(module.WebpagePdfResultDialog)
                              if child.isVisible())
                assert dialog.parent() is owner
                assert dialog.isVisible() and not dialog.isModal()
                assert opened == []
                for label in dialog.findChildren(QLabel):
                    assert label.textFormat() == Qt.TextFormat.PlainText
                    if label.isVisible() and label.wordWrap() and label.text():
                        assert label.height() >= label.heightForWidth(label.width())
                button = next(button for button in dialog.findChildren(QPushButton)
                              if button.text() == i18n.t('knowledge_tree_open_pdf'))
                if outcome == 'profile-switch':
                    profile[0] = 'Second'
                if outcome == 'close':
                    next(button for button in dialog.findChildren(QPushButton)
                         if button.text() == i18n.t('reader_close')).click()
                else:
                    button.click()
                assert opened == ([123] if outcome in ('success', 'open-failed') else [])
                if outcome == 'open-failed':
                    message = i18n.t('root_document_open_failed', error='Missing PDF')
                    assert any(label.text() == message for label in dialog.findChildren(QLabel))
                    assert dialog.isVisible()
                    fail_open[0] = False
                    button.click()
                    assert opened == [123, 123] and not dialog.isVisible()
                else:
                    assert not dialog.isVisible()
                dialog.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, outcome], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cancelled_saved_pdf_picker_does_not_start_work(monkeypatch, tmp_path):
    state, namespace, _profile, _opened, accepted, pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    namespace["QFileDialog"].getOpenFileName = lambda *_a: ("", "")

    state._on_saved_pdf()

    assert accepted == pending == []
    assert state._import_btn.enabled and state._saved_pdf_btn.enabled


def test_browser_fallback_guidance_fits_in_all_bundled_languages():
    script = dedent('''
        import importlib
        from pathlib import Path
        import sys
        from types import ModuleType, SimpleNamespace
        import aqt
        from aqt.qt import QApplication, QFont, QLabel
        package = ModuleType('webpage_layout_fixture')
        package.__path__ = [str(Path.cwd())]
        sys.modules[package.__name__] = package
        aqt.mw = SimpleNamespace(col=None)
        module = importlib.import_module('webpage_layout_fixture.frontend.webpage_dialog')
        i18n = importlib.import_module('webpage_layout_fixture.backend.i18n')
        app = QApplication([])
        app.setStyle('Fusion')
        failures = []
        for language in ('en', 'hr', 'zh-Hans'):
            i18n.initialize_language(language)
            for font_size in (13, 18):
                app.setFont(QFont('Arial', font_size))
                dialog = module.WebpageToPdfDialog()
                dialog._status_lbl.setText(i18n.t('imports_webpage_access_blocked', status=429))
                dialog.show()
                for _ in range(3):
                    app.processEvents()
                for label in dialog.findChildren(QLabel):
                    if label.isVisible() and label.wordWrap() and label.text():
                        required = label.heightForWidth(label.width())
                        if label.height() < required:
                            failures.append((language, font_size, label.text(), label.height(), required))
                dialog.close()
        assert not failures, failures
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("style", ["website", "article"])
def test_dynamic_export_uses_browser_and_keeps_requested_style(style):
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    function = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == "_prepare_webpage")
    import time
    calls = []
    namespace = {"time": time, "_t": lambda key: key, "validate_public_http_url": lambda url: url,
                 "render_browser_pdf": lambda url, html, **kw: calls.append((url, html, kw)) or b"%PDF-browser",
                 "_fetch_wikipedia_article_pdf": lambda *_a, **_kw: pytest.fail("Wrong renderer"),
                 "_fetch_webpage_html": lambda *_a, **_kw: pytest.fail("Static fetch used")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    assert namespace["_prepare_webpage"]("https://example.org/a", "", 10, style, True, True) == ("", b"%PDF-browser")
    assert calls[0][2]["style"] == style
    assert calls[0][2]["include_links"] is True


def test_dynamic_cleanup_captures_rendered_html_for_an_offline_editable_preview():
    prepare, namespace = _offline_webpage_preparer()
    calls = []
    namespace["validate_public_http_url"] = lambda url: url
    namespace["capture_browser_html"] = lambda url, html, **kw: calls.append((url, kw)) or (url, '<main><p>Dynamic comments</p></main>')
    namespace["render_browser_pdf"] = lambda *_a, **_kw: pytest.fail("Cleanup needs the DOM before PDF printing")

    html, pdf = prepare("https://example.test/post", "", 10, style="website", dynamic=True, capture_html=True)

    assert pdf is None
    assert "Dynamic comments" in html
    assert "default-src 'none'" in html
    assert calls[0][0] == "https://example.test/post"


@pytest.mark.parametrize("switch_during", ["capture", "print"])
def test_pdf_render_rejects_profile_changes_before_returning_to_importer(tmp_path, switch_during):
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    function = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == "render_webpage_to_pdf")
    state = {"profile": "First", "prints": 0}

    def prepare(*_args):
        if switch_during == "capture":
            state["profile"] = "Second"
        return "<p>Article</p>", None

    def print_pdf(*_args, **_kwargs):
        state["prints"] += 1
        if switch_during == "print":
            state["profile"] = "Second"

    namespace = {"os": os, "tempfile": tempfile, "_t": lambda key: key,
        "_active_profile": lambda: state["profile"], "_prepare_in_background": prepare,
        "_print_offline_snapshot": print_pdf}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    with pytest.raises(RuntimeError, match="profile"):
        namespace["render_webpage_to_pdf"](str(tmp_path / "article.pdf"), html="Article")

    assert state["prints"] == (switch_during == "print")


@pytest.mark.parametrize("generation,profile,expected", [
    (3, "First", True), (2, "First", False), (3, "Second", False),
])
def test_closed_or_switched_profile_webpage_import_cannot_accept_late_result(generation, profile, expected):
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    dialog = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.ClassDef) and node.name == "WebpageToPdfDialog")
    function = next(node for node in dialog.body if isinstance(node, ast.FunctionDef) and node.name == "_import_current")
    namespace = {"_active_profile": lambda: "First"}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    assert namespace["_import_current"](SimpleNamespace(_import_generation=3), generation, profile) is expected


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("about:blank", True),
        ("data:image/png;base64,AA==", True),
        ("https://example.test/image.png", False),
        ("http://127.0.0.1/private", False),
        ("file:///tmp/private", False),
        ("blob:https://example.test/id", False),
    ],
)
def test_offline_snapshot_allows_no_network_or_local_resources(url, allowed):
    assert webpage_snapshot.offline_snapshot_resource_allowed(url) is allowed


def test_offline_renderer_can_load_only_its_exact_generated_document():
    document = "file:///tmp/incremento-snapshot.html"

    assert webpage_snapshot.offline_snapshot_resource_allowed(document, document_url=document)
    for target in ("file:///etc/passwd", document + "?x=1", "https://example.test/image.png"):
        assert not webpage_snapshot.offline_snapshot_resource_allowed(target, document_url=document)


def test_fetch_webpage_html_uses_bounded_public_client(monkeypatch):
    calls = []

    class _Response:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self):
            self._chunks = iter([b"<html>safe</html>", b""])

        def read(self, _size=-1):
            return next(self._chunks)

        def geturl(self):
            return "https://example.test/final"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )
    monkeypatch.setattr(
        webpage_snapshot,
        "open_public_http",
        lambda request, *, timeout: (
            calls.append((request.full_url, timeout)) or _Response()
        ),
    )

    final_url, html = webpage_snapshot.fetch_webpage_html(
        "https://example.test/start",
        timeout_sec=7,
    )

    assert calls == [("https://example.test/start", 7.0)]
    assert final_url == "https://example.test/final"
    assert html == "<html>safe</html>"


@pytest.mark.parametrize("valid_certificate", [True, False], ids=["valid-tls", "invalid-tls"])
def test_https_webpage_fetch_preserves_tls_verification(monkeypatch, valid_certificate):
    """Exercise the real urllib handler/connection, replacing only network I/O."""
    url = "https://93.184.216.34/article"
    body = b"<html>Article for PDF conversion</html>"
    destinations = []
    tls_checks = []
    requests = []

    class _Socket:
        def setsockopt(self, *args):
            pass

        def sendall(self, data):
            requests.append(data)

        def makefile(self, mode):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                + body
            )

        def close(self):
            pass

    def connect(address, timeout, source_address):
        destinations.append((address, timeout))
        return _Socket()

    def wrap_socket(context, sock, *, server_hostname):
        tls_checks.append((context.verify_mode, context.check_hostname, server_hostname))
        if not valid_certificate:
            raise ssl.SSLCertVerificationError("Test certificate rejected")
        return sock

    monkeypatch.setattr(network_safety, "_create_public_connection", connect)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)

    if valid_certificate:
        assert webpage_snapshot.fetch_webpage_html(url, timeout_sec=7) == (
            url, body.decode("utf-8")
        )
        assert b"GET /article HTTP/1.1\r\n" in b"".join(requests)
    else:
        with pytest.raises(URLError) as exc:
            webpage_snapshot.fetch_webpage_html(url, timeout_sec=7)
        assert isinstance(exc.value.reason, ssl.SSLCertVerificationError)
        assert requests == []

    assert destinations == [(("93.184.216.34", 443), 7.0)]
    assert tls_checks == [(ssl.CERT_REQUIRED, True, "93.184.216.34")]


def test_fetch_webpage_html_rejects_non_document_content(monkeypatch):
    response = SimpleNamespace(
        headers={"Content-Type": "application/octet-stream"},
        read=lambda _size=-1: b"binary",
        geturl=lambda: "https://example.test/file",
        __enter__=lambda self: self,
        __exit__=lambda self, *_args: False,
    )

    class _ContextResponse:
        headers = response.headers

        def read(self, size=-1):
            return response.read(size)

        def geturl(self):
            return response.geturl()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )
    monkeypatch.setattr(
        webpage_snapshot,
        "open_public_http",
        lambda *_args, **_kwargs: _ContextResponse(),
    )

    with pytest.raises(ValueError, match="HTML document"):
        webpage_snapshot.fetch_webpage_html("https://example.test/file")


@pytest.mark.parametrize(
    ("article_url", "pdf_url"),
    [
        (
            "https://en.wikipedia.org/wiki/Alan_Turing#Early_life",
            "https://en.wikipedia.org/api/rest_v1/page/pdf/Alan_Turing",
        ),
        (
            "https://hr.wikipedia.org/wiki/Nikola_Tesla?oldid=123",
            "https://hr.wikipedia.org/api/rest_v1/page/pdf/Nikola_Tesla",
        ),
        (
            "https://de.wikipedia.org/w/index.php?title=K%C3%A4the_Kollwitz&oldid=1",
            "https://de.wikipedia.org/api/rest_v1/page/pdf/K%C3%A4the_Kollwitz",
        ),
    ],
)
def test_wikipedia_article_pdf_url_uses_official_download_service(
    monkeypatch, article_url, pdf_url
):
    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )

    assert webpage_snapshot.wikipedia_article_pdf_url(article_url) == pdf_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/wiki/Alan_Turing",
        "https://wikipedia.org/",
        "https://en.wikipedia.org/w/index.php?action=history",
    ],
)
def test_wikipedia_article_pdf_url_ignores_non_article_urls(monkeypatch, url):
    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda candidate: str(candidate),
    )

    assert webpage_snapshot.wikipedia_article_pdf_url(url) is None


def test_fetch_wikipedia_article_pdf_is_bounded_and_requires_pdf(monkeypatch):
    calls = []

    class _Response:
        headers = {"Content-Type": "application/pdf"}

        def __init__(self):
            self._chunks = iter([b"%PDF-1.7 article", b""])

        def read(self, _size=-1):
            return next(self._chunks)

        def geturl(self):
            return "https://en.wikipedia.org/api/rest_v1/page/pdf/Alan_Turing"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )
    monkeypatch.setattr(
        webpage_snapshot,
        "open_public_http",
        lambda request, *, timeout: (
            calls.append((request.full_url, request.get_header("Accept"), timeout))
            or _Response()
        ),
    )

    pdf = webpage_snapshot.fetch_wikipedia_article_pdf(
        "https://en.wikipedia.org/wiki/Alan_Turing",
        timeout_sec=12,
    )

    assert pdf == b"%PDF-1.7 article"
    assert calls == [
        (
            "https://en.wikipedia.org/api/rest_v1/page/pdf/Alan_Turing",
            "application/pdf",
            12.0,
        )
    ]


def test_fetch_wikipedia_article_pdf_rejects_html_response(monkeypatch):
    class _Response:
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self):
            self._chunks = iter([b"<html>error</html>", b""])

        def read(self, _size=-1):
            return next(self._chunks)

        def geturl(self):
            return "https://en.wikipedia.org/api/rest_v1/page/pdf/Missing"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        webpage_snapshot,
        "validate_public_http_url",
        lambda url: str(url),
    )
    monkeypatch.setattr(
        webpage_snapshot,
        "open_public_http",
        lambda *_args, **_kwargs: _Response(),
    )

    with pytest.raises(ValueError, match="valid PDF"):
        webpage_snapshot.fetch_wikipedia_article_pdf(
            "https://en.wikipedia.org/wiki/Missing"
        )
@pytest.mark.parametrize("closed", [False, True])
def test_import_routes_selected_options_and_drops_results_after_closing(tmp_path, monkeypatch, closed):
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    dialog = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.ClassDef) and node.name == "WebpageToPdfDialog")
    function = next(node for node in dialog.body if isinstance(node, ast.FunctionDef) and node.name == "_on_import")
    calls = []
    accepted = []
    control = SimpleNamespace(setEnabled=lambda *_a: None, setVisible=lambda *_a: None, setText=lambda *_a: None)
    state = SimpleNamespace(_url_edit=SimpleNamespace(text=lambda: "https://example.org/a"),
        _title_edit=SimpleNamespace(text=lambda: "Article"), _style_combo=SimpleNamespace(currentData=lambda: "article"),
        _dynamic_check=SimpleNamespace(isChecked=lambda: True), _links_check=SimpleNamespace(isChecked=lambda: True),
        _import_generation=0, _import_btn=control, _progress=control, _status_lbl=control,
        _set_busy=lambda _busy: None,
        _stop_browser_handoff=lambda: None,
        accept=lambda: accepted.append(True))
    state._import_current = lambda generation, profile: state._import_generation == generation and profile == "First"
    def render(output, **options):
        Path(output).write_bytes(b"%PDF-fixture")
        calls.append((output, options))
        if closed:
            state._import_generation += 1
    namespace = {"tempfile": tempfile, "threading": threading, "os": os, "_active_profile": lambda: "First",
                 "_t": lambda key: key, "QApplication": SimpleNamespace(processEvents=lambda: None), "render_webpage_to_pdf": render}
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    namespace["_on_import"](state)

    output, options = calls[0]
    assert options["style"] == "article"
    assert options["dynamic"] is True
    assert options["include_links"] is True
    assert options["timeout_ms"] == 90000
    assert bool(accepted) is not closed
    assert Path(output).exists() is not closed
    if not closed:
        assert state._pdf_path == output
        Path(output).unlink()


def test_cleanup_choice_is_retained_through_verification_even_if_controls_change(monkeypatch, tmp_path):
    state, namespace, _profile, _opened, accepted, _pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    state._style_combo.currentData = lambda: "website"
    state._cleanup_check.isChecked = lambda: True
    calls = []
    def render(path, **options):
        calls.append(options)
        if len(calls) == 1:
            raise WebpageVerificationRequired()
        Path(path).write_bytes(b"%PDF-fixture")
    namespace["render_webpage_to_pdf"] = render

    state._on_import()
    state._cleanup_check.isChecked = lambda: False
    namespace["browser_pdf_handoffs"].submit(state._handoff_ticket, "https://example.org/article", "<article>Verified article</article>")
    state._poll_browser_handoff()

    assert [options["edit_before_save"] for options in calls] == [True, True]
    assert accepted == [True]
    Path(state.pdf_path).unlink()


def test_missing_companion_browser_leaves_no_pending_pdf_handoff(monkeypatch, tmp_path):
    state, namespace, _profile, opened, accepted, pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    namespace["open_companion_url"] = lambda _url: False
    def blocked(*_a, **_kw):
        raise WebpageVerificationRequired()
    namespace["render_webpage_to_pdf"] = blocked
    state._on_import()
    assert state._handoff_ticket is None
    assert state._import_btn.enabled and not state._progress.visible
    assert not opened and not accepted and not pending
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("browser,app", [("chrome", "com.google.Chrome"), ("firefox", "org.mozilla.firefox")])
@pytest.mark.parametrize("action", ["manual", "verification"])
def test_webpage_browser_and_verification_use_the_saved_browser(monkeypatch, tmp_path, browser, app, action):
    import file_shell
    state, namespace, _profile, _opened, accepted, pending, _finish = _browser_fallback_dialog(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(file_shell, "_companion_browser", browser)
    monkeypatch.setattr(file_shell.sys, "platform", "darwin")
    monkeypatch.setattr(file_shell.subprocess, "run", lambda argv, **_kw: calls.append(argv) or SimpleNamespace(returncode=0))
    namespace["open_companion_url"] = file_shell.open_companion_url
    if action == "manual":
        state._open_in_browser()
        expected = "https://example.org/article"
    else:
        def blocked(*_args, **_kwargs):
            raise WebpageVerificationRequired()
        namespace["render_webpage_to_pdf"] = blocked
        state._on_import()
        expected = "http://127.0.0.1:8766/incremento/webpage-pdf#" + state._handoff_ticket
        assert not state._import_btn.enabled and state._progress.visible
    assert calls == [["/usr/bin/open", "-b", app, expected]]
    assert accepted == pending == []
    assert list(tmp_path.iterdir()) == []
