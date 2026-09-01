"""Versioned first-run guide for Incremento."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Mapping


ONBOARDING_VERSION = 1


@dataclass(frozen=True)
class OnboardingStep:
    step_id: str
    title: str
    body: str
    action_id: str = ""
    action_label: str = ""


def default_onboarding_steps() -> list[OnboardingStep]:
    return [
        OnboardingStep(
            "welcome",
            "Welcome to Incremento",
            "Incremento keeps long-form reading, extraction, review, and progress "
            "inside Anki. This short guide follows the safest first workflow.",
        ),
        OnboardingStep(
            "add_document",
            "1. Add your first document",
            "Start with a PDF or EPUB. Incremento stores managed documents inside "
            "the active Anki profile and restores your reading position.",
            "add_pdf",
            "Add PDF…",
        ),
        OnboardingStep(
            "extract",
            "2. Extract one useful idea",
            "Select a passage in the reader and choose Extract. Review the source, "
            "destination field, tags, priority, and duplicate warning before saving.",
        ),
        OnboardingStep(
            "start_session",
            "3. Start a small session",
            "Use the Basic session view first. Choose a small card count and your "
            "Topic/Item and Document/Other mix; Advanced keeps the full scheduler.",
            "start_learning",
            "Open session setup…",
        ),
        OnboardingStep(
            "extension_privacy",
            "4. Connect the browser only if needed",
            "The companion extension uses temporary access by default. Persistent "
            "Automatic site access is optional and can be revoked in the popup.",
        ),
        OnboardingStep(
            "backup",
            "5. Create a backup",
            "Export a full backup before a large import or workflow change. Runtime "
            "content remains isolated under the active Anki profile.",
            "export_user_data",
            "Export backup…",
        ),
    ]


def _completed_version(config: Mapping | None) -> int:
    try:
        return max(0, int((config or {}).get("onboarding_completed_version", 0)))
    except Exception:
        return 0


def should_show_onboarding(
    config: Mapping | None,
    *,
    version: int = ONBOARDING_VERSION,
) -> bool:
    return _completed_version(config) < max(1, int(version))


def mark_onboarding_complete(
    config: Mapping | None,
    *,
    version: int = ONBOARDING_VERSION,
) -> dict:
    updated = copy.deepcopy(dict(config or {}))
    updated["onboarding_completed_version"] = max(1, int(version))
    return updated


def create_onboarding_dialog(
    parent,
    *,
    on_complete: Callable[[], object],
    actions: Mapping[str, Callable[[], object]] | None = None,
):
    """Create a non-modal guided dialog so its optional actions can open Anki UI."""
    from aqt.qt import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    steps = default_onboarding_steps()
    callbacks = dict(actions or {})

    class IncrementoOnboardingDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle("Getting Started with Incremento")
            self.setMinimumSize(640, 420)
            self.setModal(False)
            self._completed = False

            root = QVBoxLayout(self)
            self.progress_label = QLabel("")
            self.progress_label.setAccessibleName("Onboarding progress")
            root.addWidget(self.progress_label)

            self.pages = QStackedWidget()
            self.pages.setAccessibleName("Incremento onboarding steps")
            for step in steps:
                page = QWidget()
                page_layout = QVBoxLayout(page)
                title = QLabel(step.title)
                title.setStyleSheet("font-size: 20px; font-weight: bold;")
                title.setWordWrap(True)
                page_layout.addWidget(title)
                body = QLabel(step.body)
                body.setWordWrap(True)
                body.setAccessibleName(step.title)
                page_layout.addWidget(body)
                if step.action_id and step.action_label:
                    action_button = QPushButton(step.action_label)
                    action_button.setAccessibleName(step.action_label)
                    action_button.clicked.connect(
                        lambda _checked=False, action_id=step.action_id: self._run_action(action_id)
                    )
                    page_layout.addWidget(action_button)
                page_layout.addStretch(1)
                self.pages.addWidget(page)
            root.addWidget(self.pages, 1)

            buttons = QHBoxLayout()
            self.skip_button = QPushButton("Skip guide")
            self.skip_button.setAccessibleName("Skip onboarding guide")
            self.skip_button.clicked.connect(self._finish)
            buttons.addWidget(self.skip_button)
            buttons.addStretch(1)
            self.back_button = QPushButton("Back")
            self.back_button.setAccessibleName("Go to previous onboarding step")
            self.back_button.clicked.connect(self._back)
            buttons.addWidget(self.back_button)
            self.next_button = QPushButton("Next")
            self.next_button.setAccessibleName("Go to next onboarding step")
            self.next_button.clicked.connect(self._next)
            buttons.addWidget(self.next_button)
            root.addLayout(buttons)
            self.pages.currentChanged.connect(self._sync_navigation)
            self._sync_navigation(0)

        def _run_action(self, action_id: str) -> None:
            callback = callbacks.get(action_id)
            if callable(callback):
                callback()

        def _back(self) -> None:
            self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1))

        def _next(self) -> None:
            if self.pages.currentIndex() >= len(steps) - 1:
                self._finish()
                return
            self.pages.setCurrentIndex(self.pages.currentIndex() + 1)

        def _sync_navigation(self, index: int) -> None:
            self.progress_label.setText(f"Step {index + 1} of {len(steps)}")
            self.back_button.setEnabled(index > 0)
            self.next_button.setText("Finish" if index == len(steps) - 1 else "Next")
            self.next_button.setAccessibleName(
                "Finish onboarding guide"
                if index == len(steps) - 1
                else "Go to next onboarding step"
            )

        def _finish(self) -> None:
            if not self._completed:
                self._completed = True
                on_complete()
            self.accept()

    return IncrementoOnboardingDialog()
