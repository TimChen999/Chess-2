## Per-color, per-ability runtime state. Replaces the per-piece charges/
## recharge tracking that used to live on Piece. Abilities are now a global
## resource owned by the player, not by individual pieces.
class_name AbilityRuntime
extends RefCounted

var charges: int = 0
var recharge: int = 0

func clone() -> AbilityRuntime:
	var c := AbilityRuntime.new()
	c.charges = charges
	c.recharge = recharge
	return c
