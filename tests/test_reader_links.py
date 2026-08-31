import json
from html import escape
from pathlib import Path

import pytest

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
