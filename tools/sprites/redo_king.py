"""Rescale the existing white king to fit the 64x64 canvas at the same
visual size as the queen/bishop/rook.

Uses the current white/king/static.png as its own 'reference' — same
pipeline as redo_queen.py / redo_rook.py:
  1. Take alpha mask of the existing king (silhouette already clean).
  2. Fit silhouette bbox to 64x64 preserving aspect (LANCZOS).
  3. Threshold alpha back to a binary mask.
  4. Symmetrize around centroid.
  5. Restyle into the suite palette.
  6. Save white + recolor black.

The existing king's cross-on-orb is part of the silhouette (it extends
the alpha mask upward), so it scales with the body — no separate
cross-painting step needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402
from restyle import restyle_one  # noqa: E402

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
SIZE = 64
ALPHA_THRESH = 8


def alpha_mask(img):
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def silhouette_bbox(img):
    w, h = img.size
    px = img.load()
    xs = []; ys = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > ALPHA_THRESH:
                xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def silhouette_only(img: Image.Image) -> Image.Image:
    """Convert to a pure white-on-transparent silhouette so the
    LANCZOS rescale doesn't get confused by the original's color
    detail (outline / fill / cross internal pixels)."""
    w, h = img.size
    src = img.load()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            if src[x, y][3] > ALPHA_THRESH:
                op[x, y] = (255, 255, 255, 255)
    return out


def fit_to_canvas(silhouette: Image.Image, target: int) -> Image.Image:
    x0, y0, x1, y1 = silhouette_bbox(silhouette)
    crop = silhouette.crop((x0, y0, x1 + 1, y1 + 1))
    cw, ch = crop.size
    aspect = cw / ch
    if aspect > 1:
        new_w = target
        new_h = int(target / aspect)
    else:
        new_h = target
        new_w = int(target * aspect)
    crop = crop.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    canvas.paste(crop, ((target - new_w) // 2, (target - new_h) // 2), crop)
    px = canvas.load()
    for y in range(target):
        for x in range(target):
            r, g, b, a = px[x, y]
            if a < 32:
                px[x, y] = (0, 0, 0, 0)
            else:
                px[x, y] = (255, 255, 255, 255)
    return canvas


def silhouette_centroid_x(mask) -> int:
    w = len(mask); h = len(mask[0])
    xs = [x for y in range(h) for x in range(w) if mask[x][y]]
    if not xs:
        return w // 2
    return round(sum(xs) / len(xs))


def symmetrize(img: Image.Image, cx: int) -> Image.Image:
    w, h = img.size
    src = img.load()
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dst = out.load()
    for y in range(h):
        left = sum(1 for x in range(0, cx) if src[x, y][3] > ALPHA_THRESH)
        right = sum(1 for x in range(cx, w) if src[x, y][3] > ALPHA_THRESH)
        dst[cx, y] = src[cx, y]
        if left >= right:
            for d in range(1, max(cx + 1, w - cx)):
                xl = cx - d
                xr = cx + d
                if 0 <= xl < w and 0 <= xr < w:
                    dst[xl, y] = src[xl, y]
                    dst[xr, y] = src[xl, y]
        else:
            for d in range(1, max(cx + 1, w - cx)):
                xl = cx - d
                xr = cx + d
                if 0 <= xl < w and 0 <= xr < w:
                    dst[xr, y] = src[xr, y]
                    dst[xl, y] = src[xr, y]
    return out


def main():
    src_path = WHITE_DIR / "king" / "static.png"
    src = Image.open(src_path).convert("RGBA")
    bbox = silhouette_bbox(src)
    print(f"original silhouette bbox: {bbox} "
          f"size={bbox[2]-bbox[0]+1}x{bbox[3]-bbox[1]+1}")

    sil = silhouette_only(src)
    canvas = fit_to_canvas(sil, SIZE)
    new_bbox = silhouette_bbox(canvas)
    print(f"rescaled silhouette bbox: {new_bbox} "
          f"size={new_bbox[2]-new_bbox[0]+1}x{new_bbox[3]-new_bbox[1]+1}")

    mask = alpha_mask(canvas)
    cx = silhouette_centroid_x(mask)
    print(f"centroid x: {cx}")

    sym = symmetrize(canvas, cx)
    final = restyle_one(sym, "king")

    fm = alpha_mask(final)
    sm = alpha_mask(sym)
    diff = sum(1 for y in range(SIZE) for x in range(SIZE) if fm[x][y] != sm[x][y])
    print(f"silhouette preserved by restyle: {diff} mismatched cells")

    a = alpha_mask(final)
    b = alpha_mask(ImageOps.mirror(final))
    bd_diff = 0; op_total = 0
    for y in range(SIZE):
        for x in range(SIZE):
            if a[x][y]:
                op_total += 1
            if a[x][y] != b[x][y]:
                bd_diff += 1
    print(f"bilateral asymmetry cells: {bd_diff} (out of {op_total} opaque)")

    final.save(src_path)
    recolor_to_black(final).save(BLACK_DIR / "king" / "static.png")
    print(f"\nsaved white/king + black/king")
    final_bbox = silhouette_bbox(final)
    print(f"final silhouette bbox: {final_bbox} "
          f"size={final_bbox[2]-final_bbox[0]+1}x{final_bbox[3]-final_bbox[1]+1}")


if __name__ == "__main__":
    main()
