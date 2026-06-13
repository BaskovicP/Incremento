def filter_reviewer_shortcuts(
    shortcuts,
    *,
    state: str,
    hidden_answer_keys: set[str],
    is_on_enter_callback,
):
    if state != "answer" or not hidden_answer_keys:
        return list(shortcuts)

    filtered = []
    for key, callback in shortcuts:
        if is_on_enter_callback(callback):
            filtered.append((key, callback))
            continue
        if isinstance(key, str) and key.lower() == "space":
            filtered.append((key, callback))
            continue
        if isinstance(key, str) and key in hidden_answer_keys:
            continue
        filtered.append((key, callback))
    return filtered
