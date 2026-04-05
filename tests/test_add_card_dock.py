import add_card_dock as dock


class _FakeWindow:
    def __init__(self):
        self.set_menu_bar_args = []

    def setMenuBar(self, menu_bar):
        self.set_menu_bar_args.append(menu_bar)


class _FakeNote:
    def __init__(self, tags=None, note_id=0):
        self.tags = list(tags or [])
        self.id = note_id

    def string_tags(self):
        return " ".join(self.tags)


class _FakeEditor:
    def __init__(self, note=None, add_mode=False):
        self.note = note
        self.addMode = add_mode
        self.web = None
        self.added_buttons = []
        self.tags = _FakeTagsWidget()
        if note is not None:
            self.tags.setText(note.string_tags())
        self.saved_current_note = 0
        self.tag_focus_lost_calls = 0
        self.load_note_calls = 0

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

    def _save_current_note(self):
        self.saved_current_note += 1

    def on_tag_focus_lost(self):
        self.tag_focus_lost_calls += 1
        self.note.tags = self.tags.text().split()
        if not self.addMode:
            self._save_current_note()

    def loadNote(self):
        self.load_note_calls += 1


class _FakeTagsWidget:
    def __init__(self):
        self.col = None
        self.text_value = None
        self.updated = 0
        self.repainted = 0

    def setCol(self, col):
        self.col = col

    def setText(self, text):
        self.text_value = text

    def text(self):
        return self.text_value or ""

    def update(self):
        self.updated += 1

    def repaint(self):
        self.repainted += 1


def test_detach_embedded_window_menu_bar_removes_native_menu():
    window = _FakeWindow()

    dock._detach_embedded_window_menu_bar(window)

    assert window.set_menu_bar_args == [None]


def test_configured_extract_notetype_name_reads_config_value():
    assert dock.configured_extract_notetype_name({"extract_notetype": "Basic"}) == "Basic"
    assert dock.configured_extract_notetype_name({"extract_notetype": ""}) == ""
    assert dock.configured_extract_notetype_name({}) == ""


def test_configured_add_card_topic_tags_defaults_to_topic():
    assert dock.configured_add_card_topic_tags({}) == ["topic"]


def test_configured_add_card_item_tags_defaults_to_item():
    assert dock.configured_add_card_item_tags({}) == ["item"]


def test_configured_add_card_tag_lists_dedupe_case_insensitively():
    cfg = {
        "add_card_topic_tags": "Topic, topic, Focus",
        "add_card_item_tags": ["Item", "item", "Atom"],
    }
    assert dock.configured_add_card_topic_tags(cfg) == ["Topic", "Focus"]
    assert dock.configured_add_card_item_tags(cfg) == ["Item", "Atom"]


def test_configured_extract_source_links_supports_bool_backcompat():
    assert dock.configured_extract_source_links({"extract_source_links": True}) == {
        "pdf": True,
        "epub": True,
        "web": True,
        "parent": True,
    }
    assert dock.configured_extract_source_links({"extract_source_links": False}) == {
        "pdf": False,
        "epub": False,
        "web": False,
        "parent": False,
    }


def test_configured_extract_source_links_merges_partial_dict():
    assert dock.configured_extract_source_links(
        {"extract_source_links": {"pdf": False, "web": True}}
    ) == {
        "pdf": False,
        "epub": True,
        "web": True,
        "parent": True,
    }


def test_should_add_extract_source_link_reads_specific_kind():
    cfg = {"extract_source_links": {"pdf": False, "web": True, "parent": False}}
    assert dock.should_add_extract_source_link("pdf", cfg) is False
    assert dock.should_add_extract_source_link("web", cfg) is True
    assert dock.should_add_extract_source_link("parent", cfg) is False
    assert dock.should_add_extract_source_link("unknown", cfg) is True


def test_should_apply_extract_notetype_only_for_blank_mismatched_note():
    assert dock.should_apply_extract_notetype(
        "Basic",
        "Cloze",
        note_has_content=False,
    )
    assert not dock.should_apply_extract_notetype(
        "Basic",
        "Basic",
        note_has_content=False,
    )
    assert not dock.should_apply_extract_notetype(
        "Basic",
        "Cloze",
        note_has_content=True,
    )
    assert not dock.should_apply_extract_notetype(
        "",
        "Cloze",
        note_has_content=False,
    )


def test_note_has_all_tags_matches_case_insensitively():
    note = _FakeNote(["Topic", "extra"])

    assert dock._note_has_all_tags(note, ["topic"])
    assert not dock._note_has_all_tags(note, ["topic", "item"])


def test_toggle_note_tag_set_adds_all_missing_tags():
    note = _FakeNote(["existing"])

    active = dock._toggle_note_tag_set(note, ["topic", "item"])

    assert active is True
    assert note.tags == ["existing", "topic", "item"]


def test_toggle_note_tag_set_removes_existing_tags_case_insensitively():
    note = _FakeNote(["Topic", "ITEM", "keep"])

    active = dock._toggle_note_tag_set(note, ["topic", "item"])

    assert active is False
    assert note.tags == ["keep"]


def test_toggle_note_tag_set_preserves_unrelated_tags_and_avoids_duplicates():
    note = _FakeNote(["topic", "keep"])

    active = dock._toggle_note_tag_set(note, ["topic", "custom"])

    assert active is True
    assert note.tags == ["topic", "keep", "custom"]


def test_refresh_add_card_tag_buttons_updates_tracked_editors(monkeypatch):
    calls = []
    editor = _FakeEditor(_FakeNote(["topic"], note_id=1))
    dock._tracked_tag_button_editors.clear()
    dock._track_tag_button_editor(editor)
    monkeypatch.setattr(
        dock,
        "_refresh_add_card_tag_buttons_for_editor",
        lambda current_editor: calls.append(current_editor),
    )

    dock.refresh_add_card_tag_buttons()

    assert calls == [editor]


def test_on_editor_did_update_tags_refreshes_matching_edit_note(monkeypatch):
    calls = []
    matching_note = _FakeNote(["topic"], note_id=42)
    editor = _FakeEditor(matching_note, add_mode=False)
    dock._tracked_tag_button_editors.clear()
    dock._track_tag_button_editor(editor)
    monkeypatch.setattr(
        dock,
        "_refresh_add_card_tag_buttons_for_editor",
        lambda current_editor: calls.append(current_editor),
    )

    dock._on_editor_did_update_tags(_FakeNote(["item"], note_id=42))

    assert calls == [editor]


def test_toolbar_buttons_register_even_before_note_is_loaded():
    buttons = []
    editor = _FakeEditor(note=None, add_mode=False)

    dock._add_add_card_tag_toolbar_buttons(buttons, editor)

    assert [button["label"] for button in buttons] == ["T", "I"]


def test_toggle_editor_tag_button_saves_edit_current_note(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep"], note_id=9), add_mode=False)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": object()})())
    calls = []
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: (calls.append(delay), func()),
    )

    dock._toggle_editor_tag_button(editor, ["topic"], "unused")

    assert editor.note.tags == ["keep", "topic"]
    assert editor.tags.text_value == "keep topic"
    assert editor.tags.updated >= 1
    assert editor.tags.repainted >= 1
    assert calls == [0, 40, 0, 60]
    assert editor.tag_focus_lost_calls == 1
    assert editor.load_note_calls == 2
    assert editor.saved_current_note == 1
