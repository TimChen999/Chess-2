## CustomizationScene — variant picker (PIECE-VARIANTS.md §5.1).
##
## Replaces the legacy granular per-piece editor with a slot-based variant
## picker. Each slot (pawn / bishop / knight / rook / queen / king) shows
## one card per available variant with a live sprite, stat readout, and
## one-line move description. Picking a card sets variant_selection[slot]
## on the working config; Save commits + persists.
##
## Ability editor stays — abilities are global and orthogonal to piece
## variants. It lives at the bottom of the same scroll view.
extends Control

signal back_to_menu

# Working copy — Save commits to GameSettings.active_config; Cancel discards.
var working: GameConfig
var _variants_by_slot: Dictionary = {}    ## slot -> Array[PieceDef]

# UI refs.
var content_pane: VBoxContainer

func _ready() -> void:
    working = _clone_config(GameSettings.active_config)
    _variants_by_slot = Defaults.make_variants_map()
    _build_ui()
    _populate_content()

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

    var scroll := ScrollContainer.new()
    scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    root.add_child(scroll)

    content_pane = VBoxContainer.new()
    content_pane.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    content_pane.add_theme_constant_override("separation", 14)
    scroll.add_child(content_pane)

# ============================================================================
# Variant picker grid
# ============================================================================

func _populate_content() -> void:
    for c in content_pane.get_children(): c.queue_free()

    ## One row per slot, in the canonical order from Defaults.
    for slot in Defaults.variant_slots():
        content_pane.add_child(_build_slot_section(slot))

    ## Ability sub-pages — one per ability. Stays editable; orthogonal to
    ## piece variants.
    var ability_header := Label.new()
    ability_header.text = "Abilities"
    ability_header.add_theme_font_size_override("font_size", 18)
    ability_header.modulate = Color(0.95, 0.88, 0.74)
    content_pane.add_child(ability_header)

    content_pane.add_child(_build_ability_section(SpecialAbilityDef.Kind.CANNON))
    content_pane.add_child(_build_ability_section(SpecialAbilityDef.Kind.LIGHTNING))

func _build_slot_section(slot: String) -> Control:
    var sec := VBoxContainer.new()
    sec.add_theme_constant_override("separation", 4)

    var heading := Label.new()
    heading.text = _slot_display_name(slot)
    heading.add_theme_font_size_override("font_size", 16)
    heading.modulate = Color(0.95, 0.88, 0.74)
    sec.add_child(heading)

    var row := HBoxContainer.new()
    row.add_theme_constant_override("separation", 8)
    sec.add_child(row)

    var variants: Array = _variants_by_slot.get(slot, [])
    var current_id: String = String(working.variant_selection.get(slot, slot))
    for def in variants:
        row.add_child(_build_variant_card(slot, def, def.id == current_id))

    return sec

## One picker card. Click anywhere on the card to select that variant.
## Selected card has a highlighted border. Single-variant slots still get
## a card so the player understands the slot is fixed.
func _build_variant_card(slot: String, def: PieceDef, selected: bool) -> Control:
    var card := PanelContainer.new()
    card.custom_minimum_size = Vector2(180, 150)
    var sb := StyleBoxFlat.new()
    sb.bg_color = Color(0.10, 0.08, 0.10)
    sb.border_color = Color(0.95, 0.88, 0.74) if selected else Color(0.30, 0.25, 0.30)
    sb.set_border_width_all(3 if selected else 2)
    sb.set_corner_radius_all(0)
    sb.set_content_margin_all(6)
    card.add_theme_stylebox_override("panel", sb)

    var inner := VBoxContainer.new()
    inner.add_theme_constant_override("separation", 4)
    card.add_child(inner)

    var top := HBoxContainer.new()
    top.add_theme_constant_override("separation", 6)
    inner.add_child(top)

    ## Live sprite — uses the same procedural sprite that renders on the
    ## board, so picker cards are visually authoritative.
    var sprite := TextureRect.new()
    sprite.texture = SpriteFactory.piece_texture(def.id, 0)
    sprite.custom_minimum_size = Vector2(56, 56)
    sprite.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
    sprite.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
    sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
    top.add_child(sprite)

    var name_box := VBoxContainer.new()
    name_box.add_theme_constant_override("separation", 2)
    top.add_child(name_box)

    var name_lbl := Label.new()
    name_lbl.text = def.display_name
    name_lbl.add_theme_font_size_override("font_size", 14)
    name_lbl.modulate = Color(0.95, 0.88, 0.74)
    name_box.add_child(name_lbl)

    var stats := Label.new()
    stats.text = "%dHP / %dDMG" % [def.hp, def.damage]
    stats.add_theme_font_size_override("font_size", 12)
    stats.modulate = Color(1, 1, 1, 0.75)
    name_box.add_child(stats)

    var desc := Label.new()
    desc.text = _describe_variant(def)
    desc.add_theme_font_size_override("font_size", 11)
    desc.modulate = Color(1, 1, 1, 0.65)
    desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    desc.custom_minimum_size = Vector2(160, 0)
    inner.add_child(desc)

    ## Click target — covers the whole card.
    var hit := Button.new()
    hit.flat = true
    hit.focus_mode = Control.FOCUS_NONE
    hit.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    hit.pressed.connect(_on_variant_picked.bind(slot, def.id))
    card.add_child(hit)

    return card

func _on_variant_picked(slot: String, variant_id: String) -> void:
    working.variant_selection[slot] = variant_id
    _populate_content()

# ============================================================================
# Ability editor
# ============================================================================

func _build_ability_section(kind: int) -> Control:
    var spec: SpecialAbilityDef
    var heading_text: String
    var description: String
    if kind == SpecialAbilityDef.Kind.CANNON:
        if working.cannon == null:
            working.cannon = Defaults.make_special(SpecialAbilityDef.Kind.CANNON, 2, 4, 1, 0)
        spec = working.cannon
        heading_text = "◎  Cannon"
        description = "Plus-shape AOE attack queued one turn ahead. " \
                    + "Cannot target squares the enemy started on."
    else:
        if working.lightning == null:
            working.lightning = Defaults.make_special(SpecialAbilityDef.Kind.LIGHTNING, 1, 3, 1, 1)
        spec = working.lightning
        heading_text = "⚡  Lightning"
        description = "Instant single-target damage. Cannot target the royal piece."

    var sec := VBoxContainer.new()
    sec.add_theme_constant_override("separation", 4)

    var head_row := HBoxContainer.new()
    head_row.add_theme_constant_override("separation", 8)
    sec.add_child(head_row)

    var heading := Label.new()
    heading.text = heading_text
    heading.add_theme_font_size_override("font_size", 15)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    head_row.add_child(heading)

    var active_cb := CheckBox.new()
    active_cb.text = "Active"
    active_cb.button_pressed = (working.enabled_ability == kind)
    active_cb.toggled.connect(_on_active_ability_toggled.bind(kind))
    head_row.add_child(active_cb)

    var blurb := Label.new()
    blurb.text = description
    blurb.modulate = Color(1, 1, 1, 0.65)
    blurb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    sec.add_child(blurb)

    sec.add_child(_int_row("Damage",          spec.damage,         1, 5,  spec, "damage"))
    sec.add_child(_int_row("Cooldown turns",  spec.cooldown_turns, 1, 10, spec, "cooldown_turns"))
    sec.add_child(_int_row("Energy cost",     spec.energy_cost,    0, 10, spec, "energy_cost"))
    sec.add_child(_int_row("Max charges",     spec.max_charges,    1, 5,  spec, "max_charges"))
    sec.add_child(_int_row("Initial charges", spec.initial_charges, 0, max(spec.max_charges, 0),
                            spec, "initial_charges"))
    return sec

func _int_row(label: String, value: int, min_v: int, max_v: int,
              spec: SpecialAbilityDef, field: String) -> HBoxContainer:
    var h := HBoxContainer.new()
    h.add_theme_constant_override("separation", 8)
    var l := Label.new()
    l.text = label
    l.custom_minimum_size = Vector2(180, 0)
    h.add_child(l)
    var sb := SpinBox.new()
    sb.min_value = min_v
    sb.max_value = max_v
    sb.value = value
    sb.step = 1
    sb.value_changed.connect(_ability_setter.bind(spec, field))
    h.add_child(sb)
    return h

## Generic int-setter. SpinBox emits floats; cast to int and clamp the
## related initial_charges field if max_charges drops.
func _ability_setter(value: float, spec: SpecialAbilityDef, field: String) -> void:
    spec.set(field, int(value))
    if field == "max_charges" and spec.initial_charges > int(value):
        spec.initial_charges = int(value)
        _populate_content()

func _on_active_ability_toggled(pressed: bool, kind: int) -> void:
    if pressed:
        working.enabled_ability = kind
    elif working.enabled_ability == kind:
        ## Toggling the active one off → no ability for this game.
        working.enabled_ability = SpecialAbilityDef.Kind.NONE
    _populate_content()

# ============================================================================
# Save / Cancel / Reset
# ============================================================================

func _on_save() -> void:
    working.rebuild_initial_setup()
    GameSettings.active_config = working
    GameSettings.save()
    back_to_menu.emit()

func _on_cancel() -> void:
    back_to_menu.emit()

func _on_reset_all() -> void:
    working = Defaults.make_default_config()
    _populate_content()

# ============================================================================
# Variant copy / display helpers
# ============================================================================

func _slot_display_name(slot: String) -> String:
    match slot:
        "pawn":   return "Pawn"
        "bishop": return "Bishop"
        "knight": return "Knight"
        "rook":   return "Rook"
        "queen":  return "Queen"
        "king":   return "King"
    return slot.capitalize()

## One-line copy describing what the variant does. Hand-authored per id so
## it can mention the gameplay differentiator instead of summarizing
## auto-generated move-pattern records.
func _describe_variant(def: PieceDef) -> String:
    match def.id:
        "pawn":            return "Push, double-push, diagonal capture, promotes."
        "bandit_pawn":     return "Cross-step move, X-pounce attack. No promote."
        "bishop":          return "Slides any number of diagonals."
        "assassin_bishop": return "Jumps up to 2 diagonals; ignores blockers."
        "knight":          return "L-shape leap. On hit: freeze (1 turn)."
        "alter_knight":    return "Knight move (jump), king-shape attack. Freeze on hit."
        "rook":            return "Slides orthogonally. On hit: burn (2 turns)."
        "queen":           return "Slides any number of squares any direction."
        "king":            return "Royal piece. One step, any direction."
    return ""

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
    if src.cannon != null:    dst.cannon    = _clone_special(src.cannon)
    if src.lightning != null: dst.lightning = _clone_special(src.lightning)
    dst.enabled_ability = src.enabled_ability
    dst.stage = src.stage
    dst.debris_spawn_chance = src.debris_spawn_chance
    dst.debris_damage = src.debris_damage
    dst.variant_selection = src.variant_selection.duplicate(true)
    return dst

func _clone_special(s: SpecialAbilityDef) -> SpecialAbilityDef:
    var d := SpecialAbilityDef.new()
    d.kind = s.kind
    d.damage = s.damage
    d.cooldown_turns = s.cooldown_turns
    d.max_charges = s.max_charges
    d.initial_charges = s.initial_charges
    d.energy_cost = s.energy_cost
    return d

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
    return d
