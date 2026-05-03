"""Surgically derive body_static.png + weapon_static.png for every
weapon-bearing piece, preserving every non-weapon pixel from
aeaa0be:static.png byte-for-byte.

Why this approach (not running wizard_statics.py to regenerate):
    The wizard_statics pipeline has evolved since aeaa0be (newer mitre
    cross prompt, body-texture-pass tweaks, accessory snap thresholds,
    etc.) so a fresh run produces SUBSTANTIALLY different pixels even
    in regions unrelated to the staff/sword. Per the user's contract,
    the new sprites must equal aeaa0be everywhere outside the weapon's
    footprint. So we use aeaa0be:static.png as the ground truth and
    only modify pixels under the weapon's mask.

Outputs per piece × team:
    static.png         <- restored from aeaa0be (UI consumer source-of-truth)
    weapon_static.png  <- weapon accessory composited onto transparent canvas
    body_static.png    <- aeaa0be minus weapon-mask pixels:
                          - if weapon overlaps body silhouette: fill from
                            nearest non-mask pixel in the same row (preserves
                            local body texture cleanly)
                          - else: erase to transparent

Per-piece "weapon overlaps body" flag:
    pawn          spellbook held at center body              -> True
    bishop        staff held at right side, outside body     -> False
    queen         scepter at right side, outside body        -> False
    king          scepter at right side, outside body        -> False
    bandit_pawn   sword held vertical at center body         -> True

Run: python tools/sprites/_split_weapons_from_aeaa0be.py
"""

from pathlib import Path
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wizard_statics import (  # type: ignore
    ALPHA_THRESH,
    PIECES_ACCESSORIES,
    alpha_mask,
    composite_accessory,
    generate_accessory,
    load_client,
    normalize_outline_per_team,
    snap_outline,
)

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"

# Per-piece — does the weapon's footprint overlap the body silhouette?
# When True, erased weapon pixels need to be filled with body color (not
# left transparent), otherwise the body has holes.
WEAPON_OVERLAPS_BODY = {
    "pawn": True,
    "bishop": False,
    "queen": False,
    "king": False,
    "bandit_pawn": True,
    # Arc-only — weapon_static is transparent so the lockstep mask is
    # always empty and overlaps doesn't matter, but include for safety.
    "assassin_bishop": False,
}

# Pieces with a weapon BAKED INTO THE BASELINE silhouette (not a
# weapon=True accessory). The weapon static itself can't be cleanly
# extracted from the baseline, but we still want a swing-arc overlay
# during attack frames. For these pieces we generate:
#   body_static.png   = byte-for-byte copy of aeaa0be:static.png
#                       (no subtraction — weapon stays in the body)
#   weapon_static.png = fully transparent 64x64 canvas
# The arc-only weapon attack strip is then painted onto the empty
# weapon canvas by _split_anim_weapons.py, layered on top of the
# unchanged body in Godot. The body keeps its baked-in sword.
ARC_ONLY_PIECES = ["assassin_bishop"]


def restore_aeaa0be_static(piece: str, color: str, dst: Path):
    src = f"aeaa0be:godot/assets/sprites/anim/pieces/{color}/{piece}/static.png"
    with open(dst, "wb") as f:
        subprocess.run(
            ["git", "show", src],
            check=True,
            stdout=f,
            cwd=ROOT,
        )


def build_weapon_static(client, piece: str, weapon_acc, color: str) -> Image.Image:
    """Composite the weapon accessory onto a transparent 64x64 canvas
    using the same pipeline wizard_statics uses (snap_outline + resize +
    anchor + per-team outline color)."""
    seeds = [6000, 6017, 6034, 6051]
    weapon_img = None
    for seed in seeds:
        img = generate_accessory(client, piece, weapon_acc, seed,
                                  force=False)
        if img is not None:
            weapon_img = snap_outline(img)
            break
    assert weapon_img is not None, f"could not load {piece} {weapon_acc.id}"

    canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    canvas = composite_accessory(
        canvas, weapon_img,
        anchor_xy=weapon_acc.anchor,
        target_w=weapon_acc.target_w,
        target_h=weapon_acc.target_h,
        symmetric=weapon_acc.symmetric,
        full_sym=weapon_acc.full_sym,
    )
    canvas = normalize_outline_per_team(canvas, color)
    return canvas


def fill_from_nearest_in_row(full_img: Image.Image, weapon_mask: list,
                              x: int, y: int) -> tuple:
    """For an in-mask pixel, sample the closest non-mask opaque pixel in
    the same row. Used for weapons that sit ON the body (pawn book,
    bandit sword) — the row neighbors are body interior."""
    fp = full_img.load()
    w = full_img.size[0]
    for d in range(1, w):
        for x2 in (x - d, x + d):
            if not (0 <= x2 < w):
                continue
            if weapon_mask[x2][y]:
                continue
            c = fp[x2, y]
            if c[3] >= ALPHA_THRESH:
                return c
    return (0, 0, 0, 0)


def split_piece(client, piece: str) -> dict:
    accs = PIECES_ACCESSORIES[piece]
    weapon_acc = next((a for a in accs if a.weapon), None)
    if weapon_acc is None:
        return {"piece": piece, "status": "no_weapon"}

    overlaps = WEAPON_OVERLAPS_BODY.get(piece, False)
    print(f"\n=== {piece} (weapon={weapon_acc.id}, overlaps_body={overlaps}) ===")

    counts = {}
    for color, src_dir in (("white", WHITE_DIR), ("black", BLACK_DIR)):
        static_path = src_dir / piece / "static.png"
        body_path = src_dir / piece / "body_static.png"
        weapon_path = src_dir / piece / "weapon_static.png"

        # 1. Restore aeaa0be:static.png to disk.
        restore_aeaa0be_static(piece, color, static_path)

        # 2. Build weapon_static.png.
        weapon_canvas = build_weapon_static(client, piece, weapon_acc, color)
        weapon_canvas.save(weapon_path)

        # 3. Build body_static.png by erasing weapon mask pixels.
        full = Image.open(static_path).convert("RGBA")
        body = full.copy()
        bp = body.load()
        wm = alpha_mask(weapon_canvas)

        cleared = 0
        filled_from_row = 0
        for y in range(64):
            for x in range(64):
                if not wm[x][y]:
                    continue
                cleared += 1
                if overlaps:
                    bp[x, y] = fill_from_nearest_in_row(full, wm, x, y)
                    if bp[x, y][3] >= ALPHA_THRESH:
                        filled_from_row += 1
                else:
                    bp[x, y] = (0, 0, 0, 0)

        body.save(body_path)

        # 4. Verify body_static.png matches static.png everywhere weapon
        #    mask is OFF. (Pixels INSIDE weapon mask are allowed to differ
        #    — that's the whole point of the split.)
        body_check = Image.open(body_path).convert("RGBA")
        full_check = Image.open(static_path).convert("RGBA")
        bc = body_check.load()
        fc = full_check.load()
        non_weapon_diffs = 0
        for y in range(64):
            for x in range(64):
                if wm[x][y]:
                    continue
                if bc[x, y] != fc[x, y]:
                    non_weapon_diffs += 1

        counts[color] = {
            "cleared": cleared,
            "filled_from_row": filled_from_row,
            "non_weapon_diffs": non_weapon_diffs,
        }
        status = "PASS" if non_weapon_diffs == 0 else "FAIL"
        fill_str = (f"  filled-from-row={filled_from_row}" if overlaps
                    else "  (erased to transparent)")
        print(f"  {color:5s}  cleared={cleared}{fill_str}  "
              f"non-weapon-diffs={non_weapon_diffs}  [{status}]")

    return {"piece": piece, "status": "ok", "counts": counts}


def split_arc_only(piece: str) -> dict:
    """Generate body_static.png + transparent weapon_static.png for a
    piece whose weapon is baked into the baseline silhouette (e.g.,
    assassin_bishop's sword). No accessory subtraction; the body keeps
    its original silhouette intact."""
    print(f"\n=== {piece} (arc-only — weapon baked into baseline) ===")
    for color, src_dir in (("white", WHITE_DIR), ("black", BLACK_DIR)):
        static_path = src_dir / piece / "static.png"
        body_path = src_dir / piece / "body_static.png"
        weapon_path = src_dir / piece / "weapon_static.png"
        # Restore canonical aeaa0be:static.png.
        restore_aeaa0be_static(piece, color, static_path)
        # body_static = byte-for-byte copy of static.png.
        Image.open(static_path).convert("RGBA").save(body_path)
        # weapon_static = fully transparent canvas.
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(weapon_path)
        print(f"  {color:5s}  body=copy of static  weapon=transparent canvas")
    return {"piece": piece, "status": "ok"}


def main():
    client = load_client()
    print(f"[pixellab] balance: {client.get_balance()}")

    results = []
    pieces_with_weapons = [p for p, accs in PIECES_ACCESSORIES.items()
                            if any(a.weapon for a in accs)]
    print(f"weapon-bearing pieces: {pieces_with_weapons}")
    print(f"arc-only pieces: {ARC_ONLY_PIECES}")
    for piece in pieces_with_weapons:
        results.append(split_piece(client, piece))
    for piece in ARC_ONLY_PIECES:
        results.append(split_arc_only(piece))

    print("\n=== SUMMARY ===")
    fail = 0
    for r in results:
        if r["status"] != "ok":
            print(f"  {r['piece']:14s}  {r['status']}")
            continue
        if "counts" not in r:
            # Arc-only piece — no subtraction stats to report.
            print(f"  {r['piece']:14s}  arc-only (body=copy, weapon=transparent)")
            continue
        for color, c in r["counts"].items():
            tag = "PASS" if c["non_weapon_diffs"] == 0 else "FAIL"
            print(f"  {r['piece']:14s} {color:5s}  cleared={c['cleared']:3d}  "
                  f"filled={c['filled_from_row']:3d}  "
                  f"non-weapon-diffs={c['non_weapon_diffs']}  [{tag}]")
            if c["non_weapon_diffs"] != 0:
                fail += 1
    if fail:
        print(f"\nFAIL: {fail} colors had pixel diffs outside weapon mask")
        sys.exit(1)
    else:
        print("\nALL PASS — every body_static.png matches aeaa0be:static.png "
              "everywhere outside its weapon's mask")


if __name__ == "__main__":
    main()
