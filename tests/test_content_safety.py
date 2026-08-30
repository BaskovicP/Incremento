import pytest

from content_safety import (
    external_plain_text,
    external_plain_text_to_anki_html,
    external_plain_text_to_markdown,
    normalize_external_http_url,
)


def test_external_plain_text_to_anki_html_escapes_active_markup():
    value = '<img src=x onerror="alert(1)">\nsecond & line'

    rendered = external_plain_text_to_anki_html(value)

    assert rendered == (
        "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
        "<br>second &amp; line"
    )


def test_external_plain_text_removes_control_bytes_and_is_bounded():
    assert external_plain_text("a\x00b\tc\nd", max_chars=4) == "ab\tc"


def test_external_plain_text_to_markdown_disables_markup_and_raw_html():
    rendered = external_plain_text_to_markdown(
        '<img src="file:///private"> ![remote](https://tracker.test/x.png)'
    )

    assert "<img" not in rendered
    assert "![remote](" not in rendered
    assert "&lt;img" in rendered
    assert r"\!\[remote\]\(https://tracker.test/x.png\)" in rendered


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///tmp/private",
        "https://user:secret@example.com/",
        "https://example.com/a b",
        "https://example.com/\nheader",
    ],
)
def test_external_http_url_rejects_unsafe_forms(url):
    with pytest.raises(ValueError):
        normalize_external_http_url(url)


def test_external_http_url_normalizes_scheme_and_host():
    assert (
        normalize_external_http_url("HTTPS://Example.COM:443/path?q=1#part")
        == "https://example.com:443/path?q=1#part"
    )
