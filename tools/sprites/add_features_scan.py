"""Scan-match the user's marker reference (ref_bishop_markers.png) to
paint:
  - the bishop's cross (embossed 2-line thick: highlight + shadow)
  - the assassin_bishop's stylized sword (pommel + grip + cross-guard
    + fullered blade with shading; can extend outside the body)

Scan-match drives positions/sizes; the actual pixel design is enforced
to be symmetric and pixel-clean (the marker lines are anti-aliased
over many ref pixels, so direct per-pixel mapping yields lopsided
results).

Verification: for each painted feature we report the centroid, bbox,
and pixel-by-pixel comparison to the marker bbox.
"""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402

REF       = ROOT / "tools/sprites/ref_bishop_markers.png"
WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
ALPHA_THRESH = 8

OUTLINE   = (40, 40, 50, 255)     # dark / shadow side
HIGHLIGHT = (130, 128, 138, 255)  # medium grey / lit side


def alpha_mask(img):
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def silhouette_bbox(img):
    w, h = img.size
    mask = alpha_mask(img)
    xs = [x for y in range(h) for x in range(w) if mask[x][y]]
    ys = [y for y in range(h) for x in range(w) if mask[x][y]]
    return min(xs), min(ys), max(xs), max(ys)


def navy_frame_bbox(ref):
    w, h = ref.size
    px = ref.load()
    xs = []; ys = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y][:3]
            if r < 50 and g < 50 and b < 50:
                xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def ref_bishop_bbox(ref):
    fx0, fy0, fx1, fy1 = navy_frame_bbox(ref)
    px = ref.load()
    xs = []; ys = []
    for y in range(fy0, fy1 + 1):
        for x in range(fx0, fx1 + 1):
            r, g, b = px[x, y][:3]
            if (r + g + b) // 3 > 100:
                xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def find_color_pixels(ref, predicate):
    w, h = ref.size
    px = ref.load()
    out = []
    for y in range(h):
        for x in range(w):
            if predicate(*px[x, y][:3]):
                out.append((x, y))
    return out


def is_red(r, g, b):
    return r > 180 and g < 80 and b < 80


def is_orange(r, g, b):
    return r > 200 and 100 < g < 200 and b < 60


def marker_bbox_in_sprite(pixels, paste_x, paste_y, scale):
    """Return (x0, y0, x1, y1) in sprite coords (rounded, inclusive)."""
    xs = [(p[0] - paste_x) / scale for p in pixels]
    ys = [(p[1] - paste_y) / scale for p in pixels]
    return round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))


def widest_row_y(pixels, paste_x, paste_y, scale):
    """Sprite-y row of the marker that has the widest horizontal span
    (= where the cross's horizontal arm or sword's cross-guard sits)."""
    rows: dict[int, list[int]] = {}
    for x, y in pixels:
        sy = round((y - paste_y) / scale)
        sx = round((x - paste_x) / scale)
        rows.setdefault(sy, []).append(sx)
    return max(rows, key=lambda yy: max(rows[yy]) - min(rows[yy]))


def main():
    ref = Image.open(REF).convert("RGBA")
    bishop = Image.open(WHITE_DIR / "bishop" / "static.png").convert("RGBA")

    rx0, ry0, rx1, ry1 = ref_bishop_bbox(ref)
    sx0, sy0, sx1, sy1 = silhouette_bbox(bishop)
    rw, rh = rx1 - rx0 + 1, ry1 - ry0 + 1
    sw, sh = sx1 - sx0 + 1, sy1 - sy0 + 1
    scale = min(rw / sw, rh / sh)
    paste_x = rx0 - sx0 * scale
    paste_y = ry0 - sy0 * scale
    print(f"scale={scale:.3f}, paste=({paste_x:.1f}, {paste_y:.1f})")

    bw, bh = bishop.size
    bishop_mask = alpha_mask(bishop)

    # =====================================================================
    # Cross: bbox-driven, 2-line thick, embossed (HIGHLIGHT + OUTLINE)
    # =====================================================================
    red = find_color_pixels(ref, is_red)
    if not red:
        sys.exit("no red marker found")
    cx0, cy0, cx1, cy1 = marker_bbox_in_sprite(red, paste_x, paste_y, scale)
    arm_y = widest_row_y(red, paste_x, paste_y, scale)
    # Snap the cross's OUTLINE column to the bishop's actual mitre
    # center (so the cross looks centered ON the bishop, not on the
    # marker — which can be ~half a sprite-pixel off due to anti-
    # aliasing of the marker drawing).
    mitre_xs = []
    for y in range(cy0, arm_y + 1):
        for x in range(bw):
            if bishop_mask[x][y]:
                mitre_xs.append(x)
    mitre_xs.sort()
    mitre_cx = mitre_xs[len(mitre_xs) // 2]  # median column
    v_right = mitre_cx
    v_left = v_right - 1
    cross_h = cy1 - cy0 + 1
    cross_w = cx1 - cx0 + 1
    # Horizontal arm: same total width as the marker, centered on the
    # 2-wide vertical bar (i.e., extends (cross_w-2)/2 past each side).
    arm_ext = (cross_w - 2) // 2
    arm_x0 = v_left - arm_ext
    arm_x1 = v_right + arm_ext
    print(f"\n[cross] marker bbox x={cx0}..{cx1} y={cy0}..{cy1} ({cross_w}x{cross_h})")
    print(f"        bishop mitre center x={mitre_cx}; placing vertical at x={v_left},{v_right}")
    print(f"        horizontal arm x={arm_x0}..{arm_x1} at y={arm_y}")

    bishop_out = bishop.copy()
    op = bishop_out.load()

    def paint_clip(arr, x, y, color):
        if 0 <= x < bw and 0 <= y < bh and arr[x][y]:
            op[x, y] = color

    # Paint horizontal arm FIRST (centered on vertical bar, top=H bot=O).
    for sx in range(arm_x0, arm_x1 + 1):
        paint_clip(bishop_mask, sx, arm_y, HIGHLIGHT)
        paint_clip(bishop_mask, sx, arm_y + 1, OUTLINE)

    # Then vertical bar (overwrites at intersection so the bar's
    # left/right shading wins through). Vertical spans the bbox y range.
    for sy in range(cy0, cy1 + 1):
        paint_clip(bishop_mask, v_left, sy, HIGHLIGHT)
        paint_clip(bishop_mask, v_right, sy, OUTLINE)

    bishop_out.save(WHITE_DIR / "bishop" / "static.png")
    recolor_to_black(bishop_out).save(BLACK_DIR / "bishop" / "static.png")
    print(f"[cross] saved bishop")

    # =====================================================================
    # Sword: stylized actual sword shape, can extend outside body
    # =====================================================================
    # Re-load bishop master so the assassin inherits cross + sword
    base = Image.open(WHITE_DIR / "bishop" / "static.png").convert("RGBA")
    base_mask = alpha_mask(base)

    orange = find_color_pixels(ref, is_orange)
    ox0, oy0, ox1, oy1 = marker_bbox_in_sprite(orange, paste_x, paste_y, scale)
    cg_y = widest_row_y(orange, paste_x, paste_y, scale)  # cross-guard sits here
    sword_cx = (ox0 + ox1) // 2
    cg_half_w = (ox1 - ox0) // 2
    print(f"\n[sword] bbox sprite x={ox0}..{ox1} y={oy0}..{oy1}; "
          f"cross-guard at y={cg_y} (half-width {cg_half_w}), center x={sword_cx}")
    print(f"  pommel/grip top y={oy0}, blade tip y={oy1}")

    assassin = base.copy()
    aop = assassin.load()

    def paint(x, y, color):
        """Paint regardless of body silhouette (sword can extend out)."""
        if 0 <= x < bw and 0 <= y < bh:
            aop[x, y] = color

    # Sword anatomy laid out top-to-bottom:
    #
    #   pommel apex   y = oy0          (1 px dark)
    #   pommel ball   y = oy0 + 1      (3 px dark)
    #   pommel base   y = oy0 + 2      (1 px dark)
    #   grip rows                      (1 px dark per row, length = grip_h)
    #   cross-guard top row            HIGHLIGHT, full width
    #   cross-guard bottom row         OUTLINE, full width
    #   blade rows                     (3 px wide: left=OUTLINE,
    #                                     center=HIGHLIGHT (fuller),
    #                                     right=OUTLINE)
    #   blade tip                      (1 px OUTLINE)

    pommel_apex_y = oy0
    pommel_ball_y = oy0 + 1
    pommel_base_y = oy0 + 2
    grip_top = oy0 + 3
    cg_top = cg_y
    cg_bot = cg_y + 1
    blade_top = cg_bot + 1
    blade_bot = oy1

    # Pommel — small round
    paint(sword_cx, pommel_apex_y, OUTLINE)
    for ddx in (-1, 0, 1):
        paint(sword_cx + ddx, pommel_ball_y, OUTLINE)
    paint(sword_cx, pommel_base_y, OUTLINE)

    # Grip — fill rows between pommel base and cross-guard
    for sy in range(grip_top, cg_top):
        paint(sword_cx, sy, OUTLINE)

    # Cross-guard — 2 rows tall, with end caps slightly wider for shape
    # Build symmetric span: cg_half_w on each side of sword_cx
    cg_half = max(2, cg_half_w)
    for ddx in range(-cg_half, cg_half + 1):
        # Top row HIGHLIGHT
        paint(sword_cx + ddx, cg_top, HIGHLIGHT)
        # Bottom row OUTLINE
        paint(sword_cx + ddx, cg_bot, OUTLINE)
    # End-cap pips (1-pixel taller dark dots at each end of the guard
    # to read as 'finials'/quillon caps)
    paint(sword_cx - cg_half, cg_top - 1, OUTLINE)
    paint(sword_cx + cg_half, cg_top - 1, OUTLINE)

    # Blade — 3 px wide with fuller, tapers to 1 px at tip
    taper_start = blade_bot - 1
    for sy in range(blade_top, blade_bot):
        if sy < taper_start:
            paint(sword_cx - 1, sy, OUTLINE)   # left edge
            paint(sword_cx, sy, HIGHLIGHT)     # center fuller (highlight)
            paint(sword_cx + 1, sy, OUTLINE)   # right edge
        else:
            # taper: 1 px wide
            paint(sword_cx, sy, OUTLINE)
    # Tip
    paint(sword_cx, blade_bot, OUTLINE)

    assassin.save(WHITE_DIR / "assassin_bishop" / "static.png")
    recolor_to_black(assassin).save(BLACK_DIR / "assassin_bishop" / "static.png")
    print(f"[sword] saved assassin_bishop")

    # =====================================================================
    # Comprehensive verification
    # =====================================================================
    def gather_features(img: Image.Image, kind: str):
        """Return list of (x, y, role) for cross/sword feature pixels in
        the sprite — pixels matching OUTLINE or HIGHLIGHT colors and
        not part of the body fill/outline boundary."""
        w, h = img.size
        ip = img.load()
        # We treat any pixel whose color is *exactly* OUTLINE or
        # HIGHLIGHT and is NOT on the body's silhouette boundary as a
        # feature pixel. (The body's outline is also OUTLINE colored,
        # but it sits on the silhouette boundary.)
        body_mask = alpha_mask(img)
        out = []
        for y in range(h):
            for x in range(w):
                if not body_mask[x][y]:
                    # silhouette extension — counts as feature if it's
                    # outside the original bishop silhouette
                    continue
                # check if it's body-outline by checking neighbors
                is_body_outline = False
                for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    nx, ny = x+dx, y+dy
                    if not (0 <= nx < w and 0 <= ny < h) or not body_mask[nx][ny]:
                        is_body_outline = True
                        break
                if is_body_outline:
                    continue
                c = ip[x, y]
                if c == OUTLINE or c == HIGHLIGHT:
                    role = "outline" if c == OUTLINE else "highlight"
                    out.append((x, y, role))
        return out

    print("\n=== VERIFICATION ===")
    cross_pixels = gather_features(bishop_out, "cross")
    cxs = [p[0] for p in cross_pixels]
    cys = [p[1] for p in cross_pixels]
    if cross_pixels:
        print(f"[cross] {len(cross_pixels)} feature pixels; "
              f"sprite bbox x={min(cxs)}..{max(cxs)} y={min(cys)}..{max(cys)}")
        print(f"        marker bbox     x={cx0}..{cx1} y={cy0}..{cy1}")
        print(f"        Δ x={min(cxs) - cx0:+d}..{max(cxs) - cx1:+d}, "
              f"y={min(cys) - cy0:+d}..{max(cys) - cy1:+d}")
        # left/right symmetry around the 2-wide vertical bar
        left = sum(1 for x in cxs if x < v_left)
        right = sum(1 for x in cxs if x > v_right)
        center = sum(1 for x in cxs if v_left <= x <= v_right)
        print(f"        L/center/R column counts: {left}/{center}/{right}  "
              f"(symmetric L↔R: {left == right})")

    print()
    sword_assassin = Image.open(WHITE_DIR / "assassin_bishop" / "static.png").convert("RGBA")
    # Sword pixels = pixels different from the bishop master
    bp = bishop_out.load(); ap = sword_assassin.load()
    sword_pixels = []
    for y in range(bh):
        for x in range(bw):
            if bp[x, y] != ap[x, y]:
                sword_pixels.append((x, y, ap[x, y]))
    sxs = [p[0] for p in sword_pixels]
    sys_ = [p[1] for p in sword_pixels]
    if sword_pixels:
        print(f"[sword] {len(sword_pixels)} new pixels vs bishop")
        print(f"        sprite bbox x={min(sxs)}..{max(sxs)} y={min(sys_)}..{max(sys_)}")
        print(f"        marker bbox x={ox0}..{ox1} y={oy0}..{oy1}")
        print(f"        Δ x={min(sxs) - ox0:+d}..{max(sxs) - ox1:+d}, "
              f"y={min(sys_) - oy0:+d}..{max(sys_) - oy1:+d}")
        # extension: pixels outside original bishop silhouette
        ext = sum(1 for (x, y, _) in sword_pixels if not bishop_mask[x][y])
        print(f"        silhouette-extension pixels (outside body): {ext}")
        # shading distribution
        from collections import Counter
        col_counts = Counter(p[2] for p in sword_pixels)
        print(f"        color distribution: OUTLINE={col_counts.get(OUTLINE, 0)}, "
              f"HIGHLIGHT={col_counts.get(HIGHLIGHT, 0)}")


if __name__ == "__main__":
    main()
