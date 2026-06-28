import current_document_search_dialog as dialog


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
