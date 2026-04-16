from note_metadata import (
    INCREMENTO_IMPORTED_AT_FIELD,
    INCREMENTO_METADATA_FIELDS,
    INCREMENTO_SOURCE_LINK_FIELD,
    INCREMENTO_SOURCE_TITLE_FIELD,
    INCREMENTO_SOURCE_TYPE_FIELD,
    build_incremento_metadata,
    derive_note_source_metadata,
    ensure_incremento_metadata_fields,
    visible_field_names,
)


def test_visible_field_names_filters_incremento_metadata_fields():
    result = visible_field_names(
        ["Front", INCREMENTO_SOURCE_LINK_FIELD, "Back", INCREMENTO_SOURCE_TYPE_FIELD]
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
