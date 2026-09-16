"""Offline Markdown study copies, backed by the existing EPUB document reader.

Anki already depends on Python-Markdown. Conversion owns temporary files only;
epub_manager owns journaled profile storage, note creation, and the search index.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import shutil
import tempfile
import threading
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
import zipfile
import uuid

from bs4 import BeautifulSoup
import markdown

try:
    from .content_safety import external_plain_text, normalize_external_http_url
    from .i18n import t
except ImportError:
    from content_safety import external_plain_text, normalize_external_http_url
    from i18n import t


MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 48 * 1024 * 1024
MAX_IMAGES = 128
MAX_SECTIONS = 2_000
MAX_LEGACY_HTML_BYTES = 16 * 1024 * 1024
_ALLOWED_TAGS = {
    "p",
    "div",
    "span",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
    "hr",
    "strong",
    "b",
    "em",
    "i",
    "del",
    "s",
    "blockquote",
    "pre",
    "code",
    "kbd",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "a",
    "img",
    "sup",
    "sub",
}
_DROP_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "svg",
    "math",
    "form",
    "input",
    "button",
    "textarea",
    "select",
    "template",
}
_STYLE = """body {line-height:1.6; overflow-wrap:anywhere;}
img {max-width:100%; height:auto;} pre {white-space:pre-wrap; padding:0.8em;}
code, kbd {font-family:monospace;} table {border-collapse:collapse; max-width:100%;}
th, td {border:1px solid #888; padding:0.4em;} blockquote {border-left:3px solid #888; margin-left:0; padding-left:1em;}
"""


class MarkdownImportError(RuntimeError):
    """Controlled validation failure with no managed-storage side effects."""


@dataclass
class PreparedMarkdown:
    path: str
    _temporary: tempfile.TemporaryDirectory

    def close(self) -> None:
        self._temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


@dataclass
class MarkdownDocument:
    text: str
    revision: str
    images: dict
    assets: dict
    _archive: bytes


_edit_lock = threading.RLock()


def _read_regular_file(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise MarkdownImportError(t("imports_markdown_invalid_file"))
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise MarkdownImportError(t("imports_markdown_invalid_file"))
        if info.st_size > limit:
            raise MarkdownImportError(t("imports_markdown_too_large"))
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise MarkdownImportError(t("imports_markdown_too_large"))
    return data


def _image_type(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif", "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def _prepare_html(text: str, source: Path, *, embedded_images=None, assets=None) -> tuple[BeautifulSoup, dict]:
    rendered = markdown.markdown(
        text, extensions=["fenced_code", "tables", "footnotes", "sane_lists", "toc"], output_format="xhtml"
    )
    soup = BeautifulSoup(rendered, "html.parser")
    for tag in list(soup.find_all(_DROP_TAGS)):
        if tag.parent is not None:
            tag.decompose()
    images: dict[str, tuple[bytes, str]] = dict(embedded_images or {})
    assets = assets if assets is not None else {}
    copied: dict[Path, str] = {}
    total = 0
    root = source.parent.resolve()
    for tag in list(soup.find_all(True)):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        original = dict(tag.attrs)
        tag.attrs = {}
        anchor_id = original.get("id")
        if (
            isinstance(anchor_id, str)
            and len(anchor_id) <= 200
            and not any(c.isspace() or ord(c) < 32 for c in anchor_id)
        ):
            tag["id"] = anchor_id
        if tag.name == "a":
            href = str(original.get("href") or "")
            try:
                parsed = urlsplit(href)
                if parsed.scheme.casefold() in {"http", "https"}:
                    tag["href"] = normalize_external_http_url(href)
                elif href.startswith("#"):
                    tag["href"] = href
            except ValueError:
                pass
        elif tag.name == "img":
            tag["alt"] = external_plain_text(original.get("alt"), max_chars=1_000)
            href = str(original.get("src") or "")
            try:
                if embedded_images is not None:
                    name = assets.get(href, href)
                    if name not in images:
                        raise ValueError("Image is not embedded in this document")
                    tag["src"] = name
                    continue
                parsed = urlsplit(href)
                relative = Path(unquote(parsed.path))
                if (
                    parsed.scheme
                    or parsed.netloc
                    or parsed.query
                    or parsed.fragment
                    or relative.is_absolute()
                    or "\\" in href
                ):
                    raise ValueError("Not a local image")
                candidate = root / relative
                resolved = candidate.resolve()
                if not resolved.is_relative_to(root) or any(
                    p.is_symlink() for p in [candidate, *candidate.parents] if p != root and p.is_relative_to(root)
                ):
                    raise ValueError("Image outside source directory")
                if resolved in copied:
                    tag["src"] = copied[resolved]
                    assets[href] = copied[resolved]
                    continue
                data = _read_regular_file(candidate, MAX_IMAGE_BYTES)
                kind = _image_type(data)
                if kind is None:
                    raise ValueError("Not a supported raster image")
                if len(images) >= MAX_IMAGES or total + len(data) > MAX_TOTAL_IMAGE_BYTES:
                    raise MarkdownImportError(t("imports_markdown_images_too_large"))
                name = f"images/image-{len(images) + 1}.{kind[0]}"
                images[name] = (data, kind[1])
                copied[resolved] = name
                total += len(data)
                tag["src"] = name
                assets[href] = name
            except (OSError, ValueError):
                # Missing/unsupported/escaping images retain their alt text only.
                tag.replace_with(tag["alt"])
    return soup, images


def _split_sections(soup: BeautifulSoup, title: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list]] = []
    nodes: list = []
    section_title = title
    for node in list(soup.contents):
        if getattr(node, "name", None) in {"h1", "h2"}:
            if any(str(n).strip() for n in nodes):
                sections.append((section_title, nodes))
                nodes = []
            section_title = node.get_text(" ", strip=True) or title
        nodes.append(node)
    if any(str(n).strip() for n in nodes):
        sections.append((section_title, nodes))
    if not sections or len(sections) > MAX_SECTIONS:
        raise MarkdownImportError(t("imports_markdown_sections_invalid"))
    anchors = {}
    for index, (_, content) in enumerate(sections, 1):
        for node in content:
            if getattr(node, "attrs", None) and node.get("id"):
                anchors.setdefault(node["id"], index)
            if hasattr(node, "find_all"):
                for child in node.find_all(id=True):
                    anchors.setdefault(child["id"], index)
    for link in soup.find_all("a", href=True):
        if link["href"].startswith("#"):
            anchor = unquote(link["href"][1:])
            if anchor in anchors:
                link["href"] = f"section-{anchors[anchor]}.xhtml#{anchor}"
            else:
                del link["href"]
    return [(name, "".join(str(n) for n in content)) for name, content in sections]


def prepare_markdown_epub(markdown_path: str, *, title: str = "") -> PreparedMarkdown:
    """Validate and render a UTF-8 .md/.markdown file without changing its source."""
    source = Path(markdown_path).absolute()
    if source.suffix.casefold() not in {".md", ".markdown"}:
        raise MarkdownImportError(t("imports_markdown_invalid_file"))
    try:
        raw = _read_regular_file(source, MAX_MARKDOWN_BYTES)
        raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise MarkdownImportError(t("imports_markdown_invalid_file")) from exc
    return _prepare_bytes(raw, source, title=title)


def _prepare_bytes(raw: bytes, source: Path, *, title: str, embedded_images=None, assets=None) -> PreparedMarkdown:
    text = raw.decode("utf-8-sig")
    if len(raw) > MAX_MARKDOWN_BYTES or not text.strip() or "\x00" in text:
        raise MarkdownImportError(t("imports_markdown_invalid_file"))
    name = external_plain_text(title.strip() or source.stem, max_chars=2_000).strip() or "Untitled"
    assets = dict(assets or {})
    soup, images = _prepare_html(
        external_plain_text(text, max_chars=len(text)), source, embedded_images=embedded_images, assets=assets
    )
    sections = _split_sections(soup, name)
    temporary = tempfile.TemporaryDirectory(prefix="incremento-markdown-")
    stem = re.sub(r"[^\w.-]", "_", source.stem)[:80].strip("._-") or "document"
    prepared = PreparedMarkdown(str(Path(temporary.name) / f"{stem}.epub"), temporary)
    try:
        package = ET.Element(
            "package", {"xmlns": "http://www.idpf.org/2007/opf", "version": "3.0", "unique-identifier": "book-id"}
        )
        metadata = ET.SubElement(package, "metadata", {"xmlns:dc": "http://purl.org/dc/elements/1.1/"})
        ET.SubElement(metadata, "dc:identifier", {"id": "book-id"}).text = "incremento-markdown"
        ET.SubElement(metadata, "dc:title").text = name
        ET.SubElement(metadata, "dc:language").text = "und"
        manifest = ET.SubElement(package, "manifest")
        spine = ET.SubElement(package, "spine")
        nav = ET.Element(
            "html", {"xmlns": "http://www.w3.org/1999/xhtml", "xmlns:epub": "http://www.idpf.org/2007/ops"}
        )
        listing = ET.SubElement(ET.SubElement(ET.SubElement(nav, "body"), "nav", {"epub:type": "toc"}), "ol")
        ET.SubElement(
            manifest,
            "item",
            {"id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav"},
        )
        with zipfile.ZipFile(prepared.path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("source.md", raw)
            archive.writestr("source_assets.json", json.dumps(assets, ensure_ascii=False))
            archive.writestr(
                "META-INF/container.xml",
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            for index, (label, body) in enumerate(sections, 1):
                filename = f"section-{index}.xhtml"
                ET.SubElement(
                    manifest,
                    "item",
                    {"id": f"section-{index}", "href": filename, "media-type": "application/xhtml+xml"},
                )
                ET.SubElement(spine, "itemref", {"idref": f"section-{index}"})
                ET.SubElement(ET.SubElement(listing, "li"), "a", {"href": filename}).text = label
                # Labels and titles never enter an executable HTML interpolation.
                document = BeautifulSoup(
                    '<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><title></title><style></style></head><body></body></html>',
                    "html.parser",
                )
                document.title.string = label
                document.style.string = _STYLE
                fragment = BeautifulSoup(body, "html.parser")
                for node in list(fragment.contents):
                    document.body.append(node)
                archive.writestr(f"OEBPS/{filename}", str(document))
            for index, (filename, (data, mime)) in enumerate(images.items(), 1):
                ET.SubElement(manifest, "item", {"id": f"image-{index}", "href": filename, "media-type": mime})
                archive.writestr(f"OEBPS/{filename}", data)
            archive.writestr("OEBPS/nav.xhtml", ET.tostring(nav, encoding="utf-8", xml_declaration=True))
            archive.writestr("OEBPS/content.opf", ET.tostring(package, encoding="utf-8", xml_declaration=True))
        return prepared
    except BaseException:
        prepared.close()
        raise


def render_markdown_text_preview(text: str) -> str:
    """Inert text-only preview: no resource loading, scripts, or filesystem access."""
    if len(text.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise MarkdownImportError(t("imports_markdown_too_large"))
    soup, _ = _prepare_html(text, Path("preview.md"), embedded_images={})
    for link in soup.find_all("a"):
        link.attrs.pop("href", None)
    return "<style>" + _STYLE + "</style>" + str(soup)


def render_markdown_preview(path: str) -> str:
    raw = _read_regular_file(Path(path), MAX_MARKDOWN_BYTES)
    return render_markdown_text_preview(raw.decode("utf-8-sig"))


def _managed_path(addon_dir: str, profile: str, filename: str) -> Path:
    try:
        from . import paths
    except ImportError:
        import paths
    if not filename or Path(filename).name != filename or "\\" in filename or not filename.endswith(".epub"):
        raise MarkdownImportError(t("imports_markdown_invalid_file"))
    root = paths.get_epub_dir(addon_dir, profile)
    candidate = root / filename
    if candidate.is_symlink() or any(p.is_symlink() for p in [root, *root.parents]):
        raise MarkdownImportError(t("imports_markdown_invalid_file"))
    return candidate


def load_markdown_document(addon_dir: str, profile: str, filename: str) -> MarkdownDocument:
    """Read only an exact managed Markdown archive, with bounded source and assets."""
    try:
        from . import epub_manager
    except ImportError:
        import epub_manager
    target = _managed_path(addon_dir, profile, filename)
    try:
        raw = _read_regular_file(target, 64 * 1024 * 1024)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = dict((name, info) for info, name in epub_manager._safe_zip_members(archive))
            source_info = members.get("source.md")
            if source_info is None or source_info.file_size > MAX_MARKDOWN_BYTES:
                raise ValueError("Not a Markdown document")
            text = archive.read(source_info).decode("utf-8-sig")
            if not text.strip() or "\x00" in text:
                raise ValueError("Invalid Markdown source")
            images, total = {}, 0
            for name, info in members.items():
                if not re.fullmatch(r"OEBPS/images/image-\d+\.(png|jpg|gif|webp)", name):
                    continue
                if (
                    info.file_size > MAX_IMAGE_BYTES
                    or len(images) >= MAX_IMAGES
                    or total + info.file_size > MAX_TOTAL_IMAGE_BYTES
                ):
                    raise ValueError("Embedded image budget exceeded")
                data = archive.read(info)
                kind = _image_type(data)
                if not kind:
                    raise ValueError("Invalid embedded image")
                images[name.removeprefix("OEBPS/")] = (data, kind[1])
                total += len(data)
            assets = {}
            if "source_assets.json" in members:
                if members["source_assets.json"].file_size > 64 * 1024:
                    raise ValueError("Asset map budget exceeded")
                mapping = json.loads(archive.read("source_assets.json"))
                if not isinstance(mapping, dict) or len(mapping) > MAX_IMAGES * 4:
                    raise ValueError("Invalid asset map")
                assets = {
                    key: value
                    for key, value in mapping.items()
                    if isinstance(key, str) and isinstance(value, str) and value in images
                }
            else:
                # Legacy imports predate the asset map. Match only unambiguous alt labels.
                original = BeautifulSoup(
                    markdown.markdown(text, extensions=["fenced_code", "tables", "footnotes"]), "html.parser"
                ).find_all("img")
                rendered = []
                html_bytes = 0
                for name, info in members.items():
                    if re.fullmatch(r"OEBPS/section-\d+\.xhtml", name):
                        html_bytes += info.file_size
                        if html_bytes > MAX_LEGACY_HTML_BYTES:
                            raise ValueError("Legacy rendered HTML budget exceeded")
                        rendered.extend(BeautifulSoup(archive.read(info), "html.parser").find_all("img"))
                for image in original:
                    matches = [img.get("src") for img in rendered if img.get("alt") == image.get("alt")]
                    if len(set(matches)) == 1 and matches[0] in images:
                        assets[str(image.get("src") or "")] = matches[0]
        return MarkdownDocument(text, hashlib.sha256(raw).hexdigest(), images, assets, raw)
    except (OSError, ValueError, KeyError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise MarkdownImportError(t("imports_markdown_invalid_file")) from exc


def save_markdown_document(
    addon_dir: str, profile: str, card_id: int, filename: str, text: str, *, title: str, expected_revision: str
) -> dict:
    """Replace the managed copy/cache/index, retaining one previous archive.

    Card identity, provenance, annotations, progress, and Anki scheduling are untouched.
    A failed save restores every replaced resource and rolls back the index.
    """
    try:
        from . import paths, epub_manager, db
    except ImportError:
        import paths
        import epub_manager
        import db
    with _edit_lock:
        target = _managed_path(addon_dir, profile, filename)
        snapshot = load_markdown_document(addon_dir, profile, filename)
        if snapshot.revision != expected_revision:
            raise MarkdownImportError(t("imports_markdown_edit_conflict"))
        conn = db.get_connection(addon_dir, profile)
        owner = conn.execute(
            "SELECT card_id FROM content_items WHERE kind=? AND storage_key=?", ("epub", "epubs/" + filename)
        ).fetchall()
        if owner != [(int(card_id),)]:
            raise MarkdownImportError(t("imports_markdown_cancelled"))
        backup = paths.get_markdown_backup_path(addon_dir, profile, filename)
        if any(p.is_symlink() for p in [backup, *backup.parents]):
            raise MarkdownImportError(t("imports_markdown_invalid_file"))
        with _prepare_bytes(
            text.encode("utf-8"),
            Path("document.md"),
            title=title,
            embedded_images=snapshot.images,
            assets=snapshot.assets,
        ) as prepared:
            stage_name = "markdown-edit-" + uuid.uuid4().hex + ".epub"
            cache = paths.get_epub_extract_root(addon_dir, profile) / filename
            stage_cache = paths.get_epub_extract_root(addon_dir, profile) / stage_name
            if any(p.is_symlink() for p in [cache, *cache.parents]):
                raise MarkdownImportError(t("imports_markdown_invalid_file"))
            try:
                metadata = epub_manager.ensure_epub_extracted(
                    prepared.path, stored_filename=stage_name, profile=profile
                )
                with tempfile.TemporaryDirectory(prefix=".markdown-edit-", dir=target.parent) as stage:
                    stage = Path(stage)
                    previous = stage / "previous.epub"
                    previous.write_bytes(snapshot._archive)
                    os.chmod(previous, 0o600)
                    replacement = stage / "replacement.epub"
                    shutil.copyfile(prepared.path, replacement)
                    os.chmod(replacement, 0o600)
                    for output in (previous, replacement):
                        with output.open("rb") as handle:
                            os.fsync(handle.fileno())
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    old_backup = stage / "old-backup.epub"
                    if backup.exists():
                        shutil.copyfile(backup, old_backup)
                    old_cache = stage / "old-cache"
                    changed_archive = changed_cache = changed_backup = False
                    try:
                        with conn:
                            db.replace_epub_text_index(
                                addon_dir,
                                profile,
                                card_id,
                                [(str(s.get("title") or ""), str(s.get("text") or "")) for s in metadata["sections"]],
                                commit=False,
                            )
                            # Publish a recoverable previous version before changing the document.
                            os.replace(previous, backup)
                            changed_backup = True
                            os.replace(replacement, target)
                            changed_archive = True
                            if cache.exists():
                                os.replace(cache, old_cache)
                            try:
                                os.replace(stage_cache, cache)
                            except Exception:
                                if old_cache.exists():
                                    os.replace(old_cache, cache)
                                raise
                            changed_cache = True
                    except Exception:
                        if changed_archive:
                            restore = stage / "restore.epub"
                            restore.write_bytes(snapshot._archive)
                            os.chmod(restore, 0o600)
                            os.replace(restore, target)
                        if changed_cache:
                            shutil.rmtree(cache)
                            if old_cache.exists():
                                os.replace(old_cache, cache)
                        if changed_backup:
                            if old_backup.exists():
                                os.replace(old_backup, backup)
                            else:
                                backup.unlink()
                        raise
                return metadata
            finally:
                if stage_cache.exists():
                    shutil.rmtree(stage_cache)


def add_markdown_card(
    addon_dir: str,
    profile: str,
    col,
    markdown_path: str,
    title: str,
    *,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
) -> int:
    """Import one rendered study document through the journaled EPUB boundary."""
    try:
        from .epub_manager import add_epub_card
    except ImportError:
        from epub_manager import add_epub_card
    with prepare_markdown_epub(markdown_path, title=title) as prepared:
        return add_epub_card(
            addon_dir,
            col,
            prepared.path,
            title,
            deck_name=deck_name,
            tags=tags,
            profile=profile,
            source_type="Markdown",
        )
