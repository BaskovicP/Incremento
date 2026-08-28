import db
import reconciliation


def setup_function():
    db.close_connection()


def teardown_function():
    db.close_connection()


def test_reconciliation_deletes_only_stale_external_rows(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    conn = db.get_connection(addon_dir, profile)
    conn.executemany(
        "INSERT INTO priorities(card_id, priority) VALUES (?, ?)",
        [(1, 10), (2, 20)],
    )
    conn.executemany(
        "INSERT INTO pdf_card_sources(pdf_card_id, page, note_id, excerpt) "
        "VALUES (?, ?, ?, '')",
        [(1, 1, 11), (1, 2, 12), (2, 1, 11)],
    )
    conn.commit()

    result = reconciliation.reconcile_profile_state(
        addon_dir,
        profile,
        live_card_ids={1},
        live_note_ids={11},
    )

    assert result["stale_rows"] == 3
    assert conn.execute("SELECT card_id FROM priorities").fetchall() == [(1,)]
    assert conn.execute(
        "SELECT pdf_card_id, note_id FROM pdf_card_sources"
    ).fetchall() == [(1, 11)]


def test_reconciliation_detaches_missing_knowledge_tree_parent(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    conn = db.get_connection(addon_dir, profile)
    conn.executemany(
        "INSERT INTO knowledge_tree_nodes("
        "card_id, parent_card_id, node_kind, sort_order, created_at, updated_at"
        ") VALUES (?, ?, 'topic', 0, 1, 1)",
        [(1, None), (2, 99)],
    )
    conn.commit()

    result = reconciliation.reconcile_profile_state(
        addon_dir,
        profile,
        live_card_ids={1, 2},
        live_note_ids=set(),
    )

    assert result["repaired_links"] == 1
    assert conn.execute(
        "SELECT parent_card_id FROM knowledge_tree_nodes WHERE card_id=2"
    ).fetchone() == (None,)


def test_collection_adapter_reads_live_ids(tmp_path):
    class _DB:
        def list(self, query):
            return [1, 2] if "cards" in query else [10, 20]

    class _Collection:
        db = _DB()

    result = reconciliation.reconcile_collection(
        str(tmp_path),
        "TestProfile",
        _Collection(),
    )

    assert result["stale_rows"] == 0


def test_profile_open_recovery_does_not_read_anki_when_nothing_is_pending(tmp_path):
    class _Collection:
        def __getattribute__(self, name):
            if name.startswith("__"):
                return object.__getattribute__(self, name)
            raise AssertionError(f"unexpected collection access: {name}")

    result = reconciliation.reconcile_pending_imports(
        str(tmp_path),
        "TestProfile",
        _Collection(),
    )

    assert result == {
        "stale_rows": 0,
        "repaired_links": 0,
        "touched_tables": 0,
        "pending_recovered": 0,
        "pending_rolled_back": 0,
        "pending_cleanup_failed": 0,
        "journal_pruned": 0,
    }


def test_profile_open_recovery_checks_only_bound_pending_card(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    from operation_journal import ImportOperation

    operation = ImportOperation(addon_dir, profile, "writing")
    operation.bind_anki(card_id=99, note_id=98)

    class _Card:
        id = 99
        nid = 98

    class _Collection:
        def get_card(self, card_id):
            assert card_id == 99
            return _Card()

        def find_notes(self, _query):
            raise AssertionError("bound live cards must not trigger a note search")

    result = reconciliation.reconcile_pending_imports(
        addon_dir,
        profile,
        _Collection(),
    )

    assert result["pending_recovered"] == 1
    assert db.get_connection(addon_dir, profile).execute(
        "SELECT state, card_id, note_id FROM import_journal"
    ).fetchone() == ("committed", 99, 98)


def test_profile_open_recovery_finds_unbound_import_by_content_id(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    from operation_journal import ImportOperation

    operation = ImportOperation(addon_dir, profile, "writing")

    class _DB:
        def list(self, query):
            raise AssertionError(f"profile-open recovery enumerated Anki rows: {query}")

    class _Card:
        id = 7
        nid = 8

    class _Note:
        def __getitem__(self, field):
            assert field == "Incremento_Content_ID"
            return operation.content_id

    class _Collection:
        db = _DB()

        def find_notes(self, query):
            return [8] if operation.content_id in query else []

        def get_note(self, note_id):
            assert note_id == 8
            return _Note()

        def find_cards(self, query):
            assert query == "nid:8"
            return [7]

        def get_card(self, card_id):
            assert card_id == 7
            return _Card()

    result = reconciliation.reconcile_pending_imports(
        addon_dir,
        profile,
        _Collection(),
    )

    assert result["pending_recovered"] == 1
    assert db.get_connection(addon_dir, profile).execute(
        "SELECT state, card_id, note_id FROM import_journal"
    ).fetchone() == ("committed", 7, 8)


def test_collection_adapter_recovers_without_adding_content_id_field(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    from operation_journal import ImportOperation

    operation = ImportOperation(addon_dir, profile, "writing")
    operation.track_created_relpath("writing/draft.md")

    class _DB:
        def list(self, query):
            return [7] if "cards" in query else [8]

    class _Note:
        def __getitem__(self, field):
            if field == "Incremento_Source_Link":
                return "writing/draft.md"
            raise KeyError(field)

    class _Collection:
        db = _DB()

        def find_notes(self, query):
            if "Incremento_Source_Link" in query and "writing/draft.md" in query:
                return [8]
            return []

        def get_note(self, note_id):
            assert note_id == 8
            return _Note()

        def find_cards(self, query):
            assert query == "nid:8"
            return [7]

    result = reconciliation.reconcile_collection(addon_dir, profile, _Collection())

    assert result["pending_recovered"] == 1
    assert db.get_connection(addon_dir, profile).execute(
        "SELECT state, card_id, note_id FROM import_journal"
    ).fetchone() == ("committed", 7, 8)


def test_source_link_recovery_escapes_anki_search_syntax(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    from operation_journal import ImportOperation

    operation = ImportOperation(addon_dir, profile, "writing")
    source_link = 'writing/a "quoted" draft.md'
    operation.track_created_relpath(source_link)
    seen_queries = []

    class _DB:
        def list(self, query):
            return [7] if "cards" in query else [8]

    class _Note:
        def __getitem__(self, field):
            if field == "Incremento_Source_Link":
                return source_link
            raise KeyError(field)

    class _Collection:
        db = _DB()

        def find_notes(self, query):
            seen_queries.append(query)
            if "Incremento_Source_Link" in query:
                return [8]
            return []

        def get_note(self, note_id):
            return _Note()

        def find_cards(self, query):
            return [7]

    result = reconciliation.reconcile_collection(addon_dir, profile, _Collection())

    assert result["pending_recovered"] == 1
    source_queries = [
        query for query in seen_queries if "Incremento_Source_Link" in query
    ]
    assert source_queries
    assert '\\"quoted\\"' in source_queries[0]


def test_anki_search_value_escapes_quotes_and_backslashes():
    assert reconciliation._escape_anki_search_value('a\\b "quoted"') == (
        'a\\\\b \\"quoted\\"'
    )
