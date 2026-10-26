from bounded_cache import ByteLRU, thumbnail_window


def test_cache_evicts_least_recently_used_bytes_and_replacement_accounting():
    cache = ByteLRU(10)
    cache.put("a", "A", 4)
    cache.put("b", "B", 4)
    assert cache.get("a") == "A"
    cache.put("c", "C", 4)
    assert cache.get("b") is None
    assert cache.bytes_used == 8
    cache.put("a", "new", 8)
    assert cache.bytes_used == 8
    cache.put("huge", "X", 11)
    assert cache.get("huge") is None
    cache.discard("a")
    assert cache.bytes_used == 0


def test_thumbnail_work_depends_on_viewport_and_preserves_stable_order():
    assert list(thumbnail_window(10_000, columns=5, first_row=100, visible_rows=4)) == list(range(495, 525))
    assert list(thumbnail_window(12, columns=5, first_row=0, visible_rows=4)) == list(range(12))
