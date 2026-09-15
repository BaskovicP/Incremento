"""Safe persisted annotation colors and their PDF RGB appearance."""
import re

COLORS = {
    'yellow': ([1, 220 / 255, 0], .45), 'green': ([0, 200 / 255, 80 / 255], .4),
    'blue': ([30 / 255, 144 / 255, 1], .4), 'pink': ([1, 80 / 255, 140 / 255], .4),
    'aqua': ([45 / 255, 212 / 255, 191 / 255], .42), 'orange': ([251 / 255, 146 / 255, 60 / 255], .42),
    'red': ([248 / 255, 113 / 255, 113 / 255], .42), 'purple': ([168 / 255, 85 / 255, 247 / 255], .4),
    'snapshot': ([37 / 255, 99 / 255, 235 / 255], .95),
}


def normalize_highlight_color(value: str, *, allow_snapshot: bool = False) -> str:
    color = str(value).strip().lower()
    if color in COLORS and (allow_snapshot or color != 'snapshot'):
        return color
    if re.fullmatch(r'#[0-9a-f]{3}', color):
        return '#' + ''.join(character * 2 for character in color[1:])
    if re.fullmatch(r'#[0-9a-f]{6}', color):
        return color
    raise ValueError('Invalid highlight color')


def highlight_appearance(value: str) -> tuple[list[float], float]:
    color = normalize_highlight_color(value, allow_snapshot=True)
    if color in COLORS:
        return COLORS[color]
    return [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)], .42


def color_from_rgb(rgb: list[float]) -> str:
    for name, (named_rgb, _opacity) in COLORS.items():
        if name != 'snapshot' and all(abs(a - b) < .5 / 255 for a, b in zip(rgb, named_rgb)):
            return name
    return '#' + ''.join(f'{round(channel * 255):02x}' for channel in rgb)
