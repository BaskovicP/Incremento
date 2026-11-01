"""Offline OCR, semantic retrieval, smart lists and bounded library audits."""

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

try:
    from . import db, paths
    from .mcp_collection import McpCollection, local_media_name, media_names, ADVANCED_OPERATIONS
    from .mcp_anki import AnkiToolError, MANAGED_NOTE_TYPES, digest, plain, native_id
    from .mcp_undo import encoded, restore_sqlite, atomic_bytes
    from .mcp_creation import fingerprint
    from .mcp_semantic import build_model, rank, tokens
    from .note_metadata import INCREMENTO_OCR_TEXT_FIELD, visible_field_names
    from .mcp_ocr import image_dimensions
except ImportError:
    import db
    import paths
    from mcp_collection import McpCollection, local_media_name, media_names, ADVANCED_OPERATIONS
    from mcp_anki import AnkiToolError, MANAGED_NOTE_TYPES, digest, plain, native_id
    from mcp_undo import encoded, restore_sqlite, atomic_bytes
    from mcp_creation import fingerprint
    from mcp_semantic import build_model, rank, tokens
    from note_metadata import INCREMENTO_OCR_TEXT_FIELD, visible_field_names
    from mcp_ocr import image_dimensions


LIBRARY_WRITES = frozenset({"run_image_ocr", "run_pdf_ocr", "build_semantic_index", "manage_smart_list"})
ADVANCED_OPERATIONS.add("smart_refresh")
_STORE_LIMIT = 12 * 1024 * 1024


def recognize_image(data, language):
    """One bounded installed Tesseract process; never a runtime installer."""
    try:
        from .deps import tesseract_path
    except ImportError:
        from deps import tesseract_path
    binary = tesseract_path()
    if not binary:
        raise AnkiToolError(
            "Tesseract is unavailable. Install it explicitly using Incremento dependency setup; no software was installed."
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+\-]{0,79}", language):
        raise AnkiToolError("Invalid OCR language identifier.")
    width, height = image_dimensions(data)
    if width <= 0 or height <= 0 or width * height > 16_000_000:
        raise AnkiToolError("OCR image exceeds its pixel budget.")
    with tempfile.TemporaryDirectory(prefix="incremento-mcp-ocr-") as directory:
        image = Path(directory) / "input.png"
        image.write_bytes(data)
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                [binary, str(image), "stdout", "-l", language], stdout=output, stderr=subprocess.DEVNULL
            )
            deadline = time.monotonic() + 8
            try:
                while process.poll() is None:
                    if time.monotonic() > deadline or os.fstat(output.fileno()).st_size > 1024 * 1024:
                        raise AnkiToolError("OCR exceeded its time/output budget. Existing text was preserved.")
                    threading.Event().wait(0.05)
                if process.returncode:
                    raise AnkiToolError(
                        "The installed OCR engine could not read this image/language. Existing text was preserved."
                    )
                output.seek(0)
                raw = output.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise AnkiToolError("OCR text exceeds its output budget.")
                return raw.decode("utf-8", errors="replace").strip()[:48000]
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)


def library_tools(tool, identity, ids, text, revision, cursor, limit):
    return [
        tool(
            "get_ocr_capabilities",
            "Report installed local OCR/PDF capabilities and request budgets. Never installs or downloads engines/models.",
        ),
        tool(
            "run_image_ocr",
            "Run installed Tesseract on exact local image references from up to 10 text notes (at most 2 images total). "
            "Writes saved OCR/index and source fingerprints with durable undo. Missing hidden fields are left unchanged; index-only OCR remains readable.",
            {"note_ids": {**ids, "maxItems": 10}, "language": {"type": "string", "minLength": 1, "maxLength": 80}},
            ["note_ids"],
            write=True,
        ),
        tool(
            "run_pdf_ocr",
            "OCR up to 3 selected pages of an imported PDF using installed PyMuPDF/Tesseract. "
            "Updates only those search-index pages; the original PDF and other pages are unchanged and old text is durably reversible.",
            {
                "card_id": identity,
                "pages": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"type": "integer", "minimum": 1, "maximum": 100000},
                },
                "language": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            ["card_id", "pages"],
            write=True,
        ),
        tool(
            "build_semantic_index",
            "Build/resume a private local latent-semantic index over notes, OCR and saved source passages. "
            "Processes at most 60 chunks per call; follow next_cursor or call again to resume after restart. "
            "No embeddings service, downloaded model, account or new runtime is required. Each batch has durable undo.",
            {"reset": {"type": "boolean"}, "cursor": cursor},
            write=True,
        ),
        tool(
            "get_semantic_status",
            "Inspect local semantic-index size, source coverage and progress; no index is generated implicitly.",
        ),
        tool(
            "search_meaning",
            "Retrieve related wording through the corpus-trained latent-semantic index, blended with literal evidence. "
            "Optional related_terms supply additional concepts from the client. Results cite saved source passages and stale sources are excluded.",
            {
                "query": text,
                "related_terms": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 100}},
                "cursor": cursor,
                "limit": limit,
            },
            ["query"],
        ),
        tool(
            "find_library_duplicates",
            "Find whole-collection exact duplicate groups by native first-field text (SQLite lower/trim), "
            "plus bounded near-duplicate candidates across decks. Follow cursors to scan later groups/notes. Never deletes or merges automatically.",
            {"minimum_similarity": {"type": "number", "minimum": 0.5, "maximum": 1}, "cursor": cursor, "limit": limit},
        ),
        tool(
            "audit_library",
            "Page through missing media/sources, empty visible fields, broken parent/resource links and stale OCR fingerprints. "
            "Reports old OCR with no source fingerprint as unverified. Read-only; never runs repairs or changes study state.",
            {"cursor": cursor, "limit": limit},
        ),
        tool(
            "get_smart_lists",
            "Read saved profile-local smart-list rules and their revision. Rules use Anki search syntax; no automatic refresh is run.",
        ),
        tool(
            "manage_smart_list",
            "Save/delete a smart-list rule for an existing book list using a fresh rules revision. "
            "Rules have a name and Anki query. Membership remains unchanged until a concrete refresh proposal is applied.",
            {
                "action": {"type": "string", "enum": ["save", "delete"]},
                "list_id": identity,
                "name": {"type": "string", "maxLength": 200},
                "anki_query": text,
                "expected_revision": revision,
            },
            ["action", "list_id", "expected_revision"],
            write=True,
        ),
        tool(
            "preview_smart_list_refresh",
            "Resolve a complete bounded smart-list query and preview additions/removals. "
            "Refuses oversized results rather than removing unscanned books; apply_advanced_plan commits one durably reversible membership change.",
            {"list_id": identity},
            ["list_id"],
        ),
    ]


class McpLibrary(McpCollection):
    def _store_path(self, kind):
        path = paths.get_mcp_library_path(self.addon_dir, self.profile, kind)
        return self._profile_file(path.name, must_exist=False)

    def _read_store(self, kind, default):
        path = self._store_path(kind)
        if not path.exists():
            return deepcopy(default)
        try:
            value = json.loads(self._bounded_bytes(path, _STORE_LIMIT))
        except (ValueError, OSError, RecursionError):
            raise AnkiToolError(
                "The private MCP library store is invalid. Preserve it and restore its last valid backup."
            ) from None
        if not isinstance(value, dict) or type(value.get("version")) is not int or value.get("version") != 1:
            raise AnkiToolError("Unsupported private MCP library-store version.")
        self._validate_store(kind, value)
        return value

    @staticmethod
    def _validate_store(kind, value):
        try:
            if kind == "smart_lists":
                rules = value["rules"]
                if not isinstance(rules, dict) or len(rules) > 100:
                    raise ValueError()
                for key, rule in rules.items():
                    native_id(key)
                    if (
                        not isinstance(rule, dict)
                        or rule["list_id"] != key
                        or not isinstance(rule["name"], str)
                        or len(rule["name"]) > 200
                        or not isinstance(rule["anki_query"], str)
                        or len(rule["anki_query"]) > 2000
                    ):
                        raise ValueError()
            elif kind == "ocr":
                if not isinstance(value["notes"], dict) or not isinstance(value["pdfs"], dict):
                    raise ValueError()
                for key, item in value["notes"].items():
                    native_id(key)
                    if not isinstance(item.get("images"), dict) or len(item["images"]) > 200:
                        raise ValueError()
                    for name, sha in item["images"].items():
                        local_media_name(name)
                        if not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha):
                            raise ValueError()
                for key, item in value["pdfs"].items():
                    native_id(key)
                    if (
                        not isinstance(item, dict)
                        or not isinstance(item.get("hash"), str)
                        or not re.fullmatch("[0-9a-f]{64}", item["hash"])
                    ):
                        raise ValueError()
                    texts = item.get("texts", {})
                    if not isinstance(texts, dict) or len(texts) > 1000:
                        raise ValueError()
                    for page, text in texts.items():
                        if (
                            not str(page).isdigit()
                            or not 1 <= int(page) <= 100000
                            or not isinstance(text, str)
                            or len(text) > 48000
                        ):
                            raise ValueError()
            else:
                docs = value["documents"]
                if (
                    not isinstance(docs, dict)
                    or len(docs) > 2000
                    or not isinstance(value["model"], dict)
                    or type(value["complete"]) is not bool
                    or type(value["unavailable"]) is not int
                    or not isinstance(value["progress"], list)
                    or len(value["progress"]) != 3
                    or any(type(item) is not int or item < 0 for item in value["progress"])
                ):
                    raise ValueError()
                for key, entry in docs.items():
                    if not isinstance(entry, dict) or not isinstance(entry["text"], str) or len(entry["text"]) > 4000:
                        raise ValueError()
                    native_id(entry["card_id"])
                    native_id(entry["note_id"])
                    if (
                        type(entry["position"]) is not int
                        or entry["position"] < 0
                        or type(entry["offset"]) is not int
                        or entry["offset"] < 0
                    ):
                        raise ValueError()
                model = value["model"]
                if docs:
                    vocab = model["vocabulary"]
                    basis = model["basis"]
                    if (
                        not isinstance(vocab, list)
                        or len(vocab) > 2048
                        or not all(isinstance(term, str) and len(term) <= 4000 for term in vocab)
                        or len(model["idf"]) != len(vocab)
                        or not isinstance(basis, list)
                        or len(basis) > 8
                        or not isinstance(model["embeddings"], dict)
                        or set(model["embeddings"]) != set(docs)
                    ):
                        raise ValueError()
                    vectors = [model["idf"], *basis, *model["embeddings"].values()]
                    for vector in vectors:
                        if not isinstance(vector, list) or any(
                            type(number) not in (int, float) or not math.isfinite(number) for number in vector
                        ):
                            raise ValueError()
                    if any(len(vector) != len(vocab) for vector in basis) or any(
                        len(vector) != len(basis) for vector in model["embeddings"].values()
                    ):
                        raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            raise AnkiToolError(
                "The private MCP library store is malformed. Preserve it and restore a valid backup."
            ) from None

    def _write_store(self, kind, value):

        raw = encoded(value)
        if len(raw) > _STORE_LIMIT:
            raise AnkiToolError("The private index/rule budget is full; use a smaller corpus.")
        atomic_bytes(self._store_path(kind), raw)

    def _snapshot_store(self, kind):
        path = self._store_path(kind)
        state = {"kind": "library_file", "store": kind, "present": path.exists(), "hash": None, "retained": None}
        if path.exists():
            raw = self._bounded_bytes(path, _STORE_LIMIT)
            sha = hashlib.sha256(raw).hexdigest()
            relative = "mcp_undo_files/state/" + sha + ".json.gz"
            retained = self._profile_file(relative, must_exist=False)
            if not retained.exists():
                atomic_bytes(retained, gzip.compress(raw, mtime=0))
            state.update(hash=sha, retained=relative)
        return state

    def _restore_store(self, state):
        path = self._store_path(state["store"])
        if state["present"]:
            relative = state["retained"]
            if not relative.startswith("mcp_undo_files/state/"):
                raise AnkiToolError("Invalid retained library-state identity.")
            retained = self._profile_file(relative)
            try:
                with gzip.open(retained, "rb") as stream:
                    raw = stream.read(_STORE_LIMIT + 1)
            except (OSError, EOFError):
                raise AnkiToolError("Retained library state is damaged. Restore a valid backup first.") from None
            if len(raw) > _STORE_LIMIT or hashlib.sha256(raw).hexdigest() != state["hash"]:
                raise AnkiToolError("Retained library state changed or exceeds its budget.")

            atomic_bytes(path, raw)
        elif path.exists():
            path.unlink()

    def _get_ocr_capabilities(self, col):
        try:
            from .deps import has_tesseract
        except ImportError:
            from deps import has_tesseract
        return {
            "tesseract_installed": has_tesseract(),
            "pdf_renderer_installed": importlib.util.find_spec("fitz") is not None,
            "max_images": 2,
            "max_pdf_pages": 3,
            "max_pixels": 16000000,
            "automatic_install": False,
        }

    def _ocr_registry(self):
        return self._read_store("ocr", {"version": 1, "notes": {}, "pdfs": {}})

    def _run_image_ocr(self, col, note_ids, language="eng"):
        prepared = []
        root = Path(col.media.dir())
        if root.is_symlink():
            raise AnkiToolError("Unsafe Anki media directory.")
        for nid in dict.fromkeys(note_ids):
            note = self._bounded_note(col, nid)
            if note.note_type()["name"] in MANAGED_NOTE_TYPES:
                raise AnkiToolError("Use PDF OCR for imported PDFs; image OCR accepts text notes only.")
            images = [
                name
                for name in media_names(note.fields)
                if Path(name).suffix.casefold() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
            ]
            rows = []
            for name in images:
                data = self._bounded_bytes(root / local_media_name(name), 16 * 1024 * 1024)
                rows.append((name, data))
            prepared.append((note, rows))
        if not 1 <= sum(len(rows) for _, rows in prepared) <= 2:
            raise AnkiToolError("Select notes containing one or two local images in total.")
        registry = self._ocr_registry()
        results = []
        # Recognize everything before the first write; an unavailable engine,
        # missing language or failed image cannot erase saved OCR.
        recognized = []
        for note, rows in prepared:
            recognized.append(
                (
                    note,
                    [(name, recognize_image(data, language), hashlib.sha256(data).hexdigest()) for name, data in rows],
                )
            )
            self.check()
        changed = []
        for note, rows in recognized:
            combined = "\n\n".join(f"[{name}] {text}" for name, text, _ in rows if text)
            if INCREMENTO_OCR_TEXT_FIELD in dict(note.items()):
                note[INCREMENTO_OCR_TEXT_FIELD] = (
                    combined.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                self._stable_note_layout(col, note)
                changed.append(note)
            card_ids = col.find_cards(f"nid:{note.id}")
            db.replace_note_ocr_index(
                self.addon_dir, self.profile, note.id, card_ids, [(name, text) for name, text, _ in rows]
            )
            registry["notes"][str(note.id)] = {"images": {name: sha for name, _, sha in rows}, "language": language}
            results.append({"note_id": str(note.id), "images": len(rows), "characters": len(combined)})
        if changed:
            self.changes = col.update_notes(changed)
        self._write_store("ocr", registry)
        return {"items": results, "engine": "installed_tesseract", "note_types_changed": False}

    def _run_pdf_ocr(self, col, card_id, pages, language="eng"):
        item = self._card(col, card_id)
        if item["kind"] != "pdf":
            raise AnkiToolError("Choose an imported PDF card.")
        try:
            import fitz
        except ImportError:
            raise AnkiToolError(
                "PyMuPDF is unavailable; install it explicitly through Incremento dependency setup."
            ) from None
        path = self._document_path(item)
        if path.stat().st_size > 128 * 1024 * 1024:
            raise AnkiToolError("PDF exceeds the OCR source budget.")

        original_hash = fingerprint(path)
        recognized = {}
        with fitz.open(path) as document:
            for number in sorted(set(pages)):
                self.check()
                if not 1 <= number <= len(document):
                    raise AnkiToolError("PDF page is out of range.")
                page = document[number - 1]
                if page.rect.width * page.rect.height * 4 > 16_000_000:
                    raise AnkiToolError("Rendered PDF page exceeds 16 million pixels.")
                data = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
                recognized[number] = recognize_image(data, language)
        self.check()
        if fingerprint(path) != original_hash:
            raise AnkiToolError("PDF changed during recognition. No OCR text was written.")
        conn = db.get_connection(self.addon_dir, self.profile)
        with conn:
            for number, text in recognized.items():
                conn.execute("DELETE FROM pdf_text_index WHERE card_id=? AND page=?", (int(card_id), number))
                if text:
                    conn.execute(
                        "INSERT INTO pdf_text_index(card_id,page,text) VALUES(?,?,?)", (int(card_id), number, text)
                    )
        registry = self._ocr_registry()

        sha = original_hash
        prior = registry["pdfs"].get(card_id, {})
        texts = dict(prior.get("texts", {})) if prior.get("hash") == sha else {}
        texts.update({str(page): text for page, text in recognized.items()})
        registry["pdfs"][card_id] = {
            "hash": sha,
            "pages": sorted(map(int, texts)),
            "texts": texts,
            "language": language,
        }
        self._write_store("ocr", registry)
        return {
            "card_id": card_id,
            "pages": sorted(recognized),
            "characters": sum(map(len, recognized.values())),
            "source_file_changed": False,
        }

    @staticmethod
    def _empty_semantic():
        return {"version": 1, "documents": {}, "model": {}, "progress": [0, 0, 0], "complete": False, "unavailable": 0}

    def _get_semantic_status(self, col):
        index = self._read_store("semantic", self._empty_semantic())
        return {
            "documents": len(index["documents"]),
            "complete": index["complete"],
            "unavailable_sources": index["unavailable"],
            "engine": "local_latent_semantic_indexing",
            "source_coverage": "saved_notes_ocr_and_source_passages",
            "downloaded_models": False,
            "instructions": "Call build_semantic_index repeatedly to resume; reset=true starts a clean corpus.",
        }

    def _build_semantic_index(self, col, reset=False, cursor=None):
        if reset and cursor:
            raise AnkiToolError("Choose reset or a continuation cursor.")
        index = self._empty_semantic() if reset else self._read_store("semantic", self._empty_semantic())
        state = (
            self._cursor("semantic-build", cursor)
            if cursor
            else index["progress"]
            if not index["complete"]
            else [0, 0, 0]
        )
        if (
            not isinstance(state, list)
            or len(state) != 3
            or any(type(value) is not int or value < 0 for value in state)
        ):
            raise AnkiToolError("Invalid semantic-index cursor.")
        if cursor and state != index["progress"]:
            raise AnkiToolError("Semantic-index progress changed. Resume without the old cursor.")
        if not cursor and index["complete"]:
            index["unavailable"] = 0
        cid, position, offset = state
        complete = False
        cache = {}
        scanned = 0
        while scanned < 60:
            self.check()
            rows = col.db.all("SELECT id FROM cards WHERE id>=? ORDER BY id LIMIT 1", max(1, cid))
            if not rows:
                complete = True
                break
            current = rows[0][0]
            if current != cid:
                cid, position, offset = current, 0, 0
            note = self._bounded_note(col, col.get_card(cid).nid)
            note_revision = digest([list(note.items()), list(note.tags)])
            item = self._card(col, str(cid))
            if position == 0:
                if offset == 0:
                    index["documents"] = {
                        key: value for key, value in index["documents"].items() if value["card_id"] != str(cid)
                    }
                text = "\n".join(plain(value) for _, value in note.items()) + "\n" + " ".join(note.tags)
                revision = digest(text)
            else:
                try:
                    if (cid, position) not in cache:
                        cache[(cid, position)] = self._source_text(col, str(cid), position)
                    text, _, revision = cache[(cid, position)]
                except (ValueError, OSError, KeyError, RuntimeError):
                    index["unavailable"] += 1
                    cid, position, offset = cid + 1, 0, 0
                    scanned += 1
                    continue
            chunk = text[offset : offset + 4000]
            key = f"{cid}:{position}:{offset}"
            if chunk.strip():
                index["documents"][key] = {
                    "card_id": str(cid),
                    "note_id": str(note.id),
                    "title": item["title"],
                    "position": position,
                    "offset": offset,
                    "text": chunk,
                    "note_revision": note_revision,
                    "source_revision": revision,
                }
            scanned += 1
            if offset + 4000 < len(text):
                offset += 4000
            else:
                try:
                    total = (
                        self._source_positions(col, str(cid))
                        if item["kind"] in {"pdf", "epub"}
                        or item["note_type"]
                        in {"Incremento Writing", "Incremento Video", "Incremento Audio", "Incremento Web"}
                        else 0
                    )
                except (ValueError, OSError, RuntimeError):
                    total = 0
                    index["unavailable"] += 1
                if position < total:
                    position, offset = position + 1, 0
                else:
                    cid, position, offset = cid + 1, 0, 0
            if len(index["documents"]) > 2000:
                raise AnkiToolError(
                    "Semantic index exceeds 2,000 passages; narrow or split the library before rebuilding."
                )
        index.update(progress=[cid, position, offset], complete=complete)
        index["model"] = build_model(index["documents"], self.check)
        self._write_store("semantic", index)
        return {
            "documents": len(index["documents"]),
            "chunks_processed": scanned,
            "complete": complete,
            "engine": index["model"]["engine"],
            "unavailable_sources": index["unavailable"],
            "next_cursor": None if complete else self._cursor("semantic-build", state=[cid, position, offset]),
        }

    def _search_meaning(self, col, query, related_terms=None, cursor=None, limit=20):
        index = self._read_store("semantic", self._empty_semantic())
        if not index["documents"]:
            return {"items": [], "coverage": "index_not_built", "next_cursor": None}
        label = "meaning:" + digest([query, related_terms, index])
        offset = self._cursor(label, cursor) or 0
        if type(offset) is not int or offset < 0:
            raise AnkiToolError("Invalid semantic search cursor.")
        ranked = rank(index["model"], index["documents"], query, related_terms or [])
        items = []
        stale = 0
        consumed = 0
        for score, key in ranked[offset : offset + 200]:
            self.check()
            consumed += 1
            entry = index["documents"][key]
            try:
                note = self._bounded_note(col, entry["note_id"])
                if digest([list(note.items()), list(note.tags)]) != entry["note_revision"]:
                    raise AnkiToolError("Stale indexed note.")
                if entry["position"]:
                    _, _, revision = self._source_text(col, entry["card_id"], entry["position"])
                    if revision != entry["source_revision"]:
                        raise AnkiToolError("Stale source passage.")
                elif not col.db.all(
                    "SELECT id FROM cards WHERE id=? AND nid=?", int(entry["card_id"]), int(entry["note_id"])
                ):
                    raise AnkiToolError("Stale card identity.")
            except (ValueError, OSError, KeyError, RuntimeError):
                stale += 1
                continue
            items.append(
                {key: entry[key] for key in ("card_id", "note_id", "title", "position", "offset", "text")}
                | {
                    "score": round(score, 6),
                    "source_kind": "note_fields" if entry["position"] == 0 else "saved_source",
                    "position": entry["position"] or None,
                }
            )
            if len(items) >= limit:
                break
        more = offset + consumed < len(ranked)
        return {
            "items": items,
            "engine": "local_latent_semantic_indexing",
            "stale_passages_skipped": stale,
            "index_complete": index["complete"],
            "coverage": "indexed_saved_passages_only",
            "next_cursor": self._cursor(label, state=offset + consumed) if more else None,
        }

    def _get_smart_lists(self, col):
        value = self._read_store("smart_lists", {"version": 1, "rules": {}})
        return {
            "items": list(value["rules"].values()),
            "revision": digest(value),
            "refresh": "explicit_preview_and_apply",
        }

    def _manage_smart_list(self, col, action, list_id, expected_revision, name="", anki_query=""):
        value = self._read_store("smart_lists", {"version": 1, "rules": {}})
        if digest(value) != expected_revision:
            raise AnkiToolError("Smart-list rules changed. Read them again.")
        self._require_list(db.get_connection(self.addon_dir, self.profile), native_id(list_id))
        if action == "delete":
            value["rules"].pop(list_id, None)
        else:
            if not name.strip() or not anki_query.strip():
                raise AnkiToolError("Supply a rule name and an Anki query.")
            # Validate Anki syntax without applying membership changes.
            col.find_cards(anki_query)
            value["rules"][list_id] = {"list_id": list_id, "name": name.strip(), "anki_query": anki_query.strip()}
            if len(value["rules"]) > 100:
                raise AnkiToolError("Smart-list rule budget is full.")
        self._write_store("smart_lists", value)
        return self._get_smart_lists(col)

    def _smart_candidates(self, col, list_id):
        rules = self._read_store("smart_lists", {"version": 1, "rules": {}})
        rule = rules["rules"].get(list_id)
        if not rule:
            raise AnkiToolError("Save a smart-list rule first.")
        ids = col.find_cards(rule["anki_query"])
        if len(ids) > 5000:
            raise AnkiToolError("The rule matches more than 5,000 cards. Narrow it before refreshing.")
        result = {}
        for cid in ids:
            self.check()
            item = self._card(col, str(cid))
            if item.get("book_id"):
                self._document_path(item)
                note = col.get_note(int(item["note_id"]))
                result[item["book_id"]] = {
                    "card_id": str(cid),
                    "note_revision": digest([list(note.items()), list(note.tags)]),
                }
        if len(result) > 500:
            raise AnkiToolError("The smart list exceeds 500 books. Narrow its rule before refreshing.")
        return rule, dict(sorted(result.items()))

    def _preview_smart_list_refresh(self, col, list_id):
        rule, books = self._smart_candidates(col, list_id)
        conn = db.get_connection(self.addon_dir, self.profile)
        self._require_list(conn, int(list_id))
        current = {
            kind + ":" + filename
            for kind, filename in conn.execute(
                "SELECT kind,filename FROM document_library_memberships WHERE list_id=?", (int(list_id),)
            )
        }
        return self._new_advanced_plan(
            col,
            "smart_refresh",
            {"list_id": list_id},
            {
                "rule": rule,
                "add": sorted(set(books) - current),
                "remove": sorted(current - set(books)),
                "complete_query": True,
            },
        )

    def _perform_smart_refresh(self, col, list_id):
        rule, books = self._smart_candidates(col, list_id)
        planned = self.history.get(self._active_change)["args"]["_advanced"]["arguments"]
        if rule != planned["_smart_rule"] or books != planned["_smart_candidates"]:
            raise AnkiToolError("The smart-list rule or matching books changed after preview. Generate a new proposal.")
        conn = db.get_connection(self.addon_dir, self.profile)
        self._require_list(conn, int(list_id))
        with conn:
            conn.execute("DELETE FROM document_library_memberships WHERE list_id=?", (int(list_id),))
            for book in books:
                kind, filename = book.split(":", 1)
                conn.execute(
                    "INSERT OR IGNORE INTO document_library_books(kind,filename,reason,source) VALUES(?,?,'','')",
                    (kind, filename),
                )
                if (
                    conn.execute(
                        "SELECT count(*) FROM document_library_memberships WHERE kind=? AND filename=?",
                        (kind, filename),
                    ).fetchone()[0]
                    >= 64
                ):
                    raise AnkiToolError("A book has reached its list-membership budget.")
                conn.execute(
                    "INSERT INTO document_library_memberships(list_id,kind,filename) VALUES(?,?,?)",
                    (int(list_id), kind, filename),
                )
        return {"list_id": list_id, "books": len(books)}

    def _find_library_duplicates(self, col, minimum_similarity=0.85, cursor=None, limit=20):
        state = self._cursor("library-duplicates:" + str(minimum_similarity), cursor) or [0, 0, 0, False]
        if not isinstance(state, list) or len(state) != 4:
            raise AnkiToolError("Invalid duplicate scan cursor.")
        mid, last, after, exact_done = state
        if type(mid) is not int or type(last) is not int or type(after) is not int or type(exact_done) is not bool:
            raise AnkiToolError("Invalid duplicate scan cursor.")
        pairs = []
        exact = []
        if not exact_done:
            exact = col.db.all(
                "SELECT mid,lower(trim(sfld)) AS value,count(*),min(id) AS first_id FROM notes "
                "WHERE length(trim(sfld))>0 GROUP BY mid,value HAVING count(*)>1 AND (mid,first_id)>(?,?) ORDER BY mid,first_id LIMIT ?",
                mid,
                last,
                min(limit, 20) + 1,
            )
            for model, value, count, first_id in exact[: min(limit, 20)]:
                ids = col.db.list(
                    "SELECT id FROM notes WHERE mid=? AND lower(trim(sfld))=? ORDER BY id LIMIT 101", model, value
                )
                pairs.append(
                    {
                        "note_ids": list(map(str, ids[:100])),
                        "similarity": 1.0,
                        "kind": "exact_first_field",
                        "group_size": count,
                        "truncated": len(ids) > 100,
                    }
                )
                mid, last = model, first_id
            exact_done = len(exact) <= min(limit, 20)
        notes = col.db.all("SELECT id,mid,substr(sfld,1,2001) FROM notes WHERE id>? ORDER BY id LIMIT 21", after)
        examined = 0
        seen = {tuple(value["note_ids"]) for value in pairs}
        for nid, model, text in notes[:20]:
            self.check()
            normalized = " ".join(plain(text).casefold().split())
            after = nid
            examined += 1
            if len(normalized) < 8:
                continue
            prefix = normalized[:3].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            candidates = col.db.all(
                "SELECT id,substr(sfld,1,2001) FROM notes WHERE mid=? AND id>? AND lower(trim(sfld)) LIKE ? ESCAPE '\\' ORDER BY id LIMIT 201",
                model,
                nid,
                prefix,
            )
            words = set(tokens(normalized))
            for other, value in candidates[:200]:
                candidate = " ".join(plain(value).casefold().split())
                if normalized == candidate:
                    continue
                other_words = set(tokens(candidate))
                score = len(words & other_words) / max(1, len(words | other_words))
                key = (str(nid), str(other))
                if score >= minimum_similarity and key not in seen:
                    seen.add(key)
                    pairs.append({"note_ids": list(key), "similarity": round(score, 6), "kind": "near_candidate"})
            if len(pairs) >= 100:
                break
        more = not exact_done or examined < len(notes)
        return {
            "pairs": pairs[:100],
            "notes_scanned": examined,
            "exact_scope": "whole_collection_native_first_field_lower_trim",
            "near_scope": "bounded_first_field_prefix_candidates",
            "next_cursor": self._cursor(
                "library-duplicates:" + str(minimum_similarity), state=[mid, last, after, exact_done]
            )
            if more
            else None,
        }

    def _audit_library(self, col, cursor=None, limit=50):
        after = self._cursor("library-audit", cursor) or 0
        if type(after) is not int or after < 0:
            raise AnkiToolError("Invalid audit cursor.")
        rows = col.db.all("SELECT id FROM notes WHERE id>? ORDER BY id LIMIT ?", after, limit + 1)
        issues = []
        unverified = 0
        registry = self._ocr_registry()
        media_root = Path(col.media.dir())
        for (nid,) in rows[:limit]:
            self.check()
            note = self._bounded_note(col, nid)
            fields = dict(note.items())
            for name in visible_field_names(list(fields)):
                if not fields[name].strip():
                    issues.append({"note_id": str(nid), "issue": "empty_field", "field": name})
            for name in media_names(note.fields):
                path = media_root / name
                if not path.is_file() or path.is_symlink():
                    issues.append({"note_id": str(nid), "issue": "missing_media", "filename": name})
            parent = fields.get("Incremento_Parent_Card_ID", "").strip()
            if parent and (not parent.isdigit() or not col.db.all("SELECT id FROM cards WHERE id=?", int(parent))):
                issues.append({"note_id": str(nid), "issue": "broken_parent_link"})
            signature = registry["notes"].get(str(nid))
            if signature:
                for name, expected in signature["images"].items():
                    try:
                        actual = hashlib.sha256(
                            self._bounded_bytes(media_root / local_media_name(name), 16 * 1024 * 1024)
                        ).hexdigest()
                    except (ValueError, OSError):
                        actual = None
                    if actual != expected:
                        issues.append({"note_id": str(nid), "issue": "stale_ocr", "filename": name})
            elif fields.get(INCREMENTO_OCR_TEXT_FIELD):
                unverified += 1
            for (cid,) in col.db.all("SELECT id FROM cards WHERE nid=? LIMIT 101", nid):
                item = self._card(col, str(cid))
                if item["kind"] in {"pdf", "epub"}:
                    try:
                        self._document_path(item)
                    except (ValueError, OSError):
                        issues.append({"note_id": str(nid), "card_id": str(cid), "issue": "missing_source"})
                conn = db.get_connection(self.addon_dir, self.profile)
                for table, target in (("document_links", "target_card_id"), ("recording_links", "recording_card_id")):
                    for (target_id,) in conn.execute(
                        f"SELECT {target} FROM {table} WHERE source_card_id=? LIMIT 101", (cid,)
                    ):
                        if not col.db.all("SELECT id FROM cards WHERE id=?", target_id):
                            issues.append({"note_id": str(nid), "card_id": str(cid), "issue": "broken_resource_link"})
        return {
            "issues": issues[:200],
            "issues_truncated": len(issues) > 200,
            "notes_scanned": min(limit, len(rows)),
            "ocr_sources_unverified": unverified,
            "data_changed": False,
            "next_cursor": self._cursor("library-audit", state=rows[limit - 1][0]) if len(rows) > limit else None,
        }

    def _capture_library(self, col, name, args):
        if name in {"build_semantic_index", "manage_smart_list"}:
            return self._snapshot_store("semantic" if name == "build_semantic_index" else "smart_lists")
        if name == "run_image_ocr":
            return {
                "kind": "ocr_run",
                "notes": [self._ocr_state(col, nid) for nid in dict.fromkeys(args["note_ids"])],
                "sources": self._snapshot_store("ocr"),
            }
        if name == "run_pdf_ocr":
            cid = int(args["card_id"])
            conn = db.get_connection(self.addon_dir, self.profile)
            pages = sorted(set(args["pages"]))
            predicate = f"card_id=? AND page IN ({','.join('?' for _ in pages)})"
            columns = [row[1] for row in conn.execute("PRAGMA table_info(pdf_text_index)")]
            rows = conn.execute(
                f"SELECT * FROM pdf_text_index WHERE {predicate} ORDER BY page", [cid, *pages]
            ).fetchall()
            return {
                "kind": "pdf_ocr",
                "card_id": str(cid),
                "tables": [
                    {
                        "table": "pdf_text_index",
                        "columns": columns,
                        "predicate": predicate,
                        "params": [cid, *pages],
                        "rows": [list(row) for row in rows],
                    }
                ],
                "sources": self._snapshot_store("ocr"),
            }
        return None

    def _capture_advanced_action(self, col, payload):
        if payload["operation"] != "smart_refresh":
            return super()._capture_advanced_action(col, payload)
        lid = payload["arguments"]["list_id"]
        args = payload["arguments"]
        if "_smart_rule" not in args:
            rule, candidates = self._smart_candidates(col, lid)
            args["_smart_rule"], args["_smart_candidates"] = rule, candidates
        else:
            rule, candidates = args["_smart_rule"], args["_smart_candidates"]
        conn = db.get_connection(self.addon_dir, self.profile)
        self._require_list(conn, int(lid))
        keys = [book.split(":", 1) for book in candidates]
        predicate = " OR ".join("(kind=? AND filename=?)" for _ in keys) or "0"
        params = [value for key in keys for value in key]
        tables = []
        for table, condition, values in (
            ("document_library_books", predicate, params),
            ("document_library_memberships", "list_id=? OR " + predicate, [int(lid), *params]),
        ):
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            rows = conn.execute(f"SELECT * FROM {table} WHERE {condition} ORDER BY rowid", values).fetchall()
            tables.append(
                {
                    "table": table,
                    "columns": columns,
                    "predicate": condition,
                    "params": values,
                    "rows": [list(row) for row in rows],
                }
            )
        return {"kind": "smart_refresh", "list_id": lid, "rule": rule, "candidates": candidates, "tables": tables}

    def _restore_library(self, col, state):
        kind = state["kind"]
        if kind == "library_file":
            self._restore_store(state)
        elif kind == "ocr_run":
            for note in state["notes"]:
                self._restore_anki(col, note)
            self._restore_store(state["sources"])
        elif kind in {"pdf_ocr", "smart_refresh"}:
            restore_sqlite(db.get_connection(self.addon_dir, self.profile), [state], self.check)
            if kind == "pdf_ocr":
                self._restore_store(state["sources"])
        else:
            return False
        return True

    def _validate_library_restore(self, before, current):
        if before["kind"] == "library_file" and before["store"] != current["store"]:
            raise AnkiToolError("Library store ownership changed.")
        if before["kind"] == "ocr_run":
            if len(before["notes"]) != len(current["notes"]):
                raise AnkiToolError("OCR note ownership changed.")
            for old, live in zip(before["notes"], current["notes"]):
                self._validate_anki_restore(old, live)
            self._validate_library_restore(before["sources"], current["sources"])
        if before["kind"] in {"pdf_ocr", "smart_refresh"}:
            key = "card_id" if before["kind"] == "pdf_ocr" else "list_id"
            if before[key] != current[key]:
                raise AnkiToolError("Indexed source/list ownership changed.")
            for old, live in zip(before["tables"], current["tables"]):
                if any(old[key] != live[key] for key in ("table", "columns", "predicate", "params")):
                    raise AnkiToolError("Indexed source/list scope changed.")
