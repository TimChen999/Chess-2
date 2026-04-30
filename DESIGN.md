# Chess Engine — Design Notes

A reference for the rules-engine design used in `index.html`, plus the
architectural directions for variants (custom movesets, multi-move turns,
richer presentation).

---

## 1. State representation

A position is fully described by:

| Field           | Purpose                                                                        |
| --------------- | ------------------------------------------------------------------------------ |
| `board`         | 8x8 array (length 64); each cell is `null` or `{ type, color }`                |
| `side`          | `'w'` \| `'b'` — whose turn                                                    |
| `castling`      | `{ wK, wQ, bK, bQ }` rights flags                                              |
| `ep`            | square index a pawn could capture into (set for **one ply** after a 2-square push) |
| `halfmove`      | counter for the 50-move rule (resets on pawn move or capture)                  |
| `fullmove`      | full-move number; increments after Black's move                                |

Square indexing convention: `sq = rank * 8 + file`, with rank 0 = White's
back rank.

---

## 2. The two primitives everything rests on

The whole rules layer is built on two functions. Get these right and the
rest is glue.

### 2.1 `isAttacked(board, sq, byColor)`

> "If `byColor` got to move next, could any of their pieces capture `sq`?"

- Walks **outward** from `sq`: rays for sliders, fixed offsets for
  knights / king / pawns
- First piece hit on each ray decides the answer
- Used in three places — see [§5](#5-the-five-check-points)

### 2.2 `pseudoLegalMoves(state, color)`

> Moves that obey piece-movement rules but **ignore** whether they leave
> the mover's own king in check.

- Self-check rejection happens one layer up, in `legalMoves`
- Includes castling candidates (with their special preconditions)
- Includes en-passant captures (only when `state.ep` is set)
- Promotion moves are emitted as four distinct candidates (=Q, =R, =B, =N)

---

## 3. Move legality — the self-check filter

The single rule:

> A move is legal iff, after playing it, your own king is not attacked.

```
legalMoves(state):
  for m in pseudoLegalMoves(state, side):
    next = applyMove(state, m)
    if not isAttacked(next.board, kingSquare(side), opposite(side)):
      keep m
```

This one rule subsumes:

- **Pins** — a pinned piece can't move off the pin line because doing so
  exposes the king
- **Blocking a check** — only moves that interpose or capture the checker
  survive the filter
- **King escapes** — you can't move your king onto an attacked square

No special-case pin or check-evasion code is needed.

**Cost.** ~30 candidates per position, each requiring a board clone and an
`isAttacked` query. Negligible for a UI; only worth optimizing if you build
a search engine on top.

---

## 4. Check / checkmate / stalemate

These are **not separate systems** — they're trivial derivations from two
inputs:

- `inCheck = isAttacked(myKing, opposite)`
- `noMoves = legalMoves(state).length === 0`

| Condition                  | Status        |
| -------------------------- | ------------- |
| `inCheck && noMoves`       | **checkmate** |
| `!inCheck && noMoves`      | **stalemate** |
| `inCheck && !noMoves`      | in check      |
| `!inCheck && !noMoves`     | normal        |
| `halfmove >= 100`          | 50-move draw  |

Run **once per turn**, after applying the previous move; every UI question
becomes a property of the returned object.

---

## 5. The five check points

The order things actually get checked during a turn:

| # | Where                                       | What it does                                                                                                                                         |
| - | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | **`isAttacked`** primitive                  | Square-attack lookup — used by every other check                                                                                                     |
| 2 | **Castling** inside move generation         | Three checks: king not currently in check, transit square not attacked (with king simulated onto it), destination handled by the standard filter    |
| 3 | **`legalMoves`** self-check filter          | Reject any pseudo-legal move that leaves the mover's king attacked                                                                                   |
| 4 | **`gameStatus`** end-of-turn classification | `legalMoves + isAttacked(king)` → check / mate / stalemate                                                                                           |
| 5 | **Input validation** in click handler       | Just a lookup against the precomputed legal-move list — no bespoke logic                                                                             |

### Castling subtlety (check point #2)

The transit-square attack check requires **simulating the king onto the
transit square** before running `isAttacked`, because the king blocks rays
through its own origin. Example: rook on a1, king on e1, transit on f1.
Currently `isAttacked(f1)` returns false (king on e1 blocks the rook's
ray). The moment the king slides to f1, that ray completes — the king is
in check on its transit. Without the simulation, you'd allow an illegal
castle.

---

## 6. The per-turn flow

```
on user click:
  if click is a valid move from selected piece:
    state = applyMove(state, move)            # piece pos, castling, ep, clocks
    lastStatus = gameStatus(state)            # one computation per turn
    if lastStatus.kind in {checkmate, stalemate, draw50}: lock board
    else if lastStatus.kind == check: highlight king
  else:
    treat as piece selection
```

`applyMove` is pure (clones state) and updates **every** piece of derived
state in one place. Forgetting any one breaks subtle rules:

- Move piece (with promotion if requested)
- En passant: remove the pawn behind the destination
- Castling: also slide the rook
- Castling rights: clear on king move, rook leave, rook capture-on-home
- EP target: set only on a 2-square push, otherwise clear
- Halfmove clock: reset on pawn move or capture, else increment
- Fullmove: bump after Black's move
- Flip side-to-move

---

## 7. Architecture / tech stack decisions

### Frontend only is enough for hot-seat play

- Two players sharing a keyboard need no server
- Save/load fits in `localStorage`
- Only reasons to add a backend: online multiplayer, accounts, server-side
  AI opponent, leaderboards

### Godot / Unity is overkill for plain chess

- No physics, no real-time loop, no scene graph, no audio mixing — every
  reason game engines exist is absent
- Worth adopting only if the goal is *polish*: 3D board, animation editor,
  controller support, mobile/Steam release

### Stack progression

| Want                                | Use                                    |
| ----------------------------------- | -------------------------------------- |
| Quick playable game                 | HTML/CSS/JS (current `index.html`)     |
| Desktop binary, no browser chrome   | Wrap with **Tauri** or Electron        |
| Polished web game w/ animations, FX | **PixiJS** (2D WebGL) over engine module |
| Native mobile, Steam, controllers, animation editor | **Godot** |
| Online multiplayer                  | Add a backend (any language); engine code is shared |

The single architectural commitment that unlocks all of this:
**separate the rules engine from the renderer**. The engine module
(`state`, `applyMove`, `legalMoves`, `gameStatus`) is the same code in
every target.

---

## 8. Customizable movesets (variant pieces)

The single biggest architectural change is here, but it's contained: only
the **move generator** and **attack detector** change. The rules layer
above (legalMoves, gameStatus, applyMove) stays identical.

### 8.1 Replace hardcoded branches with data-driven patterns

Standard fairy-chess decomposition (used by ChessV, Fairy-Stockfish):

| Primitive    | Behavior                                                              | Examples                                    |
| ------------ | --------------------------------------------------------------------- | ------------------------------------------- |
| **Leaper**   | Jumps to a relative offset, ignoring intermediate squares             | Knight `(1,2)`, King `(1,0)+(1,1)`          |
| **Rider**    | Slides in a direction until blocked                                   | Rook (orthogonal), Bishop (diagonal)        |
| **Hopper**   | Slides, but must jump exactly one piece on the way                    | Chinese cannon, grasshopper                 |

Each pattern carries modifiers:

- *move-only* (m) / *capture-only* (c) — covers pawn forward-vs-diagonal split
- *initial-only* (i) — covers pawn double-push
- *direction-restricted* — covers pawn forward-only

[**Betza notation**](https://en.wikipedia.org/wiki/Betza%27s_funny_notation)
already encodes all of this. Use it instead of inventing a DSL.

A piece becomes a record:

```
{ name: 'Knight', glyph: '♞', patterns: [Leaper((1,2))], royal: false }
```

The move generator collapses from six hardcoded `if` branches to **one**
~30-line interpreter that walks the pattern list.

### 8.2 Special moves become declarative properties

Currently hardcoded around fixed pieces and ranks. Refactor each as a flag
on the piece spec:

| Special move | Today                            | Variant-friendly form                                              |
| ------------ | -------------------------------- | ------------------------------------------------------------------ |
| Promotion    | Pawn-on-rank-7/0, hardcoded      | `promotesAt: rank, promotesTo: [piece names]`                      |
| Castling     | King + rook, hardcoded squares   | Per-royal-piece linked-move rule (king + partner, rights, transit) |
| En passant   | Pawn double-push, hardcoded      | Tied to any pattern with the *initial-only-double* modifier        |
| Royalty      | "Find the king"                  | `royal: true` flag; check/mate keys off this                       |

### 8.3 `isAttacked` has to be rewritten

Today it walks outward asking "is there a *knight* here, a *rook* on this
ray?" — that hardcodes piece types. The variant-safe version flips the
loop:

> Iterate enemy pieces, generate their pseudo-moves, check if the target
> square is among the destinations.

- Cost: O(pieces × moves-per-piece) per query, vs O(constant) before
- For UI use (tens of queries per turn): unnoticeable
- Optimize only if a search engine sits on top

### 8.4 What stays exactly the same

- The self-check filter (`legalMoves`)
- `gameStatus` (mate/stalemate emerge as before)
- `applyMove` structure
- The UI's click-and-validate flow

This is the architectural payoff of clean layering: variant support is
*entirely* a move-generator concern.

### 8.5 Pre-game configuration

A JSON or YAML file that defines available piece types and starting
position. Loaded into the engine before render. The "customize before
game" UI is then just an editor over that config.

---

## 9. Knockback / piece-pushing effects

A variant where a move displaces enemy (or friendly) pieces without
capturing them. Surprisingly cheap on the runtime side; moderate on the
code side; **specification is the actual hard part**.

### 9.1 Why runtime barely changes

- Branching factor is unchanged — still ~30 *initiating* moves per turn
- `isAttacked` is unchanged
- The self-check filter naturally handles **every** weird interaction
  because it operates on the post-move board state. Discovered checks via
  knockback, blocking via knockback, pin-breaking via knockback — none of
  these need special code; they fall out of "make the full move, check
  king" the same way pins did originally

### 9.2 Where code complexity actually grows

| Layer                | Impact                                                                         |
| -------------------- | ------------------------------------------------------------------------------ |
| `isAttacked`         | None                                                                           |
| `pseudoLegalMoves`   | Small — each move now carries side-effect data (which pieces get pushed where) |
| `applyMove`          | **Moderate** — applies the pushes, handles chains and off-board cases          |
| Self-check filter    | None — works unchanged on whatever post-move board `applyMove` produces        |
| `gameStatus`         | Tiny — possibly add "king pushed off board" termination                        |

Move records grow from `{ from, to }` to `{ from, to, sideEffects: [...] }`.
`applyMove` walks the side-effects list and applies each push.

### 9.3 The specification questions you must answer first

Each is a one-line answer that ripples through `applyMove`. Different
answers give meaningfully different games — playtest before committing.

- **Push direction** — always away from the attacker? Fixed compass
  direction? Chosen by the mover?
- **Chains** — if A pushes B onto C's square, does C also get pushed?
  Propagate indefinitely or stop after one?
- **Collisions when no chain** — does the push fail, the pushed piece die,
  or the moving piece's move fail?
- **Off-board behavior** — pushed off = captured? Push fails? Auto-win
  if it's the king?
- **Friendly fire** — can you knock back your own pieces? (Often
  desirable for tactics like clearing a square for a check.)
- **Pushing the king** — allowed? If the destination is attacked, is the
  king captured (variant ends), is it normal check, or is the push
  illegal?
- **Castling-rights & EP bookkeeping** — if your king/rook gets pushed
  off its home square, do castling rights vanish? (Conventional answer:
  yes — the piece moved.) Does pushing a pawn two squares create an EP
  target? (Probably no — EP is specifically about own-pawn double-push,
  but write the rule down.)

### 9.4 New tactical surface (these emerge for free)

These are not bugs — they're design surface. The self-check filter
produces them naturally, and they're worth knowing about for playtesting:

- **Discovered check by knockback** — push a piece off your queen's /
  rook's / bishop's ray; the line clears; the enemy king is in check
- **Self-defense by knockback** — push your own piece into the path of
  an attacker, blocking a check you couldn't otherwise escape
- **Anti-pin by knockback** — push the pinning piece off its line; your
  previously-pinned piece is now free
- **Knockback as quasi-capture** — if pushed-off-board = dead, you have
  a second way to remove pieces, possibly with different range or
  direction than your normal captures
- **Push-mate** — push the enemy king onto a square your other pieces
  attack. If your variant says "king pushed onto an attacked square =
  checkmate," that's a whole new mating-pattern category

### 9.5 Verdict

| Dimension              | Verdict                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| Runtime complexity     | Effectively unchanged. Same branching factor; `isAttacked` calls per move grow only slightly. |
| Code complexity        | +20-30%, concentrated in `applyMove` and the move-data shape.                                 |
| Specification effort   | High relative to code. Edge cases (chains, off-board, king-push, friendly fire) are the work. |
| New tactical surface   | Large — knockback creates whole new motifs (discovered, anti-pin, push-mate). That's a feature. |

The architectural pattern holds: knockback is a `pseudoLegalMoves` +
`applyMove` change; everything above (`legalMoves`, `gameStatus`, UI,
mate detection) doesn't notice.

---

## 10. Health bars (per-piece HP, attacks-as-damage, push-back)

Pieces have HP. An attack that doesn't kill its target deals 1 damage and
pushes the target one square toward its home rank; any pieces sitting
behind it chain-push the same direction (chain victims take **no damage**,
they just relocate). The attacker stays put when the target survives, and
moves into the vacated square when the target dies (normal capture).

**Locked-in scope assumptions** that make this variant cheap to build:

- One move per turn (multi-move turns rejected — see §11)
- One damage per attack

Together they collapse the check definition to a closed-form predicate.

### 10.1 The closed-form check rule

> **Check = king.hp == 1 AND king square is attacked.**

Because at most 1 HP can be lost per opponent turn, a king with HP > 1
cannot die this turn. Below HP 1, the classical chess rule is recovered.
No lookahead, no search.

### 10.2 King HP creates a tempo structure

| King HP | Status                                                                              |
| ------- | ----------------------------------------------------------------------------------- |
| 3       | Untouchable — attacks land but are never check; player can ignore freely            |
| 2       | Still ignorable — one more free hit before danger                                   |
| 1       | "True king" — any attack is check, must be responded to like classic chess          |

You effectively get two free turns of king tomfoolery before the game
plays like classical chess. Strategy splits cleanly into a high-HP
attrition phase and a low-HP endgame.

### 10.3 What changes in code

| Layer                | Impact                                                                                                                          |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Piece state          | `hp` per instance + `maxHp` per type — small addition                                                                           |
| Piece config         | HP value per piece type (default damage = 1 unless varied)                                                                      |
| `pseudoLegalMoves`   | Unchanged — moves are still "to enemy square"; the *outcome* differs                                                            |
| `applyMove`          | **Significant** — branch on whether the hit kills, apply damage + push-chain if not                                             |
| `isAttacked`         | None — still answers "could a piece reach this square"                                                                          |
| `legalMoves`         | Same shape; predicate becomes `NOT (myKing.hp == 1 AND isAttacked(myKing))`                                                     |
| `gameStatus`         | Same shape; check-detection uses the new predicate                                                                              |

The whole rules-engine delta is two predicate edits + a beefier
`applyMove`. Everything above (`legalMoves` filter shape, mate/stalemate
derivation, UI, click validation) is untouched.

### 10.4 Push semantics

Same shape of questions as the knockback variant in §9, refined to the
specific rules here:

- **Direction.** Toward the *attacked piece's* home rank (white pieces → rank 0, black pieces → rank 7).
- **Damage.** Only the directly-attacked piece. Chain victims take no damage; they only relocate.
- **Chain direction.** Same direction as the originating push (NOT each victim toward its own home — that creates contradictions when colors interleave).
- **Attacker movement.** Stays put if the target survives. Moves into the vacated square if the target dies.
- **Off-board.** Default: pushed off = killed. (A second damage path — interesting design surface.)
- **Friendly fire.** Forbidden — you can't attack your own pieces.
- **King push.** King is pushed like any other piece. If pushed onto an attacked square at HP 1, that's just check; respond next turn. (Optional alt: pushed-king-attacked-at-HP-1 = immediate death. Pick before playtesting.)

### 10.5 Why the closed-form check rule depends on the chosen scope

The "HP 1 AND attacked" rule is exact only because of the locked-in scope.
Either parameter changing breaks it back into search:

| Change                            | Resulting check rule                                                |
| --------------------------------- | ------------------------------------------------------------------- |
| Multi-move turns (N sub-moves)    | Existence search: opponent reduces king to 0 over N moves           |
| Damage per attack > 1             | "King.hp ≤ max-incoming-damage AND attacked by such a piece"        |
| Both                              | Full N-ply existence search (back to the exponential)               |

**Multi-move turns are out of scope** for this design — the closed form
is therefore safe and permanent. If damage values are ever varied per
piece type, the predicate generalizes to "max-incoming-damage ≥
king.hp," still O(1) — see §10.8.

### 10.6 Specification choices that shape the game

- **HP values per type** — uniform (everything = 3) or differentiated (Pawn 1, Knight/Bishop 2, Rook 3, Queen 5, King 3)?
- **Damage per attack** — locked at 1 to preserve the closed-form check rule (recommended)
- **Healing** — default none; adding it makes games drag and complicates termination
- **Stalemate semantics** — still a draw, or a loss for the stalemated side (since they can't avoid eventual king death)?

### 10.7 Verdict

| Dimension              | Verdict                                                                          |
| ---------------------- | -------------------------------------------------------------------------------- |
| Runtime complexity     | Unchanged. Predicate is O(1).                                                    |
| Code complexity        | +30-40% over base. Concentrated in `applyMove`; rest is one-liners.              |
| Specification effort   | Moderate. HP values + push edge cases + stalemate rule are the main calls.       |
| Game-design surface    | Massive — tempo structure, attrition phase, two-step trades, all change feel    |

### 10.8 Variant: variable per-piece damage (e.g. Queen deals 2)

Letting some pieces deal more than 1 damage per attack (Pawn = 1,
Queen = 2, etc.) keeps the closed-form check rule, with one
generalization: the predicate sums against the *strongest* attacker that
can land on king this turn.

#### Generalized check predicate

> **Check = `king.hp ≤ max(p.damage for p in opponent pieces attacking king's square)`**

Equivalently: there exists an enemy piece that can hit king for ≥ king's
current HP. If no enemy attacks king, max incoming damage is 0 and king
is safe regardless of HP.

This stays O(1)-ish per evaluation — you just need a richer attack query
that tracks the max attacker damage instead of returning a boolean:

```
maxIncomingDamage(board, sq, byColor)
  → walks outward from sq exactly like isAttacked
  → tracks the highest .damage among enemy attackers found
  → returns 0 if none
```

Same cost as `isAttacked`, just a number instead of a bool.

#### Tempo table updates

The "free turns of king tomfoolery" depend on the **strongest attacker**
that can reach king, not just whether *any* attacker can:

| King HP | Max attacker dmg = 1   | Max attacker dmg = 2 |
| ------- | ---------------------- | -------------------- |
| 3       | Safe (2 free hits)     | Safe (1 free hit)    |
| 2       | Safe (1 free hit)      | **In check**         |
| 1       | **In check** (any hit) | **In check**         |

A queen-class (2 dmg) piece in attack range of a HP-2 king is check
*immediately* — no tempo grace turn.

#### Code changes on top of base HP

| Layer              | Impact                                                              |
| ------------------ | ------------------------------------------------------------------- |
| Piece config       | Add `damage: number` field per piece type (default 1)               |
| `isAttacked`       | Keep as-is; add sibling `maxIncomingDamage` for the predicate       |
| Check predicate    | `king.hp ≤ maxIncomingDamage(king, opposite)` instead of fixed 1    |
| `applyMove`        | Use attacker's `damage` value when applying hit                     |
| `pseudoLegalMoves` | Unchanged                                                           |
| `gameStatus`       | Same shape, new predicate                                           |

Roughly **+5%** on top of base HP — one new function and a config field.

#### Game-design implications

- **Trades shorten.** Queen-vs-queen takes 2 hits per side instead of 5,
  if both have HP 5 and damage 2.
- **High-damage pieces become focal threats.** Defense reorients around
  keeping the queen (or any 2-dmg piece) out of king's attack range.
- **Mate setups arrive earlier.** A queen near a HP-2 king is already
  check; you can't drift the king down to HP 1 first.
- **Sacrifices gain value.** Trading a 1-dmg piece to remove a 2-dmg
  threat caps incoming damage at 1 again — a clean exchange of tempo
  for survivability.
- **Discovered attacks gain value.** Revealing a queen-on-king ray spikes
  incoming damage from 0 → 2; sometimes immediate check.

#### What still doesn't break

The §11.7 commitment holds: damage is still summed in a *single-turn*
budget. As long as max incoming damage per turn is bounded and
computable from the current board, no lookahead is needed. Per-piece
damage variation is just a richer "current board read."

Where it WOULD break: chain-attacks (one move triggers multiple attacks)
or re-introducing multi-move turns. Either forces summing damage across
multiple actions, and you'd need careful bookkeeping or an actual
search.

---

## 11. Extended actions: instant attacks, delayed attacks, status effects

Stacking action types on top of the move. Each addition stays cheap as
long as the **per-turn damage budget** principle (§11.7) holds.

### 11.1 Instant attack alongside a move (no king target)

Each turn becomes a `(move, attack)` tuple. Branching factor jumps from
~30 → ~300, but max damage to king per opponent turn is still 1 (their
move can hit king for 1; their attack cannot). **Check predicate
unchanged.**

| Layer              | Impact                                                                  |
| ------------------ | ----------------------------------------------------------------------- |
| Turn shape         | Each turn = `(move, attack)`                                            |
| `pseudoLegalMoves` | Add `attackOptions(state, color)` returning legal attack targets        |
| `applyMove`        | Apply move, then attack (each atomic)                                   |
| Check predicate    | **Unchanged.** `king.hp == 1 AND isAttacked(king)`                      |
| Mate detection     | Enumerate ~300 candidate turns instead of ~30. ~15 ms vs 1.5 ms.        |

**Verdict: cheap.** Code +20%. Runtime linear in branching.

### 11.2 Instant attack with knockback

Knockback can chain-push the king (chain victims take no damage but
relocate). If pushed-off-board = death, attacks indirectly kill king.
The check predicate generalizes to:

> Check = (`king.hp == 1 AND isAttacked`) **OR** (any opponent attack
> would chain-push king off-board)

The second condition is an O(opponent attacks) scan per evaluation —
~160 lookups, milliseconds. **Closed form holds, just gets fatter.** If
king is given push-immunity, the predicate stays exactly O(1).

### 11.3 Delayed attack (queued this turn, lands on your next turn)

State grows by a queue:

```
pendingAttacks: [{ source, target, damage, knockback?, statusEffect?, triggersOnTurn }]
```

`applyMove` ticks the queue at turn start, applying any attacks that
trigger now. The target can move out of the way during the intervening
turn — pending damage applies to whoever sits on the target square at
trigger time, often nobody.

If delayed attacks **can** target king, max damage to king per opponent
turn becomes:

```
max_damage = (1 if pending attack lands on king's current square else 0)
           + (1 if opponent's move can hit king)
           + (1 if opponent's attack can push king off-board)
```

The predicate widens to `king.hp ≤ max_damage_next_turn AND any
contributor is feasible`. Still O(pending list + opponent attacks) per
evaluation — bounded, not exponential.

| Layer            | Impact                                                              |
| ---------------- | ------------------------------------------------------------------- |
| State            | `pendingAttacks` list                                               |
| `applyMove`      | Tick queue at turn start, apply effects                             |
| Check predicate  | Wider but still O(small). Sums damage sources.                      |
| Mate detection   | Same shape, slightly heavier per candidate                          |

**Verdict: moderate.** Code +25-30%. Runtime still linear.

### 11.4 Delayed attack: damage-only vs with knockback

Same delta as the instant-attack case: knockback adds a push-off-board
contributor to the check predicate. Cleanest rule to recommend: **king
push-immunity** (kings can be relocated by chains within the board, but
never knocked off). Keeps the predicate purely additive over damage
sources, no special-case "but they could push me off."

### 11.5 Status effect — DOT (damage over time)

Each affected piece carries `{ dotDamage, turnsRemaining, source? }`.
Effects tick at turn start.

The check predicate must include DOT damage on king:

> max_damage_next_turn = `sum(king.dots) + 1 (move) + 1 (attack if applicable)`

Still O(king's active effects) per check — typically 0–2.

**UX gotcha (not complexity):** a king at HP 5 with DOT 2 isn't "in
check" until HP 3, but death is inevitable in 2 turns regardless of
play. `gameStatus` should expose a separate "ticking countdown" signal
so the UI can warn the player without overloading the check concept.

### 11.6 Status effect — freeze

Each piece carries `frozenUntil: turnNumber`. Move generation filters
frozen pieces (one extra `if`). Effect ticks decrement.

| Layer              | Impact                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------- |
| State              | `frozenUntil: turnNumber` per piece                                                         |
| `pseudoLegalMoves` | Skip frozen pieces                                                                          |
| Check predicate    | Unchanged structurally — but a frozen king can't dodge, making existing attacks more lethal |
| `applyMove`        | Tick freeze counters at turn start                                                          |

**Verdict: trivial code.** Frozen king + DOT + attacker is a deadly
combination, and the predicate handles it because it just sums incoming
damage and asks if king can survive.

### 11.7 The principle that keeps it tractable — per-turn damage budgeting

Everything above stays cheap because the check predicate is always:

> `king.hp ≤ (sum of damage opponent can deal over *one* turn) AND that damage can actually land`

It's a sum of bounded contributors, evaluated once. The moment you
change the rule to "king dies within N turns of optimal opponent play,"
every contributor becomes a tree node and you're in alpha-beta land.

**Architectural commitment:** all status effects, queued attacks, and
damage sources contribute to a per-turn damage budget, evaluated against
current king HP. No multi-turn forecasting. Death sometimes happens
"off-screen" without a check warning (e.g. the DOT-on-high-HP case),
and that's fine — the engine doesn't predict, it just enforces
survivability rules turn by turn.

### 11.8 One-turn coupling vs multi-turn search — when knockback on abilities forces extra enumeration

A subtle question about the per-turn damage budget: if an instant
ability has knockback that can move the king, does the engine have to
enumerate "ways opponent could knock pieces around to set up a kill"
during legal-move filtering and mate detection?

**Yes — but only within one opponent turn**, and that distinction is
the line between bounded and exponential.

#### What the engine checks vs doesn't check

When evaluating my king's safety, the engine considers opponent's
coupled (ability, move) pairs on their *single next turn*. That
includes scenarios like: "opp uses lightning to knock my defender out
of the way, then their queen attacks my king through the now-open
line." The engine enumerates the ~300×300 pairs and asks whether any
combination kills my king.

What the engine **does not** check: multi-turn knockback plans like
"opp knocks defender on turn 1, repositions on turn 2, attacks on turn
3." Those require tree search — explicitly out of scope. The player
sees those threats themselves the way humans do in classical chess.

#### Cost breakdown

| Scenario                                                  | Per-evaluation work                     | Mate detection             |
| --------------------------------------------------------- | --------------------------------------- | -------------------------- |
| Without ability knockback affecting king                  | sum of independent maxes — O(branching) | O(branching²) ≈ 90k ops    |
| With ability knockback affecting king (one-turn coupling) | max over coupled pairs — O(branching²)  | O(branching³) ≈ 27M ops    |
| Multi-turn knockback planning                             | tree search — O(branching^N)            | **exponential — excluded** |

The jump from row 1 to row 2 is a constant-factor polynomial increase:
still bounded, but mate detection in interpreted languages goes from
milliseconds to ~1 second.

#### The fix: king push-immunity

If kings cannot be relocated by ability knockback (rule recommended in
§10.4 / IMPLEMENTATION-GODOT §7), the ability and move on opponent's
turn don't couple through king position. They become independent
contributors to the damage budget, and the §11.7 closed-form
sum-of-maxes is preserved. Without that rule, the engine still works
and stays polynomial — just at the higher constant factor.

#### Same family, different magnitude

Both this and multi-move turns are **coupling problems** — actions on a
single turn that can no longer be treated as independent contributors.
The engine has to enumerate combinations either way. The difference is
what gets multiplied.

Multi-move turns (§12) couple two *independent decisions* per ply,
giving polynomial-going-on-exponential branching as N grows. Knockback
on a single ability widens *one* enumeration — a constant-factor jump
in degree, not in depth. It's a one-time tax, not a growth function.

| Variant                            | Coupling                              | Complexity                       |
| ---------------------------------- | ------------------------------------- | -------------------------------- |
| Multi-move turns                   | (m₁, m₂) × (m₁', m₂') — 4-way         | Polynomial → exponential in N    |
| Ability knockback, king-immune     | None                                  | O(branching) per eval (current)  |
| Ability knockback, king-pushable   | (ability, move) coupled via king pos  | O(branching²) per eval, bounded  |

**Asymmetry:** multi-move duplicates a *ply* (search depth grows);
knockback widens *one ply's* enumeration (branching widens once). The
engine has more to check either way — but only one of those scales out
of control.

### 11.9 Summary

| Feature                              | Code add | Runtime impact                              | Check rule                                     |
| ------------------------------------ | -------- | ------------------------------------------- | ---------------------------------------------- |
| Instant attack, no king target       | +20%     | Branching ×10, mate detect ~15 ms           | Unchanged                                      |
| Instant attack with knockback        | +25%     | Same + O(attacks) per check                 | + push-off-board case                          |
| Delayed attack, no king target       | +20%     | Branching same, +pending list scan          | Unchanged (target ≠ king)                      |
| Delayed attack, can target king      | +30%     | Branching same, +pending list scan          | Sum pending damage into next-turn budget       |
| Delayed attack with knockback        | +35%     | + O(pending knockbacks) per check           | + push-off-board cases                         |
| DOT status                           | +15%     | + O(king effects) per check                 | DOT damage added to next-turn budget           |
| Freeze status                        | +10%     | + O(1) filter per move generation           | Unchanged structurally                         |

---

## 12. Multi-move turns: considered and rejected

**Decision: single move per turn.** This section documents what
multi-move turns would have looked like and why they were rejected, so
the decision sticks.

### 12.1 Why it's the wrong choice *in this design*

The HP variant in §10 is only cheap because the closed-form check rule
holds: max damage opponent can deal in one turn ≤ king HP at the boundary.
That holds **only** when there's exactly one move per turn (and 1 damage
per attack). Adding sub-moves immediately breaks the closed form into an
N-ply existence search, dragging mate detection from O(1) into the
exponential branching wall.

So the rejection isn't because multi-move turns are bad in isolation —
they're a fine variant in classical chess. They're rejected here because
**they're incompatible with the simplicity of the HP system we picked**.
You can have multi-move *or* cheap HP-aware mate detection; not both.

### 12.2 What multi-move turns would have required

Mechanical changes (small):

- Turn state grows a "moves remaining this turn" counter
- `applyMove` decrements the counter; only flips `side` when it hits zero
- UI tracks which sub-move you're on
- ~50 lines of wrapper around the existing engine

The decision that drives everything:

> **Are you allowed to be in check between your sub-moves?**

| Rule variant      | Implementation impact                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------ |
| **Strict** — must be safe at every sub-move boundary | Existing self-check filter applies unchanged at each sub-move. Almost no new code in `legalMoves`.       |
| **Lax** (Marseillais-style) — transient check OK; must end safe | Single-move filter no longer rejects "moves that put my king in check," because move 2 might rescue it. Validate **pairs**: enumerate (m1, m2) and keep those whose final position is safe. |

### 12.3 Mate detection becomes a 2-ply enumeration

Mate is no longer "no legal moves" — it's:

> No legal *pair* of moves that ends with my king safe.

You'd write an explicit `hasAnyLegalTurn()` doing the nested search.
Stalemate piggybacks on the same function. The "checkmate falls out for
free" property is gone.

### 12.4 Smaller things that would have bitten

- **En passant** — set the EP target only at end-of-turn, not between sub-moves
- **Halfmove clock / repetition** — tick once per full turn, not per sub-move
- **Castling** — counts as one sub-move, not both (standard answer)
- **Pass / null move** — does the player have to use both sub-moves? If not, add an explicit "pass" move type
- **First-move asymmetry** — Marseillais traditionally gives White only 1 move on turn 1 to balance the opening

### 12.5 Code complexity vs runtime complexity

The dangerous gap: **the code looks the same shape but the runtime balloons.**
A nested loop or short recursion *reads* fine, but the work it does is
`branching ^ depth`.

Ballpark, ~30 moves/position generated at ~50µs each in JS:

| Sub-moves per turn | Worst-case sequences | Wall time           |
| ------------------ | -------------------- | ------------------- |
| 1                  | ~30                  | ~1.5 ms             |
| 2                  | ~900                 | ~50 ms (fine)       |
| 3                  | ~27,000              | ~1.5 s (laggy)      |
| 4                  | ~810,000             | ~40 s (broken)      |
| 5                  | ~24,300,000          | minutes             |

Practical reality is much better than worst case because **mate detection
is an existence question** — stop the moment you find one escape. With
sensible move ordering (king moves first if in check, then captures of
the checker, then blocks), trees prune aggressively. But the worst-case
ceiling rises exponentially, and combined with the HP variant's "did the
opponent reduce my king to 0?" check, the search depth doubles in
effect.

### 12.6 Build cost if reversed

| N (sub-moves) | Build it as                                                |
| ------------- | ---------------------------------------------------------- |
| 2             | Free — exhaustive enumeration is fine                      |
| 3             | On the edge — needs early termination + move ordering      |
| ≥ 4           | Requires a real search (alpha-beta, transposition tables)  |

Same wall every chess engine hits. Pruning techniques don't change the
worst-case complexity; they just slash the constant factor by orders of
magnitude.

### 12.7 Verdict

Multi-move turns add tactical depth but cost the closed-form check rule,
the O(1) mate predicate, and ultimately push the engine toward a real
search loop. **Single-move turns chosen** to keep the entire stack
predicate-based and exhaustively-decidable in milliseconds. If this is
ever revisited, build the mate-detector behind an interface that can
swap from "predicate" to "alpha-beta search" without touching the rules
layer.

---

## 13. Layering recap

```
          ┌────────────────────────────┐
          │ UI / renderer (HTML, Pixi, │
          │ Godot — interchangeable)   │
          └────────────┬───────────────┘
                       │
          ┌────────────▼───────────────┐
          │ gameStatus                 │  mate / stalemate / check
          └────────────┬───────────────┘  (HP-aware predicate, O(1))
                       │
          ┌────────────▼───────────────┐
          │ legalMoves (self-check)    │  the one filter that handles pins,
          └────────────┬───────────────┘  blocks, king escapes uniformly
                       │
          ┌────────────▼───────────────┐
          │ pseudoLegalMoves           │  data-driven over piece patterns
          └────────────┬───────────────┘  for variant support
                       │
          ┌────────────▼───────────────┐
          │ applyMove (+ side effects) │  damage, push-chain, castling,
          └────────────┬───────────────┘  EP, promotion all live here
                       │
          ┌────────────▼───────────────┐
          │ isAttacked + board state   │  raw square-attack lookup;
          └────────────────────────────┘  the engine's only primitive
```

No turn-manager layer — single move per turn means each `applyMove`
flips `side` directly. Everything above runs once per turn; everything
below is invoked per move-candidate.

Every higher layer should depend only on the layer immediately below it.
Variant support, custom moves, multi-move turns, richer renderers — each
slots in at its own layer without rippling through the rest.
