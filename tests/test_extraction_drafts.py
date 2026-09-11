import json

import extraction_drafts


def test_draft_round_trips_per_profile_and_keeps_only_bounded_supported_fields(tmp_path):
    saved = extraction_drafts.save_extraction_draft(
        str(tmp_path),
        "Profile A",
        {
            "source": "pdf",
            "note_type": "Basic",
            "deck": "Reading",
            "fields": ["Question", "Answer"],
            "tags": ["reading", "topic"],
            "extract_options": {"priority": 24, "mark_topic": True},
            "extract_context": {"parent_card_id": 91},
            "ignored": "must not be persisted",
        },
        now=1234.5,
    )

    assert saved["version"] == 1
    assert saved["saved_at"] == 1234.5
    assert extraction_drafts.load_extraction_draft(
        str(tmp_path), "Profile A"
    ) == saved
    assert extraction_drafts.load_extraction_draft(str(tmp_path), "Profile B") is None
    assert "ignored" not in saved


def test_corrupt_or_wrong_version_draft_fails_closed_without_deleting_evidence(tmp_path):
    path = extraction_drafts.extraction_draft_path(str(tmp_path), "Profile")
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    assert extraction_drafts.load_extraction_draft(str(tmp_path), "Profile") is None
    assert path.read_text(encoding="utf-8") == "{broken"

    path.write_text(json.dumps({"version": 99, "fields": ["x"]}), encoding="utf-8")
    assert extraction_drafts.load_extraction_draft(str(tmp_path), "Profile") is None


def test_clear_removes_only_the_requested_profiles_known_draft(tmp_path):
    extraction_drafts.save_extraction_draft(
        str(tmp_path), "Profile A", {"fields": ["one"]}
    )
    extraction_drafts.save_extraction_draft(
        str(tmp_path), "Profile B", {"fields": ["two"]}
    )

    assert extraction_drafts.clear_extraction_draft(str(tmp_path), "Profile A") is True
    assert extraction_drafts.load_extraction_draft(str(tmp_path), "Profile A") is None
    assert extraction_drafts.load_extraction_draft(str(tmp_path), "Profile B") is not None
    assert extraction_drafts.clear_extraction_draft(str(tmp_path), "Profile A") is False


def test_normalizer_rejects_empty_content_and_caps_user_controlled_payloads():
    assert extraction_drafts.normalize_extraction_draft({"fields": ["", "  "]}) is None

    normalized = extraction_drafts.normalize_extraction_draft(
        {
            "fields": ["x" * 600_000, "answer"],
            "tags": [f"tag-{index}" for index in range(300)],
            "source": "pdf" * 100,
        },
        now=42,
    )

    assert normalized is not None
    assert len(normalized["fields"][0]) == 500_000
    assert len(normalized["tags"]) == 100
    assert len(normalized["source"]) <= 32


def test_draft_round_trip_preserves_web_anchor_dom_paths(tmp_path):
    draft = {
        "source": "web",
        "fields": ["selected passage"],
        "extract_context": {
            "web_extract_records": [
                {
                    "version": 1,
                    "webCardId": 17,
                    "url": "https://example.com/guide",
                    "anchor": {
                        "version": 1,
                        "id": "stable-id",
                        "exact": "selected passage",
                        "prefix": "before ",
                        "suffix": " after",
                        "startPath": [0, 2, 1],
                        "startOffset": 4,
                        "endPath": [0, 2, 1],
                        "endOffset": 20,
                    },
                }
            ]
        },
    }

    saved = extraction_drafts.save_extraction_draft(
        str(tmp_path),
        "Profile",
        draft,
        now=12,
    )
    restored = extraction_drafts.load_extraction_draft(str(tmp_path), "Profile")

    assert restored == saved
    anchor = restored["extract_context"]["web_extract_records"][0]["anchor"]
    assert anchor["startPath"] == [0, 2, 1]
    assert anchor["endPath"] == [0, 2, 1]


def test_draft_round_trip_preserves_web_snapshot_region(tmp_path):
    draft = {
        "source": "web",
        "fields": ['<img src="capture.png">'],
        "extract_context": {
            "web_extract_records": [
                {
                    "version": 1,
                    "webCardId": 17,
                    "url": "https://example.com/guide",
                    "anchor": {
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
                    },
                }
            ]
        },
    }

    saved = extraction_drafts.save_extraction_draft(
        str(tmp_path),
        "Profile",
        draft,
        now=12,
    )
    restored = extraction_drafts.load_extraction_draft(str(tmp_path), "Profile")

    assert restored == saved
    anchor = restored["extract_context"]["web_extract_records"][0]["anchor"]
    assert anchor["kind"] == "snapshot"
    assert anchor["anchorPath"] == [0, 2]
    assert anchor["width"] == 200
