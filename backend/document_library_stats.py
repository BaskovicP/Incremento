"""On-demand, read-only statistics for the document bookshelf.

Call only from a collection worker with a captured profile. Counts remain an
operation-local snapshot; Anki owns due state and review counters.
"""

from __future__ import annotations

from concurrent.futures import CancelledError

try:
    from .db import get_connection
    from .media_review import linked_media_attachment_card_ids, load_media_review_tree_snapshot
except ImportError:
    from db import get_connection
    from media_review import linked_media_attachment_card_ids, load_media_review_tree_snapshot


def load_document_statistics(
    addon_dir: str,
    profile: str,
    documents,
    *,
    col,
    metric: str,
    cancelled=None,
) -> dict[int, int]:
    """Count annotations, due attachments, or document-plus-attachment reviews.

    Attachments include the same direct and nested relationships as Review All.
    Each card contributes once per document, even when it has several links.
    Annotation counts are saved highlight/annotation records, including snapshots;
    notes on an annotation do not create an additional record.
    """
    def check_cancelled():
        if cancelled is not None and cancelled.is_set():
            raise CancelledError()

    check_cancelled()
    if metric not in {"annotations", "due", "reviews"}:
        raise ValueError("Unsupported document statistic")
    documents = list(dict.fromkeys(
        (int(card_id), kind) for card_id, kind in documents
        if int(card_id) > 0 and kind in {"PDF", "EPUB"}
    ))
    counts = {card_id: 0 for card_id, _kind in documents}
    if not documents:
        return counts
    if metric == "annotations":
        conn = get_connection(addon_dir, profile)
        for kind, table in (("PDF", "pdf_highlights"), ("EPUB", "epub_highlights")):
            ids = [card_id for card_id, doc_kind in documents if doc_kind == kind]
            for start in range(0, len(ids), 900):
                check_cancelled()
                chunk = ids[start:start + 900]
                marks = ",".join("?" for _ in chunk)
                counts.update(conn.execute(
                    f"SELECT card_id, COUNT(*) FROM {table} WHERE card_id IN ({marks}) GROUP BY card_id", chunk,
                ))
        check_cancelled()
        return counts

    tree = load_media_review_tree_snapshot(addon_dir, profile)
    cards_by_document = {}
    for card_id, kind in documents:
        check_cancelled()
        attached = set(linked_media_attachment_card_ids(
            addon_dir, profile, card_id, col=col, media_kind=kind.casefold(),
            include_tree_descendants=True, tree_snapshot=tree,
        ))
        attached.discard(card_id)
        if metric == "reviews":
            attached.add(card_id)
        cards_by_document[card_id] = attached
    all_ids = sorted(set().union(*cards_by_document.values()))
    values = {}
    for start in range(0, len(all_ids), 500):
        check_cancelled()
        chunk = all_ids[start:start + 500]
        if metric == "due":
            # Delegate logical day/learning due semantics to Anki's search.
            query = "cid:" + ",".join(str(cid) for cid in chunk)
            values.update((int(cid), 1) for cid in col.find_cards(
                f"{query} is:due -is:suspended -is:buried",
            ))
        else:
            marks = ",".join("?" for _ in chunk)
            values.update((int(cid), max(0, int(reps or 0))) for cid, reps in col.db.all(
                f"SELECT id, reps FROM cards WHERE id IN ({marks})", *chunk,
            ))
    check_cancelled()
    return {doc_id: sum(values.get(cid, 0) for cid in card_ids)
            for doc_id, card_ids in cards_by_document.items()}
