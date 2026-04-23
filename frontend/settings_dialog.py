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
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from ..backend.custom_schedule import (
        configured_custom_schedule_default_mode,
        configured_custom_schedule_presets,
        normalize_custom_schedule_mode,
        normalize_custom_schedule_preset,
    )
except ImportError:
    from backend.custom_schedule import (  # type: ignore
        configured_custom_schedule_default_mode,
        configured_custom_schedule_presets,
        normalize_custom_schedule_mode,
        normalize_custom_schedule_preset,
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
        "id": "add_writing",
        "label": "Add to Markdown",
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
        "id": "open_knowledge_tree",
        "label": "Open Knowledge Tree",
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
        "id": "append_tags_reviewer",
        "label": "Append Tags To Reviewed Card",
        "default": "Alt+T",
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
        current_extract_priority: float = 40.0,
        current_extract_priority_multiplier: float = 0.98,
        current_extract_mark_topic: bool = True,
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
        current_writing_wrap_enabled: bool = True,
        current_writing_focus_mode: bool = False,
        current_writing_highlight_current_line: bool = True,
        current_writing_restore_bookmark: bool = True,
        current_writing_progress_visible: bool = True,
        current_writing_progress_default_scope: str = "today",
        current_writing_word_count_mode: str = "simple",
        current_custom_schedule_default_mode: str = "minimum_cadence",
        current_custom_schedule_presets: list[dict] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Incremento Settings")
        self.setMinimumWidth(620)
        self.resize(720, 640)
        self._defaults = default_shortcuts()
        self._editors: dict[str, QKeySequenceEdit] = {}

        root = QVBoxLayout(self)

        tabs = QTabWidget()
        root.addWidget(tabs)

        def _scrollable_tab(content: QWidget) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(content)
            return scroll

        def _section_title(text: str) -> QLabel:
            lbl = QLabel(f"<b>{text}</b>")
            lbl.setWordWrap(True)
            return lbl

        def _section_form() -> QFormLayout:
            form = QFormLayout()
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(8)
            return form

        extraction_tab = QWidget()
        extraction_layout = QVBoxLayout(extraction_tab)
        extraction_layout.setSpacing(8)

        extraction_hint = QLabel(
            "Choose how extracted content opens by default, how its priority is derived,"
            " whether extracts should start as topics, and which provenance links should be appended."
        )
        extraction_hint.setWordWrap(True)
        extraction_layout.addWidget(extraction_hint)

        extraction_layout.addWidget(_section_title("Extraction"))
        extraction_hint = QLabel(
            "Controls how extracted text opens in Add Card and which source links are appended."
        )
        extraction_hint.setWordWrap(True)
        extraction_layout.addWidget(extraction_hint)

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

        self._extract_priority_spin = QDoubleSpinBox()
        self._extract_priority_spin.setRange(0.0, 100.0)
        self._extract_priority_spin.setDecimals(1)
        self._extract_priority_spin.setSingleStep(1.0)
        try:
            extract_priority = float(current_extract_priority)
        except Exception:
            extract_priority = 40.0 if current_priority_lower_is_more_important else 60.0
        self._extract_priority_spin.setValue(max(0.0, min(100.0, extract_priority)))
        important_end = "0" if current_priority_lower_is_more_important else "100"
        self._extract_priority_spin.setToolTip(
            f"Priority assigned to newly extracted cards. {important_end} is the most important end."
        )
        extraction_form.addRow("Fallback extract priority:", self._extract_priority_spin)

        self._extract_priority_multiplier_spin = QDoubleSpinBox()
        self._extract_priority_multiplier_spin.setRange(0.01, 10.0)
        self._extract_priority_multiplier_spin.setDecimals(4)
        self._extract_priority_multiplier_spin.setSingleStep(0.01)
        try:
            extract_multiplier = float(current_extract_priority_multiplier)
        except Exception:
            extract_multiplier = 0.98 if current_priority_lower_is_more_important else 1.02
        self._extract_priority_multiplier_spin.setValue(max(0.01, min(10.0, extract_multiplier)))
        multiplier_hint = (
            "For a source priority of 6, multiplier 0.98 creates extract priority 5.88."
            if current_priority_lower_is_more_important
            else "For a source priority of 60, multiplier 1.02 creates extract priority 61.2."
        )
        self._extract_priority_multiplier_spin.setToolTip(
            "New extracts use source priority × this value when the source card is known. "
            + multiplier_hint
        )
        extraction_form.addRow("Source priority multiplier:", self._extract_priority_multiplier_spin)

        self._extract_mark_topic_cb = QCheckBox("Mark extracted cards as topics")
        self._extract_mark_topic_cb.setChecked(bool(current_extract_mark_topic))
        extraction_form.addRow("", self._extract_mark_topic_cb)

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

        extraction_layout.addLayout(extraction_form)
        extraction_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(extraction_tab), "Extraction")

        review_tab = QWidget()
        review_layout = QVBoxLayout(review_tab)
        review_layout.setSpacing(8)

        review_hint = QLabel(
            "Review settings control how priority numbers are interpreted, which extra prompts appear after answering,"
            " how browser cards resume, and how optional repeating schedule rules behave."
        )
        review_hint.setWordWrap(True)
        review_layout.addWidget(review_hint)

        review_layout.addWidget(_section_title("Review Behavior"))
        review_hint = QLabel(
            "Controls how review buttons behave and whether review flow asks for extra input after answering."
        )
        review_hint.setWordWrap(True)
        review_layout.addWidget(review_hint)

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
        priority_direction_hint = QLabel(
            "If you switch this direction, Incremento can optionally invert stored priorities for the current profile on save."
        )
        priority_direction_hint.setWordWrap(True)
        priority_direction_layout.addWidget(priority_direction_hint)
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

        review_layout.addLayout(review_form)

        review_layout.addWidget(_section_title("Custom Scheduling"))
        custom_schedule_hint = QLabel(
            "Browser right-click can apply repeating schedule rules such as every 2 days or monthly. "
            "Manage the default rule behavior and quick presets here."
        )
        custom_schedule_hint.setWordWrap(True)
        review_layout.addWidget(custom_schedule_hint)

        custom_schedule_form = _section_form()

        self._custom_schedule_default_mode_combo = QComboBox()
        self._custom_schedule_default_mode_combo.addItem(
            "Minimum cadence",
            "minimum_cadence",
        )
        self._custom_schedule_default_mode_combo.addItem(
            "Repeat exactly",
            "fixed_repeat",
        )
        self._custom_schedule_default_mode_combo.addItem(
            "One-time set due",
            "one_time",
        )
        selected_custom_schedule_mode = normalize_custom_schedule_mode(
            current_custom_schedule_default_mode
        )
        for idx in range(self._custom_schedule_default_mode_combo.count()):
            if self._custom_schedule_default_mode_combo.itemData(idx) == selected_custom_schedule_mode:
                self._custom_schedule_default_mode_combo.setCurrentIndex(idx)
                break
        custom_schedule_form.addRow(
            "Default behavior:",
            self._custom_schedule_default_mode_combo,
        )

        self._custom_schedule_presets_edit = QPlainTextEdit()
        self._custom_schedule_presets_edit.setPlaceholderText(
            "One preset per line: Label | Value | Unit\n"
            "Example: Every 2 days | 2 | days"
        )
        presets_lines = []
        for preset in configured_custom_schedule_presets(
            {"custom_schedule_presets": current_custom_schedule_presets}
        ):
            normalized = normalize_custom_schedule_preset(preset)
            presets_lines.append(
                f"{normalized['label']} | {normalized['interval_value']} | {normalized['interval_unit']}"
            )
        self._custom_schedule_presets_edit.setPlainText("\n".join(presets_lines))
        self._custom_schedule_presets_edit.setMinimumHeight(120)
        custom_schedule_form.addRow("Quick presets:", self._custom_schedule_presets_edit)

        custom_schedule_form.addRow(
            "",
            QLabel("Units: days, weeks, months. Lines with invalid values are ignored."),
        )
        review_layout.addLayout(custom_schedule_form)
        review_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(review_tab), "Review")

        topics_tab = QWidget()
        topics_layout = QVBoxLayout(topics_tab)
        topics_layout.setSpacing(8)

        topics_hint = QLabel(
            "Topic settings control which cards are treated as topics, which tags the Add Card topic and item buttons apply,"
            " and whether topic reviews show the red Postpone action."
        )
        topics_hint.setWordWrap(True)
        topics_layout.addWidget(topics_hint)

        topics_layout.addWidget(_section_title("Topic Cards"))
        topic_section_hint = QLabel(
            "Topic cards use More / Same / Less buttons and A-factor scheduling instead of flashcard grading."
            " You can also add a red Postpone button for difficult topics."
        )
        topic_section_hint.setWordWrap(True)
        topics_layout.addWidget(topic_section_hint)

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

        topics_layout.addLayout(topic_form)
        topics_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(topics_tab), "Topics")

        writing_tab = QWidget()
        writing_layout = QVBoxLayout(writing_tab)
        writing_layout.setSpacing(8)

        writing_hint = QLabel(
            "Choose the default behavior for markdown writing cards. After a card is opened once, its own saved editor state takes over. "
            "The progress widget shows per-card word progress for today, the current card-open session, or all time."
        )
        writing_hint.setWordWrap(True)
        writing_layout.addWidget(writing_hint)

        writing_layout.addWidget(_section_title("Editor Defaults"))
        writing_form = _section_form()

        self._writing_wrap_enabled_cb = QCheckBox("Wrap long lines in writing cards")
        self._writing_wrap_enabled_cb.setChecked(bool(current_writing_wrap_enabled))
        writing_form.addRow("", self._writing_wrap_enabled_cb)

        self._writing_focus_mode_cb = QCheckBox("Start writing cards in focus mode")
        self._writing_focus_mode_cb.setChecked(bool(current_writing_focus_mode))
        writing_form.addRow("", self._writing_focus_mode_cb)

        self._writing_highlight_current_line_cb = QCheckBox("Highlight the current writing line")
        self._writing_highlight_current_line_cb.setChecked(bool(current_writing_highlight_current_line))
        writing_form.addRow("", self._writing_highlight_current_line_cb)

        self._writing_restore_bookmark_cb = QCheckBox(
            "Restore saved bookmark line when reopening writing cards"
        )
        self._writing_restore_bookmark_cb.setChecked(bool(current_writing_restore_bookmark))
        writing_form.addRow("", self._writing_restore_bookmark_cb)
        writing_layout.addLayout(writing_form)

        writing_layout.addWidget(_section_title("Progress"))
        writing_progress_form = _section_form()

        self._writing_progress_visible_cb = QCheckBox("Show the writing progress counter in the dock")
        self._writing_progress_visible_cb.setChecked(bool(current_writing_progress_visible))
        writing_progress_form.addRow("", self._writing_progress_visible_cb)

        self._writing_progress_scope_combo = QComboBox()
        self._writing_progress_scope_combo.addItem("Today", "today")
        self._writing_progress_scope_combo.addItem("Session", "session")
        self._writing_progress_scope_combo.addItem("All-time", "all_time")
        selected_progress_scope = str(current_writing_progress_default_scope or "today").strip().lower()
        if selected_progress_scope not in {"today", "session", "all_time"}:
            selected_progress_scope = "today"
        for idx in range(self._writing_progress_scope_combo.count()):
            if self._writing_progress_scope_combo.itemData(idx) == selected_progress_scope:
                self._writing_progress_scope_combo.setCurrentIndex(idx)
                break
        writing_progress_form.addRow("Default progress scope:", self._writing_progress_scope_combo)
        writing_progress_form.addRow(
            "",
            QLabel("Session resets when you leave and reopen that writing card."),
        )

        self._writing_word_count_mode_combo = QComboBox()
        self._writing_word_count_mode_combo.addItem("Simple whitespace", "simple")
        self._writing_word_count_mode_combo.addItem("Word-like", "word_like")
        selected_word_count_mode = str(current_writing_word_count_mode or "simple").strip().lower()
        if selected_word_count_mode not in {"simple", "word_like"}:
            selected_word_count_mode = "simple"
        for idx in range(self._writing_word_count_mode_combo.count()):
            if self._writing_word_count_mode_combo.itemData(idx) == selected_word_count_mode:
                self._writing_word_count_mode_combo.setCurrentIndex(idx)
                break
        writing_progress_form.addRow("Word counting mode:", self._writing_word_count_mode_combo)
        writing_progress_form.addRow(
            "",
            QLabel("Word-like mode approximates Microsoft Word better for punctuation, apostrophes, and hyphenated words."),
        )
        writing_layout.addLayout(writing_progress_form)
        writing_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(writing_tab), "Writing")

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

        tabs.addTab(_scrollable_tab(shortcuts_tab), "Shortcuts")

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
    def extract_priority(self) -> float:
        return round(float(self._extract_priority_spin.value()), 4)

    @property
    def extract_priority_multiplier(self) -> float:
        return round(float(self._extract_priority_multiplier_spin.value()), 4)

    @property
    def extract_mark_topic(self) -> bool:
        return bool(self._extract_mark_topic_cb.isChecked())

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

    @property
    def writing_wrap_enabled(self) -> bool:
        return bool(self._writing_wrap_enabled_cb.isChecked())

    @property
    def writing_focus_mode(self) -> bool:
        return bool(self._writing_focus_mode_cb.isChecked())

    @property
    def writing_highlight_current_line(self) -> bool:
        return bool(self._writing_highlight_current_line_cb.isChecked())

    @property
    def writing_restore_bookmark(self) -> bool:
        return bool(self._writing_restore_bookmark_cb.isChecked())

    @property
    def writing_progress_visible(self) -> bool:
        return bool(self._writing_progress_visible_cb.isChecked())

    @property
    def writing_progress_default_scope(self) -> str:
        raw = str(self._writing_progress_scope_combo.currentData() or "today").strip().lower()
        return raw if raw in {"today", "session", "all_time"} else "today"

    @property
    def writing_word_count_mode(self) -> str:
        raw = str(self._writing_word_count_mode_combo.currentData() or "simple").strip().lower()
        return raw if raw in {"simple", "word_like"} else "simple"

    @property
    def custom_schedule_default_mode(self) -> str:
        return normalize_custom_schedule_mode(
            self._custom_schedule_default_mode_combo.currentData()
        )

    @property
    def custom_schedule_presets(self) -> list[dict]:
        presets: list[dict] = []
        for index, raw_line in enumerate(
            self._custom_schedule_presets_edit.toPlainText().splitlines()
        ):
            line = str(raw_line or "").strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 3:
                continue
            label, interval_value, interval_unit = parts
            try:
                preset = normalize_custom_schedule_preset(
                    {
                        "label": label,
                        "interval_value": int(interval_value),
                        "interval_unit": interval_unit,
                        "sort_order": index,
                    },
                    index=index,
                )
            except Exception:
                continue
            presets.append(preset)
        return presets or configured_custom_schedule_presets()
