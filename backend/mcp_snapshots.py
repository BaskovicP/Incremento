"""Native package checkpoints for bounded edits that can change card identities.

Collection SQL is read-only here. Restores remove/reimport the exact owned notes
through Anki, restore explicit model/deck definitions through Anki, and restore
only Incremento-owned supplemental rows through its SQLite boundary.
"""

from copy import deepcopy
import hashlib
import os
import uuid

try:
    from . import db
    from .reconciliation import _CARD_TABLES, _SOURCE_TABLES
    from .mcp_undo import encoded, restore_sqlite
    from .mcp_creation import fingerprint
    from .mcp_anki import AnkiToolError, native_id
    from .i18n import t
except ImportError:
    import db
    from reconciliation import _CARD_TABLES, _SOURCE_TABLES
    from mcp_undo import encoded, restore_sqlite
    from mcp_creation import fingerprint
    from mcp_anki import AnkiToolError, native_id
    from i18n import t


SUPPLEMENT_TABLES = tuple(
    dict.fromkeys(
        (
            "content_items",
            "priorities",
            "reader_bookmarks",
            "pdf_highlights",
            "epub_highlights",
            "pdf_text_index",
            "epub_text_index",
            "document_index_state",
            "writing_progress",
            "writing_word_stats",
            "pdf_progress",
            "epub_progress",
            "custom_schedule_rules",
            "knowledge_tree_nodes",
            "topic_cards",
            "topic_review_history",
            "custom_schedule_review_history",
            "pdf_card_sources",
            "epub_card_sources",
            "video_card_sources",
            "document_links",
            "recording_links",
            "epub_connections",
            "note_ocr_index",
            *(table[0] for table in (*_CARD_TABLES, *_SOURCE_TABLES) if table[0] != "custom_schedule_rule_versions"),
        )
    )
)
CARD_OWNER_COLUMNS = (
    "card_id",
    "parent_card_id",
    "source_card_id",
    "target_card_id",
    "recording_card_id",
    "pdf_card_id",
    "epub_card_id",
    "video_card_id",
)


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def canonical(value):
    return {key: item for key, item in value.items() if key not in {"usn", "mod"}}


def supplement_scopes(conn, note_ids, card_ids):
    scopes = []
    for table in SUPPLEMENT_TABLES:
        columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
        if not columns:
            continue
        conditions, params = [], []
        for key, ids in [("note_id", note_ids), *((key, card_ids) for key in CARD_OWNER_COLUMNS)]:
            if key in columns and ids:
                conditions.append(f'"{key}" IN ({",".join("?" for _ in ids)})')
                params.extend(ids)
        if conditions:
            scopes.append({"table": table, "columns": columns, "predicate": " OR ".join(conditions), "params": params})
    return scopes


def capture_supplement(service, note_ids, card_ids):
    conn = db.get_connection(service.addon_dir, service.profile)
    tables = supplement_scopes(conn, note_ids, card_ids)
    total = 0
    for table in tables:
        columns = ",".join('"' + name + '"' for name in table["columns"])
        rows = conn.execute(
            f'SELECT {columns} FROM "{table["table"]}" WHERE {table["predicate"]} ORDER BY rowid LIMIT 5001',
            table["params"],
        ).fetchall()
        total += len(encoded(rows))
        if len(rows) > 5000 or total > 3 * 1024 * 1024:
            raise AnkiToolError("Affected supplemental data exceeds the recovery budget. Select fewer notes.")
        table["rows"] = [list(row) for row in rows]
    return tables


def capture_notes(service, col, args, note_ids, *, model_ids=(), mutable_models=()):
    ids = sorted({native_id(nid) for nid in note_ids})
    if len(ids) > 100:
        raise AnkiToolError("Select at most 100 notes for a native recovery operation.")
    args.setdefault("_native_note_ids", ids)
    if args["_native_note_ids"] != ids:
        raise AnkiToolError("Recovery note ownership changed.")
    models = set(model_ids) | set(args.get("_native_model_ids", []))
    card_ids = set(args.get("_native_card_ids", []))
    notes = []
    for nid in ids:
        service.check()
        if not col.db.all("SELECT id FROM notes WHERE id=?", nid):
            continue
        note = service._bounded_note(col, nid)
        model = note.note_type()
        models.add(int(model["id"]))
        cards = []
        rows = col.db.all("SELECT id FROM cards WHERE nid=? ORDER BY id LIMIT 501", nid)
        if len(rows) > 500:
            raise AnkiToolError("Affected cards exceed the recovery budget.")
        for (cid,) in rows:
            card_ids.add(cid)
            state = service._native_card(col, str(cid))
            if state["fields"]["odid"] or state["deck"]["dyn"]:
                raise AnkiToolError("Return affected notes from filtered decks before this operation.")
            cards.append(state)
        rev_columns = [row[1] for row in col.db.all("PRAGMA table_info(revlog)")]
        marks = ",".join("?" for _ in rows) or "NULL"
        logs = col.db.all(
            f"SELECT * FROM revlog WHERE cid IN ({marks}) ORDER BY id LIMIT 5001", *(row[0] for row in rows)
        )
        if len(logs) > 5000:
            raise AnkiToolError("Review history exceeds the recovery budget. Select fewer notes.")
        usn = rev_columns.index("usn")
        notes.append(
            {
                "note_id": nid,
                "guid": note.guid,
                "model_id": note.mid,
                "fields": dict(note.items()),
                "tags": list(note.tags),
                "cards": cards,
                "revlog": [[0 if index == usn else value for index, value in enumerate(row)] for row in logs],
            }
        )
    if len(card_ids) > 500:
        raise AnkiToolError("Select at most 500 affected cards per recovery operation.")
    args["_native_card_ids"] = sorted(card_ids)
    args["_native_model_ids"] = sorted(models)
    model_values = []
    for mid in sorted(models):
        model = col.models.get(mid)
        if not model:
            raise AnkiToolError("A recovery note type is unavailable.")
        model_values.append(deepcopy(model))
    tables = capture_supplement(service, ids, sorted(card_ids))
    state = {
        "kind": "native_notes",
        "note_ids": ids,
        "card_ids": sorted(card_ids),
        "notes": notes,
        "models": model_values,
        "mutable_models": sorted(mutable_models),
        "tables": tables,
    }
    # Newly generated IDs expand ownership. Empty added scopes are normalized
    # by the service guard, while actual new rows remain conflict evidence.
    semantic = semantic_state(state)
    if len(encoded(semantic)) > 4 * 1024 * 1024:
        raise AnkiToolError("Affected data exceeds the native recovery budget.")
    key = digest(semantic)
    archives = args.setdefault("_native_archives", {})
    if notes and key not in archives and not getattr(service, "_verify_capture", False):
        from anki.import_export_pb2 import ExportAnkiPackageOptions, ExportLimit
        from anki.notes_pb2 import NoteIds

        relative = "mcp_undo_files/native-" + uuid.uuid4().hex + ".apkg"
        path = service._profile_file(relative, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(".mcp-package-" + uuid.uuid4().hex + ".apkg")
        try:
            col.export_anki_package(
                out_path=str(temporary),
                options=ExportAnkiPackageOptions(with_scheduling=True, with_media=False, with_deck_configs=False),
                limit=ExportLimit(note_ids=NoteIds(note_ids=[note["note_id"] for note in notes])),
            )
            if temporary.stat().st_size > 48 * 1024 * 1024:
                raise AnkiToolError("Native recovery package exceeds 48 MiB; no change was made.")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        archives[key] = {"relative": relative, "hash": fingerprint(path)}
    state["recovery"] = archives.get(key)
    return state


def semantic_state(state):
    result = deepcopy(state)
    result.pop("recovery", None)
    result["models"] = [canonical(model) for model in result["models"]]
    result.pop("card_ids", None)
    # Predicates may expand after card generation; row ownership is validated
    # separately. Compare the actual rows, not an empty SQL selection scope.
    result["tables"] = [
        {"table": table["table"], "columns": table["columns"], "rows": sorted(table["rows"], key=encoded)}
        for table in result["tables"]
        if table["rows"]
    ]
    return result


def validate_notes_restore(service, col, target, current):
    if target["note_ids"] != current["note_ids"] or target["mutable_models"] != current["mutable_models"]:
        raise AnkiToolError("Native recovery ownership changed.")
    if {model["id"] for model in target["models"]} != {model["id"] for model in current["models"]}:
        raise AnkiToolError("Native recovery note types changed.")
    ids = sorted(set(target["card_ids"]) | set(current["card_ids"]))
    conn = db.get_connection(service.addon_dir, service.profile)
    for state in (target, current):
        allowed = supplement_scopes(conn, state["note_ids"], state["card_ids"])

        def descriptors(tables):
            return [{key: row[key] for key in ("table", "columns", "predicate", "params")} for row in tables]

        if encoded(descriptors(allowed)) != encoded(descriptors(state["tables"])):
            raise AnkiToolError("Native recovery supplemental ownership changed.")
        for note in state["notes"]:
            if note["note_id"] not in state["note_ids"] or any(
                int(card["card_id"]) not in ids for card in note["cards"]
            ):
                raise AnkiToolError("Native recovery identity changed.")


def restore_notes(service, col, target):
    current = getattr(service, "_creation_restore_current", None)
    if not current or current.get("kind") != "native_notes":
        raise AnkiToolError("Native recovery requires a verified current checkpoint.")
    validate_notes_restore(service, col, target, current)
    # Verify every dependency and retained byte before removing a live note.
    for checkpoint in (target, current):
        if not checkpoint["notes"]:
            continue
        archive = checkpoint["recovery"]
        if not archive or not archive["relative"].startswith("mcp_undo_files/native-"):
            raise AnkiToolError("Native recovery package is unavailable.")
        retained = service._profile_file(archive["relative"])
        if fingerprint(retained) != archive["hash"]:
            raise AnkiToolError("Native recovery package changed.")
    package = service._profile_file(target["recovery"]["relative"]) if target["notes"] else None
    for model in target["models"]:
        live = col.models.get(model["id"])
        if not live:
            raise AnkiToolError("Restore the original note type before undo/redo.")
        if canonical(live) != canonical(model) and model["id"] not in target["mutable_models"]:
            raise AnkiToolError("The original note type changed. Restore that edit first.")
        if model["id"] in target["mutable_models"]:
            marks = ",".join("?" for _ in target["note_ids"]) or "NULL"
            if col.db.all(
                f"SELECT id FROM notes WHERE mid=? AND id NOT IN ({marks}) LIMIT 1", model["id"], *target["note_ids"]
            ):
                raise AnkiToolError("This note type gained another note. Restore that change first.")
    for note in target["notes"]:
        collisions = col.db.list("SELECT id FROM notes WHERE guid=? AND id!=?", note["guid"], note["note_id"])
        if any(nid not in current["note_ids"] for nid in collisions):
            raise AnkiToolError("A different note now owns the retained GUID.")
        for card in note["cards"]:
            owners = col.db.list("SELECT nid FROM cards WHERE id=?", int(card["card_id"]))
            if any(nid not in current["note_ids"] for nid in owners):
                raise AnkiToolError("A different note now owns a retained card identity.")
            deck = col.decks.get(card["fields"]["did"], default=False)
            if not deck or any(deck.get(key) != value for key, value in card["deck"].items()):
                raise AnkiToolError("Restore the original deck before undo/redo.")
    service.check()
    entry = col.add_custom_undo_entry(t("mcp_undo_batch"))
    try:
        live_ids = [note["note_id"] for note in current["notes"]]
        if live_ids:
            col.remove_notes(live_ids)
        for model in target["models"]:
            if model["id"] in target["mutable_models"]:
                selected = col.models.current()["id"]
                col.models.update(deepcopy(model), preserve_usn=True)
                if selected != model["id"]:
                    col.models.set_current(col.models.get(selected))
        if target["notes"]:
            from anki.import_export_pb2 import ImportAnkiPackageOptions, ImportAnkiPackageRequest

            col.import_anki_package(
                ImportAnkiPackageRequest(
                    package_path=str(package),
                    options=ImportAnkiPackageOptions(
                        with_scheduling=True, with_deck_configs=False, update_notes=1, update_notetypes=2
                    ),
                )
            )
            for note in target["notes"]:
                actual = col.get_note(note["note_id"])
                ids = sorted(col.find_cards(f"nid:{note['note_id']}"))
                if actual.guid != note["guid"] or ids != sorted(int(card["card_id"]) for card in note["cards"]):
                    raise AnkiToolError("Anki did not restore the expected note/card identities.")
        empty = [{**table, "rows": []} for table in current["tables"]]
        restore_sqlite(
            db.get_connection(service.addon_dir, service.profile),
            [{"tables": [*empty, *target["tables"]]}],
            service.check,
        )
    finally:
        if target["mutable_models"]:
            # Native schema restoration clears Anki's in-memory undo stack.
            # The complete operation remains reversible through MCP checkpoints.
            from anki.collection import OpChanges

            service.changes = OpChanges(note=True, card=True, notetype=True, deck=True)
        else:
            service.changes = col.merge_undo_entries(entry)
