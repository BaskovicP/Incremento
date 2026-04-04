import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

from browser_bridge import (
    _create_browser_capture_note_on_main,
    build_writing_markdown,
    download_pdf_from_url,
    normalize_add_content_payload,
    normalize_add_content_batch_payload,
    normalize_add_content_request,
    normalize_browser_capture_payload,
    normalize_update_web_card_payload,
    url_looks_like_pdf,
)
from webpage_markdown import convert_webpage_html_to_markdown
from writing_manager import build_writing_relpath


def test_build_writing_markdown_includes_source_and_selection():
    md = build_writing_markdown(
        "Article Title",
        "https://example.com/article",
        "Quoted passage",
    )
    assert md.startswith("# Article Title\n")
    assert "Source: https://example.com/article" in md
    assert "## Selected text" in md
    assert "Quoted passage" in md


def test_build_writing_markdown_includes_page_markdown_body():
    md = build_writing_markdown(
        "Article Title",
        "https://example.com/article",
        page_markdown="## Body\n\nMain content",
    )
    assert md.startswith("# Article Title\n")
    assert "Source: https://example.com/article" in md
    assert "## Body" in md
    assert "Main content" in md


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
    assert payload["html"] == "<html></html>"


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
    assert payload["field_mappings"]["snapshot_field"] == "Extra"
    assert payload["snapshots"][0]["bytes"].startswith(b"\x89PNG")


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
    assert "[a link](https://example.com/more)" in result["markdown"]
    assert "Navigation links" not in result["markdown"]
    assert "Footer text" not in result["markdown"]


def test_build_writing_relpath_uses_uuid_suffix_for_repeated_titles():
    path1 = build_writing_relpath("Repeated Title")
    path2 = build_writing_relpath("Repeated Title")
    assert path1.startswith("writing/Repeated_Title-")
    assert path2.startswith("writing/Repeated_Title-")
    assert path1.endswith(".md")
    assert path2.endswith(".md")
    assert path1 != path2


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


def test_download_pdf_from_url_writes_pdf(monkeypatch, tmp_path):
    class _Resp:
        headers = {"Content-Type": "application/pdf"}

        def read(self):
            return b"%PDF-1.4\nfake\n"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("browser_bridge.urlopen", lambda *_args, **_kwargs: _Resp())

    dest = tmp_path / "downloaded.pdf"
    download_pdf_from_url("https://example.com/file.pdf", str(dest))
    assert dest.read_bytes().startswith(b"%PDF-")


def test_download_pdf_from_url_rejects_non_pdf(monkeypatch, tmp_path):
    class _Resp:
        headers = {"Content-Type": "text/html"}

        def read(self):
            return b"<html>nope</html>"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("browser_bridge.urlopen", lambda *_args, **_kwargs: _Resp())

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

        def read(self):
            return b"\n\n%PDF-1.7\nfake\n"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("browser_bridge.urlopen", lambda *_args, **_kwargs: _Resp())

    dest = tmp_path / "downloaded.pdf"
    download_pdf_from_url("https://example.com/file.pdf", str(dest))
    assert dest.read_bytes().startswith(b"\n\n%PDF-")


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
    assert "Source:" in note["Front"]
    assert '<img src="capture.png">' in note["Back"]
    assert note.tags == ["Incremento", "alpha"]
    assert priority_calls == [("/tmp/incremento-test", 321, 12.5)]
