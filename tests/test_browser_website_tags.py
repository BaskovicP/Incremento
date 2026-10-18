"""Authenticated website preferences cannot leak across profile switches."""

import io
import json
from types import SimpleNamespace

import aqt
import browser_bridge as bridge
import db
import paths
import pytest


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "_addon_dir", str(tmp_path))
    monkeypatch.setattr(bridge, "_bridge_token", "synthetic-session")
    monkeypatch.setattr(aqt, "mw", SimpleNamespace(col=object()))
    monkeypatch.setattr(paths, "get_active_profile", lambda: "ProfileA")
    monkeypatch.setattr(bridge, "_run_on_main_and_wait", lambda callback: callback())
    origin = "chrome-extension://" + "a" * 32
    monkeypatch.setattr(bridge, "_allowed_extension_origin", origin)
    yield str(tmp_path), origin
    db.close_connection()


def request(origin, payload, *, token="synthetic-session"):
    raw = json.dumps(payload).encode()
    handler = object.__new__(bridge._IncrementoBridgeHandler)
    handler.path = "/incremento/website-tags"
    handler.headers = {"Origin": origin, "X-Incremento-Token": token,
                       "X-Incremento-Protocol": "2", "Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    handler.close_connection = False
    responses = []
    handler._send_json = lambda code, body: responses.append((code, body))
    handler._do_POST()
    return responses[0]


def test_authenticated_popup_can_remember_load_and_forget_site_tags(context):
    _, origin = context
    status, loaded = request(origin, {"action": "load", "url": "https://example.org/one"})
    assert status == 200
    assert loaded["enabled"] is False
    save = {"action": "save", "url": "https://example.org/one", "enabled": True,
            "tags": ["Biology", "topic"], "profileToken": loaded["profileToken"]}
    assert request(origin, save)[0] == 200
    status, loaded = request(origin, {"action": "load", "url": "http://example.org/two"})
    assert status == 200
    assert loaded["tags"] == ["Biology", "topic"]
    assert request(origin, {**save, "enabled": False})[0] == 200
    assert request(origin, {"action": "load", "url": "https://example.org"})[1]["tags"] == []


def test_site_preferences_require_authentication_before_reading_body(context):
    _, origin = context
    assert request(origin, {"action": "load", "url": "https://example.org"}, token="wrong")[0] == 401
    assert request("chrome-extension://" + "b" * 32,
                   {"action": "load", "url": "https://example.org"})[0] == 403


def test_popup_opened_under_previous_profile_cannot_save_into_new_profile(context, monkeypatch):
    addon_dir, origin = context
    _, loaded = request(origin, {"action": "load", "url": "https://example.org"})
    monkeypatch.setattr(paths, "get_active_profile", lambda: "ProfileB")
    status, result = request(origin, {"action": "save", "url": "https://example.org", "enabled": True,
                                     "tags": ["private"], "profileToken": loaded["profileToken"]})
    assert status == 400
    assert result["error_code"] == "invalid_request"
    assert db.get_website_tags(addon_dir, "ProfileB", "https://example.org")["tags"] == []


@pytest.mark.parametrize("payload", [[], {"action": "erase_all", "url": "https://example.org"},
                                     {"action": [], "url": "https://example.org"},
                                     {"action": "load", "url": "file:///private"},
                                     {"action": "save", "url": "https://example.org", "enabled": True, "tags": []}])
def test_bad_website_preferences_fail_closed(context, payload):
    _, origin = context
    assert request(origin, payload)[0] == 400


def test_queued_website_request_from_an_ended_bridge_session_is_rejected(context):
    with pytest.raises(ValueError, match="profile changed"):
        bridge._website_tags_on_main({"action": "load", "url": "https://example.org"}, "old-session")


def test_website_endpoint_supports_extension_cors_preflight(context):
    _, origin = context
    handler = object.__new__(bridge._IncrementoBridgeHandler)
    handler.path = "/incremento/website-tags"
    handler.headers = {"Origin": origin}
    statuses = []
    handler.send_response = statuses.append
    handler.send_error = statuses.append
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None
    handler.do_OPTIONS()
    assert statuses == [204]


def test_oversized_website_preference_body_is_rejected_before_read(context):
    _, origin = context
    handler = object.__new__(bridge._IncrementoBridgeHandler)
    handler.path = "/incremento/website-tags"
    handler.headers = {"Origin": origin, "X-Incremento-Token": "synthetic-session",
                       "X-Incremento-Protocol": "2", "Content-Length": str(512 * 1024 + 1)}
    handler.rfile = SimpleNamespace(read=lambda *_args: pytest.fail("oversized body was read"))
    handler.close_connection = False
    responses = []
    handler._send_json = lambda code, body: responses.append((code, body))
    handler._do_POST()
    assert responses[0][0] == 413
    assert handler.close_connection is True
