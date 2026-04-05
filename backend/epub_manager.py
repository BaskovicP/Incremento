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
        replace_epub_text_index,
    )
    from . import paths as _paths
except ImportError:
    from db import get_connection, replace_epub_text_index  # type: ignore
    import paths as _paths


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
    ratio = current_ratio if scroll_ratio is None else max(0.0, min(float(scroll_ratio), 1.0))
    finished = current_finished if is_finished is None else bool(is_finished)
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_progress (card_id, section_index, scroll_ratio, is_finished) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "section_index = excluded.section_index, "
        "scroll_ratio = excluded.scroll_ratio, "
        "is_finished = excluded.is_finished",
        (card_id, max(0, int(section_index)), ratio, 1 if finished else 0),
    )
    conn.commit()


def ensure_epub_note_type(col) -> None:
    models = col.models
    m = models.by_name(EPUB_NOTE_TYPE)

    if m is None:
        m = models.new(EPUB_NOTE_TYPE)
        for field_name in ("Title", EPUB_FILE_FIELD):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        tmpl = m["tmpls"][0]
        changed = False
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

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note[EPUB_FILE_FIELD] = stored_filename
        for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
            if not tag:
                continue
            if hasattr(note, "add_tag"):
                note.add_tag(tag)
            elif hasattr(note, "tags"):
                note.tags.append(tag)
        note.note_type()["did"] = deck_id
        return note

    base_title = str(title or "").strip() or str(metadata.get("title") or "").strip() or Path(epub_path).stem
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
