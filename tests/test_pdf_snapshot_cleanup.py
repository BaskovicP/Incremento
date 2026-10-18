import ast
import os
import sys
from types import SimpleNamespace
from types import ModuleType
from hashlib import sha256
from pathlib import Path

import pytest

from backend import pdf_snapshot_cleanup


def _name(image):
    return "incremento-pdf-context-" + sha256(image).hexdigest()[:24] + ".png"


SNAPSHOT = _name(b"image")
SECOND = _name(b"more")


class _Media:
    def __init__(self, path, unused):
        self.path = path
        self.unused = list(unused)
        self.trashed = []

    def dir(self):
        return str(self.path)

    def check(self):
        return SimpleNamespace(unused=list(self.unused))

    def trash_files(self, filenames):
        self.trashed.extend(filenames)


def test_cleanup_preview_only_lists_unused_generated_snapshots(tmp_path):
    (tmp_path / SNAPSHOT).write_bytes(b"image")
    (tmp_path / SECOND).write_bytes(b"more")
    (tmp_path / "other.png").write_bytes(b"other")
    symlink_name = _name(b"link")
    (tmp_path / symlink_name).symlink_to(
        tmp_path / SNAPSHOT
    )
    media = _Media(tmp_path, [SNAPSHOT, SECOND, "other.png", symlink_name])
    collection = SimpleNamespace(media=media)

    preview = pdf_snapshot_cleanup.find_unused_pdf_snapshots(
        collection, protected_fields=[f'<img src="{SECOND}">']
    )

    assert preview.filenames == (SNAPSHOT,)
    assert preview.total_bytes == 5
    assert media.trashed == []


def test_cleanup_rechecks_unused_status_before_moving_approved_files_to_trash(tmp_path):
    (tmp_path / SNAPSHOT).write_bytes(b"image")
    (tmp_path / SECOND).write_bytes(b"more")
    media = _Media(tmp_path, [SNAPSHOT, SECOND])
    collection = SimpleNamespace(media=media)
    preview = pdf_snapshot_cleanup.find_unused_pdf_snapshots(collection)
    assert preview.filenames == tuple(sorted((SNAPSHOT, SECOND)))

    media.unused = [SECOND]
    removed = pdf_snapshot_cleanup.trash_unused_pdf_snapshots(
        collection, preview.filenames
    )

    assert removed.filenames == (SECOND,)
    assert removed.total_bytes == 4
    assert media.trashed == [SECOND]


def test_cleanup_rechecks_saved_draft_references_before_trashing(tmp_path):
    (tmp_path / SNAPSHOT).write_bytes(b"image")
    media = _Media(tmp_path, [SNAPSHOT])
    collection = SimpleNamespace(media=media)

    removed = pdf_snapshot_cleanup.trash_unused_pdf_snapshots(
        collection,
        [SNAPSHOT],
        protected_fields=[f'<img src="{SNAPSHOT}">'],
    )

    assert removed.filenames == ()
    assert media.trashed == []


@pytest.mark.parametrize("still_unused", [True, False])
def test_cleanup_returns_anki_changes_for_collection_operation_even_after_recheck(
    tmp_path, still_unused
):
    (tmp_path / SNAPSHOT).write_bytes(b"image")
    media = _Media(tmp_path, [SNAPSHOT] if still_unused else [])
    changes = object()

    removed = pdf_snapshot_cleanup.trash_unused_pdf_snapshots(
        SimpleNamespace(media=media),
        [SNAPSHOT],
        empty_changes_factory=lambda: changes,
    )

    assert removed.changes is changes
    assert removed.filenames == ((SNAPSHOT,) if still_unused else ())
    assert media.trashed == ([SNAPSHOT] if still_unused else [])


def test_cleanup_keeps_media_when_anki_check_fails(tmp_path):
    media = _Media(tmp_path, [SNAPSHOT])
    media.check = lambda: (_ for _ in ()).throw(RuntimeError("check failed"))

    with pytest.raises(RuntimeError, match="check failed"):
        pdf_snapshot_cleanup.trash_unused_pdf_snapshots(
            SimpleNamespace(media=media), [SNAPSHOT]
        )

    assert media.trashed == []


def test_cleanup_skips_modified_image_even_if_name_matches_generated_pattern(tmp_path):
    (tmp_path / SNAPSHOT).write_bytes(b"different")
    media = _Media(tmp_path, [SNAPSHOT])

    preview = pdf_snapshot_cleanup.find_unused_pdf_snapshots(
        SimpleNamespace(media=media)
    )

    assert preview.filenames == ()
    assert media.trashed == []


def test_utils_menu_exposes_one_cleanup_action_for_all_unused_data():
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text(encoding="utf-8")
    menu = source.split("def _build_incremento_menu()", 1)[1]

    assert "_utilsMenu.addAction(_cleanupNonActiveProfileDataAction)" in menu
    for old_action in (
        "_cleanupPdfSnapshotsAction",
        "_cleanupOrphanPdfsAction",
        "_cleanupOrphanVideosAction",
        "_cleanupStaleProgressAction",
    ):
        assert f"_utilsMenu.addAction({old_action})" not in menu


@pytest.mark.parametrize("include_orphan_pdf", [True, False])
def test_unified_cleanup_uses_one_confirmation_for_orphan_files_and_media(
    tmp_path, monkeypatch, include_orphan_pdf
):
    source_path = Path(__file__).resolve().parents[1] / "__init__.py"
    function = next(
        node for node in ast.parse(source_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "cleanupNonActiveProfileDataFunction"
    )
    if include_orphan_pdf:
        (tmp_path / "orphan.pdf").write_bytes(b"pdf")
    (tmp_path / SNAPSHOT).write_bytes(b"image")
    media = _Media(tmp_path, [SNAPSHOT])
    collection = SimpleNamespace(media=media)
    prompts = []
    messages = []

    class OpChanges:
        pass

    class CollectionOp:
        def __init__(self, _parent, operation):
            self.operation = operation

        def success(self, callback):
            self.callback = callback
            return self

        def failure(self, _callback):
            return self

        def run_in_background(self):
            result = self.operation(collection)
            assert isinstance(result.changes, OpChanges)
            self.callback(result)

    operations = ModuleType("aqt.operations")
    operations.CollectionOp = CollectionOp
    utils = ModuleType("aqt.utils")
    utils.askUser = lambda prompt, **_kwargs: prompts.append(prompt) or True
    anki_collection = ModuleType("anki.collection")
    anki_collection.OpChanges = OpChanges
    monkeypatch.setitem(sys.modules, "aqt.operations", operations)
    monkeypatch.setitem(sys.modules, "aqt.utils", utils)
    monkeypatch.setitem(sys.modules, "anki.collection", anki_collection)

    def translate(key, **kwargs):
        return f"{key} {kwargs}"

    namespace = {
        "_ADDON_DIR": str(tmp_path),
        "_active_profile": lambda: "TestProfile",
        "_current_profile_name": lambda: "TestProfile",
        "_snapshot_cleanup_add_cards_is_open": lambda: False,
        "_snapshot_cleanup_draft_fields": lambda _profile: (),
        "_scan_orphan_pdfs": lambda: (
            str(tmp_path), ["orphan.pdf"] if include_orphan_pdf else [],
            3 if include_orphan_pdf else 0,
        ),
        "_scan_orphan_videos": lambda: (str(tmp_path), [], 0),
        "_partition_any_profile_ties": lambda names, _kind: (names, [], {}),
        "_count_stale_progress_rows": lambda: {},
        "_count_stale_document_text_index_rows": lambda: {},
        "_count_stale_ocr_rows": lambda: {},
        "_prune_stale_progress_rows": lambda: {},
        "_prune_stale_document_text_index_rows": lambda: {},
        "_prune_stale_ocr_rows": lambda: {},
        "_format_pruned_progress_summary": lambda _counts: "",
        "_format_pruned_document_text_index_summary": lambda _counts: "",
        "_format_pruned_ocr_summary": lambda _counts: "",
        "_pdf_snapshot_cleanup_mod": pdf_snapshot_cleanup,
        "_t": translate,
        "mw": SimpleNamespace(col=collection),
        "os": os,
        "showInfo": messages.append,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)

    namespace["cleanupNonActiveProfileDataFunction"]()

    assert len(prompts) == 1
    assert "root_cleanup_snapshot_files" in prompts[0]
    assert not (tmp_path / "orphan.pdf").exists()
    assert media.trashed == [SNAPSHOT]
    assert len(messages) == 1
