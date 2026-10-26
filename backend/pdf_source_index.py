"""An operation-owned PDF filename index for reviewer source covers."""
from collections import defaultdict
from concurrent.futures import CancelledError
import os

try:
    from .pdf_manager import PDF_NOTE_TYPE, PDF_COVER_FIELD, _pdf_filename_lookup_key
except ImportError:
    from pdf_manager import PDF_NOTE_TYPE, PDF_COVER_FIELD, _pdf_filename_lookup_key


class PdfSourceIndex:
    def __init__(self, exact, fuzzy):
        self.exact, self.fuzzy = exact, fuzzy

    @classmethod
    def build(cls, col, *, cancel=None):
        ids = col.find_cards(f'note:"{PDF_NOTE_TYPE}"')
        rows = []
        for start in range(0, len(ids), 900):
            if cancel is not None and cancel.is_set():
                raise CancelledError()
            batch = ids[start:start + 900]
            marks = ",".join("?" for _ in batch)
            rows.extend(col.db.all(
                "SELECT c.id,c.nid,n.mid,n.flds FROM cards c JOIN notes n ON n.id=c.nid "
                f"WHERE c.id IN ({marks})", *batch,
            ))
        fields, seen = {}, set()
        exact, fuzzy = {}, defaultdict(dict)
        for cid, nid, mid, raw in sorted(rows, key=lambda row: (row[1], row[0])):
            if cancel is not None and cancel.is_set():
                raise CancelledError()
            if nid in seen:
                continue
            seen.add(nid)
            if mid not in fields:
                fields[mid] = {field["name"]: int(field.get("ord", i))
                               for i, field in enumerate((col.models.get(mid) or {}).get("flds", []))}
            values = str(raw or "").split("\x1f")
            def value(name):
                ordinal = fields[mid].get(name, len(values))
                return values[ordinal].strip() if 0 <= ordinal < len(values) else ""
            filename = os.path.basename(value("PDF_Filename"))
            if not filename:
                continue
            entry = (int(cid), value("Title"), value(PDF_COVER_FIELD))
            exact.setdefault(filename, entry)
            fuzzy[_pdf_filename_lookup_key(filename)][int(cid)] = entry
        return cls(exact, fuzzy)

    def get(self, filename):
        filename = os.path.basename(str(filename or ""))
        if filename in self.exact:
            return self.exact[filename]
        matches = self.fuzzy.get(_pdf_filename_lookup_key(filename), {})
        return next(iter(matches.values())) if len(matches) == 1 else None
