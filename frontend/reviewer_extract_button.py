import json

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


_BUTTON_ID = "incremento-reviewer-extract-button"
_CELL_ID = "incremento-reviewer-extract-cell"


def build_reviewer_extract_button_js(shortcut_text: str | None) -> str:
    shortcut = str(shortcut_text or "").strip()
    description = t("reviewer_visibility_extract_description")
    tooltip = t("reviewer_visibility_extract_shortcut", shortcut=shortcut) if shortcut else description
    return f"""
(function() {{
  var buttonId = {_BUTTON_ID!r};
  var tooltipText = {json.dumps(tooltip)};
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

  function install() {{
    var existing = document.getElementById(buttonId);
    if (existing) {{
      existing.title = tooltipText;
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
    button.title = tooltipText;
    button.setAttribute("aria-label", {json.dumps(description)});
    var icon = document.createElement("span");
    icon.className = "incremento-reviewer-extract-icon";
    icon.textContent = "+";
    icon.setAttribute("aria-hidden", "true");
    var label = document.createElement("span");
    label.textContent = {json.dumps(t("reviewer_visibility_extract_label"))};
    button.appendChild(icon);
    button.appendChild(label);
    button.onclick = function() {{
      pycmd("incremento_extract_card");
    }};

    cell.appendChild(button);

    row.appendChild(cell);
  }}

  removeExisting();
  install();
}})();
""".strip()
