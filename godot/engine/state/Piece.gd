## Live piece on the board. References its def by id (so config edits
## propagate); carries mutable runtime state (HP, status effects).
##
## (As of the global-abilities refactor, pieces no longer carry per-piece
## ability charges. Charges live on GameState.cannon_state /
## .lightning_state — owned by the player, not the piece.)
class_name Piece
extends RefCounted

var def_id: String = ""
var color: int = 0                 ## 0 = white, 1 = black
var hp: int = 1
var active_effects: Array[ActiveEffect] = []
var has_moved: bool = false        ## for pawn double-push and castling rights

func clone() -> Piece:
	var c := Piece.new()
	c.def_id = def_id
	c.color = color
	c.hp = hp
	c.has_moved = has_moved
	for e in active_effects:
		c.active_effects.append(e.clone())
	return c
