"""Exercise the entrypoint's close-backup sequencing with bounded fake boundaries."""

import ast
from pathlib import Path
from types import SimpleNamespace

from backend import backup_schedule


def _entrypoint_function(namespace, name):
    source = (Path(__file__).resolve().parents[1] / "__init__.py").read_text(
        encoding="utf-8"
    )
    function = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    exec(compile(ast.Module(body=[function], type_ignores=[]), "__init__.py", "exec"), namespace)
    return namespace[name]


def test_close_waits_for_existing_backup_then_starts_close_backup_before_unload(tmp_path):
    profile_root = tmp_path / "addon" / "user_files" / "P"
    profile_root.mkdir(parents=True)
    destination = tmp_path / "backups"
    destination.mkdir()
    starts = []
    closed = []
    namespace = {
        "__name__": "incremento",
        "_ADDON_DIR": str(tmp_path / "addon"),
        "_active_profile": lambda: "P",
        "_full_backup_running": True,
        "_backup_idle_callbacks": [],
        "_load_addon_config": lambda *_: {"automatic_backups": {"P": {
            "enabled": True, "directory": str(destination), "on_close": True,
        }}},
        "_backup_schedule": backup_schedule,
        "_paths": SimpleNamespace(get_user_files_dir=lambda *_: profile_root),
        "_start_full_backup": lambda path, *, automatic_policy, close_triggered: starts.append(
            (path, automatic_policy)
        ) or True,
        "_record_close_backup_result": lambda *_args, **_kwargs: None,
        "mw": SimpleNamespace(addonManager=object()),
        "tooltip": lambda _message: None,
        "time": SimpleNamespace(time=lambda: 1000.0),
    }
    prepare = _entrypoint_function(namespace, "_prepare_profile_close")

    prepare(lambda: closed.append(True))
    assert starts == []
    assert closed == []
    assert len(namespace["_backup_idle_callbacks"]) == 1

    namespace["_full_backup_running"] = False
    namespace["_backup_idle_callbacks"].pop(0)()
    assert len(starts) == 1
    assert starts[0][1]["on_close"] is True
    assert Path(starts[0][0]).parent == destination
    assert closed == []
    namespace["_backup_idle_callbacks"].pop(0)()
    assert closed == [True]


def test_unavailable_close_destination_reports_failure_and_continues_unload(tmp_path):
    notifications = []
    closed = []
    failures = []
    namespace = {
        "__name__": "incremento",
        "_ADDON_DIR": str(tmp_path),
        "_active_profile": lambda: "P",
        "_full_backup_running": False,
        "_backup_idle_callbacks": [],
        "_load_addon_config": lambda *_: {"automatic_backups": {"P": {
            "enabled": True, "directory": str(tmp_path / "missing"), "on_close": True,
        }}},
        "_backup_schedule": backup_schedule,
        "_paths": SimpleNamespace(get_user_files_dir=lambda *_: tmp_path / "user_files" / "P"),
        "_start_full_backup": lambda *_args, **_kwargs: None,
        "_record_close_backup_result": lambda profile, *, failed: failures.append((profile, failed)),
        "mw": SimpleNamespace(addonManager=object()),
        "tooltip": notifications.append,
        "time": SimpleNamespace(time=lambda: 1000.0),
    }
    _entrypoint_function(namespace, "_prepare_profile_close")(
        lambda: closed.append(True)
    )
    assert closed == [True]
    assert len(notifications) == 1
    assert "folder unavailable" in notifications[0]
    assert failures == [("P", True)]


def test_close_failure_marker_persists_only_in_selected_profile_policy():
    saved = []
    cfg = {"automatic_backups": {
        "P": {"enabled": True, "directory": "/backup", "on_close": True},
        "Q": {"enabled": True, "directory": "/other", "on_close": False},
    }}
    namespace = {
        "__name__": "incremento",
        "mw": SimpleNamespace(addonManager=object()),
        "_load_addon_config": lambda *_: cfg,
        "_save_addon_config": lambda _manager, _package, config: saved.append(config),
        "_backup_schedule": backup_schedule,
    }
    record = _entrypoint_function(namespace, "_record_close_backup_result")
    record("P", failed=True)
    assert saved[-1]["automatic_backups"]["P"]["last_close_failed"] is True
    assert saved[-1]["automatic_backups"]["Q"] == {
        "enabled": True, "directory": "/other", "on_close": False,
    }
    record("P", failed=False)
    assert saved[-1]["automatic_backups"]["P"]["last_close_failed"] is False
