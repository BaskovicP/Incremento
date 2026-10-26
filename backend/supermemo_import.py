"""Map parsed native SuperMemo collections into Anki and existing Incremento state."""

from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

try:
    from .db import (
        get_connection,
        get_knowledge_tree_nodes,
        set_knowledge_tree_structure,
        set_topic_schedules,
    )
    from .note_metadata import (
        INCREMENTO_METADATA_FIELDS,
        apply_incremento_metadata,
        build_incremento_metadata,
    )
    from .note_type_updates import NoteTypeSpec, ensure_note_type
    from .operation_journal import ImportOperation
    from .paths import get_supermemo_import_dir, get_user_files_dir
    from .supermemo_format import (
        SuperMemoCollection,
        SuperMemoElement,
        SuperMemoMedia,
        write_optimization_archive,
    )
except ImportError:
    from db import (  # type: ignore
        get_connection,
        get_knowledge_tree_nodes,
        set_knowledge_tree_structure,
        set_topic_schedules,
    )
    from note_metadata import (  # type: ignore
        INCREMENTO_METADATA_FIELDS,
        apply_incremento_metadata,
        build_incremento_metadata,
    )
    from note_type_updates import NoteTypeSpec, ensure_note_type  # type: ignore
    from operation_journal import ImportOperation  # type: ignore
    from paths import get_supermemo_import_dir, get_user_files_dir  # type: ignore
    from supermemo_format import (  # type: ignore
        SuperMemoCollection,
        SuperMemoElement,
        SuperMemoMedia,
        write_optimization_archive,
    )


SUPERMEMO_NOTE_TYPE = "Incremento SuperMemo"
SUPERMEMO_CLOZE_NOTE_TYPE = "Incremento SuperMemo Cloze"
SUPERMEMO_TAG = "Incremento::SuperMemo"
SUPERMEMO_MEDIA_FIELD = "Media"
_IMPORTABLE_ELEMENT_TYPES = frozenset({0, 1, 4})
_MAX_MEDIA_FILES = 10_000
_MAX_MEDIA_BYTES = 100_000_000
_MAX_TOTAL_MEDIA_BYTES = 1_000_000_000
_BLOCKED_HTML_TAGS = {
    "applet",
    "base",
    "button",
    "embed",
    "form",
    "iframe",
    "input",
    "link",
    "meta",
    "object",
    "script",
    "select",
    "svg",
    "template",
    "textarea",
}
_DROP_HTML_ATTRIBUTES = {"action", "formaction", "srcdoc", "xlink:href"}
_CSS_ACTIVE_RE = re.compile(r"(?i)(expression\s*\(|javascript\s*:|-moz-binding\s*:|@import\b)")
_CSS_URL_RE = re.compile(r"(?is)url\s*\([^)]*\)")


@dataclass(frozen=True)
class SuperMemoImportResult:
    created: int
    skipped_existing: int
    skipped_unsupported: int
    history_rows: int
    optimization_files: int
    cloze_cards: int
    media_files: int
    card_ids_by_element: dict[int, int]
    changes: object | None = None


def supermemo_note_type_spec() -> NoteTypeSpec:
    fields = (
        "Title",
        "Question",
        "Answer",
        "Body",
        SUPERMEMO_MEDIA_FIELD,
    ) + tuple(INCREMENTO_METADATA_FIELDS)
    question = (
        '<div class="incremento-supermemo">'
        "{{#Question}}{{Question}}{{/Question}}"
        "{{^Question}}<h2>{{Title}}</h2>{{Body}}{{/Question}}"
        "{{#Media}}<div class=incremento-supermemo-media>{{Media}}</div>{{/Media}}"
        "</div><style>.incremento-supermemo-media img{max-width:100%;height:auto}</style>"
    )
    answer = (
        "{{FrontSide}}"
        "{{#Answer}}<hr id=answer><div class=incremento-supermemo-answer>{{Answer}}</div>{{/Answer}}"
        "{{#Question}}{{#Body}}<div class=incremento-supermemo-context>{{Body}}</div>{{/Body}}{{/Question}}"
    )
    return NoteTypeSpec(SUPERMEMO_NOTE_TYPE, fields, question, answer)


def supermemo_cloze_note_type_spec() -> NoteTypeSpec:
    fields = (
        "Title",
        "Text",
        "Back Extra",
        SUPERMEMO_MEDIA_FIELD,
    ) + tuple(INCREMENTO_METADATA_FIELDS)
    question = (
        '<div class="incremento-supermemo">{{cloze:Text}}'
        "{{#Media}}<div class=incremento-supermemo-media>{{Media}}</div>{{/Media}}"
        "</div><style>.incremento-supermemo-media img{max-width:100%;height:auto}</style>"
    )
    answer = (
        '<div class="incremento-supermemo">{{cloze:Text}}</div>'
        "{{#Media}}<div class=incremento-supermemo-media>{{Media}}</div>{{/Media}}"
        "{{#Back Extra}}<hr id=answer>"
        '<div class="incremento-supermemo-context">{{Back Extra}}</div>'
        "{{/Back Extra}}"
        "<style>.incremento-supermemo-media img{max-width:100%;height:auto}</style>"
    )
    return NoteTypeSpec(
        SUPERMEMO_CLOZE_NOTE_TYPE,
        fields,
        question,
        answer,
        model_type=1,
    )


def is_supermemo_cloze_element(element: SuperMemoElement) -> bool:
    """Return whether one native omission can map losslessly to one cloze."""
    return (
        element.is_item
        and element.question.count("[...]") == 1
        and bool(element.answer.strip())
    )


def _source_link(fingerprint: str, element_id: int) -> str:
    return f"supermemo://{fingerprint}/element/{int(element_id)}"


def _fingerprint_token(fingerprint: str) -> str:
    # A 128-bit prefix leaves room for AF/FI/element identity under Anki's
    # strict 100-byte card custom-data limit.
    return str(fingerprint or "")[:32]


def _safe_html(value: str) -> str:
    return html.escape(str(value or ""), quote=False).replace("\n", "<br>")


def _safe_rich_url(value: object, *, allow_fragment: bool = False, allow_data_image: bool = False) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 8192 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw):
        return ""
    if allow_fragment and raw.startswith("#"):
        return raw
    if allow_data_image and raw.casefold().startswith(
        ("data:image/gif", "data:image/jpeg", "data:image/png", "data:image/webp")
    ):
        return raw
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return ""
        if parsed.username is not None or parsed.password is not None:
            return ""
        parsed.port
    except (TypeError, ValueError):
        return ""
    return raw


def _sanitize_rich_html(value: str) -> str:
    raw = str(value or "").replace("\x00", "")
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in list(soup.find_all(_BLOCKED_HTML_TAGS)):
        tag.decompose()
    for tag in soup.find_all(True):
        tag_name = str(tag.name or "").casefold()
        for attr_name in list(tag.attrs):
            normalized = str(attr_name or "").casefold()
            attr_value = tag.attrs.get(attr_name)
            if normalized.startswith("on") or normalized in _DROP_HTML_ATTRIBUTES:
                del tag.attrs[attr_name]
                continue
            if normalized == "style":
                style = _CSS_ACTIVE_RE.sub("blocked(", str(attr_value or ""))
                tag.attrs[attr_name] = _CSS_URL_RE.sub("", style)
                continue
            if normalized == "href":
                safe = _safe_rich_url(attr_value, allow_fragment=tag_name == "a")
                if safe:
                    tag.attrs[attr_name] = safe
                else:
                    del tag.attrs[attr_name]
                continue
            if normalized in {"src", "poster"}:
                safe = _safe_rich_url(attr_value, allow_data_image=tag_name == "img")
                if safe:
                    tag.attrs[attr_name] = safe
                else:
                    del tag.attrs[attr_name]
                continue
            if normalized == "srcset":
                del tag.attrs[attr_name]
    return str(soup)


def _rich_or_plain(rich_html: str, plain_text: str) -> str:
    return _sanitize_rich_html(rich_html) if str(rich_html or "").strip() else _safe_html(plain_text)


def _cloze_text(element: SuperMemoElement) -> str:
    question = _rich_or_plain(element.question_html, element.question)
    if "[...]" not in question:
        question = _safe_html(element.question)
    answer = _rich_or_plain(element.answer_html, element.answer)
    answer = answer.replace("{{", "&#123;&#123;").replace("}}", "&#125;&#125;")
    return question.replace("[...]", "{{c1::" + answer + "}}", 1)


def _existing_element_cards(col, fingerprint: str) -> dict[int, int]:
    result: dict[int, int] = {}
    prefix = f"supermemo://{fingerprint}/element/"
    try:
        note_ids = col.find_notes(f"tag:{SUPERMEMO_TAG}")
    except Exception:
        return result
    for note_id in note_ids:
        try:
            note = col.get_note(note_id)
            link = str(note["Incremento_Source_Link"] or "").strip()
            card_ids = note.card_ids()
        except Exception:
            continue
        if not card_ids:
            continue
        if link.startswith(prefix):
            try:
                element_id = int(link[len(prefix) :])
                result[element_id] = int(card_ids[0])
                continue
            except (TypeError, ValueError):
                pass
        for card_id in card_ids:
            try:
                payload = json.loads(str(col.get_card(card_id).custom_data or "{}"))
                supermemo = payload.get("incr", {}).get("sm", {})
                if (
                    not isinstance(supermemo, dict)
                    or supermemo.get("fp") != _fingerprint_token(fingerprint)
                ):
                    continue
                element_id = int(supermemo["id"])
                if element_id > 0:
                    result[element_id] = int(card_id)
                    break
            except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
    return result


def _ordered_elements(collection: SuperMemoCollection) -> tuple[SuperMemoElement, ...]:
    all_elements = {element.element_id: element for element in collection.elements}
    importable = {
        element.element_id: element
        for element in collection.elements
        if element.element_type in _IMPORTABLE_ELEMENT_TYPES and not element.deleted
    }
    for element_id, element in tuple(importable.items()):
        parent_id = element.parent_id
        visited = {element_id}
        while parent_id is not None and parent_id not in importable:
            if parent_id in visited:
                raise ValueError("The SuperMemo knowledge tree contains a cycle.")
            visited.add(parent_id)
            parent = all_elements.get(parent_id)
            parent_id = parent.parent_id if parent is not None else None
        importable[element_id] = replace(element, parent_id=parent_id)
    ordered: list[SuperMemoElement] = []
    remaining = dict(importable)
    while remaining:
        ready = [
            element
            for element in remaining.values()
            if element.parent_id not in remaining
        ]
        if not ready:
            raise ValueError("The SuperMemo knowledge tree contains a cycle.")
        ready.sort(key=lambda element: (element.sort_order, element.element_id))
        ordered.extend(ready)
        for element in ready:
            remaining.pop(element.element_id, None)
    return tuple(ordered)


def _reference_metadata(
    collection: SuperMemoCollection,
    element: SuperMemoElement,
) -> tuple[str, str, str]:
    reference = element.reference
    if reference is None:
        return (
            collection.name,
            _source_link(collection.fingerprint, element.element_id),
            "",
        )
    source_link = _safe_rich_url(reference.url) or _source_link(
        collection.fingerprint,
        element.element_id,
    )
    return reference.title or collection.name, source_link, reference.source


def _deck_id(col, deck_name: str) -> int:
    existing = col.decks.by_name(deck_name)
    if existing is not None:
        return int(existing["id"])
    return int(col.decks.add_normal_deck_with_name(deck_name).id)


def _validated_image_extension(source: Path) -> tuple[str, int]:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Missing or unsafe SuperMemo image: {source.name}")
    size = int(source.stat().st_size)
    if size <= 0 or size > _MAX_MEDIA_BYTES:
        raise ValueError(f"SuperMemo image has an unsupported size: {source.name}")
    with source.open("rb") as stream:
        header = stream.read(16)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", size
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg", size
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", size
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp", size
    if header.startswith(b"BM"):
        return ".bmp", size
    raise ValueError(f"Unsupported SuperMemo image format: {source.name}")


def _add_supermemo_media(
    col,
    collection: SuperMemoCollection,
    elements: list[SuperMemoElement],
) -> tuple[dict[int, str], list[str]]:
    by_file_id = {
        media.file_id: media
        for element in elements
        for media in element.media
    }
    if len(by_file_id) > _MAX_MEDIA_FILES:
        raise ValueError("The SuperMemo collection contains too many image files.")
    validated: list[tuple[int, SuperMemoMedia, str, int]] = []
    total_size = 0
    for file_id, media in sorted(by_file_id.items()):
        extension, size = _validated_image_extension(media.source_path)
        total_size += size
        if total_size > _MAX_TOTAL_MEDIA_BYTES:
            raise ValueError("The SuperMemo collection images are too large to import safely.")
        validated.append((file_id, media, extension, size))

    stored_by_file_id: dict[int, str] = {}
    created_names: list[str] = []
    media_root = Path(col.media.dir())
    try:
        with tempfile.TemporaryDirectory(prefix="incremento_supermemo_media_") as temporary:
            stage_root = Path(temporary)
            for file_id, media, extension, _size in validated:
                desired = f"incremento-supermemo-{collection.fingerprint[:16]}-{file_id}{extension}"
                before = {
                    path.name
                    for path in media_root.glob(f"{Path(desired).stem}*{extension}")
                    if path.is_file()
                }
                staged = stage_root / desired
                shutil.copyfile(media.source_path, staged)
                stored = str(col.media.add_file(str(staged)) or "").strip()
                if not stored or Path(stored).name != stored:
                    raise RuntimeError("Anki did not accept a SuperMemo image file.")
                stored_by_file_id[file_id] = stored
                if stored not in before:
                    created_names.append(stored)
    except Exception:
        if created_names:
            try:
                col.media.trash_files(created_names)
            except Exception:
                pass
        raise
    return stored_by_file_id, created_names


def _media_html(element: SuperMemoElement, stored_by_file_id: dict[int, str]) -> str:
    images: list[str] = []
    seen: set[int] = set()
    for media in element.media:
        if media.file_id in seen:
            continue
        seen.add(media.file_id)
        stored = stored_by_file_id.get(media.file_id)
        if not stored:
            continue
        images.append(
            '<img src="'
            + html.escape(stored, quote=True)
            + '" alt="'
            + html.escape(media.name, quote=True)
            + '">'
        )
    return "".join(images)


def _merge_custom_data(
    card,
    collection: SuperMemoCollection,
    element: SuperMemoElement,
) -> None:
    try:
        payload = json.loads(str(card.custom_data or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    # Anki restricts every custom-data key to eight UTF-8 bytes.
    incremento = payload.get("incr")
    if not isinstance(incremento, dict):
        incremento = {}
    incremento["sm"] = {
        "af": round(float(element.a_factor), 6),
        "fi": int(element.forgetting_index),
        "fp": _fingerprint_token(collection.fingerprint),
        "id": int(element.element_id),
    }
    payload["incr"] = incremento
    card.custom_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _apply_current_schedule(
    col,
    card,
    collection: SuperMemoCollection,
    element: SuperMemoElement,
    calendar_today: date,
):
    _merge_custom_data(card, collection, element)
    if element.status == 1:
        card.type = 2
        card.queue = 2
        card.ivl = max(1, int(element.current_interval or 1))
        card.reps = max(0, int(element.repetition_count))
        card.lapses = max(0, int(element.lapse_count))
        if element.due_date is not None:
            card.due = max(1, int(col.sched.today) + (element.due_date - calendar_today).days)
    card.factor = max(0, min(10_000, int(round(max(0.0, float(element.a_factor)) * 1000))))
    return col.update_card(card)


def _unique_revlog_id(col, candidate: int, allocated: set[int]) -> int:
    candidate = max(1, int(candidate))
    while candidate in allocated or col.db.scalar("select 1 from revlog where id=?", candidate):
        candidate += 1
    allocated.add(candidate)
    return candidate


def _insert_history(col, card_id: int, factor: int, element: SuperMemoElement, allocated: set[int]) -> int:
    rows = []
    for entry in element.history:
        revlog_id = _unique_revlog_id(
            col,
            int(entry.reviewed_at.timestamp() * 1000),
            allocated,
        )
        if entry.is_graded:
            ease = 1 if entry.grade <= 2 else (2 if entry.grade == 3 else (3 if entry.grade == 4 else 4))
            review_type = 1
        else:
            ease = 0
            review_type = 4
        rows.append(
            (
                revlog_id,
                int(card_id),
                -1,
                ease,
                max(0, int(entry.scheduled_interval)),
                max(0, int(entry.previous_interval)),
                int(factor),
                0,
                review_type,
            )
        )
    if rows:
        col.db.executemany(
            "insert into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type) "
            "values (?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def _merged_tree_rows(
    addon_dir: str,
    profile: str,
    imported: tuple[SuperMemoElement, ...],
    card_ids: dict[int, int],
) -> list[dict]:
    existing = get_knowledge_tree_nodes(addon_dir, profile)
    rows = [dict(row) for row in existing]
    existing_ids = {int(row["card_id"]) for row in rows}
    max_root_order = max(
        (int(row.get("sort_order") or 0) for row in rows if row.get("parent_card_id") is None),
        default=-1,
    )
    imported_set = {element.element_id for element in imported}
    for element in imported:
        card_id = card_ids[element.element_id]
        if card_id in existing_ids:
            continue
        parent_id = element.parent_id
        while parent_id is not None and parent_id not in imported_set:
            parent = next((item for item in imported if item.element_id == parent_id), None)
            parent_id = parent.parent_id if parent is not None else None
        parent_card_id = card_ids.get(parent_id) if parent_id is not None else None
        sort_order = int(element.sort_order)
        if parent_card_id is None:
            sort_order += max_root_order + 1
        rows.append(
            {
                "card_id": card_id,
                "parent_card_id": parent_card_id,
                "node_kind": "item" if element.is_item else "topic",
                "sort_order": sort_order,
            }
        )
    return rows


def _write_optimization_sidecar(
    addon_dir: str,
    profile: str,
    collection: SuperMemoCollection,
    operation: ImportOperation,
) -> int:
    if not collection.optimization_files:
        return 0
    root = get_supermemo_import_dir(addon_dir, profile, collection.fingerprint)
    destination = root / "optimization"
    manifest = destination / "manifest.json"
    if manifest.is_file():
        try:
            payload = json.loads(manifest.read_text("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Existing SuperMemo optimization archive is invalid.") from exc
        if payload.get("collection_fingerprint") != collection.fingerprint:
            raise RuntimeError("Existing SuperMemo optimization archive belongs to another collection.")
        return 0
    if root.exists():
        raise RuntimeError("Incomplete SuperMemo optimization archive already exists.")
    relative = root.relative_to(get_user_files_dir(addon_dir, profile)).as_posix()
    operation.track_created_relpath(relative)
    write_optimization_archive(collection, destination)
    return len(collection.optimization_files)


def import_supermemo_collection(
    addon_dir: str,
    profile: str,
    col,
    collection: SuperMemoCollection,
    *,
    deck_name: str,
    calendar_today: date | None = None,
) -> SuperMemoImportResult:
    """Create notes/cards, native revlog history, and existing Incremento state.

    Anki's scheduler remains authoritative after import. SuperMemo optimization
    matrices are archived with checksums and never executed.
    """
    today = calendar_today or date.today()
    deck_name = str(deck_name or "").strip()
    if not deck_name:
        raise ValueError("A destination deck is required.")
    ordered = _ordered_elements(collection)
    parent_titles = {element.element_id: element.title for element in ordered}
    unsupported = len(collection.elements) - len(ordered)
    existing = _existing_element_cards(col, collection.fingerprint)
    card_ids = dict(existing)
    to_create = [element for element in ordered if element.element_id not in existing]
    if not to_create:
        return SuperMemoImportResult(
            created=0,
            skipped_existing=len(ordered),
            skipped_unsupported=unsupported,
            history_rows=0,
            optimization_files=0,
            cloze_cards=0,
            media_files=0,
            card_ids_by_element=card_ids,
        )

    standard_needed = any(not is_supermemo_cloze_element(element) for element in to_create)
    cloze_needed = any(is_supermemo_cloze_element(element) for element in to_create)
    standard_model = None
    cloze_model = None
    if standard_needed:
        ensure_note_type(col, supermemo_note_type_spec())
        standard_model = col.models.by_name(SUPERMEMO_NOTE_TYPE)
        if standard_model is None:
            raise RuntimeError("Could not create the Incremento SuperMemo note type.")
    if cloze_needed:
        ensure_note_type(col, supermemo_cloze_note_type_spec())
        cloze_model = col.models.by_name(SUPERMEMO_CLOZE_NOTE_TYPE)
        if cloze_model is None:
            raise RuntimeError("Could not create the Incremento SuperMemo Cloze note type.")
    destination_deck_id = _deck_id(col, deck_name)
    operations: list[tuple[SuperMemoElement, ImportOperation, int, int]] = []
    allocated_revlog_ids: set[int] = set()
    history_rows = 0
    optimization_count = 0
    changes = None
    stored_media: dict[int, str] = {}
    created_media: list[str] = []

    try:
        stored_media, created_media = _add_supermemo_media(col, collection, to_create)
        for element in to_create:
            operation = ImportOperation(addon_dir, profile, "supermemo")
            try:
                cloze = is_supermemo_cloze_element(element)
                model = cloze_model if cloze else standard_model
                if model is None:
                    raise RuntimeError("The required SuperMemo note type is unavailable.")
                parent_card_id = card_ids.get(element.parent_id or 0)
                parent_title = parent_titles.get(element.parent_id, "")
                note = col.new_note(model)
                note["Title"] = _safe_html(element.title)
                if cloze:
                    note["Text"] = _cloze_text(element)
                    note["Back Extra"] = _rich_or_plain(element.body_html, element.body)
                else:
                    note["Question"] = _rich_or_plain(element.question_html, element.question)
                    note["Answer"] = _rich_or_plain(element.answer_html, element.answer)
                    note["Body"] = _rich_or_plain(element.body_html, element.body)
                note[SUPERMEMO_MEDIA_FIELD] = _media_html(element, stored_media)
                source_title, source_link, source_author = _reference_metadata(
                    collection,
                    element,
                )
                apply_incremento_metadata(
                    note,
                    build_incremento_metadata(
                        source_type="SuperMemo",
                        source_title=source_title,
                        source_link=source_link,
                        source_author=source_author,
                        parent=parent_title,
                        parent_card_id=parent_card_id,
                        content_id=operation.content_id,
                    ),
                )
                for tag in (
                    "Incremento",
                    SUPERMEMO_TAG,
                    "item" if element.is_item else "topic",
                ):
                    note.add_tag(tag)
                note.note_type()["did"] = destination_deck_id
                added = col.add_note(note, destination_deck_id)
                if int(getattr(added, "count", 0) or 0) < 1:
                    raise RuntimeError(
                        f"Anki did not create a card for SuperMemo element {element.element_id}."
                    )
                card_id = int(note.card_ids()[0])
                card_ids[element.element_id] = card_id
                operation.bind_anki(card_id=card_id, note_id=int(note.id))
                card = col.get_card(card_id)
                changes = _apply_current_schedule(col, card, collection, element, today)
                card = col.get_card(card_id)
                history_rows += _insert_history(
                    col,
                    card_id,
                    int(card.factor),
                    element,
                    allocated_revlog_ids,
                )
                operations.append((element, operation, card_id, int(note.id)))
            except Exception:
                operation.rollback(error_code="supermemo_element_import_failed")
                raise

        # Reuse Incremento's existing supplemental stores; do not create a
        # parallel SuperMemo metadata schema.
        ranked_elements = sorted(
            ordered,
            key=lambda element: (element.priority_rank, element.sort_order, element.element_id),
        )
        normalized_priority_rank = {
            element.element_id: rank for rank, element in enumerate(ranked_elements)
        }
        priority_denominator = max(1, len(ranked_elements) - 1)
        priority_rows = [
            (
                round(
                    100.0
                    * normalized_priority_rank[element.element_id]
                    / priority_denominator,
                    4,
                ),
                card_ids[element.element_id],
            )
            for element in ordered
        ]
        db_connection = get_connection(addon_dir, profile)
        with db_connection:
            db_connection.executemany(
                "INSERT OR REPLACE INTO priorities (priority, card_id) VALUES (?, ?)",
                priority_rows,
            )
        set_topic_schedules(addon_dir, profile, [
            (card_ids[element.element_id], element.a_factor, max(1, element.current_interval or 1), None)
            for element in ordered if not element.is_item
        ])
        set_knowledge_tree_structure(
            addon_dir,
            profile,
            _merged_tree_rows(addon_dir, profile, ordered, card_ids),
        )

        optimization_count = _write_optimization_sidecar(
            addon_dir,
            profile,
            collection,
            operations[0][1],
        )
        storage_root = get_supermemo_import_dir(addon_dir, profile, collection.fingerprint)
        storage_key = ""
        if storage_root.exists():
            storage_key = storage_root.relative_to(get_user_files_dir(addon_dir, profile)).as_posix()
        for _element, operation, _card_id, _note_id in operations:
            operation.commit(storage_key=storage_key if operation is operations[0][1] else "")
        # Direct revlog restoration is intentionally a one-time import rather
        # than an Anki answer operation. The low-level history inserts clear
        # Anki's undo queue, so the UI presents this import as non-undoable.
    except Exception:
        for _element, operation, _card_id, _note_id in operations:
            operation.rollback(error_code="supermemo_import_failed")
        if created_media:
            try:
                col.media.trash_files(created_media)
            except Exception:
                pass
        raise

    return SuperMemoImportResult(
        created=len(to_create),
        skipped_existing=len(existing),
        skipped_unsupported=unsupported,
        history_rows=history_rows,
        optimization_files=optimization_count,
        cloze_cards=sum(is_supermemo_cloze_element(element) for element in to_create),
        media_files=len(stored_media),
        card_ids_by_element=card_ids,
        changes=changes,
    )
