import importlib.util
import inspect
import os
import sys
import types
from types import SimpleNamespace

import pytest

import search_all
import search_all_results


def _load_dialog_module():
    module_names = (
        "aqt",
        "aqt.qt",
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtWebEngineWidgets",
    )
    originals = {name: sys.modules.get(name) for name in module_names}
    module_name = "_incremento_search_all_dialog"
    original_target = sys.modules.get(module_name)
    try:
        qt_module = types.ModuleType("aqt.qt")
        for name in (
            "QCheckBox",
            "QDialog",
            "QHBoxLayout",
            "QLabel",
            "QPushButton",
            "QSplitter",
            "QTextBrowser",
            "QVBoxLayout",
            "QWidget",
        ):
            setattr(qt_module, name, type(name, (), {}))
        qt_module.QSizePolicy = type(
            "QSizePolicy",
            (),
            {"Policy": SimpleNamespace(Ignored=1, Expanding=2)},
        )
        qt_module.Qt = SimpleNamespace(
            Orientation=SimpleNamespace(Horizontal=1),
        )

        aqt_module = types.ModuleType("aqt")
        aqt_module.mw = SimpleNamespace()
        aqt_module.qt = qt_module
        sys.modules["aqt"] = aqt_module
        sys.modules["aqt.qt"] = qt_module

        pyqt_module = types.ModuleType("PyQt6")
        qtcore_module = types.ModuleType("PyQt6.QtCore")
        qtcore_module.QTimer = type("QTimer", (), {})
        qtcore_module.QUrl = type("QUrl", (), {})
        webengine_module = types.ModuleType("PyQt6.QtWebEngineWidgets")
        webengine_module.QWebEngineView = type("QWebEngineView", (), {})
        sys.modules["PyQt6"] = pyqt_module
        sys.modules["PyQt6.QtCore"] = qtcore_module
        sys.modules["PyQt6.QtWebEngineWidgets"] = webengine_module

        spec = importlib.util.spec_from_file_location(
            module_name,
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "frontend",
                    "search_all.py",
                )
            ),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        if original_target is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_target


_DIALOG_MODULE = _load_dialog_module()
_SearchAllDialog = _DIALOG_MODULE._SearchAllDialog


class _Checked:
    def __init__(self, checked: bool):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


class _Text:
    def __init__(self, text: str):
        self._text = text

    def text(self) -> str:
        return self._text


class _HtmlSink:
    def __init__(self):
        self.html = ""

    def setHtml(self, html: str) -> None:
        self.html = html


class _LiveSearchDb:
    def all(self, sql, *ids):
        if "FROM cards" in sql:
            return [(17, 101)] if 17 in ids else []
        if "FROM notes" in sql:
            return [(101, 1, "Document\x1fBody\x1fbook.pdf")] if 101 in ids else []
        raise AssertionError(sql)


def _result_builder(filters, addon_dir="/tmp/search-all-test"):
    col = SimpleNamespace(
        db=_LiveSearchDb(), models=SimpleNamespace(get=lambda _mid: {"name": "Incremento PDF",
            "flds": [{"name": "Title", "ord": 0}, {"name": "Body", "ord": 1},
                     {"name": "PDF_Filename", "ord": 2}]}),
    )
    return search_all_results.SearchResultsBuilder(str(addon_dir), "TestProfile", col, filters)


class _SplitterPane:
    def __init__(self):
        self.size_policy = None

    def setSizePolicy(self, horizontal, vertical) -> None:
        self.size_policy = (horizontal, vertical)


class _StableSplitter:
    def __init__(self):
        self.children_collapsible = None
        self.stretch_factors: dict[int, int] = {}

    def setChildrenCollapsible(self, collapsible: bool) -> None:
        self.children_collapsible = collapsible

    def setStretchFactor(self, index: int, stretch: int) -> None:
        self.stretch_factors[index] = stretch


def test_search_all_search_while_typing_defaults_enabled():
    assert search_all.configured_search_all_search_while_typing({}) is True


def test_search_all_filter_defaults_disable_pdf_content_only():
    assert search_all.configured_search_all_filter_enabled("pdf_highlights", {}) is True
    assert search_all.configured_search_all_filter_enabled("epub_highlights", {}) is True
    assert search_all.configured_search_all_filter_enabled("pdf_sources", {}) is True
    assert search_all.configured_search_all_filter_enabled("epub_sources", {}) is True
    assert search_all.configured_search_all_filter_enabled("pdf_content", {}) is False
    assert search_all.configured_search_all_filter_enabled("epub_content", {}) is True
    assert search_all.configured_search_all_filter_enabled("image_ocr", {}) is True
    assert search_all.configured_search_all_filter_enabled("cards", {}) is True
    assert search_all.configured_search_all_filter_enabled("current_profile", {}) is True


def test_search_all_filter_config_values_override_defaults():
    cfg = {
        "search_all_filter_pdf_highlights": False,
        "search_all_filter_pdf_content": True,
        "search_all_filter_cards": False,
        "search_all_filter_current_profile": False,
    }
    assert search_all.configured_search_all_filter_enabled("pdf_highlights", cfg) is False
    assert search_all.configured_search_all_filter_enabled("pdf_content", cfg) is True
    assert search_all.configured_search_all_filter_enabled("cards", cfg) is False
    assert search_all.configured_search_all_filter_enabled("current_profile", cfg) is False


def test_search_all_splitter_ignores_dynamic_preview_content_size_hints():
    splitter = _StableSplitter()
    results = _SplitterPane()
    preview = _SplitterPane()

    _DIALOG_MODULE._stabilize_search_splitter(splitter, results, preview)

    ignored = _DIALOG_MODULE.QSizePolicy.Policy.Ignored
    expanding = _DIALOG_MODULE.QSizePolicy.Policy.Expanding
    assert results.size_policy == (ignored, expanding)
    assert preview.size_policy == (ignored, expanding)
    assert splitter.children_collapsible is False
    assert splitter.stretch_factors == {0: 1, 1: 1}
    assert (
        "_stabilize_search_splitter(splitter, self._results, preview_container)"
        in inspect.getsource(_SearchAllDialog.__init__)
    )


@pytest.mark.parametrize(("media", "position"), [("pdf", 9), ("epub", 0)])
def test_document_highlight_hover_target_uses_the_saved_highlight_text(
    media,
    position,
):
    previews: dict[str, str] = {}
    highlight_text = "Saved <highlight> with faithful wording."

    url = search_all._highlight_result_url(
        previews,
        media=media,
        card_id=17,
        position=position,
        query="faith",
        text=highlight_text,
    )
    target = search_all._document_preview_target(url, previews)

    assert target is not None
    assert target.media == media
    assert target.card_id == 17
    assert target.position == position
    assert target.query == "faith"
    assert target.highlight_text == highlight_text
    assert highlight_text not in url


def test_stale_highlight_hover_target_does_not_fall_back_to_pdf_content():
    previews: dict[str, str] = {}
    url = search_all._highlight_result_url(
        previews,
        media="pdf",
        card_id=17,
        position=9,
        query="faith",
        text="Saved highlight",
    )

    assert search_all._document_preview_target(url, {}) is None


@pytest.mark.parametrize("media,position", [("pdf", 13), ("epub", 0)])
def test_qt_escaped_result_url_keeps_the_annotation_reference(media, position):
    from html import escape

    annotation = search_all_results.AnnotationPreview("Why this matters", "The original source passage.", "green")
    previews = {}
    url = search_all._highlight_result_url(previews, media=media, card_id=17, position=position,
        query="why & how?", text=annotation.note, annotation=annotation)

    target = search_all._document_preview_target(escape(url, quote=True), previews)

    assert target is not None
    assert target.annotation == annotation
    assert target.highlight_text == annotation.note
    assert target.query == "why & how?"
    assert search_all._document_preview_target(escape(url, quote=True), {}) is None


@pytest.mark.parametrize(("media", "position"), [("pdf", 9), ("epub", 0)])
def test_annotation_hover_shows_its_colored_source_even_when_query_only_matches_note(
    monkeypatch, tmp_path, media, position,
):
    from html import unescape
    import re

    from paths import get_pdf_dir

    pdf_dir = get_pdf_dir(str(tmp_path), "TestProfile")
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "book.pdf").write_bytes(b"%PDF-fixture")
    note = "A failure mode <script>unsafe()</script>"
    passage = "Original <passage> & context without the query"
    page_text = "Before the annotated passage.\n" + passage + "\nAfter the annotated passage."
    monkeypatch.setattr(_DIALOG_MODULE, "pdf_page_text", lambda *_args, **_kwargs: page_text)
    monkeypatch.setattr(_DIALOG_MODULE, "epub_section_text", lambda *_args, **_kwargs: ("Chapter", page_text))
    monkeypatch.setattr(search_all_results, "search_excerpt_rows", lambda _a, _p, kind, *_args, **_kwargs:
        [(17, position, note, passage, "green")] if kind == f"{media}_annotations" else [])
    result = _result_builder({"annotations"}, tmp_path).run("failure mode")
    url = unescape(re.search(r"href='([^']+)'", result.html)[1])
    sink = _HtmlSink()
    headers = []
    dialog = SimpleNamespace(
        _addon_dir=str(tmp_path), _profile="TestProfile",
        _highlight_previews=result.highlight_previews,
        _valid_context=lambda: True,
        _pdf_title=lambda _cid: "Test PDF",
        _epub_title=lambda _cid: "Test EPUB",
        _preview=sink,
        _preview_header=SimpleNamespace(setText=headers.append),
        _highlight_terms=lambda *args: _SearchAllDialog._highlight_terms(None, *args),
    )
    dialog._preview_highlight = lambda target: _SearchAllDialog._preview_highlight(dialog, target)

    _SearchAllDialog._on_hover(dialog, url)

    assert "failure" in sink.html and "mode" in sink.html
    assert "Original &lt;passage&gt; &amp; context without the query" in sink.html
    assert "<mark" in sink.html and "rgba(0,200,80," in sink.html
    assert "Before the annotated passage." in sink.html
    assert "After the annotated passage." in sink.html
    assert sink.html.index("Before the annotated passage.") < sink.html.index("Original &lt;passage&gt;")
    assert sink.html.index("Original &lt;passage&gt;") < sink.html.index("After the annotated passage.")
    assert 'id="incremento-search-source"' in sink.html
    assert "scrollIntoView" in sink.html
    assert "<script>" not in sink.html
    assert headers and ("Page 9" if media == "pdf" else "Section 1") in headers[-1]
    assert passage not in url and note not in url
    assert search_all._document_preview_target(url, {}) is None


@pytest.mark.parametrize("color", ["#1a2b3c", "red; background:url(https://invalid)", None])
def test_annotation_source_color_is_normalized_before_rendering(monkeypatch, color):
    monkeypatch.setattr(_DIALOG_MODULE, "pdf_page_text", lambda *_args, **_kwargs: "")
    preview = search_all_results.AnnotationPreview("note", "<img src=x onerror=bad()>", color)
    sink = _HtmlSink()
    target = _DIALOG_MODULE._DocumentPreviewTarget("pdf", 17, 9, "", "note", preview)
    dialog = SimpleNamespace(
        _addon_dir="/tmp/unused-search-preview", _profile="TestProfile",
        _pdf_title=lambda _cid: "PDF", _preview=sink,
        _preview_header=SimpleNamespace(setText=lambda _text: None),
        _highlight_terms=lambda text, query: _SearchAllDialog._highlight_terms(None, text, query),
    )

    _SearchAllDialog._preview_highlight(dialog, target)

    expected = "rgba(26,43,60," if color == "#1a2b3c" else "rgba(255,220,0,"
    assert expected in sink.html
    assert "<img" not in sink.html and "&lt;img" in sink.html
    assert "https://invalid" not in sink.html


def test_annotation_page_preview_renders_source_color_and_scrolls_to_it(monkeypatch, tmp_path):
    import json
    import subprocess
    from textwrap import dedent

    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip("Optional webpage browser component has not been explicitly installed")
    source = "The source passage is highlighted inside the surrounding document text."
    context = "\n".join(f"Earlier context {i}: background information." for i in range(120))
    context += "\n" + source + "\n"
    context += "\n".join(f"Later context {i}: the next idea in the document." for i in range(60))
    monkeypatch.setattr(_DIALOG_MODULE, "pdf_page_text", lambda *_args, **_kwargs: context)
    sink = _HtmlSink()
    dialog = SimpleNamespace(
        _addon_dir=str(tmp_path), _profile="Synthetic",
        _pdf_title=lambda _cid: "Example document", _preview=sink,
        _preview_header=SimpleNamespace(setText=lambda _text: None),
        _highlight_terms=lambda text, query: _SearchAllDialog._highlight_terms(None, text, query),
    )
    target = _DIALOG_MODULE._DocumentPreviewTarget("pdf", 17, 13, "why", "Why this matters",
        search_all_results.AnnotationPreview("Why this matters", source, "green"))
    _SearchAllDialog._preview_highlight(dialog, target)
    script = dedent('''
        import json, sys
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width': 900, 'height': 650})
            page.route('**/*', lambda route: route.abort())
            page.set_content(json.load(sys.stdin), wait_until='load')
            source = page.locator('#incremento-search-source')
            expect(source).to_have_text('The source passage is highlighted inside the surrounding document text.')
            expect(source).to_be_in_viewport()
            assert source.evaluate("node => getComputedStyle(node).backgroundColor") == 'rgba(0, 200, 80, 0.4)'
            assert page.evaluate('window.scrollY') > 1000, 'The preview must move down to the source automatically'
            assert 'Earlier context 119' in page.locator('body').inner_text()
            assert 'Later context 0' in page.locator('body').inner_text()
            page.screenshot(path=sys.argv[3])
            browser.close()
    ''')
    result = subprocess.run(
        [runtime[0], "-I", "-c", script, str(_runtime_dir() / "packages"), runtime[1],
         str(tmp_path / "annotation-preview.png")],
        input=json.dumps(sink.html), capture_output=True, text=True, timeout=30, env=dict(os.environ),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_filter_toggle_refreshes_ready_query_when_search_while_typing_is_disabled(
    monkeypatch,
):
    saved: list[tuple[str, bool]] = []
    refreshed: list[str] = []
    dialog = SimpleNamespace(
        _cb_search_while_typing=_Checked(False),
        _search=_Text("faith"),
        _update_search_button=lambda: None,
        _query_ready=lambda: True,
        _refresh=refreshed.append,
        _show_search_hint=lambda: None,
    )
    dialog._maybe_refresh_from_controls = lambda *args, **kwargs: (
        _SearchAllDialog._maybe_refresh_from_controls(dialog, *args, **kwargs)
    )
    monkeypatch.setattr(
        _DIALOG_MODULE,
        "_set_search_all_filter_enabled",
        lambda filter_id, enabled: saved.append((filter_id, enabled)),
    )

    _SearchAllDialog._on_filter_toggled(dialog, "pdf_highlights", False)

    assert saved == [("pdf_highlights", False)]
    assert refreshed == ["faith"]


def test_live_anki_filter_label_does_not_claim_cross_profile_search():
    constructor_source = inspect.getsource(_SearchAllDialog.__init__)

    assert 'QCheckBox(t("search_all_existing_anki_items"))' in constructor_source
    assert "Current Anki Profile Only" not in constructor_source


@pytest.mark.parametrize("annotations_only", [False, True])
def test_highlight_search_filters_live_rows_before_the_display_limit(monkeypatch, annotations_only, tmp_path):
    from paths import get_pdf_dir
    pdf_dir = get_pdf_dir(str(tmp_path), "TestProfile")
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "book.pdf").write_bytes(b"%PDF-fixture")
    requested_limits: list[int | None] = []
    all_rows = [
        (99, page, "faith") for page in range(1, 121)
    ] + [
        (17, page, "faith") for page in range(121, 242)
    ]

    def fake_search_excerpt_rows(*_args, **kwargs):
        if _args[2] == "epub_annotations":
            return []
        requested_limits.append(kwargs.get("limit"))
        rows = all_rows[: kwargs.get("limit", 120)]
        return [(*row, "Saved passage", "green") for row in rows] if annotations_only else rows

    monkeypatch.setattr(
        search_all_results,
        "search_excerpt_rows",
        fake_search_excerpt_rows,
    )
    builder = _result_builder(
        {"current_profile", "annotations" if annotations_only else "pdf_highlights"}, tmp_path
    )
    results = builder.run("faith")

    assert requested_limits == [1200]
    assert results.html.count("<li>") == 120
    assert "Page 121" in results.html
    assert "Page 241" not in results.html
    if annotations_only:
        assert "Annotations (PDF)" in results.html
        assert "PDF Highlights" not in results.html


def test_source_live_filter_requires_document_card_and_source_note():
    builder = _result_builder({"current_profile"})
    rows = [
        (17, 1, "live", 101),
        (17, 2, "deleted source note", 102),
        (18, 3, "deleted document card", 101),
    ]

    filtered = builder._filter_current_profile_rows(
        rows,
        note_id_index=3,
    )

    assert filtered == [(17, 1, "live", 101)]


def test_annotations_filter_has_its_own_saved_preference():
    assert search_all.configured_search_all_filter_enabled("annotations", {}) is True
    assert search_all.configured_search_all_filter_enabled(
        "annotations", {"search_all_filter_annotations": False}
    ) is False
