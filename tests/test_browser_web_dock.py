import json
import types

from PyQt6.QtCore import QUrl

import web_dock


def test_web_bridge_script_is_private_and_progress_only():
    script = web_dock._build_web_bridge_js(
        bridge_nonce="private-token",
        card_id=42,
    )

    assert "private-token" in script
    assert "const INCREMENTO_CARD_ID = 42" in script
    assert "window.pycmd" not in script
    assert web_dock._MSG_PROGRESS in script
    assert web_dock._MSG_FILL_FIELD not in script
    assert web_dock._MSG_SNAPSHOT not in script


def test_web_javascript_runs_in_application_world():
    calls = []

    class _FakePage:
        def runJavaScript(self, *args):
            calls.append(args)

    web_dock._run_web_javascript(_FakePage(), "window.test = true;")

    assert calls == [
        (
            "window.test = true;",
            int(web_dock.QWebEngineScript.ScriptWorldId.ApplicationWorld.value),
        )
    ]


def test_web_bridge_rejects_static_prefix_and_wrong_card(monkeypatch):
    saved = []
    runtime = web_dock._WebDockRuntime(current_card_id=42)
    page = types.SimpleNamespace(_bridge_nonce="private-token", _runtime=runtime)
    monkeypatch.setattr(
        web_dock,
        "_controller",
        types.SimpleNamespace(current_display_url=lambda: "https://current.example/page"),
    )
    monkeypatch.setattr(
        web_dock,
        "_persist_web_scroll",
        lambda card_id, data: saved.append((card_id, data)),
    )
    payload = json.dumps(
        {
            "cardId": 42,
            "url": "https://forged.example/",
            "scrollRatio": 0.4,
        }
    )

    web_dock._WebDockPage.javaScriptConsoleMessage(
        page,
        0,
        web_dock._PYCMD_BRIDGE + web_dock._MSG_PROGRESS + payload,
        0,
        "page.js",
    )
    web_dock._WebDockPage.javaScriptConsoleMessage(
        page,
        0,
        web_dock._PYCMD_BRIDGE
        + "private-token:"
        + web_dock._MSG_PROGRESS
        + payload.replace('"cardId": 42', '"cardId": 99'),
        0,
        "page.js",
    )

    assert saved == []

    web_dock._WebDockPage.javaScriptConsoleMessage(
        page,
        0,
        web_dock._PYCMD_BRIDGE
        + "private-token:"
        + web_dock._MSG_PROGRESS
        + payload,
        0,
        "page.js",
    )

    assert saved == [
        (
            42,
            {
                "cardId": 42,
                "url": "https://current.example/page",
                "scrollRatio": 0.4,
            },
        )
    ]


def test_web_dock_blocks_non_http_main_frame_navigation():
    page = types.SimpleNamespace()

    assert (
        web_dock._WebDockPage.acceptNavigationRequest(
            page,
            QUrl("file:///tmp/private.txt"),
            None,
            True,
        )
        is False
    )
    assert (
        web_dock._WebDockPage.acceptNavigationRequest(
            page,
            QUrl("javascript:alert(1)"),
            None,
            True,
        )
        is False
    )
