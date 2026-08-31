import re
import types

import media_review


class _FakeNote:
    def __init__(self, parent_card_id="", *, fields=None, tags=None, note_type_name="Basic"):
        self._parent_card_id = str(parent_card_id)
        self.fields = list(fields or [])
        self.tags = list(tags or [])
        self._note_type_name = str(note_type_name)

    def __getitem__(self, field_name):
        if field_name != media_review.INCREMENTO_PARENT_CARD_ID_FIELD:
            raise KeyError(field_name)
        return self._parent_card_id

    def note_type(self):
        return {"name": self._note_type_name}


class _FakeCollection:
    def __init__(self, *, notes=None, cards=None, metadata_note_ids=None):
        self.notes = dict(notes or {})
        self.cards = dict(cards or {})
        self.metadata_note_ids = list(metadata_note_ids or [])
        self.note_queries = []
        self.card_queries = []
        self.decks = types.SimpleNamespace(by_name=lambda _name: None)

    def find_notes(self, query):
        self.note_queries.append(query)
        return list(self.metadata_note_ids)

    def get_note(self, note_id):
        return self.notes[int(note_id)]

    def find_cards(self, query):
        self.card_queries.append(query)
        if query.startswith("cid:"):
            ids_text = query.split(" ", 1)[0][len("cid:") :]
            card_ids = {int(value) for value in ids_text.split(",") if value}
            return [
                card_id
                for card_id in card_ids
                if card_id in self.cards and bool(getattr(self.cards[card_id], "ready", False))
            ]
        note_ids = {int(value) for value in re.findall(r"nid:(\d+)", query)}
        # Deliberately return reverse card order; the resolver must restore the
        # explicit note order and stable card-id order itself.
        return [
            card_id
            for card_id, card in sorted(self.cards.items(), reverse=True)
            if int(card.nid) in note_ids
        ]

    def get_card(self, card_id):
        return self.cards[int(card_id)]


def _card(
    card_id,
    note_id,
    *,
    queue=2,
    due=0,
    interval=0,
    ready=False,
    did=1,
    odid=0,
    topic=False,
):
    return types.SimpleNamespace(
        id=int(card_id),
        nid=int(note_id),
        queue=int(queue),
        due=int(due),
        ivl=int(interval),
        ready=bool(ready),
        did=int(did),
        odid=int(odid),
        topic=bool(topic),
    )


def test_resolver_combines_legacy_metadata_and_nested_tree_links(monkeypatch):
    source_card_id = 500
    cards = {
        1000: _card(1000, 10, due=8, interval=5),
        1100: _card(1100, 11, queue=-1),
        2001: _card(2001, 20, due=4, interval=2),
        2000: _card(2000, 20, due=3, interval=3),
        3000: _card(3000, 30, due=2, interval=9),
        4000: _card(4000, 40, due=1, interval=12),
        500: _card(500, 5),
    }
    col = _FakeCollection(
        notes={
            10: _FakeNote(source_card_id),
            11: _FakeNote(source_card_id),
            # A broad Anki search result must not leak through exact checking.
            99: _FakeNote(5000),
        },
        cards=cards,
        metadata_note_ids=[99, 11, 10],
    )
    monkeypatch.setattr(
        media_review,
        "get_knowledge_tree_nodes",
        lambda *_args: [
            {"card_id": 500, "parent_card_id": None, "sort_order": 0},
            {"card_id": 3000, "parent_card_id": 500, "sort_order": 0},
            {"card_id": 1000, "parent_card_id": 500, "sort_order": 1},
            {"card_id": 4000, "parent_card_id": 3000, "sort_order": 0},
        ],
    )

    rows = media_review.resolve_linked_media_review_rows(
        "/addon",
        "Profile",
        source_card_id,
        col=col,
        linked_note_ids=[20, 10, 20],
        linked_card_ids=[500, 3000],
    )

    assert [row["card_id"] for row in rows] == [2000, 2001, 1000, 3000, 4000]
    assert all(row["card_id"] != source_card_id for row in rows)
    assert 1100 not in [row["card_id"] for row in rows]
    assert col.note_queries == ["Incremento_Parent_Card_ID:500"]


def test_pdf_review_all_includes_descendants_of_attached_tree_root(monkeypatch):
    source_card_id = 500
    cards = {
        1000: _card(1000, 10, topic=True),
        2000: _card(2000, 20),
        3000: _card(3000, 30),
    }
    col = _FakeCollection(
        notes={
            10: _FakeNote(source_card_id),
            20: _FakeNote(""),
            30: _FakeNote(""),
        },
        cards=cards,
    )
    monkeypatch.setattr(
        media_review,
        "get_knowledge_tree_nodes",
        lambda *_args: [
            # The PDF card is not itself in the tree. Its directly attached
            # card is the root shown in the Knowledge Tree workspace.
            {"card_id": 1000, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
            {"card_id": 2000, "parent_card_id": 1000, "node_kind": "item", "sort_order": 0},
            {"card_id": 3000, "parent_card_id": 2000, "node_kind": "item", "sort_order": 0},
        ],
    )
    monkeypatch.setattr(
        media_review,
        "is_topic_card",
        lambda card, **_kwargs: bool(card.topic),
    )

    rows = media_review.inspect_linked_media_review_rows(
        "/addon",
        "Profile",
        source_card_id,
        col=col,
        media_kind="pdf",
        linked_source_rows=[{"note_id": 10, "position": 7}],
        topic_classifier=object(),
    )

    assert [row["card_id"] for row in rows] == [1000, 2000, 3000]
    assert [row["source_depth"] for row in rows] == [0, 1, 2]
    assert [row["media_position"] for row in rows] == [7, 7, 7]


def test_note_search_is_chunked_for_large_link_sets(monkeypatch):
    note_ids = list(range(1, 452))
    cards = {note_id + 10_000: _card(note_id + 10_000, note_id) for note_id in note_ids}
    col = _FakeCollection(cards=cards)
    monkeypatch.setattr(media_review, "get_knowledge_tree_nodes", lambda *_args: [])

    rows = media_review.resolve_linked_media_review_rows(
        "/addon",
        "Profile",
        999,
        col=col,
        linked_note_ids=note_ids,
        include_tree_descendants=False,
    )

    assert len(rows) == len(note_ids)
    assert len([query for query in col.card_queries if query.startswith("nid:")]) == 3
    assert len([query for query in col.card_queries if query.startswith("cid:")]) == 1


def test_order_choices_are_stable_and_cover_creation_due_interval_and_random():
    rows = [
        {"card_id": 30, "created_at": 30, "queue": 0, "due": 1, "interval": 0, "attached_rank": 0},
        {"card_id": 10, "created_at": 10, "queue": 2, "due": 7, "interval": 20, "attached_rank": 2},
        {"card_id": 20, "created_at": 20, "queue": 1, "due": 99, "interval": 3, "attached_rank": 1},
        {"card_id": 40, "created_at": 40, "queue": 3, "due": 2, "interval": 8, "attached_rank": 3},
        {"card_id": 50, "created_at": 50, "queue": 2, "due": 5, "interval": 4, "attached_rank": 4, "media_position": 12},
    ]

    def ids(order, **kwargs):
        return [
            row["card_id"]
            for row in media_review.order_linked_media_review_rows(rows, order, **kwargs)
        ]

    assert ids("attached") == [30, 20, 10, 40, 50]
    assert ids("created_oldest") == [10, 20, 30, 40, 50]
    assert ids("created_newest") == [50, 40, 30, 20, 10]
    assert ids("due_first") == [20, 40, 50, 10, 30]
    assert ids("interval_shortest") == [30, 20, 50, 40, 10]
    assert ids("interval_longest") == [10, 40, 50, 20, 30]
    assert ids("media_position") == [50, 30, 20, 10, 40]
    assert ids("random", shuffle=lambda items: items.reverse()) == [50, 40, 20, 10, 30]
    assert ids("not-a-real-order") == ids("attached")


def test_card_id_wrapper_applies_requested_order(monkeypatch):
    monkeypatch.setattr(
        media_review,
        "resolve_linked_media_review_rows",
        lambda *_args, **_kwargs: [
            {"card_id": 100, "created_at": 100},
            {"card_id": 300, "created_at": 300},
            {"card_id": 200, "created_at": 200},
        ],
    )

    assert media_review.linked_media_review_card_ids(
        "/addon",
        "Profile",
        1,
        col=object(),
        order="created_newest",
    ) == [300, 200, 100]


def test_inspection_adds_media_positions_topics_due_state_and_nested_inheritance(
    monkeypatch,
):
    source_card_id = 500
    notes = {
        10: _FakeNote(source_card_id),
        20: _FakeNote(source_card_id),
        30: _FakeNote(""),
        40: _FakeNote(""),
    }
    cards = {
        1000: _card(1000, 10, topic=True, ready=True),
        2000: _card(2000, 20),
        3000: _card(3000, 30, topic=True),
        4000: _card(4000, 40, odid=91, did=88),
        5000: _card(5000, 40, odid=91, did=77),
    }
    col = _FakeCollection(
        notes=notes,
        cards=cards,
        metadata_note_ids=[10, 20],
    )
    col.decks = types.SimpleNamespace(
        by_name=lambda _name: {"id": 77, "dyn": 1},
    )
    monkeypatch.setattr(
        media_review,
        "get_pdf_document_source_rows",
        lambda *_args: [
            {"note_id": 10, "position": 2, "source_rank": 0},
            {"note_id": 20, "position": 8, "source_rank": 1},
        ],
    )
    monkeypatch.setattr(
        media_review,
        "get_knowledge_tree_nodes",
        lambda *_args: [
            {"card_id": 1000, "parent_card_id": 500, "sort_order": 0},
            {"card_id": 3000, "parent_card_id": 1000, "sort_order": 0},
            {"card_id": 4000, "parent_card_id": 500, "sort_order": 1},
            {"card_id": 5000, "parent_card_id": 500, "sort_order": 2},
        ],
    )
    classifier = object()
    monkeypatch.setattr(
        media_review,
        "is_topic_card",
        lambda card, **_kwargs: bool(card.topic),
    )

    rows = media_review.inspect_linked_media_review_rows(
        "/addon",
        "Profile",
        source_card_id,
        col=col,
        media_kind="pdf",
        target_deck_name="Incremento PDF Review",
        topic_classifier=classifier,
    )
    by_id = {row["card_id"]: row for row in rows}

    assert by_id[1000]["media_position"] == 2
    assert by_id[1000]["is_topic"] is True
    assert by_id[1000]["is_due"] is True
    assert by_id[3000]["source_depth"] == 1
    assert by_id[3000]["media_position"] == 2
    assert by_id[4000]["source_depth"] == 0
    assert by_id[4000]["availability"] == "filtered"
    assert by_id[5000]["availability"] == "available"


def test_filters_topic_item_scope_position_due_and_limit_with_exclusion_counts():
    rows = [
        {"card_id": 1, "availability": "available", "source_depth": 0, "media_position": 2, "is_topic": True, "is_due": True, "attached_rank": 0},
        {"card_id": 2, "availability": "available", "source_depth": 0, "media_position": 3, "is_topic": True, "is_due": True, "attached_rank": 1},
        {"card_id": 3, "availability": "available", "source_depth": 1, "media_position": 2, "is_topic": True, "is_due": True, "attached_rank": 2},
        {"card_id": 4, "availability": "available", "source_depth": 0, "media_position": 9, "is_topic": True, "is_due": True, "attached_rank": 3},
        {"card_id": 5, "availability": "available", "source_depth": 0, "media_position": None, "is_topic": True, "is_due": True, "attached_rank": 4},
        {"card_id": 6, "availability": "available", "source_depth": 0, "media_position": 1, "is_topic": False, "is_due": True, "attached_rank": 5},
        {"card_id": 7, "availability": "available", "source_depth": 0, "media_position": 1, "is_topic": True, "is_due": False, "attached_rank": 6},
        {"card_id": 8, "availability": "suspended", "source_depth": 0, "media_position": 1, "is_topic": True, "is_due": True, "attached_rank": 7},
    ]

    selection = media_review.select_linked_media_review_rows(
        rows,
        order="media_position",
        card_kind="topics",
        tree_scope="direct",
        media_range="to_current",
        current_position=4,
        state="due",
        limit=1,
    )

    assert selection["card_ids"] == [1]
    assert selection["topic_count"] == 1
    assert selection["item_count"] == 0
    assert selection["exclusions"] == {
        "suspended": 1,
        "buried": 0,
        "filtered": 0,
        "missing": 0,
        "nested": 1,
        "beyond_current": 1,
        "unknown_position": 1,
        "other_kind": 1,
        "not_due": 1,
        "limit": 1,
    }


def test_topic_item_or_both_choice_uses_the_same_classified_rows():
    rows = [
        {"card_id": 1, "availability": "available", "is_topic": True},
        {"card_id": 2, "availability": "available", "is_topic": False},
        {"card_id": 3, "availability": "available", "is_topic": False},
    ]

    assert media_review.select_linked_media_review_rows(
        rows,
        card_kind="topics",
    )["card_ids"] == [1]
    assert media_review.select_linked_media_review_rows(
        rows,
        card_kind="items",
    )["card_ids"] == [2, 3]
    assert media_review.select_linked_media_review_rows(
        rows,
        card_kind="both",
    )["card_ids"] == [1, 2, 3]


def test_include_filtered_option_admits_filtered_cards_and_reports_the_move():
    rows = [
        {
            "card_id": 1,
            "availability": "filtered",
            "is_topic": False,
            "attached_rank": 0,
        },
        {
            "card_id": 2,
            "availability": "available",
            "is_topic": False,
            "attached_rank": 1,
        },
    ]

    excluded = media_review.select_linked_media_review_rows(rows)
    included = media_review.select_linked_media_review_rows(
        rows,
        include_filtered=True,
    )

    assert excluded["card_ids"] == [2]
    assert excluded["exclusions"]["filtered"] == 1
    assert included["card_ids"] == [1, 2]
    assert included["selected_filtered_count"] == 1
    assert included["exclusions"]["filtered"] == 0
    assert included["include_filtered"] is True


def test_seeded_random_order_is_stable_between_preview_and_final_resolution():
    rows = [
        {"card_id": card_id, "availability": "available", "attached_rank": card_id}
        for card_id in range(1, 11)
    ]

    first = media_review.select_linked_media_review_rows(
        rows,
        order="random",
        limit=4,
        random_seed=12345,
    )["card_ids"]
    second = media_review.select_linked_media_review_rows(
        rows,
        order="random",
        limit=4,
        random_seed=12345,
    )["card_ids"]

    assert first == second
    assert len(first) == 4


def test_video_position_is_recovered_from_persisted_reader_link(monkeypatch):
    source_card_id = 321
    note = _FakeNote(
        source_card_id,
        fields=["<a onclick=\"pycmd('incremento_open_video:321:73.5')\">Play</a>"],
    )
    card = _card(701, 70)
    col = _FakeCollection(
        notes={70: note},
        cards={701: card},
        metadata_note_ids=[70],
    )
    monkeypatch.setattr(media_review, "get_knowledge_tree_nodes", lambda *_args: [])

    rows = media_review.inspect_linked_media_review_rows(
        "/addon",
        "Profile",
        source_card_id,
        col=col,
        media_kind="video",
        topic_classifier=object(),
    )

    assert rows[0]["media_position"] == 73.5


def test_epub_position_is_recovered_from_exact_anchor_link():
    note = _FakeNote(
        fields=[
            '<a onclick="pycmd(&quot;incremento_open_epub:321:3:88:0.375&quot;)">Chapter</a>'
        ],
    )

    assert media_review._media_position_from_note(note, "epub", 321) == 3
