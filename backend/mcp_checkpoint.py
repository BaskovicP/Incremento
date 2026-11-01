"""Bounded native checkpoints for workflows spanning collection, files and UI.

Anki data is exported/imported through its package API; collection SQL is read
only. Private, content-addressed assets are never evicted from retained history.
"""

import base64
from copy import deepcopy
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import tempfile

try:
    from . import db, paths
    from .mcp_undo import atomic_bytes, encoded, restore_sqlite
    from .mcp_anki import AnkiToolError
except ImportError:
    import db
    import paths
    from mcp_undo import atomic_bytes, encoded, restore_sqlite
    from mcp_anki import AnkiToolError


MAX_FILE = 128 * 1024 * 1024
MAX_FILES = 512
MAX_TOTAL = 512 * 1024 * 1024


class ProfileBound:
    """Recheck the captured profile at every native helper API boundary.

    Some existing helpers perform slow file/process work before creating a
    note. Guard their collection/managers too, so a reused Anki backend cannot
    publish that result into a newly opened profile.
    """

    def __init__(self, target, check):
        self._mcp_original = target
        self._check = check

    def __getattr__(self, name):
        self._check()
        value = getattr(self._mcp_original, name)
        if name in {"models", "decks", "sched", "media", "db", "_backend"} and value is not None:
            return ProfileBound(value, self._check)
        if callable(value):

            def guarded(*args, **kwargs):
                self._check()
                return value(*args, **kwargs)

            return guarded
        return value


def checked_path(value):
    path = Path(value)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise AnkiToolError("Choose an absolute path without symbolic links.")
    return path


def retain(service, data, suffix=".bin"):
    if len(data) > MAX_TOTAL:
        raise AnkiToolError("Recovery asset exceeds 512 MiB; no change was made.")
    sha = hashlib.sha256(data).hexdigest()
    relative = "mcp_undo_files/checkpoints/" + sha + suffix
    path = service._profile_file(relative, must_exist=False)
    if not path.exists():
        atomic_bytes(path, data)
    elif service._bounded_bytes(path, MAX_TOTAL) != data:
        raise AnkiToolError("A retained checkpoint is damaged.")
    return {"relative": relative, "sha256": sha, "size": len(data)}


def retained(service, reference):
    relative = reference["relative"]
    if not relative.startswith("mcp_undo_files/checkpoints/"):
        raise AnkiToolError("Invalid recovery asset ownership.")
    data = service._bounded_bytes(service._profile_file(relative), MAX_TOTAL)
    if hashlib.sha256(data).hexdigest() != reference["sha256"] or len(data) != reference["size"]:
        raise AnkiToolError("A retained checkpoint changed. No restoration was started.")
    return data


def retain_json(service, value):
    return retain(service, gzip.compress(encoded(value), mtime=0), ".json.gz")


def retained_json(service, reference):
    import io

    with gzip.GzipFile(fileobj=io.BytesIO(retained(service, reference))) as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise AnkiToolError("Checkpoint metadata exceeds its recovery budget.")
    return json.loads(raw)


def file_state(service, files=(), trees=()):
    selected = {str(checked_path(p)) for p in files}
    if len(selected) > MAX_FILES:
        raise AnkiToolError("Affected files exceed 512; choose a smaller operation.")
    for value in trees:
        root = checked_path(value)
        if root.exists():
            for path in root.rglob("*"):
                checked_path(path)
                if path.is_file():
                    selected.add(str(path))
                if len(selected) > MAX_FILES:
                    raise AnkiToolError("Affected files exceed 512; choose a smaller operation.")
    result, total = [], 0
    for name in sorted(selected):
        path = checked_path(name)
        item = {"path": name, "asset": None}
        if path.exists():
            raw = service._bounded_bytes(path, MAX_FILE)
            total += len(raw)
            if total > MAX_TOTAL:
                raise AnkiToolError("Affected files exceed 512 MiB; choose a smaller operation.")
            item["asset"] = retain(service, raw)
        result.append(item)
    return result


def sql_state(service):
    conn = db.get_connection(service.addon_dir, service.profile)
    # Only ordinary Incremento-owned tables; FTS tables are maintained by their
    # triggers. Keep the custom-rule revision ledger monotonically increasing.
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    tables, total = [], 0
    for name in names:
        if name in {"schema_migrations", "custom_schedule_rule_versions"} or "fts" in name:
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({quoted})")]
        rows = [list(row) for row in conn.execute(f"SELECT * FROM {quoted} LIMIT 100001")]
        total += len(encoded(rows))
        if len(rows) > 100000 or total > 48 * 1024 * 1024:
            raise AnkiToolError("Supplemental checkpoint exceeds its budget; choose a smaller workflow.")
        rows.sort(key=encoded)
        tables.append({"table": name, "columns": columns, "predicate": "1", "params": [], "rows": rows})
    return retain_json(service, {"tables": tables})


def anki_state(service, col):
    content_bytes = col.db.scalar("SELECT coalesce(sum(length(CAST(flds AS BLOB))),0) FROM notes")
    model_count = col.db.scalar("SELECT count(*) FROM notetypes")
    if content_bytes > 32 * 1024 * 1024 or model_count > 500:
        raise AnkiToolError("Native checkpoint exceeds 32 MiB of note content or 500 note types.")
    ids = col.db.list("SELECT id FROM notes ORDER BY id LIMIT 10001")
    count = col.db.scalar("SELECT count(*) FROM revlog")
    if len(ids) > 10000 or count > 100000:
        raise AnkiToolError("This workflow requires a full native checkpoint (10,000 notes/100,000 reviews maximum).")
    notes = col.db.all("SELECT id,guid,mid,flds,tags,flags,data FROM notes ORDER BY id")
    reviews = col.db.all("SELECT id,cid,ease,ivl,lastIvl,factor,time,type FROM revlog ORDER BY id")
    cards = []
    for (cid,) in col.db.all("SELECT id FROM cards ORDER BY id LIMIT 50001"):
        card = col.get_card(cid)._to_backend_card()
        card.ClearField("mtime_secs")
        card.ClearField("usn")
        cards.append(base64.b64encode(card.SerializeToString()).decode())
    if len(cards) > 50000:
        raise AnkiToolError("Native card checkpoint exceeds 50,000 cards.")
    models = [
        json.loads(col._backend.get_notetype_legacy(r[0])) for r in col.db.all("SELECT id FROM notetypes ORDER BY id")
    ]
    decks = [deepcopy(col.decks.get(r[0])) for r in col.db.all("SELECT id FROM decks ORDER BY id")]
    configs = col.decks.all_config()
    value = {
        "notes": notes,
        "reviews": reviews,
        "cards": cards,
        "models": models,
        "decks": decks,
        "configs": configs,
        "collection_config": json.loads(col._backend.get_all_config()),
    }
    data = encoded(value)
    if len(data) > 48 * 1024 * 1024:
        raise AnkiToolError("Native checkpoint metadata exceeds 48 MiB.")
    semantic = deepcopy(value)
    for key in list(semantic["collection_config"]):
        if key in {"curDeck", "curModel", "activeDecks", "nextPos", "localOffset"} or re.fullmatch(
            r"_(?:deck_\d+_lastNotetype|nt_\d+_lastDeck)", key
        ):
            semantic["collection_config"].pop(key)
    semantic["collection_config"].setdefault("rollover", 4)
    for item in [*semantic["models"], *semantic["decks"], *semantic["configs"]]:
        item.pop("usn", None)
        item.pop("mod", None)
    signature = hashlib.sha256(encoded(semantic)).hexdigest()
    # Reuse an existing package when a preview captures the same native state.
    relative = "mcp_undo_files/checkpoints/" + signature + ".colpkg"
    package = service._profile_file(relative, must_exist=False)
    if not package.exists():
        package.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".mcp-export-", dir=package.parent) as directory:
            from anki.collection import Collection

            temporary = Path(directory) / "checkpoint.colpkg"
            copy_path = Path(directory) / "collection.anki2"
            reader = sqlite3.connect(Path(col.path).as_uri() + "?mode=ro", uri=True)
            try:
                with sqlite3.connect(str(copy_path)) as destination:
                    reader.backup(destination)
            finally:
                reader.close()
            isolated = Collection(str(copy_path))
            try:
                isolated.export_collection_package(str(temporary), include_media=False, legacy=False)
            finally:
                isolated.close()
            raw = service._bounded_bytes(temporary, MAX_TOTAL)
            atomic_bytes(package, raw)
    return {
        "revision": signature,
        "state": retain_json(service, value),
        "package": retain(service, service._bounded_bytes(package, MAX_TOTAL), ".colpkg"),
    }


def capture(service, col, scope):
    service.check()
    additions = []
    for tree in scope.get("append_trees", []):
        root = checked_path(tree)
        inventory = []
        if root.exists():
            for path in root.rglob("*"):
                checked_path(path)
                if path.is_file():
                    inventory.append(str(path))
                if len(inventory) > 100000:
                    raise AnkiToolError("File inventory exceeds 100,000 entries.")
        original = scope.setdefault("baseline", {}).setdefault(tree, sorted(inventory))
        additions.extend(sorted(set(inventory) - set(original)))
    state = {"kind": "operation_checkpoint", "scope": deepcopy(scope)}
    if scope.get("anki"):
        state["anki"] = anki_state(service, col)
    if scope.get("sqlite"):
        state["sqlite"] = sql_state(service)
    if scope.get("settings"):
        state["settings"] = {k: deepcopy(v) for k, v in service.config.items() if not k.startswith("_")}
    state["files"] = file_state(service, [*scope.get("files", ()), *additions], scope.get("trees", ()))
    if scope.get("ui"):
        area = scope["ui"]["area"]
        path = paths.get_mcp_runtime_state_path(service.addon_dir, service.profile)
        saved = json.loads(service._bounded_bytes(path)) if path.exists() else {}
        state["runtime"] = saved.get(area, scope["ui"]["before"])
    service.check()
    return state


def comparable(state):
    result = deepcopy(state)
    result.pop("scope", None)
    if result.get("anki"):
        result["anki"] = {"revision": result["anki"]["revision"]}
    # A file created after the preview is equivalent to an absent before-file;
    # absent rows only carry restore ownership, not user data.
    result["files"] = [row for row in result["files"] if row["asset"]]
    return result


def restore(service, col, target, current):
    # Verify both directions before any destructive action, so even a failed
    # restore retains a usable route back to the exact starting state.
    for state in (target, current):
        scope = state["scope"]
        if any(key in state and not scope.get(key) for key in ("anki", "sqlite", "settings")):
            raise AnkiToolError("The checkpoint contains data outside its declared ownership.")
        explicit = {str(checked_path(p)) for p in scope.get("files", [])}
        roots = [checked_path(p) for p in [*scope.get("trees", []), *scope.get("append_trees", [])]]
        for row in state["files"]:
            path = checked_path(row["path"])
            if str(path) not in explicit and not any(path.is_relative_to(root) for root in roots):
                raise AnkiToolError("The checkpoint contains a file outside its declared ownership.")
        if state.get("anki"):
            retained_json(service, state["anki"]["state"])
            if state["anki"]["package"]:
                retained(service, state["anki"]["package"])
        if state.get("sqlite"):
            tables = retained_json(service, state["sqlite"])["tables"]
            canonical = retained_json(service, sql_state(service))["tables"]

            def shape(items):
                return [(t["table"], t["columns"], t["predicate"], t["params"]) for t in items]

            if shape(tables) != shape(canonical):
                raise AnkiToolError("The supplemental checkpoint schema or ownership changed.")
        for row in state["files"]:
            checked_path(row["path"])
            if row["asset"]:
                retained(service, row["asset"])
    if target.get("anki"):
        from anki.collection import OpChanges, media_paths_from_col_path

        package = service._profile_file(target["anki"]["package"]["relative"])
        selected_deck = col.decks.selected()
        selected_model = col.get_config("curModel", None)
        media_dir, media_db = media_paths_from_col_path(col.path)
        col.close()
        try:
            col._backend.import_collection_package(
                col_path=col.path, backup_path=str(package), media_folder=media_dir, media_db=media_db
            )
        finally:
            col.reopen()
        if col.decks.get(selected_deck, default=False):
            col.decks.select(selected_deck)
        if selected_model and col.models.get(selected_model):
            col.set_config("curModel", selected_model)
        service.changes = OpChanges(**{field.name: True for field in OpChanges.DESCRIPTOR.fields})
    if target.get("sqlite"):
        snapshot = retained_json(service, target["sqlite"])
        restore_sqlite(db.get_connection(service.addon_dir, service.profile), [snapshot], service.check)
    desired = {row["path"]: row for row in target["files"]}
    for row in current["files"]:
        desired.setdefault(row["path"], {"path": row["path"], "asset": None})
    for row in desired.values():
        path = checked_path(row["path"])
        if row["asset"]:
            atomic_bytes(path, retained(service, row["asset"]))
        elif path.exists():
            path.unlink()
    if "settings" in target:
        service._save_operation_settings(target["settings"])
