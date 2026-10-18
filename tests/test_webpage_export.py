"""Article exports preserve reading content and links without site chrome."""

from bs4 import BeautifulSoup
import pytest

from webpage_export import prepare_export_html


def test_clean_article_keeps_figures_tables_code_and_links_but_removes_navigation():
    html = '''<html><head><title>A useful article</title><style>p{display:none}</style></head>
    <body><nav>MENU</nav><main><article><h1>A useful article</h1>
    <p>Readable article <a href="/reference">reference</a>.</p>
    <figure><img data-src="/photo.png"><figcaption>A caption</figcaption></figure>
    <table><tr><td>A value</td></tr></table><pre>some code</pre>
    <details><summary>More</summary><p>Expanded detail</p></details>
    <aside>ADVERTISEMENT</aside><form>SUBSCRIBE</form><script>evil()</script>
    <p hidden>HIDDEN</p></article></main><footer>FOOTER</footer></body></html>'''

    result = prepare_export_html(html, "https://example.org/article", style="article")
    soup = BeautifulSoup(result, "html.parser")

    assert soup.h1.get_text() == "A useful article"
    assert soup.find("a", string="reference")["href"] == "https://example.org/reference"
    assert soup.img["src"] == "https://example.org/photo.png"
    assert soup.figcaption.get_text() == "A caption"
    assert soup.table.get_text() == "A value"
    assert soup.pre.get_text() == "some code"
    assert soup.details.has_attr("open")
    for noise in ("MENU", "ADVERTISEMENT", "SUBSCRIBE", "evil()", "HIDDEN", "FOOTER", "display:none"):
        assert noise not in result


def test_link_appendix_deduplicates_destinations_and_rejects_unsafe_schemes():
    html = '''<article><h1>Links</h1><p><a href="/one">First</a>
    <a href="/one">Again</a><a href="#part">Section</a>
    <a href="javascript:alert(1)">Bad</a><a href="file:///secret">Local</a></p></article>'''
    soup = BeautifulSoup(prepare_export_html(html, "https://example.org/a", style="article", include_links=True), "html.parser")

    appendix = soup.find(id="incremento-link-list")
    assert [link["href"] for link in appendix.find_all("a")] == ["https://example.org/one"]
    assert soup.find("a", string="Section")["href"] == "#part"
    assert not soup.find("a", string="Bad").has_attr("href")
    assert not soup.find("a", string="Local").has_attr("href")


def test_article_without_semantic_container_retains_body_and_escapes_title():
    result = prepare_export_html('<title>&lt;script&gt;Title&lt;/script&gt;</title><p>Body text</p>', "https://example.org", style="article")
    soup = BeautifulSoup(result, "html.parser")
    assert soup.h1.get_text() == "<script>Title</script>"
    assert "Body text" in soup.get_text()
    assert soup.script is None


def test_website_appearance_preserves_site_layout_and_expands_details():
    soup = BeautifulSoup(prepare_export_html('<nav>MENU</nav><style>.site{color:red}</style><details><summary>Read</summary>Text</details>', "https://example.org", style="website"), "html.parser")
    assert soup.nav.get_text() == "MENU"
    assert ".site{color:red}" in str(soup)
    assert soup.details.has_attr("open")


def test_export_rejects_unknown_style_and_oversized_input():
    with pytest.raises(ValueError, match="style"):
        prepare_export_html("Body", "", style="surprise")
    with pytest.raises(ValueError, match="size"):
        prepare_export_html("a" * (16 * 1024 * 1024 + 1), "", style="article")


def test_clean_article_removes_comments_and_empty_sharing_lists_and_uses_canonical_heading():
    html = '''<head><meta property="og:title" content="Article heading"></head><main><article>
    <h1><b>2026 Featured</b> Article heading</h1><p>Main story</p>
    <ul class="share-buttons"><li><a href="/share"><i></i></a></li></ul>
    <section id="comments"><article class="comment-body">Reader comment</article></section>
    </article></main>'''
    soup = BeautifulSoup(prepare_export_html(html, "https://example.org/a", style="article"), "html.parser")
    assert soup.h1.get_text() == "Article heading"
    assert "Main story" in soup.get_text()
    assert "Reader comment" not in soup.get_text()
    assert soup.ul is None
