from types import SimpleNamespace

from browser_capture_source import render_browser_capture_source


def card_with_source(url="https://example.com/article", title="Page <title>"):
    return SimpleNamespace(note=lambda: {
        "Incremento_Source_Type": "Browser Capture",
        "Incremento_Source_Link": url,
        "Incremento_Source_Title": title,
    })


def test_browser_capture_card_displays_clickable_escaped_source_without_changing_note():
    card = card_with_source()
    result = render_browser_capture_source("<p>Question</p>", card, "reviewQuestion")
    assert '<a href="https://example.com/article"' in result
    assert 'rel="noopener noreferrer"' in result
    assert "Page &lt;title&gt;" in result
    assert "<p>Question</p>" in result
    assert render_browser_capture_source(result, card, "reviewAnswer") == result


def test_source_renderer_rejects_unsafe_urls_and_leaves_other_cards_alone():
    assert render_browser_capture_source("Question", card_with_source("javascript:alert(1)"), "reviewQuestion") == "Question"
    assert render_browser_capture_source("Question", SimpleNamespace(note=lambda: {}), "reviewQuestion") == "Question"
