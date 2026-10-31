"""Main-thread native UI controls requested through reviewed MCP operations."""

from copy import deepcopy
import threading

try:
    from ..backend.anki_compat import (
        mcp_reviewer_state,
        mcp_show_reviewer_side,
        mcp_prepare_answer,
        mcp_finish_answer,
        mcp_restore_reviewer,
    )
    from ..backend.mcp_anki import AnkiToolError
except ImportError:
    from anki_compat import (
        mcp_reviewer_state,
        mcp_show_reviewer_side,
        mcp_prepare_answer,
        mcp_finish_answer,
        mcp_restore_reviewer,
    )
    from mcp_anki import AnkiToolError


class McpRuntime:
    def __init__(self, controller):
        self.controller = controller
        self.effects = []

    def call(self, action, parameters, *, valid=lambda: True):
        done = threading.Event()
        reply = {}

        def work():
            try:
                if not valid() or self.controller.mw.col is not self.controller.collection:
                    raise AnkiToolError("The active collection changed.")
                start = len(self.effects)
                reply["value"] = self._call(action, parameters)
                self.effects[start:] = [
                    (lambda effect=effect: effect() if valid() else None) for effect in self.effects[start:]
                ]
            except Exception as error:
                reply["error"] = error
            finally:
                done.set()

        self.controller.mw.taskman.run_on_main(work)
        if not done.wait(10):
            raise AnkiToolError("The native UI adapter did not respond.")
        if "error" in reply:
            raise reply["error"]
        return reply.get("value", {})

    def flush(self):
        effects, self.effects = self.effects, []
        for effect in effects:
            effect()

    def _timer(self):
        from . import timer_widget as timer

        if timer._timer_widget is None:
            raise AnkiToolError("Enable the native focus timer toolbar first.")
        return timer, timer._timer_widget

    def _snapshot(self, area, card_id=None):
        if area == "player":
            from . import video_dock as video

            dock = video._video_dock
            if (
                not video._using_local_qt_player
                or dock is None
                or (card_id and str(video._current_video_card_id) != str(card_id))
            ):
                raise AnkiToolError("Open the selected video with the native local player first.")
            player = dock._local_player
            return {
                "card_id": str(video._current_video_card_id),
                "position": player.position() / 1000,
                "playing": player.playbackState() == video.QMediaPlayer.PlaybackState.PlayingState,
                "speed": player.playbackRate(),
                "volume": dock._local_audio.volume() * 100,
            }
        if area != "timer":
            try:
                from ..backend.session import snapshot_mcp_session
            except ImportError:
                from backend.session import snapshot_mcp_session
            state = mcp_reviewer_state(self.controller.mw, include_runtime=True)
            state["session"] = snapshot_mcp_session()
            try:
                state["timer"] = self._snapshot("timer")
            except AnkiToolError:
                state["timer"] = None
            return state
        timer, widget = self._timer()
        values = {
            key: deepcopy(value)
            for key, value in vars(timer).items()
            if key.startswith("_timer_") and isinstance(value, (str, int, float, bool, set))
        }
        values = {key: sorted(value) if isinstance(value, set) else value for key, value in values.items()}
        return {"minutes": widget._sel, "remaining": widget._rem, "running": widget._running, "counters": values}

    def _restore(self, area, state):
        mw = self.controller.mw
        if area == "player":
            from . import video_dock as video

            if str(video._current_video_card_id) != state["card_id"] or video._video_dock is None:
                try:
                    from ..backend.video_manager import get_video_note_media
                except ImportError:
                    from backend.video_manager import get_video_note_media
                note = mw.col.get_note(mw.col.get_card(int(state["card_id"])).nid)
                video.show_video_in_dock(
                    int(state["card_id"]), note["YouTube_URL"], state["position"], **get_video_note_media(note)
                )
            video._seek_to_seconds(state["position"])
            video._set_local_rate(str(state["speed"]))
            video._set_local_volume(round(state["volume"]))
            player = video._video_dock._local_player
            player.play() if state["playing"] else player.pause()
            try:
                from ..backend.video_manager import set_video_position
            except ImportError:
                from backend.video_manager import set_video_position
            set_video_position(
                self.controller.addon_dir, self.controller.profile, int(state["card_id"]), state["position"]
            )
        elif area == "timer":
            timer, widget = self._timer()
            widget._pause()
            widget._pick(state["minutes"])
            widget._rem = state["remaining"]
            for key, value in state.get("counters", {}).items():
                if not key.startswith("_timer_") or not hasattr(timer, key):
                    raise AnkiToolError("Invalid timer checkpoint.")
                setattr(timer, key, {tuple(x) for x in value} if isinstance(getattr(timer, key), set) else value)
            widget._running = state["running"]
            widget._start_btn.setText(timer._t("admin_timer_pause" if state["running"] else "admin_timer_resume"))
            widget._render()
            if state["running"]:
                widget._qt_timer.start()
        else:
            expected_collection, expected_server = self.controller.collection, self.controller.server
            if state.get("timer"):
                self._restore("timer", state["timer"])

            def restore_view():
                if self.controller.mw.col is not expected_collection or self.controller.server is not expected_server:
                    return
                if (
                    mw.state == "review"
                    and state.get("card_id")
                    and str(getattr(getattr(mw.reviewer, "card", None), "id", "")) == state["card_id"]
                ):
                    mcp_restore_reviewer(mw, state)
                    return
                if state.get("session") and state.get("screen") == "review":
                    try:
                        from ..backend.session import restore_mcp_session
                    except ImportError:
                        from backend.session import restore_mcp_session
                    if mw.state == "review":
                        mw.moveToState("deckBrowser")
                    restore_mcp_session(
                        state["session"],
                        col=mw.col,
                        addon_dir=self.controller.addon_dir,
                        profile=self.controller.profile,
                        deck_id=int(state["deck_id"]),
                    )
                elif state.get("deck_id") and mw.col.decks.get(int(state["deck_id"]), default=False):
                    mw.col.decks.select(int(state["deck_id"]))
                    if mw.state != state.get("screen"):
                        mw.moveToState("review" if state.get("screen") == "review" else "deckBrowser")
                else:
                    mw.moveToState("deckBrowser")
                mcp_restore_reviewer(mw, state)

            from aqt.qt import QTimer

            self.effects.append(lambda: QTimer.singleShot(100, restore_view))

    def _call(self, action, p):
        mw = self.controller.mw
        if action == "check_readers_closed":
            import sys

            ids = set(map(str, p["card_ids"]))
            prefix = __package__ or "frontend"
            for kind in ("pdf", "epub", "video", "web"):
                module = sys.modules.get(prefix + "." + kind + "_dock")
                dock = getattr(module, "_" + kind + "_dock", None)
                if (
                    str(getattr(module, "_current_" + kind + "_card_id", None)) in ids
                    and dock is not None
                    and dock.isVisible()
                ):
                    raise AnkiToolError(
                        "Close the selected document reader before editing its saved state or source, so its pending saves cannot overwrite the MCP change."
                    )
            return {}
        if action == "administration":
            return {
                "profile": self.controller.profile,
                "profiles": list(mw.pm.profiles()),
                "sync_configured": bool(mw.pm.profile.get("syncKey")),
                "addons": [
                    {"id": str(key), "enabled": bool(mw.addonManager.isEnabled(key))}
                    for key in mw.addonManager.allAddons()
                ],
            }
        if action == "reviewer_state":
            return mcp_reviewer_state(mw)
        if action == "tag_palette":
            from .tag_colors import tag_chip_palette_size, tag_chip_reserved_indexes, tag_chip_color_for_index

            return {
                "size": tag_chip_palette_size(),
                "reserved": tag_chip_reserved_indexes(),
                "colors": {str(index): tag_chip_color_for_index(index) for index in p.get("indexes", [])},
            }
        if action == "validate_settings":
            from .shortcut_conflicts import find_shortcut_conflicts

            if find_shortcut_conflicts(p.get("shortcuts", {})):
                raise AnkiToolError("Two actions have the same shortcut.")
            return {}
        if action == "snapshot":
            return self._snapshot(p["area"], p.get("card_id"))
        if action == "restore_checkpoint":
            state = p["state"]
            if "runtime" in state:
                self._restore(state["scope"]["ui"]["area"], state["runtime"])
            return {}
        if action == "check_restore":
            if p["state"].get("runtime", {}).get("timer"):
                self._timer()
            if p["state"]["scope"]["ui"]["area"] == "timer":
                self._timer()
            if p["state"]["scope"]["ui"]["area"] == "player":
                from . import video_dock as video

                previous = p["state"]["runtime"]
                if (
                    video._current_video_card_id is not None
                    and str(video._current_video_card_id) != previous["card_id"]
                ):
                    raise AnkiToolError("Another video is active. Close it before restoring the earlier player state.")
            return {}
        if action == "playback":
            from . import video_dock as video

            self._snapshot("player", p["card_id"])
            command = p["command"]
            player = video._video_dock._local_player
            if command == "play":
                player.play()
            elif command == "pause":
                player.pause()
            elif command == "seek":
                video._seek_to_seconds(p["value"])
            elif command == "speed":
                video._set_local_rate(str(p["value"]))
            elif command == "volume":
                video._set_local_volume(round(p["value"]))
            return self._snapshot("player", p["card_id"])
        if action == "save_settings":
            try:
                self.controller.save_config(p)
            except Exception:
                # The composition adapter saves canonically before refreshing
                # widgets. If only refresh failed, report the committed state
                # so the service can retain the correct inverse.
                try:
                    from ..backend.config_service import normalize_config
                except ImportError:
                    from config_service import normalize_config
                persisted = normalize_config(self.controller.load_config())
                if persisted != normalize_config(p):
                    raise
            self.controller.config = deepcopy(p)
            return {}
        if action == "queue_job":
            self.effects.append(lambda: self.controller.start_job(p["job_id"]))
            return {}
        if action == "check_full_restore":
            if mw.state == "review" or self.controller.open_writing_cards():
                raise AnkiToolError("Leave the reviewer and close writing editors before a full restore.")
            if mw.pm.profile.get("syncKey") and (
                mw.pm.profile.get("autoSync", True) or mw.pm.profile.get("autoSyncMediaMinutes", 15)
            ):
                raise AnkiToolError(
                    "Turn off automatic collection and media sync before a full restore; strict undo cannot reverse remote sync."
                )
            return {}
        if action == "reviewer_side":
            mcp_show_reviewer_side(mw, p["card_id"], p["side"])
            return mcp_reviewer_state(mw)
        if action == "session":
            state = {
                "screen": "deckBrowser",
                "deck_id": p.get("deck_id", str(mw.col.decks.selected())),
                "side": "question",
                "card_id": None,
            }
            if p["command"] != "end":
                state["screen"] = "review"
                state["session"] = p.get("session")
                self._restore("reviewer", state)
            else:
                # Let native session-exit hooks flush before capturing the
                # after-state rather than after the durable journal commits.
                mw.moveToState("deckBrowser")
            return state
        if action == "prepare_answer":
            answer, ease = mcp_prepare_answer(mw, p["card_id"], p["rating"], p.get("topic_choice"))
            return {"answer": answer, "ease": ease}
        if action == "finish_answer":
            mcp_finish_answer(mw, p["card_id"], p["ease"])
            self.effects.append(lambda: mw.reset())
            return {}
        if action == "timer":
            _, widget = self._timer()
            if p.get("minutes") is not None:
                widget._pause()
                widget._pick(p["minutes"])
            if p["command"] in {"start", "resume"}:
                widget._start()
            elif p["command"] == "pause":
                widget._pause()
            else:
                widget._reset()
            return self._snapshot("timer")
        raise AnkiToolError("Unknown native UI operation.")
