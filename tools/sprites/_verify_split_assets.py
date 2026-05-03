"""Verify all weapon-bearing piece sprite/animation files exist with
correct dimensions."""

from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent

PIECES = ['pawn', 'bishop', 'queen', 'king', 'bandit_pawn']
COLORS = ['white', 'black']
STATICS = ['static.png', 'body_static.png', 'weapon_static.png']
ANIMS = [('move', 6), ('attack', 6), ('hit', 3), ('death', 5)]
PREFIXES = ['', 'body_', 'weapon_']

ok = True
for piece in PIECES:
    for color in COLORS:
        d = ROOT / f"godot/assets/sprites/anim/pieces/{color}/{piece}"
        for name in STATICS:
            p = d / name
            if not p.exists():
                print(f"MISSING {p.relative_to(ROOT)}"); ok = False; continue
            sz = Image.open(p).size
            if sz != (64, 64):
                print(f"BAD {p.relative_to(ROOT)} size={sz}"); ok = False
        for anim, frames in ANIMS:
            for prefix in PREFIXES:
                p = d / f"{prefix}{anim}.png"
                if not p.exists():
                    print(f"MISSING {p.relative_to(ROOT)}"); ok = False; continue
                sz = Image.open(p).size
                if sz != (frames * 64, 64):
                    print(f"BAD {p.relative_to(ROOT)} size={sz} expected ({frames*64},64)"); ok = False
print("OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
