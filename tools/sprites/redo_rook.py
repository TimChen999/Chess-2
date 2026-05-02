"""Direct conversion of the line-art rook reference to a 64x64 pixel-
art rook sprite in the suite palette.

Same pipeline as redo_queen.py: flood-fill background → silhouette →
fit to canvas → symmetrize → restyle.

Crenellations: the reference rook has 3 teeth on top with 2 valleys
between. We use a low alpha threshold (>=32) on the LANCZOS downscale
so these thin features survive.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402
from restyle import restyle_one  # noqa: E402

REF       = ROOT / "tools/sprites/ref_rook.png"
WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
SIZE = 64
ALPHA_THRESH = 8


def silhouette_from_lineart(ref: Image.Image) -> Image.Image:
    w, h = ref.size
    src = ref.load()

    def is_bg(x: int, y: int) -> bool:
        r, g, b = src[x, y][:3]
        return r > 200 and g > 200 and b > 200

    visited = [[False] * h for _ in range(w)]
    bg_mask = [[False] * h for _ in range(w)]
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

    # Build the silhouette image, then keep only the LARGEST connected
    # component (drops the alamy watermark and 'RT27NX' tag).
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for y in range(h):
        for x in range(w):
            if not bg_mask[x][y]:
                op[x, y] = (255, 255, 255, 255)
    return keep_largest_component(out)


def keep_largest_component(img: Image.Image) -> Image.Image:
    w, h = img.size
    px = img.load()
    visited = [[False] * h for _ in range(w)]
    best_size = 0
    best_pixels: list[tuple[int, int]] = []
    for sy in range(h):
        for sx in range(w):
            if visited[sx][sy] or px[sx, sy][3] <= ALPHA_THRESH:
                continue
            # BFS
            comp = []
            q = deque([(sx, sy)])
            visited[sx][sy] = True
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < w and 0 <= ny < h):
                        continue
                    if visited[nx][ny] or px[nx, ny][3] <= ALPHA_THRESH:
                        continue
                    visited[nx][ny] = True
                    q.append((nx, ny))
            if len(comp) > best_size:
                best_size = len(comp)
                best_pixels = comp
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for x, y in best_pixels:
        op[x, y] = (255, 255, 255, 255)
    print(f"  kept largest connected component: {best_size} pixels")
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


def count_crenellations(img: Image.Image) -> int:
    """Count crenellation teeth on the top of the silhouette by detecting
    transitions from opaque to transparent in the topmost pixels of
    each column."""
    w, h = img.size
    mask = alpha_mask(img)
    top_y = []
    for x in range(w):
        ty = None
        for y in range(h):
            if mask[x][y]:
                ty = y; break
        top_y.append(ty if ty is not None else h)
    # Look at the top edge: find rows where top_y is at a local min
    teeth = 0
    i = 0
    while i < w:
        if top_y[i] >= h:
            i += 1
            continue
        j = i
        while j + 1 < w and top_y[j + 1] == top_y[i]:
            j += 1
        left = top_y[i - 1] if i > 0 else h
        right = top_y[j + 1] if j + 1 < w else h
        if top_y[i] < left and top_y[i] < right:
            teeth += 1
        i = j + 1
    return teeth


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
    teeth_before = count_crenellations(canvas)
    teeth_after = count_crenellations(sym)
    print(f"crenellations: {teeth_before} -> {teeth_after} after symmetry")

    final = restyle_one(sym, "rook")

    fm = alpha_mask(final)
    sm = alpha_mask(sym)
    diff = sum(1 for y in range(SIZE) for x in range(SIZE) if fm[x][y] != sm[x][y])
    print(f"silhouette preserved by restyle: {diff} mismatched cells")

    bd_diff = 0
    op_total = 0
    a_mask = alpha_mask(final)
    b_mask = alpha_mask(ImageOps.mirror(final))
    for y in range(SIZE):
        for x in range(SIZE):
            if a_mask[x][y]:
                op_total += 1
            if a_mask[x][y] != b_mask[x][y]:
                bd_diff += 1
    print(f"bilateral asymmetry cells: {bd_diff} (out of {op_total} opaque)")

    final_teeth = count_crenellations(final)
    print(f"final crenellation count: {final_teeth}")

    final.save(WHITE_DIR / "rook" / "static.png")
    recolor_to_black(final).save(BLACK_DIR / "rook" / "static.png")
    print(f"\nsaved white/rook + black/rook")


if __name__ == "__main__":
    main()
