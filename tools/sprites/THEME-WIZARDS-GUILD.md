# Wizards' Guild Theme — Implementation Guide

This is a self-contained guide for a fresh Claude Code session to take
the existing 9-piece chess set and reskin it as a "Wizards' Guild"
theme, then produce matching animations and three magical-ability VFX.

The base sprites are at `godot/assets/sprites/anim/pieces/<color>/<piece>/static.png`
in a clean flat-cream + outline + right-edge-shadow palette (suite
palette defined in [restyle.py](restyle.py)). They are the **baseline
canvas** — accessories are generated separately and composited on top.

> **Approach evolution recorded here**: this doc has been rewritten
> several times during implementation. The earlier inpaint-only and
> regenerate-from-scratch approaches were both abandoned. The shipped
> pipeline is **layered compositing of isolated accessory PNGs** — see
> §3 for details and §9 for a list of approaches that didn't work.
>
> **NEW — two-sprite layered animation** (§5d): for pieces with a
> distinguishable weapon (bishop staff, bandit_pawn sword, queen/king
> scepter, assassin_bishop sword), the weapon is rendered as a *separate
> overlay sprite* on top of a body-only sprite, so the weapon can swing
> / raise / glow independently of the body during attacks. Statics still
> ship the full composite for UI icons; animated rendering uses the
> body-only + weapon-only pair. Bishop is the prototype implementation.

---

## 1. Prerequisites

**PixelLab** access via the Python SDK (`pip install pixellab`). We
read `PIXELLAB_API_KEY` from the project root `.env`. The MCP entry in
`.mcp.json` is wired up but `enabledMcpjsonServers` adoption is the
user's call — the SDK is what the scripts use.

**Existing utilities you will reuse** (all in `tools/sprites/`):

| Script | Purpose |
|---|---|
| [wizard_statics.py](wizard_statics.py) | the static-sprite pipeline — generates per-piece accessory PNGs via PixelLab pixflux, composites them onto the cream baseline. **The canonical static generator.** |
| [wizard_animations.py](wizard_animations.py) | procedural animation generator — applies per-frame translate / lean / squash transforms to the wizard static. **The canonical body animator.** Loads `static.png` (full composite) and produces composite anim strips. When a piece has a body-only static (`body_static.png`), it ALSO produces body-only strips (`body_<anim>.png`) for the layered-rendering path. |
| [wizard_weapon_animations.py](wizard_weapon_animations.py) | weapon-overlay animation generator — for pieces declared as weapon-bearing, loads `weapon_static.png`, applies the SAME per-frame body POSES (so the weapon stays anchored to the body), then layers per-piece, per-anim *extra* motion (e.g. bishop staff raise + tip glow during attack). Outputs `weapon_<anim>.png`. |
| [wizard_animations_pixellab.py](wizard_animations_pixellab.py) | PixelLab `animate_with_text` attempt. Kept for reference only — see §9 for why we don't ship it. |
| [wizard_vfx.py](wizard_vfx.py) | VFX generator — generates atomic VFX images via PixelLab pixflux, composites them at progressive Y positions to produce visible falling motion. |
| [restyle.py](restyle.py) | silhouette-preserving repaint into the suite palette — used historically; not needed in the layered pipeline. |
| [gen_sprites.py](gen_sprites.py) | provides the original `recolor_to_black()` (brightness-flatten). The wizard pipeline ships its own `wizard_recolor_to_black()` inside `wizard_statics.py` that preserves accent colors so the black team's wizard outfits stay themed. |

**Suite palette** — the four base colors every body silhouette uses:

```python
OUTLINE   = (40, 40, 50, 255)     # 1-pixel dark navy outline
FILL      = (250, 248, 242, 255)  # body interior cream
SHADOW    = (210, 208, 200, 255)  # right-edge shadow band
HIGHLIGHT = (130, 128, 138, 255)  # secondary mid-grey
```

**Black-team body palette** — derived from the white baseline at
runtime via `wizard_recolor_to_black()` so the two teams share an
identical 4-color body palette regardless of what colors the on-disk
black sprite happens to have:

```python
BLACK_OUTLINE = (40, 40, 40, 255)
BLACK_FILL    = (64, 64, 70, 255)
BLACK_SHADOW  = (50, 50, 56, 255)
BLACK_HILIGHT = (102, 102, 112, 255)
```

**Accent palette** — saturated colors usable for accessory items only.
Each piece picks 1–2 accent colors that fit its role; the set spans
the rainbow so pieces read distinctly.

```python
# Cool / arcane
BLUE          = ( 76, 124, 196, 255)
BLUE_SHADOW   = ( 42,  78, 138, 255)
TEAL          = ( 70, 168, 162, 255)
TEAL_SHADOW   = ( 38, 110, 108, 255)

# Warm / fire / blood
CRIMSON       = (190,  60,  72, 255)
CRIMSON_SHADOW= (132,  32,  44, 255)

# Nature / apprentice
GREEN         = ( 96, 156,  78, 255)
GREEN_SHADOW  = ( 56, 100,  44, 255)

# Royal / archmage
PURPLE        = (126,  91, 176, 255)
PURPLE_SHADOW = ( 74,  52, 117, 255)

# Metals / glow
GOLD          = (217, 178,  60, 255)
GOLD_SHADOW   = (156, 122,  32, 255)
SILVER        = (192, 196, 210, 255)
PINK_GLOW     = (228, 122, 200, 255)
```

---

## 2. Theme overview

Each piece is a member of a wizards' guild. The change is **on the
body and around it** (held items + a small banner / saddle / sash),
**not on the head**. Heads stay cream-white with their original
silhouette.

### 2.1 What stays untouched

- **Silhouette**: the existing alpha mask of every piece is preserved
  exactly. The only exception is the king, whose cross-on-orb
  structure is intentionally pre-cleared so the orb-of-power can sit
  on top.
- **Head region**: cream-white interior + dark outline stay as-is.
  Don't add hats, mitre bands, or recolor crowns.
- **Body interior**: cream-white (FILL/SHADOW) by default. Accent
  colors land only inside the per-piece accent zones from
  `wizard_statics.py`.

### 2.2 Per-piece accessories — what's actually shipped

| piece | role | accessories (composited PNGs) | accent colors |
|---|---|---|---|
| **pawn** | apprentice mage | two narrow green jacket panels at the sides (open-front, leaving cream body visible in the middle), small open spellbook held at chest | GREEN + GOLD |
| **knight** | arcane cavalry | blue saddle blanket on the horse's back with a small silver runic glyph | BLUE + SILVER |
| **bishop** | wizard | gold five-pointed star on the mitre face (replaces the original cross), tall vertical wizard staff with a small gold orb on top alongside the body, thin purple sash at the waist | GOLD + PURPLE |
| **rook** | mage tower | crimson banner ribbon hanging vertically down one side of the tower (extends past the silhouette) | CRIMSON + GOLD |
| **queen** | high enchantress | tall slender ornate scepter with a teal gem on top alongside the body, thin gold sash at the waist | TEAL + GOLD |
| **king** | archmage | gold orb-of-power on top of the head (cross is pre-cleared), tall slender ornate scepter with a purple gem alongside the body. **No beard.** | GOLD + PURPLE |
| **bandit_pawn** | hooded mage thief | dark grey hooded cape draped over the shoulders + a sword (silver blade, crimson grip). Rebased on the BASE PAWN baseline so the cape is purely an accessory, not part of the silhouette. | CRIMSON + SILVER |
| **alter_knight** | arcane unicorn | blue saddle blanket with a silver harness on the back. (No horn-tip glow — the pink-magenta accessory was unsightly and was removed.) | BLUE + SILVER |
| **assassin_bishop** | battle-wizard | stylized gold cross emblem on the mitre face, the existing sword stays (part of the baseline silhouette), thin crimson sash with a gold buckle across the body | CRIMSON + GOLD |

**Rebase rules** — declared in `PIECE_BASELINE_OVERRIDE`:
- `bandit_pawn` uses the base `pawn` baseline (so its cape is an
  accessory rather than part of the silhouette).

**Pre-clear rules** — declared in `PIECE_PRE_CLEAR`:
- `bishop` and `assassin_bishop` clear the existing cross on the
  mitre interior so a fresh emblem can sit cleanly.
- `king` clears the entire cross-on-orb structure on top (every row
  above the first row that's ≥ 14 px wide — the body row).

### 2.3 Visual budget at 64×64

- **Body accent items**: 1–3 per piece, total ~30–80 px of accent
  color inside the body region. Cream interior should still cover the
  majority of the body.
- **Held items extending outside silhouette**: ≤ ~50 px of new
  silhouette outside the original (a thin staff / scepter is fine; a
  full second body is not).
- **Head detail**: ≤ ~12 px of accent inside the head region (the
  bishop's mitre star and assassin's mitre cross fit; the king's orb
  replaces the entire cross structure and so is allowed to be larger).
- The dark navy OUTLINE on the body silhouette boundary is preserved
  exactly via `restamp_body_outline` (color-aware per team).

---

## 3. Static sprite pipeline

**The shipped approach: layered accessory compositing.** Each piece's
wizard items are generated as isolated transparent-background PNGs,
positioned via per-piece anchors, and alpha-composited onto the
baseline. The original silhouette is **never modified** (except king,
where the cross is pre-cleared). Body cream stays cream by
construction — accessories don't touch it.

This is the third approach we tried; the first two (whole-sprite
inpaint and regenerate-from-scratch with init_image) both failed —
see §9 for the post-mortem.

### 3.1 End-to-end flow per piece

For each piece, `wizard_statics.py` runs:

1. **Snapshot baselines** at `main()` start via
   `load_original_baselines()`. White baseline comes from disk
   (`white/<piece>/static.png`). Black baseline is **derived at
   runtime** by `wizard_recolor_to_black(white_baseline)` so both
   teams share an identical 4-color palette.
2. **Resolve baseline_piece** (e.g. `bandit_pawn` → `pawn`).
3. **Pre-clear** if listed in `PIECE_PRE_CLEAR`:
   - `bishop_cross`: erase non-cream interior pixels in the upper
     mitre rows (cross pixels) back to FILL.
   - `king_cross`: erase every row above the first row that's ≥ 14 px
     wide (i.e. the entire cross-on-orb structure on top). Use ≥ 14
     not "first wide-after-thin" — that earlier heuristic stopped at
     the bauble (~row 3) and left the cross stem behind.
4. **Body texture pass** (procedural, suite palette only): add a
   1-pixel HIGHLIGHT band on the upper-left silhouette edge and widen
   the right-edge SHADOW band by 1 px. Subtle sculptural depth, no
   accent colors.
5. **Generate each accessory** via `client.generate_image_pixflux`:
   - `description = "<accessory>, dark black outline, isolated single object, transparent background, pixel art at 64x64, no other objects"`
   - `negative_description = "chess piece, person, full body, hand, multiple objects, second <type>"`
   - `image_size = {"width": 64, "height": 64}`
   - `no_background = True`
   - `text_guidance_scale = 12.0`
   - `seed = <varied>` (try 6000, 6017, 6034, 6051 — accept the first
     candidate whose opaque bbox is in the right ballpark for the
     accessory's `target_w × target_h`)
   - **No `init_image`.** Let the prompt fully drive — we want a clean
     accessory, not a chess piece with the accessory glued on.
6. **Snap accessory outline**: every pixel with average brightness
   < 95 is snapped to the suite `OUTLINE = (40, 40, 50, 255)`. The
   threshold is intentionally loose (95, not 80) so dark-tinted
   outlines (e.g. dark navy ~`(45, 67, 99)` around a blue saddle
   blanket) get snapped instead of leaving boundary breaks.
7. **Resize + symmetrize + composite** per accessory in z-order:
   - Crop to opaque bbox.
   - Resize-by-nearest to `(target_w, target_h)`.
   - If `full_sym=True` (e.g. king's orb), pick the denser side of each
     row and mirror it to the other so the result is perfectly
     bilaterally symmetric. Without this the orb visibly leans right
     (the gold pattern in PixelLab's output is asymmetric).
   - If `symmetric=True` (legacy), just fill mirror-asymmetric holes.
   - Translate so the accessory's bbox center hits the per-accessory
     anchor on the 64×64 piece canvas.
   - `Image.alpha_composite` onto the running result.
8. **Restamp body outline** (`restamp_body_outline`): walk the
   BASELINE silhouette boundary and force every boundary pixel to the
   **team's** OUTLINE color. Accessory composites that painted over
   the boundary get the dark suite outline restored. Use OUTLINE on
   white, BLACK_OUTLINE on black — the function takes `color` as a
   parameter (don't hardcode).
9. **Snap body interior to suite** (`snap_body_interior_to_suite`):
   for pixels INSIDE the baseline body silhouette and below the head
   zone, snap any non-suite, non-accent color to the nearest suite
   color. Catches accessory edge bleed (e.g. orb's mid-tone outer ring
   pixels) that landed inside the body.
10. **Normalize outline per team** (`normalize_outline_per_team`): on
    the black team, swap any pixel matching `OUTLINE = (40,40,50)`
    (the white-team outline color used by accessories at generation
    time) to `BLACK_OUTLINE = (40,40,40)`. Accessory PNGs are shared
    between teams; this final pass re-tints their outlines for the
    dark team. **Critical**: only swap exact-match `OUTLINE` pixels —
    a brightness-based snap will incorrectly map `BLACK_FILL = (64,64,70)`
    (avg 66) to BLACK_OUTLINE and turn the entire black king body
    solid black. Don't use brightness here.

### 3.2 Per-accessory config (`Accessory` dataclass)

```python
@dataclass
class Accessory:
    id: str                 # e.g. "orb", "scepter", "staff"
    prompt: str             # full PixelLab prompt
    target_w: int           # post-resize width
    target_h: int           # post-resize height
    anchor: tuple[int, int] # (cx, cy) in 64×64 canvas
    z: int = 0              # paint order; lower first; z<0 = behind body
    negative: str = ""
    symmetric: bool = False # mirror-fill holes only
    full_sym: bool = False  # force perfect bilateral symmetry (orb)
    accent_palette: list = None  # extra allowed colors in body interior
    weapon: bool = False    # NEW: if True, this accessory becomes a SEPARATE
                            # `weapon_static.png` and is composited onto a
                            # transparent canvas instead of onto the body.
                            # The body-only static (sans this accessory) is
                            # saved as `body_static.png`. The fully-composited
                            # `static.png` still ships for UI consumers
                            # (captured-piece icons, promotion icons).
```

### 3.3 Three static outputs per weapon-bearing piece

For pieces that declare any `weapon=True` accessory, `wizard_statics.py`
emits **three** PNGs into `pieces/<color>/<piece>/`:

| file | contents | consumer |
|---|---|---|
| `static.png` | body + ALL accessories (incl. weapon) | UI icons (captured pieces, promotion picker, customization preview) |
| `body_static.png` | body + non-weapon accessories | board + floating-piece animation `Sprite` layer |
| `weapon_static.png` | weapon-only on transparent canvas | board + floating-piece animation `Weapon` overlay layer |

For pieces with no `weapon=True` accessory, only `static.png` ships and
the layered code path falls back to single-sprite rendering at runtime.

---

## 4. Verification — DO THIS AFTER EACH SPRITE, BEFORE CONTINUING

### 4a. Mechanical checks

```python
# Pseudocode — load the original baseline and the composited result.
# Run for both white and black teams.

# Silhouette preservation (the layered approach guarantees this by
# construction; verification just confirms we didn't break it).
- alpha_mask(baseline ⊆ result)              # baseline pixels still opaque
- silhouette_extension_px ≤ 60               # held-item extensions in budget
- silhouette_dropped_px ≤ 30 (king: ≤ 80)    # only king allowed to shrink at top

# Outline integrity
- every baseline-silhouette boundary pixel is the TEAM's OUTLINE color
  (OUTLINE for white, BLACK_OUTLINE for black)

# No stray "beard pixels" (non-suite, non-accent colors in body interior)
- in body region (below head_bot), exclude scepter zone (x ≥ sx0+27)
- 0 non-suite, non-accent pixels among the remaining body interior

# Orb symmetry (king specifically)
- orb_only.py: extract the 12×12 orb region, mirror around its center,
  ≤ 1 asymmetric pixel allowed (subtle color anti-aliasing)

# Twin parity
- alpha_mask(white) == alpha_mask(black)
```

### 4b. Visual character check

Open the new white + black sprite. Ask:

- **Head intact**: is the head still recognizably the original chess
  piece's head? No accessory should overlap onto the head region
  except where explicitly designed (king's orb replaces the cross,
  bishop/assassin emblem sits on the mitre face).
- **Body items show clearly**: can you see the staff / book / sword /
  cape / sash listed for that piece?
- **Body cream is clean**: cream-white pixels are exact suite cream
  (no pink/yellow/grey tint).
- **Theme cohesion**: multi-color across the set (one piece does not
  clone another's accent palette).
- **Readable at small size**: squint at the sprite — silhouette + body
  items still distinguishable.

### 4c. Comprehensive script

Use a one-off `_check_<piece>.py` for tricky pieces (the king
specifically — see git history of `tools/sprites/` for examples). For
the standard set, the asset sanity check `_verify_assets.py` catches
frame-count + dimension issues.

---

## 5. Animations

Animations are **procedural, not PixelLab.** Each frame is the wizard
static transformed by a `(dx, dy, squash, lean_top)` pose entry from
`POSES` in `wizard_animations.py`. Hit gets a per-frame brightness
flash; attack gets a softer flash on the swing-peak frames; death
fades alpha and scatters a few gold sparkle pixels.

PixelLab's `animate_with_text` was tried (see
[wizard_animations_pixellab.py](wizard_animations_pixellab.py)) and
rejected — see §9.

### 5a. Frame layout

Every frame is **64 × 64** to match the statics. Each strip is a
horizontal concat of `frames × 64`. SpriteFactory slices by height
(square-frame assumption) so this works without Godot scene changes.

| anim | frames | meaning |
|---|---|---|
| `static` | 1 | idle |
| `move` | 6 | piece slides/floats up and back down |
| `attack` | 6 | wind-up, lean forward, recover, with peak-frame flash |
| `hit` | 3 | piece flashes white then recovers |
| `death` | 5 | piece fades + gold sparkle dust scatters |
| `move_jump` | 7 | knight + alter_knight only — leaping arc |
| `attack_lunge` | 7 | alter_knight only — horn-charge attack |

### 5b. Pose system

The `transformed()` function applies these per-pixel:

- `dx, dy`: whole-body translation
- `squash`: vertical compression toward the bottom (rows shift
  downward by `squash × (1 - y_norm)` where `y_norm` is 0 at top of
  bbox, 1 at bottom; top rows move down most, bottom rows planted)
- `lean_top`: horizontal shear (top rows shift by `lean_top`,
  intermediate rows interpolate to 0 at the bottom)

Attack peak (frame 3) is `(7, 0, 0, 13)` — body shifts 7 px right and
the top leans 13 px right, like a paddle pivoting at its base.

### 5c. Animation verification

```python
# For each <piece>/<anim>.png:
- file width == 64 × frame_count (table above)
- file height == 64
- valid PNG, alpha-channel intact
- frame 0 silhouette ≈ static silhouette (animation starts at rest)
- last frame ≈ first frame for `move` (loops cleanly)
- last frame mostly transparent for `death`
- attack frames 2-3 have a noticeable flash overlay
```

The `_verify_assets.py` script catches all the dimension / frame-count
checks across all 99 sprites in one pass.

### 5d. Two-sprite layered animation (weapon-bearing pieces)

For pieces with a `weapon=True` accessory (currently bishop only —
prototype), the weapon is rendered as a **separate overlay sprite** on
top of a body-only sprite. The two sprites move in lockstep for the
shared body pose (so the staff stays anchored to the bishop's hand
during a lean), then the weapon adds its own per-anim motion on top
(raise + tip glow during attack).

**Generation flow** (in [wizard_weapon_animations.py](wizard_weapon_animations.py)):

1. Load `pieces/<color>/<piece>/weapon_static.png` (just the staff on
   transparent canvas).
2. For each anim in `[move, attack, hit, death, ...]`:
   - For each frame, take the body's `(dx, dy, squash, lean_top)` from
     the same `POSES` table that drives `wizard_animations.py` — call
     `transformed()` on the weapon-only static. This guarantees lockstep:
     when the body leans 13 px right at attack peak, so does the staff.
   - Then add per-piece, per-anim **extra motion** from
     `WEAPON_EXTRAS[piece][anim]` — a list of `(extra_dx, extra_dy,
     glow_intensity)` per frame. For bishop attack: frames 2-3 get
     `extra_dy = -8` (raise) and `glow_intensity = 0.6, 0.9` (tip glow).
   - Glow is a small 3-5 px gold/yellow cluster painted at the staff's
     current top opaque pixel position post-transform.
3. Save as `pieces/<color>/<piece>/weapon_<anim>.png`.

**Per-piece extras table** (sketch):

```python
WEAPON_EXTRAS = {
    "bishop": {
        "move":   [(0, 0, 0.0)] * 6,                   # lockstep only
        "attack": [(0,  0, 0.0), (0,  0, 0.0),
                   (0, -8, 0.6), (0, -12, 0.9),
                   (0, -4, 0.3), (0,  0, 0.0)],        # raise + glow
        "hit":    [(0, 0, 0.0)] * 3,                   # lockstep only
        "death":  [(0, 0, 0.0)] * 5,                   # lockstep only
    },
    # bandit_pawn / king / queen / assassin_bishop to follow.
}
```

**Pieces with a weapon but no extras yet**: weapon strips are still
generated in lockstep with the body, so they stay anchored — just
without the extra motion polish.

**Godot-side rendering** ([SpriteFactory.gd](../../godot/engine/SpriteFactory.gd)):

- `piece_frames(id, color)` populates `weapon_<anim>` keys when the
  files exist on disk; missing → key absent, caller falls back.
- The board square node ([scenes/GameScene.gd](../../godot/scenes/GameScene.gd))
  has a `Weapon` TextureRect as a child of `Sprite`. When piece is
  set, body texture goes on `Sprite`, weapon texture goes on `Weapon`
  (or `Weapon` is hidden if the piece has none).
- `_schedule_piece_anim(tween, lbl, ...)` schedules frame swaps on
  `lbl` (body) AND on `lbl.get_node("Weapon")` (weapon overlay) when
  the weapon strip is loaded for this anim.

**Why a child of Sprite, not a sibling**: position / scale / modulate
cascade. The fade-out for `_hide_static_sprite` and the tween scale
pulses on the body propagate to the weapon for free.

### 5e. Theatrical pacing — weighted frame durations + peak burst

Default `schedule_frame_swaps` distributes frames uniformly across the
animation duration: at `total_dur ≈ 290 ms` over 6 attack frames, each
frame gets ~48 ms — not enough for the eye to fixate on the peak
strike (raised staff + glowing tip). Pacing reweights the timing so
the wind-up and peak frames hold longer while the strike itself stays
snappy.

**Table** (in [GameScene.gd](../../godot/scenes/GameScene.gd)):
`ATTACK_FRAME_DURATIONS[piece] = [ms-per-frame × 6]` per
weapon-bearing piece. Each piece's frame 3 starts at exactly **0.200 s**
to align with `T_IMPACT` — the damage whiteout flash fires the same
instant the weapon hits its peak position.

```
piece          F0   F1   F2   F3*  F4   F5    total    feel
pawn           50   80   70  130   80   50  = 460 ms   apprentice — quick
bishop         50   80   70  140   90   60  = 490 ms   caster — measured
queen          50   80   70  160  110   60  = 530 ms   royal — ceremonious
king           50   80   70  180  130   70  = 580 ms   archmage — slowest
bandit_pawn    60   80   60  130   80   50  = 460 ms   assassin — snappy
```

The position tween (`T_ANTICIPATE + T_LUNGE + T_SETTLE = 290 ms`) is
unchanged — body settles at the target square before the weapon
finishes its recovery. Weight + follow-through reads naturally.

**Wiring** ([UiMotion.gd](../../godot/engine/UiMotion.gd)):
`weighted_frame_swaps(tween, sprite, frames, durations, delay)` — the
non-uniform variant of `schedule_frame_swaps`. `_schedule_piece_anim`
picks the weighted path when `ATTACK_FRAME_DURATIONS` has the piece
and the anim is `attack`; falls back to uniform otherwise.

**Peak-frame visual punch** (in
[_split_anim_weapons.py](_split_anim_weapons.py)):

- **Burst flash** — `paint_glow_cluster` upgrades from a 9-pixel cross
  to a **25-pixel radial burst** (cardinal rays out to distance 3 +
  diagonal rays out to distance 2) at `intensity >= 0.7`. Frame 3 of
  every weapon attack hits this threshold, so all 5 pieces' peak
  frames get the burst flare.
- **Motion streak** — for vertical-raise weapons (bishop staff, king
  scepter) at frames where `|ex_dy| >= 5`, paint a fading glow trail
  below the new tip showing where the orb just came from. Length
  matches the raise distance; alpha tapers linearly toward zero.

### 5f. Pixel-art crescent slash + blade rotation (sword pieces)

For sword pieces (`bandit_pawn`, `assassin_bishop`) on the **attack**
animation, the weapon overlay is two stacked layers, both painted onto
the weapon canvas before any modifiers run:

1. **Crescent slash** (bottom layer) — a bold, hand-drawn-looking
   swoosh of three discrete radial tones with tapered angular ends and
   internal motion streaks. This is the visually dominant element —
   the slash effect itself, not a faint trail behind something else.
2. **Rotating blade with ghost trail** (top layer) — the sword image
   is rotated around a pivot at the wielder's hand to a per-frame
   angle, accompanied by 6–7 alpha-tapered ghost copies linearly
   interpolated from the previous frame's angle. The blade rides on
   the leading edge of the crescent.

Lockstep, extras, and motion-streak code paths from §5e do **not**
apply on the attack frames of swing-armed pieces — the lockstep weapon
is replaced wholesale by the crescent + blade composite. Move/hit/death
still use lockstep transforms (no rotation, no crescent).

**Crescent painter** — `paint_crescent_slash()` in
[_split_anim_weapons.py](_split_anim_weapons.py):

- Inputs: `pivot=(px, py)`, `r_inner`, `r_outer`, `start_deg`,
  `end_deg`, `palette`, `max_alpha`. Angle convention: 0° = +x (right),
  90° = -y (up), wrap-aware against `[start, end]`.
- For each pixel in the bounding box of the outer radius:
  - Compute polar `(r, θ)` from the pivot.
  - Reject pixels outside `[r_inner, r_outer]` and outside the angular
    sweep.
  - **Angular taper** — `ang_alpha = sin(t·π)^0.5` where `t ∈ [0, 1]`
    is the position along the sweep. This gives the elegantly tapered
    crescent points seen in classic action-game sprite work — opacity
    peaks at the middle of the sweep and fades cleanly to zero at the
    endpoints. The `^0.5` power keeps the middle plateau wide so the
    crescent reads as solid rather than diamond-shaped.
  - **Discrete radial bands** — three flat tones, hard edges:

    | radial position `rt` | tone | role |
    |---|---|---|
    | `[0.00, 0.22)` | `(45, 55, 75)` | inner shadow (dark, hugs `r_inner`) |
    | `[0.22, 0.78)` | `(190, 195, 210)` | mid fill body |
    | `[0.78, 1.00]` | `(248, 250, 255)` | outer highlight rim |

    No gaussian blending between bands — the crescent posterizes
    cleanly into three stripes when zoomed in.
  - **Streak markers** — every 22° of sweep, a one-pixel-wide radial
    line in the mid band gets bumped to `(225, 230, 245)` (one tone
    brighter than fill). Reads as motion-direction hash marks inside
    the crescent body.
  - **Alpha quantization** — final alpha snaps to `{0, 96, 192, 255}`
    so the crescent edges read as crisp pixel-art tones, not as a soft
    anti-aliased gradient. Without this the discrete bands gain a
    fuzzy halo that breaks the pixel-art aesthetic.

**Per-piece per-frame config** — `CRESCENT_SLASH[piece]` table:

```python
CRESCENT_SLASH = {
    "bandit_pawn": {
        "pivot": (32, 46),
        "palette": "silver",
        "attack_frames": [
            None,  # F0 rest
            None,  # F1 wind-up
            {"r_inner": 8,  "r_outer": 22, "start_deg":  85, "end_deg": 165, "max_alpha": 145},  # F2 forming
            {"r_inner": 7,  "r_outer": 30, "start_deg": -50, "end_deg": 145, "max_alpha": 235},  # F3 PEAK
            {"r_inner": 7,  "r_outer": 26, "start_deg": -85, "end_deg":  20, "max_alpha": 175},  # F4 follow-through
            None,  # F5 settle
        ],
    },
    "assassin_bishop": {...},  # same shape, slightly larger sweep
}
```

`None` → no crescent on that frame. The peak frame sweeps ~195° (more
than half a circle) so the crescent visually dominates the attack
silhouette.

**Blade rotation + ghost trail** — `render_blade_swing_frame()` in
[_split_anim_weapons.py](_split_anim_weapons.py):

- Inputs: `weapon_static`, `prev_angle`, `curr_angle`, `pivot`,
  `ghost_count`, `ghost_alpha`.
- Paints `ghost_count` rotated copies at angles linearly interpolated
  from `prev_angle` to `curr_angle`, alpha-tapered from faintest
  (oldest) to most opaque (newest).
- Paints the current sword on top at full alpha.
- Uses PIL `rotate(NEAREST, center=pivot, expand=False)` so pixels
  preserve their hard-edged style during rotation.

**Per-piece angles** — `BLADE_SWING[piece]["attack_angles"]` (degrees,
positive CCW):

```python
"bandit_pawn": [0, 35, 55, -55, -85, 0]  # rest → wind-up → wind-up peak → SLASH → follow-through → rest
```

The big jump from `+55°` (F2) to `-55°` (F3) is the swing — it covers
110° in one frame, and the 6 ghost copies fan out across that arc to
form the multi-exposure trail riding on the crescent.

**Ordering inside the per-frame loop** (in `split_anim()`):

```python
weapon_frame = Image.new("RGBA", weapon_img.size, (0, 0, 0, 0))
if crescent_cfg present and frame has crescent:
    weapon_frame = paint_crescent_slash(weapon_frame, ...)
blade_frame = render_blade_swing_frame(blade_img, prev_a, curr_a, ...)
weapon_frame = Image.alpha_composite(weapon_frame, blade_frame)
```

Crescent first, blade on top — the blade reads as the leading edge of
the slash, and the crescent reads as the trailing visual punch.
Anim modifiers (HIT_FLASH / ATTACK_FLASH / DEATH_ALPHAS) are still
applied after — same per-anim post-pass as every other weapon-bearing
piece.

### 5g. Arc-only pieces (sword baked into baseline)

`assassin_bishop` is added to the layered pipeline via a new
**arc-only** path: its sword is baked into the baseline silhouette
behind a diagonal sash, with only ~10 visible pixels above the sash.
Extracting a clean sword sprite from such a thin slice isn't viable.
Instead:

- `body_static.png` = a copy of `aeaa0be:static.png` (sword baked in).
- `weapon_static.png` = a transparent canvas (no sword on disk).
- `body_<anim>.png` = transformed `body_static` per `POSES[anim]` — so
  the body is byte-identical to `aeaa0be:<anim>.png` everywhere
  outside the weapon's lockstep mask.
- `weapon_<anim>.png` for `attack` = crescent + rotating **synthetic**
  sword (built procedurally by `make_synthetic_assassin_sword()`,
  64×64 RGBA, sword laid out vertically with pivot at `(32, 50)` —
  blade body, gold crossguard, dark wood grip, gold pommel). The
  synthetic sword is drawn from the sheath on F1 (`frame_alpha = 1.0`)
  and resheathed on F5 (`frame_alpha = 0.0`).
- `weapon_<anim>.png` for `move`/`hit`/`death` = empty canvas (no
  visible sword — the baked-in sheathed one stays in the body).

The list of arc-only pieces is in `ARC_ONLY_PIECES` (in
[_split_weapons_from_aeaa0be.py](_split_weapons_from_aeaa0be.py)) and
parallel `pieces_with_weapons + ARC_ONLY_PIECES` iteration in
[_split_anim_weapons.py](_split_anim_weapons.py). The `synthetic` key
in `BLADE_SWING[piece]` selects which procedural blade builder to use
(`"assassin_sword"` → `make_synthetic_assassin_sword()`).

### 5h. Verification — visual + pixel-perfect

- **Pixel-perfect baseline preservation** — for both arc-only and
  regular weapon-bearing pieces, `_split_anim_weapons.py` re-runs the
  per-frame body-subtract verification: `body_<anim>.png` must match
  `aeaa0be:<anim>.png` byte-for-byte everywhere outside the weapon's
  lockstep mask. 56/56 verifications PASS for the current set
  (5 weapon-bearing pieces + assassin_bishop, ×2 colors, ×4 anims).
- **Visual character check** — three throwaway preview scripts under
  `tools/sprites/`:
  - `_render_attack_preview.py` — 6× scale grid: body strip / weapon
    overlay / composite, all 6 attack frames per piece. Use to spot
    macro issues (crescent missing, blade orientation wrong, layering
    inverted).
  - `_inspect_peak_slash.py` — 12× scale single-frame view of F2/F3/F4
    per piece. Use to verify the discrete radial bands posterize
    cleanly and the streak markers read.
  - `_inspect_assassin_bishop.py` — text-art dump of the
    assassin_bishop static showing where the sword pixels land in the
    silhouette (used originally to decide between sword extraction vs.
    arc-only synthetic).

### 5i. What didn't work — crescent slash iteration

Three earlier attempts during this iteration; recording them so a
future Claude doesn't re-run the same dead ends.

- **Subtle translucent annulus** (rejected) — first cut of
  `paint_arc_swing` painted a thin annular ring with a single grey
  color and gaussian radial taper, alpha ~120. Result: faint wisps,
  nothing like the reference's bold crescents. Doubling alpha didn't
  help — the shape was wrong, not just the opacity.
- **Pure blade rotation, no crescent** (rejected) — replaced the
  overlay with just `render_blade_swing_frame()` (rotating blade +
  ghost trail). At ghost_count=6 the result reads as a multi-exposure
  fan of discrete sword copies, not a continuous painted swoosh. The
  user's reference clearly shows a single solid crescent shape, not a
  strobe of swords. The blade-rotation effect is good as a **leading
  edge** but isn't sufficient on its own.
- **Gaussian-blended crescent + blade** (rejected — too soft) — first
  proper crescent painter used three gaussian peaks across the radial
  band (`exp(-((rt - peak)/σ)²)`) and color-blended them by relative
  weight. The result was 3D-shaded but had a soft, gradient-y feel
  that didn't match the discrete-pixel-art style of the rest of the
  set. Also the soft alpha fringe smeared the crescent edges into
  surrounding pixels.

The shipped approach (§5f) replaces the gaussian peaks with **hard
band lookups** (`if rt < 0.22 → shadow; elif rt < 0.78 → fill; else →
highlight`) and **quantizes the final alpha** to `{0, 96, 192, 255}`
so the crescent reads as a deliberate three-tone pixel-art shape with
crisp edges, matching the reference's hand-drawn feel.

### 5j. Staff cast-magic flash (bishop / king / queen)

Staff casters get a dedicated **light-flash sprite asset**, *separate*
from their `weapon_attack.png`, that plays the cast-magic burst on the
staff orb during the attack. Architecturally this is its own track:
the flash gets its own strip, its own Godot child node, and its own
gem-tinted impact FX at the target square. The staff sprite itself
stays clean — no rotation, no translation, no glow baked in — so the
flash can be tuned independently and so the burst rays aren't clipped
by the 64×64 weapon canvas.

**Sprite asset** —
[`weapon_flash_<anim>.png`](../../godot/assets/sprites/anim/pieces/white/bishop/weapon_flash_attack.png)
generated by [_render_staff_flash.py](_render_staff_flash.py):

- 96×96 frames × N frames (N = attack frame count = 6).
- Per frame, the script finds the staff tip (top opaque pixel) of the
  matching `weapon_attack.png` frame, then paints a multi-pointed star
  burst at `(tip_x + 16, tip_y + 16)` in the 96×96 canvas. The +16 is
  the buffer that keeps the burst rays from clipping when the tip is
  near the canvas edge after the body's lockstep lean shifts the
  staff. In Godot the flash child is positioned at offset (-16, -16)
  relative to the 64×64 piece sprite so the canvas-space (16, 16) of
  the flash aligns with the (0, 0) of the weapon — i.e. the burst
  always lands on the *current* lockstep'd staff tip.
- 6-frame burst progression (`FRAME_PROFILES` in the same script),
  matching the user-supplied 8-frame reference compressed to attack
  frame count:

  | frame | type | content |
  |---|---|---|
  | F0 | None | invisible (rest) |
  | F1 | `spark` | tiny pre-flash dot (single bright pixel + 4-px cross) |
  | F2 | `burst` | small charging burst — core size 1, cardinal rays len 6, diagonal rays len 3 |
  | F3 | `burst` | **PEAK** — core size 2, cardinal rays len 18, diagonal rays len 12 |
  | F4 | `ring_burst` | collapsing — short rays len 5 + bright ring outline at radius 11 |
  | F5 | `ring` | fading ring outline at radius 6, alpha 130 |

- Drawing primitives (in `_render_staff_flash.py`):
  - `draw_core(canvas, cx, cy, radius, color, alpha)` — bright filled
    disc at the burst center, soft 1-px edge falloff.
  - `draw_ray(canvas, cx, cy, dir_x, dir_y, length, core, tip, alpha)`
    — single-pixel-wide line outward in `(dir_x, dir_y)` for `length`
    pixels. Color tapers `core → tip` along the ray; alpha falls off
    quadratically (`α(t) = α_max·(1 - t² · 0.95)`) so the tip dims
    smoothly without a hard cutoff.
  - `draw_ring(canvas, cx, cy, radius, thickness, color, alpha)` —
    1–2-px ring outline, alpha tapered across thickness.

- Per-piece gem tint (`GEM_COLOR`):

  | piece | tint | usage |
  |---|---|---|
  | bishop | `(255, 215, 100)` gold | rays + ring outlines |
  | king | `(200, 130, 230)` purple | rays + ring outlines |
  | queen | `(130, 230, 220)` teal | rays + ring outlines |

  The core stays near-white `(255, 252, 245)` for "intense light" feel;
  rays interpolate `core → gem` along their length so the tips read as
  saturated gem color while the center reads as a glow.

**Godot wiring** — three pieces in
[GameScene.gd](../../godot/scenes/GameScene.gd):

1. **`SpriteFactory.piece_frames()`** loads `weapon_flash_<anim>.png`
   alongside `body_<anim>` / `weapon_<anim>` strips when the file
   exists, exposing it under `weapon_flash_<anim>` in the dict.
2. **`_create_floating_piece()`** adds a `Flash` TextureRect child
   alongside the `Weapon` child. Position `(-16, -16)`, size `(96, 96)`,
   `STRETCH_KEEP_ASPECT_CENTERED`, hidden by default. (Board squares
   intentionally do **not** get a Flash child — the flash only plays
   on the transient floating piece during an attack tween, and adding
   64 hidden TextureRects to the board would just be dead weight.)
3. **`_schedule_piece_anim()`** — when the dict has `weapon_flash_<anim>`
   AND `lbl` has a Flash child, the flash gets its own
   `weighted_frame_swaps` / `schedule_frame_swaps` tween in lockstep
   with the body + weapon tracks (same `ATTACK_FRAME_DURATIONS` table
   so all three peak at exactly the same moment), then a
   `tween_callback(_hide_flash_child.bind(flash_child))` clears it
   when the anim ends so a leftover burst frame doesn't bleed into
   the next-turn render.

**Magic impact FX** —
`_spawn_attack_impact_fx(tween, to_sq, def_id, impact_t, floats)`:

- Replaces the inline `✸` flare in the `if is_attack:` block.
- Branches on `def_id`:
  - **Staff casters** (bishop / king / queen): center `✦` rune scales
    up + spins, and 6 radial sparkles (`✧✦✶✧✦✶`) fly outward at angles
    `k·τ/6 + π/6` (radial distance 24 px), each scaling + spinning +
    fading. All glyphs tinted to the caster's gem color (HDR-bright
    Color values like `Color(1.55, 1.15, 0.45)` for gold so they bloom
    against the board).
  - **Everyone else**: original single `✸` flare, gold tint.
- Both variants share the same timing window (start at `impact_t`,
  peak ~+0.22 s, fade ~+0.30 s) so chained damage / kill / push
  flashes sync correctly regardless of which branch ran.

### 5k. What didn't work — staff cast-magic iteration

Recording these so a future iteration doesn't re-run them.

- **Aura rings baked into `weapon_attack.png`** (rejected — clipped) —
  first attempt painted concentric rings (radii up to ~20 px) at the
  staff tip directly into the weapon sprite. The 64×64 canvas isn't
  big enough — the staff orb sits near the top of the canvas, so any
  ring with radius > tip's distance-to-edge gets cropped, leaving an
  asymmetric arc instead of a clean ring. Also conflated the staff
  sprite with its FX, making either hard to tune in isolation.
- **Staff translation up + right inside the sprite** (rejected — also
  clipped) — second attempt added per-frame `(extra_dx, extra_dy)`
  translation so the staff "raised" during F2-F4. With `extra_dy = -12`
  at F3 the orb pixel landed at `y = -4` (off the canvas top), getting
  cropped. The user's instruction at this point was explicit: *don't
  move things in the sprite animation if it would cut them off — move
  the whole sprite via Godot positioning instead.* So the shipped
  approach leaves the staff in pure body-lockstep within the sprite,
  and any cinematic motion happens via Godot's anticipate/lunge/settle
  position tween on the floating piece.
- **Staff rotation around the grip pivot** (rejected — body coupling
  weird) — third attempt rotated the staff by `±8–16°` per frame
  around `WEAPON_ROT_PIVOT` to stay in canvas while still adding
  motion. Worked geometrically but conflicted with the body's
  lockstep lean: the rotated staff and the leaning body read as one
  jerky welded silhouette rather than two coordinated sprites.
  The decoupled-pose approach (rotate weapon BEFORE applying body
  lockstep, with separate subtraction mask for body) added complexity
  without a corresponding visual win once we decided the flash sprite
  itself was carrying the visual interest.
- **Procedural ring-pulse drawn in Godot via custom Control** (deferred)
  — considered drawing the rings via `_draw()` on a custom Control
  subclass instead of a sprite asset. Pixel-art aesthetic vs. Godot's
  anti-aliased `draw_arc` was the friction — the sprite asset gives
  full control over ray sharpness and the "8-frame burst" reference
  look without needing a custom shader. Still viable as a future
  alternative if we want runtime-tunable burst sizes.

The shipped approach (§5j): no staff motion in `weapon_attack.png`,
all the visual punch comes from the separate flash sprite + the
magic radial-sparkle impact FX, and Godot's existing position-tween
handles the lunge/settle without any per-piece staff-rotation code.

---

## 6. Ability VFX

VFX use **atom-based procedural compositing**. For each ability, we
generate one or two static PixelLab "atoms" (one fireball image, one
explosion, one smoke; one lightning bolt, one flash, one glow; one
rock cluster, one impact, one sparkle swirl). Frames are then built
procedurally by translating those atoms to specific Y positions per
frame so the falling/striking motion is actually visible.

This replaces the earlier per-frame text generation that produced
in-canvas-centered objects with no observable motion when played.

### 6a. Cannon — `cannon_resolve.png` + `cannonball.png` (sky-strike)

Reads as **sky-strike**: a flaming cannonball falls FAST from off-screen
above and lands at the AOE center, where a single cohesive cross-shape
explosion fills the 5-cell PLUS AOE (Rules.gd `CANNON_PLUS_OFFSETS` =
center + 4 cardinal neighbors). The four flame arms reach into the
cardinal cells; the corner cells stay untouched. **One sprite = the
whole AOE explosion**, not five independent puffs.

Architecturally split into two files:

- **`cannonball.png`** — static 64×64 PixelLab atom (the falling
  cannonball). Has a black iron ball at the bottom-center with a tall
  perfectly-vertical orange-red flame column above it. Shown via a
  Godot Y-tween (no descent frames are baked into the strip).
- **`cannon_resolve.png`** — 8-frame post-impact strip on a 192×192
  canvas (3 squares × 3 squares = the cross-AOE bounding box). Plays
  AFTER the cannonball lands.

**Atoms** (in `_pixellab_cache/`):

| atom | seed | prompt | use |
|---|---|---|---|
| `cannonball_straight_down` | 8121 | black iron cannonball at bottom-center with perfectly vertical orange-red flame trail above, no diagonal angle | static descender texture |
| `cannon_cross_blast` | 8113 | plus-shaped explosion with four flame arms in cardinal directions, no diagonal arms, no circular shape | post-impact cross explosion |
| `smoke` | 8103 | soft grey smoke wisps | post-explosion fade |

The earlier `fireball` (8101), `explosion` (8102), and `cannonball_down`
(8111) atoms were rejected: 8101 was an omnidirectional fireball
(no clear "down" axis), 8102 was a circular blob (not cross-shape),
8111 came out angled. Left in cache for diff purposes.

**Post-impact strip layout** (`build_fireball()` in `wizard_vfx.py`):

192×192 frames, explosion centered at (96, 96). 8 frames total.

| frame | content |
|---|---|
| 0 | white-hot impact flash (cross_blast tinted toward white, scale 2.4) |
| 1 | cross explosion just bloomed (scale 2.50, alpha 1.00) |
| 2 | arms reaching into cardinal cells (scale 3.00, alpha 0.95) |
| 3 | **PEAK** — arms cover all 4 cardinal squares (scale 3.40, alpha 0.85) |
| 4 | fading (scale 3.50, alpha 0.65) |
| 5 | further fading (scale 3.55, alpha 0.40) |
| 6 | smoke wisp (scale 2.20, alpha 0.55) |
| 7 | smoke dissipating (scale 2.40, alpha 0.20) |

**Godot wiring** — `_play_cannon_resolve()` in
[GameScene.gd](../../godot/scenes/GameScene.gd):

1. Find the AOE center cell (the one whose 4 cardinal neighbors are
   all in `squares`). Fall back to the centroid of `squares` if
   clipped at the board edge.
2. Spawn a 32×128 TextureRect (`cannonball.png`) — display height is
   2 squares, head occupies the bottom 32×32 (~50% of debris linear
   size, with a long flame trail above). Position: 8 squares above
   the AOE center, x-centered.
3. Y-tween the cannonball's position straight down to the AOE center
   over `CANNON_DESCENT_DUR = 0.22s` (fast — heavy iron ball drops
   sharply).
4. At impact (`+ 0.22s`), `_hide_descender(cannonball)` makes the
   cannonball invisible. Spawn a 3*SQ × 3*SQ TextureRect at the AOE
   center, frame-swap through `cannon_resolve.png`, fade-out at end.

The cannonball ALWAYS spawns 8 squares above the AOE center, so for
any target row the spawn point is well above the visible board area
— the ball reads as falling from the sky regardless of where on the
board it lands.

### 6b. Lightning — `lightning_strike.png` (6 frames, **tall sky-strike**)

Reads as a **true sky-strike**: the lightning sprite is **TEN board
squares tall** (64 wide × 640 tall in source pixels — a deliberate
break from the 64×64 single-square assumption used by the other VFX).
The board is 8 squares tall, so anchoring a 10-square sprite to any
target row guarantees the sprite's top edge extends above the top of
the board → the strike *always* reads as coming from off-screen
above, no matter which square is hit. The bolt grows downward across
F0–F2, lands at the ground line at F3 with a bright radial impact
spark, and dissipates over F4–F5.

In Godot the sprite is anchored so its **bottom edge aligns with the
target square's bottom**, putting the impact spark inside the target
square and the descending bolt on the column above. See
`_play_lightning_at()` + `LIGHTNING_SQUARES_TALL = 10` in
[GameScene.gd](../../godot/scenes/GameScene.gd). Earlier iterations
shipped with `LIGHTNING_SQUARES_TALL = 4`, but for targets in the
lower rows of the board the bolt's top edge landed mid-board rather
than off-screen, so the strike read as "bolt appearing 3 squares
above target" instead of "bolt from the sky" — fixed by going to 10.

**Atoms** (in `_pixellab_cache/`):

The bolt itself is rendered as **five distinct PixelLab sprites** —
one per visible-bolt frame — so every frame's silhouette is unique
rather than the same source clipped at different heights. This is
what gives the strike its dynamic flicker (real lightning never
draws the same path twice; neither does this animation).

| atom | seed | prompt | use |
|---|---|---|---|
| `lightning_bolt_tall` | 8211 | "thin tall bolt … multiple zigzag bends" | F0 — bolt forming high in sky |
| `lightning_bolt_b` | 8221 | (same) | F1 — bolt mid-descent |
| `lightning_bolt_c2` | 8232 | "sharp angular line segments … classic Z-shape" | F2 — bolt reaches ground |
| `lightning_bolt_d2` | 8242 | (same Z-shape prompt) | F3 — PEAK |
| `lightning_bolt_e` | 8251 | "thin tall bolt … multiple zigzag bends" | F4 — fading |
| `lightning_flash` | 8202 | "bright white circular impact flash with yellow rays" | impact spark (F2-F4) |
| `lightning_glow` | 8203 | "soft yellow glow halo, mostly transparent" | F5 residual |

The first re-roll of `lightning_bolt_c` (seed 8231) and `lightning_bolt_d`
(seed 8241) under the loose prompt produced smooth columnar / flame
shapes that didn't read as zigzag once stretched, so they were
re-rolled with seeds 8232 / 8242 under a stricter "classic Z-shape …
NOT a smooth column, NOT a flame" prompt. Left in cache for diffing.

The earlier `lightning_bolt` atom (seed 8201) was a small emoji-style
bolt and isn't referenced by the shipping pipeline either.

**Composition** (`build_lightning()` in `wizard_vfx.py`):

Frame size: `LIGHTNING_FRAME_W = 64`, `LIGHTNING_FRAME_H = 640`.
`LIGHTNING_GROUND_Y = 628` is the y-coordinate (in source-pixel
units) of the strike point — close to the bottom of the canvas so
the impact spark lands inside the target square once the sprite is
bottom-anchored in Godot.

Each of the five PixelLab bolt atoms gets stretched independently
via `_stretch_bolt_to_canvas()` — height-driven scale to a 624-px
sprite that spans the full canvas height with a 4-px breathing room
at the top, horizontally centered, width capped at `max_w = 18` so
the bolt stays thin after the ~10× vertical stretch. The result is
one 640-px-tall canvas per atom (`canvas_a` through `canvas_e`).

`clip_below(img, max_y)` alpha-zeroes pixels below `max_y` and is
used **only** on F0 and F1 to convey sky-descent (the bolt hasn't
struck ground yet). The clipped sources are different atoms (a vs b),
so even the descending bolt has a different silhouette frame to frame.

| frame | source bolt | clip | overlay | reads as |
|---|---|---|---|---|
| 0 | canvas_a | y ≤ 256 (top ~40%) | — | bolt forming high in the sky, several squares above target |
| 1 | canvas_b | y ≤ 480 (top ~75%) | — | different bolt mid-descent, ~1 square above target |
| 2 | canvas_c | full | small spark at y=628 (alpha 0.55, scale 0.55) | bolt reaches ground |
| 3 | canvas_d | full | **PEAK** spark at y=626 (alpha 1.0, scale 1.05) | bright strike — damage applies here |
| 4 | canvas_e (alpha 0.45) | full | wide fading spark at y=626 (alpha 0.7, scale 1.30) | post-strike afterglow |
| 5 | (none) | — | residual glow at y=626 (alpha 0.4, scale 0.85) | dissipating |

No two consecutive frames share a bolt silhouette — the strike
flickers like real lightning rather than rendering the same source
clipped at different heights.

`LIGHTNING_GROUND_Y = 244` (a constant in `wizard_vfx.py`) is the
y-coordinate of the strike point in source-pixel units — it lines up
with the bottom of the target square in Godot once the sprite is
anchored. The bolt's full opacity at F3 doubles as the impact-cue
frame (damage applies the moment the player sees the peak spark).

**Godot wiring** — `_play_lightning_at()` in
[GameScene.gd](../../godot/scenes/GameScene.gd):

- `LIGHTNING_SQUARES_TALL = 10` — number of board squares the sprite
  spans vertically. The board is 8 squares tall, so this is enough
  margin that the sprite top is always above the board top regardless
  of which row is the target.
- TextureRect is sized `(SQ_SIZE, SQ_SIZE * 10)` and positioned at
  `(sq_pos.x, sq_pos.y - SQ_SIZE * 9)` — one square's worth at the
  bottom holds the impact spark inside the target square; nine
  squares above hold the descending bolt (clipped by the board's
  visible area, which is exactly the desired "from off-screen above"
  read).
- `SpriteFactory._load_strip(path, frame_w)` accepts an explicit
  `frame_w` param so the lightning's non-square frames slice
  correctly. Defaults to `frame_w = h` (square frames) for every
  other VFX strip.

### 6c. Debris — `debris_fall.png` + `debris_rocks.png` (sky-strike, single cell)

Same architecture as the cannon (descent via Godot Y-tween + a
post-impact strip), but for a **single-cell** target. Slower descent
than the cannon — heavy rocks drift down rather than the iron ball
plummeting.

- **`debris_rocks.png`** — static 64×64 PixelLab atom: three jagged
  dark-grey rock chunks clustered together with a faint purple
  magical aura around them. Y-tweened in Godot.
- **`debris_fall.png`** — 4-frame post-impact strip on a 64×64
  canvas. Plays AFTER the rocks land.

**Atoms**:

| atom | seed | prompt | use |
|---|---|---|---|
| `magic_rocks` | 8301 | three jagged dark-grey rock chunks clustered together with a faint purple magical aura | static descender texture |
| `rocks_impact` | 8302 | brown-and-purple dust burst with sparkle rays radiating outward, ground impact | F0 of impact strip |
| `purple_sparkles` | 8303 | swirl of purple sparkle particles spreading outward | F1–F3 fade-out |

**Post-impact strip layout** (`build_magic_rocks()` in `wizard_vfx.py`):

64×64 frames, impact centered at (32, 32). 4 frames total.

| frame | content |
|---|---|
| 0 | dust burst at impact (rocks_impact, scale 0.95) |
| 1 | sparkles swirl out (scale 0.85, alpha 0.85) |
| 2 | sparkles wider + fading (scale 1.05, alpha 0.55) |
| 3 | sparkles dissipating (scale 1.20, alpha 0.20) |

**Godot wiring** — `_play_debris_resolve()` in
[GameScene.gd](../../godot/scenes/GameScene.gd):

For each targeted square (debris is single-cell per spec, but the
same code path supports a list of cells with a per-cell ripple delay):

1. Spawn a 56×56 TextureRect (`debris_rocks.png`) — display size is
   close to 1 board square so the head reads as bigger than the
   cannonball's head. Position: 8 squares above the target square
   center, x-centered.
2. Y-tween the rocks' position straight down to the target square
   center over `DEBRIS_DESCENT_DUR = 0.42s` (~2× slower than the
   cannonball — heavy rocks fall slower than the iron ball).
3. At impact, `_hide_descender(rocks)` hides the rocks. Spawn a
   1*SQ × 1*SQ TextureRect at the target square, frame-swap through
   `debris_fall.png`, fade-out at end.

Same "always spawns 8 squares above the target" rule as the cannon
guarantees the descent is visibly from off-screen-above regardless
of target row.

### 6d. VFX verification

```python
- transparent background everywhere (no opaque corners)
- frame-to-frame motion smooth (no Y jumps > 12 px)
- final frame's opaque-pixel count < 30 (mostly faded)
- file width == 64 × frame_count, height == 64
```

---

## 7. Order of operations

1. **Static sprites** — `python tools/sprites/wizard_statics.py`
   generates all 9 pieces × 2 colors. For weapon-bearing pieces, also
   emits `body_static.png` + `weapon_static.png`. Verify against §4.
   Commit.
2. **Body animations** — `python tools/sprites/wizard_animations.py`
   generates `<anim>.png` (full composite) for every piece. For
   weapon-bearing pieces, also generates `body_<anim>.png` (body-only).
   Verify against §5c. Commit.
3. **Weapon animations** — `python tools/sprites/wizard_weapon_animations.py`
   generates `weapon_<anim>.png` for every piece declared as
   weapon-bearing. Lockstep body POSES + per-piece, per-anim extras.
   Verify against §5d. Commit.
4. **VFX** — `python tools/sprites/wizard_vfx.py` generates the three
   FX strips. Verify against §6d. Commit.
5. **Godot import check** — run `Godot --headless --path godot --quit-after 50 --import`
   to verify all assets import cleanly with 0 errors.
6. Each phase as a separate commit so reverting individual phases is
   cheap if something looks wrong in-game.

---

## 8. Cost estimate

PixelLab API calls (each ~$0.005–0.02):

- **Statics**: 9 pieces × ~2 accessories each = ~18 calls, cached by
  `(piece, accessory_id, seed)` so re-runs hit cache.
- **Body animations**: **0 calls** (procedural).
- **Weapon animations**: **0 calls** (procedural — same pose transform
  + per-piece extra motion table; no PixelLab).
- **VFX**: 3 abilities × ~3 atoms each = ~9 calls.

**Total: ~27 calls, $0.15–$0.55 USD.** Re-rolls cost a few extra
calls each. Cache makes iterative tuning essentially free. The
weapon-overlay layer adds zero PixelLab cost — accessory PNGs are
already on disk from the static pipeline, so the weapon static is just
a re-composite onto a transparent canvas.

---

## 9. What didn't work — post-mortem

Three earlier approaches were tried and abandoned. Recording them
here so a future Claude doesn't re-run the same experiments.

### 9.1 Inpaint accessories on the existing sprite (rejected)

Initial approach: build a small per-accessory mask, call PixelLab
`inpaint` with the cream sprite as `inpainting_image`, snap result to
suite palette. **Result**: pixel-level masks worked, but accessories
came out compositionally awkward — the model was forced to fill a
small rectangle on top of an existing chess piece and produced
disconnected blobs that didn't read as staffs / books / swords.

### 9.2 Regenerate-from-scratch with `init_image` (rejected)

Second approach: pass the cream sprite as `init_image` at moderate
strength via `pixflux`, let PixelLab compose the whole wizard sprite
in one shot. Tested strengths 50 → 880. **Result**:

- ≥ 500: PixelLab echoes the input — no wizard items added.
- 80–150: items appear but the head silhouette drifts (mitre wobbles,
  body squares vary frame-to-frame at the same strength + different
  seeds).
- < 80: head is unrecognizable.

No sweet spot. Even at 80 with `text_guidance_scale=14`, the cross
on the bishop's mitre frequently survived (init image dominates near
strong features) and the body items showed up only ~50% of seeds.

### 9.3 PixelLab `animate_with_text` for animations (rejected)

Tried: pass each piece's static as `reference_image`, prompt the
action ("swinging staff to attack", "trotting forward"), request
`n_frames=6`. **Result**:

- API caps practical n_frames at 4 even when 6 is requested.
- At `image_guidance_scale=4`: characters drift heavily between frames
  (mitre changes shape, horse face shifts).
- At `image_guidance_scale=8`: model adds **wing-aura artifacts** —
  large symmetric shapes flapping out the sides of the body to depict
  "motion" / "swing". Looks like a chess piece with bat wings.

Switched to procedural translate+lean+squash (the approach that
ships, see §5). Code preserved at `wizard_animations_pixellab.py` for
reference.

### 9.4 Per-frame text-prompted VFX (rejected)

Tried: generate each VFX frame independently via pixflux with a
prompt that specified position ("fireball near the top of the
canvas", "fireball 1/4 down", etc.). **Result**: PixelLab ignored
position cues and centered every fireball/bolt/rock cluster in its
frame. Played as a series of in-place morphs with no observable
falling motion.

Switched to atom-based composition: generate one atom per type,
translate procedurally per-frame. Ships at §6.

### 9.5 Other gotchas worth remembering

- **Black baseline pitfall**: the on-disk `4ceaa7d` black king used
  `(40,40,40)` and `(64,64,70)` for outline + fill, NOT
  `BLACK_OUTLINE = (16,14,22)` / `BLACK_FILL = (60,56,70)` from a
  prior version of the constants. Lesson: always derive the black
  baseline at runtime via `wizard_recolor_to_black(white)` so both
  teams share an identical 4-color contract regardless of what's on
  disk.
- **Shared accessory PNG → wrong-color outline on black team**:
  accessories are generated once with white-team `OUTLINE = (40,40,50)`
  and composited onto both teams. Without `normalize_outline_per_team`
  the black king has 248 boundary pixels in white's outline color
  instead of `BLACK_OUTLINE = (40,40,40)`. Add a final per-team swap
  (exact-match only — DO NOT use a brightness-based snap, you'll
  destroy the body fill).
- **Pre-clear king cross**: the silhouette has cross-top → bauble →
  cross-stem → body. The naive "first wide row after a thin row"
  heuristic stops at the bauble (~row 3) and leaves the bauble +
  lower stem behind to stack with the orb composite. Use "first row
  ≥ 14 px wide" (the actual body) instead.
- **Orb asymmetry**: the PixelLab orb cache has gold patterns that
  lean right. Apply `full_symmetrize()` (pick denser side of each
  row, mirror to the other) — `mirror_symmetric` only fills holes,
  doesn't enforce full symmetry.
- **`init_image_strength = 0` is invalid**: PixelLab requires `≥ 1`.
  Just omit `init_image` entirely if you don't want one.
- **Snap-outline brightness threshold**: 80 is too tight — leaves
  dark accessory outlines like dark navy `(45,67,99)` un-snapped.
  Use 95 (avg-brightness-based) instead of 80 (max-channel-based).
