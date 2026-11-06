"""Shared, explicit selected-text searches for Anki and Incremento readers."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

try:
    from ..backend.i18n import t
    from ..backend.config_service import configured_web_search_engine, configured_search_remember_logins
    from ..backend.paths import get_active_profile as _active_profile
    from ..backend.content_safety import normalize_external_http_url
except ImportError:
    from backend.i18n import t
    from backend.config_service import configured_web_search_engine, configured_search_remember_logins
    from backend.paths import get_active_profile as _active_profile
    from backend.content_safety import normalize_external_http_url


_ACTION_NAME = "incremento_search_google"
_popup = None
_popups = []
_shared_profile = None
_shared_anki_profile = None
_search_engine = "google"
_remember_logins = False
_ADDON_DIR = str(Path(__file__).resolve().parents[1])


def configure_search(config) -> None:
    global _search_engine, _remember_logins
    remember = configured_search_remember_logins(config)
    if remember != _remember_logins:
        reset_for_profile_switch()
    _search_engine = configured_web_search_engine(config)
    _remember_logins = remember


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
    """Compatibility helper for callers explicitly requesting Google."""
    return search_url(value, "google")


def search_url(value: object, engine: str = "google") -> str | None:
    text = _search_text(value)
    engine = configured_web_search_engine({"web_search_engine": engine})
    base = "https://duckduckgo.com/?" if engine == "duckduckgo" else "https://www.google.com/search?"
    return base + urlencode({"q": text}) if text else None


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
    action = menu.addAction(t("selection_search_duckduckgo" if _search_engine == "duckduckgo" else "selection_search_google"))
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


def _tabbed_owner(parent):
    if parent is None:
        from aqt import mw
        parent = mw
    for _ in range(32):
        if parent is None:
            return None
        manager = getattr(parent, '_incremento_workspace_layouts', None)
        if manager is not None and getattr(manager, 'tabbed', False) is True:
            return parent
        ancestor = getattr(parent, 'parentWidget', None)
        parent = ancestor() if callable(ancestor) else None
    return None


def _release_unused_shared_profile():
    global _shared_profile, _shared_anki_profile
    if not _popups and _shared_profile is not None:
        from .browser_profiles import destroy_browser
        profile, _shared_profile = _shared_profile, None
        _shared_anki_profile = None
        destroy_browser(None, profile)


def show_google_search(text: str, parent=None) -> None:
    """Open the selected provider (legacy entry-point name)."""
    url = search_url(text, _search_engine)
    if url is not None:
        return open_search_url(url, parent=parent)


def open_search_url(url, parent=None, *, new_tab=False, activate=True):
    """Use the same isolated browser lifetime for explicit opens and tab recovery."""
    global _popup, _shared_profile, _shared_anki_profile
    try:
        url = normalize_external_http_url(url)
    except (TypeError, ValueError):
        return
    from .google_search_dialog import GoogleSearchDialog

    profile = _active_profile()
    existing = _popup or (_popups[0] if _popups else None)
    if ((existing is not None and existing.anki_profile != profile)
            or (_shared_profile is not None and _shared_anki_profile != profile)):
        reset_for_profile_switch()
    owner = parent if new_tab else _tabbed_owner(parent)
    if owner is not None and len(_popups) >= 32:
        from aqt.utils import tooltip
        tooltip(t('reader_reference_unavailable'))
        return
    if owner is not None or _popup is None:
        if owner is not None and _shared_profile is None and _popup is not None:
            _shared_profile = _popup._profile
            _shared_anki_profile = profile
            _shared_profile.setParent(None)
            _popup._owns_profile = False
            if _popup.isHidden():
                _popup.dispose()
        popup = GoogleSearchDialog(owner or parent, anki_profile=profile, addon_dir=_ADDON_DIR,
                                   remember_logins=_remember_logins, browser_profile=_shared_profile)
        if owner is not None:
            if _shared_profile is None:
                _shared_profile = popup._profile
                _shared_anki_profile = profile
                _shared_profile.setParent(None)
                popup._owns_profile = False
            popup.setObjectName('incremento_search_dock_' + uuid4().hex)
            from aqt.qt import Qt
            popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            if not getattr(owner, '_incremento_search_shutdown', False):
                owner._incremento_search_shutdown = True
                owner.destroyed.connect(lambda *_: reset_for_profile_switch())
        _popup = popup
        _popups.append(popup)

        def clear_reference(*_args):
            global _popup
            if _popup is popup:
                _popup = None

        def retired(*_args):
            clear_reference()
            if popup in _popups:
                _popups.remove(popup)
            if _shared_profile is not None:
                from aqt.qt import QTimer
                # QObject emits destroyed before deleting its child WebEngine
                # pages. Release their shared profile on the following turn.
                QTimer.singleShot(0, _release_unused_shared_profile)

        if not _remember_logins or owner is not None:
            popup.finished.connect(clear_reference)
        popup.destroyed.connect(retired)
    _popup.search(url)
    _popup.show()
    _popup.raise_()
    if activate:
        _popup.activateWindow()
    return _popup


def reset_for_profile_switch() -> None:
    global _popup, _shared_profile, _shared_anki_profile
    popups = list(_popups)
    if _popup is not None and _popup not in popups:
        popups.append(_popup)
    profile, _shared_profile = _shared_profile, None
    _shared_anki_profile = None
    _popup = None
    _popups.clear()
    for popup in popups:
        popup.close()
        popup.dispose()
    if profile is not None:
        from .browser_profiles import destroy_browser
        destroy_browser(None, profile)
