## Immutable definition of a piece type. The customization screen edits these.
## See IMPL-GODOT §4.1.
class_name PieceDef
extends Resource

@export var id: String = ""
@export var display_name: String = ""
@export var glyph: String = "?"
@export var hp: int = 1
@export var damage: int = 1
@export var royal: bool = false
@export var can_castle: bool = false
@export var move_patterns: Array[MovePattern] = []
@export var on_hit: StatusEffectDef
@export var special: SpecialAbilityDef
@export var promotes_at_rank: int = -1
@export var promotes_to: Array[String] = []
