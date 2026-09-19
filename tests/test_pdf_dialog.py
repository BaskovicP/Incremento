import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


def _install_pdf_dialog_stubs() -> dict[str, object | None]:
    module_names = (
        "aqt",
        "aqt.qt",
        "PyQt6",
        "PyQt6.QtGui",
        "PyQt6.QtPdf",
        "incremento",
        "incremento.frontend",
        "incremento.frontend.tag_edit",
    )
    originals = {name: sys.modules.get(name) for name in module_names}
    aqt_mod = types.ModuleType("aqt")
    aqt_mod.mw = types.SimpleNamespace()
    sys.modules["aqt"] = aqt_mod

    qt_mod = types.ModuleType("aqt.qt")
    for name in (
        "QAbstractItemView",
        "QCheckBox",
        "QComboBox",
        "QDialog",
        "QDialogButtonBox",
        "QDoubleSpinBox",
        "QFileDialog",
        "QFormLayout",
        "QHBoxLayout",
        "QHeaderView",
        "QLabel",
        "QLineEdit",
        "QPixmap",
        "QProgressBar",
        "QPushButton",
        "QSize",
        "QSizePolicy",
        "QSplitter",
        "QTableWidget",
        "QTableWidgetItem",
        "QTimer",
        "QVBoxLayout",
        "QWidget",
        "QEvent",
        "QItemSelectionModel",
    ):
        setattr(qt_mod, name, type(name, (), {}))
    qt_mod.Qt = type(
        "Qt",
        (),
        {
            "AlignmentFlag": type("AlignmentFlag", (), {}),
            "Orientation": type("Orientation", (), {}),
        },
    )
    sys.modules["aqt.qt"] = qt_mod

    pyqt6_mod = types.ModuleType("PyQt6")
    sys.modules["PyQt6"] = pyqt6_mod

    qtgui_mod = types.ModuleType("PyQt6.QtGui")
    qtgui_mod.QColor = type("QColor", (), {})
    sys.modules["PyQt6.QtGui"] = qtgui_mod

    qtpdf_mod = types.ModuleType("PyQt6.QtPdf")
    qtpdf_mod.QPdfDocument = type("QPdfDocument", (), {})
    sys.modules["PyQt6.QtPdf"] = qtpdf_mod

    incremento_pkg = types.ModuleType("incremento")
    frontend_pkg = types.ModuleType("incremento.frontend")
    tag_edit_mod = types.ModuleType("incremento.frontend.tag_edit")
    tag_edit_mod.QuickTagEdit = type("QuickTagEdit", (), {})
    sys.modules["incremento"] = incremento_pkg
    sys.modules["incremento.frontend"] = frontend_pkg
    sys.modules["incremento.frontend.tag_edit"] = tag_edit_mod
    return originals


_original_modules = _install_pdf_dialog_stubs()
sys.modules.pop("pdf_dialog", None)
try:
    pdf_dialog = importlib.import_module("pdf_dialog")
finally:
    for _name, _original in _original_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def test_resolve_pdf_storage_abspath_uses_backend_resolver_when_available(tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    called = []

    def fake_resolver(stored_filename: str) -> str:
        called.append(stored_filename)
        return "/tmp/resolved.pdf"

    resolved = pdf_dialog._resolve_pdf_storage_abspath(
        "stored.pdf",
        pdf_dir=str(pdf_dir),
        storage_abspath_resolver=fake_resolver,
    )

    assert resolved == "/tmp/resolved.pdf"
    assert called == ["stored.pdf"]


def test_resolve_pdf_storage_abspath_falls_back_to_pdf_dir(tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    resolved = pdf_dialog._resolve_pdf_storage_abspath(
        "pdfs/stored.pdf",
        pdf_dir=str(pdf_dir),
    )

    assert resolved == str((pdf_dir / "stored.pdf").resolve())


def test_resolve_pdf_storage_abspath_rejects_path_traversal(tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    resolved = pdf_dialog._resolve_pdf_storage_abspath(
        "../../../etc/passwd",
        pdf_dir=str(pdf_dir),
    )

    assert resolved == ""


def test_folder_import_includes_pdf_and_djvu_case_insensitively(monkeypatch, tmp_path):
    for name in ("first.pdf", "second.DJVU", "third.djv", "skip.epub"):
        (tmp_path / name).write_bytes(b"test")
    (tmp_path / "directory.pdf").mkdir()
    monkeypatch.setattr(pdf_dialog.QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path), raising=False)
    dialog = types.SimpleNamespace(_last_dir=lambda: "", _start_folder_import=Mock())
    pdf_dialog.AddPdfDialog._add_folder(dialog)
    assert [Path(path).name for path in dialog._start_folder_import.call_args.args[0]] == ["first.pdf", "second.DJVU", "third.djv"]


def test_djvu_import_dispatches_to_background_conversion_without_synchronous_pdf_import():
    dialog = types.SimpleNamespace(_process_djvu_file=Mock())
    entries = [("book.DJVU", "Book", ["topic"], False, 25.0)]
    pdf_dialog.AddPdfDialog._process_files(dialog, entries, 0)
    dialog._process_djvu_file.assert_called_once_with(entries, 0)


class _FakeCheckBox:
    def __init__(self, checked: bool):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = checked


def test_bulk_ocr_choice_updates_every_possible_row_and_future_detection():
    first = _FakeCheckBox(False)
    second = _FakeCheckBox(False)
    dialog = types.SimpleNamespace(
        _ocr_checks={"first.pdf": first, "second.djvu": second},
        _ocr_bulk_choice=None,
    )

    pdf_dialog.AddPdfDialog._set_all_ocr_checks(dialog, True)

    assert first.isChecked() is True
    assert second.isChecked() is True
    assert pdf_dialog.AddPdfDialog._ocr_checked_by_default(dialog, False) is True

    pdf_dialog.AddPdfDialog._set_all_ocr_checks(dialog, False)

    assert first.isChecked() is False
    assert second.isChecked() is False
    assert pdf_dialog.AddPdfDialog._ocr_checked_by_default(dialog, True) is False


@pytest.mark.parametrize("switched", [False, True])
def test_prepared_djvu_is_cleaned_and_never_imported_after_dialog_close_or_profile_switch(monkeypatch, switched):
    prepared = types.SimpleNamespace(close=Mock())
    taskman = types.SimpleNamespace(run_in_background=Mock())
    collection = object()
    profile = {"name": "Original"}
    monkeypatch.setattr(pdf_dialog, "mw", types.SimpleNamespace(taskman=taskman, col=collection))
    monkeypatch.setattr(pdf_dialog, "_paths", types.SimpleNamespace(get_active_profile=lambda: profile["name"]))
    dialog = types.SimpleNamespace(
        _profile="Original", _collection=collection, _closed=False,
        _cancel_event=types.SimpleNamespace(is_set=lambda: False), _addon_dir="/tmp/test",
        _deck_combo=types.SimpleNamespace(currentText=lambda: "Topics"),
        _cancel_btn=Mock(),
        _djvu_compression=types.SimpleNamespace(choice_for=lambda path: "original"),
        _set_row_status=Mock(), _update_add_progress=Mock(), _show_error=Mock(),
    )
    dialog._request_current = lambda: pdf_dialog.AddPdfDialog._request_current(dialog)
    pdf_dialog.AddPdfDialog._process_djvu_file(dialog, [("book.djvu", "Book", [], False, 50)], 0)
    assert taskman.run_in_background.call_count == 1
    if switched:
        profile["name"] = "Other"
    else:
        dialog._closed = True
    assert not dialog._request_current()
    taskman.run_in_background.call_args.args[1](types.SimpleNamespace(result=lambda: prepared))
    prepared.close.assert_called_once()


def test_djvu_import_captures_selected_compression_before_background_work(monkeypatch):
    tasks = types.SimpleNamespace(run_in_background=Mock())
    monkeypatch.setattr(pdf_dialog, "mw", types.SimpleNamespace(taskman=tasks))
    monkeypatch.setattr(pdf_dialog, "_paths", types.SimpleNamespace(get_active_profile=lambda: "Test"))
    prepare = Mock()
    monkeypatch.setattr(pdf_dialog._djvu_manager, "prepare_djvu_pdf", prepare)
    choices = {"book.djvu": "black_white"}
    dialog = types.SimpleNamespace(
        _request_current=lambda: True, _profile="Test", _collection=object(),
        _cancel_event=types.SimpleNamespace(is_set=lambda: False), _addon_dir="/tmp/test",
        _deck_combo=types.SimpleNamespace(currentText=lambda: "Topics"), _cancel_btn=Mock(),
        _set_row_status=Mock(), _update_add_progress=Mock(),
        _djvu_compression=types.SimpleNamespace(choice_for=choices.get),
    )
    pdf_dialog.AddPdfDialog._process_djvu_file(dialog, [("book.djvu", "Book", [], False, 50)], 0)
    choices["book.djvu"] = "original"
    tasks.run_in_background.call_args.args[0]()
    assert prepare.call_args.kwargs["compression"] == "black_white"
    assert tasks.run_in_background.call_args.kwargs["uses_collection"] is False
