"""User-facing full-backup restore coordinator for the active Anki profile."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

try:
    from ..backend.activity_log import fail_activity, finish_activity, start_activity, update_activity
    from ..backend.restore_bundle import (
        RestoreRollbackError, precheck_backup, stage_backup, swap_staged_backup,
    )
    from ..backend.paths import get_user_files_dir
except ImportError:
    from backend.activity_log import fail_activity, finish_activity, start_activity, update_activity
    from backend.restore_bundle import (
        RestoreRollbackError, precheck_backup, stage_backup, swap_staged_backup,
    )
    from backend.paths import get_user_files_dir


_restore_running = False


def default_backup_folder(policy: object, fallback: Path) -> Path:
    """Prefer this profile's configured automatic-backup directory in the picker."""
    directory = policy.get("directory") if isinstance(policy, dict) else None
    if isinstance(directory, str) and directory:
        folder = Path(directory).expanduser()
        if folder.is_dir():
            return folder
    return fallback


def restore_full_backup(
    main_window,
    *,
    addon_dir: str,
    profile_key: str,
    profile_name: str,
    current_config: dict,
    save_config: Callable[[dict], None],
    backup_running: Callable[[], bool],
    reset_close_gate: Callable[[], None],
) -> None:
    """Pre-check, stage, confirm, then replace the closed profile with rollback."""
    from aqt.operations import QueryOp
    from aqt.qt import QFileDialog, QMessageBox
    from aqt.utils import showWarning, tooltip

    global _restore_running
    if _restore_running or backup_running():
        tooltip("A full backup or restore is already running.")
        return
    folder = default_backup_folder(
        current_config.get("automatic_backups", {}).get(profile_key, {}),
        Path.home(),
    )
    selected, _ = QFileDialog.getOpenFileName(
        main_window, "Select Full Incremento Backup", str(folder), "ZIP files (*.zip)"
    )
    if not selected:
        return

    collection = Path(main_window.pm.collectionPath())
    media = collection.parent / "collection.media"
    runtime = get_user_files_dir(addon_dir, profile_key)
    old_config = copy.deepcopy(current_config)
    old_auto_sync = main_window.pm.profile.get("autoSync", True)
    old_periodic_media_sync = main_window.pm.profile.get("autoSyncMediaMinutes", 15)
    activity = start_activity(
        "Restore full profile backup", category="Backup", detail="Checking backup…"
    )
    _restore_running = True

    def same_profile() -> bool:
        return main_window.pm.name == profile_name

    def restore_sync_preferences() -> None:
        main_window.pm.profile["autoSync"] = old_auto_sync
        main_window.pm.profile["autoSyncMediaMinutes"] = old_periodic_media_sync

    def fail(message: str, *, stage=None) -> None:
        global _restore_running
        _restore_running = False
        if stage is not None:
            main_window.taskman.run_in_background(stage.cleanup, lambda _future: None)
        fail_activity(activity, message)
        showWarning(message)

    def after_check(future) -> None:
        try:
            report, stage = future.result()
        except Exception as exc:
            fail(f"Backup pre-check failed: {exc}")
            return
        if not same_profile() or backup_running():
            fail("Restore stopped because the profile changed or a backup started.", stage=stage)
            return
        prompt = QMessageBox(main_window)
        prompt.setWindowTitle("Restore Full Backup")
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setText(
            f"Replace the current Anki profile “{profile_name}” with this backup?"
        )
        mismatch = (
            "\nThe backup profile name differs from the current profile. "
            "Its Incremento files will be placed under the current profile."
            if report.profile_mismatch else ""
        )
        missing_covers = (
            f"\nWarning: {report.missing_cover_count:,} PDF/EPUB covers referenced by "
            "cards are missing from this backup. Their source titles will remain, "
            "but those cover images will not be restored."
            if report.missing_cover_count else ""
        )
        prompt.setInformativeText(
            f"Backup profile: {report.source_profile}\n"
            f"Cards: {report.card_count:,}  •  Anki media files: {report.media_count:,}\n"
            f"Incremento files: {report.profile_file_count:,}"
            f"{mismatch}{missing_covers}\n\n"
            "The current collection, Anki media, and Incremento profile files "
            "will be replaced. Anki will create a safety backup first. "
            "Automatic collection and periodic media sync will be turned off "
            "until you re-enable them. Backup settings for your other profiles "
            "will be kept.\n\n"
            "AnkiWeb is not checked. A later normal sync can merge remote changes "
            "or deletions. If the restored cards should replace AnkiWeb, force a "
            "one-way Upload on your first manual sync; Download replaces the "
            "local collection. Anki media sync merges separately."
        )
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        prompt.setDefaultButton(QMessageBox.StandardButton.No)
        if prompt.exec() != QMessageBox.StandardButton.Yes:
            main_window.taskman.run_in_background(stage.cleanup, lambda _future: None)
            finish_activity(activity, detail="Restore cancelled after successful pre-check.")
            global _restore_running
            _restore_running = False
            return

        update_activity(activity, detail="Creating safety backup…")

        def safety_failed(error: Exception) -> None:
            fail(f"Could not create an Anki safety backup: {error}", stage=stage)

        def after_safety(_unused) -> None:
            try:
                if not same_profile() or backup_running():
                    raise RuntimeError("The profile changed or a backup started.")
                main_window.pm.profile["autoSync"] = False
                main_window.pm.profile["autoSyncMediaMinutes"] = 0
                main_window.pm.save()
                main_window.restoring_backup = True
                update_activity(activity, detail="Closing profile for restore…")
                main_window.unloadProfile(after_unload)
            except Exception as exc:
                restore_sync_preferences()
                main_window.restoring_backup = False
                try:
                    main_window.pm.save()
                except Exception:
                    pass
                fail(f"Could not close the profile for restore: {exc}", stage=stage)

        def after_unload() -> None:
            main_window.restoring_backup = False
            if not same_profile():
                fail("Restore stopped because the active profile changed.", stage=stage)
                return
            update_activity(activity, detail="Replacing profile files…")
            main_window.taskman.run_in_background(
                lambda: swap_staged_backup(stage, collection, media, runtime),
                after_swap,
            )

        def after_swap(future) -> None:
            try:
                swap = future.result()
            except Exception as exc:
                if isinstance(exc, RestoreRollbackError):
                    fail(
                        f"Restore stopped with an incomplete rollback: {exc} "
                        f"The prior files remain in {stage.profile_stage_dir} and "
                        f"{stage.runtime_stage_dir}. Keep Anki closed for this profile "
                        "until those files are recovered."
                    )
                    return
                restore_sync_preferences()
                save_error = None
                try:
                    main_window.pm.save()
                except Exception as error:
                    save_error = error
                try:
                    main_window.loadProfile()
                except Exception as reopen_exc:
                    fail(
                        f"Restore could not replace profile files: {exc}. "
                        f"The previous profile also could not reopen: {reopen_exc}",
                        stage=stage,
                    )
                    return
                detail = f"Restore could not replace profile files: {exc}"
                if save_error is not None:
                    detail += f". Automatic-sync preference could not be saved: {save_error}"
                fail(detail, stage=stage)
                return

            def rollback_restore(reason: Exception) -> None:
                """Close a loaded collection before moving the prior files back."""
                update_activity(activity, detail="Rolling back failed restore…")

                def after_rollback(rollback_future) -> None:
                    try:
                        rollback_future.result()
                    except Exception as rollback_exc:
                        fail(
                            f"Restore failed: {reason}. Automatic rollback also failed: "
                            f"{rollback_exc}. The prior files remain in "
                            f"{stage.profile_stage_dir} and {stage.runtime_stage_dir}."
                        )
                        return
                    config_error = None
                    try:
                        save_config(old_config)
                    except Exception as error:
                        config_error = error
                    restore_sync_preferences()
                    preference_error = None
                    try:
                        main_window.pm.save()
                    except Exception as error:
                        preference_error = error
                    try:
                        main_window.loadProfile()
                        if main_window.col is None:
                            raise RuntimeError("The previous collection could not reopen.")
                    except Exception as reopen_exc:
                        fail(
                            f"Restore failed: {reason}. Prior files were put back, "
                            f"but the profile could not reopen: {reopen_exc}",
                            stage=stage,
                        )
                        return
                    if config_error is not None or preference_error is not None:
                        fail(
                            f"Restore failed and the previous profile was restored, "
                            "but some settings could not be saved: "
                            f"{config_error or preference_error}",
                            stage=stage,
                        )
                        return
                    fail(
                        f"Restore failed and the previous profile was restored: {reason}",
                        stage=stage,
                    )

                def do_rollback() -> None:
                    main_window.restoring_backup = False
                    main_window.taskman.run_in_background(swap.rollback, after_rollback)

                if main_window.col is not None:
                    try:
                        reset_close_gate()
                        main_window.restoring_backup = True
                        main_window.unloadProfile(do_rollback)
                    except Exception as close_exc:
                        fail(
                            f"Restore failed: {reason}. The restored collection could not "
                            f"close for rollback: {close_exc}. Prior files remain in "
                            f"{stage.profile_stage_dir} and {stage.runtime_stage_dir}."
                        )
                else:
                    do_rollback()

            try:
                restored_config = copy.deepcopy(stage.config)
                restored_config["automatic_backups"] = copy.deepcopy(
                    old_config.get("automatic_backups", {})
                )
                save_config(restored_config)
                update_activity(activity, detail="Opening restored profile…")
                main_window.loadProfile()
                if main_window.col is None:
                    raise RuntimeError("Anki could not open the restored collection.")
            except Exception as exc:
                rollback_restore(exc)
                return

            def after_cleanup(cleanup_future) -> None:
                global _restore_running
                _restore_running = False
                try:
                    cleanup_future.result()
                except Exception as exc:
                    fail_activity(
                        activity,
                        f"Restore succeeded, but old-file cleanup failed: {exc}. "
                        f"Check {stage.profile_stage_dir} and {stage.runtime_stage_dir}.",
                    )
                    return
                finish_activity(activity, detail="Profile restored; automatic sync is off.")
                tooltip("Full backup restored. Review the profile before syncing.")

            def cleanup() -> None:
                swap.commit()
                stage.cleanup()

            main_window.taskman.run_in_background(cleanup, after_cleanup)

        QueryOp(
            parent=main_window,
            op=lambda _collection: main_window.create_backup_now(),
            success=after_safety,
        ).failure(safety_failed).with_progress().run_in_background()

    def check_and_stage():
        report = precheck_backup(selected, target_profile=profile_key)
        update_activity(activity, detail="Staging checked backup…")
        stage = stage_backup(selected, report, collection, runtime)
        return report, stage

    main_window.taskman.run_in_background(check_and_stage, after_check)
