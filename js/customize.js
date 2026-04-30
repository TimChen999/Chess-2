"use strict";
// ============================================================================
// customize.js — piece editor scene
// ============================================================================
// Master-detail panel (IMPL-GODOT §11). Edits a *working copy* of the config
// — Save commits + persists, Cancel discards. Movement is exposed as toggle
// presets that compose into MovePattern arrays; the raw pattern records are
// not editable by the user.
// ============================================================================

(function (root) {

const E = root.Engine;
const C = root.Config;

const { KIND_LEAPER, KIND_RIDER,
        KIND_PAWN_PUSH, KIND_PAWN_DOUBLE, KIND_PAWN_CAPTURE,
        ABILITY_NONE, ABILITY_CANNON, ABILITY_LIGHTNING,
        EFFECT_NONE, EFFECT_BURN, EFFECT_FREEZE,
        sqOf } = E;

let working;     // deep clone of the active config (working copy)
let currentId;   // currently edited piece id
let listEl, paneEl;
let onSaveCallback;

// =============================================================================
// PUBLIC ENTRY
// =============================================================================

function init({ pieceList, editorPane, onSave }) {
  listEl = pieceList;
  paneEl = editorPane;
  onSaveCallback = onSave;
}

function show(activeConfig) {
  working = deepClone(activeConfig);
  currentId = Object.keys(working.pieces)[0];
  buildPieceList();
  renderEditor();
}

// =============================================================================
// LEFT PANEL — piece list
// =============================================================================

function buildPieceList() {
  listEl.innerHTML = '';
  for (const id of Object.keys(working.pieces)) {
    const def = working.pieces[id];
    const row = document.createElement('div');
    row.className = 'piece-row';
    if (id === currentId) row.classList.add('selected');
    row.innerHTML =
      `<span class="row-glyph">${def.glyph}</span>` +
      `<span class="row-name">${def.displayName}</span>`;
    row.addEventListener('click', () => { currentId = id; buildPieceList(); renderEditor(); });
    listEl.appendChild(row);
  }
}

// =============================================================================
// RIGHT PANEL — editor
// =============================================================================

function renderEditor() {
  paneEl.innerHTML = '';
  const def = working.pieces[currentId];

  // --- Identity ---
  const identity = section('Identity');
  identity.appendChild(textField('Name', def.displayName, v => def.displayName = v));
  identity.appendChild(textField('Glyph', def.glyph, v => def.glyph = v || def.glyph, { maxLength: 2 }));
  paneEl.appendChild(identity);

  // --- Stats ---
  const stats = section('Stats');
  stats.appendChild(numberField('HP',     def.hp,     1, 10, v => def.hp     = v));
  stats.appendChild(numberField('Damage', def.damage, 1,  5, v => def.damage = v));
  paneEl.appendChild(stats);

  // --- Movement ---
  const move = section('Movement');
  const toggles = inferToggles(def);
  const onToggleChange = () => {
    def.movePatterns = togglesToPatterns(toggles);
    renderEditor();   // re-render so the reachability preview updates
  };
  move.appendChild(checkField('Slides orthogonally',           toggles.ortho,
                              v => { toggles.ortho = v; onToggleChange(); }));
  move.appendChild(checkField('Slides diagonally',             toggles.diag,
                              v => { toggles.diag = v; onToggleChange(); }));
  move.appendChild(numberField('Range limit (0 = unlimited)',  toggles.range, 0, 7,
                               v => { toggles.range = v; onToggleChange(); }));
  move.appendChild(checkField('Knight leap',                   toggles.knight,
                              v => { toggles.knight = v; onToggleChange(); }));
  move.appendChild(checkField('One step any direction',        toggles.king,
                              v => { toggles.king = v; onToggleChange(); }));
  move.appendChild(checkField('Pawn-like (push + diag capture)', toggles.pawn,
                              v => { toggles.pawn = v; onToggleChange(); }));
  paneEl.appendChild(move);

  // --- Reachability preview ---
  const reach = section('Reachability preview (centered piece)');
  reach.appendChild(buildReachabilityGrid(def));
  paneEl.appendChild(reach);

  // --- On-hit effect ---
  const onhit = section('On-hit status effect');
  if (!def.onHit) def.onHit = { kind: EFFECT_NONE };
  onhit.appendChild(selectField('Kind', def.onHit.kind,
    [['None', EFFECT_NONE], ['Burn', EFFECT_BURN], ['Freeze', EFFECT_FREEZE]],
    v => { def.onHit.kind = v; renderEditor(); }));
  if (def.onHit.kind === EFFECT_BURN) {
    onhit.appendChild(numberField('Damage per turn', def.onHit.damagePerTurn || 1, 1, 5,
                                  v => def.onHit.damagePerTurn = v));
  }
  if (def.onHit.kind === EFFECT_BURN || def.onHit.kind === EFFECT_FREEZE) {
    onhit.appendChild(numberField('Duration (turns)', def.onHit.duration || 1, 1, 10,
                                  v => def.onHit.duration = v));
  }
  paneEl.appendChild(onhit);

  // --- Special ability ---
  const ab = section('Special ability');
  if (!def.special) def.special = { kind: ABILITY_NONE };
  ab.appendChild(selectField('Kind', def.special.kind,
    [['None', ABILITY_NONE], ['Cannon (delayed AOE)', ABILITY_CANNON],
     ['Lightning (instant)', ABILITY_LIGHTNING]],
    v => {
      def.special.kind = v;
      // Provide sane defaults when switching to non-None.
      if (v !== ABILITY_NONE) {
        def.special.damage         = def.special.damage         || 1;
        def.special.cooldownTurns  = def.special.cooldownTurns  || 3;
        def.special.maxCharges     = def.special.maxCharges     || 1;
        def.special.initialCharges = def.special.initialCharges || 0;
      }
      renderEditor();
    }));
  if (def.special.kind !== ABILITY_NONE) {
    ab.appendChild(numberField('Damage',           def.special.damage,         1, 5, v => def.special.damage         = v));
    ab.appendChild(numberField('Cooldown (turns)', def.special.cooldownTurns,  1, 10, v => def.special.cooldownTurns = v));
    ab.appendChild(numberField('Max charges',      def.special.maxCharges,     1, 5, v => {
      def.special.maxCharges = v;
      if (def.special.initialCharges > v) { def.special.initialCharges = v; renderEditor(); }
    }));
    ab.appendChild(numberField('Initial charges',  def.special.initialCharges, 0, def.special.maxCharges,
                               v => def.special.initialCharges = v));
    const summary = document.createElement('div');
    summary.className = 'summary';
    summary.textContent = def.special.kind === ABILITY_CANNON
      ? '5-square plus AOE, lands one full turn later. Cannot target enemy starting zone.'
      : 'Single enemy target, instant. Cannot target the royal piece (king).';
    ab.appendChild(summary);
  }
  paneEl.appendChild(ab);

  // --- Footer ---
  const footer = document.createElement('div');
  footer.className = 'editor-footer';
  footer.appendChild(buttonField('Reset to default', () => {
    const fresh = C.defaultConfig();
    if (fresh.pieces[currentId]) {
      working.pieces[currentId] = deepClone(fresh.pieces[currentId]);
      renderEditor();
    }
  }));
  footer.appendChild(buttonField('Reset ALL pieces', () => {
    if (confirm('Reset all piece definitions to defaults?')) {
      working = C.defaultConfig();
      currentId = Object.keys(working.pieces)[0];
      buildPieceList();
      renderEditor();
    }
  }));
  footer.appendChild(buttonField('Save & back', () => onSaveCallback(working), 'primary'));
  footer.appendChild(buttonField('Cancel', () => onSaveCallback(null)));
  paneEl.appendChild(footer);
}

// =============================================================================
// FORM HELPERS
// =============================================================================

function section(title) {
  const s = document.createElement('div');
  s.className = 'editor-section';
  const h = document.createElement('h3');
  h.textContent = title;
  s.appendChild(h);
  return s;
}

function textField(label, value, onChange, opts = {}) {
  const wrap = document.createElement('label');
  wrap.className = 'field';
  wrap.textContent = label;
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.value = value;
  if (opts.maxLength) inp.maxLength = opts.maxLength;
  inp.addEventListener('input', () => onChange(inp.value));
  wrap.appendChild(inp);
  return wrap;
}

function numberField(label, value, min, max, onChange) {
  const wrap = document.createElement('label');
  wrap.className = 'field';
  wrap.textContent = label;
  const inp = document.createElement('input');
  inp.type = 'number';
  inp.value = value;
  inp.min = min;
  inp.max = max;
  inp.addEventListener('change', () => {
    let v = parseInt(inp.value, 10);
    if (isNaN(v)) v = min;
    if (v < min) v = min;
    if (v > max) v = max;
    inp.value = v;
    onChange(v);
  });
  wrap.appendChild(inp);
  return wrap;
}

function checkField(label, value, onChange) {
  const wrap = document.createElement('label');
  wrap.className = 'field field-check';
  const inp = document.createElement('input');
  inp.type = 'checkbox';
  inp.checked = !!value;
  inp.addEventListener('change', () => onChange(inp.checked));
  wrap.appendChild(inp);
  const span = document.createElement('span');
  span.textContent = label;
  wrap.appendChild(span);
  return wrap;
}

function selectField(label, value, options, onChange) {
  const wrap = document.createElement('label');
  wrap.className = 'field';
  wrap.textContent = label;
  const sel = document.createElement('select');
  for (const [text, val] of options) {
    const opt = document.createElement('option');
    opt.textContent = text;
    opt.value = String(val);
    if (val === value) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.addEventListener('change', () => onChange(parseInt(sel.value, 10)));
  wrap.appendChild(sel);
  return wrap;
}

function buttonField(label, onClick, variant) {
  const btn = document.createElement('button');
  btn.textContent = label;
  btn.className = 'editor-btn' + (variant ? ' ' + variant : '');
  btn.addEventListener('click', onClick);
  return btn;
}

// =============================================================================
// REACHABILITY PREVIEW
// -----------------------------------------------------------------------------
// 8×8 grid with the editing piece on rank 3 file 3. We synthesize a tiny
// state with just this piece, and run pseudoLegalMoves to get reachable
// squares. Captures are highlighted differently (we plant a dummy enemy on
// every empty square in turn? — no, simpler: show all empty-target moves
// with one tint, then flip every other square to "would capture" by adding
// a dummy enemy and re-running). Actually, simpler still: just show every
// square the piece's patterns can REACH, regardless of capture flag.
// =============================================================================

function buildReachabilityGrid(def) {
  const grid = document.createElement('div');
  grid.className = 'reach-grid';

  const center = sqOf(3, 3);

  // Two passes: (a) empty board (shows non-capture reach), (b) dummy enemy
  // on every square (shows capture reach for capture-only / pawn diagonals).
  const reachA = previewReach(def, center, /*placeEnemies=*/false);
  const reachB = previewReach(def, center, /*placeEnemies=*/true);

  for (let r = 7; r >= 0; r--) {
    for (let f = 0; f < 8; f++) {
      const sq = sqOf(f, r);
      const cell = document.createElement('div');
      cell.className = 'reach-cell ' + ((f + r) % 2 === 0 ? 'dark' : 'light');
      if (sq === center) {
        cell.classList.add('center');
        cell.textContent = def.glyph;
      } else if (reachA.has(sq)) {
        cell.classList.add('reach-move');
      } else if (reachB.has(sq)) {
        cell.classList.add('reach-cap');
      }
      grid.appendChild(cell);
    }
  }
  return grid;
}

function previewReach(def, fromSq, placeEnemies) {
  // Build a minimal config containing only this piece def (plus a dummy
  // enemy if requested).
  const cfg = { pieces: { [def.id]: def }, initialSetup: [] };
  if (placeEnemies) {
    // Dummy enemy is a 1-HP, 1-damage king-leaper marker. We never run the
    // engine over its turn, just need it to exist on squares for the
    // captures to register.
    cfg.pieces['__dummy'] = {
      id: '__dummy', displayName: 'dummy', glyph: '?',
      hp: 99, damage: 1, royal: false, canCastle: false,
      movePatterns: [], onHit: { kind: EFFECT_NONE },
      special: { kind: ABILITY_NONE },
      promotesAt: -1, promotesTo: [],
    };
  }
  const board = new Array(64).fill(null);
  // Color WHITE for the editing piece — pawn-like patterns will show
  // forward as "up the board" (rank 7 direction).
  board[fromSq] = makePieceLite(def.id, E.WHITE, def);
  if (placeEnemies) {
    for (let i = 0; i < 64; i++) {
      if (i === fromSq) continue;
      board[i] = makePieceLite('__dummy', E.BLACK, cfg.pieces['__dummy']);
    }
  }
  const state = {
    config: cfg, board, side: E.WHITE, ep: -1, halfmove: 0, fullmove: 1,
    pendingAttacks: [], specialUsedThisTurn: false,
    initialPiecesByColor: { 0: new Set(), 1: new Set() },
  };
  const set = new Set();
  for (const m of E.pseudoLegalMoves(state, E.WHITE)) {
    if (m.from === fromSq) set.add(m.to);
  }
  return set;
}

// Lightweight piece factory (engine.makePiece isn't exported; this is fine).
function makePieceLite(id, color, def) {
  return {
    defId: id, color,
    hp: def.hp || 1,
    activeEffects: [],
    specialCharges: 0, specialRecharge: 0,
    hasMoved: false,
  };
}

// =============================================================================
// TOGGLE ↔ PATTERN MAPPING
// -----------------------------------------------------------------------------
// The customization UI exposes movement as preset toggles (§5.3). Round-tripping
// requires inferring which toggles are on from a piece's existing patterns;
// custom patterns that don't match any preset get dropped on first save —
// acceptable since the UI doesn't expose raw editing.
// =============================================================================

function inferToggles(def) {
  const t = { ortho: false, diag: false, range: 0,
              knight: false, king: false, pawn: false };
  for (const pat of def.movePatterns) {
    if (pat.kind === KIND_RIDER) {
      if (offsetsMatch(pat.offsets, C.ORTHO))      { t.ortho = true; t.range = pat.maxRange; }
      else if (offsetsMatch(pat.offsets, C.DIAG))  { t.diag  = true; t.range = pat.maxRange; }
    } else if (pat.kind === KIND_LEAPER) {
      if (offsetsMatch(pat.offsets, C.KNIGHT_OFFS))     t.knight = true;
      else if (offsetsMatch(pat.offsets, C.KING_OFFS))  t.king   = true;
    } else if (pat.kind === KIND_PAWN_PUSH ||
               pat.kind === KIND_PAWN_DOUBLE ||
               pat.kind === KIND_PAWN_CAPTURE) {
      t.pawn = true;
    }
  }
  return t;
}

function togglesToPatterns(t) {
  const out = [];
  if (t.ortho) out.push(C.pat(KIND_RIDER, { offsets: C.ORTHO, maxRange: t.range }));
  if (t.diag)  out.push(C.pat(KIND_RIDER, { offsets: C.DIAG,  maxRange: t.range }));
  if (t.knight) out.push(C.pat(KIND_LEAPER, { offsets: C.KNIGHT_OFFS }));
  if (t.king)   out.push(C.pat(KIND_LEAPER, { offsets: C.KING_OFFS }));
  if (t.pawn) {
    out.push(C.pat(KIND_PAWN_PUSH));
    out.push(C.pat(KIND_PAWN_DOUBLE));
    out.push(C.pat(KIND_PAWN_CAPTURE));
  }
  return out;
}

function offsetsMatch(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  const norm = arr => arr.map(o => o[0] + ',' + o[1]).sort();
  const an = norm(a), bn = norm(b);
  for (let i = 0; i < an.length; i++) if (an[i] !== bn[i]) return false;
  return true;
}

// =============================================================================

function deepClone(o) { return JSON.parse(JSON.stringify(o)); }

root.Customize = { init, show };

})(typeof window !== 'undefined' ? window : globalThis);
