## Definition for an on-hit status effect. Applied to a target that survives
## a regular hit. See IMPL-GODOT §6.
class_name StatusEffectDef
extends Resource

enum Kind { NONE, BURN, FREEZE }

@export var kind: int = Kind.NONE
## BURN only: damage dealt at the start of the affected piece's owner's turn.
@export var damage_per_turn: int = 0
## Number of owner-turn ticks the effect lasts (1 = one tick).
@export var duration: int = 0
