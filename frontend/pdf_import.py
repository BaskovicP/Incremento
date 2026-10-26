"""Serialized companion PDF imports; all PDF/file/index work runs on the worker."""
from aqt import mw

try:
    from ..backend.browser_bridge import import_prepared_pdf_item
    from ..backend.paths import get_active_profile
except ImportError:
    from browser_bridge import import_prepared_pdf_item
    from paths import get_active_profile


def start_prepared_pdf_import(normalized, success, failure, *, is_cancelled):
    from aqt.operations import CollectionOp
    from anki.collection import OpChanges
    from types import SimpleNamespace
    profile, collection, item = get_active_profile(), mw.col, dict(normalized)
    def operation(col):
        if is_cancelled() or col is not collection or get_active_profile() != profile:
            raise RuntimeError("Anki profile changed. Reopen the extension popup.")
        value = import_prepared_pdf_item(item, col=col, profile=profile)
        return SimpleNamespace(value=value, changes=OpChanges(
            card=True, note=True, deck=True, tag=True, notetype=True,
            browser_table=True, browser_sidebar=True, note_text=True, study_queues=True,
        ))
    def done(result):
        try:
            if is_cancelled() or mw.col is not collection or get_active_profile() != profile:
                raise RuntimeError("Anki profile changed. Reopen the extension popup.")
        except Exception as error:
            failure(error)
            return
        success(result.value)
    CollectionOp(mw, operation).success(done).failure(failure).run_in_background()
