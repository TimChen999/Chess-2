# Medieval stage — generation plan

Reskin of the board (8x8 grid + frame), a viewport-wide backdrop, and a
board-sized macro-detail overlay. No layout changes: square pitch stays
at `SQ_SIZE = 72` and the grid stays 8x8
([GameScene.gd:18](../../godot/scenes/GameScene.gd#L18)). Everything is
added as PNG atoms generated via PixelLab and assembled by Godot's
existing `GridContainer` + `NinePatchRect` + `TextureRect` primitives.

PixelLab never generates the grid as a whole image. It only generates
**single repeatable units** (one light tile, one dark tile, one wood-
edge atlas, one backdrop tile) plus **one non-tiling board-sized
overlay** carrying all the macro detail (moss, cracks, dust, scuffs).
Godot does the duplication and compositing.

---

## 1. Asset inventory

| Asset | Native size | Generator | Output path |
|---|---|---|---|
| Light tile | 64x64 | **PIL procedural** | `godot/assets/sprites/tiles/medieval/light.png` |
| Dark tile | 64x64 | **PIL procedural** | `godot/assets/sprites/tiles/medieval/dark.png` |
| Floor overlay (transparent) | 512x512 (256→2× nearest) | PixelLab pixflux | `godot/assets/sprites/ui/floor_overlay_medieval.png` |
| Wood frame atlas | 48x48 (3x3 of 16px cells) | PixelLab pixflux + PIL slice | `godot/assets/sprites/ui/frame_medieval.png` |
| Backdrop tile | 128x128 | PixelLab pixflux | `godot/assets/sprites/ui/backdrop_medieval.png` |

Total PixelLab API calls: **3** (1 overlay + 1 frame + 1 backdrop). Tiles
are PIL-procedural (zero API cost). One tile per color; the 2×2 sub-
stone variant was tried and dropped because the interior crosses read
as visual noise at the actual board scale.

### Why this layered split

The two failure modes for a tiled chessboard are: (a) the tile texture
is too busy and the 8×8 repeat reads as a polka-dot grid, (b) the tile
texture is too plain and the floor reads as flat plastic. The
plain-tile + macro-overlay split sidesteps both: the per-tile sprite
is **deliberately plain** (uniform stone with subtle edge shading), so
identical adjacency is invisible; the **overlay** is one board-sized
non-tiling PNG that sprinkles natural detail (moss, hairline cracks,
dust, scuffs) across the full 8×8 area at irregular positions, so the
detail itself never repeats. Net effect: the grid reads as one
continuous floor with character.

---

## 2. Generation pipeline

Script: `tools/stages/gen_medieval.py`. Models the same atoms-with-PIL-
post pattern used by [../sprites/wizard_vfx.py](../sprites/wizard_vfx.py)
and [../sprites/gen_sprites.py](../sprites/gen_sprites.py).

```
load PIXELLAB_API_KEY from .env
for each asset:
    pixellab.generate_image_pixflux(prompt + style_suffix, size, seed)
    save raw to tools/stages/_pixellab_cache/<asset>_seed<n>.png
    run PIL reliability pass (see §3)
    write final PNG to godot/assets/sprites/...
```

Cache-on-seed mirrors `wizard_vfx.py:cache_path` so re-runs reuse the
same raw PixelLab bytes; only the PIL post-pass re-executes when we
tweak seam logic. `--force` bypasses cache, `--only <group>`
regenerates one group (`tiles | overlay | frame | backdrop`).

### 2.1 Tiles — PIL procedural

Both tiles are drawn in PIL, no PixelLab call. Why procedural:

- PixelLab repeatedly added internal cracks / mortar / structure even
  when prompted not to, breaking the seam-alignment requirement.
- We need precise control over the groove geometry so adjacent tiles
  butt seamlessly across the whole 8×8 board.
- "Interesting" detail comes from the macro overlay layer, so the
  stone face only needs to read as a believable flat surface.

Per-tile shape:

- Flat fill in a warm grey-brown tone (light: `(212,198,170)`, dark:
  `(108,94,78)` — same hue family, different brightness).
- Very subtle speckle (±4 brightness on ~10% of pixels, deterministic
  seed) so the surface isn't a flat painted color.
- Darker groove (1px) at every outer edge; when two tiles butt, the
  combined 2px joint reads as a hewn stone seam.
- 1px lighter bevel one row inside the groove for hint-of-depth.

All "imperfections" (chipping, color jitter on grooves) were tried and
dropped — they read as pasted-on noise rather than wear.

### 2.2 Floor overlay — board-sized non-tiling detail layer

ONE 512×512 transparent PNG carrying every macro-level detail feature
that would otherwise repeat if it lived on the tile. Prompt:

```
scattered organic detail on a fully transparent background — small
patches of green-grey moss, a few thin hairline cracks, light dust
streaks, occasional small dark scuffs and pebbles. Distribution is
IRREGULAR and SPARSE (about 60% of the canvas is empty transparent
background) and spread asymmetrically across the canvas with NO
repeating pattern, NO grid alignment, NO central composition, NO
border. The details should look like natural wear scattered randomly
across a large stone floor. Pixel art style, soft outlines, no single
feature larger than 60 pixels.
```

Generated with `no_background=True` so the result is RGBA with most
pixels fully transparent.

In Godot the overlay is composited as a single `TextureRect` parented
to `board_holder` directly above the `GridContainer`, sized to fill
the 8×8 grid (`SQ_SIZE * 8`), `mouse_filter = MOUSE_FILTER_IGNORE` so
clicks pass through to the squares underneath.
`stretch_mode = STRETCH_KEEP_ASPECT_COVERED` so the overlay scales
with nearest-neighbor filtering to the actual board size.

The overlay is **only added when stage == "medieval"** — classic and
moon stages skip it entirely.

### 2.3 Wood frame — atlas layout

PixelLab generates ONE 48x48 image containing a 3x3 atlas of carved-
wood border pieces (corner / edge / corner stacked top-to-bottom, each
16x16). Prompt:

```
3x3 sprite atlas on a 48x48 canvas, each cell exactly 16x16. Top row:
top-left corner, top edge, top-right corner of a carved dark oak wood
picture frame with iron rivets. Middle row: left edge, blank center,
right edge. Bottom row: bottom-left corner, bottom edge, bottom-right
corner. The corners are L-shaped wood joinery. The edges are straight
wood beams. Ornamental but readable at small scale. No text, no
background bleed between cells.
```

PIL post-pass slices the 48x48 into the 9 cells, asserts each cell is
exactly 16x16, and re-saves as a single 48x48 atlas. The Godot side
wraps it in a `NinePatchRect` with `patch_margin = 16` on all sides;
the engine then stretches the edges to whatever board size we pass.
Border thickness in-game = 16px on every side regardless of board
dimensions.

### 2.4 Backdrop — full-screen tiling tile

Single 128x128 tileable tile. Prompt:

```
top-down 128x128 pixel art seamless cobblestone wall texture, dense
uniform field of small irregular grey-brown stone bricks packed tight
with thin dark mortar lines between every brick, EDGE-TO-EDGE bricks
that cover the entire canvas with no central focal point, no
medallion, no circle, no vignette, no border, no shadow, FLAT uniform
mid-tone lighting across the whole image, opaque, muted desaturated
palette, ready to tile seamlessly with itself in all directions like a
repeating wallpaper texture
```

Goes on a `TextureRect` parented behind everything in `GameScene`,
with `stretch_mode = STRETCH_TILE`, anchored to fill the viewport.

---

## 3. Reliability passes (PIL post-processing)

PixelLab does not guarantee dimensions, edge-tileability, or alpha.
The post-pass is what makes the assets reliable.

### 3.1 Tile reliability

Tiles are procedurally drawn so most reliability concerns from a
PixelLab pipeline are gone by construction (correct dimensions,
opaque, identical cross-tile edges). The only step needed:

1. **Visual assertion image**: write
   `tools/stages/_inspect_medieval_tiles.png` — a full 8×8 checkerboard
   built from the two tiles. Confirms the procedural drawer produced
   the expected joint pattern.

### 3.2 Overlay reliability

For the 512x512 overlay PNG:

1. **Dimension assert**: `img.size == (512, 512)`.
2. **Mode assert**: RGBA. PixelLab's `no_background=True` should
   produce this; we just convert if not.
3. **Visual assertion image**: write
   `tools/stages/_inspect_medieval_overlay.png` — composite the
   overlay on top of an 8×8 checkerboard of the saved tiles, scaled
   so the overlay covers the full board. Confirms the detail reads
   well against the floor it'll sit on.

### 3.3 Frame reliability

For the 48x48 atlas PNG:

1. **Dimension assert**: `img.size == (48, 48)`.
2. **Cell slice + per-cell dimension assert**: 9 cells each 16x16,
   asserted explicitly.
3. **Center cell zeroed**: middle cell forced fully transparent
   (NinePatch ignores it but PixelLab might draw something there).
4. **Edge continuity**: the rightmost column of the top-edge cell must
   match the leftmost column of the top-right corner cell, and so on
   around the ring. Mismatches are blended with a 1-pixel feather so
   the stretched edges meet the corners without a visible step.
5. **Visual assertion image**: write
   `tools/stages/_inspect_medieval_frame.png` — render the NinePatch
   stretched to the actual in-game size (`SQ_SIZE * 8 + 12 = 588px`)
   so we can confirm the joinery before shipping.

### 3.4 Backdrop reliability

For the 128x128 backdrop PNG:

1. **Dimension assert**: `img.size == (128, 128)`.
2. **Opacity assert**: fully opaque.
3. **Edge-wrap fix**: per-axis seam blend (column 0 ↔ column 127, row
   0 ↔ row 127, average + 1px feather).
4. **Brightness clamp**: mean luminance must fall in `[0.18, 0.32]`
   (mid-dark range). Outside the range, multiply RGB until inside.
   Stops PixelLab from returning a too-bright backdrop that fights
   the foreground.
5. **Visual assertion image**: write
   `tools/stages/_inspect_medieval_backdrop.png` — the tile rendered
   in a 4x4 grid (512x512) so seams are visible at scale.

---

## 4. Godot wiring

### 4.1 SpriteFactory

`tile_texture_for_stage(is_dark, stage)` ([SpriteFactory.gd:221](../../godot/engine/SpriteFactory.gd#L221))
already does what we need — single light/dark per stage. The variant
param was added during prototyping and stays as a no-op default (`0`)
for forward-compatibility, but medieval ships single tiles so it's
unused for this stage.

Three helpers added next to it:

```gdscript
static func frame_texture_for_stage(stage: String) -> Texture2D
static func backdrop_texture_for_stage(stage: String) -> Texture2D
static func floor_overlay_texture_for_stage(stage: String) -> Texture2D
```

Each loads its single PNG (paths from §1) and caches by name. Returns
`null` for stages that don't have the asset (classic, moon) — callers
check for null and skip the corresponding overlay layer.

### 4.2 GameScene

Three surgical edits in [GameScene.gd](../../godot/scenes/GameScene.gd):

**(a) Backdrop** — add a backdrop `TextureRect` as the FIRST child of
the root `VBoxContainer` (so it sits behind everything else). Set
`stretch_mode = STRETCH_TILE` so the 128×128 tile fills the viewport.
Mouse filter ignore. Texture is set to the medieval backdrop only when
`state.config.stage == "medieval"`; left null otherwise.

**(b) Wood frame** — at lines 292-305, add a `NinePatchRect` driven by
the wood atlas (only when stage is medieval). Patch margins = 16 on
all sides. The existing dual-`ColorRect` flat frame stays in place for
classic/moon.

**(c) Floor overlay** — after the `GridContainer` is built and before
`anim_overlay`, add a `TextureRect` that holds the floor overlay PNG,
only when stage is medieval. `stretch_mode = STRETCH_KEEP_ASPECT_COVERED`,
sized to fill `board_holder` (`SQ_SIZE * 8` square). Mouse filter
ignore so clicks fall through to squares.

The backdrop, frame, and overlay only render for medieval; classic
and moon keep their existing flat backgrounds. This keeps the change
purely additive — no change to the look of the existing two stages.

### 4.3 MainMenu

Extend the stage picker at [MainMenu.gd:71-81](../../godot/scenes/MainMenu.gd#L71-L81):

```gdscript
opt.add_item("Medieval", 2)
opt.set_item_metadata(2, "medieval")
```

And update the `current` lookup so `"medieval"` selects index 2.

---

## 5. Acceptance criteria

Before merging:

1. All 5 PNGs present at the paths in §1, with dimensions matching
   exactly.
2. The four `_inspect_medieval_*.png` visual-assertion images render
   without visible seams or broken joinery.
3. Booting the game with `stage = "medieval"` produces:
   - Cohesive 8×8 floor of plain stone (light + dark tones, same
     material).
   - Macro detail (moss, cracks, dust, scuffs) scattered across the
     board with no visible repetition.
   - A wood-framed border around the board, joinery clean at corners.
   - A tiling stone backdrop covering the entire viewport behind the
     side rails and top bar.
4. Booting `stage = "classic"` and `stage = "moon"` still renders
   identically to current main — the change is fallback-safe.
5. No GDScript-side procedural pixel drawing introduced. All pixel art
   is from PixelLab + PIL post-pass; Godot only loads PNGs.

---

## 6. Run order

```powershell
# 1. Generate the 5 atoms (cached, idempotent on rerun)
python tools/stages/gen_medieval.py

# 2. Reload Godot — autoreimport picks up the new PNGs

# 3. (After Godot Web export exists) screenshot via Playwright,
#    iterate prompts in gen_medieval.py if anything looks off
```

`--force` to bypass the PixelLab cache. `--only tiles|overlay|frame|backdrop`
to regenerate one group.
