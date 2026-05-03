"""Render a 4x-scaled preview sheet showing the attack animation for
each weapon-bearing piece. For each piece we show, in this order:
  - body strip (just the body, no weapon)
  - weapon strip (weapon + swing arc + glow burst)
  - composite (body + weapon overlay) — what the player actually sees

Saved to tools/sprites/_attack_preview.png so the user can compare to
their reference image.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
WHITE = ROOT / "godot/assets/sprites/anim/pieces/white"
OUT = ROOT / "tools/sprites/_attack_preview.png"

PIECES = ["bandit_pawn", "assassin_bishop"]
SCALE = 6
FRAME = 64
GAP = 8
LABEL_H = 20

# Assume bandit_pawn attack has 6 frames (others may differ).
FRAMES_PER_ANIM = 6


def split(strip, n):
    return [strip.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME)) for i in range(n)]


def upscale(img, s):
    return img.resize((img.size[0] * s, img.size[1] * s), Image.NEAREST)


def render():
    sheet_w = 3 * (FRAMES_PER_ANIM * FRAME * SCALE) + 2 * GAP + 60   # 3 columns
    row_h = FRAME * SCALE + LABEL_H
    sheet_h = len(PIECES) * (row_h + GAP) + 30

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (245, 240, 230, 255))

    # Headers
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    col_w = FRAMES_PER_ANIM * FRAME * SCALE
    headers = ["BODY (no weapon)", "WEAPON OVERLAY (arc + glow)", "COMPOSITE (player view)"]
    for ci, h in enumerate(headers):
        x = 60 + ci * (col_w + GAP)
        draw.text((x + col_w // 2 - 90, 4), h, fill=(50, 50, 50, 255), font=font)

    for ri, piece in enumerate(PIECES):
        body_strip = Image.open(WHITE / piece / "body_attack.png").convert("RGBA")
        wpn_strip = Image.open(WHITE / piece / "weapon_attack.png").convert("RGBA")

        body_frames = split(body_strip, FRAMES_PER_ANIM)
        wpn_frames = split(wpn_strip, FRAMES_PER_ANIM)

        # Composite per-frame (body underneath, weapon on top).
        comp_frames = []
        for b, w in zip(body_frames, wpn_frames):
            c = Image.alpha_composite(b, w)
            comp_frames.append(c)

        y_top = 30 + ri * (row_h + GAP)

        # Piece label
        draw.text((4, y_top + (FRAME * SCALE) // 2 - 8), piece,
                  fill=(50, 50, 50, 255), font=font_small)

        for ci, frames in enumerate([body_frames, wpn_frames, comp_frames]):
            x_col = 60 + ci * (col_w + GAP)
            for fi, fr in enumerate(frames):
                up = upscale(fr, SCALE)
                sheet.paste(up, (x_col + fi * FRAME * SCALE, y_top), up)
                # Frame label
                draw.text((x_col + fi * FRAME * SCALE + 4,
                           y_top + FRAME * SCALE - LABEL_H + 4),
                          f"F{fi}", fill=(80, 80, 80, 255), font=font_small)

    sheet.save(OUT)
    print(f"saved -> {OUT.relative_to(ROOT)}  size={sheet.size}")


if __name__ == "__main__":
    render()
