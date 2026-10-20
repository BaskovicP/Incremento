"""Browser selection must not launch an unintended browser or weaken the bridge."""
import pytest
import browser_bridge
import file_shell

CHROME = "chrome-extension://" + "a" * 32
FIREFOX = "moz-extension://12345678-1234-4abc-8abc-123456789abc"


@pytest.fixture
def bridge_identity(monkeypatch):
    for name, value in (("_companion_browser", "chrome"),
                        ("_allowed_extension_origin", ""), ("_bridge_token", "old-token")):
        monkeypatch.setattr(browser_bridge, name, value, raising=False)


def handler(origin, token="old-token"):
    instance = object.__new__(browser_bridge._IncrementoBridgeHandler)
    instance.headers = {"Origin": origin, "X-Incremento-Token": token, "X-Incremento-Protocol": "2"}
    return instance


def test_firefox_is_opt_in_and_switching_revokes_old_chrome_connection(bridge_identity):
    chrome = handler(CHROME)
    assert chrome._bind_handshake_origin()
    assert not handler(FIREFOX)._bind_handshake_origin()
    browser_bridge.configure_companion_browser("firefox")
    assert not chrome._request_origin_allowed()
    assert not chrome._request_authenticated()
    assert handler(FIREFOX)._bind_handshake_origin()
    assert handler(FIREFOX, browser_bridge._bridge_token)._request_authenticated()
    assert not handler(FIREFOX.replace("12345678", "87654321"))._bind_handshake_origin()
    browser_bridge.configure_companion_browser("chrome")
    assert not handler(FIREFOX)._request_origin_allowed()
    assert handler(CHROME)._bind_handshake_origin()


def test_saving_unchanged_browser_keeps_existing_connection(bridge_identity):
    assert handler(CHROME)._bind_handshake_origin()
    browser_bridge.configure_companion_browser("chrome")
    assert handler(CHROME)._request_origin_allowed()
    assert handler(CHROME)._request_authenticated()


@pytest.mark.parametrize("origin", ["", "null", "https://example.org", "moz-extension://anything",
    FIREFOX + "/", FIREFOX + ":8766", FIREFOX + ".example.org", FIREFOX + "\r\nX: y"])
def test_firefox_rejects_untrusted_origins_without_binding_or_exposing_cors(bridge_identity, origin):
    browser_bridge.configure_companion_browser("firefox")
    request = handler(origin)
    headers = []
    request.send_header = lambda *args: headers.append(args)
    assert not request._request_origin_allowed(allow_unbound=True)
    assert not request._bind_handshake_origin()
    request._send_cors_headers()
    assert not any(name == "Access-Control-Allow-Origin" for name, _ in headers)
    assert browser_bridge._allowed_extension_origin == ""


@pytest.mark.parametrize("browser, app", [("chrome", "com.google.Chrome"), ("firefox", "org.mozilla.firefox")])
def test_opening_companion_url_uses_selected_macos_browser_and_exact_url(monkeypatch, browser, app):
    calls = []
    monkeypatch.setattr(file_shell.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or type("Result", (), {"returncode": 0})())
    url = "https://example.org/article#incremento_card=123&title=a%20b"
    assert file_shell.open_companion_url(url, browser=browser, platform="darwin")
    assert calls == [["/usr/bin/open", "-b", app, url]]


def test_missing_selected_browser_reports_failure_without_system_browser_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(file_shell.subprocess, "run", lambda *a, **kw: calls.append(a) or type("Result", (), {"returncode": 1})())
    assert not file_shell.open_companion_url("https://example.org", browser="firefox", platform="darwin")
    assert len(calls) == 1


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "https://user:pass@example.org", "--new-window", "https://example.org\n--private-window"])
def test_browser_launcher_rejects_unsafe_urls_before_launch(monkeypatch, url):
    monkeypatch.setattr(file_shell.subprocess, "run", lambda *a, **kw: pytest.fail("must not launch"))
    assert not file_shell.open_companion_url(url, browser="firefox", platform="darwin")


def test_local_pdf_handoff_keeps_opaque_fragment_when_opened(monkeypatch):
    calls = []
    monkeypatch.setattr(file_shell.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or type("Result", (), {"returncode": 0})())
    url = "http://127.0.0.1:8766/incremento/webpage-pdf#" + "a" * 64
    assert file_shell.open_companion_url(url, browser="firefox", platform="darwin")
    assert calls[0][-1] == url


@pytest.mark.parametrize("browser,platform,executable", [
    ("chrome", "linux", "/usr/bin/google-chrome"),
    ("firefox", "linux", "/usr/bin/firefox"),
    ("firefox", "win32", r"C:\Program Files\Mozilla Firefox\firefox.exe"),
])
def test_other_platforms_pass_the_url_as_one_argument(monkeypatch, browser, platform, executable):
    calls = []
    monkeypatch.setattr(file_shell.shutil, "which", lambda name: executable if name in {browser, "google-chrome"} else None)
    monkeypatch.setattr(file_shell.subprocess, "Popen", lambda args, **kw: calls.append(args))
    url = "https://example.org/?title=two%20words#incremento_card=42"
    assert file_shell.open_companion_url(url, browser=browser, platform=platform)
    assert calls == [[executable, "--new-tab", url]]


def test_absent_firefox_never_opens_an_available_chrome(monkeypatch):
    monkeypatch.setattr(file_shell.shutil, "which", lambda name: "/usr/bin/chrome" if name != "firefox" else None)
    monkeypatch.setattr(file_shell.subprocess, "Popen", lambda *_a, **_kw: pytest.fail("must not open Chrome"))
    assert not file_shell.open_companion_url("https://example.org", browser="firefox", platform="linux")


@pytest.mark.parametrize("browser,app", [("chrome", "com.google.Chrome"), ("firefox", "org.mozilla.firefox")])
@pytest.mark.parametrize("launched", [True, False])
def test_video_browser_action_only_starts_sync_after_selected_browser_opens(monkeypatch, browser, app, launched):
    import ast
    from pathlib import Path
    from video_manager import build_remote_video_watch_url
    path = Path(__file__).resolve().parents[1] / "frontend/video_dock.py"
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "_open_video_in_browser_at_seconds")
    opened, notices = [], []
    monkeypatch.setattr(file_shell, "_companion_browser", browser)
    monkeypatch.setattr(file_shell.sys, "platform", "darwin")
    monkeypatch.setattr(file_shell.subprocess, "run", lambda argv, **_kw: opened.append(argv) or type("Result", (), {"returncode": 0 if launched else 1})())
    namespace = {
        "_current_video_card_id": 42, "_current_video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "_last_known_position": 0, "_browser_sync_pending": False,
        "build_remote_video_watch_url": build_remote_video_watch_url,
        "_ADDON_DIR": "/unused", "_active_profile": lambda: "TestProfile",
        "set_video_position": lambda *_args: None,
        "open_companion_url": file_shell.open_companion_url,
        "tooltip": notices.append, "_tr": lambda key: key,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    namespace[node.name](35)
    assert len(opened) == 1 and "inc_card_id=42" in opened[0][-1] and "t=35" in opened[0][-1]
    assert opened[0][:3] == ["/usr/bin/open", "-b", app]
    assert namespace["_browser_sync_pending"] is launched
    if not launched:
        assert notices == ["reader_open_companion_browser_failed"]


@pytest.mark.parametrize("browser,app", [("chrome", "com.google.Chrome"), ("firefox", "org.mozilla.firefox")])
@pytest.mark.parametrize("action", ["open_in_window", "open_homepage_in_window"])
def test_web_reader_opens_the_companion_browser_with_linked_card_context(monkeypatch, browser, app, action):
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from web_manager import build_external_web_url
    path = Path(__file__).resolve().parents[1] / "frontend/web_dock.py"
    node = next(n for n in ast.walk(ast.parse(path.read_text()))
                if isinstance(n, ast.FunctionDef) and n.name == action)
    opened = []
    monkeypatch.setattr(file_shell, "_companion_browser", browser)
    monkeypatch.setattr(file_shell.sys, "platform", "darwin")
    monkeypatch.setattr(file_shell.subprocess, "run", lambda argv, **_kw: opened.append(argv) or type("Result", (), {"returncode": 0})())
    namespace = {"build_external_web_url": build_external_web_url,
        "open_companion_url": file_shell.open_companion_url,
        "set_web_url": lambda *_args: None, "_ADDON_DIR": "/unused",
        "_active_profile": lambda: "TestProfile", "tooltip": lambda _text: None, "t": lambda key: key}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    url = "https://example.org/article"
    instance = SimpleNamespace(current_display_url=lambda: url,
        runtime=SimpleNamespace(current_card_id=42, current_home_url=url, dock=None))
    namespace[action](instance)
    assert len(opened) == 1 and opened[0][-1].startswith(url) and "inc_card_id=42" in opened[0][-1]
    assert opened[0][:3] == ["/usr/bin/open", "-b", app]
