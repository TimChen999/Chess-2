# Sprite design tooling

All sprite-generation code for Chess-2 lives here. The output target is [godot/assets/sprites/](../../godot/assets/sprites/).

| File | Role |
|---|---|
| [generate_sprites.py](generate_sprites.py) | Procedural drawer (PIL) — produces every sprite type: piece animation strips (`move`, `attack`, `hit`, `death`), tile textures, FX, and UI sprites. Also writes a procedural `static.png` per piece, which `gen_sprites.py` later overwrites. |
| [gen_sprites.py](gen_sprites.py) | AI generator (PixelLab Python SDK) — produces only the `static.png` for each piece via pixflux. Supports the 6 base pieces + 3 variants × 2 colors (white via API, black via local recolor). |
| [inpaint_heads.py](inpaint_heads.py) | Thin wrapper that calls `gen_sprites.inpaint_head` for the 4 head-distinct pieces (rook, bishop, queen, king) when the head needs a re-roll without re-rendering the body. |

## Run order

```powershell
# 1. Procedural pass (writes everything, including a placeholder static.png)
python tools/sprites/generate_sprites.py

# 2. AI pass (overwrites just the per-piece static.png with PixelLab art)
python tools/sprites/gen_sprites.py
```

⚠️ Re-running `generate_sprites.py` after `gen_sprites.py` clobbers the AI statics. Either run the procedural pass first (current state), or modify it to skip writing existing `static.png` files.

## AI generator (`gen_sprites.py`)

### What's installed

- `pip install pixellab` (the [PixelLab Python SDK](https://github.com/pixellab-code/pixellab-python)) into Python 3.10 and 3.13 envs
- API key in [.env](../../.env) at project root as `PIXELLAB_API_KEY=...` (gitignored)

### What's already been generated

All 18 chess piece statics live at `godot/assets/sprites/anim/pieces/<color>/<id>/static.png`:

| Piece | White | Black |
|---|---|---|
| pawn / rook / knight / bishop / queen / king | pixflux | procedural recolor |
| bandit_pawn (pawn + cape) | pixflux + base init_image | procedural recolor |
| alter_knight (knight + unicorn horn) | pixflux + base init_image | procedural recolor |
| assassin_bishop (bishop + sheathed sword) | pixflux (no init_image) | procedural recolor |

Total cost for the suite: ~10 PixelLab API calls. Black versions are procedurally recolored from white via local PIL — no API calls.

### How to regenerate

```powershell
# All sprites that don't yet exist
python tools/sprites/gen_sprites.py

# Regenerate everything (10 API calls)
python tools/sprites/gen_sprites.py --force

# Regenerate specific pieces
python tools/sprites/gen_sprites.py --force --only queen alter_knight
```

The script reads `PIXELLAB_API_KEY` from `.env` (or `PIXELLAB_SECRET` if you've renamed it to match the SDK's default).

## Lessons learned

### Bitforge vs. pixflux

PixelLab exposes two main generation primitives:
- `generate_image_pixflux` — text-to-pixel-art, optionally with an `init_image` starting point
- `generate_image_bitforge` — same but with `style_image` for style transfer

We tried bitforge first (anchor pawn → style-transfer all other pieces). At `style_strength=80` (max 100) every output came back as colored noise. `text_guidance_scale`, `extra_guidance_scale`, lower `style_strength` — none of it produced clean output.

Solution: switched to pixflux for all generation. Style consistency across the suite is enforced by the shared prompt suffix (frontal view, dark outline, smooth shading) rather than `style_image`. Works well enough for chess pieces.

### Variant generation gotcha

For variants where the modification is large (cape on a pawn) or distinctive (horn on a horse's head), `init_image=base` with low `init_image_strength=80` works — the model preserves the silhouette while the prompt paints on the feature.

For variants where the modification is **small** (sword on a bishop's back), the init_image dominates and the prompt is ignored even at the lowest strengths. Solution: drop `init_image` entirely and rely on prompt alone. The variant doesn't share the exact base silhouette, but the feature is visible.

This is encoded in `VARIANTS` in `gen_sprites.py` as the `use_init_image` flag per variant.

### Line-art references confuse pixflux

When the source ref is line-art (just black outlines on white) rather than a 3D photo, do **not** feed it as `init_image`. The model copies the line-art aesthetic and outputs sketchy, washed-out sprites. Use pure text-to-image with a rich prompt instead.

### Picking init_image_strength

Lower strength = more shape fidelity to the init image. Higher = freer reinterpretation. Sweet spot for "shape locked, surface details free" is roughly 100–300; for "use this as a loose hint" go 400–600.

## Future MCP install (optional)

If you want PixelLab tools available *inside* Claude Code conversations (so you can ask "generate a boss piece" mid-session), wire up the official MCP:

1. Add to `.mcp.json` next to `playwright`:
   ```json
   "pixellab": {
     "command": "npx",
     "args": ["-y", "@pixellab/mcp@latest"],
     "env": { "PIXELLAB_API_KEY": "${env:PIXELLAB_API_KEY}" }
   }
   ```
2. Add `"pixellab"` to `enabledMcpjsonServers` in `.claude/settings.json`.
3. Restart Claude Code. Tools become available as `mcp__pixellab__*`.

## Closed-loop with Playwright (post Godot HTML5 export)

```
1. python tools/sprites/gen_sprites.py --force --only <piece>
   (PixelLab generates the new static)
        │
        ▼
2. Re-export Godot to godot/export/web/  (manual until a CLI export script lands)
        │
        ▼
3. Playwright loads index.html, screenshots the board in actual game context
   against light + dark squares, alongside siblings
        │
        ▼
4. Claude critiques: silhouette, palette match, readability at game scale
        │
        ▼
5. Claude updates the prompt in gen_sprites.py and re-runs step 1 → loop
```

The re-export step (2) is the friction. Until a Godot CLI export script lives in this repo, that step is manual.
