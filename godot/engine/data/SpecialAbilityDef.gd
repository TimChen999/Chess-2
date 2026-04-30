## Definition for a per-piece special ability. See IMPL-GODOT §7.
##
## Cannon — delayed plus-shape AOE. Fires at owner's NEXT turn-start.
##          Cannot target squares overlapping the enemy starting zone.
## Lightning — instant single-target damage. Cannot target the royal piece.
class_name SpecialAbilityDef
extends Resource

enum Kind { NONE, CANNON, LIGHTNING }

@export var kind: int = Kind.NONE
@export var damage: int = 1
@export var cooldown_turns: int = 3
@export var max_charges: int = 1
@export var initial_charges: int = 0
