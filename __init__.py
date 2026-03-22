import copy
import json
import os
import sys
import types

from aqt import mw, gui_hooks
from aqt.utils import showInfo
from aqt.qt import (QAction, QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
                     QPushButton, QDockWidget, QLabel, QWidget,
                     QShortcut, QKeySequence, QApplication,
                     qconnect, QTimer, Qt)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import QUrl
from anki.cards import CardId

# Allow utils/scheduler.py to do `import cards` as a plain import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from .utils.scheduler import get_card_from_scheduler, NO_TAGS_KEY
from .utils.statistics import StatsManager
from .utils.learn_dialog import SchedulerConfigDialog
from .utils.scheduler_config import load_scheduler_config
from .utils.stats_dialog import StatsDialog
from .utils.pdf_manager import PDF_NOTE_TYPE, get_page, set_page, get_zoom, set_zoom

INCREMENTO_DECK = "Incremento Session"
_ADDON_DIR = os.path.dirname(__file__)

mw.addonManager.setWebExports(__name__, r"user_files/.*")

# Most-recent session counts — updated after each learnFunction picking loop.
# Passed to StatsDialog so the "This Session" view reflects the last session.
_session_counts: dict = {"type": {}, "tags": {}, "mode": {}}


def _reset_session_counts() -> None:
    global _session_counts
    _session_counts = {"type": {}, "tags": {}, "mode": {}}


def learnFunction() -> None:
    config = mw.addonManager.getConfig(__name__) or {}

    dlg = SchedulerConfigDialog(mw, on_clear_session=_reset_session_counts)
    if not dlg.exec():
        return

    dlg.save_config()
    cfg = dlg.to_config()
    target_count = cfg.session_card_count

    stats = StatsManager(os.path.dirname(__file__), day_end_time=cfg.day_end_time)

    selected_ids: list[CardId] = []
    added_to_filtered: set[CardId] = set()
    # Metadata stored at pick-time; daily/lifetime are recorded on actual review.
    _picked_meta: dict[int, dict] = {}

    def _pick(use_tags: bool, tag_weights: dict,
              force_card_type: str | None = None,
              force_mode: str | None = None) -> bool:
        """Attempt one card pick. Returns False when no card is available."""
        counts = stats.counts_for(cfg.scheduler_scope)
        result = get_card_from_scheduler(
            counts=counts,
            topics_rate=cfg.topics_rate,
            random_rate=cfg.random_rate,
            use_tags=use_tags,
            tag_weights=tag_weights,
            exclude_ids=added_to_filtered,
            force_card_type=force_card_type,
            force_mode=force_mode,
            topics_filter=cfg.topics_filter,
            items_filter=cfg.items_filter,
            ready_filter=cfg.ready_filter,
        )
        if result.card is None:
            return False
        counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
        counts["mode"][result.mode] = counts["mode"].get(result.mode, 0) + 1
        if result.tag:
            counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1
        # Do NOT call stats.record() here — that would write picks to daily/lifetime.
        # Recording to daily/lifetime is deferred to the reviewer_did_answer_card hook
        # so that only actually reviewed cards count toward those scopes.
        _picked_meta[result.card] = {
            "card_type": result.card_type,
            "tag":       result.tag,
            "mode":      result.mode,
        }
        added_to_filtered.add(result.card)
        selected_ids.append(result.card)
        return True

    if cfg.enforce_priority:
        # Hard mode — Phase 1 exhausts the leading dimension's quota sequentially.
        p1 = cfg.priority_order[0] if cfg.priority_order else "tags"

        if p1 == "tags" and cfg.use_tags:
            # Loop per-tag in descending weight order.
            ordered = sorted(cfg.tag_weights.items(), key=lambda x: x[1], reverse=True)
            for tag, weight in ordered:
                tag_target = round(weight * target_count)
                tag_picked = 0
                for _ in range(tag_target * 3):
                    if tag_picked >= tag_target or len(selected_ids) >= target_count:
                        break
                    if not _pick(use_tags=True, tag_weights={tag: 1.0}):
                        break
                    tag_picked += 1

        elif p1 == "type":
            # Loop per-type: topics quota first, then items quota.
            topics_target = round(cfg.topics_rate * target_count)
            items_target = target_count - topics_target
            for forced_type, type_target in [("topics", topics_target), ("items", items_target)]:
                type_picked = 0
                for _ in range(type_target * 3):
                    if type_picked >= type_target or len(selected_ids) >= target_count:
                        break
                    if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights,
                                 force_card_type=forced_type):
                        break
                    type_picked += 1

        elif p1 == "mode":
            # Loop per-mode: priority-ordered cards first, then random.
            priority_target = round((1 - cfg.random_rate) * target_count)
            random_target = target_count - priority_target
            for forced_mode, mode_target in [("priority", priority_target), ("random", random_target)]:
                mode_picked = 0
                for _ in range(mode_target * 3):
                    if mode_picked >= mode_target or len(selected_ids) >= target_count:
                        break
                    if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights,
                                 force_mode=forced_mode):
                        break
                    mode_picked += 1

        # Phase 2 — fill remaining slots.
        run_phase2 = (cfg.include_rest or not cfg.use_tags) if p1 == "tags" else True
        if run_phase2:
            for _ in range(target_count * 3):
                if len(selected_ids) >= target_count:
                    break
                if not _pick(use_tags=False, tag_weights={}):
                    break

    else:
        # Soft mode — all dimensions handled by soft_pick (debt-based stochastic).
        # Tags, type and mode are interleaved; weights are honoured on average, not enforced.
        for _ in range(target_count * 3):
            if len(selected_ids) >= target_count:
                break
            if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights):
                break
        # If tags were used and include_rest is on, top up with any remaining cards.
        if cfg.use_tags and cfg.include_rest and len(selected_ids) < target_count:
            for _ in range(target_count * 3):
                if len(selected_ids) >= target_count:
                    break
                if not _pick(use_tags=False, tag_weights={}):
                    break

    # Snapshot session counts so the statistics dialog can show them later.
    global _session_counts
    _session_counts = copy.deepcopy(stats.session)

    if not selected_ids:
        showInfo("No cards available to study.")
        return

    # DEBUG: show scheduled card order before building the filtered deck
    if cfg.show_debug:
        _debug_dlg = QDialog(mw)
        _debug_dlg.setWindowTitle(f"DEBUG — Scheduled order ({len(selected_ids)} cards)")
        _debug_dlg.resize(700, 500)
        _debug_layout = QVBoxLayout(_debug_dlg)
        _debug_txt = QTextEdit()
        _debug_txt.setReadOnly(True)
        _debug_txt.setFontFamily("Courier")
        _debug_lines = ["#    type     mode       tag                  first field"]
        _debug_lines.append("-" * 80)
        for _i, _cid in enumerate(selected_ids):
            _meta = _picked_meta.get(_cid, {})
            _card = mw.col.get_card(_cid)
            _note = mw.col.get_note(_card.nid)
            _field = (_note.fields[0][:55].replace("\n", " ")) if _note.fields else str(_cid)
            _debug_lines.append(
                f"{_i+1:3}.  {_meta.get('card_type','?'):7}  {_meta.get('mode','?'):9}  "
                f"{(_meta.get('tag') or 'no-tag'):20} {_field}"
            )
        _debug_txt.setPlainText("\n".join(_debug_lines))
        _debug_layout.addWidget(_debug_txt)
        _debug_btn = QPushButton("Continue")
        _debug_btn.clicked.connect(_debug_dlg.accept)
        _debug_layout.addWidget(_debug_btn)
        _debug_dlg.exec()

    search = " OR ".join(f"cid:{cid}" for cid in selected_ids)

    # Get or create the filtered deck
    existing = mw.col.decks.by_name(INCREMENTO_DECK)
    if existing:
        if not existing.get("dyn"):
            showInfo(f"'{INCREMENTO_DECK}' is a normal deck. Delete or rename it first.")
            return
        did = existing["id"]
        mw.col.sched.empty_filtered_deck(did)
    else:
        did = mw.col.decks.new_filtered(INCREMENTO_DECK)

    # Configure via protobuf API (Anki 2.1.45+)
    fdu = mw.col.sched.get_or_create_filtered_deck(did)
    fdu.config.reschedule = True
    del fdu.config.search_terms[:]
    # Always a single SearchTerm — Anki only processes the first 2 SearchTerms
    # so N-per-card terms silently truncate. order=0 (default) when preserving
    # order (due values get stamped post-rebuild anyway); order=1 (RANDOM) otherwise.
    fdu.config.search_terms.add(
        search=search,
        limit=len(selected_ids),
        order=0 if cfg.preserve_order else 1,
    )
    op = mw.col.sched.add_or_update_filtered_deck(fdu)

    mw.col.sched.rebuild_filtered_deck(op.id)

    if cfg.preserve_order:
        # odue is already saved by rebuild — original scheduling is safe.
        # Stamp due = position so the scheduler presents cards in selected_ids order.
        for i, cid in enumerate(selected_ids):
            card = mw.col.get_card(cid)
            card.due = i
            mw.col.update_card(card)
    mw.col.decks.select(op.id)

    # Hook: record each card to daily/lifetime the first time it is answered.
    # This ensures only actually reviewed cards count — not just scheduled ones.
    _reviewed_ids: set[int] = set()

    def _on_card_answered(reviewer, card, ease: int) -> None:
        cid = card.id
        if cid not in _picked_meta or cid in _reviewed_ids:
            return
        _reviewed_ids.add(cid)
        meta = _picked_meta[cid]
        # NO_TAGS_KEY is a synthetic key for debt tracking — don't persist it.
        tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
        fake = types.SimpleNamespace(
            card=cid,
            card_type=meta["card_type"],
            tag=tag,
            mode=meta["mode"],
        )
        stats.record(fake, cfg.scheduler_scope)

    gui_hooks.reviewer_did_answer_card.append(_on_card_answered)

    # One-shot hook: clean up when the reviewer is left.
    def _on_reviewer_end() -> None:
        gui_hooks.reviewer_will_end.remove(_on_reviewer_end)
        gui_hooks.reviewer_did_answer_card.remove(_on_card_answered)

    gui_hooks.reviewer_will_end.append(_on_reviewer_end)
    mw.moveToState("review")


# ── PDF dock (QWebEngineView + PDF.js) ────────────────────────────────────────

_pdf_dock = None
_shortcuts_registered = False

_DOCK_HTML = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, 'user_files', 'pdf_dock.html')
).toString()
_WORKER_URL = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, 'user_files', 'pdfjs', 'pdf.worker.min.js')
).toString()


class _PdfDockPage(QWebEnginePage):
    """Intercepts console.log to get pycmd messages from the PDF viewer JS."""

    def javaScriptConsoleMessage(self, level, message, line, source):
        prefix = '__incremento_pycmd__:'
        if not message.startswith(prefix):
            return
        msg = message[len(prefix):]

        if msg.startswith('incremento_pdf_nav:'):
            parts = msg.split(':')
            if len(parts) == 3:
                try:
                    set_page(_ADDON_DIR, int(parts[1]), int(parts[2]))
                except ValueError:
                    pass
        elif msg.startswith('incremento_pdf_zoom:'):
            parts = msg.split(':')
            if len(parts) == 3:
                try:
                    set_zoom(_ADDON_DIR, int(parts[1]), float(parts[2]))
                except ValueError:
                    pass
        elif msg == 'incremento_open_add_card':
            _open_add_card_dock()
        elif msg.startswith('incremento_fill_field:'):
            try:
                data = json.loads(msg[len('incremento_fill_field:'):])
                _fill_dock_field(int(data['idx']), data['text'])
            except Exception:
                pass


def _build_pdf_dock():
    global _pdf_dock, _shortcuts_registered

    dock = QDockWidget("PDF Viewer", mw)
    dock.setObjectName("incremento_pdf_dock")
    dock.setMinimumWidth(550)

    page = _PdfDockPage(dock)
    # Allow file:// page to load other file:// resources (worker, PDF)
    s = page.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

    view = QWebEngineView(dock)
    view.setPage(page)
    dock.setWidget(view)
    dock._view = view

    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    # Inject fake pycmd bridge after every page load (needed on first load and reloads)
    def _on_load_finished(ok):
        if ok:
            view.page().runJavaScript(
                "window.pycmd = function(msg) {"
                "  console.log('__incremento_pycmd__:' + msg);"
                "};"
            )

    view.loadFinished.connect(_on_load_finished)

    # Cmd/Ctrl+1–4: get active selection from the PDF webview → fill Add Card field
    if not _shortcuts_registered:
        def _make_sc(n):
            sc = QShortcut(QKeySequence(f"Ctrl+{n}"), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            def _act():
                if _pdf_dock is None:
                    return
                try:
                    _pdf_dock._view.page().runJavaScript(
                        "window.getSelection()?.toString() || ''",
                        lambda text: _on_pdf_selection(n - 1, text),
                    )
                except Exception:
                    pass
            sc.activated.connect(_act)
        for i in range(1, 5):
            _make_sc(i)
        globals()['_shortcuts_registered'] = True

    _pdf_dock = dock
    return dock


def _on_pdf_selection(idx, text):
    text = (text or '').strip()
    if text:
        _open_add_card_dock()
        QTimer.singleShot(150, lambda: _fill_dock_field(idx, text))


def _show_pdf_in_dock(card_id, filename, page, zoom=1.0):
    global _pdf_dock
    if _pdf_dock is None:
        _build_pdf_dock()
    else:
        try:
            _pdf_dock.widget()
        except RuntimeError:
            _pdf_dock = None
            _build_pdf_dock()

    _pdf_dock.show()
    _pdf_dock.raise_()

    pdf_file_url = QUrl.fromLocalFile(
        os.path.join(mw.col.media.dir(), filename)
    ).toString()

    # Set the PDF file URL and worker URL globals before starting the viewer.
    # Use _incPdfPending so the React useEffect picks it up if not mounted yet.
    js = (
        f"window._pdfWorkerSrc = {json.dumps(_WORKER_URL)};"
        f"window._pdfFileUrl   = {json.dumps(pdf_file_url)};"
        f"window._incPdfPending = {{cardId: {card_id}, filename: {json.dumps(filename)}, page: {page}, zoom: {zoom}}};"
        f"typeof incrementoPdfStart === 'function' && "
        f"(window._incPdfPending = null,"
        f" incrementoPdfStart({card_id}, {json.dumps(filename)}, {page}, {zoom}));"
    )

    current = _pdf_dock._view.url().toString()
    if current != _DOCK_HTML:
        # First load — run JS after the page finishes loading
        def _on_first_load(ok):
            _pdf_dock._view.loadFinished.disconnect(_on_first_load)
            if ok:
                _pdf_dock._view.page().runJavaScript(js)
        _pdf_dock._view.loadFinished.connect(_on_first_load)
        _pdf_dock._view.load(QUrl(_DOCK_HTML))
    else:
        _pdf_dock._view.page().runJavaScript(js)


def _on_pdf_question_shown(card) -> None:
    global _pdf_dock
    if card is None:
        return
    try:
        note  = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
    except Exception:
        return
    if model is None or model.get("name") != PDF_NOTE_TYPE:
        # Hide the PDF dock when reviewing non-PDF cards
        if _pdf_dock is not None:
            try:
                _pdf_dock.hide()
            except RuntimeError:
                _pdf_dock = None
        return
    try:
        filename = note["PDF_Filename"]
    except (KeyError, TypeError):
        return
    page = get_page(_ADDON_DIR, card.id)
    zoom = get_zoom(_ADDON_DIR, card.id)
    _show_pdf_in_dock(card.id, filename, page, zoom)


_add_card_dock = None  # QDockWidget instance, persists across card reviews


def _build_add_card_dock():
    """Embed the native AddCards dialog into a left dock widget."""
    global _add_card_dock
    from aqt.addcards import AddCards

    dock = QDockWidget("Add Card", mw)
    dock.setObjectName("incremento_add_card_dock")
    dock.setMinimumWidth(400)

    # Open the native dialog; hide it before the event loop renders it as a
    # floating window, then reparent it into the dock as a plain widget.
    dlg = AddCards(mw)
    dlg.hide()
    dlg.setParent(dock)
    dlg.setWindowFlags(Qt.WindowType.Widget)
    dock.setWidget(dlg)

    mw.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    _add_card_dock = dock
    dlg.show()

    def _set_field(idx, text):
        note = dlg.editor.note
        if note and idx < len(note.fields):
            existing = note.fields[idx]
            note.fields[idx] = (existing + '<br><br>' + text) if existing else text
            try:
                dlg.editor.loadNote()
            except Exception:
                pass

    dock._set_field = _set_field
    return dock


def _open_add_card_dock():
    global _add_card_dock
    if _add_card_dock is not None:
        try:
            _add_card_dock.show()
            _add_card_dock.raise_()
            return
        except RuntimeError:
            _add_card_dock = None
    _build_add_card_dock()


def _fill_dock_field(idx, text):
    global _add_card_dock
    if _add_card_dock is None:
        _build_add_card_dock()
        QTimer.singleShot(600, lambda: _do_fill(idx, text))
        return
    try:
        _add_card_dock.show()
        _add_card_dock.raise_()
        _do_fill(idx, text)
    except RuntimeError:
        _add_card_dock = None


def _do_fill(idx, text):
    if _add_card_dock is None:
        return
    try:
        _add_card_dock._set_field(idx, text)
    except (RuntimeError, AttributeError):
        pass



def _on_js_message(handled, message, context) -> tuple:
    if not isinstance(message, str) or not message.startswith("incremento_"):
        return handled

    if message == "incremento_open_add_card":
        _open_add_card_dock()
        return (True, None)

    if message.startswith("incremento_fill_field:"):
        try:
            data = json.loads(message[len("incremento_fill_field:"):])
            _fill_dock_field(int(data["idx"]), data["text"])
        except Exception:
            pass
        return (True, None)

    return handled


def _on_pdf_reviewer_will_end() -> None:
    global _pdf_dock
    if _pdf_dock is not None:
        try:
            _pdf_dock.hide()
        except RuntimeError:
            _pdf_dock = None


gui_hooks.reviewer_did_show_question.append(_on_pdf_question_shown)
gui_hooks.reviewer_will_end.append(_on_pdf_reviewer_will_end)
gui_hooks.webview_did_receive_js_message.append(_on_js_message)


def _sync_pdf_note_type() -> None:
    """Update the PDF card template to the current code version on startup."""
    from .utils.pdf_manager import ensure_pdf_note_type

    def _run() -> None:
        try:
            ensure_pdf_note_type(mw.col)
        except Exception:
            pass

    mw.taskman.run_in_background(_run)


gui_hooks.main_window_did_init.append(_sync_pdf_note_type)



def showStatsFunction() -> None:
    cfg = load_scheduler_config()
    dlg = StatsDialog(
        addon_dir=os.path.dirname(__file__),
        session_counts=_session_counts,
        day_end_time=cfg.day_end_time,
        parent=mw,
    )
    dlg.exec()


def addPdfFunction() -> None:
    from .utils.pdf_dialog  import AddPdfDialog
    from .utils.pdf_manager import add_pdf_card
    dlg = AddPdfDialog(mw)
    if not dlg.exec():
        return
    try:
        add_pdf_card(_ADDON_DIR, mw.col, dlg.pdf_path, dlg.title_text)
        showInfo(f'PDF card "{dlg.title_text}" added to the Topics deck.')
    except Exception as e:
        showInfo(f"Failed to add PDF card:\n{e}")


learnAction = QAction("Start Incremental Learning", mw)
qconnect(learnAction.triggered, learnFunction)
mw.form.menuTools.addAction(learnAction)

statsAction = QAction("Incremento Statistics", mw)
qconnect(statsAction.triggered, showStatsFunction)
mw.form.menuTools.addAction(statsAction)

addPdfAction = QAction("Add PDF to Topics", mw)
qconnect(addPdfAction.triggered, addPdfFunction)
mw.form.menuTools.addAction(addPdfAction)
