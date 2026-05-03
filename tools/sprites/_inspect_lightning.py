"""Render the lightning_strike.png frames at 6x zoom on a dark
background, for visual review of the sky-strike progression."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "godot/assets/sprites/anim/fx/lightning_strike.png"
OUT = ROOT / "tools/sprites/_inspect_lightning.png"

SCALE = 1            # 10-square-tall canvas — drop scale so it fits
FRAME_W = 64
FRAME_H = 640        # tall frames — 10 squares high
GAP = 6
LABEL_H = 22


def render() -> None:
    strip = Image.open(SRC).convert("RGBA")
    n = strip.size[0] // FRAME_W
    cell_w = FRAME_W * SCALE
    cell_h = FRAME_H * SCALE
    sheet_w = n * cell_w + (n - 1) * GAP + 30
    sheet_h = cell_h + LABEL_H + 30
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (10, 12, 25, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    for i in range(n):
        f = strip.crop((i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_H))
        up = f.resize((cell_w, cell_h), Image.NEAREST)
        x = 15 + i * (cell_w + GAP)
        sheet.paste(up, (x, 18), up)
        draw.text((x + 4, 18 + cell_h + 2), f"F{i}",
                  fill=(220, 220, 220, 255), font=font)

    # Draw a horizontal "ground line" across all frames at the source
    # ground line position (LIGHTNING_GROUND_Y = 628 in source pixels)
    # so the inspector can see where the impact spark lands relative
    # to the bolt — useful to verify the bottom of the sprite is what
    # gets anchored to the target square in Godot.
    ground_y = 18 + 628 * SCALE
    draw.line([(8, ground_y), (sheet_w - 8, ground_y)],
              fill=(80, 90, 120, 255), width=1)
    draw.text((sheet_w - 80, ground_y - 16), "ground (target sq bottom)",
              fill=(80, 90, 120, 255), font=font)

    sheet.save(OUT)
    print(f"saved -> {OUT.relative_to(ROOT)}  size={sheet.size}")


if __name__ == "__main__":
    render()
