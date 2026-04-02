from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


OUT_DIR = Path(__file__).resolve().parent / "icons"
MASTER_SIZE = 512
SIZES = (16, 32, 48, 128)


def _vertical_gradient(size: int, top_rgb: tuple[int, int, int], bottom_rgb: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    px = img.load()
    denom = max(1, size - 1)
    for y in range(size):
        t = y / denom
        r = int(round(top_rgb[0] * (1 - t) + bottom_rgb[0] * t))
        g = int(round(top_rgb[1] * (1 - t) + bottom_rgb[1] * t))
        b = int(round(top_rgb[2] * (1 - t) + bottom_rgb[2] * t))
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    return img


def _rounded_rect_mask(size: int, inset: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((inset, inset, size - inset, size - inset), radius=radius, fill=255)
    return mask


def _draw_icon(size: int = MASTER_SIZE) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    bg = _vertical_gradient(size, (245, 205, 148), (180, 99, 20))
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    highlight_draw.ellipse(
        (-int(size * 0.12), -int(size * 0.18), int(size * 0.72), int(size * 0.52)),
        fill=(255, 248, 232, 78),
    )
    bg = Image.alpha_composite(bg, highlight)

    mask = _rounded_rect_mask(size, inset=int(size * 0.055), radius=int(size * 0.24))
    bg.putalpha(mask)

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (
            int(size * 0.085),
            int(size * 0.10),
            int(size * 0.915),
            int(size * 0.93),
        ),
        radius=int(size * 0.24),
        fill=(71, 46, 17, 170),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=size * 0.03))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(bg)

    draw = ImageDraw.Draw(canvas)

    step_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    step_shadow_draw = ImageDraw.Draw(step_shadow)
    step_shadow_draw.rounded_rectangle(
        (int(size * 0.18), int(size * 0.34), int(size * 0.82), int(size * 0.78)),
        radius=int(size * 0.08),
        fill=(88, 54, 17, 110),
    )
    step_shadow = step_shadow.filter(ImageFilter.GaussianBlur(radius=size * 0.025))
    canvas.alpha_composite(step_shadow, dest=(0, int(size * 0.018)))

    ivory = (255, 248, 236, 255)
    step_radius = int(size * 0.045)
    steps = [
        (0.21, 0.57, 0.38, 0.79),
        (0.40, 0.44, 0.57, 0.79),
        (0.59, 0.31, 0.76, 0.79),
    ]
    for x1, y1, x2, y2 in steps:
        draw.rounded_rectangle(
            (int(size * x1), int(size * y1), int(size * x2), int(size * y2)),
            radius=step_radius,
            fill=ivory,
        )

    line_color = (120, 64, 15, 255)
    line_width = max(8, size // 28)
    points = [
        (int(size * 0.25), int(size * 0.53)),
        (int(size * 0.49), int(size * 0.40)),
        (int(size * 0.68), int(size * 0.28)),
    ]
    draw.line(points, fill=line_color, width=line_width, joint="curve")
    arrow = [
        (int(size * 0.68), int(size * 0.28)),
        (int(size * 0.63), int(size * 0.28)),
        (int(size * 0.71), int(size * 0.21)),
        (int(size * 0.78), int(size * 0.30)),
        (int(size * 0.77), int(size * 0.24)),
        (int(size * 0.72), int(size * 0.33)),
    ]
    draw.polygon(arrow, fill=line_color)

    outline = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    outline_draw = ImageDraw.Draw(outline)
    outline_draw.rounded_rectangle(
        (int(size * 0.055), int(size * 0.055), int(size * 0.945), int(size * 0.945)),
        radius=int(size * 0.24),
        outline=(255, 244, 222, 100),
        width=max(2, size // 96),
    )
    canvas.alpha_composite(outline)

    return canvas


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    master = _draw_icon(MASTER_SIZE)
    master.save(OUT_DIR / "icon-512.png")
    for size in SIZES:
        resized = master.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(OUT_DIR / f"icon-{size}.png")


if __name__ == "__main__":
    main()
