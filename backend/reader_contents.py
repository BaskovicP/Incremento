"""Bounded document navigation metadata. Titles are plain, untrusted text."""
from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

MAX_CONTENTS_ENTRIES = 2000
MAX_CONTENTS_DEPTH = 12
MAX_CONTENTS_FILE_BYTES = 4 * 1024 * 1024


def normalize_contents_entries(entries: object, kind: str, total: int) -> list[dict]:
    result = []
    if not isinstance(entries, list):
        return result
    key = "page" if kind == "pdf" else "section_index"
    minimum = 1 if kind == "pdf" else 0
    for index, entry in enumerate(entries[:MAX_CONTENTS_ENTRIES]):
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
            continue
        title = " ".join(entry["title"].split())[:240]
        try:
            position = int(entry[key])
            depth = max(0, min(MAX_CONTENTS_DEPTH, int(entry.get("depth", 0))))
            identity = int(entry.get("id", index))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not title or not minimum <= position < total + minimum:
            continue
        clean = {"title": title, "depth": depth, key: position}
        if kind == "pdf":
            clean["id"] = identity
        else:
            fragment = str(entry.get("fragment") or "")[:1024]
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in fragment):
                continue
            clean["fragment"] = fragment
        result.append(clean)
    return result


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if root.is_symlink():
        return ""
    # Never follow document-supplied symlinks, including intermediate directories.
    if path.is_absolute() and not path.is_relative_to(root):
        return ""
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root and parent.is_relative_to(root)):
        return ""
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            return ""
        with path.open("rb") as stream:
            raw = stream.read(MAX_CONTENTS_FILE_BYTES + 1)
        return raw.decode("utf-8", errors="replace") if len(raw) <= MAX_CONTENTS_FILE_BYTES else ""
    except (OSError, ValueError):
        return ""


def epub_contents(extract_root: Path, metadata: dict) -> list[dict]:
    """Read EPUB 3 nav / EPUB 2 NCX without rewriting older extraction caches."""
    root = Path(extract_root)
    sections = list(metadata.get("sections") or [])[:MAX_CONTENTS_ENTRIES]
    known = {str(section.get("href") or ""): i for i, section in enumerate(sections)}
    opf = str(metadata.get("opf_relpath") or "")
    def xml(relative):
        text = _read(root, relative)
        if "<!ENTITY" in text.upper():
            return ET.Element("empty")
        try:
            return ET.fromstring(text)
        except ET.ParseError:
            return ET.Element("empty")

    package = xml(opf)
    items = list(package.findall(".//{*}manifest/{*}item"))[:MAX_CONTENTS_ENTRIES]
    result: list[dict] = []

    def record(href, title, directory, depth):
        if len(result) >= MAX_CONTENTS_ENTRIES:
            return
        try:
            url = urlsplit(str(href or ""))
        except ValueError:
            return
        if url.scheme or url.netloc or url.query or "\\" in url.path:
            return
        target = posixpath.normpath(posixpath.join(directory, unquote(url.path)))
        if target not in known:
            return
        result.append({"title": str(title), "depth": depth, "section_index": known[target], "fragment": unquote(url.fragment)})

    for item in items:
        if "nav" not in str(item.get("properties") or "").split():
            continue
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(opf), str(item.get("href") or "")))
        soup = BeautifulSoup(_read(root, relative), "html.parser")
        navs = soup.find_all("nav")
        nav = next((node for node in navs if "toc" in str(node.get("epub:type") or node.get("role") or "").split()), None)
        if nav is None:
            nav = navs[0] if len(navs) == 1 else None
        if nav is not None:
            for anchor in nav.find_all("a", limit=MAX_CONTENTS_ENTRIES):
                depth = min(MAX_CONTENTS_DEPTH, max(0, len(anchor.find_parents("ol")) - 1))
                record(anchor.get("href"), anchor.get_text(" ", strip=True), posixpath.dirname(relative), depth)
        if result:
            break
    if not result:
        for item in items:
            if item.get("media-type") != "application/x-dtbncx+xml":
                continue
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(opf), str(item.get("href") or "")))
            ncx = xml(relative)
            pending = [(node, 0) for node in reversed(ncx.findall(".//{*}navMap/{*}navPoint"))]
            visited = 0
            while pending and visited < MAX_CONTENTS_ENTRIES:
                point, depth = pending.pop()
                visited += 1
                content = point.find("{*}content")
                label = point.find("{*}navLabel")
                if content is not None and label is not None:
                    record(content.get("src"), " ".join(label.itertext()).strip(), posixpath.dirname(relative), depth)
                if depth < MAX_CONTENTS_DEPTH:
                    pending.extend((node, depth + 1) for node in reversed(point.findall("{*}navPoint")))
            if result:
                break
    if not result:
        result = [{"title": s.get("title") or f"{i + 1}", "depth": 0, "section_index": i, "fragment": ""} for i, s in enumerate(sections)]
    return normalize_contents_entries(result, "epub", len(sections))
