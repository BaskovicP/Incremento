from types import SimpleNamespace
from document_query import DocumentQuery


def test_typing_is_debounced_and_obsolete_document_results_never_publish():
    pending, shown, starts = [], [], []
    current = [True]
    timer = SimpleNamespace(start=lambda: starts.append(1), stop=lambda: None)
    query = DocumentQuery(None, read=lambda *args: [], publish=lambda request, hits: shown.append(hits),
        current=lambda request: current[0], timer=timer, dispatch=lambda *args: pending.append(args))
    query.submit("A", 7, "one")
    query.submit("A", 7, "two")
    assert pending == [] and len(starts) == 2
    query.start()
    assert pending[0][0].payload["query"] == "two"
    query.submit("A", 7, "three")
    pending[0][1](["obsolete"])
    assert shown == []
    query.start()
    current[0] = False
    pending[1][1](["wrong document"])
    assert shown == []
    query.close()
