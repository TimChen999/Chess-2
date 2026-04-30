## A queued ability attack (currently only Cannon uses this — Lightning is
## instant). Resolved at the start of the owner's next turn. See IMPL-GODOT
## §7.7.
class_name PendingAttack
extends RefCounted

var kind: int = SpecialAbilityDef.Kind.NONE
var owner_color: int = 0
var damage: int = 0
var target_squares: Array[int] = []
var triggers_on_fullmove: int = 0       ## resolves when state.fullmove matches

func clone() -> PendingAttack:
    var c = PendingAttack.new()
    c.kind = kind
    c.owner_color = owner_color
    c.damage = damage
    c.target_squares = target_squares.duplicate()
    c.triggers_on_fullmove = triggers_on_fullmove
    return c
