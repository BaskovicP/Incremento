"""The reviewer uses one visual contract for native and Incremento controls."""

import json
from pathlib import Path
import subprocess


def test_reviewer_buttons_share_geometry_without_recoloring_answer_grades():
    from reviewer_button_style import ACTION_BUTTONS, ALL_BUTTONS, REVIEWER_BUTTON_CSS

    for selector in (
        "#ansbut", "#incremento-postpone-but", "#incremento-item-skip-but",
        "#incremento-topic-done-button", "#incremento-reviewer-extract-button",
    ):
        assert selector in ACTION_BUTTONS
    assert 'button[data-ease]' in ALL_BUTTONS
    assert 'button[data-ease]' not in ACTION_BUTTONS
    geometry = REVIEWER_BUTTON_CSS.split(ALL_BUTTONS + " {", 1)[1].split("}", 1)[0]
    for declaration in (
        "height: 32px", "border-radius: 8px", "font-size: 14px",
        "font-weight: 500", "box-shadow: none",
    ):
        assert declaration in geometry
    assert "background:" not in geometry
    assert "color:" not in geometry
    assert ":root.night-mode" in REVIEWER_BUTTON_CSS
    assert ":focus-visible" in REVIEWER_BUTTON_CSS
    assert ":disabled" in REVIEWER_BUTTON_CSS
    assert "prefers-reduced-motion" in REVIEWER_BUTTON_CSS
    assert "linear-gradient" not in REVIEWER_BUTTON_CSS


def test_shared_styles_are_idempotent_and_replace_legacy_button_styles():
    from reviewer_button_style import build_reviewer_button_style_js

    harness = r'''
      const assert = require("node:assert/strict");
      const vm = require("node:vm");
      const script = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
      const nodes = new Map();
      const old = ["incremento-reviewer-extract-button-style", "incremento-topic-done-style"];
      for (const id of old) nodes.set(id, {remove() { nodes.delete(id); }});
      const context = vm.createContext({document: {
        getElementById: id => nodes.get(id),
        createElement: tag => ({tag}),
        head: {appendChild: node => nodes.set(node.id, node)},
      }});
      vm.runInContext(script, context);
      vm.runInContext(script, context);
      assert.equal(nodes.size, 1);
      const style = nodes.get("incremento-reviewer-button-style");
      assert.match(style.textContent, /#ansbut/);
      assert.match(style.textContent, /#incremento-topic-done-button/);
      assert.match(style.textContent, /#incremento-reviewer-extract-button/);
    '''
    result = subprocess.run(
        ["node", "-e", harness], input=json.dumps(build_reviewer_button_style_js()),
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_question_and_answer_button_sync_install_the_shared_style():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text()
    body = source.split("def _sync_reviewer_extract_button(reviewer)", 1)[1].split("\ndef ", 1)[0]
    assert "build_reviewer_button_style_js()" in body
