import json


_BADGE_ID = "incremento-reviewer-priority-badge"
_STYLE_ID = "incremento-reviewer-priority-badge-style"
_SPACER_ID = "incremento-reviewer-priority-badge-spacer"


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


def format_reviewer_saved_time_value(seconds: float | int | None) -> str:
    """Return a reviewer-friendly saved browser time label."""
    try:
        total = max(0, int(round(float(seconds))))
    except Exception:
        return ""
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_reviewer_priority_badge_js(
    priority: float | int | None,
    *,
    a_factor: float | int | None = None,
    browser_time_seconds: float | int | None = None,
) -> str:
    enabled = priority is not None
    value_text = format_reviewer_priority_value(priority) if enabled else ""
    a_factor_text = format_reviewer_a_factor_value(a_factor) if enabled else ""
    browser_time_text = format_reviewer_saved_time_value(browser_time_seconds) if enabled else ""
    safe_value = json.dumps(value_text)
    safe_a_factor = json.dumps(a_factor_text)
    safe_browser_time = json.dumps(browser_time_text)
    return f"""
(function() {{
  var enabled = {"true" if enabled else "false"};
  var badgeId = {_BADGE_ID!r};
  var styleId = {_STYLE_ID!r};
  var spacerId = {_SPACER_ID!r};
  var badge = document.getElementById(badgeId);
  var spacer = document.getElementById(spacerId);
  if (!enabled) {{
    if (badge) {{
      badge.remove();
    }}
    if (spacer) {{
      spacer.remove();
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
      #${{spacerId}} {{
        display: block;
        width: 100%;
        height: 82px;
        pointer-events: none;
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
      #${{badgeId}} .incremento-browser-time-wrap {{
        display: none;
        padding-left: 12px;
        border-left: 1px solid rgba(143, 164, 194, 0.24);
      }}
      #${{badgeId}}.has-browser-time .incremento-browser-time-wrap {{
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
      '</div>' +
      '<div class="incremento-priority-metric incremento-browser-time-wrap">' +
        '<span class="incremento-priority-label">Saved</span>' +
        '<span class="incremento-priority-value incremento-browser-time-value"></span>' +
      '</div>';
    document.body.appendChild(badge);
  }}
  if (!spacer) {{
    spacer = document.createElement("div");
    spacer.id = spacerId;
    spacer.setAttribute("aria-hidden", "true");
    document.body.insertBefore(spacer, document.body.firstChild);
  }} else if (spacer.parentNode !== document.body || spacer !== document.body.firstChild) {{
    document.body.insertBefore(spacer, document.body.firstChild);
  }}
  var valueNode = badge.querySelector(".incremento-priority-value");
  var aFactorNode = badge.querySelector(".incremento-a-factor-value");
  var browserTimeNode = badge.querySelector(".incremento-browser-time-value");
  if (!valueNode || !aFactorNode || !browserTimeNode) {{
    badge.innerHTML =
      '<div class="incremento-priority-metric incremento-priority-wrap">' +
        '<span class="incremento-priority-label">Priority</span>' +
        '<span class="incremento-priority-value"></span>' +
      '</div>' +
      '<div class="incremento-priority-metric incremento-a-factor-wrap">' +
        '<span class="incremento-priority-label">A-Factor</span>' +
        '<span class="incremento-priority-value incremento-a-factor-value"></span>' +
      '</div>' +
      '<div class="incremento-priority-metric incremento-browser-time-wrap">' +
        '<span class="incremento-priority-label">Saved</span>' +
        '<span class="incremento-priority-value incremento-browser-time-value"></span>' +
      '</div>';
    valueNode = badge.querySelector(".incremento-priority-value");
    aFactorNode = badge.querySelector(".incremento-a-factor-value");
    browserTimeNode = badge.querySelector(".incremento-browser-time-value");
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
  if ({safe_browser_time}) {{
    badge.classList.add("has-browser-time");
  }} else {{
    badge.classList.remove("has-browser-time");
  }}
  if (browserTimeNode) {{
    browserTimeNode.textContent = {safe_browser_time};
  }}
}})();
""".strip()
