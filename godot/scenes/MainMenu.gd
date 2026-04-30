## Start menu — three buttons, no styling beyond Godot defaults.
extends Control

signal start_game
signal open_customization

func _ready() -> void:
    var center := CenterContainer.new()
    center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(center)

    var vb := VBoxContainer.new()
    vb.add_theme_constant_override("separation", 16)
    center.add_child(vb)

    var title := Label.new()
    title.text = "Chess²"
    title.add_theme_font_size_override("font_size", 64)
    title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    vb.add_child(title)

    var tag := Label.new()
    tag.text = "Hot-seat chess with HP, status effects, and per-piece abilities."
    tag.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    tag.modulate = Color(1, 1, 1, 0.6)
    vb.add_child(tag)

    var spacer := Control.new()
    spacer.custom_minimum_size = Vector2(0, 16)
    vb.add_child(spacer)

    var btn_play := Button.new()
    btn_play.text = "Start Game"
    btn_play.custom_minimum_size = Vector2(280, 48)
    btn_play.pressed.connect(func(): start_game.emit())
    vb.add_child(btn_play)

    var btn_customize := Button.new()
    btn_customize.text = "Customize Pieces"
    btn_customize.custom_minimum_size = Vector2(280, 48)
    btn_customize.pressed.connect(func(): open_customization.emit())
    vb.add_child(btn_customize)
