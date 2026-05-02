"""Simplify the queen's crown via PixelLab inpaint.

Iterates a handful of candidates with varied guidance, scoring each on:
  symm: bilateral symmetry of the new crown silhouette (left half vs.
        mirrored right half)
  simp: simplicity — fewer "peaks" (silhouette-top zigzag transitions
        across the crown row band) is better
  body: the body BELOW the crown must be unchanged. Computed as
        fraction of identical pixels (alpha+RGB exact match) below the
        crown bbox. Should stay near 1.0 since inpaint only touches the
        masked region.

Final score = 0.40 * symm + 0.40 * simp + 0.20 * body.
Hard reject if body < 0.999 (we asked for "everything else same") or if
the new crown has zero opaque pixels.

Best candidate is committed to white/queen + black recolor; iter dir is
deleted on success.
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
ITER_ROOT = ROOT / "tools" / "iter" / "queen_simp"
SIZE = 64
ALPHA_THRESH = 8

STYLE = (
    ", clean pixel art chess piece, frontal view, simple flat background "
    "to be removed, single piece centered, dark outline, smooth shading, "
    "white cream coloring"
)

DESC = (
    "Pixel-art on top of a chess piece's body: a SMOOTH ROUNDED DOME "
    "shape, like a MUSHROOM CAP or a half-circle balloon resting on "
    "the shoulders. The dome is ONE single continuous curve — picture "
    "a rainbow arch or the top of a bald head: a single uninterrupted "
    "rounded silhouette with NO peaks, NO points, NO spikes, NO "
    "scallops, NO bumps, NO pearls. Just one perfectly smooth arched "
    "outline going up and back down. PERFECTLY BILATERALLY SYMMETRIC "
    "across the vertical center: the left half is an exact mirror of "
    "the right half. White cream coloring with a clean 1-pixel dark "
    "outline. Empty interior, no internal markings"
)

NEG = (
    "any peak, any point, any spike, any bump, multiple peaks, two "
    "peaks, three peaks, four peaks, five peaks, fan of spikes, "
    "zig-zag, scalloped edge, jagged top, busy outline, pearl on top, "
    "ball on top, notch, slit, asymmetric, lopsided, tilted, mitre, "
    "cross, fleur de lis, filigree, internal lines, dark splotches "
    "inside, non-uniform fill, crown with points, tiara"
)

CROWN_H = 16  # rows from top of silhouette
GUIDANCES = [7.0, 8.5, 10.0]
ROUNDS = 3  # 9 candidates total — more shots at a single-arch result
MIN_BODY_IDENTITY = 0.999


def load_client() -> pixellab.Client:
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    return pixellab.Client(secret=secret)


def alpha_mask(img: Image.Image) -> list[list[bool]]:
    w, h = img.size
    px = img.load()
    return [[px[x, y][3] > ALPHA_THRESH for y in range(h)] for x in range(w)]


def topmost_y(mask: list[list[bool]]) -> int:
    w = len(mask); h = len(mask[0])
    for y in range(h):
        for x in range(w):
            if mask[x][y]:
                return y
    return 0


def make_crown_mask(img: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Mask covers the crown rows, horizontally bounded by the head's
    actual width + a small pad so the inpaint can't blow it sideways.
    """
    w, h = img.size
    m = alpha_mask(img)
    top = topmost_y(m)
    bot = min(h - 1, top + CROWN_H - 1)

    head_left = w; head_right = -1
    for y in range(top, bot + 1):
        xs = [x for x in range(w) if m[x][y]]
        if xs:
            head_left = min(head_left, xs[0])
            head_right = max(head_right, xs[-1])
    if head_right < 0:
        head_left, head_right = 0, w - 1
    pad = 4
    x0 = max(0, head_left - pad)
    x1 = min(w - 1, head_right + pad)

    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle([x0, top, x1, bot], fill=(255, 255, 255, 255))
    return mask, (x0, top, x1 + 1, bot + 1)


def symmetry(img: Image.Image, bbox) -> float:
    crop = img.crop(bbox)
    a = alpha_mask(crop); b = alpha_mask(ImageOps.mirror(crop))
    w = len(a); h = len(a[0])
    op = sum(1 for x in range(w) for y in range(h) if a[x][y])
    if op == 0:
        return 0.0
    mm = sum(1 for x in range(w) for y in range(h) if a[x][y] != b[x][y])
    return max(0.0, 1.0 - mm / op)


def simplicity(img: Image.Image, bbox) -> float:
    """Count silhouette-top transitions in the top 4 rows of the crown.
    Fewer transitions → fewer peaks → simpler. Score scales 0..1."""
    crop = img.crop(bbox)
    cm = alpha_mask(crop)
    cw = len(cm); ch = len(cm[0])
    if ch < 4 or cw < 4:
        return 0.0
    # Top profile: per column, the topmost row index that has alpha. If
    # no alpha, mark as None (sky).
    top_profile = []
    for x in range(cw):
        ty = None
        for y in range(ch):
            if cm[x][y]:
                ty = y
                break
        top_profile.append(ty)
    # Count transitions where the top y rises (peak start) or falls.
    # We treat None like ch (very low) so transitions register at the
    # outer edges too.
    seq = [(ch if t is None else t) for t in top_profile]
    # Local minima count = number of peaks (low y = high peak).
    peaks = 0
    for i in range(1, cw - 1):
        if seq[i] < seq[i - 1] and seq[i] <= seq[i + 1]:
            # plateau handling: walk the plateau and count once
            j = i
            while j + 1 < cw - 1 and seq[j + 1] == seq[i]:
                j += 1
            peaks += 1
    # Target: 0 peaks (a pure smooth dome — the local-min detector
    # finds no protrusions). 1 peak is also fine (a single rounded
    # arch with a slight high point). >=2 is the bad case we're
    # trying to escape (multi-bump crown).
    if peaks == 0:
        return 1.0
    if peaks == 1:
        return 0.95
    if peaks == 2:
        return 0.40
    return max(0.0, 1.0 - peaks * 0.20)


def body_identity(orig: Image.Image, new: Image.Image, bbox) -> float:
    """Fraction of pixels OUTSIDE the crown bbox that are byte-identical
    between orig and new. Should be ~1.0 since inpaint shouldn't touch
    those pixels."""
    if orig.size != new.size:
        return 0.0
    op = orig.load(); np = new.load()
    w, h = orig.size
    x0, y0, x1, y1 = bbox
    total = 0; same = 0
    for y in range(h):
        for x in range(w):
            if x0 <= x < x1 and y0 <= y < y1:
                continue
            total += 1
            if op[x, y] == np[x, y]:
                same += 1
    return same / max(1, total)


def score(symm, simp, body) -> float:
    if body < MIN_BODY_IDENTITY:
        return 0.0
    return 0.30 * symm + 0.50 * simp + 0.20 * body


def main():
    base = Image.open(WHITE_DIR / "queen" / "static.png").convert("RGBA")
    mask, bbox = make_crown_mask(base)
    out_dir = ITER_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    base.save(out_dir / "_base.png")
    mask.save(out_dir / "_mask.png")

    client = load_client()
    print(f"PixelLab balance: {client.get_balance()}")

    candidates = []
    idx = 0
    for r in range(ROUNDS):
        for g in GUIDANCES:
            idx += 1
            label = f"r{r+1}_g{g}"
            print(f"  [{idx}] guidance={g} round={r+1}")
            try:
                resp = client.inpaint(
                    description=DESC + STYLE,
                    image_size={"width": SIZE, "height": SIZE},
                    inpainting_image=base,
                    mask_image=mask,
                    negative_description=NEG,
                    no_background=True,
                    text_guidance_scale=g,
                )
                img = resp.image.pil_image()
                p = out_dir / f"cand_{idx:02d}_{label}.png"
                img.save(p)
                s_symm = symmetry(img, bbox)
                s_simp = simplicity(img, bbox)
                s_body = body_identity(base, img, bbox)
                sc = score(s_symm, s_simp, s_body)
                print(f"      symm={s_symm:.3f} simp={s_simp:.3f} "
                      f"body={s_body:.4f} score={sc:.3f}  -> {p.name}")
                candidates.append({"path": p, "img": img, "symm": s_symm,
                                   "simp": s_simp, "body": s_body, "score": sc})
            except Exception as e:
                print(f"      [error] {e}")
            time.sleep(0.4)

    if not candidates:
        sys.exit("no candidates")
    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    print(f"\nbest: {best['path'].name}  symm={best['symm']:.3f} "
          f"simp={best['simp']:.3f} body={best['body']:.4f} "
          f"score={best['score']:.3f}")

    if best["score"] < 0.6:
        print(f"[skip] best score {best['score']:.3f} below 0.6 — leaving "
              f"queen master untouched. Iter dir kept for inspection.")
        return

    img = best["img"]
    img.save(WHITE_DIR / "queen" / "static.png")
    recolor_to_black(img).save(BLACK_DIR / "queen" / "static.png")
    print("saved white/black queen masters.")
    if ITER_ROOT.exists():
        shutil.rmtree(ITER_ROOT)
        print(f"removed {ITER_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
