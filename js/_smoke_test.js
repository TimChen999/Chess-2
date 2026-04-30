"use strict";
// Quick smoke test for the engine — runs in Node, no DOM.
//   node js/_smoke_test.js

const path = require('path');
require(path.join(__dirname, 'engine.js'));
require(path.join(__dirname, 'config.js'));

const E = globalThis.Engine;
const C = globalThis.Config;

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; }
  else      { failed++; console.error('FAIL:', msg); }
}

const cfg = C.defaultConfig();
const s0 = E.newGame(cfg);
const status0 = E.gameStatus(s0);

// Standard opening: 16 pawn moves + 4 knight moves = 20.
assert(status0.moves.length === 20, 'opening moves = 20, got ' + status0.moves.length);
assert(status0.kind === 'normal',    'opening status normal, got ' + status0.kind);

// e2-e4: from square 12 to square 28.
const e2e4 = status0.moves.find(m => m.from === 12 && m.to === 28);
assert(!!e2e4, 'e2-e4 in legal moves');
assert(e2e4 && e2e4.double === true, 'e2-e4 marked as double-push');

const r1 = E.applyMove(s0, e2e4);
const s1 = r1.state;
assert(s1.side === E.BLACK, 'side flipped to BLACK');
assert(s1.ep === 20,        'ep target = sq 20 (e3), got ' + s1.ep);
assert(s1.fullmove === 1,   'fullmove still 1 after white move');

const status1 = E.gameStatus(s1);
assert(status1.moves.length === 20, 'black has 20 opening moves');

// Confirm the rook-burn-on-hit attaches to a target that survives.
// Setup: empty a path so a rook can hit a 3-HP target.
// Use a synthetic state.
function place(board, sq, id, color, fromCfg) {
  const def = (fromCfg || cfg).pieces[id];
  board[sq] = {
    defId: id, color, hp: def.hp,
    activeEffects: [],
    specialCharges:  def.special ? (def.special.initialCharges | 0) : 0,
    specialRecharge: def.special ? (def.special.cooldownTurns  | 0) : 0,
    hasMoved: false,
  };
}
const tcfg = C.defaultConfig();
const tboard = new Array(64).fill(null);
place(tboard, E.sqOf(0, 0), 'rook', E.WHITE);     // rook on a1
place(tboard, E.sqOf(0, 4), 'rook', E.BLACK);     // enemy rook on a5 (HP 3)
place(tboard, E.sqOf(4, 0), 'king', E.WHITE);
place(tboard, E.sqOf(4, 7), 'king', E.BLACK);
const ts = {
  config: tcfg, board: tboard, side: E.WHITE,
  ep: -1, halfmove: 0, fullmove: 1,
  pendingAttacks: [], specialUsedThisTurn: false,
  initialPiecesByColor: { 0: new Set(), 1: new Set() },
};
const tmove = { from: E.sqOf(0,0), to: E.sqOf(0,4), capture: true };
const r = E.applyMove(ts, tmove);
const after = r.state;
// Target was at sq(0,4) (a5), survives the 1-dmg hit at HP 3, pushed to
// sq(0,5) (a6). Origin square (a5) becomes empty; attacker stays at a1.
//
// Burn ticks at the start of the target's owner's turn — which fires
// inside applyMove right after the side flip — so the target eats 1
// (hit) + 1 (burn tick) = 2 damage by the time applyMove returns. HP 3
// → 1, with one burn tick still to come on black's next turn.
assert(after.board[E.sqOf(0,4)] === null, 'a5 vacated by push');
const pushed = after.board[E.sqOf(0,5)];
assert(!!pushed, 'pushed target found at a6');
assert(pushed && pushed.hp === 1, 'pushed target HP = 1 after hit + burn tick, got ' + (pushed && pushed.hp));
assert(pushed && pushed.activeEffects.some(e => e.kind === E.EFFECT_BURN),
       'burn still active on hit target (1 tick remaining)');
assert(after.board[E.sqOf(0,0)] !== null, 'attacker still on a1 (target survived)');

// Mate setup: scholar's mate roughly. Skip; complicated to verify.

// Lightning test: bishop should NOT be allowed to target a king.
const lightcfg = C.defaultConfig();
const lboard = new Array(64).fill(null);
place(lboard, E.sqOf(0, 0), 'bishop', E.WHITE);
place(lboard, E.sqOf(4, 0), 'king',   E.WHITE);
place(lboard, E.sqOf(4, 7), 'king',   E.BLACK);
const ls = {
  config: lightcfg, board: lboard, side: E.WHITE,
  ep: -1, halfmove: 0, fullmove: 1,
  pendingAttacks: [], specialUsedThisTurn: false,
  initialPiecesByColor: { 0: new Set(), 1: new Set() },
};
const lerr = E.validateAbility(ls, {
  kind: E.ABILITY_LIGHTNING, sourceSq: E.sqOf(0,0), targetSq: E.sqOf(4,7),
});
assert(lerr !== null, 'lightning targeting king must be rejected');

// Legal alt target (a knight on the board).
place(lboard, E.sqOf(1, 7), 'knight', E.BLACK);
const lerr2 = E.validateAbility(ls, {
  kind: E.ABILITY_LIGHTNING, sourceSq: E.sqOf(0,0), targetSq: E.sqOf(1,7),
});
assert(lerr2 === null, 'lightning targeting non-royal valid (got ' + lerr2 + ')');

// Cannon: white queen fires at center; should queue with triggersOnFullmove
// = fullmove+1, and resolve at start of white's NEXT turn (after black's
// move bumps fullmove). We test that by giving the queen 1 charge.
const ccfg = C.defaultConfig();
const cboard = new Array(64).fill(null);
place(cboard, E.sqOf(3, 3), 'queen', E.WHITE);   // queen on d4
place(cboard, E.sqOf(4, 0), 'king',  E.WHITE);
place(cboard, E.sqOf(4, 7), 'king',  E.BLACK);
place(cboard, E.sqOf(0, 1), 'pawn',  E.BLACK);   // a victim — black pawn at a2... ah a black pawn shouldn't be at rank 1 (white's pawn rank)
                                                 // but for this test, anywhere is fine
cboard[E.sqOf(3,3)].specialCharges = 1;
cboard[E.sqOf(3,3)].specialRecharge = 0;
const cs = {
  config: ccfg, board: cboard, side: E.WHITE,
  ep: -1, halfmove: 0, fullmove: 1,
  pendingAttacks: [], specialUsedThisTurn: false,
  initialPiecesByColor: { 0: new Set(), 1: new Set() },
};
const targetCenter = E.sqOf(0, 1);
const cAction = { kind: E.ABILITY_CANNON, sourceSq: E.sqOf(3,3), targetSq: targetCenter };
// Plus must fit on board — this center is on file 0, so plus would include
// (-1,1) which is off-board. Fix by re-targeting.
const cTarget2 = E.sqOf(2, 4);    // c5: full plus fits
const cAction2 = { kind: E.ABILITY_CANNON, sourceSq: E.sqOf(3,3), targetSq: cTarget2 };
const cErr = E.validateAbility(cs, cAction2);
assert(cErr === null, 'cannon target (2,4) valid (got ' + cErr + ')');
const ar = E.applyAbility(cs, cAction2);
const cs1 = ar.state;
assert(cs1.pendingAttacks.length === 1, 'cannon queued');
assert(cs1.pendingAttacks[0].triggersOnFullmove === 2,
       'cannon triggersOnFullmove = 2 (got ' + cs1.pendingAttacks[0].triggersOnFullmove + ')');
assert(cs1.specialUsedThisTurn === true, 'specialUsedThisTurn flag set');
// Take a null-equivalent move to flip side. Simulate: white moves king.
const kingMoves = E.legalMoves(cs1).filter(m => m.from === E.sqOf(4,0));
assert(kingMoves.length > 0, 'white king has legal moves');
const wkMove = kingMoves[0];
const after2 = E.applyMove(cs1, wkMove).state;
assert(after2.side === E.BLACK, 'flipped to black');
assert(after2.pendingAttacks.length === 1, 'cannon still pending after white move');
// Black moves king (or any move). Black king at e8.
const bkMoves = E.legalMoves(after2).filter(m => m.from === E.sqOf(4,7));
assert(bkMoves.length > 0, 'black king has legal moves');
const bkMove = bkMoves[0];
const after3 = E.applyMove(after2, bkMove).state;
assert(after3.side === E.WHITE, 'flipped back to white');
assert(after3.pendingAttacks.length === 0,
       'cannon resolved on white turn-start (got ' + after3.pendingAttacks.length + ')');

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
