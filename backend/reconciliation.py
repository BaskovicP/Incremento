"""Reconcile Incremento's external state with the active Anki collection."""

from __future__ import annotations

import json
import time

try:
    from .db import get_connection
    from .note_metadata import INCREMENTO_CONTENT_ID_FIELD
    from .operation_journal import (
        pending_import_content_ids,
        prune_finished_journal,
        recover_interrupted_imports,
    )
except ImportError:
    from db import get_connection  # type: ignore
    from note_metadata import INCREMENTO_CONTENT_ID_FIELD  # type: ignore
    from operation_journal import (  # type: ignore
        pending_import_content_ids,
        prune_finished_journal,
        recover_interrupted_imports,
    )


_CARD_TABLES = (
    ("pdf_progress", "card_id"),
    ("pdf_daily_limits", "card_id"),
    ("pdf_due_review_prompts", "card_id"),
    ("pdf_daily_limit_usage", "card_id"),
    ("pdf_highlights", "card_id"),
    ("epub_progress", "card_id"),
    ("epub_daily_limits", "card_id"),
    ("epub_due_review_prompts", "card_id"),
    ("epub_daily_limit_usage", "card_id"),
    ("epub_highlights", "card_id"),
    ("writing_progress", "card_id"),
    ("writing_word_stats", "card_id"),
    ("priorities", "card_id"),
    ("video_progress", "card_id"),
    ("web_progress", "card_id"),
    ("reader_bookmarks", "card_id"),
    ("browser_media_refs", "card_id"),
    ("pdf_text_index", "card_id"),
    ("epub_text_index", "card_id"),
    ("document_index_state", "card_id"),
    ("topic_schedule", "card_id"),
    ("topic_review_history", "card_id"),
    ("topic_postpones", "card_id"),
    ("item_postpones", "card_id"),
    ("custom_schedule_rules", "card_id"),
    ("custom_schedule_rule_versions", "card_id"),
    ("custom_schedule_review_history", "card_id"),
    ("knowledge_tree_nodes", "card_id"),
)

_SOURCE_TABLES = (
    ("pdf_card_sources", "pdf_card_id", "note_id"),
    ("epub_card_sources", "epub_card_id", "note_id"),
    ("web_card_sources", "web_card_id", "note_id"),
    ("note_ocr_index", "card_id", "note_id"),
)


def _delete_rowids(conn, table: str, rowids: list[int]) -> int:
    if not rowids:
        return 0
    conn.executemany(
        f"DELETE FROM {table} WHERE rowid=?",
        [(int(rowid),) for rowid in rowids],
    )
    return len(rowids)


def reconcile_profile_state(
    addon_dir: str,
    profile: str,
    *,
    live_card_ids: set[int],
    live_note_ids: set[int],
    content_matches: dict[str, tuple[int, int | None]] | None = None,
) -> dict[str, int]:
    """Delete only rows whose referenced Anki card/note no longer exists."""
    started_at = int(time.time())
    conn = get_connection(addon_dir, profile)
    live_cards = {int(value) for value in live_card_ids}
    live_notes = {int(value) for value in live_note_ids}
    removed = 0
    touched_tables = 0

    recovery = recover_interrupted_imports(
        addon_dir,
        profile,
        live_card_ids=live_cards,
        content_matches=content_matches,
    )

    with conn:
        for table, card_column in _CARD_TABLES:
            rows = conn.execute(
                f"SELECT rowid, {card_column} FROM {table}"
            ).fetchall()
            stale = [int(rowid) for rowid, card_id in rows if int(card_id or 0) not in live_cards]
            deleted = _delete_rowids(conn, table, stale)
            if deleted:
                removed += deleted
                touched_tables += 1

        for table, card_column, note_column in _SOURCE_TABLES:
            rows = conn.execute(
                f"SELECT rowid, {card_column}, {note_column} FROM {table}"
            ).fetchall()
            stale = [
                int(rowid)
                for rowid, card_id, note_id in rows
                if int(card_id or 0) not in live_cards
                or int(note_id or 0) not in live_notes
            ]
            deleted = _delete_rowids(conn, table, stale)
            if deleted:
                removed += deleted
                touched_tables += 1

        content_rows = conn.execute(
            "SELECT rowid, card_id, note_id FROM content_items"
        ).fetchall()
        stale_content = [
            int(rowid)
            for rowid, card_id, note_id in content_rows
            if (card_id is not None and int(card_id) not in live_cards)
            or (note_id is not None and int(note_id) not in live_notes)
        ]
        deleted = _delete_rowids(conn, "content_items", stale_content)
        if deleted:
            removed += deleted
            touched_tables += 1

        parent_rows = conn.execute(
            "SELECT card_id, parent_card_id FROM knowledge_tree_nodes "
            "WHERE parent_card_id IS NOT NULL"
        ).fetchall()
        orphan_children = [
            int(card_id)
            for card_id, parent_card_id in parent_rows
            if int(parent_card_id or 0) not in live_cards
        ]
        if orphan_children:
            conn.executemany(
                "UPDATE knowledge_tree_nodes SET parent_card_id=NULL, updated_at=? "
                "WHERE card_id=?",
                [(started_at, card_id) for card_id in orphan_children],
            )

        preset_rows = conn.execute(
            "SELECT name, branch_root_card_id FROM knowledge_tree_postpone_presets "
            "WHERE branch_root_card_id IS NOT NULL"
        ).fetchall()
        stale_presets = [
            str(name)
            for name, root_card_id in preset_rows
            if int(root_card_id or 0) not in live_cards
        ]
        if stale_presets:
            conn.executemany(
                "UPDATE knowledge_tree_postpone_presets "
                "SET branch_root_card_id=NULL, updated_at=? WHERE name=?",
                [(started_at, name) for name in stale_presets],
            )

        conn.execute(
            "INSERT INTO reconciliation_runs("
            "started_at, finished_at, stale_rows, orphan_files, repaired_rows, details_json"
            ") VALUES (?, ?, ?, 0, ?, ?)",
            (
                started_at,
                int(time.time()),
                removed,
                len(orphan_children) + len(stale_presets),
                json.dumps(
                    {
                        "touched_tables": touched_tables,
                        "pending_recovered": int(recovery.get("recovered", 0)),
                        "pending_rolled_back": int(recovery.get("rolled_back", 0)),
                        "pending_cleanup_failed": int(recovery.get("failed_cleanup", 0)),
                    },
                    separators=(",", ":"),
                ),
            ),
        )

    pruned_journal = prune_finished_journal(
        addon_dir,
        profile,
        older_than=int(time.time()) - 90 * 24 * 60 * 60,
    )
    return {
        "stale_rows": removed,
        "repaired_links": len(orphan_children) + len(stale_presets),
        "touched_tables": touched_tables,
        "pending_recovered": int(recovery.get("recovered", 0)),
        "pending_rolled_back": int(recovery.get("rolled_back", 0)),
        "pending_cleanup_failed": int(recovery.get("failed_cleanup", 0)),
        "journal_pruned": pruned_journal,
    }


def reconcile_collection(addon_dir: str, profile: str, collection) -> dict[str, int]:
    """Read live Anki identities and reconcile the matching profile DB."""
    live_card_ids = {
        int(card_id)
        for card_id in collection.db.list("SELECT id FROM cards")
    }
    live_note_ids = {
        int(note_id)
        for note_id in collection.db.list("SELECT id FROM notes")
    }
    content_matches: dict[str, tuple[int, int | None]] = {}
    for content_id in pending_import_content_ids(addon_dir, profile):
        # Pending imports are normally zero or one row, so an exact Anki field
        # lookup avoids an expensive full-note scan on every profile open.
        note_ids: list[int] = []
        for query in (
            f'{INCREMENTO_CONTENT_ID_FIELD}:{content_id}',
            f'"{INCREMENTO_CONTENT_ID_FIELD}:{content_id}"',
        ):
            try:
                note_ids = [int(value) for value in collection.find_notes(query)]
            except Exception:
                note_ids = []
            if note_ids:
                break
        for note_id in note_ids:
            try:
                note = collection.get_note(note_id)
                if str(note[INCREMENTO_CONTENT_ID_FIELD] or "").strip() != content_id:
                    continue
                card_ids = [
                    int(value)
                    for value in collection.find_cards(f"nid:{note_id}")
                ]
            except Exception:
                continue
            live_matches = [card_id for card_id in card_ids if card_id in live_card_ids]
            if live_matches:
                content_matches[content_id] = (live_matches[0], note_id)
                break
    return reconcile_profile_state(
        addon_dir,
        profile,
        live_card_ids=live_card_ids,
        live_note_ids=live_note_ids,
        content_matches=content_matches,
    )
