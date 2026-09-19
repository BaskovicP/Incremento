"""Per-file DjVu choices and cancellable, offline size/quality estimates."""
from pathlib import Path
import threading

from aqt.qt import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, Qt

try:
    from ..backend import djvu_manager
    from ..backend.i18n import t
except ImportError:
    from backend import djvu_manager  # type: ignore[no-redef]
    from backend.i18n import t


def _signature(path):
    try:
        stat = Path(path).stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    except OSError:
        return None


class DjvuCompressionPanel(QWidget):
    def __init__(self, taskman, is_current, show_preview, parent=None):
        super().__init__(parent)
        self._taskman = taskman
        self._is_current = is_current
        self._show_preview = show_preview
        self._path = None
        self._signature = None
        self._choices = {}
        self._manual_choices = set()
        self._auto_choices = {}
        self._changing_choice = False
        self._cancel = threading.Event()
        self._generation = 0
        self._running = False
        self.result = None  # Only the current file's bounded preview is cached.

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        title = QLabel(t("imports_djvu_compression"))
        title.setWordWrap(True)
        layout.addWidget(title)
        self.preset = QComboBox()
        self.preset.setAccessibleName(t("imports_djvu_compression"))
        for mode in djvu_manager.COMPRESSION_PRESETS:
            self.preset.addItem(t("imports_djvu_mode_" + mode), mode)
        self.preset.currentIndexChanged.connect(self._choice_changed)
        layout.addWidget(self.preset)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        buttons = QHBoxLayout()
        self.estimate = QPushButton(t("imports_djvu_estimate"))
        self.estimate.clicked.connect(self._estimate)
        buttons.addWidget(self.estimate)
        self.cancel = QPushButton(t("imports_cancel"))
        self.cancel.clicked.connect(self.stop)
        self.cancel.hide()
        buttons.addWidget(self.cancel)
        layout.addLayout(buttons)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.pages = QComboBox()
        self.pages.setAccessibleName(t("imports_djvu_sample_page"))
        self.pages.currentIndexChanged.connect(self._preview)
        self.pages.hide()
        layout.addWidget(self.pages)
        self.hide()

    def choice_for(self, path):
        return self._choices.get(path, "mrc")

    def set_path(self, path):
        signature = _signature(path) if path else None
        if path == self._path and signature == self._signature:
            self.refresh()
            return
        self.stop()
        self._path, self._signature = path, signature
        self.result = None
        self.pages.clear()
        self.pages.hide()
        self.setVisible(path is not None)
        if path is not None:
            self._changing_choice = True
            try:
                self.preset.setCurrentIndex(self.preset.findData(self.choice_for(path)))
            finally:
                self._changing_choice = False
        self.refresh()
        if path is not None:
            self._estimate()

    def _choice_changed(self, _index):
        if self._path and not self._changing_choice:
            self._choices[self._path] = self.preset.currentData()
            self._manual_choices.add(self._path)
            self._auto_choices.pop(self._path, None)
        self.refresh()

    def stop(self):
        self._cancel.set()
        self._generation += 1
        self._running = False
        self.cancel.setEnabled(False)

    def refresh(self):
        mode = self.preset.currentData()
        if mode is None:
            return
        self.description.setText(t("imports_djvu_description_" + mode))
        self.estimate.setEnabled(bool(self._path) and not self._running)
        self.cancel.setVisible(self._running)
        if self.result is None:
            self.summary.setText(t("imports_djvu_estimating" if self._running else "imports_djvu_estimate_hint"))
            return
        result = self.result
        selected = result.estimates[mode]
        original = result.estimates["original"].expected_bytes
        change = (1 - selected.expected_bytes / max(1, original)) * 100
        comparison = t("imports_djvu_smaller", percent=round(change)) if change >= 0 else t(
            "imports_djvu_larger", percent=round(-change))
        summary = t("imports_djvu_estimate_result",
                    low=selected.low_bytes / 2**20, high=selected.high_bytes / 2**20,
                    source=result.source_bytes / 2**20, comparison=comparison,
                    sampled=len(result.sample_pages), total=result.page_count)
        if self._auto_choices.get(self._path) == mode:
            summary = t("imports_djvu_auto_choice", mode=self.preset.currentText()) + "\n\n" + summary
        if djvu_manager.is_risky_pdf_expansion(result.source_bytes, selected.expected_bytes):
            summary += "\n\n" + t("imports_djvu_expansion_warning")
        self.summary.setText(summary)
        self._preview()

    def _preview(self, _index=None):
        if self.result is not None and self.pages.currentIndex() >= 0:
            mode = self.preset.currentData()
            self._show_preview(self.result.estimates[mode].previews[self.pages.currentIndex()])

    def _estimate(self):
        if self._running or not self._path or not self._is_current():
            return
        self.stop()
        generation, path = self._generation, self._path
        signature = _signature(path)
        self._signature = signature
        self._cancel = cancelled = threading.Event()
        self._running = True
        self.result = None
        self.pages.hide()
        self.cancel.setEnabled(True)
        self.refresh()

        def work():
            return djvu_manager.estimate_djvu_compression(
                path, cancel_cb=lambda: cancelled.is_set() or not self._is_current())

        def done(future):
            if (generation != self._generation or cancelled.is_set() or
                    path != self._path or not self._is_current()):
                return
            self._running = False
            self.refresh()
            if signature != _signature(path):
                self.summary.setText(t("imports_djvu_estimate_changed"))
                return
            try:
                result = future.result()
            except Exception as exc:
                self.summary.setText(t("imports_djvu_estimate_failed", reason=str(exc)))
                return
            self.result = result
            if path not in self._manual_choices:
                candidates = ("mrc", "compact_color", "balanced")
                recommended = min(
                    candidates,
                    key=lambda mode: result.estimates[mode].expected_bytes,
                )
                self._choices[path] = recommended
                self._auto_choices[path] = recommended
                self._changing_choice = True
                try:
                    self.preset.setCurrentIndex(self.preset.findData(recommended))
                finally:
                    self._changing_choice = False
            self.pages.blockSignals(True)
            self.pages.clear()
            for number in self.result.sample_pages:
                self.pages.addItem(t("imports_djvu_preview_page", page=number), number)
            self.pages.blockSignals(False)
            self.pages.setVisible(True)
            self.refresh()

        try:
            self._taskman.run_in_background(work, done, uses_collection=False)
        except Exception as exc:
            self._running = False
            self.refresh()
            self.summary.setText(t("imports_djvu_estimate_failed", reason=str(exc)))
