"""Procedurally symmetrize the bishop's silhouette around its centroid x,
then run restyle to get the clean flat-white aesthetic. No PixelLab —
just deterministic geometry, so the original Staunton mitre shape is
kept and the result is guaranteed symmetric.

Per row, the script picks whichever side of the centroid has more
opaque pixels and mirrors that half to the opposite side. Result: each
row is symmetric across the global centroid x.
"""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse the restyle pass for the final clean look.
from restyle import restyle_one  # noqa: E402
from gen_sprites import recolor_to_black  # noqa: E402

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
ALPHA_THRESH = 8


def silhouette_centroid_x(img: Image.Image) -> int:
    w, h = img.size
    px = img.load()
    xs = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > ALPHA_THRESH:
                xs.append(x)
    if not xs:
        return w // 2
    return round(sum(xs) / len(xs))


def symmetrize(img: Image.Image, cx: int) -> Image.Image:
    """Per row, pick the dominant side of cx (more opaque pixels) and
    mirror it to the other side. Output is perfectly symmetric across cx."""
    w, h = img.size
    src = img.load()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dst = out.load()

    for y in range(h):
        left_count = sum(1 for x in range(0, cx) if src[x, y][3] > ALPHA_THRESH)
        right_count = sum(1 for x in range(cx, w) if src[x, y][3] > ALPHA_THRESH)
        # The center column: leave it as-is.
        dst[cx, y] = src[cx, y]
        if left_count >= right_count:
            # mirror left to right
            for dx in range(1, max(cx + 1, w - cx)):
                xl = cx - dx
                xr = cx + dx
                if 0 <= xl < w and 0 <= xr < w:
                    dst[xl, y] = src[xl, y]
                    dst[xr, y] = src[xl, y]
        else:
            # mirror right to left
            for dx in range(1, max(cx + 1, w - cx)):
                xl = cx - dx
                xr = cx + dx
                if 0 <= xl < w and 0 <= xr < w:
                    dst[xr, y] = src[xr, y]
                    dst[xl, y] = src[xr, y]
    return out


def main():
    src = WHITE_DIR / "bishop" / "static.png"
    img = Image.open(src).convert("RGBA")
    cx = silhouette_centroid_x(img)
    print(f"silhouette centroid x = {cx}")

    sym = symmetrize(img, cx)
    # Run the standard restyle pass so the result has the clean flat
    # white + outline + right-edge shadow look.
    final = restyle_one(sym, "bishop")

    final.save(src)
    recolor_to_black(final).save(BLACK_DIR / "bishop" / "static.png")
    print(f"saved {src.relative_to(ROOT)}")
    print(f"saved {(BLACK_DIR / 'bishop' / 'static.png').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
