"""Procedurally enforce bilateral symmetry on the queen's crown region
ONLY. Body and base below the crown are byte-identical to the source.

Per row in the crown band, picks the dominant side of the silhouette
centroid x and mirrors it to the opposite side. Then resaves white +
recolors to black."""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402
from restyle import restyle_one  # noqa: E402

WHITE = ROOT / "godot/assets/sprites/anim/pieces/white/queen/static.png"
BLACK = ROOT / "godot/assets/sprites/anim/pieces/black/queen/static.png"
ALPHA_THRESH = 8
CROWN_H = 18  # rows from the top of the silhouette


def alpha_mask(img: Image.Image) -> list[list[bool]]:
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def topmost_y(mask) -> int:
    w = len(mask); h = len(mask[0])
    for y in range(h):
        for x in range(w):
            if mask[x][y]:
                return y
    return 0


def silhouette_centroid_x(mask) -> int:
    w = len(mask); h = len(mask[0])
    xs = [x for y in range(h) for x in range(w) if mask[x][y]]
    if not xs:
        return w // 2
    return round(sum(xs) / len(xs))


def main():
    img = Image.open(WHITE).convert("RGBA")
    w, h = img.size
    mask = alpha_mask(img)
    cx = silhouette_centroid_x(mask)
    top = topmost_y(mask)
    bot = min(h - 1, top + CROWN_H - 1)
    print(f"crown rows {top}..{bot}, centroid x = {cx}")

    src = img.load()
    out = img.copy()
    dst = out.load()

    for y in range(top, bot + 1):
        # Per-row dominant side
        left_count = sum(1 for x in range(0, cx) if src[x, y][3] > ALPHA_THRESH)
        right_count = sum(1 for x in range(cx, w) if src[x, y][3] > ALPHA_THRESH)
        # Center column unchanged
        dst[cx, y] = src[cx, y]
        if left_count >= right_count:
            for dx in range(1, max(cx + 1, w - cx)):
                xl = cx - dx
                xr = cx + dx
                if 0 <= xl < w and 0 <= xr < w:
                    dst[xl, y] = src[xl, y]
                    dst[xr, y] = src[xl, y]
        else:
            for dx in range(1, max(cx + 1, w - cx)):
                xl = cx - dx
                xr = cx + dx
                if 0 <= xl < w and 0 <= xr < w:
                    dst[xr, y] = src[xr, y]
                    dst[xl, y] = src[xr, y]

    # Restyle to enforce the standard palette across the whole queen —
    # this also normalizes any odd colors PixelLab introduced (e.g. the
    # pearl that came out yellow in the last inpaint round).
    final = restyle_one(out, "queen")
    final.save(WHITE)
    recolor_to_black(final).save(BLACK)
    print(f"saved {WHITE.relative_to(ROOT)}")
    print(f"saved {BLACK.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
