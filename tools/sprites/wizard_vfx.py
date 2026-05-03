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
# LIGHTNING — 6 frames: charge glow → bolt → flash → fade
# ---------------------------------------------------------------------------

def build_lightning(client, force: bool) -> Image.Image:
    bolt = gen_atom(client, "lightning_bolt",
                    "a tall vertical jagged bright white-yellow lightning bolt with two short branching forks, dark outline",
                    seed=8201, force=force)
    flash = gen_atom(client, "lightning_flash",
                     "a bright white circular impact flash with yellow rays radiating outward",
                     seed=8202, force=force)
    glow = gen_atom(client, "lightning_glow",
                    "a soft yellow glow halo, mostly transparent",
                    seed=8203, force=force)

    n = 6
    strip = Image.new("RGBA", (FRAME * n, FRAME), (0, 0, 0, 0))

    # Frame 0: faint charging glow at top
    glow_scaled = resize_atom(glow, 0.6)
    f0 = place_centered(FRAME, fade(glow_scaled, 0.55),
                        FRAME // 2, 8)
    strip.paste(f0, (0, 0), f0)

    # Frame 1: full lightning bolt from top to bottom
    bolt_trim = trim(bolt)
    # Stretch bolt to full canvas height (64 px tall)
    bw, bh = bolt_trim.size
    target_h = 56
    scale = target_h / bh
    bolt_full = bolt_trim.resize((max(1, int(bw * scale)), target_h),
                                  Image.NEAREST)
    f1 = place_centered(FRAME, bolt_full, FRAME // 2, FRAME // 2)
    strip.paste(f1, (FRAME, 0), f1)

    # Frame 2: bright flash at impact (bottom of canvas)
    flash_scaled = resize_atom(flash, 0.85)
    f2 = place_centered(FRAME, flash_scaled, FRAME // 2, 50)
    strip.paste(f2, (2 * FRAME, 0), f2)

    # Frame 3: bolt fading + glow at impact
    f3 = place_centered(FRAME, fade(bolt_full, 0.35),
                        FRAME // 2, FRAME // 2)
    glow_at_impact = resize_atom(glow, 0.7)
    layer3 = place_centered(FRAME, fade(glow_at_impact, 0.7),
                            FRAME // 2, 50)
    f3 = Image.alpha_composite(f3, layer3)
    strip.paste(f3, (3 * FRAME, 0), f3)

    # Frames 4-5: glow shrinks
    for i, (op_, sc) in enumerate([(0.5, 0.55), (0.2, 0.4)]):
        g = resize_atom(glow, sc)
        f = place_centered(FRAME, fade(g, op_), FRAME // 2, 50)
        strip.paste(f, ((4 + i) * FRAME, 0), f)
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
