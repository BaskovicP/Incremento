"""Reviewed native workflows with one durable cross-store checkpoint."""

from copy import deepcopy
import json
from pathlib import Path
import uuid

try:
    from . import db, paths, mcp_checkpoint as checkpoint
    from .config_service import normalize_config, known_config_keys
    from .mcp_anki import AnkiToolError, digest, native_id
    from .mcp_content_operations import McpContentOperations, content_operations
    from .mcp_backup_operations import McpBackupOperations, backup_operations
    from .mcp_collection import ADVANCED_OPERATIONS
    from .mcp_undo import encoded
except ImportError:
    import db
    import paths
    import mcp_checkpoint as checkpoint
    from config_service import normalize_config, known_config_keys
    from mcp_anki import AnkiToolError, digest, native_id
    from mcp_content_operations import McpContentOperations, content_operations
    from mcp_backup_operations import McpBackupOperations, backup_operations
    from mcp_collection import ADVANCED_OPERATIONS
    from mcp_undo import encoded


ADVANCED_OPERATIONS.add("native_workflow")
ID = {"type": "string", "pattern": "^[1-9][0-9]{0,18}$", "maxLength": 19}
TEXT = {"type": "string", "maxLength": 2000}
NAME = {"type": "string", "minLength": 1, "maxLength": 100}
INTEGER = {"type": "integer", "minimum": 0, "maximum": 100000}
NUMBER = {"type": "number", "minimum": 0, "maximum": 10000000}
BOOL = {"type": "boolean"}
RATIO = {"type": "number", "minimum": 0, "maximum": 1}
PATCH = {"type": "object", "maxProperties": 100, "additionalProperties": {}}


def schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


OPERATIONS = {
    "settings": (4, schema({"patch": PATCH}, ["patch"])),
    "playback_control": (
        6,
        schema(
            {
                "card_id": ID,
                "command": {"type": "string", "enum": ["play", "pause", "seek", "speed", "volume"]},
                "value": NUMBER,
            },
            ["card_id", "command"],
        ),
    ),
    "session_preset": (4, schema({"name": NAME, "settings": PATCH, "delete": BOOL}, ["name"])),
    "reader_progress": (
        6,
        schema(
            {
                "card_id": ID,
                "position": NUMBER,
                "read_position": INTEGER,
                "scroll_ratio": RATIO,
                "zoom": {"type": "number", "minimum": 0.1, "maximum": 10},
                "finished": BOOL,
            },
            ["card_id"],
        ),
    ),
    "highlight_create": (
        7,
        schema(
            {
                "card_id": ID,
                "position": INTEGER,
                "text": TEXT,
                "note": TEXT,
                "color": TEXT,
                "style": TEXT,
                "start_offset": INTEGER,
                "end_offset": INTEGER,
                "rects": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": schema({"x": NUMBER, "y": NUMBER, "w": NUMBER, "h": NUMBER}, ["x", "y", "w", "h"]),
                },
            },
            ["card_id", "position", "text"],
        ),
    ),
    "highlight_resize": (
        7,
        schema(
            {
                "card_id": ID,
                "highlight_id": NAME,
                "position": INTEGER,
                "rects": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": schema({"x": NUMBER, "y": NUMBER, "w": NUMBER, "h": NUMBER}, ["x", "y", "w", "h"]),
                },
                "start_offset": INTEGER,
                "end_offset": INTEGER,
            },
            ["card_id", "highlight_id", "position"],
        ),
    ),
    "note_type_create": (12, schema({"name": NAME, "cloze": BOOL}, ["name"])),
    "note_type_clone": (12, schema({"note_type_id": ID, "name": NAME}, ["note_type_id", "name"])),
    "note_type_rename": (12, schema({"note_type_id": ID, "name": NAME}, ["note_type_id", "name"])),
    "note_type_delete": (12, schema({"note_type_id": ID}, ["note_type_id"])),
    "filtered_build": (
        3,
        schema(
            {
                "name": NAME,
                "anki_query": TEXT,
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "reschedule": BOOL,
            },
            ["name", "anki_query"],
        ),
    ),
    "filtered_rebuild": (3, schema({"deck_id": ID}, ["deck_id"])),
    "filtered_empty": (3, schema({"deck_id": ID}, ["deck_id"])),
    "review_all": (
        3,
        schema(
            {
                "card_id": ID,
                "order": TEXT,
                "card_kind": TEXT,
                "tree_scope": TEXT,
                "media_range": TEXT,
                "current_position": NUMBER,
                "state": TEXT,
                "limit": INTEGER,
                "reminder": BOOL,
            },
            ["card_id"],
        ),
    ),
    "session_start": (1, schema({"count": {"type": "integer", "minimum": 1, "maximum": 500}, "anki_query": TEXT})),
    "session_resume": (1, schema({"deck_id": ID})),
    "session_end": (1, schema()),
    "reviewer_show_answer": (2, schema({"card_id": ID}, ["card_id"])),
    "reviewer_show_question": (2, schema({"card_id": ID}, ["card_id"])),
    "answer_card": (
        2,
        schema(
            {
                "card_id": ID,
                "rating": {"type": "integer", "minimum": 1, "maximum": 4},
                "topic_choice": {"type": "string", "enum": ["more", "same", "less"]},
                "milliseconds": {"type": "integer", "minimum": 0, "maximum": 3600000},
            },
            ["card_id", "rating"],
        ),
    ),
    "deck_options": (5, schema({"deck_id": ID, "patch": PATCH}, ["deck_id", "patch"])),
    "fsrs_optimize": (5, schema({"deck_id": ID, "anki_query": TEXT}, ["deck_id"])),
    "timer": (
        15,
        schema(
            {
                "command": {"type": "string", "enum": ["start", "pause", "resume", "reset"]},
                "minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
            },
            ["command"],
        ),
    ),
    "quick_tag_settings": (
        4,
        schema(
            {
                "use_fixed_sets": BOOL,
                "fixed_tag_groups": {
                    "type": "array",
                    "minItems": 9,
                    "maxItems": 9,
                    "items": {"type": "array", "maxItems": 32, "items": NAME},
                },
            },
            ["use_fixed_sets", "fixed_tag_groups"],
        ),
    ),
    "tag_color": (
        4,
        schema(
            {"tag": NAME, "color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$", "maxLength": 7}}, ["tag", "color"]
        ),
    ),
    "check_database": (14, schema()),
    "sync": (16, schema()),
    "switch_profile": (16, schema()),
    "install_addon": (16, schema()),
    "remove_addon": (16, schema()),
}
IRREVERSIBLE = frozenset({"sync", "switch_profile", "install_addon", "remove_addon"})
UI_AREAS = {
    **{
        key: "reviewer"
        for key in (
            "session_start",
            "session_resume",
            "session_end",
            "reviewer_show_answer",
            "reviewer_show_question",
            "review_all",
        )
    },
    "timer": "timer",
    "playback_control": "player",
}
OPERATIONS.update(content_operations(schema, ID, TEXT, NAME, INTEGER, NUMBER, BOOL, PATCH))
OPERATIONS.update(backup_operations(schema, TEXT, PATCH))
AREAS = [
    "Study sessions",
    "Reviewer control",
    "Filtered decks and Review All",
    "Incremento settings and presets",
    "Deck options and FSRS",
    "Reader and playback progress",
    "New annotations and visual extracts",
    "Additional imports",
    "Video and captions",
    "Source-file management",
    "Image occlusion",
    "Note-type lifecycle",
    "Export and backups",
    "Maintenance and repair",
    "Timers and background tasks",
    "Sync and application administration",
]
JOB_TOOLS = frozenset({"start_operation_job", "cancel_operation_job", "retry_operation_job"})
READER_WRITES = frozenset(
    {
        "reader_progress",
        "highlight_create",
        "highlight_resize",
        "notebook_import",
        "source_relink",
        "pdf_annotation_sync",
    }
)


def operation_tools(tool):
    return [
        tool(
            "list_operation_types",
            "Discover reviewed native workflows, their exact parameter schemas and recovery requirements.",
        ),
        tool(
            "preview_operation",
            "Validate a concrete native workflow and retain its before-state. Review the result, then apply_advanced_plan. Strict undo refuses remote sync/profile/add-on mutations.",
            {"action": {"type": "string", "enum": list(OPERATIONS)}, "parameters": PATCH},
            ["action", "parameters"],
        ),
        tool("get_incremento_settings", "Read current normalized Incremento settings and saved session presets."),
        tool(
            "get_reader_progress",
            "Read saved PDF/EPUB/video/web reading state without opening or moving a reader.",
            {"card_id": ID},
            ["card_id"],
        ),
        tool("get_reviewer_state", "Inspect the active reviewer and MCP-owned session state without changing focus."),
        tool("get_background_tasks", "Inspect Activity Center tasks and whether cancellation/retry is reversible."),
        tool(
            "get_administration_status",
            "Read sync/profile/add-on status. Irreversible administration remains disabled under strict undo.",
        ),
        tool(
            "get_deck_options",
            "Read one normal deck preset, including FSRS parameters and daily limits.",
            {"deck_id": ID},
            ["deck_id"],
        ),
        tool(
            "read_image_occlusion",
            "Read native image-occlusion masks, image references and visible fields as inert data.",
            {"note_id": ID},
            ["note_id"],
        ),
        tool(
            "start_operation_job",
            "Queue one reviewed native operation in Anki. Returns immediately; poll get_background_tasks. The job retains its own persistent undo checkpoint.",
            {"plan_id": NAME},
            ["plan_id"],
            write=True,
        ),
        tool(
            "cancel_operation_job",
            "Cancel an owned queued job, or reverse an owned completed job using its durable undo. Running non-cancellable native work is refused until it finishes.",
            {"job_id": NAME},
            ["job_id"],
            write=True,
        ),
        tool(
            "retry_operation_job",
            "Prepare and queue a fresh attempt of an owned finished job. Interrupted writes must be recovered and reversed first.",
            {"job_id": NAME},
            ["job_id"],
            write=True,
        ),
    ]


class McpOperations(McpBackupOperations):
    def _list_operation_types(self, col):
        return {
            "areas": [
                {
                    "number": i + 1,
                    "name": name,
                    "actions": [key for key, (area, _) in OPERATIONS.items() if area == i + 1],
                }
                for i, name in enumerate(AREAS)
            ],
            "operations": [
                {"action": key, "area": area, "parameters": value, "enabled": key not in IRREVERSIBLE}
                for key, (area, value) in OPERATIONS.items()
            ],
            "apply_tool": "apply_advanced_plan",
            "strict_undo": True,
        }

    def _runtime(self, action, parameters=None):
        callback = getattr(self, "runtime", None)
        if callback is None:
            raise AnkiToolError("This operation requires the connected Anki UI adapter.")
        return callback(action, parameters or {})

    def _get_incremento_settings(self, col):
        return {
            "settings": normalize_config({k: v for k, v in self.config.items() if not k.startswith("_")}),
            "revision": digest(self.config),
            "quick_tags": db.get_browser_quick_tag_settings(self.addon_dir, self.profile),
        }

    def _save_operation_settings(self, value):
        callback = getattr(self, "save_config", None)
        if callback is None:
            raise AnkiToolError("Settings persistence is unavailable; no change was made.")
        normalized = normalize_config(value)
        callback(normalized)
        self.config.clear()
        self.config.update(normalized)

    def _get_administration_status(self, col):
        details = self._runtime("administration") if getattr(self, "runtime", None) else {"profile": self.profile}
        return {
            **details,
            "strict_undo": True,
            "irreversible_actions_enabled": False,
            "refused_actions": sorted(IRREVERSIBLE),
            "reason": "Remote sync and process/profile/add-on replacement cannot guarantee complete persistent undo.",
        }

    def _get_reviewer_state(self, col):
        return self._runtime("reviewer_state")

    def _get_background_tasks(self, col):
        try:
            from .activity_log import snapshot_activities
        except ImportError:
            from activity_log import snapshot_activities
        jobs = []
        for plan in list(self.history.plans.values()):
            if plan.get("job"):
                job = deepcopy(plan["job"])
                if job["status"] in {"queued", "preparing", "running"} and job.get("context_id") != self.context_id:
                    job["status"] = "interrupted"
                job.pop("context_id", None)
                jobs.append(job)
        return {
            "items": snapshot_activities(),
            "mcp_jobs": jobs,
            "cancel_retry_enabled": "owned_mcp_jobs_only",
            "reason": "Other native tasks can have external effects and are inspection-only.",
        }

    def _start_operation_job(self, col, plan_id):
        plan = self._advanced_plan(plan_id)
        if plan["payload"]["operation"] != "native_workflow" or plan["full_sync"]:
            raise AnkiToolError(
                "Jobs accept native workflows without schema acknowledgement; apply schema plans directly after review."
            )
        if not getattr(self, "runtime", None):
            raise AnkiToolError("Background jobs require the native Anki adapter.")
        args = {"plan_id": plan_id, "_advanced": deepcopy(plan["payload"])}
        before = self._capture_advanced_action(col, args["_advanced"])
        if plan["used"] or encoded(self._comparable_state(before)) != encoded(self._comparable_state(plan["before"])):
            raise AnkiToolError("The proposal is stale or was already applied.")
        identifier = self.history.prepare("apply_advanced_plan", args, before, collection=True)
        job = {
            "job_id": identifier,
            "plan_id": plan_id,
            "status": "queued",
            "action": plan["payload"]["arguments"]["action"],
            "context_id": self.context_id,
            "undo_id": identifier,
        }
        plan["job"] = job
        self.history.get(identifier)["job_plan"] = plan_id
        reply = {"job_id": identifier, "status": "queued", "undo_id": identifier, "poll_tool": "get_background_tasks"}
        if self._request:
            self.history.requests[self._request[0]] = {"fingerprint": self._request[1], "reply": reply}
        self.history.persist()
        self._runtime("queue_job", {"job_id": identifier})
        return reply

    def prepare_operation_job(self, job_id):
        record = self.history.get(job_id)
        plan = self.history.plans[record["job_plan"]]
        if plan["job"]["status"] != "queued":
            return
        args = record["args"]["_advanced"]["arguments"]
        if "_media_source" not in args["parameters"]:
            return
        plan["job"]["status"] = "preparing"
        self.history.persist()
        try:
            prepared = self._prepare_media(args["action"], args["parameters"])
            args["parameters"]["_prepared_media"] = prepared
            plan["payload"]["arguments"]["parameters"]["_prepared_media"] = prepared
            plan["job"]["status"] = "queued"
        except Exception:
            self.history.complete(job_id, record["before"])
            plan["job"].update(
                status="failed", undo_id=None, error="Media preparation failed; no card or managed media changed."
            )
        self.history.persist()

    def execute_operation_job(self, col, job_id):
        plan = self._job_plan(job_id)
        if plan["job"]["status"] != "queued":
            return None
        record = self.history.get(job_id)
        plan["job"]["status"] = "running"
        self.history.persist()
        self._active_change = job_id
        self._request = None
        try:
            args = record["args"]["_advanced"]["arguments"]
            prepared = args["parameters"].get("_prepared_media")
            if prepared:
                # Refresh the append inventory too: files created by somebody
                # else during preparation must never become this job's output.
                args["_scope"].pop("baseline", None)
            # A queued proposal may be stale. Its inverse must never include
            # unrelated work done by the user while it waited in the queue.
            record["before"] = self._capture_advanced_action(col, record["args"]["_advanced"])
            if prepared:
                p = args["parameters"]
                if self._media_guard(col, p["card_id"], p.get("note_id")) != p["_media_guard"]:
                    raise AnkiToolError("A target note changed during preparation.")
                plan["before"] = deepcopy(record["before"])
            self.history.persist()
            result = self._apply_advanced_plan(col, plan["job"]["plan_id"])
            after = self._capture_advanced_action(col, record["args"]["_advanced"])
            reply = self.history.complete(job_id, after, result)
            plan["job"].update(status="completed", undo_id=reply["undo_id"], result=reply)
        except Exception:
            try:
                after = self._capture_advanced_action(col, record["args"]["_advanced"])
                reply = self.history.complete(job_id, after)
                plan["job"].update(
                    status="failed",
                    undo_id=reply["undo_id"],
                    error="Native operation failed. Reverse any retained change before retrying.",
                )
            except Exception:
                plan["job"].update(
                    status="interrupted", error="Inspect recover_change before attempting another write."
                )
        self.history.persist()
        return self.changes

    def _job_plan(self, job_id):
        for plan in self.history.plans.values():
            if plan.get("job", {}).get("job_id") == job_id:
                return plan
        raise AnkiToolError("Unknown MCP-owned job.")

    def _cancel_operation_job(self, col, job_id):
        plan = self._job_plan(job_id)
        job = plan["job"]
        if job["status"] == "queued" or (job["status"] == "preparing" and job.get("context_id") != self.context_id):
            record = self.history.get(job_id)
            reply = self.history.complete(job_id, record["before"])
            job.update(status="cancelled", undo_id=None)
            self.history.persist()
            return {"job_id": job_id, "cancelled": True, **reply}
        if job["status"] in {"completed", "failed"} and job.get("undo_id"):
            reply = self._undo_change(col, job["undo_id"])
            job.update(status="reversed", undo_id=reply["undo_id"])
            self.history.persist()
            return {"job_id": job_id, **reply}
        raise AnkiToolError("This job cannot be safely cancelled now. Poll it, or recover an interrupted write first.")

    def _retry_operation_job(self, col, job_id):
        plan = self._job_plan(job_id)
        job = plan["job"]
        if job["status"] not in {"cancelled", "reversed"} and not (
            job["status"] == "failed" and not job.get("undo_id")
        ):
            raise AnkiToolError("Cancel or reverse the owned job before retrying.")
        args = plan["payload"]["arguments"]
        parameters = {k: v for k, v in args["parameters"].items() if not k.startswith("_")}
        fresh = self._preview_operation(col, args["action"], parameters)
        return self._start_operation_job(col, fresh["plan_id"])

    def _get_deck_options(self, col, deck_id):
        deck = col.decks.get(native_id(deck_id), default=False)
        if not deck or deck.get("dyn"):
            raise AnkiToolError("Choose a normal deck.")
        config = col.decks.get_config(deck["conf"])
        return {
            "deck_id": deck_id,
            "preset": config,
            "revision": digest(config),
            "fsrs_enabled": bool(col.get_config("fsrs", False)),
        }

    def _reader_kind(self, col, card_id):
        item = self._card(col, card_id)
        names = {
            "Incremento PDF": "pdf",
            "Incremento EPUB": "epub",
            "Incremento Video": "video",
            "Incremento Web": "web",
        }
        if item["note_type"] not in names:
            raise AnkiToolError("Choose a PDF, EPUB, video or web card.")
        return names[item["note_type"]]

    def _get_reader_progress(self, col, card_id):
        kind = self._reader_kind(col, card_id)
        conn = db.get_connection(self.addon_dir, self.profile)
        table = kind + "_progress"
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        row = conn.execute(f"SELECT * FROM {table} WHERE card_id=?", (int(card_id),)).fetchone()
        value = dict(zip(columns, row)) if row else {}
        position = value.get(
            "page", value.get("section_index", value.get("position", 1 if kind in {"pdf", "epub"} else 0))
        )
        if kind == "epub" and row:
            position += 1
        return {"card_id": card_id, "kind": kind, "position": position, "state": value, "revision": digest(value)}

    def _operation_scope(self, col, action, parameters):
        root = paths.get_user_files_dir(self.addon_dir, self.profile)
        scope = {
            "anki": action
            not in {
                "settings",
                "session_preset",
                "reader_progress",
                "highlight_create",
                "highlight_resize",
                "timer",
                "reviewer_show_answer",
                "reviewer_show_question",
                "quick_tag_settings",
                "tag_color",
                "playback_control",
            },
            "sqlite": action
            in {
                "reader_progress",
                "highlight_create",
                "highlight_resize",
                "answer_card",
                "session_start",
                "session_resume",
                "session_end",
                "review_all",
                "quick_tag_settings",
                "tag_color",
            },
            "settings": action in {"settings", "session_preset"},
            "files": [],
            "trees": [],
        }
        if action in {"answer_card", "session_start", "session_resume", "session_end", "review_all"}:
            scope["files"] = [str(root / "custom_learn_stats.json")]
        if action in UI_AREAS or (action == "answer_card" and "_runtime_before" in parameters):
            scope["files"].append(str(paths.get_mcp_runtime_state_path(self.addon_dir, self.profile)))
            scope["ui"] = {"area": UI_AREAS.get(action, "reviewer"), "before": parameters["_runtime_before"]}
        return self._backup_scope(col, action, parameters, self._content_scope(col, action, parameters, scope))

    def _preview_operation(self, col, action, parameters):
        try:
            from .mcp_service import validate
        except ImportError:
            from mcp_service import validate
        if action not in OPERATIONS:
            raise AnkiToolError("Unknown native workflow.")
        validate(parameters, OPERATIONS[action][1])
        if action in IRREVERSIBLE:
            raise AnkiToolError(
                "Strict undo refuses this action: remote/process effects cannot be completely reversed. Use get_administration_status."
            )
        prepared = self._prepare_operation(col, action, deepcopy(parameters))
        scope = self._operation_scope(col, action, prepared)
        return self._new_advanced_plan(
            col,
            "native_workflow",
            {"action": action, "parameters": prepared, "_scope": scope},
            {
                "action": action,
                "parameters": {k: v for k, v in prepared.items() if not k.startswith("_")},
                "recovery": "persistent_checkpoint",
                "scope": {
                    "collection_checkpoint": scope.get("anki", False),
                    "supplemental_checkpoint": scope.get("sqlite", False),
                    "settings_checkpoint": scope.get("settings", False),
                    "explicit_files": len(scope["files"]),
                    "append_only_folders": len(scope.get("append_trees", [])),
                },
                "recommended_execution": "start_operation_job"
                if action
                in {
                    "video_download",
                    "video_transcode",
                    "video_clip",
                    "caption_download",
                    "fsrs_optimize",
                    "check_database",
                    "reindex_pdf",
                    "notebook_import",
                    "backup_export",
                    "backup_restore",
                    "import_content",
                }
                else "apply_advanced_plan",
            },
            full_sync=action.startswith("note_type_")
            or (action == "import_content" and parameters.get("kind") == "apkg"),
        )

    def _prepare_operation(self, col, action, p):
        if action in READER_WRITES and getattr(self, "runtime", None):
            self._runtime("check_readers_closed", {"card_ids": p.get("card_ids", [p.get("card_id")])})
        if action in {"settings", "session_preset"}:
            if getattr(self, "save_config", None) is None:
                raise AnkiToolError("Settings persistence is unavailable.")
            if action == "settings":
                allowed = known_config_keys(self.config)
                if any(
                    k not in allowed
                    or k.startswith("_")
                    or k in {"mcp_enabled", "mcp_allow_writes", "config_schema_version"}
                    for k in p["patch"]
                ):
                    raise AnkiToolError(
                        "Only existing public settings can be changed; connection permissions remain in native settings."
                    )
                if "shortcuts" in p["patch"]:
                    self._runtime("validate_settings", normalize_config({**self.config, **p["patch"]}))
        if action.startswith("note_type_"):
            if "note_type_id" in p:
                model = col.models.get(int(p["note_type_id"]))
                if not model or model["name"].startswith("Incremento "):
                    raise AnkiToolError("Choose an existing custom note type.")
                if action == "note_type_delete" and col.db.scalar(
                    "SELECT count(*) FROM notes WHERE mid=?", model["id"]
                ):
                    raise AnkiToolError("Convert or remove the notes first; only unused types can be deleted.")
            if "name" in p and (p["name"].startswith("Incremento ") or col.models.by_name(p["name"])):
                raise AnkiToolError("Choose a new, non-managed note-type name.")
        if action in {"filtered_build", "session_start"}:
            p.setdefault("limit", 50) if action == "filtered_build" else p.setdefault("count", 50)
            p.setdefault("anki_query", "")
            if action == "filtered_build":
                found = col.decks.by_name(p["name"])
                if found and not found.get("dyn"):
                    raise AnkiToolError("A normal deck already owns this name.")
            ids = col.find_cards(p["anki_query"])
            if len(ids) > 5000:
                raise AnkiToolError("Narrow the query to at most 5,000 candidates.")
        if action in {"filtered_empty", "filtered_rebuild"}:
            deck = col.decks.get(int(p["deck_id"]), default=False)
            if not deck or not deck.get("dyn"):
                raise AnkiToolError("Choose an existing filtered deck.")
        if action == "answer_card":
            self._native_card(col, p["card_id"])
        if action == "session_start":
            from dataclasses import asdict
            from .scheduler_config import _config_from_dialog_dict, configured_day_end_time
            from .session_selection import SessionPicker
            from .topic_scheduler import resolve_topic_card_classifier

            cfg = _config_from_dialog_dict(self.config.get("dialog", {}))
            cfg.session_card_count = p["count"]
            cfg.day_end_time = configured_day_end_time(self.config)
            cfg.priority_lower_is_more_important = bool(self.config.get("priority_lower_is_more_important", True))
            cfg.show_debug = False
            for key in ("topics_filter", "items_filter"):
                value = getattr(cfg, key)
                if p["anki_query"]:
                    setattr(cfg, key, f"({value}) ({p['anki_query']})" if value else p["anki_query"])
            picker = SessionPicker(
                cfg,
                self.addon_dir,
                col=col,
                profile=self.profile,
                topic_classifier=resolve_topic_card_classifier(self.config),
                session_deck_name="Incremento Session",
            )
            picker.pick_until(cfg.session_card_count)
            if not picker.selected_ids:
                raise AnkiToolError("The session selection is empty.")
            p["_session"] = {
                "config": asdict(cfg),
                "picker": asdict(picker.snapshot()),
                "times": deepcopy(picker.stats.session_time),
                "deck_name": "Incremento Session",
            }
        if action == "review_all":
            ids = self._media_review_selection(col, p)["card_ids"]
            if not ids or len(ids) > 500:
                raise AnkiToolError("Choose 1–500 attached cards for Review All.")
            p["_selected_ids"] = ids
        if action in UI_AREAS or (action == "answer_card" and getattr(self, "runtime", None)):
            p["_runtime_before"] = self._runtime(
                "snapshot", {"area": UI_AREAS.get(action, "reviewer"), "card_id": p.get("card_id")}
            )
        return self._prepare_backup(col, action, self._prepare_content(col, action, p))

    def _capture_advanced_action(self, col, payload):
        if payload["operation"] == "native_workflow":
            return checkpoint.capture(self, col, payload["arguments"]["_scope"])
        return super()._capture_advanced_action(col, payload)

    def _comparable_state(self, state):
        return (
            checkpoint.comparable(state)
            if state["kind"] == "operation_checkpoint"
            else super()._comparable_state(state)
        )

    def _restore_collection(self, col, target):
        if target["kind"] == "operation_checkpoint":
            if target.get("anki") and getattr(self, "runtime", None):
                self._runtime("check_full_restore")
            if target.get("runtime"):
                self._runtime("check_restore", {"state": target})
            checkpoint.restore(self, col, target, self._creation_restore_current)
            if "runtime" in target and getattr(self, "runtime", None):
                self._runtime("restore_checkpoint", {"state": target})
            return True
        return super()._restore_collection(col, target)

    def _perform_native_workflow(self, col, action, parameters):
        if action not in OPERATIONS or action in IRREVERSIBLE:
            raise AnkiToolError("Unavailable native operation.")
        self._verify_content_input(parameters)
        if action in READER_WRITES and getattr(self, "runtime", None):
            self._runtime("check_readers_closed", {"card_ids": parameters.get("card_ids", [parameters.get("card_id")])})
        if "_media_source" in parameters:
            prepared = parameters.get("_prepared_media") or self._prepare_media(action, parameters)
            self.check()
            result = self._publish_media(checkpoint.ProfileBound(col, self.check), action, parameters, prepared)
            from anki.collection import OpChanges
            self.changes = OpChanges(**{field.name: True for field in OpChanges.DESCRIPTOR.fields})
            return result
        method = getattr(self, "_op_" + action, None)
        if not method:
            raise AnkiToolError("This native workflow is unavailable.")
        result = method(
            checkpoint.ProfileBound(col, self.check),
            **{
                key: value
                for key, value in parameters.items()
                if not key.startswith("_")
                or key
                in {
                    "_runtime_before",
                    "_restore_targets",
                    "_backup_report",
                    "_selected_ids",
                    "_session",
                    "_prepared_import",
                }
            },
        )
        scope = self.history.get(self._active_change)["args"]["_advanced"]["arguments"]["_scope"]
        if scope.get("anki"):
            from anki.collection import OpChanges
            self.changes = OpChanges(**{field.name: True for field in OpChanges.DESCRIPTOR.fields})
        return result

    def _record_runtime(self, area, state):
        from .mcp_undo import atomic_bytes

        path = paths.get_mcp_runtime_state_path(self.addon_dir, self.profile)
        saved = json.loads(self._bounded_bytes(path)) if path.exists() else {"version": 1}
        saved[area] = state
        atomic_bytes(path, encoded(saved))
        return state

    def _op_session_start(self, col, count=50, anki_query="", _runtime_before=None, _session=None):
        from .session import _prepare_filtered_review_deck

        ids = _session["picker"]["selected_ids"]
        result = _prepare_filtered_review_deck(
            ids,
            deck_name=_session["deck_name"],
            preserve_order=_session["config"]["preserve_order"],
            select_deck=False,
            col=col,
            return_result=True,
        )
        self.changes = result.changes
        state = self._runtime("session", {"command": "start", "deck_id": str(result.deck_id), "session": _session})
        self._record_runtime("reviewer", state)
        return {"deck_id": str(result.deck_id), "selected": len(ids)}

    def _op_session_resume(self, col, deck_id=None, _runtime_before=None):
        deck = col.decks.get(int(deck_id), default=False) if deck_id else col.decks.by_name("Incremento Session")
        if not deck:
            raise AnkiToolError("No saved session deck is available.")
        state = self._runtime("session", {"command": "resume", "deck_id": str(deck["id"])})
        return self._record_runtime("reviewer", state)

    def _op_session_end(self, col, _runtime_before=None):
        return self._record_runtime("reviewer", self._runtime("session", {"command": "end"}))

    def _op_reviewer_show_answer(self, col, card_id, _runtime_before=None):
        return self._record_runtime("reviewer", self._runtime("reviewer_side", {"card_id": card_id, "side": "answer"}))

    def _op_reviewer_show_question(self, col, card_id, _runtime_before=None):
        return self._record_runtime(
            "reviewer", self._runtime("reviewer_side", {"card_id": card_id, "side": "question"})
        )

    def _op_timer(self, col, command, minutes=None, _runtime_before=None):
        return self._record_runtime("timer", self._runtime("timer", {"command": command, "minutes": minutes}))

    def _op_playback_control(self, col, card_id, command, value=None, _runtime_before=None):
        if command in {"seek", "speed", "volume"} and value is None:
            raise AnkiToolError("This playback command requires a value.")
        if command == "speed" and not 0.25 <= value <= 4:
            raise AnkiToolError("Playback speed must be between 0.25 and 4.")
        if command == "volume" and not 0 <= value <= 100:
            raise AnkiToolError("Volume must be between zero and 100.")
        state = self._runtime("playback", {"card_id": card_id, "command": command, "value": value})
        return self._record_runtime("player", state)

    def _op_quick_tag_settings(self, col, use_fixed_sets, fixed_tag_groups):
        self._ensure_tag_colors([tag for group in fixed_tag_groups for tag in group])
        db.set_browser_quick_tag_settings(
            self.addon_dir, self.profile, use_fixed_sets=use_fixed_sets, fixed_tag_groups=fixed_tag_groups
        )
        return {"quick_tags": db.get_browser_quick_tag_settings(self.addon_dir, self.profile)}

    def _op_tag_color(self, col, tag, color):
        self._ensure_tag_colors([tag])
        assignments = db.get_browser_tag_color_indexes(self.addon_dir, self.profile)
        rendered = self._runtime("tag_palette", {"indexes": list(assignments.values())})["colors"]
        custom = db.get_browser_tag_custom_colors(self.addon_dir, self.profile)
        for key, index in assignments.items():
            if key != tag.casefold() and (custom.get(key) or rendered[str(index)]).casefold() == color.casefold():
                raise AnkiToolError("Another tag already owns this color.")
        db.set_browser_tag_custom_color(self.addon_dir, self.profile, tag, color)
        return {"tag": tag, "color": color}

    def _ensure_tag_colors(self, tags):
        if not tags:
            return
        palette = self._runtime("tag_palette", {})
        db.assign_browser_tag_color_indexes(
            self.addon_dir, self.profile, tags, palette_size=palette["size"], reserved_indexes=palette["reserved"]
        )

    def _op_check_database(self, col):
        _, ok = col.fix_integrity()
        return {
            "anki_integrity_ok": ok,
            "supplemental_integrity_ok": db.get_connection(self.addon_dir, self.profile)
            .execute("PRAGMA integrity_check")
            .fetchone()[0]
            == "ok",
        }

    def _op_settings(self, col, patch):
        value = {**normalize_config(self.config), **patch}
        self._save_operation_settings(value)
        return {"changed_settings": list(patch)}

    def _op_session_preset(self, col, name, settings=None, delete=False):
        cfg = normalize_config(self.config)
        presets = dict(cfg.get("scheduler_presets", {}))
        if delete:
            presets.pop(name, None)
        else:
            presets[name] = settings or cfg.get("dialog", {})
        cfg["scheduler_presets"] = presets
        self._save_operation_settings(cfg)
        return {"name": name, "deleted": delete}

    def _op_reader_progress(
        self, col, card_id, position=None, read_position=None, scroll_ratio=None, zoom=None, finished=None
    ):
        kind = self._reader_kind(col, card_id)
        table = kind + "_progress"
        columns = {r[1] for r in db.get_connection(self.addon_dir, self.profile).execute(f"PRAGMA table_info({table})")}
        mapping = {
            "pdf": ("page", "read_page"),
            "epub": ("section_index", "read_section_index"),
            "video": ("position", None),
            "web": ("scroll_ratio", None),
        }
        values = {}
        if position is not None:
            key = mapping[kind][0]
            if kind in {"pdf", "epub"} and (position < 1 or int(position) != position):
                raise AnkiToolError("Document positions are one-based.")
            if kind == "web" and not 0 <= position <= 1:
                raise AnkiToolError("Web scroll positions are between zero and one.")
            if kind in {"pdf", "epub"}:
                position = int(position)
            values[key] = position - 1 if kind == "epub" else position
        if read_position is not None:
            key = mapping[kind][1]
            if not key:
                raise AnkiToolError("This reader has no read-range marker.")
            values[key] = max(0, read_position - 1) if kind == "epub" else read_position
        if scroll_ratio is not None and "scroll_ratio" in columns:
            values["scroll_ratio"] = scroll_ratio
        if zoom is not None:
            values["zoom" if kind == "pdf" else "font_scale"] = zoom
        if finished is not None and kind == "epub":
            values["is_finished"] = int(finished)
        if not values or not set(values) <= columns:
            raise AnkiToolError("No supported progress fields were supplied.")
        conn = db.get_connection(self.addon_dir, self.profile)
        with conn:
            conn.execute(f"INSERT OR IGNORE INTO {table}(card_id) VALUES (?)", (int(card_id),))
            conn.execute(
                f"UPDATE {table} SET " + ",".join(k + "=?" for k in values) + " WHERE card_id=?",
                [*values.values(), int(card_id)],
            )
        return self._get_reader_progress(col, card_id)

    def _op_highlight_create(
        self,
        col,
        card_id,
        position,
        text,
        note="",
        color="yellow",
        style="highlight",
        rects=None,
        start_offset=None,
        end_offset=None,
    ):
        try:
            from . import pdf_highlights, epub_highlights
        except ImportError:
            import pdf_highlights
            import epub_highlights
        kind = self._reader_kind(col, card_id)
        if position < 1:
            raise AnkiToolError("Document positions are one-based.")
        identity = uuid.uuid4().hex
        if kind == "pdf":
            if not rects or any(r["w"] <= 0 or r["h"] <= 0 for r in rects):
                raise AnkiToolError("Supply positive PDF page rectangles.")
            pdf_highlights.add_highlight(
                self.addon_dir,
                self.profile,
                int(card_id),
                {
                    "id": identity,
                    "page": position,
                    "rects": rects,
                    "text": text,
                    "note": note,
                    "color": color,
                    "style": style,
                },
            )
        elif kind == "epub":
            if start_offset is None or end_offset is None or end_offset <= start_offset:
                raise AnkiToolError("Supply a nonempty EPUB text range.")
            epub_highlights.add_highlight(
                self.addon_dir,
                self.profile,
                int(card_id),
                {
                    "id": identity,
                    "sectionIndex": position - 1,
                    "startOffset": start_offset,
                    "endOffset": end_offset,
                    "text": text,
                    "note": note,
                    "color": color,
                    "style": style,
                },
            )
        else:
            raise AnkiToolError("Highlights require a PDF or EPUB.")
        return {"highlight_id": identity, "card_id": card_id}

    def _op_highlight_resize(
        self, col, card_id, highlight_id, position, rects=None, start_offset=None, end_offset=None
    ):
        try:
            from . import pdf_highlights, epub_highlights
        except ImportError:
            import pdf_highlights
            import epub_highlights
        module = pdf_highlights if self._reader_kind(col, card_id) == "pdf" else epub_highlights
        item = next(
            (x for x in module.load_highlights(self.addon_dir, self.profile, int(card_id)) if x["id"] == highlight_id),
            None,
        )
        if not item:
            raise AnkiToolError("Highlight no longer exists.")
        if module is pdf_highlights:
            if not rects:
                raise AnkiToolError("Supply PDF geometry.")
            item.update(page=position, rects=rects)
        else:
            if start_offset is None or end_offset is None or end_offset <= start_offset:
                raise AnkiToolError("Supply EPUB offsets.")
            item.update(sectionIndex=position - 1, startOffset=start_offset, endOffset=end_offset)
        module.update_highlight(self.addon_dir, self.profile, int(card_id), item)
        return {"highlight_id": highlight_id}

    def _op_note_type_clone(self, col, note_type_id, name):
        model = col.models.copy(col.models.get(int(note_type_id)), add=False)
        model["name"] = name
        result = col.models.add(model)
        self.changes = result.changes
        return {"note_type_id": str(result.id)}

    def _op_note_type_create(self, col, name, cloze=False):
        original = col.models.by_name("Cloze" if cloze else "Basic")
        if not original:
            raise AnkiToolError("The native Basic/Cloze base type is unavailable.")
        return self._op_note_type_clone(col, str(original["id"]), name)

    def _op_note_type_rename(self, col, note_type_id, name):
        model = col.models.get(int(note_type_id))
        model["name"] = name
        col.models.update(model)
        return {"note_type_id": note_type_id, "name": name}

    def _op_note_type_delete(self, col, note_type_id):
        self.changes = col.models.remove(int(note_type_id))
        return {"deleted": note_type_id}

    def _op_filtered_build(self, col, name, anki_query, limit=50, reschedule=True):
        existing = col.decks.by_name(name)
        did = existing["id"] if existing else col.decks.new_filtered(name)
        deck = col.sched.get_or_create_filtered_deck(did)
        deck.config.search_terms[0].search = anki_query
        deck.config.search_terms[0].limit = limit
        deck.config.reschedule = reschedule
        changed = col.sched.add_or_update_filtered_deck(deck)
        self.changes = changed.changes
        result = col.sched.rebuild_filtered_deck(did)
        self.changes = result.changes
        return {"deck_id": str(did), "cards": result.count}

    def _op_filtered_rebuild(self, col, deck_id):
        result = col.sched.rebuild_filtered_deck(int(deck_id))
        self.changes = result.changes
        return {"deck_id": deck_id, "cards": result.count}

    def _op_filtered_empty(self, col, deck_id):
        self.changes = col.sched.empty_filtered_deck(int(deck_id))
        return {"deck_id": deck_id, "emptied": True}

    def _op_deck_options(self, col, deck_id, patch):
        patch = deepcopy(patch)
        fsrs_enabled = patch.pop("fsrs_enabled", None)
        if fsrs_enabled is not None and type(fsrs_enabled) is not bool:
            raise AnkiToolError("fsrs_enabled must be a boolean.")
        value = self._get_deck_options(col, deck_id)["preset"]

        def merge(target, source):
            for key, item in source.items():
                if key not in target or key in {"id", "mod", "usn", "dyn"}:
                    raise AnkiToolError("Unsupported deck option.")
                if isinstance(item, dict):
                    if not isinstance(target[key], dict):
                        raise AnkiToolError("Invalid nested deck option.")
                    merge(target[key], item)
                else:
                    target[key] = item

        merge(value, patch)
        col.decks.update_config(value)
        if fsrs_enabled is not None:
            col.set_config("fsrs", fsrs_enabled)
        from anki.collection import OpChanges

        self.changes = OpChanges(config=True)
        return {"deck_id": deck_id, "preset_id": str(value["id"])}

    def _op_fsrs_optimize(self, col, deck_id, anki_query=""):
        value = self._get_deck_options(col, deck_id)["preset"]
        result = col._backend.compute_fsrs_params(
            search=anki_query or 'preset:"' + value["name"].replace('"', '\\"') + '"',
            current_params=value.get("fsrsParams6") or value.get("fsrsParams5") or [],
            ignore_revlogs_before_ms=0,
            num_of_relearning_steps=len(value.get("lapse", {}).get("delays", [])),
            health_check=False,
        )
        if not result.params:
            raise AnkiToolError("FSRS optimization did not return parameters; more review history may be needed.")
        value["fsrsParams6"] = list(result.params)
        col.decks.update_config(value)
        return {"deck_id": deck_id, "parameters": list(result.params), "rescheduled": False}

    def _media_review_selection(self, col, p):
        from .media_review import inspect_linked_media_review_rows, select_linked_media_review_rows
        from .topic_scheduler import resolve_topic_card_classifier

        kind = self._reader_kind(col, p["card_id"])
        if kind not in {"pdf", "epub", "video"}:
            raise AnkiToolError("Review All requires PDF, EPUB or video.")
        rows = inspect_linked_media_review_rows(
            self.addon_dir,
            self.profile,
            int(p["card_id"]),
            col=col,
            media_kind=kind,
            topic_classifier=resolve_topic_card_classifier(self.config),
        )
        return select_linked_media_review_rows(
            rows,
            **{
                k: v
                for k, v in p.items()
                if k in {"order", "card_kind", "tree_scope", "media_range", "current_position", "state", "limit"}
            },
        )

    def _op_review_all(self, col, card_id, reminder=False, _selected_ids=None, **options):
        selected = self._media_review_selection(col, {"card_id": card_id, **options})
        ids = selected["card_ids"]
        if ids != _selected_ids:
            raise AnkiToolError("The linked-card selection changed. Generate another preview.")
        if not ids or len(ids) > 500:
            raise AnkiToolError("Choose 1–500 attached cards for Review All.")
        from .session import _prepare_filtered_review_deck

        result = _prepare_filtered_review_deck(
            ids,
            deck_name="Incremento MCP Review All",
            preserve_order=True,
            reschedule=not reminder,
            select_deck=False,
            col=col,
            return_result=True,
        )
        self.changes = result.changes
        state = self._runtime("session", {"command": "start", "deck_id": str(result.deck_id)})
        self._record_runtime("reviewer", state)
        return {"deck_id": str(result.deck_id), "cards": len(ids), "reminder": reminder}

    def _op_answer_card(self, col, card_id, rating, topic_choice=None, milliseconds=0, _runtime_before=None):
        card = col.get_card(int(card_id))
        from .topic_scheduler import is_topic_card, resolve_topic_card_classifier

        topic = is_topic_card(card, classifier=resolve_topic_card_classifier(self.config))
        if topic_choice and not topic:
            raise AnkiToolError("Frequency choices require a Topic card.")
        if getattr(self, "runtime", None):
            prepared = self._runtime(
                "prepare_answer",
                {"card_id": card_id, "rating": rating, "topic_choice": topic_choice or ("same" if topic else None)},
            )
            answer = prepared["answer"]
            answer.milliseconds_taken = milliseconds
            self.changes = col.sched.answer_card(answer)
            self._runtime("finish_answer", {"card_id": card_id, "ease": prepared["ease"]})
            state = self._runtime("snapshot", {"area": "reviewer"})
            state.pop("queue", None)
            state.update(card_id=None, side="question")
            self._record_runtime("reviewer", state)
            return {"card_id": card_id, "rating": prepared["ease"], "topic_choice": topic_choice}
        if topic or db.get_custom_schedule_rule(self.addon_dir, self.profile, int(card_id)):
            raise AnkiToolError("Topic/custom answers require the live reviewer adapter.")
        card.start_timer()
        answer = col.sched.build_answer(card=card, states=col._backend.get_scheduling_states(card.id), rating=rating)
        answer.milliseconds_taken = milliseconds
        self.changes = col.sched.answer_card(answer)
        return {"card_id": card_id, "rating": rating}
