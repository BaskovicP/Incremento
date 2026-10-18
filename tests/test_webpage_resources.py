"""Ordinary webpage PDFs retain inert styles/images without browser networking."""

import base64
import io
from types import SimpleNamespace
from threading import Barrier

from bs4 import BeautifulSoup
import pytest

import network_safety
import webpage_resources


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1kAAAAASUVORK5CYII="
)


@pytest.fixture
def assets(monkeypatch):
    files, calls = {}, []

    def validate(url):
        return network_safety.validate_public_http_url(
            url, resolver=lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))]
        )

    def open_asset(request, *, timeout):
        url = request.full_url
        calls.append(url)
        mime, body, *redirect = files[url]
        response = io.BytesIO(body)
        response.headers = {"Content-Type": mime}
        response.geturl = lambda: redirect[0] if redirect else url
        return response

    monkeypatch.setattr(webpage_resources, "validate_public_http_url", validate)
    monkeypatch.setattr(webpage_resources, "open_public_http", open_asset)
    return SimpleNamespace(files=files, calls=calls)


def test_print_snapshot_keeps_styles_nested_fonts_and_lazy_images_offline(assets):
    assets.files.update({
        "https://example.test/css/site.css": ("text/css", b'@import "print.css" print; article {color: #123456}'),
        "https://example.test/css/print.css": ("text/css", b'@font-face {font-family: Article; src: url(../fonts/article.woff2)}'),
        "https://example.test/fonts/article.woff2": ("font/woff2", b"wOF2fixture"),
        "https://example.test/photo.png": ("image/png", PNG),
    })
    html = '''<html><head><link rel="stylesheet" href="/css/site.css" media="print"></head>
    <body><article>Article text<img data-src="/photo.png" src="placeholder.png"
    srcset="/large.png 2000w" loading="lazy"></article></body></html>'''

    result = webpage_resources.build_offline_webpage_html(html, "https://example.test/article")
    soup = BeautifulSoup(result, "html.parser")

    assert soup.article.get_text() == "Article text"
    assert soup.style["media"] == "print"
    assert "color: #123456" in soup.style.string
    imported = soup.style.string.split("data:text/css;base64,", 1)[1].split('"', 1)[0]
    imported_css = base64.b64decode(imported).decode()
    assert "data:font/woff2;base64," in imported_css
    assert soup.img["src"] == "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert "srcset" not in soup.img.attrs
    assert "loading" not in soup.img.attrs
    assert "https://example.test/large.png" not in assets.calls


def test_asset_redirects_rebase_css_and_repeated_images_are_fetched_once(assets):
    assets.files.update({
        "https://example.test/style.css": ("text/css", b'body {background: url(photo.png)}', "https://cdn.test/assets/site.css"),
        "https://cdn.test/assets/photo.png": ("image/png", PNG),
    })
    html = '<link rel="stylesheet" href="/style.css"><img src="https://cdn.test/assets/photo.png"><img src="https://cdn.test/assets/photo.png">'

    soup = BeautifulSoup(webpage_resources.build_offline_webpage_html(html, "https://example.test/article"), "html.parser")

    assert "data:image/png;base64," in soup.style.string
    assert len(soup.find_all("img")) == 2
    assert soup.find_all("img")[0]["src"] == soup.find_all("img")[1]["src"]
    assert assets.calls.count("https://cdn.test/assets/photo.png") == 1


def test_snapshot_removes_active_content_and_never_fetches_private_or_local_assets(assets):
    html = '''<base href="http://127.0.0.1/"><meta http-equiv="refresh" content="0;url=file:///secret">
    <script src="https://example.test/run.js"></script><iframe src="https://example.test/frame"></iframe>
    <object data="file:///secret"></object><p onclick="alert(1)">Keep this</p>
    <img src="http://127.0.0.1/private"><img src="file:///secret"><img src="https://user:pass@example.test/secret">
    <link rel="stylesheet" href="http://169.254.169.254/metadata">'''

    soup = BeautifulSoup(webpage_resources.build_offline_webpage_html(html, "https://example.test/article"), "html.parser")

    assert soup.p.get_text() == "Keep this"
    assert "onclick" not in soup.p.attrs
    assert not soup.find_all(["script", "iframe", "object", "base"])
    assert not soup.find("meta", attrs={"http-equiv": "refresh"})
    assert not any(img.get("src") for img in soup.find_all("img"))
    assert assets.calls == []
    assert "default-src 'none'" in soup.find("meta", attrs={"http-equiv": "Content-Security-Policy"})["content"]


def test_unavailable_wrong_mime_and_oversized_assets_do_not_drop_article_text(assets, monkeypatch):
    monkeypatch.setattr(webpage_resources, "MAX_RESOURCE_BYTES", 100)
    assets.files.update({
        "https://example.test/not-css": ("text/html", b"<script>bad</script>"),
        "https://example.test/large.png": ("image/png", PNG * 3),
    })
    html = '<link rel="stylesheet" href="/not-css"><p>Keep all article text</p><img src="/missing.png"><img src="/large.png">'

    soup = BeautifulSoup(webpage_resources.build_offline_webpage_html(html, "https://example.test/article"), "html.parser")

    assert soup.p.get_text() == "Keep all article text"
    assert not any(img.get("src") for img in soup.find_all("img"))
    assert "<script>" not in str(soup)


def test_asset_count_budget_and_recursive_import_cycles_are_bounded(assets, monkeypatch):
    monkeypatch.setattr(webpage_resources, "MAX_RESOURCES", 2)
    assets.files.update({
        "https://example.test/a.css": ("text/css", b'@import "a.css"; p {color: green}'),
        "https://example.test/a.png": ("image/png", PNG),
        "https://example.test/b.png": ("image/png", PNG),
    })

    result = webpage_resources.build_offline_webpage_html(
        '<link rel="stylesheet" href="a.css"><p>Text</p><img src="a.png"><img src="b.png">',
        "https://example.test/",
    )

    assert len(assets.calls) == 2
    assert assets.calls.count("https://example.test/a.css") == 1
    assert "color: green" in result


def test_total_asset_budget_is_enforced(assets, monkeypatch):
    monkeypatch.setattr(webpage_resources, "MAX_TOTAL_RESOURCE_BYTES", len(PNG))
    assets.files.update({
        "https://example.test/a.png": ("image/png", PNG),
        "https://example.test/b.png": ("image/png", PNG),
    })

    result = webpage_resources.build_offline_webpage_html(
        '<img src="a.png"><img src="b.png">', "https://example.test/"
    )

    soup = BeautifulSoup(result, "html.parser")
    assert sum(bool(img.get("src")) for img in soup.find_all("img")) == 1


def test_fonts_and_styles_take_priority_when_many_images_exhaust_asset_budget(assets, monkeypatch):
    monkeypatch.setattr(webpage_resources, "MAX_RESOURCES", 3)
    assets.files.update({
        "https://example.test/site.css": ("text/css", b'@font-face {font-family: Icons; src: url(icons.woff2)}'),
        "https://example.test/icons.woff2": ("font/woff2", b"wOF2fixture"),
        "https://example.test/a.png": ("image/png", PNG),
        "https://example.test/b.png": ("image/png", PNG),
    })

    result = webpage_resources.build_offline_webpage_html(
        '<link rel="stylesheet" href="site.css"><img src="a.png"><img src="b.png">',
        "https://example.test/",
    )

    assert "data:font/woff2;base64," in result
    assert len(assets.calls) == 3


def test_expansion_budget_stops_repeated_large_embeds_before_serializing(assets, monkeypatch):
    monkeypatch.setattr(webpage_resources, "MAX_SNAPSHOT_BYTES", 400)
    assets.files["https://example.test/a.png"] = ("image/png", PNG)
    html = '<img src="a.png">' * 4
    serialized = []
    original = BeautifulSoup.__str__
    monkeypatch.setattr(BeautifulSoup, "__str__", lambda soup: serialized.append(True) or original(soup))

    with pytest.raises(ValueError, match="snapshot exceeds"):
        webpage_resources.build_offline_webpage_html(html, "https://example.test/")

    assert serialized == []


def test_expired_capture_skips_optional_network_requests(assets):
    result = webpage_resources.build_offline_webpage_html(
        '<p>Article</p><img src="a.png">', "https://example.test/", timeout_sec=0,
    )

    assert "Article" in result
    assert assets.calls == []


def test_private_redirected_asset_is_discarded(assets):
    assets.files["https://example.test/a.png"] = ("image/png", PNG, "http://127.0.0.1/secret")

    result = webpage_resources.build_offline_webpage_html('<p>Article</p><img src="a.png">', "https://example.test/")

    assert "Article" in result
    assert not BeautifulSoup(result, "html.parser").img.get("src")


def test_independent_css_assets_download_concurrently(assets, monkeypatch):
    assets.files["https://example.test/site.css"] = (
        "text/css", b''.join(f'@font-face {{font-family: Font{i}; src: url(font{i}.woff2)}}'.encode() for i in range(3)),
    )
    for i in range(3):
        assets.files[f"https://example.test/font{i}.woff2"] = ("font/woff2", b"wOF2fixture")
    all_started = Barrier(3)
    original = webpage_resources.open_public_http

    def fetch(request, *, timeout):
        if request.full_url.endswith(".woff2"):
            all_started.wait(timeout=2)
        return original(request, timeout=timeout)

    monkeypatch.setattr(webpage_resources, "open_public_http", fetch)

    result = webpage_resources.build_offline_webpage_html('<link rel="stylesheet" href="site.css">', "https://example.test/")

    assert result.count("data:font/woff2;base64,") == 3


def test_css_escaped_font_url_with_fragment_remains_embedded_and_is_fetched_once(assets):
    assets.files["https://example.test/font.woff2"] = ("font/woff2", b"wOF2fixture")
    html = r'<style>@font-face {font-family: Icons; src: url("f\6f nt.woff2#icons")}</style>'

    result = webpage_resources.build_offline_webpage_html(html, "https://example.test/")

    assert "data:font/woff2;base64," in result
    assert assets.calls == ["https://example.test/font.woff2"]


def test_resource_stream_stops_when_capture_deadline_expires(assets, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(webpage_resources.time, "monotonic", lambda: clock[0])

    class SlowResponse(io.BytesIO):
        headers = {"Content-Type": "image/png"}

        def read(self, size=-1):
            clock[0] += 2.0
            return super().read(size)

        read1 = read

        def geturl(self):
            return "https://example.test/a.png"

    monkeypatch.setattr(webpage_resources, "open_public_http", lambda *_args, **_kwargs: SlowResponse(PNG))

    result = webpage_resources.build_offline_webpage_html(
        '<p>Article</p><img src="a.png">', "https://example.test/", timeout_sec=1,
    )

    assert "Article" in result
    assert not BeautifulSoup(result, "html.parser").img.get("src")
