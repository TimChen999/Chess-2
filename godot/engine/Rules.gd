## ============================================================================
## Rules.gd — pure rules engine for Chess² (HP variant + special abilities)
## ============================================================================
## Theory:  ../DESIGN.md             §1–§13
## Plan:    ../IMPLEMENTATION-GODOT.md  §1–§19
##
## Layering (DESIGN.md §13). Every higher layer depends only on the layer
## directly below it:
##
##   game_status()            ← once per turn — { kind, in_check, moves }
##        |
##   legal_moves()            ← HP-aware self-check filter
##        |
##   pseudo_legal_moves()     ← data-driven over MovePattern records
##        |
##   apply_move()             ← HP, push-chain, status effects, ability fire,
##                              side flip, turn-start tick
##        |
##   is_attacked() /          ← per-square attack primitives
##   max_incoming_damage()
##
## State is immutable from the engine's POV — every mutator returns a NEW
## GameState. This makes the self-check filter trivial (clone, play, query)
## and makes save-state additions cheap later.
##
## All public functions are static. Callers use `Rules.foo(...)`.
## (Named `Rules` instead of `Engine` because `Engine` is a Godot built-in
## singleton — class_name would collide.)
## ============================================================================
class_name Rules
extends RefCounted

const WHITE := 0
const BLACK := 1

## Plus-shape AOE pattern for Cannon (centered on target square).
const CANNON_PLUS_OFFSETS: Array[Vector2i] = [
	Vector2i(0, 0),
	Vector2i(1, 0), Vector2i(-1, 0),
	Vector2i(0, 1), Vector2i(0, -1),
]

# ---------------------------------------------------------------------------
# COORDINATE HELPERS
# Square indexing: sq = rank * 8 + file. Rank 0 = white's back rank, rank 7
# = black's. The renderer flips this so white sits at the bottom on screen.
# ---------------------------------------------------------------------------

static func opposite(c: int) -> int: return BLACK if c == WHITE else WHITE
static func file_of(sq: int) -> int: return sq & 7
static func rank_of(sq: int) -> int: return sq >> 3
static func sq_of(f: int, r: int) -> int: return r * 8 + f
static func in_bounds(f: int, r: int) -> bool: return f >= 0 and f < 8 and r >= 0 and r < 8

# ---------------------------------------------------------------------------
# PIECE FACTORY / FIND
# ---------------------------------------------------------------------------

static func make_piece(def_id: String, color: int, def: PieceDef) -> Piece:
	var p := Piece.new()
	p.def_id = def_id
	p.color = color
	p.hp = def.hp
	if def.special != null and def.special.kind != SpecialAbilityDef.Kind.NONE:
		p.special_charges = def.special.initial_charges
		p.special_recharge = def.special.cooldown_turns
	return p

static func find_royal(state: GameState, color: int) -> int:
	for i in 64:
		var p = state.board[i]
		if p != null and p.color == color and state.config.pieces[p.def_id].royal:
			return i
	return -1

static func is_frozen(piece: Piece) -> bool:
	if piece == null: return false
	for e in piece.active_effects:
		if e.kind == StatusEffectDef.Kind.FREEZE and e.turns_remaining > 0:
			return true
	return false

# ---------------------------------------------------------------------------
# STATE CONSTRUCTION
# ---------------------------------------------------------------------------

static func new_game(config: GameConfig) -> GameState:
	var s := GameState.new()
	s.config = config
	s.board.resize(64)
	for i in 64:
		s.board[i] = null
	var n := mini(config.initial_setup.size(), 64)
	for i in n:
		var cell = config.initial_setup[i]
		if cell == null: continue
		if not config.pieces.has(cell["id"]):
			push_error("new_game: missing piece def '%s'" % cell["id"])
			continue
		var def: PieceDef = config.pieces[cell["id"]]
		s.board[i] = make_piece(cell["id"], int(cell["color"]), def)

	## Snapshot which squares each color OCCUPIES at game start. Cannon's
	## forbidden-target rule (§7.1) tests against this set, NOT current
	## positions — pieces may have moved.
	s.initial_squares_by_color = [{}, {}]
	for i in 64:
		var p = s.board[i]
		if p != null:
			s.initial_squares_by_color[p.color][i] = true

	return s

# =============================================================================
# PRIMITIVE — is_attacked / max_incoming_damage
# -----------------------------------------------------------------------------
# "Could `by_color` capture `sq` if they got to move next?"
#
# Variant-aware version (DESIGN §8.3): instead of walking outward asking
# "is there a knight here, a rook on this ray", we iterate enemy pieces and
# generate their pseudo-moves. Cost is O(pieces × moves-per-piece) — fine
# for a UI doing tens of queries per turn.
#
# `max_incoming_damage` returns the MAX attacker.damage (DESIGN §10.8). The
# HP-aware check predicate compares king HP against this number, not 1.
# =============================================================================

static func max_incoming_damage(state: GameState, sq: int, by_color: int) -> int:
	var best := 0
	for from_sq in 64:
		var p = state.board[from_sq]
		if p == null or p.color != by_color: continue
		if is_frozen(p): continue
		var def: PieceDef = state.config.pieces[p.def_id]
		var targets := attack_targets_from_square(state, from_sq, p, def)
		for t in targets:
			if t == sq:
				if def.damage > best: best = def.damage
				break
	return best

static func is_attacked(state: GameState, sq: int, by_color: int) -> bool:
	return max_incoming_damage(state, sq, by_color) > 0

## Generate squares this piece could ATTACK from `from_sq` — squares where
## an enemy currently sits AND this piece could land. Used only by the
## attack primitives.
static func attack_targets_from_square(state: GameState, from_sq: int,
									   piece: Piece, def: PieceDef) -> Array:
	var out: Array = []
	for pat in def.move_patterns:
		if pat.move_only: continue
		_collect_pattern_targets(state, from_sq, piece, pat, out, true)
	var targets: Array = []
	for m in out:
		targets.append(int(m["to"]))
	return targets

# ---------------------------------------------------------------------------
# MOVE-PATTERN INTERPRETER (data-driven; replaces hardcoded piece branches)
# ---------------------------------------------------------------------------
# Targets are pushed as Dictionary records so apply_move can inspect flags
# (capture, double-push, en-passant, promotion, castle).  capture_only_mode
# = true is used by attack-target enumeration: only emit captures.
# ---------------------------------------------------------------------------

static func _collect_pattern_targets(state: GameState, from_sq: int,
									 piece: Piece, pat: MovePattern,
									 out: Array, capture_only_mode: bool) -> void:
	var f := file_of(from_sq)
	var r := rank_of(from_sq)
	var board := state.board
	var my_color := piece.color
	## Pawn forward direction (NOT the same as the post-attack push direction
	## from §10.4, which is the OPPOSITE — toward home rank).
	var fwd := 1 if my_color == WHITE else -1

	match pat.kind:
		MovePattern.Kind.LEAPER:
			for off in pat.offsets:
				var nf := f + off.x
				var nr := r + off.y
				if not in_bounds(nf, nr): continue
				var to := sq_of(nf, nr)
				var tgt = board[to]
				if capture_only_mode:
					if tgt != null and tgt.color != my_color:
						out.append({ "from": from_sq, "to": to, "capture": true })
				else:
					if tgt == null:
						if not pat.capture_only:
							out.append({ "from": from_sq, "to": to })
					elif tgt.color != my_color:
						if not pat.move_only:
							out.append({ "from": from_sq, "to": to, "capture": true })

		MovePattern.Kind.RIDER:
			var max_r := pat.max_range if pat.max_range > 0 else 7
			for dir_v in pat.offsets:
				var nf := f + dir_v.x
				var nr := r + dir_v.y
				var steps := 0
				while in_bounds(nf, nr) and steps < max_r:
					var to := sq_of(nf, nr)
					var tgt = board[to]
					if tgt == null:
						if not capture_only_mode and not pat.capture_only:
							out.append({ "from": from_sq, "to": to })
					else:
						if tgt.color != my_color and not pat.move_only:
							out.append({ "from": from_sq, "to": to, "capture": true })
						break
					nf += dir_v.x
					nr += dir_v.y
					steps += 1

		MovePattern.Kind.PAWN_PUSH:
			if capture_only_mode: return
			var nr := r + fwd
			if not in_bounds(f, nr): return
			var to := sq_of(f, nr)
			if board[to] == null:
				var promo_rank := 7 if my_color == WHITE else 0
				if nr == promo_rank:
					_emit_promotions(state, piece, from_sq, to, false, out)
				else:
					out.append({ "from": from_sq, "to": to })

		MovePattern.Kind.PAWN_DOUBLE:
			if capture_only_mode: return
			if piece.has_moved: return
			var r1 := r + fwd
			var r2 := r + 2 * fwd
			if not in_bounds(f, r2): return
			if board[sq_of(f, r1)] != null or board[sq_of(f, r2)] != null: return
			out.append({ "from": from_sq, "to": sq_of(f, r2), "double": true })

		MovePattern.Kind.PAWN_CAPTURE:
			var promo_rank := 7 if my_color == WHITE else 0
			for df: int in [-1, 1]:
				var nf := f + df
				var nr := r + fwd
				if not in_bounds(nf, nr): continue
				var to := sq_of(nf, nr)
				var tgt = board[to]
				if tgt != null and tgt.color != my_color:
					if nr == promo_rank:
						_emit_promotions(state, piece, from_sq, to, true, out)
					else:
						out.append({ "from": from_sq, "to": to, "capture": true })
				elif (not capture_only_mode) and tgt == null and to == state.ep:
					## En passant: legal only on the single ply after opponent's
					## 2-square pawn push. state.ep stores the target square.
					out.append({ "from": from_sq, "to": to,
								  "capture": true, "enpassant": true })

static func _emit_promotions(state: GameState, piece: Piece, from_sq: int,
							 to: int, capture: bool, out: Array) -> void:
	var def: PieceDef = state.config.pieces[piece.def_id]
	if def.promotes_to.size() == 0:
		var rec = { "from": from_sq, "to": to }
		if capture: rec["capture"] = true
		out.append(rec)
		return
	for promo in def.promotes_to:
		var rec = { "from": from_sq, "to": to, "promo": promo }
		if capture: rec["capture"] = true
		out.append(rec)

# ---------------------------------------------------------------------------
# pseudo_legal_moves — moves that obey movement rules but ignore self-check.
# Self-check (HP-aware) is enforced one layer up in legal_moves().
# ---------------------------------------------------------------------------

static func pseudo_legal_moves(state: GameState, color: int) -> Array:
	var moves: Array = []
	for from_sq in 64:
		var p = state.board[from_sq]
		if p == null or p.color != color: continue
		if is_frozen(p): continue       ## FREEZE: skip frozen pieces (§11.6)
		var def: PieceDef = state.config.pieces[p.def_id]
		for pat in def.move_patterns:
			_collect_pattern_targets(state, from_sq, p, pat, moves, false)
	return moves

# =============================================================================
# CASTLING — see DESIGN.md §5 "the three attack checks"
# -----------------------------------------------------------------------------
# 1. King not currently in check.
# 2. Transit square not attacked, with the king SIMULATED on the transit
#    square so rays previously blocked by the king's origin are now visible.
# 3. Destination not attacked — handled by the standard self-check filter.
# =============================================================================

static func _add_castling_moves(state: GameState, color: int, king_sq: int,
								moves: Array) -> void:
	var king: Piece = state.board[king_sq]
	var def: PieceDef = state.config.pieces[king.def_id]
	if not def.can_castle: return
	if king.has_moved: return
	var home_rank := 0 if color == WHITE else 7
	if king_sq != sq_of(4, home_rank): return
	if is_attacked(state, king_sq, opposite(color)): return

	_try_castle(state, color, king, king_sq, home_rank,
				7, [5, 6], 5, 6, 1, moves)
	_try_castle(state, color, king, king_sq, home_rank,
				0, [1, 2, 3], 3, 2, -1, moves)

static func _try_castle(state: GameState, color: int, king: Piece, king_sq: int,
						home_rank: int, rook_file: int, between_files: Array,
						transit_file: int, king_to_file: int, side_flag: int,
						moves: Array) -> void:
	var rook_sq := sq_of(rook_file, home_rank)
	var rook = state.board[rook_sq]
	if rook == null or rook.color != color or rook.has_moved: return
	for bf in between_files:
		if state.board[sq_of(bf, home_rank)] != null: return

	## (2) Simulate king on transit square; re-run is_attacked.
	var transit_sq := sq_of(transit_file, home_rank)
	var sim := state.clone_state()
	sim.board[king_sq] = null
	sim.board[transit_sq] = king
	if is_attacked(sim, transit_sq, opposite(color)): return

	moves.append({
		"from": king_sq, "to": sq_of(king_to_file, home_rank),
		"castle": side_flag,
	})

# =============================================================================
# apply_move — the only mutator. Returns a NEW state.
# -----------------------------------------------------------------------------
# Sequence (DESIGN §6, IMPL-GODOT §8.3):
#
#   1. Clone state.
#   2. Move/attack:
#      - empty target → relocate; if pawn double-push, set ep target.
#      - enemy target → ATTACK:
#          * effective_dmg = attacker.damage
#          * if target dies (hp <= dmg):
#              attacker takes the square.
#          * if target survives:
#              target.hp -= dmg; pushed one square toward its OWN home rank;
#              chain victims behind shift the same direction; off-board =
#              killed; attacker stays on its origin square (§10).
#          * on-hit status effect applies if target survives the hit
#            (NOT applied by ability damage — §7.1/§7.2).
#   3. Castling: also slide the rook.
#   4. Castling-rights bookkeeping: any king move kills both rights;
#      a rook leaving its home OR being captured ON its home kills the
#      relevant right.
#   5. EP target: set ONLY for a 2-square pawn push, otherwise cleared.
#   6. Halfmove clock: reset on pawn move OR any capture/damage.
#   7. Fullmove number: bump after Black's move.
#   8. Flip side-to-move.
#   9. TURN-START TICK on the new side (IMPL-GODOT §17 — order is critical):
#      (a) resolve any pending cannons triggering this turn.
#      (b) tick burns/freezes on new side's pieces (burn first; a piece may
#          die and won't keep its freeze around).
#      (c) tick ability recharge on new side's pieces (last; a freshly
#          earned charge is usable this turn).
#  10. Reset special_used_this_turn so the new side may use ONE ability.
# =============================================================================

static func apply_move(state: GameState, m: Dictionary) -> Dictionary:
	var next := state.clone_state()
	var events: Array = []

	var from_sq: int = int(m["from"])
	var to_sq:   int = int(m["to"])
	var piece: Piece = next.board[from_sq]
	if piece == null:
		push_error("apply_move: empty square at from=%d" % from_sq)
		return { "state": next, "events": events, "mute": true }
	var def: PieceDef = state.config.pieces[piece.def_id]

	var captured = next.board[to_sq]
	var damage_dealt := false
	var attacker_moves := true   ## if target survives, attacker stays put

	if m.get("enpassant", false):
		## En passant: captured pawn sits BEHIND destination.
		var cap_sq := to_sq + (-8 if piece.color == WHITE else 8)
		captured = next.board[cap_sq]
		if captured != null:
			var dmg := def.damage
			if captured.hp <= dmg:
				next.board[cap_sq] = null
				events.append({ "kind": "kill", "sq": cap_sq })
			else:
				captured.hp -= dmg
				_apply_push_chain(next, cap_sq,
								  -8 if captured.color == WHITE else 8, events)
			damage_dealt = true
			_maybe_apply_on_hit_effect(next, to_sq, captured, def)
		next.board[to_sq] = piece
		next.board[from_sq] = null
		events.append({ "kind": "move", "from": from_sq, "to": to_sq })

	elif captured != null:
		var dmg := def.damage
		if captured.hp <= dmg:
			## Target dies → attacker takes the square.
			events.append({ "kind": "kill", "sq": to_sq })
			next.board[to_sq] = piece
			next.board[from_sq] = null
			events.append({ "kind": "move", "from": from_sq, "to": to_sq })
		else:
			## Target survives → damage + push toward target's home rank.
			## Chain victims take NO damage (§10.4) — they only relocate.
			captured.hp -= dmg
			events.append({ "kind": "damage", "sq": to_sq, "hp": captured.hp })
			_maybe_apply_on_hit_effect(next, to_sq, captured, def)
			var push_dir := -8 if captured.color == WHITE else 8
			_apply_push_chain(next, to_sq, push_dir, events)
			attacker_moves = false
		damage_dealt = true

	else:
		## No target — just relocate.
		next.board[to_sq] = piece
		next.board[from_sq] = null
		events.append({ "kind": "move", "from": from_sq, "to": to_sq })

	## Promotion: replace def_id and reset def-derived stats.
	if m.has("promo") and String(m["promo"]) != "":
		var promo_id := String(m["promo"])
		var promo_piece: Piece = next.board[to_sq]
		var promo_def: PieceDef = state.config.pieces[promo_id]
		promo_piece.def_id = promo_id
		promo_piece.hp = promo_def.hp
		if promo_def.special != null and promo_def.special.kind != SpecialAbilityDef.Kind.NONE:
			promo_piece.special_charges = promo_def.special.initial_charges
			promo_piece.special_recharge = promo_def.special.cooldown_turns
		else:
			promo_piece.special_charges = 0
			promo_piece.special_recharge = 0
		events.append({ "kind": "promote", "sq": to_sq, "id": promo_id })

	piece.has_moved = true

	## Castling: slide the rook.
	var castle: int = int(m.get("castle", 0))
	if castle == 1:
		var hr := 0 if piece.color == WHITE else 7
		var rf := sq_of(7, hr)
		var rt := sq_of(5, hr)
		next.board[rt] = next.board[rf]
		next.board[rf] = null
		if next.board[rt] != null: next.board[rt].has_moved = true
		events.append({ "kind": "move", "from": rf, "to": rt })
	elif castle == -1:
		var hr := 0 if piece.color == WHITE else 7
		var rf := sq_of(0, hr)
		var rt := sq_of(3, hr)
		next.board[rt] = next.board[rf]
		next.board[rf] = null
		if next.board[rt] != null: next.board[rt].has_moved = true
		events.append({ "kind": "move", "from": rf, "to": rt })

	## EP target (set only for double push).
	next.ep = ((from_sq + to_sq) >> 1) if m.get("double", false) else -1

	## Halfmove clock: reset on pawn move OR any capture/damage. Pawn-move
	## detected via the original def's patterns (before promotion).
	var moved_def: PieceDef = state.config.pieces[piece.def_id]
	var is_pawn_move := false
	for pat in moved_def.move_patterns:
		if pat.kind == MovePattern.Kind.PAWN_PUSH \
		   or pat.kind == MovePattern.Kind.PAWN_DOUBLE \
		   or pat.kind == MovePattern.Kind.PAWN_CAPTURE:
			is_pawn_move = true
			break
	next.halfmove = 0 if (is_pawn_move or damage_dealt) else state.halfmove + 1

	## Fullmove bumps after Black's move.
	next.fullmove = state.fullmove + (1 if state.side == BLACK else 0)

	## Flip side.
	next.side = opposite(state.side)

	## TURN-START TICK on new side. Order: cannons → effects → recharge.
	_resolve_pending_cannons(next, events)
	_tick_status_effects(next, events)
	_tick_ability_recharge(next)

	next.special_used_this_turn = false

	return { "state": next, "events": events, "mute": not attacker_moves }

# ---------------------------------------------------------------------------
# Push-chain (§10.4). Piece at start_sq shifts by `dir` (square-index delta:
# ±8 for vertical home-ward push; routine is general so future variants like
# ability knockback can reuse it).
# ---------------------------------------------------------------------------

static func _apply_push_chain(state: GameState, start_sq: int, dir: int,
							  events: Array) -> bool:
	## Build the chain.
	var chain: Array[int] = [start_sq]
	var cur := start_sq
	while true:
		var nxt := cur + dir
		if not _square_reachable(cur, nxt, dir): break
		if state.board[nxt] == null: break
		chain.append(nxt)
		cur = nxt

	var tail := cur + dir
	if not _square_reachable(cur, tail, dir):
		## Chain hits the wall: last piece is pushed off-board → killed.
		events.append({ "kind": "kill", "sq": chain[chain.size() - 1] })
		state.board[chain[chain.size() - 1]] = null
		var i := chain.size() - 2
		while i >= 0:
			var src := chain[i]
			var dst := chain[i] + dir
			state.board[dst] = state.board[src]
			state.board[src] = null
			events.append({ "kind": "push", "from": src, "to": dst })
			i -= 1
		return true
	else:
		## Tail is in-bounds AND empty (loop broke on null). Shift everyone.
		var i := chain.size() - 1
		while i >= 0:
			var src := chain[i]
			var dst := chain[i] + dir
			state.board[dst] = state.board[src]
			state.board[src] = null
			events.append({ "kind": "push", "from": src, "to": dst })
			i -= 1
		return true

static func _square_reachable(a: int, b: int, dir: int) -> bool:
	if b < 0 or b >= 64: return false
	if dir == 8 or dir == -8:
		return file_of(a) == file_of(b)
	if dir == 1 or dir == -1:
		return rank_of(a) == rank_of(b) and absi(file_of(a) - file_of(b)) == 1
	if absi(dir) == 7 or absi(dir) == 9:
		return absi(file_of(a) - file_of(b)) == 1 and absi(rank_of(a) - rank_of(b)) == 1
	return false

static func _maybe_apply_on_hit_effect(state: GameState, victim_sq: int,
									   victim: Piece, attacker_def: PieceDef) -> void:
	var eff := attacker_def.on_hit
	if eff == null or eff.kind == StatusEffectDef.Kind.NONE: return
	## Single instance per (kind, victim) — latest application overwrites
	## duration; damage doesn't stack (§6.1).
	for e in victim.active_effects:
		if e.kind == eff.kind:
			e.turns_remaining = eff.duration
			e.damage_per_turn = eff.damage_per_turn
			return
	var ne := ActiveEffect.new()
	ne.kind = eff.kind
	ne.damage_per_turn = eff.damage_per_turn
	ne.turns_remaining = eff.duration
	victim.active_effects.append(ne)

# =============================================================================
# TURN-START TICKS — run on side-to-move at start of their turn.
# Order: pending cannons → burn → freeze decrement → ability recharge.
# (See IMPL-GODOT §17 "charge tick ordering" for why each step is in this
# order.)
# =============================================================================

static func _resolve_pending_cannons(state: GameState, events: Array) -> void:
	var still_pending: Array[PendingAttack] = []
	for pa: PendingAttack in state.pending_attacks:
		var triggers_now: bool = \
			pa.kind == SpecialAbilityDef.Kind.CANNON \
			and pa.owner_color == state.side \
			and pa.triggers_on_fullmove == state.fullmove
		if not triggers_now:
			still_pending.append(pa)
			continue
		## Apply damage to every piece on a target square. Special-ability
		## damage: no push-back, no on-hit effect (§7.1). Friendly fire
		## allowed — owner shouldn't aim at allies if they don't want to
		## hit them.
		for sq in pa.target_squares:
			var v = state.board[sq]
			if v == null: continue
			if v.hp <= pa.damage:
				events.append({ "kind": "kill", "sq": sq, "by": "cannon" })
				state.board[sq] = null
			else:
				v.hp -= pa.damage
				events.append({ "kind": "damage", "sq": sq, "hp": v.hp,
								"by": "cannon" })
		events.append({ "kind": "cannonResolved",
						"target": pa.target_squares.duplicate() })
	state.pending_attacks = still_pending

static func _tick_status_effects(state: GameState, events: Array) -> void:
	for i in 64:
		var p = state.board[i]
		if p == null or p.color != state.side: continue
		var died := false
		for e in p.active_effects:
			if e.kind == StatusEffectDef.Kind.BURN and e.turns_remaining > 0:
				if p.hp <= e.damage_per_turn:
					events.append({ "kind": "kill", "sq": i, "by": "burn" })
					state.board[i] = null
					died = true
					break
				else:
					p.hp -= e.damage_per_turn
					events.append({ "kind": "damage", "sq": i, "hp": p.hp,
									"by": "burn" })
		if died: continue
		## Decrement counters AFTER damage applies (so duration=2 ticks twice).
		for e in p.active_effects:
			if e.turns_remaining > 0:
				e.turns_remaining -= 1
		var keep: Array[ActiveEffect] = []
		for e in p.active_effects:
			if e.turns_remaining > 0:
				keep.append(e)
		p.active_effects = keep

static func _tick_ability_recharge(state: GameState) -> void:
	for i in 64:
		var p = state.board[i]
		if p == null or p.color != state.side: continue
		var def: PieceDef = state.config.pieces[p.def_id]
		if def.special == null or def.special.kind == SpecialAbilityDef.Kind.NONE:
			continue
		if p.special_recharge > 0: p.special_recharge -= 1
		if p.special_recharge == 0 and p.special_charges < def.special.max_charges:
			p.special_charges += 1
			p.special_recharge = def.special.cooldown_turns

# =============================================================================
# legal_moves — HP-aware self-check filter.
# -----------------------------------------------------------------------------
# > Move legal iff after playing it, opponent cannot reduce my royal's HP
# > to zero on their next turn.
# Subsumes pins, blocks, king escapes, and HP-budget survival in one rule.
# =============================================================================

static func legal_moves(state: GameState) -> Array:
	var me := state.side
	var out := pseudo_legal_moves(state, me)
	## Castling: per-color royals with can_castle.
	for i in 64:
		var p = state.board[i]
		if p == null or p.color != me: continue
		if is_frozen(p): continue
		var def: PieceDef = state.config.pieces[p.def_id]
		if def.royal and def.can_castle:
			_add_castling_moves(state, me, i, out)

	var filtered: Array = []
	for m in out:
		if _move_survivable(state, m): filtered.append(m)
	return filtered

static func _move_survivable(state: GameState, m: Dictionary) -> bool:
	var me := state.side
	var r := apply_move(state, m)
	var next: GameState = r["state"]
	var my_royal := find_royal(next, me)
	if my_royal < 0: return false
	var royal: Piece = next.board[my_royal]
	if royal == null: return false
	var threat := next_turn_damage_budget(next, my_royal, opposite(me))
	return royal.hp > threat

# next-turn damage budget on royal_sq from by_color (the side whose threat
# we're estimating).
#
#   (A) Pre-move state passed to game_status — state.side != by_color.
#       Threat = move-attack max + opponent's pending cannons that fire on
#       opponent's next turn-start (= state.fullmove + 1).
#
#   (B) Post-move state passed to _move_survivable — state.side == by_color.
#       Their turn-start tick already ran inside apply_move, so any cannon
#       scheduled for THIS turn-start is gone from the queue. Remaining
#       cannons fire on by_color's next-NEXT turn — too far in the future
#       for the immediate-next-move budget; omit them.
static func next_turn_damage_budget(state: GameState, royal_sq: int,
									by_color: int) -> int:
	var dmg := max_incoming_damage(state, royal_sq, by_color)
	if state.side != by_color:
		var next_fullmove := state.fullmove + 1
		for pa in state.pending_attacks:
			if pa.owner_color != by_color: continue
			if pa.kind != SpecialAbilityDef.Kind.CANNON: continue
			if pa.triggers_on_fullmove != next_fullmove: continue
			if pa.target_squares.has(royal_sq):
				dmg += pa.damage
	return dmg

# =============================================================================
# game_status — once per turn, after apply_move, before rendering.
# -----------------------------------------------------------------------------
#   in_check  = side-to-move's royal HP <= next-turn damage budget
#   no_moves  = legal_moves(state).size() == 0
#
#   in_check  && no_moves → checkmate (winner = opposite side)
#   !in_check && no_moves → stalemate
#   in_check               → "in check"
#   halfmove >= 100        → 50-move draw
# =============================================================================

static func game_status(state: GameState) -> Dictionary:
	var me := state.side
	var royal_sq := find_royal(state, me)
	if royal_sq < 0:
		return {
			"kind": "checkmate", "winner": opposite(me),
			"in_check": true, "moves": [], "royal_sq": -1,
		}
	var royal: Piece = state.board[royal_sq]
	var threat := next_turn_damage_budget(state, royal_sq, opposite(me))
	var in_check := royal.hp <= threat
	var moves := legal_moves(state)
	if moves.is_empty():
		if in_check:
			return { "kind": "checkmate", "winner": opposite(me),
					 "in_check": in_check, "moves": moves, "royal_sq": royal_sq }
		return { "kind": "stalemate",
				 "in_check": in_check, "moves": moves, "royal_sq": royal_sq }
	if state.halfmove >= 100:
		return { "kind": "draw50",
				 "in_check": in_check, "moves": moves, "royal_sq": royal_sq }
	return { "kind": "check" if in_check else "normal",
			 "in_check": in_check, "moves": moves, "royal_sq": royal_sq }

# =============================================================================
# ABILITIES — Cannon (queued AOE) and Lightning (instant single-target).
# -----------------------------------------------------------------------------
# Abilities are fired SEPARATELY from the regular move (UI orchestrates both
# within a single turn). Each ability use:
#   - source must belong to side-to-move and not be frozen.
#   - special_used_this_turn must be false.
#   - source.special_charges > 0.
#   - target must be valid for the ability kind.
# Ability use does NOT flip side or tick. It mutates and sets
# special_used_this_turn = true.
# =============================================================================

static func list_ability_targets(state: GameState, source_sq: int) -> Array:
	var p = state.board[source_sq]
	if p == null or p.color != state.side: return []
	var def: PieceDef = state.config.pieces[p.def_id]
	if def.special == null or def.special.kind == SpecialAbilityDef.Kind.NONE: return []
	if state.special_used_this_turn: return []
	if p.special_charges <= 0: return []
	if is_frozen(p): return []

	var out: Array = []
	if def.special.kind == SpecialAbilityDef.Kind.CANNON:
		var enemy := opposite(p.color)
		var forbidden: Dictionary = state.initial_squares_by_color[enemy]
		for target in 64:
			var plus := cannon_plus_squares(target)
			if plus.is_empty(): continue
			var ok := true
			for s in plus:
				if forbidden.has(s):
					ok = false
					break
			if ok:
				out.append({ "sq": target, "plus": plus })
	elif def.special.kind == SpecialAbilityDef.Kind.LIGHTNING:
		for target in 64:
			var t = state.board[target]
			if t == null or t.color == p.color: continue
			var tdef: PieceDef = state.config.pieces[t.def_id]
			if tdef.royal: continue
			out.append({ "sq": target })
	return out

static func cannon_plus_squares(center_sq: int) -> Array[int]:
	var out: Array[int] = []
	var f := file_of(center_sq)
	var r := rank_of(center_sq)
	for off in CANNON_PLUS_OFFSETS:
		var nf := f + off.x
		var nr := r + off.y
		if not in_bounds(nf, nr):
			## Entire plus must fit on the board — bail with an empty list.
			var empty: Array[int] = []
			return empty
		out.append(sq_of(nf, nr))
	return out

static func validate_ability(state: GameState, action: Dictionary) -> String:
	if state.special_used_this_turn: return "already used ability this turn"
	var src_sq: int = int(action["source_sq"])
	var src = state.board[src_sq]
	if src == null or src.color != state.side: return "source not your piece"
	if is_frozen(src):                        return "source is frozen"
	var def: PieceDef = state.config.pieces[src.def_id]
	if def.special == null:                   return "no ability"
	var kind: int = int(action["kind"])
	if def.special.kind != kind:              return "wrong ability"
	if src.special_charges <= 0:              return "no charges"

	var target_sq: int = int(action["target_sq"])
	if kind == SpecialAbilityDef.Kind.CANNON:
		var plus := cannon_plus_squares(target_sq)
		if plus.is_empty():                   return "plus area off-board"
		var enemy := opposite(src.color)
		var forbidden: Dictionary = state.initial_squares_by_color[enemy]
		for s in plus:
			if forbidden.has(s):
				return "plus area overlaps enemy starting zone"
	elif kind == SpecialAbilityDef.Kind.LIGHTNING:
		var t = state.board[target_sq]
		if t == null:                         return "target empty"
		if t.color == src.color:              return "cannot target friendly"
		var tdef: PieceDef = state.config.pieces[t.def_id]
		if tdef.royal:                        return "cannot target royal piece"
	else:
		return "unknown ability"
	return ""   ## valid

static func apply_ability(state: GameState, action: Dictionary) -> Dictionary:
	var err := validate_ability(state, action)
	if err != "":
		push_error("apply_ability: %s" % err)
		return { "state": state, "events": [] }

	var next := state.clone_state()
	var events: Array = []
	var src_sq: int = int(action["source_sq"])
	var target_sq: int = int(action["target_sq"])
	var src: Piece = next.board[src_sq]
	var def: PieceDef = state.config.pieces[src.def_id]
	src.special_charges -= 1
	src.special_recharge = def.special.cooldown_turns

	var kind: int = int(action["kind"])
	if kind == SpecialAbilityDef.Kind.CANNON:
		## Queue the attack — does not damage anything immediately.
		var pa := PendingAttack.new()
		pa.kind = SpecialAbilityDef.Kind.CANNON
		pa.owner_color = src.color
		pa.damage = def.special.damage
		pa.target_squares = cannon_plus_squares(target_sq)
		pa.triggers_on_fullmove = cannon_trigger_fullmove(state)
		next.pending_attacks.append(pa)
		events.append({ "kind": "cannonQueued",
						"source": src_sq, "target": target_sq })
	elif kind == SpecialAbilityDef.Kind.LIGHTNING:
		## Instant. No push-back, no on-hit effect (§7.2).
		var v: Piece = next.board[target_sq]
		if v.hp <= def.special.damage:
			events.append({ "kind": "kill", "sq": target_sq, "by": "lightning" })
			next.board[target_sq] = null
		else:
			v.hp -= def.special.damage
			events.append({ "kind": "damage", "sq": target_sq, "hp": v.hp,
							"by": "lightning" })
		events.append({ "kind": "lightning",
						"source": src_sq, "target": target_sq })

	next.special_used_this_turn = true
	return { "state": next, "events": events }

# Cannon fires on owner's turn N, lands at the start of owner's turn N+1.
# Each color's fullmove value increments by 1 between consecutive turns of
# theirs — so in BOTH cases, owner's NEXT turn is at state.fullmove + 1.
static func cannon_trigger_fullmove(state: GameState) -> int:
	return state.fullmove + 1
