from datetime import date

def bump(d: dict, key: str, n: int = 1):
    d[key] = int(d.get(key, 0)) + n

def bump_tag(d: dict, tag: str, n: int = 1):
    d[tag] = int(d.get(tag, 0)) + n

def record_done(stats: dict, *, card_type: str, pick_kind: str, subject_tags: list[str]):
    """
    card_type: "topic" | "item"
    pick_kind: "priority" | "random"   (or however you classify)
    subject_tags: list of subject tags that apply (e.g. ["psychology"])
    """
    day = date.today().isoformat()
    daily = stats.setdefault("daily", {}).setdefault(day, {
        "topic": 0, "item": 0, "priority": 0, "random": 0,
        "by_tag": {"topic": {}, "item": {}}
    })

    # lifetime
    bump(stats.setdefault("lifetime", {}), card_type)
    bump(stats["lifetime"], pick_kind)
    stats["lifetime"].setdefault("by_tag", {}).setdefault("topic", {})
    stats["lifetime"]["by_tag"].setdefault("item", {})
    for t in subject_tags:
        bump_tag(stats["lifetime"]["by_tag"][card_type], t)

    # daily
    bump(daily, card_type)
    bump(daily, pick_kind)
    daily["by_tag"].setdefault("topic", {})
    daily["by_tag"].setdefault("item", {})
    for t in subject_tags:
        bump_tag(daily["by_tag"][card_type], t)
