import add_card_dock as dock
import sys
import types


class _FakeWindow:
    def __init__(self):
        self.set_menu_bar_args = []

    def setMenuBar(self, menu_bar):
        self.set_menu_bar_args.append(menu_bar)


class _FakeNote:
    def __init__(self, tags=None, note_id=0):
        self.tags = list(tags or [])
        self.id = note_id
        self.flush_calls = 0

    def string_tags(self):
        return " ".join(self.tags)

    def flush(self):
        self.flush_calls += 1


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


class _FakeDock:
    def __init__(self, editor):
        self.editor = editor
        self.calls = []

    def _set_field(self, idx, text, mark_topic=False):
        self.calls.append((idx, text, mark_topic))


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


class _FakeCol:
    class tags:
        @staticmethod
        def split(raw):
            return str(raw or "").split()


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


def test_configured_extract_priority_defaults_to_more_important_end():
    assert dock.configured_extract_priority({}) == 40.0
    assert dock.configured_extract_priority({"priority_lower_is_more_important": False}) == 60.0


def test_configured_extract_priority_clamps_values():
    assert dock.configured_extract_priority({"extract_priority": -5}) == 0.0
    assert dock.configured_extract_priority({"extract_priority": 120}) == 100.0
    assert dock.configured_extract_priority({"extract_priority": "37.125"}) == 37.125


def test_configured_extract_priority_multiplier_defaults_by_direction():
    assert dock.configured_extract_priority_multiplier({}) == 0.98
    assert dock.configured_extract_priority_multiplier({"priority_lower_is_more_important": False}) == 1.02


def test_calculate_extract_priority_uses_source_multiplier():
    assert dock.calculate_extract_priority(6, {"extract_priority_multiplier": 0.98}) == 5.88
    assert dock.calculate_extract_priority(60, {"extract_priority_multiplier": 1.02}) == 61.2


def test_calculate_extract_priority_falls_back_without_source():
    assert dock.calculate_extract_priority(None, {"extract_priority": 33}) == 33.0


def test_configured_extract_mark_topic_defaults_enabled():
    assert dock.configured_extract_mark_topic({}) is True
    assert dock.configured_extract_mark_topic({"extract_mark_topic": False}) is False


def test_configured_extract_copy_source_tags_defaults_disabled():
    assert dock.configured_extract_copy_source_tags({}) is False
    assert dock.configured_extract_copy_source_tags({"extract_copy_source_tags": True}) is True


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


def test_pending_extract_options_are_consumed_once(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    priority_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [101, 102])
    monkeypatch.setitem(
        sys.modules,
        "priority_manager",
        types.SimpleNamespace(
            set_priority=lambda addon_dir, profile, card_id, priority: priority_calls.append((card_id, priority))
        ),
    )

    dock.set_pending_extract_options(priority=25, mark_topic=True, source="pdf")
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["source"] == "pdf"
    assert result["priority_cards_changed"] == 2
    assert note.tags == ["existing", "topic"]
    assert priority_calls == [(101, 25.0), (102, 25.0)]
    assert dock.pending_extract_options() is None
    assert dock.consume_pending_extract_options_for_note(note) is None


def test_pending_extract_options_capture_source_card_id(monkeypatch):
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: 123 if source == "pdf" else None)

    options = dock.set_pending_extract_options(priority=25, mark_topic=False, source="pdf")

    assert options["source_card_id"] == 123


def test_consume_pending_extract_options_copies_source_tags_when_enabled(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    source_note = _FakeNote(["Topic", "Source", "source"], note_id=22)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)
    monkeypatch.setattr(
        dock,
        "mw",
        type(
            "MW",
            (),
            {
                "col": type(
                    "Col",
                    (),
                    {"get_card": staticmethod(lambda card_id: type("Card", (), {"note": lambda self: source_note})())},
                )()
            },
        )(),
    )

    dock.set_pending_extract_options(priority=25, mark_topic=False, source="pdf", source_card_id=99)
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["copied_source_tags"] == ["Topic", "Source"]
    assert note.tags == ["existing", "Topic", "Source"]
    assert saved == [["existing", "Topic", "Source"]]


def test_consume_pending_extract_options_skips_source_tags_when_disabled(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: False)
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)

    dock.set_pending_extract_options(priority=25, mark_topic=False, source="pdf", source_card_id=99)
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["copied_source_tags"] == []
    assert note.tags == ["existing"]
    assert saved == []


def test_consume_pending_extract_options_combines_source_and_topic_tags(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    source_note = _FakeNote(["Topic", "Source"], note_id=22)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic", "branch"])
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)
    monkeypatch.setattr(
        dock,
        "mw",
        type(
            "MW",
            (),
            {
                "col": type(
                    "Col",
                    (),
                    {"get_card": staticmethod(lambda card_id: type("Card", (), {"note": lambda self: source_note})())},
                )()
            },
        )(),
    )

    dock.set_pending_extract_options(priority=25, mark_topic=True, source="pdf", source_card_id=99)
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert note.tags == ["existing", "Topic", "Source", "branch"]
    assert saved == [["existing", "Topic", "Source", "branch"]]


def test_set_pending_extract_options_snapshots_source_tags(monkeypatch):
    source_note = _FakeNote(["Topic", "Source", "source"], note_id=22)

    monkeypatch.setattr(
        dock,
        "mw",
        type(
            "MW",
            (),
            {
                "col": type(
                    "Col",
                    (),
                    {"get_card": staticmethod(lambda card_id: type("Card", (), {"note": lambda self: source_note})())},
                )()
            },
        )(),
    )

    options = dock.set_pending_extract_options(
        priority=25,
        mark_topic=False,
        source="pdf",
        source_card_id=99,
    )

    assert options["source_tags"] == ["Topic", "Source"]


def test_consume_pending_extract_options_ignores_missing_source_card(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)
    monkeypatch.setattr(
        dock,
        "mw",
        type(
            "MW",
            (),
            {"col": type("Col", (), {"get_card": staticmethod(lambda card_id: None)})()},
        )(),
    )

    dock.set_pending_extract_options(priority=25, mark_topic=False, source="pdf", source_card_id=99)
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["copied_source_tags"] == []
    assert note.tags == ["existing"]
    assert saved == []


def test_consume_pending_extract_options_prefers_snapshot_source_tags(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)
    monkeypatch.setattr(
        dock,
        "copy_source_card_tags_to_note",
        lambda current_note, source_card_id: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    dock._pending_extract_options = {
        "priority": 25.0,
        "mark_topic": False,
        "source": "pdf",
        "source_card_id": 99,
        "source_tags": ["Topic", "Source"],
        "seen": 0.0,
    }
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["copied_source_tags"] == ["Topic", "Source"]
    assert note.tags == ["existing", "Topic", "Source"]
    assert saved == [["existing", "Topic", "Source"]]


def test_do_fill_forwards_mark_topic_to_embedded_dock(monkeypatch):
    fake_dock = _FakeDock(_FakeEditor(_FakeNote()))
    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)

    dock.do_fill(1, "extract text", mark_topic=True)

    assert fake_dock.calls == [(1, "extract text", True)]


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
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
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


def test_toggle_editor_item_button_removes_topic_tags(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "topic"], note_id=9), add_mode=False)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: func(),
    )

    dock._toggle_editor_tag_button(
        editor,
        ["item"],
        "unused",
        opposite_tags=["topic"],
    )

    assert editor.note.tags == ["keep", "item"]
    assert editor.tags.text_value == "keep item"


def test_toggle_editor_topic_button_removes_item_tags(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "item"], note_id=9), add_mode=False)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: func(),
    )

    dock._toggle_editor_tag_button(
        editor,
        ["topic"],
        "unused",
        opposite_tags=["item"],
    )

    assert editor.note.tags == ["keep", "topic"]
    assert editor.tags.text_value == "keep topic"
