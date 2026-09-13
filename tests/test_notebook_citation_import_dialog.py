import notebook_citation_import_dialog as dialog


def test_notebook_preview_translates_labels_and_preserves_counts(monkeypatch):
    messages = {
        "reader_notebook_highlights_count": "Istaknuto: {count}",
        "reader_notebook_notes_count": "Bilješke: {count}",
        "reader_notebook_page_entries_count": "Stranice: {count}",
        "reader_notebook_location_entries_count": "Lokacije: {count}",
        "reader_notebook_colors": "Boje: {colors}",
        "reader_none": "nema",
    }
    monkeypatch.setattr(dialog, "t", lambda key, **values: messages[key].format(**values), raising=False)
    summary = dialog._format_preview_counts({"highlights": 2, "notes": 1})
    assert "Istaknuto: 2" in summary
    assert "Bilješke: 1" in summary
    assert "Boje: nema" in summary
