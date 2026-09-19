from aqt.qt import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QKeySequence,
    QKeySequenceEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStyle,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from ..backend.i18n import LANGUAGES, normalize_language_choice, t
    from ..backend.config_service import (
        DEFAULT_TOPIC_DONE_TAG, configured_reviewer_button_visibility,
        configured_reviewer_button_group_visible,
        configured_topic_done_tag, normalize_pdf_appearance_mode,
        normalize_topic_done_tag,
    )
    from ..backend.custom_schedule import (
        configured_custom_schedule_default_mode,
        configured_custom_schedule_presets,
        normalize_custom_schedule_mode,
        normalize_custom_schedule_preset,
    )
except ImportError:
    from backend.i18n import LANGUAGES, normalize_language_choice, t
    from backend.config_service import (  # type: ignore
        DEFAULT_TOPIC_DONE_TAG, configured_reviewer_button_visibility,
        configured_reviewer_button_group_visible,
        configured_topic_done_tag, normalize_pdf_appearance_mode,
        normalize_topic_done_tag,
    )
    from backend.custom_schedule import (  # type: ignore
        configured_custom_schedule_default_mode,
        configured_custom_schedule_presets,
        normalize_custom_schedule_mode,
        normalize_custom_schedule_preset,
    )

try:
    from .shortcut_conflicts import find_shortcut_conflicts
except ImportError:
    from shortcut_conflicts import find_shortcut_conflicts  # type: ignore


SHORTCUT_ACTION_SPECS = [
    {
        "id": "command_palette",
        "label": "Command Palette",
        "default": "Ctrl+K",
        "group": "Navigation",
        "keywords": ("actions", "commands", "open"),
    },
    {
        "id": "activity_center",
        "label": "Activity Center",
        "default": "",
        "group": "Navigation",
        "keywords": ("tasks", "background", "progress", "errors", "downloads"),
    },
    {
        "id": "start_learning",
        "label": "Start Incremental Learning",
        "default": "",
        "group": "Study",
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
        "id": "add_markdown_document",
        "label": "Add Markdown Document",
        "default": "",
        "keywords": ("md", "markdown", "document", "read"),
    },
    {
        "id": "edit_markdown_document",
        "label": "Edit Current Markdown Document",
        "default": "",
        "keywords": ("md", "markdown", "edit", "document"),
    },
    {
        "id": "youtube_video",
        "label": "Add Video",
        "default": "",
    },
    {
        "id": "add_writing",
        "label": "Add Markdown Writing",
        "default": "",
    },
    {
        "id": "add_web_page",
        "label": "Web Page",
        "default": "",
    },
    {
        "id": "add_local_file",
        "label": "Add Local File",
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
        "id": "search_current_document",
        "label": "Find In Current Document",
        "default": "Ctrl+F",
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
        "label": "Quick Open Content",
        "default": "Ctrl+Alt+P",
    },
    {
        "id": "document_bookshelf",
        "label": "Document Bookshelf",
        "default": "Alt+Shift+P",
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
        "id": "toggle_reviewer_buttons",
        "label": "Toggle Reviewer Buttons",
        "default": "",
        "group": "Review",
        "keywords": ("show", "hide", "done", "postpone", "extract"),
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

def localized_shortcut_action_specs() -> list[dict]:
    """Translate labels at display time while retaining English search aliases."""
    return [
        {
            **spec,
            "label": t("shortcut_" + spec["id"]),
            "group": t("shortcut_group_" + spec["group"].lower()) if spec.get("group") else "",
            "keywords": (*spec.get("keywords", ()), spec["label"]),
        }
        for spec in SHORTCUT_ACTION_SPECS
    ]


WRITING_BACKUP_TIER_OPTIONS = (
    ("1m", "1 minute"),
    ("5m", "5 minutes"),
    ("15m", "15 minutes"),
    ("30m", "30 minutes"),
    ("1h", "1 hour"),
    ("6h", "6 hours"),
    ("1d", "1 day"),
    ("7d", "7 days"),
)
DEFAULT_WRITING_BACKUP_TIERS = ("1m", "30m", "1d")


def default_shortcuts() -> dict[str, str]:
    return {spec["id"]: spec["default"] for spec in SHORTCUT_ACTION_SPECS}


def _migrated_shortcuts(
    current_shortcuts: dict[str, str] | None,
) -> dict[str, str]:
    """Map the former PDF-only action onto the document bookshelf action."""
    current = {
        str(action_id): str(shortcut or "").strip()
        for action_id, shortcut in dict(current_shortcuts or {}).items()
    }
    if "document_bookshelf" not in current and "pdf_bookshelf" in current:
        current["document_bookshelf"] = current["pdf_bookshelf"]
    current.pop("pdf_bookshelf", None)
    return current


def resolved_runtime_shortcuts(current_shortcuts: dict[str, str] | None) -> dict[str, str]:
    """Merge shortcut defaults and give the bookshelf its requested key on conflict."""
    resolved = default_shortcuts()
    resolved.update(_migrated_shortcuts(current_shortcuts))

    def identity(shortcut: str) -> str:
        return "".join(str(shortcut or "").split()).casefold()

    bookshelf_key = identity(resolved.get("document_bookshelf", ""))
    quick_open_key = identity(resolved.get("quick_open_pdf", ""))
    if bookshelf_key and bookshelf_key == quick_open_key:
        # Older profiles may already use Option+Shift+P for Quick Open Content.
        # A single key cannot trigger both dialogs, and the dedicated bookshelf
        # is the action explicitly assigned to that default. Quick Open Content
        # remains available from the menu or after assigning it another key.
        resolved["quick_open_pdf"] = ""
    return resolved


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


def _normalize_name_list(raw: list[str] | str | tuple[str, ...] | set[str] | None) -> list[str]:
    if isinstance(raw, str):
        parts = raw.replace(",", "\n").splitlines()
    elif isinstance(raw, (list, tuple, set)):
        parts = list(raw)
    else:
        parts = []

    names: list[str] = []
    seen: set[str] = set()
    for item in parts:
        name = str(item or "").strip()
        if not name:
            continue
        normalized = name.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        names.append(name)
    return names


def _name_list_text(raw: list[str] | str | tuple[str, ...] | set[str] | None) -> str:
    return "\n".join(_normalize_name_list(raw))


class IncrementoSettingsDialog(QDialog):
    def __init__(
        self,
        current_shortcuts: dict[str, str],
        note_type_names: list[str] | None = None,
        current_extract_notetype: str = "",
        current_extract_priority: float = 40.0,
        current_extract_priority_multiplier: float = 0.98,
        current_extract_mark_topic: bool = True,
        current_extract_copy_source_tags: bool = False,
        current_extract_highlight_when_extracting: bool = True,
        current_pdf_highlight_extract_field: int = 1,
        current_pdf_snapshot_auto_field_enabled: bool = False,
        extract_source_links: dict[str, bool] | bool | None = None,
        current_priority_lower_is_more_important: bool = True,
        current_show_priority_dialog_after_answer: bool = False,
        current_reviewer_priority_badge_card_types: dict[str, bool] | None = None,
        current_reviewer_button_visibility: dict[str, bool] | None = None,
        current_reviewer_button_group_visible: bool = True,
        current_show_incremento_fields: bool = False,
        current_remember_browser_card_scroll: bool = True,
        current_pdf_scroll_to_top_on_page_change: bool = True,
        current_pdf_default_appearance: str = "original",
        current_pdf_force_default_appearance: bool = False,
        current_prefer_web_card_resume_in_original_page: bool = True,
        current_track_web_window_with_extension: bool = True,
        current_use_fail_pass_on_items: bool = True,
        current_item_skip_enabled: bool = False,
        current_item_skip_minutes: int = 30,
        current_auto_timer_enabled: bool = False,
        current_auto_timer_card_types: dict[str, bool] | None = None,
        current_auto_timer_tags: list[str] | str | None = None,
        current_auto_timer_minutes: int = 30,
        current_timer_completion_beep: bool = True,
        current_topic_card_types: dict[str, bool] | None = None,
        current_topic_card_tags: list[str] | str | None = None,
        current_default_topic_a_factor: float = 3.5,
        current_topic_more_adjustment_percent: float = 10.0,
        current_topic_less_adjustment_percent: float = 10.0,
        current_topic_maximum_interval_days: int = 36500,
        current_topic_done_tag: str = DEFAULT_TOPIC_DONE_TAG,
        current_add_card_topic_tags: list[str] | str | None = None,
        current_add_card_item_tags: list[str] | str | None = None,
        current_auto_create_topics_deck: bool = True,
        current_auto_create_topics_deck_profiles: list[str] | str | None = None,
        available_profile_names: list[str] | None = None,
        current_topic_postpone_enabled: bool = False,
        current_topic_postpone_mode: str = "timed",
        current_topic_postpone_minutes: int = 30,
        current_writing_wrap_enabled: bool = True,
        current_writing_focus_mode: bool = False,
        current_writing_preview_visible: bool = True,
        current_writing_highlight_current_line: bool = True,
        current_writing_restore_bookmark: bool = True,
        current_writing_backups_enabled: bool = True,
        current_writing_backup_tiers: list[str] | tuple[str, ...] | None = None,
        current_writing_progress_visible: bool = True,
        current_writing_progress_default_scope: str = "today",
        current_writing_word_count_mode: str = "simple",
        current_custom_schedule_default_mode: str = "minimum_cadence",
        current_custom_schedule_presets: list[dict] | None = None,
        open_database_editor_callback=None,
        parent=None,
        current_ui_language: str = "auto",
        language_pack_context: tuple[str, str] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(t('settings_incremento_settings'))
        self.setMinimumWidth(620)
        self.resize(720, 640)
        self._defaults = default_shortcuts()
        self._editors: dict[str, QKeySequenceEdit] = {}
        self._open_database_editor_callback = open_database_editor_callback

        root = QVBoxLayout(self)

        tabs = QTabWidget()
        self._tabs = tabs
        root.addWidget(tabs)

        language_tab = QWidget()
        language_layout = QVBoxLayout(language_tab)
        language_label = QLabel(t("settings_language_label"))
        self._language_combo = QComboBox()
        self._language_combo.setAccessibleName(t("settings_language_label"))
        language_label.setBuddy(self._language_combo)
        self._language_combo.addItem(t("settings_language_auto"), "auto")
        for code, label in LANGUAGES:
            self._language_combo.addItem(label, code)
        selected_language = normalize_language_choice(current_ui_language)
        for index in range(self._language_combo.count()):
            if self._language_combo.itemData(index) == selected_language:
                self._language_combo.setCurrentIndex(index)
                break
        language_layout.addWidget(language_label)
        language_layout.addWidget(self._language_combo)
        self._language_restart_hint = QLabel(t("settings_language_restart"))
        self._language_restart_hint.setWordWrap(True)
        language_layout.addWidget(self._language_restart_hint)
        self._language_pack_controls = None
        if language_pack_context is not None:
            from .language_pack_settings import LanguagePackControls
            self._language_pack_controls = LanguagePackControls(
                self._language_combo, *language_pack_context, parent=language_tab,
            )
            self._language_pack_controls.select_choice(selected_language)
            language_layout.addWidget(self._language_pack_controls)
        language_layout.addStretch(1)

        def _scrollable_tab(content: QWidget) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(content)
            return scroll

        tabs.addTab(_scrollable_tab(language_tab), t("settings_language_tab"))

        def _section_title(text: str) -> QLabel:
            lbl = QLabel(f"<b>{text}</b>")
            lbl.setWordWrap(True)
            return lbl

        def _subsection_title(text: str) -> QLabel:
            lbl = QLabel(f"<b>{text}</b>")
            lbl.setWordWrap(True)
            return lbl

        def _section_form() -> QFormLayout:
            form = QFormLayout()
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(8)
            return form

        def _section_body() -> QVBoxLayout:
            layout = QVBoxLayout()
            layout.setContentsMargins(12, 0, 0, 0)
            layout.setSpacing(8)
            return layout

        def _note_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            return lbl

        def _info_button(tooltip_text: str) -> QToolButton:
            btn = QToolButton()
            btn.setText("i")
            btn.setAutoRaise(True)
            btn.setToolTip(tooltip_text)
            btn.setFixedSize(15, 15)
            btn.setStyleSheet(
                "QToolButton {"
                "  color: white;"
                "  background-color: #4a7ab5;"
                "  border: none;"
                "  border-radius: 7px;"
                "  font-size: 9px;"
                "  font-style: italic;"
                "  font-weight: bold;"
                "  padding-bottom: 1px;"
                "}"
                "QToolButton:hover { background-color: #3060a0; }"
            )
            return btn

        def _label_with_info(text: str, tooltip_text: str | None = None) -> QWidget | str:
            if not tooltip_text:
                return text
            wrap = QWidget()
            layout = QHBoxLayout(wrap)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            label = QLabel(text)
            layout.addWidget(label)
            layout.addWidget(_info_button(tooltip_text))
            layout.addStretch(1)
            return wrap

        extraction_tab = QWidget()
        extraction_layout = QVBoxLayout(extraction_tab)
        extraction_layout.setSpacing(8)

        extraction_hint = QLabel(
            t('settings_choose_how_extracted_content_opens_by_default_how_its')
        )
        extraction_hint.setWordWrap(True)
        extraction_layout.addWidget(extraction_hint)

        extraction_layout.addWidget(_section_title(t('settings_card_creation')))

        extraction_form = _section_form()

        self._extract_notetype_combo = QComboBox()
        self._extract_notetype_combo.addItem(t('settings_use_current_add_card_type'), "")
        for name in note_type_names or []:
            self._extract_notetype_combo.addItem(name, name)

        selected_value = str(current_extract_notetype or "").strip()
        for idx in range(self._extract_notetype_combo.count()):
            if self._extract_notetype_combo.itemData(idx) == selected_value:
                self._extract_notetype_combo.setCurrentIndex(idx)
                break

        extraction_form.addRow(
            _label_with_info(
                t('settings_default_extract_card_type'),
                t('settings_this_is_used_by_extract_card_when_it_creates'),
            ),
            self._extract_notetype_combo,
        )

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
            t("settings_priority_assigned", important_end=important_end)
        )
        extraction_form.addRow(
            _label_with_info(
                t('settings_fallback_extract_priority'),
                t("settings_priority_fallback_help", important_end=important_end),
            ),
            self._extract_priority_spin,
        )

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
            t("settings_multiplier_lower")
            if current_priority_lower_is_more_important
            else t("settings_multiplier_higher")
        )
        self._extract_priority_multiplier_spin.setToolTip(
            t("settings_multiplier_tooltip", example=multiplier_hint)
        )
        extraction_form.addRow(
            _label_with_info(
                t('settings_source_priority_multiplier'),
                t("settings_multiplier_help", example=multiplier_hint),
            ),
            self._extract_priority_multiplier_spin,
        )

        self._extract_mark_topic_cb = QCheckBox(t('settings_mark_extracted_cards_as_topics'))
        self._extract_mark_topic_cb.setChecked(bool(current_extract_mark_topic))
        extraction_form.addRow("", self._extract_mark_topic_cb)

        self._extract_copy_source_tags_cb = QCheckBox(t('settings_copy_source_card_tags_to_extracted_cards'))
        self._extract_copy_source_tags_cb.setChecked(bool(current_extract_copy_source_tags))
        extraction_form.addRow("", self._extract_copy_source_tags_cb)

        self._extract_highlight_when_extracting_cb = QCheckBox(t('settings_highlight_when_extracting'))
        self._extract_highlight_when_extracting_cb.setChecked(
            bool(current_extract_highlight_when_extracting)
        )
        extraction_form.addRow("", self._extract_highlight_when_extracting_cb)

        self._pdf_highlight_extract_field_spin = QSpinBox()
        self._pdf_highlight_extract_field_spin.setRange(1, 20)
        try:
            highlight_field = int(current_pdf_highlight_extract_field)
        except Exception:
            highlight_field = 1
        self._pdf_highlight_extract_field_spin.setValue(max(1, min(20, highlight_field)))
        extraction_form.addRow(
            _label_with_info(
                t('settings_pdf_highlight_card_target_field'),
                t('settings_when_you_create_a_card_from_a_pdf_highlight'),
            ),
            self._pdf_highlight_extract_field_spin,
        )

        self._pdf_snapshot_auto_field_enabled_cb = QCheckBox(
            t("settings_pdf_snapshot_auto_field")
        )
        self._pdf_snapshot_auto_field_enabled_cb.setChecked(
            bool(current_pdf_snapshot_auto_field_enabled)
        )
        extraction_form.addRow("", self._pdf_snapshot_auto_field_enabled_cb)

        extraction_layout.addLayout(extraction_form)
        extraction_layout.addWidget(_subsection_title(t('settings_saved_provenance')))

        provenance_hint = _note_label(
            t('settings_these_links_are_stored_in_dedicated_incremento_metadata_fields')
        )
        extraction_layout.addWidget(provenance_hint)

        provenance_form = _section_form()

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

        self._extract_pdf_links_cb = QCheckBox(t('settings_pdf_pages'))
        self._extract_pdf_links_cb.setChecked(source_link_cfg["pdf"])
        provenance_form.addRow(
            _label_with_info(
                t('settings_save_links_for'),
                t('settings_examples_a_pdf_page_reference_the_current_web_page'),
            ),
            self._extract_pdf_links_cb,
        )

        self._extract_web_links_cb = QCheckBox(t('settings_web_pages_urls'))
        self._extract_web_links_cb.setChecked(source_link_cfg["web"])
        provenance_form.addRow("", self._extract_web_links_cb)

        self._extract_parent_links_cb = QCheckBox(t('settings_parent_cards_in_extract_card'))
        self._extract_parent_links_cb.setChecked(source_link_cfg["parent"])
        provenance_form.addRow("", self._extract_parent_links_cb)

        extraction_layout.addLayout(provenance_form)
        extraction_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(extraction_tab), t('settings_extraction'))

        review_tab = QWidget()
        review_layout = QVBoxLayout(review_tab)
        review_layout.setSpacing(8)

        review_hint = QLabel(
            t('settings_review_settings_control_how_priority_numbers_are_interpreted_which')
        )
        review_hint.setWordWrap(True)
        review_layout.addWidget(review_hint)

        review_layout.addWidget(_section_title(t('settings_review_flow')))

        review_priority_form = _section_form()

        priority_direction_wrap = QWidget()
        priority_direction_layout = QVBoxLayout(priority_direction_wrap)
        priority_direction_layout.setContentsMargins(0, 0, 0, 0)
        priority_direction_layout.setSpacing(4)

        self._priority_direction_group = QButtonGroup(self)
        self._priority_lower_radio = QRadioButton(t('settings_lower_priority_number_is_more_important'))
        self._priority_higher_radio = QRadioButton(t('settings_higher_priority_number_is_more_important'))
        self._priority_direction_group.addButton(self._priority_lower_radio)
        self._priority_direction_group.addButton(self._priority_higher_radio)
        self._priority_lower_radio.setChecked(bool(current_priority_lower_is_more_important))
        self._priority_higher_radio.setChecked(not bool(current_priority_lower_is_more_important))

        priority_direction_layout.addWidget(self._priority_lower_radio)
        priority_direction_layout.addWidget(self._priority_higher_radio)
        priority_direction_hint = QLabel(
            t('settings_if_you_switch_this_direction_incremento_can_optionally_invert')
        )
        priority_direction_hint.setWordWrap(True)

        review_priority_form.addRow(
            _label_with_info(
                t('settings_priority_direction'),
                t('settings_this_decides_whether_smaller_numbers_mean_do_this_sooner'),
            ),
            priority_direction_wrap,
        )
        # Keep wrapping guidance in a full-width form row. Native macOS forms
        # do not reliably propagate height-for-width through a nested field.
        review_priority_form.addRow(priority_direction_hint)

        self._show_priority_dialog_after_answer_cb = QCheckBox(
            t('settings_show_priority_dialog_after_each_card_is_done_before')
        )
        self._show_priority_dialog_after_answer_cb.setChecked(
            bool(current_show_priority_dialog_after_answer)
        )
        review_priority_form.addRow("", self._show_priority_dialog_after_answer_cb)

        badge_types = current_reviewer_priority_badge_card_types or {}
        badge_visibility = QWidget()
        badge_visibility_layout = QVBoxLayout(badge_visibility)
        badge_visibility_layout.setContentsMargins(0, 0, 0, 0)
        badge_visibility_layout.setSpacing(4)
        self._reviewer_priority_badge_topics_cb = QCheckBox(t('settings_topic_cards'))
        self._reviewer_priority_badge_topics_cb.setChecked(
            bool(badge_types.get("topics", True))
        )
        badge_visibility_layout.addWidget(self._reviewer_priority_badge_topics_cb)
        self._reviewer_priority_badge_items_cb = QCheckBox(t('settings_item_and_other_cards'))
        self._reviewer_priority_badge_items_cb.setChecked(
            bool(badge_types.get("items", True))
        )
        badge_visibility_layout.addWidget(self._reviewer_priority_badge_items_cb)
        review_priority_form.addRow(
            _label_with_info(
                t('settings_show_reviewer_priority_badge_on'),
                t('settings_controls_the_floating_priority_a_factor_saved_time_and'),
            ),
            badge_visibility,
        )

        review_layout.addLayout(review_priority_form)

        review_layout.addWidget(_subsection_title(t('settings_reviewer_controls')))
        reviewer_controls_layout = _section_body()

        button_visibility = configured_reviewer_button_visibility(
            {"reviewer_button_visibility": current_reviewer_button_visibility}
        )
        self._reviewer_button_group_cb = QCheckBox(t('settings_show_review_button_group'))
        self._reviewer_button_group_cb.setChecked(
            configured_reviewer_button_group_visible(
                {"reviewer_button_group_visible": current_reviewer_button_group_visible}
            )
        )
        reviewer_controls_layout.addWidget(self._reviewer_button_group_cb)
        review_buttons = QWidget()
        review_buttons_layout = QHBoxLayout(review_buttons)
        review_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._reviewer_done_button_cb = QCheckBox(t('settings_done'))
        self._reviewer_postpone_button_cb = QCheckBox(t('settings_postpone'))
        self._reviewer_extract_button_cb = QCheckBox(t('settings_extract'))
        for key, checkbox in (
            ("done", self._reviewer_done_button_cb),
            ("postpone", self._reviewer_postpone_button_cb),
            ("extract", self._reviewer_extract_button_cb),
        ):
            checkbox.setChecked(button_visibility[key])
            review_buttons_layout.addWidget(checkbox)
        review_buttons_layout.addStretch(1)
        buttons_label = QLabel(t('settings_buttons_shown_in_the_review_bar_also_in_more'))
        buttons_label.setWordWrap(True)
        reviewer_controls_layout.addWidget(buttons_label)
        reviewer_controls_layout.addWidget(review_buttons)
        group_hint = QLabel(
            t('settings_assign_toggle_reviewer_buttons_in_the_shortcuts_tab_to')
        )
        group_hint.setWordWrap(True)
        reviewer_controls_layout.addWidget(group_hint)
        availability_hint = QLabel(
            t('settings_done_appears_on_topic_cards_postpone_appears_only_when')
        )
        availability_hint.setWordWrap(True)
        reviewer_controls_layout.addWidget(availability_hint)

        self._remember_browser_card_scroll_cb = QCheckBox(
            t('settings_remember_scrolling_position_in_browser_cards')
        )
        self._remember_browser_card_scroll_cb.setChecked(
            bool(current_remember_browser_card_scroll)
        )
        reviewer_controls_layout.addWidget(self._remember_browser_card_scroll_cb)

        self._pdf_scroll_to_top_on_page_change_cb = QCheckBox(
            t('settings_scroll_to_top_when_going_to_the_next_pdf')
        )
        self._pdf_scroll_to_top_on_page_change_cb.setChecked(
            bool(current_pdf_scroll_to_top_on_page_change)
        )
        reviewer_controls_layout.addWidget(self._pdf_scroll_to_top_on_page_change_cb)

        pdf_appearance_row = QWidget()
        pdf_appearance_layout = QHBoxLayout(pdf_appearance_row)
        pdf_appearance_layout.setContentsMargins(0, 0, 0, 0)
        pdf_appearance_layout.addWidget(QLabel(t("settings_pdf_appearance_default")))
        self._pdf_default_appearance_combo = QComboBox()
        for mode, label_key in (
            ("original", "settings_pdf_appearance_original"),
            ("dark", "settings_pdf_appearance_dark"),
            ("night", "settings_pdf_appearance_night"),
        ):
            self._pdf_default_appearance_combo.addItem(t(label_key), mode)
        selected_appearance = normalize_pdf_appearance_mode(
            current_pdf_default_appearance
        )
        for index in range(self._pdf_default_appearance_combo.count()):
            if self._pdf_default_appearance_combo.itemData(index) == selected_appearance:
                self._pdf_default_appearance_combo.setCurrentIndex(index)
                break
        pdf_appearance_layout.addWidget(self._pdf_default_appearance_combo)
        pdf_appearance_layout.addStretch(1)
        reviewer_controls_layout.addWidget(pdf_appearance_row)

        self._pdf_force_default_appearance_cb = QCheckBox(
            t("settings_pdf_appearance_force")
        )
        self._pdf_force_default_appearance_cb.setChecked(
            bool(current_pdf_force_default_appearance)
        )
        reviewer_controls_layout.addWidget(self._pdf_force_default_appearance_cb)
        pdf_appearance_hint = QLabel(t("settings_pdf_appearance_hint"))
        pdf_appearance_hint.setWordWrap(True)
        reviewer_controls_layout.addWidget(pdf_appearance_hint)

        self._prefer_web_card_resume_in_original_page_cb = QCheckBox(
            t('settings_prefer_resuming_embedded_web_card_media_in_the_original')
        )
        self._prefer_web_card_resume_in_original_page_cb.setChecked(
            bool(current_prefer_web_card_resume_in_original_page)
        )
        reviewer_controls_layout.addWidget(self._prefer_web_card_resume_in_original_page_cb)

        self._track_web_window_with_extension_cb = QCheckBox(
            t('settings_track_web_card_external_pages_via_chrome_extension_by')
        )
        self._track_web_window_with_extension_cb.setChecked(
            bool(current_track_web_window_with_extension)
        )
        reviewer_controls_layout.addWidget(self._track_web_window_with_extension_cb)

        self._use_fail_pass_on_items_cb = QCheckBox(
            t('settings_use_fail_pass_buttons_on_items')
        )
        self._use_fail_pass_on_items_cb.setChecked(
            bool(current_use_fail_pass_on_items)
        )
        reviewer_controls_layout.addWidget(self._use_fail_pass_on_items_cb)

        self._show_incremento_fields_cb = QCheckBox(
            t('settings_show_incremento_metadata_ocr_fields_in_browser_and_note')
        )
        self._show_incremento_fields_cb.setChecked(bool(current_show_incremento_fields))
        reviewer_controls_layout.addWidget(self._show_incremento_fields_cb)

        review_layout.addLayout(reviewer_controls_layout)

        review_layout.addWidget(_subsection_title(t('settings_item_skip')))
        item_skip_layout = _section_body()

        self._item_skip_enabled_cb = QCheckBox(t('settings_enable_timed_skip_button_on_items'))
        self._item_skip_enabled_cb.setChecked(bool(current_item_skip_enabled))
        item_skip_layout.addWidget(self._item_skip_enabled_cb)

        item_skip_row = QHBoxLayout()
        item_skip_row.setContentsMargins(0, 0, 0, 0)
        item_skip_row.setSpacing(8)
        item_skip_row.addWidget(QLabel(t('settings_skip_duration')))

        self._item_skip_minutes_spin = QSpinBox()
        self._item_skip_minutes_spin.setRange(1, 1440)
        try:
            item_skip_minutes = int(current_item_skip_minutes)
        except Exception:
            item_skip_minutes = 30
        self._item_skip_minutes_spin.setValue(max(1, min(1440, item_skip_minutes)))
        self._item_skip_minutes_spin.setSuffix(t('settings_min'))
        item_skip_row.addWidget(self._item_skip_minutes_spin)
        item_skip_row.addWidget(
            _info_button(
                t('settings_when_you_click_skip_on_an_item_card_incremento')
            )
        )
        item_skip_row.addStretch(1)
        item_skip_layout.addLayout(item_skip_row)

        def _sync_item_skip_widgets() -> None:
            enabled = bool(self._item_skip_enabled_cb.isChecked())
            self._item_skip_minutes_spin.setEnabled(enabled)

        self._item_skip_enabled_cb.toggled.connect(
            lambda _checked: _sync_item_skip_widgets()
        )
        _sync_item_skip_widgets()
        review_layout.addLayout(item_skip_layout)

        review_layout.addWidget(_section_title(t('settings_focus_timer')))
        timer_hint = QLabel(
            t('settings_automatically_start_the_focus_timer_when_a_matching_card')
        )
        timer_hint.setWordWrap(True)
        review_layout.addWidget(timer_hint)

        timer_form = _section_form()
        self._auto_timer_enabled_cb = QCheckBox(
            t('settings_automatically_start_focus_timer_on_matching_cards')
        )
        self._auto_timer_enabled_cb.setChecked(bool(current_auto_timer_enabled))
        timer_form.addRow("", self._auto_timer_enabled_cb)

        self._timer_completion_beep_cb = QCheckBox(
            t('settings_play_a_beep_when_the_focus_timer_finishes')
        )
        self._timer_completion_beep_cb.setChecked(bool(current_timer_completion_beep))
        timer_form.addRow("", self._timer_completion_beep_cb)

        timer_types = {
            "pdf": True,
            "epub": True,
            "video": False,
            "web": False,
            "writing": False,
            "local_file": False,
        }
        if isinstance(current_auto_timer_card_types, dict):
            for key in timer_types:
                if key in current_auto_timer_card_types:
                    timer_types[key] = bool(current_auto_timer_card_types.get(key))

        timer_types_wrap = QWidget()
        timer_types_layout = QVBoxLayout(timer_types_wrap)
        timer_types_layout.setContentsMargins(0, 0, 0, 0)
        timer_types_layout.setSpacing(4)

        self._auto_timer_pdf_cb = QCheckBox("PDF")
        self._auto_timer_pdf_cb.setChecked(timer_types["pdf"])
        timer_types_layout.addWidget(self._auto_timer_pdf_cb)

        self._auto_timer_epub_cb = QCheckBox("EPUB")
        self._auto_timer_epub_cb.setChecked(timer_types["epub"])
        timer_types_layout.addWidget(self._auto_timer_epub_cb)

        self._auto_timer_video_cb = QCheckBox(t('settings_video'))
        self._auto_timer_video_cb.setChecked(timer_types["video"])
        timer_types_layout.addWidget(self._auto_timer_video_cb)

        self._auto_timer_web_cb = QCheckBox(t('settings_web'))
        self._auto_timer_web_cb.setChecked(timer_types["web"])
        timer_types_layout.addWidget(self._auto_timer_web_cb)

        self._auto_timer_writing_cb = QCheckBox(t('settings_writing'))
        self._auto_timer_writing_cb.setChecked(timer_types["writing"])
        timer_types_layout.addWidget(self._auto_timer_writing_cb)

        self._auto_timer_local_file_cb = QCheckBox(t('settings_local_file'))
        self._auto_timer_local_file_cb.setChecked(timer_types["local_file"])
        timer_types_layout.addWidget(self._auto_timer_local_file_cb)

        timer_form.addRow(t("settings_card_types"), timer_types_wrap)

        self._auto_timer_tags_edit = QLineEdit()
        self._auto_timer_tags_edit.setPlaceholderText("tag1, tag2")
        self._auto_timer_tags_edit.setText(_tag_list_text(current_auto_timer_tags))
        timer_form.addRow(
            _label_with_info(
                t('settings_tags'),
                t('settings_optional_extra_filter_if_you_fill_this_in_the'),
            ),
            self._auto_timer_tags_edit,
        )

        self._auto_timer_minutes_spin = QSpinBox()
        self._auto_timer_minutes_spin.setRange(1, 1440)
        try:
            auto_timer_minutes = int(current_auto_timer_minutes)
        except Exception:
            auto_timer_minutes = 30
        self._auto_timer_minutes_spin.setValue(max(1, min(1440, auto_timer_minutes)))
        self._auto_timer_minutes_spin.setSuffix(t('settings_min'))
        timer_form.addRow(
            _label_with_info(
                t('settings_auto_start_duration'),
                t('settings_when_incremento_automatically_starts_the_focus_timer_for_a'),
            ),
            self._auto_timer_minutes_spin,
        )

        def _sync_auto_timer_widgets() -> None:
            enabled = bool(self._auto_timer_enabled_cb.isChecked())
            for widget in (
                self._auto_timer_pdf_cb,
                self._auto_timer_epub_cb,
                self._auto_timer_video_cb,
                self._auto_timer_web_cb,
                self._auto_timer_writing_cb,
                self._auto_timer_local_file_cb,
                self._auto_timer_tags_edit,
                self._auto_timer_minutes_spin,
            ):
                widget.setEnabled(enabled)

        self._auto_timer_enabled_cb.toggled.connect(
            lambda _checked: _sync_auto_timer_widgets()
        )
        _sync_auto_timer_widgets()
        review_layout.addLayout(timer_form)

        review_layout.addWidget(_section_title(t('settings_custom_scheduling')))
        custom_schedule_hint = QLabel(
            t('settings_browser_right_click_can_apply_repeating_schedule_rules_such')
        )
        custom_schedule_hint.setWordWrap(True)
        review_layout.addWidget(custom_schedule_hint)

        custom_schedule_form = _section_form()

        self._custom_schedule_default_mode_combo = QComboBox()
        self._custom_schedule_default_mode_combo.addItem(
            t('settings_minimum_cadence'),
            "minimum_cadence",
        )
        self._custom_schedule_default_mode_combo.addItem(
            t('settings_repeat_exactly'),
            "fixed_repeat",
        )
        self._custom_schedule_default_mode_combo.addItem(
            t('settings_one_time_set_due'),
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
            _label_with_info(
                t('settings_default_behavior'),
                t('settings_custom_schedule_behavior_help'),
            ),
            self._custom_schedule_default_mode_combo,
        )

        self._custom_schedule_presets_edit = QPlainTextEdit()
        self._custom_schedule_presets_edit.setPlaceholderText(
            t('settings_one_preset_per_line_label_value_unit_example_every')
        )
        presets_lines = []
        self._custom_schedule_source_presets = configured_custom_schedule_presets(
            {"custom_schedule_presets": current_custom_schedule_presets}
        )
        for preset in self._custom_schedule_source_presets:
            normalized = normalize_custom_schedule_preset(preset)
            presets_lines.append(
                f"{normalized['label']} | {normalized['interval_value']} | {normalized['interval_unit']}"
            )
        self._custom_schedule_presets_edit.setPlainText("\n".join(presets_lines))
        self._custom_schedule_presets_edit.setMinimumHeight(120)
        custom_schedule_form.addRow(
            _label_with_info(
                t('settings_quick_presets'),
                t('settings_these_appear_in_browser_scheduling_menus_for_one_click'),
            ),
            self._custom_schedule_presets_edit,
        )

        custom_schedule_form.addRow(
            "",
            QLabel(t('settings_units_days_weeks_months_lines_with_invalid_values_are')),
        )
        review_layout.addLayout(custom_schedule_form)
        review_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(review_tab), t('settings_review'))

        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setSpacing(8)

        advanced_hint = QLabel(
            t('settings_advanced_tools_expose_internal_incremento_runtime_data_for_inspection')
        )
        advanced_hint.setWordWrap(True)
        advanced_layout.addWidget(advanced_hint)

        advanced_layout.addWidget(_section_title(t('settings_profile_sqlite_database')))

        warning_row = QHBoxLayout()
        warning_row.setSpacing(10)

        warning_icon = QLabel()
        warning_icon.setPixmap(
            self.style()
            .standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            .pixmap(20, 20)
        )
        warning_row.addWidget(warning_icon)

        warning_copy = QLabel(
            t('settings_open_a_guarded_database_inspector_for_the_current_profile')
        )
        warning_copy.setWordWrap(True)
        warning_row.addWidget(warning_copy, 1)
        advanced_layout.addLayout(warning_row)

        advanced_button_row = QHBoxLayout()
        advanced_button_row.setSpacing(8)

        self._open_database_editor_btn = QPushButton(t('settings_open_database_editor'))
        self._open_database_editor_btn.clicked.connect(self._open_database_editor)
        self._open_database_editor_btn.setEnabled(callable(self._open_database_editor_callback))
        advanced_button_row.addWidget(self._open_database_editor_btn)

        advanced_note = QLabel(
            t('settings_the_editor_starts_read_only_sql_writes_stay_locked')
        )
        advanced_note.setWordWrap(True)
        advanced_button_row.addWidget(advanced_note, 1)
        advanced_layout.addLayout(advanced_button_row)

        advanced_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(advanced_tab), t('settings_advanced'))

        topics_tab = QWidget()
        topics_layout = QVBoxLayout(topics_tab)
        topics_layout.setSpacing(8)

        topics_hint = QLabel(
            t('settings_topic_settings_control_which_cards_are_treated_as_topics')
        )
        topics_hint.setWordWrap(True)
        topics_layout.addWidget(topics_hint)

        topics_layout.addWidget(_section_title(t('settings_topic_identity')))
        topic_section_hint = QLabel(
            t('settings_topic_cards_use_more_same_less_buttons_and_a')
        )
        topic_section_hint.setWordWrap(True)
        topics_layout.addWidget(topic_section_hint)

        topic_form = _section_form()

        self._topic_done_tag_edit = QLineEdit()
        self._topic_done_tag_edit.setText(configured_topic_done_tag({"topic_done_tag": current_topic_done_tag}))
        self._topic_done_tag_edit.setPlaceholderText(DEFAULT_TOPIC_DONE_TAG)
        self._topic_done_tag_edit.setAccessibleName(t('settings_done_tag'))
        done_tag_hint = t("settings_done_tag_help")
        self._topic_done_tag_edit.setToolTip(done_tag_hint)
        self._topic_done_tag_edit.setAccessibleDescription(done_tag_hint)
        topic_form.addRow(_label_with_info(t('settings_done_tag_label'), done_tag_hint), self._topic_done_tag_edit)
        self._topic_done_tag_error = QLabel("")
        self._topic_done_tag_error.setWordWrap(True)
        self._topic_done_tag_error.setVisible(False)
        topic_form.addRow("", self._topic_done_tag_error)

        self._default_topic_a_factor_spin = QDoubleSpinBox()
        self._default_topic_a_factor_spin.setRange(1.1, 100.0)
        self._default_topic_a_factor_spin.setDecimals(3)
        self._default_topic_a_factor_spin.setSingleStep(0.1)
        try:
            default_topic_a_factor = float(current_default_topic_a_factor)
        except Exception:
            default_topic_a_factor = 3.5
        self._default_topic_a_factor_spin.setValue(
            max(1.1, min(100.0, default_topic_a_factor))
        )
        self._default_topic_a_factor_spin.setToolTip(
            t('settings_starting_a_factor_for_topic_cards_before_they_build')
        )
        topic_form.addRow(
            _label_with_info(
                t('settings_default_topic_a_factor'),
                t('settings_used_when_a_topic_card_has_no_stored_topic'),
            ),
            self._default_topic_a_factor_spin,
        )
        topic_form.addRow(
            "",
            QLabel(
                t('settings_used_only_when_a_topic_card_does_not_yet')
            ),
        )

        self._topic_maximum_interval_days_spin = QSpinBox()
        self._topic_maximum_interval_days_spin.setRange(1, 36500)
        try:
            topic_maximum_interval_days = int(current_topic_maximum_interval_days)
        except Exception:
            topic_maximum_interval_days = 36500
        self._topic_maximum_interval_days_spin.setValue(
            max(1, min(36500, topic_maximum_interval_days))
        )
        self._topic_maximum_interval_days_spin.setSuffix(t('settings_days'))
        self._topic_maximum_interval_days_spin.setToolTip(
            t('settings_hard_cap_for_topic_intervals_the_deck_preset_s')
        )
        topic_form.addRow(
            _label_with_info(
                t('settings_maximum_topic_interval'),
                t('settings_topic_a_factor_and_custom_schedules_cannot_exceed_this'),
            ),
            self._topic_maximum_interval_days_spin,
        )

        def _topic_adjustment_spin(value) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setSuffix(" %")
            try:
                parsed = float(value)
            except Exception:
                parsed = 10.0
            spin.setValue(max(0.0, min(100.0, parsed)))
            return spin

        self._topic_more_adjustment_percent_spin = _topic_adjustment_spin(
            current_topic_more_adjustment_percent
        )
        self._topic_more_adjustment_percent_spin.setToolTip(
            t('settings_how_strongly_more_shortens_the_immediate_interval_and_reduces')
        )
        topic_form.addRow(
            _label_with_info(
                t('settings_more_adjustment'),
                t('settings_for_example_10_schedules_90_of_the_normal_next'),
            ),
            self._topic_more_adjustment_percent_spin,
        )

        self._topic_less_adjustment_percent_spin = _topic_adjustment_spin(
            current_topic_less_adjustment_percent
        )
        self._topic_less_adjustment_percent_spin.setToolTip(
            t('settings_how_strongly_less_lengthens_the_immediate_interval_and_increases')
        )
        topic_form.addRow(
            _label_with_info(
                t('settings_less_adjustment'),
                t('settings_for_example_10_schedules_110_of_the_normal_next'),
            ),
            self._topic_less_adjustment_percent_spin,
        )

        fsrs_note = QLabel(
            t('settings_anki_still_records_each_topic_answer_as_good_and')
        )
        fsrs_note.setWordWrap(True)
        topic_form.addRow("", fsrs_note)

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

        self._topic_video_cb = QCheckBox(t('settings_video'))
        self._topic_video_cb.setChecked(topic_types["video"])
        topic_layout.addWidget(self._topic_video_cb)

        self._topic_writing_cb = QCheckBox(t('settings_writing'))
        self._topic_writing_cb.setChecked(topic_types["writing"])
        topic_layout.addWidget(self._topic_writing_cb)

        self._topic_web_cb = QCheckBox(t('settings_web'))
        self._topic_web_cb.setChecked(topic_types["web"])
        topic_layout.addWidget(self._topic_web_cb)

        topic_form.addRow(
            _label_with_info(
                t('settings_treat_these_card_types_as_topics'),
                t('settings_these_cards_use_topic_review_behavior_such_as_more'),
            ),
            topic_wrap,
        )

        self._topic_tags_edit = QLineEdit()
        self._topic_tags_edit.setPlaceholderText("tag1, tag2")
        self._topic_tags_edit.setText(_tag_list_text(current_topic_card_tags))
        topic_form.addRow(
            _label_with_info(
                t('settings_topic_tags'),
                t('settings_any_card_with_one_of_these_tags_is_also'),
            ),
            self._topic_tags_edit,
        )

        self._add_card_topic_tags_edit = QLineEdit()
        self._add_card_topic_tags_edit.setPlaceholderText("topic")
        self._add_card_topic_tags_edit.setText(_tag_list_text(current_add_card_topic_tags))
        topic_form.addRow(
            _label_with_info(
                t('settings_add_card_topic_button_tags'),
                t('settings_these_tags_are_toggled_when_you_click_the_topic'),
            ),
            self._add_card_topic_tags_edit,
        )

        self._add_card_item_tags_edit = QLineEdit()
        self._add_card_item_tags_edit.setPlaceholderText("item")
        self._add_card_item_tags_edit.setText(_tag_list_text(current_add_card_item_tags))
        topic_form.addRow(
            _label_with_info(
                t('settings_add_card_item_button_tags'),
                t('settings_these_tags_are_toggled_when_you_click_the_item'),
            ),
            self._add_card_item_tags_edit,
        )

        topics_layout.addLayout(topic_form)
        topics_layout.addWidget(_subsection_title(t('settings_topics_deck')))

        topics_deck_layout = _section_body()

        self._auto_create_topics_deck_cb = QCheckBox(
            t('settings_create_the_topics_deck_automatically_when_a_selected_profile')
        )
        self._auto_create_topics_deck_cb.setChecked(bool(current_auto_create_topics_deck))
        topics_deck_layout.addWidget(self._auto_create_topics_deck_cb)

        topics_deck_form = _section_form()

        self._auto_create_topics_deck_profiles_edit = QPlainTextEdit()
        self._auto_create_topics_deck_profiles_edit.setPlaceholderText(
            t('settings_leave_blank_for_all_profiles_or_enter_one_profile')
        )
        self._auto_create_topics_deck_profiles_edit.setMinimumHeight(90)
        self._auto_create_topics_deck_profiles_edit.setPlainText(
            _name_list_text(current_auto_create_topics_deck_profiles)
        )
        topics_deck_form.addRow(
            _label_with_info(
                t('settings_only_create_for_these_profiles'),
                t('settings_leave_this_blank_to_apply_automatic_topics_deck_creation'),
            ),
            self._auto_create_topics_deck_profiles_edit,
        )
        known_profiles_text = (
            t("settings_known_profiles", profiles=", ".join(available_profile_names))
            if available_profile_names
            else t("settings_known_profiles_empty")
        )
        topics_deck_form.addRow("", QLabel(known_profiles_text))
        topics_deck_layout.addLayout(topics_deck_form)
        topics_layout.addLayout(topics_deck_layout)
        topics_layout.addWidget(_subsection_title(t('settings_postpone_button')))

        postpone_layout = _section_body()

        self._topic_postpone_enabled_cb = QCheckBox(
            t('settings_enable_red_postpone_button_on_topic_cards')
        )
        self._topic_postpone_enabled_cb.setChecked(bool(current_topic_postpone_enabled))
        postpone_layout.addWidget(self._topic_postpone_enabled_cb)

        postpone_form = _section_form()

        self._topic_postpone_mode_combo = QComboBox()
        self._topic_postpone_mode_combo.addItem(t('settings_timed_snooze'), "timed")
        self._topic_postpone_mode_combo.addItem(t('settings_session_only'), "session")
        selected_mode = (
            "session"
            if str(current_topic_postpone_mode or "").strip().lower() == "session"
            else "timed"
        )
        for idx in range(self._topic_postpone_mode_combo.count()):
            if self._topic_postpone_mode_combo.itemData(idx) == selected_mode:
                self._topic_postpone_mode_combo.setCurrentIndex(idx)
                break
        postpone_form.addRow(
            _label_with_info(
                t('settings_postpone_mode'),
                t('settings_timed_snooze_hides_the_topic_until_the_timer_expires'),
            ),
            self._topic_postpone_mode_combo,
        )

        self._topic_postpone_minutes_spin = QSpinBox()
        self._topic_postpone_minutes_spin.setRange(1, 1440)
        try:
            postpone_minutes = int(current_topic_postpone_minutes)
        except Exception:
            postpone_minutes = 30
        self._topic_postpone_minutes_spin.setValue(max(1, min(1440, postpone_minutes)))
        self._topic_postpone_minutes_spin.setSuffix(t('settings_min'))
        postpone_form.addRow(
            _label_with_info(
                t('settings_timed_snooze_duration'),
                t('settings_only_used_for_timed_snooze_example_60_minutes_hides'),
            ),
            self._topic_postpone_minutes_spin,
        )

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

        def _sync_topics_deck_widgets() -> None:
            self._auto_create_topics_deck_profiles_edit.setEnabled(
                bool(self._auto_create_topics_deck_cb.isChecked())
            )

        self._auto_create_topics_deck_cb.toggled.connect(
            lambda _checked: _sync_topics_deck_widgets()
        )
        _sync_topics_deck_widgets()

        postpone_layout.addLayout(postpone_form)
        topics_layout.addLayout(postpone_layout)
        topics_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(topics_tab), t('settings_topics'))

        writing_tab = QWidget()
        writing_layout = QVBoxLayout(writing_tab)
        writing_layout.setSpacing(8)

        writing_hint = QLabel(
            t('settings_choose_the_default_behavior_for_markdown_writing_cards_after')
        )
        writing_hint.setWordWrap(True)
        writing_layout.addWidget(writing_hint)

        writing_layout.addWidget(_section_title(t('settings_editor_defaults')))
        writing_editor_layout = _section_body()

        self._writing_wrap_enabled_cb = QCheckBox(t('settings_wrap_long_lines_in_writing_cards'))
        self._writing_wrap_enabled_cb.setChecked(bool(current_writing_wrap_enabled))
        writing_editor_layout.addWidget(self._writing_wrap_enabled_cb)

        self._writing_focus_mode_cb = QCheckBox(t('settings_start_writing_cards_in_focus_mode'))
        self._writing_focus_mode_cb.setChecked(bool(current_writing_focus_mode))
        writing_editor_layout.addWidget(self._writing_focus_mode_cb)

        self._writing_preview_visible_cb = QCheckBox(t('settings_show_markdown_preview_in_writing_cards'))
        self._writing_preview_visible_cb.setChecked(bool(current_writing_preview_visible))
        writing_editor_layout.addWidget(self._writing_preview_visible_cb)

        self._writing_highlight_current_line_cb = QCheckBox(t('settings_highlight_the_current_writing_line'))
        self._writing_highlight_current_line_cb.setChecked(bool(current_writing_highlight_current_line))
        writing_editor_layout.addWidget(self._writing_highlight_current_line_cb)

        self._writing_restore_bookmark_cb = QCheckBox(
            t('settings_restore_saved_bookmark_line_when_reopening_writing_cards')
        )
        self._writing_restore_bookmark_cb.setChecked(bool(current_writing_restore_bookmark))
        writing_editor_layout.addWidget(self._writing_restore_bookmark_cb)
        writing_layout.addLayout(writing_editor_layout)

        writing_layout.addWidget(_section_title(t('settings_backups')))
        writing_backup_layout = _section_body()

        self._writing_backups_enabled_cb = QCheckBox(t('settings_create_automatic_writing_backups'))
        self._writing_backups_enabled_cb.setChecked(bool(current_writing_backups_enabled))
        writing_backup_layout.addWidget(self._writing_backups_enabled_cb)

        selected_backup_tiers = {
            str(value or "").strip().lower()
            for value in (current_writing_backup_tiers or DEFAULT_WRITING_BACKUP_TIERS)
        }
        self._writing_backup_tier_checks: dict[str, QCheckBox] = {}
        self._writing_backup_details = QWidget()
        backup_details_layout = QVBoxLayout(self._writing_backup_details)
        backup_details_layout.setContentsMargins(24, 0, 0, 0)
        backup_details_layout.setSpacing(8)

        tier_grid = QGridLayout()
        tier_grid.setContentsMargins(0, 0, 0, 0)
        tier_grid.setHorizontalSpacing(18)
        tier_grid.setVerticalSpacing(6)
        for idx, (tier_key, label) in enumerate(WRITING_BACKUP_TIER_OPTIONS):
            checkbox = QCheckBox(t("settings_backup_" + tier_key))
            checkbox.setChecked(tier_key in selected_backup_tiers)
            self._writing_backup_tier_checks[tier_key] = checkbox
            tier_grid.addWidget(checkbox, idx // 2, idx % 2)
        backup_details_layout.addLayout(tier_grid)
        backup_details_layout.addWidget(
            _note_label(
                t('settings_each_selected_interval_keeps_one_rolling_snapshot_per_writing')
            )
        )
        writing_backup_layout.addWidget(self._writing_backup_details)
        self._writing_backups_enabled_cb.toggled.connect(self._sync_writing_backup_controls)
        self._sync_writing_backup_controls(self._writing_backups_enabled_cb.isChecked())
        writing_layout.addLayout(writing_backup_layout)

        writing_layout.addWidget(_section_title(t('settings_progress')))
        writing_progress_layout = _section_body()

        self._writing_progress_visible_cb = QCheckBox(t('settings_show_the_writing_progress_counter_in_the_dock'))
        self._writing_progress_visible_cb.setChecked(bool(current_writing_progress_visible))
        writing_progress_layout.addWidget(self._writing_progress_visible_cb)

        self._writing_progress_details = QWidget()
        progress_details_layout = QVBoxLayout(self._writing_progress_details)
        progress_details_layout.setContentsMargins(24, 0, 0, 0)
        progress_details_layout.setSpacing(8)

        writing_progress_form = _section_form()
        writing_progress_form.setContentsMargins(0, 0, 0, 0)

        self._writing_progress_scope_combo = QComboBox()
        self._writing_progress_scope_combo.addItem(t('settings_today'), "today")
        self._writing_progress_scope_combo.addItem(t('settings_session'), "session")
        self._writing_progress_scope_combo.addItem(t('settings_all_time'), "all_time")
        selected_progress_scope = str(current_writing_progress_default_scope or "today").strip().lower()
        if selected_progress_scope not in {"today", "session", "all_time"}:
            selected_progress_scope = "today"
        for idx in range(self._writing_progress_scope_combo.count()):
            if self._writing_progress_scope_combo.itemData(idx) == selected_progress_scope:
                self._writing_progress_scope_combo.setCurrentIndex(idx)
                break
        writing_progress_form.addRow(
            _label_with_info(
                t('settings_default_progress_scope'),
                t('settings_today_counts_words_written_today_on_this_card_session'),
            ),
            self._writing_progress_scope_combo,
        )
        progress_details_layout.addLayout(writing_progress_form)
        progress_details_layout.addWidget(
            _note_label(t('settings_session_resets_when_you_leave_and_reopen_that_writing'))
        )

        self._writing_word_count_mode_combo = QComboBox()
        self._writing_word_count_mode_combo.addItem(t('settings_simple_whitespace'), "simple")
        self._writing_word_count_mode_combo.addItem(t('settings_word_like'), "word_like")
        selected_word_count_mode = str(current_writing_word_count_mode or "simple").strip().lower()
        if selected_word_count_mode not in {"simple", "word_like"}:
            selected_word_count_mode = "simple"
        for idx in range(self._writing_word_count_mode_combo.count()):
            if self._writing_word_count_mode_combo.itemData(idx) == selected_word_count_mode:
                self._writing_word_count_mode_combo.setCurrentIndex(idx)
                break
        writing_progress_form.addRow(
            _label_with_info(
                t('settings_word_counting_mode'),
                t('settings_simple_whitespace_counts_chunks_separated_by_spaces_word_like'),
            ),
            self._writing_word_count_mode_combo,
        )
        progress_details_layout.addWidget(
            _note_label(
                t('settings_word_like_mode_approximates_microsoft_word_better_for_punctuation')
            )
        )
        writing_progress_layout.addWidget(self._writing_progress_details)
        self._writing_progress_visible_cb.toggled.connect(self._sync_writing_progress_controls)
        self._sync_writing_progress_controls(self._writing_progress_visible_cb.isChecked())
        writing_layout.addLayout(writing_progress_layout)
        writing_layout.addStretch(1)
        tabs.addTab(_scrollable_tab(writing_tab), t('settings_writing'))

        shortcuts_tab = QWidget()
        shortcuts_layout = QVBoxLayout(shortcuts_tab)
        shortcuts_layout.setSpacing(8)

        hint = QLabel(
            t('settings_assign_keyboard_shortcuts_for_incremento_actions_leave_a_field')
        )
        hint.setWordWrap(True)
        shortcuts_layout.addWidget(hint)

        self._shortcut_conflict_label = QLabel("")
        self._shortcut_conflict_label.setWordWrap(True)
        self._shortcut_conflict_label.setStyleSheet(
            "color: #d9534f; font-weight: bold; padding: 6px;"
        )
        self._shortcut_conflict_label.setAccessibleName(t('settings_keyboard_shortcut_conflicts'))
        self._shortcut_conflict_label.setVisible(False)
        shortcuts_layout.addWidget(self._shortcut_conflict_label)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        runtime_shortcuts = resolved_runtime_shortcuts(current_shortcuts)
        for spec in localized_shortcut_action_specs():
            action_id = spec["id"]
            editor = QKeySequenceEdit()
            configured = runtime_shortcuts.get(
                action_id, self._defaults[action_id]
            )
            editor.setKeySequence(QKeySequence(configured))
            editor.setAccessibleName(t("settings_shortcut_for", action=spec["label"]))
            self._editors[action_id] = editor
            key_sequence_changed = getattr(editor, "keySequenceChanged", None)
            if hasattr(key_sequence_changed, "connect"):
                key_sequence_changed.connect(self._refresh_shortcut_conflicts)

            row_wrap = QWidget()
            row_layout = QHBoxLayout(row_wrap)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(editor)

            clear_btn = QPushButton(t('settings_clear'))
            clear_btn.setMaximumWidth(64)
            clear_btn.clicked.connect(lambda _, e=editor: e.clear())
            row_layout.addWidget(clear_btn)

            form.addRow(spec["label"] + ":", row_wrap)

        shortcuts_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch(1)

        restore_btn = QPushButton(t('settings_restore_defaults'))
        restore_btn.clicked.connect(self._restore_defaults)
        action_row.addWidget(restore_btn)

        clear_all_btn = QPushButton(t('settings_clear_all'))
        clear_all_btn.clicked.connect(self._clear_all)
        action_row.addWidget(clear_all_btn)

        shortcuts_layout.addLayout(action_row)
        shortcuts_layout.addStretch(1)
        self._refresh_shortcut_conflicts()

        tabs.addTab(_scrollable_tab(shortcuts_tab), t('settings_shortcuts'))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_shortcuts_valid)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("common_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common_cancel"))
        root.addWidget(buttons)

    def _restore_defaults(self) -> None:
        for action_id, editor in self._editors.items():
            editor.setKeySequence(QKeySequence(self._defaults.get(action_id, "")))

    def _clear_all(self) -> None:
        for editor in self._editors.values():
            editor.clear()
        self._refresh_shortcut_conflicts()

    def _shortcut_conflicts(self):
        return find_shortcut_conflicts(self.shortcuts_map)

    def _refresh_shortcut_conflicts(self, *_args) -> bool:
        conflicts = self._shortcut_conflicts()
        if not conflicts:
            self._shortcut_conflict_label.setText("")
            self._shortcut_conflict_label.setVisible(False)
            return False
        labels = {str(spec["id"]): str(spec["label"]) for spec in localized_shortcut_action_specs()}
        lines = []
        for conflict in conflicts:
            action_labels = ", ".join(
                labels.get(action_id, action_id) for action_id in conflict.action_ids
            )
            lines.append(f"{conflict.shortcut}: {action_labels}")
        self._shortcut_conflict_label.setText(
            t("settings_shortcut_conflicts", conflicts="\n".join(lines))
        )
        self._shortcut_conflict_label.setVisible(True)
        return True

    def _accept_if_shortcuts_valid(self) -> bool:
        try:
            self.topic_done_tag
        except ValueError:
            self._topic_done_tag_error.setText(t("settings_done_tag_invalid"))
            self._topic_done_tag_error.setVisible(True)
            self._topic_done_tag_edit.setFocus()
            return False
        self._topic_done_tag_error.setText("")
        self._topic_done_tag_error.setVisible(False)
        if self._refresh_shortcut_conflicts():
            return False
        self.accept()
        return True

    def _open_database_editor(self) -> None:
        callback = self._open_database_editor_callback
        if callable(callback):
            callback()

    @property
    def ui_language(self) -> str:
        return normalize_language_choice(self._language_combo.currentData())

    @property
    def pending_language_pack(self) -> dict | None:
        return self._language_pack_controls.pending_pack if self._language_pack_controls else None

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
    def extract_copy_source_tags(self) -> bool:
        return bool(self._extract_copy_source_tags_cb.isChecked())

    @property
    def extract_highlight_when_extracting(self) -> bool:
        return bool(self._extract_highlight_when_extracting_cb.isChecked())

    @property
    def pdf_highlight_extract_field(self) -> int:
        return max(1, min(20, int(self._pdf_highlight_extract_field_spin.value())))

    @property
    def pdf_snapshot_auto_field_enabled(self) -> bool:
        return bool(self._pdf_snapshot_auto_field_enabled_cb.isChecked())

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
    def reviewer_priority_badge_card_types(self) -> dict[str, bool]:
        return {
            "topics": bool(self._reviewer_priority_badge_topics_cb.isChecked()),
            "items": bool(self._reviewer_priority_badge_items_cb.isChecked()),
        }

    @property
    def reviewer_button_visibility(self) -> dict[str, bool]:
        return {
            "done": bool(self._reviewer_done_button_cb.isChecked()),
            "postpone": bool(self._reviewer_postpone_button_cb.isChecked()),
            "extract": bool(self._reviewer_extract_button_cb.isChecked()),
        }

    @property
    def reviewer_button_group_visible(self) -> bool:
        return bool(self._reviewer_button_group_cb.isChecked())

    @property
    def remember_browser_card_scroll(self) -> bool:
        return bool(self._remember_browser_card_scroll_cb.isChecked())

    @property
    def pdf_scroll_to_top_on_page_change(self) -> bool:
        return bool(self._pdf_scroll_to_top_on_page_change_cb.isChecked())

    @property
    def pdf_default_appearance(self) -> str:
        return normalize_pdf_appearance_mode(
            self._pdf_default_appearance_combo.currentData()
        )

    @property
    def pdf_force_default_appearance(self) -> bool:
        return bool(self._pdf_force_default_appearance_cb.isChecked())

    @property
    def show_incremento_fields(self) -> bool:
        return bool(self._show_incremento_fields_cb.isChecked())

    @property
    def prefer_web_card_resume_in_original_page(self) -> bool:
        return bool(self._prefer_web_card_resume_in_original_page_cb.isChecked())

    @property
    def track_web_window_with_extension(self) -> bool:
        return bool(self._track_web_window_with_extension_cb.isChecked())

    @property
    def use_fail_pass_on_items(self) -> bool:
        return bool(self._use_fail_pass_on_items_cb.isChecked())

    @property
    def item_skip_enabled(self) -> bool:
        return bool(self._item_skip_enabled_cb.isChecked())

    @property
    def item_skip_minutes(self) -> int:
        return int(self._item_skip_minutes_spin.value())

    @property
    def auto_timer_enabled(self) -> bool:
        return bool(self._auto_timer_enabled_cb.isChecked())

    @property
    def auto_timer_card_types(self) -> dict[str, bool]:
        return {
            "pdf": bool(self._auto_timer_pdf_cb.isChecked()),
            "epub": bool(self._auto_timer_epub_cb.isChecked()),
            "video": bool(self._auto_timer_video_cb.isChecked()),
            "web": bool(self._auto_timer_web_cb.isChecked()),
            "writing": bool(self._auto_timer_writing_cb.isChecked()),
            "local_file": bool(self._auto_timer_local_file_cb.isChecked()),
        }

    @property
    def auto_timer_tags(self) -> list[str]:
        return _normalize_tag_list(self._auto_timer_tags_edit.text())

    @property
    def auto_timer_minutes(self) -> int:
        return int(self._auto_timer_minutes_spin.value())

    @property
    def timer_completion_beep(self) -> bool:
        return bool(self._timer_completion_beep_cb.isChecked())

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
    def default_topic_a_factor(self) -> float:
        return round(float(self._default_topic_a_factor_spin.value()), 3)

    @property
    def topic_more_adjustment_percent(self) -> float:
        return round(float(self._topic_more_adjustment_percent_spin.value()), 3)

    @property
    def topic_less_adjustment_percent(self) -> float:
        return round(float(self._topic_less_adjustment_percent_spin.value()), 3)

    @property
    def topic_maximum_interval_days(self) -> int:
        return int(self._topic_maximum_interval_days_spin.value())

    @property
    def topic_done_tag(self) -> str:
        return normalize_topic_done_tag(self._topic_done_tag_edit.text())

    @property
    def add_card_topic_tags(self) -> list[str]:
        return _normalize_tag_list(self._add_card_topic_tags_edit.text())

    @property
    def add_card_item_tags(self) -> list[str]:
        return _normalize_tag_list(self._add_card_item_tags_edit.text())

    @property
    def auto_create_topics_deck(self) -> bool:
        return bool(self._auto_create_topics_deck_cb.isChecked())

    @property
    def auto_create_topics_deck_profiles(self) -> list[str]:
        return _normalize_name_list(self._auto_create_topics_deck_profiles_edit.toPlainText())

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
    def writing_preview_visible(self) -> bool:
        return bool(self._writing_preview_visible_cb.isChecked())

    @property
    def writing_restore_bookmark(self) -> bool:
        return bool(self._writing_restore_bookmark_cb.isChecked())

    @property
    def writing_backups_enabled(self) -> bool:
        return bool(self._writing_backups_enabled_cb.isChecked())

    @property
    def writing_backup_tiers(self) -> list[str]:
        selected = [
            tier_key
            for tier_key, _label in WRITING_BACKUP_TIER_OPTIONS
            if self._writing_backup_tier_checks[tier_key].isChecked()
        ]
        return selected or list(DEFAULT_WRITING_BACKUP_TIERS)

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

    def _sync_writing_backup_controls(self, enabled: bool) -> None:
        self._writing_backup_details.setEnabled(bool(enabled))
        for checkbox in self._writing_backup_tier_checks.values():
            checkbox.setEnabled(bool(enabled))

    def _sync_writing_progress_controls(self, enabled: bool) -> None:
        self._writing_progress_details.setEnabled(bool(enabled))

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
            for original in self._custom_schedule_source_presets:
                if original.get("builtin_id") and all(
                    preset[key] == original[key]
                    for key in ("label", "interval_value", "interval_unit")
                ):
                    preset["builtin_id"] = original["builtin_id"]
                    break
            presets.append(preset)
        return presets or configured_custom_schedule_presets()
