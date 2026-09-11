"""Secondary Done button, Revisit menu and non-modal Undo feedback for topics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
import secrets

try:
    from ..backend.config_service import DEFAULT_TOPIC_DONE_TAG
    from ..backend.topic_review_actions import StaleTopicAction, complete_topic, revisit_topic, undo_topic_action
    from ..backend.custom_schedule import anki_logical_today
except ImportError:
    from backend.config_service import DEFAULT_TOPIC_DONE_TAG
    from backend.topic_review_actions import StaleTopicAction, complete_topic, revisit_topic, undo_topic_action
    from backend.custom_schedule import anki_logical_today


DONE_DESCRIPTION = (
    "Keep this topic as a reference and stop showing it in reviews. "
    "Add the Done tag selected in Settings → Topics to its note. "
    "Extracted cards continue reviewing. Undo restores both the card and its previous tags."
)
_COMMAND_PREFIX = "incremento_topic_done:"


def build_topic_done_button_js(command: str | None) -> str:
    return """(() => {
  const command = %s;
  const generation = (window.incrementoTopicDoneGeneration || 0) + 1;
  window.incrementoTopicDoneGeneration = generation;
  const cellId = "incremento-topic-done-cell";
  document.getElementById(cellId)?.remove();
  if (!command) return;
  let attempts = 0;
  function install() {
    if (window.incrementoTopicDoneGeneration !== generation) return;
    const answers = document.querySelectorAll('button[data-ease]');
    const anchor = (answers.length ? answers[answers.length - 1] : document.getElementById("ansbut"))?.closest("td");
    if (!anchor) {
      if (++attempts < 10) setTimeout(install, 40);
      return;
    }
    const cell = document.createElement("td");
    cell.id = cellId;
    cell.className = "stat2";
    cell.setAttribute("align", "center");
    const button = document.createElement("button");
    button.id = "incremento-topic-done-button";
    button.type = "button";
    button.textContent = "✓ Done";
    button.title = %s;
    button.setAttribute("aria-label", "Mark topic as done");
    button.setAttribute("aria-description", button.title);
    button.onclick = () => pycmd(command);
    cell.appendChild(button);
    anchor.parentElement.insertBefore(cell, anchor.nextSibling);
  }
  install();
})();
""" % (json.dumps(command), json.dumps(DONE_DESCRIPTION))


@dataclass(frozen=True)
class _Request:
    reviewer: object
    collection: object
    profile: str
    card_id: int
    command: str


class TopicReviewActions:
    def __init__(self, is_topic_card, get_profile, get_done_tag=None):
        self._is_topic = is_topic_card
        self._profile = get_profile
        self._done_tag = get_done_tag or (lambda: DEFAULT_TOPIC_DONE_TAG)
        self._request: _Request | None = None
        self._pending: _Request | None = None
        self._notice = None

    def _same_profile(self, request) -> bool:
        mw = request.reviewer.mw
        return mw.col is request.collection and self._profile() == request.profile

    def _current(self, request) -> bool:
        reviewer = request.reviewer
        card = getattr(reviewer, "card", None)
        return bool(
            self._same_profile(request)
            and reviewer.mw.state == "review"
            and reviewer.mw.reviewer is reviewer
            and reviewer.state in ("question", "answer")
            and card is not None and int(card.id) == request.card_id
            and self._is_topic(card)
        )

    def command_for(self, reviewer) -> str | None:
        card = getattr(reviewer, "card", None)
        if card is None or not self._is_topic(card) or reviewer.mw.state != "review":
            self._request = None
            return None
        if self._request is None or not self._current(self._request):
            self._request = _Request(
                reviewer, reviewer.mw.col, self._profile(), int(card.id),
                _COMMAND_PREFIX + secrets.token_hex(16),
            )
        return self._request.command

    def sync(self, reviewer) -> None:
        reviewer.bottom.web.eval(build_topic_done_button_js(self.command_for(reviewer)))

    def handle_command(self, reviewer, command: str) -> bool:
        if not command.startswith(_COMMAND_PREFIX):
            return False
        request = self._request
        if request and request.reviewer is reviewer and command == request.command:
            self._run(request)
        return True

    def _run(self, request, *, months=None, on_date=None) -> None:
        if self._pending is not None or not self._current(request):
            return
        from aqt import gui_hooks
        from aqt.operations import CollectionOp

        completing = months is None and on_date is None
        done_tag = self._done_tag() if completing else None
        if completing:
            gui_hooks.reviewer_will_suspend_card(request.card_id)
        self._pending = request

        def operation(col):
            if col is not request.collection or not self._current(request):
                raise StaleTopicAction("The current topic changed. Please try again.")
            if not self._is_topic(col.get_card(request.card_id)):
                raise StaleTopicAction("This card is no longer a topic.")
            if completing:
                return complete_topic(col, request.card_id, done_tag=done_tag)
            return revisit_topic(col, request.card_id, months=months, on_date=on_date)

        def success(result):
            if self._pending is request:
                self._pending = None
            if self._current(request):
                self._show_notice(
                    request.reviewer.mw, result.message,
                    lambda: self._undo(request, result.undo_step),
                )
            # CollectionOp's normal study-queue hook advances the reviewer once.

        def failure(exc):
            if self._pending is request:
                self._pending = None
            if self._same_profile(request):
                self._show_error(request.reviewer.mw, exc)

        try:
            CollectionOp(request.reviewer.mw, operation).success(success).failure(failure).run_in_background()
        except Exception as exc:
            failure(exc)

    def _undo(self, request, step) -> None:
        self._close_notice()
        if not self._same_profile(request):
            return
        from aqt import gui_hooks
        from aqt.operations import CollectionOp

        def operation(col):
            if col is not request.collection or not self._same_profile(request):
                raise StaleTopicAction("The profile changed.")
            return undo_topic_action(col, step)

        def success(result):
            if self._same_profile(request):
                gui_hooks.state_did_undo(result)

        def failure(exc):
            if self._same_profile(request):
                self._show_error(request.reviewer.mw, exc)

        CollectionOp(request.reviewer.mw, operation).success(success).failure(failure).run_in_background()

    def add_context_menu(self, reviewer, menu) -> None:
        if self.command_for(reviewer) is None:
            return
        request = self._request
        menu.addSeparator()
        done = menu.addAction("Mark Topic as Done")
        done.setToolTip(DONE_DESCRIPTION)
        done.triggered.connect(lambda _checked=False: self._run(request))
        revisit = menu.addMenu("Revisit in…")
        for months in (3, 6, 12):
            action = revisit.addAction(f"{months} months")
            action.triggered.connect(lambda _checked=False, m=months: self._run(request, months=m))
        revisit.addSeparator()
        revisit.addAction("Choose date…").triggered.connect(lambda _checked=False: self._choose_date(request))

    def _choose_date(self, request) -> None:
        if not self._current(request):
            return
        from aqt.qt import QDate, QDateEdit, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

        dialog = QDialog(request.reviewer.mw)
        dialog.setWindowTitle("Revisit Topic")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Choose when this topic should next be due:"))
        today = anki_logical_today(collection=request.collection)
        picker = QDateEdit(dialog)
        picker.setCalendarPopup(True)
        picker.setDisplayFormat("yyyy-MM-dd")
        picker.setMinimumDate(QDate(*(today + timedelta(days=1)).timetuple()[:3]))
        picker.setMaximumDate(QDate(*(today + timedelta(days=36500)).timetuple()[:3]))
        picker.setDate(QDate(*(today + timedelta(days=365)).timetuple()[:3]))
        picker.setAccessibleName("Next review date")
        layout.addWidget(picker)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = picker.date()
            self._run(request, on_date=date(selected.year(), selected.month(), selected.day()))
        dialog.deleteLater()

    def _show_notice(self, parent, message, undo_callback) -> None:
        from aqt.qt import QFrame, QHBoxLayout, QLabel, QPushButton, Qt, QTimer

        self._close_notice()
        notice = QFrame(parent)
        notice.setObjectName("incremento-topic-action-notice")
        notice.setFrameShape(QFrame.Shape.StyledPanel)
        notice.setAutoFillBackground(True)
        notice.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout = QHBoxLayout(notice)
        label = QLabel(message, notice)
        label.setWordWrap(True)
        layout.addWidget(label)
        undo_button = QPushButton("Undo", notice)
        undo_button.setAccessibleName("Undo topic action")
        undo_button.clicked.connect(lambda _checked=False: undo_callback())
        layout.addWidget(undo_button)
        close = QPushButton("×", notice)
        close.setAccessibleName("Dismiss notification")
        close.clicked.connect(self._close_notice)
        layout.addWidget(close)
        notice.setAccessibleName(message)
        notice.adjustSize()
        notice.move(max(8, (parent.width() - notice.width()) // 2), max(8, parent.height() - notice.height() - 90))
        self._notice = notice
        notice.show()
        notice.raise_()
        timer = QTimer(notice)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._close_notice() if self._notice is notice else None)
        timer.start(8000)

    def _close_notice(self) -> None:
        if self._notice is not None:
            self._notice.hide()
            self._notice.deleteLater()
            self._notice = None

    def reset(self) -> None:
        self._request = None
        self._pending = None
        self._close_notice()

    @staticmethod
    def _show_error(parent, exc) -> None:
        from aqt.errors import show_exception
        from aqt.utils import tooltip

        if isinstance(exc, StaleTopicAction):
            tooltip(str(exc), parent=parent)
        else:
            show_exception(parent=parent, exception=exc)
