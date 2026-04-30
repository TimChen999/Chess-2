"use strict";
// ============================================================================
// engine.js — pure rules engine for Chess² (HP variant + special abilities)
// ============================================================================
// This file is the actual game logic. Everything else (config defaults, UI,
// customization editor, persistence) is glue around it.
//
// Theory:  DESIGN.md   §1–§13
// Plan:    IMPLEMENTATION-GODOT.md  §1–§19   (ported from GDScript to JS)
//
// Layering (DESIGN.md §13). Every higher layer depends only on the layer
// directly below it:
//
//   gameStatus()         ← once per turn — { kind, inCheck, moves }
//        │
//   legalMoves()         ← HP-aware self-check filter (§8.2 of IMPL doc)
//        │
//   pseudoLegalMoves()   ← data-driven over MovePattern records (§5)
//        │
//   applyMove()          ← HP, push-chain, status effects, ability fire,
//        │                  side flip, turn-start tick
//        │
//   isAttacked() /       ← per-square attack primitives
//   maxIncomingDamage()
//
// State is immutable from the engine's POV. Every mutator returns a NEW state
// object — no in-place edits. The self-check filter relies on this to "play
// the move on a clone, then ask isAttacked". Cloning ~30 candidates per turn
// is microseconds in JS, well within budget for an interactive UI.
// ============================================================================

(function (root) {

// ---------------------------------------------------------------------------
// CONSTANTS / HELPERS
// ---------------------------------------------------------------------------
// Square indexing: sq = rank*8 + file. Rank 0 = white's back rank, rank 7 =
// black's. The renderer flips this so white sits at the bottom on screen.

const WHITE = 0, BLACK = 1;
const opposite = c => c === WHITE ? BLACK : WHITE;
const fileOf = sq => sq & 7;
const rankOf = sq => sq >> 3;
const sqOf   = (f, r) => r * 8 + f;
const inBounds = (f, r) => f >= 0 && f < 8 && r >= 0 && r < 8;

// MovePattern.kind tags. See §5.1 of the implementation plan.
const KIND_LEAPER       = 'LEAPER';        // jumps a fixed offset
const KIND_RIDER        = 'RIDER';         // slides along a direction
const KIND_PAWN_PUSH    = 'PAWN_PUSH';     // single forward step (empty only)
const KIND_PAWN_DOUBLE  = 'PAWN_DOUBLE';   // initial double step (empty only)
const KIND_PAWN_CAPTURE = 'PAWN_CAPTURE';  // diagonal forward (capture or EP)

// Special-ability tags.
const ABILITY_NONE      = 0;
const ABILITY_CANNON    = 1;   // delayed plus-shape AOE (§7.1)
const ABILITY_LIGHTNING = 2;   // instant single target, can't hit royals (§7.2)

// Status-effect tags.
const EFFECT_NONE   = 0;
const EFFECT_BURN   = 1;       // DOT — ticks at start of victim's owner turn
const EFFECT_FREEZE = 2;       // movement skipped while active

// Plus-shape AOE pattern for cannon (§7.1). Centered on target square.
const CANNON_PLUS_OFFSETS = [[0,0],[1,0],[-1,0],[0,1],[0,-1]];

// ---------------------------------------------------------------------------
// PIECE FACTORY
// ---------------------------------------------------------------------------
// A live piece carries (a) a reference to its immutable definition (so config
// edits propagate) and (b) mutable runtime state (HP, charges, effects).

function makePiece(defId, color, def) {
  return {
    defId, color,
    hp:               def.hp,
    activeEffects:    [],   // [{kind, damagePerTurn, turnsRemaining}]
    specialCharges:   def.special ? (def.special.initialCharges | 0) : 0,
    specialRecharge:  def.special ? (def.special.cooldownTurns  | 0) : 0,
    hasMoved:         false,  // for pawn double-push and castling
  };
}

// Deep-clone a piece. Lists must be copied so mutation in one state doesn't
// leak into the predecessor.
function clonePiece(p) {
  if (!p) return null;
  return {
    defId:           p.defId,
    color:           p.color,
    hp:              p.hp,
    activeEffects:   p.activeEffects.map(e => ({ ...e })),
    specialCharges:  p.specialCharges,
    specialRecharge: p.specialRecharge,
    hasMoved:        p.hasMoved,
  };
}

// Clone the whole state.  applyMove() does this once at the top, then mutates
// the clone freely. External callers are expected to treat states as frozen.
function cloneState(state) {
  return {
    config:               state.config,
    board:                state.board.map(clonePiece),
    side:                 state.side,
    ep:                   state.ep,
    halfmove:             state.halfmove,
    fullmove:             state.fullmove,
    pendingAttacks:       state.pendingAttacks.map(pa => ({
                            ...pa,
                            targetSquares: pa.targetSquares.slice(),
                          })),
    specialUsedThisTurn:  state.specialUsedThisTurn,
    initialPiecesByColor: state.initialPiecesByColor,
  };
}

// ---------------------------------------------------------------------------
// STATE CONSTRUCTION
// ---------------------------------------------------------------------------

function newGame(config) {
  const board = new Array(64).fill(null);
  for (let i = 0; i < 64 && i < config.initialSetup.length; i++) {
    const cell = config.initialSetup[i];   // { id, color } | null
    if (cell) {
      const def = config.pieces[cell.id];
      if (!def) throw new Error('newGame: missing piece def "' + cell.id + '"');
      board[i] = makePiece(cell.id, cell.color, def);
    }
  }

  // Snapshot which squares each color OCCUPIES at game start. Cannon's
  // forbidden-target rule (§7.1) tests against this set, NOT current
  // positions — pieces may have moved.
  const initialPiecesByColor = { 0: new Set(), 1: new Set() };
  for (let i = 0; i < 64; i++) {
    if (board[i]) initialPiecesByColor[board[i].color].add(i);
  }

  return {
    config,
    board,
    side:                 WHITE,
    ep:                   -1,
    halfmove:             0,
    fullmove:             1,
    pendingAttacks:       [],   // [{ kind, ownerColor, damage,
                                //    targetSquares, triggersOnFullmove }]
    specialUsedThisTurn:  false,
    initialPiecesByColor,
  };
}

function findRoyal(state, color) {
  for (let i = 0; i < 64; i++) {
    const p = state.board[i];
    if (p && p.color === color && state.config.pieces[p.defId].royal) return i;
  }
  return -1;
}

// =============================================================================
// PRIMITIVE — isAttacked / maxIncomingDamage
// -----------------------------------------------------------------------------
// "Could `byColor` capture `sq` if they got to move next?"
//
// Variant-aware version (DESIGN.md §8.3): instead of walking outward asking
// "is there a knight here, a rook on this ray", we iterate enemy pieces and
// generate their pseudo-moves. Cost goes from O(constant) to
// O(pieces × moves-per-piece). For a UI doing tens of queries per turn, that
// is unnoticeable; only worth optimizing if a search engine sits on top.
//
// THIS PRIMITIVE IS THE WHOLE BASIS for: legalMoves' self-check filter,
// gameStatus' check detection, and lightning's "can't target royal" guard.
//
// `maxIncomingDamage` is the same scan but returns the MAX attacker.damage
// instead of a boolean (DESIGN.md §10.8). With variable per-piece damage, the
// check predicate compares king HP against this number, not a fixed 1.
// =============================================================================

function maxIncomingDamage(state, sq, byColor) {
  let best = 0;
  for (let from = 0; from < 64; from++) {
    const p = state.board[from];
    if (!p || p.color !== byColor) continue;
    if (isFrozen(p)) continue;     // a frozen piece can't attack — trivially correct
    const def = state.config.pieces[p.defId];
    // attackTargetsFromSquare lists squares the piece can CAPTURE (enemy-only
    // moves). For pawns, that means diagonals; for everything else, it's the
    // full move set restricted to enemy squares.
    const targets = attackTargetsFromSquare(state, from, p, def);
    for (const t of targets) {
      if (t === sq) {
        if (def.damage > best) best = def.damage;
        break;        // can't hit harder than its own damage stat
      }
    }
  }
  return best;
}

function isAttacked(state, sq, byColor) {
  return maxIncomingDamage(state, sq, byColor) > 0;
}

// Generate the squares this piece can ATTACK from `from` — i.e. squares where
// an enemy currently sits AND this piece could land there. Used only by the
// attack primitives. Re-uses the move generator's per-pattern logic.
function attackTargetsFromSquare(state, from, piece, def) {
  const out = [];
  for (const pat of def.movePatterns) {
    if (pat.moveOnly) continue;        // by construction, never captures
    collectPatternTargets(state, from, piece, pat, out, /*captureOnly=*/true);
  }
  return out;
}

// ---------------------------------------------------------------------------
// MOVE-PATTERN INTERPRETER (data-driven; replaces hardcoded piece branches)
// ---------------------------------------------------------------------------
// Five primitives cover everything in the standard set plus generic fairy
// pieces. Custom pieces in the config combine them freely.
//
// `targets` is a list of move-record objects pushed onto the caller's array.
// `captureOnlyMode = true` is used by attack-target enumeration: only emit
// squares where an enemy currently sits, and don't emit non-capture moves
// (push squares, EP-reach without ep flag, etc.).

function collectPatternTargets(state, from, piece, pat, out, captureOnlyMode) {
  const f = fileOf(from), r = rankOf(from);
  const board = state.board;
  const myColor = piece.color;

  // Pawn forward direction is color-dependent: white pushes toward rank 7,
  // black toward rank 0. (Note this differs from the "push-back home rank"
  // direction in §10.4, which is the OPPOSITE — toward home rank.)
  const fwd = myColor === WHITE ? 1 : -1;

  if (pat.kind === KIND_LEAPER) {
    for (const off of pat.offsets) {
      const nf = f + off[0], nr = r + off[1];
      if (!inBounds(nf, nr)) continue;
      const to = sqOf(nf, nr);
      const tgt = board[to];
      if (captureOnlyMode) {
        if (tgt && tgt.color !== myColor) out.push({ from, to, capture: true });
      } else {
        if (!tgt) {
          if (!pat.captureOnly) out.push({ from, to });
        } else if (tgt.color !== myColor) {
          if (!pat.moveOnly) out.push({ from, to, capture: true });
        }
      }
    }
  }

  else if (pat.kind === KIND_RIDER) {
    const maxRange = pat.maxRange > 0 ? pat.maxRange : 7;
    for (const dir of pat.offsets) {
      let nf = f + dir[0], nr = r + dir[1];
      let steps = 0;
      while (inBounds(nf, nr) && steps < maxRange) {
        const to = sqOf(nf, nr);
        const tgt = board[to];
        if (!tgt) {
          if (!captureOnlyMode && !pat.captureOnly) out.push({ from, to });
        } else {
          if (tgt.color !== myColor && !pat.moveOnly) {
            out.push({ from, to, capture: true });
          }
          break;   // ray blocked either way
        }
        nf += dir[0]; nr += dir[1]; steps++;
      }
    }
  }

  else if (pat.kind === KIND_PAWN_PUSH) {
    if (captureOnlyMode) return;          // push never captures
    const nr = r + fwd;
    if (!inBounds(f, nr)) return;
    const to = sqOf(f, nr);
    if (!board[to]) {
      const promoRank = myColor === WHITE ? 7 : 0;
      if (nr === promoRank) emitPromotions(state, piece, from, to, /*capture=*/false, out);
      else                  out.push({ from, to });
    }
  }

  else if (pat.kind === KIND_PAWN_DOUBLE) {
    if (captureOnlyMode) return;
    if (piece.hasMoved) return;
    const r1 = r + fwd, r2 = r + 2*fwd;
    if (!inBounds(f, r2)) return;
    if (board[sqOf(f, r1)] || board[sqOf(f, r2)]) return;
    out.push({ from, to: sqOf(f, r2), double: true });
  }

  else if (pat.kind === KIND_PAWN_CAPTURE) {
    const promoRank = myColor === WHITE ? 7 : 0;
    for (const df of [-1, 1]) {
      const nf = f + df, nr = r + fwd;
      if (!inBounds(nf, nr)) continue;
      const to = sqOf(nf, nr);
      const tgt = board[to];
      if (tgt && tgt.color !== myColor) {
        if (nr === promoRank) emitPromotions(state, piece, from, to, true, out);
        else                  out.push({ from, to, capture: true });
      } else if (!captureOnlyMode && !tgt && to === state.ep) {
        // En passant: legal only on the single ply after the opponent's
        // 2-square pawn push. state.ep stores the target square.
        out.push({ from, to, capture: true, enpassant: true });
      }
    }
  }
}

// Promotion emits one move per option (=Q,=R,=B,=N — driven by piece def).
function emitPromotions(state, piece, from, to, capture, out) {
  const def = state.config.pieces[piece.defId];
  const opts = def.promotesTo && def.promotesTo.length ? def.promotesTo : [];
  if (opts.length === 0) {
    out.push(capture ? { from, to, capture: true } : { from, to });
    return;
  }
  for (const promo of opts) {
    out.push(capture ? { from, to, capture: true, promo } : { from, to, promo });
  }
}

// ---------------------------------------------------------------------------
// pseudoLegalMoves — moves that obey movement rules but ignore self-check.
// Self-check (HP-aware) is enforced one layer up in legalMoves().
// ---------------------------------------------------------------------------

function pseudoLegalMoves(state, color) {
  const moves = [];
  for (let from = 0; from < 64; from++) {
    const p = state.board[from];
    if (!p || p.color !== color) continue;
    if (isFrozen(p)) continue;     // FREEZE: skip frozen pieces (§11.6)
    const def = state.config.pieces[p.defId];
    for (const pat of def.movePatterns) {
      collectPatternTargets(state, from, p, pat, moves, /*captureOnlyMode=*/false);
    }
  }
  return moves;
}

function isFrozen(piece) {
  for (const e of piece.activeEffects) {
    if (e.kind === EFFECT_FREEZE && e.turnsRemaining > 0) return true;
  }
  return false;
}

// =============================================================================
// applyMove — the only mutator. Returns a NEW state.
// -----------------------------------------------------------------------------
// Sequence (DESIGN.md §6, IMPLEMENTATION-GODOT §8.3):
//
//   1. Clone the state.
//   2. Move/attack:
//      - destination empty → relocate; if pawn double-push, set ep target.
//      - destination has enemy → ATTACK:
//          • damage = attacker.damage; effectiveDamage clamped by target.hp
//          • if target dies (hp ≤ damage):
//              attacker takes the square; en-passant variant removes
//              the pawn behind.
//          • if target survives:
//              target.hp -= damage; target pushed one square toward its
//              own home rank; chain-push pieces behind in the same
//              direction; off-board = killed (a second damage path);
//              attacker stays on its origin square (§10).
//          • on-hit status effect (burn/freeze) applies if target survives
//            the regular hit (NOT applied by ability damage — §7.1/§7.2).
//   3. Castling: also slide the rook (handled like classical chess).
//   4. Castling-rights bookkeeping: any king move kills both rights;
//      a rook leaving its home (or being captured ON its home) kills the
//      relevant right.
//   5. EP target: set ONLY for a 2-square pawn push, otherwise cleared.
//      (Forgetting to clear means EP would remain "available" forever.)
//   6. Halfmove clock: reset on pawn move OR any capture/damage,
//      else increment.
//   7. Fullmove number: bump after Black's move.
//   8. Flip side-to-move.
//   9. TURN-START TICK on the new side (IMPL-GODOT §17 — order is critical):
//      (a) resolve any pending cannons whose triggersOnFullmove == now AND
//          ownerColor == opposite(newSide), so they hit BEFORE the new side
//          could dodge with their move. (Owned by opposite because they
//          fired on opposite's previous turn.)
//      (b) tick burns/freezes on new side's pieces.  Burn first because a
//          piece may die from burn — no need to keep its freeze around.
//      (c) tick ability recharge on new side's pieces.  Last, so freshly
//          earned charges are usable this turn.
//   10. Reset specialUsedThisTurn so the new side may use ONE ability this
//       turn.
//
// applyMove also accepts ABILITY actions (kind === 'ability'). Those don't
// flip side; they consume a charge, mutate state, and set
// specialUsedThisTurn = true.  See applyAbility below.
// =============================================================================

function applyMove(state, m) {
  const next = cloneState(state);
  const events = [];   // animation hints for the renderer; engine ignores

  const piece = next.board[m.from];
  if (!piece) throw new Error('applyMove: empty square at from=' + m.from);
  const def = state.config.pieces[piece.defId];

  // --- (2) Move / attack ----------------------------------------------------
  let captured = next.board[m.to];
  let damageDealt = false;
  let attackerMoves = true;   // if target survives, attacker stays put

  if (m.enpassant) {
    // En passant: captured pawn sits BEHIND the destination. (Pawns are
    // assumed HP 1 by config — but we still go through the damage path so
    // higher-HP pawns work in custom configs.)
    const capSq = m.to + (piece.color === WHITE ? -8 : 8);
    captured = next.board[capSq];
    if (captured) {
      const dmg = def.damage;
      if (captured.hp <= dmg) {
        next.board[capSq] = null;
        events.push({ kind: 'kill', sq: capSq });
      } else {
        captured.hp -= dmg;
        // EP push direction: the captured pawn is pushed toward its own
        // home rank, but EP is a corner-case — typically pawns are HP 1 so
        // they die. We handle it for completeness.
        const pushed = applyPushChain(next, capSq, captured.color === WHITE ? -8 : 8, events);
        if (pushed) attackerMoves = true;   // attacker still moves to m.to
      }
      damageDealt = true;
      maybeApplyOnHitEffect(next, m.to, captured, def);   // unusual but consistent
    }
    next.board[m.to] = piece;
    next.board[m.from] = null;
    events.push({ kind: 'move', from: m.from, to: m.to });
  }

  else if (captured) {
    // Regular attack on an enemy.
    const dmg = def.damage;
    if (captured.hp <= dmg) {
      // Target dies → normal capture; attacker takes the square.
      events.push({ kind: 'kill', sq: m.to });
      next.board[m.to] = piece;
      next.board[m.from] = null;
      events.push({ kind: 'move', from: m.from, to: m.to });
    } else {
      // Target survives → damage + push toward target's home rank.
      // Chain victims take NO damage (§10.4) — they only relocate.
      captured.hp -= dmg;
      events.push({ kind: 'damage', sq: m.to, hp: captured.hp });
      maybeApplyOnHitEffect(next, m.to, captured, def);
      const pushDir = captured.color === WHITE ? -8 : 8;   // toward own home rank
      applyPushChain(next, m.to, pushDir, events);
      attackerMoves = false;
    }
    damageDealt = true;
  }

  else {
    // No target — just relocate.
    next.board[m.to] = piece;
    next.board[m.from] = null;
    events.push({ kind: 'move', from: m.from, to: m.to });
    attackerMoves = true;
  }

  // Promotion. Replace defId; reset HP/charges to match the new def.
  if (m.promo) {
    const promoPiece = next.board[m.to];
    const promoDef = state.config.pieces[m.promo];
    promoPiece.defId           = m.promo;
    promoPiece.hp              = promoDef.hp;
    promoPiece.specialCharges  = promoDef.special ? (promoDef.special.initialCharges|0) : 0;
    promoPiece.specialRecharge = promoDef.special ? (promoDef.special.cooldownTurns|0)  : 0;
    events.push({ kind: 'promote', sq: m.to, defId: m.promo });
  }

  piece.hasMoved = true;

  // --- (3) Castling — slide the rook --------------------------------------
  // Castling presupposes target square was empty; so attackerMoves was true.
  // The board state at this point already has the king on its destination;
  // we just need to relocate the rook.
  if (m.castle === 1) {
    // Kingside: rook moves from h-file to f-file.
    const homeRank = piece.color === WHITE ? 0 : 7;
    const rookFrom = sqOf(7, homeRank), rookTo = sqOf(5, homeRank);
    next.board[rookTo]   = next.board[rookFrom];
    next.board[rookFrom] = null;
    if (next.board[rookTo]) next.board[rookTo].hasMoved = true;
    events.push({ kind: 'move', from: rookFrom, to: rookTo });
  } else if (m.castle === -1) {
    const homeRank = piece.color === WHITE ? 0 : 7;
    const rookFrom = sqOf(0, homeRank), rookTo = sqOf(3, homeRank);
    next.board[rookTo]   = next.board[rookFrom];
    next.board[rookFrom] = null;
    if (next.board[rookTo]) next.board[rookTo].hasMoved = true;
    events.push({ kind: 'move', from: rookFrom, to: rookTo });
  }

  // --- (5) EP target -------------------------------------------------------
  next.ep = m.double ? (m.from + m.to) >> 1 : -1;

  // --- (6) Halfmove clock --------------------------------------------------
  // Reset on pawn move, on any capture/damage. (Damage without kill still
  // counts as "progress" — we picked this so the 50-move rule doesn't fire
  // mid-attrition phase.)
  const movedDef = state.config.pieces[piece.defId];   // before promotion
  const isPawnMove = movedDef.movePatterns.some(p =>
    p.kind === KIND_PAWN_PUSH || p.kind === KIND_PAWN_DOUBLE || p.kind === KIND_PAWN_CAPTURE
  );
  next.halfmove = (isPawnMove || damageDealt) ? 0 : state.halfmove + 1;

  // --- (7) Fullmove --------------------------------------------------------
  next.fullmove = state.fullmove + (state.side === BLACK ? 1 : 0);

  // --- (8) Flip side -------------------------------------------------------
  next.side = opposite(state.side);

  // --- (9) TURN-START TICK on new side -------------------------------------
  // Order matters: cannons → burns → freezes → ability recharge.
  resolvePendingCannons(next, events);
  tickStatusEffects(next, events);
  tickAbilityRecharge(next);

  // --- (10) Reset per-turn ability cap -------------------------------------
  next.specialUsedThisTurn = false;

  return { state: next, events, mute: !attackerMoves };
}

// ---------------------------------------------------------------------------
// Push-chain (§10.4). The piece at `startSq` shifts by `dir` (a square-index
// delta: ±1 for horizontal, ±8 for vertical, ±7/±9 for diagonal). Same chain
// rule for any direction, but only ±8 is currently produced (vertical home-
// ward push). Generalized so the same routine handles ability knockback if
// added later.
//
// We require pure-rank or pure-file shifts so wrap-around isn't possible by
// the file-difference test below; for vertical (±8) the file is preserved.
// ---------------------------------------------------------------------------

function applyPushChain(state, startSq, dir, events) {
  // Build the chain: pieces that will shift by `dir` together.
  const chain = [startSq];
  let cur = startSq;
  while (true) {
    const nxt = cur + dir;
    if (!squareReachable(cur, nxt, dir)) break;   // off-board
    if (!state.board[nxt]) break;
    chain.push(nxt);
    cur = nxt;
  }

  const tail = cur + dir;   // square immediately past the last chain element
  if (!squareReachable(cur, tail, dir)) {
    // Chain hits the wall: the LAST piece is pushed off-board → killed.
    // Everyone else shifts by one in `dir`.
    events.push({ kind: 'kill', sq: chain[chain.length - 1] });
    state.board[chain[chain.length - 1]] = null;
    for (let i = chain.length - 2; i >= 0; i--) {
      const src = chain[i], dst = chain[i] + dir;
      state.board[dst] = state.board[src];
      state.board[src] = null;
      events.push({ kind: 'push', from: src, to: dst });
    }
    return true;
  } else {
    // Tail is in-bounds and (because the loop terminated) empty.
    // Shift everyone by one.
    for (let i = chain.length - 1; i >= 0; i--) {
      const src = chain[i], dst = chain[i] + dir;
      state.board[dst] = state.board[src];
      state.board[src] = null;
      events.push({ kind: 'push', from: src, to: dst });
    }
    return true;
  }
}

// Verify `b = a + dir` is on the board AND respects file alignment for the
// step kind we care about (vertical-only currently).
function squareReachable(a, b, dir) {
  if (b < 0 || b >= 64) return false;
  // Vertical (±8): file must be the same.
  if (dir === 8 || dir === -8) return fileOf(a) === fileOf(b);
  // Horizontal (±1): rank must be the same and file delta is exactly 1.
  if (dir === 1 || dir === -1) return rankOf(a) === rankOf(b) &&
                                      Math.abs(fileOf(a) - fileOf(b)) === 1;
  // Diagonals (±7, ±9): file delta exactly 1, rank delta exactly 1.
  if (Math.abs(dir) === 7 || Math.abs(dir) === 9) {
    return Math.abs(fileOf(a) - fileOf(b)) === 1 &&
           Math.abs(rankOf(a) - rankOf(b)) === 1;
  }
  return false;
}

// On-hit status effect: copy the attacker's def.onHit onto the target. Called
// only when the target SURVIVES the regular hit (matches §6.1: "applied when
// an attacker hits a target that survives").
function maybeApplyOnHitEffect(state, victimSq, victim, attackerDef) {
  if (!attackerDef.onHit || attackerDef.onHit.kind === EFFECT_NONE) return;
  const eff = attackerDef.onHit;
  // Burn: latest application overwrites duration; damage doesn't stack.
  // Freeze: refreshes duration. Both effects are kept as ONE instance per
  // (kind, victim). (§6.1.)
  const existing = victim.activeEffects.find(e => e.kind === eff.kind);
  if (existing) {
    existing.turnsRemaining = eff.duration;
    existing.damagePerTurn  = eff.damagePerTurn;
  } else {
    victim.activeEffects.push({
      kind:           eff.kind,
      damagePerTurn:  eff.damagePerTurn | 0,
      turnsRemaining: eff.duration | 0,
    });
  }
}

// =============================================================================
// TURN-START TICKS (run on the side-to-move at the start of their turn)
// -----------------------------------------------------------------------------
// Order: pending-cannons → burn → freeze → ability recharge. (See IMPL-GODOT
// §17 "Charge tick ordering" for why each step is in this order.)
// =============================================================================

// (a) Resolve pending cannons whose ownerColor == opposite(newSide) AND
// triggersOnFullmove == newState.fullmove. They were fired on the OPPONENT's
// previous turn and resolve at the start of the NEW side's turn — meaning
// the new side feels the damage before they get to react.  Wait — that's
// inconsistent with §7.7 which says cannons resolve at start of OWNER's
// turn. Resolving at start of victim's turn is functionally equivalent for
// turn-budgeting only if cannons can target opponent.
//
// We follow §7.7 LITERALLY: a cannon fires on owner-turn N, resolves at
// start of owner-turn N+1 — i.e., when side flips back to owner. So the
// new-side filter here is `pa.ownerColor === newSide`.
//
// IMPORTANT consequence for the check predicate: a pending cannon owned by
// OPPONENT will resolve when side flips back to OPPONENT — i.e., on
// opponent's NEXT turn, BEFORE their move. So opponent's pending cannons
// contribute to my-turn damage budget against my king.

function resolvePendingCannons(state, events) {
  const stillPending = [];
  for (const pa of state.pendingAttacks) {
    const triggersNow =
      pa.kind === ABILITY_CANNON &&
      pa.ownerColor === state.side &&
      pa.triggersOnFullmove === state.fullmove;
    if (!triggersNow) { stillPending.push(pa); continue; }
    // Apply damage to every piece on a target square. Special-ability damage:
    // no push-back, no on-hit effect (§7.1).
    for (const sq of pa.targetSquares) {
      const v = state.board[sq];
      if (!v) continue;
      // Friendly fire on cannon: the AOE is centered on a target chosen by
      // the owner. Plus shape can include the owner's own pieces. We allow
      // friendly damage — the owner shouldn't aim there if they don't want
      // to hit allies. (Spec is ambiguous; this is the simpler rule and
      // creates more interesting positioning decisions.)
      if (v.hp <= pa.damage) {
        events.push({ kind: 'kill', sq });
        state.board[sq] = null;
      } else {
        v.hp -= pa.damage;
        events.push({ kind: 'damage', sq, hp: v.hp });
      }
    }
    events.push({ kind: 'cannonResolved', target: pa.targetSquares.slice() });
  }
  state.pendingAttacks = stillPending;
}

// (b) Tick burns and freezes on the side-to-move's pieces.
function tickStatusEffects(state, events) {
  for (let i = 0; i < 64; i++) {
    const p = state.board[i];
    if (!p || p.color !== state.side) continue;
    let died = false;
    for (const e of p.activeEffects) {
      if (e.kind === EFFECT_BURN && e.turnsRemaining > 0) {
        if (p.hp <= e.damagePerTurn) {
          events.push({ kind: 'kill', sq: i, by: 'burn' });
          state.board[i] = null;
          died = true;
          break;
        } else {
          p.hp -= e.damagePerTurn;
          events.push({ kind: 'damage', sq: i, hp: p.hp, by: 'burn' });
        }
      }
    }
    if (died) continue;
    // Decrement counters AFTER damage applies. A burn with turnsRemaining=2
    // ticks twice (two damages on two consecutive turns).
    for (const e of p.activeEffects) {
      if (e.turnsRemaining > 0) e.turnsRemaining -= 1;
    }
    p.activeEffects = p.activeEffects.filter(e => e.turnsRemaining > 0);
  }
}

// (c) Ability recharge.  At the start of OWNER's turn:
//   if recharge counter > 0: decrement.
//   if counter hit 0 AND charges < cap: gain a charge, reset counter.
function tickAbilityRecharge(state) {
  for (let i = 0; i < 64; i++) {
    const p = state.board[i];
    if (!p || p.color !== state.side) continue;
    const def = state.config.pieces[p.defId];
    if (!def.special || def.special.kind === ABILITY_NONE) continue;
    if (p.specialRecharge > 0) p.specialRecharge -= 1;
    if (p.specialRecharge === 0 && p.specialCharges < def.special.maxCharges) {
      p.specialCharges += 1;
      p.specialRecharge = def.special.cooldownTurns;
    }
  }
}

// =============================================================================
// CASTLING (kept as a hardcoded special case, gated by the king def's
// `canCastle` flag and by the standard chess castling-rights bookkeeping.
// In a fully-data-driven future this would be a per-royal "linked-move rule"
// — see DESIGN.md §8.2 — but that's out of scope here.)
// -----------------------------------------------------------------------------
// THE THREE ATTACK CHECKS (DESIGN.md §5):
//   1. King not currently in check.
//   2. Transit square not attacked — with the king SIMULATED on the transit
//      square so rays previously blocked by the king at its origin are now
//      unblocked. Without this, you'd allow an illegal castle through a
//      cleared rook ray.
//   3. Destination not attacked — handled later by the standard self-check
//      filter in legalMoves.
// =============================================================================

function addCastlingMoves(state, color, kingSq, moves) {
  const kingPiece = state.board[kingSq];
  const def = state.config.pieces[kingPiece.defId];
  if (!def.canCastle) return;
  if (kingPiece.hasMoved) return;
  const homeRank = color === WHITE ? 0 : 7;
  if (kingSq !== sqOf(4, homeRank)) return;
  // (1) Not in check now. We use isAttacked which already incorporates HP-1
  // semantics by being a "could-anyone-hit-me" question; for castling, the
  // classical rule is "not currently attacked" regardless of HP, so we
  // preserve that.
  if (isAttacked(state, kingSq, opposite(color))) return;

  const tryCastle = (rookFile, betweenFiles, transitFile, kingToFile, castleSide) => {
    const rookSq = sqOf(rookFile, homeRank);
    const rook = state.board[rookSq];
    if (!rook) return;
    if (rook.color !== color) return;
    if (rook.hasMoved) return;
    for (const bf of betweenFiles) if (state.board[sqOf(bf, homeRank)]) return;

    // (2) Simulate king on transit square; re-run isAttacked.
    const transitSq = sqOf(transitFile, homeRank);
    const sim = cloneState(state);
    sim.board[kingSq]   = null;
    sim.board[transitSq] = kingPiece;
    if (isAttacked(sim, transitSq, opposite(color))) return;

    moves.push({ from: kingSq, to: sqOf(kingToFile, homeRank), castle: castleSide });
  };
  tryCastle(7, [5, 6],    5, 6,  1);   // kingside
  tryCastle(0, [1, 2, 3], 3, 2, -1);   // queenside
}

// =============================================================================
// legalMoves — HP-aware self-check filter (IMPL-GODOT §8.2)
// -----------------------------------------------------------------------------
// > "A move is legal iff, after playing it, OPPONENT cannot reduce my royal's
// > HP to zero on their next turn."
//
// This single rule subsumes pins, blocks, king escapes, AND HP-budget
// survival. The closed form holds (DESIGN.md §11.7) because the predicate
// is a SUM over current-state contributors, not a search:
//
//   threat = max-attacker-damage-on-my-royal-square    (move-attack threat)
//          + sum-of-pending-cannon-damage-on-my-royal  (queued ability)
//          + 0                                         (lightning can't hit royals)
//
// DOT damage on royal is already reflected in royal.hp (it ticks at start
// of my turn — applyMove ran the tick already on the pre-applyMove side
// flip; for the just-flipped side we tick INSIDE applyMove). So we don't
// add it here.
// =============================================================================

function legalMoves(state) {
  const me = state.side;
  const out = [];

  // Castling moves are added per-king inside the loop (need the per-color
  // king square).
  for (const m of pseudoLegalMoves(state, me)) out.push(m);
  // Castling: locate this side's royals that have canCastle.
  for (let i = 0; i < 64; i++) {
    const p = state.board[i];
    if (!p || p.color !== me) continue;
    if (isFrozen(p)) continue;
    const def = state.config.pieces[p.defId];
    if (def.royal && def.canCastle) addCastlingMoves(state, me, i, out);
  }

  // Self-check filter.
  return out.filter(m => moveSurvivable(state, m));
}

// "If I play m, can opponent kill my royal on their next turn?"
function moveSurvivable(state, m) {
  const me = state.side;
  const r = applyMove(state, m);
  const next = r.state;
  const myRoyal = findRoyal(next, me);
  if (myRoyal < 0) return false;        // royal died — clearly illegal
  const royal = next.board[myRoyal];
  if (!royal) return false;
  // After applyMove, side has flipped to opponent AND the cannon-tick may
  // have already resolved damage owed to me. So I need to inspect the
  // post-tick state and ask: at this moment, can opponent kill me on their
  // NEXT turn? Same formula:
  const threat = nextTurnDamageBudget(next, myRoyal, opposite(me));
  return royal.hp > threat;
}

// next-turn damage budget on `royalSq` from `byColor` (the side whose threat
// we're estimating). Two contexts call this:
//
//   (A) Pre-move state passed to gameStatus — state.side === royalSq's owner
//       (= "me"), byColor === opposite(me).  The threat is what opponent can
//       deal on their NEXT turn.  That includes pending cannons owned by
//       opponent that fire on opponent's next turn-start (== state.fullmove +
//       1, see cannonTriggerFullmove).
//
//   (B) Post-move state passed to moveSurvivable — state.side === byColor.
//       The state has already had byColor's turn-start tick run inside
//       applyMove, so any cannon scheduled for THIS turn-start is gone from
//       the queue. The remaining cannons are for byColor's NEXT-NEXT turn —
//       too far in the future to count for the immediate-next-move budget,
//       so we omit them.
//
// The `state.side !== byColor` guard distinguishes (A) from (B).
function nextTurnDamageBudget(state, royalSq, byColor) {
  let dmg = maxIncomingDamage(state, royalSq, byColor);   // move-attack
  if (state.side !== byColor) {
    const nextFullmove = state.fullmove + 1;
    for (const pa of state.pendingAttacks) {
      if (pa.ownerColor !== byColor)              continue;
      if (pa.kind !== ABILITY_CANNON)             continue;
      if (pa.triggersOnFullmove !== nextFullmove) continue;
      if (pa.targetSquares.indexOf(royalSq) >= 0) dmg += pa.damage;
    }
  }
  return dmg;
}

// =============================================================================
// gameStatus — once per turn, after applyMove, before rendering.
// -----------------------------------------------------------------------------
//   inCheck = side-to-move's royal is at HP ≤ next-turn damage budget
//   noMoves = legalMoves(state).length === 0
//
//   inCheck && noMoves → checkmate (winner = opposite side)
//   !inCheck && noMoves → stalemate
//   inCheck → "in check" badge
//   halfmove ≥ 100 → 50-move draw
// =============================================================================

function gameStatus(state) {
  const me = state.side;
  const royalSq = findRoyal(state, me);
  if (royalSq < 0) {
    // Royal already dead before the side could move — opponent wins. This
    // can happen with HP-leak modes; with the normal HP-aware filter it
    // shouldn't, but we handle it defensively.
    return { kind: 'checkmate', winner: opposite(me), inCheck: true, moves: [] };
  }
  const royal = state.board[royalSq];
  const threat = nextTurnDamageBudget(state, royalSq, opposite(me));
  const inCheck = royal.hp <= threat;
  const moves = legalMoves(state);
  if (moves.length === 0) {
    return inCheck
      ? { kind: 'checkmate', winner: opposite(me), inCheck, moves, royalSq }
      : { kind: 'stalemate', inCheck, moves, royalSq };
  }
  if (state.halfmove >= 100) return { kind: 'draw50', inCheck, moves, royalSq };
  return { kind: inCheck ? 'check' : 'normal', inCheck, moves, royalSq };
}

// =============================================================================
// ABILITIES (cannon, lightning) — see §7 of IMPLEMENTATION-GODOT.md
// -----------------------------------------------------------------------------
// Abilities are fired SEPARATELY from the regular move (UI orchestrates both
// within a single turn). Each ability use:
//   - requires the source piece to belong to side-to-move
//   - requires specialUsedThisTurn === false (one ability per turn)
//   - requires source.specialCharges > 0
//   - requires the target be valid for the ability kind
//
// Ability use does NOT flip side, does NOT tick turn-start effects. It mutates
// (returns NEW state) and sets specialUsedThisTurn = true. The next applyMove
// (regular move) flips side and ticks the new side's start.
// =============================================================================

function listAbilityTargets(state, sourceSq) {
  // Squares this source can fire its ability at, as legal targets (i.e.
  // would pass validateAbility). Returns [{ sq, plus?: [sq...] }] for
  // cannon's plus-pattern preview.
  const p = state.board[sourceSq];
  if (!p || p.color !== state.side) return [];
  const def = state.config.pieces[p.defId];
  if (!def.special || def.special.kind === ABILITY_NONE) return [];
  if (state.specialUsedThisTurn) return [];
  if (p.specialCharges <= 0) return [];

  const out = [];
  if (def.special.kind === ABILITY_CANNON) {
    // Plus-shape AOE; forbidden if any square in the plus overlaps the
    // ENEMY initial-occupied squares.
    const enemy = opposite(p.color);
    const forbidden = state.initialPiecesByColor[enemy];
    for (let target = 0; target < 64; target++) {
      const plus = cannonPlusSquares(target);
      if (plus === null) continue;            // out of bounds
      let ok = true;
      for (const s of plus) if (forbidden.has(s)) { ok = false; break; }
      if (ok) out.push({ sq: target, plus });
    }
  } else if (def.special.kind === ABILITY_LIGHTNING) {
    // Single-target enemy non-royal.
    for (let target = 0; target < 64; target++) {
      const t = state.board[target];
      if (!t || t.color === p.color) continue;
      const tdef = state.config.pieces[t.defId];
      if (tdef.royal) continue;
      out.push({ sq: target });
    }
  }
  return out;
}

function cannonPlusSquares(centerSq) {
  const f = fileOf(centerSq), r = rankOf(centerSq);
  const out = [];
  for (const off of CANNON_PLUS_OFFSETS) {
    const nf = f + off[0], nr = r + off[1];
    if (!inBounds(nf, nr)) return null;       // entire plus must fit
    out.push(sqOf(nf, nr));
  }
  return out;
}

function validateAbility(state, action) {
  // action: { kind: ABILITY_CANNON|ABILITY_LIGHTNING, sourceSq, targetSq }
  if (state.specialUsedThisTurn) return 'already used ability this turn';
  const src = state.board[action.sourceSq];
  if (!src || src.color !== state.side) return 'source not your piece';
  if (isFrozen(src))                  return 'source is frozen';
  const def = state.config.pieces[src.defId];
  if (!def.special || def.special.kind !== action.kind) return 'wrong ability';
  if (src.specialCharges <= 0)        return 'no charges';

  if (action.kind === ABILITY_CANNON) {
    const plus = cannonPlusSquares(action.targetSq);
    if (!plus) return 'plus area off-board';
    const enemy = opposite(src.color);
    const forbidden = state.initialPiecesByColor[enemy];
    for (const s of plus) {
      if (forbidden.has(s)) return 'plus area overlaps enemy starting zone';
    }
  } else if (action.kind === ABILITY_LIGHTNING) {
    const t = state.board[action.targetSq];
    if (!t)                  return 'target empty';
    if (t.color === src.color) return 'cannot target friendly';
    const tdef = state.config.pieces[t.defId];
    if (tdef.royal)          return 'cannot target royal piece';
  } else {
    return 'unknown ability';
  }
  return null;   // valid
}

function applyAbility(state, action) {
  const err = validateAbility(state, action);
  if (err) throw new Error('applyAbility: ' + err);

  const next = cloneState(state);
  const events = [];
  const src = next.board[action.sourceSq];
  const def = state.config.pieces[src.defId];
  src.specialCharges -= 1;
  // Recharge timer resets when a charge is consumed (so cooldown re-counts).
  src.specialRecharge = def.special.cooldownTurns;

  if (action.kind === ABILITY_CANNON) {
    // QUEUE the attack — does not damage anything immediately.
    // Triggers when fullmove reaches the same value AND side is back to
    // owner — i.e., owner's NEXT turn (one full move-pair away).
    next.pendingAttacks.push({
      kind:               ABILITY_CANNON,
      ownerColor:         src.color,
      damage:             def.special.damage,
      targetSquares:      cannonPlusSquares(action.targetSq).slice(),
      triggersOnFullmove: cannonTriggerFullmove(state),
    });
    events.push({ kind: 'cannonQueued', source: action.sourceSq,
                  target: action.targetSq });
  } else if (action.kind === ABILITY_LIGHTNING) {
    // INSTANT damage. No push-back, no on-hit effect (§7.2).
    const v = next.board[action.targetSq];
    if (v.hp <= def.special.damage) {
      events.push({ kind: 'kill', sq: action.targetSq, by: 'lightning' });
      next.board[action.targetSq] = null;
    } else {
      v.hp -= def.special.damage;
      events.push({ kind: 'damage', sq: action.targetSq, hp: v.hp,
                    by: 'lightning' });
    }
    events.push({ kind: 'lightning', source: action.sourceSq,
                  target: action.targetSq });
  }

  next.specialUsedThisTurn = true;
  return { state: next, events };
}

// Cannon fires on owner's turn N, lands at the start of owner's turn N+1.
// Each color's fullmove value increments by 1 between consecutive turns of
// theirs (black's move bumps fullmove for both colors' "next turn" view):
//   white at fullmove k → black at fullmove k → white again at fullmove k+1.
//   black at fullmove k → white at fullmove k+1 → black at fullmove k+1.
// So in BOTH cases, owner's NEXT turn is at state.fullmove + 1.
function cannonTriggerFullmove(state) {
  return state.fullmove + 1;
}

// =============================================================================
// EXPORT
// =============================================================================

const Engine = {
  // constants
  WHITE, BLACK,
  KIND_LEAPER, KIND_RIDER, KIND_PAWN_PUSH, KIND_PAWN_DOUBLE, KIND_PAWN_CAPTURE,
  ABILITY_NONE, ABILITY_CANNON, ABILITY_LIGHTNING,
  EFFECT_NONE, EFFECT_BURN, EFFECT_FREEZE,
  CANNON_PLUS_OFFSETS,
  // helpers
  opposite, fileOf, rankOf, sqOf, inBounds, isFrozen,
  // state
  newGame, cloneState, findRoyal,
  // moves
  pseudoLegalMoves, legalMoves, applyMove, gameStatus,
  // primitives
  isAttacked, maxIncomingDamage, nextTurnDamageBudget,
  // abilities
  listAbilityTargets, cannonPlusSquares, validateAbility, applyAbility,
};

root.Engine = Engine;
if (typeof module !== 'undefined' && module.exports) module.exports = Engine;

})(typeof window !== 'undefined' ? window : globalThis);
