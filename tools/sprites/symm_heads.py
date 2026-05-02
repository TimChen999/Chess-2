"""Symmetrize bishop and queen heads via PixelLab inpaint.

For each piece we mask the head region (top portion of the silhouette)
and run several inpaint candidates with varied guidance. Each candidate
is scored on:

  symmetry: 1 - (mismatched alpha cells when the head crop is flipped
            left/right) / (opaque cells in the head crop)
  feature:  retained head opaque-pixel count vs. original (ratio close
            to 1.0 means we didn't lose mass — i.e. mitre/crown features
            survived).

Combined score = 0.65 * symmetry + 0.35 * feature_retention. We pick the
highest-scoring candidate, copy it to the master sprite + recolor black,
and remove the iteration dir.

Outputs (during run):  tools/iter/symm/<piece>/cand_<n>.png
Final masters:         godot/assets/sprites/anim/pieces/{white,black}/
                         <piece>/static.png
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
ITER_ROOT = ROOT / "tools" / "iter" / "symm"
SIZE = 64
ALPHA_THRESH = 8

STYLE = (
    ", clean pixel art chess piece, frontal view, simple flat background "
    "to be removed, single piece centered, dark outline, smooth shading, "
    "white cream coloring"
)

PIECES = {
    "bishop": {
        "head_h": 18,
        "desc": (
            "Pixel-art chess bishop's mitre cap — a tall pointed oval "
            "helmet ending in a small round bead at the top. The cap is "
            "PERFECTLY BILATERALLY SYMMETRIC: the left half mirrors the "
            "right half exactly across the vertical center line. The "
            "outline is a smooth teardrop shape. White cream coloring "
            "with a dark outline"
        ),
        "neg": (
            "asymmetric, lopsided, tilted, leaning, slit on one side, "
            "extra bump, multiple peaks, crown of points, spikes, flat "
            "top, helmet, hat"
        ),
    },
    "queen": {
        "head_h": 22,
        "desc": (
            "Pixel-art chess queen's crown — a wide tiara with FIVE TALL "
            "SHARP POINTED PEAKS radiating straight up like a fan, each "
            "peak the same height, evenly spaced. The crown is PERFECTLY "
            "BILATERALLY SYMMETRIC: left half mirrors the right half "
            "exactly. White cream coloring with dark outline"
        ),
        "neg": (
            "asymmetric, lopsided, tilted, mitre, slit, single point, "
            "dome, plain ball top, cross, fewer than five peaks, more "
            "than five peaks, uneven peaks"
        ),
    },
}

GUIDANCES = [8.0, 9.0, 10.0]
ROUNDS_PER_PIECE = 2  # generates len(GUIDANCES) * ROUNDS_PER_PIECE candidates


def load_client() -> pixellab.Client:
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    if not secret:
        sys.exit("PIXELLAB_API_KEY missing")
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


def head_mask(img: Image.Image, head_h: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """White rectangle covering the head region; black elsewhere. The
    horizontal extent is bounded by the head's actual width (max width
    across the head rows) plus a small padding, so the inpaint can't
    explode the head sideways and double its mass."""
    w, h = img.size
    m = alpha_mask(img)
    top = topmost_y(m)
    bot = min(h - 1, top + head_h - 1)

    # Find the widest row in the head region to size the horizontal mask.
    head_left = w
    head_right = -1
    for y in range(top, bot + 1):
        xs = [x for x in range(w) if m[x][y]]
        if xs:
            head_left = min(head_left, xs[0])
            head_right = max(head_right, xs[-1])
    if head_right < 0:
        head_left, head_right = 0, w - 1

    pad = 4  # small symmetry leeway, but not enough to double width
    x0 = max(0, head_left - pad)
    x1 = min(w - 1, head_right + pad)

    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(mask)
    draw.rectangle([x0, top, x1, bot], fill=(255, 255, 255, 255))
    return mask, (x0, top, x1 + 1, bot + 1)


def head_symmetry_score(img: Image.Image, bbox: tuple[int, int, int, int]) -> float:
    """1.0 = perfectly symmetric, 0.0 = totally asymmetric."""
    crop = img.crop(bbox)
    flipped = ImageOps.mirror(crop)
    a = alpha_mask(crop)
    b = alpha_mask(flipped)
    w = len(a); h = len(a[0])
    opaque = sum(1 for x in range(w) for y in range(h) if a[x][y])
    if opaque == 0:
        return 0.0
    mismatch = sum(1 for x in range(w) for y in range(h) if a[x][y] != b[x][y])
    return max(0.0, 1.0 - (mismatch / opaque))


def feature_retention(orig_img: Image.Image, new_img: Image.Image,
                      bbox: tuple[int, int, int, int]) -> float:
    """Ratio of head opaque pixels in new vs original. Closer to 1 is
    better; values << 1 mean we lost mass (e.g. mitre got chopped),
    values >> 1 mean we gained mass (head got fatter/extra peaks)."""
    a = alpha_mask(orig_img.crop(bbox))
    b = alpha_mask(new_img.crop(bbox))
    w = len(a); h = len(a[0])
    oa = sum(1 for x in range(w) for y in range(h) if a[x][y])
    ob = sum(1 for x in range(w) for y in range(h) if b[x][y])
    if oa == 0 or ob == 0:
        # head was emptied — don't trust the symmetry score either, the
        # caller should reject this candidate outright
        return 0.0
    ratio = ob / oa
    return max(0.0, 1.0 - abs(ratio - 1.0))


def combined_score(symm: float, feat: float) -> float:
    # Hard reject if features were destroyed — symmetric emptiness is
    # not a valid result.
    if feat == 0.0:
        return 0.0
    return 0.65 * symm + 0.35 * feat


def run_piece(client: pixellab.Client, piece: str) -> tuple[Path, dict]:
    cfg = PIECES[piece]
    src = WHITE_DIR / piece / "static.png"
    base = Image.open(src).convert("RGBA")
    mask, bbox = head_mask(base, cfg["head_h"])

    out_dir = ITER_ROOT / piece
    out_dir.mkdir(parents=True, exist_ok=True)
    mask.save(out_dir / "_mask.png")
    base.save(out_dir / "_base.png")

    candidates = []
    cand_idx = 0
    for r in range(ROUNDS_PER_PIECE):
        for g in GUIDANCES:
            cand_idx += 1
            label = f"r{r+1}_g{g}"
            print(f"  [{piece} {cand_idx}] guidance={g} round={r+1}")
            try:
                resp = client.inpaint(
                    description=cfg["desc"] + STYLE,
                    image_size={"width": SIZE, "height": SIZE},
                    inpainting_image=base,
                    mask_image=mask,
                    negative_description=cfg["neg"],
                    no_background=True,
                    text_guidance_scale=g,
                )
                img = resp.image.pil_image()
                p = out_dir / f"cand_{cand_idx:02d}_{label}.png"
                img.save(p)
                symm = head_symmetry_score(img, bbox)
                feat = feature_retention(base, img, bbox)
                score = combined_score(symm, feat)
                print(f"      symm={symm:.3f} feat={feat:.3f} score={score:.3f}  -> {p.name}")
                candidates.append({"path": p, "symm": symm, "feat": feat,
                                   "score": score, "img": img})
            except Exception as e:
                print(f"      [error] {e}")
            time.sleep(0.4)

    if not candidates:
        sys.exit(f"no candidates produced for {piece}")
    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    print(f"  best: {best['path'].name}  symm={best['symm']:.3f}  feat={best['feat']:.3f}")
    return best["path"], best


def commit(piece: str, src: Path) -> None:
    img = Image.open(src).convert("RGBA")
    wp = WHITE_DIR / piece / "static.png"
    bp = BLACK_DIR / piece / "static.png"
    img.save(wp)
    recolor_to_black(img).save(bp)
    print(f"  white -> {wp.relative_to(ROOT)}")
    print(f"  black -> {bp.relative_to(ROOT)}")


def main():
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    client = load_client()
    print(f"PixelLab balance: {client.get_balance()}")

    results = {}
    for piece in PIECES.keys():
        if only and piece not in only:
            continue
        print(f"\n[{piece}] running candidates...")
        best_path, best = run_piece(client, piece)
        results[piece] = best

    # Commit + cleanup
    print("\nCommitting bests:")
    for piece, best in results.items():
        if best["score"] < 0.55:
            print(f"  [skip] {piece}: best score {best['score']:.3f} below "
                  f"threshold 0.55 — leaving master untouched")
            continue
        commit(piece, best["path"])

    # Remove the iteration directory only if every piece was committed
    # successfully — if any fell below threshold we keep candidates so
    # we can inspect what went wrong.
    all_committed = all(b["score"] >= 0.55 for b in results.values())
    if all_committed and ITER_ROOT.exists():
        shutil.rmtree(ITER_ROOT)
        print(f"\nremoved {ITER_ROOT.relative_to(ROOT)}")
    elif ITER_ROOT.exists():
        print(f"\n[kept] {ITER_ROOT.relative_to(ROOT)} (some pieces below threshold)")


if __name__ == "__main__":
    main()
