"""Add a small dark cross to the bishop's mitre via PixelLab inpaint.

Iterates a handful of candidates, scoring each on:
  body:    pixel-identity outside the mitre mask (must be ~1.0)
  visible: count of 'dark' pixels (RGB sum < 360 over an opaque pixel)
           inside the mask, normalized — a recognizable cross uses
           5–14 dark pixels in a 64x64 sprite
  symm:    bilateral symmetry of the mask crop's alpha+darkness pattern
  After scoring, the best valid candidate replaces the master sprite.

If no candidate clears the visibility threshold (i.e. PixelLab refuses
to paint a visible cross at any guidance), the script aborts and leaves
the bishop master untouched + keeps the iter dir for inspection.
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
ITER_ROOT = ROOT / "tools" / "iter" / "bishop_cross"
SIZE = 64
ALPHA_THRESH = 8
DARK_RGB_SUM = 360  # below this an opaque pixel counts as 'dark' (cross ink)

STYLE = (
    ", clean pixel art chess piece, frontal view, simple flat background "
    "to be removed, single piece centered, dark outline, smooth shading, "
    "white cream coloring"
)

DESC = (
    "Pixel-art chess bishop's mitre cap with a small but CLEARLY VISIBLE "
    "DARK CHRISTIAN CROSS painted on the front face — a plus-sign shape "
    "made of one short vertical pixel bar crossed by one short "
    "horizontal pixel bar, in a dark color that contrasts strongly with "
    "the cream mitre. The cross sits in the center of the mitre face. "
    "Bilaterally symmetric"
)

NEG = (
    "no cross, plain mitre, slit, notch, fleur de lis, multiple crosses, "
    "letter shape, decoration, ornate pattern, asymmetric cross"
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


def make_mask(bishop: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Mask covering a small rect on the bishop's mitre face.
    The mask is centered on the silhouette's horizontal axis at the
    upper portion of the mitre."""
    w, h = bishop.size
    m = alpha_mask(bishop)
    top = topmost_y(m)
    # Mid-mitre row to find horizontal center
    mid = top + 7
    xs = [x for x in range(w) if m[x][mid]]
    if not xs:
        sys.exit("no mitre row found")
    cx = (xs[0] + xs[-1]) // 2
    half_w = max(4, (xs[-1] - xs[0]) // 2)
    y0 = top + 3
    y1 = top + 13
    x0 = max(0, cx - half_w)
    x1 = min(w - 1, cx + half_w)
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, 255))
    return mask, (x0, y0, x1 + 1, y1 + 1)


def body_identity(orig: Image.Image, new: Image.Image, bbox) -> float:
    op = orig.load(); np = new.load()
    w, h = orig.size
    x0, y0, x1, y1 = bbox
    same = 0; total = 0
    for y in range(h):
        for x in range(w):
            if x0 <= x < x1 and y0 <= y < y1:
                continue
            total += 1
            if op[x, y] == np[x, y]:
                same += 1
    return same / max(1, total)


def cross_visibility(img: Image.Image, bbox) -> tuple[float, int]:
    """Count dark opaque pixels inside the bbox; map to 0..1 score peaking
    at 5..14 dark pixels (a typical small cross)."""
    crop = img.crop(bbox)
    cw, ch = crop.size
    px = crop.load()
    dark = 0
    for y in range(ch):
        for x in range(cw):
            r, g, b, a = px[x, y]
            if a > ALPHA_THRESH and (r + g + b) < DARK_RGB_SUM:
                dark += 1
    if dark < 4:
        score = dark / 4 * 0.4   # under-painted
    elif dark <= 14:
        score = 1.0
    elif dark <= 24:
        score = 1.0 - (dark - 14) * 0.07
    else:
        score = max(0.0, 1.0 - (dark - 14) * 0.05)
    return score, dark


def symmetry(img: Image.Image, bbox) -> float:
    crop = img.crop(bbox)
    cw, ch = crop.size
    a = crop.load()
    b = ImageOps.mirror(crop).load()
    matches = 0; opaque = 0
    for y in range(ch):
        for x in range(cw):
            ao = a[x, y][3] > ALPHA_THRESH
            bo = b[x, y][3] > ALPHA_THRESH
            if ao or bo:
                opaque += 1
                # match if both opaque or both transparent AND
                # darkness matches
                a_dark = ao and sum(a[x, y][:3]) < DARK_RGB_SUM
                b_dark = bo and sum(b[x, y][:3]) < DARK_RGB_SUM
                if ao == bo and a_dark == b_dark:
                    matches += 1
    return matches / max(1, opaque)


def score(body, vis, symm) -> float:
    if body < 0.999:
        return 0.0
    if vis == 0.0:
        return 0.0
    return 0.40 * vis + 0.40 * symm + 0.20 * body


def main():
    base_path = WHITE_DIR / "bishop" / "static.png"
    base = Image.open(base_path).convert("RGBA")
    mask, bbox = make_mask(base)
    out_dir = ITER_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    base.save(out_dir / "_base.png")
    mask.save(out_dir / "_mask.png")

    client = load_client()
    print(f"PixelLab balance: {client.get_balance()}")

    cands = []
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
                b = body_identity(base, img, bbox)
                v, dark_n = cross_visibility(img, bbox)
                s = symmetry(img, bbox)
                sc = score(b, v, s)
                print(f"      body={b:.4f} vis={v:.3f}({dark_n} dark) "
                      f"symm={s:.3f} score={sc:.3f}  -> {p.name}")
                cands.append({"path": p, "img": img, "body": b, "vis": v,
                              "symm": s, "score": sc, "dark_n": dark_n})
            except Exception as e:
                print(f"      [error] {e}")
            time.sleep(0.4)

    if not cands:
        sys.exit("no candidates")
    cands.sort(key=lambda c: c["score"], reverse=True)
    best = cands[0]
    print(f"\nbest: {best['path'].name}  body={best['body']:.4f} "
          f"vis={best['vis']:.3f}({best['dark_n']}) symm={best['symm']:.3f} "
          f"score={best['score']:.3f}")
    if best["score"] < 0.5:
        print("[skip] best score below 0.5 — leaving bishop master untouched")
        return
    img = best["img"]
    img.save(base_path)
    recolor_to_black(img).save(BLACK_DIR / "bishop" / "static.png")
    print("saved bishop masters.")
    if ITER_ROOT.exists():
        shutil.rmtree(ITER_ROOT)
        print(f"removed {ITER_ROOT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
