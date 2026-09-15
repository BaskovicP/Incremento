"""Canonical reader action names and accessibility metadata.

The PDF reader is the product's reference reader.  Other readers keep their own
media-specific controls, but their primary actions use this stable order and
terminology so users do not have to relearn each dock.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

try:
    from ..backend.i18n import t as _backend_t
except ImportError:
    try:
        from backend.i18n import t as _backend_t
    except ImportError:  # Standalone reader tests can run before addon startup.
        _backend_t = None


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
                    "more_colors",
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
    "more_colors": "More colors…",
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

_GROUP_MESSAGE_IDS = {
    "Navigation": "reader_navigation",
    "Navigate": "reader_navigate",
    "Zoom": "reader_zoom",
    "Reading": "reader_reading",
    "Annotation & capture": "reader_annotation_capture",
    "Annotate": "reader_annotate",
    "Capture": "reader_capture",
    "Review & cards": "reader_review_cards",
    "Review": "reader_review",
    "Cards": "reader_cards",
    "Status": "reader_status",
    "More": "reader_more",
}
_ACTION_MESSAGE_IDS = {
    "back": "reader_back",
    "search": "reader_search",
    "extract": "reader_extract",
    "bookmark": "reader_bookmark",
    "review_all": "reader_review_all",
    "status": "reader_status",
    "more": "reader_more",
}
_TOOLBAR_MESSAGE_IDS = {
    key: f"reader_toolbar_{key}" if key in {"bookmark", "review_all"} else f"reader_{key}"
    for key in _PDF_CLONE_ACTION_TEXT
}
_ENGLISH_MESSAGES = {
    **{key: text for text, key in _GROUP_MESSAGE_IDS.items()},
    **{f"reader_{kind}_name": name for kind, name in _SUPPORTED_READERS.items()},
    **{key: text for key, text in zip(_ACTION_MESSAGE_IDS.values(), ("Back", "Search", "Extract", "Bookmark", "Review All", "Status", "More"))},
    **{_TOOLBAR_MESSAGE_IDS[key]: text for key, text in _PDF_CLONE_ACTION_TEXT.items()},
    "reader_accessible_name": "{reader} reader: {action}",
    "reader_accessible_description": "{action} action in the {reader} reader.",
    "reader_tooltip": "{action} in the {reader} reader",
    "reader_unavailable": "{action} is not available in the {reader} reader yet.",
}


def _t(message_id: str, **values: object) -> str:
    """Resolve display text at use time, after the addon has selected its locale."""
    if _backend_t is not None:
        translated = _backend_t(message_id, **values)
        if translated not in (message_id, "Translation unavailable"):
            return translated
    return _ENGLISH_MESSAGES[message_id].format(**values)


def _translated_toolbar_spec() -> tuple:
    return tuple(
        (
            group_id,
            _t(_GROUP_MESSAGE_IDS[group_label]),
            tuple(
                (section_id, _t(_GROUP_MESSAGE_IDS[section_label]) if section_label else "", actions)
                for section_id, section_label, actions in sections
            ),
        )
        for group_id, group_label, sections in _PDF_CLONE_TOOLBAR_SPEC
    )


def reader_toolbar_clone_spec(reader_kind: str) -> tuple:
    """Return the exact PDF toolbar action inventory for PDF or EPUB."""
    kind = str(reader_kind or "").strip().casefold()
    if kind not in {"pdf", "epub"}:
        raise ValueError(f"PDF toolbar cloning is unsupported for: {reader_kind!r}")
    return _translated_toolbar_spec()


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
    placeholders = {name: "{" + name + "}" for name in ("current", "total", "percent", "state", "count")}
    return {key: _t(message_id, **placeholders) for key, message_id in _TOOLBAR_MESSAGE_IDS.items()}


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
        label = _t(_ACTION_MESSAGE_IDS[action.action_id])
        group = _t(_GROUP_MESSAGE_IDS[action.group])
        localized_action = replace(action, label=label, group=group)
        if action.action_id not in resolved_capabilities:
            result.append(localized_action)
            continue
        available = resolved_capabilities[action.action_id]
        result.append(
            replace(
                localized_action,
                available=available,
                unavailable_reason=(
                    ""
                    if available
                    else _t("reader_unavailable", action=label, reader=_t(f"reader_{kind}_name"))
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
    reader_label = _t(f"reader_{str(reader_kind).strip().casefold()}_name")
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
            set_accessible_name(_t("reader_accessible_name", reader=reader_label, action=action.label))
        set_accessible_description = getattr(button, "setAccessibleDescription", None)
        if callable(set_accessible_description):
            set_accessible_description(
                action.unavailable_reason
                or _t("reader_accessible_description", action=action.label, reader=reader_label)
            )
        set_tooltip = getattr(button, "setToolTip", None)
        if callable(set_tooltip):
            set_tooltip(
                action.unavailable_reason
                or _t("reader_tooltip", action=action.label, reader=reader_label)
            )
        set_enabled = getattr(button, "setEnabled", None)
        if callable(set_enabled) and not action.available:
            set_enabled(False)
        set_property = getattr(button, "setProperty", None)
        if callable(set_property):
            set_property("incrementoReaderAction", action.action_id)
            set_property("incrementoReaderGroup", action.group)
    return spec
