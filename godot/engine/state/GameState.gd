## Mutable game state. apply_move / apply_ability return a NEW GameState —
## external callers should treat any state they hold as frozen.
class_name GameState
extends RefCounted

var config: GameConfig
## 64 entries; each is Piece or null. Index 0 = a1.
var board: Array = []
var side: int = 0                       ## 0 = white, 1 = black
var ep: int = -1                        ## en-passant target square; -1 if none
var halfmove: int = 0                   ## 50-move rule counter
var fullmove: int = 1
var pending_attacks: Array[PendingAttack] = []
## Moon stage hazards. Empty for classic stage. Populated and resolved by
## Rules._tick_stage_hazards (white-turn-start tick). Each entry is a pair
## of mirrored squares scheduled to land on triggers_on_fullmove.
var pending_debris: Array[PendingDebris] = []
## Per-game RNG used by stage hazards. clone_state deep-copies the RNG
## state so simulated apply_move calls (legal-move filter) don't pollute
## the real game's hazard sequence.
var rng: RandomNumberGenerator = null
var special_used_this_turn: bool = false
## Snapshot of starting positions per color, used by Cannon's enemy-zone
## guard. [white_dict, black_dict], each dict: int square -> bool.
var initial_squares_by_color: Array = [{}, {}]
## Per-color ability state. Length 2 — [white_runtime, black_runtime].
## Each element is a plain Dictionary { "charges": int, "recharge": int }.
## (We use a Dictionary instead of a custom class to avoid a Godot 4.6
## class_name resolution quirk that only manifests for newly-added files.)
var cannon_state: Array = []
var lightning_state: Array = []
## Per-color energy ("elixir") pool — Length 2, each clamped 0..ENERGY_MAX.
## Both players start at 0 and gain 1 at the start of each of their turns
## (turn-start tick, after cannons/effects/recharge). Drained by ability
## activation; ability fires only when energy >= spec.energy_cost.
var energy: Array = [0, 0]

func clone_state() -> GameState:
	var c := GameState.new()
	c.config = config
	c.board.resize(64)
	for i in 64:
		c.board[i] = board[i].clone() if board[i] != null else null
	c.side = side
	c.ep = ep
	c.halfmove = halfmove
	c.fullmove = fullmove
	for pa in pending_attacks:
		c.pending_attacks.append(pa.clone())
	for pd in pending_debris:
		c.pending_debris.append(pd.clone())
	if rng != null:
		c.rng = RandomNumberGenerator.new()
		c.rng.seed = rng.seed
		c.rng.state = rng.state
	c.special_used_this_turn = special_used_this_turn
	c.initial_squares_by_color = [
		initial_squares_by_color[0].duplicate(),
		initial_squares_by_color[1].duplicate(),
	]
	for rt in cannon_state:    c.cannon_state.append((rt as Dictionary).duplicate())
	for rt in lightning_state: c.lightning_state.append((rt as Dictionary).duplicate())
	c.energy = energy.duplicate()
	return c
