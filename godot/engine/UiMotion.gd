## UiMotion — shared helpers for the "motion is information" treatment
## (PIECE-VARIANTS.md §4.7). Centralizes the alpha-pulse and scale-pulse
## tween shapes used by:
##   - selected-piece outline glow / scale pulse
##   - move-overlay alpha pulse (legal-target highlights)
##   - ability-HUD ready pulse
##   - ability-target preview pulse
##   - cannon plus-shape telegraph
##   - debris warning squares
##
## All helpers register their tweens as children of the target node so the
## tween dies automatically when the node is freed (e.g. on _render rebuild).
## Returned Tween reference is mostly informational — caller can ignore it.
class_name UiMotion
extends RefCounted

## Loop modulate.a between `low` and `high` over `period` seconds. Phase 0
## starts at `low` and rises first. Cancellable by killing the returned
## tween or freeing the node. The pulse uses a sine-shaped ease so all
## pulsing surfaces stay visually phase-coherent.
static func pulse_alpha(node: CanvasItem, period: float, low: float, high: float) -> Tween:
	if not is_instance_valid(node): return null
	var tw := node.create_tween().set_loops()
	tw.tween_property(node, "modulate:a", high, period * 0.5) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tw.tween_property(node, "modulate:a", low, period * 0.5) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	node.modulate.a = low
	return tw

## Loop scale between `lo_scale` and `hi_scale`. Pivot defaults to the
## node's current pivot_offset; caller can set node.pivot_offset before
## calling for proper centered breathing.
static func pulse_scale(node: Control, period: float, lo_scale: float, hi_scale: float) -> Tween:
	if not is_instance_valid(node): return null
	node.pivot_offset = node.size * 0.5
	var tw := node.create_tween().set_loops()
	var lo := Vector2(lo_scale, lo_scale)
	var hi := Vector2(hi_scale, hi_scale)
	tw.tween_property(node, "scale", hi, period * 0.5) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tw.tween_property(node, "scale", lo, period * 0.5) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	node.scale = lo
	return tw

## Mix between two tints on a ColorRect-style node — same shape as alpha
## pulse but along the full RGBA. Used for "ready" indicators where a
## pulsing tint reads better than a pulsing alpha.
static func pulse_color(node: CanvasItem, period: float,
						lo: Color, hi: Color) -> Tween:
	if not is_instance_valid(node): return null
	var tw := node.create_tween().set_loops()
	tw.tween_property(node, "modulate", hi, period * 0.5) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tw.tween_property(node, "modulate", lo, period * 0.5) \
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	node.modulate = lo
	return tw

## One-shot animation playback — swap `sprite.texture` through `frames` over
## `total_duration`, optionally delayed by `delay`. Schedules its swaps via
## tween_callback on the supplied tween, so the caller can compose this
## with other property tweens already in flight on the same Tween.
##
## Returns nothing — caller awaits the parent tween.finished as usual.
static func schedule_frame_swaps(tween: Tween, sprite: TextureRect,
								  frames: Array, total_duration: float,
								  delay: float = 0.0) -> void:
	if frames.is_empty(): return
	if not is_instance_valid(sprite): return
	var step: float = total_duration / float(frames.size())
	for i in frames.size():
		var f: Texture2D = frames[i]
		tween.tween_callback(_swap_texture.bind(sprite, f)).set_delay(delay + i * step)

static func _swap_texture(sprite: TextureRect, tex: Texture2D) -> void:
	if is_instance_valid(sprite):
		sprite.texture = tex
