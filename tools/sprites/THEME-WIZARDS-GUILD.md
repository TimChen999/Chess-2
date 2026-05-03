# Wizards' Guild Theme — Implementation Guide

This is a self-contained guide for a fresh Claude Code session to take the
existing 9-piece chess set and reskin it as a "Wizards' Guild" theme,
then produce matching animations and three magical-ability VFX.

The base sprites are already at `godot/assets/sprites/anim/pieces/<color>/<piece>/static.png`
in a clean flat-white + outline + right-edge-shadow palette (suite palette
defined in [restyle.py](restyle.py)). They are the *reference* — keep
each piece's silhouette intact and add small themed accessories on top.

---

## 1. Prerequisites

**PixelLab MCP** must be wired up (the Python SDK at `pip install pixellab`
also works as a fallback — see existing `gen_sprites.py` for SDK examples).
To install the MCP:

1. Add to `.mcp.json` next to the existing `playwright` entry:
   ```json
   "pixellab": {
     "command": "npx",
     "args": ["-y", "@pixellab/mcp@latest"],
     "env": { "PIXELLAB_API_KEY": "${env:PIXELLAB_API_KEY}" }
   }
   ```
2. Add `"pixellab"` to `enabledMcpjsonServers` in `.claude/settings.json`.
3. Restart Claude Code. Tools become available as `mcp__pixellab__*`.

**Existing utilities you will reuse** (all in `tools/sprites/`):

| Script | Purpose |
|---|---|
| [restyle.py](restyle.py) | silhouette-preserving repaint into the suite palette (OUTLINE / FILL / SHADOW / HIGHLIGHT) — used to clean a PixelLab inpaint result back into the suite palette if needed |
| [restyle_cape.py](restyle_cape.py) | example of repainting a PixelLab feature into suite palette |
| [gen_sprites.py](gen_sprites.py) | provides `recolor_to_black()` (white → black recolor for the black sibling, after the white inpaint is final) |

**Suite palette** (must match exactly across all new art):

```python
OUTLINE   = (40, 40, 50, 255)     # 1-pixel dark outline + small accents
FILL      = (250, 248, 242, 255)  # body interior cream
SHADOW    = (210, 208, 200, 255)  # right-edge shadow band
HIGHLIGHT = (130, 128, 138, 255)  # secondary accent (e.g., cross-arm top, blade highlight)
```

---

## 2. Theme overview

Each piece is a member of a wizards' guild. Keep the silhouette of the
existing piece intact; add 1–2 small themed accessories (≤15 OUTLINE
pixels, ≤8 HIGHLIGHT pixels) so the set stays cohesive and readable
at sprite scale.

| piece | role | accessory to add | replaces |
|---|---|---|---|
| **pawn** | apprentice mage | tiny 4-point star on chest (5–7 px) | — (currently plain) |
| **knight** | arcane cavalry | small runic mark on horse's flank (4–6 px) | — |
| **bishop** | **wizard** | **5-point star on mitre face**, embossed 2-tone (replace current cross) | the Latin cross |
| **rook** | mage tower | small orb sitting in the center crenellation (3 px) | — |
| **queen** | high enchantress | small gem in the center crown spike (1–2 px) | — |
| **king** | archmage | **orb-of-power** (just an orb, no cross) on top of the head | the cross-on-orb |
| **bandit_pawn** | hood-mage thief | small dagger-rune mark on the cape (3–5 px) | — (cape stays) |
| **alter_knight** | arcane unicorn | single HIGHLIGHT pixel at the horn tip (1 px) | — |
| **assassin_bishop** | battle-wizard | star on mitre (inherits from bishop change) + sword stays | — |

**Visual budget at 64×64**: each accessory is 5–15 pixels. More than
that and the body fights for attention.

---

## 3. Per-piece workflow

For **each piece** below, follow this loop:

1. **Look at the current sprite** at `godot/assets/sprites/anim/pieces/white/<piece>/static.png`. It is your reference for silhouette + body.
2. **Decide accessory placement** by reading the existing pixels (e.g. the bishop's mitre face is rows 5–13; that's where the star goes).
3. **Add the accessory** via PixelLab inpaint. Build a mask covering only the accessory region (e.g. the mitre face for the bishop's star, the head crown for the king's orb-of-power). Prompt with the suite palette spelled out and the accessory shape described concretely (e.g. *"small 5-point star embossed on the bishop's mitre, dark outline plus light highlight on upper-left, cream-white pixel-art chess piece, suite palette of dark navy outline + cream interior"*). Iterate guidance 9–10. Score each candidate on `body_identity` outside the mask (must stay 1.0000) + dark-pixel count inside the mask (must land in the per-piece budget below). Reject and re-roll candidates that fail.
4. **Recolor black** via `gen_sprites.recolor_to_black()` and save to `black/<piece>/static.png`.
5. **VERIFY** (next section). Do not move on until verification passes.

### Special steps

**Bishop cross → star**:
- Remove existing cross pixels (find OUTLINE/HIGHLIGHT pixels in mitre rows 8–19, set them back to FILL).
- Paint a 5-point star centered at the mitre face (~9 px in OUTLINE, ~3 px in HIGHLIGHT for embossed look). Same shading rule as the current cross: top-left edge = HIGHLIGHT, bottom-right = OUTLINE.

**King cross-on-orb → orb-of-power**:
- The current king's silhouette includes the cross extending up from a small orb. Replace the cross part with a larger 3×3 or 4×4 orb (filled circle) sitting where the cross used to be.
- Mask the top region (head + cross) and inpaint with PixelLab: prompt for *"a single round dark orb-of-power resting on top of the king's head, no cross, no plus-sign, pixel art, suite palette."* Verify the new silhouette has no cross arms (no thin 1-px-wide rows above the orb).

---

## 4. Verification — DO THIS AFTER EACH SPRITE, BEFORE CONTINUING

For every piece you change, run these checks. **Do not move on to
animations until every static passes.** The user explicitly asked for
this gate.

### 4a. Mechanical checks (script them)

```python
# Pseudocode — write a small verifier that loads the pre-change sprite
# and the inpainted result, then asserts:
- silhouette outside-of-feature region is byte-identical to the
  pre-change sprite (body_identity = 1.0000)
- accessory pixel count is within budget (5–15 dark)
- bilateral symmetry of HEAD region (where applicable) ≥ 0.95
- white/black recolor masks match at 100%
- only suite-palette colors present (no stray RGB values from the
  PixelLab inpaint — if any leak through, run the result through
  restyle.py to snap to the suite palette)
```

### 4b. Visual character check (read the file with your image tool)

Open the new white sprite and the new black sprite. Ask yourself:

- **Identity**: Can I tell at a glance what role this piece plays
  (apprentice / wizard / archmage / mage tower / etc.) without looking
  at file names?
- **Theme cohesion**: Does the accessory feel like it belongs to a
  wizards' guild (stars, runes, orbs, gems) — not a knight order or
  religious order?
- **Suite consistency**: Is the rendering style (outline weight,
  shading direction, fill color) identical to the unchanged pieces?
- **Readable at small size**: Squint at the sprite. Is the silhouette
  + accessory still distinguishable? If the accessory disappears at
  squint distance, it's too subtle.
- **Centered**: Is the accessory snapped to the body's actual visual
  center, not the inpaint mask's bbox center? Score candidates by the
  X-distance from accessory centroid to body centroid for the head row
  range, and re-roll with a tighter mask if it lands more than 1 px off.

### 4c. Side-by-side diff

For each changed piece, save a temporary side-by-side image:
**[unchanged previous sprite] | [new themed sprite] | [silhouette diff
overlay]**. Confirm the silhouette is identical except where the
accessory replaced/added pixels.

**If any check fails, fix the sprite before moving on.** Don't ship a
partially-themed set.

---

## 5. Animations

The current animation strips at `godot/assets/sprites/anim/pieces/<color>/<piece>/<anim>.png`
are 32×32 per-frame procedural drawings (see [generate_sprites.py](generate_sprites.py)
for the procedural code). They look stylistically different from the
64×64 AI statics — there's a brief style shift when a piece animates.

### 5a. Frame layout

Each animation is a **horizontal strip** at FRAME×FRAME pixels per
frame. Convention used by [generate_sprites.py](generate_sprites.py):

| anim | frames | meaning |
|---|---|---|
| `static` | 1 | idle (already done — the work above) |
| `move` | 6 | piece slides/floats to the next square |
| `attack` | 6 | piece performs its attack motion |
| `hit` | 3 | piece flinches when struck |
| `death` | 5 | piece is removed from the board |
| `move_jump` | 7 | knight + alter_knight only — leaping move |
| `attack_lunge` | 7 | alter_knight only — horn-charge attack |

### 5b. Themed animation guidelines

For **every piece**:
- **move**: small upward float (–2 px y-offset) + fade-back-down. The wizards' guild floats — they don't walk. 6 frames: ease-out up, hold, ease-in down.
- **attack**: piece tilts slightly toward the target (3–4 px horizontal lean) and glows on the head accessory (HIGHLIGHT pulse on the star/orb/gem). 6 frames.
- **hit**: piece flashes (1 frame fully OUTLINE-tinted, then 2 frames recovering). 3 frames.
- **death**: piece dissolves into 4–6 falling sparkle pixels then fades to transparent. 5 frames.

Use PixelLab inpaint per-frame, with the previous frame as the
init_image and a small motion delta in the prompt. If frame-to-frame
drift breaks the silhouette, tighten the inpaint mask to only the
moving region (e.g. mask just the head accessory for the attack-frame
glow) and re-roll until consecutive frames pass the §5c verification.

**Keep the resolution choice consistent.** If you upgrade animations
to 64×64 to match the statics, update the Godot scene's frame size
too (search for `FRAME = 32` in `generate_sprites.py` and also check
the AnimatedSprite2D nodes in the Godot project).

### 5c. Animation verification

After each `<piece>/<anim>.png` is generated, check:

- Frame count matches the table above (file width = FRAME × frame_count).
- Frame 1 silhouette matches the static silhouette (sanity — animation
  starts from the resting pose).
- Animation loops cleanly: last frame is visually similar to first
  for `move`; last frame fades to transparent for `death`; first
  frame matches static for `attack` and `hit`.
- Suite palette only (no stray colors from PixelLab interpretation).

---

## 6. Ability VFX

Three abilities, replacing the current `cannon_resolve` / `lightning_strike` /
`debris_fall` FX. New FX live at `godot/assets/sprites/anim/fx/<name>.png`
as horizontal strips, FRAME×FRAME per frame.

For all three, keep the same suite palette but you may add **one
saturated accent color** per ability (fireball orange, lightning yellow,
magic rocks purple) so the abilities pop visually against the muted
piece sprites.

### 6a. Fireball (replaces `cannon_resolve`)

A meteor crashing from offscreen, then an expanding explosion.

| frame | content |
|---|---|
| 1–6 | fireball falls from above the canvas. Frames show the fireball entering top edge, descending, growing slightly larger. Trailing flame sparks behind it. |
| 7 | impact frame — fireball hits the center block. White hot flash. |
| 8–12 | explosion expands outward from center to the 8 adjacent blocks. Frame 8 is a small bright core; each subsequent frame the explosion widens. |
| 13–14 | explosion dissipates — embers and smoke fade. |

**Total**: 14 frames. Strip width = 14 × FRAME.

PixelLab prompts (inpaint per frame, init = previous frame):
- frames 1–6: *"pixel-art fireball with orange/red flame trails, dropping from the top of the canvas, [N]px lower than previous frame, transparent background"*
- frame 7: *"pixel-art bright white-hot impact flash, fireball just hit the ground, transparent background"*
- frames 8–12: *"pixel-art explosion expanding outward from center, orange and yellow flames, [radius]px wide, transparent background"*
- frames 13–14: *"pixel-art smoke and embers dissipating, mostly transparent dark grey wisps"*

### 6b. Lightning bolt (replaces `lightning_strike`)

Single bolt instantly striking from the top of the screen.

| frame | content |
|---|---|
| 1 | dim charging glow at the top of the canvas (subtle yellow tint) |
| 2 | the bolt: a jagged white-yellow line from canvas top to the target block, with branching forks |
| 3 | bright flash at the impact point (full white) |
| 4 | bolt fading, only the impact glow remains |
| 5–6 | impact glow shrinks and fades to transparent |

**Total**: 6 frames. Strip width = 6 × FRAME.

PixelLab prompts:
- frame 1: *"pixel-art faint yellow charging glow at the top of canvas"*
- frame 2: *"pixel-art lightning bolt — jagged white-yellow zigzag line from top to bottom, with 2–3 small branching forks, transparent background"*
- frame 3: *"pixel-art bright white impact flash at the bottom of canvas"*
- frame 4–6: *"pixel-art fading yellow glow at impact point, gradually disappearing"*

### 6c. Magic rocks (replaces `debris_fall`)

Floating purple-glowing rocks fall from offscreen, hit the target, generate an on-hit effect.

| frame | content |
|---|---|
| 1–5 | 3–4 jagged dark rock chunks with a faint purple aura fall from above the canvas; each frame they descend ~6 px and rotate slightly. |
| 6 | rocks hit the ground — impact frame, rocks at their lowest point, with a small dust burst. |
| 7–9 | on-hit effect: a swirl of purple sparkles + small dust cloud spreading outward from impact point. Sparkles fade frame by frame. |

**Total**: 9 frames. Strip width = 9 × FRAME.

PixelLab prompts:
- frames 1–5: *"pixel-art jagged grey rocks with faint purple magical aura, falling from top of canvas, transparent background"*
- frame 6: *"pixel-art rocks hitting the ground with a dust impact burst, brown dust + purple sparkles, transparent background"*
- frames 7–9: *"pixel-art purple magic sparkles and dust cloud spreading outward, fading"*

### 6d. VFX verification

For each ability:
- All frames have transparent background (no white squares).
- Frame-to-frame motion is smooth (no jarring jumps in the falling
  fireball / rocks).
- Final frame fades to (mostly) transparent so the FX doesn't leave
  permanent pixels on the board.
- Strip width = FRAME × frame_count exactly.
- Suite palette + the one allowed accent color per ability — no
  stray hues.

---

## 7. Order of operations

Do them in this order so each step has its dependency ready:

1. **Static sprites** for all 9 pieces (white + black). **Verify each one
   against §4 before moving on.** Do not start animations with a partially-
   themed set.
2. **Animations** for all 9 pieces (move, attack, hit, death, plus
   knight-only `move_jump` and alter_knight-only `attack_lunge`).
   Verify per-piece per-anim against §5c.
3. **Ability VFX** (fireball, lightning, magic rocks). Verify against §6d.
4. Run the game in Godot to confirm the new sprites load without import
   errors and visually fit on the board. (`Project → Export → Web` to
   produce an HTML5 build, then load in Playwright if available.)
5. Commit each phase as a separate commit so reverting individual phases
   is cheap if something looks wrong in-game.

---

## 8. Cost estimate

Approximate PixelLab API call counts (each ~$0.005–0.02):

- Static sprites: 9 pieces × 1–3 PixelLab calls each (inpaint accessory) = ~20 calls
- Animations: 9 pieces × ~25 frames each × 1 PixelLab call per frame = ~225 calls
- VFX: 14 + 6 + 9 = 29 frames × 1 call each = ~29 calls

**Total: ~275 calls, $1.50–$5.50 USD.** Budget for one or two re-rolls
per piece — if a sprite fails §4 or a frame fails §5c, redo just that
one inpaint rather than the whole piece.
