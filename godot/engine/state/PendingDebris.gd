## Queued debris hit for the Moon stage. Spawned in symmetric pairs (mirror
## across the horizontal midline so White and Black halves are identical),
## telegraphed 2-3 turn-pairs ahead, and resolved at the end of the pair the
## warning expires on (= the start of the next White-turn-start tick at
## triggers_on_fullmove). One damage instance per pair — both halves' debris
## hit the same instant, so neither color gains an asymmetric advantage from
## moving first.
class_name PendingDebris
extends RefCounted

var damage: int = 1
## Symmetric pair of squares. Index 0 is the white-half square (rank 2-3);
## index 1 is its black-half mirror (rank 4-5). target_squares-style array
## (Array[int]) so the resolution loop can stay a flat iteration.
var target_squares: Array[int] = []
## Fullmove number on which this hit lands. Resolution runs inside the
## white-turn-start tick (= end of the pair) when state.fullmove matches.
var triggers_on_fullmove: int = 0

func clone() -> PendingDebris:
    var c := PendingDebris.new()
    c.damage = damage
    c.target_squares = target_squares.duplicate()
    c.triggers_on_fullmove = triggers_on_fullmove
    return c
