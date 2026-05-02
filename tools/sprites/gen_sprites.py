"""Generate Chess-2 piece sprites via the PixelLab API.

Pipeline (cost-aware):
  1. Generate ONE anchor piece (white pawn) via pixflux (text-only).
  2. Generate the other 5 white base pieces via bitforge, conditioned
     on the white pawn as style_image — locks all 6 white pieces to
     a coherent style.
  3. Generate 3 white variants (bandit_pawn, alter_knight, assassin_bishop)
     via bitforge with their respective white base piece as both
     style_image AND init_image — preserves the base shape and adds
     the variant feature (cape, horn, sword).
  4. Procedurally recolor each white sprite to black via PIL — single
     local pass, free, deterministic. No API calls for black versions.

Total API calls: 9 (1 pixflux + 8 bitforge).

Outputs land at:
  godot/assets/sprites/anim/pieces/<color>/<piece_id>/static.png

Prerequisites:
  - pip install pixellab
  - .env file at project root with PIXELLAB_API_KEY=...

Usage:
  python tools/gen_sprites.py            # generate all (skips files that exist)
  python tools/gen_sprites.py --force    # regenerate everything
  python tools/gen_sprites.py --only pawn rook    # regenerate specific pieces

Note: This script overwrites only `static.png` per piece. Animation strips
(move, attack, hit, death) are still produced by generate_sprites.py and
will look stylistically different from the AI-generated statics until
they're regenerated separately. Run generate_sprites.py once first to
ensure non-static animation strips and FX exist, THEN run this script.
generate_sprites.py would overwrite our static.png if re-run after.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pixellab
from dotenv import load_dotenv
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent.parent
SPRITES_ROOT = ROOT / "godot" / "assets" / "sprites" / "anim" / "pieces"

# Native generation resolution. PixelLab handles up to 400x400; we go 64x64
# because the in-game sprite container after the 4px tile padding on a 72px
# square is ~64x64, so 64x64 art renders 1:1 with no scaling. Higher than
# the 32x32 of the existing procedural strips, but the renderer's
# STRETCH_KEEP_ASPECT_CENTERED + nearest filter handles the mismatch.
SIZE = 64

# Common style suffix appended to every prompt to keep the suite cohesive.
STYLE = (
    ", clean pixel art chess piece, frontal view (camera facing the piece "
    "head-on), simple flat background that will be removed, single piece "
    "centered, dark outline, smooth shading, recognizable silhouette"
)

BASE_PIECES = ["pawn", "rook", "knight", "bishop", "queen", "king"]

DESCRIPTIONS_WHITE = {
    "pawn":   "white chess pawn, simple round head on a stout body",
    "rook":   ("Staunton chess rook piece. WIDE squat cylindrical body. "
               "The top is a small castle battlement: flat horizontal "
               "top edge with 3 rectangular teeth sticking up "
               "(crenellations like a parapet wall)"),
    "knight": ("Staunton chess knight piece — a horse head in profile "
               "facing right with a flowing mane and a bridle, mounted "
               "on a round base"),
    "bishop": ("Staunton chess bishop piece. Tall slender body with a "
               "round base and a thin neck collar. The TOP is shaped "
               "like a tall POINTED OVAL CAP (a teardrop-shaped mitre "
               "ending in a small round bead at the very top) with a "
               "CURVED DIAGONAL SLIT cut into the front of the cap from "
               "the upper-left toward the lower-right, like a sliver "
               "removed from the side"),
    "queen":  ("Staunton chess queen piece. Tall slender body. The TOP "
               "is a wide CROWN with multiple POINTED PEAKS each tipped "
               "with a SMALL ROUND PEARL (like a tiara: a row of about "
               "5 sharp points each capped with a tiny ball, arched "
               "across the top of the head). The crown is wider than "
               "the body. NO cross on top"),
    "king":   ("Staunton chess king piece. Tall slender body. The very "
               "TOP is a small CHRISTIAN CROSS — a clear plus-sign shape "
               "(one short vertical bar crossed by one short horizontal "
               "bar) sitting on a tiny round orb. The cross is the only "
               "thing on top, no points or spikes around it"),
}

# Negative prompts — explicitly excluded features per piece. Used by pixflux
# to steer away from common confusions.
NEGATIVE_WHITE = {
    "rook":   "spire, point, finial, dome, sphere, ball on top, cross, crown",
    "bishop": "cross, crown of points, spikes, flat top, multiple peaks",
    "queen":  "cross, mitre, slit, single point, dome, smooth ball top",
    "king":   "crown of points, multiple points, pearls, spikes, mitre, slit",
}

# Variants: (variant_id, base_id, prompt, use_init_image).
# use_init_image=True: gen_variant uses the base sprite as init_image so
# the variant inherits the base silhouette, with the prompt adding the
# distinguishing feature. Works for large features (cape).
# use_init_image=False: pure pixflux from text. Use when the feature is
# small enough that the base shape suppresses it (sword on bishop's back).
VARIANTS = [
    ("bandit_pawn",
     "pawn",
     "white chess pawn wearing a flowing dark red cape draped over its "
     "shoulders, the cape clearly visible behind the body",
     True),
    ("alter_knight",
     "knight",
     "white chess knight as a unicorn — a single long pointed horn stands "
     "straight up from the horse's forehead, like a unicorn",
     True),
    ("assassin_bishop",
     "bishop",
     "white pixel art chess bishop holding a long sheathed sword "
     "vertically behind its back, the sword's hilt visible above the "
     "bishop's mitre, the sheath extending downward behind the body",
     False),
]


def load_client() -> pixellab.Client:
    """Load creds from .env at project root, then env vars.
    The SDK reads PIXELLAB_SECRET, but we also accept PIXELLAB_API_KEY
    for parity with how the env file was originally scaffolded."""
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    if not secret:
        sys.exit("error: set PIXELLAB_API_KEY (or PIXELLAB_SECRET) in .env or env vars")
    return pixellab.Client(secret=secret)


def static_path(color: str, piece_id: str) -> Path:
    return SPRITES_ROOT / color / piece_id / "static.png"


def save_png(img: Image.Image, color: str, piece_id: str) -> Path:
    p = static_path(color, piece_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    return p


def gen_anchor(client: pixellab.Client) -> Image.Image:
    """Anchor piece: white pawn via pixflux. Sets the style for the suite."""
    print("[1/9] anchor: white pawn (pixflux)")
    resp = client.generate_image_pixflux(
        description=DESCRIPTIONS_WHITE["pawn"] + STYLE,
        image_size={"width": SIZE, "height": SIZE},
        no_background=True,
        text_guidance_scale=8.0,
    )
    img = resp.image.pil_image()
    save_png(img, "white", "pawn")
    return img


def gen_white_base(client: pixellab.Client, anchor: Image.Image,
                   piece_id: str, idx: int, total: int) -> Image.Image:
    """Other white base pieces via pixflux. We pass the white pawn as
    init_image at LOW strength — just enough to anchor the palette and
    outline style across the suite without imposing the pawn's shape.
    Without the anchor, raising text_guidance_scale to 12 caused color
    drift (some pieces came out pink/brown/dark instead of cream)."""
    print(f"[{idx}/{total}] white {piece_id} (pixflux, style-anchor=pawn)")
    resp = client.generate_image_pixflux(
        description=DESCRIPTIONS_WHITE[piece_id] + STYLE,
        image_size={"width": SIZE, "height": SIZE},
        negative_description=NEGATIVE_WHITE.get(piece_id, ""),
        init_image=anchor,
        init_image_strength=50,     # very low — palette/outline anchor only
        no_background=True,
        text_guidance_scale=12.0,
    )
    img = resp.image.pil_image()
    save_png(img, "white", piece_id)
    return img


def gen_variant(client: pixellab.Client, base_img: Image.Image,
                v_id: str, base_id: str, desc: str, use_init: bool,
                idx: int, total: int) -> Image.Image:
    """White variant via pixflux. With use_init=True, init_image is
    the base sprite so the variant inherits its silhouette. With
    use_init=False, pure pixflux from text — needed when the feature
    is small enough that the base shape suppresses it (e.g. a sword
    behind the bishop)."""
    if use_init:
        print(f"[{idx}/{total}] white {v_id} (pixflux, init={base_id}, low init_strength)")
        resp = client.generate_image_pixflux(
            description=desc + STYLE,
            image_size={"width": SIZE, "height": SIZE},
            init_image=base_img,
            init_image_strength=80,    # very low — prompt almost dominates
            no_background=True,
            text_guidance_scale=12.0,
        )
    else:
        print(f"[{idx}/{total}] white {v_id} (pixflux, no init)")
        resp = client.generate_image_pixflux(
            description=desc + STYLE,
            image_size={"width": SIZE, "height": SIZE},
            no_background=True,
            text_guidance_scale=12.0,
        )
    img = resp.image.pil_image()
    save_png(img, "white", v_id)
    return img


# =============================================================================
# INPAINT HEAD REPLACEMENT
# =============================================================================
# Take an existing AI-generated piece and ask PixelLab to regenerate
# JUST the top region (the head) with the iconic feature prompt. Keeps
# the body intact while letting the model paint a distinctive head.

HEAD_PROMPTS = {
    "rook": ("the top of a stone castle wall: a perfectly FLAT and "
             "HORIZONTAL top edge (a straight horizontal line) with "
             "THREE SHORT SQUARE BLOCKS sticking straight UP from that "
             "flat line, evenly spaced. Like a tiny city wall battlement"),
    "bishop": ("smooth round-topped pixel-art bishop mitre with a "
               "clear PLUS SIGN cut (two perpendicular lines forming "
               "a cross shape) carved as a notch into the front face"),
    "queen": ("wide pixel-art chess queen crown with FIVE TALL SHARP "
              "POINTED SPIKES radiating straight up like a fan, the "
              "crown wider than the body, like a tiara of sharp peaks"),
    "king": ("a CLEAR plus-sign CROSS shape (vertical bar + horizontal "
             "crossbar) sitting on a tiny round orb at the very top"),
}

HEAD_NEGATIVES = {
    "rook":   "single point, spire, pointed top, cross, dome, sphere, finial, spike, peak, crown",
    "bishop": "cross on top, crown of points, multiple spikes, flat top, plain bauble",
    "queen":  "cross, single point, mitre, slit, dome, plain ball",
    "king":   "crown of points, multiple spikes, mitre, slit, plain bauble, single ball",
}


def _bbox_top(img: Image.Image) -> int | None:
    """Topmost y-coordinate of any non-transparent pixel."""
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 8:
                return y
    return None


def _make_head_mask(size, top_y: int, head_h: int) -> Image.Image:
    """Create a mask the same size as the sprite, white in the head
    region (top_y to top_y+head_h), black everywhere else."""
    w, h = size
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    bottom = min(h - 1, top_y + head_h)
    draw.rectangle([0, 0, w - 1, bottom], fill=(255, 255, 255, 255))
    return mask


def inpaint_head(client: pixellab.Client, piece_id: str,
                 head_h: int = 22) -> None:
    """Use PixelLab inpaint to replace the head region of an existing
    white sprite with the iconic feature for this piece."""
    img_path = static_path("white", piece_id)
    if not img_path.exists():
        print(f"[skip] {piece_id} (no existing sprite)")
        return
    img = Image.open(img_path).convert("RGBA")
    top_y = _bbox_top(img)
    if top_y is None:
        print(f"[skip] {piece_id} (transparent sprite?)")
        return
    mask = _make_head_mask(img.size, top_y, head_h)

    print(f"[inpaint] {piece_id} (head Y range {top_y}..{top_y + head_h})")
    resp = client.inpaint(
        description=HEAD_PROMPTS[piece_id] + STYLE,
        image_size={"width": img.size[0], "height": img.size[1]},
        inpainting_image=img,
        mask_image=mask,
        negative_description=HEAD_NEGATIVES.get(piece_id, ""),
        no_background=True,
        text_guidance_scale=10.0,   # inpaint max is 10
    )
    out = resp.image.pil_image()
    out.save(img_path)
    # Recolor the new white to black
    recolor_to_black(out).save(static_path("black", piece_id))


def recolor_to_black(white_img: Image.Image) -> Image.Image:
    """Procedural white -> black palette swap.
    Approach: brightness-based remap. Bright pixels (the cream interior)
    get mapped to dark grey; dark pixels (the outline / shadows) stay
    near-dark with a small lift so they don't blend into the new fill.
    Transparent pixels stay transparent."""
    img = white_img.convert("RGBA").copy()
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 8:
                continue
            v = (r + g + b) / 3.0
            if v >= 200:
                # Bright fill (white) → mid-dark grey
                nv = 64
            elif v >= 140:
                # Mid fill (mid highlight) → darker grey
                nv = 48
            elif v >= 80:
                # Shadow tones → very dark grey, slight blue cast
                nv = 32
            else:
                # Outline / deep shadow → keep near-black, very slight lift
                nv = max(r, 12)
                px[x, y] = (nv, nv, nv, a)
                continue
            # Slight cool tint so black pieces don't read as muddy brown
            px[x, y] = (nv, nv, min(255, nv + 6), a)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if static.png already exists")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Generate only these piece ids (e.g. --only pawn knight)")
    args = ap.parse_args()

    client = load_client()
    print(f"PixelLab credit balance: {client.get_balance()}")

    only = set(args.only) if args.only else None

    def needs(piece_id: str) -> bool:
        if only is not None and piece_id not in only:
            return False
        if args.force:
            return True
        return not static_path("white", piece_id).exists()

    # Phase 1: anchor (white pawn)
    anchor = None
    if needs("pawn"):
        anchor = gen_anchor(client)
        time.sleep(0.5)
    else:
        anchor = Image.open(static_path("white", "pawn"))
        print("[skip] white pawn (already exists)")

    # Phase 2: other 5 white base pieces
    others = [p for p in BASE_PIECES if p != "pawn"]
    total_base = sum(1 for p in others if needs(p))
    base_done = 1
    for piece_id in others:
        if not needs(piece_id):
            print(f"[skip] white {piece_id}")
            continue
        base_done += 1
        gen_white_base(client, anchor, piece_id, base_done, 9)
        time.sleep(0.5)

    # Phase 3: white variants (need their base to exist if use_init=True)
    var_done = 6
    for v_id, base_id, desc, use_init in VARIANTS:
        if not needs(v_id):
            print(f"[skip] white {v_id}")
            continue
        base_img = None
        if use_init:
            base_path = static_path("white", base_id)
            if not base_path.exists():
                print(f"[error] {v_id} requires white {base_id} which is missing — "
                      f"run without --only or with --force, or generate {base_id} first")
                continue
            base_img = Image.open(base_path)
        var_done += 1
        gen_variant(client, base_img, v_id, base_id, desc, use_init, var_done, 9)
        time.sleep(0.5)

    # Phase 4: black recolors (always run for any white that exists, unless
    # the corresponding black already exists and --force is off)
    print("\nRecoloring to black...")
    all_pieces = BASE_PIECES + [v[0] for v in VARIANTS]
    for piece_id in all_pieces:
        if only is not None and piece_id not in only:
            continue
        white_path = static_path("white", piece_id)
        black_path = static_path("black", piece_id)
        if not white_path.exists():
            continue
        if black_path.exists() and not args.force:
            print(f"[skip] black {piece_id}")
            continue
        white_img = Image.open(white_path)
        black_img = recolor_to_black(white_img)
        black_path.parent.mkdir(parents=True, exist_ok=True)
        black_img.save(black_path)
        print(f"[ok]   black {piece_id} -> {black_path.relative_to(ROOT)}")

    print("\nDone.")
    print(f"Final balance: {client.get_balance()}")


if __name__ == "__main__":
    main()
