import json
from html import escape
from pathlib import Path

import pytest


def test_independent_reader_anchor_is_accepted_by_the_existing_trusted_paste_contract():
    from reader_links import make_reader_anchor_html, reader_anchor_command_from_html
    command = 'incremento_open_pdf_ref:{"card_id":7,"filename":"book.pdf","page":3,"scroll_ratio":0.25}'
    html = make_reader_anchor_html(command, '<Source "title">')
    assert reader_anchor_command_from_html(html) == command
    assert "&lt;Source" in html
    assert make_reader_anchor_html('javascript:alert(1)', 'Source') == ''

import reader_links


def _anchor_html(command, label="Page 3"):
    onclick = escape(f"pycmd({json.dumps(command)}); return false;", quote=True)
    return (
        f'<a onclick="{onclick}" '
        'style="cursor:pointer; color:#4a90d9; text-decoration:none;">'
        f"{escape(label)}</a>"
    )


class _MimeData:
    def __init__(self):
        self.html = ""
        self.text = ""
        self.formats = {}

    def setHtml(self, value):
        self.html = value

    def setText(self, value):
        self.text = value

    def setData(self, mime_type, value):
        self.formats[mime_type] = bytes(value)

    def hasFormat(self, mime_type):
        return mime_type in self.formats

    def data(self, mime_type):
        return self.formats.get(mime_type, b"")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.test/path?q=1#part", "https://example.test/path?q=1#part"),
        ("HTTP://example.test", "HTTP://example.test"),
        ("javascript:alert(1)", None),
        ("file:///etc/passwd", None),
        ("data:text/html,owned", None),
        ("mailto:user@example.test", None),
        ("https://user:secret@example.test/", None),
        ("https://example.test/line\nbreak", None),
        (r"https:\\example.test\\spoofed", None),
        ("https:///missing-host", None),
        ("", None),
    ],
)
def test_external_reader_links_allow_only_bounded_uncredentialed_http_urls(raw, expected):
    assert reader_links.normalize_external_reader_url(raw) == expected


def test_external_reader_link_opening_uses_only_the_normalized_url(monkeypatch):
    opened = []
    monkeypatch.setattr(
        reader_links,
        "_open_normalized_external_url",
        lambda url: opened.append(url) or True,
    )

    assert reader_links.open_external_reader_link("https://example.test/docs") is True
    assert reader_links.open_external_reader_link("javascript:alert(1)") is False
    assert opened == ["https://example.test/docs"]


@pytest.mark.parametrize("browser,app", [("chrome", "com.google.Chrome"), ("firefox", "org.mozilla.firefox")])
def test_pdf_and_epub_external_links_follow_the_selected_browser(monkeypatch, browser, app):
    import file_shell
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(file_shell, "_companion_browser", browser)
    monkeypatch.setattr(file_shell.sys, "platform", "darwin")
    monkeypatch.setattr(file_shell.subprocess, "run", lambda args, **_kw: calls.append(args) or SimpleNamespace(returncode=0))
    assert reader_links.open_external_reader_link("https://example.test/article#passage")
    assert calls == [["/usr/bin/open", "-b", app, "https://example.test/article#passage"]]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0.0),
        ("0.625", 0.625),
        (2, 1.0),
        (-3, 0.0),
        ("nan", None),
        (None, None),
    ],
)
def test_reader_anchor_scroll_ratio_is_finite_and_bounded(raw, expected):
    assert reader_links.normalize_reader_anchor_scroll_ratio(raw) == expected


def test_reader_anchor_clipboard_contains_rich_link_and_plain_text():
    class _Clipboard:
        def __init__(self):
            self.mime = None

        def setMimeData(self, mime):
            self.mime = mime

    clipboard = _Clipboard()
    command = (
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"scroll_ratio":0.4}'
    )
    rich_link = _anchor_html(command)

    assert reader_links.set_reader_anchor_clipboard(
        rich_link,
        "Document — page 3",
        clipboard=clipboard,
        mime_data_factory=_MimeData,
    ) is True
    assert clipboard.mime.html.startswith("<a ")
    assert "incremento_open_pdf_ref:" in clipboard.mime.html
    assert clipboard.mime.text == "Document — page 3"
    assert clipboard.mime.hasFormat(reader_links.READER_ANCHOR_MIME_TYPE)
    assert reader_links.reader_anchor_html_from_mime(clipboard.mime) == rich_link


def test_pdf_hover_context_includes_five_rows_before_and_after_excerpt():
    page_text = "\n".join(f"row {number}" for number in range(1, 18))

    preview = reader_links.pdf_hover_context_text(
        page_text,
        excerpt="row 9",
    )

    assert preview.splitlines() == [
        "…",
        "row 4",
        "row 5",
        "row 6",
        "row 7",
        "row 8",
        "row 9",
        "row 10",
        "row 11",
        "row 12",
        "row 13",
        "row 14",
        "…",
    ]


def test_pdf_hover_context_honors_configured_rows_before_and_after():
    page_text = "\n".join(f"row {number}" for number in range(1, 13))

    preview = reader_links.pdf_hover_context_text(
        page_text,
        excerpt="row 6",
        context_rows=2,
    )

    assert preview.splitlines() == [
        "…",
        "row 4",
        "row 5",
        "row 6",
        "row 7",
        "row 8",
        "…",
    ]


def test_pdf_hover_context_uses_scroll_position_for_links_without_an_excerpt():
    page_text = "\n".join(f"row {number}" for number in range(1, 21))

    preview = reader_links.pdf_hover_context_text(
        page_text,
        scroll_ratio=0.5,
    )

    assert preview.splitlines() == [
        "…",
        "row 6",
        "row 7",
        "row 8",
        "row 9",
        "row 10",
        "row 11",
        "row 12",
        "row 13",
        "row 14",
        "row 15",
        "row 16",
        "…",
    ]


def test_pdf_hover_context_marks_the_exact_extracted_sentence_blue():
    page_text = (
        "Earlier context on the same row. Reader first, last, and always! "
        "Later context on the same row."
    )

    preview = reader_links.pdf_hover_context_html(
        page_text,
        excerpt="Reader first, last, and always!",
    )

    assert "Earlier context on the same row." in preview
    assert "Later context on the same row." in preview
    assert (
        '<span class="incremento-pdf-hover-excerpt">'
        "Reader first, last, and always!</span>"
    ) in preview


def test_pdf_hover_context_marks_the_position_row_when_link_has_no_excerpt():
    page_text = "\n".join(f"row {number}" for number in range(1, 12))

    preview = reader_links.pdf_hover_context_html(
        page_text,
        scroll_ratio=0.5,
    )

    assert '<span class="incremento-pdf-hover-excerpt">row 6</span>' in preview


def test_pdf_hover_context_matches_excerpt_despite_pdf_punctuation_and_ligatures():
    page_text = (
        "Which book would people treasure?\n"
        "To help my student authors remember this, I coined the phrase "
        '"Reader ﬁrst, last, and always!" We have shortened it to "Reader First." '
        "Write it down. Post it on your computer.\n"
        "Later source material."
    )
    excerpt = (
        "To help my student authors remember this, I coined the phrase, "
        '“Reader first, last, and always!” We’ve shortened it to “Reader First.” '
        "Write it down. Post it on"
    )

    preview = reader_links.pdf_hover_context_html(page_text, excerpt=excerpt)

    assert "Which book would people treasure?" in preview
    assert '<span class="incremento-pdf-hover-excerpt">' in preview
    blue = preview.split('<span class="incremento-pdf-hover-excerpt">', 1)[1].split(
        "</span>", 1
    )[0]
    assert "student authors remember this" in blue
    assert "Reader first, last, and always" in blue
    assert "We’ve shortened it" in blue
    assert "Reader ﬁrst" not in blue
    assert "We have shortened it" not in blue
    assert "Which book would people treasure?" not in blue


def test_pdf_context_card_html_uses_exact_extracted_text_not_pdf_ocr_variant():
    page_text = (
        "Earlier context.\n"
        'The PDF says "Reader ﬁrst" and we have shortened it.\n'
        "Later context."
    )
    extracted = 'The PDF says “Reader first” and we’ve shortened it.'

    embedded = reader_links.pdf_context_card_html(
        page_text,
        excerpt=extracted,
        context_rows=1,
    )

    blue = embedded.split('class="incremento-pdf-context-excerpt"', 1)[1].split(
        "</span>", 1
    )[0]
    assert "Reader first" in blue
    assert "we’ve shortened it" in blue
    assert "Reader ﬁrst" not in blue
    assert "we have shortened it" not in blue


def test_pdf_hover_context_does_not_mark_an_unrelated_midpoint_as_the_excerpt():
    page_text = "\n".join(f"unrelated row {number}" for number in range(1, 18))

    assert reader_links.pdf_hover_context_html(
        page_text,
        excerpt="The extracted sentence is not present on this indexed page.",
    ) == ""


def test_pdf_context_card_html_embeds_centered_rows_for_mobile():
    page_text = "\n".join(f"row {number}" for number in range(1, 14))

    embedded = reader_links.pdf_context_card_html(
        page_text,
        excerpt="row 7",
        context_rows=2,
    )

    assert 'data-incremento-pdf-context="1"' in embedded
    assert 'class="incremento-pdf-context-excerpt"' in embedded
    assert ">row 7</span>" in embedded
    assert "row 4" not in embedded
    assert "row 5" in embedded
    assert "row 6" in embedded
    assert "row 8" in embedded
    assert "row 9" in embedded
    assert "row 10" not in embedded


def test_pdf_hover_preview_decorates_only_valid_incremento_links_and_escapes_pdf_text():
    command = (
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"owned"}'
    )
    rich_link = _anchor_html(command)
    hostile_page_text = "\n".join(
        [*(f"row {number}" for number in range(1, 8)), '<script>owned()</script>',
         *(f"row {number}" for number in range(9, 15))]
    )
    calls = []

    decorated = reader_links.decorate_pdf_reference_link_previews(
        f"Before {rich_link} after",
        lambda card_id, page: calls.append((card_id, page)) or hostile_page_text,
    )

    assert calls == [(7, 3)]
    assert 'class="incremento-pdf-hover-link"' in decorated
    assert 'class="incremento-pdf-hover-preview"' in decorated
    assert "&lt;script&gt;" in decorated
    assert "&lt;/script&gt;" in decorated
    assert "<script>owned()</script>" not in decorated
    assert decorated.count('id="incremento-pdf-hover-preview-style"') == 1
    assert 'onmouseenter="var preview=' in decorated
    assert 'onfocusin="var preview=' in decorated
    assert "excerpt.offsetTop" in decorated
    assert "Before " in decorated and " after" in decorated


def test_pdf_hover_preview_uses_card_text_for_legacy_link_without_excerpt():
    extracted = (
        "To help my student authors remember this, I coined the phrase, "
        "“Reader first, last, and always!” We’ve shortened it to “Reader First.” "
        "Write it down. Post it on"
    )
    page_text = (
        "Which book would people treasure?\n"
        "To help my student authors remember this, I coined the phrase "
        '"Reader first, last, and always!" We have shortened it to "Reader First." '
        "Write it down. Post it on your computer.\n"
        "Later source material."
    )
    legacy_link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf","page":3}'
    )

    decorated = reader_links.decorate_pdf_reference_link_previews(
        f'<div class="answer">{extracted}<br>{legacy_link}</div>',
        lambda _card_id, _page: page_text,
    )

    assert 'class="incremento-pdf-hover-preview"' in decorated
    blue = decorated.split(
        '<span class="incremento-pdf-hover-excerpt">', 1
    )[1].split("</span>", 1)[0]
    assert "student authors remember this" in blue
    assert "Which book would people treasure?" not in blue


def test_rebuild_pdf_reference_card_contexts_adds_mobile_context():
    extracted = "The exact extracted sentence."
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"The exact extracted sentence."}'
    )
    page_text = "Before one.\nThe exact extracted sentence.\nAfter one."

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_contexts(
        extracted + "<br>" + link,
        lambda card_id, page: page_text if (card_id, page) == (7, 3) else "",
        context_rows=1,
    )

    assert updated == 1
    assert skipped == 0
    assert rebuilt.count('data-incremento-pdf-context="1"') == 1
    assert "Before one." in rebuilt and "After one." in rebuilt
    assert ">The exact extracted sentence.</span>" in rebuilt


def test_rebuild_pdf_reference_card_contexts_replaces_existing_context_once():
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"Correct excerpt"}'
    )
    old_context = (
        '<div data-incremento-pdf-context="1" role="note">'
        '<span class="incremento-pdf-context-excerpt">Wrong text</span></div>'
    )

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_contexts(
        "Correct excerpt<br>" + link + "<br>" + old_context,
        lambda _card_id, _page: "Before\nCorrect excerpt\nAfter",
        context_rows=1,
    )

    assert updated == 1
    assert skipped == 0
    assert rebuilt.count('data-incremento-pdf-context="1"') == 1
    assert "Wrong text" not in rebuilt
    assert ">Correct excerpt</span>" in rebuilt

    repeated, repeated_updates, repeated_skips = (
        reader_links.rebuild_pdf_reference_card_contexts(
            rebuilt,
            lambda _card_id, _page: "Before\nCorrect excerpt\nAfter",
            context_rows=1,
        )
    )
    assert repeated == rebuilt
    assert repeated_updates == 0
    assert repeated_skips == 0


def test_pdf_snapshot_reference_html_shows_button_and_hides_image_until_opened():
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"The exact extracted sentence."}'
    )

    rendered = reader_links.pdf_snapshot_reference_html(
        "The exact extracted sentence.",
        link,
        "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )

    assert rendered.startswith("The exact extracted sentence.<br>" + link + "<br>")
    assert 'data-incremento-pdf-snapshot="1"' in rendered
    assert '<details class="incremento-pdf-snapshot-details"' in rendered
    assert '<summary' in rendered
    assert '>Source page preview</summary>' in rendered
    assert '<details class="incremento-pdf-snapshot-details" open' not in rendered
    assert rendered.count('src="incremento-pdf-context-abc123.png"') == 1
    assert 'alt="Source page preview"' in rendered
    assert "onmouseenter=" not in rendered
    assert "incremento-pdf-snapshot-popover" not in rendered
    assert "display:none" not in rendered


def test_rebuilding_text_fallback_replaces_its_control_with_one_snapshot():
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"Exact excerpt"}'
    )
    fallback = reader_links.pdf_text_context_reference_html(
        "Exact excerpt", link, "Before\nExact excerpt\nAfter",
        excerpt="Exact excerpt", context_rows=1, preview_label="Source page preview",
    )

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_snapshots(
        fallback + "<br>Keep this trailing text",
        lambda _payload, _excerpt: "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )

    assert updated == 1 and skipped == 0
    assert rebuilt.count("<summary") == 1
    assert 'incremento-pdf-context-details' not in rebuilt
    assert rebuilt.count('src="incremento-pdf-context-abc123.png"') == 1
    assert rebuilt.endswith("<br>Keep this trailing text")
    assert reader_links.rebuild_pdf_reference_card_snapshots(
        rebuilt,
        lambda _payload, _excerpt: "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    ) == (rebuilt, 0, 0)


def test_saved_hover_snapshot_gets_clickable_preview_without_changing_other_card_html():
    link = _anchor_html('incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf","page":3}')
    old_source = (
        '<span data-incremento-pdf-source-text="1" tabindex="0" '
        'style="cursor:help;" onmouseenter="show()" onmouseleave="hide()">'
        'Exact <b>source</b> text</span>'
    )
    old_snapshot = (
        '<div data-incremento-pdf-snapshot="1" style="display:block;">'
        '<div class="incremento-pdf-snapshot-popover" role="tooltip" style="display:none;">'
        '<img src="incremento-pdf-context-abc123.png" alt="Source page preview"></div>'
        '<details><summary>Source page preview</summary>'
        '<img src="incremento-pdf-context-abc123.png"></details>'
        '</div><!--incremento-pdf-snapshot-end-->'
    )
    original = "Before<br>" + old_source + "<br>" + link + "<br>" + old_snapshot + "<br>After"

    displayed = reader_links.collapsible_pdf_snapshot_previews(original)

    assert displayed.startswith('Before<br><span data-incremento-pdf-source-text="1">Exact <b>source</b> text</span>')
    assert displayed.endswith("<br>After")
    assert displayed.count('src="incremento-pdf-context-abc123.png"') == 1
    assert '<details class="incremento-pdf-snapshot-details"' in displayed
    assert '>Source page preview</summary>' in displayed
    assert "onmouseenter=" not in displayed
    assert "incremento-pdf-snapshot-popover" not in displayed
    assert reader_links.collapsible_pdf_snapshot_previews(displayed) == displayed


def test_saved_always_visible_snapshot_gets_closed_preview_control():
    saved_inline = (
        '<div data-incremento-pdf-snapshot="1" '
        'class="incremento-pdf-snapshot-inline">'
        '<img src="incremento-pdf-context-abc123.png" '
        'alt="Source page preview"></div><!--incremento-pdf-snapshot-end-->'
    )

    displayed = reader_links.collapsible_pdf_snapshot_previews(saved_inline)

    assert '<details class="incremento-pdf-snapshot-details"' in displayed
    assert '<summary' in displayed
    assert '>Source page preview</summary>' in displayed
    assert displayed.count('src="incremento-pdf-context-abc123.png"') == 1
    assert 'incremento-pdf-snapshot-inline' not in displayed
    assert reader_links.collapsible_pdf_snapshot_previews(displayed) == displayed


@pytest.mark.parametrize("kind", ["snapshot", "context"])
def test_saved_preview_click_guard_preserves_card_content_and_open_state(kind):
    saved = (
        '<p title="Keep > this">Before</p>\n'
        f"<details class='extra incremento-pdf-{kind}-details' open data-label='A &amp; B'>"
        '<summary>Source <b>page</b> preview</summary>\n'
        '<div>Saved <i>context</i></div></details>\n<p>After</p>'
    )

    displayed = reader_links.collapsible_pdf_snapshot_previews(saved)

    assert displayed == saved.replace(
        f"<details class='extra incremento-pdf-{kind}-details' open data-label='A &amp; B'>",
        f'<details class="extra incremento-pdf-{kind}-details" open data-label="A &amp; B" '
        'onclick="event.stopPropagation();">',
    )
    assert reader_links.collapsible_pdf_snapshot_previews(displayed) == displayed


def test_preview_click_guard_leaves_unrelated_controls_scripts_and_comments_unchanged():
    saved = (
        '<details onclick="customClick()"><summary>My control</summary>My text</details>'
        '<script>const example = \'<details class="incremento-pdf-snapshot-details">\';</script>'
        '<!-- <details class="incremento-pdf-context-details"> -->'
    )

    assert reader_links.collapsible_pdf_snapshot_previews(saved) == saved


def test_saved_snapshot_label_is_escaped_in_reveal_control():
    saved = (
        '<div data-incremento-pdf-snapshot="1" '
        'class="incremento-pdf-snapshot-inline">'
        '<img src="incremento-pdf-context-abc123.png" '
        'alt="&lt;script&gt;alert(1)&lt;/script&gt;">'
        '</div><!--incremento-pdf-snapshot-end-->'
    )

    displayed = reader_links.collapsible_pdf_snapshot_previews(saved)

    assert '<summary' in displayed
    assert '&lt;script&gt;alert(1)&lt;/script&gt;</summary>' in displayed
    assert '<script>' not in displayed


def test_saved_hover_snapshot_with_non_media_path_is_left_unchanged():
    old_snapshot = (
        '<div data-incremento-pdf-snapshot="1">'
        '<div class="incremento-pdf-snapshot-popover">'
        '<img src="../private/image.png" alt="Source page preview"></div>'
        '</div><!--incremento-pdf-snapshot-end-->'
    )

    assert reader_links.collapsible_pdf_snapshot_previews(old_snapshot) == old_snapshot


def test_reviewer_converts_saved_snapshot_previews_to_clickable_button():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text(encoding="utf-8")

    assert "_reader_links_mod.collapsible_pdf_snapshot_previews(repaired)" in source


def test_rebuild_pdf_reference_card_snapshots_replaces_text_context_and_is_idempotent():
    extracted = "The exact extracted sentence."
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"The exact extracted sentence."}'
    )
    old_context = (
        '<div data-incremento-pdf-context="1" role="note">Old indexed text</div>'
    )
    calls = []

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_snapshots(
        extracted + "<br>" + link + "<br>" + old_context,
        lambda payload, excerpt: calls.append((payload, excerpt))
        or "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )

    assert calls[0][0]["card_id"] == 7
    assert calls[0][1] == extracted
    assert updated == 1
    assert skipped == 0
    assert "Old indexed text" not in rebuilt
    assert rebuilt.count('data-incremento-pdf-snapshot="1"') == 1
    assert rebuilt.startswith(extracted + "<br>" + link + "<br>")
    assert '<details class="incremento-pdf-snapshot-details"' in rebuilt

    repeated, repeated_updates, repeated_skips = (
        reader_links.rebuild_pdf_reference_card_snapshots(
            rebuilt,
            lambda _payload, _excerpt: "incremento-pdf-context-abc123.png",
            preview_label="Source page preview",
        )
    )
    assert repeated == rebuilt
    assert repeated_updates == 0
    assert repeated_skips == 0


def test_rebuild_pdf_reference_card_snapshots_uses_complete_selection_beyond_citation_excerpt():
    selected = " ".join(f"Selected row {number}." for number in range(1, 35))
    stored_excerpt = selected[:320]
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":' + json.dumps(stored_excerpt) + "}"
    )
    seen = []

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_snapshots(
        selected + "<br>" + link,
        lambda _payload, excerpt: seen.append(excerpt)
        or ("incremento-pdf-context-abc123.png" if excerpt == selected else ""),
        preview_label="Source page preview",
    )

    assert seen[0] == selected
    assert updated == 1
    assert skipped == 0
    assert 'data-incremento-pdf-snapshot="1"' in rebuilt


def test_rebuild_pdf_reference_card_snapshots_removes_legacy_blue_source_style():
    extracted = "The exact extracted sentence."
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"The exact extracted sentence."}'
    )
    legacy_source = (
        '<span data-incremento-pdf-source-text="1" tabindex="0" '
        'style="color:#60a5fa;font-weight:700;cursor:help;">'
        f"{extracted}</span>"
    )
    snapshot = reader_links.pdf_snapshot_card_html(
        "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_snapshots(
        legacy_source + "<br>" + link + "<br>" + snapshot,
        lambda _payload, _excerpt: "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )

    source_markup = rebuilt.split("<br>", 1)[0]
    assert updated == 1
    assert skipped == 0
    assert source_markup == (
        '<span data-incremento-pdf-source-text="1">'
        + extracted + '</span>'
    )
    assert "color:" not in source_markup
    assert "font-weight:" not in source_markup


def test_rebuild_pdf_reference_card_snapshots_repairs_legacy_malformed_link():
    extracted = "The exact extracted sentence."
    legacy_link = (
        '<a onclick="pycmd(" incremento_open_pdf_ref:{\\"card_id\\":="" 7,="" '
        '\\"filename\\":="" \\"document.pdf\\",="" \\"page\\":="" 3}");="" '
        'return="" false;"="" style="cursor:pointer; color:#4a90d9; '
        'text-decoration:none;">Page 3. of Document</a>'
    )
    calls = []

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_snapshots(
        extracted + "<br>" + legacy_link,
        lambda payload, excerpt: calls.append((payload, excerpt))
        or "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )

    assert calls == [
        (
            {"card_id": 7, "filename": "document.pdf", "page": 3},
            extracted,
        )
    ]
    assert updated == 1
    assert skipped == 0
    assert rebuilt.startswith(extracted + "<br>")
    assert 'data-incremento-pdf-snapshot="1"' in rebuilt
    assert 'src="incremento-pdf-context-abc123.png"' in rebuilt
    assert 'onclick="pycmd(&quot;incremento_open_pdf_ref:' in rebuilt
    assert '=""' not in rebuilt


def test_rebuild_pdf_reference_card_snapshots_shows_each_image_below_its_citation():
    first = "First extracted passage."
    second = "Second extracted passage."
    first_link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf","page":1}'
    )
    second_link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf","page":2}'
    )
    seen = []

    def snapshot_loader(payload, excerpt):
        seen.append((payload["page"], excerpt))
        if payload["page"] == 1 and first in excerpt:
            return "incremento-pdf-context-first.png"
        if payload["page"] == 2 and second in excerpt:
            return "incremento-pdf-context-second.png"
        return ""

    rebuilt, updated, skipped = reader_links.rebuild_pdf_reference_card_snapshots(
        first + "<br>" + first_link + "<br><br>" + second + "<br>" + second_link,
        snapshot_loader,
        preview_label="Source page preview",
    )

    assert updated == 2
    assert skipped == 0
    assert rebuilt.count('data-incremento-pdf-snapshot="1"') == 2
    assert rebuilt.index(first) < rebuilt.index('src="incremento-pdf-context-first.png"')
    assert rebuilt.index(second) < rebuilt.index('src="incremento-pdf-context-second.png"')
    assert rebuilt.count('<details class="incremento-pdf-snapshot-details"') == 2
    assert (2, second) in seen

    repeated, repeated_updates, repeated_skips = (
        reader_links.rebuild_pdf_reference_card_snapshots(
            rebuilt,
            snapshot_loader,
            preview_label="Source page preview",
        )
    )
    assert repeated == rebuilt
    assert repeated_updates == 0
    assert repeated_skips == 0


def test_pdf_hover_preview_leaves_invalid_and_unindexed_links_unchanged():
    valid_link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"missing"}'
    )
    unsafe_link = '<a onclick="pycmd(&quot;owned&quot;)">bad</a>'
    original = valid_link + unsafe_link

    assert reader_links.decorate_pdf_reference_link_previews(
        original,
        lambda _card_id, _page: "",
    ) == original


def test_saved_pdf_snapshot_prevents_duplicate_legacy_link_hover_preview():
    link = _anchor_html(
        'incremento_open_pdf_ref:{"card_id":7,"filename":"document.pdf",'
        '"page":3,"excerpt":"Exact excerpt"}'
    )
    saved = reader_links.pdf_snapshot_reference_html(
        "Exact excerpt",
        link,
        "incremento-pdf-context-abc123.png",
        preview_label="Source page preview",
    )
    calls = []

    assert reader_links.decorate_pdf_reference_link_previews(
        saved,
        lambda card_id, page: calls.append((card_id, page)) or "Exact excerpt",
    ) == saved
    assert calls == []


@pytest.mark.parametrize(
    ("command", "label"),
    [
        (
            'incremento_open_pdf_ref:{"card_id":55,"filename":"document.pdf",'
            '"page":10,"scroll_ratio":0.375}',
            "Page 10. of Document",
        ),
        ("incremento_open_epub:77:3:8:0.375", "Chapter Four"),
    ],
    ids=["pdf", "epub"],
)
def test_reader_anchor_paste_forces_clickable_html_when_anki_strips_formatting(
    monkeypatch,
    command,
    label,
):
    class _Clipboard:
        def __init__(self):
            self.mime = None

        def setMimeData(self, mime):
            self.mime = mime

    rich_link = _anchor_html(command, label)
    clipboard = _Clipboard()
    assert reader_links.set_reader_anchor_clipboard(
        rich_link,
        "Book — Chapter Four",
        clipboard=clipboard,
        mime_data_factory=_MimeData,
    )

    paste_calls = []
    scheduled = []

    class _Editor:
        def doPaste(self, html, internal, extended):
            paste_calls.append((html, internal, extended))

    class _EditorWebView:
        editor = _Editor()

    monkeypatch.setattr(
        reader_links,
        "_schedule_reader_anchor_paste",
        lambda callback: scheduled.append(callback),
    )
    monkeypatch.setattr(reader_links, "_new_mime_data", _MimeData)

    replacement = reader_links.force_reader_anchor_rich_paste(
        clipboard.mime,
        _EditorWebView(),
        False,
        False,
        False,
    )

    assert replacement is not clipboard.mime
    assert scheduled and paste_calls == []
    scheduled.pop()()
    # Anki's external-rich sanitizer keeps only an anchor's href and strips the
    # validated Incremento onclick command. The private marker is accepted as
    # internal only after reader_anchor_html_from_mime() has rebuilt the exact
    # allow-listed anchor shape.
    assert paste_calls == [(rich_link, True, True)]


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps({"version": 99, "html": "<b>future</b>"}).encode(),
        json.dumps(
            {
                "version": 1,
                "html": '<img src=x onerror="pycmd(owned)">',
            }
        ).encode(),
        json.dumps(
            {
                "version": 1,
                "html": _anchor_html("incremento_open_epub:0:3:8:0.5"),
            }
        ).encode(),
    ],
)
def test_reader_anchor_mime_rejects_malformed_future_and_unsafe_payloads(payload):
    mime = _MimeData()
    mime.setData(reader_links.READER_ANCHOR_MIME_TYPE, payload)

    assert reader_links.reader_anchor_html_from_mime(mime) is None


def test_reader_anchor_rich_paste_hook_is_registered():
    addon_init = Path(__file__).resolve().parents[1] / "__init__.py"
    source = addon_init.read_text(encoding="utf-8")

    assert "from .frontend import reader_links as _reader_links_mod" in source
    assert (
        "gui_hooks.editor_will_process_mime.append(\n"
        "    _reader_links_mod.force_reader_anchor_rich_paste\n"
        ")"
    ) in source


def test_reviewer_pdf_hover_preview_is_wired_to_setting_and_bounded_page_text():
    addon_init = Path(__file__).resolve().parents[1] / "__init__.py"
    source = addon_init.read_text(encoding="utf-8")

    assert 'cfg.get("pdf_link_hover_preview_enabled", True)' in source
    assert "_reader_links_mod.decorate_pdf_reference_link_previews(" in source
    assert "context_rows=_pdf_dock_mod.configured_pdf_context_rows(cfg)" in source
    assert "max_chars=250_000" in source
    assert (
        "gui_hooks.card_will_show.append(_repair_legacy_pdf_reference_links)"
        in source
    )


def test_reader_anchor_context_menu_preserves_standard_menu_and_copies_resolved_anchor():
    copied = []

    class _Signal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

        def emit(self):
            self.callback(False)

    class _Action:
        def __init__(self, text):
            self.text = text
            self.triggered = _Signal()

    class _Menu:
        def __init__(self):
            self._actions = [object()]
            self.separator_count = 0
            self.added_action = None
            self.executed_at = None

        def actions(self):
            return list(self._actions)

        def addSeparator(self):
            self.separator_count += 1

        def addAction(self, text):
            self.added_action = _Action(text)
            self._actions.append(self.added_action)
            return self.added_action

        def exec(self, position):
            self.executed_at = position

    class _Page:
        def runJavaScript(self, script, callback):
            assert script == "resolveAnchor()"
            callback({"cardId": 7, "page": 3, "scrollRatio": 0.4})

    class _View:
        def __init__(self):
            self.menu = _Menu()

        def createStandardContextMenu(self):
            return self.menu

        def mapToGlobal(self, position):
            return ("global", position)

        def page(self):
            return _Page()

    view = _View()

    assert reader_links.show_reader_anchor_context_menu(
        view,
        (10, 20),
        resolver_script="resolveAnchor()",
        on_copy=lambda payload: copied.append(payload),
    ) is True

    assert view.menu.separator_count == 1
    assert view.menu.added_action.text == "Copy Link to This Place"
    assert view.menu.executed_at == ("global", (10, 20))
    view.menu.added_action.triggered.emit()
    assert copied == [{"cardId": 7, "page": 3, "scrollRatio": 0.4}]
