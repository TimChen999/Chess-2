"use strict";
// ============================================================================
// config.js — default Chess² configuration
// ============================================================================
// Defines the six standard piece types with HP / damage / patterns / on-hit
// effects / abilities, plus the standard initial setup. Loaded on first run;
// the customization screen mutates a working copy and persists to
// localStorage.
//
// Numeric defaults follow IMPL-GODOT §10.6 ("differentiated") and §6/§7 for
// burn/freeze/abilities. Tuned for an interesting opening and a tempo
// structure where the king has 3 HP — two free hits before classical-style
// check kicks in.
// ============================================================================

(function (root) {

const E = root.Engine;
const { WHITE, BLACK,
        KIND_LEAPER, KIND_RIDER, KIND_PAWN_PUSH, KIND_PAWN_DOUBLE,
        KIND_PAWN_CAPTURE,
        ABILITY_NONE, ABILITY_CANNON, ABILITY_LIGHTNING,
        EFFECT_NONE, EFFECT_BURN, EFFECT_FREEZE } = E;

// Direction vectors used by RIDER and king/queen leapers.
const ORTHO = [[1,0],[-1,0],[0,1],[0,-1]];
const DIAG  = [[1,1],[1,-1],[-1,1],[-1,-1]];
const KING_OFFS   = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];
const KNIGHT_OFFS = [[1,2],[2,1],[-1,2],[-2,1],[1,-2],[2,-1],[-1,-2],[-2,-1]];

function pat(kind, opts = {}) {
  return {
    kind,
    offsets:     opts.offsets || [],
    maxRange:    opts.maxRange || 0,
    captureOnly: !!opts.captureOnly,
    moveOnly:    !!opts.moveOnly,
  };
}

function defaultConfig() {
  const pieces = {
    king: {
      id: 'king', displayName: 'King', glyph: '♚',
      hp: 3, damage: 1, royal: true, canCastle: true,
      movePatterns: [ pat(KIND_LEAPER, { offsets: KING_OFFS }) ],
      onHit:   { kind: EFFECT_NONE },
      special: { kind: ABILITY_NONE },
      promotesAt: -1, promotesTo: [],
    },
    queen: {
      id: 'queen', displayName: 'Queen', glyph: '♛',
      hp: 5, damage: 2, royal: false, canCastle: false,
      movePatterns: [
        pat(KIND_RIDER, { offsets: ORTHO }),
        pat(KIND_RIDER, { offsets: DIAG  }),
      ],
      onHit:   { kind: EFFECT_NONE },
      special: { kind: ABILITY_CANNON,
                 damage: 2, cooldownTurns: 4,
                 maxCharges: 1, initialCharges: 0 },
      promotesAt: -1, promotesTo: [],
    },
    rook: {
      id: 'rook', displayName: 'Rook', glyph: '♜',
      hp: 3, damage: 1, royal: false, canCastle: false,
      movePatterns: [ pat(KIND_RIDER, { offsets: ORTHO }) ],
      // Rook attacks ignite — the target burns for 1 dmg/turn × 2 turns.
      onHit:   { kind: EFFECT_BURN, damagePerTurn: 1, duration: 2 },
      special: { kind: ABILITY_NONE },
      promotesAt: -1, promotesTo: [],
    },
    bishop: {
      id: 'bishop', displayName: 'Bishop', glyph: '♝',
      hp: 2, damage: 1, royal: false, canCastle: false,
      movePatterns: [ pat(KIND_RIDER, { offsets: DIAG }) ],
      onHit:   { kind: EFFECT_NONE },
      special: { kind: ABILITY_LIGHTNING,
                 damage: 1, cooldownTurns: 3,
                 maxCharges: 1, initialCharges: 1 },
      promotesAt: -1, promotesTo: [],
    },
    knight: {
      id: 'knight', displayName: 'Knight', glyph: '♞',
      hp: 2, damage: 1, royal: false, canCastle: false,
      movePatterns: [ pat(KIND_LEAPER, { offsets: KNIGHT_OFFS }) ],
      // Knight attacks freeze — target skips its next turn.
      onHit:   { kind: EFFECT_FREEZE, damagePerTurn: 0, duration: 1 },
      special: { kind: ABILITY_NONE },
      promotesAt: -1, promotesTo: [],
    },
    pawn: {
      id: 'pawn', displayName: 'Pawn', glyph: '♟',
      hp: 1, damage: 1, royal: false, canCastle: false,
      movePatterns: [
        pat(KIND_PAWN_PUSH),
        pat(KIND_PAWN_DOUBLE),
        pat(KIND_PAWN_CAPTURE),
      ],
      onHit:   { kind: EFFECT_NONE },
      special: { kind: ABILITY_NONE },
      promotesAt: -1, promotesTo: ['queen','rook','bishop','knight'],
    },
  };

  // Standard opening setup. Index 0 = a1 (white queenside rook).
  const back = ['rook','knight','bishop','queen','king','bishop','knight','rook'];
  const initialSetup = new Array(64).fill(null);
  for (let f = 0; f < 8; f++) {
    initialSetup[f]      = { id: back[f], color: WHITE };
    initialSetup[8 + f]  = { id: 'pawn',  color: WHITE };
    initialSetup[48 + f] = { id: 'pawn',  color: BLACK };
    initialSetup[56 + f] = { id: back[f], color: BLACK };
  }

  return { pieces, initialSetup };
}

// ---------------------------------------------------------------------------
// Persistence (localStorage)
// ---------------------------------------------------------------------------
// We round-trip the config through JSON. PieceDefs are plain data; Set/Map
// don't appear in config (only in runtime state, which is not persisted).

const STORAGE_KEY = 'chess2.config.v1';

function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultConfig();
    const parsed = JSON.parse(raw);
    // Defensive merge: any missing piece falls back to default. This keeps
    // old saves working when the schema gains a new piece type.
    const def = defaultConfig();
    for (const id in def.pieces) {
      if (!parsed.pieces[id]) parsed.pieces[id] = def.pieces[id];
    }
    if (!parsed.initialSetup || parsed.initialSetup.length !== 64) {
      parsed.initialSetup = def.initialSetup;
    }
    return parsed;
  } catch (e) {
    console.warn('config: load failed, using defaults', e);
    return defaultConfig();
  }
}

function saveConfig(cfg) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg)); }
  catch (e) { console.warn('config: save failed', e); }
}

function resetConfig() {
  try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
}

root.Config = {
  defaultConfig, loadConfig, saveConfig, resetConfig,
  ORTHO, DIAG, KING_OFFS, KNIGHT_OFFS, pat,
};

})(typeof window !== 'undefined' ? window : globalThis);
