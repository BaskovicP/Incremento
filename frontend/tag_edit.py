"""QuickTagEdit — a QLineEdit with multi-token Anki tag autocomplete.

Usage:
    edit = QuickTagEdit(parent)
    tags = edit.tags()          # → list[str], empty if nothing typed
"""

from aqt import mw
from aqt.qt import QCompleter, QLineEdit, Qt


class _MultiTokenCompleter(QCompleter):
    """Complete the last space-separated token against all Anki tags."""

    def pathFromIndex(self, index):
        tag = super().pathFromIndex(index)
        text = self.widget().text() if self.widget() else ""
        tokens = text.split()
        if tokens:
            tokens[-1] = tag
        else:
            return tag
        return " ".join(tokens) + " "

    def splitPath(self, path):
        tokens = path.split()
        return [tokens[-1]] if tokens else [""]


class QuickTagEdit(QLineEdit):
    """QLineEdit pre-wired with Anki tag autocomplete (multi-token, contains match)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Tags (space-separated, optional)")
        self._attach_completer()

    def _attach_completer(self):
        try:
            all_tags = sorted(mw.col.tags.all()) if mw and mw.col else []
        except Exception:
            all_tags = []
        comp = _MultiTokenCompleter(all_tags, self)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(comp)

    def tags(self) -> list[str]:
        """Return a cleaned list of tags from the current text."""
        raw = self.text().strip()
        if not raw:
            return []
        return [t.lstrip("#") for t in raw.split() if t.strip()]
