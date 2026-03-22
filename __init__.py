import copy
import json
import os
import sys
import types
import zipfile

from aqt import mw, gui_hooks
from aqt.utils import showInfo, tooltip
from aqt.qt import (QAction, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
                     QPushButton, QDockWidget, QLabel, QWidget,
                     QShortcut, QKeySequence, QApplication,
                     qconnect, QTimer, Qt, QPixmap)
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
from .utils.pdf_manager import PDF_NOTE_TYPE, get_page, set_page, get_zoom, set_zoom, get_read_page, set_read_page
from .utils.video_manager import (VIDEO_NOTE_TYPE, extract_video_id, fmt_time,
                                   get_video_position, set_video_position,
                                   ensure_video_note_type, add_video_card)
from .utils.pdf_highlights import load_highlights, add_highlight, remove_highlight
from .utils.priority_manager import get_priority, set_priority
from .utils.priority_dialog import PriorityDialog

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
_current_pdf_card_id  = None
_current_pdf_filename = None
_pdf_via_link         = False   # True when dock was opened via a cross-reference link

_video_dock           = None
_current_video_card_id = None
_video_timer          = None
_video_tick_count     = 0
_video_profile        = None   # module-level singleton — avoids use-after-free on exit


def _pdf_citation() -> str:
    """Return an HTML link 'Page N. of name' that reopens the PDF dock at that page."""
    if not _current_pdf_card_id or not _current_pdf_filename:
        return ''
    page = get_page(_ADDON_DIR, _current_pdf_card_id)
    name = os.path.splitext(_current_pdf_filename)[0]
    cmd  = f'incremento_open_pdf:{_current_pdf_card_id}:{page}'
    return (
        f'<a onclick="pycmd(\'{cmd}\'); return false;" '
        f'style="cursor:pointer; color:#4a90d9; text-decoration:none;">'
        f'Page {page}. of {name}</a>'
    )

_DOCK_HTML = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, 'user_files', 'pdf_dock.html')
).toString()

_VIDEO_PLAYER_HTML = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, 'user_files', 'video_player.html')
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
                    if not _pdf_via_link:
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
        elif msg.startswith('incremento_pdf_hl_add:'):
            try:
                data = json.loads(msg[len('incremento_pdf_hl_add:'):])
                add_highlight(_ADDON_DIR, int(data['cardId']), data['highlight'])
            except Exception:
                pass
        elif msg.startswith('incremento_pdf_hl_del:'):
            try:
                data = json.loads(msg[len('incremento_pdf_hl_del:'):])
                remove_highlight(_ADDON_DIR, int(data['cardId']), data['id'])
            except Exception:
                pass
        elif msg.startswith('incremento_pdf_mark_read:'):
            parts = msg.split(':')
            if len(parts) == 3:
                try:
                    set_read_page(_ADDON_DIR, int(parts[1]), int(parts[2]))
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
        elif msg.startswith('incremento_pdf_snapshot:'):
            QTimer.singleShot(0, lambda m=msg: _handle_pdf_snapshot(m))


def _handle_pdf_snapshot(msg: str) -> None:
    """Save snapshot image to media and fill a chosen field in the Add Card dock."""
    import base64 as _b64, tempfile as _tmp
    from PyQt6.QtGui import QImage
    try:
        data    = json.loads(msg[len('incremento_pdf_snapshot:'):])
        img_b64 = data["image"]
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]
        img_bytes = _b64.b64decode(img_b64)

        with _tmp.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img_bytes)
            tmp_path = f.name
        try:
            media_filename = mw.col.media.add_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        # Open Add Card dock and read its current field names
        _open_add_card_dock()
        field_names = []
        try:
            note = _add_card_dock.widget().editor.note
            if note:
                field_names = [f["name"] for f in note.note_type()["flds"]]
        except Exception:
            pass
        if not field_names:
            field_names = [f"Field {i + 1}" for i in range(4)]

        # Build pixmap preview
        pixmap = QPixmap.fromImage(QImage.fromData(img_bytes))
        scaled = pixmap.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
        if scaled.height() > 180:
            scaled = pixmap.scaledToHeight(180, Qt.TransformationMode.SmoothTransformation)

        # Dialog: image preview + one button per field name
        picker = QDialog(mw)
        picker.setWindowTitle("Insert snapshot into field")
        picker.setFixedWidth(340)
        layout = QVBoxLayout(picker)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        preview_lbl = QLabel()
        preview_lbl.setPixmap(scaled)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview_lbl)

        layout.addSpacing(14)
        layout.addWidget(QLabel("Insert image into:"))
        layout.addSpacing(8)

        chosen_idx = [-1]

        def _make_handler(idx):
            def _handler():
                chosen_idx[0] = idx
                picker.accept()
            return _handler

        for i, name in enumerate(field_names):
            btn = QPushButton(name)
            btn.setStyleSheet("text-align: left; padding: 7px 12px;")
            btn.clicked.connect(_make_handler(i))
            layout.addWidget(btn)
            layout.addSpacing(4)

        layout.addSpacing(8)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(picker.reject)
        layout.addWidget(cancel_btn)

        if not picker.exec() or chosen_idx[0] < 0:
            return

        _fill_dock_field(chosen_idx[0], f'<img src="{media_filename}">')
    except Exception as e:
        showInfo(f"Snapshot failed:\n{e}")


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


def _show_pdf_in_dock(card_id, filename, page, zoom=1.0, via_link=False, read_page=0):
    global _pdf_dock, _current_pdf_card_id, _current_pdf_filename, _pdf_via_link
    _current_pdf_card_id  = card_id
    _current_pdf_filename = filename
    _pdf_via_link         = via_link
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

    hls = load_highlights(_ADDON_DIR, card_id)

    # Set the PDF file URL and worker URL globals before starting the viewer.
    # Use _incPdfPending so the React useEffect picks it up if not mounted yet.
    js = (
        f"window._pdfWorkerSrc    = {json.dumps(_WORKER_URL)};"
        f"window._pdfFileUrl      = {json.dumps(pdf_file_url)};"
        f"window._incPdfHighlights = {json.dumps(hls)};"
        f"window._incPdfPending   = {{cardId: {card_id}, filename: {json.dumps(filename)}, page: {page}, zoom: {zoom}, readPage: {read_page}}};"
        f"typeof incrementoPdfStart === 'function' && "
        f"(window._incPdfPending = null,"
        f" incrementoPdfStart({card_id}, {json.dumps(filename)}, {page}, {zoom}, {read_page}));"
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


# ── Video dock ────────────────────────────────────────────────────────────────

_YT_CURRENT_TIME_JS = (
    "(function(){"
    "var v=document.querySelector('video');"
    "return v ? v.currentTime : 0;"
    "})()"
)


def _build_video_dock():
    global _video_dock, _video_profile

    dock = QDockWidget("Video", mw)
    dock.setObjectName("incremento_video_dock")
    dock.setMinimumWidth(560)

    from PyQt6.QtWebEngineCore import (QWebEngineSettings as _WES,
                                       QWebEngineProfile as _WEProf,
                                       QWebEnginePage as _WEPage)

    container = QWidget()
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(0)

    view = QWebEngineView(container)

    # Module-level profile with no parent — avoids use-after-free segfault on exit
    # that occurs when the profile is parented to the view and both get destroyed.
    # Persistent named profile so YouTube login cookies survive across restarts.
    if _video_profile is None:
        _video_profile = _WEProf("incremento_video")
        _video_profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        _video_profile.settings().setAttribute(
            _WES.WebAttribute.PlaybackRequiresUserGesture, False
        )

    _page = _WEPage(_video_profile)  # no parent — profile must outlive page
    view.setPage(_page)

    vbox.addWidget(view, 1)

    ctrl = QWidget(container)
    ctrl_layout = QHBoxLayout(ctrl)
    ctrl_layout.setContentsMargins(8, 4, 8, 4)

    ts_lbl = QLabel("\u25b6  0:00")
    ts_lbl.setStyleSheet("font-family: monospace; font-size: 12px;")
    ctrl_layout.addWidget(ts_lbl)
    ctrl_layout.addStretch()

    add_btn = QPushButton("+ Add Card at this point")
    ctrl_layout.addWidget(add_btn)
    vbox.addWidget(ctrl)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._view   = view
    dock._ts_lbl = ts_lbl
    qconnect(add_btn.clicked, _video_add_card_at_point)

    _video_dock = dock
    return dock


def _show_video_in_dock(card_id: int, youtube_url: str, position: float = 0.0) -> None:
    global _video_dock, _current_video_card_id

    _current_video_card_id = card_id

    if _video_dock is None:
        _build_video_dock()
    else:
        try:
            _video_dock.widget()
        except RuntimeError:
            _video_dock = None
            _build_video_dock()

    video_id = extract_video_id(youtube_url)
    if not video_id:
        showInfo(f"Could not find a YouTube video ID in:\n{youtube_url}")
        return

    # Load the full YouTube watch page — this avoids all embed-level restrictions
    # (Error 152/153) that occur when using the IFrame API from a non-browser origin.
    # Position tracking uses document.querySelector('video').currentTime.
    start_sec = int(position)
    url = QUrl(f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s&autoplay=1")

    _video_dock.show()
    _video_dock.raise_()
    _video_dock._view.load(url)
    _start_video_timer()


def _start_video_timer() -> None:
    global _video_timer, _video_tick_count
    _video_tick_count = 0
    if _video_timer is not None:
        try:
            _video_timer.stop()
        except RuntimeError:
            pass
    _video_timer = QTimer()
    _video_timer.setInterval(1000)
    _video_timer.timeout.connect(_video_timer_tick)
    _video_timer.start()


def _video_timer_tick() -> None:
    if _video_dock is None or _current_video_card_id is None:
        return
    try:
        _video_dock._view.page().runJavaScript(_YT_CURRENT_TIME_JS, _on_video_time)
    except (RuntimeError, AttributeError):
        pass


def _on_video_time(t) -> None:
    global _video_tick_count
    if _video_dock is None:
        return
    t = float(t or 0)
    try:
        _video_dock._ts_lbl.setText(f"\u25b6  {fmt_time(t)}")
    except (RuntimeError, AttributeError):
        return
    _video_tick_count += 1
    if _video_tick_count >= 5 and _current_video_card_id:
        _video_tick_count = 0
        try:
            set_video_position(_ADDON_DIR, _current_video_card_id, t)
        except Exception:
            pass


def _video_add_card_at_point() -> None:
    if _video_dock is None or _current_video_card_id is None:
        return
    try:
        _video_dock._view.page().runJavaScript(_YT_CURRENT_TIME_JS, _do_video_add_card)
    except (RuntimeError, AttributeError):
        pass


def _do_video_add_card(t) -> None:
    t = float(t or 0)
    if _current_video_card_id is None:
        return
    try:
        set_video_position(_ADDON_DIR, _current_video_card_id, t)
    except Exception:
        pass
    ts = fmt_time(t)
    try:
        note = mw.col.get_card(_current_video_card_id).note()
        title = note.fields[0][:60].strip() if note.fields else ""
    except Exception:
        title = ""
    label = f"&#9654; {ts}" + (f" \u2013 {title}" if title else "")
    link = (
        f'<a href="#" onclick="pycmd(\'incremento_open_video:{_current_video_card_id}:{t}\')" '
        f'style="color:#4a90d9;">{label}</a>'
    )
    _fill_dock_field(0, link)


def _on_video_question_shown(card) -> None:
    global _video_dock, _video_timer
    if card is None:
        return
    try:
        note  = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
    except Exception:
        return
    if model is None or model.get("name") != VIDEO_NOTE_TYPE:
        if _video_dock is not None:
            try:
                _video_dock.hide()
            except RuntimeError:
                _video_dock = None
        if _video_timer is not None:
            try:
                _video_timer.stop()
            except RuntimeError:
                pass
        return
    try:
        youtube_url = note["YouTube_URL"]
    except (KeyError, TypeError):
        return
    position = get_video_position(_ADDON_DIR, card.id)
    _show_video_in_dock(card.id, youtube_url, position)


def _on_video_reviewer_will_end() -> None:
    global _video_dock, _video_timer
    if _video_timer is not None:
        try:
            _video_timer.stop()
        except RuntimeError:
            pass
        _video_timer = None
    if _video_dock is not None:
        try:
            _video_dock.hide()
        except RuntimeError:
            _video_dock = None


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
    page      = get_page(_ADDON_DIR, card.id)
    zoom      = get_zoom(_ADDON_DIR, card.id)
    read_page = get_read_page(_ADDON_DIR, card.id)
    _show_pdf_in_dock(card.id, filename, page, zoom, read_page=read_page)


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
    citation = _pdf_citation()
    if citation:
        text = text + '<br>' + citation
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

    if message.startswith("incremento_open_card:"):
        try:
            card_id = int(message[len("incremento_open_card:"):])
            from aqt import dialogs
            def _browse():
                b = dialogs.open("Browser", mw)
                b.search_for(f"cid:{card_id}")
            QTimer.singleShot(0, _browse)
        except Exception:
            pass
        return (True, None)

    if message.startswith("incremento_open_pdf:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id = int(parts[1])
                page    = int(parts[2])
                card    = mw.col.get_card(card_id)
                note    = mw.col.get_note(card.nid)
                filename = note["PDF_Filename"]
                zoom    = get_zoom(_ADDON_DIR, card_id)
                _show_pdf_in_dock(card_id, filename, page, zoom, via_link=True)
            except Exception:
                pass
        return (True, None)

    if message.startswith("incremento_open_video:"):
        parts = message.split(":")
        if len(parts) == 3:
            try:
                card_id  = int(parts[1])
                position = float(parts[2])
                card     = mw.col.get_card(card_id)
                note     = mw.col.get_note(card.nid)
                url      = note["YouTube_URL"]
                QTimer.singleShot(0, lambda: _show_video_in_dock(card_id, url, position))
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
gui_hooks.reviewer_did_show_question.append(_on_video_question_shown)
gui_hooks.reviewer_will_end.append(_on_pdf_reviewer_will_end)
gui_hooks.reviewer_will_end.append(_on_video_reviewer_will_end)
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


def _sync_video_note_type() -> None:
    try:
        ensure_video_note_type(mw.col)
    except Exception:
        pass


gui_hooks.main_window_did_init.append(_sync_video_note_type)


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


def exportFunction() -> None:
    import datetime
    from aqt.qt import QFileDialog
    from .utils.db import (get_connection, DB_NAME,
                           export_priorities_json, export_pdf_progress_json,
                           export_highlights_json, export_stats_json)

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
    media_dir      = mw.col.media.dir()

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
            zf.writestr("data/priorities.json",   export_priorities_json(_ADDON_DIR))
            zf.writestr("data/pdf_progress.json", export_pdf_progress_json(_ADDON_DIR))
            zf.writestr("data/highlights.json",   export_highlights_json(_ADDON_DIR))
            zf.writestr("data/stats.json",        export_stats_json(_ADDON_DIR))

            # ── config.json — scheduler settings ─────────────────────────────
            config = mw.addonManager.getConfig(__name__) or {}
            zf.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))

            # ── pdfs/ — PDF media files ───────────────────────────────────────
            pdf_count = 0
            pdf_missing = []
            for fname in pdf_filenames:
                pdf_path = os.path.join(media_dir, fname)
                if os.path.exists(pdf_path):
                    zf.write(pdf_path, f"pdfs/{fname}")
                    pdf_count += 1
                else:
                    pdf_missing.append(fname)

            # ── manifest.json — export metadata ──────────────────────────────
            manifest = {
                "export_date": today,
                "addon": "Incremento",
                "anki_version": getattr(mw.pm, "meta", {}).get("ankiVersion", "unknown"),
                "counts": {
                    "pdf_notes":     len(pdf_filenames),
                    "pdfs_exported": pdf_count,
                    "pdfs_missing":  len(pdf_missing),
                    "priorities":    priority_count,
                },
                "files": {
                    f"data/{DB_NAME}":          "All user data (SQLite, for direct restore)",
                    "data/priorities.json":     "Card priorities (human-readable copy)",
                    "data/pdf_progress.json":   "PDF reading positions and zoom levels",
                    "data/highlights.json":     "PDF text highlights",
                    "data/stats.json":          "Session, daily and lifetime statistics",
                    "config.json":              "Scheduler and session settings",
                    "pdfs/":                    "PDF files referenced by Incremento cards",
                },
            }
            if pdf_missing:
                manifest["pdfs_missing_filenames"] = pdf_missing

            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # ── Success dialog ────────────────────────────────────────────────────
        missing_note = (
            f"\n\n  ⚠ {len(pdf_missing)} PDF file(s) not found in media folder"
            if pdf_missing else ""
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
    from .utils.extract_card_dialog import ExtractCardDialog

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
    parent_label = (parent_note.fields[0][:60].strip()
                    if parent_note.fields else f"Card {parent_card.id}")
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
            if deck is None else deck["id"]
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
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None) if reviewer else None
    if card is None:
        showInfo("No card is currently being reviewed.")
        return

    current = get_priority(_ADDON_DIR, card.id)
    # Build a short label: first 60 chars of the front field
    note = card.note()
    label_text = ""
    if note.fields:
        label_text = note.fields[0][:80].strip()

    dlg = PriorityDialog(current_priority=current,
                         card_label=label_text, parent=mw)
    if dlg.exec():
        set_priority(_ADDON_DIR, card.id, dlg.priority)


_priority_shortcut = QShortcut(QKeySequence("Alt+P"), mw)
_priority_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_priority_shortcut.activated, _open_priority_dialog)

_extract_shortcut = QShortcut(QKeySequence("Alt+X"), mw)
_extract_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
qconnect(_extract_shortcut.activated, _extract_card)


def addVideoFunction() -> None:
    """Incremento -> Add Content -> YouTube Video"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .utils.add_video_dialog import AddVideoDialog
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
    try:
        add_video_card(mw.col, url, title)
        mw.col.reset()
        tooltip(f"Video card '{title}' added to Topics.")
    except Exception as e:
        showInfo(f"Failed to add video card:\n{e}")


def addWebpageFunction() -> None:
    from .utils.webpage_dialog import WebpageToPdfDialog
    from .utils.pdf_manager import add_pdf_card
    dlg = WebpageToPdfDialog(mw)
    if not dlg.exec():
        return
    try:
        add_pdf_card(_ADDON_DIR, mw.col, dlg.pdf_path, dlg.title_text)
        showInfo(f'PDF card "{dlg.title_text}" added to the Topics deck.')
    except Exception as e:
        showInfo(f"Failed to import webpage as PDF:\n{e}")


# ── Incremento top-level menu ─────────────────────────────────────────────────

_menu = QMenu("Incremento", mw)
mw.menuBar().addMenu(_menu)

_startAction = QAction("Start Incremental Learning", mw)
qconnect(_startAction.triggered, learnFunction)
_menu.addAction(_startAction)

_menu.addSeparator()

_addContentMenu = QMenu("Add Content", mw)
_menu.addMenu(_addContentMenu)

_addPdfAction = QAction("Add PDF", mw)
qconnect(_addPdfAction.triggered, addPdfFunction)
_addContentMenu.addAction(_addPdfAction)

_addWebpageAction = QAction("Webpage to PDF", mw)
qconnect(_addWebpageAction.triggered, addWebpageFunction)
_addContentMenu.addAction(_addWebpageAction)

_addVideoAction = QAction("YouTube Video", mw)
qconnect(_addVideoAction.triggered, addVideoFunction)
_addContentMenu.addAction(_addVideoAction)

_menu.addSeparator()

_statsAction = QAction("Statistics", mw)
qconnect(_statsAction.triggered, showStatsFunction)
_menu.addAction(_statsAction)

_exportAction = QAction("Export User Data", mw)
qconnect(_exportAction.triggered, exportFunction)
_menu.addAction(_exportAction)
