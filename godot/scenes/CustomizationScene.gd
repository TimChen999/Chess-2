## CustomizationScene — master/detail piece editor (IMPL-GODOT §11).
##
## Edits a *working copy* of GameSettings.active_config. Save commits +
## persists; Cancel discards. Movement is exposed as toggle presets that
## compose into MovePattern arrays — raw pattern records aren't editable.
##
## All edit handlers are explicit methods (not inline lambdas) so the
## GDScript parser stays happy and the call graph is grep-able.
extends Control

signal back_to_menu

# Edit context — set by _render_editor() before any handler can fire.
var working: GameConfig
var current_id: String = ""
var _def: PieceDef                   ## piece being edited (alias into working)
var _toggles: Dictionary = {         ## movement toggle state
    "ortho": false, "diag": false, "range": 0,
    "knight": false, "king": false, "pawn": false,
}

# UI refs.
var piece_list: ItemList
var editor_pane: VBoxContainer

func _ready() -> void:
    working = _clone_config(GameSettings.active_config)
    if working.pieces.size() > 0:
        current_id = working.pieces.keys()[0]
    _build_ui()
    _populate_piece_list()
    _render_editor()

# ============================================================================
# UI construction
# ============================================================================

func _build_ui() -> void:
    var root := VBoxContainer.new()
    root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_theme_constant_override("separation", 8)
    add_child(root)

    var header := HBoxContainer.new()
    header.custom_minimum_size = Vector2(0, 36)
    root.add_child(header)

    var btn_back := Button.new()
    btn_back.text = "← Cancel"
    btn_back.pressed.connect(_on_cancel)
    header.add_child(btn_back)

    var title := Label.new()
    title.text = "  Customize Pieces"
    title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    title.add_theme_font_size_override("font_size", 20)
    header.add_child(title)

    var btn_reset_all := Button.new()
    btn_reset_all.text = "Reset all to defaults"
    btn_reset_all.pressed.connect(_on_reset_all)
    header.add_child(btn_reset_all)

    var btn_save := Button.new()
    btn_save.text = "Save"
    btn_save.pressed.connect(_on_save)
    header.add_child(btn_save)

    var body := HSplitContainer.new()
    body.size_flags_vertical = Control.SIZE_EXPAND_FILL
    body.split_offset = 220
    root.add_child(body)

    piece_list = ItemList.new()
    piece_list.custom_minimum_size = Vector2(220, 0)
    piece_list.item_selected.connect(_on_piece_selected)
    body.add_child(piece_list)

    var scroll := ScrollContainer.new()
    scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    body.add_child(scroll)

    editor_pane = VBoxContainer.new()
    editor_pane.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    editor_pane.add_theme_constant_override("separation", 12)
    scroll.add_child(editor_pane)

func _populate_piece_list() -> void:
    piece_list.clear()
    var idx := 0
    var sel_idx := 0
    for id in working.pieces.keys():
        var def: PieceDef = working.pieces[id]
        piece_list.add_item("%s  %s" % [def.glyph, def.display_name])
        piece_list.set_item_metadata(idx, id)
        if id == current_id: sel_idx = idx
        idx += 1
    if piece_list.item_count > 0:
        piece_list.select(sel_idx)

func _on_piece_selected(idx: int) -> void:
    current_id = piece_list.get_item_metadata(idx)
    _render_editor()

# ============================================================================
# EDITOR PANE
# ============================================================================

func _render_editor() -> void:
    for c in editor_pane.get_children(): c.queue_free()
    if not working.pieces.has(current_id): return
    _def = working.pieces[current_id]
    if _def.on_hit == null:
        var oh := StatusEffectDef.new()
        oh.kind = StatusEffectDef.Kind.NONE
        _def.on_hit = oh
    if _def.special == null:
        var sp := SpecialAbilityDef.new()
        sp.kind = SpecialAbilityDef.Kind.NONE
        _def.special = sp
    _toggles = _infer_toggles(_def)

    # --- Identity ---
    var sec := _section("Identity")
    sec.add_child(_text_field("Name",  _def.display_name, _on_name_changed))
    sec.add_child(_text_field("Glyph", _def.glyph,        _on_glyph_changed))
    editor_pane.add_child(sec)

    # --- Stats ---
    var stats := _section("Stats")
    stats.add_child(_int_field("HP",     _def.hp,     1, 10, _on_hp_changed))
    stats.add_child(_int_field("Damage", _def.damage, 1,  5, _on_damage_changed))
    editor_pane.add_child(stats)

    # --- Movement ---
    var move := _section("Movement")
    move.add_child(_check_field("Slides orthogonally", _toggles["ortho"],
        _on_toggle_changed.bind("ortho")))
    move.add_child(_check_field("Slides diagonally",   _toggles["diag"],
        _on_toggle_changed.bind("diag")))
    move.add_child(_int_field("Range limit (0 = unlimited)",
        _toggles["range"], 0, 7, _on_range_changed))
    move.add_child(_check_field("Knight leap",         _toggles["knight"],
        _on_toggle_changed.bind("knight")))
    move.add_child(_check_field("One step any direction", _toggles["king"],
        _on_toggle_changed.bind("king")))
    move.add_child(_check_field("Pawn-like (push + diagonal capture)",
        _toggles["pawn"], _on_toggle_changed.bind("pawn")))
    editor_pane.add_child(move)

    # --- Reachability preview ---
    var reach := _section("Reachability preview (centered piece)")
    reach.add_child(_build_reach_grid(_def))
    editor_pane.add_child(reach)

    # --- On-hit effect ---
    var onhit := _section("On-hit status effect")
    onhit.add_child(_select_field("Kind", _def.on_hit.kind, [
        ["None",   StatusEffectDef.Kind.NONE],
        ["Burn",   StatusEffectDef.Kind.BURN],
        ["Freeze", StatusEffectDef.Kind.FREEZE],
    ], _on_onhit_kind_changed))
    if _def.on_hit.kind == StatusEffectDef.Kind.BURN:
        onhit.add_child(_int_field("Damage per turn",
            max(1, _def.on_hit.damage_per_turn), 1, 5, _on_onhit_dpt_changed))
    if _def.on_hit.kind == StatusEffectDef.Kind.BURN \
       or _def.on_hit.kind == StatusEffectDef.Kind.FREEZE:
        onhit.add_child(_int_field("Duration (turns)",
            max(1, _def.on_hit.duration), 1, 10, _on_onhit_duration_changed))
    editor_pane.add_child(onhit)

    # --- Special ability ---
    var ab := _section("Special ability")
    ab.add_child(_select_field("Kind", _def.special.kind, [
        ["None",                  SpecialAbilityDef.Kind.NONE],
        ["Cannon (delayed AOE)",  SpecialAbilityDef.Kind.CANNON],
        ["Lightning (instant)",   SpecialAbilityDef.Kind.LIGHTNING],
    ], _on_special_kind_changed))
    if _def.special.kind != SpecialAbilityDef.Kind.NONE:
        ab.add_child(_int_field("Damage",     _def.special.damage,         1, 5,  _on_special_damage_changed))
        ab.add_child(_int_field("Cooldown",   _def.special.cooldown_turns, 1, 10, _on_special_cooldown_changed))
        ab.add_child(_int_field("Max charges", _def.special.max_charges,    1, 5,  _on_special_max_changed))
        ab.add_child(_int_field("Initial charges", _def.special.initial_charges,
                                0, _def.special.max_charges, _on_special_initial_changed))
        var summary := Label.new()
        summary.add_theme_font_size_override("font_size", 11)
        summary.modulate = Color(1, 1, 1, 0.6)
        summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
        if _def.special.kind == SpecialAbilityDef.Kind.CANNON:
            summary.text = "5-square plus AOE, lands one full turn later. Cannot target enemy starting zone."
        else:
            summary.text = "Single enemy target, instant. Cannot target the royal piece."
        ab.add_child(summary)
    editor_pane.add_child(ab)

    # --- Footer ---
    var footer := HBoxContainer.new()
    footer.add_theme_constant_override("separation", 8)
    var btn_reset := Button.new()
    btn_reset.text = "Reset this piece to default"
    btn_reset.pressed.connect(_on_reset_this)
    footer.add_child(btn_reset)
    editor_pane.add_child(footer)

# ============================================================================
# FIELD HANDLERS — explicit methods, no lambdas
# ============================================================================

func _on_name_changed(v: String) -> void:
    _def.display_name = v
    _populate_piece_list()

func _on_glyph_changed(v: String) -> void:
    if v.length() >= 1:
        _def.glyph = v.substr(0, 2)
        _populate_piece_list()

func _on_hp_changed(v: int) -> void:     _def.hp = v
func _on_damage_changed(v: int) -> void: _def.damage = v

func _on_toggle_changed(value: bool, key: String) -> void:
    _toggles[key] = value
    _def.move_patterns = _toggles_to_patterns(_toggles)
    _render_editor()

func _on_range_changed(v: int) -> void:
    _toggles["range"] = v
    _def.move_patterns = _toggles_to_patterns(_toggles)

func _on_onhit_kind_changed(v: int) -> void:
    _def.on_hit.kind = v
    _render_editor()

func _on_onhit_dpt_changed(v: int) -> void:      _def.on_hit.damage_per_turn = v
func _on_onhit_duration_changed(v: int) -> void: _def.on_hit.duration = v

func _on_special_kind_changed(v: int) -> void:
    _def.special.kind = v
    if v != SpecialAbilityDef.Kind.NONE:
        if _def.special.damage <= 0:         _def.special.damage = 1
        if _def.special.cooldown_turns <= 0: _def.special.cooldown_turns = 3
        if _def.special.max_charges <= 0:    _def.special.max_charges = 1
        if _def.special.initial_charges < 0: _def.special.initial_charges = 0
    _render_editor()

func _on_special_damage_changed(v: int) -> void:    _def.special.damage = v
func _on_special_cooldown_changed(v: int) -> void:  _def.special.cooldown_turns = v
func _on_special_max_changed(v: int) -> void:
    _def.special.max_charges = v
    if _def.special.initial_charges > v:
        _def.special.initial_charges = v
    _render_editor()
func _on_special_initial_changed(v: int) -> void:   _def.special.initial_charges = v

func _on_reset_this() -> void:
    var fresh := Defaults.make_default_config()
    if fresh.pieces.has(current_id):
        working.pieces[current_id] = fresh.pieces[current_id]
        _populate_piece_list()
        _render_editor()

func _on_reset_all() -> void:
    working = Defaults.make_default_config()
    if working.pieces.size() > 0:
        current_id = working.pieces.keys()[0]
    _populate_piece_list()
    _render_editor()

func _on_save() -> void:
    GameSettings.active_config = working
    GameSettings.save()
    back_to_menu.emit()

func _on_cancel() -> void:
    back_to_menu.emit()

# ============================================================================
# FORM HELPERS
# ============================================================================

func _section(title: String) -> VBoxContainer:
    var v := VBoxContainer.new()
    v.add_theme_constant_override("separation", 4)
    var h := Label.new()
    h.text = title
    h.add_theme_font_size_override("font_size", 14)
    h.modulate = Color(0.8, 0.85, 0.95)
    v.add_child(h)
    return v

func _row(label: String) -> HBoxContainer:
    var h := HBoxContainer.new()
    h.add_theme_constant_override("separation", 8)
    var l := Label.new()
    l.text = label
    l.custom_minimum_size = Vector2(180, 0)
    h.add_child(l)
    return h

func _text_field(label: String, value: String, on_change: Callable) -> HBoxContainer:
    var h := _row(label)
    var le := LineEdit.new()
    le.text = value
    le.custom_minimum_size = Vector2(180, 0)
    le.text_changed.connect(on_change)
    h.add_child(le)
    return h

func _int_field(label: String, value: int, min_v: int, max_v: int,
                on_change: Callable) -> HBoxContainer:
    var h := _row(label)
    var sb := SpinBox.new()
    sb.min_value = min_v
    sb.max_value = max_v
    sb.value = value
    sb.step = 1
    sb.value_changed.connect(_spinbox_to_int.bind(on_change))
    h.add_child(sb)
    return h

func _spinbox_to_int(value: float, sink: Callable) -> void:
    sink.call(int(value))

func _check_field(label: String, value: bool, on_change: Callable) -> HBoxContainer:
    var h := HBoxContainer.new()
    h.add_theme_constant_override("separation", 8)
    var cb := CheckBox.new()
    cb.button_pressed = value
    cb.text = label
    cb.toggled.connect(on_change)
    h.add_child(cb)
    return h

func _select_field(label: String, value: int, options: Array,
                   on_change: Callable) -> HBoxContainer:
    var h := _row(label)
    var ob := OptionButton.new()
    var idx := 0
    for o in options:
        ob.add_item(String(o[0]))
        ob.set_item_metadata(idx, int(o[1]))
        if int(o[1]) == value: ob.select(idx)
        idx += 1
    ob.item_selected.connect(_select_dispatch.bind(ob, on_change))
    h.add_child(ob)
    return h

func _select_dispatch(idx: int, ob: OptionButton, sink: Callable) -> void:
    sink.call(int(ob.get_item_metadata(idx)))

# ============================================================================
# REACHABILITY PREVIEW
# ============================================================================

func _build_reach_grid(def: PieceDef) -> GridContainer:
    var grid := GridContainer.new()
    grid.columns = 8
    grid.add_theme_constant_override("h_separation", 0)
    grid.add_theme_constant_override("v_separation", 0)

    var center := 3 * 8 + 3
    var reach_a := _preview_reach(def, center, false)
    var reach_b := _preview_reach(def, center, true)

    for r in range(7, -1, -1):
        for f in 8:
            var sq := r * 8 + f
            var cell := ColorRect.new()
            cell.custom_minimum_size = Vector2(28, 28)
            var is_dark := (f + r) % 2 == 0
            cell.color = Color("#95684a") if is_dark else Color("#d8c5a4")
            if sq == center:
                cell.color = Color(0.96, 0.83, 0.4)
            elif reach_a.has(sq):
                cell.color = cell.color.lerp(Color(0, 0, 0), 0.3)
            elif reach_b.has(sq):
                cell.color = cell.color.lerp(Color(0.85, 0.2, 0.2), 0.45)
            grid.add_child(cell)
    return grid

func _preview_reach(def: PieceDef, from_sq: int, place_enemies: bool) -> Dictionary:
    var cfg := GameConfig.new()
    cfg.pieces = { def.id: def }
    if place_enemies:
        var dummy := PieceDef.new()
        dummy.id = "__dummy"
        dummy.display_name = "dummy"
        dummy.glyph = "?"
        dummy.hp = 99
        dummy.damage = 1
        dummy.move_patterns = []
        dummy.on_hit = StatusEffectDef.new()
        dummy.special = SpecialAbilityDef.new()
        cfg.pieces["__dummy"] = dummy
    var board: Array = []; board.resize(64)
    for i in 64: board[i] = null
    board[from_sq] = Rules.make_piece(def.id, Rules.WHITE, def)
    if place_enemies:
        for i in 64:
            if i == from_sq: continue
            board[i] = Rules.make_piece("__dummy", Rules.BLACK, cfg.pieces["__dummy"])
    var s := GameState.new()
    s.config = cfg
    s.board = board
    s.side = Rules.WHITE
    var set_d: Dictionary = {}
    for m in Rules.pseudo_legal_moves(s, Rules.WHITE):
        if int(m["from"]) == from_sq:
            set_d[int(m["to"])] = true
    return set_d

# ============================================================================
# TOGGLE ↔ PATTERN MAPPING
# ============================================================================

func _infer_toggles(def: PieceDef) -> Dictionary:
    var t: Dictionary = {
        "ortho": false, "diag": false, "range": 0,
        "knight": false, "king": false, "pawn": false,
    }
    for pat in def.move_patterns:
        if pat.kind == MovePattern.Kind.RIDER:
            if _offsets_match(pat.offsets, Defaults.ORTHO):
                t["ortho"] = true
                t["range"] = pat.max_range
            elif _offsets_match(pat.offsets, Defaults.DIAG):
                t["diag"] = true
                t["range"] = pat.max_range
        elif pat.kind == MovePattern.Kind.LEAPER:
            if _offsets_match(pat.offsets, Defaults.KNIGHT_OFFS):
                t["knight"] = true
            elif _offsets_match(pat.offsets, Defaults.KING_OFFS):
                t["king"] = true
        elif pat.kind == MovePattern.Kind.PAWN_PUSH \
             or pat.kind == MovePattern.Kind.PAWN_DOUBLE \
             or pat.kind == MovePattern.Kind.PAWN_CAPTURE:
            t["pawn"] = true
    return t

func _toggles_to_patterns(t: Dictionary) -> Array[MovePattern]:
    var out: Array[MovePattern] = []
    if t["ortho"]:
        var p := MovePattern.new()
        p.kind = MovePattern.Kind.RIDER
        p.offsets = _to_v2i(Defaults.ORTHO)
        p.max_range = int(t["range"])
        out.append(p)
    if t["diag"]:
        var p := MovePattern.new()
        p.kind = MovePattern.Kind.RIDER
        p.offsets = _to_v2i(Defaults.DIAG)
        p.max_range = int(t["range"])
        out.append(p)
    if t["knight"]:
        var p := MovePattern.new()
        p.kind = MovePattern.Kind.LEAPER
        p.offsets = _to_v2i(Defaults.KNIGHT_OFFS)
        out.append(p)
    if t["king"]:
        var p := MovePattern.new()
        p.kind = MovePattern.Kind.LEAPER
        p.offsets = _to_v2i(Defaults.KING_OFFS)
        out.append(p)
    if t["pawn"]:
        var p1 := MovePattern.new(); p1.kind = MovePattern.Kind.PAWN_PUSH;    out.append(p1)
        var p2 := MovePattern.new(); p2.kind = MovePattern.Kind.PAWN_DOUBLE;  out.append(p2)
        var p3 := MovePattern.new(); p3.kind = MovePattern.Kind.PAWN_CAPTURE; out.append(p3)
    return out

func _to_v2i(arr: Array) -> Array[Vector2i]:
    var out: Array[Vector2i] = []
    for v in arr: out.append(v)
    return out

func _offsets_match(a: Array, b: Array) -> bool:
    if a.size() != b.size(): return false
    var sa: Array = []
    var sb: Array = []
    for v in a: sa.append("%d,%d" % [v.x, v.y])
    for v in b: sb.append("%d,%d" % [v.x, v.y])
    sa.sort(); sb.sort()
    for i in sa.size():
        if sa[i] != sb[i]: return false
    return true

# ============================================================================
# DEEP CLONE — the working copy is a full clone so Cancel really discards.
# ============================================================================

func _clone_config(src: GameConfig) -> GameConfig:
    var dst := GameConfig.new()
    var p_dict := {}
    for id in src.pieces.keys():
        p_dict[id] = _clone_piece_def(src.pieces[id])
    dst.pieces = p_dict
    dst.initial_setup = src.initial_setup.duplicate(true)
    return dst

func _clone_piece_def(s: PieceDef) -> PieceDef:
    var d := PieceDef.new()
    d.id = s.id
    d.display_name = s.display_name
    d.glyph = s.glyph
    d.hp = s.hp
    d.damage = s.damage
    d.royal = s.royal
    d.can_castle = s.can_castle
    d.promotes_at_rank = s.promotes_at_rank
    d.promotes_to = s.promotes_to.duplicate()
    var pats: Array[MovePattern] = []
    for p in s.move_patterns:
        var np := MovePattern.new()
        np.kind = p.kind
        np.offsets = p.offsets.duplicate()
        np.max_range = p.max_range
        np.capture_only = p.capture_only
        np.move_only = p.move_only
        pats.append(np)
    d.move_patterns = pats
    if s.on_hit != null:
        var ne := StatusEffectDef.new()
        ne.kind = s.on_hit.kind
        ne.damage_per_turn = s.on_hit.damage_per_turn
        ne.duration = s.on_hit.duration
        d.on_hit = ne
    if s.special != null:
        var ns := SpecialAbilityDef.new()
        ns.kind = s.special.kind
        ns.damage = s.special.damage
        ns.cooldown_turns = s.special.cooldown_turns
        ns.max_charges = s.special.max_charges
        ns.initial_charges = s.special.initial_charges
        d.special = ns
    return d
