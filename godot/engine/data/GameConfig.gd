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

## Which ability is active for this game. Both ability specs above are kept
## around so customization edits don't get lost when the player switches
## the active one, but only the enabled kind appears in the in-game ability
## bar and is accepted by Rules.validate_ability.
##   0 = SpecialAbilityDef.Kind.NONE        (no ability)
##   1 = SpecialAbilityDef.Kind.CANNON
##   2 = SpecialAbilityDef.Kind.LIGHTNING
@export var enabled_ability: int = 2

## Stage / arena. "classic" is the default chessboard with no environmental
## hazards. "moon" enables procedural debris hits (Rules._tick_stage_hazards)
## that land symmetrically on both halves at the end of each turn pair.
##   "classic" | "moon"
@export var stage: String = "classic"

## Probability per pair-end (white turn-start tick) that a fresh debris hit
## is rolled. Telegraph window is 2-3 pairs, sampled per spawn.
@export var debris_spawn_chance: float = 0.55
## Damage dealt by each debris hit to any piece on the targeted square.
@export var debris_damage: int = 1

## Per-slot variant selection (PIECE-VARIANTS.md §3.3). Maps slot id
## (e.g. "pawn") to the chosen variant id (e.g. "pawn", "bandit_pawn").
## Edited by CustomizationScene; projected back into `pieces` /
## `initial_setup` via `rebuild_initial_setup()`.
@export var variant_selection: Dictionary = {
	"pawn":   "pawn",
	"bishop": "bishop",
	"knight": "knight",
	"rook":   "rook",
	"queen":  "queen",
	"king":   "king",
}

## Project the current `variant_selection` back onto `initial_setup` so the
## next new game uses the picked variants. `pieces` is left containing the
## full (regular + alternate) variant catalog so promotion-target lookups
## by string id always succeed even if the player hasn't selected that
## variant in any slot. PIECE-VARIANTS.md §3.4 (option 1).
##
## Idempotent and safe to run on a freshly-loaded config that doesn't yet
## have variant_selection populated — falls back to default selections.
func rebuild_initial_setup() -> void:
	if variant_selection == null or variant_selection.is_empty():
		variant_selection = Defaults.default_variant_selection()
	## Make sure every slot has a value; old saves may not.
	for slot in Defaults.variant_slots():
		if not variant_selection.has(slot):
			variant_selection[slot] = slot

	## Always restock `pieces` with the full catalog so promotion targets
	## resolve. Cheap (~9 entries).
	pieces = Defaults.build_full_pieces_map()

	var rook_id: String   = String(variant_selection["rook"])
	var knight_id: String = String(variant_selection["knight"])
	var bishop_id: String = String(variant_selection["bishop"])
	var queen_id: String  = String(variant_selection["queen"])
	var king_id: String   = String(variant_selection["king"])
	var pawn_id: String   = String(variant_selection["pawn"])

	var back := [rook_id, knight_id, bishop_id, queen_id, king_id, bishop_id, knight_id, rook_id]
	var setup: Array = []
	setup.resize(64)
	for f in 8:
		setup[f]      = { "id": back[f], "color": 0 }
		setup[8 + f]  = { "id": pawn_id, "color": 0 }
		setup[48 + f] = { "id": pawn_id, "color": 1 }
		setup[56 + f] = { "id": back[f], "color": 1 }
	initial_setup = setup
