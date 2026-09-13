import json

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


_ROOT_ID = "incremento-reviewer-source-cover"
_STYLE_ID = "incremento-reviewer-source-cover-style"


def _cover_filename(value: str) -> str:
    name = str(value or "").strip()
    if (
        not name or name in {".", ".."} or len(name) > 255
        or any(character in name for character in '/\\:<>"?#%')
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        return ""
    return name


def build_reviewer_source_cover_js(
    title: str | None,
    *,
    cover_media: str = "",
    source_label: str | None = None,
) -> str:
    safe_title = json.dumps(str(title or "").strip())
    cover_filename = _cover_filename(cover_media)
    safe_cover = json.dumps(cover_filename)
    safe_label = json.dumps(str(source_label or "").strip() or t("reviewer_visibility_source_pdf"))
    enabled = bool(str(title or "").strip() or cover_filename)
    return f"""
(function() {{
  var enabled = {"true" if enabled else "false"};
  var rootId = {_ROOT_ID!r};
  var styleId = {_STYLE_ID!r};
  var root = document.getElementById(rootId);
  if (!enabled) {{
    if (root) {{
      root.remove();
    }}
    return;
  }}
  var host = document.getElementById("qa") || document.body;
  if (!host) {{
    return;
  }}
  var style = document.getElementById(styleId);
  if (!style) {{
    style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      #${{rootId}} {{
        display: flex;
        align-items: flex-start;
        gap: 14px;
        width: min(560px, 96vw);
        max-width: calc(100% - 24px);
        box-sizing: border-box;
        margin: 0 auto 18px;
        padding: 12px 14px;
        border-radius: 18px;
        border: 1px solid rgba(126, 143, 168, 0.28);
        background: linear-gradient(180deg, rgba(16, 20, 28, 0.96), rgba(12, 16, 24, 0.90));
        box-shadow: 0 14px 28px rgba(0, 0, 0, 0.22);
        text-align: left;
        white-space: normal;
      }}
      #${{rootId}}.title-only {{
        gap: 10px;
      }}
      #${{rootId}} .incremento-reviewer-source-cover-thumb {{
        display: block;
        width: 72px;
        min-width: 72px;
        max-height: 108px;
        border-radius: 11px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.28);
        overflow: hidden;
        background: rgba(255, 255, 255, 0.04);
      }}
      #${{rootId}} .incremento-reviewer-source-cover-thumb img {{
        display: block;
        width: 100%;
        height: auto;
        max-height: 108px;
        object-fit: cover;
      }}
      #${{rootId}} .incremento-reviewer-source-cover-body {{
        display: flex;
        min-width: 0;
        flex-direction: column;
        gap: 5px;
        padding-top: 2px;
      }}
      #${{rootId}} .incremento-reviewer-source-cover-label {{
        color: #8fa0bb;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      #${{rootId}} .incremento-reviewer-source-cover-title {{
        color: #f4f7fc;
        font-size: 16px;
        font-weight: 700;
        line-height: 1.3;
        overflow-wrap: anywhere;
      }}
      #${{rootId}} .incremento-reviewer-source-cover-hint {{
        color: #9fb0c9;
        font-size: 12px;
        line-height: 1.35;
      }}
    `;
    document.head.appendChild(style);
  }}
  if (!root) {{
    root = document.createElement("div");
    root.id = rootId;
  }}
  root.innerHTML = [
    '<div class="incremento-reviewer-source-cover-thumb"><img></div>',
    '<div class="incremento-reviewer-source-cover-body">',
    '  <div class="incremento-reviewer-source-cover-label"></div>',
    '  <div class="incremento-reviewer-source-cover-title"></div>',
    '  <div class="incremento-reviewer-source-cover-hint"></div>',
    '</div>',
  ].join("");
  var label = root.querySelector(".incremento-reviewer-source-cover-label");
  var title = root.querySelector(".incremento-reviewer-source-cover-title");
  var hint = root.querySelector(".incremento-reviewer-source-cover-hint");
  var thumb = root.querySelector(".incremento-reviewer-source-cover-thumb");
  var image = root.querySelector(".incremento-reviewer-source-cover-thumb img");
  var coverMedia = {safe_cover};
  var titleText = {safe_title};
  var labelText = {safe_label};
  label.textContent = labelText;
  title.textContent = titleText;
  hint.textContent = {json.dumps(t("reviewer_visibility_source_hint"))};
  root.classList.toggle("has-cover", !!coverMedia);
  root.classList.toggle("title-only", !coverMedia);
  thumb.style.display = coverMedia ? "block" : "none";
  if (coverMedia) {{
    // The title already names the source; a broken image must not display
    // its long filename as alt text inside the 72px thumbnail.
    image.alt = "";
    image.onerror = function() {{
      if (root.querySelector(".incremento-reviewer-source-cover-thumb img") !== image) {{
        return;
      }}
      thumb.style.display = "none";
      root.classList.remove("has-cover");
      root.classList.add("title-only");
    }};
    image.src = coverMedia;
  }} else {{
    image.removeAttribute("src");
    image.alt = "";
  }}
  if (root.parentElement !== host) {{
    root.remove();
    host.insertBefore(root, host.firstChild);
  }} else if (root !== host.firstChild) {{
    host.insertBefore(root, host.firstChild);
  }}
}})();
""".strip()
