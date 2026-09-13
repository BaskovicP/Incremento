"""User-facing full-backup restore coordinator for the active Anki profile."""

from __future__ import annotations

try:
    from ..backend.i18n import t, format_number
except ImportError:
    from backend.i18n import t, format_number

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
        tooltip(t('admin_full_restore_a_full_backup_or_restore_is_already_running'))
        return
    folder = default_backup_folder(
        current_config.get("automatic_backups", {}).get(profile_key, {}),
        Path.home(),
    )
    selected, _ = QFileDialog.getOpenFileName(
        main_window, t('admin_full_restore_select_full_incremento_backup'), str(folder), t('admin_full_restore_zip_files_zip')
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
        t('admin_full_restore_restore_full_profile_backup'), category=t('admin_full_restore_backup'), detail=t('admin_full_restore_checking_backup')
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
            fail(t('admin_full_restore_backup_pre_check_failed_error', error=exc))
            return
        if not same_profile() or backup_running():
            fail(t('admin_full_restore_restore_stopped_because_the_profile_changed_or_a'), stage=stage)
            return
        prompt = QMessageBox(main_window)
        prompt.setWindowTitle(t('admin_full_restore_restore_full_backup'))
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setText(
            t('admin_full_restore_replace_the_current_anki_profile_profile_name_with', profile_name=profile_name)
        )
        mismatch = (
            ("\n" + t('admin_full_restore_the_backup_profile_name_differs_from_the_current'))
            if report.profile_mismatch else ""
        )
        missing_covers = (
            ("\n" + t('admin_full_restore_warning_count_pdf_epub_covers_referenced_by_cards', count=format_number(report.missing_cover_count)))
            if report.missing_cover_count else ""
        )
        prompt.setInformativeText(
            t('admin_full_restore_backup_profile_source_profile_cards_card_count_anki', source_profile=report.source_profile, card_count=format_number(report.card_count), media_count=format_number(report.media_count), file_count=format_number(report.profile_file_count), mismatch=mismatch, missing_covers=missing_covers)
        )
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        prompt.button(QMessageBox.StandardButton.Yes).setText(t("admin_yes"))
        prompt.button(QMessageBox.StandardButton.No).setText(t("admin_no"))
        prompt.setDefaultButton(QMessageBox.StandardButton.No)
        if prompt.exec() != QMessageBox.StandardButton.Yes:
            main_window.taskman.run_in_background(stage.cleanup, lambda _future: None)
            finish_activity(activity, detail=t('admin_full_restore_restore_cancelled_after_successful_pre_check'))
            global _restore_running
            _restore_running = False
            return

        update_activity(activity, detail=t('admin_full_restore_creating_safety_backup'))

        def safety_failed(error: Exception) -> None:
            fail(t('admin_full_restore_could_not_create_an_anki_safety_backup_error', error=error), stage=stage)

        def after_safety(_unused) -> None:
            try:
                if not same_profile() or backup_running():
                    raise RuntimeError(t('admin_full_restore_the_profile_changed_or_a_backup_started'))
                main_window.pm.profile["autoSync"] = False
                main_window.pm.profile["autoSyncMediaMinutes"] = 0
                main_window.pm.save()
                main_window.restoring_backup = True
                update_activity(activity, detail=t('admin_full_restore_closing_profile_for_restore'))
                main_window.unloadProfile(after_unload)
            except Exception as exc:
                restore_sync_preferences()
                main_window.restoring_backup = False
                try:
                    main_window.pm.save()
                except Exception:
                    pass
                fail(t('admin_full_restore_could_not_close_the_profile_for_restore_error', error=exc), stage=stage)

        def after_unload() -> None:
            main_window.restoring_backup = False
            if not same_profile():
                fail(t('admin_full_restore_restore_stopped_because_the_active_profile_changed'), stage=stage)
                return
            update_activity(activity, detail=t('admin_full_restore_replacing_profile_files'))
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
                        t('admin_full_restore_restore_stopped_with_an_incomplete_rollback_error_the', error=exc, profile_path=stage.profile_stage_dir, runtime_path=stage.runtime_stage_dir)
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
                        t('admin_full_restore_restore_could_not_replace_profile_files_error_the', error=exc, reopen_error=reopen_exc),
                        stage=stage,
                    )
                    return
                detail = t('admin_full_restore_restore_could_not_replace_profile_files_error', error=exc)
                if save_error is not None:
                    detail += t('admin_full_restore_automatic_sync_preference_could_not_be_saved_save', save_error=save_error)
                fail(detail, stage=stage)
                return

            def rollback_restore(reason: Exception) -> None:
                """Close a loaded collection before moving the prior files back."""
                update_activity(activity, detail=t('admin_full_restore_rolling_back_failed_restore'))

                def after_rollback(rollback_future) -> None:
                    try:
                        rollback_future.result()
                    except Exception as rollback_exc:
                        fail(
                            t('admin_full_restore_restore_failed_reason_automatic_rollback_also_failed_rollback', reason=reason, rollback_error=rollback_exc, profile_path=stage.profile_stage_dir, runtime_path=stage.runtime_stage_dir)
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
                            raise RuntimeError(t('admin_full_restore_the_previous_collection_could_not_reopen'))
                    except Exception as reopen_exc:
                        fail(
                            t('admin_full_restore_restore_failed_reason_prior_files_were_put_back', reason=reason, reopen_error=reopen_exc),
                            stage=stage,
                        )
                        return
                    if config_error is not None or preference_error is not None:
                        fail(
                            t('admin_full_restore_restore_failed_and_the_previous_profile_was_restored', error=config_error or preference_error),
                            stage=stage,
                        )
                        return
                    fail(
                        t('admin_full_restore_restore_failed_and_the_previous_profile_was_restored_65c4d6', reason=reason),
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
                            t('admin_full_restore_restore_failed_reason_the_restored_collection_could_not', reason=reason, close_error=close_exc, profile_path=stage.profile_stage_dir, runtime_path=stage.runtime_stage_dir)
                        )
                else:
                    do_rollback()

            try:
                restored_config = copy.deepcopy(stage.config)
                restored_config["automatic_backups"] = copy.deepcopy(
                    old_config.get("automatic_backups", {})
                )
                save_config(restored_config)
                update_activity(activity, detail=t('admin_full_restore_opening_restored_profile'))
                main_window.loadProfile()
                if main_window.col is None:
                    raise RuntimeError(t('admin_full_restore_anki_could_not_open_the_restored_collection'))
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
                        t('admin_full_restore_restore_succeeded_but_old_file_cleanup_failed_error', error=exc, profile_path=stage.profile_stage_dir, runtime_path=stage.runtime_stage_dir),
                    )
                    return
                finish_activity(activity, detail=t('admin_full_restore_profile_restored_automatic_sync_is_off'))
                tooltip(t('admin_full_restore_full_backup_restored_review_the_profile_before_syncing'))

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
        update_activity(activity, detail=t('admin_full_restore_staging_checked_backup'))
        stage = stage_backup(selected, report, collection, runtime)
        return report, stage

    main_window.taskman.run_in_background(check_and_stage, after_check)
