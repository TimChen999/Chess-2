## Live status effect attached to a Piece. Mirrors StatusEffectDef but with
## mutable counters.
class_name ActiveEffect
extends RefCounted

var kind: int = StatusEffectDef.Kind.NONE
var damage_per_turn: int = 0
var turns_remaining: int = 0

func clone() -> ActiveEffect:
    var c = ActiveEffect.new()
    c.kind = kind
    c.damage_per_turn = damage_per_turn
    c.turns_remaining = turns_remaining
    return c
