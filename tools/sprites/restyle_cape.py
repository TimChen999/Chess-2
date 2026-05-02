"""Repaint the bandit_pawn so the cape matches the suite's flat-white
+ outline aesthetic. PixelLab gave us the right CAPE SILHOUETTE
(pawn body + cape extension), but in a different art style — purple
fill, internal lines, etc. We strip all that and re-paint with:

    body pixels (pawn-shaped region)   →  FILL  (cream/white)
    cape pixels (silhouette extension) →  CAPE_FILL (muted grey)
    boundary pixels (silhouette edge)  →  OUTLINE
    inner cape edge (cape over body)   →  OUTLINE (so the cape outline
                                         is visible against the body)
    rightmost interior of each row     →  SHADOW (the standard right-
                                         edge shadow band that other
                                         pieces have)

The pawn-region mask is taken from the current white/pawn/static.png so
the body matches the actual pawn sprite pixel for pixel.
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

# Palette — same as restyle.py for body, plus a muted grey cape fill
# that is in-palette but clearly darker than body so the cape reads.
OUTLINE   = (40, 40, 50, 255)
FILL      = (250, 248, 242, 255)
SHADOW    = (210, 208, 200, 255)
CAPE_FILL = (162, 158, 150, 255)
CAPE_SHADOW = (138, 134, 126, 255)


def alpha_mask(img: Image.Image) -> list[list[bool]]:
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def is_outline(mask, x, y) -> bool:
    w = len(mask); h = len(mask[0])
    if not mask[x][y]:
        return False
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h):
            return True
        if not mask[nx][ny]:
            return True
    return False


def main():
    pawn = Image.open(WHITE_DIR / "pawn" / "static.png").convert("RGBA")
    bandit = Image.open(WHITE_DIR / "bandit_pawn" / "static.png").convert("RGBA")
    if pawn.size != bandit.size:
        sys.exit("size mismatch between pawn and bandit_pawn")

    body_mask = alpha_mask(pawn)        # pawn-only silhouette
    full_mask = alpha_mask(bandit)      # pawn + cape silhouette
    w, h = bandit.size

    # cape_mask = pixels in bandit but NOT in pawn (silhouette extension)
    cape_mask = [[full_mask[x][y] and not body_mask[x][y]
                  for y in range(h)] for x in range(w)]

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()

    # Pass 1: paint outline + body fill + cape fill
    for y in range(h):
        for x in range(w):
            if not full_mask[x][y]:
                continue
            if is_outline(full_mask, x, y):
                op[x, y] = OUTLINE
                continue
            if cape_mask[x][y]:
                op[x, y] = CAPE_FILL
            else:
                op[x, y] = FILL

    # Pass 2: inner-cape outline so the cape's edge is visible against
    # the body. A pixel is on the inner cape edge if it's BODY but
    # adjacent to a CAPE pixel (or vice versa).
    inner_outline = []
    for y in range(h):
        for x in range(w):
            if not full_mask[x][y]:
                continue
            this_is_cape = cape_mask[x][y]
            this_is_body = body_mask[x][y]
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if not full_mask[nx][ny]:
                    continue
                neigh_cape = cape_mask[nx][ny]
                neigh_body = body_mask[nx][ny]
                # Body pixel adjacent to cape pixel = inner edge.
                # We darken the BODY side so the cape silhouette is
                # outlined against the body.
                if this_is_body and neigh_cape:
                    inner_outline.append((x, y))
                    break
    for x, y in inner_outline:
        op[x, y] = OUTLINE

    # Pass 3: right-edge shadow band per row (same logic as restyle.py).
    # Body and cape each get their own right-edge shadow because their
    # rows can extend to different right-most pixels.
    for y in range(h):
        # body interior pixels (FILL)
        body_xs = [x for x in range(w) if op[x, y] == FILL]
        for x in body_xs[-2:]:
            op[x, y] = SHADOW
        # cape interior pixels (CAPE_FILL)
        cape_xs = [x for x in range(w) if op[x, y] == CAPE_FILL]
        for x in cape_xs[-2:]:
            op[x, y] = CAPE_SHADOW

    out.save(WHITE_DIR / "bandit_pawn" / "static.png")
    recolor_to_black(out).save(BLACK_DIR / "bandit_pawn" / "static.png")
    print(f"saved {(WHITE_DIR / 'bandit_pawn' / 'static.png').relative_to(ROOT)}")
    print(f"saved {(BLACK_DIR / 'bandit_pawn' / 'static.png').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
