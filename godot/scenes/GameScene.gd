## GameScene — board rendering, click flow, ability targeting.
##
## Owns no rules logic.  Reads from Engine, calls Engine for moves and
## abilities, and renders.  Three click-flow modes (IMPL-GODOT §7.9):
##   "select_piece"   default; click your own piece to select it
##   "select_move"    a piece is selected; click destination to play
##   "select_ability" ability armed; click target square to fire
extends Control

signal back_to_menu

const SQ_SIZE := 72
const LIGHT_COLOR := Color("#ecd9b8")
const DARK_COLOR  := Color("#a97c5a")
const SELECTED_TINT     := Color(1, 0.85, 0.3)
const CHECK_TINT        := Color(0.85, 0.4, 0.4)
const ABILITY_SRC_TINT  := Color(0.4, 0.75, 0.45)
const ABILITY_CANNON_TINT    := Color(1, 0.6, 0.3, 0.85)
const ABILITY_LIGHT_TINT     := Color(0.5, 0.7, 1, 0.85)
const CANNON_PENDING_TINT    := Color(1, 0.6, 0.3, 0.4)
const CANNON_HOVER_TINT      := Color(1, 0.6, 0.3, 0.7)

# ---------- runtime state ----------
var state: GameState
var last_status: Dictionary = {}
var mode := "select_piece"
var selected := -1
var legal_for_selected: Array = []
var ability_ctx: Dictionary = {}     ## { kind, targets } — set when ability armed
var pending_promo: Array = []
var hover_target_sq := -1

# ---------- UI refs ----------
var status_label: Label
var board_grid: GridContainer
var anim_overlay: Control            ## above board_grid; hosts floating sprites
var squares: Array = []              ## [Button * 64]
var ability_bar: HBoxContainer
var end_label: Label
var promo_panel: PanelContainer
var promo_buttons: HBoxContainer

# ---------- animation timing ----------
const ANIM_MOVE_DURATION   := 0.26
const ANIM_DAMAGE_DURATION := 0.16
const ANIM_KILL_DURATION   := 0.24
const ANIM_HIT_DURATION    := 0.4
## Attack timing — anticipation pull-back, lunge to overshoot, settle into
## target square. Damage/push/kill effects are delayed to land at T_IMPACT.
const T_ANTICIPATE := 0.07
const T_LUNGE      := 0.15
const T_SETTLE     := 0.07
const T_IMPACT     := 0.20
var _animating: bool = false

func _ready() -> void:
    _build_ui()
    _new_game()

func _new_game() -> void:
    state = Rules.new_game(GameSettings.active_config)
    last_status = Rules.game_status(state)
    mode = "select_piece"
    selected = -1
    legal_for_selected = []
    ability_ctx = {}
    pending_promo = []
    hover_target_sq = -1
    _render()

# ============================================================================
# UI CONSTRUCTION
# ============================================================================

func _build_ui() -> void:
    var root := VBoxContainer.new()
    root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_theme_constant_override("separation", 12)
    root.alignment = BoxContainer.ALIGNMENT_CENTER
    add_child(root)

    # --- Header ---
    var header := HBoxContainer.new()
    header.custom_minimum_size = Vector2(SQ_SIZE * 8 + 6, 32)
    header.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
    header.add_theme_constant_override("separation", 12)
    root.add_child(header)

    var btn_back := Button.new()
    btn_back.text = "← Menu"
    btn_back.pressed.connect(func(): back_to_menu.emit())
    header.add_child(btn_back)

    status_label = Label.new()
    status_label.text = ""
    status_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    status_label.add_theme_font_size_override("font_size", 18)
    header.add_child(status_label)

    var btn_new := Button.new()
    btn_new.text = "New game"
    btn_new.pressed.connect(_new_game)
    header.add_child(btn_new)

    # --- Board grid + animation overlay ---
    var board_container := CenterContainer.new()
    root.add_child(board_container)

    ## board_holder is a Control sized exactly to the 8x8 grid. Two
    ## children, both anchored to fill: the GridContainer with the static
    ## board, and a transparent overlay that hosts floating animation
    ## sprites (Labels) above the board. anim_overlay ignores mouse so
    ## clicks still hit the squares underneath.
    var board_holder := Control.new()
    board_holder.custom_minimum_size = Vector2(SQ_SIZE * 8, SQ_SIZE * 8)
    board_container.add_child(board_holder)

    board_grid = GridContainer.new()
    board_grid.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    board_grid.columns = 8
    board_grid.add_theme_constant_override("h_separation", 0)
    board_grid.add_theme_constant_override("v_separation", 0)
    board_holder.add_child(board_grid)

    anim_overlay = Control.new()
    anim_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    anim_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
    board_holder.add_child(anim_overlay)

    squares.resize(64)
    ## Render rank 7 at top so White sits at the bottom on screen.
    for r in range(7, -1, -1):
        for f in 8:
            var sq := r * 8 + f
            var btn := _make_square(sq)
            board_grid.add_child(btn)
            squares[sq] = btn

    # --- Ability bar ---
    ability_bar = HBoxContainer.new()
    ability_bar.alignment = BoxContainer.ALIGNMENT_CENTER
    ability_bar.add_theme_constant_override("separation", 8)
    ability_bar.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
    root.add_child(ability_bar)

    # --- End-game label ---
    end_label = Label.new()
    end_label.add_theme_font_size_override("font_size", 18)
    end_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    end_label.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
    end_label.modulate = Color(1, 0.95, 0.8)
    end_label.visible = false
    root.add_child(end_label)

    # --- Promotion picker ---
    promo_panel = PanelContainer.new()
    promo_panel.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
    promo_panel.visible = false
    root.add_child(promo_panel)

    promo_buttons = HBoxContainer.new()
    promo_buttons.add_theme_constant_override("separation", 8)
    promo_panel.add_child(promo_buttons)

func _make_square(sq: int) -> Button:
    var btn := Button.new()
    btn.custom_minimum_size = Vector2(SQ_SIZE, SQ_SIZE)
    btn.focus_mode = Control.FOCUS_NONE
    btn.flat = true
    btn.set_meta("sq", sq)
    btn.pressed.connect(_on_square_clicked.bind(sq))
    btn.mouse_entered.connect(_on_square_hover.bind(sq))
    btn.mouse_exited.connect(_on_square_hover.bind(-1))

    # Background fill
    var bg := ColorRect.new()
    bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
    bg.name = "BG"
    btn.add_child(bg)

    # Highlight overlay (drawn on top of BG; usually transparent)
    var hl := ColorRect.new()
    hl.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    hl.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hl.name = "HL"
    hl.color = Color(0, 0, 0, 0)
    btn.add_child(hl)

    # Piece glyph (centered)
    var glyph := Label.new()
    glyph.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    glyph.mouse_filter = Control.MOUSE_FILTER_IGNORE
    glyph.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    glyph.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    glyph.add_theme_font_size_override("font_size", 44)
    glyph.name = "Glyph"
    btn.add_child(glyph)

    # HP (top-left)
    var hp := Label.new()
    hp.position = Vector2(3, 1)
    hp.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hp.add_theme_font_size_override("font_size", 10)
    hp.add_theme_color_override("font_color", Color.WHITE)
    hp.name = "HP"
    btn.add_child(hp)

    # FX badges (top-right)
    var fx := Label.new()
    fx.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
    fx.offset_left = -28
    fx.offset_top = 1
    fx.offset_right = -3
    fx.mouse_filter = Control.MOUSE_FILTER_IGNORE
    fx.add_theme_font_size_override("font_size", 10)
    fx.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    fx.name = "FX"
    btn.add_child(fx)

    # Charge (bottom-right)
    var ch := Label.new()
    ch.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
    ch.offset_left = -34
    ch.offset_top = -16
    ch.offset_right = -3
    ch.offset_bottom = -1
    ch.mouse_filter = Control.MOUSE_FILTER_IGNORE
    ch.add_theme_font_size_override("font_size", 10)
    ch.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    ch.name = "Charge"
    btn.add_child(ch)

    # Legal-target dot (small circle marker)
    var dot := Label.new()
    dot.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
    dot.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    dot.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    dot.add_theme_font_size_override("font_size", 36)
    dot.add_theme_color_override("font_color", Color(0, 0, 0, 0.32))
    dot.name = "Dot"
    btn.add_child(dot)

    return btn

# ============================================================================
# RENDER — pure projection of (state, mode, selected) → DOM.
# ============================================================================

func _render() -> void:
    var cannon_targets := {}
    for pa in state.pending_attacks:
        if pa.kind != SpecialAbilityDef.Kind.CANNON: continue
        for s in pa.target_squares:
            cannon_targets[s] = true

    var hover_plus := {}
    if mode == "select_ability" and ability_ctx.get("kind") == SpecialAbilityDef.Kind.CANNON \
       and hover_target_sq >= 0:
        for t in ability_ctx.get("targets", []):
            if int(t["sq"]) == hover_target_sq:
                for s in t.get("plus", []):
                    hover_plus[s] = true
                break

    for sq in 64:
        var btn: Button = squares[sq]
        var bg: ColorRect = btn.get_node("BG")
        var hl: ColorRect = btn.get_node("HL")
        var glyph: Label = btn.get_node("Glyph")
        var hp_lbl: Label = btn.get_node("HP")
        var fx_lbl: Label = btn.get_node("FX")
        var ch_lbl: Label = btn.get_node("Charge")
        var dot_lbl: Label = btn.get_node("Dot")

        var f := sq & 7
        var r := sq >> 3
        var is_dark := (f + r) % 2 == 0
        bg.color = DARK_COLOR if is_dark else LIGHT_COLOR
        hl.color = Color(0, 0, 0, 0)
        glyph.text = ""
        hp_lbl.text = ""
        fx_lbl.text = ""
        ch_lbl.text = ""
        dot_lbl.text = ""

        # Layered overlays (later overrides earlier).
        if cannon_targets.has(sq):
            hl.color = CANNON_PENDING_TINT
        if hover_plus.has(sq):
            hl.color = CANNON_HOVER_TINT
        if (last_status.get("kind", "") == "check" or last_status.get("kind", "") == "checkmate") \
           and int(last_status.get("royal_sq", -1)) == sq:
            bg.color = CHECK_TINT
        if selected == sq and mode == "select_move":
            hl.color = SELECTED_TINT
        ## (No "ability source" highlight: abilities are global, not piece-bound.)
        if mode == "select_move":
            for m in legal_for_selected:
                if int(m["to"]) == sq:
                    ## Distinct hues — green = empty-square move, red = capture.
                    ## Same scheme as the customization reachability preview.
                    if m.get("capture", false):
                        hl.color = Color(0.86, 0.42, 0.42, 0.62)  ## red
                    else:
                        hl.color = Color(0.42, 0.78, 0.5, 0.55)   ## green
                    break
        if mode == "select_ability":
            for t in ability_ctx.get("targets", []):
                if int(t["sq"]) == sq:
                    var k = ability_ctx.get("kind")
                    hl.color = ABILITY_CANNON_TINT if k == SpecialAbilityDef.Kind.CANNON else ABILITY_LIGHT_TINT
                    break

        var p = state.board[sq]
        if p != null:
            var def: PieceDef = state.config.pieces[p.def_id]
            glyph.text = def.glyph
            glyph.add_theme_color_override("font_color",
                Color.WHITE if p.color == Rules.WHITE else Color(0.07, 0.07, 0.07))
            if Rules.is_frozen(p):
                glyph.modulate = Color(0.7, 0.85, 1.2)
            else:
                glyph.modulate = Color.WHITE
            hp_lbl.text = "%d/%d" % [p.hp, def.hp]
            hp_lbl.add_theme_color_override("font_color",
                Color(1, 0.55, 0.55) if p.hp <= 1 else Color.WHITE)

            var fx_parts: Array = []
            for e in p.active_effects:
                if e.turns_remaining <= 0: continue
                if e.kind == StatusEffectDef.Kind.BURN:
                    fx_parts.append("🔥%d" % e.turns_remaining)
                elif e.kind == StatusEffectDef.Kind.FREEZE:
                    fx_parts.append("❄%d" % e.turns_remaining)
            fx_lbl.text = " ".join(fx_parts)
            ## (No per-piece charge badge: abilities are global resources
            ## owned by the player, surfaced in the ability bar instead.)

    # --- Status text ---
    var side_name := "White" if state.side == Rules.WHITE else "Black"
    match last_status.get("kind", ""):
        "checkmate":
            var w = last_status.get("winner", -1)
            var text := "Checkmate. %s wins." % ("White" if w == Rules.WHITE else "Black")
            status_label.text = text
            end_label.text = text
            end_label.visible = true
        "stalemate":
            status_label.text = "Stalemate. Draw."
            end_label.text = "Stalemate — Draw"
            end_label.visible = true
        "draw50":
            status_label.text = "50-move rule. Draw."
            end_label.text = "50-move rule — Draw"
            end_label.visible = true
        "check":
            status_label.text = "%s to move — in check." % side_name
            end_label.visible = false
        _:
            status_label.text = "%s to move." % side_name
            end_label.visible = false

    _render_ability_bar()

func _render_ability_bar() -> void:
    for c in ability_bar.get_children(): c.queue_free()

    var enabled := state.config.enabled_ability
    if enabled == SpecialAbilityDef.Kind.NONE:
        var note := Label.new()
        note.text = "No active ability for this game"
        note.modulate = Color(1, 1, 1, 0.45)
        ability_bar.add_child(note)
        return

    if state.special_used_this_turn:
        var note := Label.new()
        note.text = "Ability used this turn"
        note.modulate = Color(1, 1, 1, 0.55)
        ability_bar.add_child(note)
        return

    ## Only the enabled ability's card renders. Render runs every turn so
    ## the progress bar visibly fills as recharge ticks down.
    var color := state.side
    if enabled == SpecialAbilityDef.Kind.CANNON:
        _add_ability_button(SpecialAbilityDef.Kind.CANNON,
                            "Cannon", "◎",
                            state.config.cannon,
                            state.cannon_state[color] if color < state.cannon_state.size() else null)
    elif enabled == SpecialAbilityDef.Kind.LIGHTNING:
        _add_ability_button(SpecialAbilityDef.Kind.LIGHTNING,
                            "Lightning", "⚡",
                            state.config.lightning,
                            state.lightning_state[color] if color < state.lightning_state.size() else null)

## Builds a multi-row ability "card": a clickable button (icon + name +
## charges) over a progress bar that fills from 0 to spec.cooldown_turns
## as the next charge ticks in. When charges are at max, the bar shows
## "MAX" and is fully filled.
func _add_ability_button(kind: int, label: String, icon: String,
                         spec: SpecialAbilityDef, rt) -> int:
    if spec == null or spec.kind == SpecialAbilityDef.Kind.NONE: return 0
    if rt == null or not (rt is Dictionary): return 0
    var charges: int  = int(rt["charges"])
    var recharge: int = int(rt["recharge"])
    var maxc: int     = spec.max_charges
    var cooldown: int = spec.cooldown_turns
    var at_max := charges >= maxc

    var card := VBoxContainer.new()
    card.add_theme_constant_override("separation", 4)
    card.custom_minimum_size = Vector2(220, 0)

    var btn := Button.new()
    btn.text = "%s  %s   %d / %d" % [icon, label, charges, maxc]
    btn.disabled = (charges <= 0)
    btn.tooltip_text = _describe_ability(spec)
    if mode == "select_ability" and int(ability_ctx.get("kind", -1)) == kind:
        btn.modulate = Color(0.75, 0.95, 1.25)
    btn.pressed.connect(_on_ability_button_clicked.bind(kind))
    card.add_child(btn)

    var bar_row := HBoxContainer.new()
    bar_row.add_theme_constant_override("separation", 6)

    var bar := ProgressBar.new()
    bar.show_percentage = false
    bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    bar.custom_minimum_size = Vector2(0, 10)
    bar.max_value = max(cooldown, 1)
    if at_max:
        bar.value = bar.max_value
        bar.modulate = Color(0.55, 0.95, 0.6)
    else:
        bar.value = max(cooldown - recharge, 0)
    bar_row.add_child(bar)

    var note := Label.new()
    note.add_theme_font_size_override("font_size", 11)
    if at_max:
        note.text = "MAX"
        note.modulate = Color(0.55, 0.95, 0.6)
    else:
        note.text = "next in %d" % max(recharge, 1)
        note.modulate = Color(1, 1, 1, 0.7)
    bar_row.add_child(note)

    card.add_child(bar_row)
    ability_bar.add_child(card)
    return 1 if charges > 0 else 0

func _describe_ability(spec: SpecialAbilityDef) -> String:
    if spec.kind == SpecialAbilityDef.Kind.CANNON:
        return "Plus AOE, %d dmg, lands next turn. Cooldown %d, max %d charges." \
               % [spec.damage, spec.cooldown_turns, spec.max_charges]
    elif spec.kind == SpecialAbilityDef.Kind.LIGHTNING:
        return "Single target, %d dmg, instant. Cannot target king. Cooldown %d, max %d charges." \
               % [spec.damage, spec.cooldown_turns, spec.max_charges]
    return ""

# ============================================================================
# CLICK FLOW
# ============================================================================

func _on_square_clicked(sq: int) -> void:
    if _animating: return
    if not pending_promo.is_empty(): return
    if _game_over(): return

    if mode == "select_ability":
        _handle_ability_click(sq)
        return

    if mode == "select_move" and selected != -1:
        var matches: Array = []
        for m in legal_for_selected:
            if int(m["to"]) == sq:
                matches.append(m)
        if matches.size() == 1 and not matches[0].has("promo"):
            _play_move(matches[0])
            return
        if matches.size() > 0 and matches[0].has("promo"):
            pending_promo = matches
            _show_promo_picker(matches)
            return

    var p = state.board[sq]
    if p != null and p.color == state.side and not Rules.is_frozen(p):
        selected = sq
        legal_for_selected = []
        for m in last_status.get("moves", []):
            if int(m["from"]) == sq: legal_for_selected.append(m)
        mode = "select_move" if legal_for_selected.size() > 0 else "select_piece"
    else:
        selected = -1
        legal_for_selected = []
        mode = "select_piece"
    _render()

func _on_ability_button_clicked(kind: int) -> void:
    if _animating: return
    if mode == "select_ability" and int(ability_ctx.get("kind", -1)) == kind:
        _cancel_ability()
        return
    ability_ctx = {
        "kind": kind,
        "targets": Rules.list_ability_targets(state, kind),
    }
    mode = "select_ability"
    selected = -1
    legal_for_selected = []
    _render()

func _handle_ability_click(sq: int) -> void:
    var found := false
    for t in ability_ctx.get("targets", []):
        if int(t["sq"]) == sq:
            found = true; break
    if not found:
        _cancel_ability()
        return
    var old_state := state
    var r := Rules.apply_ability(state, {
        "kind": int(ability_ctx["kind"]),
        "target_sq": sq,
    })
    state = r["state"]
    ## Ability does not flip side — recompute status for SAME side.
    last_status = Rules.game_status(state)
    mode = "select_piece"
    ability_ctx = {}
    selected = -1
    legal_for_selected = []

    _animating = true
    await _animate_events(old_state, r["events"])
    _animating = false
    _render()

func _cancel_ability() -> void:
    mode = "select_piece"
    ability_ctx = {}
    selected = -1
    legal_for_selected = []
    _render()

func _on_square_hover(sq: int) -> void:
    if mode != "select_ability":
        if hover_target_sq != -1:
            hover_target_sq = -1
            _render()
        return
    if hover_target_sq == sq: return
    hover_target_sq = sq
    _render()

func _game_over() -> bool:
    var k = last_status.get("kind", "")
    return k == "checkmate" or k == "stalemate" or k == "draw50"

# ============================================================================
# MOVE EXECUTION
# ============================================================================

func _play_move(m: Dictionary) -> void:
    var old_state := state
    var r := Rules.apply_move(state, m)
    state = r["state"]
    selected = -1
    legal_for_selected = []
    mode = "select_piece"
    ability_ctx = {}
    hover_target_sq = -1
    last_status = Rules.game_status(state)

    ## Animate based on the events list before snapping to the new layout.
    ## Static cells still hold the OLD render (we haven't called _render yet)
    ## so floating sprites in anim_overlay slide over the unchanged board.
    _animating = true
    await _animate_events(old_state, r["events"])
    _animating = false
    _render()

# ============================================================================
# ANIMATIONS — sprite-based (Tween + transient Labels), no particles.
# ----------------------------------------------------------------------------
# Approach: between apply_move and the next _render, the static cells still
# show the OLD piece layout. We hide the relevant glyphs in those cells and
# draw floating Labels in anim_overlay that tween into their new positions.
# When the tween finishes, _render() is called which snaps everything to the
# new state and wipes the overlay.
#
# Event types from Rules.apply_move / apply_ability:
#   move {from, to}       — piece slides from one square to another
#   push {from, to}       — same shape; the pushed piece slides
#   damage {sq}           — surviving target flashes red
#   kill {sq}             — target scales down + fades to 0 alpha
#   lightning {target}    — instant FX flash on the struck square
#   cannonResolved {target: [sq...]} — FX flash on every AOE square
#   cannonQueued / promote — no animation needed
# ============================================================================

func _sq_to_pos(sq: int) -> Vector2:
    var f := sq & 7
    var r := sq >> 3
    return Vector2(f * SQ_SIZE, (7 - r) * SQ_SIZE)

func _create_floating_piece(piece: Piece, sq: int) -> Label:
    var def: PieceDef = state.config.pieces[piece.def_id]
    var lbl := Label.new()
    lbl.text = def.glyph
    lbl.size = Vector2(SQ_SIZE, SQ_SIZE)
    lbl.position = _sq_to_pos(sq)
    lbl.pivot_offset = Vector2(SQ_SIZE * 0.5, SQ_SIZE * 0.5)
    lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    lbl.add_theme_font_size_override("font_size", 44)
    lbl.add_theme_color_override("font_color",
        Color.WHITE if piece.color == Rules.WHITE else Color(0.07, 0.07, 0.07))
    lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
    anim_overlay.add_child(lbl)
    return lbl

func _create_fx_label(glyph: String, sq: int, tint: Color) -> Label:
    var lbl := Label.new()
    lbl.text = glyph
    lbl.size = Vector2(SQ_SIZE, SQ_SIZE)
    lbl.position = _sq_to_pos(sq)
    lbl.pivot_offset = Vector2(SQ_SIZE * 0.5, SQ_SIZE * 0.5)
    lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    lbl.add_theme_font_size_override("font_size", 50)
    lbl.modulate = tint
    lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
    anim_overlay.add_child(lbl)
    return lbl

## Hide the static glyph at sq (so the floating sprite is the only visible
## copy during animation). Returns the Label so the caller can restore it.
func _hide_static_glyph(sq: int) -> Label:
    var btn: Button = squares[sq]
    var glyph: Label = btn.get_node("Glyph")
    glyph.modulate = Color(1, 1, 1, 0)
    return glyph

## The orchestrator. Called between state-update and _render. Awaits the
## composite Tween before returning so the caller can _render afterward.
func _animate_events(old_state: GameState, events: Array) -> void:
    var floats: Array = []          ## transient Labels we created
    var hidden: Array = []          ## static Glyph Labels we made transparent
    var floats_by_sq: Dictionary = {}   ## origin_sq -> Label that tracks it

    ## Pass 1 — pre-build floating sprites for every piece that needs to
    ## relocate (move, push, kill). This way later events (damage flashes)
    ## can target the floating sprite instead of the static cell.
    for ev in events:
        var k = String(ev.get("kind", ""))
        if k == "move" or k == "push":
            var from_sq := int(ev["from"])
            var p = old_state.board[from_sq]
            if p == null: continue
            hidden.append(_hide_static_glyph(from_sq))
            var lbl := _create_floating_piece(p, from_sq)
            floats.append(lbl)
            floats_by_sq[from_sq] = lbl
        elif k == "kill":
            var sq := int(ev["sq"])
            var p = old_state.board[sq]
            if p == null: continue
            hidden.append(_hide_static_glyph(sq))
            var lbl := _create_floating_piece(p, sq)
            floats.append(lbl)
            floats_by_sq[sq] = lbl

    ## Detect whether any of this turn's move events is an attack — those get
    ## a 3-phase anticipate/lunge/settle animation, with damage flashes and
    ## push slides delayed to land at impact moment.
    var has_attack := false
    for ev in events:
        if String(ev.get("kind", "")) == "move":
            var to_sq := int(ev["to"])
            if old_state.board[to_sq] != null:
                has_attack = true
                break

    ## Attack timing (used when has_attack), defined at module scope:
    ##   t = 0.00 .. 0.07  attacker pulls back ~10px (anticipation)
    ##   t = 0.07 .. 0.22  attacker lunges past target into overshoot pos
    ##   t = 0.20          IMPACT — burst FX, target whiteout, push starts
    ##   t = 0.22 .. 0.29  attacker settles into target square
    ##   t = 0.20 .. 0.40  target push slide / kill fade

    var tween := create_tween().set_parallel(true)
    var any := false

    for ev in events:
        var k := String(ev.get("kind", ""))
        if k == "move" or k == "push":
            var from_sq := int(ev["from"])
            var to_sq := int(ev["to"])
            if not floats_by_sq.has(from_sq): continue
            var lbl: Label = floats_by_sq[from_sq]
            var from_pos := _sq_to_pos(from_sq)
            var to_pos := _sq_to_pos(to_sq)
            var is_attack := (k == "move") and (old_state.board[to_sq] != null)

            if is_attack:
                ## ANTICIPATE — small pull-back, opposite of the attack vector.
                var dir := (to_pos - from_pos)
                var dlen := dir.length()
                var unit := dir / dlen if dlen > 0.001 else Vector2.ZERO
                var anticipate_pos := from_pos - unit * 10.0
                var overshoot_pos  := to_pos   + unit * 10.0
                tween.tween_property(lbl, "position", anticipate_pos, T_ANTICIPATE) \
                    .set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
                ## LUNGE — fast, accelerating, slightly past the target square.
                tween.tween_property(lbl, "position", overshoot_pos, T_LUNGE) \
                    .set_delay(T_ANTICIPATE) \
                    .set_trans(Tween.TRANS_QUART).set_ease(Tween.EASE_IN)
                ## SETTLE — snap-back to actual target square.
                tween.tween_property(lbl, "position", to_pos, T_SETTLE) \
                    .set_delay(T_ANTICIPATE + T_LUNGE) \
                    .set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)

                ## IMPACT BURST — sprite at target square; spawn pre-hidden,
                ## scale up + spin + fade in/out. Pure Tween, no particles.
                var fx := _create_fx_label("✸", to_sq, Color(1.55, 1.15, 0.45))
                floats.append(fx)
                fx.scale = Vector2(0.25, 0.25)
                fx.modulate.a = 0.0
                tween.tween_property(fx, "modulate:a", 1.0, 0.05).set_delay(T_IMPACT)
                tween.tween_property(fx, "scale", Vector2(2.6, 2.6), 0.22) \
                    .set_delay(T_IMPACT) \
                    .set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
                tween.tween_property(fx, "modulate:a", 0.0, 0.18) \
                    .set_delay(T_IMPACT + 0.10)
                tween.tween_property(fx, "rotation", 0.65, 0.22).set_delay(T_IMPACT)
            else:
                ## Plain slide — non-attack move or chain push (which gets a
                ## brief delay so it visually starts at impact moment).
                var delay := T_IMPACT if (k == "push" and has_attack) else 0.0
                var dur := ANIM_MOVE_DURATION
                tween.tween_property(lbl, "position", to_pos, dur) \
                    .set_delay(delay) \
                    .set_trans(Tween.TRANS_BACK if k == "push" else Tween.TRANS_QUAD) \
                    .set_ease(Tween.EASE_OUT)
            any = true

        elif k == "damage":
            var sq := int(ev["sq"])
            var target_lbl: Label = floats_by_sq.get(sq, null)
            if target_lbl == null:
                ## Damaged piece isn't being moved — give it a floating clone
                ## so we can flash and shake without touching the static cell.
                var p = old_state.board[sq]
                if p == null: continue
                hidden.append(_hide_static_glyph(sq))
                target_lbl = _create_floating_piece(p, sq)
                floats.append(target_lbl)
            var delay: float = T_IMPACT if has_attack else 0.0
            ## WHITEOUT then RED then back. The whiteout cue is the impact.
            tween.tween_property(target_lbl, "modulate", Color(2.5, 2.5, 2.5), 0.04) \
                .set_delay(delay)
            tween.tween_property(target_lbl, "modulate", Color(1.7, 0.4, 0.4), 0.06) \
                .set_delay(delay + 0.04)
            tween.tween_property(target_lbl, "modulate", Color.WHITE, 0.10) \
                .set_delay(delay + 0.10)
            any = true

        elif k == "kill":
            var sq := int(ev["sq"])
            if floats_by_sq.has(sq):
                var lbl: Label = floats_by_sq[sq]
                var delay: float = T_IMPACT if has_attack else 0.0
                tween.tween_property(lbl, "scale", Vector2(0.25, 0.25),
                    ANIM_KILL_DURATION).set_delay(delay)
                tween.tween_property(lbl, "modulate:a", 0.0,
                    ANIM_KILL_DURATION).set_delay(delay)
                any = true

        elif k == "lightning":
            var sq := int(ev["target"])
            ## Two-pass burst: a bright ring + the bolt glyph. Together they
            ## sell the strike better than a single sprite.
            var ring := _create_fx_label("✺", sq, Color(0.7, 0.85, 1.5))
            floats.append(ring)
            ring.scale = Vector2(0.2, 0.2)
            tween.tween_property(ring, "scale", Vector2(2.4, 2.4), 0.30) \
                .set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
            tween.tween_property(ring, "modulate:a", 0.0, 0.30).set_delay(0.10)

            var bolt := _create_fx_label("⚡", sq, Color(0.95, 1.0, 1.4))
            floats.append(bolt)
            bolt.scale = Vector2(0.4, 0.4)
            tween.tween_property(bolt, "scale", Vector2(1.9, 1.9), 0.18) \
                .set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
            tween.tween_property(bolt, "modulate:a", 0.0, 0.20).set_delay(0.20)
            any = true

        elif k == "cannonResolved":
            for raw in ev.get("target", []):
                var sq := int(raw)
                var fx := _create_fx_label("💥", sq, Color(1.0, 0.7, 0.4))
                floats.append(fx)
                fx.scale = Vector2(0.3, 0.3)
                tween.tween_property(fx, "scale", Vector2(1.85, 1.85), 0.30) \
                    .set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
                tween.tween_property(fx, "modulate:a", 0.0, 0.28).set_delay(0.22)
            any = true

    if any:
        await tween.finished
    else:
        await get_tree().process_frame

    ## Cleanup — the static board (rendered after this returns) will show
    ## the new state with un-hidden glyphs.
    for f in floats:
        if is_instance_valid(f): f.queue_free()
    for g in hidden:
        if is_instance_valid(g): g.modulate = Color.WHITE

# ============================================================================
# PROMOTION PICKER
# ============================================================================

func _show_promo_picker(matches: Array) -> void:
    promo_panel.visible = true
    for c in promo_buttons.get_children(): c.queue_free()
    for m in matches:
        var promo_id := String(m["promo"])
        var def: PieceDef = state.config.pieces[promo_id]
        var btn := Button.new()
        btn.text = def.glyph
        btn.tooltip_text = def.display_name
        btn.add_theme_font_size_override("font_size", 28)
        btn.custom_minimum_size = Vector2(56, 56)
        btn.pressed.connect(_on_promo_chosen.bind(m))
        promo_buttons.add_child(btn)

func _on_promo_chosen(m: Dictionary) -> void:
    pending_promo = []
    promo_panel.visible = false
    _play_move(m)
