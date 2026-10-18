"""The completed browser handoff saves first, then returns without another prompt."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("switched", [False, True])
def test_browser_handoff_returns_to_anki_only_after_a_successful_same_profile_import(tmp_path, switched):
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "addWebpageFunction")
    function.body = [node for node in function.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    events = []
    profile = ["First"]
    pdf = tmp_path / "verified.pdf"
    pdf.write_bytes(b"%PDF-1.7\nArticle")
    def exec_dialog():
        if switched:
            profile[0] = "Second"
        return True
    dialog = SimpleNamespace(exec=exec_dialog, pdf_path=str(pdf), title_text="My article", tags_to_apply=["topic"],
                             source_url="https://example.org/article", browser_handoff_completed=True)
    def add(*_args, **kwargs):
        assert kwargs["tags"] == ["topic"]
        assert kwargs["metadata"]["source_link"] == "https://example.org/article"
        events.append("saved")
    namespace = {
        "mw": SimpleNamespace(col=object()), "_ADDON_DIR": str(tmp_path),
        "_active_profile": lambda: profile[0], "WebpageToPdfDialog": lambda _parent: dialog,
        "add_pdf_card": add, "activate_anki_window": lambda _window: events.append("focus"),
        "tooltip": lambda *_a, **_kw: events.append("message"),
        "showInfo": lambda *_a, **_kw: events.append("modal"),
        "build_incremento_metadata": lambda **kwargs: kwargs,
        "_t": lambda key, **_kw: key, "os": __import__("os"),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    namespace["addWebpageFunction"]()
    assert events == ([] if switched else ["saved", "focus", "message"])
    assert not pdf.exists()
