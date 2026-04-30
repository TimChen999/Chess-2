# Godot Implementation Plan

Concrete blueprint for building the customizable chess game in Godot 4.x.
The conceptual rules theory lives in [DESIGN.md](DESIGN.md) — read it
first if anything below feels arbitrary. This doc is the *how*.

---

## 1. Scope of the first implementation

In scope:

- Hot-seat 2-player chess with the rules engine from [DESIGN.md](DESIGN.md)
- HP system with push-back on damage (§10)
- Variable per-piece damage (§10.8)
- On-hit status effects: **burn** (DOT) and **freeze** (§11.5–§11.6)
- Per-piece **special abilities** (§7): cannon (delayed plus-shape AOE)
  and lightning (instant single-target), with configurable damage,
  cooldown, charges, and initial charges
- Start menu → Game / Customization
- Customization screen: HP, damage, movement pattern, on-hit effect,
  and special-ability parameters per piece — *every* numeric parameter
  customizable
- Persistent customization (saved to `user://`)
- Piece-slide animations and basic damage/effect feedback

Out of scope (first cut):

- AI opponent
- Online multiplayer
- Sound / music
- Multi-move turns (rejected, see [DESIGN.md §12](DESIGN.md#12-multi-move-turns-considered-and-rejected))
- Free-form ability authoring — only the two ability kinds (Cannon,
  Lightning) are selectable in the UI; their AOE shape and targeting
  rules are fixed, only their numeric parameters customizable
- Free-form Betza notation editing — the customization UI exposes preset toggles only
- 3D board / particle FX

---

## 2. Tech setup

| Item                | Choice                                                        |
| ------------------- | ------------------------------------------------------------- |
| Engine              | Godot **4.3+** (uses typed `Array[T]`, `@export` Resources)   |
| Language            | GDScript (no C# — keeps build simple and avoids extra deps)   |
| Renderer            | Forward+ (default; 2D, won't matter)                          |
| Display             | 1280×720 viewport, scalable                                   |
| Input               | Mouse / touch only                                            |
| Persistence         | `user://customizations.tres` (Godot ResourceSaver)            |

---

## 3. Architecture overview

Two layers, strictly separated:

```
        ┌────────────────────────────────┐
        │  VIEW (Godot scenes / nodes)   │
        │  scenes, sprites, animations,  │
        │  UI controls, signals          │
        └──────────────┬─────────────────┘
                       │ reads state, emits player intents
        ┌──────────────▼─────────────────┐
        │  ENGINE (pure GDScript)        │
        │  no Node, no Scene, no @tool   │
        │  state, moves, rules           │
        └────────────────────────────────┘
```

The engine is pure logic. View nodes hold a reference to a `GameSession`
(engine wrapper) and observe state. **Engine never imports view types.**
View calls engine methods and reacts to returned data.

This mirrors the layering in [DESIGN.md §13](DESIGN.md#13-layering-recap)
and means the engine is unit-testable without launching scenes.

---

## 4. Data model

### 4.1 Resources (editor-savable, used for config / piece defs)

```gdscript
# res://engine/data/PieceDef.gd
class_name PieceDef
extends Resource

@export var id: String                   # "king", "queen", "custom_1"
@export var display_name: String         # "King"
@export var glyph: String                # "♚" (or path to texture later)
@export var hp: int = 3
@export var damage: int = 1
@export var move_patterns: Array[MovePattern] = []
@export var royal: bool = false          # marks the check target
@export var promotes_at_rank: int = -1   # -1 = no promotion; else 0 or 7
@export var promotes_to: Array[String] = []   # piece ids
@export var on_hit_effect: StatusEffectDef   # null = no effect
```

```gdscript
# res://engine/data/MovePattern.gd
class_name MovePattern
extends Resource

enum Kind { LEAPER, RIDER, PAWN_PUSH, PAWN_CAPTURE, PAWN_DOUBLE }

@export var kind: Kind
@export var offsets: Array[Vector2i] = []   # leapers: target offsets
                                             # riders: direction vectors
@export var max_range: int = 0               # riders only; 0 = unlimited
@export var capture_only: bool = false
@export var move_only: bool = false
```

```gdscript
# res://engine/data/StatusEffectDef.gd
class_name StatusEffectDef
extends Resource

enum Kind { NONE, BURN, FREEZE }

@export var kind: Kind = Kind.NONE
@export var damage_per_turn: int = 0   # for BURN
@export var duration: int = 0          # turns active
```

```gdscript
# res://engine/data/GameConfig.gd
class_name GameConfig
extends Resource

@export var pieces: Dictionary = {}    # String -> PieceDef
@export var initial_setup: Array = []  # 64-element flat layout, piece ids or "" for empty
                                        # index 0 = a1, index 63 = h8
```

### 4.2 Pure runtime types (RefCounted, not Resource)

```gdscript
# res://engine/state/Piece.gd
class_name Piece
extends RefCounted

var def: PieceDef            # reference to immutable def
var color: int               # 0 = white, 1 = black
var hp: int                  # current HP (mutable)
var active_effects: Array[ActiveEffect] = []   # live status effects
var has_moved: bool = false  # for castling, pawn double-push, etc.
```

```gdscript
# res://engine/state/ActiveEffect.gd
class_name ActiveEffect
extends RefCounted

var kind: int                # mirrors StatusEffectDef.Kind
var damage_per_turn: int
var turns_remaining: int
var source_piece_id: String  # for UI / tracking
```

```gdscript
# res://engine/state/GameState.gd
class_name GameState
extends RefCounted

var board: Array              # 64 entries; each is Piece or null
var side_to_move: int         # 0 = white, 1 = black
var ep_target: int            # -1 if none
var halfmove_clock: int
var fullmove_number: int
var config: GameConfig
```

```gdscript
# res://engine/state/Move.gd
class_name Move
extends RefCounted

var from_sq: int
var to_sq: int
var capture: bool = false
var promotes_to: String = ""    # piece id
var en_passant: bool = false
var castle: int = 0             # 0 = no, 1 = kingside, -1 = queenside
var pushes: Array[Vector2i] = []  # [from_sq, to_sq] pairs for chain pushes (informational)
```

---

## 5. Move-pattern system

The engine interprets `MovePattern` records uniformly. No hardcoded
piece-type branches. See [DESIGN.md §8.1](DESIGN.md#81-replace-hardcoded-branches-with-data-driven-patterns).

### 5.1 Pattern semantics

| `Kind`           | Behavior                                                                 |
| ---------------- | ------------------------------------------------------------------------ |
| `LEAPER`         | For each offset `(df, dr)`, target = from + offset; reachable if in-bounds and (empty or enemy depending on flags) |
| `RIDER`          | For each direction vector, walk outward up to `max_range` (0 = unlimited); empty squares are move targets, first enemy hit is capturable, friendly blocks |
| `PAWN_PUSH`      | One square forward (color-dependent); empty only                         |
| `PAWN_DOUBLE`    | Two squares forward; only if `has_moved == false`; both squares empty   |
| `PAWN_CAPTURE`   | Diagonal forward; enemy only OR en-passant target                        |

`capture_only` and `move_only` modifiers gate target validity.

### 5.2 Default piece patterns (the standard chess set)

| Piece  | Patterns                                                                                                |
| ------ | ------------------------------------------------------------------------------------------------------- |
| King   | `LEAPER` with offsets `[(±1,0),(0,±1),(±1,±1)]`                                                         |
| Queen  | `RIDER` orthogonal + `RIDER` diagonal, `max_range = 0`                                                  |
| Rook   | `RIDER` orthogonal, `max_range = 0`                                                                     |
| Bishop | `RIDER` diagonal, `max_range = 0`                                                                       |
| Knight | `LEAPER` with offsets `[(±1,±2),(±2,±1)]`                                                               |
| Pawn   | `PAWN_PUSH` + `PAWN_DOUBLE` + `PAWN_CAPTURE`                                                            |

Stored as `default_pieces.tres` and loaded as the initial customization
state.

### 5.3 Customization presets (UI surface)

The customization UI does NOT expose raw `MovePattern` editing. Instead,
toggles compose into pattern arrays:

| Toggle in UI                 | Adds pattern                                                           |
| ---------------------------- | ---------------------------------------------------------------------- |
| Slides orthogonally          | `RIDER` with directions `[(0,1),(0,-1),(1,0),(-1,0)]`                  |
| Slides diagonally            | `RIDER` with directions `[(1,1),(1,-1),(-1,1),(-1,-1)]`                |
| Range limit (1-7, 0=∞)       | Sets `max_range` on all sliders                                        |
| Knight leap                  | `LEAPER` with the 8 knight offsets                                     |
| One-step any direction       | `LEAPER` with the 8 king offsets                                       |
| Pawn-like (forward + diag)   | `PAWN_PUSH` + `PAWN_DOUBLE` + `PAWN_CAPTURE`                           |

Combinations let users build pieces like "Princess" (knight + bishop),
"Empress" (knight + rook), "Amazon" (queen + knight), etc.

---

## 6. Status effects

### 6.1 Burn (DOT)

- Applied when an attacker hits a target that survives
- At the start of each turn for the **affected piece's owner**, the piece
  takes `damage_per_turn` damage and `turns_remaining` decrements
- If burn damage kills, piece is removed normally; no push-back
- Multiple stacks: latest application overwrites duration; damage doesn't
  stack (simpler — keep ONE burn instance per piece)

### 6.2 Freeze

- Applied same way, replaces any existing freeze (refresh duration)
- At the start of each of the affected piece's owner's turns,
  `turns_remaining` decrements
- While `turns_remaining > 0`, the piece is excluded from `pseudo_legal_moves`
- Frozen piece can still be attacked; freeze does not protect

### 6.3 Tick order at turn start

```
on turn start (for side_to_move):
  for each piece owned by side_to_move:
    apply burn damage (if any), check death
    decrement freeze counter (if any), remove if 0
    decrement burn counter (if any), remove if 0
  recompute legal moves, gameStatus
```

### 6.4 Effect display in UI

- Burn: red flame badge on piece sprite + small turn-counter number
- Freeze: blue ice overlay on piece sprite + turn-counter
- HP: small bar or numeric badge above piece (always visible, drives the
  whole game)

---

## 7. Special abilities (per-piece active powers)

A piece can carry an optional `SpecialAbilityDef` granting a power
separate from its movement. Two ability kinds in this first cut:

- **Cannon** — delayed plus-shape AOE attack
- **Lightning** — instant single-target strike (cannot target king)

Per-turn rules:

- Each ability is **independent of the regular move**: a turn = one
  move + optionally one special ability use
- Each ability has a per-piece cooldown and a charge cap
- One ability use per turn (across all your pieces, not per-piece) —
  prevents stacked spam

### 7.1 Cannon (delayed AOE attack)

- **Trigger.** Player selects a target square during their turn (does
  not consume the regular move). Attack queues into `state.pending_attacks`
  with `triggers_on_turn = current_fullmove + 2` (i.e., the player's *next* turn).
- **Area of effect.** 5-square plus pattern centered on target:
  `[(0,0), (1,0), (-1,0), (0,1), (0,-1)]`.
- **Targeting restriction.** No square in the plus may overlap the
  *enemy starting zone* — squares occupied by enemy pieces in the
  configured `initial_setup`. Validated at target-selection time, both
  in UI (don't show forbidden squares as targetable) and engine (refuse
  the action).
- **Resolution.** When the queued attack triggers (start of player's
  next turn, before their move), every piece in the plus pattern takes
  `damage` HP. If a piece dies, it's removed normally; survivors take
  damage with **no push-back** and **no on-hit status effect**
  (special-ability damage skips both — keeps the AOE clean and
  predictable).
- **King exposure.** The king IS a valid victim if it sits inside the
  plus area at trigger time. Pending cannon damage on king becomes part
  of the per-turn damage budget for check evaluation (§7.4).

### 7.2 Lightning (instant single-target)

- **Trigger.** Player selects an enemy piece to strike during their
  turn (does not consume the regular move).
- **Targeting restriction.** Cannot target the opponent's royal piece.
  Hard rule — both UI and engine refuse king selection.
- **Resolution.** Damage applied immediately. If target dies, removed
  normally; if target survives, apply damage with **no push-back** and
  **no on-hit status effect** (matches cannon behavior).
- **King-immunity guarantees.** Because lightning cannot target king,
  it contributes 0 to opponent's damage budget against king (§7.4).

### 7.3 Cooldown / charges system

Each ability instance has these customizable parameters:

| Field                   | Meaning                                             |
| ----------------------- | --------------------------------------------------- |
| `cooldown_turns`        | Turns between recharges                             |
| `max_charges`           | Cap on simultaneously-held charges                  |
| `initial_charges`       | Charges at game start                               |

Each piece carries runtime state:

| Field                         | Meaning                                    |
| ----------------------------- | ------------------------------------------ |
| `special_charges`             | Currently available uses                   |
| `special_recharge_remaining`  | Turns until next charge accrues            |

Tick at start of owner's turn (after burn/freeze ticks, before move
generation):

```
if special_recharge_remaining > 0:
    special_recharge_remaining -= 1
if special_recharge_remaining == 0 and special_charges < max_charges:
    special_charges += 1
    special_recharge_remaining = cooldown_turns
```

On use: `special_charges -= 1`. The "once per turn" cap is enforced via
a transient `special_used_this_turn: bool` on `GameState`, reset on
turn flip.

### 7.4 Check predicate impact

The HP-aware check rule ([DESIGN.md §10.8](DESIGN.md#108-variant-variable-per-piece-damage-eg-queen-deals-2))
generalizes per [DESIGN.md §11](DESIGN.md#11-extended-actions-instant-attacks-delayed-attacks-status-effects)
to sum damage contributors:

```
max_damage_next_turn(state, my_color) =
      max move-attack damage opponent can deal to my royal
    + sum of pending cannon damage where royal's CURRENT square is in plus area
    + 0 from lightning (cannot target royal)
    + sum of DOT damage on royal from active burns
```

`check = my_royal.hp <= max_damage_next_turn(state)`

Lightning never raises the budget. Cannon raises it only if the royal
sits inside a queued plus area at evaluation time. Both are O(small)
per evaluation — closed form holds.

### 7.5 Customization parameters per ability

All four parameters are exposed in the customization UI:

| Parameter           | Cannon | Lightning | Notes                                  |
| ------------------- | ------ | --------- | -------------------------------------- |
| `damage`            | yes    | yes       | 1-5 typical                            |
| `cooldown_turns`    | yes    | yes       | 1-10 typical                           |
| `max_charges`       | yes    | yes       | 1-5 typical                            |
| `initial_charges`   | yes    | yes       | 0..`max_charges`                       |

> **All previously-introduced "X / Y / Z" parameters are also
> customizable** — burn `damage_per_turn`, burn `duration`, freeze
> `duration`, every per-piece `damage` and `hp`. The UI exposes them
> with the same SpinBox controls as the ability parameters above.

### 7.6 Resource definition

```gdscript
# res://engine/data/SpecialAbilityDef.gd
class_name SpecialAbilityDef
extends Resource

enum Kind { NONE, CANNON, LIGHTNING }

@export var kind: Kind = Kind.NONE
@export var damage: int = 1
@export var cooldown_turns: int = 3
@export var max_charges: int = 1
@export var initial_charges: int = 0
```

Add to `PieceDef`:

```gdscript
@export var special: SpecialAbilityDef    # null = no ability
```

Add to runtime `Piece` (RefCounted):

```gdscript
var special_charges: int = 0
var special_recharge_remaining: int = 0
```

Add to `GameState`:

```gdscript
var pending_attacks: Array = []         # see §7.7
var special_used_this_turn: bool = false
```

### 7.7 Pending attack record

```gdscript
# res://engine/state/PendingAttack.gd
class_name PendingAttack
extends RefCounted

var kind: int                  # mirrors SpecialAbilityDef.Kind
var owner_color: int           # color of the piece that fired
var damage: int
var target_squares: Array[int] # squares hit when this triggers
var triggers_on_turn: int      # state.fullmove_number when this fires
```

Stored in `state.pending_attacks`. Resolved at the start of each
player's turn: any with `triggers_on_turn == current_fullmove AND
owner_color == side_to_move` apply damage to all pieces on
`target_squares`, then are removed from the queue.

### 7.8 Move record extension

`Move` already carries the regular movement. To bundle the optional
ability use into the same turn, extend:

```gdscript
# additions to Move
var special_kind: int = 0       # 0 = no special this turn; 1 = Cannon, 2 = Lightning
var special_source_sq: int = -1 # which of my pieces fired the ability
var special_target_sq: int = -1 # lightning: target piece's sq; cannon: AOE center
```

A turn = a single `Move` that may include both regular movement and a
special action. The engine validates each part independently:

1. Regular move legality (existing self-check filter)
2. Special action legality (charges available, cooldown clear, target
   valid for ability kind, can't-target-king for lightning, can't-hit-
   enemy-start for cannon, special_used_this_turn == false)

Both must pass for the whole `Move` to be legal. If only the regular
move is desired, `special_kind` stays 0 and the special-validation
short-circuits.

### 7.9 UI affordances

Extending the click flow from §12.1 to handle ability activation:

```
selected_ability: int = 0   # 0 = none, 1 = cannon, 2 = lightning
selected_ability_source: int = -1   # which piece fires it

UI mode is one of:
  - "select piece"      (default)
  - "select move"       (piece selected, showing legal targets)
  - "select ability target"  (ability armed; showing ability-target overlay)

Activating an ability button (only visible if my piece has charges and
no special used this turn) sets the mode to "select ability target".
Then a click on any board square either fires (if valid) or cancels the
mode (if invalid). After firing, mode returns to "select piece" and the
player can still make their regular move.
```

Visual feedback:

- Charges remaining: small badge near the piece sprite (e.g., "⚡×2")
- Cooldown: faded ability button + numeric "in N turns"
- Cannon target picker: hovering a square shows the prospective plus
  shape highlighted; forbidden squares (enemy start zone) tinted red
- Lightning target picker: hovering an enemy piece highlights it; king
  is dimmed to show non-targetability
- Pending cannon impact: persistent plus-shape outline on the affected
  squares from the moment it's queued until it resolves; counts down
  the turns remaining
- Lightning resolution: instant flash + damage flicker on target

---

## 8. Engine module — function specification

Direct ports of [DESIGN.md §1–§5](DESIGN.md) into GDScript. All pure
functions on `GameState`. Files live in `res://engine/`.

```gdscript
# res://engine/Engine.gd  (static utility class; no state)
class_name Engine

# Primitives
static func is_attacked(state: GameState, sq: int, by_color: int) -> bool
static func max_incoming_damage(state: GameState, sq: int, by_color: int) -> int
static func find_royal(state: GameState, color: int) -> int

# Move generation
static func pseudo_legal_moves(state: GameState, color: int) -> Array[Move]
static func legal_moves(state: GameState) -> Array[Move]

# Move application (returns NEW state — does not mutate)
static func apply_move(state: GameState, m: Move) -> GameState

# Game status
static func game_status(state: GameState) -> Dictionary
# returns { kind: "normal"|"check"|"checkmate"|"stalemate"|"draw50",
#           winner: int|-1, in_check: bool, moves: Array[Move] }
```

### 8.1 Check predicate (HP-aware, with variable damage)

```gdscript
# In game_status:
var royal_sq = find_royal(state, state.side_to_move)
var royal = state.board[royal_sq]
var max_dmg = max_incoming_damage(state, royal_sq, opposite(state.side_to_move))
var in_check = max_dmg >= royal.hp
```

This is the [DESIGN.md §10.8](DESIGN.md#108-variant-variable-per-piece-damage-eg-queen-deals-2)
generalization: closed form, O(constant) per evaluation.

### 8.2 Self-check filter

```gdscript
# In legal_moves:
for m in pseudo_legal_moves(state, state.side_to_move):
    var next = apply_move(state, m)
    var my_royal = find_royal(next, state.side_to_move)
    var their_max_dmg = max_incoming_damage(next, my_royal, opposite(state.side_to_move))
    if next.board[my_royal].hp > their_max_dmg:
        result.append(m)
```

> Move legal iff after playing it, opponent cannot kill my king on their
> next turn.

This handles pins, blocks, king escapes, and HP-budget survival
uniformly.

### 8.3 apply_move — what it does

The full update list (port of [DESIGN.md §6](DESIGN.md#6-the-per-turn-flow)):

1. Clone state
2. Tick start-of-turn effects on the *new* side's pieces (burn damage, freeze countdown, burn countdown)
3. Move the piece
4. Handle capture vs. survive-with-push:
   - If target HP > attacker.damage: target.hp -= damage, push target toward its home rank, chain-push pieces behind
   - If target HP ≤ damage: target removed, attacker takes the square
5. Apply on-hit status effect (if attacker has one and target survives)
6. Handle promotion (if pawn reaching last rank — UI must have prompted)
7. Handle castling (move rook too)
8. Handle en passant (remove captured pawn)
9. Update castling rights
10. Update EP target
11. Update halfmove clock (reset on pawn move OR capture OR damage dealt)
12. Update fullmove number
13. Flip side_to_move

---

## 9. Scene hierarchy

```
res://scenes/
├── Main.tscn                    (root: SceneSwitcher)
├── MainMenu.tscn                (start menu)
├── CustomizationScene.tscn      (piece editor)
└── GameScene.tscn               (the actual board)
```

`Main.tscn` is just a node that holds the current sub-scene and
swaps it on signals from buttons. Single autoload `GameSettings`
(an `AutoLoad` script) holds the active `GameConfig` so it persists
between scene changes.

```gdscript
# res://autoloads/GameSettings.gd  (registered as autoload "GameSettings")
extends Node

var active_config: GameConfig

func _ready() -> void:
    active_config = _load_or_default()

func _load_or_default() -> GameConfig:
    var path = "user://customizations.tres"
    if ResourceLoader.exists(path):
        return ResourceLoader.load(path) as GameConfig
    return load("res://engine/data/default_config.tres") as GameConfig

func save() -> void:
    ResourceSaver.save(active_config, "user://customizations.tres")
```

---

## 10. MainMenu scene

Layout: vertical centered panel with the title and three buttons.

```
MainMenu (Control, anchors fill)
└── CenterContainer
    └── VBoxContainer
        ├── Label "Chess²"  (h1)
        ├── Button "Start Game"        → emits start_game
        ├── Button "Customize Pieces"  → emits open_customization
        └── Button "Quit"              → quits
```

Signals up to `Main` node, which calls `change_scene_to_file`.

---

## 11. Customization scene

The main UX challenge. Layout is a master-detail panel:

```
CustomizationScene (Control)
├── HSplitContainer
│   ├── LEFT PANEL (PieceList, ItemList)
│   │   - one row per piece type with glyph + name
│   │   - selecting populates the right panel
│   │
│   └── RIGHT PANEL (ScrollContainer → VBoxContainer)
│       ├── Section: "Identity"
│       │   - LineEdit  display_name
│       │   - LineEdit  glyph (single character; later: TextureRect)
│       │
│       ├── Section: "Stats"
│       │   - SpinBox   HP        (range 1-10)
│       │   - SpinBox   Damage    (range 1-5)
│       │
│       ├── Section: "Movement"
│       │   - CheckButton  "Slides orthogonally"
│       │   - CheckButton  "Slides diagonally"
│       │   - SpinBox      "Range limit (0 = unlimited)"
│       │   - CheckButton  "Knight leap"
│       │   - CheckButton  "One step any direction (king move)"
│       │   - CheckButton  "Pawn-like (forward push + diagonal capture)"
│       │
│       ├── Section: "Reachability preview"
│       │   - 8x8 grid showing where this piece can go from center
│       │     (live re-renders on toggle change)
│       │
│       ├── Section: "On-hit status effect"
│       │   - OptionButton  Kind (None / Burn / Freeze)
│       │   - SpinBox       damage_per_turn (visible if Burn)
│       │   - SpinBox       duration         (turns; visible if Burn or Freeze)
│       │
│       ├── Section: "Special ability"
│       │   - OptionButton  Kind (None / Cannon / Lightning)
│       │   - SpinBox       Damage           (visible if not None)
│       │   - SpinBox       Cooldown turns   (visible if not None)
│       │   - SpinBox       Max charges      (visible if not None)
│       │   - SpinBox       Initial charges  (visible if not None; capped at max_charges)
│       │   - Label         Targeting summary (read-only — describes
│       │                   "5-square plus AOE, can't target enemy start
│       │                   zone, hits next turn" or "single enemy
│       │                   target, can't target king, instant")
│       │
│       └── HBoxContainer (footer)
│           ├── Button "Reset to default"
│           ├── Button "Save & back to menu"
│           └── Button "Cancel (discard changes)"
```

Behavior notes:

- The page edits a *working copy* of `GameSettings.active_config`. Save
  commits + persists; cancel discards
- The reachability preview uses a centered 8×8 grid where the current
  piece's patterns are run from the center square; squares it can reach
  are tinted (light tint = move, red tint = capturable enemy if a dummy
  enemy were there)
- Enabling a movement toggle re-derives the `move_patterns` array (don't
  store toggles separately — derive from patterns)
- Promotion / royal flag are NOT exposed in this UI for the first cut;
  defaults are kept (king royal, pawns promote to queen)

---

## 12. GameScene

```
GameScene (Control)
├── BoardRoot (Control, fixed 8×8 grid layout)
│   └── 64 × Square (TextureButton)
│       └── PieceSprite (Sprite2D, may be null)
│           ├── HPBadge (Label)
│           └── EffectBadges (HBoxContainer with flame/ice icons)
├── StatusBar (HBoxContainer)
│   ├── Label  "White to move" / etc.
│   └── Label  "Check!" / "Checkmate" / "Stalemate"
├── PromotionPicker (PopupPanel, hidden until needed)
└── EndGameOverlay (PopupPanel, hidden)
```

### 12.1 Click flow

```
on Square click(sq):
    if game_over: return
    if pending_promotion: return
    if a piece is selected and sq is in legal_targets:
        play_move(matching_move(selected, sq))
    elif state.board[sq] is mine:
        selected = sq
        legal_targets = legal moves from sq
        highlight squares
    else:
        deselect
```

Match the same lookup pattern as [index.html](index.html), check point #5.

### 12.2 Animations

Use `Tween` for piece movement:

- Selected → destination: `tween.tween_property(sprite, "position", target_pos, 0.18)`
- Push-back: chain victims slide simultaneously with the same duration
- Damage flash: tween modulate to red and back (0.15s × 2)
- Capture: scale-down + fade-out tween, then free
- Burn tick: small flame puff (AnimationPlayer one-shot)
- Freeze: blue tint stays on piece while frozen

### 12.3 Game flow

```
GameScene._ready:
    state = Engine.new_game(GameSettings.active_config)
    status = Engine.game_status(state)
    render(state, status)

on play_move(m):
    var animations = compute_animations(state, m)
    state = Engine.apply_move(state, m)
    play(animations).then:
        status = Engine.game_status(state)
        render(state, status)
        if status.kind in ["checkmate", "stalemate", "draw50"]:
            show_end_game_overlay(status)
```

`compute_animations(state, m)` figures out which sprites move/fade/take
damage and packages them into a list the view replays. The engine itself
emits no animation data — the view reconstructs it from the move record
+ pre/post state.

---

## 13. Persistence

### Save customizations

`GameSettings.save()` writes `user://customizations.tres`. Called from
the customization scene's "Save" button.

### Load customizations

`GameSettings._ready()` loads from `user://customizations.tres` or falls
back to `res://engine/data/default_config.tres`.

### No game-state save/load (first cut)

Mid-game state persistence is not in scope. Closing the app loses the
in-progress game. Trivial to add later by serializing `GameState`.

---

## 14. File-by-file checklist

```
res://
├── autoloads/
│   └── GameSettings.gd                  -- autoload, holds active config
│
├── engine/
│   ├── Engine.gd                        -- static rules functions
│   ├── data/
│   │   ├── PieceDef.gd                  -- Resource
│   │   ├── MovePattern.gd               -- Resource
│   │   ├── StatusEffectDef.gd           -- Resource
│   │   ├── SpecialAbilityDef.gd         -- Resource (Cannon / Lightning)
│   │   ├── GameConfig.gd                -- Resource
│   │   └── default_config.tres          -- saved instance, baked from defaults
│   └── state/
│       ├── Piece.gd                     -- RefCounted
│       ├── ActiveEffect.gd              -- RefCounted
│       ├── PendingAttack.gd             -- RefCounted (queued cannon attacks)
│       ├── GameState.gd                 -- RefCounted
│       └── Move.gd                      -- RefCounted
│
├── scenes/
│   ├── Main.tscn + Main.gd              -- scene switcher
│   ├── MainMenu.tscn + MainMenu.gd
│   ├── CustomizationScene.tscn + .gd
│   ├── GameScene.tscn + .gd
│   ├── Square.tscn + .gd                -- one board square; instanced 64×
│   ├── PieceSprite.tscn + .gd           -- one piece visual
│   ├── PromotionPicker.tscn + .gd
│   └── EndGameOverlay.tscn + .gd
│
├── assets/
│   ├── pieces/                           -- placeholder Unicode glyphs at first;
│   │                                        replace with sprite sheet later
│   └── icons/
│       ├── flame.svg                     -- burn badge
│       └── ice.svg                       -- freeze badge
│
└── tests/
    └── test_engine.gd                    -- GUT or built-in test runner
                                            (basic legality, mate, push, burn, freeze)
```

---

## 15. Implementation milestones

Build in this order to keep each step verifiable:

1. **Engine, headless.** All of `engine/` plus `tests/test_engine.gd`. Zero
   scenes. Run via Godot's "run script" or a CI runner. Don't move on
   until: standard chess passes, push-back works, burn ticks correctly,
   freeze blocks moves, variable damage + HP check predicate matches
   spec.

2. **Default config Resource.** `default_config.tres` with the standard
   8 piece types and the standard initial setup. Verify the engine
   loads it and produces a sane `legal_moves` from the start position.

3. **Game scene with placeholder rendering.** No animation, no fancy
   layout — just a working board with click-to-move, status text, and
   game-end detection. Use Unicode glyphs as text labels.

4. **Promotion + check/mate end states.** PromotionPicker popup,
   EndGameOverlay popup. Standard chess plays end-to-end.

5. **HP / damage / push-back visualization.** HP badges, damage flashes,
   chain-push animations.

6. **Status effects.** Burn and freeze badges, tick visuals.

7. **Special abilities.** `SpecialAbilityDef` + cooldown/charges
   bookkeeping, pending-attack queue, cannon AOE rendering with
   pending-impact indicator, lightning instant-target picker. Verify
   tests for cooldown refresh, charge cap, can't-target-king for
   lightning, can't-hit-enemy-start for cannon, once-per-turn cap.

8. **Main menu.** Just routing, no styling.

9. **Customization scene.** The big UI piece. Build incrementally:
   - Identity + Stats first
   - Movement toggles + reachability preview
   - On-hit effect
   - Special ability
   - Save/load round-trip

10. **Polish pass.** Fonts, spacing, colors, transitions. Skip until
    everything functions.

---

## 16. Design constraints / non-negotiables

- **Engine is pure.** No `Node`, no `@tool`, no scene access in
  `engine/`. The check is simple: `engine/` should grep-clean for
  `Node`, `Scene`, `get_tree`, `get_node`. Violations get refactored
  immediately — this is the architectural payoff of [DESIGN.md §13](DESIGN.md#13-layering-recap).
- **Engine returns new state, never mutates.** Cloning is cheap at the
  scale of UI moves (~30 candidates per turn × board clone is
  microseconds in GDScript). Mutation makes the self-check filter
  fragile.
- **No multi-move turns.** [DESIGN.md §12](DESIGN.md#12-multi-move-turns-considered-and-rejected)
  explains why; if the temptation comes up later, re-read it before
  changing `apply_move`'s contract.
- **Single-turn damage budget.** The check predicate is a sum, not a
  search. If a future feature wants "die within N turns" semantics,
  that's the moment to introduce a separate `evaluate_position` layer
  rather than overloading `game_status`.
- **No mocking the engine in view tests.** If you find yourself wanting
  a fake Engine in a UI test, the real one should already work; use it.

---

## 17. Common pitfalls / things to verify early

- **Square indexing.** Same convention as [index.html](index.html):
  `sq = rank * 8 + file`, rank 0 = white's back rank. Renderer flips so
  white sits at the bottom on screen. Confirm with a marker piece on a1.
- **Push-direction inversion.** White pieces push toward rank 0; black
  toward rank 7. A common bug is pushing the *attacker's* direction
  instead of the *target's*. Test: queen-on-knight push leaves the
  knight one rank closer to its own home, not the queen's.
- **Burn tick timing.** Tick at the start of the **owner's** turn (when
  side_to_move flips to that color), not at the end of the attacker's
  turn. Otherwise a freshly-applied burn ticks once free.
- **Freeze interaction with check.** A frozen royal piece that's at risk
  is still in check; it just can't move. The legal-move filter excludes
  the frozen piece, which is correct — if no other moves help, that's
  mate.
- **HP <= max-damage check ordering.** The check predicate compares
  *current* king HP to *max incoming damage*. Make sure burn-tick
  damage applied this turn is reflected before computing
  `game_status` for the next side.
- **Resource circular references.** `PieceDef` referencing
  `StatusEffectDef` referencing... keep `StatusEffectDef` and
  `SpecialAbilityDef` leaf (no back-references). Godot serializes
  nested Resources fine as long as there's no cycle.
- **Pending-attack trigger timing.** Cannons resolve at the START of
  the owner's next turn, BEFORE that owner's regular move. Otherwise
  the target gets an extra turn to dodge after the attack should
  already have landed.
- **Cannon target-zone enforcement.** Validate against the *initial
  setup* of enemy pieces from `GameConfig`, not the *current* enemy
  positions — pieces may have moved.
- **Lightning king-immunity.** Enforce in BOTH the engine (refuse the
  action) and the UI (don't show king as a target). Two layers because
  this guarantee is what keeps the check predicate's lightning
  contribution at 0.
- **Charge tick ordering.** At the start of an owner's turn:
  (1) resolve any pending cannons targeting that owner's color,
  (2) tick burn/freeze on owner's pieces,
  (3) tick ability recharge.
  Step 1 BEFORE step 2 means burn doesn't kill a piece that the cannon
  was about to hit. Step 3 last so the recharged ability is usable
  this turn.
- **`special_used_this_turn` reset.** Reset on every `apply_move` after
  flipping `side_to_move`, not at the start of evaluation. A turn that
  uses no ability still has to clear the flag for the next side.

---

## 18. Test plan (engine-level)

In `tests/test_engine.gd`, cover:

- Standard chess: opening position legal moves count = 20
- Self-check filter: pinned piece can't move off pin line
- Castling: blocked by piece, blocked by transit attack, blocked when in check
- En passant: only on the immediately-following turn
- Promotion: all four piece options
- HP variant: attacked-but-survives applies push, no HP damage if attacker dies first
- Variable damage: queen at distance 1 from HP-2 king reads as check
- Burn: HP ticks down on owner's turn start; piece dies if HP→0; effect expires after duration
- Freeze: target excluded from legal moves while frozen; expires after duration
- Mate: classic back-rank mate registers correctly
- Stalemate: classical stalemate registers as draw
- Cannon: queueing succeeds, triggers on owner's next turn, plus shape
  damages all included pieces, can't target enemy starting zone (every
  square in the plus must be outside it), survivors take damage with no
  push-back and no on-hit effect
- Cannon hits king: pending cannon damage on king's current square
  contributes to next-turn damage budget; mate detected when cannon +
  move damage ≥ king HP
- Lightning: instant damage applied, target dies if HP ≤ damage,
  refusal to target king (engine error / no-op), refusal to fire while
  on cooldown or out of charges, refusal if special already used this
  turn
- Charges: ability disabled when 0 charges, charge granted after
  `cooldown_turns` ticks, never exceeds `max_charges`,
  `initial_charges` honored at game start
- Per-turn limit: a turn that uses ability + uses ability again is
  rejected at the second one
- Customization round-trip: save config to `user://`, reload, verify
  every parameter (including ability fields, burn `damage_per_turn`
  and `duration`, freeze `duration`) is preserved

Each test runs in milliseconds, no scenes loaded.

---

## 19. Where to push next (after first cut ships)

Listed for future reference, NOT to scope-creep this implementation:

- Sprite-sheet pieces and a board theme picker
- Sound effects (move click, capture thud, burn sizzle, freeze crack)
- Per-piece "damage when attacked" reactive armor (currently just HP)
- Save/load mid-game state
- Network multiplayer over Godot's high-level multiplayer API
- AI opponent (alpha-beta with the existing engine; the closed-form
  check predicate makes node evaluation fast)
- Custom piece creator (add new piece types with custom names, beyond
  editing the canonical 6)

These slot in cleanly because the engine/view split keeps the rules
isolated.
