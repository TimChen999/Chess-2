## A single movement primitive. Pieces compose one or more patterns to define
## their full move set. See DESIGN.md §8.1 / IMPL-GODOT §5.1.
class_name MovePattern
extends Resource

enum Kind {
    LEAPER,         ## Jumps to fixed offsets, ignoring blockers in between.
    RIDER,          ## Slides along a direction until blocked.
    PAWN_PUSH,      ## Single step forward; empty target only.
    PAWN_DOUBLE,    ## Initial double-step; both squares empty; once per piece.
    PAWN_CAPTURE,   ## Diagonal forward; enemy or en-passant target only.
}

@export var kind: int = Kind.LEAPER
## Leapers: list of target offsets (Vector2i(file, rank)).
## Riders: list of direction vectors.
@export var offsets: Array[Vector2i] = []
## Riders only. 0 = unlimited; 1..7 caps the slide range.
@export var max_range: int = 0
## If true, this pattern only contributes capture moves.
@export var capture_only: bool = false
## If true, this pattern only contributes non-capture moves.
@export var move_only: bool = false
