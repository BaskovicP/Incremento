try:
    from .db import get_connection
except ImportError:
    from db import get_connection  # test environment (backend/ on sys.path)


_DEFAULT_PRIORITY_LOWER_IS_MORE_IMPORTANT = True


def configured_priority_lower_is_more_important(config: dict | None = None) -> bool:
    """Return whether lower stored priority values should rank ahead of higher ones."""
    if config is None:
        try:
            from aqt import mw

            addon_name = __name__.split(".")[0]
            config = mw.addonManager.getConfig(addon_name) or {}
        except Exception:
            config = {}
    return bool(
        (config or {}).get(
            "priority_lower_is_more_important",
            _DEFAULT_PRIORITY_LOWER_IS_MORE_IMPORTANT,
        )
    )


def get_priority(addon_dir: str, card_id: int) -> float:
    """Return stored card priority (0.0–100.0). Default 50.0."""
    row = get_connection(addon_dir).execute(
        "SELECT priority FROM priorities WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else 50.0


def set_priority(addon_dir: str, card_id: int, priority: float) -> None:
    """Persist priority (0.0–100.0, stored to 4 decimal places)."""
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT OR REPLACE INTO priorities (card_id, priority) VALUES (?, ?)",
        (card_id, round(float(priority), 4)),
    )
    conn.commit()


def get_all_priorities(addon_dir: str) -> dict[int, float]:
    """Return all stored priorities as {card_id: priority}. Useful for bulk scheduler reads."""
    rows = get_connection(addon_dir).execute(
        "SELECT card_id, priority FROM priorities"
    ).fetchall()
    return {r[0]: r[1] for r in rows}
