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

import json
import os

from aqt import mw
from aqt.utils import showInfo, tooltip
from aqt.qt import (QCheckBox, QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                    QPushButton, QLabel, Qt, qconnect)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtGui import QDesktopServices

try:
    from ..backend.web_manager import (WEB_NOTE_TYPE, get_web_url, set_web_url,
                                       ensure_web_note_type, add_web_card,
                                       build_external_web_url)
except ImportError:
    from web_manager import (WEB_NOTE_TYPE, get_web_url, set_web_url,
                              ensure_web_note_type, add_web_card,
                              build_external_web_url)

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_web_dock             = None
_current_web_card_id  = None
_current_web_home_url = None  # original URL from the card's URL field
_web_profile          = None  # module-level singleton
_PYCMD_BRIDGE = "__incremento_webdock_pycmd__:"
_MSG_SELECTION_STATE = "incremento_selection_state:"
_track_web_window_with_extension = False


class _WebDockPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        if not message.startswith(_PYCMD_BRIDGE):
            return
        msg = message[len(_PYCMD_BRIDGE):]
        if not msg.startswith(_MSG_SELECTION_STATE):
            return
        try:
            data = json.loads(msg[len(_MSG_SELECTION_STATE):])
            from . import add_card_dock as _add_card_dock_mod

            _add_card_dock_mod.update_selection_state(
                "web",
                has_text=bool(data.get("hasText")),
            )
        except Exception:
            pass


def _build_web_dock():
    global _web_dock, _web_profile

    from PyQt6.QtWebEngineCore import (QWebEngineSettings as _WES,
                                       QWebEngineProfile as _WEProf)

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

    _page = _WebDockPage(_web_profile)
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
    url_lbl.setMaximumWidth(360)
    ctrl_layout.addWidget(url_lbl, 1)

    home_btn = QPushButton("⌂ Home")
    home_btn.setFixedWidth(70)
    ctrl_layout.addWidget(home_btn)

    track_cb = QCheckBox("Track via Chrome extension")
    track_cb.setChecked(bool(_track_web_window_with_extension))
    track_cb.setToolTip(
        "When checked, opening this page externally lets the Incremento Companion "
        "extension keep the web card synced to the latest page visited in that tab."
    )
    ctrl_layout.addWidget(track_cb)

    window_btn = QPushButton("Open in Window")
    ctrl_layout.addWidget(window_btn)

    vbox.addWidget(ctrl)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._view    = view
    dock._url_lbl = url_lbl
    dock._track_cb = track_cb

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
        try:
            view.page().runJavaScript(
                f"window.pycmd = function(msg) {{"
                f"  console.log('{_PYCMD_BRIDGE}' + msg);"
                f"}};"
                "(function() {"
                "  if (window._incrementoSelectionBridgeInstalled) { return; }"
                "  window._incrementoSelectionBridgeInstalled = true;"
                "  document.addEventListener('selectionchange', function() {"
                "    var sel = window.getSelection ? window.getSelection() : null;"
                "    var text = sel ? sel.toString().trim() : '';"
                "    if (!text) { return; }"
                "    window._incrementoLastSelection = text;"
                "    window.pycmd('incremento_selection_state:' + JSON.stringify({source: 'web', hasText: true}));"
                "  });"
                "})();"
            )
        except Exception:
            pass

    view.urlChanged.connect(_on_url_changed)
    view.loadFinished.connect(_on_load_finished)
    qconnect(home_btn.clicked, _web_go_home)
    qconnect(window_btn.clicked, _open_web_in_window)
    qconnect(track_cb.toggled, _on_track_web_window_toggled)

    _web_dock = dock
    return dock


def _on_track_web_window_toggled(checked: bool) -> None:
    global _track_web_window_with_extension
    _track_web_window_with_extension = bool(checked)


def _current_web_display_url() -> str:
    if _web_dock is not None:
        try:
            current = (_web_dock._view.url().toString() or "").strip()
            if current and current != "about:blank":
                return current
        except Exception:
            pass
    return str(_current_web_home_url or "").strip()


def _open_web_in_window() -> None:
    if _current_web_card_id is None:
        tooltip("Incremento: no web card is currently open.")
        return

    current_url = _current_web_display_url()
    if not current_url:
        tooltip("Incremento: this web card has no valid URL.")
        return

    track_enabled = False
    if _web_dock is not None:
        try:
            track_enabled = bool(_web_dock._track_cb.isChecked())
        except Exception:
            track_enabled = False

    open_url = build_external_web_url(
        current_url,
        card_id=int(_current_web_card_id),
        track_with_extension=track_enabled,
    )
    try:
        set_web_url(_ADDON_DIR, _current_web_card_id, current_url)
    except Exception:
        pass

    try:
        ok = bool(QDesktopServices.openUrl(QUrl(open_url)))
    except Exception:
        ok = False
    if not ok:
        tooltip("Incremento: failed to open system browser.")
        return

    if track_enabled:
        tooltip(
            "Incremento: browser tracking enabled for this web card tab "
            "(requires the Incremento Companion extension)."
        )


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


def sync_external_web_url(card_id: int, url: str) -> bool:
    """If this web card is currently open, load the latest externally synced URL."""
    global _web_dock

    try:
        target_card_id = int(card_id)
    except Exception:
        return False
    target_url = str(url or "").strip()
    if target_card_id <= 0 or not target_url:
        return False
    if _current_web_card_id != target_card_id:
        return False
    if _web_dock is None:
        return False

    try:
        current_url = (_web_dock._view.url().toString() or "").strip()
    except Exception:
        current_url = ""
    if current_url == target_url:
        return False

    try:
        _web_dock._view.load(QUrl(target_url))
        return True
    except Exception:
        return False


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
        add_web_card(mw.col, url, title, dlg.deck_name, tags=dlg.tags)
        mw.col.reset()
        tooltip(f"Web card '{title}' added to {dlg.deck_name}.")
    except Exception as e:
        showInfo(f"Failed to add web card:\n{e}")


def get_selected_text(callback) -> None:
    if _web_dock is None:
        callback("")
        return
    try:
        _web_dock._view.page().runJavaScript(
            "(function(){ return (window._incrementoLastSelection || "
            "(window.getSelection && window.getSelection().toString()) || '').trim(); })();",
            lambda text: callback(text or ""),
        )
    except Exception:
        callback("")
