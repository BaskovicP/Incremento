"""Guards of scripts/sync_e2e.py, which replaces an AnkiWeb collection and clears directories."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sync_e2e_script", ROOT / "scripts" / "sync_e2e.py")
sync_e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_e2e)


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("INC_E2E_USER", "someone@example.org")
    monkeypatch.setenv("INC_E2E_PASS", "secret")


def test_a_run_requires_confirming_that_the_ankiweb_collection_may_be_replaced(tmp_path, credentials):
    with pytest.raises(SystemExit, match="--overwrite-ankiweb"):
        sync_e2e.main(["two-devices", "--workdir", str(tmp_path / "run")])

    assert not (tmp_path / "run").exists()


def test_a_run_requires_credentials_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("INC_E2E_USER", raising=False)
    monkeypatch.delenv("INC_E2E_PASS", raising=False)

    with pytest.raises(SystemExit, match="INC_E2E_USER"):
        sync_e2e.main(["two-devices", "--workdir", str(tmp_path / "run"), "--overwrite-ankiweb"])


def test_the_work_directory_must_be_outside_the_repository(credentials):
    with pytest.raises(SystemExit, match="outside the repository"):
        sync_e2e.main(["two-devices", "--workdir", str(ROOT / "e2e-run"), "--overwrite-ankiweb"])

    assert not (ROOT / "e2e-run").exists()


def test_a_directory_with_other_files_is_never_cleared(tmp_path):
    keep = tmp_path / "important.txt"
    keep.write_text("mine", encoding="utf-8")

    with pytest.raises(SystemExit, match="not empty"):
        sync_e2e.fresh_directory(tmp_path)

    assert keep.read_text(encoding="utf-8") == "mine"


def test_a_directory_made_by_an_earlier_run_is_cleared_for_the_next(tmp_path):
    run = tmp_path / "run"
    sync_e2e.fresh_directory(run)
    (run / "left-over").write_text("x", encoding="utf-8")

    sync_e2e.fresh_directory(run)

    assert sorted(path.name for path in run.iterdir()) == [sync_e2e.MARKER]


def test_windows_paths_are_translated_for_a_device_inside_wsl():
    assert sync_e2e._wsl_path(Path("C:/Users/me/Cloud Folder")) == "/mnt/c/Users/me/Cloud Folder"
