"""Build the two cape/sword variants from their base pieces via PixelLab
inpaint.

  assassin_bishop = bishop + sword. Mask covers the region ABOVE the
                    bishop's mitre so PixelLab can paint a hilt + cross-
                    guard sticking up from the head. Body untouched.
  bandit_pawn     = pawn + cape. Mask covers the lower-body sides
                    (where the cape drapes), preserving the head ball
                    and the base disc.

For each, several candidates are generated; each is scored on:
  base_id: pixel-identity in the protected (non-masked) region
  growth:  opaque pixels gained in the masked region (the new feature
           must extend silhouette / add ink, not just repaint white)
  vis:     'dark' opaque pixels in the masked region (feature ink)
  symm:    bilateral symmetry of the new sprite (low priority since the
           sword and cape are intrinsically off-center, but we still
           prefer the bishop's overall symmetry to be preserved)

Hard reject if base_id < 0.999 (we asked the user-protected area to
stay byte-identical).
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

import pixellab
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_sprites import recolor_to_black  # noqa: E402

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
ITER_ROOT = ROOT / "tools" / "iter" / "variants"
SIZE = 64
ALPHA_THRESH = 8
DARK_RGB_SUM = 360

STYLE = (
    ", clean pixel art chess piece, frontal view, simple flat background "
    "to be removed, single piece centered, dark outline, smooth shading, "
    "white cream coloring matching the suite"
)

GUIDANCES = [9.0, 10.0]
ROUNDS = 3


def load_client() -> pixellab.Client:
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    return pixellab.Client(secret=secret)


def alpha_mask(img: Image.Image) -> list[list[bool]]:
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def topmost_y(mask) -> int:
    w = len(mask); h = len(mask[0])
    for y in range(h):
        for x in range(w):
            if mask[x][y]:
                return y
    return 0


def silhouette_pixels(img: Image.Image, region: tuple[int, int, int, int] | None = None) -> int:
    w, h = img.size
    px = img.load()
    x0, y0, x1, y1 = region or (0, 0, w, h)
    return sum(1 for y in range(y0, y1) for x in range(x0, x1) if px[x, y][3] > ALPHA_THRESH)


# ---------------------------------------------------------------------------
# Mask builders
# ---------------------------------------------------------------------------

def sword_mask(bishop: Image.Image) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Mask = a vertical strip above the bishop's mitre, centered on the
    silhouette's horizontal axis. PixelLab will paint hilt+cross-guard
    sticking up from the head there. Returns (mask, mask_rects)."""
    w, h = bishop.size
    m = alpha_mask(bishop)
    top = topmost_y(m)
    # horizontal center of the mitre at row top+5
    sample = top + 5
    xs = [x for x in range(w) if m[x][sample]]
    cx = (xs[0] + xs[-1]) // 2 if xs else w // 2

    # Mask is a 12-wide rect above the mitre, from canvas top down to
    # just below the topmost silhouette row (so cross-guard can sit
    # right at the bead).
    half_w = 6
    x0 = max(0, cx - half_w)
    x1 = min(w - 1, cx + half_w)
    y0 = 0
    y1 = max(0, top + 1)
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    rects = [(x0, y0, x1, y1)]
    draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, 255))
    return mask, rects


def cape_mask(pawn: Image.Image) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Mask covers the area where a cape drapes — the lower-body sides
    PLUS a short band of body width above the shoulders so the cape can
    spill over and back. The head ball and the base disc are preserved.
    """
    w, h = pawn.size
    m = alpha_mask(pawn)
    top = topmost_y(m)
    # find bottom (last opaque row)
    bot = h - 1
    for y in range(h - 1, -1, -1):
        if any(m[x][y] for x in range(w)):
            bot = y
            break
    head_h_protect = 13   # protect rows [top .. top+head_h_protect-1] (head ball + neck)
    base_h_protect = 5    # protect rows [bot-base_h_protect+1 .. bot] (base disc)
    cape_top = top + head_h_protect
    cape_bot = bot - base_h_protect

    # Find body horizontal extent over cape_top..cape_bot to size the mask
    body_left = w; body_right = -1
    for y in range(cape_top, cape_bot + 1):
        xs = [x for x in range(w) if m[x][y]]
        if xs:
            body_left = min(body_left, xs[0])
            body_right = max(body_right, xs[-1])
    # Pad horizontally so cape can extend past the pawn body edges
    pad = 6
    x0 = max(0, body_left - pad)
    x1 = min(w - 1, body_right + pad)

    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    rects = [(x0, cape_top, x1, cape_bot)]
    draw.rectangle([x0, cape_top, x1, cape_bot], fill=(255, 255, 255, 255))
    return mask, rects


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def in_any_rect(x: int, y: int, rects) -> bool:
    for x0, y0, x1, y1 in rects:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def base_identity(orig: Image.Image, new: Image.Image, rects) -> float:
    op = orig.load(); np = new.load()
    w, h = orig.size
    same = 0; total = 0
    for y in range(h):
        for x in range(w):
            if in_any_rect(x, y, rects):
                continue
            total += 1
            if op[x, y] == np[x, y]:
                same += 1
    return same / max(1, total)


def feature_growth_and_visibility(orig: Image.Image, new: Image.Image, rects) -> tuple[int, int]:
    """Returns (silhouette_growth, dark_pixels) inside the mask region."""
    op = orig.load(); np = new.load()
    w, h = orig.size
    growth = 0; dark = 0
    for y in range(h):
        for x in range(w):
            if not in_any_rect(x, y, rects):
                continue
            o_op = op[x, y][3] > ALPHA_THRESH
            n_op = np[x, y][3] > ALPHA_THRESH
            if not o_op and n_op:
                growth += 1
            if n_op and sum(np[x, y][:3]) < DARK_RGB_SUM:
                dark += 1
    return growth, dark


def overall_symmetry(img: Image.Image) -> float:
    """Whole-sprite symmetry as a sanity signal."""
    a = alpha_mask(img)
    b = alpha_mask(ImageOps.mirror(img))
    w = len(a); h = len(a[0])
    op = sum(1 for x in range(w) for y in range(h) if a[x][y])
    if op == 0:
        return 0.0
    mm = sum(1 for x in range(w) for y in range(h) if a[x][y] != b[x][y])
    return max(0.0, 1.0 - mm / op)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(client, name: str, base: Image.Image, mask: Image.Image,
        rects, desc: str, neg: str, growth_floor: int, vis_floor: int,
        out_dir: Path, weight_symm: float = 0.10,
        no_background: bool = True) -> dict | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    base.save(out_dir / "_base.png")
    mask.save(out_dir / "_mask.png")
    cands = []
    idx = 0
    for r in range(ROUNDS):
        for g in GUIDANCES:
            idx += 1
            print(f"  [{name} {idx}] guidance={g} round={r+1}")
            try:
                resp = client.inpaint(
                    description=desc + STYLE,
                    image_size={"width": SIZE, "height": SIZE},
                    inpainting_image=base,
                    mask_image=mask,
                    negative_description=neg,
                    no_background=no_background,
                    text_guidance_scale=g,
                )
                img = resp.image.pil_image()
                p = out_dir / f"cand_{idx:02d}_g{g}_r{r+1}.png"
                img.save(p)
                bid = base_identity(base, img, rects)
                growth, dark = feature_growth_and_visibility(base, img, rects)
                symm = overall_symmetry(img)
                # Visibility score: prefer >= vis_floor dark pixels
                vis_score = min(1.0, dark / max(1, vis_floor))
                # Growth score: prefer >= growth_floor opaque-extension pixels
                grow_score = min(1.0, growth / max(1, growth_floor))
                if bid < 0.999:
                    sc = 0.0
                else:
                    sc = (0.45 * vis_score
                          + 0.30 * grow_score
                          + weight_symm * symm
                          + 0.15 * bid)
                print(f"      base_id={bid:.4f} growth={growth} dark={dark} "
                      f"symm={symm:.3f} score={sc:.3f}  -> {p.name}")
                cands.append({"img": img, "path": p, "score": sc,
                              "base_id": bid, "growth": growth,
                              "dark": dark, "symm": symm})
            except Exception as e:
                print(f"      [error] {e}")
            time.sleep(0.4)
    if not cands:
        return None
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands[0]


def main():
    client = load_client()
    print(f"PixelLab balance: {client.get_balance()}")

    # Step A: assassin_bishop = current bishop + sword above mitre
    print("\n[assassin_bishop]")
    bishop = Image.open(WHITE_DIR / "bishop" / "static.png").convert("RGBA")
    s_mask, s_rects = sword_mask(bishop)
    sword_desc = (
        "A pixel-art chess bishop with a SHEATHED SWORD sticking up out "
        "of the very top of the mitre — a clear vertical dark sword "
        "HILT (round pommel at the very top + grip + a small horizontal "
        "CROSS-GUARD just above the mitre tip). The sword occupies the "
        "blank canvas above the bishop's head and is the most prominent "
        "added element. Recognizable as a sword hilt at first glance"
    )
    sword_neg = (
        "no sword, plain bishop, crown, peaks, fleur de lis, mitre on "
        "top, bauble, weapon in front, gun, axe, hammer, staff, "
        "candlestick"
    )
    a_best = run(client, "assassin_bishop", bishop, s_mask, s_rects,
                 sword_desc, sword_neg, growth_floor=12, vis_floor=8,
                 out_dir=ITER_ROOT / "assassin_bishop")
    if a_best and a_best["score"] >= 0.45:
        a_best["img"].save(WHITE_DIR / "assassin_bishop" / "static.png")
        recolor_to_black(a_best["img"]).save(BLACK_DIR / "assassin_bishop" / "static.png")
        print(f"  saved assassin_bishop (score {a_best['score']:.3f})")
    else:
        print(f"  [skip] assassin_bishop best score "
              f"{a_best['score']:.3f if a_best else 0:.3f} too low")

    time.sleep(0.4)

    # Step B: bandit_pawn = current pawn + cape around body
    print("\n[bandit_pawn]")
    pawn = Image.open(WHITE_DIR / "pawn" / "static.png").convert("RGBA")
    c_mask, c_rects = cape_mask(pawn)
    cape_desc = (
        "A pixel-art chess pawn wearing a flowing dark CAPE draped over "
        "its shoulders and falling down behind/beside the body. The "
        "cape has a clear silhouette extending OUTWARD from the body "
        "(billowing) and is rendered in a darker shade than the white "
        "pawn so it reads as a separate fabric element. The pawn's "
        "ROUND HEAD BALL on top and the WIDE ROUND BASE at the bottom "
        "are unchanged"
    )
    cape_neg = (
        "no cape, plain pawn, hood, helmet, hat, dress, robe covering "
        "the head, full-body wrap that hides the silhouette, pointed "
        "hat"
    )
    b_best = run(client, "bandit_pawn", pawn, c_mask, c_rects,
                 cape_desc, cape_neg, growth_floor=18, vis_floor=12,
                 out_dir=ITER_ROOT / "bandit_pawn")
    if b_best and b_best["score"] >= 0.45:
        b_best["img"].save(WHITE_DIR / "bandit_pawn" / "static.png")
        recolor_to_black(b_best["img"]).save(BLACK_DIR / "bandit_pawn" / "static.png")
        print(f"  saved bandit_pawn (score {b_best['score']:.3f})")
    else:
        print(f"  [skip] bandit_pawn best score "
              f"{b_best['score']:.3f if b_best else 0:.3f} too low")

    # Cleanup if both committed
    a_ok = a_best and a_best["score"] >= 0.45
    b_ok = b_best and b_best["score"] >= 0.45
    if a_ok and b_ok and ITER_ROOT.exists():
        shutil.rmtree(ITER_ROOT)
        print(f"\nremoved {ITER_ROOT.relative_to(ROOT)}")
    elif ITER_ROOT.exists():
        print(f"\n[kept] {ITER_ROOT.relative_to(ROOT)} for inspection")


if __name__ == "__main__":
    main()
