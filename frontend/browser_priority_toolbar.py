"""Existing-card editor toolbar buttons for per-card priority."""

from __future__ import annotations

from collections.abc import Callable

try:
    from aqt import gui_hooks, mw
    from aqt.utils import showInfo
except Exception:  # pragma: no cover - only used outside Anki/test stubs.
    gui_hooks = None
    mw = None

    def showInfo(_message: str) -> None:
        return None


BROWSER_PRIORITY_BUTTON_ID = "incremento-browser-priority"
EDIT_CURRENT_PRIORITY_BUTTON_ID = "incremento-edit-current-priority"
BROWSER_PRIORITY_AMBIGUOUS_MESSAGE = "Select exactly one Browser card row first."
EDIT_CURRENT_PRIORITY_UNAVAILABLE_MESSAGE = "Could not determine the card being edited."

_open_priority_dialog_for_card: Callable[[object], object] | None = None


def register_open_priority_dialog_callback(callback: Callable[[object], object]) -> None:
    global _open_priority_dialog_for_card
    _open_priority_dialog_for_card = callback


def _looks_like_browser(candidate) -> bool:
    if candidate is None:
        return False

    cls = candidate.__class__
    class_name = str(getattr(cls, "__name__", "") or "")
    module_name = str(getattr(cls, "__module__", "") or "")
    if (
        class_name == "Browser"
        or module_name == "aqt.browser"
        or module_name.startswith("aqt.browser.")
    ):
        return True

    has_selected_cards = any(
        callable(getattr(candidate, method_name, None))
        for method_name in ("selected_cards", "selectedCards")
    )
    has_refresh = any(
        callable(getattr(candidate, method_name, None))
        for method_name in ("search", "refresh")
    )
    return has_selected_cards and has_refresh


def _browser_for_editor(editor):
    for attr_name in ("parentWindow", "parent_window", "browser"):
        candidate = getattr(editor, attr_name, None)
        if _looks_like_browser(candidate):
            return candidate

    current = getattr(editor, "widget", None)
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if _looks_like_browser(current):
            return current
        parent = getattr(current, "parent", None)
        if callable(parent):
            try:
                current = parent()
            except Exception:
                break
        else:
            current = parent
    return None


def _looks_like_edit_current(candidate) -> bool:
    if candidate is None:
        return False

    cls = candidate.__class__
    class_name = str(getattr(cls, "__name__", "") or "")
    module_name = str(getattr(cls, "__module__", "") or "")
    return class_name in {"EditCurrent", "EditCurrentDialog"} or (
        module_name == "aqt.editcurrent" and hasattr(candidate, "editor")
    )


def _edit_current_for_editor(editor):
    for attr_name in ("parentWindow", "parent_window"):
        candidate = getattr(editor, attr_name, None)
        if _looks_like_edit_current(candidate):
            return candidate

    current = getattr(editor, "widget", None)
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        if _looks_like_edit_current(current):
            return current
        parent = getattr(current, "parent", None)
        if callable(parent):
            try:
                current = parent()
            except Exception:
                break
        else:
            current = parent
    return None


def _is_card_like(value) -> bool:
    if value is None:
        return False
    try:
        int(getattr(value, "id"))
    except Exception:
        return False
    return True


def _collection(browser=None):
    browser_col = getattr(browser, "col", None) if browser is not None else None
    if browser_col is not None:
        return browser_col
    return getattr(mw, "col", None)


def _card_from_ref(card_ref, browser=None):
    if _is_card_like(card_ref):
        return card_ref

    try:
        card_id = int(card_ref)
    except Exception:
        return None

    col = _collection(browser)
    get_card = getattr(col, "get_card", None)
    if not callable(get_card):
        return None
    try:
        card = get_card(card_id)
    except Exception:
        return None
    return card if _is_card_like(card) else None


def _selected_browser_card_refs(browser) -> list[object]:
    if browser is None:
        return []

    refs: list[object] = []
    seen: set[int] = set()
    for method_name in ("selected_cards", "selectedCards"):
        method = getattr(browser, method_name, None)
        if not callable(method):
            continue
        try:
            selected = list(method() or [])
        except Exception:
            continue
        for raw_ref in selected:
            card = raw_ref if _is_card_like(raw_ref) else None
            try:
                card_id = int(getattr(card, "id") if card is not None else raw_ref)
            except Exception:
                continue
            if card_id in seen:
                continue
            seen.add(card_id)
            refs.append(card if card is not None else card_id)
    return refs


def _note_cards(note, browser=None) -> list[object]:
    if note is None:
        return []

    cards_method = getattr(note, "cards", None)
    if callable(cards_method):
        try:
            refs = list(cards_method() or [])
        except Exception:
            refs = []
        cards = [_card_from_ref(ref, browser) for ref in refs]
        return [card for card in cards if card is not None]

    note_id = getattr(note, "id", None)
    if note_id is None:
        return []

    col = _collection(browser)
    find_cards = getattr(col, "find_cards", None)
    if not callable(find_cards):
        return []
    try:
        refs = list(find_cards(f"nid:{int(note_id)}") or [])
    except Exception:
        return []
    cards = [_card_from_ref(ref, browser) for ref in refs]
    return [card for card in cards if card is not None]


def resolve_browser_priority_card(editor, browser=None):
    explicit_card = _card_from_ref(getattr(editor, "card", None), browser)
    if explicit_card is not None:
        return explicit_card

    if browser is None:
        browser = _browser_for_editor(editor)

    selected_refs = _selected_browser_card_refs(browser)
    if len(selected_refs) > 1:
        return None
    if len(selected_refs) == 1:
        return _card_from_ref(selected_refs[0], browser)

    note_cards = _note_cards(getattr(editor, "note", None), browser)
    if len(note_cards) == 1:
        return note_cards[0]
    return None


def _notes_match(first, second) -> bool:
    if first is None or second is None:
        return False
    if first is second:
        return True
    try:
        first_id = int(getattr(first, "id"))
        second_id = int(getattr(second, "id"))
    except Exception:
        return False
    return first_id > 0 and first_id == second_id


def resolve_edit_current_priority_card(editor):
    if _edit_current_for_editor(editor) is None:
        return None

    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer is not None else None
    if not _is_card_like(card):
        return None
    try:
        card_note = card.note()
    except Exception:
        return None
    return card if _notes_match(getattr(editor, "note", None), card_note) else None


def _is_browser_editor(editor) -> bool:
    if getattr(editor, "addMode", False):
        return False
    return _browser_for_editor(editor) is not None


def _is_edit_current_editor(editor) -> bool:
    if getattr(editor, "addMode", False):
        return False
    return _edit_current_for_editor(editor) is not None


def _refresh_browser(browser) -> None:
    if browser is None:
        return

    for method_name in ("search", "refresh"):
        method = getattr(browser, method_name, None)
        if not callable(method):
            continue
        try:
            method()
            return
        except Exception:
            continue

    table = getattr(browser, "table", None)
    update = getattr(table, "update", None)
    if callable(update):
        try:
            update()
        except Exception:
            pass


def _on_browser_priority_button(editor) -> None:
    if getattr(editor, "addMode", False):
        return
    browser = _browser_for_editor(editor)
    is_edit_current = browser is None and _is_edit_current_editor(editor)
    if browser is None and not is_edit_current:
        return
    card = (
        resolve_browser_priority_card(editor, browser)
        if browser is not None
        else resolve_edit_current_priority_card(editor)
    )
    if card is None:
        showInfo(
            BROWSER_PRIORITY_AMBIGUOUS_MESSAGE
            if browser is not None
            else EDIT_CURRENT_PRIORITY_UNAVAILABLE_MESSAGE
        )
        return

    if _open_priority_dialog_for_card is None:
        showInfo("Priority dialog is unavailable.")
        return

    saved = _open_priority_dialog_for_card(card)
    if saved is not False and browser is not None:
        _refresh_browser(browser)


def _add_browser_priority_toolbar_button(buttons, editor) -> None:
    is_browser = _is_browser_editor(editor)
    is_edit_current = not is_browser and _is_edit_current_editor(editor)
    if not is_browser and not is_edit_current:
        return

    buttons.append(
        editor.addButton(
            None,
            (
                "incrementoBrowserPriority"
                if is_browser
                else "incrementoEditCurrentPriority"
            ),
            _on_browser_priority_button,
            tip=(
                "Set priority for selected Browser card"
                if is_browser
                else "Set priority for the current card"
            ),
            label="P",
            id=(
                BROWSER_PRIORITY_BUTTON_ID
                if is_browser
                else EDIT_CURRENT_PRIORITY_BUTTON_ID
            ),
            disables=False,
        )
    )


try:
    gui_hooks.editor_did_init_buttons.append(_add_browser_priority_toolbar_button)
except Exception:
    pass
