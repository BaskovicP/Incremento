"""Reviewer-owned menus and web overlays follow Incremento's chosen locale."""

import json
import subprocess

import pytest

from backend import i18n
from frontend.reviewer_extract_button import build_reviewer_extract_button_js
from frontend.reviewer_priority_badge import build_reviewer_priority_badge_js
from frontend.reviewer_source_cover import build_reviewer_source_cover_js


@pytest.mark.parametrize(
    ("locale", "label", "description"),
    [
        ("en", "Extract", "Extract selected content into a new card"),
        ("hr", "Izdvoji", "Izdvoji odabrani sadržaj u novu karticu"),
        ("zh-Hans", "提取", "将所选内容提取到新卡片"),
    ],
)
def test_extract_button_localizes_label_tooltip_and_accessibility_without_changing_command(
    monkeypatch, locale, label, description,
):
    monkeypatch.setattr(i18n, "_translator", i18n.Translator(locale))
    script = build_reviewer_extract_button_js('Alt+"X"')
    harness = r"""
const source = require('node:fs').readFileSync(0, 'utf8');
const row = {appendChild(cell) { this.cell = cell; }};
const makeNode = () => ({
  children: [], attributes: {}, textContent: '', innerHTML: '',
  setAttribute(name, value) { this.attributes[name] = value; },
  appendChild(child) { this.children.push(child); },
});
const document = {
  getElementById(id) { return id === 'ansbut' ? {closest() {return row; }} : null; },
  createElement: makeNode,
};
let command;
require('node:vm').runInNewContext(source, {document, pycmd(value) { command = value; }});
const button = row.cell.children[0];
button.onclick();
console.log(JSON.stringify({
  text: button.textContent + button.innerHTML + button.children.map(node => node.textContent).join(''),
  title: button.title, aria: button.attributes['aria-label'], command,
}));
"""
    result = subprocess.run(["node", "-e", harness], input=script, text=True,
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert label in rendered["text"]
    assert rendered["title"] == f'{description} (Alt+"X")'
    assert rendered["aria"] == description
    assert rendered["command"] == "incremento_extract_card"


@pytest.mark.parametrize(
    ("locale", "labels"),
    [("hr", ("Prioritet", "A-faktor", "Spremljeno", "Raspored")),
     ("zh-Hans", ("优先级", "A 因子", "已保存", "计划"))],
)
def test_priority_badge_localizes_all_metric_labels_and_preserves_schedule(monkeypatch, locale, labels):
    monkeypatch.setattr(i18n, "_translator", i18n.Translator(locale))
    script = build_reviewer_priority_badge_js(52, custom_schedule_text='Moj "Plan" <tomorrow>')
    # The JS renderer receives safe strings and inserts all labels as text nodes.
    for label in labels:
        assert json.dumps(label) in script
    assert json.dumps('Moj "Plan" <tomorrow>') in script
    assert 'badge.classList.remove("has-schedule")' in build_reviewer_priority_badge_js(52)


@pytest.mark.parametrize(
    ("locale", "label", "hint"),
    [("hr", "Izvorni PDF", "Poveznica na izvor na ovoj kartici otvara dokument."),
     ("zh-Hans", "来源 PDF", "此卡片上的来源链接可打开文档。")],
)
def test_source_cover_localizes_default_and_hint_but_preserves_supplied_labels(
    monkeypatch, locale, label, hint,
):
    monkeypatch.setattr(i18n, "_translator", i18n.Translator(locale))
    default = build_reviewer_source_cover_js('User "title" <内容>')
    assert json.dumps(label) in default
    assert json.dumps(hint) in default
    assert json.dumps('User "title" <内容>') in default
    supplied = build_reviewer_source_cover_js("Title", source_label="User reference")
    assert json.dumps("User reference") in supplied
