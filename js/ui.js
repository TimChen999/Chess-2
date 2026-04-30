"use strict";
// ============================================================================
// ui.js — game scene: board rendering, click flow, ability targeting
// ============================================================================
// Owns no rules logic. Reads from Engine, calls Engine for moves and
// abilities, and renders. The three click-flow modes (§7.9 of IMPL-GODOT) are
// implemented with a single `mode` variable plus per-mode selection state.
// ============================================================================

(function (root) {

const E = root.Engine;
const { WHITE, BLACK,
        ABILITY_NONE, ABILITY_CANNON, ABILITY_LIGHTNING,
        EFFECT_BURN, EFFECT_FREEZE,
        sqOf, fileOf, rankOf } = E;

// ---------------------------------------------------------------------------
// Module state — kept here so the small helper functions can talk to each
// other without threading every variable through their signatures.
// ---------------------------------------------------------------------------

let state, lastStatus, config;
let mode = 'select_piece';   // 'select_piece' | 'select_move' | 'select_ability'
let selected = -1;            // for select_move: square of selected piece
let legalForSelected = [];    // legal moves from `selected`
let abilityCtx = null;        // for select_ability: { sourceSq, kind, targets[] }
let pendingPromo = null;      // matched promotion moves awaiting picker choice

// DOM references, set in init().
let boardEl, statusEl, abilityBarEl, promoEl, endOverlayEl, hoverPreview;

// Hover highlight for cannon plus-area preview.
let hoverTargetSq = -1;

// =============================================================================
// PUBLIC ENTRY POINTS
// =============================================================================

function init({ board, status, abilityBar, promo, endOverlay, gameConfig }) {
  boardEl       = board;
  statusEl      = status;
  abilityBarEl  = abilityBar;
  promoEl       = promo;
  endOverlayEl  = endOverlay;
  config        = gameConfig;

  state = E.newGame(config);
  lastStatus = E.gameStatus(state);
  mode = 'select_piece';
  selected = -1;
  legalForSelected = [];
  abilityCtx = null;
  pendingPromo = null;
  hoverTargetSq = -1;

  // The first applyMove triggers turn-start ticks for the new side. We need
  // the equivalent at the START of white's first turn — there is nothing to
  // tick (no pending cannons, no effects, no recharges yet) so newGame's
  // raw output is already correct.

  buildBoard();
  render();
}

function newGame() { init({ board: boardEl, status: statusEl,
                             abilityBar: abilityBarEl, promo: promoEl,
                             endOverlay: endOverlayEl, gameConfig: config }); }

// =============================================================================
// BOARD CONSTRUCTION (one-time DOM build; render() updates contents only)
// =============================================================================

function buildBoard() {
  boardEl.innerHTML = '';
  // Render rank 7 at the top so White sits at the bottom of the screen.
  for (let r = 7; r >= 0; r--) {
    for (let f = 0; f < 8; f++) {
      const sq = sqOf(f, r);
      const cell = document.createElement('div');
      cell.className = 'sq ' + ((f + r) % 2 === 0 ? 'dark' : 'light');
      cell.dataset.sq = sq;
      cell.addEventListener('click', () => onSquareClick(sq));
      cell.addEventListener('mouseenter', () => onSquareHover(sq));
      cell.addEventListener('mouseleave', () => onSquareHover(-1));
      boardEl.appendChild(cell);
    }
  }
}

// =============================================================================
// RENDER — pure projection of (state, lastStatus, mode, selected) onto DOM.
// Cheap enough at 64 squares to call after every interaction.
// =============================================================================

function render() {
  // Build per-square overlays.
  // - selected highlight on `selected`
  // - legal-target dots for legal moves from `selected`
  // - ability target overlay when in select_ability mode
  // - pending cannon plus areas (always visible)
  // - in-check king highlight

  // Compute "pending cannon target squares for each owner" — a square is
  // 'cannon-incoming' if any pending cannon has it in targetSquares.
  const cannonTargets = new Set();
  for (const pa of state.pendingAttacks) {
    if (pa.kind !== ABILITY_CANNON) continue;
    for (const sq of pa.targetSquares) cannonTargets.add(sq);
  }

  // Hover preview for cannon targeting.
  let hoverPlus = null;
  if (mode === 'select_ability' && abilityCtx.kind === ABILITY_CANNON
      && hoverTargetSq >= 0) {
    const found = abilityCtx.targets.find(t => t.sq === hoverTargetSq);
    if (found) hoverPlus = new Set(found.plus);
  }

  for (let r = 7; r >= 0; r--) {
    for (let f = 0; f < 8; f++) {
      const sq = sqOf(f, r);
      const cell = boardEl.children[(7 - r) * 8 + f];
      const p = state.board[sq];

      cell.className = 'sq ' + ((f + r) % 2 === 0 ? 'dark' : 'light');
      cell.innerHTML = '';

      // Pending cannon overlay (faded plus)
      if (cannonTargets.has(sq)) cell.classList.add('cannon-pending');
      // Hover plus preview
      if (hoverPlus && hoverPlus.has(sq)) cell.classList.add('cannon-hover');

      // Selected piece highlight
      if (selected === sq && mode === 'select_move') cell.classList.add('selected');

      // Ability source highlight
      if (mode === 'select_ability' && abilityCtx.sourceSq === sq) {
        cell.classList.add('ability-source');
      }

      // Legal-target overlay
      if (mode === 'select_move') {
        const m = legalForSelected.find(x => x.to === sq);
        if (m) cell.classList.add(m.capture ? 'legal-cap' : 'legal-move');
      }

      // Ability target overlay
      if (mode === 'select_ability') {
        if (abilityCtx.targets.find(t => t.sq === sq)) {
          cell.classList.add(abilityCtx.kind === ABILITY_LIGHTNING
                              ? 'ability-target-lightning'
                              : 'ability-target-cannon');
        }
      }

      // Check king highlight (HP-aware: the HP <= damage condition)
      if ((lastStatus.kind === 'check' || lastStatus.kind === 'checkmate')
          && lastStatus.royalSq === sq) {
        cell.classList.add('in-check');
      }

      if (p) renderPiece(cell, p, sq);
    }
  }

  // Status text
  const sideName = state.side === WHITE ? 'White' : 'Black';
  switch (lastStatus.kind) {
    case 'checkmate':
      statusEl.textContent = `Checkmate. ${lastStatus.winner === WHITE ? 'White' : 'Black'} wins.`;
      showEndOverlay(`Checkmate — ${lastStatus.winner === WHITE ? 'White' : 'Black'} wins`);
      break;
    case 'stalemate':
      statusEl.textContent = 'Stalemate. Draw.';
      showEndOverlay('Stalemate — Draw');
      break;
    case 'draw50':
      statusEl.textContent = '50-move rule. Draw.';
      showEndOverlay('50-move rule — Draw');
      break;
    case 'check':
      statusEl.textContent = `${sideName} to move — in check.`;
      hideEndOverlay();
      break;
    default:
      statusEl.textContent = `${sideName} to move.`;
      hideEndOverlay();
  }

  renderAbilityBar();
}

// Render one piece into a square cell. Includes HP bar, status badges,
// and ability charge badge.
function renderPiece(cell, p, sq) {
  const def = config.pieces[p.defId];
  const wrap = document.createElement('div');
  wrap.className = 'piece ' + (p.color === WHITE ? 'piece-w' : 'piece-b');

  const glyph = document.createElement('div');
  glyph.className = 'glyph';
  glyph.textContent = def.glyph;
  if (E.isFrozen(p)) glyph.classList.add('frozen');
  wrap.appendChild(glyph);

  // HP bar (always visible — HP drives the whole game)
  const hpWrap = document.createElement('div');
  hpWrap.className = 'hp';
  hpWrap.textContent = p.hp + '/' + def.hp;
  if (p.hp <= 1) hpWrap.classList.add('hp-low');
  wrap.appendChild(hpWrap);

  // Effect badges (top-right)
  const fx = document.createElement('div');
  fx.className = 'fx';
  for (const e of p.activeEffects) {
    if (e.turnsRemaining <= 0) continue;
    const b = document.createElement('span');
    if (e.kind === EFFECT_BURN) {
      b.className = 'fx-burn';
      b.textContent = '🔥' + e.turnsRemaining;
    } else if (e.kind === EFFECT_FREEZE) {
      b.className = 'fx-freeze';
      b.textContent = '❄' + e.turnsRemaining;
    }
    fx.appendChild(b);
  }
  wrap.appendChild(fx);

  // Ability charge badge (bottom-right) — visible if def has an ability AND
  // piece has charges OR is recharging.
  if (def.special && def.special.kind !== ABILITY_NONE) {
    const ab = document.createElement('div');
    ab.className = 'charge';
    const icon = def.special.kind === ABILITY_CANNON ? '◎' : '⚡';
    if (p.specialCharges > 0) {
      ab.textContent = icon + '×' + p.specialCharges;
      ab.classList.add('charge-ready');
    } else {
      ab.textContent = icon + '·' + p.specialRecharge;
      ab.classList.add('charge-cool');
    }
    wrap.appendChild(ab);
  }

  cell.appendChild(wrap);
}

// =============================================================================
// ABILITY BAR — buttons to arm an ability, one per side-to-move piece that
// has charges available AND no ability has been used this turn.
// =============================================================================

function renderAbilityBar() {
  abilityBarEl.innerHTML = '';
  if (state.specialUsedThisTurn) {
    const span = document.createElement('span');
    span.className = 'ability-note';
    span.textContent = 'Ability used this turn';
    abilityBarEl.appendChild(span);
    return;
  }
  let found = 0;
  for (let sq = 0; sq < 64; sq++) {
    const p = state.board[sq];
    if (!p || p.color !== state.side) continue;
    const def = config.pieces[p.defId];
    if (!def.special || def.special.kind === ABILITY_NONE) continue;
    if (p.specialCharges <= 0) continue;
    if (E.isFrozen(p)) continue;
    found++;

    const btn = document.createElement('button');
    btn.className = 'ability-btn';
    if (mode === 'select_ability' && abilityCtx.sourceSq === sq) {
      btn.classList.add('ability-btn-active');
    }
    const kindName = def.special.kind === ABILITY_CANNON ? 'Cannon' : 'Lightning';
    btn.textContent = `${def.glyph} ${kindName} (${p.specialCharges})`;
    btn.title = describeAbility(def.special);
    btn.addEventListener('click', () => onAbilityButtonClick(sq));
    abilityBarEl.appendChild(btn);
  }
  if (!found) {
    const span = document.createElement('span');
    span.className = 'ability-note';
    span.textContent = 'No abilities ready';
    abilityBarEl.appendChild(span);
  }
}

function describeAbility(spec) {
  if (spec.kind === ABILITY_CANNON) {
    return `Plus AOE, ${spec.damage} dmg, lands next turn. ` +
           `Cooldown ${spec.cooldownTurns}, max ${spec.maxCharges} charges.`;
  } else if (spec.kind === ABILITY_LIGHTNING) {
    return `Single target, ${spec.damage} dmg, instant. Cannot target king. ` +
           `Cooldown ${spec.cooldownTurns}, max ${spec.maxCharges} charges.`;
  }
  return '';
}

// =============================================================================
// CLICK FLOW
// =============================================================================

function onSquareClick(sq) {
  if (pendingPromo) return;
  if (gameOver()) return;

  if (mode === 'select_ability') {
    handleAbilityClick(sq);
    return;
  }

  // Default + select_move handling — same logic as classical chess (CP #5),
  // upgraded to also recognize "click on my own piece to reselect".
  if (mode === 'select_move' && selected !== -1) {
    const matches = legalForSelected.filter(m => m.to === sq);
    if (matches.length === 1 && !matches[0].promo) {
      playMove(matches[0]);
      return;
    }
    if (matches.length > 0 && matches[0].promo) {
      pendingPromo = matches;
      showPromoPicker(matches);
      return;
    }
  }

  // Otherwise: try to select one of my own pieces.
  const p = state.board[sq];
  if (p && p.color === state.side && !E.isFrozen(p)) {
    selected = sq;
    legalForSelected = lastStatus.moves.filter(m => m.from === sq);
    mode = legalForSelected.length > 0 ? 'select_move' : 'select_piece';
  } else {
    selected = -1;
    legalForSelected = [];
    mode = 'select_piece';
  }
  render();
}

function onAbilityButtonClick(sourceSq) {
  // Toggle: if already armed for this source, disarm.
  if (mode === 'select_ability' && abilityCtx.sourceSq === sourceSq) {
    cancelAbility();
    return;
  }
  const p = state.board[sourceSq];
  const def = config.pieces[p.defId];
  abilityCtx = {
    sourceSq,
    kind: def.special.kind,
    targets: E.listAbilityTargets(state, sourceSq),
  };
  mode = 'select_ability';
  selected = -1;
  legalForSelected = [];
  render();
}

function handleAbilityClick(sq) {
  const target = abilityCtx.targets.find(t => t.sq === sq);
  if (!target) {
    // Click off-target → cancel ability mode (don't fire, don't deselect on
    // first click — let the user see what's wrong).
    cancelAbility();
    return;
  }
  // Fire it.
  try {
    const r = E.applyAbility(state, {
      kind: abilityCtx.kind,
      sourceSq: abilityCtx.sourceSq,
      targetSq: sq,
    });
    state = r.state;
  } catch (e) {
    console.warn('ability fire failed:', e);
    cancelAbility();
    return;
  }
  // Ability does not flip side — recompute status for the SAME side, since
  // listing legal moves & checking mate after an ability is still meaningful
  // (lightning may have killed a piece and changed legality).
  lastStatus = E.gameStatus(state);
  mode = 'select_piece';
  abilityCtx = null;
  selected = -1;
  legalForSelected = [];
  render();
}

function cancelAbility() {
  mode = 'select_piece';
  abilityCtx = null;
  selected = -1;
  legalForSelected = [];
  render();
}

function onSquareHover(sq) {
  if (mode !== 'select_ability') {
    if (hoverTargetSq !== -1) { hoverTargetSq = -1; render(); }
    return;
  }
  if (hoverTargetSq === sq) return;
  hoverTargetSq = sq;
  render();
}

function gameOver() {
  return lastStatus.kind === 'checkmate'
      || lastStatus.kind === 'stalemate'
      || lastStatus.kind === 'draw50';
}

// =============================================================================
// MOVE EXECUTION
// =============================================================================

function playMove(m) {
  const r = E.applyMove(state, m);
  state = r.state;
  selected = -1;
  legalForSelected = [];
  mode = 'select_piece';
  abilityCtx = null;
  hoverTargetSq = -1;
  // Recompute status for the new side-to-move.
  lastStatus = E.gameStatus(state);
  render();
}

// =============================================================================
// PROMOTION PICKER
// =============================================================================

function showPromoPicker(matches) {
  promoEl.innerHTML = '';
  promoEl.style.display = 'flex';
  for (const m of matches) {
    const btn = document.createElement('button');
    const def = config.pieces[m.promo];
    btn.className = 'promo-btn';
    btn.textContent = def.glyph;
    btn.title = def.displayName;
    btn.addEventListener('click', () => {
      pendingPromo = null;
      promoEl.style.display = 'none';
      playMove(m);
    });
    promoEl.appendChild(btn);
  }
}

// =============================================================================
// END-GAME OVERLAY
// =============================================================================

function showEndOverlay(text) {
  endOverlayEl.textContent = text;
  endOverlayEl.style.display = 'flex';
}
function hideEndOverlay() {
  endOverlayEl.style.display = 'none';
}

// =============================================================================

root.UI = { init, newGame };

})(typeof window !== 'undefined' ? window : globalThis);
