"""Reader controls behave in real Qt without loading a document or user profile."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize('scale', ['1', '1.5'], ids=['100-percent', '150-percent'])
def test_epub_compact_drawers_and_saved_choice_survive_reopening(tmp_path, scale):
    script = dedent('''
        import copy, sys, types
        from pathlib import Path
        root = Path.cwd()
        sys.path[:0] = [str(root/'frontend'), str(root/'backend')]
        sys.modules['session'] = types.SimpleNamespace(INCREMENTO_EPUB_REVIEW_DECK='Test', start_explicit_review=lambda *a, **k: None)
        from PyQt6.QtCore import QObject, QPoint, QUrl, pyqtSignal
        from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QToolButton, QCheckBox, QWidget
        import epub_dock as reader
        class Profile(QObject):
            def setUrlRequestInterceptor(self, value): pass
        class Page(QObject):
            def __init__(self, profile, dock, interceptor): super().__init__(dock)
            def settings(self): return types.SimpleNamespace(setAttribute=lambda *args: None)
        class View(QWidget):
            loadFinished = pyqtSignal(bool)
            urlChanged = pyqtSignal(QUrl)
            def setPage(self, page): self._page = page
        app = QApplication(['reader-controls-test'])
        main = QMainWindow()
        main.setCentralWidget(QLabel('Synthetic study area'))
        main.resize(1000, 900)
        config, writes = {}, []
        reader.load_addon_config = lambda *args: copy.deepcopy(config)
        def save(*args):
            config.clear(); config.update(copy.deepcopy(args[-1])); writes.append(copy.deepcopy(config))
        reader.save_addon_config = save
        main.addonManager = types.SimpleNamespace()
        reader._active_profile = lambda: 'A'
        reader._ADDON_DIR = sys.argv[1]
        reader.mw = main
        reader.QWebEngineProfile, reader._EpubRequestInterceptor = Profile, QObject
        reader._EpubDockPage, reader.QWebEngineView = Page, View
        reader._build_epub_dock()
        dock = reader._epub_dock
        main.show(); dock.show(); app.processEvents()
        assert dock._controls_collapsed, 'New readers start with essential controls'
        for name in ('_compact_read_btn', '_compact_extract_btn', '_compact_bookmark_btn', '_compact_review_btn', '_compact_search_btn'):
            assert getattr(dock, name).isVisible(), name
        assert dock._compact_review_btn.text() == 'Review All'
        assert dock._compact_bookmark_btn.text() == '☆ Bookmark'
        dock.setFloating(True)
        for width in (900, 350):
            dock.resize(width, 700)
            for panel in (None, 'annotation', 'review', 'more'):
                if panel:
                    dock._compact_drawer_buttons[panel].click()
                for _ in range(20):
                    app.processEvents()
                assert dock.width() == width
                scroll = dock._controls_scroll
                assert scroll.height() <= 360
                assert not scroll.horizontalScrollBar().isVisible()
                for control in dock._controls_host.findChildren(QToolButton) + dock._controls_host.findChildren(QCheckBox):
                    if not control.isVisible():
                        continue
                    point = control.mapTo(dock._controls_host, QPoint(0, 0))
                    assert point.x() >= 0 and point.x() + control.width() <= scroll.viewport().width(), control.text()
                    scroll.ensureWidgetVisible(control)
                    app.processEvents()
                    center = control.mapTo(scroll.viewport(), control.rect().center())
                    assert scroll.viewport().rect().contains(center), control.text()
                if panel:
                    dock._compact_drawer_buttons[panel].click()
        dock._all_review_btn.setEnabled(False)
        dock._read_to_here_btn.setChecked(True)
        reader._sync_epub_compact_action_states()
        assert not dock._compact_review_btn.isEnabled()
        assert dock._compact_read_btn.isChecked()
        dock._all_review_btn.setEnabled(True)
        reader._sync_epub_compact_action_states()
        clicked = []
        dock._all_review_btn.clicked.connect(lambda: clicked.append('review'))
        dock._compact_review_btn.click()
        assert clicked == ['review'], 'Compact actions dispatch the existing action exactly once'
        dock._compact_annotate_btn.click(); app.processEvents()
        assert dock._control_groups['annotation'].isVisible()
        assert not dock._control_groups['review'].isVisible()
        dock._compact_annotate_btn.click(); app.processEvents()
        assert dock._controls_expanded.isHidden()
        dock._compact_more_btn.click(); app.processEvents()
        assert dock._compact_options.isVisible()
        assert all(dock._compact_appearance_combo.itemText(i) != 'Translation unavailable' for i in range(3))
        dock._compact_search_btn.click(); app.processEvents()
        assert dock._find_bar.isVisible()
        assert writes == [], 'Transient drawers and Find must not save a new control view'
        dock._show_controls_btn.click(); app.processEvents()
        assert dock._controls_expanded.isVisible() and dock._controls_compact.isHidden()
        dock.resize(1663, 900)
        for _ in range(20):
            app.processEvents()
        groups = list(dock._control_groups.values())
        boxes = [group.rect().translated(group.mapTo(dock._controls_host, QPoint(0, 0))) for group in groups]
        assert all(box.x() == boxes[0].x() and box.width() == boxes[0].width() for box in boxes)
        assert all(a.bottom() < b.top() for a, b in zip(boxes, boxes[1:])), 'Expanded sections remain in four aligned rows'
        assert boxes[0].width() >= dock._controls_scroll.viewport().width() - 20, 'Sections use the available width'
        assert dock._controls_scroll.verticalScrollBar().maximum() == 0, 'All controls fit in a wide reader'
        assert config['epub_controls_collapsed_by_profile']['A']['main'] is False
        dock.close(); reader._epub_dock = None
        reader._build_epub_dock()
        dock = reader._epub_dock
        dock.show(); app.processEvents()
        assert not dock._controls_collapsed, 'Explicit expanded choice survives reopening'
        assert len(writes) == 1, 'Restoring must not write back'
        dock._minimize_controls_btn.click()
        assert config['epub_controls_collapsed_by_profile']['A']['main'] is True
        reader._active_profile = lambda: 'B'
        dock._show_controls_btn.click()
        assert len(writes) == 2, 'Retired-profile controls cannot save into another profile'
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_SCALE_FACTOR': scale},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
