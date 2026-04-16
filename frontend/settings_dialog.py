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
    QSpinBox,
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
        "id": "reveal_current_knowledge_tree",
        "label": "Reveal Current Card In Knowledge Tree",
        "default": "Ctrl+Alt+K",
    },
    {
        "id": "go_to_parent_knowledge_tree",
        "label": "Go To Parent In Knowledge Tree",
        "default": "Ctrl+Alt+Up",
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


def _normalize_tag_list(raw: list[str] | str | tuple[str, ...] | set[str] | None) -> list[str]:
    if isinstance(raw, str):
        parts = raw.replace("\n", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        parts = []

    tags: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item or "").strip()
        if not tag:
            continue
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
    return tags


def _tag_list_text(raw: list[str] | str | tuple[str, ...] | set[str] | None) -> str:
    return ", ".join(_normalize_tag_list(raw))


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
        current_prefer_web_card_resume_in_original_page: bool = True,
        current_use_fail_pass_on_items: bool = False,
        current_topic_card_types: dict[str, bool] | None = None,
        current_topic_card_tags: list[str] | str | None = None,
        current_add_card_topic_tags: list[str] | str | None = None,
        current_add_card_item_tags: list[str] | str | None = None,
        current_topic_postpone_enabled: bool = False,
        current_topic_postpone_mode: str = "timed",
        current_topic_postpone_minutes: int = 30,
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
            " how browser-card media resume opens,"
            " whether item cards use Fail / Pass instead of standard ease buttons,"
            " and which card types or tags should be treated as topics."
        )
        general_hint.setWordWrap(True)
        general_layout.addWidget(general_hint)

        def _section_title(text: str) -> QLabel:
            lbl = QLabel(f"<b>{text}</b>")
            lbl.setWordWrap(True)
            return lbl

        def _section_form() -> QFormLayout:
            form = QFormLayout()
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(8)
            return form

        general_layout.addWidget(_section_title("Extraction"))
        extraction_hint = QLabel(
            "Controls how extracted text opens in Add Card and which source links are appended."
        )
        extraction_hint.setWordWrap(True)
        general_layout.addWidget(extraction_hint)

        extraction_form = _section_form()

        self._extract_notetype_combo = QComboBox()
        self._extract_notetype_combo.addItem("Use current Add Card type", "")
        for name in note_type_names or []:
            self._extract_notetype_combo.addItem(name, name)

        selected_value = str(current_extract_notetype or "").strip()
        for idx in range(self._extract_notetype_combo.count()):
            if self._extract_notetype_combo.itemData(idx) == selected_value:
                self._extract_notetype_combo.setCurrentIndex(idx)
                break

        extraction_form.addRow("Default extract card type:", self._extract_notetype_combo)

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
        extraction_form.addRow("Should add links to:", self._extract_pdf_links_cb)

        self._extract_web_links_cb = QCheckBox("Web pages / URLs")
        self._extract_web_links_cb.setChecked(source_link_cfg["web"])
        extraction_form.addRow("", self._extract_web_links_cb)

        self._extract_parent_links_cb = QCheckBox("Parent cards in Extract Card")
        self._extract_parent_links_cb.setChecked(source_link_cfg["parent"])
        extraction_form.addRow("", self._extract_parent_links_cb)

        general_layout.addLayout(extraction_form)

        general_layout.addWidget(_section_title("Review Behavior"))
        review_hint = QLabel(
            "Controls how review buttons behave and whether review flow asks for extra input after answering."
        )
        review_hint.setWordWrap(True)
        general_layout.addWidget(review_hint)

        review_form = _section_form()

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
        review_form.addRow("Incremental learning priority:", priority_direction_wrap)

        self._show_priority_dialog_after_answer_cb = QCheckBox(
            "Show priority dialog after each card is done before moving forward"
        )
        self._show_priority_dialog_after_answer_cb.setChecked(
            bool(current_show_priority_dialog_after_answer)
        )
        review_form.addRow("", self._show_priority_dialog_after_answer_cb)

        self._remember_browser_card_scroll_cb = QCheckBox(
            "Remember scrolling position in browser cards"
        )
        self._remember_browser_card_scroll_cb.setChecked(
            bool(current_remember_browser_card_scroll)
        )
        review_form.addRow("", self._remember_browser_card_scroll_cb)

        self._prefer_web_card_resume_in_original_page_cb = QCheckBox(
            "Prefer resuming embedded web-card media in the original page"
        )
        self._prefer_web_card_resume_in_original_page_cb.setChecked(
            bool(current_prefer_web_card_resume_in_original_page)
        )
        review_form.addRow("", self._prefer_web_card_resume_in_original_page_cb)

        self._use_fail_pass_on_items_cb = QCheckBox(
            "Use Fail / Pass buttons on items"
        )
        self._use_fail_pass_on_items_cb.setChecked(
            bool(current_use_fail_pass_on_items)
        )
        review_form.addRow("", self._use_fail_pass_on_items_cb)

        general_layout.addLayout(review_form)

        general_layout.addWidget(_section_title("Topic Cards"))
        topic_section_hint = QLabel(
            "Topic cards use More / Same / Less buttons and A-factor scheduling instead of flashcard grading."
            " You can also add a red Postpone button for difficult topics."
        )
        topic_section_hint.setWordWrap(True)
        general_layout.addWidget(topic_section_hint)

        topic_form = _section_form()

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

        topic_form.addRow("Consider these as topics:", topic_wrap)

        self._topic_tags_edit = QLineEdit()
        self._topic_tags_edit.setPlaceholderText("tag1, tag2")
        self._topic_tags_edit.setText(_tag_list_text(current_topic_card_tags))
        topic_form.addRow("Topic tags:", self._topic_tags_edit)

        self._add_card_topic_tags_edit = QLineEdit()
        self._add_card_topic_tags_edit.setPlaceholderText("topic")
        self._add_card_topic_tags_edit.setText(_tag_list_text(current_add_card_topic_tags))
        topic_form.addRow("Add Card topic-button tags:", self._add_card_topic_tags_edit)

        self._add_card_item_tags_edit = QLineEdit()
        self._add_card_item_tags_edit.setPlaceholderText("item")
        self._add_card_item_tags_edit.setText(_tag_list_text(current_add_card_item_tags))
        topic_form.addRow("Add Card item-button tags:", self._add_card_item_tags_edit)

        self._topic_postpone_enabled_cb = QCheckBox(
            "Enable red Postpone button on topic cards"
        )
        self._topic_postpone_enabled_cb.setChecked(bool(current_topic_postpone_enabled))
        topic_form.addRow("", self._topic_postpone_enabled_cb)

        self._topic_postpone_mode_combo = QComboBox()
        self._topic_postpone_mode_combo.addItem("Timed snooze", "timed")
        self._topic_postpone_mode_combo.addItem("Session only", "session")
        selected_mode = (
            "session"
            if str(current_topic_postpone_mode or "").strip().lower() == "session"
            else "timed"
        )
        for idx in range(self._topic_postpone_mode_combo.count()):
            if self._topic_postpone_mode_combo.itemData(idx) == selected_mode:
                self._topic_postpone_mode_combo.setCurrentIndex(idx)
                break
        topic_form.addRow("Postpone mode:", self._topic_postpone_mode_combo)

        self._topic_postpone_minutes_spin = QSpinBox()
        self._topic_postpone_minutes_spin.setRange(1, 1440)
        try:
            postpone_minutes = int(current_topic_postpone_minutes)
        except Exception:
            postpone_minutes = 30
        self._topic_postpone_minutes_spin.setValue(max(1, min(1440, postpone_minutes)))
        self._topic_postpone_minutes_spin.setSuffix(" min")
        topic_form.addRow("Timed snooze duration:", self._topic_postpone_minutes_spin)

        def _sync_topic_postpone_widgets() -> None:
            enabled = bool(self._topic_postpone_enabled_cb.isChecked())
            self._topic_postpone_mode_combo.setEnabled(enabled)
            mode = str(self._topic_postpone_mode_combo.currentData() or "timed")
            self._topic_postpone_minutes_spin.setEnabled(enabled and mode == "timed")

        self._topic_postpone_enabled_cb.toggled.connect(
            lambda _checked: _sync_topic_postpone_widgets()
        )
        self._topic_postpone_mode_combo.currentIndexChanged.connect(
            lambda _idx: _sync_topic_postpone_widgets()
        )
        _sync_topic_postpone_widgets()

        general_layout.addLayout(topic_form)
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
    def prefer_web_card_resume_in_original_page(self) -> bool:
        return bool(self._prefer_web_card_resume_in_original_page_cb.isChecked())

    @property
    def use_fail_pass_on_items(self) -> bool:
        return bool(self._use_fail_pass_on_items_cb.isChecked())

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
        return _normalize_tag_list(self._topic_tags_edit.text())

    @property
    def add_card_topic_tags(self) -> list[str]:
        return _normalize_tag_list(self._add_card_topic_tags_edit.text())

    @property
    def add_card_item_tags(self) -> list[str]:
        return _normalize_tag_list(self._add_card_item_tags_edit.text())

    @property
    def topic_postpone_enabled(self) -> bool:
        return bool(self._topic_postpone_enabled_cb.isChecked())

    @property
    def topic_postpone_mode(self) -> str:
        return str(self._topic_postpone_mode_combo.currentData() or "timed")

    @property
    def topic_postpone_minutes(self) -> int:
        return int(self._topic_postpone_minutes_spin.value())
