"""Rotate images selected in Anki's note editor."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from aqt import gui_hooks, mw
    from aqt.qt import (
        QByteArray,
        QBuffer,
        QImageReader,
        QImageWriter,
        QIODevice,
        QTransform,
    )
    from aqt.utils import showWarning, tooltip
except Exception:  # pragma: no cover - only used outside Anki/test stubs.
    gui_hooks = None
    mw = None
    QByteArray = QBuffer = QImageReader = QImageWriter = QIODevice = QTransform = None

    def showWarning(_message: str) -> None:
        return None

    def tooltip(_message: str) -> None:
        return None


ROTATE_LEFT_BUTTON_ID = "incremento-rotate-image-left"
ROTATE_RIGHT_BUTTON_ID = "incremento-rotate-image-right"

_INSTALL_IMAGE_TRACKER_JS = r"""
(() => {
    const key = "__incrementoImageRotation";
    let state = window[key];
    if (!state) {
        state = { selected: null };
        window[key] = state;
        document.addEventListener("pointerdown", (event) => {
            const path = typeof event.composedPath === "function"
                ? event.composedPath()
                : [event.target];
            const image = path.find((node) => node && node.tagName === "IMG");
            if (image) {
                state.selected = image;
                return;
            }
            const editable = path.find((node) =>
                node && node.classList && node.classList.contains("rich-text-editable")
            );
            if (editable) {
                state.selected = null;
            }
        }, true);
    }
    state.selected = null;
})();
"""

_SELECTED_IMAGE_SOURCE_JS = r"""
(() => {
    const state = window.__incrementoImageRotation;
    const image = state && state.selected;
    if (!image || !image.isConnected || image.tagName !== "IMG") {
        return null;
    }
    return image.getAttribute("src") || image.src || null;
})();
"""


def _replace_selected_image_js(filename: str) -> str:
    encoded_filename = json.dumps(filename)
    return rf"""
(() => {{
    const state = window.__incrementoImageRotation;
    const image = state && state.selected;
    if (!image || !image.isConnected || image.tagName !== "IMG") {{
        return false;
    }}

    const replacement = image.cloneNode(true);
    replacement.setAttribute("src", {encoded_filename});

    const width = replacement.getAttribute("width");
    const height = replacement.getAttribute("height");
    if (width !== null && height !== null) {{
        replacement.setAttribute("width", height);
        replacement.setAttribute("height", width);
    }}
    if (replacement.style.width && replacement.style.height) {{
        const styleWidth = replacement.style.width;
        replacement.style.width = replacement.style.height;
        replacement.style.height = styleWidth;
    }}

    const editable = image.closest(".rich-text-editable")
        || image.closest('[contenteditable="true"]');
    image.replaceWith(replacement);
    state.selected = replacement;

    if (editable) {{
        try {{
            editable.dispatchEvent(new InputEvent("input", {{
                bubbles: true,
                inputType: "insertReplacementText",
            }}));
        }} catch (_error) {{
            editable.dispatchEvent(new Event("input", {{ bubbles: true }}));
        }}
    }}
    if (typeof triggerChanges === "function") {{
        triggerChanges();
    }}
    return true;
}})();
"""


def _media_filename_from_src(src: object) -> str | None:
    """Return an Anki media filename from a local editor image URL."""
    if not isinstance(src, str) or not src.strip():
        return None

    parsed = urlsplit(src.strip())
    scheme = parsed.scheme.lower()
    if scheme == "data":
        return None
    if scheme in {"http", "https"} and parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return None
    if scheme not in {"", "file", "http", "https"}:
        return None

    filename = os.path.basename(unquote(parsed.path)).strip()
    if not filename or filename in {".", ".."}:
        return None
    return filename


def _output_format(source_format: bytes) -> tuple[bytes, str]:
    normalized = bytes(source_format or b"").upper()
    if normalized in {b"JPG", b"JPEG"}:
        return b"JPEG", ".jpg"
    if normalized == b"PNG":
        return b"PNG", ".png"
    if normalized == b"WEBP":
        return b"WEBP", ".webp"
    return b"PNG", ".png"


def _write_only_flag():
    try:
        return QIODevice.OpenModeFlag.WriteOnly
    except AttributeError:  # pragma: no cover - compatibility with older Qt.
        return QIODevice.WriteOnly


def _rotated_image_data(path: str, degrees: int) -> tuple[bytes, str]:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    source_format = bytes(reader.format())
    image = reader.read()
    if image.isNull():
        detail = str(reader.errorString() or "unsupported or corrupt image")
        raise ValueError(detail)

    rotated = image.transformed(QTransform().rotate(degrees))
    output_format, extension = _output_format(source_format)
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    if not buffer.open(_write_only_flag()):
        raise ValueError("could not open an in-memory image buffer")

    writer = QImageWriter(buffer, output_format)
    if output_format in {b"JPEG", b"WEBP"}:
        writer.setQuality(92)
    if not writer.write(rotated):
        detail = str(writer.errorString() or "could not encode the rotated image")
        raise ValueError(detail)
    buffer.close()
    return bytes(byte_array), extension


def _rotated_media_name(filename: str, extension: str) -> str:
    stem = Path(filename).stem or "image"
    return f"{stem}_rotated{extension}"


def _rotate_selected_image(editor, degrees: int) -> None:
    web = getattr(editor, "web", None)
    if web is None or not hasattr(web, "evalWithCallback"):
        return

    def source_received(src) -> None:
        filename = _media_filename_from_src(src)
        if filename is None:
            tooltip("Select a local image in a card field first.")
            return

        collection = getattr(mw, "col", None)
        media = getattr(collection, "media", None)
        if media is None:
            showWarning("Anki's media collection is unavailable.")
            return

        source_path = os.path.join(media.dir(), filename)
        if not os.path.isfile(source_path):
            showWarning(f"Could not find the selected image in Anki media:\n{filename}")
            return

        try:
            data, extension = _rotated_image_data(source_path, degrees)
            new_filename = media.write_data(
                _rotated_media_name(filename, extension),
                data,
            )
        except Exception as exc:
            showWarning(f"Could not rotate the selected image:\n{exc}")
            return

        def image_replaced(changed) -> None:
            if not changed:
                tooltip(
                    "The selected image is no longer available. Select it and try again."
                )
                return

            save = getattr(editor, "call_after_note_saved", None)
            if callable(save):
                save(lambda: tooltip("Image rotated."), keepFocus=True)
            else:
                tooltip("Image rotated.")

        web.evalWithCallback(_replace_selected_image_js(new_filename), image_replaced)

    web.evalWithCallback(_SELECTED_IMAGE_SOURCE_JS, source_received)


def _rotate_left(editor) -> None:
    _rotate_selected_image(editor, -90)


def _rotate_right(editor) -> None:
    _rotate_selected_image(editor, 90)


def _add_image_rotation_buttons(buttons, editor) -> None:
    buttons.append(
        editor.addButton(
            None,
            "incrementoRotateImageLeft",
            _rotate_left,
            tip="Rotate selected image 90° left",
            label="↶",
            id=ROTATE_LEFT_BUTTON_ID,
            disables=False,
        )
    )
    buttons.append(
        editor.addButton(
            None,
            "incrementoRotateImageRight",
            _rotate_right,
            tip="Rotate selected image 90° right",
            label="↷",
            id=ROTATE_RIGHT_BUTTON_ID,
            disables=False,
        )
    )


def _install_image_tracker(editor) -> None:
    web = getattr(editor, "web", None)
    if web is not None and hasattr(web, "eval"):
        web.eval(_INSTALL_IMAGE_TRACKER_JS)


try:
    gui_hooks.editor_did_init_buttons.append(_add_image_rotation_buttons)
    gui_hooks.editor_did_load_note.append(_install_image_tracker)
except Exception:
    pass
