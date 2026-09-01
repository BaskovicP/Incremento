"""Canonical reader action names and accessibility metadata.

The PDF reader is the product's reference reader.  Other readers keep their own
media-specific controls, but their primary actions use this stable order and
terminology so users do not have to relearn each dock.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping


CANONICAL_PRIMARY_ACTION_IDS = (
    "back",
    "search",
    "extract",
    "bookmark",
    "review_all",
)

_SUPPORTED_READERS = {"pdf": "PDF", "epub": "EPUB", "video": "Video", "web": "Web"}


# The shipped PDF reader is the visual and interaction reference for EPUB.  Keep
# this inventory media-neutral: EPUB maps PDF pages to its reflowed pages and
# PDF zoom to EPUB text scale, while retaining the same visible control slots.
_PDF_CLONE_TOOLBAR_SPEC = (
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

_PDF_CLONE_COMPACT_ACTION_IDS = (
    "previous_page",
    "page_location",
    "next_page",
    "zoom_percent",
    "clickable_links",
    "jump_back",
    "show_controls",
    "customize",
)

_PDF_CLONE_EXPANDED_GROUP_ROWS = (
    ("navigation", "reading"),
    ("annotation", "review"),
)

# User-visible labels are part of the PDF reference, including the symbols that
# act as its icons.  Qt standard icons vary by platform and do not match the
# shipped React reader, so EPUB consumes these exact strings instead.
_PDF_CLONE_ACTION_TEXT = {
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


def reader_toolbar_clone_spec(reader_kind: str) -> tuple:
    """Return the exact PDF toolbar action inventory for PDF or EPUB."""
    kind = str(reader_kind or "").strip().casefold()
    if kind not in {"pdf", "epub"}:
        raise ValueError(f"PDF toolbar cloning is unsupported for: {reader_kind!r}")
    return _PDF_CLONE_TOOLBAR_SPEC


def reader_toolbar_compact_action_ids(reader_kind: str) -> tuple[str, ...]:
    """Return the shared PDF/EPUB compact-toolbar action order."""
    reader_toolbar_clone_spec(reader_kind)
    return _PDF_CLONE_COMPACT_ACTION_IDS


def reader_toolbar_expanded_group_rows(reader_kind: str) -> tuple[tuple[str, ...], ...]:
    """Return the PDF reference's two expanded toolbar rows."""
    reader_toolbar_clone_spec(reader_kind)
    return _PDF_CLONE_EXPANDED_GROUP_ROWS


def reader_toolbar_action_text(reader_kind: str) -> dict[str, str]:
    """Return a fresh copy of the PDF toolbar's exact visible text/icons."""
    reader_toolbar_clone_spec(reader_kind)
    return dict(_PDF_CLONE_ACTION_TEXT)


@dataclass(frozen=True)
class ReaderShellAction:
    action_id: str
    label: str
    group: str
    primary: bool = True
    available: bool = True
    unavailable_reason: str = ""


_BASE_SPEC = (
    ReaderShellAction("back", "Back", "Navigate"),
    ReaderShellAction("search", "Search", "Navigate"),
    ReaderShellAction("extract", "Extract", "Capture"),
    ReaderShellAction("bookmark", "Bookmark", "Capture"),
    ReaderShellAction("review_all", "Review All", "Review"),
    ReaderShellAction("status", "Status", "Status", primary=False),
    ReaderShellAction("more", "More", "More", primary=False),
)

_DEFAULT_CAPABILITIES = {
    "pdf": {action_id: True for action_id in CANONICAL_PRIMARY_ACTION_IDS},
    "epub": {action_id: True for action_id in CANONICAL_PRIMARY_ACTION_IDS},
    "video": {
        "back": True,
        "search": False,
        "extract": True,
        "bookmark": True,
        "review_all": True,
    },
    "web": {
        "back": True,
        "search": True,
        "extract": True,
        "bookmark": True,
        "review_all": False,
    },
}


def reader_shell_spec(
    reader_kind: str,
    *,
    capabilities: Mapping[str, bool] | None = None,
) -> tuple[ReaderShellAction, ...]:
    kind = str(reader_kind or "").strip().casefold()
    if kind not in _SUPPORTED_READERS:
        raise ValueError(f"Unsupported reader kind: {reader_kind!r}")
    resolved_capabilities = dict(_DEFAULT_CAPABILITIES[kind])
    if capabilities:
        resolved_capabilities.update(
            {str(key): bool(value) for key, value in capabilities.items()}
        )
    result: list[ReaderShellAction] = []
    for action in _BASE_SPEC:
        if action.action_id not in resolved_capabilities:
            result.append(action)
            continue
        available = resolved_capabilities[action.action_id]
        result.append(
            replace(
                action,
                available=available,
                unavailable_reason=(
                    ""
                    if available
                    else f"{action.label} is not available in the {_SUPPORTED_READERS[kind]} reader yet."
                ),
            )
        )
    return tuple(result)


def configure_reader_shell_buttons(
    reader_kind: str,
    buttons: Mapping[str, object],
    *,
    capabilities: Mapping[str, bool] | None = None,
    preserve_text: set[str] | None = None,
) -> tuple[ReaderShellAction, ...]:
    """Apply stable labels, tooltips, and accessible names to existing Qt controls."""
    spec = reader_shell_spec(reader_kind, capabilities=capabilities)
    reader_label = _SUPPORTED_READERS[str(reader_kind).strip().casefold()]
    keep_text = set(preserve_text or ())
    for action in spec:
        button = buttons.get(action.action_id)
        if button is None:
            continue
        if action.action_id not in keep_text:
            set_text = getattr(button, "setText", None)
            if callable(set_text):
                set_text(action.label)
        set_accessible_name = getattr(button, "setAccessibleName", None)
        if callable(set_accessible_name):
            set_accessible_name(f"{reader_label} reader: {action.label}")
        set_accessible_description = getattr(button, "setAccessibleDescription", None)
        if callable(set_accessible_description):
            set_accessible_description(
                action.unavailable_reason
                or f"{action.label} action in the {reader_label} reader."
            )
        set_tooltip = getattr(button, "setToolTip", None)
        if callable(set_tooltip):
            set_tooltip(
                action.unavailable_reason
                or f"{action.label} in the {reader_label} reader"
            )
        set_enabled = getattr(button, "setEnabled", None)
        if callable(set_enabled) and not action.available:
            set_enabled(False)
        set_property = getattr(button, "setProperty", None)
        if callable(set_property):
            set_property("incrementoReaderAction", action.action_id)
            set_property("incrementoReaderGroup", action.group)
    return spec
