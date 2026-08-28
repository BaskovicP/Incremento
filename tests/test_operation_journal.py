import os

import db
import operation_journal
import pytest


def setup_function():
    db.close_connection()


def teardown_function():
    db.close_connection()


def test_failed_import_removes_only_tracked_profile_file(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    profile_root = tmp_path / "user_files" / profile
    created = profile_root / "pdfs" / "created.pdf"
    preserved = profile_root / "pdfs" / "preserved.pdf"
    created.parent.mkdir(parents=True)
    created.write_text("created")
    preserved.write_text("preserved")

    try:
        with operation_journal.ImportOperation(addon_dir, profile, "pdf") as operation:
            operation.track_created_relpath("pdfs/created.pdf")
            raise RuntimeError("Anki rejected note")
    except RuntimeError:
        pass

    assert not created.exists()
    assert preserved.read_text() == "preserved"
    row = db.get_connection(addon_dir, profile).execute(
        "SELECT state, error_code FROM import_journal"
    ).fetchone()
    assert row == ("rolled_back", "RuntimeError")


def test_committed_import_registers_stable_content_item(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    with operation_journal.ImportOperation(addon_dir, profile, "epub") as operation:
        operation.bind_anki(card_id=123, note_id=456)
        operation.commit(storage_key="epubs/book.epub")
        content_id = operation.content_id

    conn = db.get_connection(addon_dir, profile)
    assert conn.execute(
        "SELECT content_id, kind, card_id, note_id, storage_key FROM content_items"
    ).fetchone() == (content_id, "epub", 123, 456, "epubs/book.epub")
    assert conn.execute("SELECT state FROM import_journal").fetchone() == ("committed",)


def test_pending_descriptors_expose_only_recovery_identity_and_safe_paths(tmp_path):
    operation = operation_journal.ImportOperation(str(tmp_path), "Profile", "pdf")
    operation.track_created_relpath("pdfs/book.pdf")

    assert operation_journal.pending_import_descriptors(
        str(tmp_path), "Profile"
    ) == (
        {
            "content_id": operation.content_id,
            "kind": "pdf",
            "card_id": None,
            "note_id": None,
            "relpaths": ("pdfs/book.pdf",),
        },
    )


def test_pending_recovery_preflight_does_not_create_a_database(tmp_path):
    assert not operation_journal.pending_import_recovery_needed(
        str(tmp_path),
        "Profile",
    )
    assert not (tmp_path / "user_files" / "Profile" / "incremento.db").exists()


def test_pending_recovery_preflight_detects_only_pending_rows(tmp_path):
    addon_dir = str(tmp_path)
    profile = "Profile"
    operation = operation_journal.ImportOperation(addon_dir, profile, "pdf")

    assert operation_journal.pending_import_recovery_needed(addon_dir, profile)

    operation.rollback()
    assert not operation_journal.pending_import_recovery_needed(addon_dir, profile)


def test_recovery_preserves_pending_import_when_card_exists(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    operation = operation_journal.ImportOperation(addon_dir, profile, "writing")
    operation.bind_anki(card_id=99, note_id=98)

    result = operation_journal.recover_interrupted_imports(
        addon_dir,
        profile,
        live_card_ids={99},
    )

    assert result == {"recovered": 1, "rolled_back": 0, "failed_cleanup": 0}
    assert db.get_connection(addon_dir, profile).execute(
        "SELECT state FROM import_journal WHERE operation_id=?",
        (operation.operation_id,),
    ).fetchone() == ("committed",)


def test_recovery_rebinds_card_from_stable_content_identity(tmp_path):
    addon_dir = str(tmp_path)
    profile = "TestProfile"
    operation = operation_journal.ImportOperation(addon_dir, profile, "pdf")
    content_id = operation.content_id

    result = operation_journal.recover_interrupted_imports(
        addon_dir,
        profile,
        live_card_ids={321},
        content_matches={content_id: (321, 654)},
    )

    assert result == {"recovered": 1, "rolled_back": 0, "failed_cleanup": 0}
    conn = db.get_connection(addon_dir, profile)
    assert conn.execute(
        "SELECT state, card_id, note_id FROM import_journal WHERE operation_id=?",
        (operation.operation_id,),
    ).fetchone() == ("committed", 321, 654)
    assert conn.execute(
        "SELECT content_id, card_id, note_id FROM content_items"
    ).fetchone() == (content_id, 321, 654)


def test_journal_rejects_paths_outside_profile(tmp_path):
    operation = operation_journal.ImportOperation(str(tmp_path), "Profile", "pdf")
    try:
        operation.track_created_relpath("../outside")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe journal path was accepted")
    operation.rollback()
    assert not os.path.exists(tmp_path / "outside")


def test_rollback_unlinks_replaced_symlink_without_following_it(tmp_path):
    addon_dir = str(tmp_path / "addon")
    profile = "Profile"
    protected = tmp_path / "protected"
    protected.mkdir()
    protected_file = protected / "keep.txt"
    protected_file.write_text("keep")

    tracked = (
        tmp_path
        / "addon"
        / "user_files"
        / profile
        / "pdfs"
        / "created.pdf"
    )
    tracked.parent.mkdir(parents=True)
    try:
        tracked.symlink_to(protected, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    operation = operation_journal.ImportOperation(addon_dir, profile, "pdf")
    operation.track_created_relpath("pdfs/created.pdf")
    operation.rollback()

    assert not tracked.exists()
    assert not tracked.is_symlink()
    assert protected_file.read_text() == "keep"
