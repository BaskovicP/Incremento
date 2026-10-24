"""Exercise focus layout with real, offscreen Qt and synthetic review controls."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("floating", [False, True])
@pytest.mark.parametrize("reviewing", [False, True], ids=['decks', 'review'])
def test_pdf_focus_toggle_preserves_review_controls_and_restores_card_layout(floating, reviewing):
    script = dedent('''
        import ast, sys, types
        from pathlib import Path
        from PyQt6 import QtCore, QtWidgets
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtWidgets):
            for name in dir(module):
                setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.pdf_focus_mode import PdfFocusMode

        app = QApplication(['pdf-focus-test'])
        main = QMainWindow()
        main.state = 'review' if REVIEWING else 'deckBrowser'
        main.resize(1200, 800)
        main.setCentralWidget(QWidget())
        main.mainLayout = QVBoxLayout(main.centralWidget())
        main.mainLayout.setContentsMargins(0, 0, 0, 0)
        main.mainLayout.addWidget(QLabel('Top toolbar'))
        main.web = QLabel('Synthetic flashcard' if REVIEWING else 'Deck list')
        main.web.setMinimumWidth(400)
        main.mainLayout.addWidget(main.web, 1)
        main.bottomWeb = QPushButton('Show Answer / Good')
        main.bottomWeb.setVisible(REVIEWING)
        main.mainLayout.addWidget(main.bottomWeb)
        answered = []
        main.bottomWeb.clicked.connect(lambda: answered.append(True))
        dock = QDockWidget('PDF', main)
        dock.setObjectName('pdf')
        view = QLabel('Synthetic document')
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        mode = PdfFocusMode(main, dock, view)
        dock._pdf_focus_mode = mode
        assert dock.widget() is view, 'The PDF must have no extra title/button row above it'
        dock.setFloating(FLOATING)
        main.show()
        dock.show()
        app.processEvents()
        initial_area = main.dockWidgetArea(dock)
        hidden_events = []
        dock.visibilityChanged.connect(hidden_events.append)

        # Exercise the actual reader-opening adapter too: the Decks regression
        # was its review-only gate, not the Qt layout itself.
        function = next(n for n in ast.parse(Path('frontend/pdf_dock.py').read_text()).body
                        if isinstance(n, ast.FunctionDef) and n.name == '_present_pdf_reader')
        namespace = {'mw': main, '_pdf_dock': dock, 'PDF_NOTE_TYPE': 'PDF',
                     'configured_pdf_focus_mode': lambda: False,
                     'pdf_display_label_from_filename': lambda filename, **kw: filename}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'frontend/pdf_dock.py', 'exec'), namespace)
        namespace['_present_pdf_reader'](55, {'Title': 'Research <paper>'}, 'synthetic.pdf')
        assert mode.available, 'Focus must be usable on Decks as well as during review'
        assert not mode.active
        mode.request_enabled(not mode.enabled)
        app.processEvents()
        assert mode.active and mode.is_visible()
        assert main.web.isHidden()
        assert main.bottomWeb.isVisible() == REVIEWING
        assert view.isVisible()
        assert dock.windowTitle() == 'Research <paper>'
        assert view.width() >= main.width() - 10, 'The PDF must take the full window width, with no left card column'
        if REVIEWING:
            assert view.mapTo(main, view.rect().bottomLeft()).y() < main.bottomWeb.mapTo(main, main.bottomWeb.rect().topLeft()).y()
        assert hidden_events == [], 'Moving the live reader must not signal a closed PDF'
        main.bottomWeb.click()
        assert answered == [True]

        # Repeated PDF questions/reloads must not duplicate the embedded viewer.
        mode.present(eligible=True, title='Next PDF')
        mode.present(eligible=True, title='Next PDF')
        assert main.mainLayout.count() == 4
        mode.request_enabled(not mode.enabled)
        app.processEvents()
        assert not mode.active and main.web.isVisible()
        assert dock.isVisible() and dock.isFloating() == FLOATING
        assert main.dockWidgetArea(dock) == initial_area
        assert dock.widget() is view
        assert main.mainLayout.count() == 3

        mode.request_enabled(not mode.enabled)
        # A regular flashcard, ending review, or closing the reader restores it.
        mode.stop()
        dock.hide()
        app.processEvents()
        assert main.web.isVisible() and main.bottomWeb.isVisible() == REVIEWING
        assert not mode.active and not mode.is_visible()
        assert mode.enabled, 'Remember focus for the next PDF'
        mode.present(eligible=False, title='Reader unavailable')
        app.processEvents()
        assert main.web.isVisible() and not mode.active
        assert not mode.available
        mode.present(eligible=True, title='Return to PDF')
        assert mode.active
        # Profile changes retire the embedded widget; the saved setting remains separate.
        mode.stop(reset=True)
        dock.hide()
        assert main.web.isVisible() and not mode.enabled
        assert main.mainLayout.count() == 3
        main.close()
    ''').replace('FLOATING', repr(floating)).replace('REVIEWING', repr(reviewing))
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_saved_focus_button_restores_after_recreation_and_failed_save_keeps_layout():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtWidgets
        from PyQt6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.pdf_focus_mode import PdfFocusMode
        app = QApplication(['saved-pdf-focus-test'])
        saved = [False]
        states = []
        def save(enabled):
            saved[0] = enabled
            return True
        main = QMainWindow()
        main.setCentralWidget(QWidget())
        layout = QVBoxLayout(main.centralWidget())
        main.web = QLabel('Card')
        main.bottomWeb = QLabel('Answers')
        layout.addWidget(main.web)
        layout.addWidget(main.bottomWeb)
        def create():
            dock = QDockWidget('PDF', main)
            main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            mode = PdfFocusMode(main, dock, QLabel('PDF'), enabled=saved[0], save_preference=save)
            mode.state_changed = lambda: states.append((mode.enabled, mode.available))
            return mode
        mode = create()
        main.show()
        mode.present(eligible=True, title='PDF')
        mode.request_enabled(not mode.enabled)
        assert saved == [True] and mode.active
        assert states[-1] == (True, True)
        mode.stop(reset=True)
        mode.dock.hide()
        assert saved == [True], 'Closing a profile must not clear the saved choice'
        restored = create()
        restored.present(eligible=True, title='PDF')
        assert restored.enabled and restored.active and main.web.isHidden()
        restored.save_preference = lambda enabled: False
        restored.request_enabled(not restored.enabled)
        assert restored.active and restored.enabled and main.web.isHidden()
        assert states[-1] == (True, True)
        restored.save_preference = save
        restored.request_enabled(not restored.enabled)
        assert saved == [False] and not restored.active and main.web.isVisible()
        restored.stop(reset=True)
        restored.dock.hide()
        restored = create()
        restored.present(eligible=True, title='PDF')
        assert not restored.enabled and not restored.active and main.web.isVisible()
        # Settings changes update the same button without writing it a second time.
        restored.set_enabled(True)
        assert restored.active and saved == [False]
        assert states[-1] == (True, True)
        restored.stop()
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pdf_focus_keeps_the_live_webengine_document_and_selection():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtWidgets
        from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
        from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QPushButton, QVBoxLayout, QWidget
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        # Match Anki's software renderer; offscreen macOS has no GPU surface.
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtWidgets):
            for name in dir(module):
                setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.pdf_focus_mode import PdfFocusMode
        app = QApplication(['pdf-focus-webengine-test'])
        main = QMainWindow()
        main.resize(1000, 700)
        main.setCentralWidget(QWidget())
        layout = QVBoxLayout(main.centralWidget())
        main.web = QWidget()
        main.bottomWeb = QPushButton('Answer')
        layout.addWidget(main.web, 1)
        layout.addWidget(main.bottomWeb)
        dock = QDockWidget('PDF', main)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        profile = QWebEngineProfile(view)
        view.setPage(QWebEnginePage(profile, view))
        mode = PdfFocusMode(main, dock, view)
        # Geometry/visibility is covered above with real rendered Qt widgets.
        # Keep this browser host unshown. Use Qt's minimal platform below:
        # macOS's offscreen compositor can crash during the initial page load,
        # before any focus change. Disable rendering for this DOM-only test;
        # the real page still exercises reparenting and selection preservation.
        mode.present(eligible=True, title='Synthetic document')
        loop = QEventLoop()
        loads = []
        view.loadFinished.connect(lambda ok: (loads.append(ok), loop.quit()))
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(8000)
        view.setHtml('<p id="excerpt">Selected PDF text</p>')
        loop.exec()
        assert loads == [True]
        timeout.stop()
        page = view.page()
        def js(code):
            values = []
            pending = QEventLoop()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(pending.quit)
            timer.start(5000)
            page.runJavaScript(code, lambda value: (values.append(value), pending.quit()))
            pending.exec()
            assert values, 'WebEngine did not respond'
            return values[0]
        js('window.readerToken = "preserved"; const r=document.createRange();'
           'r.selectNodeContents(document.getElementById("excerpt"));'
           'getSelection().removeAllRanges(); getSelection().addRange(r);')
        for _ in range(2):
            mode.request_enabled(not mode.enabled)
            app.processEvents()
            assert view.page() is page
            assert js('[window.readerToken, getSelection().toString()]') == ['preserved', 'Selected PDF text']
            assert loads == [True], 'Changing focus must not reload the PDF page'
        main.close()
        # Retire Chromium in dependency order, before interpreter shutdown.
        # The profile owns browser storage and must outlive its page.
        page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        profile.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        main.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'minimal', 'QTWEBENGINE_DISABLE_SANDBOX': '1',
             'QTWEBENGINE_CHROMIUM_FLAGS': '--disable-gpu --disable-gpu-compositing --disable-software-rasterizer --use-gl=disabled'},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_switching_pdf_and_epub_focus_restores_only_the_active_reader():
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtWidgets
        from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QDockWidget
        from PyQt6.QtCore import Qt
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtWidgets):
            for name in dir(module):
                setattr(qt, name, getattr(module, name))
        sys.modules['aqt'] = types.ModuleType('aqt')
        sys.modules['aqt.qt'] = qt
        from frontend.pdf_focus_mode import PdfFocusMode
        app = QApplication([])
        main = QMainWindow()
        host = QWidget()
        main.setCentralWidget(host)
        layout = QVBoxLayout(host)
        main.web, main.bottomWeb = QLabel('Card'), QLabel('Answers')
        layout.addWidget(main.web)
        layout.addWidget(main.bottomWeb)
        modes = []
        for label in ('PDF', 'EPUB'):
            dock = QDockWidget(label, main)
            main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            modes.append(PdfFocusMode(main, dock, QLabel(label), enabled=True))
        main.show()
        modes[0].present(eligible=True, title='PDF')
        modes[1].present(eligible=True, title='EPUB')
        assert not modes[0].active and modes[1].active
        assert main.web.isHidden() and not main.bottomWeb.isHidden()
        assert layout.count() == 3
        modes[0].stop()  # A later old-reader hook must not uncover the card.
        assert main.web.isHidden()
        modes[1].stop()
        assert not main.web.isHidden() and layout.count() == 2
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
