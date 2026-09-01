from frontend.shortcut_conflicts import (
    find_shortcut_conflicts,
    normalize_shortcut_identity,
)


def test_shortcut_identity_normalizes_platform_aliases_and_modifier_order():
    assert normalize_shortcut_identity(" Command + Shift + K ") == "meta+shift+k"
    assert normalize_shortcut_identity("Shift+Meta+K") == "meta+shift+k"
    assert normalize_shortcut_identity("Option+Ctrl+P") == "ctrl+alt+p"


def test_conflict_detector_reports_every_action_sharing_a_key():
    shortcuts = {
        "palette": "Cmd+K",
        "tree": "Meta + K",
        "search": "Ctrl+F",
        "disabled": "",
    }

    conflicts = find_shortcut_conflicts(shortcuts)

    assert len(conflicts) == 1
    assert conflicts[0].shortcut == "meta+k"
    assert conflicts[0].action_ids == ("palette", "tree")
    assert shortcuts["palette"] == "Cmd+K"


def test_multistep_shortcuts_are_compared_as_a_complete_sequence():
    conflicts = find_shortcut_conflicts(
        {
            "one": "Ctrl+K, Ctrl+P",
            "two": "Control+K, Control+P",
            "three": "Ctrl+K",
        }
    )

    assert [(item.shortcut, item.action_ids) for item in conflicts] == [
        ("ctrl+k,ctrl+p", ("one", "two"))
    ]
