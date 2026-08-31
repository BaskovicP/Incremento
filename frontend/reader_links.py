"""Security boundary for links opened from untrusted reader documents."""

from __future__ import annotations

import json
import math
import re
from html import escape as _escape_html
from html.parser import HTMLParser
from urllib.parse import urlsplit


_MAX_EXTERNAL_READER_URL_CHARS = 4096
_ALLOWED_EXTERNAL_READER_SCHEMES = {"http", "https"}
READER_ANCHOR_MIME_TYPE = "application/x-incremento-reader-anchor+json"
_READER_ANCHOR_MIME_VERSION = 1
_MAX_READER_ANCHOR_HTML_CHARS = 32_768
_MAX_READER_ANCHOR_TEXT_CHARS = 2_048
_MAX_READER_ANCHOR_MIME_BYTES = 40_000
_READER_ANCHOR_STYLE = "cursor:pointer; color:#4a90d9; text-decoration:none;"
_READER_ANCHOR_ONCLICK_RE = re.compile(
    r'^pycmd\(("(?:\\.|[^"\\])*")\); return false;$'
)


class _ReaderAnchorHtmlParser(HTMLParser):
    """Parse the one narrow anchor shape Incremento puts on the clipboard."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.onclick = ""
        self.text_parts: list[str] = []
        self.started = False
        self.ended = False
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.started or self.ended or tag.casefold() != "a":
            self.invalid = True
            return
        normalized: dict[str, str] = {}
        for key, value in attrs:
            normalized_key = str(key or "").casefold()
            if not normalized_key or value is None or normalized_key in normalized:
                self.invalid = True
                return
            normalized[normalized_key] = str(value)
        if set(normalized) != {"onclick", "style"}:
            self.invalid = True
            return
        if normalized["style"] != _READER_ANCHOR_STYLE:
            self.invalid = True
            return
        self.onclick = normalized["onclick"]
        self.started = True

    def handle_endtag(self, tag: str) -> None:
        if not self.started or self.ended or tag.casefold() != "a":
            self.invalid = True
            return
        self.ended = True

    def handle_data(self, data: str) -> None:
        if not self.started or self.ended:
            if data.strip():
                self.invalid = True
            return
        self.text_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.invalid = True

    def handle_comment(self, data: str) -> None:
        self.invalid = True

    def handle_decl(self, decl: str) -> None:
        self.invalid = True

    def handle_pi(self, data: str) -> None:
        self.invalid = True


def _valid_reader_anchor_command(command: object) -> bool:
    if not isinstance(command, str) or not command or len(command) > 24_000:
        return False

    pdf_prefix = "incremento_open_pdf_ref:"
    if command.startswith(pdf_prefix):
        try:
            payload = json.loads(command[len(pdf_prefix) :])
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        allowed_keys = {
            "card_id",
            "filename",
            "page",
            "excerpt",
            "highlight_id",
            "scroll_ratio",
        }
        if not {"card_id", "filename", "page"}.issubset(payload) or not set(payload).issubset(
            allowed_keys
        ):
            return False
        card_id = payload.get("card_id")
        page = payload.get("page")
        filename = payload.get("filename")
        if (
            isinstance(card_id, bool)
            or not isinstance(card_id, int)
            or card_id <= 0
            or isinstance(page, bool)
            or not isinstance(page, int)
            or page <= 0
            or page > 1_000_000
            or not isinstance(filename, str)
            or not filename.strip()
            or len(filename) > 4_096
            or "\x00" in filename
        ):
            return False
        for key, limit in (("excerpt", 12_000), ("highlight_id", 1_024)):
            value = payload.get(key)
            if value is not None and (
                not isinstance(value, str) or len(value) > limit or "\x00" in value
            ):
                return False
        if "scroll_ratio" in payload:
            value = payload.get("scroll_ratio")
            if isinstance(value, bool):
                return False
            try:
                ratio = float(value)
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
                return False
        return True

    epub_prefix = "incremento_open_epub:"
    if command.startswith(epub_prefix):
        parts = command.split(":")
        if len(parts) not in {4, 5}:
            return False
        try:
            card_id = int(parts[1])
            section_index = int(parts[2])
            focus_offset = int(parts[3])
        except (TypeError, ValueError, OverflowError):
            return False
        if (
            card_id <= 0
            or section_index < 0
            or section_index > 1_000_000
            or focus_offset < -1
            or focus_offset > 50_000_000
        ):
            return False
        if len(parts) == 5:
            try:
                ratio = float(parts[4])
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
                return False
        return True

    return False


def _canonical_reader_anchor_html(raw_html: object) -> str | None:
    candidate = str(raw_html or "").strip()
    if (
        not candidate
        or len(candidate) > _MAX_READER_ANCHOR_HTML_CHARS
        or "\x00" in candidate
    ):
        return None
    parser = _ReaderAnchorHtmlParser()
    try:
        parser.feed(candidate)
        parser.close()
    except Exception:
        return None
    label = "".join(parser.text_parts).strip()
    if (
        parser.invalid
        or not parser.started
        or not parser.ended
        or not label
        or len(label) > _MAX_READER_ANCHOR_TEXT_CHARS
        or "\x00" in label
    ):
        return None
    match = _READER_ANCHOR_ONCLICK_RE.fullmatch(parser.onclick)
    if match is None:
        return None
    try:
        command = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not _valid_reader_anchor_command(command):
        return None
    onclick = _escape_html(
        f"pycmd({json.dumps(command)}); return false;",
        quote=True,
    )
    return (
        f'<a onclick="{onclick}" style="{_READER_ANCHOR_STYLE}">'
        f"{_escape_html(label)}</a>"
    )


def normalize_external_reader_url(raw_url: object) -> str | None:
    """Return a safe browser URL, or ``None`` for unsupported input."""
    candidate = str(raw_url or "").strip()
    if not candidate or len(candidate) > _MAX_EXTERNAL_READER_URL_CHARS:
        return None
    if "\\" in candidate or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() not in _ALLOWED_EXTERNAL_READER_SCHEMES:
            return None
        if not parsed.netloc or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        # Accessing ``port`` validates malformed or out-of-range port text.
        parsed.port
    except (TypeError, ValueError):
        return None
    return candidate


def _open_normalized_external_url(url: str) -> bool:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    target = QUrl(url)
    if not target.isValid():
        return False
    return bool(QDesktopServices.openUrl(target))


def open_external_reader_link(raw_url: object) -> bool:
    """Open an explicit HTTP(S) reader link in the system browser."""
    normalized = normalize_external_reader_url(raw_url)
    if normalized is None:
        return False
    try:
        return _open_normalized_external_url(normalized)
    except Exception:
        return False


def normalize_reader_anchor_scroll_ratio(raw_ratio: object) -> float | None:
    """Return a finite reader position bounded to the persisted 0..1 range."""
    if raw_ratio is None or isinstance(raw_ratio, bool):
        return None
    try:
        ratio = float(raw_ratio)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(ratio):
        return None
    return max(0.0, min(ratio, 1.0))


def set_reader_anchor_clipboard(
    html: object,
    plain_text: object,
    *,
    clipboard=None,
    mime_data_factory=None,
) -> bool:
    """Write a card-ready rich anchor plus a readable plain-text fallback."""
    rich_link = _canonical_reader_anchor_html(html)
    fallback = str(plain_text or "").strip()
    if (
        not rich_link
        or not fallback
        or len(fallback) > _MAX_READER_ANCHOR_TEXT_CHARS
        or "\x00" in rich_link
        or "\x00" in fallback
    ):
        return False
    try:
        if clipboard is None:
            from aqt.qt import QApplication

            app = QApplication.instance()
            if app is None:
                return False
            clipboard = app.clipboard()
        if mime_data_factory is None:
            from PyQt6.QtCore import QMimeData

            mime_data_factory = QMimeData
        mime_data = mime_data_factory()
        mime_data.setHtml(rich_link)
        mime_data.setText(fallback)
        marker = json.dumps(
            {"version": _READER_ANCHOR_MIME_VERSION, "html": rich_link},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        mime_data.setData(READER_ANCHOR_MIME_TYPE, marker)
        clipboard.setMimeData(mime_data)
        return True
    except Exception:
        return False


def reader_anchor_html_from_mime(mime_data) -> str | None:
    """Return a validated Incremento anchor from its private clipboard marker."""
    try:
        if not mime_data.hasFormat(READER_ANCHOR_MIME_TYPE):
            return None
        raw = bytes(mime_data.data(READER_ANCHOR_MIME_TYPE))
        if not raw or len(raw) > _MAX_READER_ANCHOR_MIME_BYTES:
            return None
        payload = json.loads(raw.decode("utf-8"))
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "html"}
        or payload.get("version") != _READER_ANCHOR_MIME_VERSION
        or not isinstance(payload.get("html"), str)
    ):
        return None
    return _canonical_reader_anchor_html(payload["html"])


def _new_mime_data():
    from PyQt6.QtCore import QMimeData

    return QMimeData()


def _schedule_reader_anchor_paste(callback) -> None:
    from aqt.qt import QTimer

    QTimer.singleShot(0, callback)


def force_reader_anchor_rich_paste(
    mime_data,
    editor_web_view,
    internal: bool,
    extended: bool,
    drop_event: bool,
):
    """Keep Incremento reader anchors clickable under Anki's plain-paste mode."""
    if internal or drop_event:
        return mime_data
    rich_link = reader_anchor_html_from_mime(mime_data)
    if rich_link is None:
        return mime_data
    try:
        editor = editor_web_view.editor
        replacement = _new_mime_data()

        def _paste() -> None:
            try:
                # Anki's external HTML sanitizer preserves only ``href`` on an
                # anchor and would remove Incremento's validated ``onclick``.
                # Treat this narrow, fully rebuilt private-MIME payload like an
                # internal field paste so the command remains clickable.
                editor.doPaste(rich_link, True, True)
            except Exception:
                return

        _schedule_reader_anchor_paste(_paste)
        return replacement
    except Exception:
        return mime_data


def show_reader_anchor_context_menu(
    view,
    position,
    *,
    resolver_script: str,
    on_copy,
    run_javascript=None,
    action_label: str = "Copy Link to This Place",
) -> bool:
    """Append an anchor-copy action to WebEngine's standard context menu."""
    try:
        menu = view.createStandardContextMenu()
        global_position = view.mapToGlobal(position)
    except Exception:
        return False

    try:
        view._incremento_reader_anchor_context_menu = menu
    except Exception:
        pass

    finished = False

    def _show_menu(payload=None) -> None:
        nonlocal finished
        if finished:
            return
        finished = True
        if isinstance(payload, dict):
            try:
                if menu.actions():
                    menu.addSeparator()
                action = menu.addAction(str(action_label))
                captured_payload = dict(payload)

                def _copy(_checked=False) -> None:
                    try:
                        on_copy(captured_payload)
                    except Exception:
                        return

                action.triggered.connect(_copy)
            except Exception:
                pass
        try:
            menu.exec(global_position)
        finally:
            try:
                if view._incremento_reader_anchor_context_menu is menu:
                    del view._incremento_reader_anchor_context_menu
            except Exception:
                pass

    try:
        runner = run_javascript or view.page().runJavaScript
        runner(str(resolver_script), _show_menu)
        return True
    except Exception:
        _show_menu(None)
        return True
