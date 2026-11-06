"""A webpage becomes an inert, editable, offline Markdown study document."""

import io
import json
from pathlib import Path
import shutil
import zipfile

import pytest
from bs4 import BeautifulSoup

import markdown_manager
import paths
import webpage_document


PNG = b"\x89PNG\r\n\x1a\nimage"
HTML = '''<html><title>Saved article</title><nav>Navigation</nav><article>
<h1>Reading</h1><p>Original <strong>passage</strong>.</p>
<img src="/picture.png" alt="diagram"><img src="/picture.png" alt="again">
<a href="/more">More</a><script>alert(1)</script></article></html>'''


def test_cleaned_snapshot_rebuilds_all_exports_offline_and_keeps_capture_identity(tmp_path, monkeypatch):
    import webpage_resources
    html = '<html><head><style>main{display:grid}</style></head><body><aside>Remove clutter</aside><main><h1>Keep article</h1><p>Retained passage.</p></main></body></html>'
    with webpage_document.prepare_webpage_document('https://example.com/article', html=html, capture_format='html') as original:
        captured = dict(original.capture)
        cleaned = BeautifulSoup(Path(original.preview_path).read_text(), 'html.parser')
        cleaned.aside.decompose()
        # A compromised serialization must not get a new network capability.
        image = cleaned.new_tag('img', src='https://example.com/new.png')
        cleaned.main.append(image)
        def no_network(*args, **kwargs):
            pytest.fail('Saving preview edits fetched a webpage/resource')
        monkeypatch.setattr(webpage_document, 'open_public_http', no_network)
        monkeypatch.setattr(webpage_resources, 'open_public_http', no_network)
        monkeypatch.setattr(webpage_document, 'fetch_webpage_html', no_network)
        with webpage_document.prepare_edited_webpage_snapshot(original, str(cleaned)) as revised:
            assert revised.capture['captured_at'] == captured['captured_at']
            assert revised.capture['url'] == captured['url']
            target = paths.get_epub_dir(str(tmp_path), 'Saved') / 'cleaned.epub'
            target.parent.mkdir(parents=True)
            shutil.copyfile(revised.path, target)
            for format in ('html', 'md', 'txt'):
                exported = markdown_manager.export_markdown_document(str(tmp_path), 'Saved', target.name, format).decode()
                assert 'Remove clutter' not in exported
                assert 'Keep article' in exported and 'Retained passage.' in exported
            assert 'display:grid' in markdown_manager.export_markdown_document(str(tmp_path), 'Saved', target.name, 'html').decode()
        assert Path(original.path).is_file()


def test_loaded_page_capture_keeps_local_images_source_and_frozen_original(tmp_path, monkeypatch):
    calls = []

    class Response(io.BytesIO):
        headers = {"Content-Type": "image/png"}

        def geturl(self):
            return "https://example.com/picture.png"

    def fetch(request, **_kwargs):
        calls.append(request.full_url)
        return Response(PNG)

    monkeypatch.setattr(webpage_document, "open_public_http", fetch)
    with webpage_document.prepare_webpage_document("https://example.com/article", html=HTML) as prepared:
        assert prepared.title == "Saved article"
        assert prepared.capture["url"] == "https://example.com/article"
        assert prepared.capture["omitted_images"] == 0
        with zipfile.ZipFile(prepared.path) as archive:
            source = archive.read("source.md").decode()
            assert "Navigation" not in source and "alert(1)" not in source
            assert "![diagram]" in source
            assert "Source:" not in source
            assert archive.read("original_source.md").decode() == source
            assert json.loads(archive.read("capture.json"))["captured_at"]
            assert archive.read("OEBPS/images/image-1.png") == PNG
            assert "https://example.com/picture.png" not in archive.read("OEBPS/section-1.xhtml").decode()
        target = paths.get_epub_dir(str(tmp_path), "Saved") / "article.epub"
        target.parent.mkdir(parents=True)
        shutil.copyfile(prepared.path, target)
    assert calls == ["https://example.com/picture.png"]  # Never reload the supplied page.

    html = markdown_manager.export_markdown_document(str(tmp_path), "Saved", target.name, "html").decode()
    assert "data:image/png;base64," in html
    assert "<strong>passage</strong>" in html and "<script" not in html
    assert "https://example.com/article" in html
    md = markdown_manager.export_markdown_document(str(tmp_path), "Saved", target.name, "md").decode()
    assert "data:image/png;base64," in md and "**passage**" in md
    plain = markdown_manager.export_markdown_document(str(tmp_path), "Saved", target.name, "txt").decode()
    assert "Original passage." in plain and "**" not in plain
    assert "https://example.com/article" in plain


def test_html_snapshot_keeps_website_layout_and_exports_saved_html(tmp_path, monkeypatch):
    import webpage_resources
    html = '''<html><head><title>Snapshot</title><style>.columns {display:grid;grid-template-columns:2fr 1fr;color:#123456}</style></head>
    <body><nav>Site navigation</nav><main class="columns"><article><h1>Original page</h1><p>Article body</p>
    <img src="/picture.png" alt="diagram"></article><aside>Sidebar content</aside></main>
    <script>alert(1)</script><iframe src="https://example.com/embed"></iframe></body></html>'''
    class Response(io.BytesIO):
        headers = {"Content-Type": "image/png"}
        def geturl(self): return "https://example.com/picture.png"
    monkeypatch.setattr(webpage_resources, "open_public_http", lambda *_a, **_k: Response(PNG))
    monkeypatch.setattr(webpage_resources, "validate_public_http_url", lambda url: url)
    with webpage_document.prepare_webpage_document("https://example.com/article", html=html, capture_format="html") as prepared:
        assert prepared.capture["format"] == "html"
        with zipfile.ZipFile(prepared.path) as archive:
            captured = archive.read("OEBPS/section-1.html").decode()
            assert 'class="columns"' in captured and "display:grid" in captured
            assert "Sidebar content" in captured and "Site navigation" in captured
            assert "data:image/png;base64," in captured
            assert "<script" not in captured and "<iframe" not in captured
            assert "Content-Security-Policy" in captured
        target = paths.get_epub_dir(str(tmp_path), "Saved") / "snapshot.epub"
        target.parent.mkdir(parents=True)
        shutil.copyfile(prepared.path, target)
    monkeypatch.setattr(webpage_resources, "open_public_http", lambda *_a, **_k: pytest.fail("export fetched a resource"))
    exported = markdown_manager.export_markdown_document(str(tmp_path), "Saved", target.name, "html").decode()
    assert exported == captured
    assert "display:grid" in exported and "Sidebar content" in exported
    assert "https://example.com/article" in exported


def test_snapshot_edit_rejects_replacing_the_saved_html_with_markdown(tmp_path):
    with webpage_document.prepare_webpage_document("https://example.com/article", html="<p>Frozen HTML</p>",
                                                   capture_format="html") as prepared:
        target = paths.get_epub_dir(str(tmp_path), "Saved") / "snapshot.epub"
        target.parent.mkdir(parents=True)
        shutil.copyfile(prepared.path, target)
    before = target.read_bytes()
    snapshot = markdown_manager.load_markdown_document(str(tmp_path), "Saved", target.name)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.save_markdown_document(str(tmp_path), "Saved", 41, target.name, "# Replaced", title="Snapshot",
                                                expected_revision=snapshot.revision)
    assert target.read_bytes() == before


def test_html_reader_copy_keeps_form_layout_and_svg_images(tmp_path, monkeypatch):
    import base64
    import epub_manager
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30"><rect width="100" height="30" fill="red"/></svg>'
    data_url = 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode()
    html = '<html><head><style>.bar{height:40px}.btn{display:block;width:195px;height:34px}</style></head><body><form class="bar">20 results</form><form><button class="btn">Save</button></form><img alt="Logo" src="' + data_url + '"></body></html>'
    profile = 'Saved'
    monkeypatch.setattr(epub_manager, 'get_epub_dir', lambda profile=None: str(paths.get_epub_dir(str(tmp_path), profile)))
    monkeypatch.setattr(epub_manager, 'get_epub_extract_root', lambda profile=None: str(paths.get_epub_extract_root(str(tmp_path), profile)))
    with webpage_document.prepare_webpage_document('https://example.com/article', html=html, capture_format='html') as prepared:
        meta = epub_manager.ensure_epub_extracted(prepared.path, stored_filename='snapshot.epub', profile=profile)
        section = paths.get_epub_extract_root(str(tmp_path), profile) / 'snapshot.epub' / 'OEBPS/section-1.html'
        soup = BeautifulSoup(section.read_text(), 'html.parser')
        assert soup.select_one('.bar').get_text() == '20 results'
        assert soup.select_one('.btn').get_text() == 'Save'
        assert not soup.find(['form', 'button'])
        image = soup.find('img')
        assert image.get('src') and not image['src'].startswith('data:image/svg')
        assert (section.parent / image['src']).read_bytes() == svg


def test_snapshot_svg_assets_cannot_read_external_files_or_run_scripts():
    import base64
    svg = b'<?xml-stylesheet href="file:///private/style.css"?><svg xmlns="http://www.w3.org/2000/svg" xml:base="file:///private/" width="10" height="10" onload="evil()"><image href="file:///private/secret.png"/><script>evil()</script><use href="https://example.com/a.svg#x"/><rect fill="url(file:///private/paint.svg)" width="10" height="10"/></svg>'
    html = '<img src="data:image/svg+xml;base64,' + base64.b64encode(svg).decode() + '">'
    _reader, files = markdown_manager._snapshot_reader_copy(html)
    content = next(iter(files.values()))[0].decode()
    assert 'file:' not in content and 'https:' not in content
    assert '<script' not in content and 'onload' not in content
    assert 'xml-stylesheet' not in content and 'base=' not in content
    assert 'rect' in content


def test_snapshot_svg_public_doctype_is_removed_without_resolving_it():
    import base64
    svg = b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "https://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd"><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    html = '<img src="data:image/svg+xml;base64,' + base64.b64encode(svg).decode() + '">'
    _reader, files = markdown_manager._snapshot_reader_copy(html)
    content = next(iter(files.values()))[0].decode()
    assert 'DOCTYPE' not in content and 'rect' in content


def test_capture_omits_unavailable_images_without_losing_text(tmp_path, monkeypatch):
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("blocked")))
    with webpage_document.prepare_webpage_document("https://example.com/article", html=HTML) as prepared:
        assert prepared.capture["omitted_images"] == 1
        with zipfile.ZipFile(prepared.path) as archive:
            # Preserved article headings now start their own reader sections.
            rendered = "".join(archive.read(name).decode() for name in archive.namelist()
                               if name.startswith("OEBPS/section-"))
            assert "Original" in rendered and "<img" not in rendered


def test_markdown_export_treats_source_url_as_metadata_not_image_markup(tmp_path):
    import markdown
    from bs4 import BeautifulSoup
    url = "https://example.com/![pixel](https://evil.example/p.png)"
    with webpage_document.prepare_webpage_document(url, html="<p>Article text</p>") as prepared:
        target = paths.get_epub_dir(str(tmp_path), "Saved") / "article.epub"
        target.parent.mkdir(parents=True)
        shutil.copyfile(prepared.path, target)
    exported = markdown_manager.export_markdown_document(str(tmp_path), "Saved", target.name, "md").decode()
    assert BeautifulSoup(markdown.markdown(exported), "html.parser").find("img") is None


def test_markdown_export_preserves_image_examples_inside_code(tmp_path):
    example = '![example](https://example.com/example.png)'
    html = '<article><h1>Code</h1><pre>' + example + '</pre><p>Inline: <code>' + example + '</code></p></article>'
    with webpage_document.prepare_webpage_document("https://example.com/article", html=html) as prepared:
        target = paths.get_epub_dir(str(tmp_path), "Saved") / "article.epub"
        target.parent.mkdir(parents=True)
        shutil.copyfile(prepared.path, target)
    exported = markdown_manager.export_markdown_document(str(tmp_path), "Saved", target.name, "md").decode()
    assert exported.count(example) == 2


@pytest.mark.parametrize("scope", ["other", "MAIN", ""])
def test_capture_rejects_invalid_scope(scope):
    with pytest.raises(ValueError):
        webpage_document.prepare_webpage_document("https://example.com/article", html=HTML, content_scope=scope)


def test_capture_cancelled_before_fetch_has_no_output(monkeypatch):
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: pytest.fail("cancelled capture fetched"))
    with pytest.raises(InterruptedError):
        webpage_document.prepare_webpage_document("https://example.com/article", html=HTML, is_cancelled=lambda: True)


def test_webpage_table_remains_a_table_in_the_reading_copy():
    with webpage_document.prepare_webpage_document("https://example.com/article", html='''<article>
        <h1>Data</h1><table><thead><tr><th>Name</th><th>Value</th></tr></thead>
        <tbody><tr><td>Alpha</td><td>42</td></tr></tbody></table></article>''') as prepared:
        with zipfile.ZipFile(prepared.path) as archive:
            assert any("<table>" in archive.read(name).decode() for name in archive.namelist()
                       if name.startswith("OEBPS/section-"))


def test_capture_preserves_article_order_around_inline_content():
    html = '<article><h1>Heading</h1><p>First paragraph.</p><a href="/next">Inline link</a><p>Last paragraph.</p></article>'
    with webpage_document.prepare_webpage_document("https://example.com/article", html=html) as prepared:
        with zipfile.ZipFile(prepared.path) as archive:
            text = archive.read("source.md").decode()
            assert text.index("First paragraph") < text.index("Inline link") < text.index("Last paragraph")


def test_capture_excludes_hidden_inline_content_and_markdown_in_page_text(monkeypatch):
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: pytest.fail("page text became an image"))
    html = '''<article><h1>Article</h1><p>Visible <span hidden>Secret hidden text</span> paragraph.</p>
    <blockquote>![literal](https://example.com/not-an-image.png)</blockquote></article>'''
    with webpage_document.prepare_webpage_document("https://example.com/article", html=html) as prepared:
        with zipfile.ZipFile(prepared.path) as archive:
            source = archive.read("source.md").decode()
            assert "Secret hidden text" not in source
            assert "literal" in source and "Visible" in source


def test_embedded_raster_image_is_kept_without_network_requests(monkeypatch):
    import base64
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: pytest.fail("data image fetched"))
    src = 'data:image/png;base64,' + base64.b64encode(PNG).decode()
    with webpage_document.prepare_webpage_document("https://example.com/article",
        html='<article><p>Local image</p><img alt="embedded" src="' + src + '"></article>') as prepared:
        with zipfile.ZipFile(prepared.path) as archive:
            assert archive.read("OEBPS/images/image-1.png") == PNG


def test_document_bridge_requires_snapshot_and_prepares_it_off_main(monkeypatch):
    import browser_bridge

    with pytest.raises(ValueError, match="HTML"):
        browser_bridge.normalize_add_content_payload({"kind": "document", "url": "https://example.com"})
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("offline")))
    request = browser_bridge.prepare_add_content_request_off_main({
        "kind": "document", "url": "https://example.com/article", "html": HTML, "title": "My title", "pageContentScope": "main",
    })
    item = request["items"][0]
    prepared = item["_prepared_document"]
    assert prepared.title == "My title"
    assert item["title"] == "My title"
    assert prepared.path.endswith(".epub")
    browser_bridge.cleanup_prepared_add_content_request(request)
    from pathlib import Path
    assert not Path(prepared.path).exists()


@pytest.mark.parametrize("html", [None, [], {}, 123, "   "])
def test_document_bridge_rejects_non_html_payloads(html):
    import browser_bridge
    with pytest.raises(ValueError, match="HTML"):
        browser_bridge.normalize_add_content_payload({"kind": "document", "url": "https://example.com", "html": html})


def test_url_capture_records_final_url_and_full_scope(monkeypatch):
    calls = []
    def fetch(url):
        calls.append(url)
        return "https://example.com/final", HTML
    monkeypatch.setattr(webpage_document, "fetch_webpage_html", fetch)
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("offline")))
    with webpage_document.prepare_webpage_document("https://example.com/start", content_scope="full") as prepared:
        assert calls == ["https://example.com/start"]
        assert prepared.capture["url"] == "https://example.com/final"
        with zipfile.ZipFile(prepared.path) as archive:
            assert b"Navigation" in archive.read("source.md")


def test_capture_rejects_too_many_images_before_downloading(monkeypatch):
    monkeypatch.setattr(webpage_document, "open_public_http", lambda *_a, **_k: pytest.fail("over-budget capture fetched"))
    html = "<article><p>Article</p>" + "".join(f'<img src="/{index}.png">' for index in range(129)) + "</article>"
    with pytest.raises(markdown_manager.MarkdownImportError, match="images"):
        webpage_document.prepare_webpage_document("https://example.com/article", html=html)


def test_bridge_preparation_failure_cleans_earlier_document_temporaries(monkeypatch):
    import browser_bridge
    from pathlib import Path
    original, prepared = webpage_document.prepare_webpage_document, []
    def prepare(url, **kwargs):
        if prepared:
            raise ValueError("second capture failed")
        value = original(url, **kwargs)
        prepared.append(value)
        return value
    monkeypatch.setattr(webpage_document, "prepare_webpage_document", prepare)
    payload = {"kind": "document", "url": "https://example.com/article", "html": "<p>Saved text</p>"}
    with pytest.raises(ValueError, match="second capture failed"):
        browser_bridge.prepare_add_content_request_off_main({"items": [payload, payload]})
    assert not Path(prepared[0].path).exists()


def test_timed_out_import_retains_document_until_worker_callback(monkeypatch):
    import browser_bridge
    import threading
    import aqt
    from pathlib import Path
    from types import SimpleNamespace

    prepared = webpage_document.prepare_webpage_document("https://example.com/article", html="<p>Saved text</p>")
    item = {"kind": "document", "_prepared_document": prepared}
    callbacks = {}
    class Event:
        def __init__(self): self.value = False
        def wait(self, _timeout): return False
        def is_set(self): return self.value
        def set(self): self.value = True
    def dispatch(_item, success, failure, *, is_cancelled):
        callbacks.update(success=success, failure=failure, is_cancelled=is_cancelled)
    monkeypatch.setattr(browser_bridge, "threading", SimpleNamespace(Event=Event, Lock=threading.Lock))
    monkeypatch.setattr(browser_bridge, "_pdf_import_dispatch", dispatch)
    monkeypatch.setattr(aqt, "mw", SimpleNamespace(taskman=SimpleNamespace(run_on_main=lambda callback: callback())))
    with pytest.raises(TimeoutError):
        browser_bridge._run_pdf_import_and_wait(item, require_authorized=lambda: None)
    browser_bridge.cleanup_prepared_add_content_request({"items": [item]})
    assert Path(prepared.path).exists()
    assert callbacks["is_cancelled"]() is True
    callbacks["failure"](RuntimeError("cancelled"))
    assert not Path(prepared.path).exists()
