import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest


def test_tall_pdf_preview_keeps_page_aspect_ratio_within_raster_budget(tmp_path, monkeypatch):
    import pdf_bookshelf as shelf
    dimensions = []
    document = SimpleNamespace(load=lambda path: None, pageCount=lambda: 1,
        pagePointSize=lambda page: SimpleNamespace(width=lambda: 100, height=lambda: 1000),
        render=lambda page, size: dimensions.append(size) or SimpleNamespace(isNull=lambda: False),
        close=lambda: None)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"test fixture")
    monkeypatch.setattr(shelf, "QPdfDocument", lambda parent: document)
    monkeypatch.setattr(shelf, "QSize", lambda width, height: (width, height))
    assert shelf._render_pdf_first_page(str(path)) is not None
    assert dimensions == [(32, 320)]


# Some older dialog tests replace the shared aqt.qt test double during
# collection. Supply only the names needed to import this dialog module so the
# pure loader/path regressions remain order-independent.
_qt_module = sys.modules.get("aqt.qt")
if _qt_module is not None:
    for _name in (
        "QAbstractItemView",
        "QCheckBox",
        "QColor",
        "QComboBox",
        "QCompleter",
        "QDialog",
        "QEvent",
        "QHBoxLayout",
        "QIcon",
        "QLabel",
        "QLineEdit",
        "QListView",
        "QListWidget",
        "QListWidgetItem",
        "QMenu",
        "QPalette",
        "QPainter",
        "QPen",
        "QPixmap",
        "QPushButton",
        "QSize",
        "QStyle",
        "QStyleOptionViewItem",
        "QStyledItemDelegate",
        "QTimer",
        "QVBoxLayout",
    ):
        if not hasattr(_qt_module, _name):
            setattr(_qt_module, _name, type(_name, (), {}))
    if not hasattr(_qt_module, "qconnect"):
        _qt_module.qconnect = lambda *_args, **_kwargs: None

# Real class bases let the menu callbacks execute under the shared Qt stub.
# Restore the Qt boundary immediately so other dialog tests keep their own setup.
with pytest.MonkeyPatch.context() as _imports:
    if _qt_module is not None:
        for _name in ("QDialog", "QCompleter", "QStyledItemDelegate"):
            _imports.setattr(_qt_module, _name, type(_name, (), {}))
    import pdf_bookshelf


ROOT = Path(__file__).resolve().parents[1]


def test_missing_pdf_scan_checks_profile_files_instead_of_covers(bookshelf_reveal_menu, monkeypatch, tmp_path):
    shelf = bookshelf_reveal_menu
    (shelf.roots["PDF"] / "present.pdf").write_bytes(b"synthetic PDF")
    (shelf.roots["PDF"] / "directory.pdf").mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"outside profile")
    (shelf.roots["PDF"] / "escape.pdf").symlink_to(outside)
    monkeypatch.setattr(pdf_bookshelf, "_active_profile", lambda: "OtherProfile")
    entries = [
        pdf_bookshelf._BookshelfEntry("Present", 1, "PDF", source_filename="present.pdf"),
        pdf_bookshelf._BookshelfEntry("Missing with cover", 2, "PDF", source_filename="missing.pdf",
                                     cover_filename="saved-cover.png"),
        pdf_bookshelf._BookshelfEntry("Empty filename", 3, "PDF"),
        pdf_bookshelf._BookshelfEntry("Directory", 4, "PDF", source_filename="directory.pdf"),
        pdf_bookshelf._BookshelfEntry("Traversal", 5, "PDF", source_filename="../outside.pdf"),
        pdf_bookshelf._BookshelfEntry("Absolute", 6, "PDF", source_filename=str(outside)),
        pdf_bookshelf._BookshelfEntry("Escaping symlink", 7, "PDF", source_filename="escape.pdf"),
        pdf_bookshelf._BookshelfEntry("Missing EPUB", 8, "EPUB", source_filename="missing.epub"),
    ]

    assert pdf_bookshelf._load_missing_pdf_card_ids(entries, profile=shelf.profile) == {2, 3, 4, 5, 6, 7}
    assert outside.read_bytes() == b"outside profile"


def test_missing_pdf_scan_stops_between_files_and_before_start(monkeypatch):
    cancelled = threading.Event()
    inspected = []
    entries = [pdf_bookshelf._BookshelfEntry(f"PDF {cid}", cid, "PDF") for cid in (1, 2)]

    def source_path(entry, *, profile):
        inspected.append((entry.card_id, profile))
        cancelled.set()
        return ""

    monkeypatch.setattr(pdf_bookshelf, "_bookshelf_source_path", source_path)
    assert pdf_bookshelf._load_missing_pdf_card_ids(entries, profile="Captured", cancelled=cancelled) == {1}
    assert inspected == [(1, "Captured")]
    inspected.clear()
    assert pdf_bookshelf._load_missing_pdf_card_ids(entries, profile="Captured", cancelled=cancelled) == set()
    assert inspected == []


def test_missing_pdf_filter_intersects_title_kind_tags_and_duplicates():
    entries = [
        pdf_bookshelf._BookshelfEntry("Study available", 1, "PDF", tags=("Read", "Work")),
        pdf_bookshelf._BookshelfEntry("Study missing", 2, "PDF", tags=("Read", "Work")),
        pdf_bookshelf._BookshelfEntry("Other missing", 3, "PDF", tags=("Read",)),
        pdf_bookshelf._BookshelfEntry("Study EPUB", 4, "EPUB", tags=("Read", "Work")),
    ]
    filter_entries = pdf_bookshelf._filter_bookshelf_entries
    assert filter_entries(entries, "", missing_files_only=True, missing_pdf_card_ids={2, 3, 4}) == entries[1:3]
    assert filter_entries(entries, "STUDY", "PDF", tag_query="read work", tag_mode="AND",
                          duplicates_only=True, duplicate_card_ids={1, 2, 4},
                          missing_files_only=True, missing_pdf_card_ids={2, 3}) == [entries[1]]
    assert filter_entries(entries, "", "EPUB", missing_files_only=True, missing_pdf_card_ids={2, 3}) == []
    assert filter_entries(entries, "", missing_files_only=True) == []  # Unknown until checked.
    assert filter_entries(entries, "", missing_pdf_card_ids={2, 3}) == entries


def test_missing_pdf_controls_check_in_background_refresh_and_reject_stale_results():
    script = dedent("""
        import os, sys, types
        from concurrent.futures import Future
        from aqt.qt import QApplication
        package = types.ModuleType('incremento')
        package.__path__ = [os.getcwd()]
        sys.modules['incremento'] = package
        from incremento.frontend import pdf_bookshelf as shelf
        app = QApplication([])
        pending, requests, notices = [], [], []
        profile = ['Captured']
        shelf._active_profile = lambda: profile[0]
        def run(worker, done, *, uses_collection):
            assert uses_collection is False
            pending.append((worker, done))
        shelf.mw = types.SimpleNamespace(
            col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: '')),
            taskman=types.SimpleNamespace(run_in_background=run),
        )
        shelf.tooltip = lambda message, **kw: notices.append(message)
        shelf.configured_priority_lower_is_more_important = lambda: True
        shelf._DocumentBookshelfDialog._start_pdf_metadata_scan = lambda self: None
        def scan(entries, *, profile, cancelled):
            requests.append((tuple(e.card_id for e in entries), profile, cancelled))
            return {2, 3}
        shelf._load_missing_pdf_card_ids = scan
        entries = [shelf._BookshelfEntry(title, cid, kind, tags=('Read',)) for title, cid, kind in [
            ('Alpha', 1, 'PDF'), ('Beta', 2, 'PDF'), ('Gamma', 3, 'PDF'), ('EPUB', 4, 'EPUB'),
        ]]
        dialog = shelf._DocumentBookshelfDialog(addon_dir='/synthetic', entries=entries)
        def ids():
            return [dialog._list.item(i).data(shelf.Qt.ItemDataRole.UserRole).card_id
                    for i in range(dialog._list.count())]
        def finish(task, *, result=None, error=None):
            future = Future()
            if error: future.set_exception(error)
            else: future.set_result(result)
            task[1](future)
        assert pending == [] and ids() == [1, 2, 4, 3]
        dialog._missing_files_only_cb.setChecked(True)
        assert len(pending) == 1 and requests == [] and ids() == []
        assert 'Checking PDF files' in dialog._count_label.text()
        assert not dialog._check_files_button.isEnabled()
        result = pending[-1][0]()
        assert requests[0][:2] == ((1, 2, 3, 4), 'Captured')
        finish(pending[-1], result=result)
        assert ids() == [2, 3] and dialog._check_files_button.isEnabled()
        assert 'PDF file missing' in dialog._list.item(0).toolTip()
        dialog._search.setText('BETA')
        dialog._filter_timer.timeout.emit()
        assert ids() == [2]
        dialog._search.clear()
        dialog._filter_timer.timeout.emit()
        dialog._missing_files_only_cb.setChecked(False)
        assert ids() == [1, 2, 4, 3]
        dialog._missing_files_only_cb.setChecked(True)
        assert len(pending) == 1 and ids() == [2, 3]  # Reuse the completed check.
        dialog._check_files_button.click()
        finish(pending[-1], result={3})
        assert ids() == [3]  # A restored file disappears after checking again.
        dialog._check_files_button.click()
        finish(pending[-1], result=set())
        assert ids() == [] and 'Showing 0' in dialog._count_label.text()
        dialog._check_files_button.click()
        stale = pending[-1]
        dialog._missing_files_only_cb.setChecked(False)
        dialog._missing_files_only_cb.setChecked(True)
        finish(stale, result={1})
        assert ids() == []  # Superseded check must not replace the current one.
        finish(pending[-1], error=RuntimeError('synthetic failure'))
        assert not dialog._missing_files_only_cb.isChecked() and ids() == [1, 2, 4, 3]
        assert notices
        dialog._missing_files_only_cb.setChecked(True)
        profile[0] = 'Other'
        finish(pending[-1], result={1})
        assert ids() == []
        profile[0] = 'Captured'
        dialog._missing_files_only_cb.setChecked(False)
        dialog._missing_files_only_cb.setChecked(True)
        collection = shelf.mw.col
        shelf.mw.col = object()
        finish(pending[-1], result={1})
        assert ids() == []
        shelf.mw.col = collection
        dialog.reject()
        finish(pending[-1], result={1})
        assert ids() == []
        dialog = shelf._DocumentBookshelfDialog(addon_dir='/synthetic', entries=entries)
        def cannot_start(*args, **kwargs):
            raise RuntimeError('synthetic dispatch failure')
        shelf.mw.taskman.run_in_background = cannot_start
        dialog._missing_files_only_cb.setChecked(True)
        assert not dialog._missing_files_only_cb.isChecked() and ids() == [1, 2, 4, 3]
        assert not dialog._missing_files_pending
        dialog.reject()
    """)
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_priority_order_uses_configured_direction_and_neutral_default():
    entries = [
        pdf_bookshelf._BookshelfEntry("Low", 1, "PDF", priority=10),
        pdf_bookshelf._BookshelfEntry("Unset", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("High", 3, "PDF", priority=90),
    ]
    sort = pdf_bookshelf._sort_bookshelf_entries
    assert [e.card_id for e in sort(entries, "priority", priority_lower_is_more_important=True)] == [1, 2, 3]
    assert [e.card_id for e in sort(entries, "priority", priority_lower_is_more_important=False)] == [3, 2, 1]
    assert [e.card_id for e in sort(entries, "title")] == [3, 1, 2]
    assert [e.card_id for e in sort(entries, "title", reverse=True)] == [2, 1, 3]
    assert [e.card_id for e in entries] == [1, 2, 3]


@pytest.mark.parametrize("mode", ["due", "reviews", "annotations"])
def test_bookshelf_metric_order_is_numeric_with_stable_title_ties(mode):
    entries = [pdf_bookshelf._BookshelfEntry(title, cid, kind) for title, cid, kind in [
        ("Zulu", 1, "PDF"), ("Alpha", 2, "EPUB"), ("Beta", 3, "PDF"), ("Empty", 4, "EPUB"),
    ]]
    counts = {1: 12, 2: 12, 3: 3}
    assert [e.card_id for e in pdf_bookshelf._sort_bookshelf_entries(entries, mode, counts=counts)] == [2, 1, 3, 4]
    assert [e.card_id for e in pdf_bookshelf._sort_bookshelf_entries(
        entries, mode, counts=counts, reverse=True,
    )] == [4, 3, 2, 1]


def test_bookshelf_random_order_is_stable_across_combined_filters_until_reshuffled():
    import random

    entries = [pdf_bookshelf._BookshelfEntry(f"Book {cid}", cid, "PDF" if cid % 2 else "EPUB",
                                          tags=("Read",)) for cid in range(1, 21)]
    order = pdf_bookshelf._shuffled_bookshelf_order(entries, rng=random.Random(8))
    shuffled = pdf_bookshelf._sort_bookshelf_entries(entries, "random", random_order=order)
    assert sorted(e.card_id for e in shuffled) == list(range(1, 21))
    assert shuffled != entries
    visible = pdf_bookshelf._filter_bookshelf_entries(entries, "Book", "PDF", tag_query="READ")
    assert pdf_bookshelf._sort_bookshelf_entries(visible, "random", random_order=order) == [
        e for e in shuffled if e.kind == "PDF"
    ]
    assert pdf_bookshelf._shuffled_bookshelf_order(entries, rng=random.Random(9)) != order


def test_bookshelf_sort_controls_apply_background_results_and_ignore_stale_callbacks():
    script = dedent("""
        import os, sys, types
        from aqt.qt import QApplication
        package = types.ModuleType('incremento')
        package.__path__ = [os.getcwd()]
        sys.modules['incremento'] = package
        from incremento.frontend import pdf_bookshelf as shelf
        app = QApplication([])
        pending, requests = [], []
        profile = ['Captured']
        shelf._active_profile = lambda: profile[0]
        shelf.mw = types.SimpleNamespace(col=types.SimpleNamespace(media=types.SimpleNamespace(dir=lambda: '')))
        shelf.tooltip = lambda *a, **kw: None
        class Query:
            def __init__(self, **kwargs):
                self.options = kwargs
                pending.append(self)
            def failure(self, callback):
                self.failed = callback
                return self
            def run_in_background(self): pass
        import aqt.operations
        aqt.operations.QueryOp = Query
        def load(addon, captured, documents, *, col, metric, cancelled):
            requests.append((addon, captured, documents, col, metric))
            return {1: 0, 2: 10, 3: 2}
        shelf.load_document_statistics = load
        shelf.configured_priority_lower_is_more_important = lambda: True
        entries = [shelf._BookshelfEntry(title, cid, kind, priority=priority) for title, cid, kind, priority in [
            ('Alpha', 1, 'PDF', 90), ('Beta', 2, 'EPUB', 10), ('Gamma', 3, 'PDF', None),
        ]]
        dialog = shelf._DocumentBookshelfDialog(addon_dir='/synthetic', entries=entries)
        assert dialog._sort_combo.isVisibleTo(dialog), 'Sort by must be visible without opening More filters'
        assert dialog._reverse_sort_cb.isVisibleTo(dialog), 'Reverse order must stay beside Sort by'
        assert dialog._shuffle_button.isVisibleTo(dialog), 'Shuffle again must stay beside Sort by'
        def choose(mode):
            dialog._sort_combo.setCurrentIndex(dialog._sort_combo.findData(mode))
        def ids():
            return [dialog._list.item(i).data(shelf.Qt.ItemDataRole.UserRole).card_id
                    for i in range(dialog._list.count())]
        assert pending == []
        choose('priority')
        assert ids() == [2, 3, 1]
        dialog._reverse_sort_cb.setChecked(True)
        assert ids() == [1, 3, 2]
        dialog._reverse_sort_cb.setChecked(False)
        choose('due')
        assert len(pending) == 1
        collection = object()
        result = pending[-1].options['op'](collection)
        assert requests == [('/synthetic', 'Captured', [(1, 'PDF'), (2, 'EPUB'), (3, 'PDF')], collection, 'due')]
        pending[-1].options['success'](result)
        assert ids() == [2, 3, 1]
        assert 'Due linked cards: 10' in dialog._list.item(0).toolTip()
        assert 'Due linked cards: 10' in dialog._list.item(0).text()
        dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData('PDF'))
        assert ids() == [3, 1]
        choose('title')
        choose('due')
        assert len(pending) == 1  # Cached for this dialog.
        choose('random')
        dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData('ALL'))
        shelf.random.seed(8)
        dialog._shuffle_button.click()
        random_ids = ids()
        dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData('PDF'))
        assert ids() == [cid for cid in random_ids if cid in {1, 3}]
        dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData('ALL'))
        assert ids() == random_ids
        dialog._shuffle_button.click()
        assert ids() != random_ids
        assert sorted(ids()) == [1, 2, 3]
        dialog._kind_combo.setCurrentIndex(dialog._kind_combo.findData('PDF'))
        choose('reviews')
        old = pending[-1]
        choose('annotations')
        old.options['success']({1: 100})
        assert ids() == [1, 3]  # Superseded callback must not apply.
        pending[-1].failed(RuntimeError('synthetic failure'))
        assert dialog._sort_combo.currentData() == 'title'
        choose('reviews')
        profile[0] = 'Other'
        pending[-1].options['success']({3: 100})
        assert ids() == [1, 3]
        profile[0] = 'Captured'
        choose('title')
        choose('reviews')
        original_collection = shelf.mw.col
        shelf.mw.col = object()
        pending[-1].options['success']({3: 100})
        assert ids() == [1, 3]
        shelf.mw.col = original_collection
        dialog.reject()
        pending[-1].options['success']({3: 100})
        assert ids() == [1, 3]
    """)
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_large_exact_origin_duplicate_group_is_compact_and_peers_stay_direct():
    entries = [pdf_bookshelf._BookshelfEntry(
        f"Different title {index}", index + 1, "PDF", source_filename="same-origin.pdf",
    ) for index in range(800)]
    matches = pdf_bookshelf._bookshelf_duplicate_matches(entries)
    assert set(matches) == set(range(1, 801))
    assert len(matches[1]) == 799
    assert matches[1][0].card_id == 2
    assert matches.stored_reference_count < 5_000


def test_bookshelf_reference_choice_accepts_dialog_with_a_distinct_open_mode(monkeypatch):
    accepted = []
    entry = pdf_bookshelf._BookshelfEntry("Reference", 8, "PDF")
    dialog = SimpleNamespace(_profile="A", _selected_entry=lambda: entry,
                             accept=lambda: accepted.append(True))
    monkeypatch.setattr(pdf_bookshelf, "_active_profile", lambda: "A")
    pdf_bookshelf._DocumentBookshelfDialog._accept_reference(dialog, beside=True)
    assert dialog._reference_mode == "beside"
    assert accepted == [True]


@pytest.mark.parametrize("mode", ["preview", "beside", "window", "main"])
@pytest.mark.parametrize('stale_callback', [None, 'success', 'failure'])
def test_bookshelf_root_opens_reference_only_after_modal_picker_exits(monkeypatch, mode, stale_callback):
    import ast
    calls, pending = [], []
    profile = ['A']
    class Query:
        def __init__(self, **options):
            self.options = options
            pending.append(options)
        def failure(self, callback):
            self.options['failure'] = callback
            return self
        def with_progress(self, label): return self
        def run_in_background(self): pass
    class Dialog:
        selected_card_id = 8
        selected_card_type = "PDF"
        reference_mode = mode
        open_card_to_study = True
        preserve_history = False
        def __init__(self, *args, **kwargs): pass
        def exec(self):
            calls.append("modal exited")
            return True
    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=Query))
    tree = ast.parse((ROOT / '__init__.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_open_document_bookshelf')
    namespace = dict(_active_profile=lambda: profile[0], _ADDON_DIR="/unused", mw=object(),
        _last_opened_document_cid=7, _DocumentBookshelfDialog=Dialog, _t=lambda key, **kw: key,
        _open_pdf_card=lambda *a, **kw: calls.append("primary replaced"),
        _open_epub_card=lambda *a, **kw: calls.append("epub"),
        addPdfFunction=lambda: calls.append("import pdf"),
        addEpubFunction=lambda: calls.append("import epub"),
        start_quick_open_review=lambda *a: calls.append("study started"),
        _pdf_dock_mod=SimpleNamespace(_pdf_dock="primary"),
        _pdf_reference_workspace_mod=SimpleNamespace(open_reference=lambda *a, **kw: calls.append((a, kw))),
        showInfo=lambda message: pytest.fail(message))
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<bookshelf-route>', 'exec'), namespace)
    namespace['_open_document_bookshelf']()
    if stale_callback:
        profile[0] = 'B'
        pending[0][stale_callback](([], {}) if stale_callback == 'success' else RuntimeError('stale'))
        assert calls == []
        return
    pending[0]['success'](([], {}))
    expected = ["modal exited", "primary replaced", "study started"] if mode == 'main' else [
        "modal exited", ((8,), {"beside": mode == 'beside', "owner": "primary"})]
    if mode == 'window':
        expected = ['modal exited', ((8,), {'new_window': True, 'owner': 'primary'})]
    assert calls == expected


class _FakeNote:
    def __init__(self, fields=None, named_fields=None, tags=None):
        self.fields = list(fields or [])
        self._named_fields = dict(named_fields or {})
        self.tags = list(tags or [])

    def __getitem__(self, key):
        return self._named_fields[key]


class _FakeCollection:
    def __init__(self, note_ids_by_query, notes, card_ids_by_nid):
        self._note_ids_by_query = dict(note_ids_by_query)
        self._notes = dict(notes)
        self._card_ids_by_nid = dict(card_ids_by_nid)
        self.queries = []
        self.note_reads = []
        self.card_searches = []
        self.batch_reads = []
        self.model_reads = []
        self._connection = sqlite3.connect(":memory:")
        self._connection.executescript("""
            CREATE TABLE notes(id INTEGER PRIMARY KEY, mid INTEGER, flds TEXT, tags TEXT);
            CREATE TABLE cards(id INTEGER PRIMARY KEY, nid INTEGER, queue INTEGER);
            CREATE INDEX ix_cards_nid ON cards(nid);
        """)
        models = {}
        for note_id, note in self._notes.items():
            named = {"Fallback": note.fields[0] if note.fields else "", **note._named_fields}
            names = tuple(named)
            if names not in models:
                models[names] = len(models) + 1
            self._connection.execute("INSERT INTO notes VALUES (?, ?, ?, ?)", (
                note_id, models[names], "\x1f".join(named.values()), " ".join(note.tags),
            ))
        for note_id, card_ids in self._card_ids_by_nid.items():
            self._connection.executemany("INSERT INTO cards VALUES (?, ?, -1)",
                                         [(card_id, note_id) for card_id in card_ids])
        self._models = {
            model_id: {"flds": [{"name": name, "ord": index} for index, name in enumerate(names)]}
            for names, model_id in models.items()
        }
        self.db = SimpleNamespace(all=self._read_rows)
        self.models = SimpleNamespace(get=self._read_model)

    def _read_rows(self, sql, *params):
        self.batch_reads.append((sql, params))
        return self._connection.execute(sql, params).fetchall()

    def _read_model(self, model_id):
        self.model_reads.append(model_id)
        return self._models.get(model_id)

    def find_notes(self, query):
        self.queries.append(query)
        return list(self._note_ids_by_query.get(query, []))

    def get_note(self, note_id):
        self.note_reads.append(note_id)
        return self._notes[note_id]

    def find_cards(self, query):
        self.card_searches.append(query)
        if not str(query).startswith("nid:"):
            return []
        note_id = int(str(query).split(":", 1)[1])
        return list(self._card_ids_by_nid.get(note_id, []))


def test_large_bookshelf_batches_notes_and_keeps_suspended_cards_and_metadata(monkeypatch):
    """Loading 1,203 documents must not do two collection round-trips per note."""
    profile_reads = []
    monkeypatch.setattr(pdf_bookshelf, "get_all_priorities",
                        lambda addon, profile: profile_reads.append((addon, profile)) or {10001: 25})
    notes = {
        nid: _FakeNote(fields=["fallback"], tags=["Reading", "reading", "Work"], named_fields={
            "Title": f"Book {nid:04}", "PDF_Filename": f"{nid}.pdf",
            pdf_bookshelf.PDF_COVER_FIELD: f"{nid}.png",
        }) for nid in range(1, 1203)
    }
    notes[1203] = _FakeNote(fields=["EPUB fallback"], named_fields={
        "Title": "EPUB title", pdf_bookshelf.EPUB_FILE_FIELD: "book.epub",
        pdf_bookshelf.EPUB_COVER_FIELD: "book.jpg",
    })
    collection = _FakeCollection(
        {f'note:"{pdf_bookshelf.PDF_NOTE_TYPE}"': list(range(1, 1203)),
         f'note:"{pdf_bookshelf.EPUB_NOTE_TYPE}"': [1203]},
        notes,
        {**{nid: [nid + 10000] for nid in range(1, 1202)}, 1: [10001, 20001], 1203: [11203]},
    )
    try:
        entries = pdf_bookshelf._load_bookshelf_entries(
            "/unused", profile="Captured", collection=collection,
        )
        assert len(entries) == 1202  # The orphaned note has no card to open.
        assert entries[0] == pdf_bookshelf._BookshelfEntry(
            "Book 0001", 10001, "PDF", "1.png", "1.pdf", 25, ("Reading", "Work"), 1,
        )
        assert entries[-1] == pdf_bookshelf._BookshelfEntry(
            "EPUB title", 11203, "EPUB", "book.jpg", "book.epub", None, (), 1203,
        )
        assert profile_reads == [("/unused", "Captured")]
        assert collection.note_reads == []
        assert collection.card_searches == []
        assert len(collection.batch_reads) <= 3
        assert all(len(params) <= 900 for _, params in collection.batch_reads)
        assert len(collection.model_reads) <= 2
    finally:
        collection._connection.close()


def test_bookshelf_attachment_pass_reads_tree_once_and_refreshes_next_time(monkeypatch):
    import media_review

    reads = []
    tree_rows = [
        {"card_id": 10, "parent_card_id": 1},
        {"card_id": 11, "parent_card_id": 10},
        {"card_id": 20, "parent_card_id": 2},
        {"card_id": 21, "parent_card_id": 20},
        {"card_id": 22, "parent_card_id": 21},  # deleted Anki card
    ]
    monkeypatch.setattr(media_review, "get_knowledge_tree_nodes",
                        lambda addon, profile: reads.append((addon, profile)) or list(tree_rows))
    monkeypatch.setattr(media_review, "get_pdf_document_source_rows", lambda *_args: [])
    monkeypatch.setattr(media_review, "get_epub_document_source_rows", lambda *_args: [])
    cards = {cid: SimpleNamespace(id=cid) for cid in [10, 11, 20, 21]}
    collection = SimpleNamespace(find_notes=lambda _query: [], get_card=cards.__getitem__)
    entries = [pdf_bookshelf._BookshelfEntry("PDF", 1, "PDF"),
               pdf_bookshelf._BookshelfEntry("EPUB", 2, "EPUB")]
    assert pdf_bookshelf._bookshelf_attachment_counts(
        "/unused", "Captured", entries, col=collection,
    ) == {1: 2, 2: 2}
    assert reads == [("/unused", "Captured")]
    tree_rows.pop(1)
    assert pdf_bookshelf._bookshelf_attachment_counts(
        "/unused", "Captured", entries, col=collection,
    ) == {1: 1, 2: 2}
    assert reads == [("/unused", "Captured")] * 2


def test_bookshelf_loads_pdf_and_epub_notes_with_cover_metadata(monkeypatch):
    monkeypatch.setattr(
        pdf_bookshelf,
        "get_all_priorities",
        lambda *_args: {11: 25, 22: 75},
    )
    monkeypatch.setattr(pdf_bookshelf, "_active_profile", lambda: "TestProfile")
    pdf_query = f'note:"{pdf_bookshelf.PDF_NOTE_TYPE}"'
    epub_query = f'note:"{pdf_bookshelf.EPUB_NOTE_TYPE}"'
    collection = _FakeCollection(
        note_ids_by_query={pdf_query: [1], epub_query: [2]},
        notes={
            1: _FakeNote(
                fields=["Alpha fallback"],
                tags=["reading", "Work"],
                named_fields={
                    "Title": "Alpha PDF",
                    "PDF_Filename": "alpha.pdf",
                    pdf_bookshelf.PDF_COVER_FIELD: "alpha-cover.png",
                },
            ),
            2: _FakeNote(
                fields=["Beta fallback"],
                tags=["reading", "machine_learning"],
                named_fields={
                    "Title": "Beta EPUB",
                    pdf_bookshelf.EPUB_FILE_FIELD: "beta.epub",
                    pdf_bookshelf.EPUB_COVER_FIELD: "beta-cover.jpg",
                },
            ),
        },
        card_ids_by_nid={1: [11], 2: [22]},
    )

    entries = pdf_bookshelf._load_bookshelf_entries(
        "/tmp/addon",
        collection=collection,
    )

    assert collection.queries == [pdf_query, epub_query]
    assert all("-is:suspended" not in query for query in collection.queries)
    assert entries == [
        pdf_bookshelf._BookshelfEntry(
            title="Alpha PDF",
            card_id=11,
            kind="PDF",
            cover_filename="alpha-cover.png",
            source_filename="alpha.pdf",
            priority=25,
            tags=("reading", "Work"),
            note_id=1,
        ),
        pdf_bookshelf._BookshelfEntry(
            title="Beta EPUB",
            card_id=22,
            kind="EPUB",
            cover_filename="beta-cover.jpg",
            source_filename="beta.epub",
            priority=75,
            tags=("reading", "machine_learning"),
            note_id=2,
        ),
    ]


def test_bookshelf_snapshot_preloads_attachment_counts_for_title_duplicates(
    monkeypatch,
):
    entries = [
        pdf_bookshelf._BookshelfEntry("Worked Copy", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("worked copy", 2, "PDF"),
        pdf_bookshelf._BookshelfEntry("Unrelated", 3, "PDF"),
    ]
    collection = object()
    calls = []

    def load_entries(addon_dir, *, collection=None, profile=None):
        calls.append(("load", addon_dir, collection, profile))
        return entries

    def attachment_counts(addon_dir, profile, candidates, *, col):
        calls.append(("counts", addon_dir, profile, candidates, col))
        return {1: 4, 2: 0}

    monkeypatch.setattr(pdf_bookshelf, "_load_bookshelf_entries", load_entries)
    monkeypatch.setattr(
        pdf_bookshelf,
        "_bookshelf_attachment_counts",
        attachment_counts,
    )

    snapshot = pdf_bookshelf._load_bookshelf_snapshot(
        "/addon",
        "Captured",
        collection=collection,
    )

    assert snapshot == (entries, {1: 4, 2: 0})
    assert calls == [
        ("load", "/addon", collection, "Captured"),
        ("counts", "/addon", "Captured", entries[:2], collection),
    ]


def test_bookshelf_keeps_legacy_pdf_without_cover_field(monkeypatch):
    monkeypatch.setattr(pdf_bookshelf, "get_all_priorities", lambda *_args: {})
    query = f'note:"{pdf_bookshelf.PDF_NOTE_TYPE}"'
    collection = _FakeCollection(
        note_ids_by_query={query: [7]},
        notes={
            7: _FakeNote(
                fields=["Legacy PDF"],
                named_fields={"PDF_Filename": "legacy.pdf"},
            )
        },
        card_ids_by_nid={7: [77]},
    )

    entries = pdf_bookshelf._load_bookshelf_entries(
        "/tmp/addon",
        collection=collection,
    )

    assert entries == [
        pdf_bookshelf._BookshelfEntry(
            title="Legacy PDF",
            card_id=77,
            kind="PDF",
            cover_filename="",
            source_filename="legacy.pdf",
            priority=None,
            note_id=7,
        )
    ]


def test_bookshelf_filter_is_case_insensitive_and_preserves_order():
    entries = [
        pdf_bookshelf._BookshelfEntry("Alpha", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("Deep Work", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Work Notes", 3, "PDF"),
    ]

    assert pdf_bookshelf._filter_bookshelf_entries(entries, "WORK") == entries[1:]
    assert pdf_bookshelf._filter_bookshelf_entries(entries, "  ") == entries
    assert pdf_bookshelf._filter_bookshelf_entries(entries, "", "EPUB") == [
        entries[1]
    ]


def test_bookshelf_possible_duplicates_match_original_filename_within_kind():
    uuid_a = "a" * 32
    uuid_b = "b" * 32
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            1,
            "PDF",
            source_filename=f"Guide-{uuid_a}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide [2]",
            2,
            "PDF",
            source_filename=f"guide-{uuid_b}.PDF",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            3,
            "EPUB",
            source_filename=f"Guide-{uuid_a}.epub",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            4,
            "PDF",
            source_filename=f"other-{uuid_a}.pdf",
        ),
    ]

    groups = pdf_bookshelf._bookshelf_duplicate_groups(entries)

    assert groups == ((entries[0], entries[1]),)
    assert pdf_bookshelf._bookshelf_duplicate_entries(entries) == entries[:2]


def test_bookshelf_possible_duplicates_fall_back_to_normalized_legacy_title():
    entries = [
        pdf_bookshelf._BookshelfEntry("Legacy Book", 1, "EPUB"),
        pdf_bookshelf._BookshelfEntry("legacy book\u200b", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Legacy Book [3]", 3, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Legacy Book", 4, "PDF"),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == (
        (entries[0], entries[1], entries[2]),
    )


def test_bookshelf_possible_duplicates_use_word_and_trigram_title_similarity():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Neuroscience: Exploring the Brain",
            1,
            "PDF",
            source_filename=f"source-one-{'a' * 32}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Exploring Brain — Neurosciences",
            2,
            "PDF",
            source_filename=f"source-two-{'b' * 32}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Unrelated",
            3,
            "PDF",
            source_filename=f"source-three-{'c' * 32}.pdf",
        ),
    ]

    matches = pdf_bookshelf._bookshelf_duplicate_matches(entries)

    assert matches[1] == (entries[1],)
    assert matches[2] == (entries[0],)
    assert 3 not in matches


def test_bookshelf_possible_duplicates_use_fuzzy_original_filename():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "First title",
            1,
            "PDF",
            source_filename=f"Sword_and_Scimitar-{'a' * 32}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Completely different title",
            2,
            "PDF",
            source_filename=f"the-sword-scimitar-scan-{'b' * 32}.pdf",
        ),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == (
        (entries[0], entries[1]),
    )


def test_bookshelf_possible_duplicates_use_pdf_metadata_title():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "First import",
            1,
            "PDF",
            source_filename=f"opaque-one-{'a' * 32}.pdf",
            metadata_title="Neuroscience: Exploring the Brain",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Second import",
            2,
            "PDF",
            source_filename=f"opaque-two-{'b' * 32}.pdf",
            metadata_title="Exploring Brain — Neurosciences",
        ),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == (
        (entries[0], entries[1]),
    )


def test_bookshelf_pdf_metadata_title_ignores_generic_values_and_number_mismatches():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Alpha",
            1,
            "PDF",
            metadata_title="Untitled",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Beta",
            2,
            "PDF",
            metadata_title="untitled",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Gamma",
            3,
            "PDF",
            metadata_title="Collected Essays Volume 1",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Delta",
            4,
            "PDF",
            metadata_title="Collected Essays Volume 2",
        ),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == ()


def test_bookshelf_loads_pdf_metadata_titles_for_captured_profile(
    monkeypatch,
    tmp_path,
):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    first_pdf.write_bytes(b"%PDF-1.7")
    second_pdf.write_bytes(b"%PDF-1.7")
    resolved = {
        "first.pdf": str(first_pdf),
        "second.pdf": str(second_pdf),
    }
    path_calls = []
    title_calls = []
    monkeypatch.setattr(
        pdf_bookshelf,
        "pdf_storage_abspath",
        lambda filename, *, profile=None: (
            path_calls.append((filename, profile)) or resolved.get(filename, "")
        ),
    )
    monkeypatch.setattr(
        pdf_bookshelf,
        "_cached_pdf_metadata_title",
        lambda path: title_calls.append(path) or f"Metadata {Path(path).stem}",
    )
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "First",
            1,
            "PDF",
            source_filename="first.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "EPUB",
            2,
            "EPUB",
            source_filename="book.epub",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Second",
            3,
            "PDF",
            source_filename="second.pdf",
        ),
    ]

    assert pdf_bookshelf._load_pdf_metadata_titles(
        entries,
        profile="Captured",
    ) == {
        1: "Metadata first",
        3: "Metadata second",
    }
    assert path_calls == [
        ("first.pdf", "Captured"),
        ("second.pdf", "Captured"),
    ]
    assert title_calls == [str(first_pdf), str(second_pdf)]


def test_bookshelf_reads_and_cleans_standard_pdf_title(monkeypatch, tmp_path):
    pdf_path = tmp_path / "metadata.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")
    instances = []

    class _FakePdfDocument:
        class MetaDataField:
            Title = object()

        def __init__(self, _parent):
            self.loaded = ""
            self.closed = False
            instances.append(self)

        def load(self, path):
            self.loaded = path

        def metaData(self, field):
            assert field is self.MetaDataField.Title
            return "  Brain\x00 Research\nHandbook  "

        def close(self):
            self.closed = True

    monkeypatch.setattr(pdf_bookshelf, "QPdfDocument", _FakePdfDocument)

    assert pdf_bookshelf._read_pdf_metadata_title(str(pdf_path)) == (
        "Brain Research Handbook"
    )
    assert instances[0].loaded == str(pdf_path)
    assert instances[0].closed is True


def test_bookshelf_pdf_metadata_scan_honors_cancellation(monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(
        pdf_bookshelf,
        "pdf_storage_abspath",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cancelled scan must not resolve files")
        ),
    )

    assert pdf_bookshelf._load_pdf_metadata_titles(
        [
            pdf_bookshelf._BookshelfEntry(
                "Cancelled",
                1,
                "PDF",
                source_filename="cancelled.pdf",
            )
        ],
        profile="Captured",
        cancelled=cancelled,
    ) == {}


def test_bookshelf_fuzzy_matching_respects_numbers_and_common_word_frequency():
    entries = [
        pdf_bookshelf._BookshelfEntry("World History Volume 1", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("World History Volume 2", 2, "PDF"),
        pdf_bookshelf._BookshelfEntry("Common Handbook Biology", 3, "PDF"),
        pdf_bookshelf._BookshelfEntry("Common Handbook Chemistry", 4, "PDF"),
        pdf_bookshelf._BookshelfEntry("Common Handbook Physics", 5, "PDF"),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == ()


def test_bookshelf_duplicate_filter_combines_with_existing_filters():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            1,
            "PDF",
            source_filename=f"guide-{'a' * 32}.pdf",
            tags=("work",),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide [2]",
            2,
            "PDF",
            source_filename=f"guide-{'b' * 32}.pdf",
            tags=("archive",),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Unique",
            3,
            "PDF",
            source_filename=f"unique-{'a' * 32}.pdf",
            tags=("work",),
        ),
    ]

    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "guide",
        "PDF",
        tag_query="work",
        duplicates_only=True,
    ) == [entries[0]]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "PDF",
        tag_query="work",
        duplicates_only=False,
    ) == [entries[0], entries[2]]


def test_bookshelf_delete_targets_distinct_live_note_ids_only():
    entries = [
        pdf_bookshelf._BookshelfEntry("One", 1, "PDF", note_id=11),
        pdf_bookshelf._BookshelfEntry("Two", 2, "PDF", note_id=11),
        pdf_bookshelf._BookshelfEntry("Missing", 3, "PDF", note_id=0),
        pdf_bookshelf._BookshelfEntry("Three", 4, "PDF", note_id=22),
    ]

    assert pdf_bookshelf._bookshelf_note_ids(entries) == (11, 22)
    assert pdf_bookshelf._without_bookshelf_notes(entries, (11,)) == entries[2:]


def test_bookshelf_delete_attachment_check_uses_lightweight_media_resolver(monkeypatch):
    calls = []
    snapshot = object()
    monkeypatch.setattr(pdf_bookshelf, "load_media_review_tree_snapshot", lambda *_args: snapshot)

    def linked_ids(addon_dir, profile, card_id, **kwargs):
        calls.append((addon_dir, profile, card_id, kwargs))
        if card_id == 1:
            return (10, 20)
        return (10, 40)

    monkeypatch.setattr(
        pdf_bookshelf,
        "linked_media_attachment_card_ids",
        linked_ids,
    )
    entries = [
        pdf_bookshelf._BookshelfEntry("PDF", 1, "PDF", note_id=101),
        pdf_bookshelf._BookshelfEntry("EPUB", 2, "EPUB", note_id=102),
    ]
    collection = object()

    assert pdf_bookshelf._bookshelf_attached_card_ids(
        "/addon",
        "Captured",
        entries,
        col=collection,
    ) == (10, 20, 40)
    assert [call[2] for call in calls] == [1, 2]
    assert [call[3]["media_kind"] for call in calls] == ["pdf", "epub"]
    assert all(call[3]["col"] is collection for call in calls)
    assert all(call[3]["tree_snapshot"] is snapshot for call in calls)


def test_bookshelf_attachment_counts_are_per_document_and_drive_duplicate_badge(
    monkeypatch,
):
    monkeypatch.setattr(pdf_bookshelf, "load_media_review_tree_snapshot", lambda *_args: object())
    def linked_ids(_addon_dir, _profile, card_id, **_kwargs):
        if card_id == 1:
            return (10, 10)
        return (20,)

    monkeypatch.setattr(
        pdf_bookshelf,
        "linked_media_attachment_card_ids",
        linked_ids,
    )
    first = pdf_bookshelf._BookshelfEntry("First", 1, "PDF")
    second = pdf_bookshelf._BookshelfEntry("Second", 2, "EPUB")
    counts = pdf_bookshelf._bookshelf_attachment_counts(
        "/addon",
        "Captured",
        [first, second],
        col=object(),
    )

    assert counts == {1: 1, 2: 1}
    assert pdf_bookshelf._bookshelf_entry_has_attachment_badge(
        first,
        duplicates_only=True,
        attachment_counts=counts,
    ) is True
    assert pdf_bookshelf._bookshelf_entry_has_attachment_badge(
        first,
        duplicates_only=False,
        attachment_counts=counts,
    ) is False
    assert pdf_bookshelf._bookshelf_entry_has_attachment_badge(
        pdf_bookshelf._BookshelfEntry("Unworked", 3, "PDF"),
        duplicates_only=True,
        attachment_counts=counts,
    ) is False


def test_bookshelf_delete_confirmation_warns_about_attached_cards():
    without_attachments = pdf_bookshelf._bookshelf_delete_confirmation(
        document_count=1,
        attached_card_count=0,
        keep_one=False,
    )
    with_attachments = pdf_bookshelf._bookshelf_delete_confirmation(
        document_count=1,
        attached_card_count=3,
        keep_one=False,
    )

    assert "attached" not in without_attachments.casefold()
    assert "3 attached cards" in with_attachments
    assert "will remain in Anki" in with_attachments
    assert "may no longer work" in with_attachments


def test_bookshelf_tag_query_normalizes_separators_case_and_duplicates():
    assert pdf_bookshelf._parse_bookshelf_tag_query(
        " Work, reading;WORK\nproject::Deep "
    ) == ("work", "reading", "project::deep")
    assert pdf_bookshelf._parse_bookshelf_tag_query("  , ; ") == ()


def test_bookshelf_tag_filter_supports_or_and_combines_with_title_and_kind():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Alpha Work",
            1,
            "PDF",
            tags=("reading", "Work"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Deep Learning",
            2,
            "EPUB",
            tags=("reading", "machine_learning"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Unsorted",
            3,
            "PDF",
            tags=(),
        ),
    ]

    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="WORK, machine_learning",
        tag_mode="OR",
    ) == entries[:2]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="READING work",
        tag_mode="AND",
    ) == [entries[0]]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "deep",
        "EPUB",
        tag_query="reading machine_learning",
        tag_mode="AND",
    ) == [entries[1]]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="missing",
        tag_mode="OR",
    ) == []
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="",
        tag_mode="AND",
    ) == entries


def test_bookshelf_tag_suggestions_rank_frequency_and_dedupe_case():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Alpha",
            1,
            "PDF",
            tags=("Work", "reading"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Beta",
            2,
            "EPUB",
            tags=("reading", "work", "machine_learning"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Gamma",
            3,
            "PDF",
            tags=("Reading", "project::Deep"),
        ),
    ]

    assert pdf_bookshelf._bookshelf_tag_suggestions(entries) == (
        "reading",
        "Work",
        "machine_learning",
        "project::Deep",
    )


def test_bookshelf_tag_completion_replaces_only_the_active_token():
    completed, cursor = pdf_bookshelf._complete_bookshelf_tag_query(
        "work, mach",
        "machine_learning",
        len("work, mach"),
    )
    assert completed == "work, machine_learning"
    assert cursor == len(completed)

    source = "work; mach reading"
    completed, cursor = pdf_bookshelf._complete_bookshelf_tag_query(
        source,
        "machine_learning",
        len("work; mach"),
    )
    assert completed == "work; machine_learning reading"
    assert cursor == len("work; machine_learning")

    assert pdf_bookshelf._complete_bookshelf_tag_query(
        "",
        "project::Deep",
        0,
    ) == ("project::Deep", len("project::Deep"))
    assert pdf_bookshelf._complete_bookshelf_tag_query(
        "work",
        "invalid tag",
        4,
    ) == ("work", 4)


def test_bookshelf_dialog_exposes_tag_filter_and_explicit_or_and_modes():
    source = Path(pdf_bookshelf.__file__).read_text(encoding="utf-8")

    assert 't("reader_bookshelf_filter_tags_placeholder")' in source
    assert 't("reader_bookshelf_any_tag")' in source
    assert 't("reader_bookshelf_all_tags")' in source
    assert 't("reader_bookshelf_browse_tags")' in source
    assert "QCompleter" in source
    assert "Qt.MatchFlag.MatchContains" in source
    assert "self._tag_search.textChanged" in source
    assert "self._tag_mode_combo.currentIndexChanged" in source


def test_bookshelf_dialog_exposes_duplicate_filter_and_safe_delete_context_menu():
    source = Path(pdf_bookshelf.__file__).read_text(encoding="utf-8")

    assert 't("reader_bookshelf_duplicates_only")' in source
    assert "Qt.ContextMenuPolicy.CustomContextMenu" in source
    assert "self._list.customContextMenuRequested" in source
    assert "def _show_context_menu" in source
    assert "remove_notes(" in source
    assert "askUser(" in source
    assert "_load_pdf_metadata_titles(" in source
    assert "uses_collection=False" in source
    assert '"reader_bookshelf_pdf_metadata_title"' in source
    assert "_bookshelf_attached_card_ids(" in source
    assert "QueryOp(" in source
    assert 't("reader_bookshelf_attachment_check_failed")' in source
    assert "class _BookshelfItemDelegate" in source
    assert "_ATTACHMENT_BADGE_ROLE" in source
    assert "self._list.setItemDelegate(" in source
    assert "_ATTACHMENT_BADGE_ROLE," in source
    assert "attachment_counts: dict[int, int] | None = None" in source
    assert "def _duplicates_filter_changed" in source
    assert "self._start_duplicate_attachment_scan()" in source
    assert '"reader_bookshelf_attached_badge_tooltip"' in source
    assert "self._list.itemClicked" not in source


@pytest.fixture
def bookshelf_reveal_menu(monkeypatch, tmp_path):
    import epub_manager
    import pdf_manager

    profile = "ShelfProfile"
    roots = {kind: tmp_path / profile / kind.lower() for kind in ("PDF", "EPUB")}
    for root in roots.values():
        root.mkdir(parents=True)
    monkeypatch.setattr(pdf_manager, "get_pdf_dir", lambda selected: str(tmp_path / selected / "pdf"))
    monkeypatch.setattr(epub_manager, "get_epub_dir", lambda selected: str(tmp_path / selected / "epub"))
    monkeypatch.setattr(pdf_bookshelf, "_active_profile", lambda: profile)
    monkeypatch.setattr(pdf_bookshelf, "qconnect", lambda signal, callback: signal.connect(callback))
    calls = []
    monkeypatch.setattr(pdf_bookshelf, "reveal_local_file", lambda path: calls.append(path) or True)
    notices = []
    monkeypatch.setattr(pdf_bookshelf, "tooltip", lambda message, **_kwargs: notices.append(message))

    class Menu:
        def __init__(self, parent):
            self.actions = []
            parent.menu = self

        def addAction(self, label):
            action = SimpleNamespace(label=label, enabled=True)
            action.setEnabled = lambda enabled: setattr(action, "enabled", enabled)
            action.triggered = SimpleNamespace(connect=lambda callback: setattr(action, "trigger", callback))
            self.actions.append(action)
            return action

        def addSeparator(self):
            pass

        def exec(self, _position):
            pass

    monkeypatch.setattr(pdf_bookshelf, "QMenu", Menu)

    def show(entry):
        item = SimpleNamespace(data=lambda _role: entry)
        selected = []
        dialog = SimpleNamespace(
            _profile=profile,
            _list=SimpleNamespace(
                itemAt=lambda _position: item,
                setCurrentItem=selected.append,
                viewport=lambda: SimpleNamespace(mapToGlobal=lambda position: position),
            ),
            _duplicates_for_entry=lambda _entry: (),
            _confirm_delete_entries=lambda *_args: pytest.fail("Reveal must not delete a book"),
            _reveal_entry=lambda target: pdf_bookshelf._DocumentBookshelfDialog._reveal_entry(dialog, target),
        )
        pdf_bookshelf._DocumentBookshelfDialog._show_context_menu(dialog, (10, 10))
        assert selected == [item]
        return dialog.menu.actions[0]

    return SimpleNamespace(show=show, roots=roots, calls=calls, notices=notices, profile=profile)


@pytest.mark.parametrize("kind", ["PDF", "EPUB"])
@pytest.mark.parametrize(
    ("platform", "label"),
    [("darwin", "Show in Finder"), ("win32", "Show in File Explorer"), ("linux", "Show containing folder")],
)
def test_bookshelf_right_click_reveals_clicked_document_file(bookshelf_reveal_menu, monkeypatch, kind, platform, label):
    shelf = bookshelf_reveal_menu
    source = shelf.roots[kind] / f"A book with spaces.{kind.lower()}"
    source.write_bytes(b"document")
    entry = pdf_bookshelf._BookshelfEntry("Selected book", 1, kind, source_filename=source.name)
    monkeypatch.setattr(sys, "platform", platform)

    action = shelf.show(entry)
    assert action.label == label
    assert action.enabled
    action.trigger()

    assert shelf.calls == [str(source)]
    assert shelf.notices == []
    assert source.read_bytes() == b"document"


@pytest.mark.parametrize("kind", ["PDF", "EPUB"])
@pytest.mark.parametrize("target", ["missing", "empty", "directory", "traversal", "absolute", "symlink"])
def test_bookshelf_reveal_is_disabled_for_missing_or_unsafe_files(bookshelf_reveal_menu, kind, target):
    shelf = bookshelf_reveal_menu
    outside = shelf.roots[kind].parent / "outside.book"
    outside.write_bytes(b"private")
    filename = "missing.book"
    if target == "empty":
        filename = ""
    elif target == "directory":
        filename = "folder"
        (shelf.roots[kind] / filename).mkdir()
    elif target == "traversal":
        filename = "../outside.book"
    elif target == "absolute":
        filename = str(outside)
    elif target == "symlink":
        filename = "linked.book"
        (shelf.roots[kind] / filename).symlink_to(outside)
    entry = pdf_bookshelf._BookshelfEntry("Unavailable", 1, kind, source_filename=filename)

    action = shelf.show(entry)

    assert not action.enabled
    action.trigger()  # Even a stale/queued signal must fail closed.
    assert shelf.calls == []
    assert shelf.notices


@pytest.mark.parametrize("change", ["removed", "profile_switched", "reveal_failed"])
def test_bookshelf_reveal_rechecks_file_and_profile_when_triggered(bookshelf_reveal_menu, monkeypatch, change):
    shelf = bookshelf_reveal_menu
    source = shelf.roots["PDF"] / "book.pdf"
    source.write_bytes(b"document")
    entry = pdf_bookshelf._BookshelfEntry("Book", 1, "PDF", source_filename=source.name)
    action = shelf.show(entry)
    assert action.enabled
    if change == "removed":
        source.unlink()
    elif change == "profile_switched":
        monkeypatch.setattr(pdf_bookshelf, "_active_profile", lambda: "AnotherProfile")
    else:
        monkeypatch.setattr(pdf_bookshelf, "reveal_local_file", lambda _path: False)

    action.trigger()

    assert shelf.calls == []
    assert shelf.notices == [pdf_bookshelf.t("admin_file_reveal_failed")]


@pytest.mark.parametrize("scale", ["1", "2"], ids=["standard", "retina"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_bookshelf_captions_stay_below_white_and_colored_covers(tmp_path, scale, theme):
    script = dedent('''
        import os, sys, types
        from pathlib import Path
        from aqt.qt import (QApplication, QColor, QFont, QIcon, QListView, QListWidget,
                            QListWidgetItem, QPainter, QPalette, QPixmap, QSize, Qt)
        package = types.ModuleType('incremento')
        package.__path__ = [os.getcwd()]
        sys.modules['incremento'] = package
        from incremento.frontend import pdf_bookshelf as shelf

        app = QApplication([])
        app.setStyle('Fusion')
        view = QListWidget()
        view.resize(390, 330)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setIconSize(QSize(160, 220))
        view.setGridSize(QSize(shelf._TILE_WIDTH, shelf._TILE_HEIGHT))
        view.setItemDelegate(shelf._BookshelfItemDelegate(view))
        font = QFont()
        font.setPixelSize(13)
        view.setFont(font)
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor('#252525' if sys.argv[1]=='dark' else '#f4f4f4'))
        palette.setColor(QPalette.ColorRole.Text, QColor('#f4b900'))
        palette.setColor(QPalette.ColorRole.Highlight, QColor('#377bc1'))
        view.setPalette(palette)

        items = []
        for index, color in enumerate(('#ffffff', '#176a94')):
            cover = QPixmap(400, 600)
            cover.fill(QColor(color))
            painter = QPainter(cover)
            painter.fillRect(0, 552, 400, 48, QColor('#d92d6f'))
            painter.end()
            entry = shelf._BookshelfEntry('A long textbook title that wraps onto two lines',
                index+1, 'PDF', list_names=('Reference',), saved_reason='Recommended for my course.')
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setIcon(QIcon(cover))
            item.setSizeHint(QSize(shelf._TILE_WIDTH, shelf._TILE_HEIGHT))
            view.addItem(item)
            items.append(item)
        view.show()
        for selected in items:
            view.setCurrentItem(selected)
            app.processEvents()
            image = view.viewport().grab().toImage()
            image.save(str(Path(sys.argv[2]) / ('tile-'+str(view.row(selected))+'.png')))
            ratio = image.devicePixelRatio()
            for item in items:
                rect = view.visualItemRect(item)
                cover_rows, title_rows = [], []
                for y in range(max(0,int(rect.top()*ratio)), min(image.height(),int((rect.bottom()+1)*ratio))):
                    for x in range(max(0,int(rect.left()*ratio)), min(image.width(),int((rect.right()+1)*ratio))):
                        color = image.pixelColor(x,y)
                        if abs(color.red()-217)<3 and abs(color.green()-45)<3 and abs(color.blue()-111)<3:
                            cover_rows.append(y)
                        if abs(color.red()-244)<3 and abs(color.green()-185)<3 and color.blue()<3:
                            title_rows.append(y)
                assert cover_rows and title_rows, 'The actual cover and caption must both render'
                assert min(title_rows)-max(cover_rows) >= 6*ratio, (
                    'Cover overlaps its caption', ratio, min(title_rows), max(cover_rows))
        view.close()
    ''')
    result = subprocess.run([sys.executable, "-c", script, theme, str(tmp_path)], cwd=ROOT,
        env={**os.environ,"QT_QPA_PLATFORM":"offscreen","QT_SCALE_FACTOR":scale},
        capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_attachment_badge_renders_above_normal_and_selected_cover():
    script = dedent("""
        import os
        import sys
        import types
        from aqt.qt import (
            QApplication,
            QColor,
            QIcon,
            QListView,
            QListWidget,
            QListWidgetItem,
            QPixmap,
            QSize,
        )

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from incremento.frontend import pdf_bookshelf

        app = QApplication([])
        view = QListWidget()
        view.resize(220, 380)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setIconSize(QSize(160, 220))
        view.setGridSize(QSize(196, 350))
        delegate = pdf_bookshelf._BookshelfItemDelegate(view)
        view.setItemDelegate(delegate)

        cover = QPixmap(160, 220)
        cover.fill(QColor("#ececec"))
        item = QListWidgetItem("Worked document")
        item.setIcon(QIcon(cover))
        item.setData(pdf_bookshelf._ATTACHMENT_BADGE_ROLE, 18)
        item.setSizeHint(QSize(196, 350))
        view.addItem(item)
        view.show()

        def badge_pixels():
            app.processEvents()
            image = view.viewport().grab().toImage()
            target = QColor("#188038")
            points = []
            for y in range(image.height()):
                for x in range(image.width()):
                    color = image.pixelColor(x, y)
                    if (
                        abs(color.red() - target.red()) <= 2
                        and abs(color.green() - target.green()) <= 2
                        and abs(color.blue() - target.blue()) <= 2
                    ):
                        points.append((x, y))
            assert len(points) > 300, len(points)
            assert max(x for x, _y in points) > 130
            assert min(y for _x, y in points) < 60

        badge_pixels()
        view.setCurrentItem(item)
        item.setSelected(True)
        badge_pixels()
        view.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bookshelf_count_describes_current_document_filter():
    entries = [
        pdf_bookshelf._BookshelfEntry("Alpha", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("Deep Work", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Work Notes", 3, "PDF"),
    ]

    assert (
        pdf_bookshelf._bookshelf_count_text(entries, entries, "ALL")
        == "3 documents · 2 PDFs · 1 EPUB"
    )
    assert (
        pdf_bookshelf._bookshelf_count_text(entries, [entries[1]], "EPUB")
        == "1 EPUB"
    )
    assert (
        pdf_bookshelf._bookshelf_count_text(entries, [entries[2]], "PDF")
        == "Showing 1 of 2 PDFs"
    )


def test_bookshelf_count_uses_locale_without_changing_kind_codes(monkeypatch):
    monkeypatch.setattr(pdf_bookshelf, "tn", lambda key, count, **values: f"{key}:{count}", raising=False)
    monkeypatch.setattr(pdf_bookshelf, "t", lambda key, **values: f"{key}:{values}", raising=False)
    entry = pdf_bookshelf._BookshelfEntry("原文", 1, "PDF")
    assert "reader_bookshelf_pdf_count:1" in pdf_bookshelf._bookshelf_count_text([entry], [entry], "PDF")


def test_bookshelf_caption_colors_are_readable_in_dark_and_light_modes():
    dark_caption, dark_muted = pdf_bookshelf._bookshelf_theme_colors(32)
    light_caption, light_muted = pdf_bookshelf._bookshelf_theme_colors(240)

    assert dark_caption == "#f4f4f5"
    assert dark_muted == "#b8bcc4"
    assert light_caption == "#202124"
    assert light_muted == "#5f6368"


def test_media_preview_path_stays_inside_anki_media_directory(tmp_path):
    media_dir = tmp_path / "collection.media"
    media_dir.mkdir()
    cover = media_dir / "cover.png"
    cover.write_bytes(b"png")
    outside = tmp_path / "private.png"
    outside.write_bytes(b"private")

    resolved = pdf_bookshelf._existing_media_preview_path(
        str(media_dir),
        "cover.png",
    )

    assert resolved == os.path.realpath(cover)
    assert (
        pdf_bookshelf._existing_media_preview_path(
            str(media_dir),
            "../private.png",
        )
        == ""
    )


def test_bookshelf_new_window_choice_does_not_replace_the_main_reader(monkeypatch):
    accepted = []
    entry = pdf_bookshelf._BookshelfEntry('Another PDF', 8, 'PDF')
    dialog = SimpleNamespace(_profile='A', _selected_entry=lambda: entry,
                             accept=lambda: accepted.append(True))
    monkeypatch.setattr(pdf_bookshelf, '_active_profile', lambda: 'A')
    pdf_bookshelf._DocumentBookshelfDialog._accept_reference(dialog, beside=False, new_window=True)
    assert dialog._reference_mode == 'window'
    assert accepted == [True]
