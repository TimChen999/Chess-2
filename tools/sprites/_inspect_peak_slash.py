"""Render JUST the F2-F4 peak-slash frames at 16x zoom so we can
inspect the discrete pixel-art bands of the crescent.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
WHITE = ROOT / "godot/assets/sprites/anim/pieces/white"
OUT = ROOT / "tools/sprites/_inspect_peak_slash.png"

PIECES = ["bandit_pawn", "assassin_bishop"]
FRAME_INDICES = [2, 3, 4]  # F2 forming, F3 peak, F4 follow-through
SCALE = 12
FRAME = 64
GAP = 12
LABEL_H = 24


def split(strip, n):
    return [strip.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME)) for i in range(n)]


def upscale(img, s):
    return img.resize((img.size[0] * s, img.size[1] * s), Image.NEAREST)


def render():
    cell_w = FRAME * SCALE
    sheet_w = 80 + 3 * (cell_w + GAP) * 2 + 100
    sheet_h = 40 + (cell_w + LABEL_H + GAP) * len(PIECES)
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (245, 240, 230, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for ri, piece in enumerate(PIECES):
        wpn_strip = Image.open(WHITE / piece / "weapon_attack.png").convert("RGBA")
        body_strip = Image.open(WHITE / piece / "body_attack.png").convert("RGBA")
        wpn_frames = split(wpn_strip, 6)
        body_frames = split(body_strip, 6)

        y = 40 + ri * (cell_w + LABEL_H + GAP)
        draw.text((10, y + cell_w // 2 - 8), piece, fill=(50, 50, 50, 255), font=font)

        for ci, fi in enumerate(FRAME_INDICES):
            comp = Image.alpha_composite(body_frames[fi], wpn_frames[fi])
            up_w = upscale(wpn_frames[fi], SCALE)
            up_c = upscale(comp, SCALE)
            x_w = 80 + ci * 2 * (cell_w + GAP)
            x_c = x_w + cell_w + GAP
            sheet.paste(up_w, (x_w, y), up_w)
            sheet.paste(up_c, (x_c, y), up_c)
            draw.text((x_w, y + cell_w + 4), f"F{fi} weapon", fill=(80, 80, 80, 255), font=font)
            draw.text((x_c, y + cell_w + 4), f"F{fi} composite", fill=(80, 80, 80, 255), font=font)

    sheet.save(OUT)
    print(f"saved -> {OUT.relative_to(ROOT)}  size={sheet.size}")


if __name__ == "__main__":
    render()
