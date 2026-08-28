import os
import tempfile

import export_bundle


def test_should_skip_transient_runtime_files():
    assert export_bundle.should_skip_user_file("video_profile/SingletonLock") is True
    assert export_bundle.should_skip_user_file("web_profile/lockfile") is True
    assert export_bundle.should_skip_user_file("__pycache__/module.pyc") is True
    assert export_bundle.should_skip_user_file("writing/note.md") is False


def test_snapshot_tree_copies_files_and_skips_transient_entries():
    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
        os.makedirs(os.path.join(src_dir, "writing"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "video_profile"), exist_ok=True)
        os.makedirs(os.path.join(src_dir, "__pycache__"), exist_ok=True)

        with open(os.path.join(src_dir, "writing", "note.md"), "w", encoding="utf-8") as fh:
            fh.write("hello")
        with open(os.path.join(src_dir, "incremento.db"), "w", encoding="utf-8") as fh:
            fh.write("db")
        with open(
            os.path.join(src_dir, "video_profile", "SingletonLock"), "w", encoding="utf-8"
        ) as fh:
            fh.write("lock")
        with open(os.path.join(src_dir, "__pycache__", "module.pyc"), "w", encoding="utf-8") as fh:
            fh.write("cache")

        stats = export_bundle.snapshot_tree(
            src_dir,
            dst_dir,
            skip_relpaths={"incremento.db"},
        )

        assert os.path.isfile(os.path.join(dst_dir, "writing", "note.md"))
        assert not os.path.exists(os.path.join(dst_dir, "incremento.db"))
        assert not os.path.exists(
            os.path.join(dst_dir, "video_profile", "SingletonLock")
        )
        assert not os.path.exists(os.path.join(dst_dir, "__pycache__", "module.pyc"))
        assert stats["files_copied"] == 1
        assert stats["files_skipped"] == 2


def test_snapshot_tree_does_not_follow_profile_symlinks(tmp_path):
    source = tmp_path / "profile"
    destination = tmp_path / "snapshot"
    outside = tmp_path / "outside.txt"
    source.mkdir()
    outside.write_text("private outside data", encoding="utf-8")
    try:
        (source / "linked.txt").symlink_to(outside)
    except OSError:
        return

    stats = export_bundle.snapshot_tree(str(source), str(destination))

    assert not (destination / "linked.txt").exists()
    assert stats["files_copied"] == 0
    assert stats["files_skipped"] == 1
