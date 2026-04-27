import json


_BADGE_ID = "incremento-reviewer-priority-badge"
_STYLE_ID = "incremento-reviewer-priority-badge-style"
_SPACER_ID = "incremento-reviewer-priority-badge-spacer"

_PRIORITY_COLOR_STOPS = [
    (0.00, "#ff0000"),
    (0.17, "#ff8800"),
    (0.33, "#ffff00"),
    (0.50, "#00cc00"),
    (0.67, "#00cccc"),
    (0.83, "#0000ff"),
    (1.00, "#8800cc"),
]


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = str(color or "").strip().lstrip("#")
    if len(color) != 6:
        return (255, 255, 255)
    return tuple(int(color[idx:idx + 2], 16) for idx in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = [max(0, min(255, int(round(component)))) for component in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix_rgb(base: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, float(amount)))
    return tuple(
        int(round(base[idx] + (target[idx] - base[idx]) * amount))
        for idx in range(3)
    )


def _priority_accent_color(
    priority: float | int | None,
    *,
    lower_is_more_important: bool = True,
) -> str:
    try:
        value = float(priority)
    except Exception:
        value = 50.0
    fraction = max(0.0, min(1.0, value / 100.0))
    if not lower_is_more_important:
        fraction = 1.0 - fraction

    stops = _PRIORITY_COLOR_STOPS
    if fraction <= stops[0][0]:
        return stops[0][1]
    if fraction >= stops[-1][0]:
        return stops[-1][1]

    for idx in range(1, len(stops)):
        left_pos, left_color = stops[idx - 1]
        right_pos, right_color = stops[idx]
        if fraction <= right_pos:
            span = right_pos - left_pos
            local = 0.0 if span <= 0 else (fraction - left_pos) / span
            return _rgb_to_hex(
                _mix_rgb(_hex_to_rgb(left_color), _hex_to_rgb(right_color), local)
            )
    return stops[-1][1]


def get_reviewer_priority_palette(
    priority: float | int | None,
    *,
    lower_is_more_important: bool = True,
) -> dict[str, str]:
    accent = _priority_accent_color(
        priority,
        lower_is_more_important=lower_is_more_important,
    )
    accent_rgb = _hex_to_rgb(accent)
    background = _rgb_to_hex(_mix_rgb(accent_rgb, (9, 13, 22), 0.82))
    border = _rgb_to_hex(_mix_rgb(accent_rgb, (255, 255, 255), 0.28))
    label = _rgb_to_hex(_mix_rgb(accent_rgb, (255, 255, 255), 0.45))
    glow = f"rgba({accent_rgb[0]}, {accent_rgb[1]}, {accent_rgb[2]}, 0.28)"
    return {
        "accent": accent,
        "background": background,
        "border": border,
        "label": label,
        "glow": glow,
    }


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
    custom_schedule_text: str = "",
    lower_is_more_important: bool = True,
) -> str:
    enabled = priority is not None
    value_text = format_reviewer_priority_value(priority) if enabled else ""
    a_factor_text = format_reviewer_a_factor_value(a_factor) if enabled else ""
    browser_time_text = format_reviewer_saved_time_value(browser_time_seconds) if enabled else ""
    schedule_text = str(custom_schedule_text or "").strip() if enabled else ""
    palette = get_reviewer_priority_palette(
        priority,
        lower_is_more_important=lower_is_more_important,
    ) if enabled else {}
    safe_value = json.dumps(value_text)
    safe_a_factor = json.dumps(a_factor_text)
    safe_browser_time = json.dumps(browser_time_text)
    safe_schedule = json.dumps(schedule_text)
    safe_accent = json.dumps(palette.get("accent", "#ffffff"))
    safe_background = json.dumps(palette.get("background", "#10141c"))
    safe_border = json.dumps(palette.get("border", "#5d7caa"))
    safe_label = json.dumps(palette.get("label", "#9fb3cf"))
    safe_glow = json.dumps(palette.get("glow", "rgba(93, 124, 170, 0.28)"))
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
        --incremento-priority-accent: #ffffff;
        --incremento-priority-soft: #18202b;
        --incremento-priority-border: rgba(93, 124, 170, 0.34);
        --incremento-priority-label: #9fb3cf;
        --incremento-priority-glow: rgba(93, 124, 170, 0.28);
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
      #${{badgeId}} .incremento-priority-wrap {{
        padding: 8px 12px;
        margin: -2px 0;
        border-radius: 14px;
        border: 1px solid var(--incremento-priority-border);
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.01)), var(--incremento-priority-soft);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 0 0 1px rgba(255, 255, 255, 0.015), 0 10px 24px var(--incremento-priority-glow);
      }}
      #${{badgeId}} .incremento-priority-label {{
        color: #9fb3cf;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      #${{badgeId}} .incremento-priority-wrap .incremento-priority-label {{
        color: var(--incremento-priority-label);
      }}
      #${{badgeId}} .incremento-priority-value {{
        color: #ffffff;
        font-size: 17px;
        font-weight: 800;
        line-height: 1;
        min-width: 2ch;
      }}
      #${{badgeId}} .incremento-priority-wrap .incremento-priority-value {{
        color: var(--incremento-priority-accent);
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
      #${{badgeId}} .incremento-schedule-wrap {{
        display: none;
        padding-left: 12px;
        border-left: 1px solid rgba(143, 164, 194, 0.24);
        max-width: 240px;
      }}
      #${{badgeId}}.has-schedule .incremento-schedule-wrap {{
        display: flex;
      }}
      #${{badgeId}} .incremento-schedule-value {{
        line-height: 1.2;
        font-size: 13px;
        min-width: 0;
        white-space: normal;
      }}
    `;
    (document.head || document.documentElement).appendChild(style);
  }}
  var renderMarkup =
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
    '</div>' +
    '<div class="incremento-priority-metric incremento-schedule-wrap">' +
      '<span class="incremento-priority-label">Schedule</span>' +
      '<span class="incremento-priority-value incremento-schedule-value"></span>' +
    '</div>';
  if (!badge) {{
    badge = document.createElement("div");
    badge.id = badgeId;
    badge.innerHTML = renderMarkup;
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
  var scheduleNode = badge.querySelector(".incremento-schedule-value");
  if (!valueNode || !aFactorNode || !browserTimeNode || !scheduleNode) {{
    badge.innerHTML = renderMarkup;
    valueNode = badge.querySelector(".incremento-priority-value");
    aFactorNode = badge.querySelector(".incremento-a-factor-value");
    browserTimeNode = badge.querySelector(".incremento-browser-time-value");
    scheduleNode = badge.querySelector(".incremento-schedule-value");
  }}
  if (valueNode) {{
    valueNode.textContent = {safe_value};
  }}
  badge.style.setProperty("--incremento-priority-accent", {safe_accent});
  badge.style.setProperty("--incremento-priority-soft", {safe_background});
  badge.style.setProperty("--incremento-priority-border", {safe_border});
  badge.style.setProperty("--incremento-priority-label", {safe_label});
  badge.style.setProperty("--incremento-priority-glow", {safe_glow});
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
  if ({safe_schedule}) {{
    badge.classList.add("has-schedule");
  }} else {{
    badge.classList.remove("has-schedule");
  }}
  if (scheduleNode) {{
    scheduleNode.textContent = {safe_schedule};
  }}
}})();
""".strip()
