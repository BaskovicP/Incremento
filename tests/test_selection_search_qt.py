"""Exercise the real popup offscreen, with network loading replaced at its boundary."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent, indent


def _run_popup_test(script):
    # WebEngine initializes asynchronously. Exercise and destroy the widgets
    # within QApplication's event loop, just as Anki does.
    setup = dedent('''
        import faulthandler
        faulthandler.enable()
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        from aqt.qt import QApplication, QTimer
        app = QApplication(['selection-search-test'])
        app.setQuitOnLastWindowClosed(False)
    ''')
    teardown = dedent('''
        errors = []
        def run():
            try:
                exercise()
            except BaseException as error:
                errors.append(error)
            finally:
                app.quit()
        QTimer.singleShot(0, run)
        app.exec()
        if errors:
            raise errors[0]
    ''')
    result = subprocess.run(
        [sys.executable, '-c', setup + '\ndef exercise():\n' + indent(dedent(script), '    ') + teardown],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QTWEBENGINE_DISABLE_SANDBOX': '1',
             'QTWEBENGINE_CHROMIUM_FLAGS': '--disable-gpu'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_popup_is_nonmodal_isolated_and_disposed_on_profile_close():
    script = dedent('''
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlsplit
        from unittest.mock import patch
        from aqt.qt import QCoreApplication, QEvent, QMenu, QPoint, QTextEdit, QUrl, Qt
        from PyQt6 import sip
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from frontend import selection_search as search
        from frontend.google_search_dialog import _SearchRequests

        loaded = []
        search._active_profile = lambda: 'Synthetic'

        # Writing's native menu keeps all of its editing actions, and installing
        # the adapter twice still opens just one menu for a right-click.
        editor = QTextEdit()
        editor.setPlainText('one\\ntwo')
        editor.selectAll()
        original = editor.createStandardContextMenu()
        native_labels = [action.text() for action in original.actions()]
        original.deleteLater()
        opened, menus = [], []
        def exec_menu(menu, position):
            menus.append(menu)
            assert [action.text() for action in menu.actions()][:len(native_labels)] == native_labels
            actions = [action for action in menu.actions() if action.objectName() == 'incremento_search_google']
            assert len(actions) == 1
            actions[0].trigger()
        with patch.object(QMenu, 'exec', exec_menu), patch.object(search, 'show_google_search',
                lambda text, parent=None: opened.append(text)):
            search.install_selection_search_menu(editor)
            search.install_selection_search_menu(editor)
            editor.customContextMenuRequested.emit(QPoint(5, 5))
        assert len(menus) == 1 and opened == ['one two']
        editor.deleteLater()

        with patch.object(QWebEngineView, 'load', lambda self, url: loaded.append(url.toString())):
            search.show_google_search('čaj & tea')
            popup = search._popup
            assert popup.isVisible() and not popup.isModal()
            assert popup.windowModality() == Qt.WindowModality.NonModal
            assert popup.width() == 760 and popup.height() == 560
            assert len(loaded) == 1
            assert parse_qs(urlsplit(loaded[0]).query) == {'q': ['čaj & tea']}
            assert popup._profile.isOffTheRecord()
            assert popup._page.webChannel() is None
            assert not popup._page.scripts().toList()
            settings = popup._page.settings()
            for name in ('LocalContentCanAccessFileUrls', 'LocalContentCanAccessRemoteUrls',
                         'JavascriptCanOpenWindows', 'JavascriptCanAccessClipboard'):
                assert not settings.testAttribute(getattr(QWebEngineSettings.WebAttribute, name))
            navigation = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
            for url in ('file:///tmp/private', 'javascript:alert(1)', 'data:text/html,hello',
                        'qrc:/secret', 'https://user:secret@example.test'):
                assert not popup._page.acceptNavigationRequest(QUrl(url), navigation, True), url
            assert popup._page.acceptNavigationRequest(QUrl('https://example.test'), navigation, True)
            assert popup._page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab) is popup._page
            assert popup._page.chooseFiles(None, [], []) == []
            popup._view.loadFinished.emit(False)
            assert popup._status.text()
            popup._view.loadFinished.emit(True)
            assert not popup._status.text()
            search.show_google_search('second search')
            assert search._popup is popup
            assert loaded[-1] == 'https://www.google.com/search?q=second+search'
            profile = popup._profile
            search.reset_for_profile_switch()
            assert search._popup is None
            for _ in range(3):
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
            assert sip.isdeleted(popup)
            assert sip.isdeleted(profile)

            # Esc closes normally and a later search builds a new browser.
            search.show_google_search('again')
            last = search._popup
            last.reject()
            assert search._popup is None
            for _ in range(3):
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
            assert sip.isdeleted(last)

        interceptor = _SearchRequests()
        for url, expected in [('file:///tmp/private', True), ('qrc:/secret', True),
                              ('https://example.test', False), ('data:image/png,abc', False)]:
            blocked = []
            interceptor.interceptRequest(SimpleNamespace(requestUrl=lambda: QUrl(url), block=blocked.append))
            assert bool(blocked) is expected, (url, blocked)
    ''')
    _run_popup_test(script)


def test_encoded_search_requests_and_result_links_remain_usable():
    # DuckDuckGo's results request encodes spaces as %20, unlike our initial
    # search URL's '+'. Qt's default display string decodes those spaces.
    script = dedent('''
        from types import SimpleNamespace
        from unittest.mock import patch
        from aqt.qt import QUrl
        from PyQt6.QtWebEngineCore import QWebEnginePage
        from frontend.google_search_dialog import GoogleSearchDialog

        popup = GoogleSearchDialog(anki_profile='Synthetic')
        navigation = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        allowed = (
            'https://links.duckduckgo.com/d.js?q=If%20a%20height%20is%20accurately%20recorded%20as',
            'https://www.google.com/search?q=tea%20%26%20coffee',
            'https://example.test/a%20b?q=%C4%8Daj%20%2B%20tea#part%20one',
        )
        try:
            for encoded in allowed:
                url = QUrl(encoded)
                blocked, loaded, opened = [], [], []
                popup._requests.interceptRequest(SimpleNamespace(requestUrl=lambda: url, block=blocked.append))
                assert not blocked, ('request blocked', encoded)
                assert popup._page.acceptNavigationRequest(url, navigation, True), encoded
                with patch.object(popup._view, 'load', loaded.append):
                    popup.search(encoded)
                assert loaded == [url], encoded
                with patch.object(popup._view, 'url', lambda: url), patch(
                        'frontend.google_search_dialog.open_companion_url', opened.append):
                    popup._open_browser()
                assert opened == [encoded], ('external URL changed', opened)

            for unsafe in ('file:///tmp/a%20b', 'qrc:/a%20b', 'javascript:alert(1)',
                           'https://user:secret@example.test/a%20b', 'https://',
                           'https://example.test:invalid/a', 'https://example.test/?q=' + '%C4%8D' * 1500):
                url = QUrl(unsafe)
                blocked, loaded, opened = [], [], []
                popup._requests.interceptRequest(SimpleNamespace(requestUrl=lambda: url, block=blocked.append))
                assert blocked == [True], unsafe
                assert not popup._page.acceptNavigationRequest(url, navigation, True), unsafe
                with patch.object(popup._view, 'load', loaded.append):
                    popup.search(unsafe)
                with patch.object(popup._view, 'url', lambda: url), patch(
                        'frontend.google_search_dialog.open_companion_url', opened.append):
                    popup._open_browser()
                assert loaded == opened == [], unsafe
        finally:
            popup.dispose()
    ''')
    _run_popup_test(script)
