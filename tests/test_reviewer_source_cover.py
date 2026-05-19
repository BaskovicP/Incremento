import importlib.util
import os


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cover = _load("_incremento_reviewer_source_cover", "frontend/reviewer_source_cover.py")

build_reviewer_source_cover_js = _cover.build_reviewer_source_cover_js


def test_build_reviewer_source_cover_js_renders_cover_and_title():
    js = build_reviewer_source_cover_js(
        "Deep Work",
        cover_media="deep-work-cover.png",
        source_label="Source PDF",
    )

    assert "incremento-reviewer-source-cover" in js
    assert "incremento-reviewer-source-cover-style" in js
    assert '"Deep Work"' in js
    assert '"deep-work-cover.png"' in js
    assert '"Source PDF"' in js
    assert "Source reference on this card opens the document." in js
    assert 'root.classList.toggle("has-cover", !!coverMedia)' in js
    assert "host.insertBefore(root, host.firstChild);" in js


def test_build_reviewer_source_cover_js_handles_title_only_payload():
    js = build_reviewer_source_cover_js("Deep Work", source_label="Source PDF")

    assert "var enabled = true;" in js
    assert 'root.classList.toggle("title-only", !coverMedia)' in js
    assert 'thumb.style.display = coverMedia ? "block" : "none";' in js


def test_build_reviewer_source_cover_js_removes_existing_root_when_disabled():
    js = build_reviewer_source_cover_js("", cover_media="", source_label="Source PDF")

    assert "var enabled = false;" in js
    assert "root.remove();" in js
