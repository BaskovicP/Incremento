import pytest

from quick_tag_shortcuts import QUICK_TAG_SLOT_COUNT, quick_tag_shortcut_keys


def test_quick_tag_slots_have_number_and_letter_shortcuts():
    assert QUICK_TAG_SLOT_COUNT == 9
    assert [quick_tag_shortcut_keys(index) for index in range(9)] == [
        ("1", "A"),
        ("2", "B"),
        ("3", "C"),
        ("4", "D"),
        ("5", "E"),
        ("6", "F"),
        ("7", "G"),
        ("8", "H"),
        ("9", "I"),
    ]


@pytest.mark.parametrize("slot_index", [-1, 9, "bad"])
def test_quick_tag_shortcuts_reject_invalid_slots(slot_index):
    with pytest.raises(ValueError):
        quick_tag_shortcut_keys(slot_index)
