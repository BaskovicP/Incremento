from types import SimpleNamespace

import image_rotation as rotation


class _FakeEditor:
    def __init__(self):
        self.added_buttons = []

    def addButton(self, icon, cmd, func, tip, label, id, disables):
        button = {
            "icon": icon,
            "cmd": cmd,
            "func": func,
            "tip": tip,
            "label": label,
            "id": id,
            "disables": disables,
        }
        self.added_buttons.append(button)
        return button


class _FakeWeb:
    def __init__(self):
        self.scripts = []

    def evalWithCallback(self, script, callback):
        self.scripts.append(script)
        callback("photo.png" if len(self.scripts) == 1 else True)


class _FakeMedia:
    def __init__(self, directory):
        self.directory = str(directory)
        self.writes = []

    def dir(self):
        return self.directory

    def write_data(self, desired_name, data):
        self.writes.append((desired_name, data))
        return desired_name


def test_media_filename_from_src_accepts_editor_media_urls():
    assert rotation._media_filename_from_src("photo.jpg") == "photo.jpg"
    assert rotation._media_filename_from_src("photo%20one.jpg") == "photo one.jpg"
    assert (
        rotation._media_filename_from_src("http://127.0.0.1:8765/folder/photo.jpg?x=1")
        == "photo.jpg"
    )


def test_media_filename_from_src_rejects_nonlocal_and_inline_images():
    assert rotation._media_filename_from_src("https://example.com/photo.jpg") is None
    assert rotation._media_filename_from_src("data:image/png;base64,abc") is None
    assert rotation._media_filename_from_src(None) is None


def test_output_format_preserves_common_formats_and_falls_back_to_png():
    assert rotation._output_format(b"jpeg") == (b"JPEG", ".jpg")
    assert rotation._output_format(b"PNG") == (b"PNG", ".png")
    assert rotation._output_format(b"webp") == (b"WEBP", ".webp")
    assert rotation._output_format(b"gif") == (b"PNG", ".png")


def test_rotated_media_name_uses_a_stable_suffix():
    assert rotation._rotated_media_name("photo.jpeg", ".jpg") == "photo_rotated.jpg"
    assert rotation._rotated_media_name("scan", ".png") == "scan_rotated.png"


def test_editor_toolbar_gets_left_and_right_rotation_buttons():
    editor = _FakeEditor()
    buttons = []

    rotation._add_image_rotation_buttons(buttons, editor)

    assert [button["id"] for button in buttons] == [
        rotation.ROTATE_LEFT_BUTTON_ID,
        rotation.ROTATE_RIGHT_BUTTON_ID,
    ]
    assert [button["label"] for button in buttons] == ["↶", "↷"]
    assert all(button["disables"] is False for button in buttons)


def test_tracker_and_replacement_scripts_preserve_selection_and_notify_editor():
    replacement_js = rotation._replace_selected_image_js("rotated photo.jpg")

    assert "event.composedPath()" in rotation._INSTALL_IMAGE_TRACKER_JS
    assert "state.selected = image" in rotation._INSTALL_IMAGE_TRACKER_JS
    assert 'replacement.setAttribute("src", "rotated photo.jpg")' in replacement_js
    assert 'new InputEvent("input"' in replacement_js
    assert "triggerChanges()" in replacement_js


def test_rotate_selected_image_writes_media_replaces_source_and_saves(
    tmp_path, monkeypatch
):
    (tmp_path / "photo.png").write_bytes(b"source")
    media = _FakeMedia(tmp_path)
    editor = _FakeEditor()
    editor.web = _FakeWeb()
    editor.save_calls = []

    def save(callback, keepFocus=False):
        editor.save_calls.append(keepFocus)
        callback()

    editor.call_after_note_saved = save
    messages = []
    monkeypatch.setattr(rotation, "mw", SimpleNamespace(col=SimpleNamespace(media=media)))
    monkeypatch.setattr(
        rotation,
        "_rotated_image_data",
        lambda path, degrees: (f"rotated:{path}:{degrees}".encode(), ".png"),
    )
    monkeypatch.setattr(rotation, "tooltip", messages.append)

    rotation._rotate_selected_image(editor, 90)

    assert media.writes == [
        (
            "photo_rotated.png",
            f"rotated:{tmp_path / 'photo.png'}:90".encode(),
        )
    ]
    assert 'replacement.setAttribute("src", "photo_rotated.png")' in editor.web.scripts[1]
    assert editor.save_calls == [True]
    assert messages == ["Image rotated."]
