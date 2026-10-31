"""Journaled MCP creation, with native Anki package restoration and owned files.

Original import files are never changed. Only exact journaled notes, supplemental
rows and managed copies can be reversed. Reviewed/edited/referenced creations
fail the normal whole-state conflict check before a reversal starts.
"""
from pathlib import Path
import hashlib
import json
import os
import uuid
from zipfile import ZipFile
from urllib.parse import urlsplit

try:
    from . import db, paths
    from .operation_journal import ImportOperation
    from .note_metadata import INCREMENTO_METADATA_FIELDS, apply_incremento_metadata, build_incremento_metadata
    from .content_safety import external_plain_text_to_anki_html, normalize_external_http_url
    from .i18n import t
    from .mcp_undo import model_state
except ImportError:
    import db
    import paths
    from operation_journal import ImportOperation
    from note_metadata import INCREMENTO_METADATA_FIELDS, apply_incremento_metadata, build_incremento_metadata
    from content_safety import external_plain_text_to_anki_html, normalize_external_http_url
    from i18n import t
    from mcp_undo import model_state


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mcp_note_type_spec():
    try:
        from .note_type_updates import NoteTypeSpec
    except ImportError:
        from note_type_updates import NoteTypeSpec
    return NoteTypeSpec(name="Incremento MCP Q/A", fields=("Front", "Back", *INCREMENTO_METADATA_FIELDS),
        question_template="{{Front}}", answer_template="{{FrontSide}}<hr id=answer>{{Back}}",
        normalize_field_ordinals=True)


class McpCreation:
    def _creation_meta(self):
        record = self.history.get(self._active_change)
        if "_creation" not in record["args"]:
            record["args"]["_creation"] = {"snapshot_version": 2, "operations": [], "files": [], "models": [],
                "archive": "mcp_undo_files/"+uuid.uuid4().hex+".apkg", "archive_hash": None}
            self.history.persist()
        return record["args"]["_creation"]

    def _creation_deck(self, col, name):
        deck = col.decks.by_name(name) if name else col.decks.get(1)
        if not deck or deck.get("dyn"):
            raise ValueError("Choose an existing normal Anki deck for creation.")
        return int(deck["id"])

    def _creation_model(self, col, kind):
        name = {"qa": "Incremento MCP Q/A", "pdf": "Incremento PDF", "epub": "Incremento EPUB"}[kind]
        model = col.models.by_name(name)
        if model is None:
            meta = self._creation_meta()
            meta["models"].append(name)
            self.history.persist()
            if kind == "pdf":
                try:
                    from .pdf_manager import ensure_pdf_note_type
                except ImportError:
                    from pdf_manager import ensure_pdf_note_type
                ensure_pdf_note_type(col)
            elif kind == "epub":
                try:
                    from .epub_manager import ensure_epub_note_type
                except ImportError:
                    from epub_manager import ensure_epub_note_type
                ensure_epub_note_type(col)
            else:
                try:
                    from .note_type_updates import ensure_note_type
                except ImportError:
                    from note_type_updates import ensure_note_type
                ensure_note_type(col, mcp_note_type_spec())
            model = col.models.by_name(name)
        required = {"qa": {"Front", "Back"}, "pdf": {"Title", "PDF_Filename"}, "epub": {"Title", "EPUB_Filename"}}[kind] | set(INCREMENTO_METADATA_FIELDS)
        if (not model or model.get("type") != 0 or not 1<=len(model.get("tmpls", []))<=4
                or not required <= {field["name"] for field in model.get("flds", [])}):
            raise ValueError("The existing note type needs its native, consent-gated format update before import.")
        return model

    def _new_creation_operation(self, kind):
        operation = ImportOperation(self.addon_dir, self.profile, kind)
        self._creation_meta()["operations"].append({"id": operation.operation_id, "content_id": operation.content_id})
        self.history.persist()
        return operation

    def _creation_add_note(self, col, operation, note, deck_id, storage_key=""):
        # The journal's stable GUID also identifies the narrow crash window
        # between Anki's add_note commit and bind_anki, without collection scans.
        note.guid = operation.content_id
        col.add_note(note, deck_id)
        cards = col.find_cards(f"nid:{note.id}")
        if not cards:
            raise ValueError("Anki did not generate a card for this note.")
        operation.bind_anki(card_id=cards[0], note_id=note.id)
        operation.commit(storage_key=storage_key)
        self._save_creation_package(col)
        return note.id, cards[0]

    def _save_creation_package(self, col):
        from anki.import_export_pb2 import ExportAnkiPackageOptions, ExportLimit
        from anki.notes_pb2 import NoteIds
        meta = self._creation_meta()
        ids = self._creation_note_ids(col, meta)
        if not ids:
            return
        path = self._profile_file(meta["archive"], must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(".mcp-package-"+uuid.uuid4().hex+".apkg")
        try:
            col.export_anki_package(out_path=str(temporary),
                options=ExportAnkiPackageOptions(with_scheduling=True, with_media=False, with_deck_configs=False),
                limit=ExportLimit(note_ids=NoteIds(note_ids=ids)))
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        meta["archive_hash"] = fingerprint(path)
        self.history.persist()

    def _creation_note_ids(self, col, meta):
        ids = []
        for operation in meta.get("operations", []):
            rows = col.db.all("SELECT id FROM notes WHERE guid=? LIMIT 2", operation["content_id"])
            if len(rows)>1:
                raise ValueError("Created note identity is ambiguous.")
            ids.extend(int(row[0]) for row in rows)
        return ids

    def _create_source_cards(self, col, cards, deck_name=None, tags=None):
        for tag in tags or []:
            if not tag or any(character.isspace() or ord(character)<32 for character in tag):
                raise ValueError("Invalid creation tags.")
        prepared = []
        for draft in cards:
            source = self._card(col, draft["source_card_id"])
            text, kind, _ = self._source_text(col, draft["source_card_id"], draft.get("position", 1))
            quote = draft.get("quote", "")
            if quote and " ".join(quote.casefold().split()) not in " ".join(text.casefold().split()):
                raise ValueError("A supplied quotation does not match the saved source position.")
            prepared.append((draft, source, kind, quote or text[:2000]))
        deck = self._creation_deck(col, deck_name)
        entry = col.add_custom_undo_entry(t("mcp_undo_source_cards"))
        ids = []
        try:
            model = self._creation_model(col, "qa")
            for draft, source, kind, quote in prepared:
                self.check()
                cid, position = int(draft["source_card_id"]), draft.get("position", 1)
                uri = (f"incremento_open_pdf:{cid}:{position}" if kind == "pdf" else
                       f"incremento_open_epub:{cid}:{position-1}:-1" if kind == "epub" else
                       f"incremento_open_video:{cid}:{draft.get('seconds', 0)}" if kind == "transcript" and source["note_type"] == "Incremento Video" else
                       source["fields"].get("Incremento_Source_Link", source["fields"].get("Markdown_File", "")))
                with self._new_creation_operation("mcp_qa") as operation:
                    note = col.new_note(model)
                    note["Front"] = external_plain_text_to_anki_html(draft["front"], max_chars=4000)
                    note["Back"] = external_plain_text_to_anki_html(draft["back"], max_chars=8000)
                    note.tags = list(dict.fromkeys(tags or []))
                    apply_incremento_metadata(note, build_incremento_metadata(source_type=kind,
                        source_title=source["title"], source_link=uri, parent=source["title"], parent_card_id=cid,
                        content_id=operation.content_id))
                    nid, created_cid = self._creation_add_note(col, operation, note, deck)
                    if kind == "pdf":
                        db.add_pdf_card_source(self.addon_dir, self.profile, cid, position, nid, quote[:4000],
                                               source["fields"].get("PDF_Filename", ""))
                    elif kind == "epub":
                        db.add_epub_card_source(self.addon_dir, self.profile, cid, position-1, nid, quote[:4000])
                    elif kind in {"transcript", "audio_notes"}:
                        try:
                            from .recording_links import add_recording_link
                        except ImportError:
                            from recording_links import add_recording_link
                        add_recording_link(self.addon_dir, self.profile, {"kind": "card", "card_id": created_cid},
                            cid, start=draft.get("seconds", 0), label=source["title"][:240])
                    ids.append(str(nid))
            self._save_creation_package(col)
        finally:
            self.changes = col.merge_undo_entries(entry)
        return {"note_ids": ids, "source_linked": True}

    def _import_documents(self, col, documents, deck_name=None, list_id=None, tags=None):
        try:
            from .mcp_workflows import atomic_bytes
            from .document_lists import save_document_details
        except ImportError:
            from mcp_workflows import atomic_bytes
            from document_lists import save_document_details
        deck = self._creation_deck(col, deck_name)
        if sum(item["kind"] == "web" for item in documents)>2:
            raise ValueError("Import at most two webpages per request to fit the client timeout budget.")
        if list_id is not None:
            self._require_list(db.get_connection(self.addon_dir, self.profile), int(list_id))
        for tag in tags or []:
            if not tag or any(character.isspace() or ord(character)<32 for character in tag):
                raise ValueError("Invalid creation tags.")
        # Validate every local input before making the first managed copy.
        source_hashes = {}
        for index, item in enumerate(documents):
            if item["kind"] != "web":
                path = Path(item.get("path", ""))
                if not path.is_absolute() or path.suffix.lower() != "."+item["kind"]:
                    raise ValueError("Choose an absolute local PDF/EPUB file path.")
                raw = self._bounded_bytes(path, 48*1024*1024)
                source_hashes[index] = hashlib.sha256(raw).hexdigest()
                if item["kind"] == "pdf" and not raw.startswith(b"%PDF-"):
                    raise ValueError("The selected file is not a PDF.")
                if item["kind"] == "epub":
                    self._validate_epub(path)
            elif not item.get("url"):
                raise ValueError("Supply a public HTTP(S) webpage URL.")
            else:
                normalize_external_http_url(item["url"])
        ids = []
        entry = col.add_custom_undo_entry(t("mcp_undo_imports"))
        try:
            for index, item in enumerate(documents):
                self.check()
                prepared = None
                try:
                    source_url = ""
                    kind = item["kind"]
                    title = item.get("title", "")
                    if kind == "web":
                        try:
                            from .webpage_markdown import fetch_webpage_markdown
                            from .markdown_manager import _prepare_bytes
                        except ImportError:
                            from webpage_markdown import fetch_webpage_markdown
                            from markdown_manager import _prepare_bytes
                        result = fetch_webpage_markdown(item["url"])
                        title = title or result["title"]
                        source_url = result["url"]
                        prepared = _prepare_bytes(result["markdown_document"].encode(), Path("captured-webpage.md"), title=title)
                        raw = self._bounded_bytes(Path(prepared.path), 48*1024*1024)
                        kind = "epub"
                    else:
                        raw = self._bounded_bytes(Path(item["path"]), 48*1024*1024)
                        if hashlib.sha256(raw).hexdigest() != source_hashes[index]:
                            raise ValueError("A selected source file changed during import.")
                        title = title or Path(item["path"]).stem
                    model = self._creation_model(col, kind)
                    filename = uuid.uuid4().hex+"."+kind
                    relative = kind+"s/"+filename
                    meta = self._creation_meta()
                    with self._new_creation_operation(kind) as operation:
                        operation.track_created_relpath(relative)
                        meta["files"].append(relative)
                        self.history.persist()
                        target = self._profile_file(relative, must_exist=False)
                        atomic_bytes(target, raw)
                        note = col.new_note(model)
                        note["Title"] = external_plain_text_to_anki_html(title[:500], max_chars=500)
                        note["PDF_Filename" if kind == "pdf" else "EPUB_Filename"] = filename
                        note.tags = list(dict.fromkeys(["Incremento", *(tags or [])]))
                        apply_incremento_metadata(note, build_incremento_metadata(source_type="Web" if source_url else kind.upper(),
                            source_title=title, source_link=source_url or relative, content_id=operation.content_id))
                        nid, cid = self._creation_add_note(col, operation, note, deck, relative)
                        save_document_details(self.addon_dir, self.profile, kind, filename,
                            {"reason": "", "source": source_url if len(source_url)<=500 else urlsplit(source_url).netloc,
                             "list_ids": [int(list_id)] if list_id else []})
                        ids.append(str(nid))
                finally:
                    if prepared is not None:
                        prepared.close()
            self._save_creation_package(col)
        finally:
            self.changes = col.merge_undo_entries(entry)
        return {"note_ids": ids, "original_files_changed": False}

    @staticmethod
    def _validate_epub(path):
        with ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos)>2000 or sum(info.file_size for info in infos)>48*1024*1024:
                raise ValueError("EPUB exceeds its expansion budget.")
            if archive.read("mimetype").strip() != b"application/epub+zip":
                raise ValueError("The selected file is not an EPUB.")
            archive.getinfo("META-INF/container.xml")

    def _creation_scopes(self, col, meta):
        conn = db.get_connection(self.addon_dir, self.profile)
        note_ids, card_ids = [], []
        for operation in meta.get("operations", []):
            row = conn.execute("SELECT note_id,card_id FROM import_journal WHERE operation_id=? AND content_id=?",
                               (operation["id"], operation["content_id"])).fetchone()
            if row:
                note_ids.extend([int(row[0])] if row[0] else [])
                card_ids.extend([int(row[1])] if row[1] else [])
        note_ids = list(dict.fromkeys([*note_ids, *self._creation_note_ids(col, meta)]))
        if note_ids:
            marks = ','.join('?' for _ in note_ids)
            card_ids.extend(row[0] for row in col.db.all(f"SELECT id FROM cards WHERE nid IN ({marks})", *note_ids))
        card_ids = list(dict.fromkeys(card_ids))
        ni = ','.join('?' for _ in note_ids) or 'NULL'
        ci = ','.join('?' for _ in card_ids) or 'NULL'
        scopes = []
        for table in ("content_items", "priorities", "reader_bookmarks", "pdf_highlights", "epub_highlights",
                      "pdf_text_index", "epub_text_index", "document_index_state", "writing_progress",
                      "pdf_progress", "epub_progress", "custom_schedule_rules", "knowledge_tree_nodes"):
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            if "card_id" in columns:
                predicate, params = f"card_id IN ({ci})", list(card_ids)
                if "parent_card_id" in columns:
                    predicate += f" OR parent_card_id IN ({ci})"
                    params += card_ids
                scopes.append((table, predicate, params))
        for table, owner in (("pdf_card_sources", "pdf_card_id"), ("epub_card_sources", "epub_card_id"), ("video_card_sources", "video_card_id")):
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            if "note_id" in columns:
                predicate, params = f"note_id IN ({ni})", list(note_ids)
                if owner in columns:
                    predicate += f" OR {owner} IN ({ci})"
                    params += card_ids
                scopes.append((table, predicate, params))
        if meta.get("snapshot_version", 1) >= 2:
            scopes.append(("note_ocr_index", f"note_id IN ({ni})", list(note_ids)))
        elif conn.execute(f"SELECT 1 FROM note_ocr_index WHERE note_id IN ({ni}) LIMIT 1", note_ids).fetchone():
            raise ValueError("A legacy creation gained OCR data. Reverse the OCR change first.")
        for table, target in (("document_links", "target_card_id"), ("recording_links", "recording_card_id"), ("epub_connections", "target_card_id")):
            scopes.append((table, f"source_card_id IN ({ci}) OR {target} IN ({ci})", card_ids+card_ids))
        for table in ("document_library_books", "document_library_memberships"):
            keys = [(Path(rel).suffix[1:], Path(rel).name) for rel in meta.get("files", [])]
            scopes.append((table, ' OR '.join('(kind=? AND filename=?)' for _ in keys) or '0', [v for key in keys for v in key]))
        return scopes

    def _capture_created(self, col, args):
        meta = args.get("_creation")
        if meta is None:
            return {"kind": "created", "notes": [], "files": [], "models": [], "tables": [], "archive": None}
        if meta.get("snapshot_version", 1) not in (1, 2):
            raise ValueError("Unsupported creation reversal version.")
        notes = []
        def sync_safe(table, rows):
            columns = [row[1] for row in col.db.all(f'PRAGMA table_info("{table}")')]
            ignored = {columns.index(key) for key in (("usn", "mod") if meta.get("snapshot_version", 1)>=2 else ("usn",))}
            return [[0 if i in ignored else value for i, value in enumerate(row)] for row in rows]
        ids = self._creation_note_ids(col, meta)
        for nid in ids:
            row = sync_safe("notes", col.db.all("SELECT * FROM notes WHERE id=?", nid))[0]
            cards = sync_safe("cards", col.db.all("SELECT * FROM cards WHERE nid=? ORDER BY id", nid))
            note = col.get_note(nid)
            card_ids = [row[0] for row in cards]
            marks = ','.join('?' for _ in card_ids)
            revlog = col.db.all(f"SELECT * FROM revlog WHERE cid IN ({marks}) ORDER BY id LIMIT 1001", *card_ids) if card_ids else []
            decks = []
            for cid in card_ids:
                card = col.get_card(cid)
                deck = col.decks.get(card.odid or card.did)
                if deck:
                    value = {key: deck.get(key) for key in ("id", "name", "dyn")}
                    if value not in decks:
                        decks.append(value)
            notes.append({"id": nid, "row": row, "cards": cards, "revlog": revlog,
                          "model_id": note.mid, "model": model_state(note.note_type()), "decks": decks})
        files = []
        for relative in meta.get("files", []):
            path = self._profile_file(relative, must_exist=False)
            files.append({"relative": relative, "present": path.exists(),
                          "hash": fingerprint(path) if path.exists() else None})
        models = []
        for name in meta.get("models", []):
            model = col.models.by_name(name)
            if model:
                marks = ','.join('?' for _ in ids) or 'NULL'
                others = col.db.all(f"SELECT count(*) FROM notes WHERE mid=? AND id NOT IN ({marks})", model["id"], *ids)[0][0]
                models.append({"model": model_state(model), "other_notes": others})
        conn = db.get_connection(self.addon_dir, self.profile)
        tables = []
        for table, predicate, params in self._creation_scopes(col, meta):
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            rows = conn.execute(f'SELECT * FROM "{table}" WHERE {predicate} ORDER BY rowid LIMIT 10001', params).fetchall()
            if len(rows)>10000 or sum(len(str(row)) for row in rows)>4*1024*1024:
                raise ValueError("Created data exceeds the MCP reversal budget.")
            tables.append({"table": table, "columns": columns, "predicate": predicate, "params": params, "rows": [list(row) for row in rows]})
        archive = {"relative": meta["archive"], "hash": meta["archive_hash"]} if meta.get("archive_hash") else None
        return {"kind": "created", "notes": notes, "files": files, "models": models, "tables": tables, "archive": archive}

    def _restore_created(self, col, target):
        current = getattr(self, "_creation_restore_current", None)
        if not current or current.get("kind") != "created":
            current = self._capture_created(col, self.history.get(self._active_change)["args"])
        desired_ids = {int(note["id"]) for note in target["notes"]}
        current_ids = {int(note["id"]) for note in current["notes"]}
        if desired_ids and current_ids:
            raise ValueError("Creation reversal expected either existing or absent notes.")
        if desired_ids:
            conn = db.get_connection(self.addon_dir, self.profile)
            for item in target["tables"]:
                if item["table"] == "document_library_memberships":
                    column = item["columns"].index("list_id")
                    for row in item["rows"]:
                        if conn.execute("SELECT 1 FROM document_library_lists WHERE id=?", (row[column],)).fetchone() is None:
                            raise ValueError("The original import list was deleted. Restore it before redoing the import.")
        all_files = {item["relative"]: item for item in [*current["files"], *target["files"]]}
        for snapshot in (current, target):
            if snapshot["notes"]:
                archive = snapshot["archive"]
                if not archive or not archive["relative"].startswith("mcp_undo_files/"):
                    raise ValueError("The retained Anki recovery package is unavailable.")
                package = self._profile_file(archive["relative"])
                if fingerprint(package) != archive["hash"]:
                    raise ValueError("The retained Anki recovery package changed.")
        # Preflight every owned file before any Anki mutation.
        for relative, item in all_files.items():
            if not (relative.startswith("pdfs/") or relative.startswith("epubs/")) or Path(relative).name != relative.split('/')[-1]:
                raise ValueError("Invalid owned import file.")
            path = self._profile_file(relative, must_exist=False)
            saved = self._profile_file("mcp_undo_files/files/"+hashlib.sha256(relative.encode()).hexdigest(), must_exist=False)
            present = any(entry["relative"] == relative and entry["present"] for entry in target["files"])
            source = path if path.exists() else saved
            if present and (not source.is_file() or fingerprint(source)!=item["hash"]):
                raise ValueError("A retained import copy changed or is unavailable.")
        entry = col.add_custom_undo_entry(t("mcp_undo_creation_reverse"))
        try:
            if desired_ids:
                archive = target["archive"]
                package = self._profile_file(archive["relative"])
                if not archive["relative"].startswith("mcp_undo_files/") or fingerprint(package)!=archive["hash"]:
                    raise ValueError("The retained native Anki package changed.")
                for note in target["notes"]:
                    for saved_deck in note["decks"]:
                        live = col.decks.get(saved_deck["id"])
                        if not live or any(live.get(key) != value for key, value in saved_deck.items()):
                            raise ValueError("The original target deck changed or was removed.")
                    live_model = col.models.get(note["model_id"])
                    owned_models = {item["model"]["id"] for item in target["models"]}
                    if (live_model is None and note["model_id"] not in owned_models) or (live_model is not None and model_state(live_model) != note["model"]):
                        raise ValueError("The original note type changed or was removed.")
                    if col.db.all("SELECT id FROM notes WHERE id=? OR guid=?", note["id"], note["row"][1]):
                        raise ValueError("Anki note identity is now in use.")
                    for card in note["cards"]:
                        if col.db.all("SELECT id FROM cards WHERE id=?", card[0]):
                            raise ValueError("Anki card identity is now in use.")
                from anki.import_export_pb2 import ImportAnkiPackageOptions, ImportAnkiPackageRequest
                col.import_anki_package(ImportAnkiPackageRequest(package_path=str(package), options=ImportAnkiPackageOptions(
                    with_scheduling=True, with_deck_configs=False, update_notes=2, update_notetypes=2)))
                for note in target["notes"]:
                    if col.get_note(note["id"]).guid != note["row"][1]:
                        raise ValueError("Native Anki restoration did not retain the expected identity.")
            elif current_ids:
                col.remove_notes(list(current_ids))
            conn = db.get_connection(self.addon_dir, self.profile)
            with conn:
                for item in reversed(current["tables"]):
                    conn.execute(f'DELETE FROM "{item["table"]}" WHERE {item["predicate"]}', item["params"])
                for item in target["tables"]:
                    if item["rows"]:
                        columns = ','.join('"'+name+'"' for name in item["columns"])
                        conn.executemany(f'INSERT INTO "{item["table"]}" ({columns}) VALUES ({",".join("?" for _ in item["columns"])})', item["rows"])
            for relative, item in all_files.items():
                path = self._profile_file(relative, must_exist=False)
                saved = self._profile_file("mcp_undo_files/files/"+hashlib.sha256(relative.encode()).hexdigest(), must_exist=False)
                desired = any(entry["relative"] == relative and entry["present"] for entry in target["files"])
                if desired and not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(saved, path)
                elif not desired and path.exists():
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    if saved.exists():
                        raise ValueError("A retained import copy already occupies the undo destination.")
                    os.replace(path, saved)
            desired_models = {item["model"]["id"] for item in target["models"]}
            for item in current["models"]:
                model = item["model"]
                if model["id"] not in desired_models:
                    if col.db.all("SELECT id FROM notes WHERE mid=? LIMIT 1", model["id"]):
                        raise ValueError("The created note type is now used by another note.")
                    col.models.remove(model["id"])
        finally:
            self.changes = col.merge_undo_entries(entry)
