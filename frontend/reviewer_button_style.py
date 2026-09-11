"""Shared reviewer-button geometry and theme-aware secondary action colors."""

import json


_ACTION_SELECTORS = (
    "#ansbut", "#incremento-postpone-but", "#incremento-item-skip-but",
    "#incremento-topic-done-button", "#incremento-reviewer-extract-button",
)
ACTION_BUTTONS = ":is(" + ", ".join(_ACTION_SELECTORS) + ")"
ALL_BUTTONS = ":is(" + ", ".join((*_ACTION_SELECTORS, "button[data-ease]")) + ")"

REVIEWER_BUTTON_CSS = """
:root {
  --incremento-button-bg: #f3f4f6;
  --incremento-button-hover: #e7eaee;
  --incremento-button-border: #c8cdd4;
  --incremento-button-fg: #303640;
  --incremento-button-focus: #3576c4;
  --incremento-defer-bg: #f8f0f1;
  --incremento-defer-hover: #f1e3e5;
  --incremento-defer-border: #bd8c90;
  --incremento-defer-fg: #98464d;
}
:root.night-mode {
  --incremento-button-bg: #36383d;
  --incremento-button-hover: #41444a;
  --incremento-button-border: #55585e;
  --incremento-button-fg: #eceef2;
  --incremento-button-focus: #8bbcff;
  --incremento-defer-bg: #3d3337;
  --incremento-defer-hover: #493a3f;
  --incremento-defer-border: #856169;
  --incremento-defer-fg: #e6aaad;
}
__ALL__ {
  appearance: none !important;
  box-sizing: border-box !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  position: relative;
  height: 32px !important;
  min-height: 32px !important;
  min-width: 100px !important;
  padding: 0 14px !important;
  border-width: 1px !important;
  border-style: solid !important;
  border-radius: 8px !important;
  font-family: inherit !important;
  font-size: 14px !important;
  font-weight: 500 !important;
  line-height: 1.2 !important;
  white-space: nowrap;
  box-shadow: none !important;
  text-shadow: none !important;
  transform: none !important;
  transition: background-color 120ms ease, border-color 120ms ease !important;
}
__ACTIONS__ {
  background: var(--incremento-button-bg) !important;
  border-color: var(--incremento-button-border) !important;
  color: var(--incremento-button-fg) !important;
}
__ACTIONS__:hover:not(:disabled) {
  background: var(--incremento-button-hover) !important;
}
:is(#incremento-postpone-but, #incremento-item-skip-but) {
  background: var(--incremento-defer-bg) !important;
  border-color: var(--incremento-defer-border) !important;
  color: var(--incremento-defer-fg) !important;
}
:is(#incremento-postpone-but, #incremento-item-skip-but):hover:not(:disabled) {
  background: var(--incremento-defer-hover) !important;
}
__ALL__:focus-visible {
  outline: 2px solid var(--incremento-button-focus) !important;
  outline-offset: 2px !important;
}
__ALL__:disabled {
  opacity: 0.55 !important;
  cursor: default;
}
__ALL__ .stattxt {
  font-size: 12px;
  font-weight: 400;
  line-height: 1.2;
}
#incremento-reviewer-extract-button .incremento-reviewer-extract-icon {
  margin-right: 6px;
  font-size: 1em;
  font-weight: inherit;
}
#incremento-topic-done-cell {
  position: relative;
  padding-inline-start: 12px;
  border: none;
}
#incremento-topic-done-cell::before {
  content: "";
  position: absolute;
  inset-inline-start: 0;
  top: 50%;
  height: 22px;
  width: 1px;
  transform: translateY(-50%);
  background: var(--incremento-button-border);
}
@media (prefers-reduced-motion: reduce) {
  __ALL__ { transition: none !important; }
}
""".replace("__ALL__", ALL_BUTTONS).replace("__ACTIONS__", ACTION_BUTTONS)


def build_reviewer_button_style_js() -> str:
    return """
(() => {
  for (const legacy of ["incremento-reviewer-extract-button-style", "incremento-topic-done-style"]) {
    document.getElementById(legacy)?.remove();
  }
  const id = "incremento-reviewer-button-style";
  let style = document.getElementById(id);
  if (!style) {
    style = document.createElement("style");
    style.id = id;
    document.head.appendChild(style);
  }
  style.textContent = %s;
})();
""" % json.dumps(REVIEWER_BUTTON_CSS)
