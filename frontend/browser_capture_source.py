"""Render stored browser provenance without modifying users' note templates."""

try:
    from ..backend.browser_capture import capture_source_html
except ImportError:
    from browser_capture import capture_source_html


def render_browser_capture_source(text, card, kind):
    if 'id="incremento-browser-source"' in text:
        return text
    try:
        note = card.note()
        if note["Incremento_Source_Type"] != "Browser Capture":
            return text
        link = capture_source_html(note["Incremento_Source_Link"], note["Incremento_Source_Title"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return text
    return text + '<div id="incremento-browser-source" style="margin-top:1em;font-size:.85em">' + link + "</div>"


def open_browser_capture_note(note_id):
    from aqt import dialogs, mw

    browser = dialogs.open("Browser", mw)
    browser.search_for(f"nid:{int(note_id)}")


def dispatch_browser_capture(normalized, success, failure, *, is_cancelled=lambda: False):
    """Keep legacy collection search off Qt and reject stale profile results."""
    from aqt import mw
    from aqt.operations import QueryOp

    try:
        from ..backend import browser_bridge as bridge
    except ImportError:
        import browser_bridge as bridge

    profile = bridge._browser_capture_active_profile()
    collection = mw.col
    token = normalized.get("profile_token", "")

    def require_current(col):
        if is_cancelled():
            raise TimeoutError("Incremento browser capture timed out.")
        if (col is not collection or mw.col is not collection
                or bridge._browser_capture_active_profile() != profile
                or (token and token != bridge._browser_capture_profile_token(profile))):
            raise ValueError("Anki profile changed. Reopen the capture dialog.")

    def inspect(col):
        require_current(col)
        return bridge._find_browser_capture_duplicate(col, profile, normalized)

    def finish(duplicate):
        try:
            require_current(mw.col)
            result = bridge._create_browser_capture_note_on_main(
                normalized, legacy_duplicate=duplicate, legacy_checked=True,
            )
            if result.get("type") == "browser_capture":
                bridge._refresh_anki_after_import()
            success(result)
        except Exception as error:
            failure(error)

    try:
        require_current(collection)
        QueryOp(parent=mw, op=inspect, success=finish).failure(failure).run_in_background()
    except Exception as error:
        failure(error)
