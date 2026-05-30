import add_card_dock as dock
import sys
import types


class _FakeWindow:
    def __init__(self):
        self.set_menu_bar_args = []

    def setMenuBar(self, menu_bar):
        self.set_menu_bar_args.append(menu_bar)


class _FakeNote:
    def __init__(self, tags=None, note_id=0, field_names=None):
        self.tags = list(tags or [])
        self.id = note_id
        self.flush_calls = 0
        self._field_names = list(field_names or ["Front", "Back"])
        self.fields = ["" for _ in self._field_names]
        self._field_map = {name: index for index, name in enumerate(self._field_names)}
        self._note_type = {
            "name": "Basic",
            "flds": [{"name": name} for name in self._field_names],
        }

    def string_tags(self):
        return " ".join(self.tags)

    def flush(self):
        self.flush_calls += 1

    def note_type(self):
        return self._note_type

    def __contains__(self, field_name):
        return field_name in self._field_map

    def __getitem__(self, field_name):
        return self.fields[self._field_map[field_name]]

    def __setitem__(self, field_name, value):
        self.fields[self._field_map[field_name]] = value


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


class _FakeWeb:
    def __init__(self):
        self.eval_calls = []

    def eval(self, js):
        self.eval_calls.append(js)


class _FakeDock:
    def __init__(self, editor):
        self.editor = editor
        self.calls = []
        self._addcards_dialog = None

    def _set_field(self, idx, text, mark_topic=False):
        self.calls.append((idx, text, mark_topic))


class _FakeAddCardsDialog:
    def __init__(self, editor):
        self.editor = editor
        self.note_type_ids = []
        self.deck_ids = []

    def set_note_type(self, note_type_id):
        self.note_type_ids.append(note_type_id)

    def set_deck(self, deck_id):
        self.deck_ids.append(deck_id)


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


def test_note_has_any_tags_matches_case_insensitively():
    note = _FakeNote(["Topic", "extra"])

    assert dock._note_has_any_tags(note, ["topic"])
    assert dock._note_has_any_tags(note, ["item", "TOPIC"])
    assert not dock._note_has_any_tags(note, ["item"])


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


def test_fill_dock_field_prepares_pdf_extract_parent_context(monkeypatch):
    filled = []
    refresh_calls = []
    delayed_refreshes = []
    fake_dock = types.SimpleNamespace(
        show=lambda: None,
        raise_=lambda: None,
        _set_field=lambda idx, text, mark_topic=False: filled.append((idx, text, mark_topic)),
    )
    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(dock, "_apply_configured_extract_notetype", lambda: None)
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: 55 if source == "pdf" else None)
    monkeypatch.setattr(dock, "source_note_tags_for_card", lambda source_card_id: ["source"])
    monkeypatch.setattr(dock, "source_relative_extract_priority_for_source", lambda source: 18)
    monkeypatch.setattr(
        dock,
        "_source_extract_metadata_for_card",
        lambda source, source_card_id: {"Incremento_Parent_Card_ID": str(source_card_id)},
    )
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: refresh_calls.append(True))
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: delayed_refreshes.append(delay),
    )

    dock.fill_dock_field(
        0,
        "Excerpt",
        include_pdf_citation=False,
        source_link_kind="pdf",
    )

    assert filled == [(0, "Excerpt", False)]
    assert dock.pending_extract_options()["source"] == "pdf"
    assert dock.pending_extract_options()["source_card_id"] == 55
    assert dock.pending_extract_options()["priority"] == 18.0
    assert dock.pending_extract_context()["parent_card_id"] == 55
    assert dock.pending_extract_context()["metadata"] == {"Incremento_Parent_Card_ID": "55"}
    assert refresh_calls == [True]
    assert delayed_refreshes == [80]
    dock.clear_pending_extract_options()
    dock.clear_pending_extract_context()


def test_fill_dock_field_resets_current_extract_priority_from_pdf_parent(monkeypatch):
    fake_dock = types.SimpleNamespace(
        show=lambda: None,
        raise_=lambda: None,
        _set_field=lambda idx, text, mark_topic=False: None,
    )

    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(dock, "_apply_configured_extract_notetype", lambda: None)
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: 55 if source == "pdf" else None)
    monkeypatch.setattr(dock, "source_note_tags_for_card", lambda source_card_id: [])
    monkeypatch.setattr(dock, "source_relative_extract_priority_for_source", lambda source: 18.0)
    monkeypatch.setattr(dock, "_source_extract_metadata_for_card", lambda source, source_card_id: {})
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(dock.QTimer, "singleShot", lambda delay, func: None)
    monkeypatch.setattr(dock, "_current_extract_priority", 77.0)

    dock.fill_dock_field(
        0,
        "Excerpt",
        include_pdf_citation=False,
        source_link_kind="pdf",
    )

    assert dock._current_extract_priority == 18.0
    dock.clear_pending_extract_options()
    dock.clear_pending_extract_context()


def test_fill_dock_field_passes_excerpt_text_to_pdf_citation(monkeypatch):
    filled = []
    fake_dock = types.SimpleNamespace(
        show=lambda: None,
        raise_=lambda: None,
        _set_field=lambda idx, text, mark_topic=False: filled.append((idx, text, mark_topic)),
    )
    captured = []

    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(dock, "_apply_configured_extract_notetype", lambda: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(dock.QTimer, "singleShot", lambda delay, func: None)
    monkeypatch.setattr(dock, "__package__", "frontend")
    monkeypatch.setitem(
        sys.modules,
        "frontend.pdf_dock",
        types.SimpleNamespace(
            pdf_citation=lambda excerpt_text=None: captured.append(excerpt_text) or "Citation",
        ),
    )

    dock.fill_dock_field(0, "Excerpt text")

    assert captured == ["Excerpt text"]
    assert filled == [(0, "Excerpt text<br>Citation", False)]


def test_source_card_id_for_transfer_reads_video_source(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "video_dock",
        types.SimpleNamespace(current_video_card_id=lambda: 456),
    )

    assert dock._source_card_id_for_transfer("video") == 456


def test_on_add_cards_did_add_note_notifies_video_extract_source(monkeypatch):
    note = _FakeNote(note_id=11)
    notify_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [701])
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)
    monkeypatch.setattr(dock, "consume_pending_extract_context_for_note", lambda current_note, options=None: {})
    monkeypatch.setitem(
        sys.modules,
        "video_dock",
        types.SimpleNamespace(
            on_video_extract_note_added=lambda source_card_id, created_card_ids: notify_calls.append(
                (source_card_id, list(created_card_ids))
            )
        ),
    )

    dock.set_pending_extract_options(
        priority=25,
        mark_topic=False,
        source="video",
        source_card_id=321,
    )

    dock.on_add_cards_did_add_note(note)

    assert notify_calls == [(321, [701]), (321, [701])]


def test_sync_pending_extract_options_from_current_carries_tree_link(monkeypatch):
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: 77 if source == "reviewer" else None)
    dock._last_selection_source = "reviewer"
    dock.set_current_extract_options(priority=33, mark_topic=True, link_to_knowledge_tree=True)

    options = dock.sync_pending_extract_options_from_current()

    assert options is not None
    assert options["priority"] == 33.0
    assert options["mark_topic"] is True
    assert options["link_to_knowledge_tree"] is True
    assert options["source"] == "reviewer"
    assert options["source_card_id"] == 77


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
    assert result["copied_source_tags"] == ["Source"]
    assert note.tags == ["existing", "Source"]
    assert saved == [["existing", "Source"]]


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
    assert note.tags == ["existing", "Source", "topic", "branch"]
    assert saved == [["existing", "Source", "topic", "branch"]]


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
        "link_to_knowledge_tree": False,
        "source": "pdf",
        "source_card_id": 99,
        "source_tags": ["Topic", "Source"],
        "seen": 0.0,
    }
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["copied_source_tags"] == ["Source"]
    assert note.tags == ["existing", "Source"]
    assert saved == [["existing", "Source"]]


def test_consume_pending_extract_options_excludes_topic_item_classification_tags(monkeypatch):
    note = _FakeNote(["existing", "item"], note_id=11)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 0)

    dock._pending_extract_options = {
        "priority": 25.0,
        "mark_topic": False,
        "link_to_knowledge_tree": False,
        "source": "pdf",
        "source_card_id": 99,
        "source_tags": ["Topic", "writing", "Item"],
        "seen": 0.0,
    }
    result = dock.consume_pending_extract_options_for_note(note)

    assert result is not None
    assert result["copied_source_tags"] == ["writing"]
    assert note.tags == ["existing", "item", "writing"]
    assert saved == [["existing", "item", "writing"]]


def test_consume_pending_extract_context_applies_metadata_and_links_lineage(monkeypatch):
    note = _FakeNote(["topic"], note_id=11)
    metadata_calls = []
    link_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [444])
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: None)
    monkeypatch.setitem(
        sys.modules,
        "note_metadata",
        types.SimpleNamespace(
            ensure_incremento_metadata_fields=lambda models, note_type: metadata_calls.append(("ensure", note_type)),
            apply_incremento_metadata=lambda current_note, metadata: metadata_calls.append(("apply", dict(metadata))),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "knowledge_tree",
        types.SimpleNamespace(
            NODE_KIND_ITEM="item",
            NODE_KIND_TOPIC="topic",
            ensure_extract_lineage_cards_in_tree=lambda addon_dir, profile, **kwargs: (
                link_calls.append((addon_dir, profile, dict(kwargs)))
                or {"linked_count": 2, "errors": []}
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "paths",
        types.SimpleNamespace(get_active_profile=lambda: "TestProfile"),
    )
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(col=types.SimpleNamespace(models=object())),
    )
    dock.set_pending_extract_context(
        metadata={"source_type": "Extract"},
        parent_card_id=55,
        knowledge_tree_link_enabled=True,
        link_to_knowledge_tree=True,
    )

    result = dock.consume_pending_extract_context_for_note(
        note,
        {"link_to_knowledge_tree": True},
    )

    assert result is not None
    assert result["metadata_saved"] is True
    assert result["knowledge_tree_link_error"] == ""
    assert metadata_calls == [
        ("ensure", note.note_type()),
        ("apply", {"source_type": "Extract"}),
    ]
    assert link_calls == [
        (
            dock._ADDON_DIR,
            "TestProfile",
            {
                "source_card_id": 55,
                "created_card_ids": [444],
                "created_node_kind": "topic",
            },
        ),
    ]


def test_consume_pending_extract_context_links_lineage_from_source_card_without_context(monkeypatch):
    note = _FakeNote(["item"], note_id=11)
    link_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [445])
    monkeypatch.setitem(
        sys.modules,
        "knowledge_tree",
        types.SimpleNamespace(
            NODE_KIND_ITEM="item",
            NODE_KIND_TOPIC="topic",
            ensure_extract_lineage_cards_in_tree=lambda addon_dir, profile, **kwargs: (
                link_calls.append((addon_dir, profile, dict(kwargs)))
                or {"linked_count": 1, "errors": []}
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "paths",
        types.SimpleNamespace(get_active_profile=lambda: "TestProfile"),
    )

    result = dock.consume_pending_extract_context_for_note(
        note,
        {"source_card_id": 99, "source": "pdf"},
    )

    assert result is not None
    assert result["metadata_saved"] is False
    assert result["knowledge_tree_link_error"] == ""
    assert link_calls == [
        (
            dock._ADDON_DIR,
            "TestProfile",
            {
                "source_card_id": 99,
                "created_card_ids": [445],
                "created_node_kind": "item",
            },
        ),
    ]


def test_consume_pending_extract_context_resolves_current_pdf_when_option_lacks_card_id(monkeypatch):
    note = _FakeNote(["item"], note_id=11)
    link_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [446])
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: 123 if source == "pdf" else None)
    monkeypatch.setitem(
        sys.modules,
        "knowledge_tree",
        types.SimpleNamespace(
            NODE_KIND_ITEM="item",
            NODE_KIND_TOPIC="topic",
            ensure_extract_lineage_cards_in_tree=lambda addon_dir, profile, **kwargs: (
                link_calls.append((addon_dir, profile, dict(kwargs)))
                or {"linked_count": 2, "errors": []}
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "paths",
        types.SimpleNamespace(get_active_profile=lambda: "TestProfile"),
    )

    result = dock.consume_pending_extract_context_for_note(
        note,
        {"source_card_id": None, "source": "pdf"},
    )

    assert result is not None
    assert result["metadata_saved"] is False
    assert result["knowledge_tree_link_error"] == ""
    assert link_calls == [
        (
            dock._ADDON_DIR,
            "TestProfile",
            {
                "source_card_id": 123,
                "created_card_ids": [446],
                "created_node_kind": "item",
            },
        ),
    ]


def test_prime_editor_note_for_extract_copies_source_tags_before_topic_tags(monkeypatch):
    note = _FakeNote(["stale"], note_id=11)
    editor = _FakeEditor(note=note)
    refreshed = []
    tag_refresh = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: refreshed.append(current_editor))
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: tag_refresh.append(current_editor))
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic", "branch"])

    dock._prime_editor_note_for_extract(
        editor,
        {"Front": "Selected text"},
        True,
        ["Topic", "Source"],
    )

    assert note.fields[0] == "Selected text"
    assert note.tags == ["Source", "topic", "branch"]
    assert editor.tags.text() == "Source topic branch"
    assert refreshed == [editor]
    assert tag_refresh == [editor]


def test_pending_pdf_extract_applies_source_tags_to_add_card_editor(monkeypatch):
    note = _FakeNote(["existing", "Source"], note_id=11)
    editor = _FakeEditor(note=note, add_mode=True)
    refreshed = []
    tag_refresh = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: refreshed.append(current_editor))
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: tag_refresh.append(current_editor))

    monkeypatch.setattr(
        dock,
        "_pending_extract_options",
        {
            "priority": 25.0,
            "mark_topic": False,
            "link_to_knowledge_tree": False,
            "source": "pdf",
            "source_card_id": 99,
            "source_tags": ["Topic", "Source", "PDF"],
            "seen": 0.0,
        },
    )

    changed = dock._apply_pending_extract_tags_to_editor(editor)

    assert changed is True
    assert note.tags == ["existing", "Source", "PDF"]
    assert editor.tags.text() == "existing Source PDF"
    assert refreshed == [editor]
    assert tag_refresh == [editor]
    assert dock.pending_extract_options()["source_tags"] == ["Topic", "Source", "PDF"]


def test_pending_pdf_extract_leaves_tags_untouched_when_copy_disabled(monkeypatch):
    note = _FakeNote(["existing"], note_id=11)
    editor = _FakeEditor(note=note, add_mode=True)
    refreshed = []
    tag_refresh = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: False)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: refreshed.append(current_editor))
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: tag_refresh.append(current_editor))
    monkeypatch.setattr(
        dock,
        "_pending_extract_options",
        {
            "priority": 25.0,
            "mark_topic": False,
            "link_to_knowledge_tree": False,
            "source": "pdf",
            "source_card_id": 99,
            "source_tags": ["Topic", "Source"],
            "seen": 0.0,
        },
    )

    changed = dock._apply_pending_extract_tags_to_editor(editor)

    assert changed is False
    assert note.tags == ["existing"]
    assert editor.tags.text() == "existing"
    assert refreshed == []
    assert tag_refresh == []


def test_prepare_reviewer_extract_primes_native_add_dialog(monkeypatch):
    note = _FakeNote(note_id=22)
    editor = _FakeEditor(note, add_mode=True)
    dlg = _FakeAddCardsDialog(editor)
    fake_dock = _FakeDock(editor)
    fake_dock._addcards_dialog = dlg
    selection_updates = []

    monkeypatch.setattr(dock, "open_add_card_dock", lambda: None)
    monkeypatch.setattr(dock, "get_add_card_dock", lambda: fake_dock)
    monkeypatch.setattr(dock, "_dock_editor", lambda: editor)
    monkeypatch.setattr(
        dock,
        "update_selection_state",
        lambda source, text=None, has_text=None: selection_updates.append((source, text, has_text)),
    )
    monkeypatch.setattr(dock, "_inject_transfer_buttons", lambda current_editor: None)
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                models=types.SimpleNamespace(by_name=lambda name: {"id": 9} if name == "Basic" else None),
                decks=types.SimpleNamespace(by_name=lambda name: {"id": 3} if name == "Deck" else None),
            )
        ),
    )

    dock.prepare_reviewer_extract(
        selected_text="Excerpt",
        note_type_name="Basic",
        deck_name="Deck",
        field_values={"Front": "Excerpt"},
        metadata={"source_type": "Extract"},
        parent_card_id=5,
        priority=30,
        mark_topic=True,
        knowledge_tree_link_enabled=True,
        link_to_knowledge_tree=True,
        knowledge_tree_tooltip="Link beneath parent",
    )

    assert selection_updates == [("reviewer", "Excerpt", True)]
    assert dlg.note_type_ids == [9]
    assert dlg.deck_ids == [3]
    assert note["Front"] == "Excerpt"
    assert note.tags == ["topic"]
    assert dock.pending_extract_options()["source"] == "reviewer"
    assert dock.pending_extract_options()["link_to_knowledge_tree"] is True
    assert dock.pending_extract_context()["parent_card_id"] == 5


def test_reviewer_extract_queue_refresh_suppression_is_one_shot(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(dock.time, "monotonic", lambda: now[0])
    dock._suppress_next_reviewer_queue_refresh = None

    dock.mark_reviewer_extract_note_added({"source": "reviewer", "source_card_id": 5})

    assert dock.consume_reviewer_extract_queue_refresh_suppression(5) is True
    assert dock.consume_reviewer_extract_queue_refresh_suppression(5) is False


def test_reviewer_extract_queue_refresh_suppression_checks_parent_card(monkeypatch):
    monkeypatch.setattr(dock.time, "monotonic", lambda: 100.0)
    dock._suppress_next_reviewer_queue_refresh = None

    dock.mark_reviewer_extract_note_added({"source": "reviewer", "source_card_id": 5})

    assert dock.consume_reviewer_extract_queue_refresh_suppression(6) is False


def test_reviewer_extract_queue_refresh_suppression_applies_to_pdf_extract_sources():
    dock._suppress_next_reviewer_queue_refresh = None

    dock.mark_reviewer_extract_note_added({"source": "pdf", "source_card_id": 5})

    assert dock.consume_reviewer_extract_queue_refresh_suppression(5) is True


def test_reviewer_extract_queue_refresh_suppression_requires_source_card_id():
    dock._suppress_next_reviewer_queue_refresh = None

    dock.mark_reviewer_extract_note_added({"source": "reviewer"})

    assert dock.consume_reviewer_extract_queue_refresh_suppression(5) is False


def test_set_editor_note_type_saves_metadata_fields_before_switch(monkeypatch):
    note = _FakeNote(note_id=22)
    editor = _FakeEditor(note, add_mode=True)
    dlg = _FakeAddCardsDialog(editor)
    fake_dock = _FakeDock(editor)
    fake_dock._addcards_dialog = dlg
    calls = []

    def _set_note_type(note_type_id):
        calls.append(("set_note_type", note_type_id))
        dlg.note_type_ids.append(note_type_id)

    dlg.set_note_type = _set_note_type
    monkeypatch.setattr(dock, "get_add_card_dock", lambda: fake_dock)
    monkeypatch.setitem(
        sys.modules,
        "note_metadata",
        types.SimpleNamespace(
            ensure_incremento_metadata_fields=lambda models, model, save=False: calls.append(
                ("ensure", save)
            )
            or True,
        ),
    )
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                models=types.SimpleNamespace(by_name=lambda name: {"id": 9} if name == "Basic" else None),
                decks=types.SimpleNamespace(by_name=lambda name: None),
            )
        ),
    )

    dock._set_editor_note_type_and_deck(editor, "Basic", "")

    assert calls == [("ensure", True), ("set_note_type", 9)]


def test_do_fill_forwards_mark_topic_to_embedded_dock(monkeypatch):
    fake_dock = _FakeDock(_FakeEditor(_FakeNote()))
    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)

    dock.do_fill(1, "extract text", mark_topic=True)

    assert fake_dock.calls == [(1, "extract text", True)]


def test_inject_transfer_buttons_shows_extract_options_for_pending_snapshot(monkeypatch):
    note = _FakeNote(note_id=9)
    editor = _FakeEditor(note, add_mode=True)
    editor.web = _FakeWeb()

    monkeypatch.setattr(dock, "_last_selection_source", "")
    monkeypatch.setattr(dock, "_last_selection_seen", 0.0)
    monkeypatch.setattr(dock, "_current_extract_priority", None)
    monkeypatch.setattr(dock, "_current_extract_mark_topic", None)
    monkeypatch.setattr(dock, "_current_extract_link_to_knowledge_tree", None)
    monkeypatch.setattr(
        dock,
        "_pending_extract_options",
        {
            "priority": 18.0,
            "mark_topic": False,
            "link_to_knowledge_tree": True,
            "source": "pdf",
            "source_card_id": 55,
        },
    )

    dock._inject_transfer_buttons(editor)

    js = editor.web.eval_calls[-1]
    assert "var visible = false;" in js
    assert "var optionsVisible = true;" in js
    assert "var defaultExtractPriority = 18.0;" in js
    assert "panel.style.display = this.optionsVisible ? 'flex' : 'none';" in js


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


def test_on_editor_did_update_tags_syncs_extract_mode_for_add_note(monkeypatch):
    note = _FakeNote(["item"], note_id=42)
    editor = _FakeEditor(note, add_mode=True)
    dock._tracked_tag_button_editors.clear()
    dock._track_tag_button_editor(editor)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda current_editor: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(
        dock,
        "sync_pending_extract_options_from_current",
        lambda: None,
    )
    dock._current_extract_mark_topic = True

    dock._on_editor_did_update_tags(_FakeNote(["item"], note_id=42))

    assert dock._current_extract_mark_topic is False


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


def test_item_button_switches_pending_extract_mode_to_item(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "topic"], note_id=9), add_mode=True)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: func(),
    )
    sync_calls = []
    monkeypatch.setattr(
        dock,
        "sync_pending_extract_options_from_current",
        lambda: sync_calls.append(True),
    )
    dock._last_selection_source = "pdf"
    dock._current_extract_mark_topic = True

    dock._on_item_tag_button(editor)

    assert editor.note.tags == ["keep", "item"]
    assert dock._current_extract_mark_topic is False
    assert sync_calls == [True]


def test_item_button_notifies_tag_update_hooks_in_add_mode(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "topic"], note_id=9), add_mode=True)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: func(),
    )
    monkeypatch.setattr(
        dock,
        "sync_pending_extract_options_from_current",
        lambda: None,
    )
    calls = []
    monkeypatch.setattr(
        dock.gui_hooks,
        "editor_did_update_tags",
        lambda note: calls.append(list(note.tags)),
    )

    dock._on_item_tag_button(editor)

    assert editor.note.tags == ["keep", "item"]
    assert calls == [["keep", "item"]]


def test_toggle_editor_item_button_reloads_add_mode_editor(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "topic"], note_id=9), add_mode=True)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    calls = []
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: (calls.append(delay), func()),
    )

    dock._toggle_editor_tag_button(
        editor,
        ["item"],
        "unused",
        opposite_tags=["topic"],
    )

    assert editor.note.tags == ["keep", "item"]
    assert editor.tags.text_value == "keep item"
    assert calls == [0, 40, 0, 60]
    assert editor.tag_focus_lost_calls == 1
    assert editor.load_note_calls == 2


def test_toggle_editor_item_button_updates_web_tag_chips(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "topic"], note_id=9), add_mode=True)
    editor.web = _FakeWeb()
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
    assert any('setTags(["keep", "item"])' in call for call in editor.web.eval_calls)


def test_apply_extract_topic_default_respects_current_item_choice(monkeypatch):
    note = _FakeNote(["item", "writing"], note_id=9)
    editor = _FakeEditor(note, add_mode=True)

    monkeypatch.setattr(dock, "_has_recent_selection", lambda: True)
    monkeypatch.setattr(dock, "_extract_mark_topic_for_transfer", lambda: True)
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "_set_add_card_tag_button_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: None)
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: None)

    dock._apply_extract_topic_default_to_editor(editor)

    assert note.tags == ["item", "writing"]


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
