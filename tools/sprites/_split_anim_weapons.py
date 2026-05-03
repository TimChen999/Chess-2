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

    overlaps = WEAPON_OVERLAPS_BODY[piece]
    extras = WEAPON_EXTRAS.get(piece, {}).get(anim, None)
    glow_color = WEAPON_GLOW_COLOR[piece]

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

        # Weapon frame: lockstep + extras + anim modifiers + glow burst
        # at peak + motion streak for vertical-raise weapons.
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
    print(f"weapon-bearing pieces: {pieces_with_weapons}\n")
    print(f"{'piece':14s} {'color':5s} {'anim':6s} {'frames':3s} {'extras':6s} "
          f"{'diffs':6s} {'verify':6s}")
    print("-" * 60)

    fail = 0
    for piece in pieces_with_weapons:
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
