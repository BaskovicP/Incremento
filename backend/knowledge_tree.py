from __future__ import annotations

import os
import random
import re
from datetime import date, datetime, timedelta
from collections import defaultdict

try:
    from .config_service import load_addon_config
    from aqt import mw
except Exception:
    mw = None

try:
    from .db import (
        get_knowledge_tree_node,
        get_knowledge_tree_nodes,
        set_knowledge_tree_structure,
    )
    from .note_metadata import (
        INCREMENTO_PARENT_CARD_ID_FIELD,
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        inline_pdf_reference,
        source_document_reference,
        visible_field_names,
    )
    from .paths import get_active_profile as _active_profile
    from .pdf_manager import find_live_pdf_card_by_filename, get_page
    from .priority_manager import get_priority, set_priority
except ImportError:
    from config_service import load_addon_config  # type: ignore
    from db import (  # type: ignore
        get_knowledge_tree_node,
        get_knowledge_tree_nodes,
        set_knowledge_tree_structure,
    )
    from note_metadata import (  # type: ignore
        INCREMENTO_PARENT_CARD_ID_FIELD,
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        inline_pdf_reference,
        source_document_reference,
        visible_field_names,
    )
    from paths import get_active_profile as _active_profile  # type: ignore
    from pdf_manager import find_live_pdf_card_by_filename, get_page  # type: ignore
    from priority_manager import get_priority, set_priority  # type: ignore


NODE_KIND_TOPIC = "topic"
NODE_KIND_ITEM = "item"
LINK_PLACEMENT_CHILDREN = "children"
LINK_PLACEMENT_SIBLINGS = "siblings"
_DEFAULT_TOPIC_TAGS = ["topic"]
_DEFAULT_ITEM_TAGS = ["item"]
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_SQL_VARIABLE_CHUNK_SIZE = 900


def normalize_node_kind(node_kind: str) -> str:
    kind = str(node_kind or "").strip().lower()
    if kind not in {NODE_KIND_TOPIC, NODE_KIND_ITEM}:
        raise ValueError(f"Unsupported knowledge-tree node kind: {node_kind}")
    return kind


def normalize_link_placement(placement: str) -> str:
    value = str(placement or "").strip().lower()
    if value not in {LINK_PLACEMENT_CHILDREN, LINK_PLACEMENT_SIBLINGS}:
        raise ValueError(f"Unsupported knowledge-tree link placement: {placement}")
    return value


def _normalize_tag_list(raw_tags, default: list[str] | None = None) -> list[str]:
    if isinstance(raw_tags, str):
        parts = raw_tags.replace("\n", ",").split(",")
    elif isinstance(raw_tags, (list, tuple, set)):
        parts = list(raw_tags)
    elif default is not None:
        parts = list(default)
    else:
        parts = []

    tags: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item or "").strip()
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(tag)
    return tags


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        return load_addon_config(mw.addonManager, addon_name)
    except Exception:
        return {}


def configured_topic_tags(config: dict | None = None) -> list[str]:
    cfg = _resolved_config(config)
    return _normalize_tag_list(
        (cfg or {}).get("add_card_topic_tags"),
        default=_DEFAULT_TOPIC_TAGS,
    )


def configured_item_tags(config: dict | None = None) -> list[str]:
    cfg = _resolved_config(config)
    return _normalize_tag_list(
        (cfg or {}).get("add_card_item_tags"),
        default=_DEFAULT_ITEM_TAGS,
    )


def sync_note_kind_tags(
    note,
    node_kind: str,
    *,
    topic_tags: list[str] | None = None,
    item_tags: list[str] | None = None,
) -> list[str]:
    kind = normalize_node_kind(node_kind)
    topic_tags = _normalize_tag_list(topic_tags, default=_DEFAULT_TOPIC_TAGS)
    item_tags = _normalize_tag_list(item_tags, default=_DEFAULT_ITEM_TAGS)
    wanted = topic_tags if kind == NODE_KIND_TOPIC else item_tags
    unwanted = item_tags if kind == NODE_KIND_TOPIC else topic_tags

    existing = _normalize_tag_list(getattr(note, "tags", []) or [])
    filtered = [tag for tag in existing if tag.lower() not in {t.lower() for t in unwanted}]
    existing_lower = {tag.lower() for tag in filtered}

    if "incremento" not in existing_lower:
        filtered.append("Incremento")
        existing_lower.add("incremento")

    for tag in wanted:
        lowered = tag.lower()
        if lowered not in existing_lower:
            filtered.append(tag)
            existing_lower.add(lowered)

    try:
        note.tags = filtered
    except Exception:
        pass
    return filtered


def _clone_row(row: dict) -> dict:
    return {
        "card_id": int(row["card_id"]),
        "parent_card_id": (
            None if row.get("parent_card_id") is None else int(row["parent_card_id"])
        ),
        "node_kind": normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC),
        "sort_order": int(row.get("sort_order", 0)),
        "created_at": int(row.get("created_at") or 0),
        "updated_at": int(row.get("updated_at") or 0),
    }


def _group_rows(rows: list[dict]) -> dict[int | None, list[dict]]:
    grouped: dict[int | None, list[dict]] = defaultdict(list)
    for row in rows:
        clone = _clone_row(row)
        grouped[clone["parent_card_id"]].append(clone)
    for items in grouped.values():
        items.sort(key=lambda item: (int(item.get("sort_order", 0)), int(item["card_id"])))
    return grouped


def _flatten_grouped_rows(grouped: dict[int | None, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for parent_card_id, items in grouped.items():
        for sort_order, row in enumerate(items):
            clone = _clone_row(row)
            clone["parent_card_id"] = parent_card_id
            clone["sort_order"] = sort_order
            rows.append(clone)
    return rows


def insert_knowledge_tree_node(
    addon_dir: str,
    profile: str,
    card_id: int,
    node_kind: str,
    *,
    parent_card_id: int | None = None,
    sort_order: int | None = None,
) -> None:
    kind = normalize_node_kind(node_kind)
    card_id = int(card_id)
    if parent_card_id is not None:
        parent_card_id = int(parent_card_id)
    if parent_card_id == card_id:
        raise ValueError("Knowledge-tree node cannot be its own parent.")
    if get_knowledge_tree_node(addon_dir, profile, card_id) is not None:
        raise ValueError(f"Card {card_id} is already present in the knowledge tree.")

    rows = get_knowledge_tree_nodes(addon_dir, profile)
    grouped = _group_rows(rows)
    siblings = list(grouped.get(parent_card_id, []))
    insert_at = len(siblings) if sort_order is None else max(0, min(int(sort_order), len(siblings)))
    siblings.insert(
        insert_at,
        {
            "card_id": card_id,
            "parent_card_id": parent_card_id,
            "node_kind": kind,
            "sort_order": insert_at,
        },
    )
    grouped[parent_card_id] = siblings
    set_knowledge_tree_structure(addon_dir, profile, _flatten_grouped_rows(grouped))


def delete_knowledge_tree_node(addon_dir: str, profile: str, card_id: int) -> bool:
    card_id = int(card_id)
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    target = next((row for row in rows if int(row["card_id"]) == card_id), None)
    if target is None:
        return False

    grouped = _group_rows(rows)
    parent_card_id = target.get("parent_card_id")
    siblings = list(grouped.get(parent_card_id, []))
    children = list(grouped.get(card_id, []))

    replacement: list[dict] = []
    for row in siblings:
        if int(row["card_id"]) == card_id:
            for child in children:
                clone = _clone_row(child)
                clone["parent_card_id"] = parent_card_id
                replacement.append(clone)
            continue
        replacement.append(_clone_row(row))

    grouped[parent_card_id] = replacement
    if card_id in grouped:
        del grouped[card_id]

    set_knowledge_tree_structure(addon_dir, profile, _flatten_grouped_rows(grouped))
    return True


def save_knowledge_tree_rows(addon_dir: str, profile: str, rows: list[dict]) -> None:
    normalized = []
    for row in rows:
        normalized.append(
            {
                "card_id": int(row["card_id"]),
                "parent_card_id": (
                    None
                    if row.get("parent_card_id") is None
                    else int(row["parent_card_id"])
                ),
                "node_kind": normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC),
                "sort_order": int(row.get("sort_order", 0)),
            }
        )
    set_knowledge_tree_structure(addon_dir, profile, normalized)


def reparent_knowledge_tree_node(
    addon_dir: str,
    profile: str,
    card_id: int,
    parent_card_id: int | None,
) -> bool:
    card_id = int(card_id)
    if parent_card_id is not None:
        parent_card_id = int(parent_card_id)
    if parent_card_id == card_id:
        raise ValueError("Knowledge-tree node cannot be its own parent.")

    rows = get_knowledge_tree_nodes(addon_dir, profile)
    target = next((row for row in rows if int(row["card_id"]) == card_id), None)
    if target is None:
        return False
    current_parent_id = target.get("parent_card_id")
    current_parent_id = None if current_parent_id is None else int(current_parent_id)
    if current_parent_id == parent_card_id:
        return False

    if parent_card_id is not None and not any(
        int(row["card_id"]) == parent_card_id for row in rows
    ):
        raise ValueError(
            f"Knowledge-tree parent {parent_card_id} for card {card_id} is missing."
        )

    grouped = _group_rows(rows)
    grouped[current_parent_id] = [
        row for row in grouped.get(current_parent_id, []) if int(row["card_id"]) != card_id
    ]

    moved = _clone_row(target)
    moved["parent_card_id"] = parent_card_id
    new_siblings = list(grouped.get(parent_card_id, []))
    moved["sort_order"] = len(new_siblings)
    new_siblings.append(moved)
    grouped[parent_card_id] = new_siblings

    set_knowledge_tree_structure(addon_dir, profile, _flatten_grouped_rows(grouped))
    return True


def _strip_html(text: str) -> str:
    return " ".join(_HTML_TAG_RE.sub(" ", str(text or "")).split()).strip()


def _card_title(card) -> str:
    try:
        note = card.note()
    except Exception:
        return f"Card {getattr(card, 'id', 0)}"
    fields = list(getattr(note, "fields", []) or [])
    if fields:
        title = _strip_html(fields[0])
        if title:
            return title
    return f"Card {getattr(card, 'id', 0)}"


def card_exists(card_id: int) -> bool:
    try:
        if mw is None or getattr(mw, "col", None) is None:
            return False
        mw.col.get_card(int(card_id))
        return True
    except Exception:
        return False


def get_card_metadata(card_id: int, *, addon_dir: str | None = None, profile: str | None = None) -> dict | None:
    try:
        if mw is None or getattr(mw, "col", None) is None:
            return None
        card = mw.col.get_card(int(card_id))
        note = card.note()
    except Exception:
        return None

    note_type_name = ""
    try:
        note_type = note.note_type()
        if isinstance(note_type, dict):
            note_type_name = str(note_type.get("name") or "").strip()
    except Exception:
        pass

    deck_name = ""
    try:
        did = card.odid if getattr(card, "odid", 0) else card.did
        deck = mw.col.decks.get(did)
        if deck:
            deck_name = str(deck.get("name") or "").strip()
    except Exception:
        pass

    priority = None
    if addon_dir is not None and profile is not None:
        try:
            priority = float(get_priority(addon_dir, profile, int(card_id)))
        except Exception:
            priority = None

    return {
        "card_id": int(card_id),
        "note_id": int(getattr(card, "nid", 0) or 0),
        "title": _card_title(card),
        "deck_name": deck_name,
        "note_type_name": note_type_name,
        "priority": priority,
    }


def resolve_card_pdf_target(
    card_id: int,
    *,
    addon_dir: str | None = None,
    profile: str | None = None,
) -> dict[str, str | int | bool]:
    empty = {
        "kind": "",
        "filename": "",
        "page": 0,
        "card_id": 0,
        "has_inline_citation": False,
    }
    if mw is None or getattr(mw, "col", None) is None:
        return dict(empty)

    resolved_addon_dir = str(addon_dir or _ADDON_DIR).strip() or _ADDON_DIR
    resolved_profile = str(profile or _active_profile()).strip() or _active_profile()

    card = mw.col.get_card(int(card_id))
    note = card.note()

    inline_reference = inline_pdf_reference(note) or {}
    source_reference = source_document_reference(note)

    filename = ""
    page = 1
    has_inline_citation = False

    inline_filename = os.path.basename(str(inline_reference.get("filename") or "").strip())
    if inline_filename:
        filename = inline_filename
        try:
            page = max(1, int(inline_reference.get("page") or 1))
        except Exception:
            page = 1
        has_inline_citation = True
    elif str(source_reference.get("kind") or "").strip() == "pdf":
        filename = os.path.basename(str(source_reference.get("filename") or "").strip())
    else:
        return dict(empty)

    if not filename:
        return dict(empty)

    live_card_id = 0
    try:
        resolved_card_id = find_live_pdf_card_by_filename(mw.col, filename)
        if resolved_card_id is not None:
            live_card_id = int(resolved_card_id)
    except Exception:
        live_card_id = 0

    if not has_inline_citation:
        if live_card_id > 0:
            try:
                page = max(1, int(get_page(resolved_addon_dir, resolved_profile, live_card_id) or 1))
            except Exception:
                page = 1
        else:
            page = 1

    return {
        "kind": "pdf",
        "filename": filename,
        "page": int(page),
        "card_id": int(live_card_id),
        "has_inline_citation": bool(has_inline_citation),
    }


def infer_node_kind_for_card(card_id: int) -> str:
    if mw is None or getattr(mw, "col", None) is None:
        return NODE_KIND_ITEM

    try:
        card = mw.col.get_card(int(card_id))
    except Exception:
        return NODE_KIND_ITEM

    try:
        from .topic_scheduler import is_topic_card as _is_topic_card
    except ImportError:
        try:
            from topic_scheduler import is_topic_card as _is_topic_card  # type: ignore
        except Exception:
            _is_topic_card = None  # type: ignore

    if _is_topic_card is not None:
        try:
            return NODE_KIND_TOPIC if _is_topic_card(card) else NODE_KIND_ITEM
        except Exception:
            pass

    try:
        note = card.note()
        note_tags = {
            str(tag or "").strip().lower()
            for tag in list(getattr(note, "tags", []) or [])
            if str(tag or "").strip()
        }
    except Exception:
        return NODE_KIND_ITEM

    topic_tags = {
        str(tag or "").strip().lower()
        for tag in configured_topic_tags()
        if str(tag or "").strip()
    }
    item_tags = {
        str(tag or "").strip().lower()
        for tag in configured_item_tags()
        if str(tag or "").strip()
    }
    if topic_tags and topic_tags.issubset(note_tags):
        return NODE_KIND_TOPIC
    if item_tags and item_tags.issubset(note_tags):
        return NODE_KIND_ITEM
    return NODE_KIND_ITEM


def metadata_parent_card_id(card_id: int) -> int | None:
    if mw is None or getattr(mw, "col", None) is None:
        return None

    try:
        card = mw.col.get_card(int(card_id))
        note = card.note()
        raw_value = str(note[INCREMENTO_PARENT_CARD_ID_FIELD] or "").strip()
    except Exception:
        return None

    if not raw_value:
        return None
    try:
        parent_card_id = int(raw_value)
    except Exception:
        return None
    if parent_card_id == int(card_id):
        return None
    return parent_card_id


def metadata_child_card_ids(card_id: int) -> list[int]:
    if mw is None or getattr(mw, "col", None) is None:
        return []

    try:
        note_ids = mw.col.find_notes(
            f'"{INCREMENTO_PARENT_CARD_ID_FIELD}:{int(card_id)}"'
        )
    except Exception:
        return []

    child_card_ids: list[int] = []
    seen: set[int] = set()
    for note_id in list(note_ids or []):
        try:
            card_ids = mw.col.find_cards(f"nid:{int(note_id)}")
        except Exception:
            continue
        for raw_card_id in list(card_ids or []):
            try:
                child_card_id = int(raw_card_id)
            except Exception:
                continue
            if child_card_id == int(card_id) or child_card_id in seen:
                continue
            seen.add(child_card_id)
            child_card_ids.append(child_card_id)
    child_card_ids.sort()
    return child_card_ids


def metadata_ancestor_card_ids(card_id: int) -> list[int]:
    card_id = int(card_id)
    seen: set[int] = {card_id}

    ancestors: list[int] = []
    current_card_id = card_id
    while True:
        parent_card_id = metadata_parent_card_id(current_card_id)
        if parent_card_id is None or parent_card_id in seen:
            break
        ancestors.append(parent_card_id)
        seen.add(parent_card_id)
        current_card_id = parent_card_id
    ancestors.reverse()
    return ancestors + [card_id]


def lineage_card_ids(card_id: int) -> list[int]:
    card_id = int(card_id)
    lineage = metadata_ancestor_card_ids(card_id)
    seen: set[int] = set(lineage)

    descendants: list[int] = []

    def visit_children(parent_card_id: int) -> None:
        for child_card_id in metadata_child_card_ids(parent_card_id):
            if child_card_id in seen:
                continue
            seen.add(child_card_id)
            descendants.append(child_card_id)
            visit_children(child_card_id)

    visit_children(card_id)
    return lineage + descendants


def ensure_extract_lineage_cards_in_tree(
    addon_dir: str,
    profile: str,
    *,
    source_card_id: int | None = None,
    created_card_ids=None,
    created_node_kind: str | None = None,
) -> dict:
    ordered_card_ids: list[int] = []
    seen: set[int] = set()

    def append_card(raw_card_id) -> None:
        try:
            resolved_card_id = int(raw_card_id)
        except Exception:
            return
        if resolved_card_id in seen:
            return
        seen.add(resolved_card_id)
        ordered_card_ids.append(resolved_card_id)

    if source_card_id is not None:
        for related_card_id in metadata_ancestor_card_ids(int(source_card_id)):
            append_card(related_card_id)
    for created_card_id in list(created_card_ids or []):
        append_card(created_card_id)

    created_card_id_set = {
        int(card_id)
        for card_id in list(created_card_ids or [])
        if card_id is not None
    }
    ordered_card_id_set = set(ordered_card_ids)
    source_card_id_int = None
    if source_card_id is not None:
        try:
            source_card_id_int = int(source_card_id)
        except Exception:
            source_card_id_int = None

    def desired_parent_for_card(card_id: int) -> int | None:
        metadata_parent_id = metadata_parent_card_id(card_id)
        if (
            metadata_parent_id is not None
            and metadata_parent_id != int(card_id)
            and (
                metadata_parent_id in ordered_card_id_set
                or get_knowledge_tree_node(addon_dir, profile, metadata_parent_id) is not None
            )
        ):
            return metadata_parent_id
        if (
            source_card_id_int is not None
            and int(card_id) != source_card_id_int
            and int(card_id) in created_card_id_set
            and (
                source_card_id_int in ordered_card_id_set
                or get_knowledge_tree_node(addon_dir, profile, source_card_id_int) is not None
            )
        ):
            return source_card_id_int
        return None

    linked_card_ids: list[int] = []
    reparented_card_ids: list[int] = []
    errors: list[dict] = []

    for card_id in ordered_card_ids:
        existing_node = get_knowledge_tree_node(addon_dir, profile, card_id)
        desired_parent_id = desired_parent_for_card(card_id)
        if existing_node is not None:
            current_parent_id = existing_node.get("parent_card_id")
            current_parent_id = None if current_parent_id is None else int(current_parent_id)
            if desired_parent_id is not None and current_parent_id != desired_parent_id:
                try:
                    if reparent_knowledge_tree_node(
                        addon_dir,
                        profile,
                        card_id,
                        desired_parent_id,
                    ):
                        reparented_card_ids.append(card_id)
                except Exception as exc:
                    errors.append({"card_id": card_id, "error": str(exc)})
            continue
        node_kind = (
            normalize_node_kind(created_node_kind)
            if created_node_kind and card_id in created_card_id_set
            else infer_node_kind_for_card(card_id)
        )
        try:
            link_card_to_tree(
                addon_dir,
                profile,
                card_id,
                node_kind,
                parent_card_id=desired_parent_id,
            )
            linked_card_ids.append(card_id)
        except Exception as exc:
            errors.append({"card_id": card_id, "error": str(exc)})

    return {
        "linked_card_ids": linked_card_ids,
        "linked_count": len(linked_card_ids),
        "reparented_card_ids": reparented_card_ids,
        "reparented_count": len(reparented_card_ids),
        "errors": errors,
        "error_count": len(errors),
    }


def load_knowledge_tree_nodes(
    addon_dir: str,
    profile: str,
    *,
    cleanup_missing: bool = True,
) -> list[dict]:
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    enriched: list[dict] = []
    missing: list[int] = []

    for row in rows:
        meta = get_card_metadata(int(row["card_id"]), addon_dir=addon_dir, profile=profile)
        if meta is None:
            missing.append(int(row["card_id"]))
            continue
        clone = _clone_row(row)
        clone.update(meta)
        enriched.append(clone)

    if cleanup_missing and missing:
        for stale_card_id in missing:
            delete_knowledge_tree_node(addon_dir, profile, stale_card_id)
        return load_knowledge_tree_nodes(addon_dir, profile, cleanup_missing=False)

    return enriched


def _rows_in_tree_order(rows: list[dict]) -> list[dict]:
    cloned_rows: list[dict] = []
    for row in rows:
        clone = dict(row)
        clone["card_id"] = int(row["card_id"])
        clone["parent_card_id"] = (
            None if row.get("parent_card_id") is None else int(row["parent_card_id"])
        )
        clone["node_kind"] = normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC)
        clone["sort_order"] = int(row.get("sort_order", 0))
        cloned_rows.append(clone)

    grouped: dict[int | None, list[dict]] = defaultdict(list)
    for row in cloned_rows:
        grouped[row.get("parent_card_id")].append(row)
    for items in grouped.values():
        items.sort(key=lambda item: (int(item.get("sort_order", 0)), int(item["card_id"])))

    row_by_card_id = {int(row["card_id"]): row for row in cloned_rows}

    ordered: list[dict] = []
    seen: set[int] = set()

    root_rows: list[dict] = list(grouped.get(None, []))
    for row in cloned_rows:
        card_id = int(row["card_id"])
        parent_card_id = row.get("parent_card_id")
        if parent_card_id is None:
            continue
        parent_card_id = int(parent_card_id)
        if parent_card_id == card_id or parent_card_id not in row_by_card_id:
            root_rows.append(row)

    def visit(row: dict) -> None:
        card_id = int(row["card_id"])
        if card_id in seen:
            return
        seen.add(card_id)
        ordered.append(row)
        for child_row in grouped.get(card_id, []):
            visit(child_row)

    for row in root_rows:
        visit(row)

    for row in cloned_rows:
        visit(row)

    return ordered


def _visible_note_text_matches(card_id: int, query_text: str) -> list[str]:
    if mw is None or getattr(mw, "col", None) is None:
        return []

    try:
        card = mw.col.get_card(int(card_id))
        note = card.note()
    except Exception:
        return []

    field_defs = []
    try:
        note_type = note.note_type()
        if isinstance(note_type, dict):
            field_defs = list(note_type.get("flds") or [])
    except Exception:
        field_defs = []

    field_names = [
        str((field or {}).get("name") or "").strip()
        for field in field_defs
        if str((field or {}).get("name") or "").strip()
    ]
    visible_names = visible_field_names(field_names)
    if visible_names:
        visible_names = visible_names[1:]

    matched_fields: list[str] = []
    for field_name in visible_names:
        try:
            raw_value = note[field_name]
        except Exception:
            raw_value = ""
        cleaned_value = _strip_html(str(raw_value or ""))
        if cleaned_value and query_text in cleaned_value.casefold():
            matched_fields.append(field_name)
    return matched_fields


def _search_match_reason(match_source: str, matched_fields: list[str]) -> str:
    if match_source == "title":
        return "Title match"
    if match_source == "metadata":
        labels: list[str] = []
        if "deck_name" in matched_fields:
            labels.append("deck")
        if "note_type_name" in matched_fields:
            labels.append("note type")
        if "card_id" in matched_fields:
            labels.append("card id")
        if labels:
            return "Metadata: " + ", ".join(labels)
        return "Metadata match"

    note_fields = [
        field_name.split(":", 1)[1]
        for field_name in matched_fields
        if field_name.startswith("field:")
    ]
    if not note_fields:
        return "Card text match"
    summary = ", ".join(note_fields[:2])
    extra = len(note_fields) - 2
    if extra > 0:
        summary += f" +{extra}"
    return f"Card text: {summary}"


def search_knowledge_tree_nodes(
    addon_dir: str,
    profile: str,
    query: str,
    *,
    include_title: bool = True,
    include_metadata: bool = False,
    include_note_text: bool = False,
    limit: int | None = None,
) -> list[dict]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return []
    if not (include_title or include_metadata or include_note_text):
        return []

    query_text = normalized_query.casefold()
    rows = load_knowledge_tree_nodes(addon_dir, profile, cleanup_missing=False)
    ordered_rows = _rows_in_tree_order(rows)
    max_results = None if limit is None else max(1, int(limit))

    results: list[dict] = []
    for row in ordered_rows:
        card_id = int(row["card_id"])
        matched_fields: list[str] = []

        if include_title:
            title = str(row.get("title") or "")
            if title and query_text in title.casefold():
                matched_fields.append("title")

        if include_metadata:
            deck_name = str(row.get("deck_name") or "")
            note_type_name = str(row.get("note_type_name") or "")
            if deck_name and query_text in deck_name.casefold():
                matched_fields.append("deck_name")
            if note_type_name and query_text in note_type_name.casefold():
                matched_fields.append("note_type_name")
            if query_text in str(card_id).casefold():
                matched_fields.append("card_id")

        if include_note_text:
            matched_fields.extend(
                [f"field:{name}" for name in _visible_note_text_matches(card_id, query_text)]
            )

        if not matched_fields:
            continue

        if "title" in matched_fields:
            match_source = "title"
        elif any(
            field_name in {"deck_name", "note_type_name", "card_id"}
            for field_name in matched_fields
        ):
            match_source = "metadata"
        else:
            match_source = "note_text"

        results.append(
            {
                "card_id": card_id,
                "title": str(row.get("title") or f"Card {card_id}").strip() or f"Card {card_id}",
                "node_kind": normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC),
                "deck_name": str(row.get("deck_name") or "").strip(),
                "note_type_name": str(row.get("note_type_name") or "").strip(),
                "match_source": match_source,
                "matched_fields": matched_fields,
                "match_reason": _search_match_reason(match_source, matched_fields),
            }
        )
        if max_results is not None and len(results) >= max_results:
            break

    return results


def _save_note(note) -> None:
    try:
        mw.col.update_note(note)
        return
    except Exception:
        pass
    try:
        note.flush()
    except Exception:
        pass


def apply_node_kind_to_card(card_id: int, node_kind: str) -> list[str]:
    kind = normalize_node_kind(node_kind)
    if mw is None or getattr(mw, "col", None) is None:
        raise RuntimeError("Anki collection is not available.")

    card = mw.col.get_card(int(card_id))
    note = card.note()
    tags = sync_note_kind_tags(
        note,
        kind,
        topic_tags=configured_topic_tags(),
        item_tags=configured_item_tags(),
    )
    _save_note(note)
    return tags


def apply_node_kind_to_cards(card_ids, node_kind: str) -> dict:
    kind = normalize_node_kind(node_kind)
    changed_card_ids: list[int] = []
    errors: list[dict] = []
    seen: set[int] = set()

    for raw_card_id in list(card_ids or []):
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        try:
            apply_node_kind_to_card(card_id, kind)
            changed_card_ids.append(card_id)
        except Exception as exc:
            errors.append({"card_id": card_id, "error": str(exc)})

    return {
        "node_kind": kind,
        "changed_card_ids": changed_card_ids,
        "changed_count": len(changed_card_ids),
        "errors": errors,
        "error_count": len(errors),
    }


def rename_card_title(card_id: int, title: str) -> str:
    title = str(title or "").strip()
    if not title:
        raise ValueError("Knowledge-tree titles cannot be empty.")
    if mw is None or getattr(mw, "col", None) is None:
        raise RuntimeError("Anki collection is not available.")

    card = mw.col.get_card(int(card_id))
    note = card.note()
    fields = list(getattr(note, "fields", []) or [])
    if not fields:
        raise RuntimeError("Linked card note has no editable title field.")
    first_field_name = ""
    try:
        note_type = note.note_type()
        if isinstance(note_type, dict):
            first_field_name = str(note_type["flds"][0]["name"] or "").strip()
    except Exception:
        first_field_name = ""

    current_title = _strip_html(fields[0])
    if current_title == title:
        return title

    if first_field_name:
        note[first_field_name] = title
    else:
        note.fields[0] = title
    _save_note(note)
    return title


def available_note_type_names() -> list[str]:
    return [spec["name"] for spec in available_note_types()]


def available_note_types() -> list[dict]:
    try:
        if mw is None or getattr(mw, "col", None) is None:
            return []
        out: list[dict] = []
        for model in list(mw.col.models.all() or []):
            name = str(model.get("name") or "").strip()
            if not name:
                continue
            fields = [
                str(field.get("name") or "").strip()
                for field in list(model.get("flds") or [])
                if str(field.get("name") or "").strip()
            ]
            fields = visible_field_names(fields)
            out.append({"name": name, "fields": fields})
        out.sort(key=lambda item: item["name"].casefold())
        return out
    except Exception:
        return []


def note_type_field_names(note_type_name: str) -> list[str]:
    target = str(note_type_name or "").strip()
    for spec in available_note_types():
        if spec["name"] == target:
            return list(spec.get("fields") or [])
    return []


def available_deck_names() -> list[str]:
    try:
        if mw is None or getattr(mw, "col", None) is None:
            return []
        names: list[str] = []
        for deck in list(mw.col.decks.all_names_and_ids() or []):
            name = str(getattr(deck, "name", "") or "").strip()
            if name:
                names.append(name)
        return sorted(set(names))
    except Exception:
        return []


def default_note_type_name(parent_card_id: int | None = None) -> str:
    available = available_note_type_names()
    if not available:
        return ""

    if parent_card_id is not None:
        meta = get_card_metadata(parent_card_id)
        parent_name = str((meta or {}).get("note_type_name") or "").strip()
        if parent_name in available:
            return parent_name

    configured = str(_resolved_config().get("extract_notetype") or "").strip()
    if configured in available:
        return configured
    if "Basic" in available:
        return "Basic"
    return available[0]


def default_deck_name(parent_card_id: int | None = None) -> str:
    available = available_deck_names()
    if not available:
        return "Topics"

    if parent_card_id is not None:
        meta = get_card_metadata(parent_card_id)
        parent_name = str((meta or {}).get("deck_name") or "").strip()
        if parent_name in available:
            return parent_name

    if "Topics" in available:
        return "Topics"
    return available[0]


def create_card_for_node(
    note_type_name: str,
    deck_name: str,
    title: str,
    node_kind: str,
    field_values: dict[str, str] | None = None,
    metadata: dict[str, str] | None = None,
) -> int:
    kind = normalize_node_kind(node_kind)
    if mw is None or getattr(mw, "col", None) is None:
        raise RuntimeError("Anki collection is not available.")

    model = mw.col.models.by_name(str(note_type_name or "").strip())
    if model is None:
        raise RuntimeError(f"Note type '{note_type_name}' was not found.")
    try:
        ensure_incremento_metadata_fields(mw.col.models, model, save=True)
    except TypeError:
        if ensure_incremento_metadata_fields(mw.col.models, model):
            try:
                mw.col.models.update_dict(model)
            except Exception:
                pass

    deck = mw.col.decks.by_name(str(deck_name or "").strip())
    if deck is None:
        deck_id = mw.col.decks.add_normal_deck_with_name(str(deck_name or "Topics")).id
    else:
        deck_id = deck["id"]

    first_field = str(model["flds"][0]["name"] or "").strip()
    if not first_field:
        raise RuntimeError("Selected note type does not expose a first field.")

    raw_first_field = ""
    normalized_fields: dict[str, str] = {}
    for field in list(model.get("flds") or []):
        field_name = str(field.get("name") or "").strip()
        if not field_name:
            continue
        value = ""
        if field_values is not None:
            value = str((field_values or {}).get(field_name) or "")
        normalized_fields[field_name] = value
    raw_first_field = str(normalized_fields.get(first_field) or title or "")
    if not _strip_html(raw_first_field):
        raise ValueError("Knowledge-tree cards need a value in the first field.")

    for attempt in range(25):
        stored_title = raw_first_field.rstrip()
        if attempt > 0:
            stored_title = f"{stored_title} [{attempt + 1}]"
        note = mw.col.new_note(model)
        for field_name, value in normalized_fields.items():
            note[field_name] = value
        note[first_field] = stored_title
        apply_incremento_metadata(
            note,
            metadata
            or build_incremento_metadata(
                source_type="Knowledge Tree",
                source_title=title,
            ),
        )
        sync_note_kind_tags(
            note,
            kind,
            topic_tags=configured_topic_tags(),
            item_tags=configured_item_tags(),
        )
        note.note_type()["did"] = deck_id
        added = mw.col.add_note(note, deck_id)
        if not added:
            continue
        cards = mw.col.find_cards(f"nid:{note.id}")
        if cards:
            return int(cards[0])

    raise RuntimeError("Failed to add the knowledge-tree card. Anki rejected the note.")


def link_card_to_tree(
    addon_dir: str,
    profile: str,
    card_id: int,
    node_kind: str,
    *,
    parent_card_id: int | None = None,
    sort_order: int | None = None,
) -> None:
    result = link_cards_to_tree(
        addon_dir,
        profile,
        [card_id],
        node_kind,
        parent_card_id=parent_card_id,
        sort_order=sort_order,
    )
    if result["linked_count"] >= 1:
        return
    errors = result.get("errors") or []
    if errors:
        raise RuntimeError(str(errors[0].get("error") or "Failed to link the selected card."))
    raise RuntimeError("Failed to link the selected card.")


def link_cards_to_tree(
    addon_dir: str,
    profile: str,
    card_ids,
    node_kind: str,
    *,
    parent_card_id: int | None = None,
    sort_order: int | None = None,
    insert_after_card_id: int | None = None,
) -> dict:
    kind = normalize_node_kind(node_kind)
    if parent_card_id is not None:
        parent_card_id = int(parent_card_id)
    if insert_after_card_id is not None:
        insert_after_card_id = int(insert_after_card_id)

    rows = get_knowledge_tree_nodes(addon_dir, profile)
    grouped = _group_rows(rows)
    siblings = list(grouped.get(parent_card_id, []))

    insert_at = len(siblings) if sort_order is None else max(0, min(int(sort_order), len(siblings)))
    if insert_after_card_id is not None:
        insert_at = len(siblings)
        for index, row in enumerate(siblings):
            if int(row["card_id"]) == insert_after_card_id:
                insert_at = index + 1
                break

    linked_card_ids: list[int] = []
    errors: list[dict] = []
    seen: set[int] = set()

    for raw_card_id in list(card_ids or []):
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)

        if parent_card_id == card_id:
            errors.append(
                {
                    "card_id": card_id,
                    "error": "Knowledge-tree node cannot be its own parent.",
                }
            )
            continue

        try:
            if not card_exists(card_id):
                raise RuntimeError(f"Card {card_id} was not found in the current collection.")
            if get_knowledge_tree_node(addon_dir, profile, card_id) is not None:
                raise RuntimeError(f"Card {card_id} is already present in the knowledge tree.")
            apply_node_kind_to_card(card_id, kind)
        except Exception as exc:
            errors.append({"card_id": card_id, "error": str(exc)})
            continue

        linked_card_ids.append(card_id)

    if linked_card_ids:
        for offset, card_id in enumerate(linked_card_ids):
            siblings.insert(
                insert_at + offset,
                {
                    "card_id": int(card_id),
                    "parent_card_id": parent_card_id,
                    "node_kind": kind,
                    "sort_order": insert_at + offset,
                },
            )
        grouped[parent_card_id] = siblings
        set_knowledge_tree_structure(addon_dir, profile, _flatten_grouped_rows(grouped))

    return {
        "node_kind": kind,
        "linked_card_ids": linked_card_ids,
        "linked_count": len(linked_card_ids),
        "errors": errors,
        "error_count": len(errors),
    }


def search_linkable_cards(
    query: str,
    *,
    exclude_card_ids: set[int] | None = None,
    limit: int = 200,
) -> list[dict]:
    if mw is None or getattr(mw, "col", None) is None:
        return []

    exclude_card_ids = {int(card_id) for card_id in (exclude_card_ids or set())}
    limit = max(1, int(limit))
    query = str(query or "").strip()

    rows = []
    for sort_field_column in ("sfld", "sf"):
        sql = (
            f"SELECT c.id, n.{sort_field_column}, n.mid, c.did "
            "FROM cards c "
            "JOIN notes n ON n.id = c.nid "
        )
        params: list[object] = []
        if query:
            sql += f"WHERE lower(n.{sort_field_column}) LIKE lower(?) "
            params.append(f"%{query}%")
        sql += "ORDER BY c.id DESC LIMIT ?"
        params.append(max(limit * 3, limit))

        try:
            rows = list(mw.col.db.all(sql, *params) or [])
            break
        except Exception:
            rows = []
            continue

    results: list[dict] = []
    for card_id, title, mid, did in rows:
        card_id = int(card_id)
        if card_id in exclude_card_ids:
            continue

        note_type_name = ""
        try:
            model = mw.col.models.get(mid)
            if model:
                note_type_name = str(model.get("name") or "").strip()
        except Exception:
            pass

        deck_name = ""
        try:
            deck = mw.col.decks.get(did)
            if deck:
                deck_name = str(deck.get("name") or "").strip()
        except Exception:
            pass

        results.append(
            {
                "card_id": card_id,
                "title": str(title or "").strip() or f"Card {card_id}",
                "note_type_name": note_type_name,
                "deck_name": deck_name,
            }
        )
        if len(results) >= limit:
            break

    return results


def descendant_card_ids(rows: list[dict], root_card_id: int) -> list[int]:
    infos = subtree_node_infos(rows, root_card_id)
    return [int(info["card_id"]) for info in infos if int(info.get("depth", 0)) > 0]


def subtree_card_ids(
    rows: list[dict],
    root_card_id: int,
    *,
    include_root: bool = True,
) -> list[int]:
    infos = subtree_node_infos(rows, root_card_id)
    if include_root:
        return [int(info["card_id"]) for info in infos]
    return [int(info["card_id"]) for info in infos if int(info.get("depth", 0)) > 0]


def get_parent_card_id(addon_dir: str, profile: str, card_id: int) -> int | None:
    row = get_knowledge_tree_node(addon_dir, profile, int(card_id))
    if row is None or row.get("parent_card_id") is None:
        return None
    return int(row["parent_card_id"])


def ancestor_card_ids(rows: list[dict], card_id: int) -> list[int]:
    row_by_card_id = {int(row["card_id"]): row for row in rows}
    current_card_id = int(card_id)
    ancestors: list[int] = []
    seen: set[int] = set()

    while True:
        row = row_by_card_id.get(current_card_id)
        if row is None:
            break
        parent_card_id = row.get("parent_card_id")
        if parent_card_id is None:
            break
        parent_card_id = int(parent_card_id)
        if parent_card_id in seen:
            break
        ancestors.append(parent_card_id)
        seen.add(parent_card_id)
        current_card_id = parent_card_id

    ancestors.reverse()
    return ancestors


def subtree_node_infos(rows: list[dict], root_card_id: int) -> list[dict]:
    root_card_id = int(root_card_id)
    row_by_card_id = {
        int(row["card_id"]): _clone_row(row)
        for row in rows
    }
    root_row = row_by_card_id.get(root_card_id)
    if root_row is None:
        return []

    grouped = _group_rows(rows)
    infos: list[dict] = []
    queue: list[tuple[dict, int]] = [(root_row, 0)]
    while queue:
        row, depth = queue.pop(0)
        clone = _clone_row(row)
        clone["depth"] = int(depth)
        infos.append(clone)
        for child_row in grouped.get(int(clone["card_id"]), []):
            queue.append((child_row, depth + 1))
    return infos


def subtree_priority_stats(addon_dir: str, profile: str, root_card_id: int) -> dict:
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    infos = subtree_node_infos(rows, int(root_card_id))
    if not infos:
        return {
            "exists": False,
            "total_count": 0,
            "descendant_count": 0,
            "direct_child_count": 0,
            "max_depth": 0,
            "min_priority": None,
            "max_priority": None,
            "selected_priority": None,
        }

    grouped = _group_rows(rows)
    priorities = [
        float(get_priority(addon_dir, profile, int(info["card_id"])))
        for info in infos
    ]
    return {
        "exists": True,
        "total_count": len(infos),
        "descendant_count": max(0, len(infos) - 1),
        "direct_child_count": len(grouped.get(int(root_card_id), [])),
        "max_depth": max(int(info.get("depth", 0)) for info in infos),
        "min_priority": min(priorities) if priorities else None,
        "max_priority": max(priorities) if priorities else None,
        "selected_priority": priorities[0] if priorities else None,
    }


def _summary_priority_text(value) -> str:
    if value is None:
        return "Default"
    try:
        return f"{float(value):.0f}"
    except Exception:
        return "Default"


def describe_branch_summary(stats: dict | None) -> dict[str, str]:
    raw = stats or {}
    total_count = max(0, int(raw.get("total_count") or 0))
    direct_child_count = max(0, int(raw.get("direct_child_count") or 0))
    descendant_count = max(0, int(raw.get("descendant_count") or 0))
    nested_descendant_count = max(0, descendant_count - direct_child_count)
    levels_below = max(0, int(raw.get("max_depth") or 0))

    selected_priority = _summary_priority_text(raw.get("selected_priority"))
    min_priority = raw.get("min_priority")
    max_priority = raw.get("max_priority")

    if total_count <= 0:
        return {
            "size_line": "Select a topic or item to inspect this branch.",
            "children_line": "",
            "levels_line": "",
            "selected_priority_line": "",
            "range_line": "",
            "impact_line": (
                "Study Branch and Postpone will explain how many cards are affected "
                "once a node is selected."
            ),
        }

    size_line = f"This branch contains {total_count} card{'s' if total_count != 1 else ''} total."
    if descendant_count <= 0:
        children_line = "Children: no child cards yet."
        impact_line = (
            "Study Branch and Postpone will affect only this card until you add children."
        )
    else:
        child_parts = [
            f"{direct_child_count} direct {'child' if direct_child_count == 1 else 'children'}"
        ]
        if nested_descendant_count:
            child_parts.append(
                f"{nested_descendant_count} deeper descendant"
                f"{'' if nested_descendant_count == 1 else 's'}"
            )
        children_line = "Children: " + " and ".join(child_parts) + "."
        impact_line = (
            f"Study Branch and Postpone can affect {total_count} "
            f"card{'' if total_count == 1 else 's'} in this branch."
        )

    levels_line = f"Levels below this node: {levels_below}."
    selected_priority_line = f"Selected node priority: {selected_priority}."

    if total_count <= 1 or min_priority is None or max_priority is None:
        range_line = ""
    else:
        low = _summary_priority_text(min_priority)
        high = _summary_priority_text(max_priority)
        if low == high:
            range_line = f"Priority across this branch: {low}."
        else:
            range_line = f"Priority range across this branch: {low} to {high}."

    return {
        "size_line": size_line,
        "children_line": children_line,
        "levels_line": levels_line,
        "selected_priority_line": selected_priority_line,
        "range_line": range_line,
        "impact_line": impact_line,
    }


def _collection_available() -> bool:
    return mw is not None and getattr(mw, "col", None) is not None


def _format_calendar_day(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    return value.strftime("%b %d, %Y")


def _latest_revlog_by_card_id(card_ids: list[int]) -> dict[int, int]:
    if not card_ids or not _collection_available():
        return {}
    db = getattr(mw.col, "db", None)
    if db is None or not hasattr(db, "all"):
        return {}

    latest: dict[int, int] = {}
    for start in range(0, len(card_ids), _SQL_VARIABLE_CHUNK_SIZE):
        chunk = card_ids[start : start + _SQL_VARIABLE_CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        sql = (
            f"SELECT cid, MAX(id) "
            f"FROM revlog "
            f"WHERE cid IN ({placeholders}) "
            f"GROUP BY cid"
        )
        try:
            rows = list(db.all(sql, *chunk) or [])
        except Exception:
            continue
        for cid, review_id in rows:
            try:
                latest[int(cid)] = int(review_id or 0)
            except Exception:
                continue
    return latest


def _last_review_label(review_id: int | None) -> tuple[str, float]:
    if not review_id:
        return ("", float("-inf"))
    try:
        dt = datetime.fromtimestamp(int(review_id) / 1000.0)
    except Exception:
        return ("", float("-inf"))
    return (_format_calendar_day(dt), dt.timestamp())


def _next_review_label(card) -> tuple[str, float]:
    if card is None:
        return ("", float("inf"))

    queue = int(getattr(card, "queue", getattr(card, "type", 0)) or 0)
    card_type = int(getattr(card, "type", 0) or 0)
    due = getattr(card, "due", None)

    if queue == -1:
        return ("Suspended", float("inf"))
    if queue in {-2, -3}:
        return ("Buried", float("inf"))
    if card_type == 0 or queue == 0:
        return ("New", float("inf"))
    if due in (None, ""):
        return ("", float("inf"))

    try:
        due_value = int(due)
    except Exception:
        return (str(due), float("inf"))

    # Learning cards typically store an absolute timestamp in seconds.
    if abs(due_value) >= 100000000:
        try:
            due_dt = datetime.fromtimestamp(due_value)
            return (_format_calendar_day(due_dt), due_dt.timestamp())
        except Exception:
            return (str(due_value), float(due_value))

    today = getattr(getattr(mw.col, "sched", None), "today", None) if _collection_available() else None
    if today is None:
        return (str(due_value), float(due_value))

    try:
        delta_days = int(due_value) - int(today)
        due_day = date.today() + timedelta(days=delta_days)
    except Exception:
        return (str(due_value), float(due_value))
    return (_format_calendar_day(due_day), float(due_day.toordinal()))


def build_subset_review_rows(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    *,
    include_descendants: bool = True,
) -> list[dict]:
    if not _collection_available():
        return []

    rows = get_knowledge_tree_nodes(addon_dir, profile)
    infos = subtree_node_infos(rows, int(root_card_id))
    if not include_descendants and infos:
        infos = infos[:1]
    if not infos:
        return []

    card_ids = [int(info["card_id"]) for info in infos]
    latest_reviews = _latest_revlog_by_card_id(card_ids)
    subset_rows: list[dict] = []

    try:
        from .db import get_topic_schedule
    except ImportError:
        from db import get_topic_schedule  # type: ignore

    for tree_index, info in enumerate(infos, start=1):
        card_id = int(info["card_id"])
        meta = get_card_metadata(card_id, addon_dir=addon_dir, profile=profile)
        if meta is None:
            continue
        try:
            card = mw.col.get_card(card_id)
        except Exception:
            continue

        node_kind = normalize_node_kind(info.get("node_kind") or NODE_KIND_TOPIC)
        priority = meta.get("priority")
        try:
            priority_value = None if priority is None else float(priority)
        except Exception:
            priority_value = None

        a_factor = None
        interval = max(0, int(getattr(card, "ivl", 0) or 0))
        if node_kind == NODE_KIND_TOPIC:
            try:
                a_factor, topic_interval = get_topic_schedule(addon_dir, profile, card_id)
                interval = max(interval, max(0, int(topic_interval or 0)))
            except Exception:
                a_factor = None

        next_review_text, next_review_sort = _next_review_label(card)
        last_review_text, last_review_sort = _last_review_label(latest_reviews.get(card_id))
        title = str(meta.get("title") or f"Card {card_id}")
        depth = max(0, int(info.get("depth", 0) or 0))
        display_title = f"{'  ' * depth}{title}" if depth else title

        subset_rows.append(
            {
                "row_number": tree_index,
                "tree_index": tree_index,
                "depth": depth,
                "card_id": card_id,
                "note_id": int(meta.get("note_id") or 0),
                "title": title,
                "display_title": display_title,
                "node_kind": node_kind,
                "priority": priority_value,
                "interval": int(interval),
                "next_review": next_review_text,
                "next_review_sort": next_review_sort,
                "last_review": last_review_text,
                "last_review_sort": last_review_sort,
                "reps": int(getattr(card, "reps", 0) or 0),
                "lapses": int(getattr(card, "lapses", 0) or 0),
                "a_factor": (
                    None
                    if a_factor is None
                    else round(float(a_factor), 3)
                ),
                "deck_name": str(meta.get("deck_name") or ""),
                "note_type_name": str(meta.get("note_type_name") or ""),
            }
        )

    return subset_rows


def build_branch_study_scope(
    addon_dir: str,
    profile: str,
    root_card_id: int,
) -> dict | None:
    rows = load_knowledge_tree_nodes(addon_dir, profile, cleanup_missing=False)
    infos = subtree_node_infos(rows, int(root_card_id))
    if not infos:
        return None

    root_info = infos[0]
    card_ids = [int(info["card_id"]) for info in infos]
    return {
        "root_card_id": int(root_card_id),
        "root_title": str(root_info.get("title") or f"Card {int(root_card_id)}"),
        "card_ids": card_ids,
    }


def get_card_priority_context(addon_dir: str, profile: str, card_id: int) -> dict:
    priority = float(get_priority(addon_dir, profile, int(card_id)))
    is_topic = False
    a_factor = None
    interval = None

    try:
        from .topic_scheduler import is_topic_card
        from .db import get_topic_schedule
    except ImportError:
        from topic_scheduler import is_topic_card  # type: ignore
        from db import get_topic_schedule  # type: ignore

    try:
        card = mw.col.get_card(int(card_id)) if mw is not None and getattr(mw, "col", None) is not None else None
    except Exception:
        card = None

    if card is not None:
        try:
            is_topic = bool(is_topic_card(card))
        except Exception:
            is_topic = False

    if is_topic:
        try:
            a_factor, interval = get_topic_schedule(addon_dir, profile, int(card_id))
        except Exception:
            a_factor = None
            interval = None

    return {
        "priority": priority,
        "is_topic": is_topic,
        "a_factor": a_factor,
        "interval": interval,
    }


def _clamp_priority(priority: float) -> float:
    return round(max(0.0, min(100.0, float(priority))), 4)


def set_selected_card_priority(
    addon_dir: str,
    profile: str,
    card_id: int,
    priority: float,
    *,
    a_factor: float | None = None,
) -> dict:
    clamped_priority = _clamp_priority(priority)
    set_priority(addon_dir, profile, int(card_id), clamped_priority)

    context = get_card_priority_context(addon_dir, profile, int(card_id))
    if a_factor is not None and context.get("is_topic"):
        try:
            from .db import set_topic_schedule
        except ImportError:
            from db import set_topic_schedule  # type: ignore

        interval = int(context.get("interval") or 1)
        set_topic_schedule(
            addon_dir,
            profile,
            int(card_id),
            float(a_factor),
            interval,
        )
        context["a_factor"] = round(float(a_factor), 3)
        context["interval"] = interval

    context["priority"] = clamped_priority
    return context


def _subtree_target_infos(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    *,
    include_root: bool = True,
) -> list[dict]:
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    infos = subtree_node_infos(rows, int(root_card_id))
    if include_root:
        return infos
    return [info for info in infos if int(info.get("depth", 0)) > 0]


def shift_subtree_priorities(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    delta: float,
    *,
    include_root: bool = True,
) -> int:
    try:
        delta_value = float(delta)
    except Exception:
        return 0
    if abs(delta_value) < 1e-9:
        return 0

    infos = _subtree_target_infos(
        addon_dir,
        profile,
        int(root_card_id),
        include_root=include_root,
    )
    for info in infos:
        card_id = int(info["card_id"])
        current = float(get_priority(addon_dir, profile, card_id))
        set_priority(addon_dir, profile, card_id, _clamp_priority(current + delta_value))
    return len(infos)


def spread_subtree_priorities(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    start_priority: float,
    end_priority: float,
    *,
    include_root: bool = False,
) -> int:
    infos = _subtree_target_infos(
        addon_dir,
        profile,
        int(root_card_id),
        include_root=include_root,
    )
    if not infos:
        return 0

    start_value = _clamp_priority(start_priority)
    end_value = _clamp_priority(end_priority)
    max_depth = max(int(info.get("depth", 0)) for info in infos)
    origin_depth = 0 if include_root else 1
    depth_span = max(0, max_depth - origin_depth)

    for info in infos:
        depth = int(info.get("depth", 0))
        if depth_span == 0:
            ratio = 0.0 if include_root else 1.0
        else:
            ratio = (depth - origin_depth) / depth_span
        next_priority = start_value + ((end_value - start_value) * ratio)
        set_priority(
            addon_dir,
            profile,
            int(info["card_id"]),
            _clamp_priority(next_priority),
        )
    return len(infos)


def randomize_subtree_priorities(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    minimum_priority: float,
    maximum_priority: float,
    *,
    include_root: bool = True,
    seed: int | None = None,
) -> int:
    infos = _subtree_target_infos(
        addon_dir,
        profile,
        int(root_card_id),
        include_root=include_root,
    )
    if not infos:
        return 0

    lower = _clamp_priority(minimum_priority)
    upper = _clamp_priority(maximum_priority)
    if lower > upper:
        lower, upper = upper, lower

    rng = random.Random(seed)
    for info in infos:
        if abs(upper - lower) < 1e-9:
            next_priority = lower
        else:
            next_priority = rng.uniform(lower, upper)
        set_priority(
            addon_dir,
            profile,
            int(info["card_id"]),
            _clamp_priority(next_priority),
        )
    return len(infos)


def _important_priority_end(lower_is_more_important: bool) -> float:
    return 0.0 if lower_is_more_important else 100.0


def _less_important_priority_end(lower_is_more_important: bool) -> float:
    return 100.0 if lower_is_more_important else 0.0


def focus_subtree_priorities(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    *,
    lower_is_more_important: bool = True,
) -> int:
    infos = _subtree_target_infos(
        addon_dir,
        profile,
        int(root_card_id),
        include_root=True,
    )
    if not infos:
        return 0

    important_end = _important_priority_end(lower_is_more_important)
    for info in infos:
        depth = int(info.get("depth", 0))
        strength = max(0.2, 0.8 - (depth * 0.15))
        card_id = int(info["card_id"])
        current = float(get_priority(addon_dir, profile, card_id))
        next_priority = current + ((important_end - current) * strength)
        set_priority(addon_dir, profile, card_id, _clamp_priority(next_priority))
    return len(infos)


def fade_child_priorities(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    *,
    lower_is_more_important: bool = True,
) -> int:
    infos = _subtree_target_infos(
        addon_dir,
        profile,
        int(root_card_id),
        include_root=False,
    )
    if not infos:
        return 0

    less_important_end = _less_important_priority_end(lower_is_more_important)
    for info in infos:
        depth = int(info.get("depth", 0))
        strength = min(0.8, 0.25 + (max(0, depth - 1) * 0.15))
        card_id = int(info["card_id"])
        current = float(get_priority(addon_dir, profile, card_id))
        next_priority = current + ((less_important_end - current) * strength)
        set_priority(addon_dir, profile, card_id, _clamp_priority(next_priority))
    return len(infos)


def spread_priority_delta(
    addon_dir: str,
    profile: str,
    root_card_id: int,
    delta: float,
) -> int:
    return shift_subtree_priorities(
        addon_dir,
        profile,
        int(root_card_id),
        delta,
        include_root=False,
    )


def active_profile() -> str:
    return _active_profile()
