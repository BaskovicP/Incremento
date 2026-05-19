import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from PyQt6.QtPdf import QPdfDocument

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_STEM = 80
_PDF_DISPLAY_LABEL_MAX_LEN = 48
_PDF_UUID_SUFFIX_RE = re.compile(r"^(?P<label>.+)-(?P<uuid>[0-9a-f]{32})$", re.IGNORECASE)


def _safe_pdf_stem(raw_name: str, fallback: str = "document") -> str:
    stem = _SAFE_FILENAME_RE.sub("_", str(raw_name or "").strip()).strip("._-")
    stem = stem[:_MAX_FILENAME_STEM].strip("._-")
    return stem or fallback


def pdf_display_label_from_filename(filename: str, fallback: str = "PDF") -> str:
    """Return a short readable label for a stored PDF filename."""
    stem = os.path.splitext(os.path.basename(str(filename or "").strip()))[0].strip("._-")
    if not stem:
        return fallback

    match = _PDF_UUID_SUFFIX_RE.match(stem)
    if match:
        stem = match.group("label").strip("._-")

    stem = re.sub(r"[_-]+", " ", stem).strip()
    if len(stem) > _PDF_DISPLAY_LABEL_MAX_LEN:
        stem = stem[:_PDF_DISPLAY_LABEL_MAX_LEN].rstrip(" ._-")
    return stem or fallback


def find_live_pdf_card_by_filename(col, filename: str) -> int | None:
    clean_filename = os.path.basename(str(filename or "").strip())
    if not clean_filename:
        return None
    try:
        note_ids = col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
    except Exception:
        return None
    for nid in note_ids:
        try:
            note = col.get_note(nid)
            stored = str(note["PDF_Filename"] or "").strip()
        except Exception:
            continue
        if os.path.basename(stored) == clean_filename:
            try:
                cids = col.find_cards(f"nid:{nid}")
            except Exception:
                cids = []
            if cids:
                try:
                    return int(cids[0])
                except Exception:
                    return None
    return None

try:
    from .db import (
        get_connection,
        get_pdf_card_sources_up_to_page,
        get_pdf_daily_limit_config,
        get_pdf_due_review_prompt_config,
        get_pdf_daily_limit_usage,
        replace_pdf_text_index,
        set_pdf_daily_limit_config,
        set_pdf_due_review_prompt_config,
        set_pdf_daily_limit_usage,
    )
    from . import paths as _paths
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        INCREMENTO_IMPORTED_AT_FIELD,
        INCREMENTO_PARENT_CARD_ID_FIELD,
        INCREMENTO_PARENT_FIELD,
        INCREMENTO_SOURCE_AUTHOR_FIELD,
    )
    from .scheduler_config import build_ready_filter, load_scheduler_config
    from .statistics import _effective_date
except ImportError:
    from db import (  # test environment
        get_connection,
        get_pdf_card_sources_up_to_page,
        get_pdf_daily_limit_config,
        get_pdf_due_review_prompt_config,
        get_pdf_daily_limit_usage,
        replace_pdf_text_index,
        set_pdf_daily_limit_config,
        set_pdf_due_review_prompt_config,
        set_pdf_daily_limit_usage,
    )
    import paths as _paths
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        INCREMENTO_IMPORTED_AT_FIELD,
        INCREMENTO_PARENT_CARD_ID_FIELD,
        INCREMENTO_PARENT_FIELD,
        INCREMENTO_SOURCE_AUTHOR_FIELD,
    )
    from scheduler_config import build_ready_filter, load_scheduler_config  # type: ignore
    from statistics import _effective_date  # type: ignore


def get_pdf_dir() -> str:
    """Return (and create) the addon's user_files/<profile>/pdfs/ folder."""
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    d = str(_paths.get_pdf_dir(addon_dir, _paths.get_active_profile()))
    os.makedirs(d, exist_ok=True)
    return d


def pdf_storage_abspath(stored_filename: str) -> str:
    """Resolve a stored PDF filename inside the managed profile PDF directory."""
    raw = str(stored_filename or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("user_files/") and "/pdfs/" in raw:
        raw = raw.split("/pdfs/", 1)[1]
    elif raw.startswith("pdfs/"):
        raw = raw[len("pdfs/"):]

    root = Path(get_pdf_dir()).resolve()
    raw_path = Path(raw)
    candidate = raw_path.resolve() if raw_path.is_absolute() else (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return ""
    return str(candidate)


def _copy_to_pdf_dir(pdf_path: str) -> str:
    """Copy *pdf_path* into the profile PDF dir; return the stored filename.

    Stored filenames always get a UUID suffix so repeated imports never reuse
    an older file just because the basename matches.
    """
    pdf_dir = get_pdf_dir()
    raw_name = os.path.basename(pdf_path)
    stem, ext = os.path.splitext(raw_name)
    stem = _safe_pdf_stem(stem, fallback="document")
    ext = ext if ext.lower() == ".pdf" else ".pdf"
    dest_name = f"{stem}-{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(pdf_dir, dest_name)

    shutil.copy2(pdf_path, dest_path)
    return dest_name

PDF_NOTE_TYPE = "Incremento PDF"
PDF_COVER_FIELD = "PDF_Cover_Image"
_PDF_COVER_RENDER_WIDTH = 360

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:36px 20px 44px; font-family:sans-serif; color:#888;">
  {{#PDF_Cover_Image}}
    <div style="margin:0 auto 22px; max-width:340px;">
      <img
        src="{{PDF_Cover_Image}}"
        alt="{{Title}} cover"
        style="display:block; width:100%; height:auto; border-radius:14px; box-shadow:0 16px 42px rgba(0,0,0,0.28);"
      >
    </div>
  {{/PDF_Cover_Image}}
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">PDF open in sidebar &nbsp;·&nbsp; select text → ⌘C → ⌘1–4 to fill fields</div>
</div>
<div style="display:none;">{{PDF_Filename}}</div>
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


def _stored_pdf_title(title: str, attempt: int) -> str:
    base_title = str(title or "").strip() or "Untitled"
    if attempt <= 0:
        return base_title
    return f"{base_title} [{attempt + 1}]"


# ---------------------------------------------------------------------------
# Page progress I/O
# ---------------------------------------------------------------------------


def get_page(addon_dir: str, profile: str, card_id: int) -> int:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT page FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 1


def get_zoom(addon_dir: str, profile: str, card_id: int) -> float:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT zoom FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 1.0


def set_page(addon_dir: str, profile: str, card_id: int, page: int) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, ?, 1.0) "
        "ON CONFLICT(card_id) DO UPDATE SET page = excluded.page",
        (card_id, page),
    )
    conn.commit()


def set_zoom(addon_dir: str, profile: str, card_id: int, zoom: float) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, 1, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET zoom = excluded.zoom",
        (card_id, round(float(zoom), 2)),
    )
    conn.commit()


def get_read_page(addon_dir: str, profile: str, card_id: int) -> int:
    """Return the highest page marked as read (0 = nothing marked yet)."""
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT read_page FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 0


def _normalize_read_anchor(anchor) -> dict:
    if not isinstance(anchor, dict):
        return {}

    text = str(anchor.get("text") or "").strip()
    try:
        page = max(1, int(anchor.get("page", 1) or 1))
    except Exception:
        page = 1

    def _coord(name: str, default: float = 0.0) -> float:
        try:
            value = float(anchor.get(name, default) or default)
        except Exception:
            value = default
        return round(max(0.0, value), 3)

    normalized = {
        "page": page,
        "x": _coord("x"),
        "y": _coord("y"),
        "w": _coord("w"),
        "h": _coord("h"),
    }
    if text:
        normalized["text"] = text[:240]
    return normalized


def get_read_anchor(addon_dir: str, profile: str, card_id: int) -> dict | None:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT read_anchor_json FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    if not row or not str(row[0] or "").strip():
        return None
    try:
        return _normalize_read_anchor(json.loads(row[0] or "{}")) or None
    except Exception:
        return None


def set_read_page(
    addon_dir: str,
    profile: str,
    card_id: int,
    read_page: int,
    read_anchor: dict | None = None,
) -> None:
    conn = get_connection(addon_dir, profile)
    anchor_json = ""
    if int(read_page or 0) > 0 and read_anchor:
        normalized_anchor = _normalize_read_anchor(read_anchor)
        if normalized_anchor:
            anchor_json = json.dumps(normalized_anchor, ensure_ascii=False, sort_keys=True)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom, read_page, read_anchor_json) "
        "VALUES (?, 1, 1.0, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "read_page = excluded.read_page, "
        "read_anchor_json = excluded.read_anchor_json",
        (card_id, read_page, anchor_json),
    )
    conn.commit()


_PDF_LIMIT_MODE_LABELS = {
    "warning": "Warning",
    "soft_lock": "Soft Lock",
    "hard_stop": "Hard Stop",
}
_DEFAULT_DAY_END_TIME = "04:00"


def _current_day_end_time() -> str:
    try:
        cfg = load_scheduler_config()
        day_end_time = str(
            getattr(cfg, "day_end_time", _DEFAULT_DAY_END_TIME) or _DEFAULT_DAY_END_TIME
        ).strip()
    except Exception:
        day_end_time = _DEFAULT_DAY_END_TIME
    return day_end_time or _DEFAULT_DAY_END_TIME


def get_pdf_limit_mode_label(mode: str) -> str:
    return _PDF_LIMIT_MODE_LABELS.get(str(mode or "").strip().lower(), "Warning")


def get_pdf_daily_limit_settings(addon_dir: str, profile: str, card_id: int) -> dict:
    config = get_pdf_daily_limit_config(addon_dir, profile, card_id)
    limit = int(config.get("daily_page_limit", 0) or 0)
    mode = str(config.get("enforcement_mode") or "warning").strip().lower()
    if mode not in _PDF_LIMIT_MODE_LABELS:
        mode = "warning"
    return {
        "enabled": limit > 0,
        "daily_page_limit": limit,
        "enforcement_mode": mode,
        "enforcement_label": get_pdf_limit_mode_label(mode),
        "updated_at": int(config.get("updated_at", 0) or 0),
    }


def save_pdf_daily_limit_settings(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
    daily_page_limit: int,
    enforcement_mode: str,
) -> dict:
    limit = int(daily_page_limit or 0)
    if not enabled or limit <= 0:
        set_pdf_daily_limit_config(
            addon_dir,
            profile,
            card_id,
            daily_page_limit=0,
            enforcement_mode=enforcement_mode,
        )
        return get_pdf_daily_limit_settings(addon_dir, profile, card_id)

    set_pdf_daily_limit_config(
        addon_dir,
        profile,
        card_id,
        daily_page_limit=limit,
        enforcement_mode=enforcement_mode,
    )
    return get_pdf_daily_limit_settings(addon_dir, profile, card_id)


def get_pdf_due_review_prompt_settings(addon_dir: str, profile: str, card_id: int) -> dict:
    config = get_pdf_due_review_prompt_config(addon_dir, profile, card_id)
    return {
        "enabled": bool(config.get("enabled", True)),
        "updated_at": int(config.get("updated_at", 0) or 0),
    }


def save_pdf_due_review_prompt_settings(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
) -> dict:
    set_pdf_due_review_prompt_config(
        addon_dir,
        profile,
        card_id,
        enabled=bool(enabled),
    )
    return get_pdf_due_review_prompt_settings(addon_dir, profile, card_id)


def _plain_first_field(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return " ".join(text.split()).strip()


def get_due_pdf_source_cards(
    addon_dir: str,
    profile: str,
    pdf_card_id: int,
    max_page: int,
    *,
    col=None,
) -> list[dict]:
    """Return due/learning extracted cards from this PDF up to max_page."""
    max_pg = max(0, int(max_page or 0))
    if max_pg <= 0:
        return []

    source_rows = get_pdf_card_sources_up_to_page(addon_dir, profile, int(pdf_card_id), max_pg)
    if not source_rows:
        return []

    source_by_note: dict[int, dict] = {}
    for row in source_rows:
        note_id = int(row.get("note_id", 0) or 0)
        if note_id <= 0 or note_id in source_by_note:
            continue
        source_by_note[note_id] = {
            "page": int(row.get("page", 0) or 0),
            "excerpt": str(row.get("excerpt") or "").strip(),
        }
    if not source_by_note:
        return []

    if col is None:
        from aqt import mw

        col = mw.col

    note_ids = sorted(source_by_note)
    note_query = " OR ".join(f"nid:{nid}" for nid in note_ids)
    ready_filter = build_ready_filter(
        include_new=False,
        include_learning=True,
        include_due=True,
    )
    try:
        due_card_ids = list(col.find_cards(f"({note_query}) {ready_filter}"))
    except Exception:
        return []

    rows: list[dict] = []
    for card_id in due_card_ids:
        try:
            card = col.get_card(int(card_id))
        except Exception:
            continue
        if card is None:
            continue
        source = source_by_note.get(int(getattr(card, "nid", 0) or 0))
        if not source:
            continue
        try:
            note = col.get_note(card.nid)
        except Exception:
            continue
        if note is None:
            continue
        fields = getattr(note, "fields", []) or []
        title = _plain_first_field(fields[0] if fields else f"Card {card.id}") or f"Card {card.id}"
        queue = int(getattr(card, "queue", 0) or 0)
        due_value = getattr(card, "due", 0)
        try:
            due_value = int(due_value or 0)
        except Exception:
            due_value = 0
        rows.append(
            {
                "card_id": int(card.id),
                "note_id": int(card.nid),
                "page": int(source["page"]),
                "title": title,
                "excerpt": str(source["excerpt"] or ""),
                "queue": queue,
                "due": due_value,
                "due_state": "learning" if queue in {1, 3} else "due",
            }
        )

    rows.sort(key=lambda row: (int(row["page"]), int(row["due"]), int(row["card_id"])))
    return rows


def get_pdf_daily_limit_status(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    current_page: int | None = None,
    count_current_page: bool = True,
    persist_usage: bool = True,
) -> dict:
    settings = get_pdf_daily_limit_settings(addon_dir, profile, card_id)
    page = max(1, int(current_page or get_page(addon_dir, profile, card_id) or 1))
    day_end_time = _current_day_end_time()
    logical_date = _effective_date(day_end_time)

    status = {
        "enabled": settings["enabled"],
        "daily_page_limit": settings["daily_page_limit"],
        "enforcement_mode": settings["enforcement_mode"],
        "enforcement_label": settings["enforcement_label"],
        "logical_date": logical_date,
        "day_end_time": day_end_time,
        "current_page": page,
        "baseline_page": max(0, page - 1),
        "highest_page": page if count_current_page else max(0, page - 1),
        "pages_used": 0,
        "pages_remaining": 0,
        "allowed_max_page": None,
        "override_enabled": False,
        "limit_reached": False,
        "blocking_active": False,
        "can_override": False,
    }

    if not settings["enabled"]:
        return status

    usage = get_pdf_daily_limit_usage(addon_dir, profile, card_id, logical_date)
    baseline_page = int(usage.get("baseline_page", 0) or 0)
    highest_page = int(usage.get("highest_page", 0) or 0)
    override_enabled = bool(usage.get("override_enabled"))

    if baseline_page <= 0 and highest_page <= 0:
        baseline_page = max(0, page - 1)
        highest_page = page if count_current_page else baseline_page
        if persist_usage:
            set_pdf_daily_limit_usage(
                addon_dir,
                profile,
                card_id,
                logical_date,
                baseline_page=baseline_page,
                highest_page=highest_page,
                override_enabled=override_enabled,
            )
    elif count_current_page and page > highest_page:
        highest_page = page
        if persist_usage:
            set_pdf_daily_limit_usage(
                addon_dir,
                profile,
                card_id,
                logical_date,
                baseline_page=baseline_page,
                highest_page=highest_page,
                override_enabled=override_enabled,
            )

    daily_limit = int(settings["daily_page_limit"] or 0)
    pages_used = max(0, highest_page - baseline_page)
    allowed_max_page = baseline_page + daily_limit if daily_limit > 0 else None
    pages_remaining = max(0, daily_limit - pages_used) if daily_limit > 0 else 0
    limit_reached = bool(daily_limit > 0 and pages_used >= daily_limit)
    blocking_active = bool(
        daily_limit > 0
        and settings["enforcement_mode"] in {"soft_lock", "hard_stop"}
        and not override_enabled
        and limit_reached
    )

    status.update(
        {
            "baseline_page": baseline_page,
            "highest_page": highest_page,
            "pages_used": pages_used,
            "pages_remaining": pages_remaining,
            "allowed_max_page": allowed_max_page,
            "override_enabled": override_enabled,
            "limit_reached": limit_reached,
            "blocking_active": blocking_active,
            "can_override": bool(
                settings["enforcement_mode"] == "soft_lock"
                and daily_limit > 0
                and not override_enabled
            ),
        }
    )
    return status


def set_pdf_daily_limit_override(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
    current_page: int | None = None,
) -> dict:
    settings = get_pdf_daily_limit_settings(addon_dir, profile, card_id)
    if not settings["enabled"]:
        return get_pdf_daily_limit_status(
            addon_dir,
            profile,
            card_id,
            current_page=current_page,
        )

    page = max(1, int(current_page or get_page(addon_dir, profile, card_id) or 1))
    logical_date = _effective_date(_current_day_end_time())
    usage = get_pdf_daily_limit_usage(addon_dir, profile, card_id, logical_date)
    baseline_page = int(usage.get("baseline_page", 0) or max(0, page - 1))
    highest_page = int(usage.get("highest_page", 0) or page)
    if page > highest_page:
        highest_page = page
    set_pdf_daily_limit_usage(
        addon_dir,
        profile,
        card_id,
        logical_date,
        baseline_page=baseline_page,
        highest_page=highest_page,
        override_enabled=bool(enabled),
    )
    return get_pdf_daily_limit_status(
        addon_dir,
        profile,
        card_id,
        current_page=page,
    )


# ---------------------------------------------------------------------------
# Note type management
# ---------------------------------------------------------------------------


def extract_pdf_pages_text(pdf_path: str, *, allow_qt: bool = True) -> list[str]:
    """Extract per-page text from a PDF.

    Extraction order:
      1. PyMuPDF (fitz) — handles Tesseract invisible-text layers (rendering
         mode 3) and is safe to call from background threads.
      2. Qt QPdfDocument — fast for regular PDFs; skips invisible text.
      3. pdftotext (poppler) — last resort external binary.
    """
    # 1. PyMuPDF — best at reading Tesseract OCR output
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = [doc.load_page(i).get_text("text").strip() for i in range(len(doc))]
        doc.close()
        if any(pages):
            return pages
    except Exception:
        pass

    # 2. Qt QPdfDocument
    if allow_qt:
        doc = QPdfDocument(None)
        try:
            doc.load(pdf_path)
            if doc.pageCount() > 0:
                pages = []
                for i in range(doc.pageCount()):
                    sel = doc.getAllText(i)
                    pages.append(sel.text().strip() if sel.isValid() else "")
                if any(pages):
                    return pages
        except Exception:
            pass
        finally:
            doc.close()

    # 3. pdftotext (poppler)
    _candidates = [
        shutil.which("pdftotext"),
        "/opt/homebrew/bin/pdftotext",
        "/usr/local/bin/pdftotext",
        "/usr/bin/pdftotext",
    ]
    exe = next((c for c in _candidates if c and os.path.isfile(c)), None)
    if exe:
        try:
            proc = subprocess.run(
                [exe, "-layout", "-enc", "UTF-8", pdf_path, "-"],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                parts = [p.strip() for p in (proc.stdout or "").split("\f")]
                while parts and not parts[-1]:
                    parts.pop()
                if parts:
                    return parts
        except Exception:
            pass

    return []


def extract_pdf_text(pdf_path: str) -> str:
    pages = extract_pdf_pages_text(pdf_path)
    return "\n\n".join([p for p in pages if p]).strip()

    return ""


def render_pdf_cover_media(col, pdf_path: str, *, title: str = "", source_filename: str = "") -> str:
    """Render the first PDF page to Anki media and return the stored media filename."""
    if not pdf_path or not os.path.exists(pdf_path):
        raise FileNotFoundError("PDF file was not found.")

    try:
        from PyQt6.QtCore import QSize
    except Exception:
        return ""

    doc = QPdfDocument(None)
    try:
        doc.load(pdf_path)
        if doc.pageCount() <= 0:
            return ""

        render_w = _PDF_COVER_RENDER_WIDTH
        render_h = int(render_w * 1.414)
        try:
            page_size = doc.pagePointSize(0)
            width = float(page_size.width() or 0)
            height = float(page_size.height() or 0)
            if width > 0 and height > 0:
                render_h = max(1, int(render_w * height / width))
        except Exception:
            pass

        image = doc.render(0, QSize(render_w, render_h))
        if image is None or image.isNull():
            return ""

        stem_source = title or source_filename or os.path.splitext(os.path.basename(pdf_path))[0]
        image_name = f"{_safe_pdf_stem(stem_source, fallback='pdf_cover')}-cover-{uuid.uuid4().hex}.png"
        tmp_dir = tempfile.mkdtemp(prefix="incremento-pdf-cover-")
        tmp_path = os.path.join(tmp_dir, image_name)
        try:
            if not image.save(tmp_path, "PNG"):
                return ""
            return str(col.media.add_file(tmp_path) or "").strip()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass
    except Exception:
        return ""
    finally:
        doc.close()


def regenerate_pdf_note_cover(col, note, pdf_path: str) -> str:
    """Refresh a PDF note's stored cover media reference and persist the note."""
    ensure_pdf_note_type(col)
    cover_media = render_pdf_cover_media(
        col,
        pdf_path,
        title=str(note["Title"] or "").strip(),
        source_filename=str(note["PDF_Filename"] or "").strip(),
    )
    note[PDF_COVER_FIELD] = cover_media
    col.update_note(note)
    return cover_media


def regenerate_pdf_card_cover(addon_dir: str, col, card_id: int) -> str:
    """Regenerate the stored cover preview for an existing PDF card."""
    cid = int(card_id)
    card = col.get_card(cid)
    if card is None:
        raise RuntimeError("PDF card was not found.")
    note = col.get_note(card.nid)
    if note is None:
        raise RuntimeError("Linked PDF note was not found.")

    pdf_filename = str(note["PDF_Filename"] or "").strip()
    if not pdf_filename:
        raise RuntimeError("This PDF note does not have a stored PDF filename.")

    pdf_path = pdf_storage_abspath(pdf_filename)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Stored PDF file was not found:\n{pdf_path}")

    return regenerate_pdf_note_cover(col, note, pdf_path)


def ensure_pdf_note_type(col) -> None:
    """Create the Incremento PDF note type, or update its template/fields if it already exists."""
    models = col.models
    m = models.by_name(PDF_NOTE_TYPE)

    if m is None:
        m = models.new(PDF_NOTE_TYPE)
        for field_name in ("Title", "PDF_Filename", PDF_COVER_FIELD):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        ensure_incremento_metadata_fields(models, m)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        changed = False
        existing_fields = {str((field or {}).get("name") or "") for field in list(m.get("flds") or [])}
        for field_name in ("Title", "PDF_Filename", PDF_COVER_FIELD):
            if field_name in existing_fields:
                continue
            fld = models.new_field(field_name)
            models.add_field(m, fld)
            changed = True
        if ensure_incremento_metadata_fields(models, m):
            changed = True
        # Sync template
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            changed = True
        if changed:
            models.update_dict(m)


# ---------------------------------------------------------------------------
# Card creation
# ---------------------------------------------------------------------------


def _find_bin(*candidates: str) -> str | None:
    """Return the first existing executable path from candidates."""
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def ocr_pdf_in_place(pdf_path: str, progress_cb=None) -> bool:
    """OCR a scanned PDF and replace it with a searchable version.

    Pipeline:
      1. PyMuPDF renders all pages to PNG at 200 DPI (sequential — fitz is not thread-safe)
      2. Tesseract OCRs all pages in parallel (ThreadPoolExecutor, one thread per core)
      3. PyMuPDF merges the per-page PDFs (no pdfunite dependency)
      4. The merged file replaces the original

    Falls back to ocrmypdf if Tesseract is unavailable.
    Returns True on success, False if required tools are missing or OCR fails.
    """
    import tempfile
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # --- preferred pipeline: tesseract + PyMuPDF ---------------------------
    tesseract = _find_bin(
        shutil.which("tesseract"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    )

    if tesseract:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            pass
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Step 1: render all pages to PNG (sequential — fitz not thread-safe)
                img_paths: list[str] = []
                out_bases: list[str] = []
                total_pages = 0
                try:
                    doc = fitz.open(pdf_path)
                    total_pages = len(doc)
                    mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI
                    for i in range(total_pages):
                        pix = doc.load_page(i).get_pixmap(matrix=mat)
                        img_path = os.path.join(tmpdir, f"p{i:04d}.png")
                        pix.save(img_path)
                        img_paths.append(img_path)
                        out_bases.append(os.path.join(tmpdir, f"p{i:04d}"))
                    doc.close()
                except Exception:
                    total_pages = 0

                if total_pages == 0:
                    pass  # fall through to ocrmypdf
                else:
                    # Step 2: OCR all pages in parallel
                    page_pdfs: dict[int, str] = {}
                    workers = min(os.cpu_count() or 1, total_pages, 8)
                    done_count = 0
                    failed = False

                    def _ocr_page(i: int):
                        proc = subprocess.run(
                            [tesseract, img_paths[i], out_bases[i], "pdf"],
                            capture_output=True,
                            timeout=120,
                        )
                        return i, proc.returncode == 0

                    try:
                        with ThreadPoolExecutor(max_workers=workers) as pool:
                            futs = {pool.submit(_ocr_page, i): i for i in range(total_pages)}
                            for fut in as_completed(futs):
                                i, ok = fut.result()
                                if not ok:
                                    failed = True
                                    break
                                page_pdfs[i] = out_bases[i] + ".pdf"
                                done_count += 1
                                if progress_cb:
                                    progress_cb(done_count, total_pages)
                    except Exception:
                        failed = True

                    if not failed and len(page_pdfs) == total_pages:
                        # Step 3: merge with PyMuPDF (no pdfunite needed)
                        try:
                            merged_doc = fitz.open()
                            for i in range(total_pages):
                                with fitz.open(page_pdfs[i]) as part:
                                    merged_doc.insert_pdf(part)
                            merged_path = os.path.join(tmpdir, "merged.pdf")
                            merged_doc.save(merged_path)
                            merged_doc.close()
                            if os.path.getsize(merged_path) > 0:
                                shutil.move(merged_path, pdf_path)
                                return True
                        except Exception:
                            pass

    # --- fallback: ocrmypdf ------------------------------------------------
    ocrmypdf = _find_bin(
        shutil.which("ocrmypdf"),
        "/opt/homebrew/bin/ocrmypdf",
        "/usr/local/bin/ocrmypdf",
        "/usr/bin/ocrmypdf",
    )
    if not ocrmypdf:
        return False

    import tempfile as _tempfile
    fd, tmp_path = _tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        proc = subprocess.run(
            [ocrmypdf, "--skip-text", "--quiet", pdf_path, tmp_path],
            capture_output=True,
            timeout=300,
        )
        if proc.returncode == 0 and os.path.getsize(tmp_path) > 0:
            shutil.move(tmp_path, pdf_path)
            return True
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return False


def add_pdf_card(
    addon_dir: str,
    col,
    pdf_path: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
    daily_page_limit: int | None = None,
    enforcement_mode: str = "warning",
    precomputed_page_texts: list[str] | None = None,
) -> int:
    """Copy PDF to media, create note, return card id."""
    ensure_pdf_note_type(col)

    # Copy file to profile-local PDF dir (not Anki media, so it won't sync)
    media_filename = _copy_to_pdf_dir(pdf_path)
    dest_path = os.path.join(get_pdf_dir(), media_filename)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(PDF_NOTE_TYPE)

    page_texts = (
        list(precomputed_page_texts)
        if precomputed_page_texts is not None
        else extract_pdf_pages_text(dest_path)
    )
    cover_media = render_pdf_cover_media(
        col,
        dest_path,
        title=title,
        source_filename=media_filename,
    )

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note["PDF_Filename"] = media_filename
        note[PDF_COVER_FIELD] = cover_media
        apply_incremento_metadata(
            note,
            metadata
            or build_incremento_metadata(
                source_type="PDF",
                source_title=title,
                source_link=f"pdfs/{media_filename}",
            ),
        )
        for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
            if not tag:
                continue
            if hasattr(note, "add_tag"):
                note.add_tag(tag)
            elif hasattr(note, "tags"):
                note.tags.append(tag)
        note.note_type()["did"] = deck_id
        return note

    cid = 0
    for attempt in range(25):
        stored_title = _stored_pdf_title(title, attempt)
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            cid = cards[0]
            break
    if not cid:
        raise RuntimeError("Failed to add PDF card. Anki rejected the note.")

    try:
        replace_pdf_text_index(addon_dir, _paths.get_active_profile(), cid, page_texts)
    except Exception:
        pass
    try:
        save_pdf_daily_limit_settings(
            addon_dir,
            _paths.get_active_profile(),
            cid,
            enabled=bool(int(daily_page_limit or 0) > 0),
            daily_page_limit=int(daily_page_limit or 0),
            enforcement_mode=enforcement_mode,
        )
    except Exception:
        pass
    return cid


def replace_pdf_card_file(addon_dir: str, col, card_id: int, pdf_path: str) -> str:
    """Copy a replacement PDF into storage and relink an existing PDF card."""
    ensure_pdf_note_type(col)
    cid = int(card_id)
    if not pdf_path or not os.path.exists(pdf_path):
        raise FileNotFoundError("Replacement PDF was not found.")

    card = col.get_card(cid)
    if card is None:
        raise RuntimeError("PDF card was not found.")
    note = col.get_note(card.nid)
    if note is None:
        raise RuntimeError("Linked PDF note was not found.")

    media_filename = _copy_to_pdf_dir(pdf_path)
    dest_path = os.path.join(get_pdf_dir(), media_filename)
    page_texts = extract_pdf_pages_text(dest_path)

    note["PDF_Filename"] = media_filename
    note[PDF_COVER_FIELD] = render_pdf_cover_media(
        col,
        dest_path,
        title=str(note["Title"] or "").strip(),
        source_filename=media_filename,
    )
    try:
        current_author = str(note[INCREMENTO_SOURCE_AUTHOR_FIELD] or "").strip()
    except Exception:
        current_author = ""
    metadata = build_incremento_metadata(
        source_type="PDF",
        source_title=str(note["Title"] or "").strip(),
        source_link=f"pdfs/{media_filename}",
        source_author=current_author,
    )
    for field_name in (
        INCREMENTO_IMPORTED_AT_FIELD,
        INCREMENTO_PARENT_FIELD,
        INCREMENTO_PARENT_CARD_ID_FIELD,
    ):
        try:
            current_value = str(note[field_name] or "").strip()
        except Exception:
            current_value = ""
        if current_value:
            metadata[field_name] = current_value
    apply_incremento_metadata(note, metadata)
    col.update_note(note)

    try:
        replace_pdf_text_index(addon_dir, _paths.get_active_profile(), cid, page_texts)
    except Exception:
        pass
    return media_filename
