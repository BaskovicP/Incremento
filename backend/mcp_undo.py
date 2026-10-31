"""Bounded, durable per-profile reversal snapshots and reviewed plans.

No eviction: when retaining another reversal would exceed the budget, the write
is refused before it starts. No user content enters diagnostics or tool history
listings. Atomic private JSON storage survives normal profile/application restarts.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
import sqlite3
import stat
import tempfile
import uuid

try:
    from .paths import get_mcp_history_path
except ImportError:
    from paths import get_mcp_history_path


class UndoError(ValueError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")


def model_state(model):
    """Sync transport counters do not represent a user's note-type edit."""
    return {key: value for key, value in (model or {}).items() if key != "usn"}


def atomic_bytes(path, data):
    """Publish a private same-directory file without exposing a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix=".mcp-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def restore_sqlite(conn, snapshots, check):
    """Restore overlapping fixed scopes once, with parents before dependents."""
    tables = {}
    for snapshot in snapshots:
        for item in snapshot["tables"]:
            group = tables.setdefault(item["table"], {"columns": item["columns"], "scopes": {}, "rows": {}})
            if group["columns"] != item["columns"]:
                raise UndoError("Undo schema changed.")
            group["scopes"][encoded([item["predicate"], item["params"]])] = (item["predicate"], item["params"])
            for row in item["rows"]:
                group["rows"][encoded(row)] = row
    foreign_keys = {table: list(conn.execute(f'PRAGMA foreign_key_list("{table}")')) for table in tables}
    dependencies = {table: {row[2] for row in foreign_keys[table]
                            if row[2] != table and row[2] in tables} for table in tables}
    pending, order = set(tables), []
    while pending:
        ready = sorted(table for table in pending if not dependencies[table] & pending)
        if not ready:
            raise UndoError("Undo contains unsupported cyclic table dependencies.")
        order.extend(ready)
        pending.difference_update(ready)

    def restore():
        for table in reversed(order):
            for predicate, params in tables[table]["scopes"].values():
                conn.execute(f'DELETE FROM "{table}" WHERE {predicate}', params)
        for table in order:
            group = tables[table]
            if group["rows"]:
                columns = ','.join('"'+name+'"' for name in group["columns"])
                conn.executemany(f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in group["columns"])})',
                                 group["rows"].values())
        # Enforce the relationships of inserted rows even on SQLite connections
        # where foreign_keys is disabled. Never recreate orphan memberships.
        for table in order:
            constraints = {}
            for rule in foreign_keys[table]:
                constraints.setdefault(rule[0], []).append(rule)
            for rules in constraints.values():
                rules.sort(key=lambda rule: rule[1])
                parent = rules[0][2].replace('"', '""')
                names = [rule[4] for rule in rules]
                if any(name is None for name in names):
                    raise UndoError("Undo contains an unsupported relationship.")
                clause = ' AND '.join('"'+name.replace('"','""')+'"=?' for name in names)
                for row in tables[table]["rows"].values():
                    values = [row[tables[table]["columns"].index(rule[3])] for rule in rules]
                    if all(value is not None for value in values) and conn.execute(
                            f'SELECT 1 FROM "{parent}" WHERE {clause} LIMIT 1', values).fetchone() is None:
                        raise UndoError("Referenced data was removed. Restore the parent change before undo/redo.")
        check()

    def atomic_restore():
        conn.execute("SAVEPOINT incremento_mcp_restore")
        try:
            restore()
        except Exception as error:
            try:
                conn.execute("ROLLBACK TO incremento_mcp_restore")
                conn.execute("RELEASE incremento_mcp_restore")
            except sqlite3.Error:
                pass  # SQLite may already have rolled back a failed transaction.
            if isinstance(error, sqlite3.IntegrityError):
                raise UndoError("Undo/redo conflicts with newer data or a removed parent.") from None
            raise
        conn.execute("RELEASE incremento_mcp_restore")
    if conn.in_transaction:
        atomic_restore()
    else:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            atomic_restore()


class UndoHistory:
    def __init__(self, *, addon_dir=None, profile=None, max_entries=1000, max_bytes=16 * 1024 * 1024):
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.records, self.plans, self.requests = {}, {}, {}
        self.profile = profile
        self.path = get_mcp_history_path(addon_dir, profile) if addon_dir is not None else None
        self._disk_hash = None
        if self.path is not None:
            raw = self._read()
            if raw is not None:
                try:
                    value = json.loads(raw)
                    if (set(value) != {"version", "profile", "records", "plans", "requests"}
                            or value["version"] != 1 or value["profile"] != profile
                            or not all(isinstance(value[key], dict) for key in ("records", "plans", "requests"))):
                        raise ValueError()
                    for identifier, record in value["records"].items():
                        if (not isinstance(identifier, str) or len(identifier) != 32 or not isinstance(record, dict)
                                or not {"action", "args", "before", "after", "collection", "redo", "size"} <= record.keys()
                                or not isinstance(record["args"], dict) or not isinstance(record["before"], dict)):
                            raise ValueError()
                    self.records, self.plans, self.requests = (value[key] for key in ("records", "plans", "requests"))
                    self._disk_hash = hashlib.sha256(raw).hexdigest()
                except (ValueError, TypeError, KeyError, RecursionError):
                    raise UndoError("MCP history is damaged. Preserve it and restore a valid backup; writes are disabled.") from None

    def _read(self):
        if any(path.is_symlink() for path in (self.path, self.path.parent, self.path.parent.parent)):
            raise UndoError("Unsafe MCP history path.")
        try:
            descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > self.max_bytes:
                raise UndoError("MCP history is unsafe or exceeds its storage budget.")
            return stream.read(self.max_bytes+1)

    def persist(self):
        if self.path is None:
            return
        raw = encoded({"version": 1, "profile": self.profile, "records": self.records,
                       "plans": self.plans, "requests": self.requests})
        if len(raw) > self.max_bytes:
            raise UndoError("MCP history storage is full; retained reversals have not been evicted.")
        current = self._read()
        digest = hashlib.sha256(current).hexdigest() if current is not None else None
        if digest != self._disk_hash:
            raise UndoError("MCP history changed in another operation. Reconnect before writing.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix=".mcp-history-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.path)
            self._disk_hash = hashlib.sha256(raw).hexdigest()
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def clear(self):
        self.records.clear()
        self.persist()

    def check_capacity(self, before):
        # Input bodies are capped at 64 KiB. Reserve room for both snapshots
        # and up to 1 MiB of normalized/HTML-escaped new input before a write.
        used = len(encoded({"records": self.records, "plans": self.plans, "requests": self.requests}))
        if len(self.records) >= self.max_entries or used + 2*len(encoded(before)) + 1024*1024 > self.max_bytes:
            raise UndoError("MCP undo history is full. Existing undo/redo remains available; retained reversals were not evicted.")

    def add(self, action, args, before, after, *, collection=False, redo=False, persist=True):
        if encoded(before) == encoded(after):
            return None
        record = deepcopy({"action": action, "args": args, "before": before, "after": after,
                           "collection": collection, "redo": redo})
        record.update(self._order_metadata())
        record["size"] = len(encoded(record))
        if sum(value["size"] for value in self.records.values()) + record["size"] > self.max_bytes:
            raise UndoError("MCP undo snapshot exceeded its reserved budget.")
        identifier = uuid.uuid4().hex
        self.records[identifier] = record
        if persist:
            self.persist()
        return identifier

    def prepare(self, action, args, before, *, collection=False, request=None):
        self.check_capacity(before)
        identifier = uuid.uuid4().hex
        self.records[identifier] = deepcopy({"action": action, "args": args, "before": before,
            "after": None, "collection": collection, "redo": False, "size": len(encoded(before)), "pending": True,
            **self._order_metadata()})
        if request is not None:
            self.records[identifier]["request"] = request
            self.requests[request[0]] = {"fingerprint": request[1], "pending": True, "undo_id": identifier}
        self.persist()
        return identifier

    def complete(self, identifier, after, result=None, request=None):
        record = self.records[identifier]
        if encoded(record["before"]) == encoded(after):
            del self.records[identifier]
            reference = None
        else:
            record.update(after=deepcopy(after), pending=False)
            record["size"] = len(encoded(record))
            reference = identifier
        reply = {**(result or {}), "undo_id": reference}
        if request is not None:
            self.requests[request[0]] = {"fingerprint": request[1], "reply": reply}
        self.persist()
        return reply

    def get(self, identifier):
        if identifier not in self.records:
            raise UndoError("Unknown or already-used undo reference.")
        return self.records[identifier]

    def rebase_rule(self, previous, restored):
        """Keep successive Undo/Redo usable while rule versions increase."""
        def replace(value):
            if encoded(value) == encoded(previous):
                return deepcopy(restored)
            if value.get("kind") == "batch":
                value["steps"] = [replace(step) for step in value["steps"]]
            return value
        for record in self.records.values():
            for side in ("before", "after"):
                if isinstance(record[side], dict):
                    record[side] = replace(record[side])
            record["size"] = len(encoded({key: value for key, value in record.items() if key != "size"}))

    def _order_metadata(self):
        return {"sequence": max((record.get("sequence", 0) for record in self.records.values()), default=0)+1,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def items(self):
        ordered = sorted(self.records.items(), key=lambda pair: pair[1].get("sequence", 0), reverse=True)
        return [{"undo_id": identifier, "action": record["action"], "created_at": record.get("created_at"),
                 "direction": "pending" if record.get("pending") else "redo" if record["redo"] else "undo"}
                for identifier, record in ordered]
