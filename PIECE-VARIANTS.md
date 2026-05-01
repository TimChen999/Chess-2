# Piece Variants & Sprite Animation Plan

Implementation blueprint for replacing the current blanket per-piece
customization with a **variant picker** system, plus migrating from
procedural static textures to programmatically-generated spritesheet
animations.

Companion to [DESIGN.md](DESIGN.md) and
[IMPLEMENTATION-GODOT.md](IMPLEMENTATION-GODOT.md). Read those first if
anything below references concepts (MovePattern kinds, on-hit effects,
push-chain, HP-aware self-check) without explaining them.

---

## 1. Motivation & scope

### 1.1 What changes

**Today:** [CustomizationScene.gd](godot/scenes/CustomizationScene.gd)
exposes a granular editor — per-piece HP, damage, movement toggles
(ortho / diag / range / knight / king / pawn), on-hit effect. Every
numeric parameter is editable.

**Going forward:** Each piece type has a small fixed set of *variants*.
The customization screen becomes a variant **picker** (radio per piece),
not a parameter editor. Variants are authored in code, not produced by
combining toggles.

### 1.2 Why

- Authored variants have personality: handcrafted moveset + sprite +
  attack feel, instead of mix-and-match toggles that produce
  configurations the designer never balanced.
- Variant identity carries through to art and animation, which
  granular toggles can't do.
- Smaller, more meaningful decision surface for the player.

### 1.3 Scope

In scope:

- Three new piece variants (Bandit Pawn, Assassin Bishop, Alter Ego
  Knight) plus a cosmetic refresh on the Knight.
- Variant picker UI replacing the current movement/stat editor.
- Spritesheet-based animation pipeline (idle, move, attack, hit, death)
  generated programmatically from ASCII patterns, the same way static
  sprites are produced today.
- Knight move animation upgraded from straight-tween to parabolic jump.

Out of scope (first cut):

- Free-form variant authoring in UI.
- Animations beyond idle / move / attack / hit / death.
- Sound effects.
- Variant unlocks / progression — all variants are available from the
  start.

---

## 2. New pieces & mechanics

The engine already supports every mechanic below via existing
[MovePattern](godot/engine/data/MovePattern.gd) primitives. No changes
to [Rules.gd](godot/engine/Rules.gd) are required for the rules
themselves.

Move patterns reference flags from `MovePattern`:

- `kind` — `LEAPER`, `RIDER`, `PAWN_PUSH`, `PAWN_DOUBLE`, `PAWN_CAPTURE`
- `offsets` — list of `Vector2i(file, rank)` deltas
- `max_range` — for RIDER, 0 = unlimited; 1..7 caps slide
- `move_only` — pattern only contributes non-capture moves
- `capture_only` — pattern only contributes capture moves

### 2.1 Pawn variants

#### Regular Pawn (unchanged)

Same as today: forward push, optional double-push on first move,
diagonal capture, promotion at last rank to queen / rook / bishop /
knight. HP 1, damage 1.

#### Bandit Pawn (new)

> *Moves in a cross, attacks in an X. Doesn't promote, doesn't double-push.*

| Stat | Value |
|---|---|
| HP | 1 |
| Damage | 1 |
| Royal | false |
| Promotes | **no** (`promotes_to = []`) |
| Double-push | **no** |

**Move patterns:**

```gdscript
# Cross-shape move (4 orthogonal neighbors), move-only.
LEAPER offsets=[(1,0),(-1,0),(0,1),(0,-1)] move_only=true

# X-shape attack (4 diagonal neighbors), capture-only.
LEAPER offsets=[(1,1),(1,-1),(-1,1),(-1,-1)] capture_only=true
```

Both `move_only` and `capture_only` flags are already honored in
[Rules.gd `_collect_pattern_targets`](godot/engine/Rules.gd#L206).
LEAPER kind handles the "1-tile away" range naturally.

The piece is symmetric (no forward direction concept), so it has the
same moveset for both colors.

### 2.2 Bishop variants

#### Regular Bishop (unchanged)

Slides any number of diagonal squares, blocked by intervening pieces.
HP 2, damage 1.

#### Assassin Bishop (new)

> *Jumps to its target instead of sliding. Blocked pieces don't matter.
> Range capped at 2 diagonal squares.*

| Stat | Value |
|---|---|
| HP | 2 |
| Damage | 1 |
| Royal | false |

**Move pattern:**

```gdscript
# Jump up to 2 squares diagonally. LEAPER ignores blockers — exactly
# the "jumps to target location instead of sliding" behavior.
LEAPER offsets=[
    ( 1, 1), ( 1,-1), (-1, 1), (-1,-1),   # 1-square diagonals
    ( 2, 2), ( 2,-2), (-2, 2), (-2,-2),   # 2-square diagonals
]
```

This is the cleanest expression — a single LEAPER pattern emits all
candidate squares, each individually checked against board contents in
the existing pattern interpreter. No new `kind` is needed.

### 2.3 Knight variants

#### Normal Knight (mechanically unchanged, animation refresh)

Same moveset as today (the eight (±1,±2) / (±2,±1) jumps). The only
change is **how it animates**: instead of a straight-line tween, the
move uses a parabolic arc (vertical Y offset peaking mid-flight) with a
subtle squash on landing. See §4.3 for animation details.

This is a renderer change in [GameScene.gd](godot/scenes/GameScene.gd),
not an engine change.

#### Alter Ego Knight (new)

> *Knight's move (with jump animation), king's attack (one square in any
> direction, with straight-line attack animation).*

| Stat | Value |
|---|---|
| HP | 2 |
| Damage | 1 |
| On-hit | freeze (same as Knight) |
| Royal | false |

**Move patterns:**

```gdscript
# Move like a knight (non-captures only).
LEAPER offsets=KNIGHT_OFFS move_only=true

# Attack like a king (captures only, 1 square in any direction).
LEAPER offsets=KING_OFFS capture_only=true
```

Both `KNIGHT_OFFS` and `KING_OFFS` already exist as constants in
[Defaults.gd](godot/engine/Defaults.gd).

**Animation hint** — see §4.4. The renderer needs to know which
pattern produced a given move so it can pick the right animation
(jump for the knight-shape move, lunge for the king-shape attack).
The simplest approach: tag emitted moves with a hint string. Captures
trivially route to "lunge" because only `capture_only` patterns can
emit captures here; non-captures route to "jump" for the same reason.
No new field on the move dict is strictly required as long as the
renderer keys off `m.has("capture")`.

---

## 3. Engine & data changes

### 3.1 New constants in `Defaults.gd`

Add offset-set constants used by the new variants:

```gdscript
# Cross / plus shape — already implicit in ORTHO but spelled out for
# clarity at the variant call site.
const CROSS_OFFS := ORTHO    # alias

# X / diagonal-1 shape — for bandit pawn capture.
const X_OFFS := DIAG         # alias

# Bishop's extended jump set — 1- and 2-square diagonals.
const ASSASSIN_OFFS := [
    Vector2i( 1, 1), Vector2i( 1,-1), Vector2i(-1, 1), Vector2i(-1,-1),
    Vector2i( 2, 2), Vector2i( 2,-2), Vector2i(-2, 2), Vector2i(-2,-2),
]
```

### 3.2 New variant factory functions in `Defaults.gd`

Add a `_make_variants_map()` static returning
`Dictionary[String, Array[PieceDef]]` keyed by base piece slot:

```gdscript
static func _make_variants_map() -> Dictionary:
    return {
        "pawn":   [_make_regular_pawn(),   _make_bandit_pawn()],
        "bishop": [_make_regular_bishop(), _make_assassin_bishop()],
        "knight": [_make_normal_knight(),  _make_alter_knight()],
        "rook":   [_make_regular_rook()],
        "queen":  [_make_regular_queen()],
        "king":   [_make_regular_king()],
    }
```

Each `_make_*()` returns a fully configured `PieceDef` with a unique
`id`. Suggested ids:

- `pawn`, `bandit_pawn`
- `bishop`, `assassin_bishop`
- `knight`, `alter_knight`
- `rook`, `queen`, `king`

The existing `_make_piece()` helper already takes patterns + on-hit
+ promotions, so the factories are short.

### 3.3 `GameConfig` changes

Add a per-slot variant selection:

```gdscript
# In godot/engine/data/GameConfig.gd
@export var variant_selection: Dictionary = {
    "pawn":   "pawn",
    "bishop": "bishop",
    "knight": "knight",
    "rook":   "rook",
    "queen":  "queen",
    "king":   "king",
}
```

`Defaults.make_default_config()` populates this with the regular
variants. `cfg.pieces` still maps piece-id → `PieceDef`, but it's
rebuilt from the variant selection each time the config is loaded /
edited.

### 3.4 Initial-setup rebuild

Currently `cfg.initial_setup` hardcodes ids like `"pawn"`, `"knight"`
etc. With variants, those slots need to use the *selected variant id*
for that slot:

```gdscript
# Rebuild whenever variant_selection changes.
func rebuild_initial_setup() -> void:
    var back: Array[String] = [
        variant_selection["rook"],   variant_selection["knight"],
        variant_selection["bishop"], variant_selection["queen"],
        variant_selection["king"],   variant_selection["bishop"],
        variant_selection["knight"], variant_selection["rook"],
    ]
    var pawn_id := variant_selection["pawn"]
    initial_setup.resize(64)
    for f in 8:
        initial_setup[f]      = { "id": back[f], "color": 0 }
        initial_setup[8 + f]  = { "id": pawn_id, "color": 0 }
        initial_setup[48 + f] = { "id": pawn_id, "color": 1 }
        initial_setup[56 + f] = { "id": back[f], "color": 1 }
```

`cfg.pieces` must contain the selected variant defs *and* every other
def referenced by `promotes_to` (regular pawn promotes to queen / rook
/ bishop / knight, so those defs must exist in `pieces` even if their
variant slot is occupied by an alter-ego). Two approaches:

1. Always include ALL variant defs in `cfg.pieces`. Cheap (~9 entries).
   Promotion targets are looked up by id; the renderer only displays
   what's on the board so unused defs cost nothing.
2. Walk `promotes_to` lists and pull in referenced defs. More work,
   no real benefit at this scale.

**Recommendation:** option 1.

### 3.5 Promotion implications

The Bandit Pawn has `promotes_to = []`. The existing
[`_emit_promotions`](godot/engine/Rules.gd#L296) already handles empty
promotion lists by emitting a plain move record with no `promo` key —
the bandit pawn simply walks onto its 8th rank if it ever gets there
(though its cross/X moveset means rank 8 is reachable only via capture
diagonals, which is fine).

### 3.6 What does NOT change

- `Rules.gd` — every variant works through existing pattern primitives.
- `Piece.gd`, `GameState.gd`, `Move.gd` — unchanged.
- Push-chain, status effects, ability system — unchanged.
- `apply_move` move-vs-attack split — unchanged.

---

## 4. Sprite & animation pipeline

### 4.1 Decision: programmatic spritesheets

Both projects already use programmatic sprite generation —
[SpriteFactory.gd](godot/engine/SpriteFactory.gd) draws Chess-2 pieces
from 16×16 ASCII patterns into `Texture2D`, and Game-sandbox's
[generate_sprites.py](../Game-sandbox/generate_sprites.py) generates
multi-frame spritesheets with PIL. The migration is to extend the
former in the direction of the latter, in GDScript at runtime.

**Why programmatic, not hand-drawn:**

- Same pattern → many frames means ~1 line of code per frame, not 1
  drawing per frame.
- Adding a new variant costs the same as adding a new static sprite —
  one new pattern array in `SpriteFactory.gd`.
- Recoloring (white / black sides, hit flash) stays trivial.

**Why spritesheets over tween-only motion:**

- Variant identity needs animation, not just silhouette. A bandit pawn
  reads as a different piece because it *moves* differently (skulk vs.
  the pawn's upright shuffle), not just because the pattern has 2
  pixels in different places.
- The Knight's jump and Alter Knight's lunge are *part of the variant
  spec* — the user explicitly called these out as differentiating.
  Position tweens can fake an arc, but anticipation pose + landing
  squash sells "jump" in a way pure motion cannot.
- The architectural change is small (see §4.5).

### 4.2 Native resolution

Stay at **16×16 native** for now. Risks:

- A 16×16 idle bob has only a few rows of headroom for vertical motion;
  the silhouette can look cramped. Acceptable trade-off given existing
  pattern art is at this size.
- If Phase 1 (idle bobs on existing pieces) shows the motion is mushy,
  upscale **before** authoring more frames — re-doing 6 patterns at
  24px is fine, re-doing 100 frames is not.

### 4.3 Animation set

Per-variant animation list:

| Animation | Frames | Played when |
|---|---|---|
| `idle` | 4–6 (loop) | Default state; gentle bob / sway |
| `move` | 6–8 (one-shot) | Piece moves to a new square (no capture) |
| `attack` | 6–8 (one-shot) | Piece captures or damages |
| `hit` | 3 (one-shot) | Piece took damage but survived |
| `death` | 4 (one-shot) | Piece HP reached zero |

Knight + Alter Knight have an additional `move_jump` animation (the
parabolic leap). Alter Knight's `attack` animation is the king-style
straight-line lunge. Bandit Pawn's `move` is a cross-step shuffle and
its `attack` is an X-pounce.

`hit` and `death` can be shared across all variants for v1 (a flash +
crumple animation works for any silhouette). Specialize later only if
needed.

### 4.4 Move-to-animation mapping

The renderer needs to pick the right animation when a move is played.
Inputs available: `Move` dict from `Rules.apply_move()` events, plus
the `def_id` of the piece on the from-square at apply time.

Mapping rules:

```
event.kind == "move":
    if def_id is "knight" or "alter_knight" and not has("capture"):
        play "move_jump"
    else:
        play "move"

event.kind == "damage" or "kill" (with attacker on from-square):
    if def_id is "alter_knight":
        play "attack" (king-lunge animation)
    else:
        play "attack" (default for that variant)

event.kind == "damage" on victim square (victim survives):
    play "hit" on victim
event.kind == "kill" on victim square:
    play "death" on victim
```

No new fields on the move dict needed. The renderer keys off
`m.has("capture")` and the piece's `def_id`.

### 4.5 SpriteFactory migration

Today: `SpriteFactory.piece_texture(id, color) -> Texture2D` produces
a single static texture per (id, color), cached.

Target API: `SpriteFactory.piece_frames(id, color) -> SpriteFrames`,
returning a Godot `SpriteFrames` resource with named animations
(`"idle"`, `"move"`, `"attack"`, `"hit"`, `"death"`, plus
`"move_jump"` for knights). Cached identically.

Internal structure:

```gdscript
static func piece_frames(piece_id: String, color: int) -> SpriteFrames:
    var key := "piece_frames:%s:%d" % [piece_id, color]
    if _cache.has(key): return _cache[key]
    var sf := SpriteFrames.new()
    _add_idle(sf, piece_id, color)
    _add_move(sf, piece_id, color)
    _add_attack(sf, piece_id, color)
    _add_hit(sf, piece_id, color)
    _add_death(sf, piece_id, color)
    if _piece_has_jump(piece_id):
        _add_move_jump(sf, piece_id, color)
    _cache[key] = sf
    return sf
```

Each `_add_*` builds frames from the variant's pattern + an
animation-specific transform applied per frame:

- `idle` — vertical 1-pixel bob; copy pattern, shift body rows by 0
  for half the frames and by -1 for the other half, alternated to
  produce a sway.
- `move` — same body, with motion lines or a slight forward lean
  on intermediate frames.
- `attack` — wind-up frame (slight back-lean), strike frame (forward
  lunge), recoil frame (pulled back). For the alter knight's straight
  lunge, exaggerate the strike-frame forward extension.
- `move_jump` (knight, alter knight) — squash before liftoff,
  tucked-leg silhouette mid-air, landing dust + squash on touchdown.
  The vertical arc itself is still a tween on the Y position; the
  spritesheet sells the *pose* changes.
- `hit` / `death` — generic; full-piece tint to red for hit, then
  pixel-by-pixel collapse for death.

The pattern-mutation helpers should compose, so a variant's `attack`
animation is just `_lunge(_pattern_for(id), strength)` not a new
hand-authored array.

### 4.6 GameScene rendering changes

Today [GameScene.gd line 376-385](godot/scenes/GameScene.gd#L376-L385)
puts a `TextureRect` in each square. Migration:

- Replace `TextureRect` with `AnimatedSprite2D` (or `TextureRect` whose
  texture is swapped per-frame from a `SpriteFrames` resource — Godot
  supports both).
- Default to `play("idle")`.
- On `move` events, play the correct one-shot animation, then return to
  `idle` via `animation_finished`.
- Existing position/knockback tweens stay — they layer on top of
  whatever animation is playing.

The piece-render call site changes from
`sprite.texture = SpriteFactory.piece_texture(p.def_id, p.color)` to
`sprite.sprite_frames = SpriteFactory.piece_frames(p.def_id, p.color);
sprite.play("idle")`.

### 4.7 Knight jump arc tween

Independent of spritesheets: the move tween for normal knight and
alter knight (when moving non-capture) gets a parabolic Y offset on
top of the linear from→to interpolation:

```gdscript
# t in [0, 1] over ANIM_MOVE_DURATION.
var arc_height := 24.0   # pixels
var y_offset := -arc_height * 4.0 * t * (1.0 - t)   # parabola peaking at t=0.5
```

This is a few-line change in the existing `_animate_events` block in
[GameScene.gd](godot/scenes/GameScene.gd).

---

## 5. Customization UI changes

### 5.1 New layout

Replace the granular per-piece editor in
[CustomizationScene.gd](godot/scenes/CustomizationScene.gd) with a
**variant picker grid**:

```
┌─────────────────────────────────────────────────────┐
│  Customize Pieces        [Reset]  [Cancel] [Save]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│   Pawn                                              │
│   ┌──────────────┐  ┌──────────────┐                │
│   │ ◉ Regular    │  │ ○ Bandit     │                │
│   │ [sprite]     │  │ [sprite]     │                │
│   │ 1HP / 1DMG   │  │ 1HP / 1DMG   │                │
│   │ Push, double,│  │ Cross-move,  │                │
│   │ promotes     │  │ X-attack     │                │
│   └──────────────┘  └──────────────┘                │
│                                                     │
│   Bishop                                            │
│   ┌──────────────┐  ┌──────────────┐                │
│   │ ◉ Regular    │  │ ○ Assassin   │                │
│   │ ...          │  │ ...          │                │
│   └──────────────┘  └──────────────┘                │
│                                                     │
│   Knight                                            │
│   ┌──────────────┐  ┌──────────────┐                │
│   │ ◉ Normal     │  │ ○ Alter Ego  │                │
│   │ ...          │  │ ...          │                │
│   └──────────────┘  └──────────────┘                │
│                                                     │
│   Rook | Queen | King   (one variant each)          │
│                                                     │
│   ─── Abilities ─────────────────────────────────── │
│   ◯ Cannon    ◉ Lightning                           │
│                                                     │
└─────────────────────────────────────────────────────┘
```

Each variant card shows: live animated sprite (idle loop), HP/damage,
1-line move description, on-hit effect if any.

The reachability preview (the 8×8 mini-board showing where a piece can
reach) carries over — render it under the *currently-selected* variant
card so picking a variant updates the preview live.

### 5.2 Removed UI

The current panel sections going away:

- "Identity" (name / glyph) — variant-defined.
- "Stats" (HP / damage spinboxes) — variant-defined.
- "Movement" (six checkboxes + range spinbox) — replaced by variant
  description text.
- "On-hit status effect" — variant-defined.

The "Reset this piece to default" button becomes "reset to regular
variant" (i.e. set this slot back to the default variant).

The ability editor (Cannon / Lightning parameters) **stays** — abilities
are global and orthogonal to piece variants.

### 5.3 Persistence

`GameSettings.active_config` already serializes via Godot's
`ResourceSaver`. The new `variant_selection` dict on `GameConfig` is
@export-tagged so it persists automatically. On load, call
`rebuild_initial_setup()` to project the selection back into
`cfg.pieces` and `cfg.initial_setup`.

Old saves (before variants existed) should default to the regular
variant for every slot — `rebuild_initial_setup` is idempotent and
safe to run on a freshly loaded config that doesn't yet have the
field.

---

## 6. Implementation phases

Each phase is independently shippable and testable. Don't bundle.

### Phase 1 — Spritesheet pipeline (no new pieces, no rules changes)

**Goal:** prove the SpriteFrames migration works at board scale before
investing in variant art.

Tasks:

1. Add `piece_frames(id, color) -> SpriteFrames` to
   [SpriteFactory.gd](godot/engine/SpriteFactory.gd) alongside the
   existing `piece_texture`.
2. Implement `_add_idle` for all 6 existing pieces — gentle 4-frame
   bob.
3. Swap [GameScene.gd](godot/scenes/GameScene.gd) board renderer from
   `TextureRect` to `AnimatedSprite2D` (or equivalent), playing
   `"idle"` by default.
4. Verify: the board still reads cleanly at the existing zoom; idle
   bobs are visible but not distracting; no perf regression with 32
   simultaneous animated sprites.

**Decision gate:** if 16×16 looks too cramped for animation, upscale
patterns to 24×24 here, before authoring move/attack frames.

**Ship:** existing customization UI unchanged. Only visual change is
that pieces now bob on the board.

### Phase 2 — Variant system + new pieces

**Goal:** ship the three new variants with their gameplay mechanics.

Tasks:

1. Add `CROSS_OFFS`, `X_OFFS`, `ASSASSIN_OFFS` constants to
   [Defaults.gd](godot/engine/Defaults.gd).
2. Add variant factory functions: `_make_bandit_pawn`,
   `_make_assassin_bishop`, `_make_alter_knight`. Existing
   `_make_piece` helper handles all the heavy lifting.
3. Add `_make_variants_map()` and the `variant_selection` field on
   `GameConfig`.
4. Add `cfg.rebuild_initial_setup()` and call it from
   `Defaults.make_default_config` and from save/load paths.
5. Replace [CustomizationScene.gd](godot/scenes/CustomizationScene.gd)
   editor pane with the variant picker grid (§5.1). Keep the ability
   editor sub-page.
6. Add `move`, `attack`, `hit`, `death` animations to
   `SpriteFactory.piece_frames` for all variants. Reuse `hit` and
   `death` across variants.

**Verification:**

- Spawn a board with each new variant; play a few moves with each.
- Verify bandit pawn cannot promote and cannot double-push.
- Verify assassin bishop can land on a square with a friendly piece
  blocking the line (it can't, friendlies still block landing — but it
  *can* hop *over* a blocker to reach an empty square, which the test
  should confirm).
- Verify alter knight uses knight-shape for non-captures and
  king-shape for captures via legal-move enumeration.
- Run existing test suite — no engine regressions.

**Ship:** customization screen now offers variant selection. New
pieces are playable. Animations: idle + move/attack are sprite-driven.

### Phase 3 — Polish: knight jump, attack animations, special motion

**Goal:** the variants *feel* different in motion.

Tasks:

1. Add `move_jump` animation to `SpriteFactory.piece_frames` for
   knight + alter knight.
2. Add parabolic Y-arc tween in [GameScene.gd](godot/scenes/GameScene.gd)
   move animator, gated on the piece being a knight variant moving
   non-capture.
3. Add the king-lunge attack animation specifically for alter knight
   (longer forward extension on the strike frame, sustained recoil).
4. Add bandit pawn's cross-step move animation and X-pounce attack
   animation.
5. Tune `ANIM_MOVE_DURATION` per piece if needed (knight jumps may
   want a slightly longer beat to sell the arc).

**Verification:** play a full hot-seat game using new variants; gut
check that animations read well and don't drag pacing.

**Ship:** full variant differentiation in motion. Good enough for an
end-to-end "polished" feel.

### Phase 4 (deferred) — stretch

Out-of-scope-but-noted-in-case:

- Per-variant `hit` and `death` animations (e.g. assassin bishop fades
  out instead of crumpling).
- Sound effects matched to attack animations.
- Variant-specific particle effects (bandit pawn kicks up dust,
  assassin bishop leaves an afterimage).
- More variants per slot (e.g. a third pawn variant).

---

## 7. File-by-file change list

| File | Phase | Change |
|---|---|---|
| [godot/engine/data/GameConfig.gd](godot/engine/data/GameConfig.gd) | 2 | Add `variant_selection` dict; add `rebuild_initial_setup()` |
| [godot/engine/Defaults.gd](godot/engine/Defaults.gd) | 2 | Add new offset constants; split `_make_piece` calls into per-variant factories; add `_make_variants_map`; default `variant_selection` |
| [godot/engine/SpriteFactory.gd](godot/engine/SpriteFactory.gd) | 1, 2, 3 | Add `piece_frames(id, color)`; idle bob (P1); move/attack/hit/death (P2); jump + lunge specializations (P3); add patterns for `bandit_pawn`, `assassin_bishop`, `alter_knight` (P2) |
| [godot/scenes/GameScene.gd](godot/scenes/GameScene.gd) | 1, 3 | Swap `TextureRect` → animated sprite; route move/attack events to animations; add knight jump arc tween (P3) |
| [godot/scenes/CustomizationScene.gd](godot/scenes/CustomizationScene.gd) | 2 | Replace per-piece editor pane with variant picker grid; keep ability sub-page; remove movement-toggle helpers (`_infer_toggles`, `_toggles_to_patterns`, related field handlers) |
| [godot/autoloads/GameSettings.gd](godot/autoloads/GameSettings.gd) | 2 | On load, call `cfg.rebuild_initial_setup()`; default `variant_selection` for old saves missing the field |
| [DESIGN.md](DESIGN.md) | 2 | New section: piece variants concept (brief — full detail lives in this doc) |
| [IMPLEMENTATION-GODOT.md](IMPLEMENTATION-GODOT.md) | 2 | Update §1 scope: variant picker replaces granular customization; cross-link to this doc |

[Rules.gd](godot/engine/Rules.gd), [Piece.gd](godot/engine/state/Piece.gd),
[GameState.gd](godot/engine/state/GameState.gd), [Move.gd](godot/engine/state/Move.gd),
ability files, and stage-hazard files — **no changes**.

---

## 8. Open questions

These don't block implementation but are worth deciding before
Phase 2 ships:

1. **Mirror by color?** Bandit pawn is symmetric so it works identically
   for both sides. But should the regular pawn's promotion targets be
   pulled from the *opposing* side's selected variants? (E.g. if Black
   plays Alter Knight, does a White pawn promoting to "knight" become
   a normal knight or an alter knight?) Recommendation: pawns always
   promote to the **regular** variants regardless of slot selection,
   to avoid a player accidentally locking themselves out of a piece
   shape they wanted as a promotion target. The regular variant defs
   are always in `cfg.pieces` (per §3.4) so this is free.
2. **Variant identity in saved games / replays?** If the on-disk save
   format ever needs to round-trip mid-game state, `Piece.def_id`
   already encodes the variant. No change needed unless save format
   gains a "starting config" field separate from per-square defs.
3. **AI / future networked play** — variant selection becomes part of
   the agreed-upon configuration before a game starts. Same protocol
   slot as today's customization payload.
