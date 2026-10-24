"""Selected text is searched only after an explicit action, in an isolated popup."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest


@pytest.mark.parametrize("engine,host,path", [
    ("google", "www.google.com", "/search"),
    ("duckduckgo", "duckduckgo.com", "/"),
    ("https://untrusted.test/", "www.google.com", "/search"),
])
def test_selected_engine_receives_one_encoded_bounded_query(engine, host, path):
    from frontend import selection_search as search
    url = urlsplit(search.search_url("čaj & <tea>#?", engine))
    assert (url.scheme, url.netloc, url.path, url.fragment) == ("https", host, path, "")
    assert parse_qs(url.query) == {"q": ["čaj & <tea>#?"]}


def test_configured_engine_is_named_in_the_menu(monkeypatch):
    from frontend import selection_search as search
    monkeypatch.setattr(search, "_search_engine", "google", raising=False)
    monkeypatch.setattr(search, "_remember_logins", False, raising=False)
    search.configure_search({"web_search_engine": "duckduckgo"})
    menu = Menu()
    search.add_selection_search_action(SimpleNamespace(selectedText=lambda: "tea"), menu)
    assert menu.items[-1].label == "Search DuckDuckGo"


class Signal:
    def connect(self, callback):
        self.callback = callback

    def emit(self, *args):
        self.callback(*args)


class Menu:
    def __init__(self):
        self.items = [SimpleNamespace(objectName=lambda: "copy")]
        self.separators = 0

    def actions(self):
        return self.items

    def addSeparator(self):
        self.separators += 1

    def addAction(self, label):
        action = SimpleNamespace(label=label, triggered=Signal())
        action.setObjectName = lambda name: setattr(action, "name", name)
        action.objectName = lambda: action.name
        self.items.append(action)
        return action


@pytest.mark.parametrize("text", [None, "", " \n\t\u2029", "\x00\x7f", 42])
def test_empty_or_invalid_selection_does_not_produce_a_search(text):
    from frontend import selection_search as search

    assert search.google_search_url(text) is None


def test_search_encodes_selection_as_one_query_without_interpreting_html_or_urls():
    from frontend import selection_search as search

    text = 'čaj & tea\u2029<script>"x"</script> #a?b=2'
    url = urlsplit(search.google_search_url(text))

    assert (url.scheme, url.netloc, url.path, url.fragment) == (
        "https", "www.google.com", "/search", ""
    )
    assert parse_qs(url.query) == {"q": ['čaj & tea <script>"x"</script> #a?b=2']}


def test_large_and_malformed_unicode_selection_is_bounded_and_encodable():
    from frontend import selection_search as search

    url = search.google_search_url("\ud800" + "a" * 100_000)

    assert parse_qs(urlsplit(url).query) == {"q": ["a" * 1000]}


def test_multibyte_selection_fits_the_browser_url_limit():
    from frontend import selection_search as search
    from backend.content_safety import normalize_external_http_url

    url = search.google_search_url("学" * 1000)

    assert normalize_external_http_url(url) == url
    query = parse_qs(urlsplit(url).query)["q"][0]
    assert query and set(query) == {"学"}


def test_menu_preserves_copy_and_searches_the_captured_selection_only_on_click(monkeypatch):
    from frontend import selection_search as search

    selected = ["original selection"]
    view = SimpleNamespace(selectedText=lambda: selected[0], window=lambda: "owner")
    opened = []
    monkeypatch.setattr(search, "_active_profile", lambda: "Synthetic")
    monkeypatch.setattr(search, "show_google_search", lambda text, parent=None: opened.append((text, parent)))
    menu = Menu()

    search.add_selection_search_action(view, menu)
    search.add_selection_search_action(view, menu)
    assert len(menu.items) == 2
    assert menu.items[0].objectName() == "copy"
    assert opened == []

    selected[0] = "changed after menu opened"
    menu.items[-1].triggered.emit(False)
    assert opened == [("original selection", "owner")]


def test_menu_without_selection_keeps_only_native_actions():
    from frontend import selection_search as search

    menu = Menu()
    search.add_selection_search_action(SimpleNamespace(selectedText=lambda: "  "), menu)

    assert len(menu.items) == 1
    assert menu.separators == 0


def test_search_menu_from_previous_profile_cannot_open_a_popup(monkeypatch):
    from frontend import selection_search as search

    profile = ["First"]
    monkeypatch.setattr(search, "_active_profile", lambda: profile[0])
    opened = []
    monkeypatch.setattr(search, "show_google_search", lambda *args, **kwargs: opened.append(args))
    menu = Menu()
    search.add_selection_search_action(SimpleNamespace(selectedText=lambda: "selected"), menu)
    profile[0] = "Second"

    menu.items[-1].triggered.emit(False)

    assert opened == []


def test_native_text_editor_selection_can_be_searched(monkeypatch):
    from frontend import selection_search as search

    monkeypatch.setattr(search, "_active_profile", lambda: "Synthetic")
    editor = SimpleNamespace(textCursor=lambda: SimpleNamespace(selectedText=lambda: "one\u2029two"))
    menu = Menu()

    search.add_selection_search_action(editor, menu)

    assert len(menu.items) == 2


def test_profile_close_disposes_of_popup_and_clears_reference(monkeypatch):
    from frontend import selection_search as search

    events = []
    popup = SimpleNamespace(close=lambda: events.append("close"), dispose=lambda: events.append("delete"))
    monkeypatch.setattr(search, "_popup", popup)

    search.reset_for_profile_switch()
    search.reset_for_profile_switch()

    assert events == ["close", "delete"]
    assert search._popup is None


def test_reader_menu_includes_search_even_when_no_copy_anchor_is_resolved(monkeypatch):
    import reader_links
    from frontend import selection_search as search

    opened = []
    monkeypatch.setattr(search, "_active_profile", lambda: "Synthetic")
    monkeypatch.setattr(search, "show_google_search", lambda text, parent=None: opened.append(text))
    menu = Menu()
    menu.exec = lambda position: None
    view = SimpleNamespace(
        selectedText=lambda: "reader excerpt",
        window=lambda: None,
        createStandardContextMenu=lambda: menu,
        mapToGlobal=lambda position: position,
    )

    assert reader_links.show_reader_anchor_context_menu(
        view, (10, 20), resolver_script="resolve()", on_copy=lambda payload: None,
        run_javascript=lambda script, callback: callback(None),
    )

    assert len(menu.items) == 2
    menu.items[-1].triggered.emit(False)
    assert opened == ["reader excerpt"]


def test_root_registers_card_editor_and_profile_hooks_once_without_replacing_other_handlers():
    import ast
    from pathlib import Path
    from frontend import selection_search as search

    class Hook:
        # Anki hook objects expose append/remove, but are not iterable.
        def __init__(self):
            self.callbacks = ["another addon"]

        def append(self, callback):
            self.callbacks.append(callback)

        def remove(self, callback):
            if callback in self.callbacks:
                self.callbacks.remove(callback)

    hooks = SimpleNamespace(**{name: Hook() for name in (
        "webview_will_show_context_menu", "editor_will_show_context_menu", "profile_will_close"
    )})
    tree = ast.parse((Path(__file__).resolve().parents[1] / "__init__.py").read_text())
    register = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_register_selection_search_hooks")
    namespace = {"gui_hooks": hooks, "_selection_search_mod": search}
    exec(compile(ast.Module(body=[register], type_ignores=[]), "<search-hooks>", "exec"), namespace)
    namespace[register.name]()
    namespace[register.name]()

    for name in ("webview_will_show_context_menu", "editor_will_show_context_menu"):
        assert getattr(hooks, name).callbacks == ["another addon", search.add_selection_search_action]
    assert hooks.profile_will_close.callbacks == ["another addon", search.reset_for_profile_switch]


def test_web_browsers_close_on_profile_close_and_quit_with_idempotent_registration():
    import ast
    from pathlib import Path
    from unittest.mock import Mock

    class Callbacks:
        def __init__(self):
            self.callbacks = ["another addon"]

        def remove(self, callback):
            if callback in self.callbacks:
                self.callbacks.remove(callback)

        append = lambda self, callback: self.callbacks.append(callback)
        connect = append
        disconnect = remove

    tree = ast.parse((Path(__file__).resolve().parents[1] / "__init__.py").read_text())
    names = {"_close_website_browsers", "_register_website_browser_shutdown"}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in definitions} == names
    hook, quit_signal = Callbacks(), Callbacks()
    web, search = Mock(), Mock()
    namespace = {"_web_dock_mod": web, "_selection_search_mod": search,
                 "gui_hooks": SimpleNamespace(profile_will_close=hook),
                 "mw": SimpleNamespace(app=SimpleNamespace(aboutToQuit=quit_signal))}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "<browser-shutdown>", "exec"), namespace)
    namespace["_register_website_browser_shutdown"]()
    namespace["_register_website_browser_shutdown"]()
    assert hook.callbacks == ["another addon", web.reset_for_profile_switch]
    assert quit_signal.callbacks == ["another addon", namespace["_close_website_browsers"]]
    quit_signal.callbacks[-1]()
    web.reset_for_profile_switch.assert_called_once_with()
    search.reset_for_profile_switch.assert_called_once_with()
