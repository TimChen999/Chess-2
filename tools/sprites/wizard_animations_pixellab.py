"""Wizards' Guild animations via PixelLab `animate_with_text`.

Generates move, attack, and move_jump (where applicable) using the new
wizard static as the `reference_image`. The static handles the
character description; the per-anim prompt provides the action.

We KEEP the procedural hit / death / attack_lunge from
wizard_animations.py — this script only writes move / attack /
move_jump. Run wizard_animations.py first, then this script overlays
the action animations.

Run: python tools/sprites/wizard_animations_pixellab.py
     python tools/sprites/wizard_animations_pixellab.py --only bishop king
     python tools/sprites/wizard_animations_pixellab.py --force
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pixellab
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"
CACHE_DIR = ROOT / "tools/sprites/_pixellab_cache"

FRAME = 64
ALPHA_THRESH = 8

# ---------------------------------------------------------------------------
# Per-piece descriptions + action prompts.
# ---------------------------------------------------------------------------

PIECE_DESCRIPTIONS = {
    "pawn": ("a chess pawn as an apprentice mage, with a small round "
             "head, two narrow green jacket panels on the sides, "
             "holding a small open spellbook at the chest, cream-white "
             "body"),
    "knight": ("a chess knight horse-head profile, with a deep blue "
               "saddle blanket bearing a silver runic glyph on its "
               "back, cream-white horse body"),
    "bishop": ("a chess bishop as a wizard, with a tall pointed cream-"
               "white mitre on top, a small gold star on the mitre "
               "face, holding a tall vertical wizard staff with a "
               "small gold orb on top alongside the body, a thin "
               "purple stole sash on the chest, cream-white body"),
    "rook": ("a stone chess rook tower as a mage tower, with a long "
             "crimson banner ribbon hanging vertically down one side, "
             "cream-white stone walls, dark battlements on top"),
    "queen": ("a chess queen as a high enchantress, with a tall "
              "pointed cream-white crown, holding a tall slender "
              "scepter with a teal gem at the side, a thin gold sash "
              "at the waist, cream-white body"),
    "king": ("a chess king as an archmage, with a single round gold "
             "orb-of-power on top of the head, a long flowing white "
             "beard hanging from the face, holding a tall slender "
             "scepter at the side, a gold sash on the lower body, "
             "cream-white body, no cross"),
    "bandit_pawn": ("a chess pawn as a hooded mage thief, with a "
                    "dark grey hooded cape draped over the shoulders, "
                    "holding a sword with a silver blade and crimson "
                    "grip vertically at the body"),
    "alter_knight": ("a chess knight as a unicorn — a horse head "
                     "profile with a long pointed horn, a deep blue "
                     "saddle blanket bearing a silver harness on its "
                     "back, cream-white horse body"),
    "assassin_bishop": ("a chess bishop as a battle-wizard, with a "
                        "tall pointed cream-white mitre, a small gold "
                        "star on the mitre face, a sword sheathed "
                        "vertically behind the body, a wide diagonal "
                        "crimson sash with a gold buckle across the "
                        "torso"),
}

# Per-piece action descriptions for each animation type.
# Each animation type has its own visual vocabulary.

ATTACKS = {
    "pawn": "casting a glowing spell from the open spellbook held in front of the chest",
    "knight": "rearing slightly and lunging the head forward to charge an enemy",
    "bishop": "swinging the tall wizard staff forward to cast a spell",
    "rook": "the crimson banner waving vigorously while the tower channels magic",
    "queen": "sweeping the scepter forward to cast an enchantment",
    "king": "raising and swinging the scepter forward to channel arcane power",
    "bandit_pawn": "stabbing the sword forward in a quick attack thrust",
    "alter_knight": "lowering the head to charge with the horn pointed forward",
    "assassin_bishop": "drawing the sword and slashing forward in a battle strike",
}

MOVES = {
    p: "floating gently upward and back down, not walking, magical hover"
    for p in PIECE_DESCRIPTIONS
}
# Knight + alter_knight literally walk/canter as horses
MOVES["knight"] = "trotting forward, the horse body bobbing slightly"
MOVES["alter_knight"] = "trotting forward, the unicorn body bobbing slightly"

JUMPS = {
    "knight": "leaping forward in an arc, the horse body airborne mid-jump",
    "alter_knight": "leaping forward in an arc, the unicorn body airborne mid-jump",
}

# Doc target frame counts. PixelLab's animate_with_text caps output
# around 4 frames in practice — we pad up to the doc target by
# repeating the first frame at the start and the last frame at the
# end so the timing matches what Godot is configured for.
ANIM_FRAMES = {"move": 6, "attack": 6, "move_jump": 7}
PIXELLAB_REQUEST_FRAMES = 4   # actual API request
ANIM_PIECES = {
    "move": list(PIECE_DESCRIPTIONS.keys()),
    "attack": list(PIECE_DESCRIPTIONS.keys()),
    "move_jump": ["knight", "alter_knight"],
}


# ---------------------------------------------------------------------------
# CLIENT
# ---------------------------------------------------------------------------

def load_client():
    load_dotenv(ROOT / ".env")
    secret = os.environ.get("PIXELLAB_SECRET") or os.environ.get("PIXELLAB_API_KEY")
    if not secret:
        sys.exit("error: PIXELLAB_API_KEY missing from .env")
    return pixellab.Client(secret=secret)


def cache_path(piece: str, color: str, anim: str, seed: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{piece}_{color}_anim_{anim}_v2_seed{seed}.png"


def call_animate(client, piece, color, anim, ref_img, action, n_frames,
                 seed, force):
    cp = cache_path(piece, color, anim, seed)
    if cp.exists() and not force:
        print(f"   [cache] {cp.name}")
        return Image.open(cp).convert("RGBA")
    desc = PIECE_DESCRIPTIONS[piece]
    print(f"   [pixellab] {piece} {color} {anim} seed={seed}")
    resp = client.animate_with_text(
        image_size={"width": FRAME, "height": FRAME},
        description=desc,
        action=action,
        reference_image=ref_img,
        view="side",
        direction="east",
        negative_description=("different head shape, different mitre, "
                              "second character, deformed body, distorted, "
                              "off-model"),
        n_frames=n_frames,
        text_guidance_scale=8.0,
        image_guidance_scale=8.0,
        seed=seed,
    )
    # Response has `.images` — list of frame images.
    frames = []
    for fi in resp.images:
        frames.append(fi.pil_image().convert("RGBA"))
    if len(frames) != n_frames:
        print(f"   [warn] got {len(frames)} frames, expected {n_frames}")
    # Composite horizontally into one strip.
    strip = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        if f.size != (FRAME, FRAME):
            f = f.resize((FRAME, FRAME), Image.NEAREST)
        strip.paste(f, (i * FRAME, 0), f)
    strip.save(cp)
    return strip


# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------

def process_piece_anim(client, piece: str, anim: str, force: bool) -> dict:
    if piece not in ANIM_PIECES[anim]:
        return {"piece": piece, "anim": anim, "status": "skip"}
    if anim == "attack":
        action = ATTACKS[piece]
    elif anim == "move":
        action = MOVES[piece]
    elif anim == "move_jump":
        action = JUMPS[piece]
    target_frames = ANIM_FRAMES[anim]
    n_frames = PIXELLAB_REQUEST_FRAMES

    saved = []
    for color, src_dir in (("white", WHITE_DIR), ("black", BLACK_DIR)):
        static_path = src_dir / piece / "static.png"
        if not static_path.exists():
            continue
        ref = Image.open(static_path).convert("RGBA")
        seed = 7000  # deterministic per piece+color via the action prompt
        try:
            strip = call_animate(client, piece, color, anim, ref, action,
                                 n_frames, seed, force)
        except Exception as e:
            print(f"   [error] {piece}/{color}/{anim}: {e}")
            continue
        # Pad the strip to target_frames by repeating first and last
        # frames symmetrically so the action is in the middle.
        cur_frames = strip.size[0] // FRAME
        if cur_frames < target_frames:
            extra = target_frames - cur_frames
            front = extra // 2
            back = extra - front
            padded = Image.new("RGBA", (FRAME * target_frames, FRAME),
                               (0, 0, 0, 0))
            first = strip.crop((0, 0, FRAME, FRAME))
            last = strip.crop((FRAME * (cur_frames - 1), 0,
                               FRAME * cur_frames, FRAME))
            for i in range(front):
                padded.paste(first, (i * FRAME, 0), first)
            padded.paste(strip, (front * FRAME, 0), strip)
            for i in range(back):
                padded.paste(last,
                             ((front + cur_frames + i) * FRAME, 0), last)
            strip = padded
        out_path = src_dir / piece / f"{anim}.png"
        strip.save(out_path)
        saved.append(color)
    return {"piece": piece, "anim": anim, "status": "ok", "saved": saved}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--anims", nargs="*", default=["move", "attack", "move_jump"])
    args = ap.parse_args()

    client = load_client()
    print(f"[pixellab] balance: {client.get_balance()}")

    only = set(args.only) if args.only else None
    results = []
    for anim in args.anims:
        for piece in PIECE_DESCRIPTIONS.keys():
            if only and piece not in only:
                continue
            r = process_piece_anim(client, piece, anim, args.force)
            results.append(r)

    print("\n=== SUMMARY ===")
    for r in results:
        if r["status"] == "skip":
            continue
        if r["status"] == "ok":
            colors = ", ".join(r["saved"])
            print(f"  {r['piece']:18s} {r['anim']:10s} OK ({colors})")
        else:
            print(f"  {r['piece']:18s} {r['anim']:10s} {r['status']}")


if __name__ == "__main__":
    main()
