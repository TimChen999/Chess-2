## Mutable game state. apply_move / apply_ability return a NEW GameState —
## external callers should treat any state they hold as frozen.
class_name GameState
extends RefCounted

var config: GameConfig
## 64 entries; each is Piece or null. Index 0 = a1.
var board: Array = []
var side: int = 0                       ## 0 = white, 1 = black
var ep: int = -1                        ## en-passant target square; -1 if none
var halfmove: int = 0                   ## 50-move rule counter
var fullmove: int = 1
var pending_attacks: Array[PendingAttack] = []
var special_used_this_turn: bool = false
## Snapshot of starting positions per color, used by Cannon's enemy-zone
## guard. [white_dict, black_dict], each dict: int square -> bool.
var initial_squares_by_color: Array = [{}, {}]

func clone_state() -> GameState:
    var c = GameState.new()
    c.config = config
    c.board.resize(64)
    for i in 64:
        c.board[i] = board[i].clone() if board[i] != null else null
    c.side = side
    c.ep = ep
    c.halfmove = halfmove
    c.fullmove = fullmove
    for pa in pending_attacks:
        c.pending_attacks.append(pa.clone())
    c.special_used_this_turn = special_used_this_turn
    c.initial_squares_by_color = [
        initial_squares_by_color[0].duplicate(),
        initial_squares_by_color[1].duplicate(),
    ]
    return c
