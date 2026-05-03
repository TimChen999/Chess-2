"""Wizards' Guild theme — layered-accessory approach.

The original chess piece silhouette is **never modified** (except king,
whose cross is pre-cleared). For each piece:

  1. Apply a subtle body-texture pass — adds a 1-pixel HIGHLIGHT band
     on the upper-left silhouette boundary and widens the right-edge
     SHADOW band by 1 px. Suite palette only. Procedural.

  2. For each accessory in the piece's config, generate a 64×64
     transparent-background PNG via PixelLab pixflux at strength 0
     (no init image). Find the opaque bbox, resize-by-nearest to the
     target dimensions, snap near-black pixels to suite OUTLINE.

  3. Translate the accessory so its bbox center hits the per-piece
     anchor, alpha-composite onto the textured piece. Repeat per
     accessory in z-order.

  4. The same accessory PNGs composite onto both white-team and
     black-team baselines, since the accessory has its own outline
     and colors that read on either body.

Run: python tools/sprites/wizard_statics.py
     python tools/sprites/wizard_statics.py --only bishop king
     python tools/sprites/wizard_statics.py --force        # ignore cache
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pixellab
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
CACHE_DIR = ROOT / "tools/sprites/_pixellab_cache"

# ---------------------------------------------------------------------------
# Suite palette
# ---------------------------------------------------------------------------
OUTLINE   = (40, 40, 50, 255)
FILL      = (250, 248, 242, 255)
SHADOW    = (210, 208, 200, 255)
HIGHLIGHT = (130, 128, 138, 255)

ALPHA_THRESH = 8

# Black-team body palette. The values match what the baseline black
# sprites actually use (committed at 4ceaa7d): FILL = (64,64,70),
# OUTLINE = (40,40,40). BLACK_HILIGHT is the lighter shading the user
# asked for on dark pieces; BLACK_SHADOW exists for parity but the
# baseline black doesn't currently have a separate shadow band.
BLACK_OUTLINE = (40, 40, 40, 255)
BLACK_FILL    = (64, 64, 70, 255)
BLACK_SHADOW  = (50, 50, 56, 255)
BLACK_HILIGHT = (102, 102, 112, 255)


# ---------------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------------

def alpha_mask(img):
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def silhouette_bbox(img):
    px = img.load()
    w, h = img.size
    xs = [x for y in range(h) for x in range(w) if px[x, y][3] > ALPHA_THRESH]
    ys = [y for y in range(h) for x in range(w) if px[x, y][3] > ALPHA_THRESH]
    if not xs:
        return 0, 0, 0, 0
    return min(xs), min(ys), max(xs), max(ys)


def opaque_bbox(img):
    """Same as silhouette_bbox but returns None for fully-transparent images."""
    bb = silhouette_bbox(img)
    if bb == (0, 0, 0, 0):
        return None
    return bb


def is_boundary(mask, x, y):
    w = len(mask); h = len(mask[0])
    if not mask[x][y]:
        return False
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < w and 0 <= ny < h) or not mask[nx][ny]:
            return True
    return False


def row_xs(mask, y):
    return [x for x in range(len(mask)) if mask[x][y]]


# ---------------------------------------------------------------------------
# BODY TEXTURE PASS — subtle shading bump (procedural, no API)
# ---------------------------------------------------------------------------

def body_texture_pass(img: Image.Image, color: str = "white") -> Image.Image:
    """Add subtle interior shading without changing the silhouette.

    For white pieces (cream body): paint a 1-pixel HIGHLIGHT band along
    the upper-left silhouette edge (looks like a cool inner shadow) and
    widen the right-edge SHADOW band by 1 px (more depth toward the
    bottom-right).

    For black pieces (dark body): paint a 1-pixel BLACK_HILIGHT band on
    the upper-left silhouette edge (a LIGHTER inner band — opposite of
    white, since the dark body needs lighter pixels to show depth) and
    widen the right-edge BLACK_SHADOW band similarly. Other parts
    outside the new shading bands stay byte-identical to the input.
    """
    if color == "white":
        edge_band = HIGHLIGHT       # mid-grey, darker than FILL
        existing_fill = FILL
        existing_shadow = SHADOW
        widen_color = SHADOW        # extend the existing shadow band
    else:
        edge_band = BLACK_HILIGHT   # lighter than BLACK_FILL
        existing_fill = BLACK_FILL
        existing_shadow = BLACK_SHADOW
        widen_color = BLACK_HILIGHT  # widen with LIGHTER color (per user)

    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    sm = alpha_mask(img)

    bb = silhouette_bbox(img)
    sx0, sy0, sx1, sy1 = bb
    upper_bot = sy0 + int((sy1 - sy0) * 0.60)
    for y in range(sy0, upper_bot + 1):
        for x in range(sx0, sx1 + 1):
            if not sm[x][y]:
                continue
            if is_boundary(sm, x, y):
                rx = x + 1
                if (0 <= rx < w and sm[rx][y]
                        and op[rx, y][:3] == existing_fill[:3]
                        and not is_boundary(sm, rx, y)):
                    op[rx, y] = edge_band
                break

    # Right-edge band: for each row, find the rightmost SHADOW pixel
    # and add a `widen_color` pixel just to its left.
    for y in range(h):
        rightmost_shadow = -1
        for x in range(w - 1, -1, -1):
            if sm[x][y] and op[x, y][:3] == existing_shadow[:3]:
                rightmost_shadow = x
                break
        if rightmost_shadow < 0:
            continue
        leftmost_shadow = rightmost_shadow
        for xx in range(rightmost_shadow, -1, -1):
            if sm[xx][y] and op[xx, y][:3] == existing_shadow[:3]:
                leftmost_shadow = xx
            else:
                break
        target = leftmost_shadow - 1
        if (0 <= target < w and sm[target][y]
                and op[target, y][:3] == existing_fill[:3]
                and not is_boundary(sm, target, y)):
            op[target, y] = widen_color
    return out


# ---------------------------------------------------------------------------
# PRE-CLEAR — erase pre-existing detail before compositing accessories
# ---------------------------------------------------------------------------

def pre_clear_king_cross(img: Image.Image) -> Image.Image:
    """Erase rows above the king's first wide row (the cross+bauble
    structure on top), so the orb accessory has a clean head to sit on."""
    out = img.copy()
    op = out.load()
    sm = alpha_mask(img)
    bb = silhouette_bbox(img)
    sx0, sy0, sx1, sy1 = bb
    widths = [len(row_xs(sm, y)) for y in range(sy0, min(sy0 + 16, len(sm[0])))]
    cut_y = sy0
    found_thin = False
    for i, wrow in enumerate(widths):
        y = sy0 + i
        if wrow <= 4:
            found_thin = True
            cut_y = y
        elif found_thin and wrow >= 6:
            cut_y = y
            break
    for y in range(0, cut_y):
        for x in range(img.size[0]):
            op[x, y] = (0, 0, 0, 0)
    return out


def pre_clear_bishop_cross(img: Image.Image) -> Image.Image:
    """Clear the cross emblem painted on the bishop's mitre face. The
    cross is OUTLINE + HIGHLIGHT pixels in rows ~6-22 on the upper
    mitre interior. Set them back to FILL (or to whatever the row's
    SHADOW band is) so the mitre face is clean for a new emblem."""
    out = img.copy()
    op = out.load()
    sm = alpha_mask(img)
    bb = silhouette_bbox(img)
    sx0, sy0, sx1, sy1 = bb
    # Detect light/dark team by sampling a non-boundary FILL pixel.
    # Default to white-team FILL.
    sample_fill = FILL
    for y in range(sy0, sy1 + 1):
        for x in range(sx0, sx1 + 1):
            if sm[x][y] and not is_boundary(sm, x, y):
                c = op[x, y]
                if c[3] >= ALPHA_THRESH:
                    sample_fill = c
                    break
        else:
            continue
        break

    # Mitre face = upper ~55% of the body. Clear ANY non-FILL/SHADOW
    # interior pixel back to FILL. This catches anti-aliased
    # OUTLINE/HIGHLIGHT variants from earlier pipelines (e.g. (52,48,61)
    # near-OUTLINE and (199,199,189) near-SHADOW that are not exact
    # palette matches but are clearly cross detail).
    y_top = sy0 + 2
    y_bot = sy0 + int((sy1 - sy0) * 0.55)
    for y in range(y_top, y_bot + 1):
        for x in range(sx0, sx1 + 1):
            if not sm[x][y]:
                continue
            if is_boundary(sm, x, y):
                continue
            c = op[x, y]
            # Keep only the cream body palette. Anything else (cross
            # detail) gets snapped to FILL.
            if c == FILL or c == SHADOW:
                continue
            op[x, y] = sample_fill
    return out


# ---------------------------------------------------------------------------
# ACCESSORY OUTLINE SNAP — near-black pixels → exact suite OUTLINE
# ---------------------------------------------------------------------------

def snap_outline(img: Image.Image) -> Image.Image:
    """Snap near-black pixels to exact suite OUTLINE so accessory
    outlines match the piece outlines. We use brightness rather than
    max-channel so dark-tinted pixels (e.g. dark navy blue ~45,67,99
    that PixelLab paints around a blue saddle) also snap. Threshold:
    average brightness < 100."""
    out = img.convert("RGBA").copy()
    op = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = op[x, y]
            if a < ALPHA_THRESH:
                continue
            if (r + g + b) / 3.0 < 95:
                op[x, y] = OUTLINE
    return out


# ---------------------------------------------------------------------------
# COMPOSITE — resize accessory to target dimensions and place at anchor
# ---------------------------------------------------------------------------

def mirror_symmetric(img: Image.Image) -> Image.Image:
    """For each (x, y) in the image: if exactly one of the two mirror
    columns (around the image's vertical center) is opaque, copy the
    opaque pixel to the transparent side. Fills small asymmetric holes
    in vertically-symmetric items like the cross — typically adds 1–4
    pixels."""
    w, h = img.size
    out = img.copy()
    op = out.load()
    src = img.load()
    for y in range(h):
        for x in range(w // 2):
            mx = w - 1 - x
            l = src[x, y]
            r = src[mx, y]
            l_op = l[3] >= ALPHA_THRESH
            r_op = r[3] >= ALPHA_THRESH
            if l_op and not r_op:
                op[mx, y] = l
            elif r_op and not l_op:
                op[x, y] = r
    return out


def composite_accessory(piece_img: Image.Image, accessory_img: Image.Image,
                        anchor_xy: tuple[int, int],
                        target_w: int, target_h: int,
                        symmetric: bool = False) -> Image.Image:
    """Crop accessory to its opaque bbox, resize-nearest to target
    dimensions, optionally mirror-fill missing symmetry pixels, paste
    at anchor (so the resized accessory's center sits at anchor_xy),
    alpha-composite onto piece_img. Returns a NEW image."""
    bb = opaque_bbox(accessory_img)
    if bb is None:
        return piece_img.copy()
    ax0, ay0, ax1, ay1 = bb
    cropped = accessory_img.crop((ax0, ay0, ax1 + 1, ay1 + 1))
    if (cropped.size[0], cropped.size[1]) != (target_w, target_h):
        cropped = cropped.resize((target_w, target_h), Image.NEAREST)
    if symmetric:
        cropped = mirror_symmetric(cropped)
    pw, ph = piece_img.size
    cw, ch = cropped.size
    paste_x = anchor_xy[0] - cw // 2
    paste_y = anchor_xy[1] - ch // 2
    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    layer.paste(cropped, (paste_x, paste_y), cropped)
    return Image.alpha_composite(piece_img.convert("RGBA"), layer)


def restamp_body_outline(composed: Image.Image, baseline: Image.Image) -> Image.Image:
    """Walk the BASELINE silhouette boundary and force every boundary
    pixel to be exactly OUTLINE color in the composed result. This
    restores the body's 1-pixel dark outline if any accessory composite
    painted over it.

    Pixels OUTSIDE the baseline silhouette are left alone (so accessory
    extensions like staffs/scepters keep their own outlines)."""
    out = composed.convert("RGBA").copy()
    op = out.load()
    sm = alpha_mask(baseline)
    w, h = baseline.size
    for y in range(h):
        for x in range(w):
            if not sm[x][y]:
                continue
            if is_boundary(sm, x, y):
                op[x, y] = OUTLINE
    return out


# ---------------------------------------------------------------------------
# PER-PIECE ACCESSORY CONFIG
# ---------------------------------------------------------------------------

@dataclass
class Accessory:
    id: str
    prompt: str
    target_w: int
    target_h: int
    anchor: tuple[int, int]   # (cx, cy) in 64×64 piece canvas
    z: int = 0                # paint order; lower first (under)
                              # z < 0 → composited BEHIND the body
                              # (the cape, for example)
    negative: str = ""
    manual_template: list[str] | None = None
    """If set, skip PixelLab and use this hand-designed pixel template.
    Each row is a string; chars: ' ' = transparent, '#' = OUTLINE,
    'G' = gold, 'R' = red jewel, 'F' = FILL (cream), 'S' = SHADOW,
    'P' = purple, 'B' = blue, 'T' = teal."""
    symmetric: bool = False
    """If True, mirror-fill missing pixels around the vertical axis
    after resize so the accessory is bilaterally symmetric. Useful for
    items like the cross where PixelLab nearest-neighbor downsample
    can drop a few pixels on one side."""

STYLE_SUFFIX = (
    ", isolated single object, transparent background, dark black "
    "outline, smooth shading, pixel art at 64x64 resolution, no other "
    "objects, no text"
)


# Bbox sizes are SUBSTANTIAL — drapes ~25 px wide, staffs ~50 px tall.
PIECES_ACCESSORIES = {
    "pawn": [
        # Open jacket: two narrow vertical fabric panels on the left
        # and right sides of the body, leaving the middle cream visible
        # (like an open-front vest). Generated as one wider piece and
        # split, then composited on each side.
        Accessory(
            id="left_panel",
            prompt=("a narrow vertical strip of green fabric, dark "
                    "outline, isolated single fabric strip, no person, "
                    "no body, no hood, just the green cloth panel"),
            target_w=5, target_h=16,
            anchor=(26, 36), z=0,
            negative=("person, body, humanoid, hood, head, hand, "
                     "weapon, sword, character, figure, face, "
                     "horizontal, flag, banner, large fabric"),
        ),
        Accessory(
            id="right_panel",
            prompt=("a narrow vertical strip of green fabric, dark "
                    "outline, isolated single fabric strip, no person, "
                    "no body, no hood, just the green cloth panel"),
            target_w=5, target_h=16,
            anchor=(38, 36), z=0,
            negative=("person, body, humanoid, hood, head, hand, "
                     "weapon, sword, character, figure, face, "
                     "horizontal, flag, banner, large fabric"),
        ),
        Accessory(
            id="spellbook",
            prompt=("a small open spellbook with dark blue covers and "
                    "gold-trimmed pages, held flat horizontally, dark "
                    "outline"),
            target_w=12, target_h=8,
            anchor=(32, 40), z=1,
            negative="chess piece, hand, person, multiple books",
        ),
    ],
    "knight": [
        Accessory(
            id="saddle",
            prompt=("a deep blue saddle blanket with a small silver "
                    "runic glyph in its center, draped flat horizontally, "
                    "dark outline"),
            target_w=24, target_h=12,
            anchor=(28, 38), z=0,
            negative="horse, person, rider, full armor, blanket on face",
        ),
    ],
    "bishop": [
        Accessory(
            id="mitre_cross",
            prompt=("a small ornate stylized gold cross with flared "
                    "diamond-shaped tips at each of the four ends and "
                    "a small jewel at the intersection, dark outline, "
                    "isolated single decorative cross, transparent "
                    "background"),
            target_w=10, target_h=12,
            anchor=(32, 14), z=0,
            symmetric=True,
            negative=("plain cross, simple plus sign, latin cross, "
                     "star, multiple crosses"),
        ),
        Accessory(
            id="staff",
            prompt=("a tall vertical wizard staff with a small round "
                    "gold orb on top, brown wooden shaft, dark outline, "
                    "isolated single staff"),
            target_w=6, target_h=50,
            anchor=(46, 32), z=1,
            negative="chess piece, person, hand, multiple staffs, weapon",
        ),
        Accessory(
            id="stole",
            prompt=("a long thin deep-purple stole sash hanging "
                    "vertically, dark outline, isolated fabric strip"),
            target_w=7, target_h=26,
            anchor=(32, 38), z=2,
            negative="full robe, chess piece, person",
        ),
    ],
    "rook": [
        Accessory(
            id="banner",
            prompt=("a long crimson red banner ribbon hanging vertically "
                    "with a torn bottom edge, dark outline, isolated "
                    "fabric strip"),
            target_w=8, target_h=28,
            anchor=(40, 26), z=0,
            negative="pole, person, multiple banners, sigil",
        ),
    ],
    "queen": [
        Accessory(
            id="scepter",
            prompt=("a tall slender royal scepter with a small teal "
                    "gem on top, gold shaft, dark outline, isolated "
                    "single scepter"),
            target_w=6, target_h=40,
            anchor=(46, 34), z=0,
            negative="hand, person, crown, weapon, multiple scepters",
        ),
        Accessory(
            id="sash",
            prompt=("a thin gold royal sash band, horizontal fabric "
                    "strip, dark outline, isolated"),
            target_w=18, target_h=6,
            anchor=(32, 42), z=1,
            negative="full robe, person, chess piece",
        ),
    ],
    "king": [
        Accessory(
            id="orb",
            prompt=("a single round dark gold orb-of-power with a small "
                    "highlight on the upper left, dark outline, isolated "
                    "single orb"),
            target_w=12, target_h=12,
            anchor=(32, 8), z=0,
            negative="cross, plus sign, religious symbol, multiple orbs",
        ),
        Accessory(
            id="beard",
            prompt=("a long silver-grey beard hanging downward in a "
                    "wedge shape, fluffy texture, dark outline, "
                    "isolated"),
            target_w=10, target_h=15,
            anchor=(32, 22), z=1,
            negative="face, person, body, mustache only, white beard",
        ),
        Accessory(
            id="scepter",
            prompt=("a tall slender ornate scepter with a small purple "
                    "gem on top, gold shaft, dark outline, isolated"),
            target_w=6, target_h=40,
            anchor=(46, 36), z=2,
            negative="hand, person, crown, weapon, cross",
        ),
    ],
    "bandit_pawn": [
        Accessory(
            id="cape",
            prompt=("a wide dark grey cape spread out behind, fabric "
                    "flowing to both sides past the shoulders, viewed "
                    "from the back, dark outline, isolated cape fabric "
                    "only, no body, no head, no face, no person, just "
                    "the empty cape spread wide"),
            target_w=30, target_h=26,
            anchor=(32, 36), z=-1,   # behind the body
            negative=("person, body, humanoid, full character, face, "
                     "head visible, hood with face, weapon, hand, "
                     "narrow cape, vertical strip"),
        ),
        Accessory(
            id="sword",
            prompt=("a sword held vertically with a silver blade and "
                    "a dark crimson wrapped grip, gold pommel, dark "
                    "outline, isolated single sword"),
            target_w=6, target_h=22,
            anchor=(32, 36), z=1,
            negative="hand, person, multiple weapons, dagger, axe",
        ),
    ],
    "alter_knight": [
        Accessory(
            id="saddle",
            prompt=("a deep blue saddle blanket with a small silver "
                    "runic glyph in its center, draped flat horizontally, "
                    "dark outline"),
            target_w=22, target_h=11,
            anchor=(28, 38), z=0,
            negative="horse, person, rider, full armor, blanket on face",
        ),
    ],
    "assassin_bishop": [
        Accessory(
            id="mitre_cross",
            prompt=("a small ornate stylized gold cross with flared "
                    "diamond-shaped tips at each of the four ends and "
                    "a small jewel at the intersection, dark outline, "
                    "isolated single decorative cross, transparent "
                    "background"),
            target_w=10, target_h=12,
            anchor=(32, 14), z=0,
            symmetric=True,
            negative=("plain cross, simple plus sign, latin cross, "
                     "star, multiple crosses"),
        ),
        Accessory(
            id="sash",
            prompt=("a wide diagonal crimson sash with a small gold "
                    "buckle in the middle, fabric strip from upper-"
                    "right to lower-left, dark outline, isolated"),
            target_w=24, target_h=22,
            anchor=(32, 38), z=1,
            negative="full robe, person, chess piece, multiple sashes",
        ),
    ],
}


# Pieces that need pre-clearing of pre-existing detail before compositing.
PIECE_PRE_CLEAR = {
    "king": "king_cross",
    "bishop": "bishop_cross",
    "assassin_bishop": "bishop_cross",
}


# Pieces that should use a different piece's static.png as baseline
# (instead of their own). Used for bandit_pawn so the cape + sword get
# composited onto the clean base pawn rather than an already-caped pawn.
PIECE_BASELINE_OVERRIDE = {
    "bandit_pawn": "pawn",
}


# ---------------------------------------------------------------------------
# PIXELLAB CALL
# ---------------------------------------------------------------------------

def load_client():
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    if not secret:
        sys.exit("error: PIXELLAB_API_KEY missing from .env")
    return pixellab.Client(secret=secret)


def cache_path(piece: str, acc_id: str, seed: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{piece}_{acc_id}_v6_seed{seed}.png"


CHAR_TO_RGBA = {
    " ": (0, 0, 0, 0),
    "#": OUTLINE,
    "G": (217, 178, 60, 255),    # gold
    "R": (190, 60, 72, 255),     # crimson jewel
    "F": FILL,
    "S": SHADOW,
    "P": (126, 91, 176, 255),    # purple
    "B": (76, 124, 196, 255),    # blue
    "T": (70, 168, 162, 255),    # teal
    "V": (192, 196, 210, 255),   # silver
}


def render_manual_template(template: list[str]) -> Image.Image:
    """Render a hand-designed pixel template (list of strings) to an
    RGBA image at exactly the template dimensions."""
    h = len(template)
    w = max(len(row) for row in template)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    p = img.load()
    for y, row in enumerate(template):
        for x, ch in enumerate(row):
            p[x, y] = CHAR_TO_RGBA.get(ch, (0, 0, 0, 0))
    return img


def generate_accessory(client, piece: str, acc: Accessory, seed: int,
                       force: bool) -> Image.Image:
    if acc.manual_template is not None:
        # Hand-designed template — skip PixelLab entirely.
        print(f"   [manual] {acc.id}")
        return render_manual_template(acc.manual_template)
    cp = cache_path(piece, acc.id, seed)
    if cp.exists() and not force:
        print(f"   [cache] {cp.name}")
        return Image.open(cp).convert("RGBA")
    print(f"   [pixellab] {acc.id} seed={seed}")
    resp = client.generate_image_pixflux(
        description=acc.prompt + STYLE_SUFFIX,
        image_size={"width": 64, "height": 64},
        negative_description=acc.negative,
        no_background=True,
        text_guidance_scale=12.0,
        seed=seed,
    )
    out = resp.image.pil_image()
    out.save(cp)
    return out


def acceptable_accessory(img: Image.Image, target_w: int, target_h: int) -> bool:
    """Sanity-check the generated accessory: the opaque bbox should be
    in the right ballpark (within ±60% of target, accounting for the fact
    that we'll resize)."""
    bb = opaque_bbox(img)
    if bb is None:
        return False
    bw = bb[2] - bb[0] + 1
    bh = bb[3] - bb[1] + 1
    # Reject empty / micro accessories
    if bw < 4 or bh < 4:
        return False
    # Reject if completely fills the canvas with no transparency
    if bw >= 60 and bh >= 60:
        return False
    return True


# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------

def load_original_baselines() -> dict:
    """Snapshot all 9 white + 9 black baselines into memory BEFORE any
    piece gets overwritten. Pieces that override their baseline (like
    bandit_pawn → pawn) need the ORIGINAL pawn, not the already-
    wizardized version."""
    out = {"white": {}, "black": {}}
    for color, src_dir in (("white", WHITE_DIR), ("black", BLACK_DIR)):
        for piece in PIECES_ACCESSORIES.keys():
            path = src_dir / piece / "static.png"
            if path.exists():
                out[color][piece] = Image.open(path).convert("RGBA")
    return out


def process_piece(client, piece: str, force: bool, baselines: dict) -> dict:
    accs = PIECES_ACCESSORIES.get(piece, [])
    if not accs:
        return {"piece": piece, "status": "no_accessories"}

    # Generate each accessory (cached). Re-roll seeds until acceptable_accessory.
    accessory_pngs = []
    for acc in sorted(accs, key=lambda a: a.z):
        SEEDS = [6000, 6017, 6034, 6051]
        chosen = None
        for seed in SEEDS:
            img = generate_accessory(client, piece, acc, seed, force)
            if acceptable_accessory(img, acc.target_w, acc.target_h):
                chosen = img
                break
            print(f"   [reject] {acc.id} seed={seed} (bbox out of range)")
        if chosen is None:
            print(f"   [warn] {acc.id} no acceptable seed; using last")
            chosen = img
        accessory_pngs.append((acc, snap_outline(chosen)))

    # Compose for white + black baselines
    results = {}
    baseline_piece = PIECE_BASELINE_OVERRIDE.get(piece, piece)
    for color, src_dir in (("white", WHITE_DIR), ("black", BLACK_DIR)):
        # Always save under THIS piece's path, but the baseline may
        # come from a different piece (e.g. bandit_pawn uses pawn).
        # Read the baseline from the in-memory snapshot taken at start
        # of main() — guarantees we get the ORIGINAL piece even if
        # processing order has already overwritten its on-disk file.
        save_path = src_dir / piece / "static.png"
        baseline = baselines[color].get(baseline_piece)
        if baseline is None:
            continue
        baseline = baseline.copy()
        clear_kind = PIECE_PRE_CLEAR.get(piece)
        if clear_kind == "king_cross":
            baseline = pre_clear_king_cross(baseline)
        elif clear_kind == "bishop_cross":
            baseline = pre_clear_bishop_cross(baseline)
        textured = body_texture_pass(baseline, color=color)

        # Three-layer compositing: behind (z<0) → body → front (z≥0).
        behind = [(a, i) for (a, i) in accessory_pngs if a.z < 0]
        front = [(a, i) for (a, i) in accessory_pngs if a.z >= 0]

        # Start with empty canvas; lay down each behind-accessory.
        canvas = Image.new("RGBA", textured.size, (0, 0, 0, 0))
        for acc, acc_img in behind:
            canvas = composite_accessory(
                canvas, acc_img,
                anchor_xy=acc.anchor,
                target_w=acc.target_w,
                target_h=acc.target_h,
                symmetric=acc.symmetric,
            )
        # Body goes on top of behind layer.
        composed = Image.alpha_composite(canvas, textured)
        # Front accessories on top.
        for acc, acc_img in front:
            composed = composite_accessory(
                composed, acc_img,
                anchor_xy=acc.anchor,
                target_w=acc.target_w,
                target_h=acc.target_h,
                symmetric=acc.symmetric,
            )
        # Restamp the body's 1-px outline so any accessory composite
        # that painted over the boundary gets the dark suite OUTLINE
        # restored. Accessory silhouette extensions (staff, scepter,
        # cape extending past body) keep their own outlines.
        composed = restamp_body_outline(composed, baseline)
        composed.save(save_path)
        results[color] = save_path

    print(f"[{piece}] saved white + black")
    return {"piece": piece, "status": "ok", "paths": results,
            "accessory_count": len(accessory_pngs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    client = load_client()
    print(f"[pixellab] balance: {client.get_balance()}")

    # Snapshot all original baselines BEFORE processing any piece, so
    # baseline-override pieces (e.g. bandit_pawn → pawn) get the
    # untouched pawn instead of the already-wizardized one.
    baselines = load_original_baselines()

    only = set(args.only) if args.only else None
    results = []
    for piece in PIECES_ACCESSORIES.keys():
        if only and piece not in only:
            continue
        results.append(process_piece(client, piece, args.force, baselines))

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['piece']:18s}  {r['status']}  "
              f"accessories={r.get('accessory_count', 0)}")


if __name__ == "__main__":
    main()
