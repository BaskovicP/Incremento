from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest


@pytest.fixture
def ui(monkeypatch):
    import reviewer_topic_actions as module

    pending = []

    class Op:
        def __init__(self, parent, op):
            self.op = op

        def success(self, callback):
            self.on_success = callback
            return self

        def failure(self, callback):
            self.on_failure = callback
            return self

        def run_in_background(self):
            pending.append(self)

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(CollectionOp=Op))
    card = SimpleNamespace(id=42, nid=123, queue=2, topic=True)
    col = Mock()
    col.get_card.return_value = card
    col.undo_status.return_value = SimpleNamespace(undo="Suspend", last_step=7)
    mw = SimpleNamespace(col=col, state="review")
    reviewer = SimpleNamespace(mw=mw, card=card, state="question", bottom=SimpleNamespace(web=Mock()))
    mw.reviewer = reviewer
    profile = ["Synthetic"]
    done_tag = ["topic/done"]
    controller = module.TopicReviewActions(lambda c: c.topic, lambda: profile[0], lambda: done_tag[0])
    monkeypatch.setattr(controller, "_show_notice", Mock())
    monkeypatch.setattr(controller, "_show_error", Mock())
    return SimpleNamespace(
        module=module, controller=controller, reviewer=reviewer, col=col,
        card=card, profile=profile, pending=pending, done_tag=done_tag,
    )


@pytest.mark.parametrize("side", ["question", "answer"])
def test_done_button_dispatches_one_card_only_and_reports_undo(ui, side):
    ui.reviewer.state = side
    command = ui.controller.command_for(ui.reviewer)
    assert command.startswith("incremento_topic_done:")
    assert ui.controller.handle_command(ui.reviewer, command)
    assert ui.controller.handle_command(ui.reviewer, command)  # double click is ignored
    assert len(ui.pending) == 1
    op = ui.pending[0]
    result = op.op(ui.col)
    ui.col.sched.suspend_cards.assert_called_once_with([42])
    ui.col.tags.bulk_add.assert_called_once_with([123], "topic/done")
    ui.col.sched.answer_card.assert_not_called()
    op.on_success(result)
    assert ui.controller._show_notice.call_args.args[1] == "Topic marked as done."
    undo_callback = ui.controller._show_notice.call_args.args[2]
    undo_callback()
    assert len(ui.pending) == 2
    ui.pending[1].op(ui.col)
    ui.col.undo.assert_called_once()


def test_done_captures_selected_tag_before_background_work(ui):
    ui.done_tag[0] = "reading::finished"
    ui.controller.handle_command(ui.reviewer, ui.controller.command_for(ui.reviewer))
    ui.done_tag[0] = "reference/completed"
    ui.pending[0].op(ui.col)
    ui.col.tags.bulk_add.assert_called_once_with([123], "reading::finished")


def test_more_menu_done_uses_the_same_selected_tag(ui):
    ui.done_tag[0] = "reading::finished"
    menu = Mock()
    ui.controller.add_context_menu(ui.reviewer, menu)
    done_callback = menu.addAction.return_value.triggered.connect.call_args.args[0]
    done_callback()
    assert len(ui.pending) == 1
    ui.pending[0].op(ui.col)
    ui.col.sched.suspend_cards.assert_called_once_with([42])
    ui.col.tags.bulk_add.assert_called_once_with([123], "reading::finished")


@pytest.mark.parametrize("change", ["card", "profile", "collection", "item", "closed"])
def test_stale_done_command_does_not_change_collection(ui, change):
    command = ui.controller.command_for(ui.reviewer)
    if change == "card":
        ui.reviewer.card = SimpleNamespace(id=43, topic=True)
    elif change == "profile":
        ui.profile[0] = "Another"
    elif change == "collection":
        ui.reviewer.mw.col = Mock()
    elif change == "item":
        ui.card.topic = False
    else:
        ui.reviewer.mw.state = "overview"
    assert ui.controller.handle_command(ui.reviewer, command)
    assert ui.pending == []


def test_background_profile_switch_aborts_before_suspension(ui):
    ui.controller.handle_command(ui.reviewer, ui.controller.command_for(ui.reviewer))
    ui.profile[0] = "Another"
    with pytest.raises(ui.module.StaleTopicAction):
        ui.pending[0].op(ui.col)
    ui.col.sched.suspend_cards.assert_not_called()
    ui.col.tags.bulk_add.assert_not_called()


def test_late_success_does_not_show_notice_in_another_profile(ui):
    ui.controller.handle_command(ui.reviewer, ui.controller.command_for(ui.reviewer))
    result = ui.pending[0].op(ui.col)
    ui.profile[0] = "Another"
    ui.pending[0].on_success(result)
    ui.controller._show_notice.assert_not_called()


def test_failure_keeps_card_available_and_allows_retry(ui):
    command = ui.controller.command_for(ui.reviewer)
    ui.controller.handle_command(ui.reviewer, command)
    ui.pending[0].on_failure(RuntimeError("Synthetic failure"))
    ui.controller._show_notice.assert_not_called()
    ui.controller._show_error.assert_called_once()
    ui.controller.handle_command(ui.reviewer, command)
    assert len(ui.pending) == 2


def test_item_has_no_done_command(ui):
    ui.card.topic = False
    assert ui.controller.command_for(ui.reviewer) is None


def test_unknown_and_previous_card_commands_are_ignored(ui):
    old_command = ui.controller.command_for(ui.reviewer)
    ui.reviewer.card = SimpleNamespace(id=43, queue=2, topic=True)
    new_command = ui.controller.command_for(ui.reviewer)
    assert old_command != new_command
    assert ui.controller.handle_command(ui.reviewer, old_command)
    assert not ui.controller.handle_command(ui.reviewer, "ans")
    assert ui.pending == []


def test_late_success_after_card_change_does_not_show_notice(ui):
    ui.controller.handle_command(ui.reviewer, ui.controller.command_for(ui.reviewer))
    result = ui.pending[0].op(ui.col)
    ui.reviewer.card = SimpleNamespace(id=43, queue=2, topic=True)
    ui.pending[0].on_success(result)
    ui.controller._show_notice.assert_not_called()


def test_menu_revisit_routes_to_one_time_schedule_and_rejects_stale_selection(ui, monkeypatch):
    class Menu:
        def __init__(self):
            self.entries = {}

        def addSeparator(self):
            pass

        def addAction(self, text):
            action = SimpleNamespace(triggered=Mock(), setToolTip=Mock())
            self.entries[text] = action
            return action

        def addMenu(self, text):
            menu = Menu()
            self.entries[text] = menu
            return menu

    menu = Menu()
    ui.controller.add_context_menu(ui.reviewer, menu)
    assert "Mark Topic as Done" in menu.entries
    revisit = menu.entries["Revisit in…"]
    assert list(revisit.entries) == ["3 months", "6 months", "12 months", "Choose date…"]
    apply = Mock(return_value=SimpleNamespace(message="Scheduled", undo_step=7))
    monkeypatch.setattr(ui.module, "revisit_topic", apply)
    choose_year = revisit.entries["12 months"].triggered.connect.call_args.args[0]
    choose_year()
    result = ui.pending[0].op(ui.col)
    apply.assert_called_once_with(ui.col, 42, months=12, on_date=None)
    ui.pending[0].on_success(result)
    ui.col.sched.suspend_cards.assert_not_called()
    ui.reviewer.card = SimpleNamespace(id=43, queue=2, topic=True)
    choose_year()
    assert len(ui.pending) == 1


def test_rendered_done_button_is_secondary_and_cannot_leak_to_items():
    import json
    import subprocess
    from reviewer_topic_actions import build_topic_done_button_js

    scripts = [build_topic_done_button_js(command) for command in ("first", "second", None)]
    harness = r'''
      const assert = require("node:assert/strict");
      const vm = require("node:vm");
      const scripts = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
      class Element {
        constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; }
        appendChild(child) { child.parentElement = this; this.children.push(child); }
        remove() { if (this.parentElement) this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1); }
        setAttribute(name, value) { this.attributes[name] = value; }
        closest(tag) { return this.tag === tag ? this : this.parentElement?.closest(tag); }
        get nextSibling() { return this.parentElement.children[this.parentElement.children.indexOf(this) + 1] || null; }
        insertBefore(child, next) {
          child.parentElement = this;
          const index = next ? this.children.indexOf(next) : this.children.length;
          this.children.splice(index, 0, child);
        }
      }
      for (const side of ["question", "answer"]) {
        const head = new Element("head"), row = new Element("tr");
        function all(node) { return [node, ...node.children.flatMap(all)]; }
        const buttons = side === "answer" ? [1, 2, 3].map(ease => {
          const td = new Element("td"), button = new Element("button");
          button.attributes["data-ease"] = ease; td.appendChild(button); row.appendChild(td); return button;
        }) : [];
        if (side === "question") {
          const td = new Element("td"), button = new Element("button");
          button.id = "ansbut"; td.appendChild(button); row.appendChild(td);
        }
        const extract = new Element("td"); extract.id = "extract"; row.appendChild(extract);
        const sent = [], timers = [];
        let anchorsReady = true;
        const context = vm.createContext({
          window: {}, pycmd: command => sent.push(command), setTimeout: callback => timers.push(callback),
          document: {head, createElement: tag => new Element(tag),
            getElementById: id => all(head).concat(all(row)).find(el => el.id === id && (anchorsReady || id !== "ansbut")),
            querySelectorAll: () => anchorsReady ? buttons : [],
          },
        });
        const get = id => context.document.getElementById(id);
        vm.runInContext(scripts[0], context);
        let done = get("incremento-topic-done-button");
        assert.equal(done.textContent, "✓ Done");
        assert.equal(done.attributes["aria-label"], "Mark topic as done");
        assert.match(done.title, /Extracted cards continue reviewing/);
        assert.equal(done.attributes["data-ease"], undefined);
        assert.equal(row.children.at(-2).id, "incremento-topic-done-cell");
        done.onclick(); assert.deepEqual(sent, ["first"]);
        vm.runInContext(scripts[1], context);
        assert.equal(all(row).filter(el => el.id === "incremento-topic-done-button").length, 1);
        get("incremento-topic-done-button").onclick(); assert.deepEqual(sent, ["first", "second"]);
        vm.runInContext(scripts[2], context);
        assert.equal(get("incremento-topic-done-button"), undefined);
        anchorsReady = false;
        vm.runInContext(scripts[0], context);
        assert.equal(timers.length, 1);
        vm.runInContext(scripts[2], context);
        anchorsReady = true;
        timers.shift()();
        assert.equal(get("incremento-topic-done-button"), undefined);
      }
    '''
    result = subprocess.run(["node", "-e", harness], input=json.dumps(scripts), text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
