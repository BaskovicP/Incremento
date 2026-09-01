from frontend.reader_shell import (
    CANONICAL_PRIMARY_ACTION_IDS,
    configure_reader_shell_buttons,
    reader_shell_spec,
)
import frontend.reader_shell as reader_shell


PDF_TOOLBAR_REFERENCE = (
    (
        "navigation",
        "Navigation",
        (
            ("navigate", "Navigate", ("previous_page", "page_location", "next_page")),
            ("zoom", "Zoom", ("zoom_out", "zoom_percent", "zoom_in")),
        ),
    ),
    (
        "reading",
        "Reading",
        (
            (
                "reading",
                "Reading",
                (
                    "read_to_here",
                    "exact_read_marker",
                    "clickable_links",
                    "jump_back",
                    "read_range",
                ),
            ),
            ("progress", "", ("progress_percent", "progress_segments")),
        ),
    ),
    (
        "annotation",
        "Annotation & capture",
        (
            (
                "annotate",
                "Annotate",
                (
                    "highlight_yellow",
                    "highlight_green",
                    "highlight_blue",
                    "highlight_pink",
                    "highlight_aqua",
                    "highlight_orange",
                    "highlight_red",
                    "highlight_purple",
                    "highlight_when_extracting",
                ),
            ),
            (
                "capture",
                "Capture",
                ("snapshot", "highlights", "bookmark", "bookmarks"),
            ),
        ),
    ),
    (
        "review",
        "Review & cards",
        (
            (
                "review",
                "Review",
                ("review_due", "review_all", "reading_limit", "regenerate_cover"),
            ),
            ("cards", "Cards", ("open_all_in_browser", "page_cards", "add_card")),
            ("status", "Status", ("finished_reading",)),
        ),
    ),
)

PDF_COMPACT_REFERENCE = (
    "previous_page",
    "page_location",
    "next_page",
    "zoom_percent",
    "clickable_links",
    "jump_back",
    "show_controls",
    "customize",
)

PDF_EXPANDED_ROW_REFERENCE = (
    ("navigation", "reading"),
    ("annotation", "review"),
)

PDF_ACTION_TEXT_REFERENCE = {
    "previous_page": "← Prev",
    "page_location": "Page {current} / {total}",
    "next_page": "Next →",
    "zoom_out": "−",
    "zoom_percent": "{percent}%",
    "zoom_in": "+",
    "read_to_here": "✓ Read to here",
    "exact_read_marker": "↦",
    "clickable_links": "Links {state}",
    "jump_back": "↩ Jump Back",
    "highlight_when_extracting": "Highlight when extracting",
    "snapshot": "📷 Snapshot",
    "highlights": "📑 Highlights ({count})",
    "bookmark": "★ Bookmark",
    "bookmarks": "Bookmarks ({count})",
    "review_due": "🧠 Review Due",
    "review_all": "▶ Review All",
    "reading_limit": "📖 Reading Limit",
    "regenerate_cover": "Regenerate Cover",
    "open_all_in_browser": "Open All in Browser",
    "page_cards": "📄 Page cards ({count})",
    "add_card": "+ Add Card",
    "finished_reading": "✓ Finished Reading",
}


def test_every_reader_uses_the_pdf_primary_action_order():
    for reader_kind in ("pdf", "epub", "video", "web"):
        spec = reader_shell_spec(reader_kind)
        primary_ids = tuple(action.action_id for action in spec if action.primary)

        assert primary_ids == CANONICAL_PRIMARY_ACTION_IDS


def test_unavailable_reader_capability_keeps_its_stable_visible_slot():
    spec = reader_shell_spec("video", capabilities={"search": False})
    search = next(action for action in spec if action.action_id == "search")

    assert search.label == "Search"
    assert search.available is False
    assert "not available" in search.unavailable_reason.casefold()


def test_reader_button_metadata_adds_consistent_labels_and_accessible_names():
    class Button:
        def __init__(self):
            self.text = ""
            self.accessible_name = ""
            self.accessible_description = ""
            self.tooltip = ""
            self.enabled = None
            self.properties = {}

        def setText(self, value):
            self.text = value

        def setAccessibleName(self, value):
            self.accessible_name = value

        def setAccessibleDescription(self, value):
            self.accessible_description = value

        def setToolTip(self, value):
            self.tooltip = value

        def setEnabled(self, value):
            self.enabled = bool(value)

        def setProperty(self, key, value):
            self.properties[key] = value

    buttons = {action_id: Button() for action_id in CANONICAL_PRIMARY_ACTION_IDS}

    configure_reader_shell_buttons("epub", buttons)

    assert [buttons[action_id].text for action_id in CANONICAL_PRIMARY_ACTION_IDS] == [
        "Back",
        "Search",
        "Extract",
        "Bookmark",
        "Review All",
    ]
    assert buttons["review_all"].accessible_name == "EPUB reader: Review All"
    assert "EPUB reader" in buttons["review_all"].accessible_description
    assert buttons["review_all"].properties["incrementoReaderAction"] == "review_all"


def test_unknown_reader_kind_fails_closed():
    try:
        reader_shell_spec("browser")
    except ValueError as exc:
        assert "reader" in str(exc).casefold()
    else:
        raise AssertionError("unknown reader kind must be rejected")


def test_epub_toolbar_is_an_exact_action_clone_of_the_pdf_reference():
    pdf = reader_shell.reader_toolbar_clone_spec("pdf")
    epub = reader_shell.reader_toolbar_clone_spec("epub")

    assert pdf == PDF_TOOLBAR_REFERENCE
    assert epub == pdf
    assert reader_shell.reader_toolbar_compact_action_ids("epub") == PDF_COMPACT_REFERENCE
    assert (
        reader_shell.reader_toolbar_expanded_group_rows("epub")
        == PDF_EXPANDED_ROW_REFERENCE
    )


def test_epub_toolbar_uses_the_exact_visible_pdf_text_and_icons():
    pdf = reader_shell.reader_toolbar_action_text("pdf")
    epub = reader_shell.reader_toolbar_action_text("epub")

    assert pdf == PDF_ACTION_TEXT_REFERENCE
    assert epub == pdf
    pdf["snapshot"] = "changed"
    assert reader_shell.reader_toolbar_action_text("pdf") == PDF_ACTION_TEXT_REFERENCE
