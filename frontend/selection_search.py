"""Shared, explicit selected-text searches for Anki and Incremento readers."""

from __future__ import annotations

import re
from urllib.parse import urlencode

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile as _active_profile


_ACTION_NAME = "incremento_search_google"
_popup = None


def _search_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    # Bound work before normalizing potentially very large document selections.
    value = re.sub(r"[\ud800-\udfff]", "", value[:10_000])
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    text = " ".join(value.split())[:1000].strip()
    # UTF-8 bytes can each expand to three URL characters after percent encoding.
    return text.encode("utf-8")[:2500].decode("utf-8", errors="ignore")


def google_search_url(value: object) -> str | None:
    text = _search_text(value)
    return "https://www.google.com/search?" + urlencode({"q": text}) if text else None


def _selected_text(view) -> str:
    try:
        if callable(getattr(view, "selectedText", None)):
            return _search_text(view.selectedText())
        return _search_text(view.textCursor().selectedText())
    except (AttributeError, RuntimeError):
        return ""


def add_selection_search_action(view, menu) -> None:
    """Append to the existing menu, capturing text before the menu takes focus."""
    text = _selected_text(view)
    if not text or any(action.objectName() == _ACTION_NAME for action in menu.actions()):
        return
    profile = _active_profile()
    if menu.actions():
        menu.addSeparator()
    action = menu.addAction(t("selection_search_google"))
    action.setObjectName(_ACTION_NAME)

    def search(_checked=False):
        if _active_profile() != profile:
            return
        try:
            parent = view.window()
        except (AttributeError, RuntimeError):
            parent = None
        show_google_search(text, parent=parent)

    action.triggered.connect(search)


def install_selection_search_menu(view) -> None:
    """Preserve native WebEngine/text-edit actions in standalone reader widgets."""
    from aqt.qt import Qt

    if getattr(view, "_incremento_selection_search_installed", False):
        return

    def show_menu(position):
        menu = view.createStandardContextMenu()
        if menu is None:
            return
        try:
            add_selection_search_action(view, menu)
            # QTextEdit sends viewport-relative positions; WebEngine uses itself.
            viewport = getattr(view, "viewport", None)
            origin = viewport() if callable(viewport) else view
            menu.exec(origin.mapToGlobal(position))
        finally:
            menu.deleteLater()

    view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    view.customContextMenuRequested.connect(show_menu)
    view._incremento_selection_search_installed = True


def show_google_search(text: str, parent=None) -> None:
    global _popup
    url = google_search_url(text)
    if url is None:
        return
    from .google_search_dialog import GoogleSearchDialog

    profile = _active_profile()
    if _popup is not None and _popup.anki_profile != profile:
        reset_for_profile_switch()
    if _popup is None:
        popup = GoogleSearchDialog(parent, anki_profile=profile)
        _popup = popup

        def clear_reference(*_args):
            global _popup
            if _popup is popup:
                _popup = None

        popup.finished.connect(clear_reference)
        popup.destroyed.connect(clear_reference)
    _popup.search(url)
    _popup.show()
    _popup.raise_()
    _popup.activateWindow()


def reset_for_profile_switch() -> None:
    global _popup
    popup, _popup = _popup, None
    if popup is not None:
        popup.close()
        popup.deleteLater()
