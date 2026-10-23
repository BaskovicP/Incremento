"""Real Qt docking geometry, with the PDF engine replaced at its boundary."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("floating_primary", [False, True])
def test_native_pdf_panes_are_visible_and_horizontal_after_pin(floating_primary):
    script = dedent('''
        import importlib.util, sys, types
        from pathlib import Path
        from PyQt6.QtCore import QObject, QSignalBlocker, Qt, QUrl
        from PyQt6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QWidget
        app = QApplication(['incremento-reference-layout-test'])
        main = QMainWindow()
        main.resize(1400, 800)
        main.setCentralWidget(QLabel('Synthetic study area'))
        qt = types.ModuleType('aqt.qt')
        qt.QApplication, qt.QDockWidget, qt.Qt, qt.QUrl = QApplication, QDockWidget, Qt, QUrl
        qt.QSignalBlocker = QSignalBlocker
        aqt = types.ModuleType('aqt')
        aqt.mw = main
        for name, module in {
            'aqt': aqt, 'aqt.qt': qt,
            'aqt.operations': types.SimpleNamespace(QueryOp=object),
            'aqt.utils': types.SimpleNamespace(tooltip=lambda text: None),
            'PyQt6.QtWebEngineCore': types.SimpleNamespace(QWebEnginePage=QObject,
                QWebEngineProfile=object, QWebEngineSettings=object),
            'PyQt6.QtWebEngineWidgets': types.SimpleNamespace(QWebEngineView=QWidget),
            'backend.pdf_manager': types.SimpleNamespace(get_pdf_daily_limit_status=lambda *a, **kw: {}),
        }.items():
            sys.modules[name] = module
        spec = importlib.util.spec_from_file_location('_reference_layout', 'frontend/pdf_reference_workspace.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        primary = QDockWidget('Primary PDF', main)
        primary.setObjectName('incremento_pdf_dock')
        primary.setWidget(QLabel('PDF A'))
        primary.setMinimumWidth(400)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, primary)
        reference = module.ReferenceWindow.__new__(module.ReferenceWindow)
        QDockWidget.__init__(reference, 'Reference PDF', main)
        reference.state = module.PdfReaderState('Test', 8, 'synthetic.pdf', page=3)
        reference.owner = primary
        reference.view = QLabel('PDF B')
        reference.view.stop = lambda: None
        reference.page = QObject(reference)
        reference.setWidget(reference.view)
        reference.setMinimumWidth(280)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, reference)
        reference.setFloating(True)
        module._windows.append(reference)
        main.show()
        primary.show()
        reference.show()
        app.processEvents()
    ''') + f'primary.setFloating({floating_primary!r})\n' + dedent('''
        app.processEvents()
        visibility = []
        primary.visibilityChanged.connect(visibility.append)
        reference.pin()
        app.processEvents()
        main.layout().activate()
        left, right = primary.geometry(), reference.geometry()
        assert primary.isVisible() and reference.isVisible()
        assert not primary.isFloating() and not reference.isFloating()
        assert right.x() >= left.x() + left.width(), (left.getRect(), right.getRect())
        assert abs(right.y() - left.y()) <= 2, (left.getRect(), right.getRect())
        assert False not in visibility, 'Layout changes must not stop primary reading-time tracking'
        module.reset_for_profile_switch()
        main.close()
        app.processEvents()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_link_target_page_bounds_use_real_pdf_metadata_in_a_worker():
    script = dedent('''
        import importlib.util, sys, tempfile, types
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        import pymupdf
        from PyQt6.QtWidgets import QApplication
        app = QApplication(['incremento-page-count-test'])
        for name, module in {
            'aqt': types.SimpleNamespace(mw=None),
            'aqt.operations': types.SimpleNamespace(QueryOp=object),
            'aqt.utils': types.SimpleNamespace(tooltip=lambda text: None),
            'backend.pdf_manager': types.SimpleNamespace(get_pdf_daily_limit_status=lambda *a, **kw: {}),
        }.items():
            sys.modules[name] = module
        spec = importlib.util.spec_from_file_location('_page_count', 'frontend/pdf_page_links.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder, ThreadPoolExecutor(max_workers=1) as worker:
            path = Path(folder) / 'synthetic.pdf'
            document = pymupdf.open()
            for _ in range(3):
                document.new_page()
            document.save(path)
            document.close()
            assert worker.submit(module.pdf_page_count, str(path)).result(timeout=5) == 3
            broken = Path(folder) / 'broken.pdf'
            broken.write_bytes(b'not a PDF')
            try:
                worker.submit(module.pdf_page_count, str(broken)).result(timeout=5)
            except ValueError:
                pass
            else:
                raise AssertionError('An unreadable PDF must not offer invented target pages')
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
