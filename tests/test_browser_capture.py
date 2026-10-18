"""Browser capture contracts: inert formatting, source navigation, and identity."""

import pytest

from browser_capture import capture_fingerprint, capture_source_url, legacy_capture_matches, selection_html


def test_selection_keeps_paragraphs_lists_and_emphasis_without_page_code():
    assert selection_html(
        "One important point\nTwo",
        '<p class="page" onclick="alert(1)">One <strong>important</strong> point</p>'
        '<nav>Menu</nav><ul><li>Two</li></ul><script>alert(1)</script>'
        '<img src="https://tracker.test/pixel"><iframe>Hidden</iframe>',
    ) == "<p>One <strong>important</strong> point</p><ul><li>Two</li></ul>"


def test_selection_falls_back_to_escaped_edited_text_and_cleans_blank_lines():
    assert selection_html("  <unsafe>  \r\n\r\n\r\nNext\u00a0 line  ") == (
        "&lt;unsafe&gt;<br><br>Next line"
    )
    assert selection_html("Changed", "<b>Original</b>") == "Changed"


def test_selection_preserves_code_spacing_and_balances_malformed_markup():
    assert selection_html("a\n  b", "<pre>a\n  b</pre>") == "<pre>a\n  b</pre>"
    assert selection_html("hello", "<p><b>hello") == "<p><b>hello</b></p>"


@pytest.mark.parametrize("markup", ["x" * 200_001, "<b>" * 65 + "x"])
def test_selection_rejects_oversized_or_excessively_nested_markup(markup):
    with pytest.raises(ValueError):
        selection_html("x", markup)


def test_passage_link_preserves_anchor_and_encodes_delimiters():
    assert capture_source_url("https://example.com/a#section:~:text=old", "a-b, c & 中文") == (
        "https://example.com/a#section:~:text=a%2Db%2C%20c%20%26%20%E4%B8%AD%E6%96%87"
    )
    assert capture_source_url("https://example.com/a#section", "") == "https://example.com/a#section"


def test_multiline_passage_links_use_start_and_end_in_separate_blocks():
    assert capture_source_url("https://example.com", "First paragraph\nSecond paragraph") == (
        "https://example.com#:~:text=First%20paragraph,Second%20paragraph"
    )


def test_long_passage_link_terms_do_not_overlap_and_keep_word_boundaries():
    from urllib.parse import unquote

    text = " ".join(f"word{index}" for index in range(40))
    directive = unquote(capture_source_url("https://example.com", text).split("text=", 1)[1])
    start, end = directive.split(",")
    assert text.startswith(start) and text.endswith(end)
    assert text.index(end) >= len(start)
    assert start.split()[-1] in text.split()


def test_passage_link_single_long_word_does_not_invent_partial_word_ranges():
    text = "a" * 200
    assert capture_source_url("https://example.com", text).endswith("text=" + text)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://user:pass@example.com", "file:///tmp/a"])
def test_passage_links_reject_unsafe_sources(url):
    with pytest.raises(ValueError):
        capture_source_url(url, "text")


def test_capture_identity_ignores_formatting_and_text_directives_but_keeps_page_identity():
    first = capture_fingerprint("https://example.com/a#part", "A  passage\nwith text")
    assert first == capture_fingerprint("https://example.com/a#part:~:text=old", "A passage with text")
    assert first != capture_fingerprint("https://example.com/b", "A passage with text")
    assert first != capture_fingerprint("https://example.com/a#part", "Another passage")
    assert capture_fingerprint("https://example.com/a", "") == ""


def test_legacy_duplicate_check_does_not_treat_source_metadata_as_an_excerpt():
    note = {"Front": "Different excerpt", "Incremento_Source_Type": "Browser Capture",
            "Incremento_Source_Link": "https://example.com", "Incremento_Source_Title": "Page title"}
    assert not legacy_capture_matches(note, "https://example.com", "Page title")
