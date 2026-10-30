"""Hostile wire requests must never acquire internal import privileges."""

import io
import json
import sys
import base64
from types import SimpleNamespace

import pytest

import browser_bridge


def _post(monkeypatch, payload):
    origin = "chrome-extension://" + "a" * 32
    monkeypatch.setattr(browser_bridge, "_companion_browser", "chrome")
    monkeypatch.setattr(browser_bridge, "_allowed_extension_origin", origin)
    monkeypatch.setattr(browser_bridge, "_bridge_token", "test-session")
    raw = json.dumps(payload).encode("utf-8")
    handler = object.__new__(browser_bridge._IncrementoBridgeHandler)
    handler.headers = {
        "Origin": origin,
        "X-Incremento-Token": "test-session",
        "X-Incremento-Protocol": "2",
        "Content-Length": str(len(raw)),
    }
    handler.path = browser_bridge.BRIDGE_PATH
    handler.rfile = io.BytesIO(raw)
    responses = []
    handler._send_json = lambda status, body: responses.append((status, body))
    handler.close_connection = False
    return handler, responses


def test_wire_request_cannot_delete_a_claimed_prepared_file(monkeypatch, tmp_path):
    unrelated = tmp_path / "user-document.txt"
    unrelated.write_text("preserve this document", encoding="utf-8")
    payload = {
        "batch": False,
        "browser_capture": False,
        "items": [{
            "kind": "writing",
            "url": "https://example.test/article",
            "markdown": "excerpt",
            "_prepared_pdf_path": str(unrelated),
            "_prepared_pdf_page_texts": ["forged index"],
            "_prepared_writing_markdown": True,
        }],
    }
    imports = []
    monkeypatch.setattr(browser_bridge, "_run_on_main_and_wait", lambda fn: fn())
    monkeypatch.setattr(browser_bridge, "_run_content_request_and_wait",
                        lambda request, **_kwargs: imports.append(request) or {"ok": True})
    handler, responses = _post(monkeypatch, payload)

    handler._do_POST()

    assert unrelated.exists(), "Wire input must not authorize deleting a local file"
    assert unrelated.read_text(encoding="utf-8") == "preserve this document"
    assert responses == [(200, {"ok": True})]
    item = imports[0]["items"][0]
    assert not any(key.startswith("_prepared_") for key in item)
    assert item["deck_name"] == "Topics"
    assert imports[0]["batch"] is True


@pytest.mark.parametrize("items", [[], [{"kind": "writing", "url": "https://example.test"}] * 101])
def test_wire_internal_shape_cannot_bypass_batch_limits(monkeypatch, items):
    payload = {"batch": False, "browser_capture": False, "items": items}
    dispatched = []
    monkeypatch.setattr(browser_bridge, "_run_on_main_and_wait", lambda fn: dispatched.append(fn))
    handler, responses = _post(monkeypatch, payload)

    handler._do_POST()

    assert responses[0][0] == 400
    assert responses[0][1]["error_code"] == "invalid_request"
    assert dispatched == []


@pytest.mark.parametrize("method,path,operation", [
    ("POST", browser_bridge.BRIDGE_PATH, "_add_content_request_on_main"),
    ("POST", browser_bridge.WEB_TRACK_PATH, "_update_web_card_on_main"),
    ("POST", browser_bridge.WEB_TRACK_MEDIA_PATH, "_update_web_card_media_on_main"),
    ("POST", browser_bridge.BROWSER_MEDIA_REF_PATH, "_save_browser_media_ref_on_main"),
    ("POST", browser_bridge.BROWSER_CAPTURE_META_PATH, "_browser_capture_meta_on_main"),
    ("POST", browser_bridge.BROWSER_MEDIA_REF_PATH + "?cardId=1", "_load_browser_media_ref_on_main"),
    ("GET", browser_bridge.BROWSER_CAPTURE_META_PATH, "_browser_capture_meta_on_main"),
    ("GET", browser_bridge.BROWSER_MEDIA_REF_PATH + "?cardId=1", "_load_browser_media_ref_on_main"),
])
def test_revoked_queued_request_cannot_access_the_next_profile(monkeypatch, method, path, operation):
    handler, responses = _post(monkeypatch, {"kind": "writing", "url": "https://example.test"})
    handler.path = path
    if operation in {"_browser_capture_meta_on_main", "_load_browser_media_ref_on_main"}:
        handler.headers["Content-Length"] = "0"
        handler.rfile = io.BytesIO(b"")
    accessed = []
    monkeypatch.setattr(browser_bridge, operation, lambda *args: accessed.append(args) or {"ok": True})

    def after_profile_switch(fn):
        # Profile close/start rotates the session while this callback is queued.
        monkeypatch.setattr(browser_bridge, "_bridge_token", "next-profile-session")
        return fn()

    monkeypatch.setattr(browser_bridge, "_run_on_main_and_wait", after_profile_switch)

    getattr(handler, "_do_" + method)()

    assert accessed == [], "A revoked request must not read or mutate the next profile"
    # Do not return 401: the companion automatically replays 401s with a new token.
    assert responses[0][0] == 400


def test_timed_out_main_thread_request_never_executes_later(monkeypatch):
    queued, mutations = [], []
    mw = SimpleNamespace(taskman=SimpleNamespace(run_on_main=queued.append))
    monkeypatch.setitem(sys.modules, "aqt", SimpleNamespace(mw=mw))

    with pytest.raises(TimeoutError):
        browser_bridge._run_on_main_and_wait(lambda: mutations.append("import"), timeout_sec=0)
    queued[0]()

    assert mutations == []


def test_revoked_queued_capture_never_starts_in_the_next_profile(monkeypatch):
    handler, responses = _post(monkeypatch, {
        "type": "browser_capture", "noteTypeName": "Basic", "url": "https://example.test",
    })
    dispatched = []

    def after_profile_switch(fn):
        monkeypatch.setattr(browser_bridge, "_bridge_token", "next-profile-session")
        fn()

    mw = SimpleNamespace(taskman=SimpleNamespace(run_on_main=after_profile_switch))
    monkeypatch.setitem(sys.modules, "aqt", SimpleNamespace(mw=mw))

    def dispatch(raw, success, failure, **kwargs):
        dispatched.append(raw)
        success({"ok": True})

    monkeypatch.setattr(browser_bridge, "_browser_capture_dispatch", dispatch)

    handler._do_POST()

    assert dispatched == []
    assert responses[0][0] == 400


def test_profile_revoked_during_pdf_preparation_cleans_only_owned_temporary_file(monkeypatch, tmp_path):
    staged = tmp_path / "prepared.pdf"
    handler, responses = _post(monkeypatch, {
        "kind": "pdf", "url": "https://example.test/book.pdf",
        "pdfBase64": base64.b64encode(b"%PDF-1.4\nfixture").decode("ascii"),
    })
    monkeypatch.setattr(browser_bridge, "_make_temp_pdf_path", lambda: str(staged))

    def extract(path):
        assert path == str(staged) and staged.exists()
        monkeypatch.setattr(browser_bridge, "_bridge_token", "next-profile-session")
        return ["page one"]

    imported = []
    monkeypatch.setattr(browser_bridge, "_extract_pdf_pages_text_off_main", extract)
    monkeypatch.setattr(browser_bridge, "_run_on_main_and_wait", lambda fn: fn())
    monkeypatch.setattr(browser_bridge, "_add_content_request_on_main", lambda request: imported.append(request))

    handler._do_POST()

    assert imported == []
    assert responses[0][0] == 400
    assert not staged.exists()


def test_main_thread_wait_preserves_success_and_operation_errors(monkeypatch):
    mw = SimpleNamespace(taskman=SimpleNamespace(run_on_main=lambda fn: fn()))
    monkeypatch.setitem(sys.modules, "aqt", SimpleNamespace(mw=mw))
    assert browser_bridge._run_on_main_and_wait(lambda: {"ok": True}, timeout_sec=0) == {"ok": True}

    def failed_operation():
        raise ValueError("invalid import")

    with pytest.raises(ValueError, match="invalid import"):
        browser_bridge._run_on_main_and_wait(failed_operation, timeout_sec=0)


def test_pdf_preparation_rejection_reports_the_backend_stage_without_creating_a_card(monkeypatch):
    handler, responses = _post(monkeypatch, {"kind": "pdf", "url": "https://example.org/article"})
    imported = []

    def rejected(*_args, **_kwargs):
        raise ValueError("The remote host resolves to a private or special address.")

    monkeypatch.setattr(browser_bridge, "prepare_add_content_request_off_main", rejected)
    monkeypatch.setattr(browser_bridge, "_run_content_request_and_wait", lambda *a, **k: imported.append(a))
    handler._do_POST()

    assert responses == [(400, {
        "ok": False, "error": "The remote host resolves to a private or special address.",
        "error_code": "invalid_request", "error_stage": "preparation",
    })]
    assert imported == []


def test_pdf_verification_failure_explains_recovery_and_cleans_the_staged_file(monkeypatch, tmp_path):
    from webpage_handoff import WebpageVerificationRequired

    staged = tmp_path / "prepared.pdf"
    handler, responses = _post(monkeypatch, {"kind": "pdf", "url": "https://example.org/article"})
    imported = []

    def needs_verification(*_args, **_kwargs):
        raise WebpageVerificationRequired()

    monkeypatch.setattr(browser_bridge, "_make_temp_pdf_path", lambda: str(staged))
    monkeypatch.setattr(browser_bridge, "_render_prepared_webpage_pdf", needs_verification)
    monkeypatch.setattr(browser_bridge, "_run_content_request_and_wait", lambda *a, **k: imported.append(a))
    handler._do_POST()

    assert responses == [(400, {
        "ok": False,
        "error": "This site requires verification. Complete the security check or sign-in in your browser, then use Capture opened page as PDF.",
        "error_code": "webpage_verification_required", "error_stage": "preparation",
    })]
    assert imported == []
    assert not staged.exists()
