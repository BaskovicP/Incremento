"""Browser bulk priority changes only the captured selection, atomically and per profile."""

import ast
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import priority_manager
import browser_priority_toolbar
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_function(name, namespace):
    tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "__init__.py"), "exec"), namespace)
    return namespace[name]


@pytest.fixture
def context(tmp_path, monkeypatch):
    pending, dialogs, messages = [], [], []
    state = SimpleNamespace(profile="BulkA", accepted=True, priority=17.1234, visible=True)
    anki_db = sqlite3.connect(":memory:")
    anki_db.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, ivl INTEGER)")
    anki_db.executemany("INSERT INTO cards VALUES (?, 12)", [(cid,) for cid in range(1, 1003)])
    collection = SimpleNamespace(db=SimpleNamespace(
        list=lambda sql, *args: [row[0] for row in anki_db.execute(sql, args)]))
    main = SimpleNamespace(col=collection)
    refreshed = []
    browser = SimpleNamespace(
        col=collection, isVisible=lambda: state.visible, search=lambda: refreshed.append(True),
        selected_cards=lambda: [1, 2],
    )

    class Query:
        def __init__(self, parent, op, success):
            self.op, self.success = op, success

        def failure(self, callback):
            self.failed = callback
            return self

        def run_in_background(self):
            pending.append(self)

        def finish(self):
            try:
                result = self.op(main.col)
            except Exception as exc:
                self.failed(exc)
            else:
                self.success(result)

    class Dialog:
        def __init__(self, **kwargs):
            dialogs.append(kwargs)

        def exec(self):
            return state.accepted

        @property
        def priority(self):
            return state.priority

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=Query))
    namespace = dict(
        mw=main, _ADDON_DIR=str(tmp_path), _active_profile=lambda: state.profile,
        PriorityDialog=Dialog, configured_priority_lower_is_more_important=lambda: False,
        _set_priorities=priority_manager.set_priorities,
        _sync_reviewer_priority_badge=lambda: None,
        _t=lambda key, **kw: kw["count_label"] if key == "root_browser_priority_scope" else key,
        _tn=lambda key, count, **kw: f"{count} {key}",
        showInfo=messages.append, tooltip=messages.append,
    )
    action = _load_function("_open_browser_priority_dialog", namespace)
    yield SimpleNamespace(
        action=action, namespace=namespace, state=state, main=main, browser=browser,
        pending=pending, dialogs=dialogs, messages=messages, refreshed=refreshed,
        anki_db=anki_db,
        priorities=lambda profile="BulkA": priority_manager.get_all_priorities(str(tmp_path), profile),
    )
    anki_db.close()


@pytest.mark.parametrize("priority", [0.0, 17.1234, 100.0])
def test_accepted_bulk_priority_saves_only_selected_cards_and_refreshes_after_commit(context, priority):
    c = context
    c.state.priority = priority
    selected = [1, 2, 2]
    c.action(c.browser, selected)
    selected.append(3)

    assert c.priorities() == {} and c.refreshed == []
    assert c.dialogs[0]["lower_is_more_important"] is False
    assert "2 " in c.dialogs[0]["card_label"]
    c.pending.pop().finish()

    assert c.priorities() == {1: priority, 2: priority}
    assert c.refreshed == [True]
    assert c.messages == ["root_browser_priority_saved"]
    assert c.anki_db.execute("SELECT DISTINCT ivl FROM cards").fetchall() == [(12,)]


def test_bulk_priority_handles_selection_larger_than_sql_parameter_batch(context):
    c = context
    c.action(c.browser, list(range(1, 1002)))
    c.pending.pop().finish()
    assert c.priorities() == dict.fromkeys(range(1, 1002), 17.1234)


@pytest.mark.parametrize("selection, accepted", [([], True), ([1], False)])
def test_empty_or_cancelled_bulk_priority_never_queues_a_write(context, selection, accepted):
    c = context
    c.state.accepted = accepted
    c.action(c.browser, selection)
    assert c.pending == [] and c.priorities() == {} and c.refreshed == []


def test_card_deleted_before_bulk_save_leaves_all_priorities_unchanged(context):
    c = context
    c.action(c.browser, [1, 2])
    c.anki_db.execute("DELETE FROM cards WHERE id=2")
    c.pending.pop().finish()
    assert c.priorities() == {} and c.refreshed == []
    assert c.messages == ["root_browser_priority_failed"]


@pytest.mark.parametrize("changed", ["profile", "collection"])
def test_stale_bulk_priority_worker_does_not_write(context, changed):
    c = context
    c.action(c.browser, [1, 2])
    if changed == "profile":
        c.state.profile = "BulkB"
    else:
        c.main.col = object()
    c.pending.pop().finish()
    assert c.priorities() == {} and c.priorities("BulkB") == {}
    assert c.refreshed == [] and c.messages == []


@pytest.mark.parametrize("changed", ["profile", "collection", "closed"])
def test_bulk_priority_completion_does_not_refresh_a_stale_or_closed_browser(context, changed):
    c = context
    c.action(c.browser, [1])
    query = c.pending.pop()
    result = query.op(c.main.col)
    if changed == "profile":
        c.state.profile = "BulkB"
    elif changed == "collection":
        c.main.col = object()
    else:
        c.state.visible = False
    query.success(result)
    assert c.priorities() == {1: 17.1234}
    assert c.refreshed == [] and c.messages == []


def test_bulk_priority_storage_failure_rolls_back_the_whole_selection(context):
    c = context
    conn = priority_manager.get_connection(c.namespace["_ADDON_DIR"], "BulkA")
    conn.execute("INSERT INTO priorities VALUES (1, 80)")
    conn.execute("CREATE TRIGGER reject_priority BEFORE INSERT ON priorities "
                 "WHEN NEW.card_id=2 BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    conn.commit()
    c.action(c.browser, [1, 2])
    c.pending.pop().finish()
    assert c.priorities() == {1: 80.0} and c.refreshed == []
    assert c.messages == ["root_browser_priority_failed"]


def test_browser_incremento_context_menu_applies_priority_to_its_captured_selection(context):
    c = context

    class Menu:
        def __init__(self, *args):
            self.actions, self.menus = [], []

        def addSeparator(self):
            pass

        def addAction(self, action):
            self.actions.append(action)

        def addMenu(self, menu):
            self.menus.append(menu)

    class Action:
        def __init__(self, text, parent):
            self.text = text
            self.triggered = SimpleNamespace(callback=None)

    c.namespace.update(
        QMenu=Menu, QAction=Action, _browser_selected_incremento_card_ids=lambda browser: [1, 2, 3],
        _browser_priority_toolbar_mod=browser_priority_toolbar,
        qconnect=lambda signal, callback: setattr(signal, "callback", callback),
    )
    build_menu = _load_function("_on_browser_context_menu", c.namespace)
    menu = Menu()
    build_menu(c.browser, menu)
    action = next(a for a in menu.menus[0].actions if a.text == "root_browser_set_priority")
    action.triggered.callback()
    c.pending.pop().finish()
    assert c.priorities() == {1: 17.1234, 2: 17.1234}
