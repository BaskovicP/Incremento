from note_metadata import (
    INCREMENTO_HIDDEN_FIELDS,
    INCREMENTO_IMPORTED_AT_FIELD,
    INCREMENTO_METADATA_FIELDS,
    INCREMENTO_OCR_TEXT_FIELD,
    INCREMENTO_SOURCE_LINK_FIELD,
    INCREMENTO_SOURCE_TITLE_FIELD,
    INCREMENTO_SOURCE_TYPE_FIELD,
    build_incremento_metadata,
    derive_note_source_metadata,
    ensure_incremento_ocr_field,
    ensure_incremento_metadata_fields,
    hidden_field_values,
    matches_hidden_field_reference,
    visible_field_names,
)


def test_visible_field_names_filters_incremento_metadata_fields():
    result = visible_field_names(
        ["Front", INCREMENTO_SOURCE_LINK_FIELD, "Back", INCREMENTO_SOURCE_TYPE_FIELD, INCREMENTO_OCR_TEXT_FIELD]
    )

    assert result == ["Front", "Back"]


def test_build_incremento_metadata_uses_explicit_values():
    result = build_incremento_metadata(
        source_type="Web",
        source_title="Example",
        source_link="https://example.com",
        imported_at="2026-04-16 10:11:12",
        parent="Parent Topic",
        parent_card_id=123,
    )

    assert result[INCREMENTO_SOURCE_TYPE_FIELD] == "Web"
    assert result[INCREMENTO_SOURCE_TITLE_FIELD] == "Example"
    assert result[INCREMENTO_SOURCE_LINK_FIELD] == "https://example.com"
    assert result[INCREMENTO_IMPORTED_AT_FIELD] == "2026-04-16 10:11:12"


def test_ensure_incremento_metadata_fields_adds_missing_fields():
    model = {"flds": [{"name": "Front"}, {"name": "Back"}]}

    class _Models:
        def new_field(self, name):
            return {"name": name}

        def add_field(self, model_dict, field):
            model_dict["flds"].append(field)

    changed = ensure_incremento_metadata_fields(_Models(), model)

    assert changed is True
    assert [field["name"] for field in model["flds"]][-len(INCREMENTO_METADATA_FIELDS):] == list(
        INCREMENTO_METADATA_FIELDS
    )


def test_ensure_incremento_ocr_field_adds_hidden_ocr_field():
    model = {"flds": [{"name": "Front"}, {"name": "Back"}]}

    class _Models:
        def new_field(self, name):
            return {"name": name}

        def add_field(self, model_dict, field):
            model_dict["flds"].append(field)

    changed = ensure_incremento_ocr_field(_Models(), model)

    assert changed is True
    assert model["flds"][-1]["name"] == INCREMENTO_OCR_TEXT_FIELD


def test_hidden_field_values_returns_incremento_hidden_fields():
    class _FakeNote(dict):
        def note_type(self):
            return {"flds": [{"name": "Front"}] + [{"name": field} for field in INCREMENTO_HIDDEN_FIELDS]}

    note = _FakeNote()
    note[INCREMENTO_SOURCE_LINK_FIELD] = "https://example.com"
    note[INCREMENTO_OCR_TEXT_FIELD] = "ocr text"

    result = hidden_field_values(note)

    assert (INCREMENTO_SOURCE_LINK_FIELD, "https://example.com") in result
    assert (INCREMENTO_OCR_TEXT_FIELD, "ocr text") in result


def test_matches_hidden_field_reference_handles_browser_style_keys():
    assert matches_hidden_field_reference(INCREMENTO_OCR_TEXT_FIELD) is True
    assert matches_hidden_field_reference(f"field_{INCREMENTO_OCR_TEXT_FIELD}") is True
    assert matches_hidden_field_reference(f"Field: {INCREMENTO_OCR_TEXT_FIELD}") is True
    assert matches_hidden_field_reference(f"notes/{INCREMENTO_OCR_TEXT_FIELD}") is True
    assert matches_hidden_field_reference("Front") is False


def test_derive_note_source_metadata_falls_back_to_pdf_fields():
    class _FakeNote(dict):
        fields = ["Imported PDF"]

    note = _FakeNote(PDF_Filename="paper.pdf")

    result = derive_note_source_metadata(note)

    assert result == {
        "source_type": "PDF",
        "source_title": "Imported PDF",
        "source_link": "pdfs/paper.pdf",
        "source_author": "",
    }
