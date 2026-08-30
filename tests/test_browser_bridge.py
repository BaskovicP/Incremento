import base64
import browser_bridge
import db
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys
from note_metadata import (
    INCREMENTO_IMPORTED_AT_FIELD,
    INCREMENTO_PARENT_CARD_ID_FIELD,
    INCREMENTO_PARENT_FIELD,
    INCREMENTO_SOURCE_AUTHOR_FIELD,
    INCREMENTO_SOURCE_LINK_FIELD,
    INCREMENTO_SOURCE_TITLE_FIELD,
    INCREMENTO_SOURCE_TYPE_FIELD,
)

from browser_bridge import (
    _create_browser_capture_note_on_main,
    _load_browser_media_ref_on_main,
    _save_browser_media_ref_on_main,
    _sanitize_media_filename,
    build_writing_markdown,
    download_pdf_from_url,
    normalize_add_content_payload,
    normalize_add_content_batch_payload,
    normalize_add_content_request,
    normalize_browser_media_ref_payload,
    normalize_browser_media_ref_query,
    normalize_browser_capture_payload,
    normalize_update_web_card_payload,
    normalize_update_web_card_media_payload,
    url_looks_like_pdf,
)


def _bare_bridge_handler(headers=None, *, origin=""):
    handler = object.__new__(browser_bridge._IncrementoBridgeHandler)
    resolved_headers = dict(headers or {})
    if origin:
        resolved_headers["Origin"] = origin
    handler.headers = resolved_headers
    handler.client_address = ("127.0.0.1", 12345)
    handler.close_connection = False
    return handler


def test_bridge_binds_one_exact_extension_origin(monkeypatch):
    first = "chrome-extension://" + "a" * 32
    second = "chrome-extension://" + "b" * 32
    monkeypatch.setattr(browser_bridge, "_allowed_extension_origin", "")

    handler = _bare_bridge_handler(origin=first)
    assert handler._request_origin_allowed(allow_unbound=True) is True
    assert handler._bind_handshake_origin() is True
    assert _bare_bridge_handler(origin=first)._request_origin_allowed() is True
    assert _bare_bridge_handler(origin=second)._request_origin_allowed() is False


def test_bridge_never_authorizes_an_originless_handshake(monkeypatch):
    monkeypatch.setattr(browser_bridge, "_allowed_extension_origin", "")
    handler = _bare_bridge_handler()

    assert handler._request_origin_allowed(allow_unbound=True) is False
    assert handler._bind_handshake_origin() is False


def test_bridge_requires_matching_protocol_and_token(monkeypatch):
    monkeypatch.setattr(browser_bridge, "_bridge_token", "secret")

    assert _bare_bridge_handler(
        {"X-Incremento-Token": "secret", "X-Incremento-Protocol": "2"}
    )._request_authenticated() is True
    assert _bare_bridge_handler(
        {"X-Incremento-Token": "wrong", "X-Incremento-Protocol": "2"}
    )._request_authenticated() is False
    assert _bare_bridge_handler(
        {"X-Incremento-Token": "secret", "X-Incremento-Protocol": "1"}
    )._request_authenticated() is False


def test_bridge_unbound_valid_origin_requests_fresh_handshake(monkeypatch):
    monkeypatch.setattr(browser_bridge, "_allowed_extension_origin", "")
    origin = "chrome-extension://" + "a" * 32
    post_handler = _bare_bridge_handler(origin=origin)
    post_handler.path = browser_bridge.BRIDGE_PATH
    post_handler.rfile = type(
        "_Body",
        (),
        {"read": lambda *_args: (_ for _ in ()).throw(AssertionError("read"))},
    )()
    responses = []
    post_handler._send_json = lambda status, payload: responses.append((status, payload))

    post_handler._do_POST()

    get_handler = _bare_bridge_handler(origin=origin)
    get_handler.path = browser_bridge.BROWSER_CAPTURE_META_PATH
    get_handler._send_json = lambda status, payload: responses.append((status, payload))
    get_handler._do_GET()

    expected = (401, {"ok": False, "error": "Bridge authorization required."})
    assert responses == [expected, expected]


def test_bridge_rejects_a_different_bound_extension_origin(monkeypatch):
    monkeypatch.setattr(
        browser_bridge,
        "_allowed_extension_origin",
        "chrome-extension://" + "a" * 32,
    )
    handler = _bare_bridge_handler(origin="chrome-extension://" + "b" * 32)
    handler.path = browser_bridge.BRIDGE_PATH
    responses = []
    handler._send_json = lambda status, payload: responses.append((status, payload))

    handler._do_POST()

    assert responses == [(403, {"ok": False, "error": "Origin not allowed."})]


def test_bridge_rejects_oversized_body_before_reading(monkeypatch):
    handler = _bare_bridge_handler(
        {"Content-Length": str(browser_bridge._MAX_REQUEST_BYTES + 1)}
    )
    handler.path = browser_bridge.BRIDGE_PATH
    handler.rfile = type("_Body", (), {"read": lambda *_args: (_ for _ in ()).throw(AssertionError("read"))})()
    responses = []
    handler._request_origin_allowed = lambda: True
    handler._request_authenticated = lambda: True
    handler._send_json = lambda status, payload: responses.append((status, payload))

    handler._do_POST()

    assert responses[0][0] == 413
    assert handler.close_connection is True


def test_bridge_rejects_transfer_encoded_bodies_before_reading():
    handler = _bare_bridge_handler(
        {"Content-Length": "4", "Transfer-Encoding": "chunked"}
    )
    handler.path = browser_bridge.BRIDGE_PATH
    handler.rfile = type(
        "_Body",
        (),
        {"read": lambda *_args: (_ for _ in ()).throw(AssertionError("read"))},
    )()
    responses = []
    handler._request_origin_allowed = lambda: True
    handler._request_authenticated = lambda: True
    handler._send_json = lambda status, payload: responses.append((status, payload))

    handler._do_POST()

    assert responses == [
        (400, {"ok": False, "error": "Transfer-Encoding is not supported."})
    ]
    assert handler.close_connection is True
from webpage_markdown import convert_webpage_html_to_markdown
from writing_manager import build_writing_relpath, add_writing_card, _stored_writing_title


def test_build_writing_markdown_includes_source_and_selection():
    md = build_writing_markdown(
        "Article Title",
        "https://example.com/article",
        "Quoted passage",
    )
    assert md.startswith("# Article Title\n")
    assert "## Selected text" in md
    assert "Quoted passage" in md


def test_build_writing_markdown_includes_page_markdown_body():
    md = build_writing_markdown(
        "Article Title",
        "https://example.com/article",
        page_markdown="## Body\n\nMain content",
    )
    assert md.startswith("# Article Title\n")
    assert "## Body" in md
    assert "Main content" in md


def test_build_writing_markdown_treats_page_selection_as_literal_text():
    md = build_writing_markdown(
        "<img src=x> ![title](https://tracker.test/title.png)",
        "https://example.com/article",
        "![selection](file:///private.png) <script>alert(1)</script>",
    )

    assert "<img" not in md
    assert "<script" not in md
    assert "![title](" not in md
    assert "![selection](" not in md
    assert "&lt;script&gt;" in md


def test_normalize_add_content_payload_defaults_and_aliases():
    payload = normalize_add_content_payload(
        {
            "kind": "web",
            "url": "https://example.com/a",
            "title": "  Example   Title  ",
            "deckName": "  ",
            "tags": ["alpha", "alpha", " beta "],
            "html": "<html></html>",
        }
    )
    assert payload["kind"] == "webpage"
    assert payload["title"] == "Example Title"
    assert payload["deck_name"] == "Topics"
    assert payload["tags"] == ["alpha", "beta"]
    assert payload["priority"] == 50.0
    assert payload["parent_card_id"] is None
    assert payload["html"] == "<html></html>"
    assert payload["media_seconds"] == 0.0


def test_normalize_add_content_payload_accepts_parent_card_id():
    payload = normalize_add_content_payload(
        {
            "kind": "webpage",
            "url": "https://example.com/a",
            "title": "Example",
            "parentCardId": "123",
        }
    )
    assert payload["parent_card_id"] == 123


def test_normalize_add_content_payload_accepts_webpage_media_timing():
    payload = normalize_add_content_payload(
        {
            "kind": "webpage",
            "url": "https://example.com/article",
            "title": "Article",
            "mediaUrl": "https://cdn.example.com/video.mp4",
            "mediaTitle": "  Embedded clip  ",
            "mediaSeconds": "126.24",
        }
    )
    assert payload["kind"] == "webpage"
    assert payload["media_url"] == "https://cdn.example.com/video.mp4"
    assert payload["media_title"] == "Embedded clip"
    assert payload["media_seconds"] == 126.2


def test_normalize_add_content_payload_ignores_non_http_webpage_media_url():
    payload = normalize_add_content_payload(
        {
            "kind": "webpage",
            "url": "https://example.com/article",
            "mediaUrl": "blob:https://example.com/not-storable",
            "mediaSeconds": 44,
        }
    )
    assert payload["media_url"] == ""
    assert payload["media_seconds"] == 44.0


def test_normalize_add_content_payload_accepts_webpage_markdown_fields():
    payload = normalize_add_content_payload(
        {
            "kind": "writing",
            "url": "https://example.com/article",
            "title": "Example",
            "writingMode": "webpage_markdown",
            "pageContentScope": "full",
            "preferredFilename": "example-123.md",
            "html": "<html><body><main>Body</main></body></html>",
        }
    )
    assert payload["kind"] == "writing"
    assert payload["writing_mode"] == "webpage_markdown"
    assert payload["page_content_scope"] == "full"
    assert payload["preferred_filename"] == "example-123.md"
    assert "main" in payload["html"].lower()


def test_normalize_add_content_payload_accepts_video_alias():
    payload = normalize_add_content_payload(
        {
            "kind": "youtube",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "  Demo video  ",
        }
    )
    assert payload["kind"] == "video"
    assert payload["title"] == "Demo video"


def test_normalize_add_content_payload_keeps_pdf_base64_payload():
    payload = normalize_add_content_payload(
        {
            "kind": "pdf",
            "url": "https://example.com/file.pdf",
            "title": "Example PDF",
            "priority": "12.34567",
            "pdfBase64": "JVBERi0xLjQK",
            "pdfFilename": "file.pdf",
        }
    )
    assert payload["priority"] == 12.3457
    assert payload["pdf_base64"] == "JVBERi0xLjQK"
    assert payload["pdf_filename"] == "file.pdf"


def test_prepare_add_content_request_decodes_pdf_base64_off_main(monkeypatch):
    monkeypatch.setattr(browser_bridge, "_extract_pdf_pages_text_off_main", lambda path: ["page one"])
    request = normalize_add_content_request(
        {
            "kind": "pdf",
            "url": "https://example.com/file.pdf",
            "title": "Example PDF",
            "pdfBase64": base64.b64encode(b"%PDF-1.4\nfake\n").decode("ascii"),
        }
    )

    prepared = browser_bridge.prepare_add_content_request_off_main(request)
    pdf_path = Path(prepared["items"][0][browser_bridge._PREPARED_PDF_PATH_KEY])
    try:
        assert pdf_path.read_bytes().startswith(b"%PDF-")
        assert prepared["items"][0][browser_bridge._PREPARED_PDF_PAGE_TEXTS_KEY] == ["page one"]
    finally:
        browser_bridge.cleanup_prepared_add_content_request(prepared)

    assert not pdf_path.exists()


def test_prepare_add_content_request_downloads_pdf_url_off_main(monkeypatch):
    calls = []

    def fake_download(url, dest_path):
        calls.append((url, dest_path))
        Path(dest_path).write_bytes(b"%PDF-1.7\nfake\n")

    monkeypatch.setattr(browser_bridge, "download_pdf_from_url", fake_download)
    monkeypatch.setattr(browser_bridge, "_extract_pdf_pages_text_off_main", lambda path: [])
    request = normalize_add_content_request(
        {
            "kind": "pdf",
            "url": "https://example.com/file.pdf",
            "title": "Example PDF",
        }
    )

    prepared = browser_bridge.prepare_add_content_request_off_main(request)
    pdf_path = Path(prepared["items"][0][browser_bridge._PREPARED_PDF_PATH_KEY])
    try:
        assert calls == [("https://example.com/file.pdf", str(pdf_path))]
        assert pdf_path.read_bytes().startswith(b"%PDF-")
    finally:
        browser_bridge.cleanup_prepared_add_content_request(prepared)

    assert not pdf_path.exists()


def test_prepare_add_content_request_builds_webpage_markdown_off_main(monkeypatch):
    calls = []

    def fake_convert(url, html, *, title, content_scope):
        calls.append((url, html, title, content_scope))
        return {"title": "Resolved Title", "markdown": "## Body\n\nText"}

    monkeypatch.setattr(browser_bridge, "convert_webpage_html_to_markdown", fake_convert)
    request = normalize_add_content_request(
        {
            "kind": "writing",
            "url": "https://example.com/article",
            "title": "Original Title",
            "writingMode": "webpage_markdown",
            "pageContentScope": "full",
            "html": "<html><body>Text</body></html>",
        }
    )

    prepared = browser_bridge.prepare_add_content_request_off_main(request)

    assert calls == [
        (
            "https://example.com/article",
            "<html><body>Text</body></html>",
            "Original Title",
            "full",
        )
    ]
    assert prepared["items"][0]["title"] == "Resolved Title"
    assert prepared["items"][0]["markdown"].startswith("# Resolved Title\n")
    assert "## Body" in prepared["items"][0]["markdown"]


def test_normalize_add_content_payload_rejects_invalid_priority():
    try:
        normalize_add_content_payload(
            {
                "kind": "webpage",
                "url": "https://example.com",
                "title": "Example",
                "priority": "100.0001",
            }
        )
        assert False, "Expected normalize_add_content_payload to reject out-of-range priorities"
    except ValueError as exc:
        assert "Priority" in str(exc)


def test_normalize_add_content_batch_payload_merges_defaults():
    payload = normalize_add_content_batch_payload(
        {
            "deckName": "Research",
            "items": [
                {
                    "kind": "pdf",
                    "url": "https://example.com/guide.pdf",
                    "title": "Guide",
                    "tags": "alpha beta alpha",
                },
                {
                    "kind": "writing",
                    "url": "https://example.com/post",
                    "title": "Post",
                    "tags": ["draft", "draft", "ideas"],
                },
            ],
        }
    )
    assert [item["deck_name"] for item in payload] == ["Research", "Research"]
    assert payload[0]["tags"] == ["alpha", "beta"]
    assert payload[1]["tags"] == ["draft", "ideas"]


def test_normalize_add_content_batch_payload_inherits_parent_card_id():
    payload = normalize_add_content_batch_payload(
        {
            "parentCardId": 123,
            "items": [
                {"kind": "pdf", "url": "https://example.com/guide.pdf", "title": "Guide"},
                {
                    "kind": "writing",
                    "url": "https://example.com/post",
                    "title": "Post",
                    "parentCardId": 456,
                },
            ],
        }
    )
    assert [item["parent_card_id"] for item in payload] == [123, 456]


def test_normalize_add_content_request_detects_batch_mode():
    payload = normalize_add_content_request(
        {
            "items": [
                {
                    "kind": "webpage",
                    "url": "https://example.com",
                    "title": "Example",
                }
            ]
        }
    )
    assert payload["batch"] is True
    assert len(payload["items"]) == 1
    assert payload["items"][0]["kind"] == "webpage"


def test_normalize_add_content_request_detects_browser_capture_mode():
    payload = normalize_add_content_request(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "deckName": "Default",
            "fieldMappings": {"selectedTextField": "Front"},
        }
    )
    assert payload["batch"] is False
    assert payload["browser_capture"] is True
    assert payload["items"][0]["note_type_name"] == "Basic"


def test_normalize_browser_capture_payload_accepts_snapshots_and_mappings():
    image_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
    payload = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "  Example Article  ",
            "noteTypeName": "Basic",
            "deckName": "Research",
            "selectedText": "  Selected text  ",
            "fieldMappings": {
                "titleField": "Back",
                "selectedTextField": "Front",
                "urlField": "Back",
                "snapshotField": "Extra",
            },
            "snapshots": [
                {
                    "mimeType": "image/png",
                    "filename": "capture.png",
                    "base64": image_b64,
                }
            ],
        }
    )
    assert payload["note_type_name"] == "Basic"
    assert payload["deck_name"] == "Research"
    assert payload["selected_text"] == "Selected text"
    assert payload["field_mappings"]["title_field"] == "Back"
    assert payload["field_mappings"]["snapshot_field"] == "Extra"
    assert payload["parent_card_id"] is None
    assert payload["snapshots"][0]["bytes"].startswith(b"\x89PNG")


def test_normalize_browser_capture_payload_accepts_parent_card_id():
    payload = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "parentCardId": 123,
            "fieldMappings": {"titleField": "Front"},
        }
    )
    assert payload["parent_card_id"] == 123


def test_normalize_browser_capture_payload_rejects_unknown_snapshot_mime_type():
    try:
        normalize_browser_capture_payload(
            {
                "type": "browser_capture",
                "url": "https://example.com/article",
                "title": "Example",
                "noteTypeName": "Basic",
                "deckName": "Default",
                "snapshots": [{"mimeType": "image/jpeg", "base64": "abcd"}],
            }
        )
        assert False, "Expected normalize_browser_capture_payload to reject non-PNG snapshot payloads"
    except ValueError as exc:
        assert "PNG" in str(exc)


def test_url_looks_like_pdf_checks_url_path():
    assert url_looks_like_pdf("https://example.com/files/doc.pdf")
    assert url_looks_like_pdf("https://example.com/files/doc.PDF?download=1")
    assert not url_looks_like_pdf("https://example.com/article")


def test_convert_webpage_html_to_markdown_prefers_main_content():
    result = convert_webpage_html_to_markdown(
        "https://example.com/article",
        """
        <html>
          <head><title>Example Article</title></head>
          <body>
            <header>Site header</header>
            <nav>Navigation links</nav>
            <article>
              <h1>Article heading</h1>
              <p>Paragraph one.</p>
              <p>Paragraph two with <a href="/more">a link</a>.</p>
            </article>
            <footer>Footer text</footer>
          </body>
        </html>
        """,
        content_scope="main",
    )
    assert result["title"] == "Example Article"
    assert "Article heading" in result["markdown"]
    assert "Paragraph one." in result["markdown"]
    assert "[a link](<https://example.com/more>)" in result["markdown"]
    assert "Navigation links" not in result["markdown"]
    assert "Footer text" not in result["markdown"]


def test_convert_webpage_html_to_markdown_blocks_active_and_auto_loaded_targets():
    result = convert_webpage_html_to_markdown(
        "https://example.com/article",
        """
        <main>
          <p>Literal ![tracking](file:///private.png)</p>
          <a href="javascript:alert(1)">Unsafe link</a>
          <img src="file:///private.png" alt="private">
          <img src="https://cdn.example.com/image.png" alt="remote">
        </main>
        """,
    )

    markdown = result["markdown"]
    assert "![tracking](" not in markdown
    assert "javascript:" not in markdown
    assert "[Image: private]" not in markdown
    assert "![remote]" not in markdown
    assert "[Image: remote](<https://cdn.example.com/image.png>)" in markdown


def test_build_writing_relpath_uses_uuid_suffix_for_repeated_titles():
    path1 = build_writing_relpath("Repeated Title")
    path2 = build_writing_relpath("Repeated Title")
    assert path1.startswith("writing/Repeated_Title-")
    assert path2.startswith("writing/Repeated_Title-")
    assert path1.endswith(".md")
    assert path2.endswith(".md")
    assert path1 != path2


def test_stored_writing_title_uses_visible_duplicate_suffix():
    assert _stored_writing_title("Repeated Title", 0) == "Repeated Title"
    assert _stored_writing_title("Repeated Title", 1) == "Repeated Title [2]"
    assert _stored_writing_title("Repeated Title", 2) == "Repeated Title [3]"


def test_add_writing_card_uses_visible_duplicate_title(monkeypatch):
    class FakeNote(dict):
        def __init__(self):
            super().__init__()
            self.id = 501
            self.tags = []
            self._note_type = {"did": 0}

        def note_type(self):
            return self._note_type

        def add_tag(self, tag):
            self.tags.append(tag)

    note1 = FakeNote()
    note2 = FakeNote()

    col = MagicMock()
    col.models.by_name.return_value = {"name": "Incremento Writing"}
    col.decks.by_name.return_value = {"id": 9}
    col.new_note.side_effect = [note1, note2]
    col.add_note.side_effect = [0, 1]
    col.find_cards.return_value = [777]

    monkeypatch.setattr("writing_manager.ensure_writing_note_type", lambda _col: None)
    monkeypatch.setattr("writing_manager.build_writing_relpath", lambda **_kwargs: "writing/example.md")
    monkeypatch.setattr("writing_manager.ensure_writing_file", lambda *_args, **_kwargs: "/tmp/example.md")

    card_id = add_writing_card(
        "/tmp/incremento-test",
        col,
        "Repeated Title",
        deck_name="Topics",
        tags=["alpha"],
        initial_markdown="# Repeated Title\n\n",
        preferred_filename="example.md",
    )

    assert card_id == 777
    assert note1["Title"] == "Repeated Title"
    assert note2["Title"] == "Repeated Title [2]"
    assert note2["Markdown_File"] == "writing/example.md"
    assert note2[INCREMENTO_SOURCE_TYPE_FIELD] == "Writing"
    assert note2[INCREMENTO_SOURCE_LINK_FIELD] == "writing/example.md"


def test_normalize_update_web_card_payload_accepts_valid_payload():
    payload = normalize_update_web_card_payload(
        {
            "cardId": 123,
            "url": "https://example.com/next/page",
            "title": "  New title  ",
        }
    )
    assert payload == {
        "card_id": 123,
        "url": "https://example.com/next/page",
        "title": "New title",
    }


def test_normalize_update_web_card_payload_rejects_invalid_card_id():
    try:
        normalize_update_web_card_payload(
            {
                "cardId": 0,
                "url": "https://example.com/next/page",
            }
        )
        assert False, "Expected normalize_update_web_card_payload to reject invalid card IDs"
    except ValueError as exc:
        assert "cardId" in str(exc)


def test_normalize_update_web_card_media_payload_accepts_valid_payload():
    payload = normalize_update_web_card_media_payload(
        {
            "cardId": 123,
            "url": "https://example.com/next/page",
            "mediaUrl": "https://player.vimeo.com/video/148751763",
            "mediaTitle": "  Demo clip  ",
            "seconds": 83.2,
        }
    )
    assert payload == {
        "card_id": 123,
        "url": "https://example.com/next/page",
        "media_url": "https://player.vimeo.com/video/148751763",
        "media_title": "Demo clip",
        "seconds": 83.2,
    }


def test_normalize_update_web_card_media_payload_allows_missing_media_url():
    payload = normalize_update_web_card_media_payload(
        {
            "cardId": 123,
            "url": "https://example.com/next/page",
            "mediaUrl": "blob:https://example.com/not-storable",
            "seconds": 44,
        }
    )
    assert payload["media_url"] == ""
    assert payload["seconds"] == 44.0


def test_normalize_update_web_card_media_payload_rejects_non_positive_seconds():
    try:
        normalize_update_web_card_media_payload(
            {
                "cardId": 123,
                "url": "https://example.com/next/page",
                "seconds": 0,
            }
        )
        assert False, "Expected normalize_update_web_card_media_payload to reject non-positive seconds"
    except ValueError as exc:
        assert "seconds" in str(exc)


def test_normalize_browser_media_ref_payload_accepts_valid_payload():
    payload = normalize_browser_media_ref_payload(
        {
            "cardId": 123,
            "pageUrl": "https://example.com/article",
            "mediaUrl": "https://player.vimeo.com/video/148751763",
            "mediaTitle": "  Example clip  ",
            "seconds": 0,
        }
    )
    assert payload == {
        "card_id": 123,
        "page_url": "https://example.com/article",
        "media_url": "https://player.vimeo.com/video/148751763",
        "media_title": "Example clip",
        "seconds": 0.0,
    }


def test_normalize_browser_media_ref_payload_allows_invalid_media_url_as_blank():
    payload = normalize_browser_media_ref_payload(
        {
            "cardId": 123,
            "pageUrl": "https://example.com/article",
            "mediaUrl": "blob:https://example.com/not-storable",
            "seconds": 12.4,
        }
    )
    assert payload["media_url"] == ""
    assert payload["seconds"] == 12.4


def test_normalize_browser_media_ref_payload_rejects_negative_seconds():
    try:
        normalize_browser_media_ref_payload(
            {
                "cardId": 123,
                "pageUrl": "https://example.com/article",
                "seconds": -1,
            }
        )
        assert False, "Expected normalize_browser_media_ref_payload to reject negative seconds"
    except ValueError as exc:
        assert "seconds" in str(exc)


def test_normalize_browser_media_ref_query_accepts_card_id():
    payload = normalize_browser_media_ref_query({"cardId": ["123"]})
    assert payload == {"card_id": 123}


def test_download_pdf_from_url_writes_pdf(monkeypatch, tmp_path):
    class _Resp:
        headers = {"Content-Type": "application/pdf"}

        def __init__(self):
            self.done = False

        def read(self, _size=-1):
            if self.done:
                return b""
            self.done = True
            return b"%PDF-1.4\nfake\n"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("browser_bridge.open_public_http", lambda *_args, **_kwargs: _Resp())

    dest = tmp_path / "downloaded.pdf"
    download_pdf_from_url("https://example.com/file.pdf", str(dest))
    assert dest.read_bytes().startswith(b"%PDF-")


def test_download_pdf_from_url_rejects_non_pdf(monkeypatch, tmp_path):
    class _Resp:
        headers = {"Content-Type": "text/html"}

        def __init__(self):
            self.done = False

        def read(self, _size=-1):
            if self.done:
                return b""
            self.done = True
            return b"<html>nope</html>"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("browser_bridge.open_public_http", lambda *_args, **_kwargs: _Resp())

    dest = tmp_path / "downloaded.pdf"
    try:
        download_pdf_from_url("https://example.com/file.pdf", str(dest))
        assert False, "Expected download_pdf_from_url to reject non-PDF responses"
    except RuntimeError as exc:
        assert "did not return a PDF" in str(exc)
    assert not Path(dest).exists()


def test_download_pdf_from_url_accepts_pdf_url_with_generic_content_type(monkeypatch, tmp_path):
    class _Resp:
        headers = {"Content-Type": "application/octet-stream"}

        def __init__(self):
            self.done = False

        def read(self, _size=-1):
            if self.done:
                return b""
            self.done = True
            return b"\n\n%PDF-1.7\nfake\n"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("browser_bridge.open_public_http", lambda *_args, **_kwargs: _Resp())

    dest = tmp_path / "downloaded.pdf"
    download_pdf_from_url("https://example.com/file.pdf", str(dest))
    assert dest.read_bytes().startswith(b"\n\n%PDF-")


def test_sanitize_media_filename_truncates_long_stem_before_uuid_suffix():
    filename = _sanitize_media_filename(f'{"c" * 140}.png', "fallback")
    stem = Path(filename).stem
    base, _, suffix = stem.rpartition("-")
    assert len(base) <= 80
    assert len(suffix) == 32


def test_create_browser_capture_note_populates_mapped_fields(monkeypatch):
    image_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
    normalized = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "deckName": "Research",
            "tags": ["alpha"],
            "priority": 12.5,
            "selectedText": "Selected\ntext",
            "fieldMappings": {
                "titleField": "Back",
                "selectedTextField": "Front",
                "urlField": "Front",
                "snapshotField": "Back",
            },
            "snapshots": [
                {
                    "mimeType": "image/png",
                    "filename": "capture.png",
                    "base64": image_b64,
                }
            ],
        }
    )

    class FakeNote(dict):
        def __init__(self):
            super().__init__()
            self.id = 444
            self.tags = []
            self._note_type = {"did": 0}

        def note_type(self):
            return self._note_type

        def add_tag(self, tag):
            self.tags.append(tag)

    note = FakeNote()
    col = MagicMock()
    col.models.by_name.return_value = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    col.decks.by_name.return_value = {"id": 9}
    col.new_note.return_value = note
    col.find_cards.return_value = [321]
    col.media.add_file.return_value = "capture.png"

    mw = SimpleNamespace(col=col)
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)

    priority_calls = []
    priority_module = MagicMock()
    priority_module.set_priority.side_effect = lambda addon_dir, profile, card_id, priority: priority_calls.append(
        (addon_dir, card_id, priority)
    )
    monkeypatch.setattr("browser_bridge._addon_dir", "/tmp/incremento-test")
    monkeypatch.setitem(sys.modules, "priority_manager", priority_module)

    result = _create_browser_capture_note_on_main(normalized)

    assert result["ok"] is True
    assert result["cardId"] == 321
    assert "Selected<br>text" in note["Front"]
    assert "https://example.com/article" in note["Front"]
    assert "Source:" not in note["Front"]
    assert "Example" in note["Back"]
    assert '<img src="capture.png">' in note["Back"]
    assert note[INCREMENTO_SOURCE_TYPE_FIELD] == "Browser Capture"
    assert note[INCREMENTO_SOURCE_TITLE_FIELD] == "Example"
    assert note[INCREMENTO_SOURCE_LINK_FIELD] == "https://example.com/article"
    assert note.tags == ["Incremento", "alpha"]
    assert priority_calls == [("/tmp/incremento-test", 321, 12.5)]


def test_create_browser_capture_note_can_insert_only_source_url(monkeypatch):
    normalized = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "deckName": "Research",
            "fieldMappings": {
                "urlField": "Back",
            },
        }
    )

    class FakeNote(dict):
        def __init__(self):
            super().__init__()
            self.id = 445
            self.tags = []
            self._note_type = {"did": 0}

        def note_type(self):
            return self._note_type

        def add_tag(self, tag):
            self.tags.append(tag)

    note = FakeNote()
    col = MagicMock()
    col.models.by_name.return_value = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    col.decks.by_name.return_value = {"id": 9}
    col.new_note.return_value = note
    col.find_cards.return_value = [654]

    mw = SimpleNamespace(col=col)
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)

    priority_module = MagicMock()
    monkeypatch.setitem(sys.modules, "priority_manager", priority_module)
    monkeypatch.setattr("browser_bridge._addon_dir", "/tmp/incremento-test")

    result = _create_browser_capture_note_on_main(normalized)

    assert result["ok"] is True
    assert note["Back"] == "https://example.com/article"
    assert note[INCREMENTO_SOURCE_LINK_FIELD] == "https://example.com/article"


def test_create_browser_capture_note_records_parent_and_syncs_tree(monkeypatch):
    normalized = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "deckName": "Research",
            "parentCardId": 123,
            "fieldMappings": {
                "titleField": "Front",
            },
        }
    )

    class FakeNote(dict):
        def __init__(self):
            super().__init__()
            self.id = 446
            self.tags = []
            self._note_type = {"did": 0}

        def note_type(self):
            return self._note_type

        def add_tag(self, tag):
            self.tags.append(tag)

    note = FakeNote()
    col = MagicMock()
    col.models.by_name.return_value = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    col.decks.by_name.return_value = {"id": 9}
    col.new_note.return_value = note
    col.find_cards.return_value = [654]

    mw = SimpleNamespace(col=col)
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)
    monkeypatch.setitem(sys.modules, "priority_manager", MagicMock())
    monkeypatch.setattr("browser_bridge._addon_dir", "/tmp/incremento-test")

    sync_calls = []
    monkeypatch.setattr(
        browser_bridge,
        "_sync_parent_child_knowledge_tree_on_main",
        lambda **kwargs: sync_calls.append(kwargs) or {"linked_count": 2},
    )

    result = _create_browser_capture_note_on_main(normalized)

    assert result["ok"] is True
    assert note[INCREMENTO_PARENT_CARD_ID_FIELD] == "123"
    assert sync_calls == [
        {
            "parent_card_id": 123,
            "child_card_id": 654,
            "node_kind": "item",
        }
    ]
    assert result["knowledgeTree"] == {"linked_count": 2}


def test_browser_capture_meta_hides_incremento_metadata_fields(monkeypatch):
    col = MagicMock()
    col.models.all.return_value = [
        {
            "name": "Basic",
            "flds": [
                {"name": "Front"},
                {"name": "Back"},
                {"name": INCREMENTO_SOURCE_LINK_FIELD},
                {"name": INCREMENTO_PARENT_FIELD},
            ],
        }
    ]
    col.decks.all_names_and_ids.return_value = [SimpleNamespace(name="Topics")]

    mw = SimpleNamespace(col=col)
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)

    result = browser_bridge._browser_capture_meta_on_main()

    assert result["ok"] is True
    assert result["noteTypes"] == [{"name": "Basic", "fields": ["Front", "Back"]}]


def test_create_browser_capture_note_uses_unique_title_for_first_field(monkeypatch):
    normalized = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "deckName": "Research",
            "fieldMappings": {
                "titleField": "Front",
            },
        }
    )

    class FakeNote(dict):
        def __init__(self):
            super().__init__()
            self.id = 445
            self.tags = []
            self._note_type = {"did": 0}

        def note_type(self):
            return self._note_type

        def add_tag(self, tag):
            self.tags.append(tag)

    note = FakeNote()
    col = MagicMock()
    col.models.by_name.return_value = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    col.decks.by_name.return_value = {"id": 9}
    col.new_note.return_value = note
    col.find_cards.return_value = [654]
    monkeypatch.setattr(browser_bridge, "_browser_capture_unique_label_suffix", lambda: "20260405-120000-abcd1234")

    mw = SimpleNamespace(col=col)
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)

    priority_module = MagicMock()
    monkeypatch.setitem(sys.modules, "priority_manager", priority_module)
    monkeypatch.setattr("browser_bridge._addon_dir", "/tmp/incremento-test")

    result = _create_browser_capture_note_on_main(normalized)

    assert result["ok"] is True
    assert note["Front"] == "Example [snapshot 20260405-120000-abcd1234]"


def test_create_browser_capture_note_raises_clear_duplicate_error(monkeypatch):
    normalized = normalize_browser_capture_payload(
        {
            "type": "browser_capture",
            "url": "https://example.com/article",
            "title": "Example",
            "noteTypeName": "Basic",
            "deckName": "Research",
            "selectedText": "Duplicate front field",
            "fieldMappings": {
                "selectedTextField": "Front",
            },
        }
    )

    class FakeNote(dict):
        def __init__(self):
            super().__init__()
            self.id = 446
            self.tags = []
            self._note_type = {"did": 0}

        def note_type(self):
            return self._note_type

        def add_tag(self, tag):
            self.tags.append(tag)

    note = FakeNote()
    col = MagicMock()
    col.models.by_name.return_value = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    col.decks.by_name.return_value = {"id": 9}
    col.new_note.return_value = note
    col.add_note.return_value = 0

    mw = SimpleNamespace(col=col)
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)

    try:
        _create_browser_capture_note_on_main(normalized)
        assert False, "Expected duplicate browser capture note creation to raise"
    except ValueError as exc:
        assert "first field 'Front'" in str(exc)
        assert "Duplicate front field" in str(exc)


def test_save_browser_media_ref_on_main_persists_latest_reference(monkeypatch, tmp_path):
    class _Card:
        id = 123
        nid = 456

    class _Col:
        def get_card(self, card_id):
            assert card_id == 123
            return _Card()

    mw = SimpleNamespace(col=_Col())
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)
    monkeypatch.setattr(browser_bridge, "_addon_dir", str(tmp_path))
    monkeypatch.setitem(sys.modules, "db", db)

    result = _save_browser_media_ref_on_main(
        {
            "cardId": 123,
            "pageUrl": "https://example.com/article",
            "mediaUrl": "https://player.example.com/video",
            "mediaTitle": "Example clip",
            "seconds": 83.2,
        }
    )

    assert result["ok"] is True
    assert result["cardId"] == 123
    assert result["timeText"] == "1:23"
    stored = db.get_card_browser_media_ref(str(tmp_path), "TestProfile", 123)
    assert stored["page_url"] == "https://example.com/article"
    assert stored["media_url"] == "https://player.example.com/video"
    assert stored["media_title"] == "Example clip"
    assert stored["media_seconds"] == 83.2


def test_save_browser_media_ref_on_main_routes_web_cards_to_web_progress(monkeypatch, tmp_path):
    class _Card:
        id = 123
        nid = 456

    class _Note:
        mid = 789

    class _Models:
        def get(self, mid):
            assert mid == 789
            return {"name": "Incremento Web"}

    class _Col:
        models = _Models()

        def get_card(self, card_id):
            assert card_id == 123
            return _Card()

        def get_note(self, note_id):
            assert note_id == 456
            return _Note()

    mw = SimpleNamespace(col=_Col())
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)
    monkeypatch.setattr(browser_bridge, "_addon_dir", str(tmp_path))
    monkeypatch.setitem(sys.modules, "db", db)

    result = _save_browser_media_ref_on_main(
        {
            "cardId": 123,
            "pageUrl": "https://example.com/article",
            "mediaUrl": "https://player.example.com/video",
            "mediaTitle": "Example clip",
            "seconds": 83.2,
        }
    )

    assert result["ok"] is True
    stored_ref = db.get_card_browser_media_ref(str(tmp_path), "TestProfile", 123)
    assert stored_ref["media_seconds"] == 0.0

    import web_manager

    progress = web_manager.get_web_progress(str(tmp_path), "TestProfile", 123)
    assert progress["url"] == "https://example.com/article"
    assert progress["media_url"] == "https://player.example.com/video"
    assert progress["media_title"] == "Example clip"
    assert progress["media_seconds"] == 83.2


def test_load_browser_media_ref_on_main_reads_web_progress_for_web_cards(monkeypatch, tmp_path):
    import web_manager

    web_manager.set_web_media_progress(
        str(tmp_path),
        "TestProfile",
        123,
        url="https://example.com/article",
        media_url="https://player.example.com/video",
        media_title="Example clip",
        media_seconds=83.2,
        media_updated_at=1000,
    )

    class _Card:
        id = 123
        nid = 456

    class _Note:
        mid = 789

    class _Models:
        def get(self, mid):
            assert mid == 789
            return {"name": "Incremento Web"}

    class _Col:
        models = _Models()

        def get_card(self, card_id):
            assert card_id == 123
            return _Card()

        def get_note(self, note_id):
            assert note_id == 456
            return _Note()

    mw = SimpleNamespace(col=_Col())
    fake_aqt = MagicMock()
    fake_aqt.mw = mw
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)
    monkeypatch.setattr(browser_bridge, "_addon_dir", str(tmp_path))
    monkeypatch.setitem(sys.modules, "db", db)

    result = _load_browser_media_ref_on_main(123)

    assert result["ok"] is True
    assert result["hasReference"] is True
    assert result["pageUrl"] == "https://example.com/article"
    assert result["mediaUrl"] == "https://player.example.com/video"
    assert result["mediaTitle"] == "Example clip"
    assert result["seconds"] == 83.2
    assert result["timeText"] == "1:23"


def test_load_browser_media_ref_on_main_returns_empty_state_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_bridge, "_addon_dir", str(tmp_path))
    monkeypatch.setitem(sys.modules, "db", db)

    result = _load_browser_media_ref_on_main(999)

    assert result["ok"] is True
    assert result["cardId"] == 999
    assert result["hasReference"] is False
    assert result["timeText"] == ""
