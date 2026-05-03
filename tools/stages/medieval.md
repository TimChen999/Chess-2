# Medieval stage — generation plan

Reskin of the board (8x8 grid + frame) and the GameScene-wide backdrop to
match the stylized medieval theme already established by the cards and FX.
No layout changes: square pitch stays at `SQ_SIZE = 72` and the grid stays
8x8 ([GameScene.gd:18](../../godot/scenes/GameScene.gd#L18)). Everything is
added as PNG atoms generated via PixelLab and assembled by Godot's existing
`GridContainer` + `NinePatchRect` + `TextureRect` (TILE) primitives.

PixelLab never generates the grid as a whole image. It only generates
**single repeatable units**: one tile (4 of them, see below), one wood-edge
atlas, one backdrop tile. Godot does the duplication.

---

## 1. Asset inventory

| Asset | Native size | Generator | Output path |
|---|---|---|---|
| Light tile A | 64x64 | PixelLab pixflux | `godot/assets/sprites/tiles/medieval/light_a.png` |
| Light tile B | 64x64 | PixelLab pixflux | `godot/assets/sprites/tiles/medieval/light_b.png` |
| Dark tile A  | 64x64 | PixelLab pixflux | `godot/assets/sprites/tiles/medieval/dark_a.png`  |
| Dark tile B  | 64x64 | PixelLab pixflux | `godot/assets/sprites/tiles/medieval/dark_b.png`  |
| Wood frame atlas | 48x48 (3x3 of 16px cells) | PixelLab pixflux + PIL slice | `godot/assets/sprites/ui/frame_medieval.png` |
| Backdrop tile | 128x128 | PixelLab pixflux | `godot/assets/sprites/ui/backdrop_medieval.png` |

Total PixelLab API calls: **6** (4 tiles + 1 frame + 1 backdrop).
Cost: a few cents.

The 4-tile design (2 light + 2 dark variants) breaks up the obvious 1-tile
repeat without exploding the seam matrix. Variant per square is picked
deterministically:

```
variant = ((file * 7 + rank * 13) >> 1) & 1
```

So `a1` always picks the same variant on every render — no flicker, no RNG.

---

## 2. Generation pipeline

New script: `tools/stages/gen_medieval.py`. Models the same
atoms-with-PIL-post pattern used by [../sprites/wizard_vfx.py](../sprites/wizard_vfx.py)
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
same raw PixelLab bytes; only the PIL post-pass re-executes when we tweak
seam logic. `--force` bypasses cache, `--only <asset>` regenerates one.

### 2.1 Tiles — prompt template

Style suffix shared across all 4 tile prompts to lock the look:

```
, top-down 64x64 pixel art floor tile, EDGE-TO-EDGE coverage (no border,
no padding, no vignette, no shadow), uniform mid-tone shading across the
whole tile, opaque, no transparency, single material, ready to tile
seamlessly with itself
```

Per-tile descriptions:

- **light_a**: "weathered cream limestone flagstone with faint chisel
  marks and a subtle warm beige tint"
- **light_b**: "same cream limestone flagstone with a small hairline
  crack across one corner and slightly more wear"
- **dark_a**: "warm aged oak wood plank with visible grain running
  diagonally, deep umber tone"
- **dark_b**: "same warm aged oak plank with a small dark knot and
  slightly different grain direction"

Both within-pair variants must share the same dominant color so a `light_b`
neighbor next to a `light_a` reads as "the same floor, slightly varied,"
not "two different stages glued together." The PIL pass enforces this
quantitatively (§3.1).

### 2.2 Wood frame — atlas layout

PixelLab generates ONE 48x48 image containing a 3x3 atlas of carved-wood
border pieces (corner / edge / corner stacked top-to-bottom, each 16x16).
Prompt:

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
exactly 16x16, and re-saves as a single 48x48 atlas. The Godot side wraps
it in a `NinePatchRect` with `patch_margin = 16` on all sides; the engine
then stretches the edges to whatever board size we pass. Border thickness
in-game = 16px on every side regardless of board dimensions.

### 2.3 Backdrop — full-screen tiling tile

Single 128x128 tileable tile. Prompt:

```
top-down 128x128 pixel art tavern stone floor, large rough flagstones
with grout lines, edge-to-edge coverage, uniform mid-tone shading, opaque,
muted desaturated palette so it sits behind UI without competing, ready
to tile seamlessly with itself in all directions
```

Goes on a `TextureRect` parented behind everything in `GameScene`, with
`stretch_mode = STRETCH_TILE`, anchored to fill the viewport.

---

## 3. Reliability passes (PIL post-processing)

PixelLab does not guarantee dimensions, edge-tileability, or alpha. The
post-pass is what makes the assets reliable.

### 3.1 Tile reliability

For each of the 4 tile PNGs:

1. **Dimension assert**: `img.size == (64, 64)`. If PixelLab returned a
   different size, resize via `Image.NEAREST` and warn.
2. **Opacity assert**: every pixel `alpha == 255`. If any pixel is
   transparent, fail loudly — a transparent tile would let the backdrop
   leak through and break the chess look.
3. **Edge-wrap fix**: copy the left edge column average to the right
   edge column (and top row to bottom row) using a 2-pixel feather, so
   the tile butts seamlessly against itself. Same algorithm applied
   independently per axis.
4. **Cross-variant color clamp**: for each `(light_a, light_b)` and
   `(dark_a, dark_b)` pair, compute the mean RGB. If pair-mean RGB
   distance > threshold (15 in 0–255), shift `*_b` toward `*_a` by an
   alpha blend until under threshold. Keeps "same floor, slight variation"
   coherence quantitative, not eyeballed.
5. **Visual assertion image**: write
   `tools/stages/_inspect_medieval_tiles.png` — a 4x4 grid of all 4
   variants tiled twice in each direction. Easy to eyeball whether
   seams disappear.

### 3.2 Frame reliability

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

### 3.3 Backdrop reliability

For the 128x128 backdrop PNG:

1. **Dimension assert**: `img.size == (128, 128)`.
2. **Opacity assert**: fully opaque.
3. **Edge-wrap fix**: same horizontal + vertical seam blend as tiles.
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

Extend [SpriteFactory.gd:218-231](../../godot/engine/SpriteFactory.gd#L218-L231):

```gdscript
static func tile_texture_for_stage(is_dark: bool, stage: String,
                                   variant: int = 0) -> Texture2D:
    var suffix := "_b" if variant == 1 else "_a"
    var key := "tile:%s:%d:%d" % [stage, 1 if is_dark else 0, variant]
    if _cache.has(key): return _cache[key]
    var name := ("dark" if is_dark else "light") + suffix
    var path := "%s/tiles/%s/%s.png" % [ASSET_ROOT, stage, name]
    var tex := _load_single(path)
    if tex == null:
        # Fallback chain: medieval -> classic single tile.
        tex = _load_single("%s/tiles/%s/%s.png" % [ASSET_ROOT, stage,
            "dark" if is_dark else "light"])
    if tex == null:
        tex = _load_single("%s/tiles/classic/%s.png" % [ASSET_ROOT,
            "dark" if is_dark else "light"])
    _cache[key] = tex
    return tex
```

`classic` and `moon` fall through to the single-tile fallback (their
existing files), so this is backwards-compatible. `medieval` uses the
new `_a`/`_b` files.

Add two helpers:

```gdscript
static func frame_texture_medieval() -> Texture2D
static func backdrop_texture_medieval() -> Texture2D
```

Each loads its single PNG and caches by name.

### 4.2 GameScene

Two surgical edits in [GameScene.gd](../../godot/scenes/GameScene.gd):

**(a) Tile variant selection** — at lines 847-848, replace:

```gdscript
var stage := state.config.stage if state.config != null else "classic"
bg.texture = SpriteFactory.tile_texture_for_stage(is_dark, stage)
```

with:

```gdscript
var stage := state.config.stage if state.config != null else "classic"
var variant := ((f * 7 + r * 13) >> 1) & 1
bg.texture = SpriteFactory.tile_texture_for_stage(is_dark, stage, variant)
```

**(b) Frame + backdrop** — replace the two flat `ColorRect` frames at
lines 292-305 with a `NinePatchRect` driven by the wood atlas (only
when stage == "medieval"; classic/moon keep the existing dual-ColorRect
frame). Add a backdrop `TextureRect` as the FIRST child of the root
VBox in `_build_ui()` so it sits behind everything else.

The backdrop only renders when the stage is medieval; classic/moon get
the existing flat viewport-clear background. This keeps the change
purely additive — no change to the look of the existing two stages.

### 4.3 MainMenu

Extend the stage picker at [MainMenu.gd:75-80](../../godot/scenes/MainMenu.gd#L75-L80):

```gdscript
opt.add_item("Medieval")
opt.set_item_metadata(2, "medieval")
```

And update `_on_stage_selected` only if it lists explicit stage values.

---

## 5. Acceptance criteria

Before merging:

1. All 6 PNGs present at the paths in §1, with dimensions matching exactly.
2. The three `_inspect_medieval_*.png` visual-assertion images render
   without visible seams or broken joinery.
3. Booting the game with `stage = "medieval"` produces:
   - 4 visually distinct but tonally coherent tile variants distributed
     across the 8x8 board.
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
# 1. Generate the 6 atoms (cached, idempotent on rerun)
python tools/stages/gen_medieval.py

# 2. Reload Godot — autoreimport picks up the new PNGs

# 3. (After Godot Web export exists) screenshot via Playwright,
#    iterate prompts in gen_medieval.py if anything looks off
```

`--force` to bypass the PixelLab cache. `--only tiles|frame|backdrop`
to regenerate one group.
