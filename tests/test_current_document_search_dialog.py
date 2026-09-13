import current_document_search_dialog as dialog


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
