from aqt.qt import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QKeySequence,
    QKeySequenceEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


SHORTCUT_ACTION_SPECS = [
    {
        "id": "start_learning",
        "label": "Start Incremental Learning",
        "default": "",
    },
    {
        "id": "add_pdf",
        "label": "Add PDF",
        "default": "",
    },
    {
        "id": "webpage_to_pdf",
        "label": "Webpage to PDF",
        "default": "",
    },
    {
        "id": "add_epub",
        "label": "Add EPUB",
        "default": "",
    },
    {
        "id": "youtube_video",
        "label": "Add Video",
        "default": "",
    },
    {
        "id": "add_web_page",
        "label": "Web Page",
        "default": "",
    },
    {
        "id": "toggle_focus_timer",
        "label": "Show Focus Timer",
        "default": "",
    },
    {
        "id": "statistics",
        "label": "Statistics",
        "default": "",
    },
    {
        "id": "search_all",
        "label": "Search ALL",
        "default": "Ctrl+Alt+S",
    },
    {
        "id": "open_settings",
        "label": "Settings",
        "default": "",
    },
    {
        "id": "export_user_data",
        "label": "Export Full Backup",
        "default": "",
    },
    {
        "id": "quick_open_pdf",
        "label": "Quick Open Docs",
        "default": "Ctrl+Alt+P",
    },
    {
        "id": "set_priority",
        "label": "Set Priority",
        "default": "Alt+P",
    },
    {
        "id": "extract_card",
        "label": "Extract Card",
        "default": "Alt+X",
    },
    {
        "id": "pdf_prev_page",
        "label": "PDF Viewer: Previous Page",
        "default": "Ctrl+Alt+Left",
    },
    {
        "id": "pdf_next_page",
        "label": "PDF Viewer: Next Page",
        "default": "Ctrl+Alt+Right",
    },
    {
        "id": "pdf_zoom_out",
        "label": "PDF Viewer: Zoom Out",
        "default": "Ctrl+Alt+-",
    },
    {
        "id": "pdf_zoom_in",
        "label": "PDF Viewer: Zoom In",
        "default": "Ctrl+Alt+=",
    },
    {
        "id": "pdf_mark_read",
        "label": "PDF Viewer: Mark Read",
        "default": "Ctrl+Alt+M",
    },
]


def default_shortcuts() -> dict[str, str]:
    return {spec["id"]: spec["default"] for spec in SHORTCUT_ACTION_SPECS}


class IncrementoSettingsDialog(QDialog):
    def __init__(
        self,
        current_shortcuts: dict[str, str],
        note_type_names: list[str] | None = None,
        current_extract_notetype: str = "",
        extract_source_links: dict[str, bool] | bool | None = None,
        current_priority_lower_is_more_important: bool = True,
        current_show_priority_dialog_after_answer: bool = False,
        current_remember_browser_card_scroll: bool = True,
        current_topic_card_types: dict[str, bool] | None = None,
        current_topic_card_tags: list[str] | str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Incremento Settings")
        self.setMinimumWidth(620)
        self._defaults = default_shortcuts()
        self._editors: dict[str, QKeySequenceEdit] = {}

        root = QVBoxLayout(self)

        tabs = QTabWidget()
        root.addWidget(tabs)

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setSpacing(8)

        general_hint = QLabel(
            "Choose which card type extraction opens in by default."
            " This applies to the Add Card dock and Extract Card dialog."
            " You can also choose which source links should be appended while extracting,"
            " how incremental learning interprets stored priority numbers,"
            " whether to prompt for priority after answering a card,"
            " whether browser cards remember scroll position,"
            " and which card types or tags should be treated as topics."
        )
        general_hint.setWordWrap(True)
        general_layout.addWidget(general_hint)

        general_form = QFormLayout()
        general_form.setHorizontalSpacing(16)
        general_form.setVerticalSpacing(8)

        self._extract_notetype_combo = QComboBox()
        self._extract_notetype_combo.addItem("Use current Add Card type", "")
        for name in note_type_names or []:
            self._extract_notetype_combo.addItem(name, name)

        selected_value = str(current_extract_notetype or "").strip()
        for idx in range(self._extract_notetype_combo.count()):
            if self._extract_notetype_combo.itemData(idx) == selected_value:
                self._extract_notetype_combo.setCurrentIndex(idx)
                break

        general_form.addRow("Default extract card type:", self._extract_notetype_combo)

        if isinstance(extract_source_links, dict):
            source_link_cfg = {
                "pdf": bool(extract_source_links.get("pdf", True)),
                "web": bool(extract_source_links.get("web", True)),
                "parent": bool(extract_source_links.get("parent", True)),
            }
        elif isinstance(extract_source_links, bool):
            source_link_cfg = {
                "pdf": bool(extract_source_links),
                "web": bool(extract_source_links),
                "parent": bool(extract_source_links),
            }
        else:
            source_link_cfg = {"pdf": True, "web": True, "parent": True}

        self._extract_pdf_links_cb = QCheckBox("PDF pages")
        self._extract_pdf_links_cb.setChecked(source_link_cfg["pdf"])
        general_form.addRow("Should add links to:", self._extract_pdf_links_cb)

        self._extract_web_links_cb = QCheckBox("Web pages / URLs")
        self._extract_web_links_cb.setChecked(source_link_cfg["web"])
        general_form.addRow("", self._extract_web_links_cb)

        self._extract_parent_links_cb = QCheckBox("Parent cards in Extract Card")
        self._extract_parent_links_cb.setChecked(source_link_cfg["parent"])
        general_form.addRow("", self._extract_parent_links_cb)

        priority_direction_wrap = QWidget()
        priority_direction_layout = QVBoxLayout(priority_direction_wrap)
        priority_direction_layout.setContentsMargins(0, 0, 0, 0)
        priority_direction_layout.setSpacing(4)

        self._priority_direction_group = QButtonGroup(self)
        self._priority_lower_radio = QRadioButton("Lower priority number is more important")
        self._priority_higher_radio = QRadioButton("Higher priority number is more important")
        self._priority_direction_group.addButton(self._priority_lower_radio)
        self._priority_direction_group.addButton(self._priority_higher_radio)
        self._priority_lower_radio.setChecked(bool(current_priority_lower_is_more_important))
        self._priority_higher_radio.setChecked(not bool(current_priority_lower_is_more_important))

        priority_direction_layout.addWidget(self._priority_lower_radio)
        priority_direction_layout.addWidget(self._priority_higher_radio)
        general_form.addRow("Incremental learning priority:", priority_direction_wrap)

        self._show_priority_dialog_after_answer_cb = QCheckBox(
            "Show priority dialog after each card is done before moving forward"
        )
        self._show_priority_dialog_after_answer_cb.setChecked(
            bool(current_show_priority_dialog_after_answer)
        )
        general_form.addRow("", self._show_priority_dialog_after_answer_cb)

        self._remember_browser_card_scroll_cb = QCheckBox(
            "Remember scrolling position in browser cards"
        )
        self._remember_browser_card_scroll_cb.setChecked(
            bool(current_remember_browser_card_scroll)
        )
        general_form.addRow("", self._remember_browser_card_scroll_cb)

        topic_types = {
            "pdf_epub": True,
            "video": True,
            "writing": True,
            "web": False,
        }
        if isinstance(current_topic_card_types, dict):
            for key in topic_types:
                if key in current_topic_card_types:
                    topic_types[key] = bool(current_topic_card_types.get(key))

        topic_wrap = QWidget()
        topic_layout = QVBoxLayout(topic_wrap)
        topic_layout.setContentsMargins(0, 0, 0, 0)
        topic_layout.setSpacing(4)

        self._topic_pdf_epub_cb = QCheckBox("PDF / EPUB")
        self._topic_pdf_epub_cb.setChecked(topic_types["pdf_epub"])
        topic_layout.addWidget(self._topic_pdf_epub_cb)

        self._topic_video_cb = QCheckBox("Video")
        self._topic_video_cb.setChecked(topic_types["video"])
        topic_layout.addWidget(self._topic_video_cb)

        self._topic_writing_cb = QCheckBox("Writing")
        self._topic_writing_cb.setChecked(topic_types["writing"])
        topic_layout.addWidget(self._topic_writing_cb)

        self._topic_web_cb = QCheckBox("Web")
        self._topic_web_cb.setChecked(topic_types["web"])
        topic_layout.addWidget(self._topic_web_cb)

        general_form.addRow("Consider these as topics:", topic_wrap)

        tags_text = ""
        if isinstance(current_topic_card_tags, str):
            tags_text = current_topic_card_tags
        elif isinstance(current_topic_card_tags, (list, tuple, set)):
            tags_text = ", ".join(
                str(tag).strip()
                for tag in current_topic_card_tags
                if str(tag).strip()
            )

        self._topic_tags_edit = QLineEdit()
        self._topic_tags_edit.setPlaceholderText("tag1, tag2")
        self._topic_tags_edit.setText(tags_text)
        general_form.addRow("Topic tags:", self._topic_tags_edit)

        topic_hint = QLabel(
            "Topic cards use More / Same / Less buttons and A-factor scheduling instead of flashcard grading."
        )
        topic_hint.setWordWrap(True)
        general_form.addRow("", topic_hint)

        general_layout.addLayout(general_form)
        general_layout.addStretch(1)
        tabs.addTab(general_tab, "General")

        shortcuts_tab = QWidget()
        shortcuts_layout = QVBoxLayout(shortcuts_tab)
        shortcuts_layout.setSpacing(8)

        hint = QLabel(
            "Assign keyboard shortcuts for Incremento actions."
            " Leave a field empty to disable that shortcut."
        )
        hint.setWordWrap(True)
        shortcuts_layout.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        for spec in SHORTCUT_ACTION_SPECS:
            action_id = spec["id"]
            editor = QKeySequenceEdit()
            configured = (current_shortcuts or {}).get(
                action_id, self._defaults[action_id]
            )
            editor.setKeySequence(QKeySequence(configured))
            self._editors[action_id] = editor

            row_wrap = QWidget()
            row_layout = QHBoxLayout(row_wrap)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(editor)

            clear_btn = QPushButton("Clear")
            clear_btn.setMaximumWidth(64)
            clear_btn.clicked.connect(lambda _, e=editor: e.clear())
            row_layout.addWidget(clear_btn)

            form.addRow(spec["label"] + ":", row_wrap)

        shortcuts_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch(1)

        restore_btn = QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self._restore_defaults)
        action_row.addWidget(restore_btn)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.clicked.connect(self._clear_all)
        action_row.addWidget(clear_all_btn)

        shortcuts_layout.addLayout(action_row)
        shortcuts_layout.addStretch(1)

        tabs.addTab(shortcuts_tab, "Shortcuts")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _restore_defaults(self) -> None:
        for action_id, editor in self._editors.items():
            editor.setKeySequence(QKeySequence(self._defaults.get(action_id, "")))

    def _clear_all(self) -> None:
        for editor in self._editors.values():
            editor.clear()

    @property
    def shortcuts_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for action_id, editor in self._editors.items():
            result[action_id] = editor.keySequence().toString(
                QKeySequence.SequenceFormat.PortableText
            )
        return result

    @property
    def extract_notetype_name(self) -> str:
        return str(self._extract_notetype_combo.currentData() or "").strip()

    @property
    def extract_source_links(self) -> dict[str, bool]:
        return {
            "pdf": bool(self._extract_pdf_links_cb.isChecked()),
            "web": bool(self._extract_web_links_cb.isChecked()),
            "parent": bool(self._extract_parent_links_cb.isChecked()),
        }

    @property
    def priority_lower_is_more_important(self) -> bool:
        return bool(self._priority_lower_radio.isChecked())

    @property
    def show_priority_dialog_after_answer(self) -> bool:
        return bool(self._show_priority_dialog_after_answer_cb.isChecked())

    @property
    def remember_browser_card_scroll(self) -> bool:
        return bool(self._remember_browser_card_scroll_cb.isChecked())

    @property
    def topic_card_types(self) -> dict[str, bool]:
        return {
            "pdf_epub": bool(self._topic_pdf_epub_cb.isChecked()),
            "video": bool(self._topic_video_cb.isChecked()),
            "writing": bool(self._topic_writing_cb.isChecked()),
            "web": bool(self._topic_web_cb.isChecked()),
        }

    @property
    def topic_card_tags(self) -> list[str]:
        raw = str(self._topic_tags_edit.text() or "")
        tags: list[str] = []
        seen: set[str] = set()
        for chunk in raw.replace("\n", ",").split(","):
            tag = chunk.strip()
            if not tag:
                continue
            normalized = tag.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            tags.append(tag)
        return tags
