"""Direct conversion of the line-art queen reference to a 64x64 pixel-
art queen sprite in the suite palette.

Pipeline:
  1. Threshold the ref to find black outline pixels.
  2. Flood-fill from the four corners on 'background' (white pixels).
     Everything NOT background is the queen silhouette (outline + interior).
  3. Tight crop to the silhouette bbox, downscale to a 64x64 canvas
     preserving aspect ratio (centered).
  4. Threshold the downscaled image into a clean binary alpha mask.
  5. Procedurally symmetrize the silhouette around the centroid x so
     the 5-crenellation crown reads as bilaterally symmetric.
  6. Run restyle to enforce the suite palette (1px outline + cream fill
     + right-edge shadow band).
  7. Save white + recolor black.
  8. Comprehensive verification.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402
from restyle import restyle_one  # noqa: E402

REF       = ROOT / "tools/sprites/ref_queen.png"
WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
SIZE = 64
ALPHA_THRESH = 8


def silhouette_from_lineart(ref: Image.Image) -> Image.Image:
    """Return an RGBA image same size as ref where queen pixels are
    opaque white and everything else is transparent."""
    w, h = ref.size
    src = ref.load()

    # is_bg: bright pixel (any non-outline pixel). The reference has
    # JPEG noise so we threshold loosely: anything brighter than ~200
    # is bg-ish. The outline is near-black so it'll fall well below.
    def is_bg(x: int, y: int) -> bool:
        r, g, b = src[x, y][:3]
        return r > 200 and g > 200 and b > 200

    visited = [[False] * h for _ in range(w)]
    bg_mask = [[False] * h for _ in range(w)]

    # Seed flood-fill from EVERY border pixel that's bg-ish. Robust
    # against any single corner being corrupted.
    q = deque()
    border = (
        [(x, 0) for x in range(w)]
        + [(x, h - 1) for x in range(w)]
        + [(0, y) for y in range(h)]
        + [(w - 1, y) for y in range(h)]
    )
    for bx, by in border:
        if not visited[bx][by] and is_bg(bx, by):
            visited[bx][by] = True
            bg_mask[bx][by] = True
            q.append((bx, by))

    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if visited[nx][ny]:
                continue
            visited[nx][ny] = True
            if is_bg(nx, ny):
                bg_mask[nx][ny] = True
                q.append((nx, ny))

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            if not bg_mask[x][y]:
                op[x, y] = (255, 255, 255, 255)
    return out


def silhouette_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    w, h = img.size
    px = img.load()
    xs = []; ys = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > ALPHA_THRESH:
                xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def fit_to_canvas(silhouette: Image.Image, target: int,
                  debug_save: Path | None = None) -> Image.Image:
    """Crop to silhouette bbox, scale to fit target × target preserving
    aspect, paste centered on a transparent canvas.

    Uses LANCZOS for the resample then a low alpha threshold (>=32)
    so the thin crown crenellations survive (they read as semi-
    transparent edges after downscale)."""
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
    if debug_save is not None:
        canvas.save(debug_save)
    # Threshold alpha generously so thin features (crenellations) survive
    px = canvas.load()
    for y in range(target):
        for x in range(target):
            r, g, b, a = px[x, y]
            if a < 32:
                px[x, y] = (0, 0, 0, 0)
            else:
                px[x, y] = (255, 255, 255, 255)
    return canvas


def alpha_mask(img):
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def silhouette_centroid_x(mask) -> int:
    w = len(mask); h = len(mask[0])
    xs = [x for y in range(h) for x in range(w) if mask[x][y]]
    if not xs:
        return w // 2
    return round(sum(xs) / len(xs))


def symmetrize(img: Image.Image, cx: int) -> Image.Image:
    """Per row, take the dominant side (more opaque pixels) and mirror
    it. Result is perfectly bilateral around column cx."""
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


def count_crown_peaks(img: Image.Image) -> int:
    """Count the number of peaks in the top profile of the silhouette
    (treating local minima of topmost-y as 'peaks')."""
    w, h = img.size
    mask = alpha_mask(img)
    top_profile = []
    for x in range(w):
        ty = None
        for y in range(h):
            if mask[x][y]:
                ty = y
                break
        top_profile.append(ty if ty is not None else h)
    peaks = 0
    i = 0
    while i < w:
        if top_profile[i] >= h:
            i += 1
            continue
        # walk over a plateau of equal top-y
        j = i
        while j + 1 < w and top_profile[j + 1] == top_profile[i]:
            j += 1
        # a peak = top-y is strictly less than both left and right
        # neighbors of the plateau
        left_y = top_profile[i - 1] if i > 0 else h
        right_y = top_profile[j + 1] if j + 1 < w else h
        if top_profile[i] < left_y and top_profile[i] < right_y:
            peaks += 1
        i = j + 1
    return peaks


def main():
    ref = Image.open(REF).convert("RGBA")
    print(f"ref {ref.size}")

    sil = silhouette_from_lineart(ref)
    bbox = silhouette_bbox(sil)
    print(f"silhouette bbox in ref: {bbox} "
          f"size={bbox[2]-bbox[0]+1}x{bbox[3]-bbox[1]+1}")

    canvas = fit_to_canvas(sil, SIZE)
    mask = alpha_mask(canvas)
    cx = silhouette_centroid_x(mask)
    print(f"centroid x in 64x64 canvas: {cx}")

    sym = symmetrize(canvas, cx)
    peaks_before = count_crown_peaks(canvas)
    peaks_after = count_crown_peaks(sym)
    print(f"crown peaks: {peaks_before} -> {peaks_after} after symmetry")

    # Apply suite palette via restyle
    final = restyle_one(sym, "queen")

    # Verification: the silhouette in `final` must match `sym` exactly
    fm = alpha_mask(final)
    sm = alpha_mask(sym)
    diff = sum(1 for y in range(SIZE) for x in range(SIZE) if fm[x][y] != sm[x][y])
    print(f"silhouette preserved by restyle: {diff} mismatched cells")

    # Bilateral symmetry check
    bd_diff = 0
    op_total = 0
    for y in range(SIZE):
        for x in range(SIZE):
            if fm[x][y]:
                op_total += 1
            mx = 2 * cx - x
            if 0 <= mx < SIZE:
                if fm[x][y] != fm[mx][y]:
                    bd_diff += 1
    print(f"bilateral asymmetry cells: {bd_diff} (out of {op_total} opaque)")

    # Crown peak count (after restyle)
    final_peaks = count_crown_peaks(final)
    print(f"final crown peak count: {final_peaks}")

    final.save(WHITE_DIR / "queen" / "static.png")
    recolor_to_black(final).save(BLACK_DIR / "queen" / "static.png")
    print(f"\nsaved white/queen + black/queen")


if __name__ == "__main__":
    main()
