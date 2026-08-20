from __future__ import annotations

import time

from aqt import mw
from aqt.operations.tag import add_tags_to_notes
from aqt.qt import (
    QAction,
    QCheckBox,
    QColor,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QLineEdit,
    QPushButton,
    QShortcut,
    QScrollArea,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.utils import showInfo, tooltip

try:
    from ..backend.db import (
        assign_browser_tag_color_indexes,
        get_browser_tag_color_indexes,
        get_browser_tag_custom_colors,
        get_browser_quick_tag_settings,
        get_recent_browser_tag_groups,
        seed_recent_browser_tag_groups,
        set_browser_tag_custom_color,
        set_browser_quick_tag_settings,
        touch_recent_browser_tag_group,
    )
    from ..backend.paths import get_active_profile
    from ..backend.reviewer_tags import (
        deduplicate_tag_groups,
        normalize_tag_list,
        recent_tag_groups_from_note_rows,
        tag_groups_with_new_tags,
    )
    from .tag_colors import (
        assign_unique_tag_chip_colors,
        tag_chip_color_for_index,
        tag_chip_palette_size,
        tag_chip_reserved_indexes,
        tag_chip_stylesheet,
    )
    from .quick_tag_shortcuts import quick_tag_shortcut_keys
except ImportError:
    from backend.db import (
        assign_browser_tag_color_indexes,
        get_browser_tag_color_indexes,
        get_browser_tag_custom_colors,
        get_browser_quick_tag_settings,
        get_recent_browser_tag_groups,
        seed_recent_browser_tag_groups,
        set_browser_tag_custom_color,
        set_browser_quick_tag_settings,
        touch_recent_browser_tag_group,
    )
    from backend.paths import get_active_profile
    from backend.reviewer_tags import (
        deduplicate_tag_groups,
        normalize_tag_list,
        recent_tag_groups_from_note_rows,
        tag_groups_with_new_tags,
    )
    from tag_colors import (
        assign_unique_tag_chip_colors,
        tag_chip_color_for_index,
        tag_chip_palette_size,
        tag_chip_reserved_indexes,
        tag_chip_stylesheet,
    )
    from quick_tag_shortcuts import quick_tag_shortcut_keys


_RECENT_TAG_LIMIT = 9
_RECENT_NOTE_SCAN_LIMIT = 500


def _collection_recent_tag_groups(*, limit: int = _RECENT_TAG_LIMIT) -> list[list[str]]:
    try:
        rows = mw.col.db.all(
            "SELECT tags FROM notes WHERE tags != '' "
            "ORDER BY mod DESC, id DESC LIMIT ?",
            _RECENT_NOTE_SCAN_LIMIT,
        )
    except Exception:
        rows = []
    return recent_tag_groups_from_note_rows(rows, limit=limit)


def _browser_recent_tag_groups(
    addon_dir: str,
    *,
    limit: int = _RECENT_TAG_LIMIT,
) -> list[list[str]]:
    profile = get_active_profile()
    try:
        settings = get_browser_quick_tag_settings(addon_dir, profile)
        if settings.get("use_fixed_sets"):
            return [
                group
                for group in settings.get("fixed_tag_groups", [])
                if normalize_tag_list(group)
            ][:_RECENT_TAG_LIMIT]
    except Exception:
        pass
    try:
        exact_recent = get_recent_browser_tag_groups(
            addon_dir,
            profile,
            limit=limit,
        )
    except Exception:
        exact_recent = []

    inferred = _collection_recent_tag_groups(limit=limit)
    if not exact_recent:
        try:
            seed_recent_browser_tag_groups(
                addon_dir,
                profile,
                inferred,
                limit=limit,
            )
            return get_recent_browser_tag_groups(addon_dir, profile, limit=limit)
        except Exception:
            return inferred

    # Keep established number positions stable. Only the newest collection set
    # may enter at the front, and only when it introduces a previously unseen tag.
    additions = tag_groups_with_new_tags(inferred[:1], exact_recent, limit=1)
    if additions:
        try:
            touch_recent_browser_tag_group(
                addon_dir,
                profile,
                additions[0],
                limit=limit,
                used_at=int(time.time() * 1000),
            )
        except Exception:
            pass

    try:
        seed_recent_browser_tag_groups(
            addon_dir,
            profile,
            inferred,
            limit=limit,
        )
        return get_recent_browser_tag_groups(addon_dir, profile, limit=limit)
    except Exception:
        return deduplicate_tag_groups(exact_recent + additions, limit=limit)


class BrowserTagColorSettingsDialog(QDialog):
    def __init__(
        self,
        tags,
        *,
        automatic_colors: dict[str, str],
        custom_colors: dict[str, str],
        all_effective_colors: dict[str, str],
        use_fixed_sets: bool = False,
        fixed_tag_groups=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick Tag Settings")
        self.setMinimumWidth(880)
        self._base_tags = normalize_tag_list(tags)
        self._tags = list(self._base_tags)
        self._automatic_colors = {
            str(key).casefold(): str(value).upper()
            for key, value in automatic_colors.items()
        }
        self._custom_colors = {
            str(key).casefold(): str(value).upper()
            for key, value in custom_colors.items()
        }
        self._all_effective_colors = {
            str(key).casefold(): str(value).upper()
            for key, value in all_effective_colors.items()
        }
        self._previews: dict[str, QLabel] = {}
        self._fixed_edits: list[QLineEdit] = []

        root = QVBoxLayout(self)
        intro = QLabel(
            "Choose a unique color for each tag. Topic uses green automatically. "
            "Automatic restores the assigned default color."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._use_fixed_sets = QCheckBox(
            "Use my fixed tag sets instead of recent tag sets",
            self,
        )
        self._use_fixed_sets.setChecked(bool(use_fixed_sets))
        root.addWidget(self._use_fixed_sets)

        fixed_hint = QLabel(
            "Define the numbered slots yourself. Separate tags with spaces, commas, "
            "or semicolons. Fill slots from 1 upward without gaps.",
            self,
        )
        fixed_hint.setWordWrap(True)
        root.addWidget(fixed_hint)

        fixed_grid = QGridLayout()
        fixed_grid.setHorizontalSpacing(10)
        fixed_grid.setVerticalSpacing(6)
        saved_groups = list(fixed_tag_groups or [])[:_RECENT_TAG_LIMIT]
        while len(saved_groups) < _RECENT_TAG_LIMIT:
            saved_groups.append([])
        for index in range(_RECENT_TAG_LIMIT):
            row = index // 3
            column = (index % 3) * 2
            fixed_grid.addWidget(QLabel(str(index + 1), self), row, column)
            edit = QLineEdit(self)
            edit.setPlaceholderText("topic psychology")
            edit.setText(" ".join(normalize_tag_list(saved_groups[index])))
            edit.setEnabled(self._use_fixed_sets.isChecked())
            edit.textChanged.connect(self._on_fixed_sets_changed)
            self._fixed_edits.append(edit)
            fixed_grid.addWidget(edit, row, column + 1)
        root.addLayout(fixed_grid)
        self._use_fixed_sets.toggled.connect(self._on_fixed_mode_toggled)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._color_host = QWidget(scroll)
        self._color_grid = QGridLayout(self._color_host)
        self._color_grid.setColumnStretch(1, 1)
        scroll.setWidget(self._color_host)
        root.addWidget(scroll, 1)
        self._rebuild_color_rows()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        root.addWidget(buttons)

    def _on_fixed_mode_toggled(self, enabled: bool) -> None:
        for edit in self._fixed_edits:
            edit.setEnabled(bool(enabled))
        self._rebuild_color_rows()

    def _on_fixed_sets_changed(self, _text: str = "") -> None:
        self._rebuild_color_rows()

    def _ensure_automatic_colors(self, tags) -> None:
        cleaned = normalize_tag_list(tags)
        used_colors = {
            str(color).upper()
            for color in list(self._automatic_colors.values())
            + list(self._custom_colors.values())
            + list(self._all_effective_colors.values())
            if color
        }
        if "topic" in {tag.casefold() for tag in cleaned} and "topic" not in self._automatic_colors:
            topic_green = tag_chip_color_for_index(
                tag_chip_reserved_indexes()["topic"]
            )
            owner = next(
                (
                    key
                    for key, color in self._automatic_colors.items()
                    if str(color).upper() == topic_green
                ),
                "",
            )
            if owner:
                replacement_index = 0
                replacement = tag_chip_color_for_index(replacement_index)
                while replacement.upper() in used_colors:
                    replacement_index += 1
                    replacement = tag_chip_color_for_index(replacement_index)
                self._automatic_colors[owner] = replacement
                used_colors.add(replacement.upper())
            self._automatic_colors["topic"] = topic_green
            used_colors.add(topic_green.upper())

        next_index = 0
        for tag in cleaned:
            key = tag.casefold()
            if key in self._automatic_colors:
                continue
            color = tag_chip_color_for_index(next_index)
            while color.upper() in used_colors:
                next_index += 1
                color = tag_chip_color_for_index(next_index)
            self._automatic_colors[key] = color
            used_colors.add(color.upper())
            next_index += 1

    def _rebuild_color_rows(self) -> None:
        while self._color_grid.count():
            item = self._color_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._previews.clear()

        fixed_tags = [
            tag
            for group in self.fixed_tag_groups
            for tag in group
        ]
        self._tags = normalize_tag_list(self._base_tags + fixed_tags)
        self._ensure_automatic_colors(self._tags)

        for row, tag in enumerate(self._tags):
            key = tag.casefold()
            name_label = QLabel(f"#{tag}", self._color_host)
            self._color_grid.addWidget(name_label, row, 0)

            preview = QLabel(f"#{tag}", self._color_host)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setMinimumWidth(150)
            self._previews[key] = preview
            self._color_grid.addWidget(preview, row, 1)

            choose = QPushButton("Choose…", self._color_host)
            qconnect(
                choose.clicked,
                lambda _checked=False, value=tag: self._choose_color(value),
            )
            self._color_grid.addWidget(choose, row, 2)

            automatic = QPushButton("Automatic", self._color_host)
            qconnect(
                automatic.clicked,
                lambda _checked=False, value=tag: self._use_automatic(value),
            )
            self._color_grid.addWidget(automatic, row, 3)
            self._refresh_preview(tag)

    def _effective_color(self, tag: str) -> str:
        key = str(tag or "").casefold()
        return self._custom_colors.get(key) or self._automatic_colors.get(
            key,
            tag_chip_color_for_index(0),
        )

    def _color_owner(self, tag: str, color: str) -> str:
        key = str(tag or "").casefold()
        target = str(color or "").upper()
        effective = dict(self._all_effective_colors)
        for visible_tag in self._tags:
            visible_key = visible_tag.casefold()
            effective[visible_key] = self._effective_color(visible_tag)
        for other_key, other_color in effective.items():
            if other_key != key and str(other_color or "").upper() == target:
                return other_key
        return ""

    def _set_color(self, tag: str, color: str, *, custom: bool) -> None:
        key = str(tag or "").casefold()
        normalized = str(color or "").upper()
        owner = self._color_owner(tag, normalized)
        if owner:
            showInfo(
                f"That color is already used by #{owner}. Choose a different color.",
                parent=self,
            )
            return
        if custom:
            self._custom_colors[key] = normalized
        else:
            self._custom_colors.pop(key, None)
        self._all_effective_colors[key] = normalized
        self._refresh_preview(tag)

    def _choose_color(self, tag: str) -> None:
        current = QColor(self._effective_color(tag))
        chosen = QColorDialog.getColor(current, self, f"Choose color for #{tag}")
        if not chosen.isValid():
            return
        color = chosen.name(QColor.NameFormat.HexRgb).upper()
        self._set_color(tag, color, custom=True)

    def _use_automatic(self, tag: str) -> None:
        key = str(tag or "").casefold()
        automatic = self._automatic_colors.get(key, tag_chip_color_for_index(0))
        self._set_color(tag, automatic, custom=False)

    def _refresh_preview(self, tag: str) -> None:
        preview = self._previews.get(str(tag or "").casefold())
        if preview is not None:
            preview.setStyleSheet(tag_chip_stylesheet(self._effective_color(tag)))

    @property
    def custom_colors(self) -> dict[str, str]:
        return dict(self._custom_colors)

    @property
    def use_fixed_sets(self) -> bool:
        return self._use_fixed_sets.isChecked()

    @property
    def fixed_tag_groups(self) -> list[list[str]]:
        return [normalize_tag_list(edit.text()) for edit in self._fixed_edits]

    def accept(self) -> None:
        if self.use_fixed_sets:
            groups = self.fixed_tag_groups
            filled_indexes = [index for index, group in enumerate(groups) if group]
            if not filled_indexes:
                showInfo("Add at least one fixed tag set, or turn fixed mode off.", parent=self)
                return
            last_filled = max(filled_indexes)
            if any(not groups[index] for index in range(last_filled + 1)):
                showInfo("Fill fixed tag-set slots from 1 upward without gaps.", parent=self)
                return
            seen: set[tuple[str, ...]] = set()
            for group in groups[: last_filled + 1]:
                key = tuple(sorted(tag.casefold() for tag in group))
                if key in seen:
                    showInfo("Each fixed tag set must be unique.", parent=self)
                    return
                seen.add(key)
        super().accept()


class BrowserQuickTagDialog(QDialog):
    def __init__(
        self,
        tag_groups,
        *,
        selected_note_count: int,
        tag_colors: dict[str, str] | None = None,
        color_settings_callback=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick Add Tags")
        self.setMinimumWidth(960)
        self.selected_tags: list[str] = []
        self._shortcuts: list[QShortcut] = []
        self._color_settings_callback = color_settings_callback
        self._tag_chips: list[tuple[str, QLabel]] = []
        self.settings_changed = False
        groups = deduplicate_tag_groups(tag_groups, limit=_RECENT_TAG_LIMIT)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        noun = "note" if selected_note_count == 1 else "notes"
        if groups:
            intro_text = (
                f"Apply one tag set to {selected_note_count} selected {noun}. "
                "Press 1–9 or A–I, or click a set. Slots run across each row. "
                "Each tag always keeps the same color."
            )
        else:
            intro_text = (
                "No tag sets are available yet. Open Settings… to define your own "
                "fixed tag sets."
            )
        intro = QLabel(intro_text)
        intro.setWordWrap(True)
        root.addWidget(intro)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)

        visible_tags = [tag for group in groups for tag in group]
        self._tag_colors = tag_colors or assign_unique_tag_chip_colors(visible_tags)
        for index, tags in enumerate(groups):
            number_key, letter_key = quick_tag_shortcut_keys(index)
            shortcut_label = f"{number_key} / {letter_key}"
            button = QPushButton(self)
            button.setMinimumHeight(42)
            button.setAccessibleName(
                f"{number_key} or {letter_key}: {', '.join(tags)}"
            )
            button.setToolTip(
                f"{number_key} or {letter_key}: {' + '.join(tags)}"
            )

            button_layout = QHBoxLayout(button)
            button_layout.setContentsMargins(10, 5, 10, 5)
            button_layout.setSpacing(6)

            key_label = QLabel(shortcut_label, button)
            key_label.setFixedWidth(48)
            key_label.setStyleSheet("font-weight: 700;")
            key_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            button_layout.addWidget(key_label)

            for tag in tags:
                chip = QLabel(f"#{tag}", button)
                chip.setStyleSheet(
                    tag_chip_stylesheet(
                        self._tag_colors.get(tag.casefold(), tag_chip_color_for_index(0)),
                    )
                )
                chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                button_layout.addWidget(chip)
                self._tag_chips.append((tag, chip))
            button_layout.addStretch(1)

            qconnect(
                button.clicked,
                lambda _checked=False, values=list(tags): self._choose(values),
            )
            # Standard 3×3 order: 1/2/3, then 4/5/6, then 7/8/9.
            grid.addWidget(button, index // 3, index % 3)

            for shortcut_key in (number_key, letter_key):
                shortcut = QShortcut(QKeySequence(shortcut_key), self)
                qconnect(
                    shortcut.activated,
                    lambda values=list(tags): self._choose(values),
                )
                self._shortcuts.append(shortcut)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, parent=self)
        if self._color_settings_callback is not None:
            settings_button = buttons.addButton(
                "Settings…",
                QDialogButtonBox.ButtonRole.ActionRole,
            )
            settings_button.setToolTip("Configure fixed tag sets and colors")
            qconnect(settings_button.clicked, self._open_color_settings)
        qconnect(buttons.rejected, self.reject)
        root.addWidget(buttons)

    def _open_color_settings(self) -> None:
        if self._color_settings_callback is None:
            return
        updated = self._color_settings_callback(self)
        if not updated:
            return
        if isinstance(updated, dict) and updated.get("reload"):
            self.settings_changed = True
            self.reject()
            return
        if isinstance(updated, dict) and "colors" in updated:
            updated = updated["colors"]
        self._tag_colors = {
            str(key).casefold(): str(value).upper()
            for key, value in updated.items()
        }
        for tag, chip in self._tag_chips:
            chip.setStyleSheet(
                tag_chip_stylesheet(
                    self._tag_colors.get(tag.casefold(), tag_chip_color_for_index(0))
                )
            )

    def _choose(self, tags) -> None:
        self.selected_tags = normalize_tag_list(tags)
        if self.selected_tags:
            self.accept()


def _selected_note_ids(browser) -> list[int]:
    try:
        raw_ids = browser.selected_notes()
    except Exception:
        raw_ids = []

    note_ids: list[int] = []
    seen: set[int] = set()
    for raw_note_id in raw_ids or []:
        try:
            note_id = int(raw_note_id)
        except Exception:
            continue
        if note_id in seen:
            continue
        seen.add(note_id)
        note_ids.append(note_id)
    return note_ids


def open_browser_quick_tag_dialog(browser, addon_dir: str) -> None:
    note_ids = _selected_note_ids(browser)
    if not note_ids:
        showInfo("Select one or more Browser rows first.", parent=browser)
        return

    recent_groups = _browser_recent_tag_groups(addon_dir)
    visible_tags = [tag for group in recent_groups for tag in group]
    profile = get_active_profile()
    try:
        color_indexes = assign_browser_tag_color_indexes(
            addon_dir,
            profile,
            visible_tags,
            palette_size=tag_chip_palette_size(),
            reserved_indexes=tag_chip_reserved_indexes(),
        )
        automatic_colors = {
            key: tag_chip_color_for_index(color_index)
            for key, color_index in color_indexes.items()
        }
        all_color_indexes = get_browser_tag_color_indexes(addon_dir, profile)
        all_automatic_colors = {
            key: tag_chip_color_for_index(color_index)
            for key, color_index in all_color_indexes.items()
        }
        all_custom_colors = get_browser_tag_custom_colors(addon_dir, profile)
        all_effective_colors = dict(all_automatic_colors)
        all_effective_colors.update(all_custom_colors)
        tag_colors = {
            tag.casefold(): all_effective_colors[tag.casefold()]
            for tag in normalize_tag_list(visible_tags)
        }
        quick_tag_settings = get_browser_quick_tag_settings(addon_dir, profile)

        def _edit_tag_colors(parent):
            visible_keys = {tag.casefold() for tag in normalize_tag_list(visible_tags)}
            visible_custom_colors = {
                key: value
                for key, value in all_custom_colors.items()
                if key in visible_keys
            }
            settings = BrowserTagColorSettingsDialog(
                visible_tags,
                automatic_colors=automatic_colors,
                custom_colors=visible_custom_colors,
                all_effective_colors=all_effective_colors,
                use_fixed_sets=bool(quick_tag_settings.get("use_fixed_sets")),
                fixed_tag_groups=quick_tag_settings.get("fixed_tag_groups", []),
                parent=parent,
            )
            if not settings.exec():
                return None

            previous_use_fixed = bool(quick_tag_settings.get("use_fixed_sets"))
            previous_fixed_groups = list(quick_tag_settings.get("fixed_tag_groups", []))
            chosen_use_fixed = settings.use_fixed_sets
            chosen_fixed_groups = settings.fixed_tag_groups
            set_browser_quick_tag_settings(
                addon_dir,
                profile,
                use_fixed_sets=chosen_use_fixed,
                fixed_tag_groups=chosen_fixed_groups,
            )
            quick_tag_settings["use_fixed_sets"] = chosen_use_fixed
            quick_tag_settings["fixed_tag_groups"] = chosen_fixed_groups

            managed_tags = normalize_tag_list(
                visible_tags
                + [tag for group in chosen_fixed_groups for tag in group]
            )
            assign_browser_tag_color_indexes(
                addon_dir,
                profile,
                managed_tags,
                palette_size=tag_chip_palette_size(),
                reserved_indexes=tag_chip_reserved_indexes(),
            )
            refreshed_indexes = get_browser_tag_color_indexes(addon_dir, profile)
            all_automatic_colors.clear()
            all_automatic_colors.update(
                {
                    key: tag_chip_color_for_index(color_index)
                    for key, color_index in refreshed_indexes.items()
                }
            )

            chosen_custom_colors = settings.custom_colors
            for tag in managed_tags:
                key = tag.casefold()
                set_browser_tag_custom_color(
                    addon_dir,
                    profile,
                    tag,
                    chosen_custom_colors.get(key, ""),
                )
                if key in chosen_custom_colors:
                    all_custom_colors[key] = chosen_custom_colors[key]
                else:
                    all_custom_colors.pop(key, None)

            all_effective_colors.clear()
            all_effective_colors.update(all_automatic_colors)
            all_effective_colors.update(all_custom_colors)
            settings_changed = (
                previous_use_fixed != chosen_use_fixed
                or previous_fixed_groups != chosen_fixed_groups
            )
            return {
                "reload": settings_changed,
                "colors": {
                    key: all_effective_colors[key]
                    for key in visible_keys
                },
            }

        color_settings_callback = _edit_tag_colors
    except Exception:
        tag_colors = assign_unique_tag_chip_colors(visible_tags)
        color_settings_callback = None

    dialog = BrowserQuickTagDialog(
        recent_groups,
        selected_note_count=len(note_ids),
        tag_colors=tag_colors,
        color_settings_callback=color_settings_callback,
        parent=browser,
    )
    dialog_result = dialog.exec()
    if dialog.settings_changed:
        QTimer.singleShot(
            0,
            lambda b=browser, path=addon_dir: open_browser_quick_tag_dialog(b, path),
        )
        return
    if not dialog_result or not dialog.selected_tags:
        return

    selected_tags = list(dialog.selected_tags)

    def _on_success(result) -> None:
        try:
            touch_recent_browser_tag_group(
                addon_dir,
                get_active_profile(),
                selected_tags,
                limit=_RECENT_TAG_LIMIT,
            )
        except Exception:
            pass
        count = int(getattr(result, "count", 0) or 0)
        noun = "note" if count == 1 else "notes"
        tag_label = " ".join(f"#{tag}" for tag in selected_tags)
        tooltip(f"Added {tag_label} to {count} {noun}.", parent=browser)

    add_tags_to_notes(
        parent=browser,
        note_ids=note_ids,
        space_separated_tags=" ".join(selected_tags),
    ).success(_on_success).run_in_background(initiator=browser)


def install_browser_quick_tag_action(browser, addon_dir: str) -> None:
    if getattr(browser, "_incremento_quick_tag_action", None) is not None:
        return

    action = QAction("Quick Add Tags…", browser)
    action.setShortcut(QKeySequence("Ctrl+T"))
    action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
    qconnect(
        action.triggered,
        lambda _checked=False, b=browser: open_browser_quick_tag_dialog(b, addon_dir),
    )

    notes_menu = getattr(getattr(browser, "form", None), "menu_Notes", None)
    before_action = getattr(getattr(browser, "form", None), "actionAdd_Tags", None)
    if notes_menu is not None and before_action is not None:
        notes_menu.insertAction(before_action, action)
    elif notes_menu is not None:
        notes_menu.addAction(action)
    else:
        browser.addAction(action)
    browser._incremento_quick_tag_action = action
