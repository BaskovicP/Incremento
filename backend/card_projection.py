"""Read-only, operation-owned card/note projections. Never use for mutations."""
from types import SimpleNamespace
from concurrent.futures import CancelledError


def supports_projection(col):
    return type(col).__module__ == "anki.collection" and type(col).__name__ == "Collection"


class NoteProjection(dict):
    def __init__(self, nid, model, values, tags):
        self.id, self.mid, self.fields = int(nid), int(model.get("id", 0)), values
        self.tags, self._model = str(tags or "").split(), model
        super().__init__((field["name"], values[ordinal] if ordinal < len(values) else "")
                         for ordinal, field in enumerate(model.get("flds", [])))

    def note_type(self):
        return self._model


class CardProjection(SimpleNamespace):
    def note(self):
        return self._note


class ReadCollection:
    def __init__(self, col, *, cancel=None):
        self.collection, self.cancel = col, cancel
        self.cards, self.notes, self.models_cache = {}, {}, {}

    def __getattr__(self, name):
        return getattr(self.collection, name)

    def load(self, card_ids):
        ids = list(dict.fromkeys(int(cid) for cid in card_ids if int(cid) not in self.cards))
        for start in range(0, len(ids), 900):
            if self.cancel is not None and self.cancel.is_set():
                raise CancelledError()
            chunk = ids[start:start + 900]
            self.cards.update((cid, None) for cid in chunk)
            marks = ",".join("?" for _ in chunk)
            for cid, nid, did, odid, ctype, queue, due, ivl, reps, lapses, mid, flds, tags in self.collection.db.all(
                "SELECT c.id,c.nid,c.did,c.odid,c.type,c.queue,c.due,c.ivl,c.reps,c.lapses,n.mid,n.flds,n.tags "
                f"FROM cards c JOIN notes n ON n.id=c.nid WHERE c.id IN ({marks})", *chunk,
            ):
                if mid not in self.models_cache:
                    self.models_cache[mid] = self.collection.models.get(mid) or {}
                if nid not in self.notes:
                    self.notes[nid] = NoteProjection(nid, self.models_cache[mid], str(flds or "").split("\x1f"), tags)
                self.cards[int(cid)] = CardProjection(
                    id=int(cid), nid=int(nid), did=int(did), odid=int(odid), type=int(ctype),
                    queue=int(queue), due=int(due), ivl=int(ivl), reps=int(reps), lapses=int(lapses),
                    _note=self.notes[nid],
                )

    def get_card(self, cid):
        if int(cid) not in self.cards:
            self.load([int(cid)])
        return self.cards.get(int(cid))

    def get_note(self, nid):
        if int(nid) in self.notes:
            return self.notes[int(nid)]
        return self.collection.get_note(nid)
