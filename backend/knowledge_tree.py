from __future__ import annotations

import os
import random
import re
from collections import defaultdict

try:
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
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        visible_field_names,
    )
    from .paths import get_active_profile as _active_profile
    from .priority_manager import get_priority, set_priority
except ImportError:
    from db import (  # type: ignore
        get_knowledge_tree_node,
        get_knowledge_tree_nodes,
        set_knowledge_tree_structure,
    )
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        visible_field_names,
    )
    from paths import get_active_profile as _active_profile  # type: ignore
    from priority_manager import get_priority, set_priority  # type: ignore


NODE_KIND_TOPIC = "topic"
NODE_KIND_ITEM = "item"
_DEFAULT_TOPIC_TAGS = ["topic"]
_DEFAULT_ITEM_TAGS = ["item"]
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)


def normalize_node_kind(node_kind: str) -> str:
    kind = str(node_kind or "").strip().lower()
    if kind not in {NODE_KIND_TOPIC, NODE_KIND_ITEM}:
        raise ValueError(f"Unsupported knowledge-tree node kind: {node_kind}")
    return kind


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
        return mw.addonManager.getConfig(addon_name) or {}
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
    ensure_incremento_metadata_fields(mw.col.models, model)

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
    if not card_exists(card_id):
        raise RuntimeError(f"Card {card_id} was not found in the current collection.")
    apply_node_kind_to_card(card_id, node_kind)
    insert_knowledge_tree_node(
        addon_dir,
        profile,
        card_id,
        node_kind,
        parent_card_id=parent_card_id,
        sort_order=sort_order,
    )


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

    sql = (
        "SELECT c.id, n.sf, n.mid, c.did "
        "FROM cards c "
        "JOIN notes n ON n.id = c.nid "
    )
    params: list[object] = []
    if query:
        sql += "WHERE lower(n.sf) LIKE lower(?) "
        params.append(f"%{query}%")
    sql += "ORDER BY c.id DESC LIMIT ?"
    params.append(max(limit * 3, limit))

    try:
        rows = list(mw.col.db.all(sql, *params) or [])
    except Exception:
        return []

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
