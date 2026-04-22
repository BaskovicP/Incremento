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
