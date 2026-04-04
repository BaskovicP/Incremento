from aqt import mw
from aqt.utils import showInfo
from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTextEdit,
)

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.tag_edit import QuickTagEdit

try:
    from ..backend.webpage_markdown import fetch_webpage_markdown
except ImportError:
    from webpage_markdown import fetch_webpage_markdown


class AddWritingDialog(QDialog):
    """Dialog to create an Incremento writing card backed by a markdown file."""

    def __init__(self, deck_names: list[str], default_deck: str = "Topics", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to Markdown")
        self.setMinimumWidth(560)
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Markdown note title")
        layout.addWidget(self._title_edit)

        layout.addWidget(QLabel("Filename (optional):"))
        self._filename_edit = QLineEdit()
        self._filename_edit.setPlaceholderText("my-note.md  (stored under user_files/writing)")
        layout.addWidget(self._filename_edit)

        self._tag_edit = QuickTagEdit()
        layout.addWidget(self._tag_edit)

        import_mode_row = QHBoxLayout()
        import_mode_row.addWidget(QLabel("Import mode:"))
        self._import_mode_combo = QComboBox()
        self._import_mode_combo.addItem("Manual markdown", "manual")
        self._import_mode_combo.addItem("Import webpage markdown", "webpage_markdown")
        import_mode_row.addWidget(self._import_mode_combo, 1)
        layout.addLayout(import_mode_row)

        source_row = QHBoxLayout()
        self._source_url_label = QLabel("Source URL:")
        source_row.addWidget(self._source_url_label)
        self._source_url_edit = QLineEdit()
        self._source_url_edit.setPlaceholderText("https://…")
        source_row.addWidget(self._source_url_edit, 1)
        self._fetch_btn = QPushButton("Fetch page")
        source_row.addWidget(self._fetch_btn)
        layout.addLayout(source_row)

        scope_row = QHBoxLayout()
        self._scope_label = QLabel("Webpage scope:")
        scope_row.addWidget(self._scope_label)
        self._scope_combo = QComboBox()
        self._scope_combo.addItem("Main content", "main")
        self._scope_combo.addItem("Entire page", "full")
        scope_row.addWidget(self._scope_combo, 1)
        layout.addLayout(scope_row)

        self._fetch_status = QLabel("")
        self._fetch_status.setWordWrap(True)
        self._fetch_status.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(self._fetch_status)

        deck_row = QHBoxLayout()
        deck_row.addWidget(QLabel("Deck:"))
        self._deck_combo = QComboBox()
        for d in deck_names:
            self._deck_combo.addItem(d)
        if default_deck:
            idx = self._deck_combo.findText(default_deck)
            if idx >= 0:
                self._deck_combo.setCurrentIndex(idx)
        deck_row.addWidget(self._deck_combo, 1)
        layout.addLayout(deck_row)

        layout.addWidget(QLabel("Initial markdown:"))
        self._markdown_edit = QTextEdit()
        self._markdown_edit.setAcceptRichText(False)
        self._markdown_edit.setPlaceholderText(
            "# Heading\n\nWrite initial content here…"
        )
        layout.addWidget(self._markdown_edit, 1)

        hint = QLabel(
            "The markdown file is autosaved while typing when this card is reviewed."
        )
        hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Add Markdown Card")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self._import_mode_combo.currentIndexChanged.connect(self._refresh_import_controls)
        self._fetch_btn.clicked.connect(self._fetch_page_markdown)
        self._refresh_import_controls()

    def _refresh_import_controls(self) -> None:
        webpage_mode = self.import_mode == "webpage_markdown"
        self._source_url_label.setVisible(webpage_mode)
        self._source_url_edit.setVisible(webpage_mode)
        self._fetch_btn.setVisible(webpage_mode)
        self._scope_label.setVisible(webpage_mode)
        self._scope_combo.setVisible(webpage_mode)
        if webpage_mode:
            self._fetch_status.setText(
                "Fetches webpage content into markdown. Main content tries to ignore navigation and sidebars."
            )
        else:
            self._fetch_status.setText(
                "Write or paste markdown manually, or switch import mode to pull it from a webpage."
            )

    def _normalized_source_url(self) -> str:
        url = self._source_url_edit.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def _set_fetch_busy(self, busy: bool, message: str = "") -> None:
        self._fetch_btn.setEnabled(not busy)
        self._import_mode_combo.setEnabled(not busy)
        self._scope_combo.setEnabled(not busy)
        self._source_url_edit.setEnabled(not busy)
        self._fetch_status.setText(message or self._fetch_status.text())

    def _fetch_page_markdown(self) -> None:
        url = self._normalized_source_url()
        if not url:
            showInfo("Please enter a source URL first.")
            return

        scope = self.page_content_scope
        self._set_fetch_busy(True, "Fetching webpage markdown…")
        try:
            mw.progress.start(label="Fetching webpage markdown…", immediate=True)
        except TypeError:
            mw.progress.start(label="Fetching webpage markdown…")

        def _task():
            return fetch_webpage_markdown(url, content_scope=scope)

        def _on_done(fut) -> None:
            try:
                mw.progress.finish()
            except Exception:
                pass
            try:
                result = fut.result()
            except Exception as exc:
                try:
                    self._set_fetch_busy(False, "Fetch failed.")
                except RuntimeError:
                    return
                showInfo(f"Failed to fetch webpage markdown:\n{exc}")
                return

            fetched_title = str(result.get("title") or "").strip()
            fetched_markdown = str(result.get("markdown") or "").strip()
            if not fetched_markdown:
                try:
                    self._set_fetch_busy(False, "No markdown content was extracted.")
                except RuntimeError:
                    return
                showInfo("Failed to fetch webpage markdown:\nNo readable content was extracted.")
                return

            try:
                if not self.title and fetched_title:
                    self._title_edit.setText(fetched_title)
                self._markdown_edit.setPlainText(
                    str(
                        result.get("markdown_document")
                        or fetched_markdown
                    )
                )
                self._set_fetch_busy(False, "Webpage markdown loaded into the editor.")
            except RuntimeError:
                return

        mw.taskman.run_in_background(_task, _on_done)

    @property
    def title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def filename(self) -> str:
        return self._filename_edit.text().strip()

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    @property
    def tags(self) -> list[str]:
        return self._tag_edit.tags()

    @property
    def initial_markdown(self) -> str:
        return self._markdown_edit.toPlainText()

    @property
    def import_mode(self) -> str:
        return str(self._import_mode_combo.currentData() or "manual")

    @property
    def source_url(self) -> str:
        return self._normalized_source_url()

    @property
    def page_content_scope(self) -> str:
        return str(self._scope_combo.currentData() or "main")
