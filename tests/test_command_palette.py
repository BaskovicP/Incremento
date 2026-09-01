from frontend.command_palette import (
    PaletteCommand,
    build_palette_commands,
    fuzzy_score,
    rank_commands,
)


COMMANDS = [
    PaletteCommand(
        command_id="search_all",
        label="Search ALL",
        shortcut="Ctrl+Alt+S",
        group="Find",
        keywords=("global", "find"),
    ),
    PaletteCommand(
        command_id="start_learning",
        label="Start Incremental Learning",
        shortcut="",
        group="Study",
    ),
    PaletteCommand(
        command_id="search_current_document",
        label="Find In Current Document",
        shortcut="Ctrl+F",
        group="Find",
        enabled=False,
        unavailable_reason="No document is open",
    ),
]


def test_palette_ranking_prefers_exact_prefix_over_keyword_and_subsequence():
    ranked = rank_commands(COMMANDS, "search")

    assert [command.command_id for command in ranked] == ["search_all"]


def test_palette_supports_initials_and_keywords_without_case_sensitivity():
    assert fuzzy_score("sil", "Start Incremental Learning") is not None
    assert [command.command_id for command in rank_commands(COMMANDS, "GLOBAL")] == [
        "search_all"
    ]


def test_palette_keeps_unavailable_matches_visible_with_their_reason():
    ranked = rank_commands(COMMANDS, "current document", include_unavailable=True)

    assert [command.command_id for command in ranked] == [
        "search_current_document"
    ]
    assert ranked[0].unavailable_reason == "No document is open"
    assert rank_commands(COMMANDS, "current document") == []


def test_empty_query_preserves_registration_order_and_available_commands_first():
    ranked = rank_commands(COMMANDS, "", include_unavailable=True)

    assert [command.command_id for command in ranked] == [
        "search_all",
        "start_learning",
        "search_current_document",
    ]


def test_runtime_command_builder_reports_shortcuts_and_current_availability():
    class Action:
        def __init__(self, enabled):
            self._enabled = enabled

        def isEnabled(self):
            return self._enabled

    invoked = []
    commands = build_palette_commands(
        [
            {"id": "start", "label": "Start", "group": "Study"},
            {"id": "find", "label": "Find", "group": "Search"},
        ],
        {"start": [Action(True)], "find": [Action(False)]},
        {"start": "Ctrl+L", "find": "Ctrl+F"},
        invoke=lambda action_id: invoked.append(action_id),
        unavailable_reasons={"find": "No document is open"},
    )

    assert [(c.command_id, c.shortcut, c.enabled) for c in commands] == [
        ("start", "Ctrl+L", True),
        ("find", "Ctrl+F", False),
    ]
    commands[0].callback()
    assert invoked == ["start"]
    assert commands[1].unavailable_reason == "No document is open"
