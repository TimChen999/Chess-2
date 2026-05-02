"""Procedurally add a small dark SWORD HILT to the assassin_bishop's
upper body. The bishop already fills its 64x64 canvas vertically, so
the hilt is painted ON the body (an internal feature) rather than
extending the silhouette upward.

The hilt is a tiny ⊥ shape — pommel + grip + cross-guard at the bottom
— positioned above the body collar, slightly right of center. The
distinguishing feature vs. the bishop's cross (which has its cross-bar
in the middle) is that the hilt has its cross-bar at the BOTTOM.

   #       pommel (1 px)
   #       grip (2 px)
  ###      cross-guard (3 px)

Total: 6 dark pixels in the suite OUTLINE color, matching the visual
weight of the bishop's cross on the mitre.
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
ALPHA_THRESH = 8
OUTLINE = (40, 40, 50, 255)


def alpha_mask(img):
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def topmost_y(mask):
    w = len(mask); h = len(mask[0])
    for y in range(h):
        for x in range(w):
            if mask[x][y]:
                return y
    return 0


def bottom_y(mask) -> int:
    w = len(mask); h = len(mask[0])
    for y in range(h - 1, -1, -1):
        if any(mask[x][y] for x in range(w)):
            return y
    return h - 1


def main():
    bishop = Image.open(WHITE_DIR / "bishop" / "static.png").convert("RGBA")
    w, h = bishop.size
    mask = alpha_mask(bishop)
    top_y = topmost_y(mask)
    bot_y = bottom_y(mask)
    full_h = bot_y - top_y
    print(f"silhouette rows {top_y}..{bot_y}")

    # Place the hilt at ~42% of the silhouette height — that's the
    # upper-body / shoulder area, well below the mitre. The bishop's
    # body is widest there so the 3-px cross-guard fits comfortably.
    hilt_y = top_y + int(full_h * 0.42)
    body_xs = [x for x in range(w) if mask[x][hilt_y]]
    if not body_xs:
        # Fall back to the next opaque row below
        for y in range(hilt_y, bot_y + 1):
            xs = [x for x in range(w) if mask[x][y]]
            if xs:
                hilt_y = y
                body_xs = xs
                break
    body_cx = (body_xs[0] + body_xs[-1]) // 2
    body_width = body_xs[-1] - body_xs[0] + 1
    # Place hilt 1 column right of body center: barely off-center so
    # the sword reads as 'on the side' yet stays well inside the body
    # interior at every row, including rows below where the body
    # narrows. The previous offset (body_width//4) put the column on
    # the right outline at narrower rows, hiding the sheath as a no-op
    # over already-dark outline pixels.
    hx = body_cx + 1
    print(f"hilt anchor x={hx} y={hilt_y} (body cx={body_cx} width={body_width})")

    out = bishop.copy()
    op = out.load()

    def paint_if_inside(x, y):
        """Paint OUTLINE at (x,y) only if it's inside the bishop
        silhouette — keeps the hilt as an INTERNAL feature, not a
        silhouette extension."""
        if 0 <= x < w and 0 <= y < h and mask[x][y]:
            op[x, y] = OUTLINE

    # The sword reads as a vertical column running along the body with
    # a small cross-guard near the top — that's the clearest pixel-art
    # representation of "sword strapped to body" we can fit in this
    # space. Layout (relative to hilt_y, which sits at ~42% down):
    #
    #     ###     cross-guard (3 px) at hilt_y
    #      #      grip (1 px above)
    #      #      sheath top
    #      #
    #      #      sheath body — runs down ~10 px
    #      #
    #      #
    #
    # cross-guard: 5 px wide for visibility at sprite scale
    cg_y = hilt_y
    for ddx in range(-2, 3):
        paint_if_inside(hx + ddx, cg_y)
    # grip (1 px above cross-guard)
    paint_if_inside(hx, cg_y - 1)
    # pommel (1 px at top of grip)
    paint_if_inside(hx, cg_y - 2)
    # sheath running downward — clamps to the body silhouette
    sheath_len = 14
    for ddy in range(1, sheath_len + 1):
        paint_if_inside(hx, cg_y + ddy)

    out.save(WHITE_DIR / "assassin_bishop" / "static.png")
    recolor_to_black(out).save(BLACK_DIR / "assassin_bishop" / "static.png")
    print(f"saved {(WHITE_DIR / 'assassin_bishop' / 'static.png').relative_to(ROOT)}")
    print(f"saved {(BLACK_DIR / 'assassin_bishop' / 'static.png').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
