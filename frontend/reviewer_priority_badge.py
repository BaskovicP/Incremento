import json


_BADGE_ID = "incremento-reviewer-priority-badge"
_STYLE_ID = "incremento-reviewer-priority-badge-style"


def format_reviewer_priority_value(priority: float | int | None) -> str:
    """Return a reviewer-friendly integer label for the stored priority."""
    try:
        value = float(priority)
    except Exception:
        value = 50.0
    value = max(0.0, min(100.0, value))
    return str(int(round(value)))


def format_reviewer_a_factor_value(a_factor: float | int | None) -> str:
    """Return a reviewer-friendly A-factor label for topic cards."""
    try:
        value = float(a_factor)
    except Exception:
        return ""
    return f"{value:.3f}"


def build_reviewer_priority_badge_js(
    priority: float | int | None,
    *,
    a_factor: float | int | None = None,
) -> str:
    enabled = priority is not None
    value_text = format_reviewer_priority_value(priority) if enabled else ""
    a_factor_text = format_reviewer_a_factor_value(a_factor) if enabled else ""
    safe_value = json.dumps(value_text)
    safe_a_factor = json.dumps(a_factor_text)
    return f"""
(function() {{
  var enabled = {"true" if enabled else "false"};
  var badgeId = {_BADGE_ID!r};
  var styleId = {_STYLE_ID!r};
  var badge = document.getElementById(badgeId);
  if (!enabled) {{
    if (badge) {{
      badge.remove();
    }}
    return;
  }}
  if (!document.body) {{
    return;
  }}
  var style = document.getElementById(styleId);
  if (!style) {{
    style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      #${{badgeId}} {{
        position: fixed;
        top: 12px;
        right: 16px;
        z-index: 2147483000;
        display: inline-flex;
        align-items: center;
        gap: 12px;
        padding: 9px 12px;
        border-radius: 16px;
        border: 1px solid rgba(93, 124, 170, 0.34);
        background: rgba(16, 20, 28, 0.82);
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.26);
        color: #eef3fb;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        pointer-events: none;
        backdrop-filter: blur(10px);
      }}
      #${{badgeId}} .incremento-priority-metric {{
        display: flex;
        flex-direction: column;
        gap: 3px;
      }}
      #${{badgeId}} .incremento-priority-label {{
        color: #9fb3cf;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      #${{badgeId}} .incremento-priority-value {{
        color: #ffffff;
        font-size: 17px;
        font-weight: 800;
        line-height: 1;
        min-width: 2ch;
      }}
      #${{badgeId}} .incremento-a-factor-wrap {{
        display: none;
        padding-left: 12px;
        border-left: 1px solid rgba(143, 164, 194, 0.24);
      }}
      #${{badgeId}}.has-a-factor .incremento-a-factor-wrap {{
        display: flex;
      }}
    `;
    (document.head || document.documentElement).appendChild(style);
  }}
  if (!badge) {{
    badge = document.createElement("div");
    badge.id = badgeId;
    badge.innerHTML =
      '<div class="incremento-priority-metric incremento-priority-wrap">' +
        '<span class="incremento-priority-label">Priority</span>' +
        '<span class="incremento-priority-value"></span>' +
      '</div>' +
      '<div class="incremento-priority-metric incremento-a-factor-wrap">' +
        '<span class="incremento-priority-label">A-Factor</span>' +
        '<span class="incremento-priority-value incremento-a-factor-value"></span>' +
      '</div>';
    document.body.appendChild(badge);
  }}
  var valueNode = badge.querySelector(".incremento-priority-value");
  var aFactorNode = badge.querySelector(".incremento-a-factor-value");
  if (!valueNode || !aFactorNode) {{
    badge.innerHTML =
      '<div class="incremento-priority-metric incremento-priority-wrap">' +
        '<span class="incremento-priority-label">Priority</span>' +
        '<span class="incremento-priority-value"></span>' +
      '</div>' +
      '<div class="incremento-priority-metric incremento-a-factor-wrap">' +
        '<span class="incremento-priority-label">A-Factor</span>' +
        '<span class="incremento-priority-value incremento-a-factor-value"></span>' +
      '</div>';
    valueNode = badge.querySelector(".incremento-priority-value");
    aFactorNode = badge.querySelector(".incremento-a-factor-value");
  }}
  if (valueNode) {{
    valueNode.textContent = {safe_value};
  }}
  if ({safe_a_factor}) {{
    badge.classList.add("has-a-factor");
  }} else {{
    badge.classList.remove("has-a-factor");
  }}
  if (aFactorNode) {{
    aFactorNode.textContent = {safe_a_factor};
  }}
}})();
""".strip()
