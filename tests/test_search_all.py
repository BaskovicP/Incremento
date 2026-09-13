import importlib.util
import inspect
import os
import sys
import types
from types import SimpleNamespace

import pytest

import search_all


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


def test_highlight_search_filters_live_rows_before_the_display_limit(monkeypatch):
    requested_limits: list[int | None] = []
    all_rows = [
        (99, page, "faith") for page in range(1, 121)
    ] + [
        (17, page, "faith") for page in range(121, 242)
    ]

    def fake_search_excerpt_rows(*_args, **kwargs):
        requested_limits.append(kwargs.get("limit"))
        return all_rows[: kwargs.get("limit", 120)]

    monkeypatch.setattr(
        _DIALOG_MODULE,
        "search_excerpt_rows",
        fake_search_excerpt_rows,
    )
    results = _HtmlSink()
    dialog = SimpleNamespace(
        _addon_dir="/tmp/search-all-test",
        _highlight_previews={},
        _cb_highlights=_Checked(True),
        _cb_sources=_Checked(False),
        _cb_epub_highlights=_Checked(False),
        _cb_epub_sources=_Checked(False),
        _cb_content=_Checked(False),
        _cb_epub_content=_Checked(False),
        _cb_ocr=_Checked(False),
        _cb_cards=_Checked(False),
        _cb_current_profile=_Checked(True),
        _is_current_profile_card=lambda card_id: card_id == 17,
        _pdf_title=lambda _card_id: "Document",
        _snippet=lambda text, _query, max_len=120: text[:max_len],
        _results=results,
    )
    dialog._filter_current_profile_rows = lambda rows, **kwargs: (
        _SearchAllDialog._filter_current_profile_rows(dialog, rows, **kwargs)
    )
    dialog._search_excerpt_hits = lambda kind, query, **kwargs: (
        _SearchAllDialog._search_excerpt_hits(
            dialog,
            kind,
            query,
            **kwargs,
        )
    )

    _SearchAllDialog._refresh(dialog, "faith")

    assert requested_limits == [1200]
    assert results.html.count("<li>") == 120
    assert "Page 121" in results.html
    assert "Page 241" not in results.html


def test_source_live_filter_requires_document_card_and_source_note():
    dialog = SimpleNamespace(
        _cb_current_profile=_Checked(True),
        _is_current_profile_card=lambda card_id: card_id == 17,
        _is_current_profile_note=lambda note_id: note_id == 101,
    )
    rows = [
        (17, 1, "live", 101),
        (17, 2, "deleted source note", 102),
        (18, 3, "deleted document card", 101),
    ]

    filtered = _SearchAllDialog._filter_current_profile_rows(
        dialog,
        rows,
        note_id_index=3,
    )

    assert filtered == [(17, 1, "live", 101)]
