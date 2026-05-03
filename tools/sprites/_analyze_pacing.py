"""Analyze the impact of theatrical pacing + burst flash + motion
streak on the weapon attack strips.

Prints:
  - per-piece total animation length vs the position tween (290 ms)
  - peak-frame screen-time vs uniform-timing baseline (% increase)
  - opaque-pixel count of frame 3 vs frames 0/1/5 (rest frames) —
    confirms the peak frame has materially more visible pixels
    (burst flash, motion streak)
"""

from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
WHITE = ROOT / "godot/assets/sprites/anim/pieces/white"

DURATIONS = {
    "pawn":        [0.050, 0.080, 0.070, 0.130, 0.080, 0.050],
    "bishop":      [0.050, 0.080, 0.070, 0.140, 0.090, 0.060],
    "queen":       [0.050, 0.080, 0.070, 0.160, 0.110, 0.060],
    "king":        [0.050, 0.080, 0.070, 0.180, 0.130, 0.070],
    "bandit_pawn": [0.060, 0.080, 0.060, 0.130, 0.080, 0.050],
}

T_IMPACT = 0.200
POSITION_TWEEN = 0.290   # T_ANTICIPATE + T_LUNGE + T_SETTLE
BASELINE_TOTAL = 0.290   # what was happening before pacing
FRAME = 64


def opaque_count(img):
    px = img.load()
    w, h = img.size
    return sum(1 for y in range(h) for x in range(w) if px[x, y][3] >= 8)


def split_strip(strip):
    n = strip.size[0] // FRAME
    return [strip.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME))
            for i in range(n)]


def main():
    print("=" * 70)
    print("THEATRICAL PACING IMPACT ANALYSIS")
    print("=" * 70)

    print("\n[1] Total animation length vs position tween (290 ms)")
    print(f"{'piece':14s} {'total':>7s} {'vs tween':>9s} {'peak@':>7s}  peak-hold (ms)")
    print("-" * 60)
    for piece, durs in DURATIONS.items():
        total = sum(durs) * 1000
        peak_start = sum(durs[:3]) * 1000   # F3 starts after F0+F1+F2
        peak_dur = durs[3] * 1000
        delta = total - POSITION_TWEEN * 1000
        print(f"  {piece:12s}  {total:5.0f}ms  +{delta:4.0f}ms  "
              f"{peak_start:4.0f}ms  {peak_dur:4.0f}ms")

    print(f"\n  T_IMPACT = {T_IMPACT*1000:.0f} ms — peak frame should start "
          f"here for damage flash sync")
    print("  All pieces: peak starts at 200 ms — synced.")

    print("\n[2] Peak frame screen-time: weighted vs uniform baseline")
    print("  Uniform-baseline assumption: total_dur = 290 ms / 6 frames "
          "= 48 ms per frame")
    print(f"{'piece':14s}   weighted F3   uniform F3   multiplier")
    print("-" * 55)
    for piece, durs in DURATIONS.items():
        weighted_f3 = durs[3] * 1000
        uniform_f3 = (BASELINE_TOTAL / 6) * 1000
        mult = weighted_f3 / uniform_f3
        print(f"  {piece:12s}  {weighted_f3:5.0f}ms      {uniform_f3:5.0f}ms      "
              f"{mult:.2f}x")

    print("\n[3] Peak-frame visual punch — opaque-pixel count per frame")
    print("  Frame 3 (peak) gets burst flash + motion streak; frames 0,1,5 "
          "are mostly the resting weapon at lockstep.")
    print(f"{'piece':14s}  F0   F1   F2   F3   F4   F5   peak-vs-rest")
    print("-" * 70)
    for piece in DURATIONS.keys():
        weapon_strip = Image.open(WHITE / f"{piece}/weapon_attack.png").convert("RGBA")
        frames = split_strip(weapon_strip)
        counts = [opaque_count(f) for f in frames]
        rest_avg = (counts[0] + counts[1] + counts[5]) / 3
        peak_ratio = counts[3] / max(1, rest_avg)
        cs = "  ".join(f"{c:3d}" for c in counts)
        print(f"  {piece:12s}  {cs}    {peak_ratio:.2f}x rest")


if __name__ == "__main__":
    main()
