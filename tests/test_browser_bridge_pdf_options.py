"""Companion PDF choices reach the exporter without weakening payload validation."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import browser_bridge
import pytest


@pytest.mark.parametrize("style", ["print", "website", "article"])
def test_pdf_export_options_preserve_the_selected_layout_and_flags(style):
    normalized = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/article",
        "pdfOptions": {"style": style, "dynamic": True, "includeLinks": True},
    })
    assert normalized["pdf_options"] == {
        "style": style, "dynamic": True, "include_links": True,
    }


def test_older_companions_keep_print_layout_without_dynamic_content_or_appendix():
    normalized = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/article",
    })
    assert normalized["pdf_options"] == {
        "style": "print", "dynamic": False, "include_links": False,
    }


@pytest.mark.parametrize("options", [
    None, [], "website", {"style": "unknown"}, {"style": []},
    {"dynamic": "false"}, {"includeLinks": 1}, {"dynamic": None},
    {"includeLinks": {}}, {"executable": "/private/file"},
])
def test_invalid_pdf_options_are_rejected_before_import(options):
    with pytest.raises(ValueError, match="pdfOptions"):
        browser_bridge.normalize_add_content_payload({
            "kind": "pdf", "url": "https://example.org/article", "pdfOptions": options,
        })


@pytest.mark.parametrize("changes", [
    {"captureOpenedPage": "true"}, {"captureOpenedPage": 1}, {"captureOpenedPage": None},
    {"html": ""}, {"html": "   "}, {"kind": "webpage"},
    {"pdfBase64": "JVBERi0xLjcK"},
])
def test_opened_page_capture_requires_an_explicit_boolean_and_html(changes):
    with pytest.raises(ValueError, match="captureOpenedPage"):
        browser_bridge.normalize_add_content_payload({
            "kind": "pdf", "url": "https://example.org/article", "html": "<p>Article</p>",
            "captureOpenedPage": True, **changes,
        })


def test_opened_page_capture_does_not_download_a_url_ending_in_pdf(monkeypatch):
    payload = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/article.pdf", "html": "<p>Article</p>",
        "captureOpenedPage": True,
    })
    download = Mock(side_effect=AssertionError("Do not download the opened page again"))
    monkeypatch.setattr(browser_bridge, "download_pdf_from_url", download)
    browser_bridge._prepare_pdf_item_off_main(payload)
    download.assert_not_called()
    assert browser_bridge._PREPARED_PDF_PATH_KEY not in payload


def import_adapter(render, add):
    """Execute the real adapter with only its Anki/Qt collaborators replaced."""
    path = Path(browser_bridge.__file__)
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "_add_content_item_on_main")
    node.body = [n for n in node.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    namespace = dict(vars(browser_bridge))
    namespace.update(
        mw=SimpleNamespace(col=object()), add_pdf_card=add,
        render_webpage_to_pdf=render, set_priority=Mock(), _active_profile=lambda: "TestProfile",
        _sync_parent_child_knowledge_tree_on_main=Mock(return_value={}),
        _source_metadata_for_extension_card=lambda **kwargs: kwargs,
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_add_content_item_on_main"]


@pytest.mark.parametrize("dynamic", [False, True])
def test_webpage_import_uses_pdf_preferences_and_cleans_its_temporary_file(dynamic):
    renders, imported = [], []
    def render(path, **options):
        renders.append(options)
        Path(path).write_bytes(b"%PDF-1.7\nfixture")
    def add(_root, _col, path, _title, **_kwargs):
        imported.append(Path(path))
        assert Path(path).read_bytes().startswith(b"%PDF-")
        return 42
    payload = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/article", "html": "<p>Snapshot</p>",
        "pdfOptions": {"style": "article", "dynamic": dynamic, "includeLinks": True},
    })

    result = import_adapter(render, add)(payload)

    assert result["cardId"] == 42
    assert renders == [{
        "url": "https://example.org/article", "html": "" if dynamic else "<p>Snapshot</p>",
        "style": "article", "dynamic": dynamic, "include_links": True,
        "timeout_ms": 90000 if dynamic else 45000,
    }]
    assert len(imported) == 1 and not imported[0].exists()


def test_direct_pdf_upload_bypasses_webpage_export_preferences():
    render = Mock(side_effect=AssertionError("A PDF must not be re-rendered"))
    add = Mock(return_value=42)
    payload = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/document.pdf", "pdfBase64": "JVBERi0xLjcK",
        "pdfOptions": {"style": "article", "dynamic": True, "includeLinks": True},
    })
    assert import_adapter(render, add)(payload)["cardId"] == 42
    render.assert_not_called()
    assert not Path(add.call_args.args[2]).exists()


def test_opened_page_capture_passes_snapshot_mode_and_never_reloads(monkeypatch):
    renders = []
    def render(path, **options):
        renders.append(options)
        Path(path).write_bytes(b"%PDF-1.7\nfixture")
    add = Mock(return_value=42)
    monkeypatch.setattr(browser_bridge, "download_pdf_from_url", Mock(side_effect=AssertionError("Do not refetch")))
    payload = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/article.pdf", "html": "<p>Verified article</p>",
        "captureOpenedPage": True,
        "pdfOptions": {"style": "print", "dynamic": True, "includeLinks": True},
    })

    assert import_adapter(render, add)(payload)["cardId"] == 42
    assert renders == [{
        "url": "https://example.org/article.pdf", "html": "<p>Verified article</p>",
        "style": "print", "dynamic": False, "include_links": True,
        "timeout_ms": 45000, "prefer_snapshot": True,
    }]
    assert not Path(add.call_args.args[2]).exists()


def test_failed_webpage_render_leaves_no_file_or_card():
    paths = []
    def render(path, **_kwargs):
        paths.append(Path(path))
        raise RuntimeError("synthetic renderer failure")
    add = Mock()
    payload = browser_bridge.normalize_add_content_payload({
        "kind": "pdf", "url": "https://example.org/article", "pdfOptions": {"dynamic": True},
    })
    with pytest.raises(RuntimeError, match="synthetic renderer failure"):
        import_adapter(render, add)(payload)
    add.assert_not_called()
    assert len(paths) == 1 and not paths[0].exists()
