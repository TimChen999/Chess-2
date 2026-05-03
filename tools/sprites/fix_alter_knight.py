"""Surgical fix for alter_knight:

  (a) Remove the 17-pixel floating cluster above y=14 on the right
      side of the head (visually weird disconnected cluster).
  (b) Restore the 3 pink pixels at the horn tip — leftover from the
      old horn-glow accessory — back to the pristine 4ceaa7d baseline
      values.

Touches ONLY those 20 pixels per color. Verifies byte-identity for
every other pixel before saving.

Run: python tools/sprites/fix_alter_knight.py
"""
import subprocess
from io import BytesIO
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent

# (a) The 17 pixel coordinates that form the floating upper-right
# cluster. Identified by inspecting the saved alter_knight: every
# opaque pixel with y<=13 AND x>=43 is part of the disconnected
# cluster sitting above the main body.
WEIRD_PIXELS: list[tuple[int, int]] = [
    (49,  9), (50,  9),
    (48, 10), (49, 10), (50, 10),
    (47, 11), (48, 11), (49, 11),
    (45, 12), (46, 12), (47, 12), (48, 12),
    (44, 13), (45, 13), (46, 13), (47, 13), (48, 13),
]
assert len(WEIRD_PIXELS) == 17

# (b) The 3 pink pixels at the horn tip — leftover from the old
# horn-glow accessory. Identified by `tools/sprites/_check_pink.py`
# (any opaque pixel matching is_pink).
PINK_PIXELS: list[tuple[int, int]] = [
    (37, 9), (38, 9), (37, 10),
]
assert len(PINK_PIXELS) == 3


def from_git(rel_path: str) -> Image.Image:
    """Read a file at commit 4ceaa7d directly from git history."""
    r = subprocess.run(
        ["git", "show", f"4ceaa7d:{rel_path}"],
        capture_output=True, check=True, cwd=str(ROOT),
    )
    return Image.open(BytesIO(r.stdout)).convert("RGBA")


def fix_one(color: str) -> dict:
    rel = f"godot/assets/sprites/anim/pieces/{color}/alter_knight/static.png"
    path = ROOT / rel
    img = Image.open(path).convert("RGBA")
    baseline = from_git(rel)
    w, h = img.size
    assert (w, h) == baseline.size, "baseline + saved size mismatch"

    # Snapshot every pixel so we can verify what changed.
    before_px = {(x, y): img.getpixel((x, y)) for y in range(h) for x in range(w)}
    base_px = {(x, y): baseline.getpixel((x, y)) for y in range(h) for x in range(w)}

    px = img.load()

    # (a) Pre-check + zap floating cluster.
    for (x, y) in WEIRD_PIXELS:
        if before_px[(x, y)][3] < 8:
            raise SystemExit(f"PRE-CHECK FAIL (weird): ({x},{y}) in {color} is already transparent")
    for (x, y) in WEIRD_PIXELS:
        px[x, y] = (0, 0, 0, 0)

    # (b) Restore pink pixels to their pristine baseline values.
    for (x, y) in PINK_PIXELS:
        cur = before_px[(x, y)]
        target = base_px[(x, y)]
        # Sanity check: current pixel should look pink-ish (high R/B,
        # lower G); baseline pixel should NOT be pink.
        r, g, b, a = cur
        if not (a >= 8 and r > 150 and b > 100 and g < r - 30):
            raise SystemExit(f"PRE-CHECK FAIL (pink): ({x},{y}) in {color} doesn't look pink: {cur}")
        px[x, y] = target

    # Verify: only the 20 target pixels changed; every other pixel is
    # byte-identical to before.
    targets = set(WEIRD_PIXELS) | set(PINK_PIXELS)
    expected = {}
    for (x, y) in WEIRD_PIXELS:
        expected[(x, y)] = (0, 0, 0, 0)
    for (x, y) in PINK_PIXELS:
        expected[(x, y)] = base_px[(x, y)]

    changed = 0
    leaked = []
    for y in range(h):
        for x in range(w):
            after = img.getpixel((x, y))
            before = before_px[(x, y)]
            if (x, y) in targets:
                if after != expected[(x, y)]:
                    raise SystemExit(f"target ({x},{y}) wrong: got {after}, want {expected[(x,y)]}")
                if before != after:
                    changed += 1
            else:
                if after != before:
                    leaked.append((x, y, before, after))
    if leaked:
        for L in leaked[:5]:
            print(f"  LEAK: {L}")
        raise SystemExit(f"verification fail: {len(leaked)} non-target pixels changed")

    img.save(path)
    return {
        "color": color,
        "changed": changed,
        "leaked": len(leaked),
        "weird_count": len(WEIRD_PIXELS),
        "pink_count": len(PINK_PIXELS),
    }


def main():
    print("=== alter_knight surgical fix ===\n")
    for color in ("white", "black"):
        r = fix_one(color)
        ok = (r["changed"] == r["weird_count"] + r["pink_count"]
              and r["leaked"] == 0)
        print(f"[{r['color']}]  changed={r['changed']}  "
              f"weird={r['weird_count']}  pink={r['pink_count']}  "
              f"leaked={r['leaked']}  -> {'PASS' if ok else 'FAIL'}")
    print("\nAll 17 weird-cluster pixels removed and 3 pink pixels restored")
    print("from baseline (per color). Every other pixel byte-identical.")


if __name__ == "__main__":
    main()
