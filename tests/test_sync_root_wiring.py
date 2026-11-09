"""Shared-folder sync is reachable from the menu and follows the profile and AnkiWeb lifecycle (§7 step 5)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = (ROOT / "__init__.py").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return ENTRYPOINT.split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]


def test_the_menu_opens_the_sync_dialog():
    assert 'QAction(_t("root_menu_sync"), mw)' in ENTRYPOINT
    assert '"incremento_translation_key", "root_menu_sync"' in ENTRYPOINT
    assert "SyncDialog(" in _body("openSyncDialogFunction")


def test_sync_runs_after_profile_open_after_every_ankiweb_sync_and_publishes_on_close():
    assert "gui_hooks.profile_did_open.append(_start_sync_schedule)" in ENTRYPOINT
    assert "gui_hooks.sync_did_finish.append(_sync_after_ankiweb)" in ENTRYPOINT
    assert "gui_hooks.profile_will_close.append(_publish_sync_on_close)" in ENTRYPOINT
    assert "gui_hooks.collection_will_temporarily_close.append(_cancel_running_sync)" in ENTRYPOINT


def test_background_sync_reads_the_collection_in_a_query_op_and_drops_stale_results():
    body = _body("_start_background_sync")
    assert "QueryOp(" in body and "run_in_background()" in body
    assert "col.db.all" in body
    assert "is_current=" in body and "_sync_generation" in body


def test_closing_publishes_only_and_never_blocks_close_on_failure():
    body = _body("_publish_sync_on_close")
    assert "publish_now(" in body
    assert "except Exception" in body


def test_choosing_a_folder_checks_it_against_this_collection():
    assert "configure(_ADDON_DIR, self.profile, folder, query=mw.col.db.all)" in ENTRYPOINT
