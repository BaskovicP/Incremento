"""Explicit source, planning and file workflows for the local MCP service.

The assistant supplies classification and draft text. This module uses existing
Incremento/Anki repositories; it never invokes another AI or installs a runtime.
"""
from copy import deepcopy
import hashlib
import json
import os
import posixpath
import stat
from pathlib import Path, PurePosixPath
import re
import uuid
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile
from urllib.parse import unquote, urlsplit

try:
    from . import db, paths
    from .mcp_anki import CARD_WRITES
    from .mcp_operations import McpOperations
    from .i18n import t
    from .mcp_undo import restore_sqlite, atomic_bytes
except ImportError:
    import db
    import paths
    from mcp_anki import CARD_WRITES
    from mcp_operations import McpOperations
    from i18n import t
    from mcp_undo import restore_sqlite, atomic_bytes


class WorkflowError(ValueError):
    pass


BATCH_TOOLS = ("create_list", "rename_list", "delete_list", "update_list_members", "update_tags",
               "update_note_fields", "set_priorities", "update_book_details", "add_bookmark",
               "update_bookmark_comment", "delete_bookmark", "update_highlight", "delete_highlight",
               "update_knowledge_tree", "set_daily_goals", "set_custom_schedule", "clear_custom_schedule",
               "update_writing", "update_resource_links", *sorted(CARD_WRITES), "update_ocr_text")
CREATION_TOOLS = frozenset({"create_source_cards", "import_documents", "create_cards", "clone_cards"})
COLLECTION_TOOLS = frozenset({"apply_plan", *CREATION_TOOLS})


def workflow_tools(tool, identity, ids, text, revision, cursor, limit):
    item = {"type": "object", "additionalProperties": False, "required": ["tool", "arguments"], "properties": {
        "tool": {"type": "string", "enum": list(BATCH_TOOLS)},
        "arguments": {"type": "object", "additionalProperties": {}}}}
    resource = {"type": "object", "additionalProperties": False, "required": ["kind", "card_id"], "properties": {
        "kind": {"type": "string", "enum": ["pdf", "video", "audio"]}, "card_id": identity,
        "page": {"type": "integer", "minimum": 1, "maximum": 100000},
        "start": {"type": "number", "minimum": 0, "maximum": 100000000},
        "end": {"type": "number", "minimum": 0, "maximum": 100000000}, "label": {"type": "string", "maxLength": 240}}}
    draft = {"type": "object", "additionalProperties": False, "required": ["front", "back", "source_card_id"], "properties": {
        "front": {"type": "string", "minLength": 1, "maxLength": 4000},
        "back": {"type": "string", "minLength": 1, "maxLength": 8000}, "source_card_id": identity,
        "seconds": {"type": "number", "minimum": 0, "maximum": 100000000},
        "position": {"type": "integer", "minimum": 1, "maximum": 100000}, "quote": {"type": "string", "maxLength": 4000}}}
    imported = {"type": "object", "additionalProperties": False, "required": ["kind"], "properties": {
        "kind": {"type": "string", "enum": ["pdf", "epub", "web"]},
        "path": {"type": "string", "maxLength": 2000}, "url": text, "title": {"type": "string", "maxLength": 500}}}
    return [
        tool("read_source", "Read bounded writing/Markdown, saved webpage/EPUB, or local subtitle text with "
             "revisions; PDF/EPUB positions are one-based. Never downloads missing transcripts or follows webpage links.",
             {"card_id": identity, "position": {"type": "integer", "minimum": 1, "maximum": 100000},
              "cursor": cursor, "max_chars": {"type": "integer", "minimum": 1, "maximum": 16000}}, ["card_id"]),
        tool("search_sources", "Search saved source text, including writing and local video/audio transcripts. "
             "Follow cursors even for empty pages. Bounded scan; unavailable or oversized sources prevent complete coverage claims.",
             {"query": text, "cursor": cursor, "limit": limit}, ["query"]),
        tool("update_writing", "Replace a managed writing document's Markdown using a fresh read_source revision. "
             "Preserve the entire old text for durable undo. Refuses while its native editor is open.",
             {"card_id": identity, "text": {"type": "string", "maxLength": 48000}, "expected_revision": revision},
             ["card_id", "text", "expected_revision"], write=True, destructive=True),
        tool("preview_changes", "Validate and save a concrete batch proposal without changing library data. "
             "Call get_plan to inspect all proposed actions, then apply_plan. update_list_members.list_id may refer to "
             "$0.list_id from a preceding create_list action (zero-based index). No nested plans or imports.",
             {"actions": {"type": "array", "minItems": 1, "maxItems": 50, "items": item}}, ["actions"]),
        tool("get_plan", "Read the saved actions and affected data for a proposed batch. Does not apply it.",
             {"plan_id": {"type": "string", "minLength": 32, "maxLength": 32}}, ["plan_id"]),
        tool("apply_plan", "Apply exactly a saved preview after verifying all affected state is unchanged. "
             "All steps share one durable undo reference. Failure compensates already-completed steps.",
             {"plan_id": {"type": "string", "minLength": 32, "maxLength": 32}}, ["plan_id"], write=True, destructive=True),
        tool("list_tags", "Page through Anki's registered tags and suggest spelling/separator variants for review. "
             "Suggestions do not establish that tags mean the same thing.", {"cursor": cursor, "limit": limit}),
        tool("preview_tag_changes", "Propose literal tag renames/merges on exact notes. Does not change notes; "
             "use apply_plan after reviewing. Subtags are preserved unless explicitly mapped.",
             {"note_ids": ids, "mappings": {"type": "array", "minItems": 1, "maxItems": 20, "items": {
                 "type": "object", "additionalProperties": False, "required": ["from", "to"],
                 "properties": {"from": {"type": "string", "maxLength": 100}, "to": {"type": "string", "maxLength": 100}}}}},
             ["note_ids", "mappings"]),
        tool("get_resource_links", "Read direct document and recording associations for a live card.", {"card_id": identity}, ["card_id"]),
        tool("update_resource_links", "Add links to imported PDF pages or local video/audio segments, or remove "
             "exact direct link IDs. Uses a fresh link revision and preserves source files and citations.",
             {"card_id": identity, "expected_revision": revision,
              "add": {"type": "array", "maxItems": 32, "items": resource},
              "remove": {"type": "array", "maxItems": 32, "items": {"type": "string", "maxLength": 64}}},
             ["card_id", "expected_revision"], write=True, destructive=True),
        tool("preview_session", "Run Incremento's real read-only selection using the saved scheduler settings "
             "and optional search/count overrides. Explain selected cards; never builds a filtered deck or changes schedules.",
             {"count": {"type": "integer", "minimum": 1, "maximum": 100}, "anki_query": text}),
        tool("create_source_cards", "Create up to 20 Q/A notes from supplied source-backed drafts, with dedicated "
             "provenance and source positions. Uses the existing target deck; creates the dedicated Q/A type only if absent. "
             "Undo/redo preserves note/card identities using Anki's native package API and refuses reviewed/edited cards.",
             {"cards": {"type": "array", "minItems": 1, "maxItems": 20, "items": draft},
              "deck_name": {"type": "string", "maxLength": 200}, "tags": {"type": "array", "maxItems": 64,
                 "items": {"type": "string", "minLength": 1, "maxLength": 100}}}, ["cards"], write=True),
        tool("import_documents", "Import up to 5 local PDFs/EPUBs or public webpages into managed profile copies "
             "with provenance, optional list/tags and durable undo. Original files are read-only. Web content uses the "
             "existing guarded fetcher and a local EPUB study copy. No downloads/installations of dependencies.",
             {"documents": {"type": "array", "minItems": 1, "maxItems": 5, "items": imported},
              "deck_name": {"type": "string", "maxLength": 200}, "list_id": identity,
              "tags": {"type": "array", "maxItems": 64, "items": {"type": "string", "minLength": 1, "maxLength": 100}}},
             ["documents"], write=True),
        tool("recover_change", "Inspect a write-ahead record left by an interrupted operation. Confirm its current "
             "state_revision to retain that exact state as the undo conflict guard; this does not alter library data.",
             {"undo_id": {"type": "string", "maxLength": 32}, "state_revision": revision}, ["undo_id"]),
    ]


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def state_preview(value):
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, list):
        return [state_preview(item) for item in value[:20]]
    if isinstance(value, dict):
        return {key: state_preview(item) for key, item in value.items()}
    return value


class McpWorkflows(McpOperations):
    def _profile_file(self, relpath, *, must_exist=True):
        raw = str(relpath).replace("\\", "/")
        relative = PurePosixPath(raw)
        if relative.is_absolute() or not raw or any(part in ("", ".", "..") for part in relative.parts):
            raise WorkflowError("Invalid managed source path.")
        root = paths.get_user_files_dir(self.addon_dir, self.profile)
        candidate = root.joinpath(*relative.parts)
        if any(part.is_symlink() for part in (root.parent, root, *candidate.parents, candidate)):
            raise WorkflowError("Source paths cannot contain symlinks.")
        if must_exist and not candidate.is_file():
            raise WorkflowError("The managed source is unavailable.")
        return candidate

    def _bounded_bytes(self, path, limit=2*1024*1024):
        if path.is_symlink():
            raise WorkflowError("Source unavailable or over the MCP size budget.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
                raise WorkflowError("Source unavailable or over the MCP size budget.")
            value = stream.read(limit+1)
        if len(value)>limit:
            raise WorkflowError("Source exceeds its MCP size budget.")
        return value

    def _writing_file(self, col, card_id):
        item = self._card(col, card_id)
        if item["note_type"] != "Incremento Writing":
            raise WorkflowError("This is not a writing document.")
        relative = item["fields"].get("Markdown_File", "")
        if not relative.startswith("writing/"):
            raise WorkflowError("Writing files must stay in this profile's writing directory.")
        return relative, self._profile_file(relative)

    @staticmethod
    def _epub_sections(archive):
        infos = archive.infolist()
        if len(infos)>2000 or sum(info.file_size for info in infos)>48*1024*1024:
            raise WorkflowError("EPUB exceeds the source reading budget.")
        if archive.getinfo("META-INF/container.xml").file_size>1024*1024:
            raise WorkflowError("EPUB metadata exceeds the reading budget.")
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        package_name = next(node.attrib["full-path"] for node in container.iter() if node.tag.endswith("rootfile"))
        if archive.getinfo(package_name).file_size>1024*1024:
            raise WorkflowError("EPUB package metadata exceeds the reading budget.")
        package = ET.fromstring(archive.read(package_name))
        manifest = {node.attrib["id"]: node.attrib.get("href", "") for node in package.iter()
                    if node.tag.endswith("}item") and "id" in node.attrib}
        names = []
        for node in package.iter():
            if not node.tag.endswith("itemref"):
                continue
            target = urlsplit(manifest[node.attrib["idref"]])
            if target.scheme or target.netloc:
                raise WorkflowError("Remote EPUB sections are unavailable to offline source reads.")
            name = posixpath.normpath(posixpath.join(posixpath.dirname(package_name), unquote(target.path)))
            if name.startswith(("/", "../")) or name == "..":
                raise WorkflowError("Invalid EPUB section path.")
            names.append(name)
        return names

    def _source_text(self, col, card_id, position=1):
        item = self._card(col, card_id)
        fields, kind = item["fields"], item["kind"]
        if item["note_type"] == "Incremento Writing":
            _, path = self._writing_file(col, card_id)
            raw = self._bounded_bytes(path)
            return raw.decode("utf-8"), "writing", digest(raw)
        if kind == "epub":
            path = self._document_path(item)
            with ZipFile(path) as archive:
                sections = self._epub_sections(archive)
                if not 1 <= position <= len(sections):
                    raise WorkflowError("EPUB section is out of range.")
                name = sections[position-1]
                info = archive.getinfo(name)
                if info.file_size>2*1024*1024:
                    raise WorkflowError("EPUB section is too large.")
                raw = archive.read(name)
                # Offline text only; no extraction, resources, script or network execution.
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw, "html.parser")
                for node in soup(["script", "style", "iframe", "svg"]):
                    node.decompose()
                text = soup.get_text(" ", strip=True)
                return text, "epub", digest(raw)
        if kind == "pdf":
            conn = db.get_connection(self.addon_dir, self.profile)
            path = self._document_path(item)
            self._check_index_signature(conn, int(card_id), kind, path)
            row = conn.execute("SELECT substr(text,1,1000000) FROM pdf_text_index WHERE card_id=? AND page=?",
                               (int(card_id), position)).fetchone()
            if row is not None:
                return row[0], kind, digest(row[0])
            if path.stat().st_size>128*1024*1024:
                raise WorkflowError("PDF exceeds the extraction budget; index it first.")
            try:
                import fitz
            except ImportError:
                raise WorkflowError("PDF text is unavailable. Run the native PDF indexer; no dependency is installed automatically.") from None
            with fitz.open(path) as document:
                if not 1 <= position <= len(document):
                    raise WorkflowError("PDF page is out of range.")
                text = document[position-1].get_text()[:1000000]
            return text, kind, digest(text)
        tracks = self._transcript_paths(col, item)
        if tracks:
            if not 1<=position<=len(tracks):
                raise WorkflowError("Saved subtitle track position is out of range.")
            raw = self._bounded_bytes(tracks[position-1])
            return raw.decode("utf-8-sig", errors="replace"), "transcript", digest(raw)
        for key in ("Markdown", "Content", "Text", "HTML", "Notes"):
            if fields.get(key) and item["note_type"] in {"Incremento Web", "Incremento Audio"}:
                return fields[key], "audio_notes" if item["note_type"] == "Incremento Audio" else "saved_web", digest(fields[key])
        raise WorkflowError("No saved text is available. Import the webpage or local subtitles first; this tool does not fetch them.")

    def _transcript_paths(self, col, item):
        result = []
        fields = item["fields"]
        for key in ("Target_Subtitle_File", "Reference_Subtitle_File", "Subtitle_File", "Transcript_File"):
            if fields.get(key):
                relative = fields[key]
                if not relative.startswith("videos/"):
                    relative = "videos/"+relative
                path = self._profile_file(relative, must_exist=False)
                if path.is_file() and path not in result:
                    result.append(path)
        # Local audio sidecars are exact siblings of its canonical Anki media
        # filename, never caller-supplied arbitrary media paths.
        filename = fields.get("Audio_Filename", "")
        if item["note_type"] == "Incremento Audio" and filename and Path(filename).name == filename and not any(c in filename for c in ("/", "\\", "\0")):
            root = Path(col.media.dir())
            if not root.is_symlink():
                for suffix in (".srt", ".vtt"):
                    path = root/Path(filename).with_suffix(suffix)
                    if path.is_file() and not path.is_symlink():
                        result.append(path)
        return result

    def _source_positions(self, col, card_id):
        item = self._card(col, card_id)
        if item["kind"] == "epub":
            with ZipFile(self._document_path(item)) as archive:
                return len(self._epub_sections(archive))
        if item["kind"] == "pdf":
            row = db.get_connection(self.addon_dir, self.profile).execute(
                "SELECT max(page) FROM pdf_text_index WHERE card_id=?", (int(card_id),)).fetchone()
            try:
                import fitz
            except ImportError:
                return min(100000,int(row[0])) if row and row[0] else 1
            path = self._document_path(item)
            if path.stat().st_size>128*1024*1024:
                raise WorkflowError("PDF exceeds its extraction budget.")
            with fitz.open(path) as document:
                return min(100000, len(document))
        return max(1, len(self._transcript_paths(col, item)))

    def _read_source(self, col, card_id, position=1, cursor=None, max_chars=12000):
        try:
            text, kind, revision = self._source_text(col, card_id, position)
        except (BadZipFile, ET.ParseError, StopIteration):
            raise WorkflowError("This saved source is malformed or unavailable. Check it in the native reader.") from None
        label = "source:"+card_id+":"+str(position)+":"+revision
        offset = self._cursor(label, cursor) or 0
        if type(offset) is not int or offset<0 or offset>len(text):
            raise WorkflowError("Invalid source cursor.")
        return {"card_id": card_id, "title": self._card(col, card_id)["title"], "kind": kind, "position": position, "revision": revision,
                "text": text[offset:offset+max_chars], "source_chars": len(text),
                "next_cursor": self._cursor(label, state=offset+max_chars) if offset+max_chars<len(text) else None,
                "next_position": position+1 if position<self._source_positions(col, card_id) else None,
                "coverage": "requested_position_only"}

    def _search_sources(self, col, query, cursor=None, limit=20):
        after = self._cursor("sources:"+query, cursor) or [0, 1]
        if (not isinstance(after, list) or len(after)!=2 or any(type(value) is not int for value in after)
                or after[0]<0 or not 1<=after[1]<=100000):
            raise WorkflowError("Invalid search cursor.")
        rows = col.db.all("SELECT id FROM cards WHERE id>=? ORDER BY id LIMIT 21", after[0])
        items, next_state, unavailable, scanned = [], None, 0, 0
        terms = query.casefold().split()
        for index, row in enumerate(rows):
            self.check()
            cid = row[0]
            position = after[1] if cid == after[0] else 1
            try:
                count = self._source_positions(col, str(cid))
                while position<=count:
                    if scanned>=20 or len(items)>=limit:
                        next_state = [cid, position]
                        break
                    scanned += 1
                    text, kind, revision = self._source_text(col, str(cid), position)
                    if all(term in text.casefold() for term in terms):
                        offset = text.casefold().find(terms[0]) if terms else 0
                        items.append({"card_id": str(cid), "title": self._card(col, str(cid))["title"], "kind": kind, "position": position,
                            "revision": revision, "text": text[max(0,offset-150):offset+650]})
                    position += 1
            except (ValueError, OSError, KeyError, RuntimeError, BadZipFile, ET.ParseError, StopIteration):
                unavailable += 1
                scanned += 1
            if next_state is not None:
                break
            if (scanned>=20 or len(items)>=limit) and index+1<len(rows):
                next_state = [rows[index+1][0], 1]
                break
        return {"items": items, "next_cursor": self._cursor("sources:"+query, state=next_state) if next_state is not None else None,
                "coverage": "bounded_saved_sources", "unavailable_in_scan": unavailable, "scanned": scanned,
                "max_pdf_chars_per_page": 1000000}

    def _update_writing(self, col, card_id, text, expected_revision):
        if int(card_id) in self.config.get("_mcp_open_writing_card_ids", []):
            raise WorkflowError("Close this document's native writing editor before applying an MCP edit.")
        relative, path = self._writing_file(col, card_id)
        if digest(self._bounded_bytes(path)) != expected_revision:
            raise WorkflowError("Writing content changed. Read it again before editing.")
        self.check()
        atomic_bytes(path, text.encode("utf-8"))
        return {"card_id": card_id, "revision": digest(text.encode()), "source": relative}

    def _plan_steps(self, actions):
        try:
            from .mcp_service import tool_arguments
        except ImportError:
            from mcp_service import tool_arguments
        if not isinstance(actions, list) or not 1 <= len(actions) <= 50:
            raise WorkflowError("Choose one to 50 explicit batch actions.")
        result = []
        for index, action in enumerate(actions):
            if action["tool"] not in BATCH_TOOLS or "context_id" in action["arguments"] or "request_id" in action["arguments"]:
                raise WorkflowError("Unsupported batch action.")
            args = deepcopy(action["arguments"])
            reference = args.get("list_id")
            if isinstance(reference, str) and reference.startswith("$"):
                match = re.fullmatch(r"\$(\d+)\.list_id", reference)
                if (action["tool"] != "update_list_members" or not match or int(match[1])>=index
                        or result[int(match[1])]["tool"] != "create_list"):
                    raise WorkflowError("Only update_list_members may reference a preceding create_list action.")
                args["list_id"] = "1"
            tool_arguments(action["tool"], {"context_id": self.context_id, **args}, self.context_id)
            result.append({"tool": action["tool"], "arguments": deepcopy(action["arguments"])})
        return result

    def _batch_state(self, col, steps):
        snapshots, size = [], 0
        for step in steps:
            args = deepcopy(step["arguments"])
            if str(args.get("list_id", "")).startswith("$"):
                args["list_id"] = "1"
            snapshot = self._capture_change(col, step["tool"], args)
            size += len(json.dumps(snapshot, ensure_ascii=False).encode())
            if size>4*1024*1024:
                raise WorkflowError("This batch exceeds the reversal budget. Preview smaller batches.")
            snapshots.append(snapshot)
        return {"kind": "batch", "steps": snapshots}

    def _preview_changes(self, col, actions):
        for identifier, plan in list(self.history.plans.items()):
            if len(self.history.plans)<100:
                break
            if plan["used"]:
                del self.history.plans[identifier]
        if len(self.history.plans)>=100:
            raise WorkflowError("The saved draft-plan budget is full. Reuse or apply an existing proposal first.")
        steps = self._plan_steps(actions)
        before = self._batch_state(col, steps)
        self.history.check_capacity(before)
        identifier = uuid.uuid4().hex
        self.history.plans[identifier] = {"steps": steps, "before": before, "used": False}
        self.history.persist()
        return {"plan_id": identifier, "actions": steps, "data_changed": False, "undo_steps_after_apply": 1}

    def _get_plan(self, col, plan_id):
        plan = self._plan(plan_id)
        if plan.get('kind')=='advanced':
            return {**plan['details'],'arguments':state_preview({key:value for key,value in plan['payload']['arguments'].items() if not key.startswith('_')}),
                    'affected_before_preview':state_preview(plan['before']),'applied':plan['used']}
        return {"plan_id": plan_id, "actions": plan["steps"], "affected_before_preview": state_preview(plan["before"]),
                "affected_state_revision": digest(plan["before"]), "preview_bounded": True, "applied": plan["used"]}

    def _plan(self, identifier):
        plan = self.history.plans.get(identifier)
        if not isinstance(plan, dict):
            raise WorkflowError("Unknown plan reference.")
        return plan

    def _apply_plan(self, col, plan_id):
        plan = self._plan(plan_id)
        if plan["used"] or digest(self._batch_state(col, plan["steps"])) != digest(plan["before"]):
            raise WorkflowError("Plan data changed or this plan was already applied. Generate a new preview.")
        steps = self._plan_steps(plan["steps"])
        record = self.history.get(self._active_change)
        record["args"]["steps"] = steps
        self.history.persist()
        results = []
        native = any(step["tool"] in {"update_tags", "update_note_fields", "update_ocr_text", *CARD_WRITES} for step in steps)
        entry = col.add_custom_undo_entry(t("mcp_undo_batch")) if native else None
        try:
            for step in steps:
                self.check()
                args = step["arguments"]
                if str(args.get("list_id", "")).startswith("$"):
                    args["list_id"] = results[int(args["list_id"][1:].split(".")[0])]["list_id"]
                # Whole-plan before-state has already been verified. Refresh only
                # revision guards that earlier steps in this approved plan changed.
                name = step["tool"]
                if name == "update_tags":
                    values = self._read_notes(col, args["note_ids"])["items"]
                    args["expected_revisions"] = {item["note_id"]: item["revision"] for item in values}
                elif name == "update_note_fields":
                    args["expected_revision"] = self._read_notes(col, [args["note_id"]])["items"][0]["content_revision"]
                elif name == "update_book_details":
                    args["expected_revision"] = self._get_book_details(col, args["card_id"])["revision"]
                elif name in CARD_WRITES:
                    args["expected_revisions"] = {item["card_id"]: item["revision"] for item in self._get_cards(col,args["card_ids"])["items"]}
                elif name == "update_ocr_text":
                    args["expected_revision"] = self._read_ocr(col,args["note_id"])["revision"]
                elif name == "update_knowledge_tree":
                    args["expected_revision"] = self._get_knowledge_tree(col)["revision"]
                elif name in {"set_custom_schedule", "clear_custom_schedule"}:
                    rule = db.get_custom_schedule_rule(self.addon_dir, self.profile, int(args["card_id"]))
                    args["expected_revision"] = (rule or {}).get("revision", 0)
                self.history.persist()
                results.append(getattr(self, "_"+name)(col, **args))
        except Exception:
            active = self.alive
            try:
                self.alive = lambda: True  # Compensate the captured old profile even after cancellation.
                self._restore_workflow(col, plan["before"])
            finally:
                self.alive = active
            raise
        finally:
            if entry is not None:
                self.changes = col.merge_undo_entries(entry)
        plan["used"] = True
        self.history.persist()
        return {"plan_id": plan_id, "results": results, "completed": True}

    def _list_tags(self, col, cursor=None, limit=100):
        after = self._cursor("tags", cursor) or ""
        if not isinstance(after, str):
            raise WorkflowError("Invalid tag cursor.")
        rows = col.db.all("SELECT tag FROM tags WHERE tag>? ORDER BY tag LIMIT ?", after, limit+1)
        items = [{"tag": row[0], "comparison_key": re.sub(r"[-_]+", "-", row[0].casefold())} for row in rows[:limit]]
        return {"items": items, "next_cursor": self._cursor("tags", state=rows[limit-1][0]) if len(rows)>limit else None}

    def _preview_tag_changes(self, col, note_ids, mappings):
        try:
            from .mcp_service import _revision
        except ImportError:
            from mcp_service import _revision
        mapping = {}
        for item in mappings:
            if any(not item[key] or re.search(r"[\s\x00-\x1f\x7f*?]", item[key]) for key in ("from", "to")):
                raise WorkflowError("Use literal non-empty tags.")
            if item["from"].casefold() in mapping:
                raise WorkflowError("Each source tag may have only one target.")
            mapping[item["from"].casefold()] = item["to"]
        actions = []
        for nid in dict.fromkeys(note_ids):
            note = col.get_note(int(nid))
            removed = [tag for tag in note.tags if tag.casefold() in mapping and mapping[tag.casefold()].casefold()!=tag.casefold()]
            if removed:
                actions.append({"tool": "update_tags", "arguments": {"note_ids": [nid], "remove": removed,
                    "add": list(dict.fromkeys(mapping[tag.casefold()] for tag in removed)), "expected_revisions": {nid: _revision(note.tags)}}})
        if not actions:
            return {"plan_id": None, "actions": [], "data_changed": False}
        # 100 notes may be split into independent previews to retain per-call budgets.
        if len(actions)>50:
            raise WorkflowError("Select at most 50 affected notes for each tag-cleanup plan.")
        return self._preview_changes(col, actions)

    def _get_resource_links(self, col, card_id):
        try:
            from .document_links import list_document_links
            from .recording_links import list_recording_links
        except ImportError:
            from document_links import list_document_links
            from recording_links import list_recording_links
        self._card(col, card_id)
        documents = list_document_links(self.addon_dir, self.profile, int(card_id))
        recordings = list_recording_links(self.addon_dir, self.profile, source={"kind": "card", "card_id": int(card_id)})
        items = [{**row, "link_id": "pdf:"+str(row["id"])} for row in documents if row["source_kind"] == "card"]
        items += [{**row, "link_id": "recording:"+str(row["id"])} for row in recordings]
        return {"items": items, "revision": digest(items)}

    def _update_resource_links(self, col, card_id, expected_revision, add=None, remove=None):
        try:
            from .card_resource_links import save_card_resource_links
        except ImportError:
            from card_resource_links import save_card_resource_links
        before = self._get_resource_links(col, card_id)
        if before["revision"] != expected_revision:
            raise WorkflowError("Resource links changed. Read them again.")
        if not add and not remove:
            raise WorkflowError("Supply resource links to add or remove.")
        known = {item["link_id"] for item in before["items"]}
        if not set(remove or []) <= known:
            raise WorkflowError("A selected direct link no longer exists.")
        selection = [{**row, "card_id": int(row["card_id"])} for row in add or []]
        if selection:
            save_card_resource_links(self.addon_dir, self.profile, col, int(card_id), selection,
                                     is_cancelled=lambda: not self.alive())
        conn = db.get_connection(self.addon_dir, self.profile)
        with conn:
            for identifier in remove or []:
                kind, row_id = identifier.split(":", 1)
                table = "document_links" if kind == "pdf" else "recording_links"
                conn.execute(f"DELETE FROM {table} WHERE id=? AND source_card_id=? AND source_kind='card'", (int(row_id), int(card_id)))
        return self._get_resource_links(col, card_id)

    def _preview_session(self, col, count=None, anki_query=""):
        try:
            from .scheduler_config import _config_from_dialog_dict, configured_day_end_time
            from .session_selection import select_session_cards
            from .topic_scheduler import resolve_topic_card_classifier
        except ImportError:
            from scheduler_config import _config_from_dialog_dict, configured_day_end_time
            from session_selection import select_session_cards
            from topic_scheduler import resolve_topic_card_classifier
        cfg = _config_from_dialog_dict(self.config.get("dialog", {}))
        saved_count = cfg.session_card_count
        count = count if count is not None else min(saved_count, 100)
        cfg.session_card_count = count
        cfg.day_end_time = configured_day_end_time(self.config)
        cfg.priority_lower_is_more_important = bool(self.config.get("priority_lower_is_more_important", True))
        if anki_query:
            cfg.topics_filter = f"({cfg.topics_filter}) ({anki_query})" if cfg.topics_filter else anki_query
            cfg.items_filter = f"({cfg.items_filter}) ({anki_query})" if cfg.items_filter else anki_query
        result = select_session_cards(cfg, self.addon_dir, col=col, profile=self.profile,
                                      topic_classifier=resolve_topic_card_classifier(self.config))
        cards = [{"card_id": str(cid), "title": self._card(col, str(cid))["title"],
                  "selection": result.picked_meta.get(cid, {}), "reason": "Selected by the current Incremento scheduler and supplied search filter"}
                 for cid in result.selected_ids]
        return {"items": cards, "requested": count, "saved_count": saved_count, "selected": len(cards), "schedules_changed": False,
                "filtered_deck_created": False, "coverage": "scheduler_preview_at_request_time"}

    def _capture_workflow(self, col, name, args):
        library=self._capture_library(col,name,args)
        if library is not None:
            return library
        extended=self._capture_collection(col,name,args)
        if extended is not None:
            return extended
        native = self._capture_anki(col, name, args)
        if native is not None:
            return native
        if name == "update_writing":
            relative, path = self._writing_file(col, args["card_id"])
            raw = self._bounded_bytes(path)
            return {"kind": "writing", "card_id": args["card_id"], "relative": relative, "text": raw.decode("utf-8")}
        if name == "apply_plan":
            return self._batch_state(col, args["steps"] if "steps" in args else self._plan(args["plan_id"])["steps"])
        if name in CREATION_TOOLS:
            return self._capture_created(col, args)
        return None

    def _restore_workflow(self, col, state):
        if self._restore_library(col,state):
            return True
        if self._restore_collection(col,state):
            return True
        if self._restore_anki(col, state):
            return True
        if state["kind"] == "writing":
            relative, path = self._writing_file(col, state["card_id"])
            if relative != state["relative"]:
                raise WorkflowError("Writing identity changed.")
            if self._bounded_bytes(path).decode("utf-8") == state["text"]:
                return True
            if int(state["card_id"]) in self.config.get("_mcp_open_writing_card_ids", []):
                raise WorkflowError("Writing identity changed or its native editor is open.")
            atomic_bytes(path, state["text"].encode("utf-8"))
        elif state["kind"] == "batch":
            sqlite = [step for step in state["steps"] if step["kind"] == "sqlite"]
            if sqlite:
                restore_sqlite(db.get_connection(self.addon_dir, self.profile), sqlite, self.check)
            steps = state["steps"] if getattr(self, "_restore_forward", False) else reversed(state["steps"])
            for step in steps:
                if step["kind"] != "sqlite":
                    self._restore_change(col, step)
        elif state["kind"] == "created":
            self._restore_created(col, state)
        else:
            return False
        return True

    def _recover_change(self, col, undo_id, state_revision=None):
        record = self.history.get(undo_id)
        if not record.get("pending"):
            raise WorkflowError("This change is already finalized.")
        current = self._capture_change(col, record["action"], record["args"])
        revision = digest(current)
        if state_revision is None:
            return {"undo_id": undo_id, "state_revision": revision, "action": record["action"],
                    "affected_before_preview": state_preview(record["before"]),
                    "affected_current_preview": state_preview(current), "preview_bounded": True,
                    "instructions": "Inspect the affected data (previews are bounded); repeat with state_revision only after reviewing the current state as the undo guard. Intervening edits must not be silently overwritten."}
        if state_revision != revision:
            raise WorkflowError("Affected data changed during recovery. Inspect it again.")
        request = record.get("request")
        def finish_request(reply):
            if request:
                self.history.requests[request[0]] = {"fingerprint": request[1], "reply": reply}
            self.history.persist()
            return reply
        if "desired" in record and digest(current) == digest(record["before"]):
            # The interrupted reversal did not commit: retain the original undo.
            record.update(before=record.pop("desired"), after=current, pending=False, redo=not record["redo"])
            return finish_request({"undo_id": undo_id, "recovered": True, "reversal_committed": False})
        if "desired" in record:
            # The previous reference has been used by a committed or partial
            # reversal. Retain its inverse under a new single-use reference.
            del self.history.records[undo_id]
            inverse = self.history.add(record["action"], record["args"], record["before"], current,
                collection=record["collection"], redo=record["redo"], persist=False)
            return finish_request({"undo_id": inverse, "recovered": True, "consumed": undo_id})
        return self.history.complete(undo_id, current,
            {"recovered": True, "data_changed": digest(record["before"]) != digest(current)}, request=request)
