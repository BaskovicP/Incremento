from __future__ import annotations

import os
import re
import subprocess
from html import unescape
from urllib.parse import unquote, urlparse

from aqt import mw

try:
    from .db import replace_note_ocr_index
    from .deps import has_tesseract, tesseract_path, tesseract_instructions
    from .note_metadata import INCREMENTO_OCR_TEXT_FIELD, ensure_incremento_ocr_field
except ImportError:
    from db import replace_note_ocr_index  # type: ignore
    from deps import has_tesseract, tesseract_path, tesseract_instructions  # type: ignore
    from note_metadata import INCREMENTO_OCR_TEXT_FIELD, ensure_incremento_ocr_field  # type: ignore


_IMG_SRC_RE = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE)
_MARKDOWN_IMG_RE = re.compile(r"""!\[[^\]]*\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)""")
_SKIP_NOTE_TYPES = {
    "Incremento PDF",
    "Incremento EPUB",
    "Incremento Video",
    "Incremento Web",
    "Incremento Writing",
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def supported_image_ocr_note(note) -> bool:
    try:
        model = note.note_type()
    except Exception:
        model = None
    model_name = str((model or {}).get("name") or "").strip()
    return bool(model_name) and model_name not in _SKIP_NOTE_TYPES


def extract_local_image_names_from_field(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in _IMG_SRC_RE.findall(text or "") + _MARKDOWN_IMG_RE.findall(text or ""):
        src = unescape(str(raw or "").strip())
        if not src:
            continue
        parsed = urlparse(src)
        if parsed.scheme in {"http", "https", "data"}:
            continue
        filename = os.path.basename(unquote(parsed.path or src)).strip()
        if not filename:
            continue
        lowered = filename.lower()
        if os.path.splitext(lowered)[1] not in _IMAGE_EXTENSIONS:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        found.append(filename)
    return found


def collect_note_image_names(note) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for field_text in list(getattr(note, "fields", []) or []):
        for filename in extract_local_image_names_from_field(str(field_text or "")):
            lowered = filename.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            names.append(filename)
    return names


def ensure_note_ocr_field_for_note(note) -> bool:
    try:
        model = note.note_type()
    except Exception:
        return False
    changed = ensure_incremento_ocr_field(mw.col.models, model)
    if changed:
        try:
            mw.col.models.update_dict(model)
        except Exception:
            pass
    return changed


def _ocr_image_text(image_path: str) -> str:
    binary = tesseract_path()
    if not binary:
        raise RuntimeError("Tesseract OCR is not installed.")
    proc = subprocess.run(
        [binary, image_path, "stdout"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "OCR failed").strip())
    return " ".join((proc.stdout or "").split())


def sync_note_ocr_field_and_index(
    addon_dir: str,
    profile: str,
    note,
    *,
    image_rows: list[tuple[str, str]],
) -> str:
    normalized_rows = [
        (str(image_name or "").strip(), " ".join(str(text or "").split()).strip())
        for image_name, text in list(image_rows or [])
        if str(text or "").strip()
    ]
    combined_text = "\n\n".join(
        f"[{image_name}] {text}" if image_name else text
        for image_name, text in normalized_rows
    ).strip()
    ensure_note_ocr_field_for_note(note)
    try:
        note[INCREMENTO_OCR_TEXT_FIELD] = combined_text
        note.flush()
    except Exception:
        pass

    card_ids = []
    try:
        card_ids = [int(card.id) for card in list(note.cards())]
    except Exception:
        card_ids = []
    replace_note_ocr_index(
        addon_dir,
        profile,
        int(getattr(note, "id", 0) or 0),
        card_ids,
        normalized_rows,
        fallback_text=combined_text,
    )
    return combined_text


def rebuild_note_ocr_index_from_field(
    addon_dir: str,
    profile: str,
    note,
) -> str:
    note_id = int(getattr(note, "id", 0) or 0)
    if note_id <= 0:
        return ""
    try:
        text = str(note[INCREMENTO_OCR_TEXT_FIELD] or "").strip()
    except Exception:
        text = ""
    try:
        card_ids = [int(card.id) for card in list(note.cards())]
    except Exception:
        card_ids = []
    replace_note_ocr_index(
        addon_dir,
        profile,
        note_id,
        card_ids,
        [],
        fallback_text=text,
    )
    return text


def ocr_note_images(addon_dir: str, profile: str, note, *, media_dir: str) -> dict:
    result = {
        "note_id": int(getattr(note, "id", 0) or 0),
        "supported": supported_image_ocr_note(note),
        "images_found": 0,
        "updated": False,
        "missing_images": [],
        "errors": [],
        "image_rows": [],
        "combined_text": "",
    }
    if not result["supported"]:
        return result
    image_names = collect_note_image_names(note)
    result["images_found"] = len(image_names)
    if not image_names:
        rebuild_note_ocr_index_from_field(addon_dir, profile, note)
        return result

    rows: list[tuple[str, str]] = []
    for image_name in image_names:
        image_path = os.path.join(media_dir, image_name)
        if not os.path.exists(image_path):
            result["missing_images"].append(image_name)
            continue
        try:
            text = _ocr_image_text(image_path)
        except Exception as exc:
            result["errors"].append(f"{image_name}: {exc}")
            continue
        if text:
            rows.append((image_name, text))
    result["image_rows"] = list(rows)
    result["combined_text"] = sync_note_ocr_field_and_index(
        addon_dir,
        profile,
        note,
        image_rows=rows,
    )
    result["updated"] = bool(result["combined_text"])
    return result


def tesseract_ready_message() -> str | None:
    if has_tesseract():
        return None
    return tesseract_instructions()
