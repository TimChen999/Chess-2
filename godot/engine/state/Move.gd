## A single move record produced by the move generator and consumed by
## apply_move. Plain data — no behavior. See IMPL-GODOT §4.2.
class_name Move
extends RefCounted

var from_sq: int = -1
var to_sq: int = -1
var capture: bool = false
var promo_id: String = ""           ## "" if not a promotion
var en_passant: bool = false
var double_push: bool = false       ## pawn 2-square push (sets ep target)
var castle: int = 0                 ## 0 none, 1 kingside, -1 queenside
