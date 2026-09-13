"""Compact reviewer-bar visibility controls shared by More and Settings."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


_BUTTONS = (
    ("done", "reviewer_visibility_show_done", "incremento-topic-done-cell"),
    ("postpone", "reviewer_visibility_show_postpone", "incremento-topic-postpone-cell"),
    ("extract", "reviewer_visibility_show_extract", "incremento-reviewer-extract-cell"),
)
_STYLE_ID = "incremento-reviewer-button-visibility"


def add_reviewer_button_visibility_menu(
    menu: object,
    visibility: Mapping[str, bool],
    on_toggle: Callable[[str, bool], None],
    *,
    group_visible: bool = True,
    on_group_toggle: Callable[[bool], None] | None = None,
) -> None:
    """Offer independent, live toggles without changing the current card."""
    submenu = menu.addMenu(t("reviewer_visibility_menu"))
    if on_group_toggle is not None:
        group_action = submenu.addAction(t("reviewer_visibility_show_group"))
        group_action.setCheckable(True)
        group_action.setChecked(bool(group_visible))
        group_action.triggered.connect(lambda checked=False: on_group_toggle(bool(checked)))
        submenu.addSeparator()
    for key, label_id, _cell_id in _BUTTONS:
        action = submenu.addAction(t(label_id))
        action.setCheckable(True)
        action.setChecked(bool(visibility.get(key, True)))
        if on_group_toggle is not None:
            action.setEnabled(bool(group_visible))
        action.triggered.connect(
            lambda checked=False, button=key: on_toggle(button, bool(checked))
        )


def effective_reviewer_button_visibility(
    visibility: Mapping[str, bool], group_visible: bool,
) -> dict[str, bool]:
    """Collapse the group without losing the user's per-button preferences."""
    return {key: bool(group_visible and visibility.get(key, True)) for key, _, _ in _BUTTONS}


def build_reviewer_button_visibility_js(visibility: Mapping[str, bool]) -> str:
    """Hide whole cells so bar spacing closes even for asynchronously added buttons."""
    css = "\n".join(
        f"#{cell_id} {{ display: none !important; }}"
        for key, _label, cell_id in _BUTTONS
        if not visibility.get(key, True)
    )
    return """(() => {
  const id = %s;
  const css = %s;
  let style = document.getElementById(id);
  if (!css) {
    style?.remove();
    return;
  }
  if (!style) {
    style = document.createElement("style");
    style.id = id;
    document.head.appendChild(style);
  }
  style.textContent = css;
})();""" % (json.dumps(_STYLE_ID), json.dumps(css))
