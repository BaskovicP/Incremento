import pytest

from reviewer_extract import (
    extract_default_notetype_name,
    extract_source_field_values,
    initial_extract_field_values,
    knowledge_tree_link_state,
    parse_batch_qa_text,
    visible_note_field_values,
)


class _FakeNote:
    def __init__(self):
        self._fields = {
            "Front": "Visible front",
            "Back": "Visible back",
            "Incremento_Parent": "Hidden parent",
            "Incremento_Parent_Card_ID": "999",
        }
        self._note_type = {
            "name": "Basic",
            "flds": [
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Incremento_Parent"},
                {"name": "Incremento_Parent_Card_ID"},
            ],
        }

    def note_type(self):
        return self._note_type

    def __getitem__(self, key):
        return self._fields[key]


def test_visible_note_field_values_skip_hidden_incremento_fields():
    note = _FakeNote()

    assert visible_note_field_values(note) == {
        "Front": "Visible front",
        "Back": "Visible back",
    }


def test_extract_with_selected_text_starts_without_automatic_field_content():
    note = _FakeNote()

    assert initial_extract_field_values(note, "Chosen excerpt") == {}


def test_extract_without_selection_does_not_clone_the_source_fields():
    note = _FakeNote()

    assert initial_extract_field_values(note, "") == {}


@pytest.mark.parametrize("field_name", ["Source URL", "Source_URL", "sourceUrl", "URL", "Source", "Sources"])
@pytest.mark.parametrize("selected_text", ["", "Chosen excerpt"])
def test_extract_prefills_only_source_url_without_copying_question_or_answer(field_name, selected_text):
    note = _FakeNote()
    note._fields[field_name] = "https://example.test/topic/1"
    note._note_type["flds"].append({"name": field_name})

    assert initial_extract_field_values(note, selected_text) == {
        field_name: "https://example.test/topic/1",
    }


@pytest.mark.parametrize("field_name", ["Source", "Sources"])
def test_extract_preserves_rich_sources_instead_of_replacing_them_with_a_plain_url(field_name):
    note = _FakeNote()
    rich_source = '<a href="https://example.test/video">Video title</a><br>Reference chapter 3'
    note._fields[field_name] = rich_source
    note._note_type["flds"].append({"name": field_name})
    metadata = {"Incremento_Source_Link": "https://example.test/video"}

    source_fields = initial_extract_field_values(note, "Selected paragraph")
    draft_fields = extract_source_field_values(note, metadata, source_fields)

    assert source_fields == {field_name: rich_source}
    assert draft_fields[field_name] == rich_source
    assert "Front" not in draft_fields
    assert "Back" not in draft_fields


def test_extract_default_notetype_uses_parent_for_empty_selection():
    assert extract_default_notetype_name(
        selected_text="",
        configured_notetype="Cloze",
        parent_notetype="Basic",
        available_notetype_names=["Basic", "Cloze"],
    ) == "Basic"


def test_extract_default_notetype_uses_configured_type_for_selected_text_when_available():
    assert extract_default_notetype_name(
        selected_text="excerpt",
        configured_notetype="Cloze",
        parent_notetype="Basic",
        available_notetype_names=["Basic", "Cloze"],
    ) == "Cloze"


def test_knowledge_tree_link_state_defaults_checked_when_parent_is_in_tree():
    state = knowledge_tree_link_state(True)

    assert state["enabled"] is False
    assert state["checked"] is True
    assert "added to the knowledge tree automatically" in str(state["tooltip"]).lower()


def test_knowledge_tree_link_state_disables_when_parent_is_not_in_tree():
    state = knowledge_tree_link_state(False)

    assert state["enabled"] is False
    assert state["checked"] is True
    assert "beneath their source parent" in str(state["tooltip"]).lower()


def test_parse_batch_qa_text_returns_two_valid_rows():
    rows = parse_batch_qa_text("Q: One\nA: First\n\nQ: Two\nA: Second")

    assert rows == [
        {"question": "One", "answer": "First", "valid": True, "error": ""},
        {"question": "Two", "answer": "Second", "valid": True, "error": ""},
    ]


def test_parse_batch_qa_text_accepts_alternating_question_and_answer_lines():
    rows = parse_batch_qa_text("One?\nFirst\nTwo?\nSecond")

    assert rows == [
        {"question": "One?", "answer": "First", "valid": True, "error": ""},
        {"question": "Two?", "answer": "Second", "valid": True, "error": ""},
    ]


def test_parse_batch_qa_text_marks_unpaired_question_line_invalid():
    rows = parse_batch_qa_text("One?\nFirst\nMissing answer")

    assert rows == [
        {"question": "One?", "answer": "First", "valid": True, "error": ""},
        {
            "question": "Missing answer",
            "answer": "",
            "valid": False,
            "error": "Missing answer line.",
        },
    ]


def test_parse_batch_qa_text_accepts_adjacent_labeled_pairs_without_blank_lines():
    rows = parse_batch_qa_text("Q: One\nA: First\nQ: Two\nA: Second")

    assert rows == [
        {"question": "One", "answer": "First", "valid": True, "error": ""},
        {"question": "Two", "answer": "Second", "valid": True, "error": ""},
    ]


def test_parse_batch_qa_text_preserves_multiline_question_and_answer():
    rows = parse_batch_qa_text("Q: Line one\nLine two\nA: Answer one\nAnswer two")

    assert rows == [
        {
            "question": "Line one\nLine two",
            "answer": "Answer one\nAnswer two",
            "valid": True,
            "error": "",
        }
    ]


def test_parse_batch_qa_text_marks_missing_answer_invalid():
    rows = parse_batch_qa_text("Q: Missing answer")

    assert rows == [
        {
            "question": "Missing answer",
            "answer": "",
            "valid": False,
            "error": "Missing A: line.",
        }
    ]


def test_parse_batch_qa_text_marks_empty_question_or_answer_invalid():
    rows = parse_batch_qa_text("Q:   \nA: Filled\n\nQ: Filled\nA:   ")

    assert rows == [
        {
            "question": "",
            "answer": "Filled",
            "valid": False,
            "error": "Question is empty.",
        },
        {
            "question": "Filled",
            "answer": "",
            "valid": False,
            "error": "Answer is empty.",
        },
    ]


def test_batch_validation_localizes_messages_but_preserves_qa_syntax():
    import backend.i18n as i18n
    import reviewer_extract
    old = i18n.get_locale()
    try:
        i18n.initialize_language('hr')
        row = reviewer_extract.parse_batch_qa_text('Q: Pitanje')[0]
        assert row['question'] == 'Pitanje'
        assert row['error'] == 'Nedostaje redak A:.'
        assert row['valid'] is False
        assert reviewer_extract.parse_batch_qa_text('Q: 中文\nA: 答案')[0]['answer'] == '答案'
    finally:
        i18n.initialize_language(old)
