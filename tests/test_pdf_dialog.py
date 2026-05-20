import importlib
import sys
import types


def _install_pdf_dialog_stubs() -> None:
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


_install_pdf_dialog_stubs()
sys.modules.pop("pdf_dialog", None)
pdf_dialog = importlib.import_module("pdf_dialog")


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
