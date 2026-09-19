import add_card_dock as dock
import sys
import types


def test_transfer_button_tooltips_translate_and_keep_field_names_literal(monkeypatch):
    import json
    import subprocess
    from backend.i18n import Translator

    for locale, expected, fallback in [('hr', 'Umetni odabrani tekst u Naziv $& <题>', 'Umetni odabrani tekst u Polje 2'), ('zh-Hans', '将所选文本插入Naziv $& <题>', '将所选文本插入字段 2')]:
        monkeypatch.setattr(dock, 't', Translator(locale).t)
        monkeypatch.setattr(dock, '_pending_extract_options', {'source': 'web'})
        editor = _FakeEditor(_FakeNote(field_names=['Naziv $& <题>']))
        editor.web = _FakeWeb()
        dock._inject_transfer_buttons(editor)
        js = editor.web.eval_calls[-1]
        harness = '''
            const vm = require('node:vm');
            const buttons = [], commands = [];
            const sourceBadge = {textContent:''};
            const panel = {style:{}, querySelector:selector=>selector==='#incremento-extract-source'?sourceBadge:null};
            const fields = [0,1].map(i => {
                const host = {parentElement:{}, querySelectorAll:()=>[], querySelector:()=>null,
                    appendChild:button=>buttons.push(button)};
                return {id:'f'+i, closest:()=>host, parentElement:host};
            });
            const context = {window:{}, pycmd:x=>commands.push(x),
                MutationObserver:class {observe(){}},
                document:{body:{}, getElementById:()=>panel, querySelectorAll:()=>fields,
                    createElement:()=>({dataset:{},style:{},events:{},addEventListener(event,fn){this.events[event]=fn;}})}};
            vm.runInNewContext(SCRIPT,context);
            buttons[0].events.click({preventDefault(){},stopPropagation(){}});
            process.stdout.write(JSON.stringify({titles:buttons.map(b=>b.title),commands,source:sourceBadge.textContent}));
        '''.replace('SCRIPT', json.dumps(js))
        result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        rendered = json.loads(result.stdout)
        assert rendered['titles'] == [expected, fallback]
        assert rendered['source'] == Translator(locale).t('reader_web_name')
        assert 'incremento_transfer_selection:0' in rendered['commands']


def test_tag_button_fallback_lookup_uses_translated_tooltip(monkeypatch):
    import json
    import subprocess
    from backend.i18n import Translator

    monkeypatch.setattr(dock, 't', Translator('hr').t)
    editor = _FakeEditor()
    editor.web = _FakeWeb()
    dock._set_add_card_tag_button_state(editor, dock._TOPIC_TAG_BUTTON_ID, True)
    harness = '''
        const vm = require('node:vm');
        const button={textContent:'Tema',style:{},attrs:{},getAttribute:()=>TITLE,
            setAttribute(key,value){this.attrs[key]=value;}};
        vm.runInNewContext(SCRIPT,{setTimeout(){},document:{getElementById:()=>null,querySelectorAll:()=>[button]}});
        process.stdout.write(JSON.stringify(button.attrs));
    '''.replace('TITLE', json.dumps(Translator('hr').t('add_card_topic_button_tooltip'))).replace('SCRIPT', json.dumps(editor.web.eval_calls[-1]))
    result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['aria-pressed'] == 'true'


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


class _BatchFakeModels:
    def __init__(self, model):
        self._model = model
        self.updated = []

    def by_name(self, name):
        return self._model if self._model.get("name") == name else None

    def update_dict(self, model):
        self.updated.append(model)


class _BatchFakeDecks:
    def __init__(self, deck_name="Topics", deck_id=99):
        self._deck = {"name": deck_name, "id": deck_id}

    def by_name(self, name):
        return self._deck if self._deck["name"] == name else None

    def get(self, deck_id):
        return self._deck if int(deck_id) == self._deck["id"] else None

    def add_normal_deck_with_name(self, name):
        self._deck = {"name": name, "id": self._deck["id"]}
        return types.SimpleNamespace(id=self._deck["id"])


class _BatchFakeCollection:
    def __init__(self, model, deck_name="Topics", deck_id=99):
        self.models = _BatchFakeModels(model)
        self.decks = _BatchFakeDecks(deck_name=deck_name, deck_id=deck_id)
        self.created_notes = []
        self.added = []

    def new_note(self, model):
        note = _FakeNote(field_names=[field["name"] for field in model["flds"]])
        note._note_type = model
        note.cards = lambda: [types.SimpleNamespace(id=note.id * 10 + 1)]
        self.created_notes.append(note)
        return note

    def add_note(self, note, deck_id):
        note.id = len(self.added) + 1
        note.note_type()["did"] = deck_id
        self.added.append((note, deck_id))
        return 1


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


def test_scratch_priority_defaults_to_neutral_value():
    editor = _FakeEditor(_FakeNote(note_id=1), add_mode=True)

    assert dock.scratch_priority_for_editor(editor) == 50.0
    assert dock.scratch_priority_for_note(editor.note) == 50.0


def test_set_scratch_priority_for_editor_clamps_and_stores_on_note():
    editor = _FakeEditor(_FakeNote(note_id=2), add_mode=True)

    assert dock.set_scratch_priority_for_editor(editor, 120) == 100.0
    assert dock.scratch_priority_for_editor(editor) == 100.0

    token = getattr(editor, "_incremento_scratch_priority_token")
    assert getattr(editor.note, f"_incremento_scratch_priority_{token}") == 100.0


def test_set_scratch_priority_for_editor_keeps_editors_isolated():
    first = _FakeEditor(_FakeNote(note_id=3), add_mode=True)
    second = _FakeEditor(_FakeNote(note_id=4), add_mode=True)

    dock.set_scratch_priority_for_editor(first, 10)
    dock.set_scratch_priority_for_editor(second, 90)

    assert dock.scratch_priority_for_editor(first) == 10.0
    assert dock.scratch_priority_for_editor(second) == 90.0


def test_current_add_mode_editor_prefers_originating_bridge_context(monkeypatch):
    dock_editor = _FakeEditor(_FakeNote(note_id=5), add_mode=True)
    native_editor = _FakeEditor(_FakeNote(note_id=6), add_mode=True)

    monkeypatch.setattr(dock, "_dock_editor", lambda: dock_editor)
    monkeypatch.setattr(dock, "_last_add_mode_editor", dock_editor)

    assert dock._current_add_mode_editor(native_editor) is native_editor


def test_current_add_mode_editor_ignores_non_add_bridge_context(monkeypatch):
    dock_editor = _FakeEditor(_FakeNote(note_id=7), add_mode=True)
    browser_editor = _FakeEditor(_FakeNote(note_id=8), add_mode=False)

    monkeypatch.setattr(dock, "_dock_editor", lambda: dock_editor)

    assert dock._current_add_mode_editor(browser_editor) is dock_editor


def test_configured_extract_priority_multiplier_defaults_by_direction():
    assert dock.configured_extract_priority_multiplier({}) == 0.98
    assert dock.configured_extract_priority_multiplier({"priority_lower_is_more_important": False}) == 1.02


def test_calculate_extract_priority_uses_source_multiplier():
    assert dock.calculate_extract_priority(6, {"extract_priority_multiplier": 0.98}) == 5.88
    assert dock.calculate_extract_priority(60, {"extract_priority_multiplier": 1.02}) == 61.2


def test_calculate_extract_priority_falls_back_without_source():
    assert dock.calculate_extract_priority(None, {"extract_priority": 33}) == 33.0


def test_source_card_priority_for_card_uses_exact_stored_priority(monkeypatch):
    monkeypatch.setattr(dock, "_priority_for_card_id", lambda card_id: 24.5)

    assert dock.source_card_priority_for_card(
        123,
        {"extract_priority": 80, "extract_priority_multiplier": 0.25},
    ) == 24.5


def test_source_card_priority_for_card_falls_back_without_source(monkeypatch):
    monkeypatch.setattr(dock, "_priority_for_card_id", lambda card_id: None)

    assert dock.source_card_priority_for_card(123, {"extract_priority": 33}) == 33.0


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


def test_apply_priority_to_note_cards_updates_every_generated_card(monkeypatch):
    note = _FakeNote(note_id=12)
    priority_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [201, 202])
    monkeypatch.setitem(
        sys.modules,
        "priority_manager",
        types.SimpleNamespace(
            set_priority=lambda addon_dir, profile, card_id, priority: priority_calls.append(
                (addon_dir, profile, card_id, priority)
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "paths",
        types.SimpleNamespace(get_active_profile=lambda: "TestProfile"),
    )

    changed = dock.apply_priority_to_note_cards(note, 17.25)

    assert changed == 2
    assert priority_calls == [
        (dock._ADDON_DIR, "TestProfile", 201, 17.25),
        (dock._ADDON_DIR, "TestProfile", 202, 17.25),
    ]


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


def test_prepare_source_fill_clears_stale_context_without_current_source_card(monkeypatch):
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: None)
    monkeypatch.setattr(dock, "source_relative_extract_priority_for_source", lambda source: 40.0)
    monkeypatch.setattr(dock, "source_note_tags_for_card", lambda source_card_id: [])
    dock._pending_extract_context = {"parent_card_id": 99, "seen": 0.0}

    options = dock.prepare_pending_extract_from_source_fill("pdf")

    assert options is not None
    assert options["source_card_id"] is None
    assert dock.pending_extract_context() is None


def test_explicit_missing_source_snapshot_does_not_later_bind_to_another_pdf(monkeypatch):
    monkeypatch.setattr(dock, "_source_card_id_for_transfer", lambda source: 202)

    assert dock._source_card_id_from_extract_options(
        {
            "source": "pdf",
            "source_card_id": None,
            "source_card_id_is_snapshot": True,
        }
    ) is None
    assert dock._source_card_id_from_extract_options(
        {"source": "pdf", "source_card_id": None}
    ) == 202


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


def test_fill_dock_field_reports_success_only_after_field_update(monkeypatch):
    outcomes = []
    fake_dock = types.SimpleNamespace(
        show=lambda: None,
        raise_=lambda: None,
        _set_field=lambda idx, text, mark_topic=False: True,
    )
    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(dock, "_apply_configured_extract_notetype", lambda: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(dock.QTimer, "singleShot", lambda delay, func: None)

    result = dock.fill_dock_field(
        0,
        "Excerpt",
        include_pdf_citation=False,
        on_complete=outcomes.append,
    )

    assert result is True
    assert outcomes == [True]


def test_fill_dock_field_delays_completion_until_new_dock_accepts_field(monkeypatch):
    outcomes = []
    timers = []
    fake_dock = types.SimpleNamespace(
        _set_field=lambda idx, text, mark_topic=False: True,
    )

    def build():
        dock._add_card_dock = fake_dock

    monkeypatch.setattr(dock, "_add_card_dock", None)
    monkeypatch.setattr(dock, "build_add_card_dock", build)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: timers.append((delay, func)),
    )

    result = dock.fill_dock_field(
        0,
        "Excerpt",
        include_pdf_citation=False,
        on_complete=outcomes.append,
    )

    assert result is None
    assert outcomes == []
    delayed_fill = next(func for delay, func in timers if delay == 600)
    delayed_fill()
    assert outcomes == [True]


def test_fill_dock_field_reports_rejected_field_without_false_highlight(monkeypatch):
    outcomes = []
    fake_dock = types.SimpleNamespace(
        show=lambda: None,
        raise_=lambda: None,
        _set_field=lambda idx, text, mark_topic=False: False,
    )
    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(dock, "_apply_configured_extract_notetype", lambda: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    monkeypatch.setattr(dock.QTimer, "singleShot", lambda delay, func: None)

    result = dock.fill_dock_field(
        99,
        "Excerpt",
        include_pdf_citation=False,
        on_complete=outcomes.append,
    )

    assert result is False
    assert outcomes == [False]


def test_fill_dock_field_reports_failed_dock_creation_once(monkeypatch):
    outcomes = []
    monkeypatch.setattr(dock, "_add_card_dock", None)
    monkeypatch.setattr(
        dock,
        "build_add_card_dock",
        lambda: (_ for _ in ()).throw(RuntimeError("could not build")),
    )

    result = dock.fill_dock_field(
        0,
        "Excerpt",
        include_pdf_citation=False,
        on_complete=outcomes.append,
    )

    assert result is False
    assert outcomes == [False]


def test_pending_web_extract_records_survive_appended_source_context_refresh():
    record = {
        "webCardId": 17,
        "url": "https://example.com/guide",
        "anchor": {
            "version": 1,
            "exact": "selected passage",
            "prefix": "before ",
            "suffix": " after",
            "startPath": [0],
            "startOffset": 0,
            "endPath": [0],
            "endOffset": 16,
        },
    }
    dock.clear_pending_extract_context()
    try:
        dock.set_pending_extract_context(parent_card_id=17)
        assert dock.append_pending_web_extract_record(record) is True

        dock.set_pending_extract_context(
            parent_card_id=17,
            preserve_web_extract_records=True,
        )

        records = dock.pending_web_extract_records()
        assert len(records) == 1
        assert records[0]["webCardId"] == 17
        assert records[0]["anchor"]["exact"] == "selected passage"
    finally:
        dock.clear_pending_extract_context()


def test_pending_web_extract_record_can_be_rolled_back_after_rejected_fill(monkeypatch):
    record = {
        "webCardId": 17,
        "url": "https://example.com/guide",
        "anchor": {
            "version": 1,
            "exact": "selected passage",
            "prefix": "before ",
            "suffix": " after",
            "startPath": [0],
            "startOffset": 0,
            "endPath": [0],
            "endOffset": 16,
        },
    }
    monkeypatch.setattr(dock, "_schedule_extract_draft_autosave", lambda *_args: None)
    dock.clear_pending_extract_context()
    try:
        dock.set_pending_extract_context(parent_card_id=17)
        assert dock.append_pending_web_extract_record(record) is True

        assert dock.remove_pending_web_extract_record(record) is True
        assert dock.pending_web_extract_records() == []
        assert dock.remove_pending_web_extract_record(record) is False
        assert (dock.pending_extract_context() or {}).get("parent_card_id") == 17
    finally:
        dock.clear_pending_extract_context()


def test_pending_web_extract_record_limit_drops_oldest_and_keeps_new_transfer(
    monkeypatch,
):
    monkeypatch.setattr(dock, "_schedule_extract_draft_autosave", lambda *_args: None)
    dock.clear_pending_extract_context()
    try:
        for index in range(dock.MAX_PENDING_WEB_EXTRACT_RECORDS + 1):
            record = {
                "webCardId": 17,
                "url": "https://example.com/guide",
                "anchor": {
                    "version": 1,
                    "exact": f"passage {index}",
                    "prefix": "before ",
                    "suffix": " after",
                    "startPath": [index],
                    "startOffset": 0,
                    "endPath": [index],
                    "endOffset": len(f"passage {index}"),
                },
            }
            assert dock.append_pending_web_extract_record(record) is True

        records = dock.pending_web_extract_records()
        assert len(records) == dock.MAX_PENDING_WEB_EXTRACT_RECORDS
        assert records[0]["anchor"]["exact"] == "passage 1"
        assert records[-1]["anchor"]["exact"] == (
            f"passage {dock.MAX_PENDING_WEB_EXTRACT_RECORDS}"
        )
    finally:
        dock.clear_pending_extract_context()


def test_source_card_id_for_transfer_reads_video_source(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "video_dock",
        types.SimpleNamespace(current_video_card_id=lambda: 456),
    )

    assert dock._source_card_id_for_transfer("video") == 456


def test_on_add_cards_did_add_note_notifies_video_extract_source(monkeypatch):
    note = _FakeNote(note_id=11)
    note._incremento_add_card_draft_owner = True
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


def test_on_add_cards_did_add_note_applies_scratch_priority_when_no_extract_options(monkeypatch):
    note = _FakeNote(note_id=12)
    priority_calls = []

    note._incremento_scratch_priority_active_token = "1"
    note._incremento_scratch_priority_1 = "77.25"

    monkeypatch.setattr(dock, "consume_pending_extract_options_for_note", lambda current_note: None)
    monkeypatch.setattr(
        dock,
        "apply_priority_to_note_cards",
        lambda current_note, priority: priority_calls.append((current_note, priority)) or 2,
    )
    monkeypatch.setattr(dock, "_notify_video_extract_note_added", lambda current_note, options: None)
    monkeypatch.setattr(dock, "mark_reviewer_extract_note_added", lambda options: None)
    monkeypatch.setattr(dock, "consume_pending_extract_context_for_note", lambda current_note, options=None: None)

    dock.on_add_cards_did_add_note(note)

    assert priority_calls == [(note, 77.25)]


def test_on_add_cards_did_add_note_falls_back_to_default_scratch_priority(monkeypatch):
    note = _FakeNote(note_id=13)
    priority_calls = []

    note._incremento_scratch_priority_active_token = "1"
    note._incremento_scratch_priority_1 = "not-a-number"

    monkeypatch.setattr(dock, "consume_pending_extract_options_for_note", lambda current_note: None)
    monkeypatch.setattr(
        dock,
        "apply_priority_to_note_cards",
        lambda current_note, priority: priority_calls.append(priority) or 1,
    )
    monkeypatch.setattr(dock, "_notify_video_extract_note_added", lambda current_note, options: None)
    monkeypatch.setattr(dock, "mark_reviewer_extract_note_added", lambda options: None)
    monkeypatch.setattr(dock, "consume_pending_extract_context_for_note", lambda current_note, options=None: None)

    dock.on_add_cards_did_add_note(note)

    assert priority_calls == [50.0]


def test_on_add_cards_did_add_note_keeps_extract_priority_when_pending_options_exist(monkeypatch):
    note = _FakeNote(note_id=14)
    note._incremento_add_card_draft_owner = True
    priority_calls = []

    note._incremento_scratch_priority_active_token = "1"
    note._incremento_scratch_priority_1 = 90.0

    monkeypatch.setattr(
        dock,
        "consume_pending_extract_options_for_note",
        lambda current_note: {"priority": 25.0, "source": "pdf", "priority_cards_changed": 1},
    )
    monkeypatch.setattr(
        dock,
        "apply_priority_to_note_cards",
        lambda current_note, priority: priority_calls.append(priority) or 1,
    )
    monkeypatch.setattr(dock, "_notify_video_extract_note_added", lambda current_note, options: None)
    monkeypatch.setattr(dock, "mark_reviewer_extract_note_added", lambda options: None)
    monkeypatch.setattr(dock, "consume_pending_extract_context_for_note", lambda current_note, options=None: None)

    dock.on_add_cards_did_add_note(note)

    assert priority_calls == []


def test_unrelated_note_add_does_not_consume_pending_extract_state(monkeypatch):
    unrelated_note = _FakeNote(note_id=45)
    consume_calls = []
    context_calls = []

    monkeypatch.setattr(
        dock,
        "consume_pending_extract_options_for_note",
        lambda note: consume_calls.append(note),
    )
    monkeypatch.setattr(
        dock,
        "consume_pending_extract_context_for_note",
        lambda note, options=None: context_calls.append((note, options)),
    )
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda *_args: 0)
    monkeypatch.setattr(dock, "_notify_video_extract_note_added", lambda *_args: None)
    monkeypatch.setattr(dock, "mark_reviewer_extract_note_added", lambda *_args: None)
    monkeypatch.setattr(dock, "_carry_auto_extract_tag_keys_after_add", lambda *_args: None)

    dock.on_add_cards_did_add_note(unrelated_note)

    assert consume_calls == []
    assert context_calls == []


def test_consuming_extract_context_snapshots_web_records_on_owning_note(monkeypatch):
    note = _FakeNote(note_id=46)
    note._incremento_add_card_draft_owner = True
    record = {
        "webCardId": 17,
        "url": "https://example.com/guide",
        "anchor": {
            "version": 1,
            "exact": "selected passage",
            "prefix": "before ",
            "suffix": " after",
            "startPath": [0],
            "startOffset": 0,
            "endPath": [0],
            "endOffset": 16,
        },
    }
    monkeypatch.setattr(
        dock,
        "apply_extract_context_to_note",
        lambda current_note, options=None, context=None: dict(context or {}),
    )
    dock.clear_pending_extract_context()
    try:
        dock.set_pending_extract_context(parent_card_id=17)
        assert dock.append_pending_web_extract_record(record) is True

        dock.consume_pending_extract_context_for_note(note, {"source": "web"})

        assert dock.pending_extract_context() is None
        records = dock.web_extract_records_for_note(note)
        assert len(records) == 1
        assert records[0]["anchor"]["exact"] == "selected passage"
    finally:
        dock.clear_pending_extract_context()


def test_extract_draft_capture_ignores_a_separate_native_add_editor(monkeypatch):
    dock_note = _FakeNote(note_id=0)
    dock_note.fields[0] = "Dock draft"
    dock_editor = _FakeEditor(dock_note, add_mode=True)
    native_note = _FakeNote(note_id=0)
    native_note.fields[0] = "Unrelated native Add note"
    native_editor = _FakeEditor(native_note, add_mode=True)
    monkeypatch.setattr(dock, "_dock_editor", lambda: dock_editor)

    assert dock._capture_extract_draft(native_editor) is None


def test_unrelated_note_add_does_not_clear_the_dock_owned_draft(monkeypatch):
    unrelated_note = _FakeNote(note_id=45)
    clear_calls = []
    monkeypatch.setattr(
        dock,
        "consume_pending_extract_options_for_note",
        lambda _note: None,
    )
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda *_args: 0)
    monkeypatch.setattr(dock, "_notify_video_extract_note_added", lambda *_args: None)
    monkeypatch.setattr(dock, "mark_reviewer_extract_note_added", lambda *_args: None)
    monkeypatch.setattr(
        dock,
        "consume_pending_extract_context_for_note",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(dock, "_carry_auto_extract_tag_keys_after_add", lambda *_args: None)
    monkeypatch.setattr(
        dock,
        "_clear_saved_extract_draft",
        lambda: clear_calls.append("clear"),
    )

    dock.on_add_cards_did_add_note(unrelated_note)

    assert clear_calls == []


def test_typing_timer_does_not_confuse_two_unsaved_note_ids(monkeypatch):
    native_note = _FakeNote(note_id=0)
    dock_note = _FakeNote(note_id=0)
    native_editor = _FakeEditor(native_note, add_mode=True)
    dock_editor = _FakeEditor(dock_note, add_mode=True)
    scheduled = []
    monkeypatch.setattr(
        dock,
        "_iter_tracked_tag_button_editors",
        lambda: [native_editor, dock_editor],
    )
    monkeypatch.setattr(
        dock,
        "_schedule_extract_draft_autosave",
        lambda editor: scheduled.append(editor),
    )

    dock._on_editor_did_fire_typing_timer(dock_note)

    assert scheduled == [dock_editor]


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


def test_apply_extract_options_adds_custom_tags_and_exclusive_item_classification(monkeypatch):
    note = _FakeNote(["existing", "topic"], note_id=11)
    saved = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: False)
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])
    monkeypatch.setattr(dock, "_save_note_tag_changes", lambda current_note: saved.append(list(current_note.tags)))
    monkeypatch.setattr(dock, "apply_priority_to_note_cards", lambda current_note, priority: 1)

    result = dock.apply_extract_options_to_note(
        note,
        {
            "priority": 22,
            "mark_topic": False,
            "mark_item": True,
            "tags": ["custom", "Existing"],
        },
    )

    assert note.tags == ["existing", "custom", "item"]
    assert saved == [["existing", "custom", "item"]]
    assert result["added_tags"] == ["custom"]
    assert result["priority_cards_changed"] == 1


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


def test_apply_extract_context_to_note_uses_explicit_context_without_consuming_globals(monkeypatch):
    note = _FakeNote(["item"], note_id=11)
    link_calls = []

    monkeypatch.setattr(dock, "_card_ids_for_note", lambda current_note: [447])
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
    dock._pending_extract_context = {"parent_card_id": 123, "seen": 0.0}

    result = dock.apply_extract_context_to_note(
        note,
        options={"source": "pdf", "source_card_id": 55},
        context={"parent_card_id": 55},
    )

    assert result is not None
    assert result["knowledge_tree_link_error"] == ""
    assert dock._pending_extract_context == {"parent_card_id": 123, "seen": 0.0}
    assert link_calls == [
        (
            dock._ADDON_DIR,
            "TestProfile",
            {
                "source_card_id": 55,
                "created_card_ids": [447],
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


def test_pending_extract_replaces_previous_auto_tags_when_source_changes(monkeypatch):
    note = _FakeNote(["keep", "Source", "topic"], note_id=11)
    editor = _FakeEditor(note=note, add_mode=True)
    refreshed = []
    tag_refresh = []

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: refreshed.append(current_editor))
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: tag_refresh.append(current_editor))
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])

    dock._set_auto_extract_tag_keys_for_editor(editor, note, ["Source", "topic"])
    monkeypatch.setattr(
        dock,
        "_pending_extract_options",
        {
            "priority": 25.0,
            "mark_topic": False,
            "link_to_knowledge_tree": False,
            "source": "reviewer",
            "source_card_id": 55,
            "source_tags": ["Reviewer"],
            "seen": 0.0,
        },
    )

    changed = dock._apply_pending_extract_tags_to_editor(editor)

    assert changed is True
    assert note.tags == ["keep", "Reviewer"]
    assert editor.tags.text() == "keep Reviewer"
    assert refreshed == [editor]
    assert tag_refresh == [editor]


def test_cmd1_pdf_switch_replaces_sticky_auto_tags_on_next_add_note(monkeypatch):
    first_note = _FakeNote(["manual"], note_id=0)
    editor = _FakeEditor(note=first_note, add_mode=True)

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: None)
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: None)
    monkeypatch.setattr(dock, "_inject_transfer_buttons", lambda current_editor: None)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda current_editor: None)

    dock._pending_extract_options = {
        "priority": 25.0,
        "mark_topic": False,
        "link_to_knowledge_tree": False,
        "source": "pdf",
        "source_card_id": 101,
        "source_tags": ["FirstPdf", "Shared"],
        "seen": 0.0,
    }
    assert dock._apply_pending_extract_tags_to_editor(editor) is True
    assert first_note.tags == ["manual", "FirstPdf", "Shared"]

    # Anki deliberately copies tags to the next blank Add note. The editor
    # load hook must carry Incremento's ownership record with those sticky
    # tags so the next Cmd+1 can clean them up safely.
    second_note = _FakeNote(list(first_note.tags), note_id=0)
    editor.note = second_note
    editor.tags.setText(second_note.string_tags())
    dock._on_editor_did_load_note(editor)

    dock._pending_extract_options = {
        "priority": 25.0,
        "mark_topic": False,
        "link_to_knowledge_tree": False,
        "source": "pdf",
        "source_card_id": 202,
        "source_tags": ["SecondPdf", "Shared"],
        "seen": 0.0,
    }
    assert dock._apply_pending_extract_tags_to_editor(editor) is True

    assert second_note.tags == ["manual", "SecondPdf", "Shared"]
    assert dock._auto_extract_tag_keys_for_editor(editor, second_note) == {
        "secondpdf",
        "shared",
    }


def test_add_note_hook_carries_auto_tag_ownership_before_editor_load(monkeypatch):
    added_note = _FakeNote(["manual", "FirstPdf"], note_id=11)
    next_note = _FakeNote(list(added_note.tags), note_id=0)
    editor = _FakeEditor(note=next_note, add_mode=True)
    editor._incremento_auto_extract_tag_note = added_note
    editor._incremento_auto_extract_tag_keys = ["firstpdf"]

    monkeypatch.setattr(dock, "_iter_tracked_tag_button_editors", lambda: [editor])

    dock._carry_auto_extract_tag_keys_after_add(added_note)

    assert dock._auto_extract_tag_keys_for_editor(editor, next_note) == {"firstpdf"}


def test_extract_tag_refresh_does_not_claim_preexisting_manual_tag(monkeypatch):
    note = _FakeNote(["manual", "Shared"], note_id=0)
    editor = _FakeEditor(note=note, add_mode=True)

    monkeypatch.setattr(dock, "configured_extract_copy_source_tags", lambda config=None: True)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: None)
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: None)

    dock._pending_extract_options = {
        "priority": 25.0,
        "mark_topic": False,
        "link_to_knowledge_tree": False,
        "source": "pdf",
        "source_card_id": 101,
        "source_tags": ["Shared", "FirstPdf"],
        "seen": 0.0,
    }
    dock._apply_pending_extract_tags_to_editor(editor)
    assert dock._auto_extract_tag_keys_for_editor(editor, note) == {"firstpdf"}

    dock._pending_extract_options = {
        "priority": 25.0,
        "mark_topic": False,
        "link_to_knowledge_tree": False,
        "source": "pdf",
        "source_card_id": 202,
        "source_tags": ["SecondPdf"],
        "seen": 0.0,
    }
    dock._apply_pending_extract_tags_to_editor(editor)

    assert note.tags == ["manual", "Shared", "SecondPdf"]


def test_auto_topic_default_is_owned_and_cleaned_when_extract_mode_changes(monkeypatch):
    first_note = _FakeNote(["manual"], note_id=0)
    editor = _FakeEditor(note=first_note, add_mode=True)

    monkeypatch.setattr(dock, "_has_recent_selection", lambda: True)
    monkeypatch.setattr(dock, "_extract_mark_topic_for_transfer", lambda: True)
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])
    monkeypatch.setattr(dock, "_set_add_card_tag_button_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(dock, "_schedule_editor_tag_widget_sync", lambda current_editor: None)
    monkeypatch.setattr(dock, "_schedule_add_card_tag_button_refresh", lambda current_editor: None)

    dock._apply_extract_topic_default_to_editor(editor)

    assert first_note.tags == ["manual", "topic"]
    assert dock._auto_extract_tag_keys_for_editor(editor, first_note) == {"topic"}

    second_note = _FakeNote(list(first_note.tags), note_id=0)
    editor.note = second_note
    dock._carry_auto_extract_tag_keys_to_note(editor, second_note)
    dock._replace_auto_extract_tags(editor, second_note, mark_topic=False)

    assert second_note.tags == ["manual"]


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


def test_embedded_add_dialog_arms_queue_suppression_before_background_add(monkeypatch):
    note = _FakeNote(note_id=0)
    editor = _FakeEditor(note, add_mode=True)
    dlg = _FakeAddCardsDialog(editor)
    dlg.deck_chooser = types.SimpleNamespace(selected_deck_id=7)
    dlg._last_added_note = None
    dlg._add_current_note = lambda: None
    dlg._note_can_be_added = lambda current_note: True
    history_calls = []
    load_calls = []
    hook_calls = []
    armed = []
    add_note_calls = []
    audio_stop_calls = []

    dlg.addHistory = lambda current_note: history_calls.append(current_note)
    dlg._load_new_note = lambda sticky_fields_from=None: load_calls.append(sticky_fields_from)

    class _FakeAddNoteOp:
        def __init__(self, parent, current_note, target_deck_id):
            self.parent = parent
            self.note = current_note
            self.target_deck_id = target_deck_id
            self._success = None

        def success(self, callback):
            self._success = callback
            return self

        def run_in_background(self):
            add_note_calls.append(
                (self.parent, self.note, self.target_deck_id, len(armed))
            )
            assert self._success is not None
            self._success(types.SimpleNamespace(count=1))

    monkeypatch.setattr(
        dock,
        "pending_extract_options",
        lambda: {"source": "reviewer", "source_card_id": 42},
    )
    monkeypatch.setattr(
        dock,
        "mark_reviewer_extract_note_added",
        lambda options: armed.append(dict(options or {})),
    )
    monkeypatch.setattr(dock, "tooltip", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        dock,
        "gui_hooks",
        types.SimpleNamespace(
            add_cards_did_add_note=lambda current_note: hook_calls.append(current_note)
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "aqt.operations.note",
        types.SimpleNamespace(
            add_note=lambda parent, note, target_deck_id: _FakeAddNoteOp(
                parent, note, target_deck_id
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "aqt.sound",
        types.SimpleNamespace(
            av_player=types.SimpleNamespace(
                stop_and_clear_queue=lambda: audio_stop_calls.append(True)
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "aqt.utils",
        types.SimpleNamespace(
            tr=types.SimpleNamespace(
                importing_cards_added=lambda count: f"{count} card added"
            )
        ),
    )

    dock._install_embedded_add_dialog_hooks(dlg)
    dlg._add_current_note()

    assert armed == [{"source": "reviewer", "source_card_id": 42}]
    assert add_note_calls == [(dlg, note, 7, 1)]
    assert dlg._last_added_note is note
    assert history_calls == [note]
    assert load_calls == [note]
    assert hook_calls == [note]
    assert audio_stop_calls == [True]


def test_embedded_add_dialog_discard_retires_dock_and_extract_draft(monkeypatch):
    editor = _FakeEditor(_FakeNote(note_id=0), add_mode=True)
    dlg = _FakeAddCardsDialog(editor)
    close_calls = []
    removed_docks = []

    dlg._add_current_note = lambda: None
    dlg._close = lambda: close_calls.append("native-close") or "closed"

    class _DiscardedDock:
        def __init__(self):
            self._addcards_dialog = dlg
            self.hide_calls = 0
            self.delete_later_calls = 0

        def hide(self):
            self.hide_calls += 1

        def deleteLater(self):
            self.delete_later_calls += 1

    embedded_dock = _DiscardedDock()
    monkeypatch.setattr(dock, "_add_card_dock", embedded_dock)
    monkeypatch.setattr(dock, "_last_add_mode_editor", editor)
    monkeypatch.setattr(
        dock,
        "_pending_extract_options",
        {"source": "reviewer", "source_card_id": 42},
    )
    monkeypatch.setattr(
        dock,
        "_pending_extract_context",
        {"parent_card_id": 42, "metadata": {"source_type": "Extract"}},
    )
    monkeypatch.setattr(dock, "_current_extract_priority", 30.0)
    monkeypatch.setattr(dock, "_current_extract_mark_topic", True)
    monkeypatch.setattr(dock, "_current_extract_link_to_knowledge_tree", True)
    monkeypatch.setattr(dock, "_last_selection_source", "reviewer")
    monkeypatch.setattr(dock, "_last_selection_text", "discarded text")
    monkeypatch.setattr(dock, "_last_selection_seen", 123.0)
    monkeypatch.setattr(dock, "_last_fill_source", "reviewer")
    monkeypatch.setattr(dock, "_last_fill_seen", 123.0)
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(
            removeDockWidget=lambda current: removed_docks.append(current)
        ),
    )

    dock._install_embedded_add_dialog_hooks(dlg)

    assert dlg._close() == "closed"
    assert close_calls == ["native-close"]
    assert dock.get_add_card_dock() is None
    assert embedded_dock.hide_calls == 1
    assert embedded_dock.delete_later_calls == 1
    assert removed_docks == [embedded_dock]
    assert dock.pending_extract_options() is None
    assert dock.pending_extract_context() is None
    assert dock._current_extract_priority is None
    assert dock._current_extract_mark_topic is None
    assert dock._current_extract_link_to_knowledge_tree is None
    assert dock._last_add_mode_editor is None
    assert dock._last_selection_source == ""
    assert dock._last_selection_text == ""
    assert dock._last_selection_seen == 0.0
    assert dock._last_fill_source == ""
    assert dock._last_fill_seen == 0.0


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
    assert "var extractLabels =" in js
    assert "extractLabels.batch" in js
    # Both initial creation and refresh must use the chosen UI language.
    assert js.count("extractSourceLabel || extractLabels.selection") == 2
    assert "pycmd('incremento_open_extract_batch');" in js


def test_inject_transfer_buttons_shows_immediately_synced_priority_for_scratch_note(monkeypatch):
    note = _FakeNote(note_id=10)
    editor = _FakeEditor(note, add_mode=True)
    editor.web = _FakeWeb()

    monkeypatch.setattr(dock, "_last_selection_source", "")
    monkeypatch.setattr(dock, "_last_selection_seen", 0.0)
    monkeypatch.setattr(dock, "_current_extract_priority", None)
    monkeypatch.setattr(dock, "_current_extract_mark_topic", None)
    monkeypatch.setattr(dock, "_current_extract_link_to_knowledge_tree", None)
    monkeypatch.setattr(dock, "_pending_extract_options", None)

    dock.set_scratch_priority_for_editor(editor, 27.5)
    dock._inject_transfer_buttons(editor)

    js = editor.web.eval_calls[-1]
    assert "var optionsVisible = false;" in js
    assert "var defaultScratchPriority = 27.5;" in js
    assert "scratchPanel.style.display = this.optionsVisible ? 'none' : 'flex';" in js
    assert "input.addEventListener('input'" in js
    assert "window.incrementoTransferButtons.syncScratchPriority();" in js


def test_snapshot_extract_batch_state_requires_two_visible_fields(monkeypatch):
    note = _FakeNote(field_names=["Front", "Incremento_Parent"])
    editor = _FakeEditor(note=note, add_mode=True)
    fake_dock = _FakeDock(editor)
    fake_dock._addcards_dialog = types.SimpleNamespace(
        editor=editor,
        deck_chooser=types.SimpleNamespace(selected_deck_id=99),
    )

    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                decks=types.SimpleNamespace(get=lambda deck_id: {"id": deck_id, "name": "Topics"})
            )
        ),
    )

    try:
        dock.snapshot_extract_batch_state()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "at least two visible fields" in str(exc)


def test_snapshot_add_card_target_state_allows_one_visible_field(monkeypatch):
    note = _FakeNote(field_names=["Front", "Incremento_Parent"])
    editor = _FakeEditor(note=note, add_mode=True)
    fake_dock = _FakeDock(editor)
    fake_dock._addcards_dialog = types.SimpleNamespace(
        editor=editor,
        deck_chooser=types.SimpleNamespace(selected_deck_id=99),
    )

    monkeypatch.setattr(dock, "_add_card_dock", fake_dock)
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                decks=types.SimpleNamespace(get=lambda deck_id: {"id": deck_id, "name": "Topics"})
            )
        ),
    )

    snapshot = dock.snapshot_add_card_target_state(min_visible_fields=1)

    assert snapshot["note_type_name"] == "Basic"
    assert snapshot["deck_id"] == 99
    assert snapshot["deck_name"] == "Topics"
    assert snapshot["visible_fields"] == ["Front"]
    assert snapshot["note_type_model"]["flds"] == [{"name": "Front"}, {"name": "Incremento_Parent"}]


def test_snapshot_extract_batch_state_uses_originating_native_add_editor(monkeypatch):
    note = _FakeNote(["custom", "topic"], field_names=["Front", "Back"])
    editor = _FakeEditor(note=note, add_mode=True)
    editor.parentWindow = types.SimpleNamespace(
        deck_chooser=types.SimpleNamespace(selected_deck_id=42),
    )

    monkeypatch.setattr(dock, "_add_card_dock", None)
    monkeypatch.setattr(dock, "_pending_extract_options", {"priority": 7, "source": "pdf"})
    monkeypatch.setattr(dock, "_pending_extract_context", {"parent_card_id": 99})
    monkeypatch.setattr(dock, "scratch_priority_for_editor", lambda current: 64.5)
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                decks=types.SimpleNamespace(get=lambda deck_id: {"id": deck_id, "name": "Native deck"})
            )
        ),
    )

    snapshot = dock.snapshot_extract_batch_state(editor=editor)

    assert snapshot["deck_id"] == 42
    assert snapshot["deck_name"] == "Native deck"
    assert snapshot["extract_options"] == {
        "priority": 64.5,
        "mark_topic": True,
        "mark_item": False,
    }
    assert snapshot["extract_context"] == {}
    assert snapshot["default_classification"] == "topic"
    assert snapshot["default_tags"] == ["custom"]


def test_create_extract_batch_notes_uses_selected_field_mapping_and_explicit_state(monkeypatch):
    model = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}, {"name": "Extra"}],
    }
    collection = _BatchFakeCollection(model)
    priority_calls = []
    context_calls = []
    mark_calls = []

    monkeypatch.setattr(dock, "_pending_extract_options", {"priority": 77.0, "source": "pdf"})
    monkeypatch.setattr(
        dock,
        "mw",
        types.SimpleNamespace(col=collection),
    )
    monkeypatch.setattr(dock, "_ensure_incremento_metadata_fields_saved", lambda models, current_model: False)
    monkeypatch.setattr(
        dock,
        "apply_extract_options_to_note",
        lambda note, options: (
            priority_calls.append((note["Back"], dict(options)))
            or dict(options, priority_cards_changed=1, copied_source_tags=[])
        ),
    )
    monkeypatch.setattr(
        dock,
        "apply_extract_context_to_note",
        lambda note, options=None, context=None: (
            context_calls.append((note["Back"], dict(options or {}), dict(context or {})))
            or {"metadata_saved": True, "knowledge_tree_link_error": ""}
        ),
    )
    monkeypatch.setattr(dock, "mark_reviewer_extract_note_added", lambda options: mark_calls.append(dict(options or {})))
    monkeypatch.setattr(dock, "_notify_video_extract_note_added", lambda note, options: None)

    summary = dock.create_extract_batch_notes(
        note_type_name="Basic",
        deck_name="Topics",
        question_field="Back",
        answer_field="Extra",
        rows=[
            {
                "question": "Q1",
                "answer": "A1",
                "priority": 9.5,
                "classification": "topic",
                "tags": ["alpha"],
            },
            {
                "question": "Q2",
                "answer": "A2",
                "priority": 81,
                "classification": "item",
                "tags": ["beta", "shared"],
            },
        ],
        extract_options={
            "priority": 15.0,
            "mark_topic": False,
            "source": "reviewer",
            "source_card_id": 55,
        },
        extract_context={"parent_card_id": 55, "metadata": {"source_type": "Extract"}},
    )

    assert summary["created"] == 2
    assert summary["skipped"] == 0
    assert summary["failed"] == 0
    assert collection.created_notes[0]["Front"] == ""
    assert collection.created_notes[0]["Back"] == "Q1"
    assert collection.created_notes[0]["Extra"] == "A1"
    assert collection.created_notes[1]["Back"] == "Q2"
    assert collection.created_notes[1]["Extra"] == "A2"
    assert priority_calls == [
        ("Q1", {"priority": 9.5, "mark_topic": True, "source": "reviewer", "source_card_id": 55, "mark_item": False, "tags": ["alpha"]}),
        ("Q2", {"priority": 81.0, "mark_topic": False, "source": "reviewer", "source_card_id": 55, "mark_item": True, "tags": ["beta", "shared"]}),
    ]
    assert context_calls == [
        (
            "Q1",
            {"priority": 9.5, "mark_topic": True, "source": "reviewer", "source_card_id": 55, "mark_item": False, "tags": ["alpha"], "priority_cards_changed": 1, "copied_source_tags": []},
            {"parent_card_id": 55, "metadata": {"source_type": "Extract"}},
        ),
        (
            "Q2",
            {"priority": 81.0, "mark_topic": False, "source": "reviewer", "source_card_id": 55, "mark_item": True, "tags": ["beta", "shared"], "priority_cards_changed": 1, "copied_source_tags": []},
            {"parent_card_id": 55, "metadata": {"source_type": "Extract"}},
        ),
    ]
    assert len(mark_calls) == 2
    assert dock._pending_extract_options == {"priority": 77.0, "source": "pdf"}


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


def test_on_editor_did_update_tags_skips_extract_mode_sync_when_suspended(monkeypatch):
    note = _FakeNote(["item"], note_id=42)
    editor = _FakeEditor(note, add_mode=True)
    dock._tracked_tag_button_editors.clear()
    dock._track_tag_button_editor(editor)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda current_editor: None)
    monkeypatch.setattr(dock, "_refresh_transfer_buttons", lambda: None)
    sync_calls = []
    monkeypatch.setattr(
        dock,
        "sync_pending_extract_options_from_current",
        lambda: sync_calls.append(True),
    )
    dock._current_extract_mark_topic = True
    dock._push_extract_mark_topic_sync_suspension()

    try:
        dock._on_editor_did_update_tags(_FakeNote(["item"], note_id=42))
    finally:
        dock._pop_extract_mark_topic_sync_suspension()

    assert dock._current_extract_mark_topic is True
    assert sync_calls == []


def test_edit_mode_toolbar_buttons_register_even_before_note_is_loaded():
    buttons = []
    editor = _FakeEditor(note=None, add_mode=False)

    dock._add_add_card_tag_toolbar_buttons(buttons, editor)

    assert [button["label"] for button in buttons] == ["T", "I"]


def test_add_mode_toolbar_includes_priority_batch_qa_and_tag_buttons():
    buttons = []
    editor = _FakeEditor(note=None, add_mode=True)

    dock._add_add_card_tag_toolbar_buttons(buttons, editor)

    assert [button["label"] for button in buttons] == ["P", "Q/A", "T", "I"]
    assert buttons[0]["id"] == dock._ADD_CARD_PRIORITY_BUTTON_ID
    assert buttons[1]["id"] == dock._EXTRACT_BATCH_BUTTON_ID


def test_batch_qa_toolbar_button_dispatches_from_originating_editor():
    editor = _FakeEditor(_FakeNote(note_id=0), add_mode=True)
    editor.web = _FakeWeb()

    dock._on_extract_batch_button(editor)

    assert editor.web.eval_calls == ["pycmd('incremento_open_extract_batch');"]


def test_new_card_priority_button_stores_dialog_value_on_originating_note(monkeypatch):
    editor = _FakeEditor(_FakeNote(note_id=0), add_mode=True)
    dialog_calls = []
    refresh_calls = []
    messages = []

    class _FakePriorityDialog:
        priority = 12.75

        def __init__(self, **kwargs):
            dialog_calls.append(kwargs)

        def exec(self):
            return True

    monkeypatch.setattr(dock, "_priority_dialog_class", lambda: _FakePriorityDialog)
    monkeypatch.setattr(
        dock,
        "_config",
        lambda config=None: {"priority_lower_is_more_important": False},
    )
    monkeypatch.setattr(
        dock,
        "_inject_transfer_buttons",
        lambda current_editor: refresh_calls.append(current_editor),
    )
    monkeypatch.setattr(dock, "tooltip", lambda message: messages.append(message))

    dock._on_add_card_priority_button(editor)

    assert dialog_calls[0]["current_priority"] == 50.0
    assert dialog_calls[0]["lower_is_more_important"] is False
    assert dock.scratch_priority_for_note(editor.note) == 12.75
    assert refresh_calls == [editor]
    assert messages == ["New-card priority set to 12.75"]


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


def test_topic_button_releases_classification_tags_from_auto_ownership(monkeypatch):
    note = _FakeNote(["Source", "topic"], note_id=0)
    editor = _FakeEditor(note, add_mode=True)
    toggle_calls = []

    dock._set_auto_extract_tag_keys_for_editor(editor, note, ["Source", "topic"])
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])
    monkeypatch.setattr(
        dock,
        "_toggle_editor_tag_button",
        lambda *args, **kwargs: toggle_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(dock, "_sync_extract_mark_topic_from_note", lambda current_note: None)

    dock._on_topic_tag_button(editor)

    assert len(toggle_calls) == 1
    assert dock._auto_extract_tag_keys_for_editor(editor, note) == {"source"}


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


def test_transfer_selection_to_field_updates_pending_extract_source_before_fill(monkeypatch):
    pending_sources = []

    monkeypatch.setattr(dock, "_has_recent_selection", lambda: True)
    monkeypatch.setattr(dock, "_last_selection_source", "reviewer")
    monkeypatch.setattr(dock, "_last_selection_text", "")
    monkeypatch.setattr(dock, "_current_extract_priority", None)
    monkeypatch.setattr(dock, "_resolve_selection_from_source", lambda source, callback: callback(source, "Selection"))
    monkeypatch.setattr(dock, "source_relative_extract_priority_for_source", lambda source: 15.0)
    monkeypatch.setattr(dock, "_extract_mark_topic_for_transfer", lambda: False)
    monkeypatch.setattr(dock, "_extract_link_to_knowledge_tree_for_transfer", lambda: True)

    original_set_pending = dock.set_pending_extract_options

    def _record_pending(**kwargs):
        result = original_set_pending(**kwargs)
        pending_sources.append(result["source"])
        return result

    monkeypatch.setattr(dock, "set_pending_extract_options", _record_pending)
    monkeypatch.setattr(
        dock,
        "fill_dock_field",
        lambda *args, **kwargs: pending_sources.append((dock.pending_extract_options() or {}).get("source")),
    )

    dock.transfer_selection_to_field(0)

    assert pending_sources == ["reviewer", "reviewer"]


def test_web_transfer_stages_marker_before_fill_callback_and_rolls_back_failure(
    monkeypatch,
):
    events = []
    record = {
        "webCardId": 17,
        "url": "https://example.com/guide",
        "anchor": {
            "version": 1,
            "exact": "Selection",
            "prefix": "before ",
            "suffix": " after",
            "startPath": [0],
            "startOffset": 0,
            "endPath": [0],
            "endOffset": 9,
        },
    }
    fake_web_dock = types.SimpleNamespace(
        get_selected_extraction=lambda callback: callback("Selection", record),
        web_citation=lambda: None,
        _accept_web_extract_record=lambda current, *, expected_profile: events.append(
            ("stage", current, expected_profile)
        )
        or True,
        _remove_pending_web_extract_record=lambda current, *, expected_profile: events.append(
            ("rollback", current, expected_profile)
        )
        or True,
    )
    fill_calls = []

    monkeypatch.setattr(dock, "__package__", "frontend")
    monkeypatch.setitem(sys.modules, "frontend.web_dock", fake_web_dock)
    monkeypatch.setattr(dock, "_has_recent_selection", lambda: True)
    monkeypatch.setattr(dock, "_last_selection_source", "web")
    monkeypatch.setattr(dock, "_last_selection_text", "")
    monkeypatch.setattr(dock, "_current_extract_priority", None)
    monkeypatch.setattr(dock, "_active_profile", lambda: "Profile A")
    monkeypatch.setattr(dock, "source_relative_extract_priority_for_source", lambda source: 15.0)
    monkeypatch.setattr(dock, "_extract_mark_topic_for_transfer", lambda: False)
    monkeypatch.setattr(dock, "_extract_link_to_knowledge_tree_for_transfer", lambda: True)
    monkeypatch.setattr(
        dock,
        "fill_dock_field",
        lambda *args, **kwargs: fill_calls.append((args, kwargs)),
    )

    dock.transfer_selection_to_field(0)

    assert events == [("stage", record, "Profile A")]
    assert len(fill_calls) == 1
    fill_calls[0][1]["on_complete"](False)
    assert events == [
        ("stage", record, "Profile A"),
        ("rollback", record, "Profile A"),
    ]


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


def test_apply_extract_topic_mark_to_editor_adds_topic_and_removes_item(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "item"], note_id=9), add_mode=True)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: func(),
    )
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])

    changed = dock.apply_extract_topic_mark_to_editor(editor, True)

    assert changed is True
    assert editor.note.tags == ["keep", "topic"]
    assert editor.tags.text_value == "keep topic"


def test_apply_extract_topic_mark_to_editor_removes_topic(monkeypatch):
    editor = _FakeEditor(_FakeNote(["keep", "topic"], note_id=9), add_mode=True)
    monkeypatch.setattr(dock, "_refresh_add_card_tag_buttons_for_editor", lambda editor: None)
    monkeypatch.setattr(dock, "mw", type("MW", (), {"col": _FakeCol()})())
    monkeypatch.setattr(
        dock.QTimer,
        "singleShot",
        lambda delay, func: func(),
    )
    monkeypatch.setattr(dock, "configured_add_card_topic_tags", lambda config=None: ["topic"])
    monkeypatch.setattr(dock, "configured_add_card_item_tags", lambda config=None: ["item"])

    changed = dock.apply_extract_topic_mark_to_editor(editor, False)

    assert changed is True
    assert editor.note.tags == ["keep"]
    assert editor.tags.text_value == "keep"
