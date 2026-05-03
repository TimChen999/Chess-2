"""Wizards' Guild animation strips — procedural per-frame transforms
applied to each piece's wizard static.

For each piece + animation, we produce a horizontal frame strip (W*N
wide, H tall, where W = H = 64). Each frame is the wizard static
transformed by a (dx, dy, squash, lean_dx_top) pose entry — a sheared
translate-and-squash that gives a recognizable motion at sprite scale.

Hit adds a per-frame brightness flash. Death adds a sparkle dust
falling alongside the fading body.

No PixelLab calls — deterministic, free, fast.

Run: python tools/sprites/wizard_animations.py
     python tools/sprites/wizard_animations.py --only bishop king
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"

FRAME = 64
ALPHA_THRESH = 8

OUTLINE = (40, 40, 50, 255)

PIECES = ["pawn", "rook", "knight", "bishop", "queen", "king",
          "bandit_pawn", "alter_knight", "assassin_bishop"]

# ---------------------------------------------------------------------------
# Per-frame pose deltas: (dx, dy, squash, lean_dx_top).
# Borrowed from generate_sprites.py — the timing reads consistently
# across all pieces.
# ---------------------------------------------------------------------------
POSES = {
    "static": [(0, 0, 0, 0)],
    "move": [
        (0,  0, 0,  1),
        (0, -2, 0,  0),
        (0, -3, 0, -1),
        (0, -2, 0,  0),
        (0, -1, 0,  1),
        (0,  0, 0,  0),
    ],
    "attack": [
        # Wind up (lean back), swing forward (lean ahead hard), recover.
        (-1,  1, 0, -4),
        (-3,  2, 0, -7),
        ( 4,  0, 0,  9),
        ( 7,  0, 0, 13),
        ( 3,  0, 0,  5),
        ( 0,  0, 0,  0),
    ],
    "hit": [
        ( 2, 0, 0, 0),
        (-2, 0, 0, 0),
        ( 0, 0, 0, 0),
    ],
    "death": [
        (0, 0,  0, 0),
        (0, 0,  4, 0),
        (0, 0,  9, 0),
        (0, 0, 16, 0),
        (0, 0, 24, 0),
    ],
    "move_jump": [
        (0,  0, 3,  0),
        (0, -3, 0,  0),
        (0, -7, 0,  0),
        (0, -10, 0, 0),
        (0, -7, 0,  0),
        (0, -3, 0,  0),
        (0,  0, 3,  0),
    ],
    "attack_lunge": [
        (-2,  1, 0, -5),
        (-4,  2, 0, -7),
        ( 5,  0, 0,  8),
        ( 8,  0, 0, 10),
        ( 7,  0, 0,  9),
        ( 3,  0, 0,  4),
        ( 0,  0, 0,  0),
    ],
}

EXTRA_PIECES = {
    "move_jump": ["knight", "alter_knight"],
    "attack_lunge": ["alter_knight"],
}

# Hit-flash intensity per frame (0..1 = full body tinted toward white).
HIT_FLASH = [0.85, 0.50, 0.00]

# Attack-flash intensity — a subtle bright pulse on the swing-peak frames
# (frames 2, 3) to emphasize the strike. 0 = no flash.
ATTACK_FLASH = [0.0, 0.0, 0.18, 0.30, 0.10, 0.0]

# Death alpha attenuation per frame.
DEATH_ALPHAS = [1.0, 0.85, 0.65, 0.4, 0.18]


# ---------------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------------

def transformed(static: Image.Image, dx: int, dy: int, squash: int,
                lean_top: int) -> Image.Image:
    """Apply the pose transform to a 64x64 static and return a new
    64x64 RGBA. Each pixel is mapped:
        new_y = orig_y + dy + (squash * orig_y_norm_from_top)   (compresses
                                                                  toward bottom)
        new_x = orig_x + dx + (lean_top * (1 - y_norm))         (top leans;
                                                                  bottom stays)
    where y_norm goes 0 at top to 1 at bottom of the silhouette bbox.
    Out-of-bounds pixels are dropped.
    """
    w, h = static.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sp = static.load()
    op = out.load()
    # Find silhouette bbox to normalize y for the lean blend.
    ys_min, ys_max = h, 0
    for y in range(h):
        for x in range(w):
            if sp[x, y][3] >= ALPHA_THRESH:
                ys_min = min(ys_min, y)
                ys_max = max(ys_max, y)
                break
    if ys_max <= ys_min:
        return out
    span = max(1, ys_max - ys_min)
    for y in range(h):
        # Skip rows that won't be drawn after squash.
        if y < ys_min or y > ys_max:
            for x in range(w):
                if sp[x, y][3] < ALPHA_THRESH:
                    continue
                nx = x + dx
                ny = y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    op[nx, ny] = sp[x, y]
            continue
        y_norm = (y - ys_min) / span    # 0 at top, 1 at bottom
        # Squash compresses toward bottom: rows shift downward by
        # squash * (1 - y_norm) — top rows move down most, bottom rows
        # don't move.
        ssh = int(round(squash * (1.0 - y_norm)))
        # Lean: top rows shift in lean direction by lean_top * (1 - y_norm).
        lsh = int(round(lean_top * (1.0 - y_norm)))
        for x in range(w):
            if sp[x, y][3] < ALPHA_THRESH:
                continue
            nx = x + dx + lsh
            ny = y + dy + ssh
            if 0 <= nx < w and 0 <= ny < h:
                op[nx, ny] = sp[x, y]
    return out


def apply_alpha(img: Image.Image, alpha_mul: float) -> Image.Image:
    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = op[x, y]
            if a < ALPHA_THRESH:
                continue
            op[x, y] = (r, g, b, max(0, min(255, int(a * alpha_mul))))
    return out


def apply_flash(img: Image.Image, intensity: float) -> Image.Image:
    """Lighten every opaque pixel toward white by `intensity` (0..1)."""
    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = op[x, y]
            if a < ALPHA_THRESH:
                continue
            r2 = int(r + (255 - r) * intensity)
            g2 = int(g + (255 - g) * intensity)
            b2 = int(b + (255 - b) * intensity)
            op[x, y] = (r2, g2, b2, a)
    return out


def add_death_sparkles(frame: Image.Image, sparkle_seed: int,
                       progress: float) -> Image.Image:
    """Sprinkle a few falling-sparkle pixels around the body, with
    intensity based on progress (0..1). Sparkles use OUTLINE color
    (dark) for visibility on either team."""
    rng = random.Random(sparkle_seed)
    out = frame.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    n = int(2 + progress * 6)   # 2 → 8 sparkles
    for _ in range(n):
        # Random position in body center area
        x = rng.randint(20, w - 20)
        # Sparkle falls — y range based on progress
        y0 = int(20 + progress * 30)
        y = rng.randint(max(0, y0 - 6), min(h - 1, y0 + 10))
        if 0 <= x < w and 0 <= y < h:
            # Sparkle is bright pixel — use a near-OUTLINE dark for
            # visibility against cream, or accent gold-ish.
            op[x, y] = (220, 200, 90, 255)   # gold sparkle
    return out


# ---------------------------------------------------------------------------
# BUILD STRIPS
# ---------------------------------------------------------------------------

def build_strip(static: Image.Image, anim: str, piece: str,
                color: str) -> Image.Image:
    poses = POSES[anim]
    n = len(poses)
    strip = Image.new("RGBA", (FRAME * n, FRAME), (0, 0, 0, 0))
    for i, (dx, dy, squash, lean_top) in enumerate(poses):
        frame = transformed(static, dx, dy, squash, lean_top)
        if anim == "hit":
            frame = apply_flash(frame, HIT_FLASH[i])
        elif anim == "attack":
            if i < len(ATTACK_FLASH) and ATTACK_FLASH[i] > 0:
                frame = apply_flash(frame, ATTACK_FLASH[i])
        elif anim == "death":
            frame = apply_alpha(frame, DEATH_ALPHAS[i])
            progress = i / max(1, n - 1)
            seed = hash((piece, color, "death", i)) & 0xFFFF
            frame = add_death_sparkles(frame, seed, progress)
        strip.paste(frame, (i * FRAME, 0), frame)
    return strip


def process(piece: str, color: str) -> dict:
    src_dir = WHITE_DIR if color == "white" else BLACK_DIR
    static_path = src_dir / piece / "static.png"
    if not static_path.exists():
        return {"piece": piece, "color": color, "status": "missing"}
    static = Image.open(static_path).convert("RGBA")
    saved = []
    for anim in POSES.keys():
        if anim == "static":
            continue
        if anim in EXTRA_PIECES and piece not in EXTRA_PIECES[anim]:
            continue
        strip = build_strip(static, anim, piece, color)
        out_path = src_dir / piece / f"{anim}.png"
        strip.save(out_path)
        saved.append(anim)
    return {"piece": piece, "color": color, "status": "ok",
            "saved": saved}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    only = set(args.only) if args.only else None
    for piece in PIECES:
        if only and piece not in only:
            continue
        for color in ["white", "black"]:
            r = process(piece, color)
            if r["status"] == "ok":
                print(f"[{piece} / {color}] saved: {', '.join(r['saved'])}")
            else:
                print(f"[{piece} / {color}] {r['status']}")


if __name__ == "__main__":
    main()
