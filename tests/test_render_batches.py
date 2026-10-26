from render_batches import build_in_batches


def test_batches_bound_each_callback_and_stop_obsolete_generation():
    pending, rendered, finished = [], [], []
    valid = [True]
    build_in_batches(range(10000), rendered.append, valid=lambda: valid[0],
                     done=lambda: finished.append(True), schedule=pending.append, batch_size=40)
    assert len(rendered) == 40
    pending.pop(0)()
    assert len(rendered) == 80
    valid[0] = False
    pending.pop(0)()
    assert len(rendered) == 80 and not pending and not finished


def test_all_items_remain_reachable_in_order():
    pending, rendered, finished = [], [], []
    build_in_batches(range(105), rendered.append, valid=lambda: True,
                     done=lambda: finished.append(True), schedule=pending.append, batch_size=40)
    while pending:
        pending.pop(0)()
    assert rendered == list(range(105))
    assert finished == [True]
