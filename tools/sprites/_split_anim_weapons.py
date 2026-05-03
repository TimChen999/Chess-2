"""Surgically derive body_<anim>.png + weapon_<anim>.png for every
weapon-bearing piece, preserving every non-weapon pixel from the
existing aeaa0be-era animation strips byte-for-byte.

Per-frame contract (mirrors the static split in
_split_weapons_from_aeaa0be.py):

  existing_frame  = aeaa0be:<anim>.png frame i
                  ~ transformed(aeaa0be:static, POSES[anim][i])

  lockstep_weapon = transformed(weapon_static, POSES[anim][i])
                    using the body_static y-span (so the weapon shears
                    in lockstep with the body, identical to how it
                    moved in the original full composite)

  body_<anim>.png frame i  = existing_frame - lockstep_weapon mask
                              (erase to transparent if weapon is outside
                              body, otherwise fill from nearest non-mask
                              pixel in same row)

  weapon_<anim>.png frame i = lockstep_weapon
                              + per-piece extras for (piece, anim, i)
                                (raise + tip glow for bishop/king,
                                 sweep for queen, thrust for bandit,
                                 book-light for pawn — attack only)
                              + same anim modifiers used by
                                wizard_animations.py (HIT_FLASH,
                                ATTACK_FLASH, DEATH_ALPHAS)

Because body_<anim>.png is derived BY SUBTRACTION from the existing
strip, every body pixel outside the weapon mask is byte-for-byte
identical to the existing aeaa0be-era strip. Non-weapon body
animation behavior is preserved exactly.

Run: python tools/sprites/_split_anim_weapons.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wizard_statics import (  # type: ignore
    ALPHA_THRESH,
    PIECES_ACCESSORIES,
    alpha_mask,
)
from wizard_animations import (  # type: ignore
    POSES,
    HIT_FLASH,
    ATTACK_FLASH,
    DEATH_ALPHAS,
    apply_alpha,
    apply_flash,
)
from _split_weapons_from_aeaa0be import (  # type: ignore
    ARC_ONLY_PIECES,
    WEAPON_OVERLAPS_BODY,
    fill_from_nearest_in_row,
)

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"

FRAME = 64

# Anims to split — knight/alter_knight extras (move_jump / attack_lunge)
# don't apply to weapon-bearing pieces.
ANIMS = ["move", "attack", "hit", "death"]


# ---------------------------------------------------------------------------
# PER-PIECE WEAPON EXTRAS (attack only — other anims = lockstep)
# ---------------------------------------------------------------------------
# (extra_dx, extra_dy, glow_intensity)  for each frame of the attack anim.
# The weapon translates by (extra_dx, extra_dy) on top of its lockstep
# pose, and the glow paints a small bright cluster at the weapon's top
# opaque pixel with the given intensity (0..1).

WEAPON_EXTRAS = {
    "bishop": {
        "attack": [
            (0,   0, 0.00),
            (0,   0, 0.00),
            (0,  -8, 0.55),   # raise + early glow
            (0, -12, 0.90),   # peak raise + bright glow
            (0,  -4, 0.40),   # coming down
            (0,   0, 0.00),
        ],
    },
    "king": {
        "attack": [
            (0,   0, 0.00),
            (0,   0, 0.00),
            (0,  -8, 0.55),
            (0, -12, 0.90),
            (0,  -4, 0.40),
            (0,   0, 0.00),
        ],
    },
    "queen": {
        "attack": [
            (0,  0, 0.00),
            (-1, 0, 0.00),
            (3, -2, 0.40),    # sweep forward + tip glow
            (5, -3, 0.80),
            (3, -2, 0.30),
            (0,  0, 0.00),
        ],
    },
    "pawn": {
        "attack": [
            (0,  0, 0.00),
            (0, -1, 0.00),
            (1, -2, 0.50),    # raise book + magical light
            (2, -3, 0.85),
            (1, -1, 0.40),
            (0,  0, 0.00),
        ],
    },
    "bandit_pawn": {
        "attack": [
            (0,  0, 0.00),
            (-1, 0, 0.00),
            (3, -1, 0.40),    # thrust forward + blade flash
            (5, -2, 0.70),
            (3, -1, 0.30),
            (0,  0, 0.00),
        ],
    },
}

# Tip-glow color per piece. Bright RGB; alpha is set per pixel via
# intensity blend.
WEAPON_GLOW_COLOR = {
    "bishop":      (255, 215, 100),
    "king":        (200, 130, 230),
    "queen":       (130, 230, 220),
    "pawn":        (255, 230, 130),
    "bandit_pawn": (220, 230, 245),
}


# Per-piece SWING ARC — a crescent-shaped slash trail painted around
# the weapon during attack frames. Modeled after classic action-game
# sword swing arcs (think Sonic / Castlevania): a translucent grey/
# white moon shape that grows during the wind-up, peaks at the strike,
# then fades during recovery.
#
# Each piece's "frames" entry is one tuple per attack frame:
#   (start_deg, end_deg, max_alpha)  or  None  (no arc this frame)
# Angles are in math convention: 0deg = right (+x), 90deg = up (-y),
# 180deg = left, -90deg = down.
#
# - center: (cx, cy) on the 64x64 canvas — the pivot the arc curves
#   around. For sword/sash pieces this is the body's chest area; for
#   staves it's the hilt (lower) so the arc sweeps through the orb's
#   raised position.
# - inner_r / outer_r: thickness of the crescent. The reference uses
#   ~12-px thick crescents on a 64x64 canvas.
# - color: the swing trail tint (silvers / weapon-aligned colors).
# Sword-blade swing animation. Rather than painting a separate
# crescent overlay on top of a static sword, we ROTATE THE SWORD
# SPRITE itself per frame around a pivot point (the hilt), and add
# motion-blur ghost copies at intermediate angles to fill the arc the
# blade sweeps through. This is how classic action-platformer sword
# animations work — the blade IS the arc.
#
# Per piece:
#   pivot           — (cx, cy) on 64x64 canvas to rotate around
#                     (typically the hilt, where the hand holds it)
#   ghost_count     — number of intermediate ghost copies between
#                     consecutive frame angles (more = smoother arc)
#   ghost_alpha     — peak alpha for the ghost trail (0..255)
#   attack_angles   — angle in degrees for each attack frame.
#                     PIL convention: positive = counter-clockwise.
#                     For a forward (rightward) slash:
#                       0   = vertical, sword pointing up (rest)
#                       +N  = sword tilted up-back over shoulder
#                       -N  = sword tilted forward (toward right)
#                       -90 = sword horizontal-right (full thrust)
def make_synthetic_assassin_sword() -> Image.Image:
    """Hand-painted 64x64 sword sprite for assassin_bishop. The
    assassin's baseline shows the sword sheathed behind the body
    (mostly hidden by the sash) so we can't extract it. Instead we
    draw a synthetic sword that the assassin DRAWS during attack
    frames — sheathed at rest (F0, F5), drawn for the swing (F1-F4).
    Hilt sits at the pivot point (32, 50) so rotation pivots around
    the grip."""
    OUTLINE = (40, 40, 50, 255)
    BLADE = (192, 200, 215, 255)        # silver
    BLADE_HI = (235, 240, 248, 255)      # blade highlight
    GUARD = (217, 178, 60, 255)          # gold crossguard
    GRIP = (90, 55, 40, 255)             # dark wood grip
    POMMEL = (217, 178, 60, 255)         # gold pommel
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    p = img.load()
    # Sword laid out vertically (tip up, hilt down), pivot at (32, 50).
    # Blade tip y=22 (decorative point).
    p[32, 22] = OUTLINE
    # Blade body y=23..42 (20 px tall, 3 px wide with highlight).
    for y in range(23, 43):
        p[31, y] = OUTLINE
        p[32, y] = BLADE
        p[33, y] = BLADE_HI
        p[34, y] = OUTLINE
    # Crossguard y=43-44 (5 px wide, gold).
    for x in range(29, 37):
        p[x, 43] = OUTLINE
    for x in range(29, 37):
        p[x, 44] = GUARD
    p[29, 44] = OUTLINE
    p[36, 44] = OUTLINE
    # Cap row below crossguard.
    p[29, 45] = OUTLINE
    p[36, 45] = OUTLINE
    # Grip y=45-48 (3 px wide, dark wood).
    for y in range(45, 49):
        p[31, y] = OUTLINE
        p[32, y] = GRIP
        p[33, y] = GRIP
        p[34, y] = OUTLINE
    # Pommel y=49-50 (round, gold).
    p[32, 49] = POMMEL
    p[33, 49] = POMMEL
    p[31, 49] = OUTLINE
    p[34, 49] = OUTLINE
    p[32, 50] = OUTLINE
    p[33, 50] = OUTLINE
    return img


BLADE_SWING = {
    "bandit_pawn": {
        "pivot": (32, 47),
        "ghost_count": 6,
        "ghost_alpha": 110,
        "attack_angles": [
            0,    # F0 rest — sword vertical
            35,   # F1 wind-up — sword raised back-up
            55,   # F2 deeper wind-up — peak back
            -55,  # F3 SLASH — sword swung forward through arc
            -85,  # F4 follow-through — sword horizontal forward
            0,    # F5 settle — back to rest
        ],
    },
    "assassin_bishop": {
        # Sword is baked into the baseline silhouette and largely
        # hidden behind the diagonal sash, so weapon_static.png is a
        # transparent canvas. For the attack swing we draw a SYNTHETIC
        # sword (built by make_synthetic_assassin_sword), which the
        # assassin "draws" from the sheath on F1, swings F2-F4, then
        # resheathes on F5. The body's baked-in sheathed sword stays
        # in place (pixel-perfect preserved) — the synthetic sword is
        # an additional overlay that only appears during the swing.
        "pivot": (32, 50),
        "ghost_count": 7,
        "ghost_alpha": 130,
        "synthetic": "assassin_sword",
        "attack_angles": [
            0,    # F0 rest — sheathed (alpha 0 below)
            30,   # F1 drawn + wind-up
            55,   # F2 peak wind-up — sword raised back
            -50,  # F3 SLASH — sword swung forward
            -85,  # F4 follow-through — full thrust
            0,    # F5 — sheathed again (alpha 0)
        ],
        # Per-frame alpha multiplier — F0 and F5 are 0 (sword is
        # sheathed and invisible at the start/end of the swing).
        "frame_alphas": [0.0, 1.0, 1.0, 1.0, 1.0, 0.0],
    },
}


# ---------------------------------------------------------------------------
# CRESCENT SLASH — bold painted swoosh that reads as the slash itself.
# Per-frame None means "no crescent on this frame". Otherwise dict with:
#   r_inner, r_outer, start_deg, end_deg, max_alpha, palette
# Angles: 0=right, 90=up, 180=left, -90=down (screen coords).
# Painted on the weapon canvas BEHIND the rotated blade so the blade
# rides on the leading edge of the crescent.
# ---------------------------------------------------------------------------

CRESCENT_SLASH = {
    "bandit_pawn": {
        "pivot": (32, 46),
        "palette": "silver",
        "attack_frames": [
            None,                                                                                       # F0 rest
            None,                                                                                       # F1 wind-up
            {"r_inner": 8,  "r_outer": 22, "start_deg":  85, "end_deg": 165, "max_alpha": 145},        # F2 forming
            {"r_inner": 7,  "r_outer": 30, "start_deg": -50, "end_deg": 145, "max_alpha": 235},        # F3 PEAK SLASH
            {"r_inner": 7,  "r_outer": 26, "start_deg": -85, "end_deg":  20, "max_alpha": 175},        # F4 follow-through
            None,                                                                                       # F5 settle
        ],
    },
    "assassin_bishop": {
        "pivot": (32, 50),
        "palette": "silver",
        "attack_frames": [
            None,
            None,
            {"r_inner": 8,  "r_outer": 22, "start_deg":  80, "end_deg": 160, "max_alpha": 150},
            {"r_inner": 7,  "r_outer": 30, "start_deg": -55, "end_deg": 150, "max_alpha": 240},
            {"r_inner": 7,  "r_outer": 26, "start_deg": -90, "end_deg":  15, "max_alpha": 180},
            None,
        ],
    },
}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def silhouette_yspan(img: Image.Image) -> tuple[int, int]:
    """Return (ys_min, ys_max) of opaque pixels."""
    w, h = img.size
    px = img.load()
    ys_min, ys_max = h, -1
    for y in range(h):
        for x in range(w):
            if px[x, y][3] >= ALPHA_THRESH:
                if y < ys_min: ys_min = y
                if y > ys_max: ys_max = y
                break
    return ys_min, ys_max


def transformed_with_yspan(img: Image.Image, dx: int, dy: int, squash: int,
                            lean_top: int, ys_min: int, ys_max: int) -> Image.Image:
    """transformed() but with explicit y-span (instead of computed from
    the input image's silhouette). Used to transform a weapon-only image
    using the BODY's y-norm so the weapon shears in lockstep — i.e.
    pixel at y=10 shears by lean_top * (1 - (10 - body_ys_min)/body_span),
    not by the weapon's own y-norm. This produces the same per-pixel
    shear the wizard_animations pipeline applied when transforming the
    full composite (whose silhouette bbox = body bbox)."""
    w, h = img.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sp = img.load()
    op = out.load()
    span = max(1, ys_max - ys_min)
    for y in range(h):
        if y < ys_min or y > ys_max:
            for x in range(w):
                if sp[x, y][3] < ALPHA_THRESH:
                    continue
                nx = x + dx
                ny = y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    op[nx, ny] = sp[x, y]
            continue
        y_norm = (y - ys_min) / span
        ssh = int(round(squash * (1.0 - y_norm)))
        lsh = int(round(lean_top * (1.0 - y_norm)))
        for x in range(w):
            if sp[x, y][3] < ALPHA_THRESH:
                continue
            nx = x + dx + lsh
            ny = y + dy + ssh
            if 0 <= nx < w and 0 <= ny < h:
                op[nx, ny] = sp[x, y]
    return out


def find_top_opaque(img: Image.Image) -> tuple[int, int] | None:
    """Return the (x, y) of the topmost opaque pixel — used to anchor
    the tip glow."""
    w, h = img.size
    px = img.load()
    for y in range(h):
        for x in range(w):
            if px[x, y][3] >= ALPHA_THRESH:
                return (x, y)
    return None


def paint_glow_cluster(img: Image.Image, cx: int, cy: int,
                        color: tuple[int, int, int],
                        intensity: float) -> Image.Image:
    """Paint a glow cluster at (cx, cy). At low intensity (<0.7) it's a
    subtle 9-pixel cross. At high intensity (>=0.7) — the attack-peak
    "staff light flash" — it expands into a 21-pixel radial burst with
    cardinal rays out to distance 3 + diagonal rays out to distance 2.
    The burst reads as a magical flare at the orb / blade-tip the
    instant the strike lands."""
    if intensity <= 0:
        return img
    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    if intensity >= 0.7:
        # Burst flash — peak strike frame. Center + 8-neighborhood +
        # cardinal rays at distance 2 and 3 + diagonal rays at distance 2.
        spots = [
            (0, 0, 1.00),
            (-1, 0, 0.90), (1, 0, 0.90),
            (0, -1, 0.90), (0, 1, 0.90),
            (-1, -1, 0.70), (1, -1, 0.70),
            (-1, 1, 0.70),  (1, 1, 0.70),
            (-2, 0, 0.55), (2, 0, 0.55),
            (0, -2, 0.55), (0, 2, 0.55),
            (-2, -1, 0.35), (2, -1, 0.35),
            (-2, 1, 0.35),  (2, 1, 0.35),
            (-1, -2, 0.35), (1, -2, 0.35),
            (-1, 2, 0.35),  (1, 2, 0.35),
            (-3, 0, 0.30), (3, 0, 0.30),
            (0, -3, 0.30), (0, 3, 0.30),
        ]
    else:
        spots = [
            (0, 0,  1.0),
            (-1, 0, 0.65), (1, 0, 0.65),
            (0, -1, 0.65), (0, 1, 0.65),
            (-1, -1, 0.40), (1, -1, 0.40),
            (-1, 1, 0.40),  (1, 1, 0.40),
        ]
    for (ox, oy, factor) in spots:
        x = cx + ox
        y = cy + oy
        if not (0 <= x < w and 0 <= y < h):
            continue
        a = int(255 * intensity * factor)
        if a <= 0:
            continue
        existing = op[x, y]
        nr = min(255, existing[0] + (color[0] - existing[0]) * a // 255)
        ng = min(255, existing[1] + (color[1] - existing[1]) * a // 255)
        nb = min(255, existing[2] + (color[2] - existing[2]) * a // 255)
        na = max(existing[3], a)
        op[x, y] = (nr, ng, nb, na)
    return out


CRESCENT_PALETTES = {
    # (shadow / fill / highlight) — three radial bands, dark on the
    # inner edge, mid-tone fill, bright rim on the outer edge. Matches
    # the "painted crescent" look of classic action-game slash effects.
    "silver": ((45, 55, 75), (190, 195, 210), (248, 250, 255)),
    "steel":  ((30, 35, 50), (165, 170, 185), (240, 244, 252)),
}


def paint_crescent_slash(img: Image.Image,
                          pivot: tuple[float, float],
                          r_inner: float, r_outer: float,
                          start_deg: float, end_deg: float,
                          palette: str = "silver",
                          max_alpha: int = 235,
                          streaks: bool = True) -> Image.Image:
    """Paint a bold, painted-looking crescent slash — the kind seen in
    classic action-game sprite work where a single solid swoosh dominates
    the frame.

    Built from three radial gaussian bands so the crescent has 3D depth:
      - inner shadow ring (dark, hugs r_inner)
      - mid fill body  (light grey, fills the bulk of the band)
      - outer highlight rim (bright silver, hugs r_outer)
    Bands blend smoothly into each other — no hard band boundaries.

    Angular alpha tapers as sin(t*pi)^0.55, so opacity peaks at the
    middle of the sweep and fades cleanly to zero at start_deg and
    end_deg, giving the elegantly tapered crescent points.

    Optional internal streaks add radial motion lines (slightly brighter
    every ~10° of sweep) to convey direction of the swing.
    """
    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    px, py = pivot

    sweep = end_deg - start_deg
    if abs(sweep) < 1.0 or r_outer <= r_inner:
        return out

    shadow_rgb, fill_rgb, hi_rgb = CRESCENT_PALETTES[palette]

    x_min = max(0, int(px - r_outer - 1))
    x_max = min(w, int(px + r_outer + 2))
    y_min = max(0, int(py - r_outer - 1))
    y_max = min(h, int(py + r_outer + 2))

    band = r_outer - r_inner
    for y in range(y_min, y_max):
        for x in range(x_min, x_max):
            dx = x - px
            dy = y - py
            r = math.sqrt(dx * dx + dy * dy)
            if r < r_inner - 0.5 or r > r_outer + 0.5:
                continue
            # Wrap-aware angle test against [start_deg, end_deg].
            angle = math.degrees(math.atan2(-dy, dx))
            ang_local = None
            for trial in (angle, angle + 360.0, angle - 360.0):
                if min(start_deg, end_deg) <= trial <= max(start_deg, end_deg):
                    ang_local = trial - start_deg
                    break
            if ang_local is None:
                continue
            t = ang_local / sweep  # 0..1 along the sweep
            if t < 0.0 or t > 1.0:
                continue

            # Tapered angular profile — 0 at endpoints, 1 in the middle.
            ang_alpha = math.sin(t * math.pi) ** 0.55
            if ang_alpha <= 0.01:
                continue

            # Radial position 0..1 across the band.
            rt = (r - r_inner) / band
            rt = max(0.0, min(1.0, rt))

            # Three gaussian peaks — shadow, fill, highlight.
            s_w = math.exp(-((rt - 0.10) / 0.13) ** 2)
            f_w = math.exp(-((rt - 0.50) / 0.32) ** 2)
            h_w = math.exp(-((rt - 0.92) / 0.10) ** 2)
            tot = s_w + f_w + h_w
            if tot <= 0.001:
                continue
            r_alpha = min(1.0, tot)

            # Weighted color blend.
            cr = (shadow_rgb[0]*s_w + fill_rgb[0]*f_w + hi_rgb[0]*h_w) / tot
            cg = (shadow_rgb[1]*s_w + fill_rgb[1]*f_w + hi_rgb[1]*h_w) / tot
            cb = (shadow_rgb[2]*s_w + fill_rgb[2]*f_w + hi_rgb[2]*h_w) / tot

            # Internal motion streaks — modulate brightness on the fill
            # band only (don't disturb shadow/highlight bands).
            if streaks and 0.18 < rt < 0.82:
                # ~9 streaks across the sweep, biased bright.
                phase = math.sin(t * 9.0 * math.pi)
                if phase > 0.55:
                    boost = (phase - 0.55) * 90.0  # +0..40 brightness
                    cr = min(255, cr + boost)
                    cg = min(255, cg + boost)
                    cb = min(255, cb + boost)
                elif phase < -0.55:
                    dim = (-phase - 0.55) * 70.0  # -0..32 brightness
                    cr = max(0, cr - dim)
                    cg = max(0, cg - dim)
                    cb = max(0, cb - dim)

            final_alpha = int(max_alpha * ang_alpha * r_alpha)
            if final_alpha <= 0:
                continue

            existing = op[x, y]
            er, eg, eb, ea = existing
            sa = final_alpha / 255.0
            inv_sa = 1.0 - sa
            nr = int(cr * sa + er * inv_sa)
            ng = int(cg * sa + eg * inv_sa)
            nb = int(cb * sa + eb * inv_sa)
            na = max(ea, final_alpha)
            op[x, y] = (nr, ng, nb, na)
    return out


def rotate_around(img: Image.Image, angle_deg: float,
                   pivot: tuple[int, int]) -> Image.Image:
    """Rotate img around the given pivot point on the canvas. Same-size
    output. PIL's rotate uses NEAREST sampling (preserves pixel-art),
    angle is positive CCW."""
    return img.rotate(angle_deg, resample=Image.NEAREST,
                       center=pivot, expand=False)


def render_blade_swing_frame(weapon_static: Image.Image,
                              prev_angle: float, curr_angle: float,
                              pivot: tuple[int, int],
                              ghost_count: int = 6,
                              ghost_alpha: int = 110) -> Image.Image:
    """Render the sword at curr_angle PLUS a motion-blur trail of N
    ghost copies at angles linearly interpolated from prev_angle to
    curr_angle. The ghosts are painted faintest (closest to prev) to
    brightest (closest to curr), and the current sword sits on top.
    Together the ghosts form the swept-arc trail.

    The blade itself is what creates the arc — there is no separate
    overlay shape. This is the classic action-game sword-slash effect.
    """
    canvas = Image.new("RGBA", weapon_static.size, (0, 0, 0, 0))
    if abs(curr_angle - prev_angle) < 0.5:
        # No real motion — just place sword at curr_angle, no trail.
        return rotate_around(weapon_static, curr_angle, pivot)
    # Ghost copies — paint from oldest (closest to prev_angle) to newest.
    for k in range(ghost_count, 0, -1):
        # t = 0 is at prev, t = 1 is at curr; we use t in (0, 1)
        t = k / float(ghost_count + 1)
        a_deg = prev_angle + t * (curr_angle - prev_angle)
        ghost = rotate_around(weapon_static, a_deg, pivot)
        # Alpha tapers: oldest ghosts are faintest.
        ghost_a = (ghost_alpha * (1.0 - (1.0 - t) * 0.7)) / 255.0
        ghost = apply_alpha(ghost, ghost_a)
        canvas = Image.alpha_composite(canvas, ghost)
    # Current sword — full alpha, on top.
    current = rotate_around(weapon_static, curr_angle, pivot)
    canvas = Image.alpha_composite(canvas, current)
    return canvas


def paint_motion_streak(img: Image.Image, x: int, y_start: int, y_end: int,
                         color: tuple[int, int, int],
                         max_alpha: int = 110) -> Image.Image:
    """Paint a vertical fading streak at column x from y_start (brighter,
    near tip) toward y_end (dimmer, where the tip used to be). Reads as
    motion blur behind a fast-moving glowing object. Each pixel blends
    additively toward `color` with alpha tapered by distance from the
    starting end."""
    if y_start == y_end:
        return img
    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    step = 1 if y_end > y_start else -1
    span = abs(y_end - y_start)
    for k in range(1, span + 1):
        y = y_start + k * step
        if not (0 <= x < w and 0 <= y < h):
            continue
        # Linear taper from max_alpha (near start) to 0 (at y_end).
        a = int(max_alpha * (1.0 - k / float(span + 1)))
        if a <= 0:
            continue
        existing = op[x, y]
        nr = min(255, existing[0] + (color[0] - existing[0]) * a // 255)
        ng = min(255, existing[1] + (color[1] - existing[1]) * a // 255)
        nb = min(255, existing[2] + (color[2] - existing[2]) * a // 255)
        na = max(existing[3], a)
        op[x, y] = (nr, ng, nb, na)
    return out


def translate(img: Image.Image, dx: int, dy: int) -> Image.Image:
    """Translate the image by (dx, dy). Pixels going out of the canvas
    are dropped."""
    if dx == 0 and dy == 0:
        return img.convert("RGBA").copy()
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy), img)
    return out


def split_strip_to_frames(strip: Image.Image, n: int) -> list:
    """Split a horizontal strip into a list of N frames."""
    return [strip.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME)) for i in range(n)]


def join_frames_to_strip(frames: list) -> Image.Image:
    """Join a list of frames back into a horizontal strip."""
    n = len(frames)
    out = Image.new("RGBA", (FRAME * n, FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        out.paste(f, (i * FRAME, 0), f)
    return out


# ---------------------------------------------------------------------------
# CORE
# ---------------------------------------------------------------------------

def split_anim(piece: str, color: str, anim: str) -> dict:
    src_dir = WHITE_DIR if color == "white" else BLACK_DIR
    pdir = src_dir / piece
    body_static = pdir / "body_static.png"
    weapon_static_path = pdir / "weapon_static.png"
    full_anim_path = pdir / f"{anim}.png"
    body_out = pdir / f"body_{anim}.png"
    weapon_out = pdir / f"weapon_{anim}.png"

    if not (body_static.exists() and weapon_static_path.exists()
            and full_anim_path.exists()):
        return {"piece": piece, "color": color, "anim": anim,
                "status": "skip"}

    body_img = Image.open(body_static).convert("RGBA")
    weapon_img = Image.open(weapon_static_path).convert("RGBA")
    full_strip = Image.open(full_anim_path).convert("RGBA")

    # Pose y-span: silhouette of the BODY (which equals the full
    # composite's silhouette since the weapon is inside the body's
    # y-range for all 5 pieces).
    body_ys_min, body_ys_max = silhouette_yspan(body_img)

    poses = POSES[anim]
    n = len(poses)
    expected_w = FRAME * n
    if full_strip.size != (expected_w, FRAME):
        return {"piece": piece, "color": color, "anim": anim,
                "status": "size_mismatch",
                "got": full_strip.size, "expected": (expected_w, FRAME)}

    overlaps = WEAPON_OVERLAPS_BODY.get(piece, False)
    extras = WEAPON_EXTRAS.get(piece, {}).get(anim, None)
    glow_color = WEAPON_GLOW_COLOR.get(piece, (255, 255, 255))

    full_frames = split_strip_to_frames(full_strip, n)
    body_frames = []
    weapon_frames = []
    non_weapon_diffs_total = 0

    for i, (dx, dy, squash, lean_top) in enumerate(poses):
        # Lockstep weapon frame using body's y-span.
        lock = transformed_with_yspan(weapon_img, dx, dy, squash, lean_top,
                                       body_ys_min, body_ys_max)

        # Body frame: existing - lockstep mask (with row-fill if overlaps)
        full_frame = full_frames[i]
        body_frame = full_frame.copy()
        bp = body_frame.load()
        wm = alpha_mask(lock)
        for y in range(FRAME):
            for x in range(FRAME):
                if not wm[x][y]:
                    continue
                if overlaps:
                    bp[x, y] = fill_from_nearest_in_row(full_frame, wm, x, y)
                else:
                    bp[x, y] = (0, 0, 0, 0)

        # Verify body == full where mask is OFF.
        bcheck = body_frame.load()
        fcheck = full_frame.load()
        for y in range(FRAME):
            for x in range(FRAME):
                if wm[x][y]:
                    continue
                if bcheck[x, y] != fcheck[x, y]:
                    non_weapon_diffs_total += 1

        body_frames.append(body_frame)

        # Weapon frame layers (in z-order from back to front):
        #   1. lockstep  (the weapon image transformed in body-pose)
        #      OR for swords during attack: rotated blade with
        #      motion-blur ghost trail — this REPLACES lockstep
        #   2. extras translate  (e.g., raised staff position at peak)
        #   3. motion streak  (vertical glow trail — staves only)
        #   4. tip glow burst  (radial flare at the weapon tip — peak)
        #
        # For sword pieces (BLADE_SWING) on the ATTACK animation, the
        # blade itself rotates through the swing arc and the motion-blur
        # ghosts of past angles form the slash trail. For non-attack
        # anims (move/hit/death), the sword stays in lockstep with the
        # body — no rotation, no swing.
        blade_cfg = BLADE_SWING.get(piece) if anim == "attack" else None
        crescent_cfg = CRESCENT_SLASH.get(piece) if anim == "attack" else None
        if blade_cfg is not None:
            angles = blade_cfg["attack_angles"]
            curr_a = angles[i] if i < len(angles) else 0.0
            prev_a = angles[i - 1] if i > 0 and i - 1 < len(angles) else curr_a
            # Synthetic sword override — for pieces where weapon_static
            # is transparent (sword baked into baseline). Built once
            # per-piece in memory.
            blade_img = weapon_img
            synth = blade_cfg.get("synthetic")
            if synth == "assassin_sword":
                blade_img = make_synthetic_assassin_sword()
            # Paint crescent FIRST so the blade rides on top of it.
            weapon_frame = Image.new("RGBA", weapon_img.size, (0, 0, 0, 0))
            if crescent_cfg is not None:
                cf = crescent_cfg["attack_frames"]
                if i < len(cf) and cf[i] is not None:
                    weapon_frame = paint_crescent_slash(
                        weapon_frame,
                        pivot=crescent_cfg["pivot"],
                        r_inner=cf[i]["r_inner"],
                        r_outer=cf[i]["r_outer"],
                        start_deg=cf[i]["start_deg"],
                        end_deg=cf[i]["end_deg"],
                        palette=crescent_cfg.get("palette", "silver"),
                        max_alpha=cf[i]["max_alpha"],
                    )
            blade_frame = render_blade_swing_frame(
                blade_img,
                prev_angle=prev_a, curr_angle=curr_a,
                pivot=blade_cfg["pivot"],
                ghost_count=blade_cfg["ghost_count"],
                ghost_alpha=blade_cfg["ghost_alpha"],
            )
            # Per-frame alpha (e.g., F0/F5 sheathed = invisible).
            fa = blade_cfg.get("frame_alphas")
            if fa is not None and i < len(fa) and fa[i] < 1.0:
                blade_frame = apply_alpha(blade_frame, fa[i])
            weapon_frame = Image.alpha_composite(weapon_frame, blade_frame)
        else:
            weapon_frame = lock
        if extras is not None and i < len(extras):
            ex_dx, ex_dy, glow_int = extras[i]
            if ex_dx or ex_dy:
                weapon_frame = translate(weapon_frame, ex_dx, ex_dy)
            # Motion streak — for staves/scepters that raise vertically
            # (bishop, king), draw a fading glow trail BELOW the new
            # tip showing where the orb just came from. Only apply when
            # the raise is significant (|ex_dy| >= 5).
            if (piece in ("bishop", "king") and ex_dy is not None
                    and ex_dy <= -5 and glow_int > 0):
                new_tip = find_top_opaque(weapon_frame)
                if new_tip is not None:
                    streak_len = abs(ex_dy)
                    weapon_frame = paint_motion_streak(
                        weapon_frame, new_tip[0],
                        y_start=new_tip[1] + 1,
                        y_end=new_tip[1] + streak_len,
                        color=glow_color,
                        max_alpha=int(95 * glow_int),
                    )
            if glow_int > 0:
                tip = find_top_opaque(weapon_frame)
                if tip is not None:
                    weapon_frame = paint_glow_cluster(
                        weapon_frame, tip[0], tip[1], glow_color, glow_int)

        # Anim modifiers (mirror wizard_animations.py per-anim post-pass).
        if anim == "hit" and i < len(HIT_FLASH):
            if HIT_FLASH[i] > 0:
                weapon_frame = apply_flash(weapon_frame, HIT_FLASH[i])
        elif anim == "attack" and i < len(ATTACK_FLASH):
            if ATTACK_FLASH[i] > 0:
                weapon_frame = apply_flash(weapon_frame, ATTACK_FLASH[i])
        elif anim == "death" and i < len(DEATH_ALPHAS):
            weapon_frame = apply_alpha(weapon_frame, DEATH_ALPHAS[i])

        weapon_frames.append(weapon_frame)

    body_strip = join_frames_to_strip(body_frames)
    weapon_strip = join_frames_to_strip(weapon_frames)
    body_strip.save(body_out)
    weapon_strip.save(weapon_out)

    status = "PASS" if non_weapon_diffs_total == 0 else "FAIL"
    return {"piece": piece, "color": color, "anim": anim,
            "status": "ok", "verify": status,
            "non_weapon_diffs": non_weapon_diffs_total,
            "frames": n, "extras": extras is not None}


def main():
    pieces_with_weapons = [p for p, accs in PIECES_ACCESSORIES.items()
                            if any(a.weapon for a in accs)]
    pieces_to_process = pieces_with_weapons + list(ARC_ONLY_PIECES)
    print(f"weapon-bearing pieces: {pieces_with_weapons}")
    print(f"arc-only pieces:       {list(ARC_ONLY_PIECES)}\n")
    print(f"{'piece':14s} {'color':5s} {'anim':6s} {'frames':3s} {'extras':6s} "
          f"{'diffs':6s} {'verify':6s}")
    print("-" * 60)

    fail = 0
    for piece in pieces_to_process:
        for color in ("white", "black"):
            for anim in ANIMS:
                r = split_anim(piece, color, anim)
                if r["status"] == "skip":
                    continue
                if r["status"] != "ok":
                    print(f"  {piece:14s} {color:5s} {anim:6s} {r}")
                    fail += 1
                    continue
                tag = r["verify"]
                ex = "yes" if r["extras"] else "no"
                print(f"  {piece:14s} {color:5s} {anim:6s} {r['frames']:3d} "
                      f"{ex:6s} {r['non_weapon_diffs']:6d} {tag}")
                if r["non_weapon_diffs"] != 0:
                    fail += 1

    if fail:
        print(f"\nFAIL: {fail} animations had pixel diffs outside weapon mask")
        sys.exit(1)
    else:
        print("\nALL PASS — every body_<anim>.png matches the existing "
              "<anim>.png everywhere outside its weapon's lockstep mask")


if __name__ == "__main__":
    main()
