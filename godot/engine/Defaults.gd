## Defaults factory — builds the standard six piece defs, the global ability
## specs, and an opening setup. Called by GameSettings on first run (no save
## file present). Tunable values documented in IMPL-GODOT §10.6 and DESIGN.md
## §10/§11.
class_name Defaults
extends RefCounted

const ORTHO := [
	Vector2i(1, 0), Vector2i(-1, 0),
	Vector2i(0, 1), Vector2i(0, -1),
]
const DIAG := [
	Vector2i(1, 1), Vector2i(1, -1),
	Vector2i(-1, 1), Vector2i(-1, -1),
]
const KING_OFFS := [
	Vector2i(1, 0), Vector2i(-1, 0),
	Vector2i(0, 1), Vector2i(0, -1),
	Vector2i(1, 1), Vector2i(1, -1),
	Vector2i(-1, 1), Vector2i(-1, -1),
]
const KNIGHT_OFFS := [
	Vector2i(1, 2), Vector2i(2, 1),
	Vector2i(-1, 2), Vector2i(-2, 1),
	Vector2i(1, -2), Vector2i(2, -1),
	Vector2i(-1, -2), Vector2i(-2, -1),
]

## Cross / plus shape — alias of ORTHO. Used at the bandit-pawn call site
## to make the "cross-step" intent obvious.
const CROSS_OFFS := ORTHO

## X / single-square diagonals — alias of DIAG. Used by bandit-pawn capture.
const X_OFFS := DIAG

## Assassin Bishop — 1- and 2-square diagonals. LEAPER ignores blockers,
## which is exactly the "jumps to target instead of sliding" behavior.
const ASSASSIN_OFFS := [
	Vector2i( 1,  1), Vector2i( 1, -1), Vector2i(-1,  1), Vector2i(-1, -1),
	Vector2i( 2,  2), Vector2i( 2, -2), Vector2i(-2,  2), Vector2i(-2, -2),
]

static func _make_pat(kind: int, offsets: Array = [], max_range: int = 0,
					  capture_only: bool = false, move_only: bool = false) -> MovePattern:
	var p := MovePattern.new()
	p.kind = kind
	var typed: Array[Vector2i] = []
	for o in offsets:
		typed.append(o)
	p.offsets = typed
	p.max_range = max_range
	p.capture_only = capture_only
	p.move_only = move_only
	return p

static func _make_effect(kind: int, dpt: int = 0, dur: int = 0) -> StatusEffectDef:
	var e := StatusEffectDef.new()
	e.kind = kind
	e.damage_per_turn = dpt
	e.duration = dur
	return e

static func make_special(kind: int, damage: int = 1, cd: int = 3,
						 maxc: int = 1, init_c: int = 0,
						 energy_cost: int = 4) -> SpecialAbilityDef:
	var s := SpecialAbilityDef.new()
	s.kind = kind
	s.damage = damage
	s.cooldown_turns = cd
	s.max_charges = maxc
	s.initial_charges = init_c
	s.energy_cost = energy_cost
	return s

static func _make_piece(id: String, display_name: String, glyph: String,
						hp: int, dmg: int, royal: bool, can_castle: bool,
						patterns: Array, on_hit: StatusEffectDef = null,
						promotes_to: Array[String] = []) -> PieceDef:
	var d := PieceDef.new()
	d.id = id
	d.display_name = display_name
	d.glyph = glyph
	d.hp = hp
	d.damage = dmg
	d.royal = royal
	d.can_castle = can_castle
	var tp: Array[MovePattern] = []
	for p in patterns:
		tp.append(p)
	d.move_patterns = tp
	d.on_hit = on_hit if on_hit != null else _make_effect(StatusEffectDef.Kind.NONE)
	d.promotes_to = promotes_to
	return d

## ===========================================================================
## Per-variant factories. Each returns a fresh PieceDef. The factories live
## here (not on PieceDef itself) so the customization picker can pull them
## by id from `_make_variants_map()` without a class registry.
## ===========================================================================

static func _make_regular_king() -> PieceDef:
	return _make_piece(
		"king", "King", "♚",
		3, 1, true, true,
		[_make_pat(MovePattern.Kind.LEAPER, KING_OFFS)],
	)

static func _make_regular_queen() -> PieceDef:
	return _make_piece(
		"queen", "Queen", "♛",
		5, 2, false, false,
		[
			_make_pat(MovePattern.Kind.RIDER, ORTHO),
			_make_pat(MovePattern.Kind.RIDER, DIAG),
		],
	)

static func _make_regular_rook() -> PieceDef:
	return _make_piece(
		"rook", "Rook", "♜",
		3, 1, false, false,
		[_make_pat(MovePattern.Kind.RIDER, ORTHO)],
		## On-hit ignite: surviving target burns for 1 dmg/turn × 2 turns.
		_make_effect(StatusEffectDef.Kind.BURN, 1, 2),
	)

static func _make_regular_bishop() -> PieceDef:
	return _make_piece(
		"bishop", "Bishop", "♝",
		2, 1, false, false,
		[_make_pat(MovePattern.Kind.RIDER, DIAG)],
	)

static func _make_regular_knight() -> PieceDef:
	return _make_piece(
		"knight", "Knight", "♞",
		2, 1, false, false,
		[_make_pat(MovePattern.Kind.LEAPER, KNIGHT_OFFS)],
		## On-hit freeze: target skips next turn.
		_make_effect(StatusEffectDef.Kind.FREEZE, 0, 1),
	)

static func _make_regular_pawn() -> PieceDef:
	return _make_piece(
		"pawn", "Pawn", "♟",
		1, 1, false, false,
		[
			_make_pat(MovePattern.Kind.PAWN_PUSH),
			_make_pat(MovePattern.Kind.PAWN_DOUBLE),
			_make_pat(MovePattern.Kind.PAWN_CAPTURE),
		],
		null,
		["queen", "rook", "bishop", "knight"],
	)

## Bandit Pawn — moves in a cross (4 ortho neighbors), attacks in an X (4
## diagonals). No double-push. No promotion. Symmetric: same moveset for
## both colors. PIECE-VARIANTS.md §2.1.
static func _make_bandit_pawn() -> PieceDef:
	return _make_piece(
		"bandit_pawn", "Bandit Pawn", "✠",
		1, 1, false, false,
		[
			_make_pat(MovePattern.Kind.LEAPER, CROSS_OFFS, 0, false, true),
			_make_pat(MovePattern.Kind.LEAPER, X_OFFS,     0, true,  false),
		],
	)

## Assassin Bishop — jumps up to 2 squares diagonally, ignoring blockers.
## Range capped via the offset list itself (LEAPER offsets are explicit).
## PIECE-VARIANTS.md §2.2.
static func _make_assassin_bishop() -> PieceDef:
	return _make_piece(
		"assassin_bishop", "Assassin Bishop", "♗",
		2, 1, false, false,
		[_make_pat(MovePattern.Kind.LEAPER, ASSASSIN_OFFS)],
	)

## Alter Ego Knight — knight-shape moves (non-capture), king-shape attacks
## (capture-only). Inherits the on-hit freeze from the regular knight.
## PIECE-VARIANTS.md §2.3.
static func _make_alter_knight() -> PieceDef:
	return _make_piece(
		"alter_knight", "Alter Ego Knight", "♘",
		2, 1, false, false,
		[
			_make_pat(MovePattern.Kind.LEAPER, KNIGHT_OFFS, 0, false, true),
			_make_pat(MovePattern.Kind.LEAPER, KING_OFFS,   0, true,  false),
		],
		_make_effect(StatusEffectDef.Kind.FREEZE, 0, 1),
	)

## Variant catalog — keyed by base slot. Order matters: index 0 is the
## default/regular variant for that slot. CustomizationScene reads this
## directly to populate the variant picker. Slots with only one variant
## still appear so the picker can show "no choices yet" for them.
static func make_variants_map() -> Dictionary:
	return {
		"pawn":   [_make_regular_pawn(),   _make_bandit_pawn()],
		"bishop": [_make_regular_bishop(), _make_assassin_bishop()],
		"knight": [_make_regular_knight(), _make_alter_knight()],
		"rook":   [_make_regular_rook()],
		"queen":  [_make_regular_queen()],
		"king":   [_make_regular_king()],
	}

## Slot order — the order in which slots appear in the variant picker, and
## also used to lay out the back rank in `rebuild_initial_setup`.
static func variant_slots() -> Array:
	return ["pawn", "knight", "bishop", "rook", "queen", "king"]

static func default_variant_selection() -> Dictionary:
	## All slots default to their first (regular) variant.
	var sel: Dictionary = {}
	for slot in variant_slots():
		sel[slot] = slot   ## variant id == slot id for the regulars
	return sel

## Build the full piece-id → PieceDef map containing every variant from
## every slot. Used so promotion targets (which reference ids by string)
## always find a def, even if the player hasn't selected that variant for
## the relevant slot. Cheap (~9 entries) and avoids walking promotes_to
## chains — see PIECE-VARIANTS.md §3.4 (option 1).
static func build_full_pieces_map() -> Dictionary:
	var out: Dictionary = {}
	var vmap := make_variants_map()
	for slot in vmap.keys():
		for def in vmap[slot]:
			out[def.id] = def
	return out

static func make_default_config() -> GameConfig:
	var cfg := GameConfig.new()
	cfg.pieces = build_full_pieces_map()

	## Global abilities — both players share these specs but each has their
	## own runtime charges (GameState.cannon_state / .lightning_state).
	## Only one of them is active at a time per cfg.enabled_ability.
	## (kind, damage, cooldown, max_charges, initial_charges, energy_cost).
	## Energy costs roughly mirror Clash Royale's elixir costs: cheap quick
	## strikes vs. expensive AOE. Both still gated by the per-turn cooldown.
	cfg.cannon    = make_special(SpecialAbilityDef.Kind.CANNON,    2, 4, 1, 0, 5)
	cfg.lightning = make_special(SpecialAbilityDef.Kind.LIGHTNING, 1, 3, 1, 1, 3)
	cfg.enabled_ability = SpecialAbilityDef.Kind.LIGHTNING

	cfg.variant_selection = default_variant_selection()
	cfg.rebuild_initial_setup()
	return cfg
