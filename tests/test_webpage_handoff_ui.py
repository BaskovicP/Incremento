"""Completed webpage imports offer to open their saved PDF without blocking Anki."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("handoff", [False, True])
@pytest.mark.parametrize("outcome", ["success", "profile-switch", "save-failed"])
def test_webpage_import_offers_its_saved_pdf_only_after_success(tmp_path, handoff, outcome):
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "addWebpageFunction")
    function.body = [node for node in function.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    events = []
    profile = ["First"]
    pdf = tmp_path / "verified.pdf"
    pdf.write_bytes(b"%PDF-1.7\nArticle")
    def exec_dialog():
        if outcome == "profile-switch":
            profile[0] = "Second"
        return True
    details = {"reason": "Practise mental maths", "source": "A blog", "list_ids": [1]}
    dialog = SimpleNamespace(exec=exec_dialog, pdf_path=str(pdf), title_text="My article", tags_to_apply=["topic"],
                             source_url="https://example.org/article", browser_handoff_completed=handoff,
                             document_details=details)
    def add(*_args, **kwargs):
        assert kwargs["tags"] == ["topic"]
        assert kwargs["metadata"]["source_link"] == "https://example.org/article"
        assert kwargs["document_details"] == details
        assert kwargs["profile"] == "First"
        if outcome == "save-failed":
            raise OSError("Synthetic import failure")
        events.append("saved")
        return 123
    result_dialogs = []
    def result_dialog(parent, title, result_profile, open_pdf):
        assert parent is namespace["mw"]
        assert title == "My article" and result_profile == "First"
        result_dialogs.append(open_pdf)
        return SimpleNamespace(show=lambda: events.append("result"))
    namespace = {
        "mw": SimpleNamespace(col=object()), "_ADDON_DIR": str(tmp_path),
        "_active_profile": lambda: profile[0], "WebpageToPdfDialog": lambda _parent, **_kw: dialog,
        "add_pdf_card": add, "activate_anki_window": lambda _window: events.append("focus"),
        "WebpagePdfResultDialog": result_dialog,
        "_open_pdf_card": lambda cid: events.append(("open", cid)),
        "tooltip": lambda *_a, **_kw: events.append("message"),
        "showInfo": lambda *_a, **_kw: events.append("modal"),
        "build_incremento_metadata": lambda **kwargs: kwargs,
        "_t": lambda key, **_kw: key, "os": __import__("os"),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    namespace["addWebpageFunction"]()
    if outcome == "success":
        assert events == (["saved", "focus", "result"] if handoff else ["saved", "result"])
        assert len(result_dialogs) == 1
        # The temporary conversion is already gone; open the durable card through
        # the shared reader route, only when the user chooses the action.
        result_dialogs[0]()
        assert events[-1] == ("open", 123)
    else:
        assert events == (["modal"] if outcome == "save-failed" else [])
        assert result_dialogs == []
    assert not pdf.exists()
