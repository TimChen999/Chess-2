"""Inspect assassin_bishop's baseline to identify the sword region.

Dumps a pixel-art ASCII representation of the white assassin_bishop
static and saves a 16x-scaled version with coordinate labels so I can
identify which pixels belong to the sword (vs body / mitre / sash).
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

import sys

ROOT = Path(__file__).resolve().parent.parent.parent
TEMP = Path(r"C:\Users\timch\AppData\Local\Temp\assassin_bishop_temp")
OUT = ROOT / "tools/sprites/_inspect_assassin_bishop.png"

FILL = (250, 248, 242)
SHADOW = (210, 208, 200)
HIGHLIGHT = (130, 128, 138)
OUTLINE = (40, 40, 50)
GOLD = (217, 178, 60)
CRIMSON = (190, 60, 72)


def dump_ascii(img):
    """Print a coarse character map showing structure."""
    px = img.load()
    w, h = img.size
    # Build legend.
    print("Legend:")
    print("  '#' = OUTLINE / dark")
    print("  '.' = FILL (cream)")
    print("  's' = SHADOW (light grey)")
    print("  'h' = HIGHLIGHT (mid grey)")
    print("  'g' = gold")
    print("  'r' = crimson")
    print("  '?' = other (likely sword silver / unknown)")
    print("  ' ' = transparent")
    print()
    # Header columns.
    print("    " + "".join(str((c // 10) % 10) for c in range(w)))
    print("    " + "".join(str(c % 10) for c in range(w)))
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 8:
                row.append(" ")
                continue
            if (r, g, b) == OUTLINE:
                row.append("#")
            elif (r, g, b) == FILL:
                row.append(".")
            elif (r, g, b) == SHADOW:
                row.append("s")
            elif (r, g, b) == HIGHLIGHT:
                row.append("h")
            elif abs(r - 217) < 20 and abs(g - 178) < 20 and abs(b - 60) < 20:
                row.append("g")
            elif abs(r - 190) < 30 and abs(g - 60) < 30 and abs(b - 72) < 30:
                row.append("r")
            else:
                row.append("?")
        print(f"{y:2d}: {''.join(row)}")


def render_zoomed():
    src = Image.open(TEMP / "white_static.png").convert("RGBA")
    SCALE = 16
    z = src.resize((src.size[0] * SCALE, src.size[1] * SCALE), Image.NEAREST)
    out = Image.new("RGBA", (z.size[0] + 80, z.size[1] + 40), (240, 240, 230, 255))
    out.paste(z, (40, 20), z)
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
    # Y labels every 4 px
    for y in range(0, src.size[1], 4):
        draw.text((4, 20 + y * SCALE - 6), str(y), fill=(80, 80, 80, 255), font=font)
    # X labels every 4 px
    for x in range(0, src.size[0], 4):
        draw.text((40 + x * SCALE, 4), str(x), fill=(80, 80, 80, 255), font=font)
    out.save(OUT)
    print(f"saved -> {OUT.relative_to(ROOT)}  size={out.size}")


def main():
    print("=" * 60)
    print("assassin_bishop white static (aeaa0be):")
    print("=" * 60)
    src = Image.open(TEMP / "white_static.png").convert("RGBA")
    dump_ascii(src)
    print()
    render_zoomed()


if __name__ == "__main__":
    main()
