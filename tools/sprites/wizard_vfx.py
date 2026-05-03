"""Wizards' Guild VFX strips — fireball, lightning, magic_rocks.

Approach: generate each VFX's *atoms* (one fireball image, one
explosion, one smoke wisp, one lightning bolt, one rock cluster, one
dust burst, etc.) ONCE via PixelLab pixflux. Then build the multi-frame
strip procedurally by translating the atoms to specific Y positions
per frame (so the fireball/rocks visibly fall from top to bottom).

This guarantees the falling motion that per-frame text generation
couldn't reliably produce.

Run: python tools/sprites/wizard_vfx.py
     python tools/sprites/wizard_vfx.py --only fireball
     python tools/sprites/wizard_vfx.py --force
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pixellab
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

FX_DIR = ROOT / "godot/assets/sprites/anim/fx"
CACHE_DIR = ROOT / "tools/sprites/_pixellab_cache"

FRAME = 64
ALPHA_THRESH = 8

STYLE_SUFFIX = (
    ", isolated single object, transparent background, dark outline, "
    "pixel art, no other objects, no text"
)


def load_client():
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    if not secret:
        sys.exit("error: PIXELLAB_API_KEY missing from .env")
    return pixellab.Client(secret=secret)


def cache_path(name: str, seed: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"vfx_atom_{name}_v3_seed{seed}.png"


def gen_atom(client, name: str, prompt: str, seed: int,
             force: bool, size: int = 64) -> Image.Image:
    cp = cache_path(name, seed)
    if cp.exists() and not force:
        print(f"   [cache] {cp.name}")
        return Image.open(cp).convert("RGBA")
    print(f"   [pixellab] {name} seed={seed}")
    resp = client.generate_image_pixflux(
        description=prompt + STYLE_SUFFIX,
        image_size={"width": size, "height": size},
        no_background=True,
        text_guidance_scale=11.0,
        seed=seed,
    )
    out = resp.image.pil_image().convert("RGBA")
    out.save(cp)
    return out


def opaque_bbox(img: Image.Image):
    px = img.load()
    w, h = img.size
    xs = [x for y in range(h) for x in range(w) if px[x, y][3] >= ALPHA_THRESH]
    ys = [y for y in range(h) for x in range(w) if px[x, y][3] >= ALPHA_THRESH]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def trim(img: Image.Image) -> Image.Image:
    bb = opaque_bbox(img)
    if bb is None:
        return img
    return img.crop((bb[0], bb[1], bb[2] + 1, bb[3] + 1))


def fade(img: Image.Image, alpha_mul: float) -> Image.Image:
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


def place_centered(canvas_size: int, atom: Image.Image,
                   cx: int, cy: int) -> Image.Image:
    """Return a (canvas_size × canvas_size) RGBA frame with the trimmed
    atom centered at (cx, cy)."""
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    a = trim(atom)
    aw, ah = a.size
    px = cx - aw // 2
    py = cy - ah // 2
    canvas.paste(a, (px, py), a)
    return canvas


def resize_atom(atom: Image.Image, scale: float) -> Image.Image:
    a = trim(atom)
    aw, ah = a.size
    new_size = (max(1, int(aw * scale)), max(1, int(ah * scale)))
    return a.resize(new_size, Image.NEAREST)


# ---------------------------------------------------------------------------
# FIREBALL — 14 frames: fireball falls top→bottom, impact, explosion, smoke
# ---------------------------------------------------------------------------

def build_fireball(client, force: bool) -> Image.Image:
    fb = gen_atom(client, "fireball", "a single bright orange-and-red fireball with flame trails behind it",
                  seed=8101, force=force)
    expl = gen_atom(client, "explosion", "a bright orange-and-yellow circular explosion with flame tongues",
                    seed=8102, force=force)
    smoke = gen_atom(client, "smoke", "a soft grey smoke cloud, mostly transparent wisps",
                     seed=8103, force=force)

    n = 14
    strip = Image.new("RGBA", (FRAME * n, FRAME), (0, 0, 0, 0))

    # Frames 0-5: fireball descends from y=8 to y=48, slight scale-up
    for i in range(6):
        progress = i / 5.0
        y = int(8 + progress * 40)
        scale = 0.55 + progress * 0.30   # 0.55 → 0.85
        fb_scaled = resize_atom(fb, scale)
        frame = place_centered(FRAME, fb_scaled, FRAME // 2, y)
        strip.paste(frame, (i * FRAME, 0), frame)

    # Frame 6: white-hot impact flash at y=52
    flash = expl.copy()
    # Tint flash to bright white
    fp = flash.load()
    fw, fh = flash.size
    for y in range(fh):
        for x in range(fw):
            r, g, b, a = fp[x, y]
            if a >= ALPHA_THRESH:
                fp[x, y] = (255, min(255, g + 80), min(255, b + 80), a)
    flash_scaled = resize_atom(flash, 0.85)
    frame = place_centered(FRAME, flash_scaled, FRAME // 2, 52)
    strip.paste(frame, (6 * FRAME, 0), frame)

    # Frames 7-11: explosion expands outward at the bottom
    for i in range(5):
        progress = (i + 1) / 5.0
        scale = 0.55 + progress * 0.65   # 0.55 → 1.20
        opacity = 1.0 - progress * 0.4
        expl_scaled = resize_atom(expl, scale)
        frame = place_centered(FRAME, fade(expl_scaled, opacity),
                               FRAME // 2, 48)
        strip.paste(frame, ((7 + i) * FRAME, 0), frame)

    # Frames 12-13: smoke dissipating
    for i, opacity in enumerate([0.55, 0.20]):
        smoke_scaled = resize_atom(smoke, 0.9 + i * 0.1)
        frame = place_centered(FRAME, fade(smoke_scaled, opacity),
                               FRAME // 2, 44 - i * 4)
        strip.paste(frame, ((12 + i) * FRAME, 0), frame)
    return strip


# ---------------------------------------------------------------------------
# LIGHTNING — 6 frames on a TALL canvas (64×256, 4 board squares tall).
# Reads as a true sky-strike: bolt grows downward across F0-F2 covering
# 4 squares of vertical extent, lands at the BOTTOM of the canvas
# (which Godot anchors to the target square's bottom), explodes into a
# radial spark on F3, then bolt+spark dissipate over F4-F5.
#
# The taller-than-square canvas is what makes the bolt feel like it
# comes from the sky — Godot positions the sprite so its bottom-72px
# fits the target square and its remaining 216 px extends UP above the
# target onto the squares overhead.
# ---------------------------------------------------------------------------

LIGHTNING_FRAME_W = 64
LIGHTNING_FRAME_H = 640        # 10 squares tall in source-pixel units —
                                # tall enough that the bolt's top edge is
                                # always at or above the top of the board
                                # regardless of which row the target is in,
                                # so the strike always reads as coming from
                                # the sky / off-screen above.
LIGHTNING_GROUND_Y = 628       # bolt tip + spark land here (~98% down)


def clip_below(img: Image.Image, max_y: int) -> Image.Image:
    """Return a copy of img where every pixel with y > max_y has alpha 0.
    Used to reveal the lightning bolt progressively from the top."""
    out = img.convert("RGBA").copy()
    p = out.load()
    w, h = out.size
    for y in range(max(0, max_y + 1), h):
        for x in range(w):
            r, g, b, a = p[x, y]
            if a:
                p[x, y] = (r, g, b, 0)
    return out


def _place_centered_xy(canvas_w: int, canvas_h: int, atom: Image.Image,
                        cx: int, cy: int) -> Image.Image:
    """place_centered() variant that takes separate w/h (so we can place
    onto a non-square canvas like the 64x256 lightning frame)."""
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    a = trim(atom)
    aw, ah = a.size
    canvas.paste(a, (cx - aw // 2, cy - ah // 2), a)
    return canvas


def _stretch_bolt_to_canvas(bolt_atom: Image.Image,
                              fw: int, fh: int,
                              ground_y: int,
                              max_w: int = 18) -> Image.Image:
    """Stretch a bolt atom to span from the top of the canvas down to
    `ground_y`, horizontally centered. Width is capped at `max_w` so
    the bolt stays thin after the vertical stretch."""
    bolt_trim = trim(bolt_atom)
    bw, bh = bolt_trim.size
    target_h = ground_y - 4
    scale = target_h / bh
    new_w = max(2, int(bw * scale))
    if new_w > max_w:
        new_w = max_w
    stretched = bolt_trim.resize((new_w, target_h), Image.NEAREST)
    canvas = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    canvas.paste(stretched, (fw // 2 - new_w // 2, 4), stretched)
    return canvas


def build_lightning(client, force: bool) -> Image.Image:
    # FIVE distinct bolt sprites — different PixelLab seeds give each
    # a unique zigzag path so every frame has its OWN bolt rather than
    # the same source clipped at different heights. Reads as real
    # lightning where each flash flickers a different shape.
    bolt_prompt = (
        "a single thin tall lightning bolt that spans the entire vertical extent "
        "of the frame from top edge to bottom edge, multiple sharp zigzag bends "
        "along its length, bright electric white core with pale blue glow halo, "
        "no branches, no forks"
    )
    # Stricter prompt for re-rolls — the loose bolt prompt sometimes
    # produces a smooth column / flame shape instead of an angular
    # zigzag, which doesn't read as lightning once stretched.
    zigzag_prompt = (
        "a single thin jagged lightning bolt made of sharp straight angular line "
        "segments with sudden direction changes every few pixels, classic Z-shape "
        "or N-shape zigzag pattern, vertical orientation, white electric core with "
        "blue outline, NOT a smooth column, NOT a flame, NOT a curved line"
    )
    bolt_a = gen_atom(client, "lightning_bolt_tall", bolt_prompt,
                      seed=8211, force=force)
    bolt_b = gen_atom(client, "lightning_bolt_b", bolt_prompt,
                      seed=8221, force=force)
    # bolt_c (seed 8231) and bolt_d (seed 8241) gave smooth columnar
    # shapes; regenerated under different seeds with a stricter zigzag
    # prompt. The original seeds stay in cache for diff purposes.
    bolt_c = gen_atom(client, "lightning_bolt_c2", zigzag_prompt,
                      seed=8232, force=force)
    bolt_d = gen_atom(client, "lightning_bolt_d2", zigzag_prompt,
                      seed=8242, force=force)
    bolt_e = gen_atom(client, "lightning_bolt_e", bolt_prompt,
                      seed=8251, force=force)

    spark = gen_atom(client, "lightning_flash",
                     "a bright white circular impact flash with yellow rays radiating outward",
                     seed=8202, force=force)
    glow = gen_atom(client, "lightning_glow",
                    "a soft yellow glow halo, mostly transparent",
                    seed=8203, force=force)

    n = 6
    fw = LIGHTNING_FRAME_W
    fh = LIGHTNING_FRAME_H
    strip = Image.new("RGBA", (fw * n, fh), (0, 0, 0, 0))

    # Five independent stretched-to-canvas bolt sprites. Each frame
    # below uses its own bolt — the only "clipping" happens on F0/F1
    # which legitimately need a partial bolt (sky-descent stage), and
    # those clips are applied to DIFFERENT source sprites so no two
    # frames share a silhouette.
    canvas_a = _stretch_bolt_to_canvas(bolt_a, fw, fh, LIGHTNING_GROUND_Y)
    canvas_b = _stretch_bolt_to_canvas(bolt_b, fw, fh, LIGHTNING_GROUND_Y)
    canvas_c = _stretch_bolt_to_canvas(bolt_c, fw, fh, LIGHTNING_GROUND_Y)
    canvas_d = _stretch_bolt_to_canvas(bolt_d, fw, fh, LIGHTNING_GROUND_Y)
    canvas_e = _stretch_bolt_to_canvas(bolt_e, fw, fh, LIGHTNING_GROUND_Y)

    # F0: bolt_a, only the top ~40% revealed — bolt forming high in sky.
    # On the 10-square-tall canvas this is roughly the top 4 squares of
    # the bolt, which on screen translates to the bolt being visible from
    # off-screen-above down to ~3 squares above the target square.
    f0 = clip_below(canvas_a, int(fh * 0.40))
    strip.paste(f0, (0, 0), f0)

    # F1: bolt_b, top ~75% revealed — different zigzag, mid-descent.
    # Visible from off-screen-above down to ~1 square above target.
    f1 = clip_below(canvas_b, int(fh * 0.75))
    strip.paste(f1, (fw, 0), f1)

    # F2: bolt_c full + small spark forming at the strike point.
    f2 = canvas_c.copy()
    spark_small = resize_atom(spark, 0.55)
    spark_early = _place_centered_xy(fw, fh, fade(spark_small, 0.55),
                                      fw // 2, LIGHTNING_GROUND_Y)
    f2 = Image.alpha_composite(f2, spark_early)
    strip.paste(f2, (2 * fw, 0), f2)

    # F3 PEAK: bolt_d (different jagged path again) + bright impact spark.
    f3 = canvas_d.copy()
    spark_peak = resize_atom(spark, 1.05)
    spark_layer3 = _place_centered_xy(fw, fh, spark_peak,
                                       fw // 2, LIGHTNING_GROUND_Y - 2)
    f3 = Image.alpha_composite(f3, spark_layer3)
    strip.paste(f3, (3 * fw, 0), f3)

    # F4: bolt_e fading + spark expanding outward.
    f4 = fade(canvas_e, 0.45)
    spark_wide = resize_atom(spark, 1.30)
    spark_layer4 = _place_centered_xy(fw, fh, fade(spark_wide, 0.70),
                                       fw // 2, LIGHTNING_GROUND_Y - 2)
    f4 = Image.alpha_composite(f4, spark_layer4)
    strip.paste(f4, (4 * fw, 0), f4)

    # F5: bolt gone, residual glow at the strike point.
    glow_scaled = resize_atom(glow, 0.85)
    f5 = _place_centered_xy(fw, fh, fade(glow_scaled, 0.40),
                             fw // 2, LIGHTNING_GROUND_Y - 2)
    strip.paste(f5, (5 * fw, 0), f5)
    return strip


# ---------------------------------------------------------------------------
# MAGIC ROCKS — 9 frames: rocks fall, impact, sparkle spread
# ---------------------------------------------------------------------------

def build_magic_rocks(client, force: bool) -> Image.Image:
    rocks = gen_atom(client, "magic_rocks",
                     "three jagged dark-grey rock chunks clustered together with a faint purple magical aura around them",
                     seed=8301, force=force)
    impact = gen_atom(client, "rocks_impact",
                      "a brown-and-purple dust burst with sparkle rays radiating outward, ground impact effect",
                      seed=8302, force=force)
    sparkles = gen_atom(client, "purple_sparkles",
                        "a swirl of purple sparkle particles spreading outward, mostly transparent",
                        seed=8303, force=force)

    n = 9
    strip = Image.new("RGBA", (FRAME * n, FRAME), (0, 0, 0, 0))

    # Frames 0-4: rocks descend
    for i in range(5):
        progress = i / 4.0
        y = int(10 + progress * 38)
        rocks_scaled = resize_atom(rocks, 0.75)
        f = place_centered(FRAME, rocks_scaled, FRAME // 2, y)
        strip.paste(f, (i * FRAME, 0), f)

    # Frame 5: impact at bottom
    impact_scaled = resize_atom(impact, 0.85)
    f5 = place_centered(FRAME, impact_scaled, FRAME // 2, 50)
    strip.paste(f5, (5 * FRAME, 0), f5)

    # Frames 6-8: sparkles spread + fade
    for i, (op_, sc) in enumerate([(0.85, 0.85), (0.55, 1.05), (0.20, 1.20)]):
        s = resize_atom(sparkles, sc)
        f = place_centered(FRAME, fade(s, op_), FRAME // 2, 48)
        strip.paste(f, ((6 + i) * FRAME, 0), f)
    return strip


# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------

VFX = {
    "fireball": ("cannon_resolve", build_fireball),
    "lightning": ("lightning_strike", build_lightning),
    "magic_rocks": ("debris_fall", build_magic_rocks),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    client = load_client()
    print(f"[pixellab] balance: {client.get_balance()}")
    only = set(args.only) if args.only else None
    for vfx, (out_name, build_fn) in VFX.items():
        if only and vfx not in only:
            continue
        print(f"\n=== {vfx} ===")
        strip = build_fn(client, args.force)
        out_path = FX_DIR / f"{out_name}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        strip.save(out_path)
        print(f"   saved -> {out_path.relative_to(ROOT)}  size={strip.size}")


if __name__ == "__main__":
    main()
