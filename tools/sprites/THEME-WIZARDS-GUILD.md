# Wizards' Guild Theme — Implementation Guide

This is a self-contained guide for a fresh Claude Code session to take
the existing 9-piece chess set and reskin it as a "Wizards' Guild"
theme, then produce matching animations and three magical-ability VFX.

The base sprites are at `godot/assets/sprites/anim/pieces/<color>/<piece>/static.png`
in a clean flat-cream + outline + right-edge-shadow palette (suite
palette defined in [restyle.py](restyle.py)). They are the **baseline
canvas** — accessories are generated separately and composited on top.

> **Approach evolution recorded here**: this doc was rewritten after
> implementation. The earlier inpaint-only and regenerate-from-scratch
> approaches were both abandoned. The shipped pipeline is **layered
> compositing of isolated accessory PNGs** — see §3 for details and
> §9 for a list of approaches that didn't work.

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
| [wizard_animations.py](wizard_animations.py) | procedural animation generator — applies per-frame translate / lean / squash transforms to the wizard static. **The canonical animator.** |
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
```

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

### 5d. Per-piece weapon-only animation (NOT shipped)

The current animations apply the same translate+lean transform to the
WHOLE sprite (body + accessories baked in as one rigid image). The
weapon visibly swings only because it sits at the top of the piece —
where the lean shear amplifies most. Pieces with weapons at mid-body
(pawn book, bandit dagger) barely register as swinging.

To get true per-weapon animation (e.g. bishop staff thrusting
independently of the body), each accessory would need to stay layered
post-static-generation — a per-piece weapon mask stored alongside the
static, then transformed independently per attack frame. Not done.
File a follow-up if you want this.

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

### 6a. Fireball — `cannon_resolve.png` (14 frames)

Atoms (PixelLab pixflux, prompt + transparent background):
- `fireball`: orange-red fireball with flame trails
- `explosion`: orange-yellow circular explosion
- `smoke`: soft grey smoke wisps (mostly transparent)

Procedural composition (`build_fireball()` in `wizard_vfx.py`):

| frames | content |
|---|---|
| 0–5 | fireball descends from y=8 to y=48, scale 0.55 → 0.85 |
| 6 | white-hot impact flash (explosion atom tinted bright) at y=52 |
| 7–11 | explosion expands (scale 0.55 → 1.20, fades opacity) |
| 12–13 | smoke dissipates (50% then 20% opacity) |

### 6b. Lightning — `lightning_strike.png` (6 frames)

Atoms: `lightning_bolt` (full canvas-height jagged zigzag),
`lightning_flash` (white impact flash), `lightning_glow` (yellow halo).

| frame | content |
|---|---|
| 0 | faint glow at top y=8 |
| 1 | full bolt stretched to canvas height |
| 2 | bright flash at impact (y=50) |
| 3 | bolt fading + glow at impact |
| 4 | small dim glow |
| 5 | barely-visible glow remnant |

### 6c. Magic rocks — `debris_fall.png` (9 frames)

Atoms: `magic_rocks` (cluster of grey chunks with purple aura),
`rocks_impact` (dust + sparkle burst), `purple_sparkles` (swirl).

| frames | content |
|---|---|
| 0–4 | rocks descend from y=10 to y=48 |
| 5 | impact at y=50 |
| 6–8 | sparkles spread outward (scale up, opacity down) |

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
   generates all 9 pieces × 2 colors. Verify against §4. Commit.
2. **Animations** — `python tools/sprites/wizard_animations.py`
   generates move/attack/hit/death + knight/alter_knight extras.
   Verify against §5c. Commit.
3. **VFX** — `python tools/sprites/wizard_vfx.py` generates the three
   FX strips. Verify against §6d. Commit.
4. **Godot import check** — run `Godot --headless --path godot --quit-after 50 --import`
   to verify all assets import cleanly with 0 errors.
5. Each phase as a separate commit so reverting individual phases is
   cheap if something looks wrong in-game.

---

## 8. Cost estimate

PixelLab API calls (each ~$0.005–0.02):

- **Statics**: 9 pieces × ~2 accessories each = ~18 calls, cached by
  `(piece, accessory_id, seed)` so re-runs hit cache.
- **Animations**: **0 calls** (procedural).
- **VFX**: 3 abilities × ~3 atoms each = ~9 calls.

**Total: ~27 calls, $0.15–$0.55 USD.** Re-rolls cost a few extra
calls each. Cache makes iterative tuning essentially free.

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
