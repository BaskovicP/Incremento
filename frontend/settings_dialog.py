from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QKeySequence,
    QKeySequenceEdit,
    QPushButton,
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
        "id": "youtube_video",
        "label": "YouTube Video",
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
        "label": "Export User Data",
        "default": "",
    },
    {
        "id": "quick_open_pdf",
        "label": "Quick Open PDFs",
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
    def __init__(self, current_shortcuts: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Incremento Settings")
        self.setMinimumWidth(620)
        self._defaults = default_shortcuts()
        self._editors: dict[str, QKeySequenceEdit] = {}

        root = QVBoxLayout(self)

        tabs = QTabWidget()
        root.addWidget(tabs)

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
