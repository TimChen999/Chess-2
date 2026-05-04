"""Medieval stage atoms — 4 tiles, 1 wood frame atlas, 1 stone backdrop.

Implements the plan in [medieval.md](medieval.md). Generates ONE PNG per
repeatable unit via PixelLab pixflux; Godot duplicates them at runtime
via GridContainer / NinePatchRect / TextureRect.

Run:
  python tools/stages/gen_medieval.py
  python tools/stages/gen_medieval.py --only tiles
  python tools/stages/gen_medieval.py --only frame
  python tools/stages/gen_medieval.py --only backdrop
  python tools/stages/gen_medieval.py --force
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
ASSETS = ROOT / "godot" / "assets" / "sprites"
TILES_DIR = ASSETS / "tiles" / "medieval"
UI_DIR = ASSETS / "ui"
INSPECT_DIR = ROOT / "tools" / "stages"
CACHE_DIR = ROOT / "tools" / "stages" / "_pixellab_cache"

TILE_PX = 64
FRAME_PX = 48
FRAME_CELL = 16
BACKDROP_PX = 128

TILE_STYLE_SUFFIX = (
    ", top-down 64x64 pixel art floor tile, EDGE-TO-EDGE coverage (no border, "
    "no padding, no vignette, no shadow), uniform mid-tone shading across the "
    "whole tile, opaque, no transparency, single material, ready to tile "
    "seamlessly with itself"
)

## Tiles are PROCEDURALLY drawn in PIL — not PixelLab. Each tile is a
## flat stone face with darker grooves at the sub-stone boundaries and
## subtle deterministic speckle noise. PIL is a strict win here because:
##   - we have absolute control over groove placement (always at the
##     outer edge of the tile, never mid-stone), so adjacency is
##     guaranteed to align regardless of which variant picks which.
##   - PixelLab repeatedly added internal cracks / mortar / structure
##     even when prompted not to, breaking edge alignment.
##   - "Interesting" detail comes from the macro overlay layer, so the
##     stone face only needs to be a believable flat surface.
##
## Variant pairs alternate 1×1 (one big slab) and 2×2 (four sub-stones
## per tile) — same outer-edge groove on every variant, so every
## adjacency butts cleanly. Variant picker is the deterministic
## ((f*7+r*13)>>1)&1 from the original spec.

# RGB tones for the two stones. Same hue family (warm grey-brown), one
# light and one dark — reads as the same floor cut from a lighter and
# darker vein. Groove color is a darkened version of base, computed at
# draw time.
TILE_LIGHT_RGB = (212, 198, 170)   # warm cream limestone
TILE_DARK_RGB = (108, 94, 78)      # warm umber stone

# One 1×1 slab per color — no variants. The 2×2 sub-stone variant
# was tried and consistently looked busier than a single uniform slab
# at the actual board scale, so we ship just light.png + dark.png.
TILE_VARIANTS = {
    "light": (TILE_LIGHT_RGB, 1),
    "dark":  (TILE_DARK_RGB, 1),
}

# Per-tile speckle seed — deterministic so re-runs reproduce the same
# noise pattern (avoids "tile looks slightly different after rerun").
TILE_SPECKLE_SEEDS = {
    "light": 17,
    "dark":  29,
}

OVERLAY_NATIVE = 256    # PixelLab caps at 400; 256 is the round size below
OVERLAY_PX = 512        # ship size — nearest-upscaled 2× from native
## Overlay features are deliberately FLAT (top-down view) and SHALLOW
## (cracks and dust, not 3D objects). PixelLab tends to interpret
## "moss patches" as 3D Minecraft-style grass blocks; "cracks and dust
## streaks" stays in 2D. We trade a little visual variety for asset
## reliability.
OVERLAY_PROMPT = (
    "TOP-DOWN VIEW of small flat detail markings scattered EVENLY across "
    "the ENTIRE canvas on a fully transparent background, including the "
    "center and the corners and everywhere in between. Features are "
    "FLAT 2D markings on a flat floor — NOT 3D objects, NOT blocks, NOT "
    "cubes, NOT pillars. Markings: thin dark hairline cracks (1-2 pixel "
    "wide squiggly lines), light dust streaks, dark scuffs, small dark "
    "specks. Random asymmetric placement, NO border concentration, NO "
    "empty center, NO clustering. About 70% of the canvas stays empty "
    "transparent background between features. Pixel art style, soft "
    "outlines, no single feature larger than 30 pixels, no repeating "
    "pattern"
)
OVERLAY_SEED = 9421

FRAME_PROMPT = (
    "3x3 sprite atlas on a 48x48 canvas, each cell exactly 16x16. Top row: "
    "top-left corner, top edge, top-right corner of a carved dark oak wood "
    "picture frame with iron rivets. Middle row: left edge, blank center, "
    "right edge. Bottom row: bottom-left corner, bottom edge, bottom-right "
    "corner. The corners are L-shaped wood joinery. The edges are straight "
    "wood beams. Ornamental but readable at small scale. No text, no "
    "background bleed between cells."
)
FRAME_SEED = 9201

## Backdrop is a SINGLE large stone slab. ONLY the four canvas edges
## have a darker shadow groove; the interior is completely uniform
## with NO internal divisions. When Godot tiles the texture, the edge
## grooves of adjacent tiles butt together to form clean intentional
## joints between slabs. Because the joints only ever appear at tile
## boundaries, they always align — never "cut off" mid-stone.
BACKDROP_PROMPT = (
    "ONE single uniform dark grey-brown stone slab face viewed top-down, "
    "128x128 pixel art. The slab fills the ENTIRE canvas edge-to-edge as "
    "one continuous piece. There is a slightly darker shadow groove ONLY "
    "along the four outer edges of the canvas (3 to 4 pixels wide on "
    "each edge), reading as the joint where this slab meets the next "
    "slab in a tiled floor. The interior of the slab is COMPLETELY "
    "uniform speckled stone grain with NO internal lines, NO internal "
    "joints, NO internal grid, NO 2x2 division, NO 3x3 division, NO "
    "central feature, NO bricks, NO sub-stones. Just one continuous "
    "slab face. Opaque, muted desaturated palette so it sits behind UI "
    "without competing, mid-dark tone"
)
BACKDROP_SEED = 9341

# Pair-mean RGB distance threshold for cross-variant color clamp (§3.1.4).
PAIR_MEAN_THRESHOLD = 15.0
# Backdrop luminance window (§3.3.4).
BACKDROP_LUMA_LOW = 0.18
BACKDROP_LUMA_HIGH = 0.32


# ---------------------------------------------------------------------------
# PixelLab client + cache
# ---------------------------------------------------------------------------

def load_client():
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    if not secret:
        sys.exit("error: PIXELLAB_API_KEY missing from .env")
    return pixellab.Client(secret=secret)


def cache_path(name: str, seed: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"medieval_{name}_seed{seed}.png"


def gen_atom(client, name: str, prompt: str, seed: int, size: int,
             force: bool) -> Image.Image:
    cp = cache_path(name, seed)
    if cp.exists() and not force:
        print(f"   [cache] {cp.name}")
        return Image.open(cp).convert("RGBA")
    print(f"   [pixellab] {name} seed={seed} size={size}")
    resp = client.generate_image_pixflux(
        description=prompt,
        image_size={"width": size, "height": size},
        text_guidance_scale=11.0,
        seed=seed,
    )
    out = resp.image.pil_image().convert("RGBA")
    out.save(cp)
    return out


# ---------------------------------------------------------------------------
# Shared PIL helpers
# ---------------------------------------------------------------------------

def assert_size(img: Image.Image, expected: int, name: str) -> Image.Image:
    if img.size == (expected, expected):
        return img
    print(f"   [warn] {name} returned {img.size}, resizing to "
          f"{expected}x{expected}")
    return img.resize((expected, expected), Image.NEAREST)


def force_opaque(img: Image.Image, name: str) -> Image.Image:
    """Strip alpha for tiles/backdrop. PixelLab sometimes leaves a few
    transparent pixels around object boundaries; on a chess tile that
    would let the backdrop bleed through and break the read. Force every
    pixel to alpha=255 (fail loudly if a substantial portion is
    transparent — that means the prompt produced an isolated object,
    not a tile)."""
    rgba = img.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    transparent = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 255:
                transparent += 1
                px[x, y] = (r, g, b, 255)
    total = w * h
    if transparent > total * 0.10:
        print(f"   [warn] {name}: {transparent}/{total} pixels were "
              f"transparent — prompt may have produced an isolated object")
    return rgba


def seam_blend(img: Image.Image) -> Image.Image:
    """Make a single tile butt seamlessly against itself in both axes.

    Average the opposite-edge pixel pairs (col 0 ↔ col W-1, row 0 ↔ row
    H-1), write that average to BOTH edges, feather 1px inward.

    Note: this only handles the self-tiling case. For a *set* of tiles
    that must also butt against each other (the chess checkerboard),
    use harmonize_seams() instead."""
    out = img.copy()
    w, h = out.size
    px = out.load()

    for y in range(h):
        l = px[0, y]
        r = px[w - 1, y]
        avg = tuple((a + b) // 2 for a, b in zip(l, r))
        px[0, y] = avg
        px[w - 1, y] = avg
        l1 = px[1, y]
        r1 = px[w - 2, y]
        px[1, y] = tuple((a * 2 + b) // 3 for a, b in zip(l1, avg))
        px[w - 2, y] = tuple((a * 2 + b) // 3 for a, b in zip(r1, avg))

    for x in range(w):
        t = px[x, 0]
        b = px[x, h - 1]
        avg = tuple((a + c) // 2 for a, c in zip(t, b))
        px[x, 0] = avg
        px[x, h - 1] = avg
        t1 = px[x, 1]
        b1 = px[x, h - 2]
        px[x, 1] = tuple((a * 2 + c) // 3 for a, c in zip(t1, avg))
        px[x, h - 2] = tuple((a * 2 + c) // 3 for a, c in zip(b1, avg))

    return out


def harmonize_seams(tiles: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """Force a *set* of same-size tiles to share identical edges so
    arbitrary checkerboard adjacency butts seamlessly.

    Why: a per-tile seam_blend only guarantees `tile.right == tile.left`,
    which lets one tile tile against ITSELF. On a real chessboard tile A
    sits next to tile B, so we also need `A.right == B.left`. The way
    to get that without manual eyeballing is: compute a SHARED edge
    (one column for left/right, one row for top/bottom) by averaging
    the corresponding edges across every tile in the set, then write
    that shared edge into every tile.

    After this pass, every tile shares: identical left column, identical
    right column (== left column), identical top row, identical bottom
    row (== top row). Any pair of tiles A,B in the set now butts
    seamlessly in any direction. A 2-pixel feather inward preserves
    each tile's unique interior."""
    names = list(tiles.keys())
    if not names:
        return tiles
    ref = tiles[names[0]]
    w, h = ref.size

    # Collect all four edges from every tile, average pixel-wise.
    shared_col = []
    for y in range(h):
        # Average left col 0 + right col W-1 of every tile at row y.
        rs = gs = bs = as_ = 0
        n = 0
        for name in names:
            p = tiles[name].load()
            for x in (0, w - 1):
                r, g, b, a = p[x, y]
                rs += r
                gs += g
                bs += b
                as_ += a
                n += 1
        shared_col.append((rs // n, gs // n, bs // n, as_ // n))

    shared_row = []
    for x in range(w):
        rs = gs = bs = as_ = 0
        n = 0
        for name in names:
            p = tiles[name].load()
            for y in (0, h - 1):
                r, g, b, a = p[x, y]
                rs += r
                gs += g
                bs += b
                as_ += a
                n += 1
        shared_row.append((rs // n, gs // n, bs // n, as_ // n))

    # Corners are over-determined (they appear in both shared_col AND
    # shared_row averages). Force the four corners to a single shared
    # value so any 4-tile junction lines up. Use the average of the
    # corner contributions from both edge sets.
    corner_tl = tuple(
        (shared_col[0][i] + shared_row[0][i]) // 2 for i in range(4))
    corner_tr = tuple(
        (shared_col[0][i] + shared_row[w - 1][i]) // 2 for i in range(4))
    corner_bl = tuple(
        (shared_col[h - 1][i] + shared_row[0][i]) // 2 for i in range(4))
    corner_br = tuple(
        (shared_col[h - 1][i] + shared_row[w - 1][i]) // 2 for i in range(4))

    out: dict[str, Image.Image] = {}
    for name in names:
        img = tiles[name].copy()
        px = img.load()
        # Write shared edges. Corners get the corner-specific value.
        for y in range(h):
            v = shared_col[y]
            px[0, y] = v
            px[w - 1, y] = v
        for x in range(w):
            v = shared_row[x]
            px[x, 0] = v
            px[x, h - 1] = v
        px[0, 0] = corner_tl
        px[w - 1, 0] = corner_tr
        px[0, h - 1] = corner_bl
        px[w - 1, h - 1] = corner_br

        # 2-pixel feather inward so the forced edges don't read as a
        # hard outline of the tile. Per-axis blend toward the interior.
        for y in range(h):
            for off, weight in ((1, 0.66), (2, 0.33)):
                # left side
                inner = px[off, y]
                edge = px[0, y]
                px[off, y] = tuple(
                    int(inner[i] * (1 - weight) + edge[i] * weight)
                    for i in range(4))
                # right side
                inner = px[w - 1 - off, y]
                edge = px[w - 1, y]
                px[w - 1 - off, y] = tuple(
                    int(inner[i] * (1 - weight) + edge[i] * weight)
                    for i in range(4))
        for x in range(w):
            for off, weight in ((1, 0.66), (2, 0.33)):
                inner = px[x, off]
                edge = px[x, 0]
                px[x, off] = tuple(
                    int(inner[i] * (1 - weight) + edge[i] * weight)
                    for i in range(4))
                inner = px[x, h - 1 - off]
                edge = px[x, h - 1]
                px[x, h - 1 - off] = tuple(
                    int(inner[i] * (1 - weight) + edge[i] * weight)
                    for i in range(4))
        out[name] = img
    return out


def mean_rgb(img: Image.Image) -> tuple[float, float, float]:
    px = img.convert("RGB").load()
    w, h = img.size
    sr = sg = sb = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            sr += r
            sg += g
            sb += b
    n = w * h
    return (sr / n, sg / n, sb / n)


def rgb_distance(a: tuple, b: tuple) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def shift_toward(img: Image.Image, target_mean: tuple, blend: float) -> Image.Image:
    """Shift `img`'s pixels toward `target_mean` by alpha blend `blend`
    (0 = no change, 1 = full target tint applied as a flat overlay).
    Used to clamp an `*_b` variant's average color closer to its `*_a`
    sibling so neighbors read as the same floor."""
    src_mean = mean_rgb(img)
    delta = (target_mean[0] - src_mean[0],
             target_mean[1] - src_mean[1],
             target_mean[2] - src_mean[2])
    out = img.convert("RGBA").copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            r = max(0, min(255, int(r + delta[0] * blend)))
            g = max(0, min(255, int(g + delta[1] * blend)))
            b = max(0, min(255, int(b + delta[2] * blend)))
            px[x, y] = (r, g, b, a)
    return out


# ---------------------------------------------------------------------------
# Tiles (§3.1)
# ---------------------------------------------------------------------------

def _clamp(v: int) -> int:
    return max(0, min(255, v))


def _scale_rgb(rgb: tuple[int, int, int], mul: float) -> tuple[int, int, int]:
    return (_clamp(int(rgb[0] * mul)),
            _clamp(int(rgb[1] * mul)),
            _clamp(int(rgb[2] * mul)))


def _draw_stone_tile(base_rgb: tuple[int, int, int],
                      subdivisions: int,
                      speckle_seed: int) -> Image.Image:
    """Procedural stone tile — flat fill, darker grooves at every
    sub-stone boundary (outer + interior crosses), subtle speckle.

    Groove geometry: 1 pixel of groove-dark at every outer edge of the
    canvas; for subdivisions > 1, an interior cross with 1 dark pixel
    on each side of every sub-stone boundary (forming a 2px joint
    visible inside the tile). When two tiles butt together, their
    1-pixel outer edges combine into a 2px joint matching the interior
    joints — so every joint on the board is uniformly 2px wide and
    every joint sits exactly at a sub-stone boundary."""
    import random
    img = Image.new("RGBA", (TILE_PX, TILE_PX), base_rgb + (255,))
    px = img.load()

    # Very subtle deterministic speckle so the stone face isn't a flat
    # painted color, but quiet enough to read as one tone (±4 brightness,
    # ~10% of pixels touched). Anything more aggressive read as added
    # noise that didn't blend with the base color.
    rng = random.Random(speckle_seed)
    for _ in range((TILE_PX * TILE_PX) // 10):
        x = rng.randrange(TILE_PX)
        y = rng.randrange(TILE_PX)
        d = rng.randint(-4, 4)
        r, g, b, _a = px[x, y]
        px[x, y] = (_clamp(r + d), _clamp(g + d), _clamp(b + d), 255)

    # Groove tones. Two intensities: dark for the actual joint pixel,
    # mid for a subtle 1-pixel inner highlight. The dark groove is a
    # 30% darkening of the base — strong enough to read as a clear
    # joint, gentle enough to feel like the same stone in shadow
    # rather than a black painted line.
    g_dark = _scale_rgb(base_rgb, 0.70) + (255,)
    g_mid = _scale_rgb(base_rgb, 0.88) + (255,)

    sub = TILE_PX // subdivisions

    # Vertical grooves: at x = 0 (outer left), every interior boundary,
    # and x = TILE_PX-1 (outer right). Clean 2px joints with no chip
    # imperfections — chip noise read as pasted-on dots; the groove
    # itself stays clean and the stone-face speckle (drawn earlier)
    # carries the natural variation.
    boundary_xs = [i * sub for i in range(subdivisions + 1)]
    for bx in boundary_xs:
        if bx == 0:
            for y in range(TILE_PX):
                px[0, y] = g_dark
        elif bx == TILE_PX:
            for y in range(TILE_PX):
                px[TILE_PX - 1, y] = g_dark
        else:
            for y in range(TILE_PX):
                px[bx - 1, y] = g_dark
                px[bx, y] = g_dark

    # Horizontal grooves: same pattern.
    boundary_ys = [i * sub for i in range(subdivisions + 1)]
    for by in boundary_ys:
        if by == 0:
            for x in range(TILE_PX):
                px[x, 0] = g_dark
        elif by == TILE_PX:
            for x in range(TILE_PX):
                px[x, TILE_PX - 1] = g_dark
        else:
            for x in range(TILE_PX):
                px[x, by - 1] = g_dark
                px[x, by] = g_dark

    # Subtle inner highlight one pixel inside each outer edge — gives
    # the slab a hint of bevel without crowding the joint.
    for x in range(1, TILE_PX - 1):
        if px[x, 1][:3] != g_dark[:3]:
            px[x, 1] = g_mid
        if px[x, TILE_PX - 2][:3] != g_dark[:3]:
            px[x, TILE_PX - 2] = g_mid
    for y in range(1, TILE_PX - 1):
        if px[1, y][:3] != g_dark[:3]:
            px[1, y] = g_mid
        if px[TILE_PX - 2, y][:3] != g_dark[:3]:
            px[TILE_PX - 2, y] = g_mid

    return img


def process_tiles(client, force: bool) -> dict[str, Image.Image]:
    """Procedurally render the 4 tile variants. No PixelLab calls."""
    raw: dict[str, Image.Image] = {}
    for name, (base_rgb, subdiv) in TILE_VARIANTS.items():
        raw[name] = _draw_stone_tile(base_rgb, subdiv,
                                       TILE_SPECKLE_SEEDS[name])

    TILES_DIR.mkdir(parents=True, exist_ok=True)
    for name, img in raw.items():
        out = TILES_DIR / f"{name}.png"
        img.save(out)
        print(f"   saved -> {out.relative_to(ROOT)}")

    # Visual assertion: full 8×8 checkerboard. Confirms seam alignment
    # under realistic adjacency.
    inspect = Image.new("RGB", (TILE_PX * 8, TILE_PX * 8))
    for r in range(8):
        for c in range(8):
            name = "dark" if (c + r) % 2 == 0 else "light"
            inspect.paste(raw[name].convert("RGB"),
                          (c * TILE_PX, r * TILE_PX))
    inspect_path = INSPECT_DIR / "_inspect_medieval_tiles.png"
    inspect.save(inspect_path)
    print(f"   inspect -> {inspect_path.relative_to(ROOT)}")
    return raw


# ---------------------------------------------------------------------------
# Overlay (board-sized transparent detail layer)
# ---------------------------------------------------------------------------

def process_overlay(client, force: bool) -> Image.Image:
    """Generate ONE board-sized transparent PNG carrying all the macro
    detail (moss, cracks, dust, scuffs). Composited on top of the tiled
    grid as a single TextureRect — so the visible noise across the
    board is non-tiling and breaks up any residual tile-repeat read.
    PixelLab generates at 512px (within its limit); we ship at 512 and
    let Godot's STRETCH_KEEP_ASPECT scale to the actual board size."""
    img = gen_atom_with_no_bg(client, "overlay", OVERLAY_PROMPT,
                               OVERLAY_SEED, OVERLAY_NATIVE, force)
    img = assert_size(img, OVERLAY_NATIVE, "overlay")

    # Chroma-key: PixelLab's no_background=True often returns a fully
    # opaque image with a flat light-grey background instead of an
    # actual transparent one. Detect the dominant color and threshold
    # any pixel close to it to alpha=0 — leaves only the dust/cracks/
    # scuffs visible.
    img = chroma_key_background(img, threshold=42)

    # 2× nearest upscale so the ship file matches the in-game board
    # size more closely (board is 576px; 512 with KEEP_ASPECT_COVERED
    # gives clean nearest-neighbor scaling).
    img = img.resize((OVERLAY_PX, OVERLAY_PX), Image.NEAREST)

    # Soften any stray opaque background by pruning pixels that read as
    # the dominant background color. PixelLab usually returns a clean
    # transparent BG with no_background=True; this is belt-and-braces.
    img = img.convert("RGBA")

    UI_DIR.mkdir(parents=True, exist_ok=True)
    out_path = UI_DIR / "floor_overlay_medieval.png"
    img.save(out_path)
    print(f"   saved -> {out_path.relative_to(ROOT)}")

    # Visual assertion: composite the overlay on top of a checkerboard
    # built from the 4 tile variants using the same variant picker the
    # game uses. Confirms the detail reads well against the actual
    # floor it'll sit on.
    variants_loaded = {
        name: (TILES_DIR / f"{name}.png")
        for name in TILE_VARIANTS.keys()
    }
    if all(p.exists() for p in variants_loaded.values()):
        loaded = {name: Image.open(p).convert("RGBA")
                  for name, p in variants_loaded.items()}
        bg = Image.new("RGBA", (TILE_PX * 8, TILE_PX * 8), (0, 0, 0, 255))
        for r in range(8):
            for c in range(8):
                name = "dark" if (c + r) % 2 == 0 else "light"
                bg.paste(loaded[name], (c * TILE_PX, r * TILE_PX))
        scaled = img.resize((TILE_PX * 8, TILE_PX * 8), Image.NEAREST)
        composite = Image.alpha_composite(bg, scaled)
        inspect_path = INSPECT_DIR / "_inspect_medieval_overlay.png"
        composite.convert("RGB").save(inspect_path)
        print(f"   inspect -> {inspect_path.relative_to(ROOT)}")
    return img


def chroma_key_background(img: Image.Image, threshold: int,
                            detail_alpha: int = 190) -> Image.Image:
    """Make pixels close to the dominant color transparent and apply a
    partial alpha to the remaining detail pixels.

    Why partial alpha: the overlay layer carries dust / cracks / scuffs
    that are meant to sit ON the floor, not REPLACE it. Fully-opaque
    detail pixels would override the tile's seam grooves wherever a
    dot lands on a joint, making the floor look like the detail was
    pasted on. At ~75% alpha the floor's joints, speckle, and tone
    show through every dot, so the detail reads as natural wear that
    settled on the floor instead of stickers stuck to it.

    Threshold is RGB distance (0..441) — pixels within this distance
    of the dominant background color get alpha=0; everything else
    keeps RGB and gets alpha=detail_alpha."""
    rgba = img.convert("RGBA").copy()
    px = rgba.load()
    w, h = rgba.size

    # Use the four corners as a background-color hint — PixelLab's flat
    # background usually occupies all four corners.
    samples = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg_r = sum(s[0] for s in samples) // 4
    bg_g = sum(s[1] for s in samples) // 4
    bg_b = sum(s[2] for s in samples) // 4

    cleared = 0
    kept = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            d = ((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2) ** 0.5
            if d <= threshold:
                px[x, y] = (r, g, b, 0)
                cleared += 1
            else:
                px[x, y] = (r, g, b, detail_alpha)
                kept += 1
    pct = cleared / (w * h) * 100
    print(f"   [chroma] bg=({bg_r},{bg_g},{bg_b}) cleared {cleared}/"
          f"{w * h} ({pct:.1f}%) thresh={threshold}; detail kept at "
          f"alpha={detail_alpha} ({kept} px)")
    return rgba


def gen_atom_with_no_bg(client, name: str, prompt: str, seed: int,
                         size: int, force: bool) -> Image.Image:
    """Variant of gen_atom() that asks PixelLab to drop the background
    so the output is RGBA with transparency. Used for the overlay."""
    cp = cache_path(name, seed)
    if cp.exists() and not force:
        print(f"   [cache] {cp.name}")
        return Image.open(cp).convert("RGBA")
    print(f"   [pixellab] {name} seed={seed} size={size} (no_background)")
    resp = client.generate_image_pixflux(
        description=prompt,
        image_size={"width": size, "height": size},
        no_background=True,
        text_guidance_scale=11.0,
        seed=seed,
    )
    out = resp.image.pil_image().convert("RGBA")
    out.save(cp)
    return out


# ---------------------------------------------------------------------------
# Frame atlas (§3.2)
# ---------------------------------------------------------------------------

def edge_blend(left: Image.Image, right: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Soften a 1px seam between two cells that will sit next to each
    other in the NinePatch. Average the rightmost column of `left` with
    the leftmost column of `right`."""
    out_l = left.copy()
    out_r = right.copy()
    pl = out_l.load()
    pr = out_r.load()
    h = left.size[1]
    for y in range(h):
        a = pl[left.size[0] - 1, y]
        b = pr[0, y]
        avg = tuple((x + y_) // 2 for x, y_ in zip(a, b))
        pl[left.size[0] - 1, y] = avg
        pr[0, y] = avg
    return out_l, out_r


def process_frame(client, force: bool) -> Image.Image:
    img = gen_atom(client, "frame", FRAME_PROMPT, FRAME_SEED, FRAME_PX, force)
    img = assert_size(img, FRAME_PX, "frame")

    # Slice into 9 cells.
    cells: list[list[Image.Image]] = []
    for r in range(3):
        row = []
        for c in range(3):
            x = c * FRAME_CELL
            y = r * FRAME_CELL
            cell = img.crop((x, y, x + FRAME_CELL, y + FRAME_CELL))
            assert cell.size == (FRAME_CELL, FRAME_CELL), \
                f"cell ({r},{c}) is {cell.size}, expected 16x16"
            row.append(cell.convert("RGBA"))
        cells.append(row)

    # Center cell zeroed — NinePatch ignores the middle, but PixelLab
    # might draw something there that would bleed if we ever sampled it.
    cells[1][1] = Image.new("RGBA", (FRAME_CELL, FRAME_CELL), (0, 0, 0, 0))

    # Edge continuity around the ring: each adjacent cell pair gets a
    # 1px seam blend. Top row: TL↔T↔TR; Bot row: BL↔B↔BR.
    cells[0][0], cells[0][1] = edge_blend(cells[0][0], cells[0][1])
    cells[0][1], cells[0][2] = edge_blend(cells[0][1], cells[0][2])
    cells[2][0], cells[2][1] = edge_blend(cells[2][0], cells[2][1])
    cells[2][1], cells[2][2] = edge_blend(cells[2][1], cells[2][2])
    # Vertical seams on the side edges (rotate to reuse edge_blend).
    def vblend(top: Image.Image, bot: Image.Image) -> tuple:
        t = top.transpose(Image.ROTATE_270)
        b = bot.transpose(Image.ROTATE_270)
        t, b = edge_blend(t, b)
        return t.transpose(Image.ROTATE_90), b.transpose(Image.ROTATE_90)
    cells[0][0], cells[1][0] = vblend(cells[0][0], cells[1][0])
    cells[1][0], cells[2][0] = vblend(cells[1][0], cells[2][0])
    cells[0][2], cells[1][2] = vblend(cells[0][2], cells[1][2])
    cells[1][2], cells[2][2] = vblend(cells[1][2], cells[2][2])

    # Reassemble.
    out = Image.new("RGBA", (FRAME_PX, FRAME_PX), (0, 0, 0, 0))
    for r in range(3):
        for c in range(3):
            out.paste(cells[r][c], (c * FRAME_CELL, r * FRAME_CELL))

    UI_DIR.mkdir(parents=True, exist_ok=True)
    out_path = UI_DIR / "frame_medieval.png"
    out.save(out_path)
    print(f"   saved -> {out_path.relative_to(ROOT)}")

    # Visual assertion: render the NinePatch stretched to the in-game
    # board size (SQ_SIZE * 8 + 12 = 588). Stretch matches Godot's
    # default NinePatchRect axis_stretch_mode = STRETCH.
    target = 588
    inspect = _render_ninepatch(out, target, target)
    inspect_path = INSPECT_DIR / "_inspect_medieval_frame.png"
    inspect.save(inspect_path)
    print(f"   inspect -> {inspect_path.relative_to(ROOT)}")
    return out


def _render_ninepatch(atlas: Image.Image, w: int, h: int) -> Image.Image:
    """Replicate Godot's NinePatchRect on a 48x48 atlas with patch
    margin 16 on all sides, stretch axis mode. Used only for the
    visual-assertion image."""
    m = FRAME_CELL
    canvas = Image.new("RGBA", (w, h), (40, 30, 25, 255))

    # Slice the 9 patches.
    def piece(r, c):
        return atlas.crop((c * m, r * m, c * m + m, r * m + m))

    tl, t, tr = piece(0, 0), piece(0, 1), piece(0, 2)
    l_, _c, r_ = piece(1, 0), piece(1, 1), piece(1, 2)
    bl, b_, br = piece(2, 0), piece(2, 1), piece(2, 2)

    # Stretch edges to fill between corners.
    edge_w = w - 2 * m
    edge_h = h - 2 * m
    t_s = t.resize((edge_w, m), Image.NEAREST)
    b_s = b_.resize((edge_w, m), Image.NEAREST)
    l_s = l_.resize((m, edge_h), Image.NEAREST)
    r_s = r_.resize((m, edge_h), Image.NEAREST)

    canvas.paste(tl, (0, 0), tl)
    canvas.paste(tr, (w - m, 0), tr)
    canvas.paste(bl, (0, h - m), bl)
    canvas.paste(br, (w - m, h - m), br)
    canvas.paste(t_s, (m, 0), t_s)
    canvas.paste(b_s, (m, h - m), b_s)
    canvas.paste(l_s, (0, m), l_s)
    canvas.paste(r_s, (w - m, m), r_s)
    return canvas


# ---------------------------------------------------------------------------
# Backdrop (§3.3)
# ---------------------------------------------------------------------------

def process_backdrop(client, force: bool) -> Image.Image:
    img = gen_atom(client, "backdrop", BACKDROP_PROMPT, BACKDROP_SEED,
                   BACKDROP_PX, force)
    img = assert_size(img, BACKDROP_PX, "backdrop")
    img = force_opaque(img, "backdrop")
    img = seam_blend(img)

    # Brightness clamp: keep mean luminance in the mid-dark window so
    # the backdrop sits behind the UI without competing.
    rgb = img.convert("RGB")
    mr, mg, mb = mean_rgb(rgb)
    luma = (0.2126 * mr + 0.7152 * mg + 0.0722 * mb) / 255.0
    if luma < BACKDROP_LUMA_LOW or luma > BACKDROP_LUMA_HIGH:
        target = (BACKDROP_LUMA_LOW + BACKDROP_LUMA_HIGH) / 2
        scale = target / max(luma, 0.01)
        print(f"   [clamp] backdrop luma {luma:.2f} outside "
              f"[{BACKDROP_LUMA_LOW}, {BACKDROP_LUMA_HIGH}], scaling by "
              f"{scale:.2f}")
        px = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                px[x, y] = (max(0, min(255, int(r * scale))),
                            max(0, min(255, int(g * scale))),
                            max(0, min(255, int(b * scale))),
                            a)
    else:
        print(f"   [clamp] backdrop luma {luma:.2f} ok")

    UI_DIR.mkdir(parents=True, exist_ok=True)
    out_path = UI_DIR / "backdrop_medieval.png"
    img.save(out_path)
    print(f"   saved -> {out_path.relative_to(ROOT)}")

    # Visual assertion: 4×4 tiling at scale.
    inspect = Image.new("RGB", (BACKDROP_PX * 4, BACKDROP_PX * 4))
    for r in range(4):
        for c in range(4):
            inspect.paste(img.convert("RGB"),
                          (c * BACKDROP_PX, r * BACKDROP_PX))
    inspect_path = INSPECT_DIR / "_inspect_medieval_backdrop.png"
    inspect.save(inspect_path)
    print(f"   inspect -> {inspect_path.relative_to(ROOT)}")
    return img


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

GROUPS = ("tiles", "overlay", "frame", "backdrop")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None,
                    choices=GROUPS, help="regenerate one group")
    ap.add_argument("--force", action="store_true",
                    help="bypass the PixelLab cache")
    args = ap.parse_args()

    client = load_client()
    print(f"[pixellab] balance: {client.get_balance()}")
    only = set(args.only) if args.only else set(GROUPS)

    if "tiles" in only:
        print("\n=== tiles ===")
        process_tiles(client, args.force)
    if "overlay" in only:
        print("\n=== overlay ===")
        process_overlay(client, args.force)
    if "frame" in only:
        print("\n=== frame ===")
        process_frame(client, args.force)
    if "backdrop" in only:
        print("\n=== backdrop ===")
        process_backdrop(client, args.force)


if __name__ == "__main__":
    main()
