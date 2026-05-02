"""Generate pixel-art spritesheet assets for Chess-2.

Produces, under godot/assets/sprites/:
  anim/pieces/<color>/<piece_id>/<anim>.png   (horizontal frame strip)
  anim/fx/<kind>.png                          (horizontal frame strip)
  tiles/<stage>/<light|dark>.png              (single tile, 32x32)
  ui/energy_<filled|empty>.png                (single segment, 12x32)
  ui/ability_<cannon|lightning>.png           (single icon, 24x24)
  ui/shadow.png                               (drop shadow, 32x12)

Animation strips: each frame is FRAME x FRAME (32x32) laid out horizontally.

Pieces (id):
  pawn, rook, knight, bishop, queen, king,
  bandit_pawn, assassin_bishop, alter_knight

Animations per piece:
  static (1), move (6), attack (6), hit (3), death (5)
  + knight, alter_knight: move_jump (7)
  + alter_knight: attack_lunge (7)

FX:
  cannon_resolve (8), debris_fall (8), lightning_strike (6)

Run from anywhere (paths resolve relative to the project root regardless of cwd):
  python tools/sprites/generate_sprites.py
"""

import os
import math
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

FRAME = 32

# Resolve godot/ relative to this script's location so the script works
# whether you run it from the project root or from inside tools/sprites/.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPRITES_ROOT = os.path.join(_PROJECT_ROOT, "godot", "assets", "sprites")
ROOT = os.path.join(SPRITES_ROOT, "anim")
PIECES_ROOT = os.path.join(ROOT, "pieces")
FX_ROOT = os.path.join(ROOT, "fx")
TILES_ROOT = os.path.join(SPRITES_ROOT, "tiles")
UI_ROOT = os.path.join(SPRITES_ROOT, "ui")

OUTLINE = (15, 10, 18, 255)

# (deep_shadow, shadow, mid, highlight)
PALETTES = {
    "white": (
        (162, 130, 84, 255),
        (200, 168, 115, 255),
        (240, 222, 184, 255),
        (255, 246, 224, 255),
    ),
    "black": (
        (22, 16, 26, 255),
        (44, 34, 50, 255),
        (78, 64, 86, 255),
        (138, 116, 146, 255),
    ),
}

PIECES = [
    "pawn", "rook", "knight", "bishop", "queen", "king",
    "bandit_pawn", "assassin_bishop", "alter_knight",
]

# Animation frame counts (entries with `extra=True` are in addition to the
# six base animations and only emitted for the listed piece ids).
BASE_ANIMS = {
    "static": 1,
    "move":   6,
    "attack": 6,
    "hit":    3,
    "death":  5,
}
EXTRA_ANIMS = {
    "move_jump":    (7, ["knight", "alter_knight"]),
    "attack_lunge": (7, ["alter_knight"]),
}

# Per-frame pose deltas: (dx, dy, squash, lean_dx_top).
#   dx, dy:        whole-body translation
#   squash:        compress vertically by N pixels (toward the bottom)
#   lean_dx_top:   shift the top row by N pixels, scaling to 0 at bottom.
# The pose table is shared across all pieces so timing reads consistently.
POSES = {
    "static": [(0, 0, 0, 0)],
    "move": [
        (0,  0, 0,  1),
        (0, -1, 0,  0),
        (0, -1, 0, -1),
        (0,  0, 0,  0),
        (0, -1, 0,  1),
        (0,  0, 0,  0),
    ],
    "attack": [
        (-1,  1, 0, -2),
        (-2,  1, 0, -3),
        ( 2,  0, 0,  3),
        ( 3,  0, 0,  4),
        ( 1,  0, 0,  1),
        ( 0,  0, 0,  0),
    ],
    "hit": [
        ( 1, 0, 0, 0),
        (-1, 0, 0, 0),
        ( 0, 0, 0, 0),
    ],
    "death": [
        (0, 0,  0, 0),
        (0, 0,  3, 0),
        (0, 0,  7, 0),
        (0, 0, 12, 0),
        (0, 0, 18, 0),
    ],
    "move_jump": [
        (0,  0, 3,  0),
        (0, -2, 0,  0),
        (0, -5, 0,  0),
        (0, -7, 0,  0),
        (0, -5, 0,  0),
        (0, -2, 0,  0),
        (0,  0, 3,  0),
    ],
    "attack_lunge": [
        (-2,  1, 0, -4),
        (-3,  2, 0, -5),
        ( 4,  0, 0,  5),
        ( 5,  0, 0,  6),
        ( 5,  0, 0,  6),
        ( 2,  0, 0,  3),
        ( 0,  0, 0,  0),
    ],
}

# Hit flash tint per frame of the hit anim — bright whiteout, then a
# warm-red wash, then normal.
HIT_FLASH = [(0.9, 255, 240, 235), (0.55, 245, 80, 80), (0.0, 0, 0, 0)]

# Death alpha attenuation per frame.
DEATH_ALPHAS = [1.0, 0.92, 0.78, 0.55, 0.18]

# ---------------------------------------------------------------------------
# PIXEL HELPERS
# ---------------------------------------------------------------------------

def new_frame():
    return Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))

def putpx(img, x, y, c):
    if 0 <= x < img.width and 0 <= y < img.height:
        img.putpixel((x, y), c)

def fill_rect(img, x, y, w, h, c):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            putpx(img, xx, yy, c)

def fill_circle(img, cx, cy, r, c):
    rr = r * r
    for yy in range(-r, r + 1):
        for xx in range(-r, r + 1):
            if xx * xx + yy * yy <= rr:
                putpx(img, cx + xx, cy + yy, c)

def fill_ellipse(img, cx, cy, rx, ry, c):
    if rx <= 0 or ry <= 0:
        return
    for yy in range(-ry, ry + 1):
        for xx in range(-rx, rx + 1):
            if (xx * xx) * (ry * ry) + (yy * yy) * (rx * rx) <= (rx * rx) * (ry * ry):
                putpx(img, cx + xx, cy + yy, c)

def fill_poly(img, pts, c):
    tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(tmp).polygon(pts, fill=c)
    img.alpha_composite(tmp)

def fill_trap(img, x_top_l, x_top_r, x_bot_l, x_bot_r, y_top, y_bot, c):
    """Fill a trapezoid bounded by horizontal top/bot edges."""
    fill_poly(img, [(x_top_l, y_top), (x_top_r, y_top),
                    (x_bot_r, y_bot), (x_bot_l, y_bot)], c)

# ---------------------------------------------------------------------------
# PIECE SILHOUETTE DRAWS — each takes (img, mid_color) and paints the
# body in the mid color. Auto-shading is applied afterward.
# ---------------------------------------------------------------------------

def draw_pawn(img, c):
    # Head
    fill_circle(img, 16, 8, 4, c)
    # Neck collar
    fill_ellipse(img, 16, 14, 5, 2, c)
    # Bell body
    fill_trap(img, 11, 21, 9, 23, 15, 23, c)
    fill_ellipse(img, 16, 23, 7, 3, c)
    # Stem
    fill_rect(img, 11, 17, 11, 3, c)
    fill_ellipse(img, 16, 19, 6, 2, c)
    # Skirt
    fill_trap(img, 10, 22, 7, 25, 22, 27, c)
    # Base
    fill_rect(img, 6, 27, 21, 2, c)

def draw_rook(img, c):
    # Crenellated top — three battlements with gaps
    fill_rect(img, 8, 4, 3, 4, c)
    fill_rect(img, 13, 4, 3, 4, c)   # offset to shift the gaps to columns 11/12
    fill_rect(img, 17, 4, 3, 4, c)
    fill_rect(img, 22, 4, 3, 4, c)
    # Battlement band
    fill_rect(img, 7, 8, 19, 3, c)
    # Body shaft
    fill_rect(img, 11, 11, 11, 13, c)
    # Belt
    fill_rect(img, 9, 16, 15, 2, c)
    # Skirt + base
    fill_trap(img, 9, 23, 6, 26, 24, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_knight(img, c):
    # Snout pointing left + head body
    fill_poly(img, [(7, 8), (10, 5), (16, 4), (20, 7), (22, 11),
                    (11, 11), (7, 11)], c)
    # Forelock notch (cut by transparent later? leave outline-only)
    # Nostril gap
    putpx(img, 8, 9, (0, 0, 0, 0))
    # Mane down right
    fill_poly(img, [(20, 7), (24, 9), (25, 14), (22, 17), (18, 14)], c)
    # Neck
    fill_poly(img, [(11, 11), (22, 11), (24, 22), (10, 22)], c)
    # Chest swell
    fill_ellipse(img, 14, 19, 5, 4, c)
    # Base
    fill_trap(img, 9, 24, 6, 26, 22, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_bishop(img, c):
    # Mitre tip
    fill_poly(img, [(15, 3), (17, 3), (19, 6), (13, 6)], c)
    # Mitre body
    fill_ellipse(img, 16, 9, 5, 4, c)
    # Slash gap (transparent)
    fill_rect(img, 12, 9, 8, 1, (0, 0, 0, 0))
    # Collar
    fill_ellipse(img, 16, 14, 5, 2, c)
    # Body
    fill_trap(img, 11, 21, 9, 23, 14, 24, c)
    # Base
    fill_trap(img, 9, 23, 6, 26, 24, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_queen(img, c):
    # Crown spikes (5 with sphere tips)
    for cx in (8, 12, 16, 20, 24):
        fill_circle(img, cx, 4, 1, c)
        fill_rect(img, cx, 5, 1, 3, c)
    # Crown band
    fill_trap(img, 9, 23, 7, 25, 8, 11, c)
    # Body
    fill_ellipse(img, 16, 13, 7, 3, c)
    fill_trap(img, 11, 21, 9, 23, 14, 22, c)
    # Belt
    fill_rect(img, 9, 18, 15, 1, c)
    # Base
    fill_trap(img, 9, 23, 6, 26, 22, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_king(img, c):
    # Cross at top
    fill_rect(img, 15, 2, 2, 6, c)
    fill_rect(img, 13, 4, 6, 2, c)
    # Crown band
    fill_trap(img, 10, 22, 8, 24, 8, 11, c)
    # Body
    fill_ellipse(img, 16, 13, 7, 3, c)
    fill_trap(img, 11, 21, 9, 23, 14, 22, c)
    # Belt
    fill_rect(img, 9, 18, 15, 1, c)
    # Base
    fill_trap(img, 9, 23, 6, 26, 22, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_bandit_pawn(img, c):
    # Hood point
    fill_poly(img, [(15, 4), (18, 4), (20, 8), (12, 8)], c)
    # Hood body (wider than pawn head — sells "bandit")
    fill_ellipse(img, 16, 10, 6, 4, c)
    # Eye slit gap
    fill_rect(img, 12, 10, 8, 1, (0, 0, 0, 0))
    # Cape arms — outstretched cross-shape, defining motif
    fill_rect(img, 4, 14, 24, 3, c)
    # Hands at cape tips
    fill_circle(img, 5, 15, 2, c)
    fill_circle(img, 27, 15, 2, c)
    # Body
    fill_trap(img, 12, 20, 9, 23, 17, 24, c)
    # Base
    fill_trap(img, 9, 23, 6, 26, 24, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_assassin_bishop(img, c):
    # Hood point
    fill_poly(img, [(15, 2), (17, 2), (20, 6), (12, 6)], c)
    # Hood — narrower than regular bishop, cleaver-shaped
    fill_poly(img, [(13, 6), (19, 6), (22, 12), (10, 12)], c)
    # Slash gap (eye-shadow)
    fill_rect(img, 11, 9, 10, 1, (0, 0, 0, 0))
    # Collar
    fill_ellipse(img, 16, 13, 5, 2, c)
    # Cloak body (wider at bottom, narrow neck — assassin-y)
    fill_trap(img, 13, 19, 9, 23, 14, 24, c)
    # Blade tip peeking out (right side accent)
    fill_rect(img, 22, 16, 1, 6, c)
    fill_poly(img, [(22, 14), (24, 16), (22, 16)], c)
    # Base
    fill_trap(img, 9, 23, 6, 26, 24, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

def draw_alter_knight(img, c):
    # Mirrored knight: snout points RIGHT instead of left, with split mane.
    fill_poly(img, [(25, 8), (22, 5), (16, 4), (12, 7), (10, 11),
                    (21, 11), (25, 11)], c)
    # Nostril gap
    putpx(img, 24, 9, (0, 0, 0, 0))
    # Forked mane on left side (the "alter ego" tell)
    fill_poly(img, [(12, 7), (8, 8), (7, 13), (10, 16), (14, 13)], c)
    putpx(img, 9, 11, (0, 0, 0, 0))   # split notch
    # Neck
    fill_poly(img, [(10, 11), (21, 11), (22, 22), (8, 22)], c)
    # Chest swell
    fill_ellipse(img, 18, 19, 5, 4, c)
    # Base
    fill_trap(img, 9, 24, 6, 26, 22, 27, c)
    fill_rect(img, 6, 27, 21, 2, c)

PIECE_DRAWERS = {
    "pawn":            draw_pawn,
    "rook":            draw_rook,
    "knight":          draw_knight,
    "bishop":          draw_bishop,
    "queen":           draw_queen,
    "king":            draw_king,
    "bandit_pawn":     draw_bandit_pawn,
    "assassin_bishop": draw_assassin_bishop,
    "alter_knight":    draw_alter_knight,
}

# ---------------------------------------------------------------------------
# FILTERS — outline, auto-shading, transforms.
# ---------------------------------------------------------------------------

def apply_outline(img, color=OUTLINE):
    """Paint `color` into every transparent pixel that 4-neighbors a body
    pixel. Two-pass to avoid mid-pass pollution."""
    w, h = img.size
    px = img.load()
    paints = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] >= 128:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] >= 128:
                    paints.append((x, y))
                    break
    for x, y in paints:
        px[x, y] = color

def auto_shade(img, palette):
    """Add highlights / shadows inside the silhouette by examining 8-neighbors.
    Top-left edges get the highlight; bottom-right edges get the shadow.
    Bottom row gets the deep_shadow color so the piece sits on a base line."""
    deep, shadow, mid, hi = palette
    w, h = img.size
    px = img.load()
    body = [[px[x, y][3] >= 128 for x in range(w)] for y in range(h)]

    def is_outline(x, y):
        # Outline pixels are full-opaque OUTLINE-colored — leave them.
        return px[x, y] == OUTLINE

    # Highlights (top + left edges of body).
    for y in range(h):
        for x in range(w):
            if not body[y][x] or is_outline(x, y):
                continue
            up_empty = y == 0 or not body[y - 1][x]
            left_empty = x == 0 or not body[y][x - 1]
            if up_empty or left_empty:
                px[x, y] = hi
    # Shadows (bottom + right edges of body, but skip already-highlighted
    # pixels by checking they're still mid).
    for y in range(h):
        for x in range(w):
            if not body[y][x] or is_outline(x, y) or px[x, y] == hi:
                continue
            dn_empty = y == h - 1 or not body[y + 1][x]
            rt_empty = x == w - 1 or not body[y][x + 1]
            if dn_empty or rt_empty:
                px[x, y] = shadow
    # Deep-shadow for the very bottom row of body pixels — gives the piece
    # a grounded silhouette without an external drop shadow.
    for x in range(w):
        for y in range(h - 1, -1, -1):
            if body[y][x] and not is_outline(x, y):
                px[x, y] = deep
                break

def render_piece_static(piece_id, color_name):
    img = new_frame()
    palette = PALETTES[color_name]
    _, _, mid, _ = palette
    PIECE_DRAWERS[piece_id](img, mid)
    auto_shade(img, palette)
    apply_outline(img, OUTLINE)
    return img

def transform(img, dx, dy, squash, lean_dx_top):
    """Apply pose deltas to `img`. Returns a fresh image."""
    out = new_frame()
    w, h = img.size
    src = img.load()
    dst = out.load()
    if squash < 0:
        squash = 0
    base_h = h - squash
    denom = max(h - 1, 1)
    for y in range(h):
        sy = y - dy
        if sy < 0 or sy >= h:
            continue
        # The lean amount scales linearly from `lean_dx_top` at the visual
        # top of the body to 0 at the bottom. We use sy as the source row
        # to keep the lean pinned to the body's own frame of reference.
        t = 1.0 - (sy / denom)
        lean_dx = int(round(lean_dx_top * t))
        # Squash maps the vertical body extent into [squash, h).
        if squash > 0:
            ty = squash + int(round((y - squash) * (base_h / float(h)))) if squash <= y else None
            if ty is None:
                continue
        else:
            ty = y
        for x in range(w):
            sx = x - dx - lean_dx
            if sx < 0 or sx >= w:
                continue
            c = src[sx, sy]
            if c[3] == 0:
                continue
            if 0 <= ty < h:
                dst[x, ty] = c
    return out

def tint_blend(img, mix, tint_rgb):
    """Mix every non-transparent, non-outline pixel toward `tint_rgb` by
    `mix` in [0..1]. Used for hit flash."""
    if mix <= 0:
        return img
    w, h = img.size
    px = img.load()
    tr, tg, tb = tint_rgb
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0 or (r, g, b, a) == OUTLINE:
                continue
            nr = int(r * (1 - mix) + tr * mix)
            ng = int(g * (1 - mix) + tg * mix)
            nb = int(b * (1 - mix) + tb * mix)
            px[x, y] = (nr, ng, nb, a)
    return img

def alpha_mul(img, factor):
    if factor >= 1.0:
        return img
    w, h = img.size
    px = img.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (r, g, b, max(0, int(a * factor)))
    return img

# ---------------------------------------------------------------------------
# STRIP COMPOSITION
# ---------------------------------------------------------------------------

def compose_strip(frames):
    n = len(frames)
    strip = Image.new("RGBA", (FRAME * n, FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.alpha_composite(f, dest=(i * FRAME, 0))
    return strip

def render_anim(piece_id, color_name, anim, n_frames):
    base = render_piece_static(piece_id, color_name)
    poses = POSES[anim]
    if len(poses) < n_frames:
        # Pad by repeating the last pose if we somehow asked for more.
        poses = poses + [poses[-1]] * (n_frames - len(poses))
    frames = []
    for i in range(n_frames):
        dx, dy, squash, lean = poses[i]
        f = transform(base, dx, dy, squash, lean)
        if anim == "hit":
            mix, tr, tg, tb = HIT_FLASH[i] if i < len(HIT_FLASH) else (0, 0, 0, 0)
            tint_blend(f, mix, (tr, tg, tb))
        elif anim == "death":
            alpha = DEATH_ALPHAS[i] if i < len(DEATH_ALPHAS) else 0.0
            alpha_mul(f, alpha)
        frames.append(f)
    return frames

# ---------------------------------------------------------------------------
# FX — abstract impact effects, drawn directly per frame.
# ---------------------------------------------------------------------------

CANNON_INNER = (255, 246, 200, 255)
CANNON_MID   = (255, 145, 60, 255)
CANNON_OUTER = (220, 88, 40, 255)
CANNON_OUTLINE = (90, 30, 14, 255)

def cannon_resolve_frames():
    cx = cy = FRAME // 2
    frames = []
    # Phase 1 — reticle contracts: 3 frames.
    for i in range(3):
        img = new_frame()
        r = 13 - i * 3   # 13, 10, 7
        # outer thin ring
        fill_circle(img, cx, cy, r + 1, CANNON_OUTER)
        fill_circle(img, cx, cy, r - 1, (0, 0, 0, 0))
        # crosshair ticks at cardinal directions
        for d in range(2, 5):
            putpx(img, cx + r + 1 + d, cy, CANNON_OUTLINE)
            putpx(img, cx - r - 1 - d, cy, CANNON_OUTLINE)
            putpx(img, cx, cy + r + 1 + d, CANNON_OUTLINE)
            putpx(img, cx, cy - r - 1 - d, CANNON_OUTLINE)
        frames.append(img)
    # Phase 2 — burst expands: 3 frames.
    for i in range(3):
        img = new_frame()
        r_inner = 2 + i * 2
        r_mid = r_inner + 3
        r_out = r_mid + 2
        fill_circle(img, cx, cy, r_out, CANNON_OUTER)
        fill_circle(img, cx, cy, r_mid, CANNON_MID)
        fill_circle(img, cx, cy, r_inner, CANNON_INNER)
        frames.append(img)
    # Phase 3 — plus arms flash outward: 2 frames.
    for i in range(2):
        img = new_frame()
        # Faint center
        fill_circle(img, cx, cy, 4, (255, 200, 110, 200))
        # Plus arms — a band along each cardinal direction at radius 8 + i*2
        arm_off = 6 + i * 3
        thickness = 3 - i
        for s in (-1, 1):
            fill_rect(img, cx + s * arm_off - 1, cy - thickness // 2,
                      2 + thickness, 1 + thickness * 2, CANNON_MID)
            fill_rect(img, cx - thickness // 2, cy + s * arm_off - 1,
                      1 + thickness * 2, 2 + thickness, CANNON_MID)
        frames.append(img)
    return frames

DEBRIS_DARK = (44, 38, 56, 255)
DEBRIS_MID  = (90, 80, 110, 255)
DEBRIS_HI   = (160, 150, 180, 255)
DUST_COLOR  = (200, 200, 220, 200)
SHADOW_COLOR = (0, 0, 0, 140)

def debris_fall_frames():
    cx = FRAME // 2
    ground_y = FRAME - 6
    frames = []

    def shadow_ellipse(img, scale):
        rx = max(1, int(8 * scale))
        ry = max(1, int(rx * 0.4))
        for yy in range(-ry, ry + 1):
            for xx in range(-rx, rx + 1):
                if (xx * xx) * (ry * ry) + (yy * yy) * (rx * rx) <= (rx * rx) * (ry * ry):
                    putpx(img, cx + xx, ground_y + yy,
                          (SHADOW_COLOR[0], SHADOW_COLOR[1], SHADOW_COLOR[2],
                           int(SHADOW_COLOR[3] * min(1.0, 0.4 + 0.6 * scale))))

    # Phase 1 — shadow grows: 3 frames.
    for i in range(3):
        img = new_frame()
        shadow_ellipse(img, 0.35 + 0.25 * i)
        frames.append(img)
    # Phase 2 — debris drops in: 3 frames.
    for i in range(3):
        img = new_frame()
        shadow_ellipse(img, 0.85)
        rock_y = 4 + i * 7
        fill_circle(img, cx, rock_y, 4, DEBRIS_DARK)
        fill_circle(img, cx - 1, rock_y - 1, 3, DEBRIS_MID)
        putpx(img, cx + 1, rock_y - 1, DEBRIS_HI)
        putpx(img, cx - 2, rock_y - 2, DEBRIS_HI)
        # Streak trail
        for s in range(1, 4):
            putpx(img, cx, rock_y - s * 2, (255, 200, 140, max(0, 180 - s * 50)))
        frames.append(img)
    # Phase 3 — impact dust ring + rubble: 2 frames.
    for i in range(2):
        img = new_frame()
        # Rubble pile at base
        fill_rect(img, cx - 5, ground_y - 1, 11, 3, DEBRIS_DARK)
        fill_rect(img, cx - 4, ground_y - 1, 9, 1, DEBRIS_MID)
        putpx(img, cx - 3, ground_y - 1, DEBRIS_HI)
        # Dust ring
        rx = 6 + i * 4
        ry = 2 + i
        for yy in range(-ry, ry + 1):
            for xx in range(-rx, rx + 1):
                d = (xx * xx) * (ry * ry) + (yy * yy) * (rx * rx)
                outer = (rx * rx) * (ry * ry)
                inner = ((rx - 2) * (rx - 2)) * (ry * ry)
                if inner < d <= outer:
                    putpx(img, cx + xx, ground_y - 4 + yy,
                          (DUST_COLOR[0], DUST_COLOR[1], DUST_COLOR[2],
                           max(0, DUST_COLOR[3] - i * 70)))
        frames.append(img)
    return frames

LIGHTNING_CORE = (255, 255, 240, 255)
LIGHTNING_BODY = (255, 240, 120, 255)
LIGHTNING_DARK = (210, 160, 30, 255)
LIGHTNING_GLOW = (255, 230, 130, 130)

def _draw_bolt(img, cx, y_top, y_bot, half_w, color):
    """Jagged vertical bolt from y_top to y_bot, centered horizontally on cx.
    Wiggle is fixed at +-2 every few rows so the shape reads as lightning."""
    prev_x = cx
    for y in range(y_top, y_bot + 1):
        off = 0
        m = (y - y_top) % 6
        if m == 1: off = -2
        elif m == 4: off = 2
        bx = cx + off
        for w in range(-half_w, half_w + 1):
            putpx(img, bx + w, y, color)
        if y > y_top and prev_x != bx:
            lo, hi = min(prev_x, bx), max(prev_x, bx)
            for xx in range(lo - half_w, hi + half_w + 1):
                putpx(img, xx, y - 1, color)
        prev_x = bx

def lightning_strike_frames():
    cx = FRAME // 2
    frames = []
    # Frame 0 — full glow pre-flash.
    img = new_frame()
    fill_circle(img, cx, FRAME // 2, 14, LIGHTNING_GLOW)
    fill_circle(img, cx, FRAME // 2, 10, (255, 255, 220, 200))
    frames.append(img)
    # Frame 1 — wide bolt with halo.
    img = new_frame()
    fill_circle(img, cx, FRAME // 2, 12, LIGHTNING_GLOW)
    _draw_bolt(img, cx, 2, FRAME - 3, 2, LIGHTNING_BODY)
    _draw_bolt(img, cx, 2, FRAME - 3, 0, LIGHTNING_CORE)
    frames.append(img)
    # Frame 2 — narrow bolt with smaller halo.
    img = new_frame()
    fill_circle(img, cx, FRAME // 2, 8, (255, 230, 130, 90))
    _draw_bolt(img, cx, 2, FRAME - 3, 1, LIGHTNING_BODY)
    _draw_bolt(img, cx, 2, FRAME - 3, 0, LIGHTNING_CORE)
    frames.append(img)
    # Frames 3-5 — fading afterglow.
    for i in range(3):
        img = new_frame()
        a = 200 - i * 60
        fill_circle(img, cx, FRAME // 2, 9 - i, (255, 230, 130, max(0, a)))
        if i == 0:
            _draw_bolt(img, cx, 2, FRAME - 3, 0, LIGHTNING_DARK)
        frames.append(img)
    return frames

# ---------------------------------------------------------------------------
# TILES — board squares, per stage. 32x32 each, dithered base color with a
# 1px inset darker border so tiles read as discrete pieces of board.
# ---------------------------------------------------------------------------

TILE_PALETTES = {
    "classic": {
        "light": ((237, 217, 168, 255), (226, 207, 158, 255)),
        "dark":  ((140, 92,  56,  255), (128, 82,  51,  255)),
    },
    "moon": {
        "light": ((158, 158, 184, 255), (140, 140, 168, 255)),
        "dark":  (( 51,  51,  72, 255), ( 40,  40,  62, 255)),
    },
}

def render_tile(stage, kind, size=32):
    base, alt = TILE_PALETTES[stage][kind]
    img = Image.new("RGBA", (size, size), base)
    px = img.load()
    # 2x2 dither — every third 2x2 block uses the alt color, giving a soft
    # wood-grain / dust-mottle texture.
    for y in range(size):
        for x in range(size):
            if ((x >> 1) + (y >> 1)) % 3 == 0:
                px[x, y] = alt
    # Inset darker border on all 4 sides.
    border = (max(0, base[0] - 35), max(0, base[1] - 35), max(0, base[2] - 35), 255)
    for x in range(size):
        px[x, 0] = border
        px[x, size - 1] = border
    for y in range(size):
        px[0, y] = border
        px[size - 1, y] = border
    return img

# ---------------------------------------------------------------------------
# UI — energy segment, ability icons, drop shadow.
# ---------------------------------------------------------------------------

ENERGY_FILL       = (82, 199, 245, 255)
ENERGY_FILL_LIGHT = (158, 235, 255, 255)
ENERGY_EMPTY      = (33, 41, 56, 255)
ENERGY_FRAME      = (10, 13, 20, 255)

def render_energy(filled):
    w, h = 12, 32
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    # Frame
    for y in range(h):
        for x in range(w):
            px[x, y] = ENERGY_FRAME
    if filled:
        # Inner darker fill, then brighter overlay leaving 2px at the bottom
        # for the gradient floor, plus a 2x18 gloss strip.
        for y in range(2, h - 2):
            for x in range(2, w - 2):
                px[x, y] = (
                    int(ENERGY_FILL[0] * 0.75),
                    int(ENERGY_FILL[1] * 0.75),
                    int(ENERGY_FILL[2] * 0.75),
                    255,
                )
        for y in range(2, h - 4):
            for x in range(2, w - 2):
                px[x, y] = ENERGY_FILL
        for y in range(3, h - 11):
            for x in range(3, 5):
                px[x, y] = ENERGY_FILL_LIGHT
    else:
        for y in range(2, h - 2):
            for x in range(2, w - 2):
                px[x, y] = ENERGY_EMPTY
    return img

ABILITY_OUTLINE = (15, 10, 18, 255)

def render_cannon_icon():
    img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    inner = (255, 145, 60, 255)
    outer = (235, 105, 50, 255)
    cx = cy = 12
    for yy in range(-9, 10):
        for xx in range(-9, 10):
            d = xx * xx + yy * yy
            if d <= 81:
                img.putpixel((cx + xx, cy + yy), outer)
            if d <= 16:
                img.putpixel((cx + xx, cy + yy), inner)
    img.putpixel((11, 11), (255, 220, 150, 255))
    apply_outline(img, ABILITY_OUTLINE)
    return img

def render_lightning_icon():
    img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    bolt = (255, 235, 80, 255)
    bolt_dark = (215, 170, 30, 255)
    rows = [
        "..............",
        "...XXXXX......",
        "..XXXXXX......",
        ".XXXXXXX......",
        ".XXXXXX.......",
        "XXXXXX........",
        "XXXXX.........",
        "XXXXXXXXXXX...",
        ".XXXXXXXXX....",
        "....XXXXXX....",
        "....XXXXX.....",
        "...XXXX.......",
        "..XXX.........",
        "..XX..........",
    ]
    ox, oy = 5, 5
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == "X":
                img.putpixel((ox + x, oy + y), bolt)
    apply_outline(img, bolt_dark)
    apply_outline(img, ABILITY_OUTLINE)
    return img

def render_shadow():
    w, h = 32, 12
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y in range(h):
        for x in range(w):
            dx = (x - w * 0.5) / (w * 0.5)
            dy = (y - h * 0.5) / (h * 0.5)
            d = dx * dx + dy * dy
            if d <= 1.0:
                a = int(0.42 * (1.0 - d) * 255)
                px[x, y] = (0, 0, 0, a)
    return img

# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------

def ensure(path):
    os.makedirs(path, exist_ok=True)

def emit_pieces():
    for color in ("white", "black"):
        for pid in PIECES:
            piece_dir = os.path.join(PIECES_ROOT, color, pid)
            ensure(piece_dir)
            anims = dict(BASE_ANIMS)
            for anim_name, (n, allowed) in EXTRA_ANIMS.items():
                if pid in allowed:
                    anims[anim_name] = n
            for anim, n in anims.items():
                frames = render_anim(pid, color, anim, n)
                strip = compose_strip(frames)
                out_path = os.path.join(piece_dir, anim + ".png")
                strip.save(out_path)
                print("wrote", out_path)

def emit_fx():
    ensure(FX_ROOT)
    for kind, fn in (
        ("cannon_resolve", cannon_resolve_frames),
        ("debris_fall",    debris_fall_frames),
        ("lightning_strike", lightning_strike_frames),
    ):
        frames = fn()
        strip = compose_strip(frames)
        out_path = os.path.join(FX_ROOT, kind + ".png")
        strip.save(out_path)
        print("wrote", out_path)

def emit_tiles():
    for stage in TILE_PALETTES:
        stage_dir = os.path.join(TILES_ROOT, stage)
        ensure(stage_dir)
        for kind in ("light", "dark"):
            out_path = os.path.join(stage_dir, kind + ".png")
            render_tile(stage, kind).save(out_path)
            print("wrote", out_path)

def emit_ui():
    ensure(UI_ROOT)
    for state in (True, False):
        out_path = os.path.join(UI_ROOT, ("energy_filled" if state else "energy_empty") + ".png")
        render_energy(state).save(out_path)
        print("wrote", out_path)
    for kind, fn in (("ability_cannon", render_cannon_icon),
                     ("ability_lightning", render_lightning_icon),
                     ("shadow", render_shadow)):
        out_path = os.path.join(UI_ROOT, kind + ".png")
        fn().save(out_path)
        print("wrote", out_path)

def main():
    ensure(PIECES_ROOT)
    ensure(FX_ROOT)
    emit_pieces()
    emit_fx()
    emit_tiles()
    emit_ui()
    print("done.")

if __name__ == "__main__":
    main()
