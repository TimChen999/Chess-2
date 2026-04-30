## Singleton holding the currently-active GameConfig. Persisted to
## user://customizations.tres. On first run (no save), generated from
## Defaults.make_default_config().
extends Node

const SAVE_PATH := "user://customizations.tres"

var active_config: GameConfig

func _ready() -> void:
    active_config = _load_or_default()

func _load_or_default() -> GameConfig:
    if ResourceLoader.exists(SAVE_PATH):
        var loaded = ResourceLoader.load(SAVE_PATH)
        if loaded is GameConfig:
            return loaded
        push_warning("GameSettings: customizations.tres present but not GameConfig; using defaults")
    return Defaults.make_default_config()

func save() -> void:
    var err := ResourceSaver.save(active_config, SAVE_PATH)
    if err != OK:
        push_warning("GameSettings: save failed (%d)" % err)

func reset() -> void:
    active_config = Defaults.make_default_config()
    if FileAccess.file_exists(SAVE_PATH):
        DirAccess.remove_absolute(ProjectSettings.globalize_path(SAVE_PATH))
