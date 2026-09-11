import json


_BUTTON_ID = "incremento-reviewer-extract-button"
_CELL_ID = "incremento-reviewer-extract-cell"


def build_reviewer_extract_button_js(shortcut_text: str | None) -> str:
    safe_shortcut = json.dumps(str(shortcut_text or "").strip())
    return f"""
(function() {{
  var buttonId = {_BUTTON_ID!r};
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

    row.appendChild(cell);
  }}

  removeExisting();
  install();
}})();
""".strip()
