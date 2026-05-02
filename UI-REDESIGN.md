# UI Redesign — Chess²

Focused redesign covering the four areas you called out (energy bar, ability symbols, buttons, promote menu) plus the underlying structural change that makes the rest of the cleanup possible: replace the decorative right rail with functional player panels, and pin the promote picker to the action.

Keeps the existing pixel-art tabletop feel — every change reuses the cream/dark-wood palette, the 2px hard-outline button style, and `SpriteFactory`'s textures.

---

## Current state (the baseline I'm redesigning)

From [godot/scenes/GameScene.gd](godot/scenes/GameScene.gd):

```
┌─ left spacer (200) ─┬─────────── board column ───────────┬─ right control rail (200) ─┐
│                     │  black panel (HBox above board)    │  CHESS² title (32pt)       │
│                     │    [BLACK | 10-seg bar | num | ⚡] │  ← Menu                    │
│                     │                                    │                            │
│                     │  ┌──────── 8x8 board ────────┐     │  status_label              │
│                     │  │                           │     │  end_label                 │
│                     │  │  per-square: HP top-left  │     │  promo_panel ← bug         │
│                     │  │             FX top-right  │     │                            │
│                     │  └───────────────────────────┘     │  (spacer expand)           │
│                     │                                    │                            │
│                     │  white panel (HBox below board)    │  New game                  │
│                     │    [WHITE | 10-seg bar | num | ⚡] │                            │
└─────────────────────┴────────────────────────────────────┴────────────────────────────┘
```

The right "control" rail is mostly chrome — a brand title, two top-level buttons, a status label, and the misplaced promote picker. The actual gameplay info (energy, abilities) is squeezed into thin horizontal strips above and below the board.

This redesign reclaims the right rail for gameplay info, moves chrome to a top utility bar, and pins the promote picker to the promoting pawn.

---

## A. Energy bar

### Current
- 10 horizontal `TextureRect` segments (14×32 px each, 2px sep) inside the per-side panel
- Numeric readout sits as a separate `Label` next to the bar
- Tag label "BLACK"/"WHITE" precedes the bar
- Both players' bars are visually identical; the active player isn't privileged
- Fills "from inside outward" (toward board edge)

### Issues
1. The horizontal strip puts the bar on the same line as the side tag and the ability card, so all three resources fight for one row of attention
2. The bar + numeric readout duplicate the same info twice on the same line
3. No visual distinction between the side that's about to spend (active) and the side just watching

### Proposed
- **Move energy bars into vertical player panels in the right rail.** One panel per side, stacked top (opponent) → bottom (you). Lichess uses the same convention.
- **Vertical bar, fills upward from the bottom** (Clash Royale / Hearthstone mana convention — "fills up to play"). 10 segments × 12px tall each = 120px, ~24px wide.
- **Drop the numeric readout duplicate** — fold it into the panel header. The panel header reads `White ⚡ 4` with the bar visualizing the same number underneath. One source of truth, two visual treatments (number + bar).
- **Active side gets a soft glow** on the bar; inactive side desaturates ~30%.
- **Drop the per-side tag** ("BLACK"/"WHITE") — the panel's own header carries it.

### Why
- Vertical bars in side panels separate "your resources" from "the board" — the eye doesn't have to compete with piece sprites
- Filling-up direction is universally read as "ready to spend"
- Active glow turns "whose turn is it?" into a parafoveal cue, not something you have to read

### GDScript notes
- Refactor `_build_side_panel(color)` → `_build_player_panel(color)` returning a `VBoxContainer` placed in the right rail
- Bar becomes a `VBoxContainer` of segments, ordered visually bottom-up
- `_render_side_panel` already drives the segment textures via `SpriteFactory.energy_segment_texture(filled)` — no factory change needed, just rotate the layout

---

## B. Ability symbols

### Current (`_make_ability_card`)
- 64×40 panel, pixel icon centered, cost badge top-right (`Nblitz`), charge count bottom-left (`x/y` text), cooldown overlay = full black 55% dim + recharge number, insufficient-energy = 45% dim, opponent's = 30% dim, armed = yellow border
- Card sits at the END of each side's horizontal strip, far from the energy bar visually

### Issues
1. Four data dimensions in 64×40 (icon, cost, charges, state) → all of them get small
2. Tied functionally to energy but spatially separated by the strip layout
3. Cooldown number is a hard read at 22pt inside a 64×40 dim — no progress indicator, just a stamp
4. Charge count `2/3` text is the same visual weight as the cost — a glance can't distinguish "I have 2 charges" from "It costs 3 energy"

### Proposed
- **Move into the right-rail player panel, directly under the energy bar.** Tied to the resource it consumes.
- **Grow to ~96×96** (energy bar + ability card together fit in a ~120-wide rail comfortably).
- **Three-zone interior:**
  - **Top half:** pixel icon, ~48px tall, no clutter overlapping
  - **Bottom-left:** charge pips — three filled circles (●●○) instead of `2/3` text. Smaller, scannable, and the eye immediately reads "two of three" without parsing characters.
  - **Bottom-right:** energy cost as a single oversized number + ⚡ glyph (e.g. `3⚡` at 18pt)
- **Cooldown overlay → radial sweep, not stamp.** A `ColorRect` with a custom shader (or a `TextureProgressBar` masked to a circle) that depletes from full to zero as `recharge / max_recharge`. MOBA / Slay the Spire convention — recognizable as "filling back up." Drop the recharge number; the radial conveys it.
- **Insufficient-energy → desaturate, don't dim.** Replace the 45% black overlay with `modulate = Color(0.45, 0.45, 0.45)` on the icon itself. Icon stays legible; player still understands "not now."
- **Armed border:** keep the yellow 3px bump. It's working.

### Why
- Pip-based charge readout is faster than text at small sizes
- Radial cooldowns communicate progress, not just remaining count
- Putting the card directly under the energy bar makes the cost-vs-available comparison spatial: my eye can verify "the bar reaches above the cost number" without reading either

### GDScript notes
- Pip row: small `HBoxContainer` of `ColorRect` circles (or `TextureRect` of pre-rendered pip glyphs from `SpriteFactory`) — populate filled/empty based on `charges` and `max_charges`
- Radial cooldown: simplest first version is a `TextureProgressBar` with `fill_mode = MODE_RADIAL_CLOCKWISE`; a custom shader is nicer-looking but not blocking
- Insufficient-energy desaturate: replace the dim `ColorRect` with a `modulate` on the inner stack

---

## C. Promote menu — the actual UX bug

### Current
- `promo_panel` is a `PanelContainer` parented to the **right control column**, far from the promoting pawn
- Player has to break their gaze from the action (a pawn reaching the back rank, a critical moment) to look at a side rail and pick

### Issues
1. Spatial disconnect from the event that triggered the picker
2. No "the game is paused waiting for you" cue — the picker just appears in a side rail with no escalation
3. No keyboard shortcuts; mouse-only
4. The rest of the UI (ability buttons, opposing pieces) remains visually active during the choice

### Proposed
- **Anchor the picker to the promoting square in board space.** When `pending_promo` is set, compute the promoting square's screen rect and position the picker adjacent to it (above for white promotions on rank 8, below for black on rank 1). Lichess does exactly this; chess.com too.
- **Vertical column of 4 piece sprites** (Q on top, R, B, N below). 56×56 each. Total ~224px tall × 56px wide. Use the same `SpriteFactory.piece_texture` the rest of the game uses — visual consistency with the board.
- **Edge-clamping:** if positioning the column above the square would clip the viewport (h8 / a8 edge cases on smaller windows), fan to the side instead of clipping.
- **Dim the rest of the board** with a 50% black overlay during promotion — clear "input required" cue. Restore on pick.
- **Keyboard shortcuts:** Q/R/B/N pick the corresponding piece; Esc cancels (matches lichess behavior).
- **Style:** same `PanelContainer` shell as today (cream 2px border, dark wood fill) — just relocated.

### Why
- The picker pinned to the square turns "where do I look?" into a non-question
- The dim overlay communicates "the game is waiting" the way a modal does, without going full-screen
- Keyboard shortcuts let speed players promote without breaking flow

### GDScript notes
- `_show_promo_picker(matches)` → `_show_promo_picker(matches, promo_sq)` — pass the destination square so the picker knows where to anchor
- Compute global position: `var sq_rect = squares[promo_sq].get_global_rect()` then offset the panel to the upper-edge anchor and clamp to `get_viewport_rect()`
- Add an `_unhandled_input` handler in `GameScene` that maps `KEY_Q/R/B/N/ESCAPE` to the same `_on_promo_chosen` / `_cancel_promo` flow when `pending_promo` is non-empty
- Dim overlay: a single full-rect `ColorRect` parented to `anim_overlay`, visible only during `pending_promo`

---

## D. Buttons

### Current (`_make_styled_button`)
- Flat dark wood (`#2E2120`), 2px black outline, cream-on-hover, 16pt cream font
- The style itself is good — keeps the tabletop feel, hover state is clear
- Used for: ← Menu (right rail top), promo buttons, New game (right rail bottom)

### Issues with the style
- None. It's working. Don't redesign the visual.

### Issues with placement
1. Menu and New game live among gameplay UI → they compete with status / abilities for visual attention
2. The "CHESS²" title at the top of the right rail (32pt + outline) is branding the screen the user is already on — wasted vertical space

### Proposed
- **Keep `_make_styled_button` unchanged** for promo buttons and any other in-flow buttons
- **Move Menu / New game to a top utility bar** above the board, right-aligned, smaller (28px height, 14pt font). They become chrome, not gameplay UI.
- **Delete the in-game `CHESS²` title.** Branding belongs on the main menu, not on the game screen. Frees ~50px of vertical space at the top of the right rail.
- **Add a 3rd top-bar item: a turn indicator** ("Move 12 · White to move" or similar) — replaces the right-rail status label and uses the freed top space for the most important runtime state.

### Why
- A clean utility bar at the top is a universal convention (lichess, chess.com, every web app) — players parse "chrome stuff up there" without thinking
- Moving Menu/New game out of the right rail removes them from competing with energy/abilities, and shrinks them to the size their function deserves
- Promoting status ("White to move") to the top bar fixes the bug where the most important game state is currently smaller than the brand title

### GDScript notes
- New method `_build_top_bar()` returning an `HBoxContainer` placed at the top of the root `Control`, anchored top-stretch
- Three children: status label (left, expand_fill), Menu button, New game button (both right-aligned, fixed width)
- Delete the title label code in `_build_ui`
- Move `status_label` reference target from right rail → top bar

---

## E. Space-use summary

After A-D, the layout becomes:

```
┌─ top utility bar — full width ───────────────────────────────────────┐
│  Move 12 · White to move                       ← Menu    New game   │
├─ left rail (224) ─┬─────── center board ─────┬─ right rail (224) ───┤
│                   │                          │  ┌─ Black panel ──┐  │
│  captured pieces  │   ┌──────────────────┐   │  │  Black ⚡ 7    │  │
│  (white captured  │   │                  │   │  │  ┃▮▮▮▮▮▮▮□□□  │  │
│   by black)       │   │   8x8 board      │   │  │  ┃ (vert)      │  │
│                   │   │   with file/rank │   │  │  [Cannon  3⚡] │  │
│                   │   │   corner labels  │   │  └──────────────┘  │
│  move history     │   │                  │   │                    │
│  (algebraic,      │   │   promote popup  │   │  ┌─ White panel ──┐│
│   scrollable,     │   │   anchors HERE,  │   │  │  White ⚡ 4    │  │
│   last move hi)   │   │   not in a rail  │   │  │  ┃▮▮▮▮□□□□□□   │  │
│                   │   │                  │   │  │  [Lightning2⚡]│  │
│                   │   └──────────────────┘   │  └──────────────┘  │
└───────────────────┴──────────────────────────┴────────────────────┘
```

Net wins:
- The two ~200px rails are full of *gameplay* info (captured pieces, move history, energy, abilities), not chrome
- The board got file/rank labels and is otherwise unchanged
- The single most important runtime state ("White to move") moved from a side label to the top of the screen
- The promote picker now appears at the pawn, not in a side rail
- Chrome (Menu, New game) is a small top-right utility, where users expect chrome

---

## F. Optional: cleaner board (out of scope but related)

The redesign above doesn't touch per-square overlays — your existing layered tints (`SELECTED_TINT`, `MOVE_EMPTY_TINT`, `CANNON_HOVER_TINT` etc.) are well-thought-out and the pulse system from `PIECE-VARIANTS.md §4.7` is doing real work.

The one area worth a follow-up is the **always-on HP plate** in every occupied square's top-left corner. 32 dark plates at game start is a lot of visual noise on what's otherwise a clean board.

If you want, a tighter follow-up redesign:
- HP plate appears only when `hp < max_hp` (any damage) OR the piece is selected/hovered/targeted
- For full-HP pieces, a thin HP bar segment at the bottom of the square — only renders when damaged (Into the Breach unit-HP convention)
- Status FX glyphs (🔥, ❄, ☄): smaller and outlined so they don't fight the piece sprite

This is independent of A-D and can ship later.

---

## Recommended order of implementation

1. **Promote picker anchored to square** — biggest UX bug, smallest code change (modify `_show_promo_picker`)
2. **Top utility bar + delete in-game title** — quick win, frees right rail for the rest
3. **Right-rail player panels** — biggest visual restructure; energy bar + ability card together
4. **File/rank corner labels** — quick win
5. **Captured pieces tray + move history in left rail** — bigger feature, can ship later
6. **HP plate conditional display** (optional follow-up)

---

## Web research sources

- [Lichess training board](https://lichess.org/training) — layout reference for 3-column with rich rails
- [Lichess pawn promotion design](https://github.com/lichess-org/chessground/issues/320) — anchored-to-square popup pattern
- [Slay the Spire UI gallery](https://interfaceingame.com/games/slay-the-spire/) — energy orb, HP bars, card UI
- [Game UI Database — Clash Royale](https://www.gameuidatabase.com/gameData.php?id=1299) — segmented elixir bar reference
- [Into the Breach HP indicators](https://intothebreach.fandom.com/wiki/Abilities_and_status_effects) — pip-based unit HP under sprites
- [Slay the Spire orbs reference](https://slay-the-spire.fandom.com/wiki/Orbs) — radial cooldown / charge convention
