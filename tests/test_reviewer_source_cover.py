import importlib.util
import os
import subprocess

import pytest


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


def test_missing_cover_does_not_fill_thumbnail_with_wrapped_filename():
    js = build_reviewer_source_cover_js(
        "Saintly Habits_ Aquinas_ 7 Simple Strategies You Can Use to Grow in Virtue",
        cover_media="Saintly Habits_ Aquinas_ 7 Simple Strategies You Can Use to Grow in Virtue-cover.png",
    )
    browser = r"""
const vm = require('node:vm');
const source = require('node:fs').readFileSync(0, 'utf8');
const elements = new Map();
const host = { firstChild: null, insertBefore(el) { this.firstChild = el; el.parentElement = this; } };
const thumb = { style: {} };
const image = { alt: '', removeAttribute(name) { if (name === 'src') this.src = ''; } };
const label = { textContent: '' };
const title = { textContent: '' };
const selectors = {
  '.incremento-reviewer-source-cover-thumb': thumb,
  '.incremento-reviewer-source-cover-thumb img': image,
  '.incremento-reviewer-source-cover-label': label,
  '.incremento-reviewer-source-cover-title': title,
};
const classes = new Set();
const root = {
  parentElement: null,
  classList: {
    toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
    add(name) { classes.add(name); },
    remove(name) { classes.delete(name); },
  },
  querySelector(selector) { return selectors[selector]; },
  remove() { this.parentElement = null; },
};
const document = {
  body: host,
  head: { appendChild(el) { elements.set(el.id, el); } },
  getElementById(id) { return id === 'qa' ? host : elements.get(id); },
  createElement(tag) { if (tag === 'style') return {}; elements.set('incremento-reviewer-source-cover', root); return root; },
};
vm.runInNewContext(source, { document });
if (typeof image.onerror !== 'function') throw Error('missing cover has no fallback');
image.onerror();
if (thumb.style.display !== 'none' || image.alt !== '' || !classes.has('title-only') || classes.has('has-cover')) {
  throw Error('broken cover still crowds the source title');
}
if (!title.textContent.startsWith('Saintly Habits')) throw Error('source title was lost');
"""
    result = subprocess.run(["node", "-e", browser], input=js, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("unsafe_cover", [
    "https://example.invalid/cover.png", "../outside.png", "<img src=cover.png>",
])
def test_source_cover_never_loads_an_untrusted_media_reference(unsafe_cover):
    js = build_reviewer_source_cover_js("A source title", cover_media=unsafe_cover)

    assert unsafe_cover not in js
    assert 'var coverMedia = "";' in js
