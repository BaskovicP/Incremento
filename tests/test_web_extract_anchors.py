import web_extract_anchors


def _anchor(*, exact: str = "selected passage", start: int = 2) -> dict:
    return {
        "version": 1,
        "exact": exact,
        "prefix": "before ",
        "suffix": " after",
        "startPath": [0, 1],
        "startOffset": start,
        "endPath": [0, 1],
        "endOffset": start + len(exact),
    }


def _snapshot_anchor(**overrides) -> dict:
    anchor = {
        "version": 1,
        "kind": "snapshot",
        "pageX": 140,
        "pageY": 580,
        "width": 200,
        "height": 100,
        "documentWidth": 1200,
        "documentHeight": 4000,
        "anchorPath": [0, 2],
        "anchorTag": "article",
        "anchorXRatio": 350_000,
        "anchorYRatio": 400_000,
    }
    anchor.update(overrides)
    return anchor


def test_anchor_normalization_is_deterministic_and_keeps_quote_context():
    first = web_extract_anchors.normalize_web_extract_anchor(_anchor())
    second = web_extract_anchors.normalize_web_extract_anchor(_anchor())

    assert first == second
    assert first == {
        "version": 1,
        "id": first["id"],
        "exact": "selected passage",
        "prefix": "before ",
        "suffix": " after",
        "startPath": [0, 1],
        "startOffset": 2,
        "endPath": [0, 1],
        "endOffset": 18,
    }
    assert len(first["id"]) == 24


def test_anchor_normalization_rejects_oversized_or_hostile_boundaries():
    oversized = _anchor(
        exact="x" * (web_extract_anchors.MAX_WEB_EXTRACT_EXACT_CHARS + 1)
    )
    negative_path = _anchor()
    negative_path["startPath"] = [-1]
    excessive_depth = _anchor()
    excessive_depth["endPath"] = [0] * (
        web_extract_anchors.MAX_WEB_EXTRACT_PATH_DEPTH + 1
    )
    fractional_path = _anchor()
    fractional_path["startPath"] = [1.5]
    fractional_offset = _anchor()
    fractional_offset["endOffset"] = 2.5

    assert web_extract_anchors.normalize_web_extract_anchor(oversized) is None
    assert web_extract_anchors.normalize_web_extract_anchor(negative_path) is None
    assert web_extract_anchors.normalize_web_extract_anchor(excessive_depth) is None
    assert web_extract_anchors.normalize_web_extract_anchor(fractional_path) is None
    assert web_extract_anchors.normalize_web_extract_anchor(fractional_offset) is None
    assert web_extract_anchors.normalize_web_extract_anchor({"exact": ""}) is None


def test_snapshot_anchor_normalization_is_bounded_and_deterministic():
    first = web_extract_anchors.normalize_web_extract_anchor(_snapshot_anchor())
    second = web_extract_anchors.normalize_web_extract_anchor(_snapshot_anchor())

    assert first == second
    assert first == {
        "version": 1,
        "id": first["id"],
        "kind": "snapshot",
        "pageX": 140,
        "pageY": 580,
        "width": 200,
        "height": 100,
        "documentWidth": 1200,
        "documentHeight": 4000,
        "anchorPath": [0, 2],
        "anchorTag": "article",
        "anchorXRatio": 350_000,
        "anchorYRatio": 400_000,
    }
    assert len(first["id"]) == 24


def test_snapshot_anchor_normalization_rejects_unsafe_geometry():
    for changes in (
        {"width": 5},
        {"height": True},
        {"pageY": -1},
        {"documentHeight": 0},
        {"anchorPath": [-1]},
        {"anchorXRatio": 1_000_001},
        {"anchorTag": "article<script>"},
    ):
        assert (
            web_extract_anchors.normalize_web_extract_anchor(
                _snapshot_anchor(**changes)
            )
            is None
        )


def test_record_normalization_requires_card_and_safe_exact_http_url():
    record = web_extract_anchors.normalize_web_extract_record(
        {
            "version": 1,
            "webCardId": 17,
            "url": "HTTPS://Example.COM/guide?q=1#part",
            "anchor": _anchor(),
        }
    )

    assert record is not None
    assert record["webCardId"] == 17
    assert record["url"] == "https://example.com/guide?q=1#part"
    assert record["anchor"]["exact"] == "selected passage"
    assert (
        web_extract_anchors.normalize_web_extract_record(
            {
                "webCardId": 0,
                "url": "https://example.com/",
                "anchor": _anchor(),
            }
        )
        is None
    )


def test_record_normalization_rejects_fractional_or_boolean_identity_values():
    base = {
        "version": 1,
        "webCardId": 17,
        "url": "https://example.com/guide",
        "anchor": _anchor(),
    }

    for field, value in (
        ("version", 1.5),
        ("version", True),
        ("webCardId", 17.5),
        ("webCardId", True),
    ):
        candidate = dict(base)
        candidate[field] = value
        assert web_extract_anchors.normalize_web_extract_record(candidate) is None
    assert (
        web_extract_anchors.normalize_web_extract_record(
            {
                "webCardId": 17,
                "url": "https://user:secret@example.com/",
                "anchor": _anchor(),
            }
        )
        is None
    )


def test_anchor_normalization_accepts_integral_numbers_from_qt_javascript():
    text_anchor = _anchor()
    text_anchor.update(
        {
            "version": 1.0,
            "startPath": [0.0, 1.0],
            "endPath": [0.0, 1.0],
            "startOffset": 2.0,
            "endOffset": 18.0,
        }
    )
    snapshot_anchor = _snapshot_anchor(
        version=1.0,
        pageX=140.0,
        pageY=580.0,
        width=200.0,
        height=100.0,
        documentWidth=1200.0,
        documentHeight=4000.0,
        anchorPath=[0.0, 2.0],
        anchorXRatio=350_000.0,
        anchorYRatio=400_000.0,
    )

    assert web_extract_anchors.normalize_web_extract_anchor(text_anchor) is not None
    assert web_extract_anchors.normalize_web_extract_anchor(snapshot_anchor) is not None


def test_record_list_is_bounded_and_deduplicated_without_mutating_input():
    raw = {
        "webCardId": 17,
        "url": "https://example.com/guide",
        "anchor": _anchor(),
    }
    records = web_extract_anchors.normalize_web_extract_records(
        [raw, raw, *[{
            "webCardId": 17,
            "url": "https://example.com/guide",
            "anchor": _anchor(exact=f"passage {index}", start=index),
        } for index in range(100)]],
        limit=5,
    )

    assert len(records) == 5
    assert records[0]["anchor"]["exact"] == "selected passage"
    assert raw["anchor"].get("id") is None
    assert web_extract_anchors.normalize_web_extract_records([raw], limit=0) == []
