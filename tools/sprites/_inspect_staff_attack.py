"""Render staff-piece attack frames at 10x zoom so the aura ring + raise +
tip burst can be inspected. Bishop / king / queen, all 6 attack frames each,
weapon-overlay + composite columns.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
WHITE = ROOT / "godot/assets/sprites/anim/pieces/white"
OUT = ROOT / "tools/sprites/_inspect_staff_attack.png"

PIECES = ["bishop", "king", "queen"]
SCALE = 10
FRAME = 64
GAP = 8
LABEL_H = 22
N_FRAMES = 6


def split(strip, n):
    return [strip.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME)) for i in range(n)]


def upscale(img, s):
    return img.resize((img.size[0] * s, img.size[1] * s), Image.NEAREST)


def render():
    cell_w = FRAME * SCALE
    col_w = N_FRAMES * cell_w
    sheet_w = 90 + 2 * (col_w + GAP) + 30
    row_h = cell_w + LABEL_H + GAP
    sheet_h = 30 + len(PIECES) * row_h + 10

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (245, 240, 230, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        font_small = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    headers = ["WEAPON OVERLAY (raise + aura + tip burst)", "COMPOSITE (player view)"]
    for ci, h in enumerate(headers):
        x = 90 + ci * (col_w + GAP)
        draw.text((x + col_w // 2 - 180, 4), h, fill=(40, 40, 50, 255), font=font)

    for ri, piece in enumerate(PIECES):
        body_strip = Image.open(WHITE / piece / "body_attack.png").convert("RGBA")
        wpn_strip = Image.open(WHITE / piece / "weapon_attack.png").convert("RGBA")
        body_frames = split(body_strip, N_FRAMES)
        wpn_frames = split(wpn_strip, N_FRAMES)

        comp_frames = [Image.alpha_composite(b, w)
                        for b, w in zip(body_frames, wpn_frames)]

        y_top = 30 + ri * row_h
        draw.text((6, y_top + cell_w // 2 - 8), piece,
                  fill=(40, 40, 50, 255), font=font_small)

        for ci, frames in enumerate([wpn_frames, comp_frames]):
            x_col = 90 + ci * (col_w + GAP)
            for fi, fr in enumerate(frames):
                up = upscale(fr, SCALE)
                sheet.paste(up, (x_col + fi * cell_w, y_top), up)
                draw.text((x_col + fi * cell_w + 4,
                           y_top + cell_w + 2),
                          f"F{fi}", fill=(80, 80, 80, 255), font=font_small)

    sheet.save(OUT)
    print(f"saved -> {OUT.relative_to(ROOT)}  size={sheet.size}")


if __name__ == "__main__":
    render()
