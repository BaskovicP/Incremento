import pytest

import reader_links


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.test/path?q=1#part", "https://example.test/path?q=1#part"),
        ("HTTP://example.test", "HTTP://example.test"),
        ("javascript:alert(1)", None),
        ("file:///etc/passwd", None),
        ("data:text/html,owned", None),
        ("mailto:user@example.test", None),
        ("https://user:secret@example.test/", None),
        ("https://example.test/line\nbreak", None),
        (r"https:\\example.test\\spoofed", None),
        ("https:///missing-host", None),
        ("", None),
    ],
)
def test_external_reader_links_allow_only_bounded_uncredentialed_http_urls(raw, expected):
    assert reader_links.normalize_external_reader_url(raw) == expected


def test_external_reader_link_opening_uses_only_the_normalized_url(monkeypatch):
    opened = []
    monkeypatch.setattr(
        reader_links,
        "_open_normalized_external_url",
        lambda url: opened.append(url) or True,
    )

    assert reader_links.open_external_reader_link("https://example.test/docs") is True
    assert reader_links.open_external_reader_link("javascript:alert(1)") is False
    assert opened == ["https://example.test/docs"]
