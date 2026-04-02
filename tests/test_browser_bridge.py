from browser_bridge import (
    build_writing_markdown,
    normalize_add_content_payload,
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
