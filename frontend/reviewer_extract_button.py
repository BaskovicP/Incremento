import json


_BUTTON_ID = "incremento-reviewer-extract-button"
_STYLE_ID = "incremento-reviewer-extract-button-style"
_CELL_ID = "incremento-reviewer-extract-cell"


def build_reviewer_extract_button_js(shortcut_text: str | None) -> str:
    safe_shortcut = json.dumps(str(shortcut_text or "").strip())
    return f"""
(function() {{
  var buttonId = {_BUTTON_ID!r};
  var styleId = {_STYLE_ID!r};
  var shortcutText = {safe_shortcut};
  var attempts = 0;

  function removeExisting() {{
    var existing = document.getElementById(buttonId);
    if (!existing) {{
      return;
    }}
    var cell = existing.closest("td");
    if (cell && cell.parentElement && cell.parentElement.children.length > 1) {{
      cell.remove();
      return;
    }}
    existing.remove();
  }}

  function ensureStyle() {{
    var style = document.getElementById(styleId);
    if (style) {{
      return;
    }}
    style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      #${{buttonId}} {{
        background: linear-gradient(180deg, rgba(44, 50, 62, 0.94), rgba(24, 28, 36, 0.97)) !important;
        border: 1px solid rgba(20, 24, 32, 0.64) !important;
        box-shadow: 0 8px 18px rgba(0, 0, 0, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
        color: #f4f7fb !important;
        min-width: 92px;
        font-weight: 600;
        transition: background 120ms ease, border-color 120ms ease, color 120ms ease, transform 120ms ease, box-shadow 120ms ease;
      }}
      #${{buttonId}}:hover,
      #${{buttonId}}:focus {{
        background: linear-gradient(180deg, rgba(58, 68, 84, 0.96), rgba(29, 36, 48, 0.98)) !important;
        border-color: rgba(58, 121, 202, 0.72) !important;
        color: #ffffff !important;
        box-shadow: 0 10px 22px rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.11) !important;
        transform: translateY(-1px);
      }}
      #${{buttonId}}:disabled {{
        background: linear-gradient(180deg, rgba(198, 204, 214, 0.96), rgba(181, 188, 200, 0.98)) !important;
        border: 1px solid rgba(104, 114, 130, 0.48) !important;
        box-shadow: 0 5px 12px rgba(0, 0, 0, 0.10) !important;
        color: rgba(35, 42, 53, 0.78) !important;
        opacity: 1 !important;
      }}
      #${{buttonId}} .incremento-reviewer-extract-icon {{
        margin-right: 6px;
        opacity: 0.92;
        font-size: 0.95em;
      }}
      #${{buttonId}} .stattxt {{
        opacity: 0.82;
      }}
    `;
    document.head.appendChild(style);
  }}

  function install() {{
    var existing = document.getElementById(buttonId);
    if (existing) {{
      existing.title = shortcutText
        ? "Extract selected content into a new card (" + shortcutText + ")"
        : "Extract selected content into a new card";
      return;
    }}

    function findButtonRow() {{
      var showAnswerButton = document.getElementById("ansbut");
      if (
        showAnswerButton &&
        showAnswerButton.closest &&
        showAnswerButton.closest("tr")
      ) {{
        return showAnswerButton.closest("tr");
      }}

      var easeButton = document.querySelector('button[data-ease]');
      if (easeButton && easeButton.closest && easeButton.closest("tr")) {{
        return easeButton.closest("tr");
      }}

      var buttonRows = Array.prototype.slice.call(
        document.querySelectorAll("table tr")
      );
      for (var idx = buttonRows.length - 1; idx >= 0; idx -= 1) {{
        var candidateRow = buttonRows[idx];
        if (
          candidateRow &&
          candidateRow.querySelector &&
          candidateRow.querySelector("button")
        ) {{
          return candidateRow;
        }}
      }}
      return null;
    }}

    var row = findButtonRow();
    if (!row) {{
      attempts += 1;
      if (attempts < 10) {{
        setTimeout(install, 40);
      }}
      return;
    }}

    var cell = document.createElement("td");
    cell.className = "stat2";
    cell.setAttribute("align", "center");
    cell.id = {_CELL_ID!r};

    var button = document.createElement("button");
    button.id = buttonId;
    button.title = shortcutText
      ? "Extract selected content into a new card (" + shortcutText + ")"
      : "Extract selected content into a new card";
    button.setAttribute("aria-label", "Extract selected content into a new card");
    button.innerHTML =
      '<span class="incremento-reviewer-extract-icon">+</span>Extract';
    button.onclick = function() {{
      pycmd("incremento_extract_card");
    }};

    cell.appendChild(button);
    ensureStyle();

    var insertBeforeCell = null;
    var rowCells = Array.prototype.slice.call(row.children || []);
    for (var i = rowCells.length - 1; i >= 0; i -= 1) {{
      var candidate = rowCells[i];
      if (
        candidate &&
        candidate.querySelector &&
        candidate.querySelector("button") &&
        !candidate.querySelector("#" + buttonId)
      ) {{
        insertBeforeCell = candidate;
        break;
      }}
    }}

    if (
      insertBeforeCell &&
      rowCells.length > 2 &&
      insertBeforeCell !== row.firstElementChild
    ) {{
      row.insertBefore(cell, insertBeforeCell);
    }} else {{
      row.appendChild(cell);
    }}
  }}

  removeExisting();
  install();
}})();
""".strip()
