"""Native context-menu and clipboard lifecycle, without a live reader/profile."""

from concurrent.futures import Future
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
from unittest.mock import MagicMock

import pytest

from frontend import pdf_image_copy as ui
from backend.pdf_embedded_images import PdfImageResult


def _request(monkeypatch, point=None):
    jobs, copied = [], []
    current = [True]
    menu, action = MagicMock(), MagicMock()
    menu.addAction.return_value = action
    monkeypatch.setattr(ui, "t", lambda key: key)
    monkeypatch.setattr(ui, "_set_image_clipboard", copied.append)
    ui.add_pdf_image_copy_action(
        menu, pdf_path="/tmp/selected.pdf",
        point={"page": 2, "x": .25, "y": .5} if point is None else point,
        is_current=lambda: current[0],
        run_in_background=lambda work, done: jobs.append((work, done)),
    )
    return action, jobs, copied, current


def _finish(jobs, result):
    future = Future()
    future.set_result(result)
    jobs[0][1](future)


def test_context_action_decodes_off_thread_and_copies_only_on_user_click(monkeypatch):
    extracted = []
    monkeypatch.setattr(ui, "extract_pdf_image_at_point", lambda path, **kw: (
        extracted.append((path, kw)) or PdfImageResult("ready", b"native PNG")))
    action, jobs, copied, _ = _request(monkeypatch)
    assert extracted == copied == []
    action.setEnabled.assert_called_with(False)
    result = jobs[0][0]()
    assert extracted == [("/tmp/selected.pdf", {"page_number": 2, "x_ratio": .25, "y_ratio": .5})]
    _finish(jobs, result)
    action.setEnabled.assert_called_with(True)
    assert copied == []
    action.triggered.connect.call_args.args[0]()
    assert copied == [b"native PNG"]


@pytest.mark.parametrize("stage", ["before_completion", "before_click"])
def test_closed_menu_or_changed_profile_document_cannot_replace_clipboard(monkeypatch, stage):
    action, jobs, copied, current = _request(monkeypatch)
    if stage == "before_completion":
        current[0] = False
    _finish(jobs, PdfImageResult("ready", b"image"))
    if stage == "before_click":
        current[0] = False
        action.triggered.connect.call_args.args[0]()
    else:
        action.triggered.connect.assert_not_called()
    assert copied == []


@pytest.mark.parametrize("status", ["not_found", "too_large", "unavailable", "failed"])
def test_missing_or_unsupported_image_keeps_clipboard_and_explains_disabled_action(monkeypatch, status):
    action, jobs, copied, _ = _request(monkeypatch)
    _finish(jobs, PdfImageResult(status))
    action.setEnabled.assert_called_with(False)
    action.setToolTip.assert_called_with("reader_pdf_image_" + status)
    assert copied == []


@pytest.mark.parametrize("point", [{}, {"page": 0, "x": .5, "y": .5},
    {"page": 1, "x": float("nan"), "y": .5}, {"page": 1, "x": -1, "y": .5},
    {"page": True, "x": .5, "y": .5}, {"page": 1, "x": "0.5", "y": .5},
    {"page": 1, "x": 10 ** 1000, "y": .5}])
def test_invalid_viewer_points_do_not_start_document_work(monkeypatch, point):
    _, jobs, copied, _ = _request(monkeypatch, point)
    assert jobs == copied == []


def test_worker_failure_preserves_clipboard_and_explains_disabled_action(monkeypatch):
    action, jobs, copied, _ = _request(monkeypatch)
    future = Future()
    future.set_exception(RuntimeError("decoder failure"))
    jobs[0][1](future)
    action.setEnabled.assert_called_with(False)
    action.setToolTip.assert_called_with("reader_pdf_image_failed")
    assert copied == []


@pytest.mark.parametrize("invalid", [False, True])
def test_native_clipboard_receives_only_a_valid_decoded_image(monkeypatch, invalid):
    image, clipboard = MagicMock(), MagicMock()
    image.isNull.return_value = invalid
    monkeypatch.setattr(ui.QImage, "fromData", lambda png, fmt: image)
    monkeypatch.setattr(ui.QApplication, "clipboard", lambda: clipboard)
    ui._set_image_clipboard(b"PNG")
    if invalid:
        clipboard.setImage.assert_not_called()
    else:
        clipboard.setImage.assert_called_once_with(image)


def test_real_qt_menu_enables_background_result_and_copies_native_image_offscreen():
    script = dedent('''
        from concurrent.futures import Future
        from aqt.qt import QApplication, QBuffer, QIODevice, QImage, QMenu, QPoint, QTimer
        from backend.pdf_embedded_images import PdfImageResult
        from frontend import pdf_image_copy as ui, reader_links

        app = QApplication(['embedded-image-test'])
        image = QImage(2, 1, QImage.Format.Format_ARGB32)
        image.fill(0x80402010)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, 'PNG')
        png = bytes(buffer.data())
        app.clipboard().setText('unchanged until click')
        ui.t = lambda key: key

        class View:
            def __init__(self):
                self.menu = QMenu()
                self.menu.addAction('Native Copy')
            def selectedText(self):
                return ''
            def createStandardContextMenu(self):
                return self.menu
            def mapToGlobal(self, point):
                return point

        view = View()
        def populate(menu, payload):
            def current():
                return getattr(view, '_incremento_reader_anchor_context_menu', None) is menu
            def background(work, done):
                def finish():
                    future = Future()
                    future.set_result(PdfImageResult('ready', png))
                    done(future)
                    action = menu.actions()[-1]
                    assert action.isEnabled()
                    assert app.clipboard().text() == 'unchanged until click'
                    action.trigger()
                    menu.close()
                QTimer.singleShot(0, finish)
            ui.add_pdf_image_copy_action(menu, pdf_path='/tmp/synthetic.pdf',
                point={'page': 1, 'x': .5, 'y': .5},
                is_current=current, run_in_background=background)
            assert not menu.actions()[-1].isEnabled()

        QTimer.singleShot(2000, view.menu.close)
        assert reader_links.show_reader_anchor_context_menu(view, QPoint(0, 0),
            resolver_script='synthetic()', run_javascript=lambda script, done: done({'page': 1}),
            on_copy=lambda payload: None, populate_menu=populate)
        assert view.menu.actions()[0].text() == 'Native Copy'
        copied = app.clipboard().image()
        assert (copied.width(), copied.height()) == (2, 1)
        assert copied.pixelColor(0, 0).alpha() == 128
        assert not hasattr(view, '_incremento_reader_anchor_context_menu')
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
