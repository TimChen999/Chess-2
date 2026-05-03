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

**Suite palette** — the four base colors all body silhouettes use:

```python
OUTLINE   = (40, 40, 50, 255)     # 1-pixel dark outline + small accents
FILL      = (250, 248, 242, 255)  # body interior cream
SHADOW    = (210, 208, 200, 255)  # right-edge shadow band
HIGHLIGHT = (130, 128, 138, 255)  # secondary accent (e.g., cross-arm top, blade highlight)
```

**Accent palette** — saturated colors usable for *small accessory
items only* (a hood, saddle blanket, banner, mitre band, gem, glow,
dagger mark). The set spans the rainbow so pieces read distinctly —
each piece picks 1–2 accent colors that fit its role:

```python
# Cool / arcane
BLUE          = ( 76, 124, 196, 255)  # arcane cavalry, frost robes
BLUE_SHADOW   = ( 42,  78, 138, 255)
TEAL          = ( 70, 168, 162, 255)  # enchantress, mist
TEAL_SHADOW   = ( 38, 110, 108, 255)

# Warm / fire / blood
CRIMSON       = (190,  60,  72, 255)  # battle-wizard, fire-mage, bandit
CRIMSON_SHADOW= (132,  32,  44, 255)

# Nature / apprentice
GREEN         = ( 96, 156,  78, 255)  # apprentice mage, druid
GREEN_SHADOW  = ( 56, 100,  44, 255)

# Royal / archmage
PURPLE        = (126,  91, 176, 255)  # archmage, ceremonial
PURPLE_SHADOW = ( 74,  52, 117, 255)

# Metals / glow
GOLD          = (217, 178,  60, 255)  # crown trim, gems, orbs
GOLD_SHADOW   = (156, 122,  32, 255)
SILVER        = (192, 196, 210, 255)  # rune marks, magic etching
PINK_GLOW     = (228, 122, 200, 255)  # arcane glow (unicorn horn, etc.)
```

---

## 2. Theme overview

Each piece is a member of a wizards' guild. The change is **on the body
and around it** (clothes + held items + a small banner / saddle / sash),
**not on the head**. The head silhouette stays exactly as it is —
don't add hats, don't paint mitre bands, don't recolor crowns.

### 2.1 What stays untouched

- **Silhouette**: the existing alpha mask of every piece is preserved
  byte-for-byte. The only exception is the king, whose cross-on-orb
  is replaced with a single orb (silhouette intentionally drops the
  cross arms — see §3 special step).
- **Head region** (top portion of each piece — the "face area" listed
  per-piece below): cream-white interior + dark outline stay as-is.
  *Tiny* crown details (a single gem on king/queen) are allowed if
  they're truly small and clearly secondary to the body changes.
- **Body interior** is cream-white (FILL/SHADOW) by default.
  Accent-color paint lands only inside the per-piece accent zones
  defined in `wizard_statics.py`.

### 2.2 What changes (per piece — the bulk of the work)

Each piece gets **clothes + a held accessory**, painted on the body /
chest / lower-body region. Held items (staff, wand, scepter, sword,
dagger) may extend slightly outside the silhouette to the side or
below — the same way the existing assassin_bishop's sword does.

| piece | role | head region (DON'T touch) | body / clothes / accessory (DO paint) | accent colors |
|---|---|---|---|---|
| **pawn** | apprentice mage | round head (top ~30%) | small spellbook held at chest, short green cloak draped from shoulders down the sides | GREEN + GOLD |
| **knight** | arcane cavalry | horse face + ears | blue saddle blanket on the horse's back with a small silver rune on it | BLUE + SILVER |
| **bishop** | **wizard** | mitre (top ~30%) | tall wizard staff with a gold orb on top, held vertically alongside the body (extends outside silhouette to one side); thin purple sash at the waist | PURPLE + GOLD |
| **rook** | mage tower | crenellation row (top ~12%) | crimson banner ribbon hanging vertically down one side of the tower (extends outside silhouette); small gold magical etching at mid-tower | CRIMSON + GOLD |
| **queen** | high enchantress | crown peaks + collar (top ~30%) | small scepter held at the side (extends outside silhouette), thin teal sash on the gown lower body. *Tiny* teal gem on the central crown spike is OK as a small secondary detail | TEAL + GOLD |
| **king** | archmage | crown structure (replaced — see special step) | long white beard hanging from the face down the upper chest, scepter held at the side (extends outside silhouette), gold sash on the lower body. **Special**: replace the cross-on-orb with a single gold orb-of-power | GOLD + PURPLE |
| **bandit_pawn** | hood-mage thief | hooded head | dagger held at chest level on the body, small crimson rune on the dagger blade. Cape stays as-is (don't repaint it) | CRIMSON + SILVER |
| **alter_knight** | arcane unicorn | horse face + horn (the horn itself stays cream — only its very tip glows) | blue saddle blanket with a small silver harness strap. *Very tiny* pink-magenta glow at the horn's apex (1–2 px max) is OK as a small secondary detail | BLUE + PINK_GLOW |
| **assassin_bishop** | battle-wizard | mitre (top ~30%) | sword stays. Add a thin crimson sash across the body at the level the sword crosses, plus a small gold belt buckle on the sash | CRIMSON + GOLD |

### 2.3 Visual budget at 64×64

- **Body accent items**: 1–2 per piece, each occupying ~30–80 pixels
  inside the body region (NOT in the head region). The body's cream
  interior should still cover the majority of the body — accent
  pixels < ~30% of total interior.
- **Held items extending outside silhouette**: ≤ ~50 px of new
  silhouette outside the original (a thin staff or scepter is fine; a
  full second body is not).
- **Head detail (only king, queen)**: ≤ 3 accent pixels in the head
  region.
- The dark navy OUTLINE on the body silhouette boundary is preserved
  exactly.

---

## 3. Per-piece workflow

The approach is **layered accessories + a light body-texture pass**.
The original chess piece silhouette is **never modified** (except the
king, whose cross is pre-cleared so the orb-of-power can sit on top).
Wizard items are generated as isolated transparent-background PNGs and
composited onto the original.

For each piece:

1. **Body texture pass (procedural).** Take the original cream-white
   sprite and add a *subtle* shading bump: a 1-pixel HIGHLIGHT band
   along the upper-left silhouette boundary (cool reflected light) and
   widen the existing right-edge SHADOW band by 1 px. Suite palette
   only — no accent colors here. This gives the body more sculptural
   depth without changing the silhouette. Procedural, deterministic,
   no API call.

2. **Per-accessory generation (PixelLab pixflux).** For each accessory
   listed for the piece in §2.2:
   - `description = "<accessory>, dark black outline, isolated single object, transparent background, pixel art at 64x64"`
   - `negative_description = "chess piece, person, full body, hand, multiple objects, second <type>"`
   - `image_size = {"width": 64, "height": 64}`
   - `no_background = True`
   - `init_image = None`, `init_image_strength = 0` (let the prompt fully drive)
   - `text_guidance_scale = 12.0`
   - `seed = <varied>` for re-rolls
   The output is a 64×64 transparent-background image containing just
   the accessory.

3. **Snap accessory outline.** Any near-black pixel in the accessory
   (`max channel < 80`) is snapped to the exact suite `OUTLINE = (40,40,50,255)`
   so accessory outlines visually match the piece's existing outline.

4. **Composite accessory.** Find the bbox of opaque pixels in the
   accessory result. If the bbox doesn't match the per-accessory
   target size (within ±20%), reject the seed and re-roll. Otherwise
   resize-by-nearest to the target size, translate so the accessory's
   bbox center hits the per-accessory anchor on the piece canvas, and
   alpha-composite onto the piece. Repeat for each accessory in z-order.

5. **Save white + black.** The same accessory PNG composites onto both
   teams' baselines — the accessory has its own outline + colors that
   read on cream and dark bodies alike.

### Special step — King cross-on-orb → orb-of-power

Pre-clear the cross from the king sprite **before** compositing
accessories. Find the king's "first wide row" (where the head
silhouette becomes ≥ 6 px wide) and erase every opaque pixel above
that row to transparent. Then composite the orb-of-power accessory
onto the cleared head. The silhouette is allowed to drop the cross
arms (this is the only piece where silhouette changes).

---

## 4. Verification — DO THIS AFTER EACH SPRITE, BEFORE CONTINUING

For every piece you change, run these checks. **Do not move on to
animations until every static passes.** The user explicitly asked for
this gate.

### 4a. Mechanical checks (script them)

```python
# Pseudocode — load the original baseline sprite and the composited
# result, then assert:

# Silhouette preservation — the layered approach guarantees the
# original's body silhouette by construction. Verification just
# confirms we didn't accidentally erase it.
- body_silhouette_intersection ≥ 0.99   # original silhouette pixels
    # are still opaque in the result (excludes the silhouette
    # extensions added by accessories like staffs)
- head_silhouette_intersection ≥ 0.95   # original head pixels still
                                        # opaque in result (king
                                        # exempt — cross is cleared)

# Accessory presence — each piece's accessory zone has saturated /
# accent-colored pixels.
- accessory_pixel_count ≥ piece's accessory_min   # at least N opaque
    # pixels in the accessory bbox region that came from the
    # accessory composite (i.e. not in the original sprite)

# Outline cleanness — accessory outlines were snapped to suite OUTLINE.
- no near-black pixels at non-OUTLINE RGB values

# Twin parity — same accessory, both teams.
- accessory_alpha_diff(white_result, black_result) == 0
```

### 4b. Visual character check (read the file with your image tool)

After every regeneration, **open the new white sprite and look at its
head region first**. The head silhouette should match the original
within ~1–2 pixels of margin (PixelLab redraws the whole sprite, so
small shape-edge tweaks are fine, but the head should still be
recognizably the same chess-piece head). Then ask:

- **Head intact**: Does the head still read as the original piece's
  head? Pawn = round head, knight = horse profile, bishop = pointed
  mitre, queen = crown, king = orb-of-power (replaced cross), rook =
  battlements, etc. If the head drifted (mitre lost its point, horse
  lost its mane, etc.), bump `init_image_strength` and re-roll.
- **Body items show clearly**: Can you see the staff / book / sword /
  cloak / sash / etc. listed for that piece? If the prompt items are
  missing or buried, drop strength slightly and re-roll.
- **Body cream is clean**: After the cream-snap pass, the body's
  cream-white is exact suite cream (no pink/yellow tint). If the snap
  produced patchy results, bump strength.
- **Theme cohesion**: Multi-color across the set (one piece should
  not just clone another's accent palette).
- **Readable at small size**: Squint at the sprite. Silhouette + body
  items still distinguishable.

### 4c. Side-by-side diff

For each changed piece, save a temporary side-by-side image:
**[original sprite] | [regenerated sprite] | [head-region overlay]**.
Confirm the head is recognizably the same piece and the body now has
the wizard items.

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
