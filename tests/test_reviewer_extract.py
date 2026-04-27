from reviewer_extract import (
    extract_default_notetype_name,
    initial_extract_field_values,
    knowledge_tree_link_state,
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


def test_initial_extract_field_values_use_selected_text_only_for_first_visible_field():
    note = _FakeNote()

    assert initial_extract_field_values(note, "Chosen excerpt") == {
        "Front": "Chosen excerpt",
    }


def test_initial_extract_field_values_clone_visible_fields_when_no_selection():
    note = _FakeNote()

    assert initial_extract_field_values(note, "") == {
        "Front": "Visible front",
        "Back": "Visible back",
    }


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

    assert state["enabled"] is True
    assert state["checked"] is True
    assert "beneath the current source card" in str(state["tooltip"]).lower()


def test_knowledge_tree_link_state_disables_when_parent_is_not_in_tree():
    state = knowledge_tree_link_state(False)

    assert state["enabled"] is False
    assert state["checked"] is False
    assert "not in the knowledge tree yet" in str(state["tooltip"]).lower()
