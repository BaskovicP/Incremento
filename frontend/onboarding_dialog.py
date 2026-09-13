"""Versioned first-run guide for Incremento."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Mapping

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t  # type: ignore


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
            t("onboarding_welcome_title"),
            t("onboarding_welcome_body"),
        ),
        OnboardingStep(
            "add_document",
            t("onboarding_add_document_title"),
            t("onboarding_add_document_body"),
            "add_pdf",
            t("onboarding_add_document_action"),
        ),
        OnboardingStep(
            "extract",
            t("onboarding_extract_title"),
            t("onboarding_extract_body"),
        ),
        OnboardingStep(
            "start_session",
            t("onboarding_start_session_title"),
            t("onboarding_start_session_body"),
            "start_learning",
            t("onboarding_start_session_action"),
        ),
        OnboardingStep(
            "extension_privacy",
            t("onboarding_extension_privacy_title"),
            t("onboarding_extension_privacy_body"),
        ),
        OnboardingStep(
            "backup",
            t("onboarding_backup_title"),
            t("onboarding_backup_body"),
            "export_user_data",
            t("onboarding_backup_action"),
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
            self.setWindowTitle(t("onboarding_dialog_title"))
            self.setMinimumSize(640, 420)
            self.setModal(False)
            self._completed = False

            root = QVBoxLayout(self)
            self.progress_label = QLabel("")
            self.progress_label.setAccessibleName(t("onboarding_progress_accessible"))
            root.addWidget(self.progress_label)

            self.pages = QStackedWidget()
            self.pages.setAccessibleName(t("onboarding_steps_accessible"))
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
            self.skip_button = QPushButton(t("onboarding_skip"))
            self.skip_button.setAccessibleName(t("onboarding_skip_accessible"))
            self.skip_button.clicked.connect(self._finish)
            buttons.addWidget(self.skip_button)
            buttons.addStretch(1)
            self.back_button = QPushButton(t("common_back"))
            self.back_button.setAccessibleName(t("onboarding_back_accessible"))
            self.back_button.clicked.connect(self._back)
            buttons.addWidget(self.back_button)
            self.next_button = QPushButton(t("common_next"))
            self.next_button.setAccessibleName(t("onboarding_next_accessible"))
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
            self.progress_label.setText(
                t("onboarding_progress", current=index + 1, total=len(steps))
            )
            self.back_button.setEnabled(index > 0)
            self.next_button.setText(
                t("common_finish") if index == len(steps) - 1 else t("common_next")
            )
            self.next_button.setAccessibleName(
                t("onboarding_finish_accessible")
                if index == len(steps) - 1
                else t("onboarding_next_accessible")
            )

        def _finish(self) -> None:
            if not self._completed:
                self._completed = True
                on_complete()
            self.accept()

    return IncrementoOnboardingDialog()
