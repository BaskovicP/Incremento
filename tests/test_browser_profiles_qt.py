"""Real browser storage across processes; never touches live Anki profiles."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def run_browser(script, *args):
    setup = "import faulthandler; faulthandler.enable()\nfrom PyQt6.QtQuick import QQuickWindow, QSGRendererInterface\nQQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)\n"
    result = subprocess.run(
        [sys.executable, "-c", setup + dedent(script), *map(str, args)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_DISABLE_SANDBOX": "1",
             "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu"},
        capture_output=True, text=True, timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Release of profile requested but WebEnginePage still not deleted" not in result.stderr


@pytest.mark.parametrize("search", [False, True], ids=["web-reader", "search-popup"])
def test_browser_session_cookies_and_local_storage_survive_restart_and_stay_isolated(tmp_path, search):
    script = r'''
        import sys
        from aqt.qt import QApplication, QTimer, QUrl
        from PyQt6.QtCore import QEventLoop, QObject
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from frontend.browser_profiles import create_browser_profile, destroy_browser
        app = QApplication(['browser-storage-test'])
        def exercise():
            root, mode, person, purpose = sys.argv[1:]
            def await_result(start):
                loop = QEventLoop()
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                results = []
                def done(value):
                    results.append(value)
                    loop.quit()
                start(done)
                timer.start(10000)
                if not results:
                    loop.exec()
                timer.stop()
                assert results, 'Browser operation timed out'
                return results[0]
            # Anki has initialized its own browser before an add-on opens a profile.
            main_profile = QWebEngineProfile()
            main_owner = QObject()
            main_page = QWebEnginePage(main_profile, main_owner)
            def initialize(done):
                main_page.loadFinished.connect(done)
                main_page.setHtml('<html><body>Main browser fixture</body></html>')
            assert await_result(initialize)
            profile = create_browser_profile(root, person, search=purpose == 'True')
            assert not profile.isOffTheRecord()
            # Storage needs a real page but no painted view/compositor. Widget
            # ownership is covered separately by the reader and popup lifecycle tests.
            owner = QObject()
            page = QWebEnginePage(profile, owner)
            events = []
            page.destroyed.connect(lambda: events.append('page'))
            profile.destroyed.connect(lambda: events.append('profile'))
            def load(done):
                page.loadFinished.connect(done)
                page.setHtml('<html><body>Storage fixture</body></html>', QUrl('https://login.example.test/'))
            assert await_result(load)
            if mode == 'write':
                js = "document.cookie='session=remembered; path=/'; document.cookie='durable=kept; max-age=86400; path=/'; localStorage.setItem('login', 'saved'); true"
                assert await_result(lambda done: page.runJavaScript(js, done)) is True
            result = await_result(lambda done: page.runJavaScript("[document.cookie, localStorage.getItem('login')]", done))
            if mode == 'empty':
                assert result == ['', None], result
            else:
                assert set(result[0].split('; ')) == {'session=remembered', 'durable=kept'}, result
                assert result[1] == 'saved', result
            destroy_browser(owner, profile)
            assert events == ['page', 'profile'], events
            destroy_browser(owner, profile)
            destroy_browser(main_owner, main_profile)
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
    '''
    run_browser(script, tmp_path, "write", "First", search)
    run_browser(script, tmp_path, "read", "First", search)
    run_browser(script, tmp_path, "empty", "Second", search)
    run_browser(script, tmp_path, "empty", "First", not search)


def test_web_reader_profile_reset_destroys_owned_page_before_profile(tmp_path):
    run_browser(r'''
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path.cwd() / 'backend'))
        from aqt.qt import QApplication, QDockWidget
        from PyQt6 import sip
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from frontend import web_dock
        app = QApplication(['web-reader-close-test'])
        profile = QWebEngineProfile()
        dock = QDockWidget()
        view = QWebEngineView(dock)
        dock.setWidget(view)
        dock._view = view
        runtime = web_dock._WebDockRuntime(dock=dock, profile=profile, current_card_id=1)
        page = web_dock._WebDockPage(runtime)
        view.setPage(page)
        events = []
        page.destroyed.connect(lambda: events.append('page'))
        profile.destroyed.connect(lambda: events.append('profile'))
        web_dock._runtime = runtime
        web_dock.reset_for_profile_switch()
        assert events == ['page', 'profile'], events
        assert sip.isdeleted(dock)
        assert runtime.dock is None and runtime.profile is None and runtime.current_card_id is None
        web_dock.reset_for_profile_switch()
    ''', tmp_path)


def test_search_preferences_apply_to_navigation_and_profile_lifecycle(tmp_path):
    run_browser(r'''
        import sys
        from aqt.qt import QApplication, QCoreApplication, QEvent, QWidget
        from PyQt6 import sip
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from unittest.mock import patch
        from frontend import selection_search as search
        app = QApplication(['search-preferences-test'])
        search._ADDON_DIR = sys.argv[1]
        person = ['First']
        search._active_profile = lambda: person[0]
        search.configure_search({'web_search_engine': 'duckduckgo', 'search_remember_logins': True})
        loaded = []
        with patch.object(QWebEngineView, 'load', lambda self, url: loaded.append(url.toString())):
            search.show_google_search('tea & coffee')
            popup = search._popup
            profile = popup._profile
            assert loaded == ['https://duckduckgo.com/?q=tea+%26+coffee']
            assert not profile.isOffTheRecord()
            first_path = profile.persistentStoragePath()
            assert popup._page.webChannel() is None
            popup.close()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert not popup.isVisible() and not sip.isdeleted(profile)
            search.show_google_search('again')
            assert search._popup is popup and popup.isVisible()
            # Disabling persistence takes effect now and cannot reuse saved state.
            search.configure_search({'web_search_engine': 'google', 'search_remember_logins': False})
            assert sip.isdeleted(profile) and sip.isdeleted(popup)
            assert search._popup is None
            search.show_google_search('private')
            private = search._popup
            assert private._profile.isOffTheRecord()
            assert loaded[-1] == 'https://www.google.com/search?q=private'
            search.configure_search({'search_remember_logins': True})
            assert sip.isdeleted(private)
            search.show_google_search('remembered')
            old = search._popup
            assert old._profile.persistentStoragePath() == first_path
            person[0] = 'Second'
            search.show_google_search('other profile')
            assert sip.isdeleted(old)
            assert search._popup._profile.persistentStoragePath() != first_path
            search.reset_for_profile_switch()
            assert search._popup is None
            editor = QWidget()
            search.show_google_search('from editor', parent=editor)
            popup = search._popup
            profile = popup._profile
            events = []
            popup._page.destroyed.connect(lambda: events.append('page'))
            profile.destroyed.connect(lambda: events.append('profile'))
            sip.delete(editor)
            assert events == ['page', 'profile'], events
            assert search._popup is None
            assert sip.isdeleted(profile)
    ''', tmp_path)
