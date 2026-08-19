"""Helpers for reviewer-side tag append actions."""

from __future__ import annotations


def normalize_tag_list(raw_tags) -> list[str]:
    if isinstance(raw_tags, str):
        parts = (
            raw_tags.replace("\n", " ")
            .replace(",", " ")
            .replace(";", " ")
            .split()
        )
    elif isinstance(raw_tags, (list, tuple, set)):
        parts = list(raw_tags)
    else:
        parts = []

    tags: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item or "").strip().lstrip("#")
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def append_missing_tags(existing_tags, requested_tags) -> tuple[list[str], list[str]]:
    current = normalize_tag_list(existing_tags)
    wanted = normalize_tag_list(requested_tags)
    if not wanted:
        return current, []

    updated = list(current)
    current_keys = {tag.lower() for tag in current}
    added: list[str] = []
    for tag in wanted:
        key = tag.lower()
        if key in current_keys:
            continue
        current_keys.add(key)
        updated.append(tag)
        added.append(tag)
    return updated, added


def filter_tags(tags, query: str = "") -> list[str]:
    cleaned = normalize_tag_list(tags)
    needle = str(query or "").strip().lower()
    if needle:
        cleaned = [tag for tag in cleaned if needle in tag.lower()]
    return sorted(cleaned, key=lambda value: (value.lower(), value))


def deduplicate_tag_groups(tag_groups, *, limit: int = 10) -> list[list[str]]:
    try:
        max_groups = max(1, int(limit or 10))
    except Exception:
        max_groups = 10

    recent: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for raw_group in tag_groups or []:
        tags = normalize_tag_list(raw_group)
        key = tuple(sorted(tag.casefold() for tag in tags))
        if not tags or key in seen:
            continue
        seen.add(key)
        recent.append(tags)
        if len(recent) >= max_groups:
            break
    return recent


def recent_tag_groups_from_note_rows(note_tag_rows, *, limit: int = 10) -> list[list[str]]:
    """Return distinct tag sets in the order of supplied newest-first notes."""
    groups = [
        row[0] if isinstance(row, (list, tuple)) and row else row
        for row in (note_tag_rows or [])
    ]
    return deduplicate_tag_groups(groups, limit=limit)


def tag_groups_with_new_tags(candidate_groups, known_groups, *, limit: int = 9) -> list[list[str]]:
    """Return candidate sets that introduce tags absent from the known sets."""
    known_keys = {
        tag.casefold()
        for group in deduplicate_tag_groups(known_groups, limit=max(1, len(known_groups or [])))
        for tag in group
    }
    additions: list[list[str]] = []
    for group in deduplicate_tag_groups(candidate_groups, limit=limit):
        group_keys = {tag.casefold() for tag in group}
        if not (group_keys - known_keys):
            continue
        additions.append(group)
        known_keys.update(group_keys)
        if len(additions) >= limit:
            break
    return additions
