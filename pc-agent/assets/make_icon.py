from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SCALE = SIZE / 64
ACCENT = (52, 211, 153)
BACKGROUND = (18, 18, 21, 255)
BORDER = (39, 39, 42, 255)
PULSE = ((10, 38), (19, 38), (25, 21), (33, 47), (41, 29), (47, 38), (54, 38))

image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
inset = round(2 * SCALE)
draw.rounded_rectangle(
    (inset, inset, SIZE - inset - 1, SIZE - inset - 1),
    radius=round(14 * SCALE),
    fill=BACKGROUND,
    outline=BORDER,
    width=max(2, round(2 * SCALE)),
)
draw.line(
    [(round(x * SCALE), round(y * SCALE)) for x, y in PULSE],
    fill=ACCENT,
    width=round(5 * SCALE),
    joint="curve",
)

target = Path(__file__).resolve().parent / "framepulse.ico"
image.save(target, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.resize((256, 256), Image.LANCZOS).save(target.with_suffix(".png"), format="PNG")
print(f"Saved {target} ({target.stat().st_size} B)")
