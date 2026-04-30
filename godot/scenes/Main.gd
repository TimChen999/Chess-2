## Root scene: holds whichever sub-scene is active and swaps them on signals
## from buttons. Sub-scenes communicate "what to switch to" by signal —
## `start_game`, `open_customization`, `back_to_menu` — so they don't import
## Main.
extends Control

const MAIN_MENU      = preload("res://scenes/MainMenu.tscn")
const GAME_SCENE     = preload("res://scenes/GameScene.tscn")
const CUSTOMIZE_SCENE = preload("res://scenes/CustomizationScene.tscn")

var _current: Node = null

func _ready() -> void:
    show_main_menu()

func show_main_menu() -> void:
    _swap(MAIN_MENU.instantiate())
    _current.start_game.connect(show_game)
    _current.open_customization.connect(show_customize)

func show_game() -> void:
    _swap(GAME_SCENE.instantiate())
    _current.back_to_menu.connect(show_main_menu)

func show_customize() -> void:
    _swap(CUSTOMIZE_SCENE.instantiate())
    _current.back_to_menu.connect(show_main_menu)

func _swap(new_scene: Node) -> void:
    if _current != null:
        _current.queue_free()
    _current = new_scene
    add_child(new_scene)
