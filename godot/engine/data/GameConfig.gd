## Full game configuration: piece type registry + initial board layout +
## global ability specs.
class_name GameConfig
extends Resource

## piece id (String) -> PieceDef
@export var pieces: Dictionary = {}

## 64-element layout. Each entry is either:
##   - { "id": String, "color": int }    (color: 0 = white, 1 = black)
##   - null
## Index 0 = a1 (white queenside rook in the standard setup).
@export var initial_setup: Array = []

## Global player abilities — both players share these specs but each has
## their own runtime charges/cooldown (see GameState.cannon_state /
## lightning_state). Either field can be null to disable that ability.
@export var cannon: SpecialAbilityDef
@export var lightning: SpecialAbilityDef
