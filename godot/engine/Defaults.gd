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
						 maxc: int = 1, init_c: int = 0) -> SpecialAbilityDef:
	var s := SpecialAbilityDef.new()
	s.kind = kind
	s.damage = damage
	s.cooldown_turns = cd
	s.max_charges = maxc
	s.initial_charges = init_c
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

static func make_default_config() -> GameConfig:
	var cfg := GameConfig.new()
	cfg.pieces = {}

	cfg.pieces["king"] = _make_piece(
		"king", "King", "♚",
		3, 1, true, true,
		[_make_pat(MovePattern.Kind.LEAPER, KING_OFFS)],
	)

	cfg.pieces["queen"] = _make_piece(
		"queen", "Queen", "♛",
		5, 2, false, false,
		[
			_make_pat(MovePattern.Kind.RIDER, ORTHO),
			_make_pat(MovePattern.Kind.RIDER, DIAG),
		],
	)

	cfg.pieces["rook"] = _make_piece(
		"rook", "Rook", "♜",
		3, 1, false, false,
		[_make_pat(MovePattern.Kind.RIDER, ORTHO)],
		## On-hit ignite: surviving target burns for 1 dmg/turn × 2 turns.
		_make_effect(StatusEffectDef.Kind.BURN, 1, 2),
	)

	cfg.pieces["bishop"] = _make_piece(
		"bishop", "Bishop", "♝",
		2, 1, false, false,
		[_make_pat(MovePattern.Kind.RIDER, DIAG)],
	)

	cfg.pieces["knight"] = _make_piece(
		"knight", "Knight", "♞",
		2, 1, false, false,
		[_make_pat(MovePattern.Kind.LEAPER, KNIGHT_OFFS)],
		## On-hit freeze: target skips next turn.
		_make_effect(StatusEffectDef.Kind.FREEZE, 0, 1),
	)

	cfg.pieces["pawn"] = _make_piece(
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

	## Global abilities — both players share these specs but each has their
	## own runtime charges (GameState.cannon_state / .lightning_state).
	## Only one of them is active at a time per cfg.enabled_ability.
	cfg.cannon    = make_special(SpecialAbilityDef.Kind.CANNON,    2, 4, 1, 0)
	cfg.lightning = make_special(SpecialAbilityDef.Kind.LIGHTNING, 1, 3, 1, 1)
	cfg.enabled_ability = SpecialAbilityDef.Kind.LIGHTNING

	## Standard opening setup. Index 0 = a1.
	var back: Array[String] = ["rook","knight","bishop","queen","king","bishop","knight","rook"]
	var setup: Array = []
	setup.resize(64)
	for f in 8:
		setup[f]      = { "id": back[f], "color": 0 }
		setup[8 + f]  = { "id": "pawn",  "color": 0 }
		setup[48 + f] = { "id": "pawn",  "color": 1 }
		setup[56 + f] = { "id": back[f], "color": 1 }
	cfg.initial_setup = setup

	return cfg
