"""Bounded read models for card → document → local recording reference visits."""
from __future__ import annotations

from html import unescape
import json
from pathlib import Path
import re

try:
    from .db import get_connection
    from .document_links import list_document_links
    from .epub_reference import resolve_epub_reference, validate_location, location_allowed
    from .epub_manager import get_epub_daily_limit_status
    from .pdf_reference import resolve_pdf_reference
    from .pdf_reader_state import maximum_reference_page
    from .pdf_manager import get_pdf_daily_limit_status
    from .paths import get_videos_dir
    from .recording_links import normalize_source, list_recording_links, validate_segment
    from .video_manager import get_video_note_media, local_video_abspath, supported_local_video_extensions
except ImportError:
    from db import get_connection
    from document_links import list_document_links
    from epub_reference import resolve_epub_reference, validate_location, location_allowed
    from epub_manager import get_epub_daily_limit_status
    from pdf_reference import resolve_pdf_reference
    from pdf_reader_state import maximum_reference_page
    from pdf_manager import get_pdf_daily_limit_status
    from paths import get_videos_dir
    from recording_links import normalize_source, list_recording_links, validate_segment
    from video_manager import get_video_note_media, local_video_abspath, supported_local_video_extensions

MAX_RESOURCES = 32
MAX_RECORDINGS = 500
_EPUB = re.compile(r"incremento_open_epub:(\d+):(\d+):(-?\d+)(?::([0-9.]+))?")
_VIDEO = re.compile(r"incremento_open_video:(\d+):([0-9.]+)")
_OLD_PDF = re.compile(r"incremento_open_pdf:(\d+):(\d+)")


def note_field(note, key):
    try:
        return str(note[key] or "").strip()
    except (KeyError, TypeError, AttributeError):
        return ""


def file_signature(path):
    info = Path(path).stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def resolve_recording(addon_dir, profile, collection, card_id):
    if type(card_id) is not int or not 1 <= card_id <= 2**53 - 1:
        raise ValueError("Recording unavailable")
    try:
        note = collection.get_note(collection.get_card(card_id).nid)
    except Exception as error:
        # Anki's missing-card exceptions differ across supported releases.
        raise ValueError("Local recording unavailable") from error
    try:
        kind = (note.note_type() or {}).get("name")
        if kind == "Incremento Video":
            media = get_video_note_media(note)
            raw = local_video_abspath(addon_dir, profile, media["local_video_file"])
            root = get_videos_dir(addon_dir, profile).resolve()
            path = Path(raw).resolve()
            if not raw or path.suffix.lower() not in supported_local_video_extensions():
                raise ValueError("A local recording is required")
            kind = "video"
        elif kind == "Incremento Audio":
            raw = note_field(note, "Audio_Filename")
            if not raw or Path(raw).name != raw or "/" in raw or "\\" in raw or "\0" in raw:
                raise ValueError("Audio media unavailable")
            root = Path(collection.media.dir()).resolve()
            path = (root / raw).resolve()
            kind = "audio"
        else:
            raise ValueError("Unsupported recording card")
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Local recording unavailable")
        return dict(card_id=card_id, kind=kind, title=note_field(note, "Title")[:240] or path.stem,
                    path=str(path), signature=file_signature(path))
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError("Local recording unavailable") from error


def list_recordings(addon_dir, profile, collection):
    """Explicit library picker: one bounded background query, no startup scan."""
    ids = collection.db.list(
        "SELECT min(c.id) FROM cards c JOIN notes n ON n.id=c.nid JOIN notetypes m ON m.id=n.mid "
        "WHERE m.name IN (?,?) GROUP BY n.id ORDER BY n.id DESC LIMIT ?",
        "Incremento Video", "Incremento Audio", MAX_RECORDINGS + 1,
    )
    rows = []
    for cid in ids[:MAX_RECORDINGS]:
        try:
            rows.append({**resolve_recording(addon_dir, profile, collection, int(cid)), "available": True})
        except ValueError:
            try:
                note = collection.get_note(collection.get_card(cid).nid)
                title = note_field(note, "Title")[:240]
            except Exception:
                continue
            rows.append(dict(card_id=int(cid), title=title, available=False))
    return rows, len(ids) > MAX_RECORDINGS


def _note_text(note):
    # Existing citations are data. No HTML or Python/JavaScript is executed.
    return unescape("\n".join(str(v)[:200_000] for v in list(note.fields)[:80])[:400_000]).replace('\\"', '"')


def inline_locations(text):
    result = []
    prefix = "incremento_open_pdf_ref:"
    for part in text.split(prefix)[1:MAX_RESOURCES + 1]:
        try:
            data, _ = json.JSONDecoder().raw_decode(part)
            result.append(normalize_source(dict(kind="pdf", card_id=data["card_id"], page=data["page"],
                scroll=data.get("scroll_ratio") or 0, page_y=data.get('page_y'),
                quote=str(data.get("excerpt") or "")[:2000])))
        except (ValueError, TypeError, KeyError):
            continue
    for match in list(_OLD_PDF.finditer(text))[:MAX_RESOURCES]:
        try:
            result.append(normalize_source(dict(kind="pdf", card_id=int(match[1]), page=int(match[2]))))
        except ValueError:
            continue
    for match in list(_EPUB.finditer(text))[:MAX_RESOURCES]:
        try:
            result.append(normalize_source(dict(kind="epub", card_id=int(match[1]), section=int(match[2]),
                offset=int(match[3]), scroll=float(match[4] or 0))))
        except ValueError:
            continue
    return result[:MAX_RESOURCES]


def source_locations(addon_dir, profile, collection, card_id):
    card = collection.get_card(card_id)
    note = collection.get_note(card.nid)
    sources = inline_locations(_note_text(note))
    conn = get_connection(addon_dir, profile)
    for row in list_document_links(addon_dir, profile, card_id)[:MAX_RESOURCES]:
        if row["target_card_id"] > 0:
            sources.append(dict(kind="pdf", card_id=row["target_card_id"], page=row["target_page"],
                                scroll=row["target_scroll"], page_y=row.get("target_y"), quote=row["quote"]))
    for cid, page, quote in conn.execute(
        "SELECT pdf_card_id,page,excerpt FROM pdf_card_sources WHERE note_id=? ORDER BY id LIMIT ?",
        (card.nid, MAX_RESOURCES),
    ).fetchall():
        sources.append(dict(kind="pdf", card_id=cid, page=page, quote=str(quote)[:2000]))
    for cid, section, quote in conn.execute(
        "SELECT epub_card_id,section_index,excerpt FROM epub_card_sources WHERE note_id=? ORDER BY id LIMIT ?",
        (card.nid, MAX_RESOURCES),
    ).fetchall():
        sources.append(dict(kind="epub", card_id=cid, section=section, quote=str(quote)[:2000]))
    result, seen = [], set()
    for source in sources:
        try:
            source = normalize_source(source)
        except ValueError:
            continue
        key = (source["kind"], source["card_id"], source.get("page", source.get("section")))
        if key not in seen:
            seen.add(key)
            result.append(source)
        if len(result) >= MAX_RESOURCES:
            break
    return result


def resolve_document(addon_dir, profile, collection, source):
    source = normalize_source(source)
    if source["kind"] == "pdf":
        snapshot = resolve_pdf_reference(addon_dir, profile, collection, source["card_id"])
        status = get_pdf_daily_limit_status(addon_dir, profile, source["card_id"],
                                           count_current_page=False, persist_usage=False)
        maximum = maximum_reference_page(status)
        if source["page"] > maximum:
            raise ValueError("Reference page is locked")
        return {**snapshot, "max_page": maximum}
    if source["kind"] == "epub":
        snapshot = resolve_epub_reference(addon_dir, profile, collection, source["card_id"])
        validate_location(snapshot, source)
        status = get_epub_daily_limit_status(addon_dir, profile, source["card_id"],
                                            count_current_page=False, persist_usage=False)
        if not location_allowed(source, status):
            raise ValueError("Reference passage is locked")
        return {**snapshot, 'path': snapshot['paths'][source['section']]}
    raise ValueError("A document source is required")


def resolve_link_rows(addon_dir, profile, collection, rows):
    result = []
    for row in rows[:200]:
        try:
            recording = resolve_recording(addon_dir, profile, collection, row["recording_card_id"])
            result.append({**row, "recording": recording, "available": True})
        except ValueError:
            result.append({**row, "recording": None, "available": False})
    return result


def load_card_resources(addon_dir, profile, collection, card_id):
    sources = source_locations(addon_dir, profile, collection, card_id)
    documents, recordings = [], []
    for source in sources:
        try:
            snapshot = resolve_document(addon_dir, profile, collection, source)
            documents.append(dict(location=source, title=snapshot["title"], available=True))
        except ValueError:
            documents.append(dict(location=source, title="", available=False))
        recordings.extend(list_recording_links(addon_dir, profile, source=source))
    direct = dict(kind="card", card_id=card_id)
    recordings.extend(list_recording_links(addon_dir, profile, source=direct))
    # Video extracts already contain exact source timestamps; retain those too.
    note = collection.get_note(collection.get_card(card_id).nid)
    for match in list(_VIDEO.finditer(_note_text(note)))[:MAX_RESOURCES]:
        try:
            start, _ = validate_segment(float(match[2]))
            recordings.append(dict(id=0, source=normalize_source(direct), recording_card_id=int(match[1]),
                                   start=start, end=None, label=""))
        except ValueError:
            continue
    unique = {}
    for row in recordings:
        unique.setdefault((row["recording_card_id"], row["start"], row["end"]), row)
    return dict(documents=documents, recordings=resolve_link_rows(
        addon_dir, profile, collection, list(unique.values())[:MAX_RESOURCES]))
