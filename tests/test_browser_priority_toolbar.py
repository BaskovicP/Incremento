import types

import browser_priority_toolbar as toolbar


class _FakeCard:
    def __init__(self, card_id, note=None):
        self.id = card_id
        self._note = note

    def note(self):
        return self._note


class _FakeNote:
    def __init__(self, cards=None, note_id=1):
        self._cards = list(cards or [])
        self.id = note_id

    def cards(self):
        return list(self._cards)


class _FakeCol:
    def __init__(self, cards=None):
        self.cards = {int(card.id): card for card in list(cards or [])}

    def get_card(self, card_id):
        return self.cards.get(int(card_id))

    def find_cards(self, query):
        if not str(query).startswith("nid:"):
            return []
        return [card_id for card_id in self.cards]


class _FakeBrowser:
    def __init__(self, selected=(), cards=None):
        self._selected = list(selected)
        self.col = _FakeCol(cards)
        self.search_calls = 0

    def selected_cards(self):
        return list(self._selected)

    def search(self):
        self.search_calls += 1


EditCurrent = type("EditCurrent", (), {"__module__": "aqt.editcurrent"})


class _FakeEditor:
    def __init__(self, *, note=None, card=None, add_mode=False, browser=None):
        self.note = note
        self.addMode = add_mode
        self.parentWindow = browser
        self.added_buttons = []
        if card is not None:
            self.card = card

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


def test_resolve_browser_priority_card_uses_editor_card():
    explicit = _FakeCard(10)
    selected = [_FakeCard(20), _FakeCard(30)]
    browser = _FakeBrowser(selected=[20, 30], cards=selected)
    editor = _FakeEditor(card=explicit, browser=browser)

    assert toolbar.resolve_browser_priority_card(editor, browser) is explicit


def test_resolve_browser_priority_card_uses_exactly_one_selected_browser_card():
    note_card = _FakeCard(10)
    selected_card = _FakeCard(20)
    note = _FakeNote([note_card])
    browser = _FakeBrowser(selected=[20], cards=[note_card, selected_card])
    editor = _FakeEditor(note=note, browser=browser)

    assert toolbar.resolve_browser_priority_card(editor, browser) is selected_card


def test_resolve_browser_priority_card_falls_back_to_single_note_card():
    note_card = _FakeCard(10)
    note = _FakeNote([note_card])
    browser = _FakeBrowser(selected=[], cards=[note_card])
    editor = _FakeEditor(note=note, browser=browser)

    assert toolbar.resolve_browser_priority_card(editor, browser) is note_card


def test_resolve_browser_priority_card_rejects_multiple_selected_cards():
    note_card = _FakeCard(10)
    selected_card = _FakeCard(20)
    note = _FakeNote([note_card])
    browser = _FakeBrowser(selected=[10, 20], cards=[note_card, selected_card])
    editor = _FakeEditor(note=note, browser=browser)

    assert toolbar.resolve_browser_priority_card(editor, browser) is None


def test_resolve_browser_priority_card_rejects_multi_card_note_without_specific_card():
    first = _FakeCard(10)
    second = _FakeCard(20)
    note = _FakeNote([first, second])
    browser = _FakeBrowser(selected=[], cards=[first, second])
    editor = _FakeEditor(note=note, browser=browser)

    assert toolbar.resolve_browser_priority_card(editor, browser) is None


def test_toolbar_button_registers_only_for_browser_editors():
    card = _FakeCard(10)
    browser = _FakeBrowser(cards=[card])

    add_buttons = []
    toolbar._add_browser_priority_toolbar_button(
        add_buttons,
        _FakeEditor(add_mode=True, browser=browser),
    )
    assert add_buttons == []

    other_edit_buttons = []
    toolbar._add_browser_priority_toolbar_button(
        other_edit_buttons,
        _FakeEditor(add_mode=False, browser=None),
    )
    assert other_edit_buttons == []

    edit_buttons = []
    toolbar._add_browser_priority_toolbar_button(
        edit_buttons,
        _FakeEditor(add_mode=False, browser=browser),
    )

    assert len(edit_buttons) == 1
    assert edit_buttons[0]["id"] == toolbar.BROWSER_PRIORITY_BUTTON_ID
    assert edit_buttons[0]["label"] == "P"


def test_toolbar_button_registers_for_edit_current_editor():
    buttons = []
    editor = _FakeEditor(add_mode=False, browser=EditCurrent())

    toolbar._add_browser_priority_toolbar_button(buttons, editor)

    assert len(buttons) == 1
    assert buttons[0]["id"] == toolbar.EDIT_CURRENT_PRIORITY_BUTTON_ID
    assert buttons[0]["label"] == "P"


def test_browser_priority_button_opens_dialog_and_refreshes_browser(monkeypatch):
    card = _FakeCard(10)
    browser = _FakeBrowser(selected=[10], cards=[card])
    editor = _FakeEditor(browser=browser)
    opened = []
    monkeypatch.setattr(toolbar, "mw", types.SimpleNamespace(col=browser.col))
    toolbar.register_open_priority_dialog_callback(
        lambda resolved: opened.append(resolved) or True
    )

    toolbar._on_browser_priority_button(editor)

    assert opened == [card]
    assert browser.search_calls == 1


def test_edit_current_priority_button_opens_dialog_for_current_reviewer_card(monkeypatch):
    note = _FakeNote(note_id=5)
    card = _FakeCard(10, note=note)
    editor = _FakeEditor(note=note, browser=EditCurrent())
    opened = []
    monkeypatch.setattr(
        toolbar,
        "mw",
        types.SimpleNamespace(reviewer=types.SimpleNamespace(card=card)),
    )
    toolbar.register_open_priority_dialog_callback(
        lambda resolved: opened.append(resolved) or True
    )

    toolbar._on_browser_priority_button(editor)

    assert opened == [card]


def test_edit_current_priority_button_ignores_stale_explicit_editor_card(monkeypatch):
    note = _FakeNote(note_id=5)
    current_card = _FakeCard(10, note=note)
    stale_card = _FakeCard(20, note=_FakeNote(note_id=6))
    editor = _FakeEditor(
        note=note,
        card=stale_card,
        browser=EditCurrent(),
    )
    opened = []
    monkeypatch.setattr(
        toolbar,
        "mw",
        types.SimpleNamespace(reviewer=types.SimpleNamespace(card=current_card)),
    )
    toolbar.register_open_priority_dialog_callback(
        lambda resolved: opened.append(resolved) or True
    )

    toolbar._on_browser_priority_button(editor)

    assert opened == [current_card]


def test_edit_current_priority_button_fails_closed_for_mismatched_note(monkeypatch):
    card = _FakeCard(10, note=_FakeNote(note_id=5))
    editor = _FakeEditor(note=_FakeNote(note_id=6), browser=EditCurrent())
    opened = []
    messages = []
    monkeypatch.setattr(
        toolbar,
        "mw",
        types.SimpleNamespace(reviewer=types.SimpleNamespace(card=card)),
    )
    monkeypatch.setattr(toolbar, "showInfo", lambda message: messages.append(message))
    toolbar.register_open_priority_dialog_callback(
        lambda resolved: opened.append(resolved) or True
    )

    toolbar._on_browser_priority_button(editor)

    assert opened == []
    assert messages == [toolbar.EDIT_CURRENT_PRIORITY_UNAVAILABLE_MESSAGE]


def test_browser_priority_button_shows_ambiguity_message(monkeypatch):
    cards = [_FakeCard(10), _FakeCard(20)]
    browser = _FakeBrowser(selected=[10, 20], cards=cards)
    editor = _FakeEditor(browser=browser)
    messages = []
    opened = []
    monkeypatch.setattr(toolbar, "showInfo", lambda message: messages.append(message))
    toolbar.register_open_priority_dialog_callback(lambda card: opened.append(card) or True)

    toolbar._on_browser_priority_button(editor)

    assert messages == [toolbar.BROWSER_PRIORITY_AMBIGUOUS_MESSAGE]
    assert opened == []
    assert browser.search_calls == 0
