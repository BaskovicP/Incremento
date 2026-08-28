from note_type_update_dialog import (
    ACTION_APPLY,
    ACTION_LATER,
    ACTION_SYNC_FIRST,
    format_note_type_update_html,
)
from note_type_updates import PendingNoteTypeUpdate


def test_update_dialog_explains_no_mutation_and_safe_sync_order():
    html = format_note_type_update_html(
        [
            PendingNoteTypeUpdate(
                "Incremento PDF",
                ("add fields: PDF_Cover_Image", "update the card template"),
            )
        ]
    )

    assert "has not changed your Anki collection yet" in html
    assert "Incremento PDF" in html
    assert "Sync this device normally before applying" in html
    assert "Upload to AnkiWeb" in html
    assert "other devices" in html
    assert "Later" in html


def test_update_dialog_action_values_are_distinct():
    assert {ACTION_LATER, ACTION_SYNC_FIRST, ACTION_APPLY} == {
        "later",
        "sync_first",
        "apply",
    }
