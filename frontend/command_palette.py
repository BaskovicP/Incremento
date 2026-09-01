"""Search model and lightweight Qt dialog for Incremento's command palette."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PaletteCommand:
    command_id: str
    label: str
    shortcut: str = ""
    group: str = ""
    keywords: tuple[str, ...] = ()
    enabled: bool = True
    unavailable_reason: str = ""
    callback: Callable[[], object] | None = field(
        default=None,
        compare=False,
        repr=False,
    )


def _normalized_words(value: str) -> list[str]:
    return [word for word in str(value or "").casefold().replace("_", " ").split() if word]


def _subsequence_distance(query: str, candidate: str) -> int | None:
    cursor = -1
    distance = 0
    for char in query:
        found = candidate.find(char, cursor + 1)
        if found < 0:
            return None
        if cursor >= 0:
            distance += found - cursor - 1
        cursor = found
    return distance


def fuzzy_score(query: str, candidate: str, keywords: Sequence[str] = ()) -> int | None:
    """Return a deterministic lower-is-better match score, or ``None``."""
    needle = " ".join(_normalized_words(query))
    if not needle:
        return 0

    label = " ".join(_normalized_words(candidate))
    keyword_text = " ".join(_normalized_words(" ".join(keywords)))
    searchable = " ".join(part for part in (label, keyword_text) if part)
    if label.startswith(needle):
        return 0
    if needle in label:
        return 10 + label.index(needle)
    if keyword_text and needle in keyword_text:
        return 30 + keyword_text.index(needle)

    query_words = needle.split()
    if query_words and all(word in searchable for word in query_words):
        return 50 + sum(searchable.index(word) for word in query_words)

    initials = "".join(word[0] for word in label.split() if word)
    compact = needle.replace(" ", "")
    if compact and initials.startswith(compact):
        return 100 + len(initials) - len(compact)

    distance = _subsequence_distance(compact, label.replace(" ", ""))
    if distance is not None:
        return 200 + distance
    return None


def rank_commands(
    commands: Iterable[PaletteCommand],
    query: str,
    *,
    include_unavailable: bool = False,
) -> list[PaletteCommand]:
    """Filter and rank commands while keeping unavailable matches explainable."""
    ranked: list[tuple[int, int, int, PaletteCommand]] = []
    for index, command in enumerate(commands):
        if not command.enabled and not include_unavailable:
            continue
        score = fuzzy_score(
            query,
            command.label,
            (*command.keywords, command.group, command.shortcut),
        )
        if score is None:
            continue
        ranked.append((0 if command.enabled else 1, score, index, command))
    ranked.sort(key=lambda row: row[:3])
    return [row[3] for row in ranked]


def build_palette_commands(
    action_specs: Iterable[dict],
    action_targets: dict[str, Sequence[object]],
    shortcuts: dict[str, str],
    *,
    invoke: Callable[[str], object],
    unavailable_reasons: Mapping[str, str] | None = None,
) -> list[PaletteCommand]:
    """Build a snapshot of the registered runtime commands for presentation."""
    reasons = dict(unavailable_reasons or {})
    commands: list[PaletteCommand] = []
    for raw_spec in action_specs:
        action_id = str(raw_spec.get("id") or "").strip()
        label = str(raw_spec.get("label") or "").strip()
        if not action_id or not label:
            continue
        targets = list(action_targets.get(action_id) or [])
        enabled_states: list[bool] = []
        for target in targets:
            is_enabled = getattr(target, "isEnabled", None)
            try:
                enabled_states.append(bool(is_enabled()) if callable(is_enabled) else True)
            except Exception:
                enabled_states.append(False)
        enabled = bool(targets) and any(enabled_states)

        def _callback(command_id: str = action_id):
            return invoke(command_id)

        commands.append(
            PaletteCommand(
                command_id=action_id,
                label=label,
                shortcut=str(shortcuts.get(action_id) or "").strip(),
                group=str(raw_spec.get("group") or "").strip(),
                keywords=tuple(
                    str(value).strip()
                    for value in raw_spec.get("keywords", ())
                    if str(value).strip()
                ),
                enabled=enabled,
                unavailable_reason=(
                    "" if enabled else reasons.get(action_id, "Unavailable in the current Anki view")
                ),
                callback=_callback,
            )
        )
    return commands


def create_command_palette_dialog(
    parent,
    commands: Sequence[PaletteCommand],
):
    """Create the Qt dialog lazily so the pure ranking model stays Qt-free."""
    from aqt.qt import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QVBoxLayout,
        Qt,
    )

    class CommandPaletteDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Incremento Commands")
            self.setMinimumSize(620, 420)
            self.setModal(False)
            self._commands = list(commands)
            self._visible_commands: list[PaletteCommand] = []

            root = QVBoxLayout(self)
            intro = QLabel(
                "Search every Incremento action. Disabled commands stay visible "
                "and explain why they are unavailable."
            )
            intro.setWordWrap(True)
            root.addWidget(intro)

            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("Type an action, e.g. review, PDF, statistics…")
            self.search_edit.setAccessibleName("Search Incremento commands")
            root.addWidget(self.search_edit)

            self.command_list = QListWidget()
            self.command_list.setAccessibleName("Matching Incremento commands")
            root.addWidget(self.command_list, 1)

            self.status_label = QLabel("")
            self.status_label.setWordWrap(True)
            root.addWidget(self.status_label)

            actions = QHBoxLayout()
            actions.addStretch(1)
            close_button = QPushButton("Close")
            close_button.setAccessibleName("Close command palette")
            close_button.clicked.connect(self.reject)
            actions.addWidget(close_button)
            root.addLayout(actions)

            self.search_edit.textChanged.connect(self._refresh)
            self.search_edit.returnPressed.connect(self._activate_current)
            self.command_list.itemActivated.connect(lambda _item: self._activate_current())
            self.command_list.currentRowChanged.connect(self._update_status)
            self._refresh("")
            self.search_edit.setFocus()

        def _refresh(self, query: str) -> None:
            self._visible_commands = rank_commands(
                self._commands,
                query,
                include_unavailable=True,
            )
            self.command_list.clear()
            for command in self._visible_commands:
                suffix = f"    {command.shortcut}" if command.shortcut else ""
                if not command.enabled:
                    suffix += "    Unavailable"
                item = QListWidgetItem(f"{command.label}{suffix}")
                item.setData(Qt.ItemDataRole.UserRole, command.command_id)
                if not command.enabled:
                    item.setForeground(Qt.GlobalColor.gray)
                self.command_list.addItem(item)
            if self._visible_commands:
                self.command_list.setCurrentRow(0)
            else:
                self.status_label.setText("No matching Incremento commands.")

        def _current_command(self) -> PaletteCommand | None:
            row = self.command_list.currentRow()
            if 0 <= row < len(self._visible_commands):
                return self._visible_commands[row]
            return None

        def _update_status(self, _row: int) -> None:
            command = self._current_command()
            if command is None:
                return
            if command.enabled:
                group = f"{command.group} · " if command.group else ""
                shortcut = command.shortcut or "No shortcut assigned"
                self.status_label.setText(f"{group}{shortcut}")
            else:
                self.status_label.setText(
                    command.unavailable_reason or "This command is not available right now."
                )

        def _activate_current(self) -> None:
            command = self._current_command()
            if command is None:
                return
            if not command.enabled or not callable(command.callback):
                self._update_status(self.command_list.currentRow())
                return
            self.accept()
            command.callback()

    return CommandPaletteDialog()
