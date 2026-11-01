"""Native import, media, annotation, export and maintenance adapters."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import uuid

try:
    from . import db, paths, mcp_checkpoint as checkpoint
    from .mcp_library import McpLibrary
    from .mcp_anki import AnkiToolError
    from .mcp_undo import atomic_bytes, encoded
    from .operation_journal import ImportOperation
except ImportError:
    import db
    import paths
    import mcp_checkpoint as checkpoint
    from mcp_library import McpLibrary
    from mcp_anki import AnkiToolError
    from mcp_undo import atomic_bytes, encoded
    from operation_journal import ImportOperation


def content_operations(schema, identity, text, name, integer, number, boolean, patch):
    return {
        "import_content": (
            8,
            schema(
                {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "writing",
                            "markdown",
                            "audio",
                            "video",
                            "local_file",
                            "live_web",
                            "djvu",
                            "supermemo",
                            "apkg",
                            "csv",
                        ],
                    },
                    "path": text,
                    "url": text,
                    "title": name,
                    "deck_name": name,
                    "initial_markdown": {"type": "string", "maxLength": 100000},
                    "tags": {"type": "array", "maxItems": 64, "items": name},
                    "encode_mode": {"type": "string", "enum": ["original", "h264_high", "h264_small"]},
                    "mode": {"type": "string", "enum": ["reference", "copy"]},
                },
                ["kind", "title"],
            ),
        ),
        "pdf_snapshot": (
            7,
            schema(
                {
                    "source_card_id": identity,
                    "note_id": identity,
                    "field_name": name,
                    "position": integer,
                    "excerpt": text,
                },
                ["source_card_id", "note_id", "field_name", "position", "excerpt"],
            ),
        ),
        "notebook_import": (
            7,
            schema(
                {"path": text, "card_ids": {"type": "array", "minItems": 1, "maxItems": 10, "items": identity}},
                ["path", "card_ids"],
            ),
        ),
        "source_relink": (10, schema({"card_id": identity, "path": text}, ["card_id", "path"])),
        "pdf_annotation_sync": (10, schema({"card_id": identity, "source_path": text}, ["card_id"])),
        "video_download": (
            9,
            schema({"card_id": identity, "max_height": integer, "original_quality": boolean}, ["card_id"]),
        ),
        "video_transcode": (
            9,
            schema(
                {"card_id": identity, "encode_mode": {"type": "string", "enum": ["h264_high", "h264_small"]}},
                ["card_id"],
            ),
        ),
        "video_clip": (
            9,
            schema(
                {"card_id": identity, "start": number, "end": number, "note_id": identity, "field_name": name},
                ["card_id", "start", "end", "note_id", "field_name"],
            ),
        ),
        "caption_set": (
            9,
            schema(
                {"card_id": identity, "path": text, "track": {"type": "string", "enum": ["target", "reference"]}},
                ["card_id", "path", "track"],
            ),
        ),
        "caption_download": (
            9,
            schema(
                {
                    "card_id": identity,
                    "language": name,
                    "automatic": boolean,
                    "track": {"type": "string", "enum": ["target", "reference"]},
                },
                ["card_id", "language", "track"],
            ),
        ),
        "export_cards": (
            13,
            schema(
                {
                    "path": text,
                    "format": {"type": "string", "enum": ["apkg", "csv"]},
                    "card_ids": {"type": "array", "minItems": 1, "maxItems": 500, "items": identity},
                    "include_media": boolean,
                },
                ["path", "format", "card_ids"],
            ),
        ),
        "reindex_pdf": (
            14,
            schema({"card_ids": {"type": "array", "minItems": 1, "maxItems": 10, "items": identity}}, ["card_ids"]),
        ),
        "reindex_ocr": (
            14,
            schema({"note_ids": {"type": "array", "minItems": 1, "maxItems": 100, "items": identity}}, ["note_ids"]),
        ),
        "quarantine_files": (
            14,
            schema({"paths": {"type": "array", "minItems": 1, "maxItems": 100, "items": text}}, ["paths"]),
        ),
        "image_occlusion_create": (
            11,
            schema(
                {
                    "path": text,
                    "header": text,
                    "back_extra": text,
                    "masks": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 100,
                        "items": schema(
                            {
                                "group": {"type": "integer", "minimum": 1, "maximum": 500},
                                "shape": {"type": "string", "enum": ["rect", "ellipse"]},
                                "left": {"type": "number", "minimum": 0, "maximum": 1},
                                "top": {"type": "number", "minimum": 0, "maximum": 1},
                                "width": {"type": "number", "minimum": 0.001, "maximum": 1},
                                "height": {"type": "number", "minimum": 0.001, "maximum": 1},
                            },
                            ["group", "shape", "left", "top", "width", "height"],
                        ),
                    },
                    "hide_all": boolean,
                },
                ["path", "masks"],
            ),
        ),
        "image_occlusion_edit": (
            11,
            schema(
                {
                    "note_id": identity,
                    "occlusions": {"type": "string", "maxLength": 32000},
                    "header": text,
                    "back_extra": text,
                },
                ["note_id", "occlusions"],
            ),
        ),
    }


class McpContentOperations(McpLibrary):
    def _media_guard(self, col, card_id, note_id=None):
        ids = [col.get_card(int(card_id)).nid]
        if note_id:
            ids.append(int(note_id))
        result = []
        for nid in dict.fromkeys(ids):
            note = col.get_note(nid)
            result.append(
                {
                    "id": str(nid),
                    "guid": note.guid,
                    "mid": str(note.mid),
                    "fields": dict(note.items()),
                    "tags": list(note.tags),
                }
            )
        return result

    def _prepare_media(self, action, p):
        """Run external engines without a collection, then retain bounded bytes."""
        from . import video_manager as video

        source = p["_media_source"]
        self.check()
        with tempfile.TemporaryDirectory(prefix="incremento-mcp-media-") as directory:
            if action == "video_download":
                relative = video.download_and_compress_video(
                    self.addon_dir,
                    self.profile,
                    source["url"],
                    overwrite=False,
                    max_height=p.get("max_height"),
                    original_quality=p.get("original_quality", False),
                    output_directory=directory,
                )
                output = Path(directory) / Path(relative).name
            elif action == "video_transcode":
                path = self._profile_file(source["local"])
                raw = self._bounded_bytes(path, checkpoint.MAX_FILE)
                if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                    raise AnkiToolError("The local video changed after the preview.")
                frozen = Path(directory) / ("source" + path.suffix)
                frozen.write_bytes(raw)
                relative = video.import_local_video_file(
                    self.addon_dir,
                    self.profile,
                    str(frozen),
                    encode_mode=p.get("encode_mode", "h264_high"),
                    output_directory=directory,
                )
                output = Path(directory) / Path(relative).name
            elif action == "caption_download":
                result = video.download_video_subtitle(
                    self.addon_dir,
                    self.profile,
                    source["url"],
                    language=p["language"],
                    automatic=p.get("automatic", False),
                    output_directory=directory,
                )
                output = Path(directory) / Path(result["relpath"]).name
            else:
                start, end = video.validate_mobile_video_clip_range(p["start"], p["end"])
                output = Path(directory) / "clip.mp4"
                if source["local"]:
                    path = self._profile_file(source["local"])
                    raw = self._bounded_bytes(path, checkpoint.MAX_FILE)
                    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                        raise AnkiToolError("The local video changed after the preview.")
                    frozen = Path(directory) / ("source" + path.suffix)
                    frozen.write_bytes(raw)
                    video.render_mobile_video_clip(frozen, output, start, end)
                else:
                    video.download_remote_mobile_video_clip(
                        self.addon_dir,
                        self.profile,
                        source["url"],
                        output,
                        start,
                        end,
                    )
            raw = self._bounded_bytes(
                checkpoint.checked_path(str(output.resolve())),
                2 * 1024 * 1024 if action == "caption_download" else checkpoint.MAX_FILE,
            )
            if not raw:
                raise AnkiToolError("The media engine produced an empty output.")
            self.check()
            return {"asset": checkpoint.retain(self, raw), "suffix": output.suffix.lower()}

    def _publish_media(self, col, action, p, prepared):
        from . import video_manager as video
        from .mcp_undo import atomic_bytes
        import uuid

        if self._media_guard(col, p["card_id"], p.get("note_id")) != p["_media_guard"]:
            raise AnkiToolError("A target note changed during media preparation. Generate another preview.")
        raw = checkpoint.retained(self, prepared["asset"])
        suffix = prepared["suffix"]
        allowed = {".vtt", ".srt"} if action == "caption_download" else video._VIDEO_EXTS
        if suffix not in allowed:
            raise AnkiToolError("The media engine returned an unsupported format.")
        note = self._video_note(col, p["card_id"])
        if action == "video_clip":
            with tempfile.TemporaryDirectory(prefix="incremento-mcp-publish-") as directory:
                path = Path(directory) / ("clip" + suffix)
                path.write_bytes(raw)
                stored = video.add_mobile_video_clip_to_anki_media(
                    col,
                    path,
                    source_title=note["Title"],
                    start_sec=p["start"],
                    end_sec=p["end"],
                )
            destination = col.get_note(int(p["note_id"]))
            destination[p["field_name"]] += video.mobile_video_clip_html(
                stored,
                start_sec=p["start"],
                end_sec=p["end"],
                source_title=note["Title"],
            )
            self._stable_note_layout(col, destination)
            self.changes = col.update_note(destination)
            return {"filename": stored, "note_id": p["note_id"]}
        relative = "videos/mcp-" + uuid.uuid4().hex + suffix
        with ImportOperation(self.addon_dir, self.profile, "mcp_" + action) as operation:
            operation.track_created_relpath(relative)
            atomic_bytes(self._profile_file(relative, must_exist=False), raw)
            if action == "caption_download":
                video.update_video_note_media(
                    note,
                    **{
                        p["track"] + "_subtitle_file": relative,
                        p["track"] + "_subtitle_label": p["language"],
                    },
                )
            else:
                video.update_video_note_media(note, local_video_file=relative)
            self.changes = col.update_note(note)
            operation.bind_anki(card_id=int(p["card_id"]), note_id=note.id)
            operation.commit(storage_key=relative)
        return {"card_id": p["card_id"], "relative": relative}

    def _content_scope(self, col, action, p, scope):
        root = paths.get_user_files_dir(self.addon_dir, self.profile)
        if action in {
            "import_content",
            "source_relink",
            "video_download",
            "video_transcode",
            "video_clip",
            "caption_set",
            "caption_download",
            "pdf_snapshot",
            "image_occlusion_create",
            "image_occlusion_edit",
        }:
            scope["sqlite"] = True
            scope["append_trees"] = [
                str(root / name)
                for name in ("pdfs", "epubs", "epub_extracted", "writing", "files", "videos", "supermemo_imports")
            ]
            scope["append_trees"].append(str(Path(col.media.dir())))
        if action in {"highlight_create", "highlight_resize", "notebook_import", "reindex_pdf", "reindex_ocr"}:
            scope["anki"] = False
            scope["sqlite"] = True
        if action == "pdf_annotation_sync":
            scope["sqlite"] = True
            scope["anki"] = False
            item = self._card(col, p["card_id"])
            scope["files"].append(str(self._profile_file("pdfs/" + item["fields"]["PDF_Filename"])))
            scope["trees"].append(str(root / "pdf_annotations" / p["card_id"]))
            if p.get("source_path"):
                scope["files"].append(str(checkpoint.checked_path(p["source_path"])))
        if action == "export_cards":
            scope["anki"] = False
            scope["files"] = [p["path"]]
        if action == "quarantine_files":
            scope["anki"] = False
            scope["files"] = p["paths"]
        return scope

    def _prepare_content(self, col, action, p):
        if action == "caption_download":
            from .video_manager import validated_subtitle_language

            p["language"] = validated_subtitle_language(p["language"])
        if action in {"video_download", "video_transcode", "video_clip", "caption_download"}:
            from .video_manager import get_video_note_media

            note = self._video_note(col, p["card_id"])
            local = get_video_note_media(note)["local_video_file"]
            source = {"url": note["YouTube_URL"], "local": local}
            if local:
                source["sha256"] = hashlib.sha256(
                    self._bounded_bytes(self._profile_file(local), checkpoint.MAX_FILE)
                ).hexdigest()
            if action == "video_transcode" and not local:
                raise AnkiToolError("Download or import a local video before transcoding it.")
            p["_media_source"] = source
            p["_media_guard"] = self._media_guard(col, p["card_id"], p.get("note_id"))
        if "path" in p:
            path = checkpoint.checked_path(p["path"])
            if action in {"export_cards", "backup_export", "support_export"}:
                extension = p["format"] if action == "export_cards" else "zip"
                if path.exists() or path.suffix.casefold() != "." + extension:
                    raise AnkiToolError("Choose a new output filename with the matching extension.")
                if not path.parent.is_dir():
                    raise AnkiToolError("The output directory must exist.")
            else:
                raw = self._bounded_bytes(path, checkpoint.MAX_FILE)
                p["_input_sha256"] = hashlib.sha256(raw).hexdigest()
        if action == "import_content":
            p.setdefault("deck_name", "Topics")
            p.setdefault("tags", [])
            if p["kind"] not in {"live_web", "writing"} and "path" not in p:
                raise AnkiToolError("Choose an existing local input file.")
            if p["kind"] in {"video", "live_web"} and p.get("url"):
                from .content_safety import normalize_external_http_url

                p["url"] = normalize_external_http_url(p["url"])
            if p["kind"] == "apkg":
                self._preflight_apkg(col, p["path"])
            if p["kind"] == "markdown":
                from .markdown_manager import prepare_markdown_epub

                with prepare_markdown_epub(p["path"], title=p["title"]) as prepared:
                    raw = self._bounded_bytes(Path(prepared.path), 48 * 1024 * 1024)
                    p["_prepared_import"] = checkpoint.retain(self, raw)
            if p["kind"] == "supermemo":
                from .supermemo_format import (
                    locate_supermemo_collection,
                    parse_supermemo_collection,
                    extract_supermemo_archive,
                )

                with tempfile.TemporaryDirectory(prefix="incremento-mcp-supermemo-") as directory:
                    source = Path(p["path"])
                    kno, folder = (
                        extract_supermemo_archive(source, directory)
                        if source.suffix.lower() == ".zip"
                        else locate_supermemo_collection(source)
                    )
                    parsed = parse_supermemo_collection(kno, folder)
                    if len(parsed.elements) > 100:
                        raise AnkiToolError("Import at most 100 SuperMemo elements per checkpoint.")
                    inventory = self._supermemo_inventory(kno, folder)
                    if source.suffix.lower() != ".zip":
                        p["_supermemo_inputs"] = inventory
            if p["kind"] == "video" and not p.get("url") and not p.get("path"):
                raise AnkiToolError("Supply a local video or supported provider URL.")
        if action in {"pdf_snapshot", "video_clip"}:
            note = self._bounded_note(col, int(p["note_id"]))
            from .note_metadata import visible_field_names

            if p["field_name"] not in visible_field_names(list(dict(note.items()))):
                raise AnkiToolError("Choose an existing visible field.")
        if action == "quarantine_files":
            checked = []
            allowed = [
                paths.get_user_files_dir(self.addon_dir, self.profile) / name
                for name in ("pdfs", "epubs", "videos", "files")
            ]
            for value in p["paths"]:
                path = checkpoint.checked_path(value)
                if not any(path.is_relative_to(folder) for folder in allowed) and path.parent != Path(col.media.dir()):
                    raise AnkiToolError("Quarantine accepts only profile content or Anki media files.")
                self._bounded_bytes(path, checkpoint.MAX_FILE)
                checked.append(str(path))
            p["paths"] = checked
            self._check_unused_files(col, checked)
        if action == "pdf_annotation_sync":
            from .pdf_annotations import pdf_annotation_sync_state

            saved = pdf_annotation_sync_state(self.addon_dir, self.profile, int(p["card_id"])) or {}
            effective = p.get("source_path") or saved.get("source_path")
            if effective:
                p["source_path"] = str(checkpoint.checked_path(effective))
        return p

    def _supermemo_inventory(self, kno, folder):
        result = {}
        total = 0
        for path in [kno, *folder.rglob("*")]:
            checkpoint.checked_path(str(path.resolve()) if not path.is_symlink() else str(path))
            if not path.is_file():
                continue
            raw = self._bounded_bytes(path, checkpoint.MAX_FILE)
            total += len(raw)
            if len(result) >= 500 or total > checkpoint.MAX_FILE:
                raise AnkiToolError("SuperMemo input exceeds 500 files or 128 MiB.")
            result[str(path)] = hashlib.sha256(raw).hexdigest()
        return result

    def _preflight_apkg(self, col, path):
        import sqlite3
        from zipfile import ZipFile
        from anki.collection import Collection
        from anki.import_export_pb2 import ImportAnkiPackageRequest, ImportAnkiPackageOptions

        with ZipFile(path) as archive:
            entries = archive.infolist()
            if (
                len(entries) > 400
                or sum(e.file_size for e in entries) > 256 * 1024 * 1024
                or any(e.file_size > checkpoint.MAX_FILE for e in entries)
            ):
                raise AnkiToolError("APKG exceeds its 400-entry/256 MiB expanded import budget.")
        with tempfile.TemporaryDirectory(prefix="incremento-mcp-apkg-") as directory:
            target = Path(directory) / "collection.anki2"
            reader = sqlite3.connect(Path(col.path).as_uri() + "?mode=ro", uri=True)
            try:
                with sqlite3.connect(str(target)) as destination:
                    reader.backup(destination)
            finally:
                reader.close()
            isolated = Collection(str(target))
            try:
                isolated.import_anki_package(
                    ImportAnkiPackageRequest(
                        package_path=path,
                        options=ImportAnkiPackageOptions(
                            with_scheduling=True, with_deck_configs=False, update_notes=1, update_notetypes=2
                        ),
                    )
                )
                checkpoint.anki_state(self, isolated)
                checkpoint.file_state(self, trees=[str(Path(isolated.media.dir()).resolve())])
            finally:
                isolated.close()

    def _check_unused_files(self, col, selected):
        from html import unescape
        from urllib.parse import unquote

        def decoded(value):
            return unquote(unescape(value)).casefold()

        if col.db.scalar("SELECT coalesce(sum(length(CAST(flds AS BLOB))),0) FROM notes") > 32 * 1024 * 1024:
            raise AnkiToolError("Reference inspection exceeds 32 MiB; use native maintenance.")
        references = [decoded(row[0]) for row in col.db.all("SELECT flds FROM notes")]
        draft = paths.get_extraction_draft_path(self.addon_dir, self.profile)
        if draft.exists():
            references.append(decoded(self._bounded_bytes(draft, 4 * 1024 * 1024).decode("utf-8")))
        media_root = Path(col.media.dir())
        media_files = [Path(p) for p in selected if Path(p).parent == media_root]
        unused = set(col.media.check().unused) if media_files else set()
        for value in selected:
            path = checkpoint.checked_path(value)
            if any(decoded(path.name) in reference for reference in references) or (
                path.parent == media_root and path.name not in unused
            ):
                raise AnkiToolError("A selected file is referenced by a note, template or unsaved draft.")

    def _verify_content_input(self, p):
        for name, expected in p.get("_supermemo_inputs", {}).items():
            if (
                hashlib.sha256(self._bounded_bytes(checkpoint.checked_path(name), checkpoint.MAX_FILE)).hexdigest()
                != expected
            ):
                raise AnkiToolError("The SuperMemo collection changed after its preview.")
        if (
            "_input_sha256" in p
            and hashlib.sha256(self._bounded_bytes(checkpoint.checked_path(p["path"]), checkpoint.MAX_FILE)).hexdigest()
            != p["_input_sha256"]
        ):
            raise AnkiToolError("The selected input changed after its preview.")

    def _op_import_content(
        self,
        col,
        kind,
        title,
        path=None,
        url=None,
        deck_name="Topics",
        tags=None,
        initial_markdown="",
        encode_mode="original",
        mode="copy",
        _input_sha256=None,
        _prepared_import=None,
    ):
        tags = tags or []
        if kind != "apkg" and not col.decks.by_name(deck_name):
            col.decks.add_normal_deck_with_name(self._deck_name(deck_name))
        if kind == "writing":
            from .writing_manager import add_writing_card

            cid = add_writing_card(self.addon_dir, col, title, deck_name, tags, initial_markdown, profile=self.profile)
        elif kind == "markdown":
            from .note_metadata import apply_incremento_metadata

            # Use the existing MCP document importer: it writes only under the
            # captured addon/profile and leaves reader extraction to the reader.
            with tempfile.TemporaryDirectory(prefix="incremento-mcp-markdown-") as directory:
                prepared = Path(directory) / "document.epub"
                prepared.write_bytes(checkpoint.retained(self, _prepared_import))
                result = self._import_documents(
                    col, [{"kind": "epub", "path": str(prepared), "title": title}], deck_name=deck_name, tags=tags
                )
            note = col.get_note(int(result["note_ids"][0]))
            apply_incremento_metadata(note, {"Incremento_Source_Type": "Markdown"})
            self.changes = col.update_note(note)
            cid = note.card_ids()[0]
        elif kind == "audio":
            from .audio_manager import add_audio_card

            cid = add_audio_card(
                self.addon_dir, self.profile, col, source_path=path, title=title, deck_name=deck_name, tags=tags
            )
        elif kind == "local_file":
            from .local_file_manager import add_local_file_card

            cid = add_local_file_card(
                self.addon_dir,
                self.profile,
                col,
                source_path=path,
                title=title,
                deck_name=deck_name,
                tags=tags,
                mode=mode,
            )
        elif kind == "djvu":
            from .djvu_manager import prepare_djvu_pdf

            prepared = prepare_djvu_pdf(path, do_ocr=False)
            try:
                result = self._import_documents(
                    col, [{"kind": "pdf", "path": str(prepared.path), "title": title}], deck_name=deck_name, tags=tags
                )
            finally:
                prepared.close()
            cid = col.find_cards("nid:" + result["note_ids"][0])[0]
        elif kind == "supermemo":
            from .supermemo_format import (
                locate_supermemo_collection,
                parse_supermemo_collection,
                extract_supermemo_archive,
            )
            from .supermemo_import import import_supermemo_collection

            with tempfile.TemporaryDirectory(prefix="incremento-mcp-supermemo-") as directory:
                source = Path(path)
                kno, folder = (
                    extract_supermemo_archive(source, directory)
                    if source.suffix.lower() == ".zip"
                    else locate_supermemo_collection(source)
                )
                self._supermemo_inventory(kno, folder)
                result = import_supermemo_collection(
                    self.addon_dir, self.profile, col, parse_supermemo_collection(kno, folder), deck_name=deck_name
                )
            return {"created": result.created}
        elif kind == "apkg":
            from anki.import_export_pb2 import ImportAnkiPackageRequest, ImportAnkiPackageOptions

            result = col.import_anki_package(
                ImportAnkiPackageRequest(
                    package_path=path,
                    options=ImportAnkiPackageOptions(
                        with_scheduling=True, with_deck_configs=False, update_notes=1, update_notetypes=2
                    ),
                )
            )
            self.changes = result.changes
            return {"imported": True}
        elif kind == "csv":
            import csv

            rows = list(csv.reader(self._bounded_bytes(Path(path), 2 * 1024 * 1024).decode("utf-8-sig").splitlines()))
            if not rows or len(rows) > 100 or any(len(row) != 2 for row in rows):
                raise AnkiToolError("CSV imports require 1–100 Front,Back rows without a header.")
            result = self._create_cards(
                col,
                [{"fields": {"Front": a, "Back": b}} for a, b in rows],
                note_type_name="Basic",
                deck_name=deck_name,
                tags=tags,
            )
            return result
        elif kind in {"video", "live_web"}:
            from .note_metadata import build_incremento_metadata, apply_incremento_metadata

            with ImportOperation(self.addon_dir, self.profile, "mcp_" + kind) as operation:
                if kind == "video":
                    from .video_manager import add_video_card, import_local_video_file

                    local = ""
                    if path:
                        with tempfile.TemporaryDirectory(prefix="incremento-mcp-video-import-") as directory:
                            relative = import_local_video_file(
                                self.addon_dir, self.profile, path, encode_mode=encode_mode, output_directory=directory
                            )
                            prepared = Path(directory) / Path(relative).name
                            raw = self._bounded_bytes(prepared, checkpoint.MAX_FILE)
                            self.check()
                            local = "videos/mcp-" + uuid.uuid4().hex + prepared.suffix
                            operation.track_created_relpath(local)
                            atomic_bytes(self._profile_file(local, must_exist=False), raw)
                    cid = add_video_card(col, url or "", title, deck_name, tags, local_video_file=local)
                else:
                    from .web_manager import add_web_card

                    cid = add_web_card(col, url, title, deck_name, tags)
                card = col.get_card(cid)
                note = col.get_note(card.nid)
                apply_incremento_metadata(
                    note,
                    build_incremento_metadata(
                        source_type=kind, source_title=title, source_link=url or local, content_id=operation.content_id
                    ),
                )
                col.update_note(note)
                operation.bind_anki(card_id=cid, note_id=note.id)
                operation.commit(storage_key=url or local)
        else:
            raise AnkiToolError("Unknown import format.")
        return {"card_id": str(cid), "kind": kind}

    def _op_pdf_snapshot(self, col, source_card_id, note_id, field_name, position, excerpt):
        from .pdf_context_snapshot import render_pdf_context_snapshot

        item = self._card(col, source_card_id)
        if item["note_type"] != "Incremento PDF":
            raise AnkiToolError("Choose a PDF source.")
        image = render_pdf_context_snapshot(
            self._profile_file("pdfs/" + item["fields"]["PDF_Filename"]), page_number=position, excerpt=excerpt
        )
        if not image:
            raise AnkiToolError("The excerpt could not be located for a snapshot.")
        filename = "incremento-mcp-snapshot-" + hashlib.sha256(image).hexdigest() + ".png"
        stored = col.media.write_data(filename, image)
        note = col.get_note(int(note_id))
        note[field_name] += '<br><img src="' + stored + '">'
        self._stable_note_layout(col, note)
        self.changes = col.update_notes([note])
        return {"filename": stored, "note_id": note_id}

    def _op_notebook_import(self, col, path, card_ids, _input_sha256=None):
        from .notebook_citations import import_notebook_citations

        selected = []
        for cid in card_ids:
            item = self._card(col, cid)
            if item["note_type"] != "Incremento PDF":
                raise AnkiToolError("Notebook matching requires PDF cards.")
            selected.append(
                {"card_id": int(cid), "stored_filename": item["fields"]["PDF_Filename"], "title": item["title"]}
            )
        return import_notebook_citations(
            self.addon_dir,
            self.profile,
            path,
            selected,
            pdf_path_resolver=lambda name: str(self._profile_file("pdfs/" + name)),
        )

    def _op_source_relink(self, col, card_id, path, _input_sha256=None):
        card = col.get_card(int(card_id))
        note = col.get_note(card.nid)
        if note.note_type()["name"] == "Incremento PDF":
            raw = self._bounded_bytes(Path(path), checkpoint.MAX_FILE)
            if not raw.startswith(b"%PDF-"):
                raise AnkiToolError("Choose a valid PDF.")
            from .pdf_manager import replace_pdf_card_file

            with ImportOperation(self.addon_dir, self.profile, "pdf") as operation:
                filename = replace_pdf_card_file(
                    self.addon_dir,
                    col,
                    int(card_id),
                    path,
                    profile=self.profile,
                    created_relpath_cb=operation.track_created_relpath,
                    allow_qt=False,
                )
                operation.bind_anki(card_id=int(card_id), note_id=note.id)
                operation.commit(storage_key="pdfs/" + filename)
            return {"card_id": card_id, "filename": filename}
        if note.note_type()["name"] == "Incremento Local File":
            from .local_file_manager import relink_local_file

            with ImportOperation(self.addon_dir, self.profile, "local_file") as operation:
                stored, filename = relink_local_file(
                    self.addon_dir,
                    self.profile,
                    note,
                    new_source_path=path,
                    created_relpath_cb=operation.track_created_relpath,
                )
                self.changes = col.update_note(note)
                operation.bind_anki(card_id=int(card_id), note_id=note.id)
                operation.commit(storage_key=stored)
            return {"card_id": card_id, "stored_path": stored, "filename": filename}
        raise AnkiToolError("Relinking currently accepts PDF and local-file cards.")

    def _op_pdf_annotation_sync(self, col, card_id, source_path=None):
        from .pdf_annotations import sync_pdf_annotations

        item = self._card(col, card_id)
        if item["note_type"] != "Incremento PDF":
            raise AnkiToolError("Choose a PDF card.")
        return sync_pdf_annotations(
            self.addon_dir, self.profile, int(card_id), item["fields"]["PDF_Filename"], source_path=source_path
        )

    def _op_export_cards(self, col, path, format, card_ids, include_media=True):
        from anki.import_export_pb2 import ExportLimit, ExportAnkiPackageOptions

        limit = ExportLimit(card_ids={"cids": list(map(int, card_ids))})
        with tempfile.TemporaryDirectory(prefix="incremento-mcp-export-") as temporary:
            target = Path(temporary) / ("cards." + format)
            if format == "apkg":
                count = col.export_anki_package(
                    out_path=str(target),
                    options=ExportAnkiPackageOptions(with_scheduling=True, with_media=include_media),
                    limit=limit,
                )
            else:
                count = col.export_card_csv(out_path=str(target), limit=limit, with_html=True)
            atomic_bytes(checkpoint.checked_path(path), self._bounded_bytes(target, checkpoint.MAX_FILE))
        return {"path": path, "cards": count}

    def _op_reindex_pdf(self, col, card_ids):
        from .search_indexer import index_pdf_documents
        from .pdf_search import prepare_pdf_index_documents

        documents = prepare_pdf_index_documents(self.addon_dir, self.profile, col, list(map(int, card_ids)))
        return {"result": index_pdf_documents(self.addon_dir, self.profile, documents, force=True)}

    def _op_reindex_ocr(self, col, note_ids):
        from .note_metadata import INCREMENTO_OCR_TEXT_FIELD

        for nid in note_ids:
            note = self._bounded_note(col, int(nid))
            if INCREMENTO_OCR_TEXT_FIELD not in note:
                continue
            conn = db.get_connection(self.addon_dir, self.profile)
            with conn:
                conn.execute("DELETE FROM note_ocr_index WHERE note_id=?", (int(nid),))
            db.replace_note_ocr_index(
                self.addon_dir,
                self.profile,
                int(nid),
                col.find_cards("nid:" + nid),
                [],
                fallback_text=note[INCREMENTO_OCR_TEXT_FIELD],
            )
        return {"notes": len(note_ids)}

    def _op_quarantine_files(self, col, paths):
        self._check_unused_files(col, paths)
        for name in paths:
            path = checkpoint.checked_path(name)
            checkpoint.retain(self, self._bounded_bytes(path, checkpoint.MAX_FILE))
            path.unlink()
        return {"quarantined": len(paths), "permanent_deletion": False}

    def _video_note(self, col, card_id):
        card = col.get_card(int(card_id))
        note = col.get_note(card.nid)
        if note.note_type()["name"] != "Incremento Video":
            raise AnkiToolError("Choose an Incremento Video card.")
        return note

    def _op_caption_set(self, col, card_id, path, track, _input_sha256=None):
        from .video_manager import import_local_subtitle_file, update_video_note_media

        note = self._video_note(col, card_id)
        relative = import_local_subtitle_file(self.addon_dir, self.profile, path)
        update_video_note_media(
            note, **{track + "_subtitle_file": relative, track + "_subtitle_label": Path(path).stem}
        )
        self.changes = col.update_note(note)
        return {"card_id": card_id, "track": track, "relative": relative}

    def _op_image_occlusion_create(self, col, path, masks, header="", back_extra="", hide_all=True, _input_sha256=None):
        from .mcp_ocr import image_dimensions
        from .content_safety import external_plain_text_to_anki_html

        raw = self._bounded_bytes(Path(path), 32 * 1024 * 1024)
        width, height = image_dimensions(raw)
        if width * height > 16000000:
            raise AnkiToolError("Occlusion image exceeds 16 million pixels.")
        model = next((m for m in col.models.all() if m.get("originalStockKind") == 6), None)
        if model is None:
            col.add_image_occlusion_notetype()
            model = next((m for m in col.models.all() if m.get("originalStockKind") == 6), None)
        if model is None:
            raise AnkiToolError("Native image occlusion is unavailable.")
        parts = []
        for mask in masks:
            if mask["left"] + mask["width"] > 1 or mask["top"] + mask["height"] > 1:
                raise AnkiToolError("Occlusion geometry exceeds the image.")
            properties = {"left": mask["left"], "top": mask["top"]}
            if mask["shape"] == "ellipse":
                properties.update(rx=mask["width"] / 2, ry=mask["height"] / 2)
            else:
                properties.update(width=mask["width"], height=mask["height"])
            values = ":".join(key + "=" + str(value) for key, value in properties.items())
            parts.append(
                "{{c"
                + str(mask["group"])
                + "::image-occlusion:"
                + mask["shape"]
                + ":"
                + values
                + ":oi="
                + str(int(hide_all))
                + "}}"
            )
        before = set(col.db.list("SELECT id FROM notes WHERE mid=?", model["id"]))
        with ImportOperation(self.addon_dir, self.profile, "image_occlusion") as operation:
            self.changes = col.add_image_occlusion_note(
                model["id"],
                path,
                "<br>".join(parts),
                external_plain_text_to_anki_html(header, max_chars=2000),
                external_plain_text_to_anki_html(back_extra, max_chars=2000),
                [],
            )
            created = set(col.db.list("SELECT id FROM notes WHERE mid=?", model["id"])) - before
            if len(created) != 1:
                raise AnkiToolError("The native occlusion note identity is ambiguous.")
            nid = next(iter(created))
            ids = col.find_cards("nid:" + str(nid))
            operation.bind_anki(card_id=ids[0], note_id=nid)
            operation.commit(storage_key=Path(path).name)
        return {
            "created": True,
            "note_id": str(nid),
            "card_ids": list(map(str, ids)),
            "groups": len({m["group"] for m in masks}),
        }

    def _op_image_occlusion_edit(self, col, note_id, occlusions, header="", back_extra=""):
        import re
        import math
        from .content_safety import external_plain_text_to_anki_html

        note = self._bounded_note(col, int(note_id))
        if note.note_type().get("originalStockKind") != 6:
            raise AnkiToolError("Choose a native Image Occlusion note.")
        # Native mask grammar is data, never arbitrary card HTML or script.
        if not re.fullmatch(
            r"(?:\{\{c[1-9][0-9]{0,2}::image-occlusion:(?:rect|ellipse):[a-z0-9=:.+\-]+\}\}(?:<br>)?)+", occlusions
        ):
            raise AnkiToolError("Supply native rectangle/ellipse mask markup.")
        for shape, properties in re.findall(r"image-occlusion:(rect|ellipse):([^}]+)", occlusions):
            values = dict(part.split("=", 1) for part in properties.split(":"))
            required = {"left", "top", "width", "height"} if shape == "rect" else {"left", "top", "rx", "ry"}
            if not required <= set(values) or not set(values) <= required | {"oi"}:
                raise AnkiToolError("Invalid native mask properties.")
            numbers = {key: float(value) for key, value in values.items()}
            if any(not math.isfinite(value) or not 0 <= value <= 1 for value in numbers.values()):
                raise AnkiToolError("Mask coordinates must be finite normalized values.")
        self.changes = col.update_image_occlusion_note(
            int(note_id),
            occlusions,
            external_plain_text_to_anki_html(header, max_chars=2000),
            external_plain_text_to_anki_html(back_extra, max_chars=2000),
            list(note.tags),
        )
        groups = {int(number) - 1 for number in re.findall(r"\{\{c([1-9][0-9]*)::", occlusions)}
        removed = [cid for cid in col.find_cards("nid:" + note_id) if col.get_card(cid).ord not in groups]
        if removed:
            col.remove_cards_and_orphaned_notes(removed)
        return {"note_id": note_id, "updated": True}

    def _read_image_occlusion(self, col, note_id):
        from google.protobuf.json_format import MessageToDict

        note = self._bounded_note(col, int(note_id))
        if note.note_type().get("originalStockKind") != 6:
            raise AnkiToolError("Choose a native Image Occlusion note.")
        result = MessageToDict(col.get_image_occlusion_note(int(note_id)), preserving_proto_field_name=True)
        if len(encoded(result)) > 128 * 1024:
            raise AnkiToolError("Occlusion metadata exceeds 128 KiB.")
        return {"note_id": note_id, "native": result}
