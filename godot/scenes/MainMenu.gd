## Start menu — three buttons in the same pixel-art treatment used in the
## game scene (dark wood plates with hard 2px borders, cream type), so the
## whole game reads as one stylized package.
extends Control

signal start_game
signal open_customization

const ACCENT  := Color(0.95, 0.88, 0.74)
const ACCENT2 := Color(1.00, 0.97, 0.86)
const SHADE   := Color(0.06, 0.04, 0.07)
const PLATE   := Color(0.18, 0.13, 0.12)
const PLATE2  := Color(0.28, 0.20, 0.18)

func _ready() -> void:
    var center := CenterContainer.new()
    center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(center)

    var vb := VBoxContainer.new()
    vb.add_theme_constant_override("separation", 18)
    vb.alignment = BoxContainer.ALIGNMENT_CENTER
    center.add_child(vb)

    var title := Label.new()
    title.text = "CHESS²"
    title.add_theme_font_size_override("font_size", 96)
    title.add_theme_color_override("font_color", ACCENT)
    title.add_theme_color_override("font_outline_color", SHADE)
    title.add_theme_constant_override("outline_size", 8)
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    vb.add_child(title)

    var tag := Label.new()
    tag.text = "Hot-seat chess with HP, status effects, and per-piece abilities."
    tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    tag.add_theme_color_override("font_color", ACCENT)
    tag.modulate = Color(1, 1, 1, 0.55)
    vb.add_child(tag)

    var spacer := Control.new()
    spacer.custom_minimum_size = Vector2(0, 12)
    vb.add_child(spacer)

    var btn_play := _make_btn("Start Game")
    btn_play.pressed.connect(func(): start_game.emit())
    vb.add_child(btn_play)

    var btn_customize := _make_btn("Customize Pieces")
    btn_customize.pressed.connect(func(): open_customization.emit())
    vb.add_child(btn_customize)

    ## Stage picker — Classic (no hazards) vs. Moon (procedural debris that
    ## lands symmetrically on both halves at the end of each turn pair).
    ## Saved into the active GameConfig so the choice persists across runs
    ## alongside customization data.
    vb.add_child(_make_stage_picker())

func _make_stage_picker() -> Control:
    var row := HBoxContainer.new()
    row.alignment = BoxContainer.ALIGNMENT_CENTER
    row.add_theme_constant_override("separation", 10)

    var lbl := Label.new()
    lbl.text = "Stage"
    lbl.add_theme_color_override("font_color", ACCENT)
    lbl.modulate = Color(1, 1, 1, 0.75)
    lbl.add_theme_font_size_override("font_size", 16)
    row.add_child(lbl)

    var opt := OptionButton.new()
    opt.add_item("Classic", 0)
    opt.set_item_metadata(0, "classic")
    opt.add_item("Moon (debris)", 1)
    opt.set_item_metadata(1, "moon")
    opt.custom_minimum_size = Vector2(180, 36)
    var current := "classic"
    if GameSettings.active_config != null and GameSettings.active_config.stage != "":
        current = GameSettings.active_config.stage
    opt.select(1 if current == "moon" else 0)
    opt.item_selected.connect(_on_stage_selected.bind(opt))
    row.add_child(opt)
    return row

func _on_stage_selected(idx: int, opt: OptionButton) -> void:
    var stage := String(opt.get_item_metadata(idx))
    if GameSettings.active_config == null: return
    GameSettings.active_config.stage = stage
    GameSettings.save()

func _make_btn(text: String) -> Button:
    var b := Button.new()
    b.text = text
    b.custom_minimum_size = Vector2(280, 48)
    b.focus_mode = Control.FOCUS_NONE

    var normal := StyleBoxFlat.new()
    normal.bg_color = PLATE
    normal.border_color = SHADE
    normal.set_border_width_all(2)
    normal.set_corner_radius_all(0)
    normal.set_content_margin_all(8)
    var hover := normal.duplicate() as StyleBoxFlat
    hover.bg_color = PLATE2
    hover.border_color = ACCENT
    var pressed := normal.duplicate() as StyleBoxFlat
    pressed.bg_color = Color(0.10, 0.08, 0.07)
    pressed.border_color = ACCENT

    b.add_theme_stylebox_override("normal", normal)
    b.add_theme_stylebox_override("hover", hover)
    b.add_theme_stylebox_override("pressed", pressed)
    b.add_theme_stylebox_override("focus", normal)
    b.add_theme_color_override("font_color", ACCENT)
    b.add_theme_color_override("font_hover_color", ACCENT2)
    b.add_theme_color_override("font_pressed_color", ACCENT2)
    b.add_theme_font_size_override("font_size", 20)
    return b
