"""Explicit rich-content, deck, scheduling, schema and removal workflows."""

from copy import deepcopy
import hashlib
import html
import json
import os
from pathlib import Path
import re
import uuid
import tempfile
from urllib.parse import unquote

try:
    from . import db
    from .mcp_anki import McpAnki, AnkiToolError, MANAGED_NOTE_TYPES, digest, native_id, plain
    from .mcp_snapshots import capture_notes, restore_notes, semantic_state, validate_notes_restore, canonical
    from .mcp_undo import encoded, atomic_bytes
    from .mcp_creation import fingerprint
    from .note_metadata import visible_field_names
    from .content_safety import normalize_external_http_url
    from .i18n import t
except ImportError:
    import db
    from mcp_anki import McpAnki, AnkiToolError, MANAGED_NOTE_TYPES, digest, native_id, plain
    from mcp_snapshots import capture_notes, restore_notes, semantic_state, validate_notes_restore, canonical
    from mcp_undo import encoded, atomic_bytes
    from mcp_creation import fingerprint
    from note_metadata import visible_field_names
    from content_safety import normalize_external_http_url
    from i18n import t


COLLECTION_EXT_WRITES = frozenset(
    {
        "create_deck",
        "rename_deck",
        "change_card_schedule",
        "apply_advanced_plan",
        "update_note_html",
        "attach_media",
        "run_image_ocr",
    }
)
ADVANCED_OPERATIONS = {"deck_merge", "conversion", "type_edit", "removal", "duplicate_merge"}
_ALLOWED_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "s",
    "strike",
    "sub",
    "sup",
    "div",
    "p",
    "span",
    "br",
    "hr",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "pre",
    "code",
    "blockquote",
    "a",
    "img",
    "audio",
    "video",
    "source",
    "anki-mathjax",
}


def local_media_name(value):
    value = unquote(html.unescape(str(value)))
    if (
        not value
        or len(value) > 255
        or Path(value).name != value
        or any(c in value for c in ("/", "\\", "\0", ":"))
        or any(ord(c) < 32 for c in value)
        or value in {".", ".."}
    ):
        raise AnkiToolError("Use an exact local Anki media filename.")
    return value


def safe_css(value):
    if len(value) > 32000 or re.search(
        r"url\s*\(|expression\s*\(|@(?:import|font-face)|behavior\s*:|binding\s*:|[<>\\\x00]", value, re.I
    ):
        raise AnkiToolError("CSS must be bounded and cannot load resources or active content.")
    return value


def rich_html(value, *, template=False):
    from bs4 import BeautifulSoup

    if len(value) > 48000:
        raise AnkiToolError("Rich text exceeds 48,000 characters.")
    soup = BeautifulSoup(value, "html.parser")
    for tag in list(
        soup.find_all(["script", "style", "iframe", "object", "embed", "svg", "math", "link", "meta", "base", "form"])
    ):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        for key in list(tag.attrs):
            value = tag.attrs[key]
            if key == "href" and tag.name == "a":
                try:
                    tag.attrs[key] = normalize_external_http_url(value)
                except ValueError:
                    del tag.attrs[key]
            elif key in {"src", "poster"} and tag.name in {"img", "audio", "video", "source"}:
                try:
                    if template and re.fullmatch(r"\{\{[\w :_-]+\}\}", str(value)):
                        continue
                    tag.attrs[key] = local_media_name(value)
                except AnkiToolError:
                    del tag.attrs[key]
            elif key == "style":
                try:
                    tag.attrs[key] = safe_css(str(value))
                except AnkiToolError:
                    del tag.attrs[key]
            elif key == "class":
                tag.attrs[key] = [part for part in value if re.fullmatch(r"[\w-]{1,80}", part)][:12]
            elif key in {"width", "height", "colspan", "rowspan"} and re.fullmatch(r"\d{1,4}%?", str(value)):
                continue
            elif key in {"alt", "title", "controls", "block"}:
                tag.attrs[key] = str(value)[:500]
            else:
                del tag.attrs[key]

    def sound_marker(match):
        try:
            local_media_name(match.group(1))
            return match.group(0)
        except AnkiToolError:
            return "&#91;sound:" + html.escape(match.group(1)) + "&#93;"

    return re.sub(r"\[sound:([^\]]*)\]", sound_marker, str(soup), flags=re.IGNORECASE)


def media_names(fields):
    from bs4 import BeautifulSoup

    names = set()
    for text in fields:
        for tag in BeautifulSoup(text, "html.parser").find_all(["img", "audio", "video", "source"]):
            for key in ("src", "poster"):
                if tag.get(key):
                    try:
                        names.add(local_media_name(tag[key]))
                    except AnkiToolError:
                        pass
        for name in re.findall(r"\[sound:([^\]]+)\]", text):
            try:
                names.add(local_media_name(name))
            except AnkiToolError:
                pass
    return sorted(names)


def collection_tools(tool, identity, ids, text, revision, cursor, limit):
    fields = {"type": "object", "maxProperties": 20, "additionalProperties": {"type": "string", "maxLength": 48000}}
    mapping = {"type": "object", "maxProperties": 100, "additionalProperties": revision}
    return [
        tool(
            "update_note_html",
            "Edit selected visible fields as sanitized rich HTML, retaining formatting, local media and equations. "
            "Requires a read_notes content revision and stable card layout. Scripts, event handlers and remote resources are removed.",
            {"note_id": identity, "fields": fields, "expected_revision": revision},
            ["note_id", "fields", "expected_revision"],
            write=True,
            destructive=True,
        ),
        tool(
            "get_media_references",
            "Inspect exact local image/audio/video references and their availability for selected notes.",
            {"note_ids": ids},
            ["note_ids"],
        ),
        tool(
            "attach_media",
            "Copy one local image/audio/video into a unique Anki media filename and append/replace one visible field. "
            "Original files and existing attachments are retained; durable undo removes only the owned copy when it has no newer references.",
            {
                "note_id": identity,
                "field_name": {"type": "string", "maxLength": 100},
                "path": {"type": "string", "maxLength": 2000},
                "mode": {"type": "string", "enum": ["append", "replace"]},
                "expected_revision": revision,
            },
            ["note_id", "field_name", "path", "expected_revision"],
            write=True,
        ),
        tool(
            "create_deck",
            "Create a normal Anki deck, including missing ancestor decks. Retains exact deck IDs for durable undo/redo.",
            {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
            ["name"],
            write=True,
        ),
        tool(
            "rename_deck",
            "Rename or move a deck hierarchy by its full :: path, preserving IDs/cards. Target parent must exist; requires a deck revision.",
            {
                "deck_id": identity,
                "name": {"type": "string", "minLength": 1, "maxLength": 200},
                "expected_revision": revision,
            },
            ["deck_id", "name", "expected_revision"],
            write=True,
            destructive=True,
        ),
        tool(
            "preview_deck_merge",
            "Preview merging complete source deck branches into one normal target deck. Preserves schedules; apply_advanced_plan performs it as one durable change.",
            {"source_deck_ids": ids, "target_deck_id": identity},
            ["source_deck_ids", "target_deck_id"],
        ),
        tool(
            "change_card_schedule",
            "Explicit native due-date, ease-factor, bury/unbury or reset-to-new operation. "
            "Requires fresh get_cards revisions, normal decks, and a retained native checkpoint including siblings/revlog. "
            "Does not answer cards. Reset preserves past review history.",
            {
                "card_ids": ids,
                "expected_revisions": mapping,
                "action": {"type": "string", "enum": ["due", "ease", "bury", "unbury", "reset"]},
                "days": {"type": "integer", "minimum": 0, "maximum": 36500},
                "ease_factor": {"type": "integer", "minimum": 1300, "maximum": 5000},
            },
            ["card_ids", "expected_revisions", "action"],
            write=True,
            destructive=True,
        ),
        tool(
            "preview_note_type_conversion",
            "Preview converting selected notes to an existing type using target-field -> source-field mappings. "
            "Optional wrap_cloze explicitly wraps the target cloze text in c1. Shows data/card effects and full-sync implications.",
            {
                "note_ids": ids,
                "target_note_type_id": identity,
                "field_map": {
                    "type": "object",
                    "maxProperties": 100,
                    "additionalProperties": {"type": "string", "maxLength": 100},
                },
                "wrap_cloze": {"type": "boolean"},
            },
            ["note_ids", "target_note_type_id", "field_map"],
        ),
        tool(
            "preview_note_type_edit",
            "Preview a concrete field/template/CSS edit on an existing text note type, with native rendered HTML. "
            "All notes using the type must fit the checkpoint budget. Field source names preserve/reorder existing values; omitted sources add blank fields. "
            "Managed Incremento formats remain protected. Applying requires explicit full-sync acknowledgement.",
            {
                "note_type_id": identity,
                "fields": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string", "minLength": 1, "maxLength": 100},
                            "source": {"type": "string", "maxLength": 100},
                        },
                    },
                },
                "templates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "front", "back"],
                        "properties": {
                            "name": {"type": "string", "minLength": 1, "maxLength": 100},
                            "front": {"type": "string", "maxLength": 16000},
                            "back": {"type": "string", "maxLength": 16000},
                        },
                    },
                },
                "css": {"type": "string", "maxLength": 32000},
            },
            ["note_type_id"],
        ),
        tool(
            "preview_note_removal",
            "Preview deleting exact notes or archiving them with native suspension plus the incremento::archived tag. "
            "Delete retains an identity-preserving native package, supplemental rows and all original media for durable restoration.",
            {"note_ids": ids, "mode": {"type": "string", "enum": ["delete", "archive"]}},
            ["note_ids", "mode"],
        ),
        tool(
            "preview_duplicate_merge",
            "Preview merging selected duplicate notes into a chosen survivor. Requires an explicit survivor and field values; "
            "unions tags and retains the survivor schedule, while removed notes/reviews are retained for undo. Does not combine FSRS histories.",
            {"note_ids": ids, "survivor_note_id": identity, "fields": fields},
            ["note_ids", "survivor_note_id", "fields"],
        ),
        tool(
            "apply_advanced_plan",
            "Apply one exact reviewed advanced proposal after checking all affected state. "
            "Schema/type edits require acknowledge_full_sync=true after user review. Returns one durable undo/redo reference.",
            {
                "plan_id": {"type": "string", "minLength": 32, "maxLength": 32},
                "acknowledge_full_sync": {"type": "boolean"},
            },
            ["plan_id"],
            write=True,
            destructive=True,
        ),
    ]


class McpCollection(McpAnki):
    def _new_advanced_plan(self, col, operation, args, details=None, full_sync=False):
        self.history.check_capacity({})
        if operation not in ADVANCED_OPERATIONS or len(self.history.plans) >= 100:
            raise AnkiToolError("Advanced proposal budget is full or the operation is unavailable.")
        payload = {"operation": operation, "arguments": deepcopy(args)}
        before = self._capture_advanced_action(col, payload)
        self.history.check_capacity(before)
        identifier = uuid.uuid4().hex
        result = {
            "plan_id": identifier,
            "operation": operation,
            "data_changed": False,
            "requires_full_sync_acknowledgement": full_sync,
            **(details or {}),
        }
        self.history.plans[identifier] = {
            "kind": "advanced",
            "payload": payload,
            "before": before,
            "details": result,
            "used": False,
            "full_sync": full_sync,
        }
        self.history.persist()
        return result

    def _advanced_plan(self, plan_id):
        plan = self.history.plans.get(plan_id)
        if (
            not isinstance(plan, dict)
            or plan.get("kind") != "advanced"
            or plan["payload"]["operation"] not in ADVANCED_OPERATIONS
        ):
            raise AnkiToolError("Unknown advanced plan.")
        return plan

    def _apply_advanced_plan(self, col, plan_id, acknowledge_full_sync=False):
        plan = self._advanced_plan(plan_id)
        payload = self.history.get(self._active_change)["args"]["_advanced"]
        current = self._capture_advanced_action(col, payload)
        if plan["used"] or encoded(self._comparable_state(current)) != encoded(self._comparable_state(plan["before"])):
            raise AnkiToolError("The proposal changed or was already applied. Generate another preview.")
        if plan["full_sync"] and not acknowledge_full_sync:
            raise AnkiToolError(
                "This exact schema/type proposal requires user review and explicit full-sync acknowledgement."
            )
        self.check()
        result = getattr(self, "_perform_" + payload["operation"])(
            col, **{key: value for key, value in payload["arguments"].items() if not key.startswith("_")}
        )
        plan["used"] = True
        return {"plan_id": plan_id, "operation": payload["operation"], "applied": True, **(result or {})}

    @staticmethod
    def _deck_name(name):
        parts = [part.strip() for part in name.split("::")]
        if not parts or any(not part or any(ord(c) < 32 for c in part) for part in parts):
            raise AnkiToolError("Use a nonempty ::-separated deck name.")
        return "::".join(parts)

    def _deck_ids(self, col, ids):
        found = []
        for did in ids:
            deck = col.decks.get(native_id(did), default=False)
            if not deck or deck.get("dyn"):
                raise AnkiToolError("Choose existing normal decks.")
            found.append(deck)
        return found

    def _deck_branch_ids(self, col, ids):
        decks = self._deck_ids(col, ids)
        names = [deck["name"].casefold() for deck in decks]
        result = [
            item.id
            for item in col.decks.all_names_and_ids()
            if any(item.name.casefold() == name or item.name.casefold().startswith(name + "::") for name in names)
        ]
        if len(result) > 100:
            raise AnkiToolError("Select a smaller deck branch (at most 100 decks).")
        self._deck_ids(col, result)
        return sorted(result)

    def _capture_decks(self, col, args, ids=(), names=()):
        anchors = set(args.get("_deck_ids", [])) | set(map(int, ids))
        for name in names:
            deck = col.decks.by_name(name)
            if deck:
                anchors.add(deck["id"])
        args["_deck_ids"] = sorted(anchors)
        definitions = []
        for did in sorted(anchors):
            deck = col.decks.get(did, default=False)
            if deck:
                count = col.db.scalar("SELECT count(*) FROM cards WHERE did=? OR odid=?", did, did)
                children = [
                    item.id
                    for item in col.decks.all_names_and_ids()
                    if item.name.casefold().startswith(deck["name"].casefold() + "::")
                ]
                definitions.append({"definition": deepcopy(deck), "card_count": count, "children": sorted(children)})
        if "_deck_note_ids" not in args:
            marks = ",".join("?" for _ in anchors) or "NULL"
            note_ids = col.db.list(
                f"SELECT DISTINCT nid FROM cards WHERE did IN ({marks}) ORDER BY nid LIMIT 101", *sorted(anchors)
            )
            if len(note_ids) > 100:
                raise AnkiToolError("Deck operation exceeds 100 affected notes; move smaller batches first.")
            args["_deck_note_ids"] = note_ids
        notes = capture_notes(self, col, args, args["_deck_note_ids"])
        return {
            "kind": "native_decks",
            "decks": definitions,
            "notes": notes,
            "names": list(names),
            "scope_ids": sorted(anchors),
        }

    def _create_deck(self, col, name):
        name = self._deck_name(name)
        deck = col.decks.by_name(name)
        if deck:
            return {"deck_id": str(deck["id"]), "created": False}
        result = col.decks.add_normal_deck_with_name(name)
        self.changes = result.changes
        return {"deck_id": str(result.id), "created": True}

    def _rename_deck(self, col, deck_id, name, expected_revision):
        deck = self._deck_ids(col, [deck_id])[0]
        if digest({key: value for key, value in deck.items() if key != "usn"}) != expected_revision:
            raise AnkiToolError("Deck changed. Read get_decks again.")
        name = self._deck_name(name)
        parent = name.rpartition("::")[0]
        if parent and not col.decks.by_name(parent):
            raise AnkiToolError("Create the target parent deck first.")
        if name.casefold().startswith(deck["name"].casefold() + "::"):
            raise AnkiToolError("A deck cannot be moved inside itself.")
        for item in self._deck_ids(col, self._deck_branch_ids(col, [deck_id])):
            candidate = name + item["name"][len(deck["name"]) :]
            found = col.decks.by_name(candidate)
            if found and found["id"] != item["id"]:
                raise AnkiToolError("The destination deck hierarchy already exists.")
        self.changes = col.decks.rename(native_id(deck_id), name)
        return {"deck_id": deck_id, "name": name}

    def _preview_deck_merge(self, col, source_deck_ids, target_deck_id):
        sources = self._deck_branch_ids(col, source_deck_ids)
        target = self._deck_ids(col, [target_deck_id])[0]
        if target["id"] in sources or 1 in sources:
            raise AnkiToolError("The target cannot be a source branch; the Default deck cannot be removed.")
        return self._new_advanced_plan(
            col,
            "deck_merge",
            {"source_deck_ids": list(map(str, sources)), "target_deck_id": target_deck_id},
            {"source_decks": [deck["name"] for deck in self._deck_ids(col, sources)], "target_deck": target["name"]},
        )

    def _perform_deck_merge(self, col, source_deck_ids, target_deck_id):
        self._deck_ids(col, [*source_deck_ids, target_deck_id])
        ids = col.db.list(
            f"SELECT id FROM cards WHERE did IN ({','.join('?' for _ in source_deck_ids)})", *map(int, source_deck_ids)
        )
        entry = col.add_custom_undo_entry(t("mcp_undo_batch"))
        try:
            if ids:
                col.set_deck(ids, native_id(target_deck_id))
            col.decks.remove(list(map(int, source_deck_ids)))
        finally:
            self.changes = col.merge_undo_entries(entry)
        return {"cards_moved": len(ids), "target_deck_id": target_deck_id}

    def _change_card_schedule(self, col, card_ids, expected_revisions, action, days=None, ease_factor=None):
        ids = self._checked_cards(col, card_ids, expected_revisions, normal=True)
        self.check()
        if action == "due":
            if days is None:
                raise AnkiToolError("Supply an exact due-day offset.")
            # Set Due Date adds an undeletable manual revlog through today's
            # public API. Update cards through Anki instead so persistent undo
            # can restore the exact pre-operation review history.
            cards = [col.get_card(cid) for cid in ids]
            for card in cards:
                card.due = col.sched.today + days
                if card.type != 2:
                    card.type = 2
                    card.ivl = max(1, days)
                    card.factor = card.factor or 2500
                    card.left = 0
                    card.memory_state = None
                    card.original_position = None
                if card.queue >= 0:
                    card.queue = 2
            self.changes = col.update_cards(cards)
        elif action == "reset":
            from anki.scheduler_pb2 import ScheduleCardsAsNewRequest

            self.changes = col._backend.schedule_cards_as_new(
                ScheduleCardsAsNewRequest(card_ids=ids, log=False, reset_counts=True, restore_position=False)
            )
        elif action == "bury":
            self.changes = col.sched.bury_cards(ids).changes
        elif action == "unbury":
            buried = [cid for cid in ids if col.get_card(cid).queue in (-2, -3)]
            if buried:
                self.changes = col.sched.unbury_cards(buried)
        else:
            if ease_factor is None:
                raise AnkiToolError("Supply ease_factor in native per-thousand units.")
            cards = [col.get_card(cid) for cid in ids]
            for card in cards:
                card.factor = ease_factor
            self.changes = col.update_cards(cards)
        return {"card_ids": card_ids, "action": action}

    def _editable_fields(self, col, note_id, fields, expected_revision):
        note = self._bounded_note(col, note_id)
        if digest(list(note.items())) != expected_revision:
            raise AnkiToolError("Note changed. Read it again before editing.")
        allowed = set(visible_field_names(list(dict(note.items()))))
        if note.note_type()["name"] in MANAGED_NOTE_TYPES:
            allowed &= {"Title"}
        if not fields or not set(fields) <= allowed:
            raise AnkiToolError("Choose existing visible fields; managed identities/provenance are protected.")
        return note

    def _update_note_html(self, col, note_id, fields, expected_revision):
        note = self._editable_fields(col, note_id, fields, expected_revision)
        for name, value in fields.items():
            note[name] = rich_html(value)
        self._stable_note_layout(col, note)
        self.check()
        self.changes = col.update_notes([note])
        return {"note_id": note_id, "content_revision": digest(list(note.items()))}

    def _get_media_references(self, col, note_ids):
        root = Path(col.media.dir())
        if root.is_symlink():
            raise AnkiToolError("Anki media directory is unsafe.")
        items = []
        for nid in dict.fromkeys(note_ids):
            note = self._bounded_note(col, nid)
            for name in media_names(note.fields):
                path = root / name
                items.append({"note_id": nid, "filename": name, "available": path.is_file() and not path.is_symlink()})
                if len(items) > 200:
                    raise AnkiToolError("Select fewer notes for media inspection.")
        return {"items": items}

    def _attach_media(self, col, note_id, field_name, path, expected_revision, mode="append"):
        note = self._editable_fields(col, note_id, {field_name: ""}, expected_revision)
        source = Path(path)
        if not source.is_absolute():
            raise AnkiToolError("Choose an absolute local media file.")
        raw = self._bounded_bytes(source, 32 * 1024 * 1024)
        extension = source.suffix.casefold()
        raster = {
            ".png": b"\x89PNG\r\n\x1a\n",
            ".jpg": b"\xff\xd8",
            ".jpeg": b"\xff\xd8",
            ".gif": b"GIF",
            ".webp": b"RIFF",
        }
        kind = (
            "image"
            if extension in raster
            else "audio"
            if extension in {".mp3", ".ogg", ".wav", ".m4a", ".flac", ".opus"}
            else "video"
            if extension in {".mp4", ".webm", ".mov", ".mkv"}
            else None
        )
        audio_video = (
            (raw.startswith(b"ID3") or (len(raw) >= 2 and raw[0] == 255 and raw[1] & 224 == 224))
            if extension == ".mp3"
            else raw.startswith(b"RIFF") and raw[8:12] == b"WAVE"
            if extension == ".wav"
            else raw.startswith(b"OggS")
            if extension in {".ogg", ".opus"}
            else raw.startswith(b"fLaC")
            if extension == ".flac"
            else raw[4:8] == b"ftyp"
            if extension in {".mp4", ".m4a", ".mov"}
            else raw.startswith(b"\x1a\x45\xdf\xa3")
            if extension in {".webm", ".mkv"}
            else False
        )
        image_valid = (
            kind == "image" and raw.startswith(raster[extension]) and (extension != ".webp" or raw[8:12] == b"WEBP")
        )
        if not kind or (not image_valid if kind == "image" else not audio_video):
            raise AnkiToolError("Choose a supported local raster image, audio or video file.")
        meta = self.history.get(self._active_change)["args"].get("_attachment")
        if meta is None:
            filename = "incremento-mcp-" + uuid.uuid4().hex + extension
            relative = "mcp_undo_files/media/" + uuid.uuid4().hex + extension
            retained = self._profile_file(relative, must_exist=False)
            retained.parent.mkdir(parents=True, exist_ok=True)

            atomic_bytes(retained, raw)
            meta = {"filename": filename, "relative": relative, "hash": hashlib.sha256(raw).hexdigest()}
            self.history.get(self._active_change)["args"]["_attachment"] = meta
            self.history.persist()
        filename = col.media.write_data(meta["filename"], raw)
        if filename != meta["filename"]:
            raise AnkiToolError("Anki changed the allocated media identity.")
        markup = f'<img src="{html.escape(filename, quote=True)}">' if kind == "image" else f"[sound:{filename}]"
        note[field_name] = (note[field_name] + "<br>" + markup) if mode == "append" else markup
        self._stable_note_layout(col, note)
        self.changes = col.update_notes([note])
        return {"note_id": note_id, "filename": filename, "media_kind": kind}

    def _preview_note_removal(self, col, note_ids, mode):
        return self._new_advanced_plan(
            col,
            "removal",
            {"note_ids": list(dict.fromkeys(note_ids)), "mode": mode},
            {"notes": len(set(note_ids)), "mode": mode, "media_preserved": True},
        )

    def _conversion_drafts(self, col, note_ids, target_note_type_id, field_map, wrap_cloze=False):
        notes = [self._bounded_note(col, nid) for nid in dict.fromkeys(note_ids)]
        if len({note.mid for note in notes}) != 1 or any(
            note.note_type()["name"] in MANAGED_NOTE_TYPES for note in notes
        ):
            raise AnkiToolError("Convert notes of one text type; managed reader identities remain protected.")
        target = col.models.get(native_id(target_note_type_id))
        if not target or target["name"] in MANAGED_NOTE_TYPES:
            raise AnkiToolError("Choose an existing normal/cloze text type.")
        source = notes[0].note_type()
        source_names = [field["name"] for field in source["flds"]]
        target_names = [field["name"] for field in target["flds"]]
        if not field_map or not set(field_map) <= set(target_names) or not set(field_map.values()) <= set(source_names):
            raise AnkiToolError("Map existing target field names to existing source field names.")
        if len(set(field_map.values())) != len(field_map):
            raise AnkiToolError("Map each source field at most once.")
        drafts = []
        projected = 0
        cloze_fields = list(col.models.cloze_fields(target["id"])) if target["type"] == 1 else []
        for old in notes:
            note = col.new_note(target)
            for key in target_names:
                source_name = field_map.get(key, key if key in source_names else None)
                note[key] = old[source_name] if source_name else ""
            if wrap_cloze and cloze_fields:
                index = cloze_fields[0]
                note.fields[index] = "{{c1::" + note.fields[index] + "}}"
            if target["type"] == 1:
                numbers = note.cloze_numbers_in_fields()
                if not numbers:
                    raise AnkiToolError(
                        "The target needs cloze markup. Explicitly choose wrap_cloze to wrap the target text."
                    )
                projected += len(numbers)
            else:
                projected += len(target["tmpls"])
            drafts.append((old, note))
        if len(encoded([dict(note.items()) for _, note in drafts])) > 3 * 1024 * 1024:
            raise AnkiToolError("The converted fields exceed the recovery budget. Select fewer notes.")
        if projected > 500:
            raise AnkiToolError("The proposed conversion exceeds 500 generated cards.")
        return source, target, drafts

    def _preview_note_type_conversion(self, col, note_ids, target_note_type_id, field_map, wrap_cloze=False):
        source, target, drafts = self._conversion_drafts(col, note_ids, target_note_type_id, field_map, wrap_cloze)
        return self._new_advanced_plan(
            col,
            "conversion",
            {
                "note_ids": list(dict.fromkeys(note_ids)),
                "target_note_type_id": target_note_type_id,
                "field_map": field_map,
                "wrap_cloze": wrap_cloze,
            },
            {
                "source_type": source["name"],
                "target_type": target["name"],
                "field_map": field_map,
                "fields_after": [{"note_id": str(old.id), "fields": dict(note.items())} for old, note in drafts[:10]],
                "preview_bounded": len(drafts) > 10,
                "sync_consequence": "Schema/type changes and their reversal can require a full AnkiWeb sync. No sync is started.",
            },
            True,
        )

    def _perform_conversion(self, col, note_ids, target_note_type_id, field_map, wrap_cloze=False):
        source, target, drafts = self._conversion_drafts(col, note_ids, target_note_type_id, field_map, wrap_cloze)
        info = col.models.change_notetype_info(old_notetype_id=source["id"], new_notetype_id=target["id"])
        request = info.input
        request.note_ids.extend(map(int, note_ids))
        old_names = [field["name"] for field in source["flds"]]
        del request.new_fields[:]
        request.new_fields.extend(
            old_names.index(field_map.get(field["name"], field["name"]))
            if field_map.get(field["name"], field["name"]) in old_names
            else -1
            for field in target["flds"]
        )
        entry = col.add_custom_undo_entry(t("mcp_undo_batch"))
        try:
            col.models.change_notetype_of_notes(request)
            if wrap_cloze:
                changed = []
                for old, draft in drafts:
                    note = col.get_note(old.id)
                    note.fields = list(draft.fields)
                    changed.append(note)
                col.update_notes(changed)
        finally:
            self.changes = col.merge_undo_entries(entry)
        return {"note_ids": note_ids, "note_type_id": target_note_type_id, "full_sync_may_be_required": True}

    def _edited_model(self, col, note_type_id, fields=None, templates=None, css=None):
        original = col.models.get(native_id(note_type_id))
        if not original or original["name"].startswith("Incremento "):
            raise AnkiToolError("Use the consent-gated native format update for managed Incremento note types.")
        model = deepcopy(original)
        if fields is not None:
            names = [value["name"].strip() for value in fields]
            sources = [value["source"] for value in fields if value.get("source")]
            existing = {value["name"]: value for value in original["flds"]}
            if (
                len(set(names)) != len(names)
                or not all(names)
                or len(set(sources)) != len(sources)
                or not set(sources) <= set(existing)
            ):
                raise AnkiToolError("Field names/sources must be unique and existing sources must match exactly.")
            model["flds"] = []
            for value in fields:
                field = (
                    deepcopy(existing[value["source"]]) if value.get("source") else col.models.new_field(value["name"])
                )
                field["name"] = value["name"]
                model["flds"].append(field)
        if templates is not None:
            if len({value["name"] for value in templates}) != len(templates) or (
                model["type"] == 1 and len(templates) != 1
            ):
                raise AnkiToolError("Template names must be unique; cloze types have one template.")
            model["tmpls"] = []
            for index, value in enumerate(templates):
                template = (
                    deepcopy(original["tmpls"][index])
                    if index < len(original["tmpls"])
                    else col.models.new_template(value["name"])
                )
                template.update(
                    name=value["name"],
                    qfmt=rich_html(value["front"], template=True),
                    afmt=rich_html(value["back"], template=True),
                )
                model["tmpls"].append(template)
        if css is not None:
            model["css"] = safe_css(css)
        return model

    def _render_type_preview(self, model, values):
        # A disposable native collection renders proposed fields/templates
        # without changing the open collection or running WebEngine/JS/hooks.
        from anki.collection import Collection

        with tempfile.TemporaryDirectory(prefix="incremento-mcp-preview-") as directory:
            preview = Collection(str(Path(directory) / "preview.anki2"))
            try:
                copy = deepcopy(model)
                copy["id"] = 0
                copy["name"] = "Incremento MCP preview"
                for field in copy["flds"]:
                    field["ord"] = None
                for template in copy["tmpls"]:
                    template["ord"] = None
                preview.models.add(copy)
                note = preview.new_note(preview.models.get(copy["id"]))
                for key, value in values.items():
                    if key in dict(note.items()):
                        note[key] = value
                if not any(note.fields):
                    note.fields[0] = "{{c1::Preview}}" if copy["type"] == 1 else "Preview"
                preview.add_note(note, 1)
                cid = preview.find_cards(f"nid:{note.id}")[0]
                rendered = preview._backend.render_existing_card(card_id=cid, browser=True, partial_render=False)
                question = "".join(node.text for node in rendered.question_nodes)
                answer = "".join(node.text for node in rendered.answer_nodes)
                return {
                    "question_html": rich_html(question[:48000]),
                    "answer_html": rich_html(answer[:48000]),
                    "css": safe_css(model.get("css", "")),
                    "scripts_executed": False,
                    "bounded": True,
                }
            finally:
                preview.close()

    def _preview_note_type_edit(self, col, note_type_id, fields=None, templates=None, css=None):
        model = self._edited_model(col, note_type_id, fields, templates, css)
        ids = col.db.list("SELECT id FROM notes WHERE mid=? ORDER BY id LIMIT 101", int(note_type_id))
        if len(ids) > 100 or len(ids) * len(model["tmpls"]) > 500:
            raise AnkiToolError("This type has too many affected notes/cards for one recovery checkpoint.")
        values = {}
        if ids:
            old = dict(self._bounded_note(col, ids[0]).items())
            values = (
                {value["name"]: old.get(value.get("source", ""), "") for value in fields} if fields is not None else old
            )
        rendered = self._render_type_preview(model, values)
        args = {"note_type_id": note_type_id, "_affected_notes": ids}
        args.update(
            {
                key: value
                for key, value in {"fields": fields, "templates": templates, "css": css}.items()
                if value is not None
            }
        )
        return self._new_advanced_plan(
            col,
            "type_edit",
            args,
            {
                "affected_notes": len(ids),
                "fields_after": [value["name"] for value in model["flds"]],
                "templates_after": [value["name"] for value in model["tmpls"]],
                "rendered_preview": rendered,
                "sync_consequence": "Field/template schema changes and their reversal can require a full AnkiWeb sync. No sync is started.",
            },
            True,
        )

    def _perform_type_edit(self, col, note_type_id, fields=None, templates=None, css=None):
        planned = self.history.get(self._active_change)["args"]["_advanced"]["arguments"]
        current = col.db.list("SELECT id FROM notes WHERE mid=? ORDER BY id LIMIT 101", int(note_type_id))
        if current != planned["_affected_notes"]:
            raise AnkiToolError("This note type gained or lost notes after preview. Generate another proposal.")
        model = self._edited_model(col, note_type_id, fields, templates, css)
        self.changes = col.models.update_dict(model)
        return {"note_type_id": note_type_id, "full_sync_may_be_required": True}

    def _perform_removal(self, col, note_ids, mode):
        if mode == "delete":
            pdf_ids = []
            for nid in note_ids:
                note = self._bounded_note(col, nid)
                if note.note_type()["name"] == "Incremento PDF":
                    pdf_ids.extend(col.find_cards(f"nid:{nid}"))
            self.changes = col.remove_notes(list(map(int, note_ids)))
            if pdf_ids:
                try:
                    from .pdf_search import reconcile_pdf_search_indexes
                except ImportError:
                    from pdf_search import reconcile_pdf_search_indexes
                reconcile_pdf_search_indexes(self.addon_dir, self.profile, col, card_ids=pdf_ids)
        else:
            ids = col.db.list(
                f"SELECT id FROM cards WHERE nid IN ({','.join('?' for _ in note_ids)})", *map(int, note_ids)
            )
            entry = col.add_custom_undo_entry(t("mcp_undo_batch"))
            try:
                col.sched.suspend_cards(ids)
                col.tags.bulk_add(list(map(int, note_ids)), "incremento::archived")
            finally:
                self.changes = col.merge_undo_entries(entry)
        return {"note_ids": note_ids, "mode": mode}

    def _preview_duplicate_merge(self, col, note_ids, survivor_note_id, fields):
        if len(set(note_ids)) < 2 or survivor_note_id not in note_ids:
            raise AnkiToolError("Choose at least two notes and an explicit survivor from that set.")
        notes = [self._bounded_note(col, nid) for nid in dict.fromkeys(note_ids)]
        if len({note.mid for note in notes}) != 1 or notes[0].note_type()["name"] in MANAGED_NOTE_TYPES:
            raise AnkiToolError("Merge notes of one text type; managed readers retain separate identities.")
        survivor = self._bounded_note(col, survivor_note_id)
        self._editable_fields(col, survivor_note_id, fields, digest(list(survivor.items())))
        for name, value in fields.items():
            survivor[name] = rich_html(value)
        self._stable_note_layout(col, survivor)
        return self._new_advanced_plan(
            col,
            "duplicate_merge",
            {"note_ids": note_ids, "survivor_note_id": survivor_note_id, "fields": fields},
            {
                "survivor_note_id": survivor_note_id,
                "removed_note_ids": [nid for nid in note_ids if nid != survivor_note_id],
                "fields_after": fields,
                "schedule_policy": "survivor unchanged; removed notes and their reviews retained for undo",
            },
        )

    def _perform_duplicate_merge(self, col, note_ids, survivor_note_id, fields):
        note = self._bounded_note(col, survivor_note_id)
        tags = []
        for nid in note_ids:
            tags.extend(self._bounded_note(col, nid).tags)
        for name, value in fields.items():
            note[name] = rich_html(value)
        note.tags = list(dict.fromkeys(tags))
        entry = col.add_custom_undo_entry(t("mcp_undo_batch"))
        try:
            col.update_notes([note])
            col.remove_notes([int(nid) for nid in note_ids if nid != survivor_note_id])
        finally:
            self.changes = col.merge_undo_entries(entry)
        return {"survivor_note_id": survivor_note_id}

    def _capture_collection(self, col, name, args):
        if name == "apply_advanced_plan":
            if "_advanced" not in args:
                args["_advanced"] = deepcopy(self._advanced_plan(args["plan_id"])["payload"])
            return self._capture_advanced_action(col, args["_advanced"])
        if name == "change_card_schedule":
            if "_schedule_notes" not in args:
                args["_schedule_notes"] = sorted(
                    {self._native_card(col, cid)["fields"]["nid"] for cid in args["card_ids"]}
                )
            return capture_notes(self, col, args, args["_schedule_notes"])
        if name == "create_deck":
            name = self._deck_name(args["name"])
            parts = name.split("::")
            return self._capture_decks(col, args, names=["::".join(parts[:i]) for i in range(1, len(parts) + 1)])
        if name == "rename_deck":
            ids = args.setdefault("_branch_ids", self._deck_branch_ids(col, [args["deck_id"]]))
            return self._capture_decks(col, args, ids)
        if name in {"update_note_html", "attach_media"}:
            fields = args["fields"] if name == "update_note_html" else {args["field_name"]: ""}
            value = self._capture_change(col, "update_note_fields", {"note_id": args["note_id"], "fields": fields})
            if name == "update_note_html":
                return value
            meta = args.get("_attachment")
            media = None
            if meta:
                filename = local_media_name(meta["filename"])
                path = Path(col.media.dir()) / filename
                refs = col.db.list(
                    "SELECT id FROM notes WHERE id!=? AND instr(flds,?)>0 LIMIT 2", int(args["note_id"]), filename
                )
                media = {
                    "filename": filename,
                    "present": path.exists(),
                    "hash": fingerprint(path) if path.exists() and not path.is_symlink() else None,
                    "other_references": refs,
                }
            return {"kind": "media_attachment", "note": value, "media": media, "retained": meta}
        return None

    def _capture_advanced_action(self, col, payload):
        operation, args = payload["operation"], payload["arguments"]
        if operation == "deck_merge":
            return self._capture_decks(col, args, [*map(int, args["source_deck_ids"]), int(args["target_deck_id"])])
        ids = args["note_ids"] if operation != "type_edit" else args["_affected_notes"]
        model_ids = (
            [int(args["target_note_type_id"])]
            if operation == "conversion"
            else [int(args["note_type_id"])]
            if operation == "type_edit"
            else []
        )
        return capture_notes(
            self, col, args, ids, model_ids=model_ids, mutable_models=model_ids if operation == "type_edit" else []
        )

    def _comparable_state(self, state):
        if state["kind"] == "native_notes":
            return semantic_state(state)
        if state["kind"] == "native_decks":
            return {
                "kind": state["kind"],
                "decks": [{**value, "definition": canonical(value["definition"])} for value in state["decks"]],
                "notes": semantic_state(state["notes"]),
            }
        if state["kind"] == "batch":
            return {**state, "steps": [self._comparable_state(value) for value in state["steps"]]}
        return state

    def _restore_collection(self, col, target):
        if target["kind"] == "native_notes":
            restore_notes(self, col, target)
        elif target["kind"] == "native_decks":
            current = self._creation_restore_current
            desired = {item["definition"]["id"]: item["definition"] for item in target["decks"]}
            live = {item["definition"]["id"]: item["definition"] for item in current["decks"]}
            for deck in desired.values():
                collision = col.decks.by_name(deck["name"])
                if collision and collision["id"] != deck["id"]:
                    raise AnkiToolError("A different deck now owns the restored name.")
            for deck in sorted(desired.values(), key=lambda item: item["name"].count("::")):
                col.decks.update(deepcopy(deck), preserve_usn=True)
            if encoded(semantic_state(target["notes"])) != encoded(semantic_state(current["notes"])):
                self._creation_restore_current = current["notes"]
                try:
                    restore_notes(self, col, target["notes"])
                finally:
                    self._creation_restore_current = current
            for did in sorted(set(live) - set(desired), key=lambda did: live[did]["name"].count("::"), reverse=True):
                if did == 1 or col.db.scalar("SELECT count(*) FROM cards WHERE did=? OR odid=?", did, did):
                    raise AnkiToolError("The created deck now contains other cards.")
                col.decks.remove([did])
            from anki.collection import OpChanges

            self.changes = OpChanges(deck=True, card=True, note=True)
        elif target["kind"] == "media_attachment":
            current = self._creation_restore_current
            meta = current["retained"] or target["retained"]
            if meta:
                filename = local_media_name(meta["filename"])
                retained = self._profile_file(meta["relative"])
                if not meta["relative"].startswith("mcp_undo_files/media/") or fingerprint(retained) != meta["hash"]:
                    raise AnkiToolError("Retained media changed or is unavailable.")
                if target["media"] and target["media"]["present"]:
                    result = col.media.write_data(filename, self._bounded_bytes(retained, 32 * 1024 * 1024))
                    if result != filename:
                        raise AnkiToolError("The media identity is now in use.")
                else:
                    others = col.db.list(
                        "SELECT id FROM notes WHERE id!=? AND instr(flds,?)>0 LIMIT 1",
                        int(target["note"]["note_id"]),
                        filename,
                    )
                    if others:
                        raise AnkiToolError("Another note now references this media. Restore that change first.")
                    col.media.trash_files([filename])
            self._restore_change(col, target["note"])
        else:
            return False
        return True

    def _validate_collection_restore(self, col, before, current):
        if before["kind"] == "native_notes":
            validate_notes_restore(self, col, before, current)
        elif before["kind"] == "native_decks":
            if before["notes"]["note_ids"] != current["notes"]["note_ids"]:
                raise AnkiToolError("Deck recovery note ownership changed.")
            if not {item["definition"]["id"] for item in before["decks"]} <= set(current["scope_ids"]):
                raise AnkiToolError("Deck recovery scope changed.")
        elif before["kind"] == "media_attachment":
            self._validate_restore(before["note"], current["note"])
