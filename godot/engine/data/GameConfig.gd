## Full game configuration: piece type registry + initial board layout.
## Persisted via ResourceSaver to user://customizations.tres (when available),
## otherwise round-tripped through JSON in user://customizations.json.
class_name GameConfig
extends Resource

## piece id (String) -> PieceDef
@export var pieces: Dictionary = {}

## 64-element layout. Each entry is either:
##   - { "id": String, "color": int }    (color: 0 = white, 1 = black)
##   - null
## Index 0 = a1 (white queenside rook in the standard setup).
@export var initial_setup: Array = []
