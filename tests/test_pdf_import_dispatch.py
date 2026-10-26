from types import SimpleNamespace
import sys
import pytest

import pdf_import


def test_pdf_import_dispatch_rejects_switched_profile_before_work_and_after_work(monkeypatch):
    queued, saved, shown, errors = [], [], [], []

    class Operation:
        def __init__(self, parent, operation):
            self.operation = operation

        def success(self, callback):
            self.done = callback
            return self

        def failure(self, callback):
            self.error = callback
            return self

        def run_in_background(self):
            queued.append(self)

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(CollectionOp=Operation))
    monkeypatch.setitem(sys.modules, "anki.collection", SimpleNamespace(OpChanges=lambda **kwargs: kwargs))
    profile = ["A"]
    col = object()
    monkeypatch.setattr(pdf_import, "mw", SimpleNamespace(col=col))
    monkeypatch.setattr(pdf_import, "get_active_profile", lambda: profile[0])
    monkeypatch.setattr(
        pdf_import, "import_prepared_pdf_item", lambda item, **kwargs: saved.append(kwargs) or {"ok": True}
    )
    pdf_import.start_prepared_pdf_import({}, shown.append, errors.append, is_cancelled=lambda: False)
    profile[0] = "B"
    with pytest.raises(RuntimeError, match="profile changed"):
        queued[0].operation(col)
    assert saved == []
    profile[0] = "A"
    result = queued[0].operation(col)
    assert saved == [{"col": col, "profile": "A"}]
    profile[0] = "B"
    queued[0].done(result)
    assert shown == [] and len(errors) == 1
