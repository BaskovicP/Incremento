"""Small, byte-budgeted derived-image cache and viewport scheduling rules."""
from collections import OrderedDict


class ByteLRU:
    def __init__(self, max_bytes: int):
        self.max_bytes = max(0, int(max_bytes))
        self.bytes_used = 0
        self._values = OrderedDict()

    def __contains__(self, key):
        return key in self._values

    def get(self, key, default=None):
        record = self._values.get(key)
        if record is None:
            return default
        self._values.move_to_end(key)
        return record[0]

    def put(self, key, value, size: int):
        self.discard(key)
        size = max(0, int(size))
        if size > self.max_bytes:
            return
        while self._values and self.bytes_used + size > self.max_bytes:
            _, (_, old_size) = self._values.popitem(last=False)
            self.bytes_used -= old_size
        self._values[key] = (value, size)
        self.bytes_used += size

    def discard(self, key):
        record = self._values.pop(key, None)
        if record is not None:
            self.bytes_used -= record[1]


def thumbnail_window(count: int, *, columns: int, first_row: int, visible_rows: int):
    columns = max(1, columns)
    return range(max(0, first_row - 1) * columns,
                 min(count, (max(0, first_row) + max(1, visible_rows) + 1) * columns))
