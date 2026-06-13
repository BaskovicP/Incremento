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
    inline_pdf_reference,
    inline_pdf_reference_filename,
    matches_hidden_field_reference,
    source_document_reference,
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


def test_ensure_incremento_metadata_fields_save_refreshes_ordinals():
    model = {"id": 123, "flds": [{"name": "Front", "ord": 0}]}

    class _Models:
        def __init__(self):
            self.updated = False

        def new_field(self, name):
            return {"name": name, "ord": None}

        def add_field(self, model_dict, field):
            model_dict["flds"].append(field)

        def update_dict(self, model_dict):
            self.updated = True

        def get(self, model_id):
            assert model_id == 123
            return {
                "id": 123,
                "flds": [
                    {"name": field["name"], "ord": index}
                    for index, field in enumerate(model["flds"])
                ],
            }

    models = _Models()
    changed = ensure_incremento_metadata_fields(models, model, save=True)

    assert changed is True
    assert models.updated is True
    assert None not in [field["ord"] for field in model["flds"]]


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


def test_ensure_incremento_ocr_field_save_refreshes_ordinals():
    model = {"id": 124, "flds": [{"name": "Front", "ord": 0}]}

    class _Models:
        def __init__(self):
            self.updated = False

        def new_field(self, name):
            return {"name": name, "ord": None}

        def add_field(self, model_dict, field):
            model_dict["flds"].append(field)

        def update_dict(self, model_dict):
            self.updated = True

        def get(self, model_id):
            assert model_id == 124
            return {
                "id": 124,
                "flds": [
                    {"name": field["name"], "ord": index}
                    for index, field in enumerate(model["flds"])
                ],
            }

    models = _Models()
    changed = ensure_incremento_ocr_field(models, model, save=True)

    assert changed is True
    assert models.updated is True
    assert None not in [field["ord"] for field in model["flds"]]


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


def test_inline_pdf_reference_filename_extracts_citation_target():
    class _FakeNote(dict):
        fields = [
            'Excerpt<br><a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 55, \\"filename\\": \\"writer-guide.pdf\\", \\"page\\": 42}&quot;); return false;">Page 42</a>'
        ]

    assert inline_pdf_reference_filename(_FakeNote()) == "writer-guide.pdf"


def test_inline_pdf_reference_extracts_first_citation_filename_and_page():
    class _FakeNote(dict):
        fields = [
            'First <a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 55, \\"filename\\": \\"writer-guide.pdf\\", \\"page\\": 42}&quot;); return false;">Page 42</a>',
            'Second <a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 99, \\"filename\\": \\"other.pdf\\", \\"page\\": 7}&quot;); return false;">Page 7</a>',
        ]

    assert inline_pdf_reference(_FakeNote()) == {
        "filename": "writer-guide.pdf",
        "page": 42,
        "card_id": 55,
    }


def test_source_document_reference_reports_pdf_metadata_and_inline_state():
    class _FakeNote(dict):
        fields = [
            'Excerpt<br><a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 55, \\"filename\\": \\"writer-guide.pdf\\", \\"page\\": 42}&quot;); return false;">Page 42</a>'
        ]

    note = _FakeNote(
        Incremento_Source_Title="Deep Work",
        Incremento_Source_Link="pdfs/writer-guide.pdf",
    )

    result = source_document_reference(note)

    assert result == {
        "kind": "pdf",
        "title": "Deep Work",
        "link": "pdfs/writer-guide.pdf",
        "author": "",
        "filename": "writer-guide.pdf",
        "has_inline_pdf_reference": True,
    }


def test_source_document_reference_falls_back_to_inline_pdf_reference_when_metadata_is_missing():
    class _FakeNote(dict):
        fields = [
            "Atomic note",
            'Excerpt<br><a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 55, \\"filename\\": \\"writer-guide.pdf\\", \\"page\\": 42}&quot;); return false;">Page 42</a>',
        ]

    result = source_document_reference(_FakeNote())

    assert result == {
        "kind": "pdf",
        "title": "",
        "link": "pdfs/writer-guide.pdf",
        "author": "",
        "filename": "writer-guide.pdf",
        "has_inline_pdf_reference": True,
    }
