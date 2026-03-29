import json
import os
import zipfile

from aqt import mw, gui_hooks
from aqt.utils import showInfo, tooltip
from aqt.qt import (
    QAction,
    QMenu,
    QShortcut,
    QKeySequence,
    QTimer,
    Qt,
    qconnect,
)

from .frontend.stats_dialog import StatsDialog
from .backend.scheduler_config import load_scheduler_config
from .backend.pdf_manager import (
    PDF_NOTE_TYPE,
    get_page,
    get_zoom,
    get_read_page,
    extract_pdf_pages_text,
)
from .backend.video_manager import (
    VIDEO_NOTE_TYPE,
    LOCAL_VIDEO_FIELD,
    extract_video_id,
    add_video_card,
    download_and_compress_youtube_video,
)
from .backend.priority_manager import get_priority, set_priority, get_all_priorities
from .frontend.priority_dialog import PriorityDialog
from .frontend import timer_widget as _timer_mod
from .backend.topic_scheduler import on_topic_card_answered as _on_topic_card_answered
from .frontend.timer_widget import (
    build_timer_toolbar,
    on_timer_question_shown as _on_timer_question_shown,
    timer_on_card_answered as _timer_on_card_answered,
)
from .frontend import pdf_dock as _pdf_dock_mod
from .frontend import video_dock as _video_dock_mod
from .frontend import web_dock as _web_dock_mod
from .frontend import add_card_dock as _add_card_dock_mod
from .backend import review_time_tracker as _review_time_mod
from .backend.db import get_connection, replace_pdf_text_index, search_pdf_text_index
from .backend.session import (
    learnFunction,
    reset_session_counts,
    get_session_counts,
    get_session_times,
)
from .frontend.settings_dialog import IncrementoSettingsDialog, default_shortcuts
from .frontend.pdf_quick_jump import _PdfQuickJumpDialog
from .frontend.search_all import _SearchAllDialog

_ADDON_DIR = os.path.dirname(__file__)

_shortcut_actions: dict[str, object] = {}


def _register_shortcut_action(action_id: str, action_obj) -> None:
    _shortcut_actions[action_id] = action_obj


def _apply_shortcuts_from_config() -> None:
    cfg = mw.addonManager.getConfig(__name__) or {}
    defaults = default_shortcuts()
    user_shortcuts = cfg.get("shortcuts") or {}

    for action_id, action_obj in _shortcut_actions.items():
        shortcut_text = user_shortcuts.get(action_id, defaults.get(action_id, ""))
        seq = QKeySequence(shortcut_text) if shortcut_text else QKeySequence()
        if hasattr(action_obj, "setShortcut"):
            action_obj.setShortcut(seq)
        elif hasattr(action_obj, "setKey"):
            action_obj.setKey(seq)


mw.addonManager.setWebExports(__name__, r"user_files/.*")

# Last PDF card opened via the Quick Open dialog (used by Ctrl+L).
_last_opened_pdf_cid: int | None = None


# Wire add_card_dock callbacks to pdf_dock.
_pdf_dock_mod.register_add_card_callbacks(
    _add_card_dock_mod.open_add_card_dock,
    _add_card_dock_mod.fill_dock_field,
    _add_card_dock_mod.get_add_card_dock,
)
_pdf_dock_mod.register_pdf_view_callbacks(
    _review_time_mod.on_pdf_view_started,
    _review_time_mod.on_pdf_view_stopped,
)


def _on_js_message(handled, message, context) -> tuple:
    if not isinstance(message, str) or not message.startswith("incremento_"):
        return handled

    if message == "incremento_open_add_card":
        _add_card_dock_mod.open_add_card_dock()
        return (True, None)

    if message.startswith("incremento_fill_field:"):
        try:
            data = json.loads(message[len("incremento_fill_field:") :])
            _add_card_dock_mod.fill_dock_field(int(data["idx"]), data["text"])
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_card:"):
        try:
            note_id = int(message[len("incremento_open_card:") :])
            from aqt import dialogs

            def _browse(nid=note_id):
                b = dialogs.open("Browser", mw)
                b.search_for(f"nid:{nid}")

            QTimer.singleShot(0, _browse)
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_pdf:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                page = int(parts[2])
                card = mw.col.get_card(card_id)
                note = mw.col.get_note(card.nid)
                filename = note["PDF_Filename"]
                zoom = get_zoom(_ADDON_DIR, card_id)
                _pdf_dock_mod.show_pdf_in_dock(
                    card_id, filename, page, zoom, via_link=True
                )
            except Exception:
                pass
        return (True, None)

    if message.startswith("incremento_open_video:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                position = float(parts[2])
                card = mw.col.get_card(card_id)
                note = mw.col.get_note(card.nid)
                try:
                    url = note["YouTube_URL"]
                except Exception:
                    url = ""
                try:
                    local_video_file = note["Local_Video_File"]
                except Exception:
                    local_video_file = ""
                QTimer.singleShot(
                    0,
                    lambda: _video_dock_mod.show_video_in_dock(
                        card_id,
                        url,
                        position,
                        local_video_file,
                    ),
                )
            except Exception:
                pass
        return (True, None)

    return handled


gui_hooks.add_cards_did_add_note.append(_pdf_dock_mod.on_add_cards_did_add_note)

gui_hooks.reviewer_did_show_question.append(_on_timer_question_shown)
gui_hooks.reviewer_did_show_question.append(_review_time_mod.on_reviewer_question_shown)
gui_hooks.reviewer_did_show_question.append(_pdf_dock_mod.on_pdf_question_shown)
gui_hooks.reviewer_did_show_question.append(_video_dock_mod.on_video_question_shown)
gui_hooks.reviewer_did_show_question.append(_web_dock_mod.on_web_question_shown)
gui_hooks.reviewer_did_show_answer.append(_review_time_mod.on_reviewer_answer_shown)
gui_hooks.state_did_change.append(_review_time_mod.on_state_did_change)
gui_hooks.reviewer_did_answer_card.append(_timer_on_card_answered)
gui_hooks.reviewer_did_answer_card.append(_on_topic_card_answered)
gui_hooks.reviewer_will_end.append(_pdf_dock_mod.on_pdf_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_video_dock_mod.on_video_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_web_dock_mod.on_web_reviewer_will_end)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)


def _sync_pdf_note_type() -> None:
    """Update the PDF card template to the current code version on startup."""
    from .backend.pdf_manager import ensure_pdf_note_type

    def _run() -> None:
        try:
            ensure_pdf_note_type(mw.col)
        except Exception:
            pass

    mw.taskman.run_in_background(_run)


gui_hooks.main_window_did_init.append(_sync_pdf_note_type)
gui_hooks.main_window_did_init.append(_video_dock_mod.sync_video_note_type)
gui_hooks.main_window_did_init.append(_web_dock_mod.sync_web_note_type)


def _check_deps_first_run() -> None:
    """On first run after install, show the dependency setup dialog if anything is missing."""
    from .backend.deps import status
    config = mw.addonManager.getConfig(__name__) or {}
    if config.get("deps_notified"):
        return
    s = status()
    if s["pymupdf"] and s["tesseract"]:
        # Everything present — mark as notified and skip
        config["deps_notified"] = True
        mw.addonManager.writeConfig(__name__, config)
        return
    # Something is missing — show the setup dialog once
    config["deps_notified"] = True
    mw.addonManager.writeConfig(__name__, config)

    def _show():
        from .backend.deps import show_setup_dialog
        show_setup_dialog(mw)

    # Defer slightly so Anki finishes loading before the dialog appears
    from aqt.qt import QTimer
    QTimer.singleShot(1500, _show)


gui_hooks.main_window_did_init.append(_check_deps_first_run)


def _build_timer_toolbar() -> None:
    build_timer_toolbar(_timerToggleAction)


gui_hooks.main_window_did_init.append(_build_timer_toolbar)


# ── Option+P quick-jump to PDF ────────────────────────────────────────────────


def _open_pdf_quick_jump() -> None:
    global _last_opened_pdf_cid
    dlg = _PdfQuickJumpDialog(mw, addon_dir=_ADDON_DIR, last_opened_pdf_cid=_last_opened_pdf_cid)
    if not dlg.exec():
        return
    cid = dlg.selected_card_id
    if cid is None:
        return
    try:
        _open_pdf_card(cid)
    except Exception as e:
        showInfo(f"Could not open PDF:\n{e}")


def _open_pdf_card(
    card_id: int, page: int | None = None, search_query: str = ""
) -> None:
    global _last_opened_pdf_cid
    card = mw.col.get_card(card_id)
    note = mw.col.get_note(card.nid)
    filename = note["PDF_Filename"]
    open_page = page if page is not None else get_page(_ADDON_DIR, card_id)
    zoom = get_zoom(_ADDON_DIR, card_id)
    read_page = get_read_page(_ADDON_DIR, card_id)
    _last_opened_pdf_cid = card_id
    _pdf_dock_mod.show_pdf_in_dock(
        card_id,
        filename,
        open_page,
        zoom,
        read_page=read_page,
        search_query=search_query,
    )


def _open_search_all() -> None:
    _SearchAllDialog(mw, addon_dir=_ADDON_DIR, open_pdf_card=_open_pdf_card).exec()


def _trigger_pdf_viewer_action(action: str) -> None:
    _pdf_dock_mod.trigger_viewer_action(action)


_pdf_jump_shortcut = QShortcut(QKeySequence("Ctrl+Alt+P"), mw)
_pdf_jump_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_pdf_jump_shortcut.activated, _open_pdf_quick_jump)
_register_shortcut_action("quick_open_pdf", _pdf_jump_shortcut)


def showStatsFunction() -> None:
    base_time = get_session_times() or {"type": {}, "tags": {}}
    runtime_time = _review_time_mod.get_runtime_session_time() or {
        "type": {},
        "tags": {},
    }
    merged_time = {"type": {}, "tags": {}}
    for key in ("type", "tags"):
        for src in (base_time.get(key, {}), runtime_time.get(key, {})):
            for name, value in src.items():
                merged_time[key][name] = merged_time[key].get(name, 0.0) + float(value)

    cfg = load_scheduler_config()
    dlg = StatsDialog(
        addon_dir=os.path.dirname(__file__),
        session_counts=get_session_counts(),
        session_time=merged_time,
        day_end_time=cfg.day_end_time,
        parent=mw,
    )
    dlg.exec()


def addPdfFunction() -> None:
    from .frontend.pdf_dialog import AddPdfDialog

    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    dlg = AddPdfDialog(addon_dir=_ADDON_DIR, deck_names=deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return

    created = dlg.created
    failed = dlg.failed
    deck = dlg.deck_name

    if not created and not failed:
        return

    def _fmt_size(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b // 1024} KB"
        except OSError:
            return "?"

    if created:
        lines = [f"Added {len(created)} PDF card(s) → {deck}\n"]
        for path, title in created:
            lines.append(f"• {title}")
            lines.append(f"  {os.path.basename(path)}  ·  {_fmt_size(path)}")
        if failed:
            lines.append(f"\nFailed: {len(failed)}")
            for path, msg in failed[:10]:
                lines.append(f"• {os.path.basename(path)}: {msg}")
            if len(failed) > 10:
                lines.append(f"  …and {len(failed) - 10} more")
        showInfo("\n".join(lines))
    else:
        failed_lines = "\n".join(
            f"• {os.path.basename(p)}: {msg}" for p, msg in failed[:10]
        )
        extra = f"\n…and {len(failed) - 10} more" if len(failed) > 10 else ""
        showInfo(f"All imports failed ({len(failed)}):\n\n{failed_lines}{extra}")


def exportFunction() -> None:
    import datetime
    from aqt.qt import QFileDialog
    from .backend.db import (
        get_connection,
        DB_NAME,
        export_priorities_json,
        export_pdf_progress_json,
        export_highlights_json,
        export_stats_json,
    )

    today = datetime.date.today().isoformat()
    default_name = os.path.expanduser(f"~/incremento_export_{today}.zip")

    path, _ = QFileDialog.getSaveFileName(
        mw,
        "Export Incremento User Data",
        default_name,
        "ZIP files (*.zip)",
    )
    if not path:
        return

    user_files_dir = os.path.join(_ADDON_DIR, "user_files")
    from .backend.pdf_manager import get_pdf_dir
    pdf_dir = get_pdf_dir()

    # Gather PDF filenames from all Incremento PDF notes
    pdf_filenames = []
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
        for nid in note_ids:
            try:
                fname = mw.col.get_note(nid)["PDF_Filename"]
                if fname:
                    pdf_filenames.append(fname)
            except Exception:
                pass
    except Exception:
        pass

    try:
        # Snapshot counts before opening the ZIP
        conn = get_connection(_ADDON_DIR)
        priority_count = conn.execute("SELECT COUNT(*) FROM priorities").fetchone()[0]

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            # ── data/incremento.db — main SQLite database (direct restore) ──
            db_path = os.path.join(user_files_dir, DB_NAME)
            if os.path.exists(db_path):
                zf.write(db_path, f"data/{DB_NAME}")

            # ── data/*.json — human-readable copies of each dataset ──────────
            zf.writestr("data/priorities.json", export_priorities_json(_ADDON_DIR))
            zf.writestr("data/pdf_progress.json", export_pdf_progress_json(_ADDON_DIR))
            zf.writestr("data/highlights.json", export_highlights_json(_ADDON_DIR))
            zf.writestr("data/stats.json", export_stats_json(_ADDON_DIR))

            # ── config.json — scheduler settings ─────────────────────────────
            config = mw.addonManager.getConfig(__name__) or {}
            zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))

            # ── pdfs/ — PDF media files ───────────────────────────────────────
            pdf_count = 0
            pdf_missing = []
            for fname in pdf_filenames:
                pdf_path = os.path.join(pdf_dir, fname)
                if os.path.exists(pdf_path):
                    zf.write(pdf_path, f"pdfs/{fname}")
                    pdf_count += 1
                else:
                    pdf_missing.append(fname)

            # ── manifest.json — export metadata ──────────────────────────────
            manifest = {
                "export_date": today,
                "addon": "Incremento",
                "anki_version": getattr(mw.pm, "meta", {}).get(
                    "ankiVersion", "unknown"
                ),
                "counts": {
                    "pdf_notes": len(pdf_filenames),
                    "pdfs_exported": pdf_count,
                    "pdfs_missing": len(pdf_missing),
                    "priorities": priority_count,
                },
                "files": {
                    f"data/{DB_NAME}": "All user data (SQLite, for direct restore)",
                    "data/priorities.json": "Card priorities (human-readable copy)",
                    "data/pdf_progress.json": "PDF reading positions and zoom levels",
                    "data/highlights.json": "PDF text highlights",
                    "data/stats.json": "Session, daily and lifetime statistics",
                    "config.json": "Scheduler and session settings",
                    "pdfs/": "PDF files referenced by Incremento cards",
                },
            }
            if pdf_missing:
                manifest["pdfs_missing_filenames"] = pdf_missing

            zf.writestr(
                "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
            )

        # ── Success dialog ────────────────────────────────────────────────────
        missing_note = (
            f"\n\n  ⚠ {len(pdf_missing)} PDF file(s) not found in media folder"
            if pdf_missing
            else ""
        )
        showInfo(
            f"Export complete.\n\n"
            f"  • {pdf_count} of {len(pdf_filenames)} PDF file(s)\n"
            f"  • {priority_count} card priorit{'y' if priority_count == 1 else 'ies'}\n"
            f"  • Statistics, highlights, progress, config"
            f"{missing_note}\n\n"
            f"Saved to:\n{path}"
        )
    except Exception as e:
        showInfo(f"Export failed:\n{e}")


def _extract_card() -> None:
    """Option+X: grab the reviewer's selected text, open the extract-card dialog."""
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        return
    mw.reviewer.web.page().runJavaScript(
        "window.getSelection()?.toString() || ''",
        lambda text: _on_extract_selection(text.strip(), card),
    )


def _on_extract_selection(selected_text: str, parent_card) -> None:
    from .frontend.extract_card_dialog import ExtractCardDialog

    # Build note-type list
    notetypes = [
        {"name": m["name"], "fields": [f["name"] for f in m["flds"]]}
        for m in mw.col.models.all()
    ]

    # Build deck list
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]

    # Defaults: same note type and deck as the parent card
    parent_note = parent_card.note()
    default_notetype = parent_note.note_type()["name"]
    parent_deck = mw.col.decks.get(parent_card.did)
    default_deck = parent_deck["name"] if parent_deck else ""

    # Parent card link (appended to field 0 of the new card)
    parent_label = (
        parent_note.fields[0][:60].strip()
        if parent_note.fields
        else f"Card {parent_card.id}"
    )
    parent_link = (
        f'<a href="#" onclick="pycmd(\'incremento_open_card:{parent_card.id}\')" '
        f'style="font-size:0.85em;color:#888;">↩ {parent_label}</a>'
    )

    dlg = ExtractCardDialog(
        selected_text=selected_text,
        parent_link_html=parent_link,
        notetypes=notetypes,
        deck_names=deck_names,
        default_notetype=default_notetype,
        default_deck=default_deck,
        parent=mw,
    )
    if not dlg.exec():
        return

    try:
        model = mw.col.models.by_name(dlg.notetype_name)
        if model is None:
            showInfo(f"Note type '{dlg.notetype_name}' not found.")
            return
        deck = mw.col.decks.by_name(dlg.deck_name)
        deck_id = (
            mw.col.decks.add_normal_deck_with_name(dlg.deck_name).id
            if deck is None
            else deck["id"]
        )
        note = mw.col.new_note(model)
        for fname, val in dlg.field_values.items():
            if fname in note:
                note[fname] = val
        mw.col.add_note(note, deck_id)
        showInfo(f"Card created in '{dlg.deck_name}'.")
    except Exception as e:
        showInfo(f"Failed to create card:\n{e}")


def _open_priority_dialog() -> None:
    """Open the priority assignment dialog for the currently reviewed card."""
    from .backend.topic_scheduler import is_topic_card
    from .backend.db import get_topic_schedule, set_topic_schedule

    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        showInfo("No card is currently being reviewed.")
        return

    current = get_priority(_ADDON_DIR, card.id)
    note = card.note()
    label_text = note.fields[0][:80].strip() if note.fields else ""

    a_factor = None
    interval = None
    if is_topic_card(card):
        a_factor, interval = get_topic_schedule(_ADDON_DIR, card.id)

    dlg = PriorityDialog(
        current_priority=current,
        card_label=label_text,
        current_a_factor=a_factor,
        current_interval=interval,
        parent=mw,
    )
    if dlg.exec():
        set_priority(_ADDON_DIR, card.id, dlg.priority)
        msg = f"Priority set to {dlg.priority:.0f}"
        if dlg.a_factor is not None:
            set_topic_schedule(_ADDON_DIR, card.id, dlg.a_factor, interval or 1)
            msg += f"  ·  A-Factor {dlg.a_factor:.3f}"
        tooltip(msg)


_priority_shortcut = QShortcut(QKeySequence("Alt+P"), mw)
_priority_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_priority_shortcut.activated, _open_priority_dialog)
_register_shortcut_action("set_priority", _priority_shortcut)

_extract_shortcut = QShortcut(QKeySequence("Alt+X"), mw)
_extract_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_extract_shortcut.activated, _extract_card)
_register_shortcut_action("extract_card", _extract_shortcut)

_pdf_prev_page_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Left"), mw)
_pdf_prev_page_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_prev_page_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("prev_page"),
)
_register_shortcut_action("pdf_prev_page", _pdf_prev_page_shortcut)

_pdf_next_page_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Right"), mw)
_pdf_next_page_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_next_page_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("next_page"),
)
_register_shortcut_action("pdf_next_page", _pdf_next_page_shortcut)

_pdf_zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+Alt+-"), mw)
_pdf_zoom_out_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_zoom_out_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("zoom_out"),
)
_register_shortcut_action("pdf_zoom_out", _pdf_zoom_out_shortcut)

_pdf_zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+Alt+="), mw)
_pdf_zoom_in_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_zoom_in_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("zoom_in"),
)
_register_shortcut_action("pdf_zoom_in", _pdf_zoom_in_shortcut)

_pdf_mark_read_shortcut = QShortcut(QKeySequence("Ctrl+Alt+M"), mw)
_pdf_mark_read_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(
    _pdf_mark_read_shortcut.activated,
    lambda: _trigger_pdf_viewer_action("mark_read"),
)
_register_shortcut_action("pdf_mark_read", _pdf_mark_read_shortcut)


def addVideoFunction() -> None:
    """Incremento -> Add Content -> YouTube Video"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .frontend.add_video_dialog import AddVideoDialog

    dlg = AddVideoDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return
    url = dlg.youtube_url
    if not url:
        showInfo("Please enter a YouTube URL.")
        return
    if not extract_video_id(url):
        showInfo("Could not find a valid YouTube video ID in that URL.")
        return
    title = dlg.title or url
    deck_name = dlg.deck_name
    tags = dlg.tags

    def _add_url_card(local_relpath: str = "") -> bool:
        try:
            add_video_card(
                mw.col,
                url,
                title,
                deck_name=deck_name,
                tags=tags,
                local_video_file=local_relpath,
            )
            mw.col.reset()
            if local_relpath:
                tooltip(f"Video card '{title}' added to {deck_name} (local copy ready).")
            else:
                tooltip(f"Video card '{title}' added to {deck_name}.")
            return True
        except Exception as e:
            showInfo(f"Failed to add video card:\n{e}")
            return False

    if not dlg.download_locally:
        _add_url_card()
        return

    try:
        mw.progress.start(
            label="Downloading and compressing video…",
            immediate=True,
            value=0,
            max=100,
        )
    except TypeError:
        mw.progress.start(label="Downloading and compressing video…", immediate=True)

    def _progress_main(percent: int, label: str) -> None:
        try:
            mw.progress.update(label=label, value=int(percent), max=100)
        except TypeError:
            mw.progress.update(label=label)

    def _progress_cb(percent: int, label: str) -> None:
        mw.taskman.run_on_main(lambda p=percent, l=label: _progress_main(p, l))

    def _task():
        return download_and_compress_youtube_video(
            _ADDON_DIR,
            url,
            progress_cb=_progress_cb,
        )

    def _on_done(fut) -> None:
        mw.progress.finish()
        try:
            local_relpath = fut.result()
        except Exception as e:
            showInfo(f"Video download/compression failed:\n{e}")
            return
        _add_url_card(local_relpath=local_relpath)

    mw.taskman.run_in_background(_task, _on_done)


def addWebpageFunction() -> None:
    from .frontend.webpage_dialog import WebpageToPdfDialog
    from .backend.pdf_manager import add_pdf_card

    dlg = WebpageToPdfDialog(mw)
    if not dlg.exec():
        return
    try:
        add_pdf_card(
            _ADDON_DIR,
            mw.col,
            dlg.pdf_path,
            dlg.title_text,
            tags=dlg.tags_to_apply,
        )
        showInfo(f'PDF card "{dlg.title_text}" added to the Topics deck.')
    except Exception as e:
        showInfo(f"Failed to import webpage as PDF:\n{e}")


def reindexPdfTextFunction() -> None:
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
    except Exception as e:
        showInfo(f"Could not list PDF cards:\n{e}")
        return

    if not note_ids:
        showInfo("No PDF cards found to reindex.")
        return

    indexed = 0
    skipped = 0  # file missing or no text
    failed: list[tuple[str, str]] = []
    from .backend.pdf_manager import get_pdf_dir
    pdf_dir = get_pdf_dir()

    mw.progress.start(label="Reindexing PDF text…", immediate=True)
    try:
        total = len(note_ids)
        for i, nid in enumerate(note_ids, start=1):
            try:
                mw.progress.update(label=f"({i}/{total}) Reindexing PDF text…")
            except Exception:
                pass

            try:
                note = mw.col.get_note(nid)
                filename = note["PDF_Filename"]
                pdf_path = os.path.join(pdf_dir, filename)
                if not os.path.exists(pdf_path):
                    skipped += 1
                    continue
                page_texts = extract_pdf_pages_text(pdf_path)
                if not any(page_texts):
                    skipped += 1
                    continue
                for cid in mw.col.find_cards(f"nid:{nid}"):
                    replace_pdf_text_index(_ADDON_DIR, cid, page_texts)
                indexed += 1
            except Exception as e:
                failed.append((str(nid), str(e)))
    finally:
        mw.progress.finish()

    lines = [f"PDF text reindex complete.\n"]
    lines.append(f"Indexed:  {indexed}")
    lines.append(f"Skipped (no text / missing file):  {skipped}")
    if failed:
        lines.append(f"Errors:   {len(failed)}")
        for nid_str, msg in failed[:10]:
            lines.append(f"  • nid:{nid_str}: {msg}")
        if len(failed) > 10:
            lines.append(f"  …and {len(failed) - 10} more")
    showInfo("\n".join(lines))


def cleanupOrphanPdfsFunction() -> None:
    """Delete PDF files in user_files/pdfs/ that no card references."""
    from .backend.pdf_manager import get_pdf_dir

    pdf_dir = get_pdf_dir()

    # All files currently on disk
    try:
        disk_files = {
            f for f in os.listdir(pdf_dir)
            if f.lower().endswith(".pdf")
        }
    except OSError as e:
        showInfo(f"Could not read PDF directory:\n{e}")
        return

    if not disk_files:
        showInfo("No PDF files found in user_files/pdfs/.")
        return

    # All filenames referenced by an Incremento PDF note
    try:
        note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}"')
        referenced = set()
        for nid in note_ids:
            note = mw.col.get_note(nid)
            fname = note["PDF_Filename"].strip()
            if fname:
                referenced.add(fname)
    except Exception as e:
        showInfo(f"Could not query PDF cards:\n{e}")
        return

    orphans = sorted(disk_files - referenced)

    if not orphans:
        showInfo(
            f"No orphaned PDFs found.\n\n"
            f"{len(disk_files)} file(s) on disk, all referenced by a card."
        )
        return

    def _fmt_size(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b // 1024} KB"
        except OSError:
            return "?"

    lines = [f"Found {len(orphans)} orphaned PDF(s) (no card references them):\n"]
    total_bytes = 0
    for fname in orphans:
        fpath = os.path.join(pdf_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
        lines.append(f"• {fname}  ({_fmt_size(fpath)})")
    total_str = f"{total_bytes / 1_048_576:.1f} MB" if total_bytes >= 1_048_576 else f"{total_bytes // 1024} KB"
    lines.append(f"\nTotal: {total_str}")
    lines.append("\nDelete these files?")

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title="Clean Up Orphaned PDFs"):
        return

    deleted = 0
    errors: list[str] = []
    for fname in orphans:
        fpath = os.path.join(pdf_dir, fname)
        try:
            os.remove(fpath)
            deleted += 1
        except OSError as e:
            errors.append(f"• {fname}: {e}")

    if not errors:
        showInfo(f"Deleted {deleted} orphaned PDF file(s).\nRecovered {total_str}.")
    else:
        showInfo(
            f"Deleted {deleted} of {len(orphans)} file(s).\n\nErrors:\n" + "\n".join(errors)
        )


def cleanupOrphanVideosFunction() -> None:
    """Delete local videos in user_files/videos/ that no video card references."""
    videos_dir = os.path.join(_ADDON_DIR, "user_files", "videos")
    if not os.path.isdir(videos_dir):
        showInfo("No local videos found in user_files/videos/.")
        return

    try:
        disk_files = {
            f
            for f in os.listdir(videos_dir)
            if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v"))
            and os.path.isfile(os.path.join(videos_dir, f))
        }
    except OSError as e:
        showInfo(f"Could not read video directory:\n{e}")
        return

    if not disk_files:
        showInfo("No local videos found in user_files/videos/.")
        return

    try:
        note_ids = mw.col.find_notes(f'note:"{VIDEO_NOTE_TYPE}"')
        referenced = set()
        for nid in note_ids:
            note = mw.col.get_note(nid)
            try:
                rel = (note[LOCAL_VIDEO_FIELD] or "").strip()
            except Exception:
                rel = ""
            if not rel:
                continue
            basename = os.path.basename(rel.replace("\\", "/"))
            if basename:
                referenced.add(basename)
    except Exception as e:
        showInfo(f"Could not query video cards:\n{e}")
        return

    orphans = sorted(disk_files - referenced)
    if not orphans:
        showInfo(
            f"No orphaned local videos found.\n\n"
            f"{len(disk_files)} file(s) on disk, all referenced by a card."
        )
        return

    def _fmt_size(path: str) -> str:
        try:
            b = os.path.getsize(path)
            return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b // 1024} KB"
        except OSError:
            return "?"

    total_bytes = 0
    lines = [f"Found {len(orphans)} orphaned local video file(s):\n"]
    for fname in orphans:
        fpath = os.path.join(videos_dir, fname)
        try:
            total_bytes += os.path.getsize(fpath)
        except OSError:
            pass
        lines.append(f"• {fname}  ({_fmt_size(fpath)})")
    total_str = (
        f"{total_bytes / 1_048_576:.1f} MB"
        if total_bytes >= 1_048_576
        else f"{total_bytes // 1024} KB"
    )
    lines.append(f"\nTotal: {total_str}")
    lines.append("\nDelete these files?")

    from aqt.utils import askUser
    if not askUser("\n".join(lines), title="Clean Up Orphaned Videos"):
        return

    deleted = 0
    errors: list[str] = []
    for fname in orphans:
        fpath = os.path.join(videos_dir, fname)
        try:
            os.remove(fpath)
            deleted += 1
        except OSError as e:
            errors.append(f"• {fname}: {e}")

    if not errors:
        showInfo(f"Deleted {deleted} orphaned video file(s).\nRecovered {total_str}.")
    else:
        showInfo(
            f"Deleted {deleted} of {len(orphans)} file(s).\n\nErrors:\n" + "\n".join(errors)
        )


def openSettingsFunction() -> None:
    cfg = mw.addonManager.getConfig(__name__) or {}
    dlg = IncrementoSettingsDialog(cfg.get("shortcuts") or {}, parent=mw)
    if not dlg.exec():
        return

    cfg["shortcuts"] = dlg.shortcuts_map
    mw.addonManager.writeConfig(__name__, cfg)
    _apply_shortcuts_from_config()
    tooltip("Incremento shortcuts updated.")


def _ensure_settings_menu_action() -> None:
    for act in _menu.actions():
        if act.text() == "Settings":
            return

    action = QAction("Settings", mw)
    action.setMenuRole(QAction.MenuRole.NoRole)
    qconnect(action.triggered, openSettingsFunction)

    inserted = False
    for act in _menu.actions():
        if act.isSeparator():
            _menu.insertAction(act, action)
            inserted = True
            break
    if not inserted:
        _menu.addAction(action)

    _register_shortcut_action("open_settings", action)
    _apply_shortcuts_from_config()


# ── Incremento top-level menu ─────────────────────────────────────────────────

_menu = QMenu("Incremento", mw)
mw.menuBar().addMenu(_menu)

_startAction = QAction("Start Incremental Learning", mw)
qconnect(_startAction.triggered, learnFunction)
_menu.addAction(_startAction)
_register_shortcut_action("start_learning", _startAction)

_settingsAction = QAction("Settings", mw)
_settingsAction.setMenuRole(QAction.MenuRole.NoRole)
qconnect(_settingsAction.triggered, openSettingsFunction)
_menu.addAction(_settingsAction)
_register_shortcut_action("open_settings", _settingsAction)

_menu.addSeparator()

_addContentMenu = QMenu("Add Content", mw)
_menu.addMenu(_addContentMenu)

_addPdfAction = QAction("Add PDF", mw)
qconnect(_addPdfAction.triggered, addPdfFunction)
_addContentMenu.addAction(_addPdfAction)
_register_shortcut_action("add_pdf", _addPdfAction)

_addWebpageAction = QAction("Webpage to PDF", mw)
qconnect(_addWebpageAction.triggered, addWebpageFunction)
_addContentMenu.addAction(_addWebpageAction)
_register_shortcut_action("webpage_to_pdf", _addWebpageAction)

_addVideoAction = QAction("YouTube Video", mw)
qconnect(_addVideoAction.triggered, addVideoFunction)
_addContentMenu.addAction(_addVideoAction)
_register_shortcut_action("youtube_video", _addVideoAction)

_addWebAction = QAction("Web Page", mw)
qconnect(_addWebAction.triggered, _web_dock_mod.add_web_function)
_addContentMenu.addAction(_addWebAction)
_register_shortcut_action("add_web_page", _addWebAction)

_menu.addSeparator()

_timerToggleAction = QAction("Show Focus Timer", mw)
_timerToggleAction.setCheckable(True)
_timerToggleAction.setChecked(True)  # default; corrected by _build_timer_toolbar


def _on_timer_toggle(checked: bool) -> None:
    if _timer_mod._timer_toolbar is not None:
        _timer_mod._timer_toolbar.setVisible(checked)
    cfg = mw.addonManager.getConfig(__name__) or {}
    cfg["show_timer"] = checked
    mw.addonManager.writeConfig(__name__, cfg)


qconnect(_timerToggleAction.triggered, _on_timer_toggle)
_menu.addAction(_timerToggleAction)
_register_shortcut_action("toggle_focus_timer", _timerToggleAction)

_menu.addSeparator()

_utilsMenu = QMenu("Utils", mw)
_menu.addMenu(_utilsMenu)

def _check_deps_manual() -> None:
    from .backend.deps import show_setup_dialog
    show_setup_dialog(mw, force=True)


_checkDepsAction = QAction("Check Dependencies…", mw)
qconnect(_checkDepsAction.triggered, _check_deps_manual)
_utilsMenu.addAction(_checkDepsAction)

_utilsMenu.addSeparator()

_reindexPdfTextAction = QAction("Reindex PDF Text (Existing Cards)", mw)
qconnect(_reindexPdfTextAction.triggered, reindexPdfTextFunction)
_utilsMenu.addAction(_reindexPdfTextAction)

_cleanupOrphanPdfsAction = QAction("Clean Up Orphaned PDF Files…", mw)
qconnect(_cleanupOrphanPdfsAction.triggered, cleanupOrphanPdfsFunction)
_utilsMenu.addAction(_cleanupOrphanPdfsAction)

_cleanupOrphanVideosAction = QAction("Clean Up Orphaned Video Files…", mw)
qconnect(_cleanupOrphanVideosAction.triggered, cleanupOrphanVideosFunction)
_utilsMenu.addAction(_cleanupOrphanVideosAction)

_statsAction = QAction("Statistics", mw)
qconnect(_statsAction.triggered, showStatsFunction)
_menu.addAction(_statsAction)
_register_shortcut_action("statistics", _statsAction)

_searchAllAction = QAction("Search ALL", mw)
qconnect(_searchAllAction.triggered, _open_search_all)
_menu.addAction(_searchAllAction)
_register_shortcut_action("search_all", _searchAllAction)

_exportAction = QAction("Export User Data", mw)
qconnect(_exportAction.triggered, exportFunction)
_menu.addAction(_exportAction)
_register_shortcut_action("export_user_data", _exportAction)

_apply_shortcuts_from_config()
_ensure_settings_menu_action()
