"""Restyle all white piece statics to a unified flat-white look while
keeping each piece's silhouette PIXEL-IDENTICAL to the original. Then
recolor each new white sprite to its black sibling.

Style:
  - 1px dark outline along the silhouette boundary
  - mostly solid white interior with a light right-edge shadow band for
    minimal volume cue
  - bishop & assassin_bishop also get a small dark cross painted on the
    mitre face

Verification:
  - After redraw we compare the binary alpha mask of the new sprite to
    the original. They must match exactly (within an alpha threshold).
  - If any piece fails verification we abort with a diff count so we can
    debug — no half-broken art gets written to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"

PIECES = [
    "pawn", "rook", "knight", "bishop", "queen", "king",
    "bandit_pawn", "alter_knight", "assassin_bishop",
]

ALPHA_THRESH = 8

# Palette
OUTLINE = (40, 40, 50, 255)
FILL    = (250, 248, 242, 255)
SHADOW  = (210, 208, 200, 255)
# Feature accents — used for cape & sword internals so they read as
# distinct elements painted *on* the white silhouette without changing
# its outer shape.
CAPE_FILL    = (108, 60, 60, 255)
CAPE_SHADOW  = (78, 40, 42, 255)
SWORD_DARK   = (60, 60, 70, 255)

# Pieces that get a dark cross painted on the mitre face.
CROSS_PIECES = {"bishop", "assassin_bishop"}


def silhouette_mask(img: Image.Image) -> list[list[bool]]:
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def is_outline(mask: list[list[bool]], x: int, y: int) -> bool:
    """True if (x,y) is in the silhouette but has at least one neighbor
    (4-connectivity, with the canvas border counting as transparent) that
    is OUT of the silhouette."""
    w = len(mask)
    h = len(mask[0])
    if not mask[x][y]:
        return False
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h):
            return True
        if not mask[nx][ny]:
            return True
    return False


def restyle_one(orig: Image.Image, piece_id: str) -> Image.Image:
    w, h = orig.size
    mask = silhouette_mask(orig)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()

    # Pass 1: outline + plain fill
    for y in range(h):
        for x in range(w):
            if not mask[x][y]:
                continue
            if is_outline(mask, x, y):
                op[x, y] = OUTLINE
            else:
                op[x, y] = FILL

    # Pass 2: right-edge shadow band per row (1-2 pixels of FILL closest
    # to the right outline get SHADOW). This gives subtle volume without
    # adding internal detail.
    for y in range(h):
        # Find indices in this row that are interior (FILL). Walk from the
        # right and convert up to 2 contiguous fill pixels to SHADOW.
        row_fill_xs = [x for x in range(w) if op[x, y] == FILL]
        if not row_fill_xs:
            continue
        for x in row_fill_xs[-2:]:
            op[x, y] = SHADOW

    # Pass 3: piece-specific feature painting is now handled by
    # tools/sprites/refine_features.py via PixelLab so the added details
    # match the suite's pixel-art aesthetic. restyle.py only does the
    # silhouette-preserving repaint.
    return out


def paint_cape(img: Image.Image, mask: list[list[bool]]) -> None:
    """Paint a burgundy cape draped from the shoulders down the right
    side of the body. The cape stays inside the silhouette — its edge
    is a curved dark line that gives the impression of fabric draping
    behind/over the body. Outline pixels are never overwritten."""
    w, h = img.size
    px = img.load()
    top_y = next((y for y in range(h)
                  for x in range(w) if mask[x][y]), None)
    bot_y = next((y for y in range(h - 1, -1, -1)
                  for x in range(w) if mask[x][y]), None)
    if top_y is None:
        return
    # Cape spans from a bit below the head to the base. Pawn head ends
    # ~20% of the silhouette height from the top; cape starts there.
    full_h = bot_y - top_y
    cape_top = top_y + max(8, int(full_h * 0.30))
    cape_bot = bot_y - max(2, int(full_h * 0.08))
    for y in range(cape_top, cape_bot + 1):
        xs = [x for x in range(w) if mask[x][y]]
        if not xs:
            continue
        left, right = xs[0], xs[-1]
        width = right - left + 1
        # Cape covers the right ~60% of the body width at this row.
        cape_left = left + max(1, width // 3)
        for x in range(cape_left, right + 1):
            # Skip outline pixels so the silhouette boundary stays dark.
            if px[x, y] == OUTLINE:
                continue
            # Darken right edge of cape further to suggest fold.
            if x >= right - 1:
                px[x, y] = CAPE_SHADOW
            else:
                px[x, y] = CAPE_FILL
        # Cape's leading edge (left boundary of cape area) gets one dark
        # pixel to make the drape edge readable.
        if cape_left > left and px[cape_left - 1, y] != OUTLINE:
            # darken just one pixel as the cape's front edge
            px[cape_left, y] = CAPE_SHADOW


def paint_sword(img: Image.Image, mask: list[list[bool]]) -> None:
    """Paint a sheathed sword behind the assassin bishop's body: a thin
    vertical dark column down the body's center line (the sheath) plus
    a short horizontal cross-guard near the collar (where the hilt
    intersects the body)."""
    w, h = img.size
    px = img.load()
    top_y = next((y for y in range(h)
                  for x in range(w) if mask[x][y]), None)
    bot_y = next((y for y in range(h - 1, -1, -1)
                  for x in range(w) if mask[x][y]), None)
    if top_y is None:
        return
    full_h = bot_y - top_y
    # Sword starts just above the collar and runs down to the base.
    sword_top = top_y + max(10, int(full_h * 0.30))
    sword_bot = bot_y - 1
    # Center column of the body — sample a row in the lower body to find
    # its horizontal midpoint, since the mitre's center may be narrower.
    sample_y = top_y + int(full_h * 0.65)
    xs = [x for x in range(w) if mask[x][sample_y]]
    if not xs:
        return
    cx = (xs[0] + xs[-1]) // 2
    # Vertical sheath (1-pixel wide, just to the right of center so the
    # cross is still visible on the mitre).
    sx = cx + 1
    for y in range(sword_top, sword_bot + 1):
        if 0 <= sx < w and mask[sx][y] and px[sx, y] != OUTLINE:
            px[sx, y] = SWORD_DARK
    # Cross-guard: short horizontal bar at sword_top, 5 pixels wide.
    for dx in range(-2, 3):
        x = sx + dx
        if 0 <= x < w and mask[x][sword_top] and px[x, sword_top] != OUTLINE:
            px[x, sword_top] = SWORD_DARK


def paint_bishop_cross(img: Image.Image, mask: list[list[bool]]) -> None:
    """Paint a small plus-sign cross on the mitre face. The mitre is the
    upper teardrop region; we place the cross at ~25% of the silhouette
    height from the top, horizontally centered for that row."""
    w, h = img.size
    # Top of silhouette
    top_y = next((y for y in range(h)
                  for x in range(w) if mask[x][y]), None)
    bot_y = next((y for y in range(h - 1, -1, -1)
                  for x in range(w) if mask[x][y]), None)
    if top_y is None:
        return
    # Aim for the upper portion of the head: ~28% down the piece's height.
    full_h = bot_y - top_y
    cy = top_y + max(5, int(full_h * 0.18))
    # Horizontal center at row cy
    xs = [x for x in range(w) if mask[x][cy]]
    if len(xs) < 3:
        return
    cx = (xs[0] + xs[-1]) // 2

    # Cross dims: 5px tall vertical bar, 5px wide horizontal bar.
    px = img.load()
    for dy in range(-2, 3):
        ny = cy + dy
        if 0 <= ny < h and mask[cx][ny]:
            px[cx, ny] = OUTLINE
    for dx in range(-2, 3):
        nx = cx + dx
        if 0 <= nx < w and mask[nx][cy]:
            px[nx, cy] = OUTLINE


def silhouette_diff(a: Image.Image, b: Image.Image) -> int:
    if a.size != b.size:
        return 10**9
    ap = a.load(); bp = b.load()
    w, h = a.size
    diff = 0
    for y in range(h):
        for x in range(w):
            ao = ap[x, y][3] > ALPHA_THRESH
            bo = bp[x, y][3] > ALPHA_THRESH
            if ao != bo:
                diff += 1
    return diff


def main():
    failed = []
    for piece in PIECES:
        wp = WHITE_DIR / piece / "static.png"
        if not wp.exists():
            print(f"[skip] {piece}: missing white static.png")
            continue
        orig = Image.open(wp).convert("RGBA")
        new = restyle_one(orig, piece)
        diff = silhouette_diff(orig, new)
        status = "OK" if diff == 0 else f"FAIL ({diff} mismatched alpha cells)"
        print(f"[{piece}] silhouette {status}")
        if diff != 0:
            failed.append((piece, diff))
            continue
        new.save(wp)
        bp = BLACK_DIR / piece / "static.png"
        bp.parent.mkdir(parents=True, exist_ok=True)
        recolor_to_black(new).save(bp)
        print(f"   white -> {wp.relative_to(ROOT)}")
        print(f"   black -> {bp.relative_to(ROOT)}")

    if failed:
        print("\nFAILURES:")
        for p, d in failed:
            print(f"  {p}: {d}")
        sys.exit(1)
    print("\nAll silhouettes preserved.")


if __name__ == "__main__":
    main()
