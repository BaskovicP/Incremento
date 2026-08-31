"""Reviewer focus recovery after Incremento's reader-dock hooks run."""

from __future__ import annotations


_FOCUS_RESTORE_DELAYS_MS = (0, 50, 150)


def _is_owned_by_main_window(window, main_window) -> bool:
    current = window
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if current is main_window:
            return True
        seen.add(id(current))
        parent_getter = getattr(current, "parentWidget", None)
        if not callable(parent_getter):
            parent_getter = getattr(current, "parent", None)
        try:
            current = parent_getter() if callable(parent_getter) else None
        except Exception:
            current = None
    return False


def _is_dock_window(window) -> bool:
    inherits = getattr(window, "inherits", None)
    try:
        if callable(inherits) and inherits("QDockWidget"):
            return True
    except Exception:
        pass
    try:
        return any(cls.__name__ == "QDockWidget" for cls in type(window).__mro__)
    except Exception:
        return False


def restore_reviewer_focus(main_window, *, application=None) -> bool:
    """Focus Anki's review webview when no dialog should retain focus."""
    if str(getattr(main_window, "state", "") or "") != "review":
        return False

    reviewer = getattr(main_window, "reviewer", None)
    if reviewer is None or getattr(reviewer, "card", None) is None:
        return False

    if application is not None:
        for getter_name in ("activeModalWidget", "activePopupWidget"):
            getter = getattr(application, getter_name, None)
            try:
                if callable(getter) and getter() is not None:
                    return False
            except Exception:
                return False

        active_window_getter = getattr(application, "activeWindow", None)
        try:
            active_window = active_window_getter() if callable(active_window_getter) else None
        except Exception:
            active_window = None
        if active_window is not None and active_window is not main_window:
            # A floating reader QDockWidget may become the active window when
            # its question hook calls show()/raise_().  Permit that specific
            # case, but do not displace a non-modal editor/browser/dialog just
            # because it is parented to Anki's main window.
            if not (
                _is_dock_window(active_window)
                and _is_owned_by_main_window(active_window, main_window)
            ):
                return False

    web = getattr(main_window, "web", None)
    set_focus = getattr(web, "setFocus", None)
    if not callable(set_focus):
        return False
    try:
        set_focus()
    except Exception:
        return False
    return True


def schedule_reviewer_focus_restore(
    main_window,
    *,
    timer,
    application=None,
) -> None:
    """Retry briefly while reviewer-transition and Qt focus events settle."""
    for delay_ms in _FOCUS_RESTORE_DELAYS_MS:
        timer.singleShot(
            delay_ms,
            lambda: restore_reviewer_focus(
                main_window,
                application=application,
            ),
        )


def register_reviewer_focus_restore_hooks(gui_hooks, callback) -> None:
    """Recover shortcuts after both sides of the reviewer are rendered."""
    gui_hooks.reviewer_did_show_question.append(callback)
    gui_hooks.reviewer_did_show_answer.append(callback)
