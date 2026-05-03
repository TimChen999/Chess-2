"""Generate the staff cast-magic FLASH sprite strip per piece per color.

For each frame of weapon_attack.png we find the staff's tip (top opaque
pixel), then paint a multi-pointed star burst onto a 96x96 flash canvas
at that tip's position (offset by +16 because the flash canvas extends
16 px beyond the 64x64 weapon canvas in each direction so the burst
can't clip).

The burst progression matches the reference 8-frame spark anim, condensed
to our 6-frame attack:
    F0  invisible (rest)
    F1  tiny pre-spark forming
    F2  small charged spark
    F3  PEAK multi-pointed star burst (full rays, white core, gem-tinted tips)
    F4  collapsing burst (shorter rays + bright ring outline)
    F5  small fading ring outline

Output: pieces/<color>/<piece>/weapon_flash_attack.png  (576x96 strip)

In Godot the flash strip is composited as a separate TextureRect overlay
above the Weapon layer, with its top-left offset by (-16, -16) relative
to the piece's anchor — so the per-frame burst lines up exactly with
the staff tip in the underlying weapon_attack frame.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

WHITE_DIR = ROOT / "godot/assets/sprites/anim/pieces/white"
BLACK_DIR = ROOT / "godot/assets/sprites/anim/pieces/black"

FRAME_W = 64                # source weapon strip frame size
CANVAS = 96                  # flash sprite frame size (16 px buffer)
BUFFER = (CANVAS - FRAME_W) // 2  # = 16 — offset from weapon coords to flash coords

# Per-piece gem color used for the ray tips. Core is always near-white.
GEM_COLOR = {
    "bishop": (255, 215, 100),  # gold
    "king":   (200, 130, 230),  # purple
    "queen":  (130, 230, 220),  # teal
}
WHITE = (255, 252, 245)        # core color — slight warm tint, reads as "light"


def find_top_opaque(img: Image.Image) -> tuple[int, int] | None:
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if px[x, y][3] >= 16:
                return (x, y)
    return None


def blend_px(canvas: Image.Image, x: int, y: int,
             color: tuple[int, int, int], alpha: int) -> None:
    """Alpha-composite a single pixel onto canvas."""
    if alpha <= 0:
        return
    w, h = canvas.size
    if not (0 <= x < w and 0 <= y < h):
        return
    p = canvas.load()
    er, eg, eb, ea = p[x, y]
    sa = alpha / 255.0
    inv = 1.0 - sa
    nr = int(color[0] * sa + er * inv)
    ng = int(color[1] * sa + eg * inv)
    nb = int(color[2] * sa + eb * inv)
    na = max(ea, alpha)
    p[x, y] = (nr, ng, nb, na)


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int],
               t: float) -> tuple[int, int, int]:
    return (
        int(a[0] * (1 - t) + b[0] * t),
        int(a[1] * (1 - t) + b[1] * t),
        int(a[2] * (1 - t) + b[2] * t),
    )


def draw_ray(canvas: Image.Image, cx: int, cy: int,
             dir_x: int, dir_y: int, length: int,
             core_color: tuple[int, int, int],
             tip_color: tuple[int, int, int],
             max_alpha: int = 255) -> None:
    """Draw a 1-px-wide ray from (cx, cy) outward in direction (dir_x, dir_y)
    for `length` pixels. Color tapers from core_color (near pivot) to
    tip_color (far end). Alpha fades to ~0 at the tip."""
    if length <= 0:
        return
    for d in range(1, length + 1):
        t = d / length
        # Color tapers: white at center → tinted at outer 60% → fade
        col_t = min(1.0, t * 1.6)
        color = lerp_color(core_color, tip_color, col_t)
        # Alpha tapers: full near center, drops to ~0 at tip with quadratic falloff
        alpha = int(max_alpha * (1.0 - t * t * 0.95))
        blend_px(canvas, cx + dir_x * d, cy + dir_y * d, color, alpha)


def draw_core(canvas: Image.Image, cx: int, cy: int,
              radius: int, color: tuple[int, int, int],
              max_alpha: int = 255) -> None:
    """Bright filled circle at (cx, cy) with radius `radius`."""
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d = math.sqrt(dx * dx + dy * dy)
            if d > radius + 0.4:
                continue
            # Soft falloff at the very edge (1-pixel band)
            t = max(0.0, min(1.0, (radius + 0.4 - d) / 1.4))
            blend_px(canvas, cx + dx, cy + dy, color, int(max_alpha * t))


def draw_ring(canvas: Image.Image, cx: int, cy: int,
              radius: float, thickness: float,
              color: tuple[int, int, int],
              max_alpha: int = 200) -> None:
    """1-2 px ring outline at given radius. Used for collapsing-burst
    and fading-ring frames."""
    half = thickness / 2.0
    R = int(radius + half + 1)
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            d = math.sqrt(dx * dx + dy * dy)
            err = abs(d - radius)
            if err > half:
                continue
            t = 1.0 - err / half if half > 0 else 1.0
            blend_px(canvas, cx + dx, cy + dy, color, int(max_alpha * t))


def paint_burst(canvas: Image.Image, cx: int, cy: int,
                profile: dict, gem: tuple[int, int, int]) -> None:
    """Paint one frame of the flash burst, centered at (cx, cy).

    Profile keys:
        type    'spark'  | 'burst' | 'ring_burst' | 'ring'
        ...  type-specific params
    """
    kind = profile["type"]
    if kind == "spark":
        # Tiny pre-spark — small bright dot + faint diagonal pixels
        intensity = profile.get("intensity", 0.4)
        a_main = int(255 * intensity)
        a_off = int(160 * intensity)
        blend_px(canvas, cx, cy, WHITE, a_main)
        for off in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            blend_px(canvas, cx + off[0], cy + off[1], WHITE, a_off)
    elif kind == "burst":
        # Multi-pointed star burst.
        core_r: int = profile.get("core_size", 1)
        card_len: int = profile["card_len"]
        diag_len: int = profile["diag_len"]
        max_a: int = profile.get("alpha", 255)
        # Bright white core
        draw_core(canvas, cx, cy, core_r, WHITE, max_a)
        # 4 cardinal rays
        for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            draw_ray(canvas, cx, cy, d[0], d[1], card_len, WHITE, gem, max_a)
        # 4 diagonal rays (shorter)
        for d in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            draw_ray(canvas, cx, cy, d[0], d[1], diag_len, WHITE, gem, max_a)
    elif kind == "ring_burst":
        # Collapsing burst — short rays + a bright ring outline
        max_a: int = profile.get("alpha", 200)
        # Short cardinal rays
        ray_len = profile.get("ray_len", 4)
        for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            draw_ray(canvas, cx, cy, d[0], d[1], ray_len, WHITE, gem, max_a)
        for d in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            draw_ray(canvas, cx, cy, d[0], d[1], max(1, ray_len - 2), WHITE, gem, max_a)
        # Bright ring at outer radius
        draw_ring(canvas, cx, cy,
                  radius=profile.get("ring_radius", 8),
                  thickness=2.0,
                  color=lerp_color(WHITE, gem, 0.4),
                  max_alpha=max_a)
    elif kind == "ring":
        # Faint ring outline (final frame).
        draw_ring(canvas, cx, cy,
                  radius=profile.get("radius", 4),
                  thickness=profile.get("thickness", 1.0),
                  color=lerp_color(WHITE, gem, 0.5),
                  max_alpha=profile.get("alpha", 110))


# Frame profiles — applied per attack frame. None = transparent frame.
# Lengths are in pixels on the 96x96 flash canvas.
FRAME_PROFILES: list = [
    None,                                                               # F0 rest — no flash
    {"type": "spark", "intensity": 0.45},                                # F1 tiny pre-spark
    {"type": "burst", "core_size": 1, "card_len": 6,
     "diag_len": 3, "alpha": 220},                                      # F2 small charging burst
    {"type": "burst", "core_size": 2, "card_len": 18,
     "diag_len": 12, "alpha": 255},                                     # F3 PEAK burst
    {"type": "ring_burst", "ray_len": 5, "ring_radius": 11,
     "alpha": 215},                                                     # F4 collapsing
    {"type": "ring", "radius": 6, "thickness": 1.5, "alpha": 130},      # F5 fading ring
]


def render_for_piece_color(piece: str, color: str) -> dict:
    src_dir = WHITE_DIR if color == "white" else BLACK_DIR
    pdir = src_dir / piece
    weapon_path = pdir / "weapon_attack.png"
    out_path = pdir / "weapon_flash_attack.png"
    if not weapon_path.exists():
        return {"piece": piece, "color": color, "status": "skip"}
    weapon = Image.open(weapon_path).convert("RGBA")
    n = weapon.size[0] // FRAME_W
    if weapon.size != (FRAME_W * n, FRAME_W):
        return {"piece": piece, "color": color, "status": "size_mismatch"}

    flash_strip = Image.new("RGBA", (CANVAS * n, CANVAS), (0, 0, 0, 0))
    gem = GEM_COLOR[piece]

    for i in range(n):
        if i >= len(FRAME_PROFILES) or FRAME_PROFILES[i] is None:
            continue
        weapon_frame = weapon.crop((i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_W))
        tip = find_top_opaque(weapon_frame)
        if tip is None:
            continue
        # Map tip position (in 64x64 weapon coords) to 96x96 flash coords
        cx = tip[0] + BUFFER
        cy = tip[1] + BUFFER
        flash_frame = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        paint_burst(flash_frame, cx, cy, FRAME_PROFILES[i], gem)
        flash_strip.paste(flash_frame, (i * CANVAS, 0), flash_frame)

    flash_strip.save(out_path)
    return {"piece": piece, "color": color, "status": "ok",
            "n_frames": n, "out": out_path.relative_to(ROOT).as_posix()}


def main() -> None:
    pieces = ["bishop", "king", "queen"]
    print(f"{'piece':10s} {'color':5s} {'frames':6s} status")
    print("-" * 50)
    for piece in pieces:
        for color in ("white", "black"):
            r = render_for_piece_color(piece, color)
            n = r.get("n_frames", "-")
            print(f"  {piece:10s} {color:5s} {str(n):6s} {r['status']}"
                  + (f"  -> {r['out']}" if r["status"] == "ok" else ""))


if __name__ == "__main__":
    main()
