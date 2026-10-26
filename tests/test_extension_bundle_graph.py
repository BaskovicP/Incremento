"""Budgets for the static dependency graph of committed extension bundles."""
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1] / "chrome_extensions/incremento_companion/dist"
STATIC_IMPORT = re.compile(
    r'''\b(?:import|export)(?:\s*\{[^}]*\}\s*from\s*|\s*\*\s*as\s*\w+\s*from\s*|'''
    r'''\s+[\w$]+\s*(?:,\s*\{[^}]*\}\s*)?from\s*|\s*)["'](\.[^"']+)["']'''
)


@pytest.mark.parametrize("entry", ["content.js", "background.js", "offscreen.js"])
def test_non_react_entries_exclude_ui_and_spreadsheet_validation_at_startup(entry):
    pending = [ROOT / entry]
    seen = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        pending.extend((path.parent / target) for target in STATIC_IMPORT.findall(path.read_text()))
    assert not any(path.name in {"extension-vendor.js", "extension-ui.js", "extension-language-packs.js"} for path in seen)
    assert sum(path.stat().st_size for path in seen) < 350_000


def test_bundle_graph_parser_excludes_dynamic_imports():
    text = '''import{t as translate}from"./core.js";import "./side-effect.js";
              export{value}from"./exports.js";const load=()=>import("./lazy.js");'''
    assert STATIC_IMPORT.findall(text) == ["./core.js", "./side-effect.js", "./exports.js"]
