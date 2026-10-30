"""Streamed React articles must remain readable without running site scripts."""

from bs4 import BeautifulSoup
import json
import pytest

from webpage_export import prepare_export_html
from webpage_resources import build_offline_webpage_html


@pytest.mark.parametrize("style", ["website", "article", "print"])
def test_lesswrong_streamed_article_and_comments_replace_loading_placeholders(style):
    html = '''<html><head><title>Forum post</title></head><body>
      <!--$?--><template id="B:1"></template><p>Loading article</p><!--/$-->
      <div hidden id="S:1"><main><h1>Forum post</h1><p>Actual article.</p>
        <!--$?--><template id="B:2"></template><p>Loading discussion</p><!--/$-->
      </main></div>
      <div hidden id="S:2"><section id="discussion"><template id="P:3"></template></section></div>
      <div hidden id="S:3"><p>A comment worth keeping.</p></div>
      <script>$RC("B:1","S:1")</script><script>$RS("S:3","P:3");$RC("B:2","S:2")</script>
      <aside hidden>Intentionally hidden menu</aside>
      <script>document.body.textContent = "UNTRUSTED SCRIPT";</script>
    </body></html>'''

    prepared = prepare_export_html(html, "https://www.lesswrong.com/posts/test", style=style)
    result = BeautifulSoup(build_offline_webpage_html(prepared, "", timeout_sec=0), "html.parser")

    assert result.h1 is not None
    assert result.h1.get_text() == "Forum post"
    assert not any(parent.has_attr("hidden") for parent in result.h1.parents)
    assert "Actual article." in result.get_text()
    assert "A comment worth keeping." in result.get_text()
    assert "Loading article" not in result.get_text()
    assert "Loading discussion" not in result.get_text()
    assert not result.find_all(["script", "template"])
    if style != "article":
        assert result.aside.has_attr("hidden")


def test_incomplete_stream_does_not_erase_the_visible_fallback():
    html = '<!--$?--><template id="B:0"></template><p>Visible fallback</p><!--/$--><script>$RC("B:0","S:0")</script>'
    result = prepare_export_html(html, "", style="website")
    assert "Visible fallback" in result


def test_lesswrong_literal_styles_survive_without_executing_the_style_loader():
    html = '''<html><head><meta id="jss-insertion-start"><meta id="jss-insertion-end"></head><body>
      <h1 class="post-title">Readable title</h1>
      <script>_embedStyles("PostTitle",0,".post-title { font-size: 25px; }");
      _embedStyles("Base",-1,"body { margin: 0; }");
      _embedStyles("NotLiteral",0,fetch("https://private.invalid"));</script>
    </body></html>'''

    result = BeautifulSoup(build_offline_webpage_html(prepare_export_html(html, "", style="website"), "", timeout_sec=0), "html.parser")

    assert [tag.get_text() for tag in result.find_all("style")] == [
        "body { margin: 0; }", ".post-title { font-size: 25px; }",
    ]
    assert not result.find_all("script")


def test_decoded_embedded_css_cannot_break_out_into_executable_html():
    css = '.title::after { content: "</style><script>unexpected()</script>"; }'
    literal = json.dumps(css).replace("<", "\\u003c")
    html = ('<html><head><meta id="jss-insertion-start"><meta id="jss-insertion-end"></head><body>'
            '<script>_embedStyles("Title",0,' + literal + ')</script></body></html>')

    exported = prepare_export_html(html, "", style="website")
    result = BeautifulSoup(build_offline_webpage_html(exported, "", timeout_sec=0), "html.parser")

    assert not result.find_all("script")
    assert len(result.find_all("style")) == 1
    assert r"\3c /style>" in result.style.get_text()
