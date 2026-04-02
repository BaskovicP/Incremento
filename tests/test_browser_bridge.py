from pathlib import Path

from browser_bridge import (
    build_writing_markdown,
    download_pdf_from_url,
    normalize_add_content_payload,
    normalize_add_content_batch_payload,
    normalize_add_content_request,
    normalize_update_web_card_payload,
    url_looks_like_pdf,
)


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
    assert payload["html"] == "<html></html>"


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
            "pdfBase64": "JVBERi0xLjQK",
            "pdfFilename": "file.pdf",
        }
    )
    assert payload["pdf_base64"] == "JVBERi0xLjQK"
    assert payload["pdf_filename"] == "file.pdf"


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


def test_url_looks_like_pdf_checks_url_path():
    assert url_looks_like_pdf("https://example.com/files/doc.pdf")
    assert url_looks_like_pdf("https://example.com/files/doc.PDF?download=1")
    assert not url_looks_like_pdf("https://example.com/article")


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
