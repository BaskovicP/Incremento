import current_document_search_dialog as dialog


def test_reader_results_capture_profile_for_workers_and_keep_open_hit_arguments():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                    and node.name == "_open_current_document_search_results")
    options, searches, opened = [], [], []
    pdf = SimpleNamespace(
        current_pdf_search_context=lambda: {"cardId": 7, "documentLabel": "Synthetic", "query": ""},
        current_pdf_card_id=lambda: 7,
        current_card_pdf_search_hits=lambda *args, **kwargs: searches.append((args, kwargs)) or [],
        open_current_pdf_search_hit=lambda *args: opened.append(args),
    )
    class Picker:
        def __init__(self, parent, **kwargs): options.append(kwargs)
        def exec(self): return 0
    namespace = {"_active_profile": lambda: "Captured", "_pdf_dock_mod": pdf,
                 "_CurrentDocumentSearchDialog": Picker, "mw": object(), "_open_search_all": lambda query: None}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<reader search wiring>", "exec"), namespace)
    assert namespace[function.name]() is True
    cancel = object()
    options[0]["search_hits_fn"]("query", cancel=cancel)
    assert searches == [((7, "query"), {"profile": "Captured", "cancel": cancel})]
    options[0]["open_hit_fn"]({"page": 3}, 0, "query")
    assert opened == [({"page": 3}, 0, "query")]


def test_document_hit_titles_translate_locations_without_changing_snippets(monkeypatch):
    monkeypatch.setattr(dialog, "t", lambda key, **values: {
        "reader_page_number": "Stranica {page}",
        "reader_section_number": "Odjeljak {number}",
    }[key].format(**values), raising=False)
    assert dialog._document_hit_summary("pdf", {"page": 3, "snippet": "用户 原文"}) == "Stranica 3  |  用户 原文"
    assert dialog._document_hit_title("epub", {"sectionIndex": 1}) == "Odjeljak 2"


def test_document_hit_summary_formats_pdf_page_and_snippet():
    summary = dialog._document_hit_summary(
        "pdf",
        {"page": 7, "snippet": "target phrase appears here"},
    )

    assert summary.startswith("Page 7")
    assert "target phrase appears here" in summary


def test_document_hit_summary_uses_epub_section_title():
    summary = dialog._document_hit_summary(
        "epub",
        {"sectionIndex": 3, "sectionTitle": "Chapter Four", "snippet": "important part"},
    )

    assert summary.startswith("Chapter Four")
    assert "important part" in summary
