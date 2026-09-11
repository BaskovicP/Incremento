import json
import types

from PyQt6.QtCore import QUrl

import web_dock


def _extract_record(*, card_id=42, url="https://example.com/guide", exact="passage"):
    return {
        "version": 1,
        "webCardId": card_id,
        "url": url,
        "anchor": {
            "version": 1,
            "exact": exact,
            "prefix": "before ",
            "suffix": " after",
            "startPath": [0],
            "startOffset": 0,
            "endPath": [0],
            "endOffset": len(exact),
        },
    }


def _snapshot_record(*, card_id=42, url="https://example.com/guide"):
    return {
        "version": 1,
        "webCardId": card_id,
        "url": url,
        "anchor": {
            "version": 1,
            "kind": "snapshot",
            "pageX": 140,
            "pageY": 580,
            "width": 200,
            "height": 100,
            "documentWidth": 1200,
            "documentHeight": 4000,
            "anchorPath": [0],
            "anchorTag": "article",
            "anchorXRatio": 350_000,
            "anchorYRatio": 400_000,
        },
    }


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


def test_web_extract_mark_is_staged_before_field_completion_and_kept_on_success(
    monkeypatch,
):
    fill_calls = []
    accepted = []
    rolled_back = []
    fake_add_card = types.SimpleNamespace(
        fill_dock_field=lambda *args, **kwargs: fill_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(web_dock, "__package__", "frontend")
    monkeypatch.setitem(__import__("sys").modules, "frontend.add_card_dock", fake_add_card)
    monkeypatch.setattr(
        web_dock,
        "_resolve_web_extraction",
        lambda callback: callback("passage", _extract_record()),
    )
    monkeypatch.setattr(
        web_dock,
        "_accept_web_extract_record",
        lambda record, *, expected_profile: accepted.append(
            (record, expected_profile)
        )
        or True,
    )
    monkeypatch.setattr(
        web_dock,
        "_remove_pending_web_extract_record",
        lambda record, *, expected_profile: rolled_back.append(
            (record, expected_profile)
        )
        or True,
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    controller = web_dock._WebDockController(
        web_dock._WebDockRuntime(current_card_id=42)
    )
    monkeypatch.setattr(controller, "citation", lambda *_args: "source")

    controller.extract_selection_to_field(0)

    assert accepted == [(_extract_record(), "Profile A")]
    assert len(fill_calls) == 1
    fill_calls[0][1]["on_complete"](True)
    assert accepted == [(_extract_record(), "Profile A")]
    assert rolled_back == []


def test_failed_web_field_fill_rolls_back_staged_anchor(monkeypatch):
    fill_calls = []
    accepted = []
    rolled_back = []
    fake_add_card = types.SimpleNamespace(
        fill_dock_field=lambda *args, **kwargs: fill_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(web_dock, "__package__", "frontend")
    monkeypatch.setitem(__import__("sys").modules, "frontend.add_card_dock", fake_add_card)
    monkeypatch.setattr(
        web_dock,
        "_resolve_web_extraction",
        lambda callback: callback("passage", _extract_record()),
    )
    monkeypatch.setattr(
        web_dock,
        "_accept_web_extract_record",
        lambda record, *, expected_profile: accepted.append(
            (record, expected_profile)
        )
        or True,
    )
    monkeypatch.setattr(
        web_dock,
        "_remove_pending_web_extract_record",
        lambda record, *, expected_profile: rolled_back.append(
            (record, expected_profile)
        )
        or True,
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    controller = web_dock._WebDockController(
        web_dock._WebDockRuntime(current_card_id=42)
    )
    monkeypatch.setattr(controller, "citation", lambda *_args: "source")

    controller.extract_selection_to_field(0)
    assert accepted == [(_extract_record(), "Profile A")]
    fill_calls[0][1]["on_complete"](False)

    assert rolled_back == [(_extract_record(), "Profile A")]


def test_web_extract_runtime_keeps_pending_anchor_if_add_card_adapter_fails(
    monkeypatch,
):
    runtime = web_dock._WebDockRuntime(current_card_id=42)
    fake_add_card = types.SimpleNamespace(
        append_pending_web_extract_record=lambda _record: (_ for _ in ()).throw(
            RuntimeError("adapter unavailable")
        ),
        pending_web_extract_records=lambda: [],
    )
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "__package__", "frontend")
    monkeypatch.setitem(__import__("sys").modules, "frontend.add_card_dock", fake_add_card)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: None,
    )

    assert web_dock._accept_web_extract_record(
        _extract_record(),
        expected_profile="Profile A",
    ) is True
    assert web_dock._pending_web_extract_records() == [
        web_dock.normalize_web_extract_record(_extract_record())
    ]


def test_accepting_extraction_stages_captured_native_geometry_immediately(monkeypatch):
    staged = []
    record = _extract_record()
    record["_nativeGeometry"] = {
        "rects": [{"x": 30, "y": 440, "width": 90, "height": 18}],
        "scrollX": 0,
        "scrollY": 400,
    }
    fake_add_card = types.SimpleNamespace(
        append_pending_web_extract_record=lambda _record: True,
    )
    monkeypatch.setattr(web_dock, "_runtime", web_dock._WebDockRuntime())
    monkeypatch.setattr(web_dock, "__package__", "frontend")
    monkeypatch.setitem(__import__("sys").modules, "frontend.add_card_dock", fake_add_card)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_stage_native_web_extraction_marker",
        lambda normalized, geometry: staged.append((normalized, geometry)),
        raising=False,
    )
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: None,
    )

    assert web_dock._accept_web_extract_record(
        record,
        expected_profile="Profile A",
    ) is True

    assert staged == [
        (
            web_dock.normalize_web_extract_record(record),
            record["_nativeGeometry"],
        )
    ]


def test_snapshot_grab_temporarily_hides_native_extraction_markers(monkeypatch):
    events = []

    class _Overlay:
        def isVisible(self):
            return True

        def hide(self):
            events.append("hide")

        def show(self):
            events.append("show")

        def raise_(self):
            events.append("raise")

    overlay = _Overlay()

    class _View:
        def grab(self, *args):
            events.append(("grab", args))
            assert events[0] == "hide"
            return "pixmap"

    monkeypatch.setattr(
        web_dock,
        "_runtime",
        web_dock._WebDockRuntime(extraction_overlay=overlay),
    )

    assert web_dock._grab_web_view_without_extraction_markers(
        _View(), "region"
    ) == "pixmap"
    assert events == ["hide", ("grab", ("region",)), "raise", "show"]


def test_rejected_field_removes_native_amber_marker_immediately(monkeypatch):
    record = web_dock.normalize_web_extract_record(_extract_record())
    removed = []

    class _Overlay:
        def remove_marker(self, marker_id):
            removed.append(marker_id)

    fake_add_card = types.SimpleNamespace(
        remove_pending_web_extract_record=lambda _record: False,
    )
    runtime = web_dock._WebDockRuntime(
        pending_extract_profile="Profile A",
        pending_extract_records=[record],
        extraction_overlay=_Overlay(),
    )
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "__package__", "frontend")
    monkeypatch.setitem(__import__("sys").modules, "frontend.add_card_dock", fake_add_card)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: None,
    )

    assert web_dock._remove_pending_web_extract_record(
        record,
        expected_profile="Profile A",
    ) is True
    assert removed == [record["anchor"]["id"]]


def test_stale_profile_completion_cannot_attach_pending_web_anchor(monkeypatch):
    appended = []
    fake_add_card = types.SimpleNamespace(
        append_pending_web_extract_record=lambda record: appended.append(record) or True,
    )
    monkeypatch.setattr(web_dock, "__package__", "frontend")
    monkeypatch.setitem(__import__("sys").modules, "frontend.add_card_dock", fake_add_card)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile B")

    accepted = web_dock._accept_web_extract_record(
        _extract_record(),
        expected_profile="Profile A",
    )

    assert accepted is False
    assert appended == []


def test_selection_capture_from_previous_bridge_card_cannot_attach_anchor(
    monkeypatch,
):
    resolved = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = types.SimpleNamespace(selectedText=lambda: "")
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    monkeypatch.setattr(
        web_dock,
        "_runtime",
        web_dock._WebDockRuntime(
            dock=types.SimpleNamespace(_view=view),
            current_card_id=42,
        ),
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    payload = {
        "cardId": 41,
        "url": "https://example.com/guide",
        "text": "passage",
        "anchor": _extract_record()["anchor"],
    }
    monkeypatch.setattr(
        web_dock,
        "_run_web_javascript",
        lambda current_page, script, callback=None: callback(payload),
    )

    web_dock._resolve_web_extraction(
        lambda text, record: resolved.append((text, record))
    )

    assert resolved == [("passage", None)]


def test_text_anchor_survives_qt_and_dom_whitespace_differences(monkeypatch):
    resolved = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = types.SimpleNamespace(
        selectedText=lambda: "First paragraph\u2029Second paragraph"
    )
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    monkeypatch.setattr(
        web_dock,
        "_runtime",
        web_dock._WebDockRuntime(
            dock=types.SimpleNamespace(_view=view),
            current_card_id=42,
        ),
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    payload = {
        "cardId": 42,
        "url": "https://example.com/guide",
        "text": "First paragraph  \n\n  Second paragraph",
        "anchor": {
            "version": 1,
            "exact": "First paragraphSecond paragraph",
            "prefix": "Before ",
            "suffix": " after",
            "startPath": [0],
            "startOffset": 0,
            "endPath": [1],
            "endOffset": 16,
        },
        "rects": [{"x": 20, "y": 500, "width": 180, "height": 34}],
        "scrollX": 0,
        "scrollY": 450,
    }
    monkeypatch.setattr(
        web_dock,
        "_run_web_javascript",
        lambda _page, _script, callback=None: callback(payload),
    )

    web_dock._resolve_web_extraction(
        lambda text, record: resolved.append((text, record))
    )

    assert resolved[0][0] == "First paragraph\nSecond paragraph"
    assert web_dock.normalize_web_extract_record(resolved[0][1]) is not None
    assert resolved[0][1]["_nativeGeometry"]["rects"] == payload["rects"]


def test_text_anchor_rejects_materially_different_native_selection(monkeypatch):
    resolved = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = types.SimpleNamespace(selectedText=lambda: "different selection")
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    monkeypatch.setattr(
        web_dock,
        "_runtime",
        web_dock._WebDockRuntime(
            dock=types.SimpleNamespace(_view=view),
            current_card_id=42,
        ),
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_run_web_javascript",
        lambda _page, _script, callback=None: callback(
            {
                "cardId": 42,
                "url": "https://example.com/guide",
                "text": "selected passage",
                "anchor": _extract_record()["anchor"],
                "rects": [{"x": 20, "y": 30, "width": 180, "height": 20}],
                "scrollX": 0,
                "scrollY": 0,
            }
        ),
    )

    web_dock._resolve_web_extraction(
        lambda text, record: resolved.append((text, record))
    )

    assert resolved == [("different selection", None)]


def test_snapshot_capture_resolves_viewport_rectangle_to_bounded_record(monkeypatch):
    resolved = []
    scripts = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = types.SimpleNamespace(bridge_nonce=lambda: "private-token")
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    monkeypatch.setattr(
        web_dock,
        "_runtime",
        web_dock._WebDockRuntime(
            dock=types.SimpleNamespace(_view=view),
            current_card_id=42,
        ),
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")

    def _run(current_page, script, callback=None):
        scripts.append((current_page, script))
        callback(
            {
                "cardId": 42,
                "url": "https://example.com/guide",
                "anchor": _snapshot_record()["anchor"],
            }
        )

    monkeypatch.setattr(web_dock, "_run_web_javascript", _run)

    web_dock._resolve_web_snapshot_anchor(
        types.SimpleNamespace(
            x=lambda: 140,
            y=lambda: 80,
            width=lambda: 200,
            height=lambda: 100,
        ),
        resolved.append,
    )

    expected_record = web_dock.normalize_web_extract_record(_snapshot_record())
    assert [web_dock.normalize_web_extract_record(item) for item in resolved] == [
        expected_record
    ]
    assert resolved[0]["_nativeGeometry"] == {
        "rects": [{"x": 140, "y": 580, "width": 200, "height": 100}],
        "scrollX": 0,
        "scrollY": 0,
    }
    assert scripts[0][0] is page
    assert "incrementoCaptureSnapshotAnchor" in scripts[0][1]
    assert "const INCREMENTO_CARD_ID" not in scripts[0][1]
    assert '"x": 140' in scripts[0][1]
    assert '"height": 100' in scripts[0][1]


def test_snapshot_field_marker_is_staged_before_fill_and_rolled_back_on_failure(
    monkeypatch,
):
    fill_calls = []
    accepted = []
    rolled_back = []
    fake_add_card = types.SimpleNamespace(
        fill_dock_field=lambda *args, **kwargs: fill_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        web_dock,
        "_accept_web_extract_record",
        lambda record, *, expected_profile: accepted.append(
            (record, expected_profile)
        )
        or True,
    )
    monkeypatch.setattr(
        web_dock,
        "_remove_pending_web_extract_record",
        lambda record, *, expected_profile: rolled_back.append(
            (record, expected_profile)
        )
        or True,
    )

    web_dock._fill_web_snapshot_field(
        fake_add_card,
        1,
        "capture.png",
        "https://example.com/guide",
        extract_record=_snapshot_record(),
        expected_profile="Profile A",
    )

    normalized = web_dock.normalize_web_extract_record(_snapshot_record())
    assert accepted == [(normalized, "Profile A")]
    assert fill_calls[0][0][:2] == (1, '<img src="capture.png">')
    fill_calls[0][1]["on_complete"](False)
    assert rolled_back == [(normalized, "Profile A")]


def test_snapshot_capture_drops_marker_after_card_changes(monkeypatch):
    resolved = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = types.SimpleNamespace(bridge_nonce=lambda: "private-token")
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(_view=view),
        current_card_id=42,
    )
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")

    def _run(_page, _script, callback=None):
        runtime.current_card_id = 99
        callback(
            {
                "cardId": 42,
                "url": "https://example.com/guide",
                "anchor": _snapshot_record()["anchor"],
            }
        )

    monkeypatch.setattr(web_dock, "_run_web_javascript", _run)

    web_dock._resolve_web_snapshot_anchor(
        types.SimpleNamespace(
            x=lambda: 140,
            y=lambda: 80,
            width=lambda: 200,
            height=lambda: 100,
        ),
        resolved.append,
    )

    assert resolved == [None]


def test_highlight_refresh_combines_saved_and_matching_pending_anchors(monkeypatch):
    scripts = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = object()
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(_view=view),
        current_card_id=42,
    )
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "get_web_extract_anchors",
        lambda *args, **kwargs: [_extract_record(exact="saved")["anchor"]],
    )
    monkeypatch.setattr(
        web_dock,
        "_pending_web_extract_records",
        lambda: [
            _extract_record(exact="pending"),
            _extract_record(card_id=99, exact="wrong card"),
            _extract_record(url="https://example.com/other", exact="wrong URL"),
        ],
    )
    monkeypatch.setattr(
        web_dock,
        "_run_web_javascript",
        lambda current_page, script, callback=None: scripts.append(
            (current_page, script)
        ),
    )

    web_dock._refresh_web_extraction_highlights()

    assert len(scripts) == 1
    assert scripts[0][0] is page
    assert "incrementoResolveExtractionRects" in scripts[0][1]
    assert "incrementoApplyExtractionHighlights" not in scripts[0][1]
    assert "const INCREMENTO_CARD_ID" not in scripts[0][1]
    assert '"exact": "saved"' in scripts[0][1]
    assert '"exact": "pending"' in scripts[0][1]
    assert "wrong card" not in scripts[0][1]
    assert "wrong URL" not in scripts[0][1]


def test_highlight_refresh_sends_resolved_geometry_to_native_overlay(monkeypatch):
    applied = []
    saved_anchor = web_dock.normalize_web_extract_anchor(
        _extract_record(exact="saved")["anchor"]
    )
    pending_record = web_dock.normalize_web_extract_record(
        _snapshot_record()
    )

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = object()
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(_view=view),
        current_card_id=42,
    )
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "get_web_extract_anchors",
        lambda *args, **kwargs: [saved_anchor],
    )
    monkeypatch.setattr(
        web_dock,
        "_pending_web_extract_records",
        lambda: [pending_record],
    )
    monkeypatch.setattr(
        web_dock,
        "_set_native_web_extraction_markers",
        lambda markers, *, scroll_x, scroll_y: applied.append(
            (markers, scroll_x, scroll_y)
        ),
        raising=False,
    )

    def _run(current_page, script, callback=None):
        assert current_page is page
        assert "incrementoResolveExtractionRects" in script
        assert "incrementoApplyExtractionHighlights" not in script
        assert callback is not None
        callback(
            {
                "cardId": 42,
                "url": "https://example.com/guide",
                "scrollX": 12,
                "scrollY": 480,
                "markers": [
                    {
                        "id": saved_anchor["id"],
                        "state": "saved",
                        "kind": "text",
                        "rects": [
                            {"x": 102, "y": 500, "width": 80, "height": 16}
                        ],
                    },
                    {
                        "id": pending_record["anchor"]["id"],
                        "state": "pending",
                        "kind": "snapshot",
                        "rects": [
                            {"x": 220, "y": 780, "width": 200, "height": 100}
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(web_dock, "_run_web_javascript", _run)

    web_dock._refresh_web_extraction_highlights()

    assert applied == [
        (
            [
                {
                    "id": saved_anchor["id"],
                    "state": "saved",
                    "kind": "text",
                    "rects": [
                        {"x": 102.0, "y": 500.0, "width": 80.0, "height": 16.0}
                    ],
                },
                {
                    "id": pending_record["anchor"]["id"],
                    "state": "pending",
                    "kind": "snapshot",
                    "rects": [
                        {
                            "x": 220.0,
                            "y": 780.0,
                            "width": 200.0,
                            "height": 100.0,
                        }
                    ],
                },
            ],
            12.0,
            480.0,
        )
    ]


def test_stale_geometry_callback_cannot_paint_a_new_web_card(monkeypatch):
    callbacks = []
    applied = []

    class _Url:
        def toString(self):
            return "https://example.com/guide"

    page = object()
    view = types.SimpleNamespace(page=lambda: page, url=lambda: _Url())
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(_view=view),
        current_card_id=42,
    )
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "get_web_extract_anchors",
        lambda *args, **kwargs: [_extract_record()["anchor"]],
    )
    monkeypatch.setattr(web_dock, "_pending_web_extract_records", lambda: [])
    monkeypatch.setattr(
        web_dock,
        "_set_native_web_extraction_markers",
        lambda *args, **kwargs: applied.append((args, kwargs)),
        raising=False,
    )
    monkeypatch.setattr(
        web_dock,
        "_run_web_javascript",
        lambda _page, _script, callback=None: callbacks.append(callback),
    )

    web_dock._refresh_web_extraction_highlights()
    runtime.current_card_id = 99
    callbacks[0](
        {
            "cardId": 42,
            "url": "https://example.com/guide",
            "scrollX": 0,
            "scrollY": 0,
            "markers": [],
        }
    )

    assert applied == []


def test_native_geometry_rejects_forged_ids_states_and_unbounded_rects():
    normalized = web_dock._normalize_native_web_extraction_geometry(
        {
            "scrollX": 0,
            "scrollY": 400,
            "markers": [
                {
                    "id": "trusted",
                    "state": "pending",
                    "kind": "text",
                    "rects": [
                        {"x": 10, "y": 420, "width": 50, "height": 16},
                        {"x": float("nan"), "y": 0, "width": 10, "height": 10},
                    ],
                },
                {
                    "id": "forged",
                    "state": "pending",
                    "kind": "text",
                    "rects": [{"x": 0, "y": 0, "width": 10, "height": 10}],
                },
                {
                    "id": "wrong-state",
                    "state": "saved",
                    "kind": "text",
                    "rects": [{"x": 0, "y": 0, "width": 10, "height": 10}],
                },
            ],
        },
        allowed_markers={
            "trusted": ("pending", "text"),
            "wrong-state": ("pending", "text"),
        },
    )

    assert normalized == (
        [
            {
                "id": "trusted",
                "state": "pending",
                "kind": "text",
                "rects": [
                    {"x": 10.0, "y": 420.0, "width": 50.0, "height": 16.0}
                ],
            }
        ],
        0.0,
        400.0,
    )


def test_note_add_persists_anchor_against_captured_url_after_navigation(monkeypatch):
    saved = []
    refreshes = []
    original_url = "https://example.com/original"
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(isVisible=lambda: True),
        current_card_id=42,
    )
    controller = web_dock._WebDockController(runtime)
    monkeypatch.setattr(
        controller,
        "current_display_url",
        lambda: "https://example.com/navigated",
    )
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_pending_web_extract_records",
        lambda: [
            _extract_record(url=original_url, exact="first"),
            _extract_record(url=original_url, exact="second"),
        ],
    )
    monkeypatch.setattr(
        web_dock,
        "add_web_card_source",
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: refreshes.append(True),
    )
    monkeypatch.setattr(controller, "refresh_cards_panel", lambda: None)
    note = types.SimpleNamespace(
        id=777,
        fields=["Front", "Back"],
        _incremento_add_card_draft_owner=True,
    )

    controller.on_add_cards_did_add_note(note)

    assert len(saved) == 1
    args, kwargs = saved[0]
    assert args[2:5] == (42, original_url, 777)
    assert [anchor["exact"] for anchor in kwargs["anchors"]] == [
        "first",
        "second",
    ]
    assert refreshes == [True]


def test_note_add_promotes_runtime_pending_anchor_and_releases_amber_state(
    monkeypatch,
):
    record = web_dock.normalize_web_extract_record(_extract_record())
    promoted = []

    class _Overlay:
        def set_marker_state(self, marker_id, state):
            promoted.append((marker_id, state))

    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(isVisible=lambda: True),
        current_card_id=42,
        pending_extract_profile="Profile A",
        pending_extract_records=[record],
        extraction_overlay=_Overlay(),
    )
    controller = web_dock._WebDockController(runtime)
    saved = []
    monkeypatch.setattr(web_dock, "_runtime", runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_pending_web_extract_records",
        lambda: list(runtime.pending_extract_records),
    )
    monkeypatch.setattr(
        web_dock,
        "add_web_card_source",
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: None,
    )
    monkeypatch.setattr(controller, "refresh_cards_panel", lambda: None)
    note = types.SimpleNamespace(
        id=777,
        fields=["Front", "Back"],
        _incremento_add_card_draft_owner=True,
    )

    controller.on_add_cards_did_add_note(note)

    assert len(saved) == 1
    assert runtime.pending_extract_records == []
    assert promoted == [(record["anchor"]["id"], "saved")]


def test_unrelated_note_cannot_claim_another_add_drafts_web_anchors(monkeypatch):
    saved = []
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(isVisible=lambda: True),
        current_card_id=42,
    )
    controller = web_dock._WebDockController(runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_pending_web_extract_records",
        lambda: [_extract_record()],
    )
    monkeypatch.setattr(
        web_dock,
        "add_web_card_source",
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )

    controller.on_add_cards_did_add_note(
        types.SimpleNamespace(id=777, fields=["Unrelated", "Note"])
    )

    assert saved == []


def test_failed_anchor_persistence_warns_and_schedules_pending_marker_cleanup(
    monkeypatch,
):
    messages = []
    refreshes = []
    runtime = web_dock._WebDockRuntime(
        dock=types.SimpleNamespace(isVisible=lambda: True),
        current_card_id=42,
    )
    controller = web_dock._WebDockController(runtime)
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(
        web_dock,
        "_pending_web_extract_records",
        lambda: [_extract_record()],
    )
    monkeypatch.setattr(
        web_dock,
        "add_web_card_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    monkeypatch.setattr(web_dock, "tooltip", messages.append)
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: refreshes.append(True),
    )
    note = types.SimpleNamespace(
        id=777,
        fields=["Front", "Back"],
        _incremento_add_card_draft_owner=True,
    )

    controller.on_add_cards_did_add_note(note)

    assert messages == [
        "Incremento: the note was added, but its Web extraction marker could not be saved."
    ]
    assert refreshes == [True]


def test_note_add_uses_anchor_snapshot_when_add_card_cleanup_hook_ran_first(
    monkeypatch,
):
    saved = []
    controller = web_dock._WebDockController(web_dock._WebDockRuntime())
    monkeypatch.setattr(web_dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(web_dock, "_pending_web_extract_records", lambda: [])
    monkeypatch.setattr(
        web_dock,
        "add_web_card_source",
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )
    monkeypatch.setattr(
        web_dock,
        "_schedule_web_extraction_highlight_refresh",
        lambda: None,
    )
    monkeypatch.setattr(controller, "refresh_cards_panel", lambda: None)
    note = types.SimpleNamespace(
        id=777,
        fields=["Front", "Back"],
        _incremento_add_card_draft_owner=True,
        _incremento_web_extract_records=[_extract_record()],
    )

    controller.on_add_cards_did_add_note(note)

    assert len(saved) == 1
    assert saved[0][0][2:5] == (
        42,
        "https://example.com/guide",
        777,
    )
