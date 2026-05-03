"""Render staff-piece attack frames at 8x zoom showing body + weapon +
flash composited together, so we can verify the burst aligns with the
staff tip and isn't cut off.

Each piece gets two rows: one row of the WEAPON OVERLAY ALONE (96x96
flash sprite + 64x64 weapon overlaid in flash coords) and one row of
the COMPOSITE (body + weapon + flash) in 96x96 frame.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
WHITE = ROOT / "godot/assets/sprites/anim/pieces/white"
OUT = ROOT / "tools/sprites/_inspect_staff_flash.png"

PIECES = ["bishop", "king", "queen"]
FRAMES_PER_ANIM = 6
SCALE = 6
F64 = 64
F96 = 96
BUFFER = (F96 - F64) // 2   # 16
GAP = 8
LABEL_H = 22


def split(strip: Image.Image, n: int, frame_w: int) -> list:
    return [strip.crop((i * frame_w, 0, (i + 1) * frame_w, strip.size[1]))
            for i in range(n)]


def upscale(img: Image.Image, s: int) -> Image.Image:
    return img.resize((img.size[0] * s, img.size[1] * s), Image.NEAREST)


def render() -> None:
    # Each row uses 96x96 frames (the flash canvas size).
    cell = F96 * SCALE
    col_w = FRAMES_PER_ANIM * cell
    sheet_w = 110 + 2 * (col_w + GAP) + 30
    row_h = cell + LABEL_H + GAP
    sheet_h = 30 + len(PIECES) * row_h + 10
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (245, 240, 230, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        small = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = ImageFont.load_default()
        small = font

    headers = ["WEAPON + FLASH (96x96 flash canvas, weapon centered)",
               "FULL COMPOSITE (body + weapon + flash)"]
    for ci, h in enumerate(headers):
        x = 110 + ci * (col_w + GAP)
        draw.text((x + col_w // 2 - 220, 4), h, fill=(40, 40, 50, 255), font=font)

    for ri, piece in enumerate(PIECES):
        body_strip = Image.open(WHITE / piece / "body_attack.png").convert("RGBA")
        wpn_strip = Image.open(WHITE / piece / "weapon_attack.png").convert("RGBA")
        flash_strip = Image.open(WHITE / piece / "weapon_flash_attack.png").convert("RGBA")

        body_frames = split(body_strip, FRAMES_PER_ANIM, F64)
        wpn_frames = split(wpn_strip, FRAMES_PER_ANIM, F64)
        flash_frames = split(flash_strip, FRAMES_PER_ANIM, F96)

        # Place each 64x64 weapon/body in the center of a 96x96 frame
        # (so the flash overlay aligns when composited at the same offset).
        weap_in_flash = []
        comp_in_flash = []
        for b, w, f in zip(body_frames, wpn_frames, flash_frames):
            w_canvas = Image.new("RGBA", (F96, F96), (0, 0, 0, 0))
            w_canvas.paste(w, (BUFFER, BUFFER), w)
            w_with_flash = Image.alpha_composite(w_canvas, f)
            weap_in_flash.append(w_with_flash)

            c_canvas = Image.new("RGBA", (F96, F96), (0, 0, 0, 0))
            c_canvas.paste(b, (BUFFER, BUFFER), b)
            c_canvas.paste(w, (BUFFER, BUFFER), w)
            c_with_flash = Image.alpha_composite(c_canvas, f)
            comp_in_flash.append(c_with_flash)

        y_top = 30 + ri * row_h
        draw.text((6, y_top + cell // 2 - 8), piece,
                  fill=(40, 40, 50, 255), font=small)

        for ci, frames in enumerate([weap_in_flash, comp_in_flash]):
            x_col = 110 + ci * (col_w + GAP)
            for fi, fr in enumerate(frames):
                up = upscale(fr, SCALE)
                sheet.paste(up, (x_col + fi * cell, y_top), up)
                draw.text((x_col + fi * cell + 4,
                           y_top + cell + 2),
                          f"F{fi}", fill=(80, 80, 80, 255), font=small)

    sheet.save(OUT)
    print(f"saved -> {OUT.relative_to(ROOT)}  size={sheet.size}")


if __name__ == "__main__":
    render()
