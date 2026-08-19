from __future__ import annotations

# Dark Material-style colors keep white chip text legible in both Anki themes.
# Profile persistence assigns these major colors without collisions.
_TAG_COLOR_PALETTE = (
    "#1565C0",
    "#C62828",
    "#2E7D32",
    "#6A1B9A",
    "#D84315",
    "#00796B",
    "#AD1457",
    "#3949AB",
    "#9A6700",
    "#00838F",
    "#6D4C41",
    "#455A64",
    "#7B1FA2",
    "#0277BD",
    "#558B2F",
    "#EF6C00",
    "#5E35B1",
    "#00897B",
    "#B71C1C",
    "#33691E",
    "#283593",
    "#8D4B32",
    "#006064",
    "#880E4F",
)

TOPIC_TAG_KEY = "topic"
TOPIC_COLOR_INDEX = 2


def _tag_color_key(tag: str) -> str:
    return str(tag or "").strip().lstrip("#").casefold()


def tag_chip_palette_size() -> int:
    return len(_TAG_COLOR_PALETTE)


def tag_chip_reserved_indexes() -> dict[str, int]:
    return {TOPIC_TAG_KEY: TOPIC_COLOR_INDEX}


def tag_chip_color_for_index(color_index: int) -> str:
    try:
        index = max(0, int(color_index))
    except Exception:
        index = 0
    if index < len(_TAG_COLOR_PALETTE):
        return _TAG_COLOR_PALETTE[index]

    # Encode the extended index injectively into a dark 18-bit RGB cube. Each
    # channel stays in 32..95 for white-text contrast, and the odd multiplier
    # permutes all 262,144 values without repetition.
    ordinal = index - len(_TAG_COLOR_PALETTE)
    encoded = ((ordinal + 1) * 0x2E2A9) & 0x3FFFF
    red = 32 + ((encoded >> 12) & 0x3F)
    green = 32 + ((encoded >> 6) & 0x3F)
    blue = 32 + (encoded & 0x3F)
    return f"#{red:02X}{green:02X}{blue:02X}"


def assign_unique_tag_chip_colors(tags) -> dict[str, str]:
    """Return collision-free colors for one picker when persistence is unavailable."""
    keys: list[str] = []
    for tag in tags or []:
        key = _tag_color_key(tag)
        if key and key not in keys:
            keys.append(key)

    assignments: dict[str, str] = {}
    used_indexes: set[int] = set()
    if TOPIC_TAG_KEY in keys:
        assignments[TOPIC_TAG_KEY] = tag_chip_color_for_index(TOPIC_COLOR_INDEX)
        used_indexes.add(TOPIC_COLOR_INDEX)

    next_index = 0
    for key in keys:
        if key in assignments:
            continue
        while next_index in used_indexes:
            next_index += 1
        assignments[key] = tag_chip_color_for_index(next_index)
        used_indexes.add(next_index)
        next_index += 1
    return assignments


def tag_chip_stylesheet(background: str) -> str:
    background = str(background or _TAG_COLOR_PALETTE[0]).strip()
    try:
        red = int(background[1:3], 16)
        green = int(background[3:5], 16)
        blue = int(background[5:7], 16)
        luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255
    except Exception:
        luminance = 0.0
    foreground = "#111111" if luminance > 0.62 else "#FFFFFF"
    return (
        "QLabel {"
        f" background-color: {background};"
        f" color: {foreground};"
        f" border: 1px solid {background};"
        " border-radius: 9px;"
        " padding: 3px 8px;"
        " font-weight: 600;"
        "}"
    )
