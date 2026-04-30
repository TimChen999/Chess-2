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
var squares: Array = []              ## [Button * 64]
var ability_bar: HBoxContainer
var end_label: Label
var promo_panel: PanelContainer
var promo_buttons: HBoxContainer

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

    # --- Board grid ---
    var board_container := CenterContainer.new()
    root.add_child(board_container)

    board_grid = GridContainer.new()
    board_grid.columns = 8
    board_grid.add_theme_constant_override("h_separation", 0)
    board_grid.add_theme_constant_override("v_separation", 0)
    board_container.add_child(board_grid)

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

    if state.special_used_this_turn:
        var note := Label.new()
        note.text = "Ability used this turn"
        note.modulate = Color(1, 1, 1, 0.55)
        ability_bar.add_child(note)
        return

    var color := state.side
    var found := 0
    found += _add_ability_button(SpecialAbilityDef.Kind.CANNON,
                                 "Cannon", "◎",
                                 state.config.cannon,
                                 state.cannon_state[color] if color < state.cannon_state.size() else null)
    found += _add_ability_button(SpecialAbilityDef.Kind.LIGHTNING,
                                 "Lightning", "⚡",
                                 state.config.lightning,
                                 state.lightning_state[color] if color < state.lightning_state.size() else null)

    if found == 0:
        var note := Label.new()
        note.text = "No abilities ready"
        note.modulate = Color(1, 1, 1, 0.45)
        ability_bar.add_child(note)

func _add_ability_button(kind: int, label: String, icon: String,
                         spec: SpecialAbilityDef, rt: AbilityRuntime) -> int:
    if spec == null or spec.kind == SpecialAbilityDef.Kind.NONE: return 0
    if rt == null: return 0
    var btn := Button.new()
    var has_charges := rt.charges > 0
    if has_charges:
        btn.text = "%s %s (%d)" % [icon, label, rt.charges]
    else:
        btn.text = "%s %s · in %d" % [icon, label, rt.recharge]
        btn.disabled = true
    btn.tooltip_text = _describe_ability(spec)
    if mode == "select_ability" and int(ability_ctx.get("kind", -1)) == kind:
        btn.modulate = Color(0.7, 0.9, 1.2)
    btn.pressed.connect(_on_ability_button_clicked.bind(kind))
    ability_bar.add_child(btn)
    return 1 if has_charges else 0

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
    var r := Rules.apply_move(state, m)
    state = r["state"]
    selected = -1
    legal_for_selected = []
    mode = "select_piece"
    ability_ctx = {}
    hover_target_sq = -1
    last_status = Rules.game_status(state)
    _render()

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
