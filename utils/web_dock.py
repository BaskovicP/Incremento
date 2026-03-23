"""
web_dock.py — Web browsing dock (QWebEngineView with persistent profile).

Displays web pages in a right-side dock that persists across card reviews.
The last-visited URL is saved when the page finishes loading.

Public API:
    show_web_in_dock(card_id, home_url, last_url)
    on_web_question_shown(card)
    on_web_reviewer_will_end()
    sync_web_note_type()
    add_web_function()
"""

import os

from aqt import mw
from aqt.utils import showInfo, tooltip
from aqt.qt import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                    QPushButton, QLabel, Qt, qconnect)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

from .web_manager import (WEB_NOTE_TYPE, get_web_url, set_web_url,
                          ensure_web_note_type, add_web_card)

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_web_dock             = None
_current_web_card_id  = None
_current_web_home_url = None  # original URL from the card's URL field
_web_profile          = None  # module-level singleton


def _build_web_dock():
    global _web_dock, _web_profile

    from PyQt6.QtWebEngineCore import (QWebEngineSettings as _WES,
                                       QWebEngineProfile as _WEProf,
                                       QWebEnginePage as _WEPage)

    dock = QDockWidget("Web", mw)
    dock.setObjectName("incremento_web_dock")
    dock.setMinimumWidth(600)

    container = QWidget()
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(0)

    view = QWebEngineView(container)

    if _web_profile is None:
        _web_profile = _WEProf("incremento_web")
        _web_profile.setPersistentStoragePath(
            os.path.join(_ADDON_DIR, "user_files", "web_profile")
        )
        _web_profile.setPersistentCookiesPolicy(
            _WEProf.PersistentCookiesPolicy.ForcePersistentCookies
        )
        _web_profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        _web_profile.settings().setAttribute(
            _WES.WebAttribute.PlaybackRequiresUserGesture, False
        )

    _page = _WEPage(_web_profile)
    view.setPage(_page)

    vbox.addWidget(view, 1)

    # Controls bar: URL display + Home button
    ctrl = QWidget(container)
    ctrl_layout = QHBoxLayout(ctrl)
    ctrl_layout.setContentsMargins(8, 4, 8, 4)
    ctrl_layout.setSpacing(6)

    url_lbl = QLabel("")
    url_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #888;")
    url_lbl.setWordWrap(False)
    url_lbl.setMaximumWidth(500)
    ctrl_layout.addWidget(url_lbl, 1)

    home_btn = QPushButton("⌂ Home")
    home_btn.setFixedWidth(70)
    ctrl_layout.addWidget(home_btn)

    vbox.addWidget(ctrl)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._view    = view
    dock._url_lbl = url_lbl

    def _on_url_changed(qurl):
        url_str = qurl.toString()
        display = url_str if len(url_str) <= 80 else url_str[:77] + "…"
        try:
            url_lbl.setText(display)
        except RuntimeError:
            pass

    def _on_load_finished(ok):
        if not ok or _current_web_card_id is None:
            return
        url_str = view.url().toString()
        if url_str and url_str != "about:blank":
            try:
                set_web_url(_ADDON_DIR, _current_web_card_id, url_str)
            except Exception:
                pass

    view.urlChanged.connect(_on_url_changed)
    view.loadFinished.connect(_on_load_finished)
    qconnect(home_btn.clicked, _web_go_home)

    _web_dock = dock
    return dock


def _web_go_home() -> None:
    if _web_dock is None or not _current_web_home_url:
        return
    try:
        _web_dock._view.load(QUrl(_current_web_home_url))
    except (RuntimeError, AttributeError):
        pass


def show_web_in_dock(card_id: int, home_url: str, last_url: str) -> None:
    global _web_dock, _current_web_card_id, _current_web_home_url

    _current_web_card_id  = card_id
    _current_web_home_url = home_url

    if _web_dock is None:
        _build_web_dock()
    else:
        try:
            _web_dock.widget()
        except RuntimeError:
            _web_dock = None
            _build_web_dock()

    load_url = last_url if last_url else home_url
    _web_dock.show()
    _web_dock.raise_()
    _web_dock._view.load(QUrl(load_url))


def on_web_question_shown(card) -> None:
    global _web_dock
    try:
        if card is None:
            return
        try:
            note  = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != WEB_NOTE_TYPE:
            if _web_dock is not None:
                try:
                    _web_dock.hide()
                except RuntimeError:
                    _web_dock = None
            return
        try:
            home_url = note["URL"]
        except (KeyError, TypeError):
            return
        if not home_url:
            return
        last_url = get_web_url(_ADDON_DIR, card.id)
        show_web_in_dock(card.id, home_url, last_url)
    except Exception as e:
        print(f"[Incremento] on_web_question_shown error: {e}")


def on_web_reviewer_will_end() -> None:
    if _web_dock is not None:
        try:
            _web_dock.hide()
        except RuntimeError:
            pass


def sync_web_note_type() -> None:
    try:
        ensure_web_note_type(mw.col)
    except Exception:
        pass


def add_web_function() -> None:
    """Incremento -> Add Content -> Web Page"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .add_web_dialog import AddWebDialog
    dlg = AddWebDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return
    url = dlg.url
    if not url:
        showInfo("Please enter a URL.")
        return
    title = dlg.title or url
    try:
        add_web_card(mw.col, url, title, dlg.deck_name)
        mw.col.reset()
        tooltip(f"Web card '{title}' added to {dlg.deck_name}.")
    except Exception as e:
        showInfo(f"Failed to add web card:\n{e}")
