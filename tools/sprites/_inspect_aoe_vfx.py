"""Render the cannon + debris VFX strips on a dark background to verify
sky-strike behavior:
  - Cannon: 192×704 frame (3 squares wide × 11 tall). Cannonball
    descends through the upper 8 squares; cross-shape explosion fills
    the bottom 3 squares.
  - Debris: 64×640 frame (1 square wide × 10 tall). Rocks descend
    through upper 9 squares; impact + sparkles in the bottom square.

Both should show motion that starts off-canvas-top and lands at the
ground line near the bottom — verifying the "from the sky" read."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
CANNON_SRC = ROOT / "godot/assets/sprites/anim/fx/cannon_resolve.png"
DEBRIS_SRC = ROOT / "godot/assets/sprites/anim/fx/debris_fall.png"
CANNON_OUT = ROOT / "tools/sprites/_inspect_cannon.png"
DEBRIS_OUT = ROOT / "tools/sprites/_inspect_debris.png"

CANNON_FW = 192
CANNON_FH = 192      # post-impact strip — 3sq×3sq cross-AOE bbox only
DEBRIS_FW = 64
DEBRIS_FH = 64       # post-impact strip — single square only

GAP = 6
LABEL_H = 22


def _draw_grid_overlay(canvas: Image.Image, frame_x: int, frame_y: int,
                        fw_disp: int, fh_disp: int, sq_size_disp: int):
    """Draw subtle vertical/horizontal grid lines on each frame so the
    inspector can see where each board square boundary falls."""
    draw = ImageDraw.Draw(canvas)
    n_cols = fw_disp // sq_size_disp
    n_rows = fh_disp // sq_size_disp
    grid_col = (40, 50, 70, 100)
    for c in range(1, n_cols):
        x = frame_x + c * sq_size_disp
        draw.line([(x, frame_y), (x, frame_y + fh_disp)], fill=grid_col, width=1)
    for r in range(1, n_rows):
        y = frame_y + r * sq_size_disp
        draw.line([(frame_x, y), (frame_x + fw_disp, y)], fill=grid_col, width=1)


def render_strip(src: Path, out: Path, frame_w: int, frame_h: int,
                  scale: int, ground_y_src: int, label: str):
    strip = Image.open(src).convert("RGBA")
    n = strip.size[0] // frame_w
    cell_w = frame_w * scale
    cell_h = frame_h * scale
    sheet_w = n * cell_w + (n - 1) * GAP + 30
    sheet_h = cell_h + LABEL_H + 50
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (10, 12, 25, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    draw.text((10, 4), label, fill=(220, 220, 220, 255), font=font)

    sq_size_disp = 64 * scale  # one source-square in display pixels
    for i in range(n):
        f = strip.crop((i * frame_w, 0, (i + 1) * frame_w, frame_h))
        up = f.resize((cell_w, cell_h), Image.NEAREST)
        x = 15 + i * (cell_w + GAP)
        y = 28
        sheet.paste(up, (x, y), up)
        _draw_grid_overlay(sheet, x, y, cell_w, cell_h, sq_size_disp)
        draw.text((x + 4, y + cell_h + 2), f"F{i}",
                  fill=(220, 220, 220, 255), font=font)

    # Ground line
    gy = 28 + ground_y_src * scale
    draw.line([(8, gy), (sheet_w - 8, gy)],
              fill=(80, 90, 120, 255), width=1)
    draw.text((sheet_w - 220, gy - 16), "ground (target sq center / bottom)",
              fill=(80, 90, 120, 255), font=font)

    sheet.save(out)
    print(f"saved -> {out.relative_to(ROOT)}  size={sheet.size}")


def render():
    render_strip(CANNON_SRC, CANNON_OUT, CANNON_FW, CANNON_FH,
                 scale=3, ground_y_src=96,
                 label="CANNON post-impact strip — 192×192 frames; cross explosion expansion + smoke (descent is Godot Y-tween of cannonball.png)")
    render_strip(DEBRIS_SRC, DEBRIS_OUT, DEBRIS_FW, DEBRIS_FH,
                 scale=4, ground_y_src=32,
                 label="DEBRIS post-impact strip — 64×64 frames; dust burst + sparkle spread (descent is Godot Y-tween of debris_rocks.png)")


if __name__ == "__main__":
    render()
