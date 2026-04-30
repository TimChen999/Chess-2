## Live piece on the board. References its def by id (so config edits
## propagate); carries mutable runtime state (HP, charges, effects).
class_name Piece
extends RefCounted

var def_id: String = ""
var color: int = 0                 ## 0 = white, 1 = black
var hp: int = 1
var active_effects: Array[ActiveEffect] = []
var special_charges: int = 0
var special_recharge: int = 0
var has_moved: bool = false        ## for pawn double-push and castling rights

func clone() -> Piece:
    var c = Piece.new()
    c.def_id = def_id
    c.color = color
    c.hp = hp
    c.special_charges = special_charges
    c.special_recharge = special_recharge
    c.has_moved = has_moved
    for e in active_effects:
        c.active_effects.append(e.clone())
    return c
