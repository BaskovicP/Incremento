"""Completed webpage imports offer their saved PDF and keep the stream open."""
import ast
from pathlib import Path
from types import SimpleNamespace
import threading
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("handoff", [False, True])
@pytest.mark.parametrize("outcome", ["success", "profile-switch", "save-failed", "closed"])
def test_webpage_import_offers_its_saved_pdf_only_after_success(tmp_path, handoff, outcome):
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "addWebpageFunction")
    function.body = [node for node in function.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    events, pending, result_dialogs = [], [], []
    profile = ["First"]
    pdf = tmp_path / "verified.pdf"
    pdf.write_bytes(b"%PDF-1.7\nArticle")
    details = {"reason": "Practise mental maths", "source": "A blog", "list_ids": [1]}
    cancelled = threading.Event()
    dialog = SimpleNamespace(pdf_path=str(pdf), title_text="My article", tags_to_apply=["topic"],
        source_url="https://example.org/article", browser_handoff_completed=handoff, document_details=details,
        _capture_cancel=cancelled, _import_generation=0, _cancel_btn=Mock(), _set_busy=Mock(),
        _status_lbl=Mock(), prepare_next_import=lambda: events.append("next"))
    dialog._import_current = lambda generation, expected_profile: (
        generation == dialog._import_generation and expected_profile == profile[0])

    class CollectionOp:
        def __init__(self, parent, operation):
            assert parent is dialog
            self.operation = operation
        def success(self, callback):
            self.on_success = callback
            return self
        def failure(self, callback):
            self.on_failure = callback
            return self
        def run_in_background(self):
            pending.append(self)

    def exec_dialog():
        dialog.save_pdf(dialog)
        assert events == []  # No collection mutation until Anki dispatches the operation.
        if outcome == "profile-switch":
            profile[0] = "Second"
        elif outcome == "closed":
            dialog._import_generation += 1
            cancelled.set()
        op = pending.pop()
        try:
            result = op.operation(namespace["mw"].col)
        except Exception as error:
            op.on_failure(error)
        else:
            op.on_success(result)

    def dialog_factory(_parent, **kwargs):
        dialog.save_pdf = kwargs["save_pdf"]
        dialog.show = exec_dialog
        dialog.exec = lambda: pytest.fail("The persistent import stream must not block other Anki windows")
        dialog.setAttribute = Mock()
        return dialog

    def add(*_args, **kwargs):
        assert kwargs["tags"] == ["topic"]
        assert kwargs["metadata"]["source_link"] == "https://example.org/article"
        assert kwargs["document_details"] == details
        assert kwargs["profile"] == "First"
        assert _args[1] is namespace["mw"].col
        if outcome == "save-failed":
            raise OSError("Synthetic import failure")
        events.append("saved")
        return 123

    def result_dialog(parent, title, result_profile, open_pdf):
        assert parent is namespace["mw"]
        assert title == "My article" and result_profile == "First"
        result_dialogs.append(open_pdf)
        return SimpleNamespace(show=lambda: events.append("result"))

    namespace = {
        "mw": SimpleNamespace(col=SimpleNamespace(add_custom_undo_entry=lambda _label: 1,
                                                  merge_undo_entries=lambda _id: object())),
        "_ADDON_DIR": str(tmp_path), "CollectionOp": CollectionOp, "SimpleNamespace": SimpleNamespace,
        "_active_profile": lambda: profile[0], "WebpageToPdfDialog": dialog_factory,
        "add_pdf_card": add, "activate_anki_window": lambda _window: events.append("focus"),
        "WebpagePdfResultDialog": result_dialog,
        "_open_pdf_card": lambda cid: events.append(("open", cid)),
        "build_incremento_metadata": lambda **kwargs: kwargs,
        "_t": lambda key, **_kw: key, "os": __import__("os"),
        "Qt": SimpleNamespace(WidgetAttribute=SimpleNamespace(WA_DeleteOnClose=object())),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    namespace["addWebpageFunction"]()
    if outcome == "success":
        assert events == (["saved", "next", "focus", "result"] if handoff else ["saved", "next", "result"])
        assert len(result_dialogs) == 1
        result_dialogs[0]()
        assert events[-1] == ("open", 123)
    else:
        assert events == []
        assert result_dialogs == []
        if outcome == "save-failed":
            dialog._set_busy.assert_called_once_with(False)
            dialog._status_lbl.setText.assert_called_once()
            assert dialog._cancel_btn.setEnabled.call_args.args == (True,)
    assert not pdf.exists()
