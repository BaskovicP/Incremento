from __future__ import annotations

import json
import os
import posixpath
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

try:
    from .db import (
        get_connection,
        get_epub_card_sources_up_to_section,
        get_epub_daily_limit_config,
        get_epub_due_review_prompt_config,
        get_epub_daily_limit_usage,
        replace_epub_text_index,
        set_epub_daily_limit_config,
        set_epub_due_review_prompt_config,
        set_epub_daily_limit_usage,
    )
    from . import paths as _paths
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )
    from .scheduler_config import build_ready_filter, load_scheduler_config
    from .statistics import _effective_date
except ImportError:
    from db import (  # type: ignore
        get_connection,
        get_epub_card_sources_up_to_section,
        get_epub_daily_limit_config,
        get_epub_due_review_prompt_config,
        get_epub_daily_limit_usage,
        replace_epub_text_index,
        set_epub_daily_limit_config,
        set_epub_due_review_prompt_config,
        set_epub_daily_limit_usage,
    )
    import paths as _paths
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )
    from scheduler_config import build_ready_filter, load_scheduler_config  # type: ignore
    from statistics import _effective_date  # type: ignore


EPUB_NOTE_TYPE = "Incremento EPUB"
EPUB_FILE_FIELD = "EPUB_Filename"
DOCUMENT_FILTER = '(note:"Incremento PDF" OR note:"Incremento EPUB")'
_INVISIBLE_DUPLICATE_MARK = "\u200b"
_HTML_MEDIA_TYPES = {
    "application/xhtml+xml",
    "text/html",
    "application/x-dtbook+xml",
}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_STEM = 80
_EPUB_LIMIT_MODE_LABELS = {
    "warning": "Warning",
    "soft_lock": "Soft Lock",
    "hard_stop": "Hard Stop",
}

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">EPUB open in sidebar &nbsp;·&nbsp; select text → ⌘C → ⌘1–4 to fill fields</div>
</div>
{{EPUB_Filename}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


def get_epub_dir() -> str:
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    d = str(_paths.get_epub_dir(addon_dir, _paths.get_active_profile()))
    os.makedirs(d, exist_ok=True)
    return d


def get_epub_extract_root() -> str:
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    d = str(_paths.get_epub_extract_root(addon_dir, _paths.get_active_profile()))
    os.makedirs(d, exist_ok=True)
    return d


def get_epub_extract_dir(stored_filename: str) -> str:
    stem = Path(str(stored_filename or "")).name
    safe = stem.replace(os.sep, "_")
    return os.path.join(get_epub_extract_root(), safe)


def _copy_to_epub_dir(epub_path: str) -> str:
    epub_dir = get_epub_dir()
    raw_name = os.path.basename(epub_path)
    stem, ext = os.path.splitext(raw_name)
    stem = _SAFE_FILENAME_RE.sub("_", stem).strip("._-")
    stem = stem[:_MAX_FILENAME_STEM].strip("._-") or "book"
    ext = ext if ext.lower() == ".epub" else ".epub"
    dest_name = f"{stem}-{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(epub_dir, dest_name)
    shutil.copy2(epub_path, dest_path)
    return dest_name


def _safe_zip_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    out: list[zipfile.ZipInfo] = []
    for info in zf.infolist():
        name = str(info.filename or "").replace("\\", "/")
        if not name or name.endswith("/"):
            out.append(info)
            continue
        parts = [part for part in Path(name).parts if part not in ("", ".")]
        if any(part == ".." for part in parts):
            continue
        out.append(info)
    return out


def _decode_xml(path: str) -> ET.Element:
    return ET.parse(path).getroot()


def _resolve_posix(base_dir: str, href: str) -> str:
    joined = posixpath.normpath(posixpath.join(base_dir or "", str(href or "").strip()))
    while joined.startswith("../"):
        joined = joined[3:]
    return joined.lstrip("/")


def _safe_read_text(path: str) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except Exception:
            continue
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", errors="ignore")


def _clean_html_file(path: str) -> None:
    try:
        soup = BeautifulSoup(_safe_read_text(path), "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(_safe_read_text(path), "html.parser")
        except Exception:
            return
    changed = False
    for tag in soup.find_all(["script"]):
        tag.decompose()
        changed = True
    if changed:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(str(soup))
        except Exception:
            pass


def _load_nav_labels(extract_dir: str, opf_dir: str, manifest: dict[str, dict]) -> dict[str, str]:
    labels: dict[str, str] = {}

    def _record(href: str, label: str, doc_dir: str) -> None:
        text = " ".join(str(label or "").split()).strip()
        target = _resolve_posix(doc_dir, href)
        if text and target and target not in labels:
            labels[target] = text

    nav_item = next((item for item in manifest.values() if "nav" in item.get("properties", [])), None)
    if nav_item:
        nav_rel = _resolve_posix(opf_dir, nav_item.get("href", ""))
        nav_path = os.path.join(extract_dir, nav_rel)
        if os.path.isfile(nav_path):
            try:
                soup = BeautifulSoup(_safe_read_text(nav_path), "lxml")
                nav_root = soup.find("nav") or soup
                nav_dir = posixpath.dirname(nav_rel)
                for a in nav_root.find_all("a"):
                    href = str(a.get("href") or "").strip()
                    label = a.get_text(" ", strip=True)
                    if href:
                        _record(href, label, nav_dir)
            except Exception:
                pass

    ncx_item = next(
        (
            item
            for item in manifest.values()
            if item.get("media_type") == "application/x-dtbncx+xml"
        ),
        None,
    )
    if ncx_item:
        ncx_rel = _resolve_posix(opf_dir, ncx_item.get("href", ""))
        ncx_path = os.path.join(extract_dir, ncx_rel)
        if os.path.isfile(ncx_path):
            try:
                root = _decode_xml(ncx_path)
                ns = {"ncx": root.tag.partition("}")[0].strip("{")}
                ncx_dir = posixpath.dirname(ncx_rel)
                for nav_point in root.findall(".//ncx:navPoint", ns):
                    label = ""
                    text_el = nav_point.find(".//ncx:navLabel/ncx:text", ns)
                    content_el = nav_point.find(".//ncx:content", ns)
                    if text_el is not None:
                        label = str(text_el.text or "").strip()
                    href = str(content_el.get("src") or "").strip() if content_el is not None else ""
                    if href:
                        _record(href, label, ncx_dir)
            except Exception:
                pass

    return labels


def _section_title(soup: BeautifulSoup, fallback: str) -> str:
    for selector in ("h1", "h2", "title"):
        node = soup.find(selector)
        text = node.get_text(" ", strip=True) if node else ""
        if text:
            return text
    return fallback


def _html_text_and_title(path: str, fallback_title: str) -> tuple[str, str]:
    text = ""
    title = fallback_title
    try:
        soup = BeautifulSoup(_safe_read_text(path), "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(_safe_read_text(path), "html.parser")
        except Exception:
            return (" ".join(text.split()).strip(), title.strip() or fallback_title)
    try:
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        title = _section_title(soup, fallback_title)
    except Exception:
        pass
    return (" ".join(text.split()).strip(), title.strip() or fallback_title)


def _metadata_path(stored_filename: str) -> str:
    return os.path.join(get_epub_extract_dir(stored_filename), "metadata.json")


def load_epub_metadata(addon_dir: str, stored_filename: str) -> dict:
    del addon_dir
    meta_path = _metadata_path(stored_filename)
    if not os.path.isfile(meta_path):
        epub_path = os.path.join(get_epub_dir(), stored_filename)
        ensure_epub_extracted(epub_path, stored_filename=stored_filename)
    with open(meta_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ensure_epub_extracted(epub_path: str, *, stored_filename: str | None = None) -> dict:
    stored_name = str(stored_filename or os.path.basename(epub_path))
    extract_dir = get_epub_extract_dir(stored_name)
    meta_path = os.path.join(extract_dir, "metadata.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    if os.path.isdir(extract_dir):
        shutil.rmtree(extract_dir, ignore_errors=True)
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(epub_path, "r") as zf:
        for info in _safe_zip_members(zf):
            name = str(info.filename or "").replace("\\", "/")
            if not name:
                continue
            target = os.path.join(extract_dir, name)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    container_path = os.path.join(extract_dir, "META-INF", "container.xml")
    if not os.path.isfile(container_path):
        raise RuntimeError("Invalid EPUB: missing META-INF/container.xml")
    container_root = _decode_xml(container_path)
    rootfile_el = container_root.find(".//{*}rootfile")
    if rootfile_el is None:
        raise RuntimeError("Invalid EPUB: missing package rootfile")
    opf_relpath = str(rootfile_el.get("full-path") or "").strip()
    if not opf_relpath:
        raise RuntimeError("Invalid EPUB: empty package rootfile")

    opf_path = os.path.join(extract_dir, opf_relpath)
    opf_dir = posixpath.dirname(opf_relpath)
    opf_root = _decode_xml(opf_path)
    ns = {
        "opf": opf_root.tag.partition("}")[0].strip("{") or "http://www.idpf.org/2007/opf",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    title = ""
    title_el = opf_root.find(".//dc:title", ns)
    if title_el is not None:
        title = str(title_el.text or "").strip()

    manifest: dict[str, dict] = {}
    for item in opf_root.findall(".//opf:manifest/opf:item", ns):
        item_id = str(item.get("id") or "").strip()
        href = str(item.get("href") or "").strip()
        if not item_id or not href:
            continue
        manifest[item_id] = {
            "href": href,
            "media_type": str(item.get("media-type") or "").strip(),
            "properties": [p for p in str(item.get("properties") or "").split() if p],
        }

    nav_labels = _load_nav_labels(extract_dir, opf_dir, manifest)
    sections: list[dict] = []
    for idx, itemref in enumerate(opf_root.findall(".//opf:spine/opf:itemref", ns)):
        item_id = str(itemref.get("idref") or "").strip()
        item = manifest.get(item_id)
        if not item or item.get("media_type") not in _HTML_MEDIA_TYPES:
            continue
        rel_href = _resolve_posix(opf_dir, item["href"])
        section_path = os.path.join(extract_dir, rel_href)
        if not os.path.isfile(section_path):
            continue
        _clean_html_file(section_path)
        fallback_title = nav_labels.get(rel_href) or Path(rel_href).stem.replace("-", " ").replace("_", " ").strip() or f"Section {idx + 1}"
        text, section_title = _html_text_and_title(section_path, fallback_title)
        sections.append(
            {
                "index": len(sections),
                "href": rel_href,
                "title": section_title,
                "text": text,
            }
        )

    if not sections:
        raise RuntimeError("Invalid EPUB: no readable HTML spine sections found.")

    metadata = {
        "title": title or sections[0]["title"] or Path(stored_name).stem,
        "opf_relpath": opf_relpath,
        "sections": sections,
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    return metadata


def get_epub_section_path(addon_dir: str, stored_filename: str, section_index: int) -> str:
    meta = load_epub_metadata(addon_dir, stored_filename)
    sections = meta.get("sections") or []
    if not sections:
        raise RuntimeError("EPUB has no readable sections.")
    idx = max(0, min(int(section_index), len(sections) - 1))
    return os.path.join(get_epub_extract_dir(stored_filename), sections[idx]["href"])


def get_epub_progress(addon_dir: str, profile: str, card_id: int) -> tuple[int, float, bool]:
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT section_index, scroll_ratio, is_finished FROM epub_progress WHERE card_id = ?",
            (card_id,),
        )
        .fetchone()
    )
    if not row:
        return (0, 0.0, False)
    return (int(row[0] or 0), float(row[1] or 0.0), bool(row[2]))


def get_read_section_index(addon_dir: str, profile: str, card_id: int) -> int:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT read_section_index FROM epub_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return int(row[0] or 0) if row else 0


def get_epub_font_scale(addon_dir: str, profile: str, card_id: int) -> float:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT font_scale FROM epub_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    if not row:
        return 1.0
    try:
        value = float(row[0] or 1.0)
    except Exception:
        value = 1.0
    return max(0.7, min(value, 2.2))


def set_epub_progress(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    section_index: int,
    scroll_ratio: float | None = None,
    is_finished: bool | None = None,
) -> None:
    current_section, current_ratio, current_finished = get_epub_progress(addon_dir, profile, card_id)
    current_read_section = get_read_section_index(addon_dir, profile, card_id)
    current_font_scale = get_epub_font_scale(addon_dir, profile, card_id)
    ratio = current_ratio if scroll_ratio is None else max(0.0, min(float(scroll_ratio), 1.0))
    finished = current_finished if is_finished is None else bool(is_finished)
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_progress (card_id, section_index, scroll_ratio, is_finished, read_section_index, font_scale) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "section_index = excluded.section_index, "
        "scroll_ratio = excluded.scroll_ratio, "
        "is_finished = excluded.is_finished, "
        "read_section_index = excluded.read_section_index, "
        "font_scale = excluded.font_scale",
        (
            card_id,
            max(0, int(section_index)),
            ratio,
            1 if finished else 0,
            max(0, int(current_read_section)),
            max(0.7, min(float(current_font_scale), 2.2)),
        ),
    )
    conn.commit()


def set_read_section_index(addon_dir: str, profile: str, card_id: int, read_section_index: int) -> None:
    current_section, current_ratio, current_finished = get_epub_progress(addon_dir, profile, card_id)
    current_font_scale = get_epub_font_scale(addon_dir, profile, card_id)
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_progress (card_id, section_index, scroll_ratio, is_finished, read_section_index, font_scale) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET read_section_index = excluded.read_section_index",
        (
            card_id,
            max(0, int(current_section)),
            max(0.0, min(float(current_ratio), 1.0)),
            1 if current_finished else 0,
            max(0, int(read_section_index)),
            max(0.7, min(float(current_font_scale), 2.2)),
        ),
    )
    conn.commit()


def set_epub_font_scale(addon_dir: str, profile: str, card_id: int, font_scale: float) -> float:
    current_section, current_ratio, current_finished = get_epub_progress(addon_dir, profile, card_id)
    current_read_section = get_read_section_index(addon_dir, profile, card_id)
    clamped = max(0.7, min(float(font_scale), 2.2))
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_progress (card_id, section_index, scroll_ratio, is_finished, read_section_index, font_scale) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET font_scale = excluded.font_scale",
        (
            card_id,
            max(0, int(current_section)),
            max(0.0, min(float(current_ratio), 1.0)),
            1 if current_finished else 0,
            max(0, int(current_read_section)),
            clamped,
        ),
    )
    conn.commit()
    return clamped


def _current_day_end_time() -> str:
    try:
        cfg = load_scheduler_config()
        day_end_time = str(getattr(cfg, "day_end_time", "00:00") or "00:00").strip()
    except Exception:
        day_end_time = "00:00"
    return day_end_time or "00:00"


def get_epub_limit_mode_label(mode: str) -> str:
    return _EPUB_LIMIT_MODE_LABELS.get(str(mode or "").strip().lower(), "Warning")


def get_epub_daily_limit_settings(addon_dir: str, profile: str, card_id: int) -> dict:
    config = get_epub_daily_limit_config(addon_dir, profile, card_id)
    limit = int(config.get("daily_section_limit", 0) or 0)
    mode = str(config.get("enforcement_mode") or "warning").strip().lower()
    if mode not in _EPUB_LIMIT_MODE_LABELS:
        mode = "warning"
    return {
        "enabled": limit > 0,
        "daily_section_limit": limit,
        "daily_page_limit": limit,
        "enforcement_mode": mode,
        "enforcement_label": get_epub_limit_mode_label(mode),
        "updated_at": int(config.get("updated_at", 0) or 0),
    }


def save_epub_daily_limit_settings(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
    daily_section_limit: int,
    enforcement_mode: str,
) -> dict:
    limit = int(daily_section_limit or 0)
    if not enabled or limit <= 0:
        set_epub_daily_limit_config(
            addon_dir,
            profile,
            card_id,
            daily_section_limit=0,
            enforcement_mode=enforcement_mode,
        )
        return get_epub_daily_limit_settings(addon_dir, profile, card_id)

    set_epub_daily_limit_config(
        addon_dir,
        profile,
        card_id,
        daily_section_limit=limit,
        enforcement_mode=enforcement_mode,
    )
    return get_epub_daily_limit_settings(addon_dir, profile, card_id)


def get_epub_due_review_prompt_settings(addon_dir: str, profile: str, card_id: int) -> dict:
    config = get_epub_due_review_prompt_config(addon_dir, profile, card_id)
    return {
        "enabled": bool(config.get("enabled", True)),
        "updated_at": int(config.get("updated_at", 0) or 0),
    }


def save_epub_due_review_prompt_settings(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
) -> dict:
    set_epub_due_review_prompt_config(
        addon_dir,
        profile,
        card_id,
        enabled=bool(enabled),
    )
    return get_epub_due_review_prompt_settings(addon_dir, profile, card_id)


def _plain_first_field(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return " ".join(text.split()).strip()


def get_due_epub_source_cards(
    addon_dir: str,
    profile: str,
    epub_card_id: int,
    max_section_index: int,
    *,
    col=None,
) -> list[dict]:
    max_section = max(0, int(max_section_index or 0))
    source_rows = get_epub_card_sources_up_to_section(
        addon_dir,
        profile,
        int(epub_card_id),
        max_section,
    )
    if not source_rows:
        return []

    source_by_note: dict[int, dict] = {}
    for row in source_rows:
        note_id = int(row.get("note_id", 0) or 0)
        if note_id <= 0 or note_id in source_by_note:
            continue
        source_by_note[note_id] = {
            "section_index": int(row.get("section_index", 0) or 0),
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
            note = col.get_note(card.nid)
        except Exception:
            continue
        if card is None or note is None:
            continue
        source = source_by_note.get(int(getattr(card, "nid", 0) or 0))
        if not source:
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
                "section_index": int(source["section_index"]),
                "title": title,
                "excerpt": str(source["excerpt"] or ""),
                "queue": queue,
                "due": due_value,
                "due_state": "learning" if queue in {1, 3} else "due",
            }
        )

    rows.sort(
        key=lambda row: (
            int(row["section_index"]),
            int(row["due"]),
            int(row["card_id"]),
        )
    )
    return rows


def get_epub_daily_limit_status(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    current_section_index: int | None = None,
    current_page_index: int | None = None,
    count_current_section: bool = True,
    count_current_page: bool | None = None,
    persist_usage: bool = True,
) -> dict:
    settings = get_epub_daily_limit_settings(addon_dir, profile, card_id)
    section_index = max(0, int(current_section_index if current_section_index is not None else get_epub_progress(addon_dir, profile, card_id)[0]))
    page_index = max(0, int(current_page_index if current_page_index is not None else section_index))
    count_page = count_current_section if count_current_page is None else bool(count_current_page)
    day_end_time = _current_day_end_time()
    logical_date = _effective_date(day_end_time)

    status = {
        "enabled": settings["enabled"],
        "daily_section_limit": settings["daily_section_limit"],
        "daily_page_limit": settings["daily_page_limit"],
        "enforcement_mode": settings["enforcement_mode"],
        "enforcement_label": settings["enforcement_label"],
        "logical_date": logical_date,
        "day_end_time": day_end_time,
        "current_section_index": section_index,
        "current_page_index": page_index,
        "baseline_section": max(0, page_index - 1),
        "highest_section": page_index if count_page else max(0, page_index - 1),
        "baseline_page": max(0, page_index - 1),
        "highest_page": page_index if count_page else max(0, page_index - 1),
        "sections_used": 0,
        "pages_used": 0,
        "sections_remaining": 0,
        "pages_remaining": 0,
        "allowed_max_section": None,
        "allowed_max_page": None,
        "override_enabled": False,
        "limit_reached": False,
        "blocking_active": False,
        "can_override": False,
    }
    if not settings["enabled"]:
        return status

    usage = get_epub_daily_limit_usage(addon_dir, profile, card_id, logical_date)
    baseline_section = int(usage.get("baseline_section", 0) or 0)
    highest_section = int(usage.get("highest_section", 0) or 0)
    override_enabled = bool(usage.get("override_enabled"))

    if baseline_section <= 0 and highest_section <= 0:
        baseline_section = max(0, page_index - 1)
        highest_section = page_index if count_page else baseline_section
        if persist_usage:
            set_epub_daily_limit_usage(
                addon_dir,
                profile,
                card_id,
                logical_date,
                baseline_section=baseline_section,
                highest_section=highest_section,
                override_enabled=override_enabled,
            )
    elif count_page and page_index > highest_section:
        highest_section = page_index
        if persist_usage:
            set_epub_daily_limit_usage(
                addon_dir,
                profile,
                card_id,
                logical_date,
                baseline_section=baseline_section,
                highest_section=highest_section,
                override_enabled=override_enabled,
            )

    daily_limit = int(settings["daily_section_limit"] or 0)
    sections_used = max(0, highest_section - baseline_section)
    allowed_max_section = baseline_section + daily_limit if daily_limit > 0 else None
    sections_remaining = max(0, daily_limit - sections_used) if daily_limit > 0 else 0
    limit_reached = bool(daily_limit > 0 and sections_used >= daily_limit)
    blocking_active = bool(
        daily_limit > 0
        and settings["enforcement_mode"] in {"soft_lock", "hard_stop"}
        and not override_enabled
        and limit_reached
    )
    status.update(
        {
            "baseline_section": baseline_section,
            "highest_section": highest_section,
            "baseline_page": baseline_section,
            "highest_page": highest_section,
            "sections_used": sections_used,
            "pages_used": sections_used,
            "sections_remaining": sections_remaining,
            "pages_remaining": sections_remaining,
            "allowed_max_section": allowed_max_section,
            "allowed_max_page": allowed_max_section,
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


def set_epub_daily_limit_override(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
    current_section_index: int | None = None,
    current_page_index: int | None = None,
) -> dict:
    settings = get_epub_daily_limit_settings(addon_dir, profile, card_id)
    if not settings["enabled"]:
        return get_epub_daily_limit_status(
            addon_dir,
            profile,
            card_id,
            current_section_index=current_section_index,
            current_page_index=current_page_index,
        )

    section_index = max(
        0,
        int(
            current_section_index
            if current_section_index is not None
            else get_epub_progress(addon_dir, profile, card_id)[0]
        ),
    )
    page_index = max(0, int(current_page_index if current_page_index is not None else section_index))
    logical_date = _effective_date(_current_day_end_time())
    usage = get_epub_daily_limit_usage(addon_dir, profile, card_id, logical_date)
    baseline_section = int(usage.get("baseline_section", 0) or max(0, page_index - 1))
    highest_section = int(usage.get("highest_section", 0) or page_index)
    if page_index > highest_section:
        highest_section = page_index
    set_epub_daily_limit_usage(
        addon_dir,
        profile,
        card_id,
        logical_date,
        baseline_section=baseline_section,
        highest_section=highest_section,
        override_enabled=bool(enabled),
    )
    return get_epub_daily_limit_status(
        addon_dir,
        profile,
        card_id,
        current_section_index=section_index,
        current_page_index=page_index,
    )


def ensure_epub_note_type(col) -> None:
    models = col.models
    m = models.by_name(EPUB_NOTE_TYPE)

    if m is None:
        m = models.new(EPUB_NOTE_TYPE)
        for field_name in ("Title", EPUB_FILE_FIELD):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        ensure_incremento_metadata_fields(models, m)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        tmpl = m["tmpls"][0]
        changed = False
        if ensure_incremento_metadata_fields(models, m):
            changed = True
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            changed = True
        if changed:
            models.update_dict(m)


def add_epub_card(
    addon_dir: str,
    col,
    epub_path: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
) -> int:
    ensure_epub_note_type(col)

    stored_filename = _copy_to_epub_dir(epub_path)
    stored_path = os.path.join(get_epub_dir(), stored_filename)
    metadata = ensure_epub_extracted(stored_path, stored_filename=stored_filename)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(EPUB_NOTE_TYPE)
    base_title = str(title or "").strip() or str(metadata.get("title") or "").strip() or Path(epub_path).stem

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note[EPUB_FILE_FIELD] = stored_filename
        apply_incremento_metadata(
            note,
            build_incremento_metadata(
                source_type="EPUB",
                source_title=base_title,
                source_link=f"epubs/{stored_filename}",
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
    for attempt in range(6):
        stored_title = base_title if attempt == 0 else f"{base_title}{_INVISIBLE_DUPLICATE_MARK * attempt}"
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            cid = cards[0]
            break
    if not cid:
        raise RuntimeError("Failed to add EPUB card. Anki rejected the note.")

    try:
        replace_epub_text_index(
            addon_dir,
            _paths.get_active_profile(),
            cid,
            [(section["title"], section["text"]) for section in (metadata.get("sections") or [])],
        )
    except Exception:
        pass
    return cid
