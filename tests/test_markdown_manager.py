"""Markdown study documents are offline, inert, and use the document reader."""

import base64
import shutil
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

import markdown_manager
import epub_manager


@pytest.fixture
def editable_document(tmp_path, monkeypatch):
    import db
    import paths

    profile = "Captured"
    source = tmp_path / "lesson.md"
    (tmp_path / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    source.write_text("# Original\n\n![diagram](diagram.png)\n\nOld content")
    target = paths.get_epub_dir(str(tmp_path), profile) / "managed.epub"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(
        epub_manager, "get_epub_dir", lambda profile=None: str(paths.get_epub_dir(str(tmp_path), profile))
    )
    monkeypatch.setattr(
        epub_manager,
        "get_epub_extract_root",
        lambda profile=None: str(paths.get_epub_extract_root(str(tmp_path), profile)),
    )
    with markdown_manager.prepare_markdown_epub(str(source)) as prepared:
        shutil.copyfile(prepared.path, target)
    epub_manager.ensure_epub_extracted(str(target), stored_filename=target.name, profile=profile)
    db.replace_epub_text_index(str(tmp_path), profile, 41, [("Original", "Old content")])
    conn = db.get_connection(str(tmp_path), profile)
    with conn:
        conn.execute("INSERT INTO content_items VALUES ('identity','epub',41,17,?,1,1)", ("epubs/" + target.name,))
    yield str(tmp_path), profile, source, target, conn
    db.close_connection()


def test_edit_keeps_embedded_images_after_original_assets_are_removed(editable_document):
    addon, profile, source, target, conn = editable_document
    snapshot = markdown_manager.load_markdown_document(addon, profile, target.name)
    (source.parent / "diagram.png").unlink()
    markdown_manager.save_markdown_document(
        addon,
        profile,
        41,
        target.name,
        "# Updated\n\n![diagram](diagram.png)\n\nNew content",
        title="Lesson",
        expected_revision=snapshot.revision,
    )
    with zipfile.ZipFile(target) as archive:
        assert archive.read("OEBPS/images/image-1.png") == b"\x89PNG\r\n\x1a\nimage"
        assert "images/image-1.png" in archive.read("OEBPS/section-1.xhtml").decode()
    # EPUB indexing flattens rendered title/body text and excludes image alt labels.
    assert conn.execute("SELECT title, text FROM epub_text_index WHERE card_id=41").fetchone() == (
        "Updated",
        "Updated Updated New content",
    )


def test_failed_edit_restores_archive_cache_index_and_does_not_replace_backup(editable_document, monkeypatch):
    import db
    import paths

    addon, profile, source, target, conn = editable_document
    snapshot = markdown_manager.load_markdown_document(addon, profile, target.name)
    before = target.read_bytes()
    cache = Path(epub_manager.get_epub_extract_dir(target.name, profile=profile))
    old_metadata = (cache / "metadata.json").read_bytes()

    def fail(*args, **kwargs):
        conn.execute("DELETE FROM epub_text_index WHERE card_id=41")
        raise RuntimeError("index failure")

    monkeypatch.setattr(db, "replace_epub_text_index", fail)
    with pytest.raises(RuntimeError, match="index failure"):
        markdown_manager.save_markdown_document(
            addon, profile, 41, target.name, "# New", title="Lesson", expected_revision=snapshot.revision
        )
    assert target.read_bytes() == before
    assert (cache / "metadata.json").read_bytes() == old_metadata
    assert conn.execute("SELECT text FROM epub_text_index WHERE card_id=41").fetchone() == ("Old content",)
    assert not paths.get_markdown_backup_path(addon, profile, target.name).exists()


@pytest.mark.parametrize("filename", ["../managed.epub", "/managed.epub", "folder/managed.epub"])
def test_markdown_editor_rejects_non_basename_managed_paths(tmp_path, filename):
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.load_markdown_document(str(tmp_path), "Captured", filename)


@pytest.mark.parametrize("text", ["", "  \n", "bad\x00text"])
def test_invalid_edited_source_leaves_the_managed_document_unchanged(editable_document, text):
    addon, profile, source, target, conn = editable_document
    snapshot = markdown_manager.load_markdown_document(addon, profile, target.name)
    before = target.read_bytes()
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.save_markdown_document(
            addon, profile, 41, target.name, text, title="Lesson", expected_revision=snapshot.revision
        )
    assert target.read_bytes() == before
    assert conn.execute("SELECT text FROM epub_text_index WHERE card_id=41").fetchone() == ("Old content",)


def test_markdown_editor_rejects_other_card_ownership_without_side_effects(editable_document):
    addon, profile, source, target, conn = editable_document
    snapshot = markdown_manager.load_markdown_document(addon, profile, target.name)
    before = target.read_bytes()
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.save_markdown_document(
            addon, profile, 99, target.name, "# Wrong card", title="Lesson", expected_revision=snapshot.revision
        )
    assert target.read_bytes() == before


def test_cache_swap_failure_restores_archive_and_index(editable_document, monkeypatch):
    addon, profile, source, target, conn = editable_document
    snapshot = markdown_manager.load_markdown_document(addon, profile, target.name)
    before = target.read_bytes()
    cache = Path(epub_manager.get_epub_extract_dir(target.name, profile=profile))
    metadata_before = (cache / "metadata.json").read_bytes()
    replace = markdown_manager.os.replace

    def fail(source_path, destination):
        if "markdown-edit-" in Path(source_path).name and Path(destination) == cache:
            raise OSError("cache swap failure")
        return replace(source_path, destination)

    monkeypatch.setattr(markdown_manager.os, "replace", fail)
    with pytest.raises(OSError, match="cache swap failure"):
        markdown_manager.save_markdown_document(
            addon, profile, 41, target.name, "# Revised", title="Lesson", expected_revision=snapshot.revision
        )
    assert target.read_bytes() == before
    assert (cache / "metadata.json").read_bytes() == metadata_before
    assert conn.execute("SELECT text FROM epub_text_index WHERE card_id=41").fetchone() == ("Old content",)


def _sections(prepared, tmp_path, monkeypatch):
    root = tmp_path / "extracted"
    monkeypatch.setattr(epub_manager, "get_epub_extract_root", lambda profile=None: str(root))
    metadata = epub_manager.ensure_epub_extracted(prepared.path, stored_filename="study.epub", profile="Captured")
    return metadata, [
        BeautifulSoup((root / "study.epub" / section["href"]).read_text(), "html.parser")
        for section in metadata["sections"]
    ]


def test_legacy_markdown_editor_bounds_total_rendered_html_before_parsing(tmp_path, monkeypatch):
    import paths

    source = tmp_path / "source.md"
    source.write_text("# Original\n\n![diagram](diagram.png)")
    target = paths.get_epub_dir(str(tmp_path), "Captured") / "legacy.epub"
    target.parent.mkdir(parents=True)
    with markdown_manager.prepare_markdown_epub(str(source)) as prepared:
        with zipfile.ZipFile(prepared.path) as archive, zipfile.ZipFile(target, "w") as legacy:
            for info in archive.infolist():
                if info.filename != "source_assets.json":
                    legacy.writestr(info.filename, archive.read(info))
    monkeypatch.setattr(markdown_manager, "MAX_LEGACY_HTML_BYTES", 128, raising=False)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.load_markdown_document(str(tmp_path), "Captured", target.name)


def test_markdown_preview_drops_resources_active_html_and_links():
    preview = markdown_manager.render_markdown_text_preview(
        '# Safe\n\n![remote](https://example.com/a.png)\n<script>attack()</script><a href="file:///secret">file</a> [external](https://example.com/)'
    )
    soup = BeautifulSoup(preview, "html.parser")
    assert soup.h1.get_text() == "Safe"
    assert not soup.find(["img", "script"])
    assert "remote" in soup.get_text()
    assert not soup.find("a", href=True)


def test_markdown_renders_headings_formatting_tables_code_and_cross_section_links(tmp_path, monkeypatch):
    source = tmp_path / "lesson.MD"
    text = "\ufeff# Lesson\n\nIntroduction **bold** and *italic*. [Next](#details)\n\n## Details\n\n- First\n- Second\n\n| Term | Meaning |\n| --- | --- |\n| A | Alpha |\n\n```python\nprint('<safe>')\n```\n"
    source.write_text(text, encoding="utf-8")
    with markdown_manager.prepare_markdown_epub(str(source), title="Study <Book>") as prepared:
        assert Path(prepared.path).stem == "lesson"
        metadata, sections = _sections(prepared, tmp_path, monkeypatch)
        assert metadata["title"] == "Study <Book>"
        assert [s["title"] for s in metadata["sections"]] == ["Lesson", "Details"]
        assert sections[0].strong.get_text() == "bold"
        assert sections[0].em.get_text() == "italic"
        assert sections[0].a["href"] == "section-2.xhtml#details"
        assert len(sections[1].select("ul li")) == 2
        assert sections[1].table is not None
        assert "print('<safe>')" in sections[1].pre.get_text()
        with zipfile.ZipFile(prepared.path) as archive:
            assert archive.read("source.md").decode("utf-8") == text
        temporary = Path(prepared.path).parent
    assert not temporary.exists()
    assert source.read_text(encoding="utf-8") == text


def test_markdown_copies_only_safe_local_raster_images_and_never_external_files(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
    )
    (source_dir / "diagram.png").write_bytes(png)
    (tmp_path / "outside.png").write_bytes(png)
    (source_dir / "alias.png").symlink_to(tmp_path / "outside.png")
    (source_dir / "active.svg").write_text('<svg onload="alert(1)"/>')
    source = source_dir / "book.md"
    source.write_text(
        "# Book\n\n![diagram](diagram.png)\n![escape](../outside.png)\n"
        "![symlink](alias.png)\n![vector](active.svg)\n![remote](https://example.com/a.png)\n"
        '<script>alert(1)</script><iframe src="file:///etc/passwd"></iframe>'
        '<img src="file:///etc/passwd" onerror="alert(1)">'
        '<a href="javascript:alert(1)" onclick="alert(1)">Bad</a>'
        "<style>body {background:url(file:///etc/passwd)}</style>",
        encoding="utf-8",
    )
    with markdown_manager.prepare_markdown_epub(str(source)) as prepared:
        _, sections = _sections(prepared, tmp_path, monkeypatch)
        assert [img.get("src") for img in sections[0].find_all("img")] == ["images/image-1.png"]
        assert sections[0].body.find(["script", "iframe", "style"]) is None
        assert "file:///etc/passwd" not in str(sections[0])
        assert not any(k.startswith("on") for tag in sections[0].find_all(True) for k in tag.attrs)
        assert sections[0].find("a", string="Bad").get("href") is None
        with zipfile.ZipFile(prepared.path) as archive:
            images = [name for name in archive.namelist() if name.startswith("OEBPS/images/")]
            assert images == ["OEBPS/images/image-1.png"]


@pytest.mark.parametrize("payload", [b"", b" \n\t", b"\xff\xfe", b"abc\x00def"])
def test_markdown_rejects_empty_binary_or_non_utf8_files_without_outputs(tmp_path, payload):
    source = tmp_path / "bad.md"
    source.write_bytes(payload)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.prepare_markdown_epub(str(source))
    assert list(tmp_path.iterdir()) == [source]


def test_markdown_rejects_oversized_source_instead_of_truncating(tmp_path, monkeypatch):
    source = tmp_path / "large.md"
    source.write_bytes(b"12345")
    monkeypatch.setattr(markdown_manager, "MAX_MARKDOWN_BYTES", 4)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.prepare_markdown_epub(str(source))


def test_markdown_without_headings_has_one_named_section(tmp_path, monkeypatch):
    source = tmp_path / "notes.markdown"
    source.write_text("A paragraph with a [safe link](https://example.com/).", encoding="utf-8")
    with markdown_manager.prepare_markdown_epub(str(source)) as prepared:
        metadata, sections = _sections(prepared, tmp_path, monkeypatch)
        assert [s["title"] for s in metadata["sections"]] == ["notes"]
        assert sections[0].a["href"] == "https://example.com/"


def test_markdown_rejects_symlink_source(tmp_path):
    source = tmp_path / "book.md"
    source.write_text("# Book", encoding="utf-8")
    alias = tmp_path / "alias.md"
    alias.symlink_to(source)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.prepare_markdown_epub(str(alias))


def test_markdown_image_size_limit_is_enforced_not_silently_omitted(tmp_path, monkeypatch):
    source = tmp_path / "book.md"
    source.write_text("# Book\n\n![too big](image.png)", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nlarge")
    monkeypatch.setattr(markdown_manager, "MAX_IMAGE_BYTES", 8)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.prepare_markdown_epub(str(source))


def test_markdown_reuses_images_and_blocks_symlinked_subdirectories(tmp_path, monkeypatch):
    source = tmp_path / "book.md"
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    (tmp_path / "alias").symlink_to(tmp_path / "images", target_is_directory=True)
    source.write_text("![first](images/a.png) ![again](images/a.png) ![alias](alias/a.png)", encoding="utf-8")
    with markdown_manager.prepare_markdown_epub(str(source)) as prepared:
        _, sections = _sections(prepared, tmp_path, monkeypatch)
        assert [img["src"] for img in sections[0].find_all("img")] == ["images/image-1.png"] * 2
        with zipfile.ZipFile(prepared.path) as archive:
            assert len([name for name in archive.namelist() if name.startswith("OEBPS/images/")]) == 1


def test_markdown_section_limit_fails_closed_and_fenced_headings_do_not_split(tmp_path, monkeypatch):
    source = tmp_path / "book.md"
    source.write_text("# One\n\n```text\n## not a section\n```\n\n## Two\n\nText", encoding="utf-8")
    monkeypatch.setattr(markdown_manager, "MAX_SECTIONS", 1)
    with pytest.raises(markdown_manager.MarkdownImportError):
        markdown_manager.prepare_markdown_epub(str(source))
    monkeypatch.setattr(markdown_manager, "MAX_SECTIONS", 2)
    with markdown_manager.prepare_markdown_epub(str(source)) as prepared:
        metadata, _ = _sections(prepared, tmp_path, monkeypatch)
        assert len(metadata["sections"]) == 2
