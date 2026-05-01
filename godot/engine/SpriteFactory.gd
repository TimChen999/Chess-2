## SpriteFactory — procedural pixel-art textures for chess pieces, board
## tiles, ability icons, and indicators. Cached on first request and reused
## for the rest of the session. All sprites are drawn at a 16-pixel native
## grid and displayed via TextureRect with NEAREST filtering, so the player
## sees crisp pixel art at any zoom level.
##
## Design: each piece is hand-designed as an array of 16 strings (one row =
## 16 chars). 'X' marks body pixels; '.' is transparent. _apply_outline()
## then paints OUTLINE color into every transparent pixel that touches a
## body pixel, giving every sprite a clean 1px black border without needing
## the artist to draw it pixel by pixel. A single highlight pixel per piece
## (specified per-shape) finishes the look.
class_name SpriteFactory
extends RefCounted

const NATIVE := 16

# --- Piece palette ---------------------------------------------------------
const WHITE_BODY  := Color(0.95, 0.88, 0.74)
const WHITE_SHADE := Color(0.78, 0.66, 0.45)
const BLACK_BODY  := Color(0.30, 0.25, 0.30)
const BLACK_SHADE := Color(0.16, 0.13, 0.18)
const OUTLINE     := Color(0.06, 0.04, 0.07)

# --- Board palette ---------------------------------------------------------
const TILE_LIGHT_A := Color(0.93, 0.85, 0.66)
const TILE_LIGHT_B := Color(0.89, 0.81, 0.62)
const TILE_DARK_A  := Color(0.55, 0.36, 0.22)
const TILE_DARK_B  := Color(0.50, 0.32, 0.20)

# --- UI palette ------------------------------------------------------------
const ENERGY_FILL   := Color(0.32, 0.78, 0.96)
const ENERGY_FILL_LIGHT := Color(0.62, 0.92, 1.00)
const ENERGY_EMPTY  := Color(0.13, 0.16, 0.22)
const ENERGY_FRAME  := Color(0.04, 0.05, 0.08)

static var _cache: Dictionary = {}

# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

static func piece_texture(piece_id: String, color: int) -> Texture2D:
	var key := "piece:%s:%d" % [piece_id, color]
	if _cache.has(key): return _cache[key]
	var img := _new_image(NATIVE, NATIVE)
	var pat := _pattern_for(piece_id)
	_paint_pattern(img, pat, color)
	_apply_outline(img, OUTLINE)
	_paint_highlights(img, piece_id, color)
	var tex := ImageTexture.create_from_image(img)
	_cache[key] = tex
	return tex

## A piece sprite at arbitrary native size. Renders a small "ghost" version
## used by the customization preview / ability target previews. For the live
## board, prefer piece_texture() — same content, cached per (id, color).
static func piece_texture_size(piece_id: String, color: int, _native: int) -> Texture2D:
	return piece_texture(piece_id, color)   # alias; size is set by TextureRect

static func tile_texture(is_dark: bool) -> Texture2D:
	var key := "tile:%d" % (1 if is_dark else 0)
	if _cache.has(key): return _cache[key]
	var img := _new_image(NATIVE, NATIVE)
	if is_dark: _draw_tile(img, TILE_DARK_A,  TILE_DARK_B)
	else:       _draw_tile(img, TILE_LIGHT_A, TILE_LIGHT_B)
	_cache[key] = ImageTexture.create_from_image(img)
	return _cache[key]

## Energy "card" — a single elixir-style segment (one of ten on the bar).
## State 0=empty, 1=full. Rendered as 12x32 pixels then upscaled.
static func energy_segment_texture(filled: bool) -> Texture2D:
	var key := "energy_seg:%d" % (1 if filled else 0)
	if _cache.has(key): return _cache[key]
	var w := 12; var h := 32
	var img := _new_image(w, h)
	# frame
	_filled_rect(img, 0, 0, w, h, ENERGY_FRAME)
	if filled:
		_filled_rect(img, 2, 2, w - 4, h - 4, ENERGY_FILL.darkened(0.25))
		_filled_rect(img, 2, 2, w - 4, h - 4 - 2, ENERGY_FILL)
		_filled_rect(img, 3, 3, 2, h - 14, ENERGY_FILL_LIGHT)   # gloss
	else:
		_filled_rect(img, 2, 2, w - 4, h - 4, ENERGY_EMPTY)
	_cache[key] = ImageTexture.create_from_image(img)
	return _cache[key]

## Ability icon — 24x24 pixel art icon of either lightning bolt or cannon.
static func ability_icon_texture(kind: int) -> Texture2D:
	var key := "ability:%d" % kind
	if _cache.has(key): return _cache[key]
	var img := _new_image(24, 24)
	if kind == 1:        # SpecialAbilityDef.Kind.CANNON
		_draw_cannon_icon(img)
	elif kind == 2:      # SpecialAbilityDef.Kind.LIGHTNING
		_draw_lightning_icon(img)
	_cache[key] = ImageTexture.create_from_image(img)
	return _cache[key]

# Single static drop-shadow disc. Drawn under pieces.
static func shadow_texture() -> Texture2D:
	var key := "shadow"
	if _cache.has(key): return _cache[key]
	var w := 16; var h := 6
	var img := _new_image(w, h)
	for y in h:
		for x in w:
			var dx := (x - w * 0.5) / (w * 0.5)
			var dy := (y - h * 0.5) / (h * 0.5)
			var d := dx * dx + dy * dy
			if d <= 1.0:
				img.set_pixel(x, y, Color(0, 0, 0, 0.32 * (1.0 - d)))
	_cache[key] = ImageTexture.create_from_image(img)
	return _cache[key]

# ---------------------------------------------------------------------------
# DRAW PRIMITIVES
# ---------------------------------------------------------------------------

static func _new_image(w: int, h: int) -> Image:
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	return img

## Bounds-checked single-pixel write. Named `_put` (not `_set`) because
## Object exposes a virtual `_set(StringName, Variant) -> bool` that this
## would otherwise override and break the parser.
static func _put(img: Image, x: int, y: int, color: Color) -> void:
	if x < 0 or y < 0 or x >= img.get_width() or y >= img.get_height(): return
	img.set_pixel(x, y, color)

static func _filled_rect(img: Image, x: int, y: int, w: int, h: int, color: Color) -> void:
	for yy in range(y, y + h):
		for xx in range(x, x + w):
			_put(img, xx, yy, color)

static func _filled_circle(img: Image, cx: int, cy: int, r: int, color: Color) -> void:
	for yy in range(-r, r + 1):
		for xx in range(-r, r + 1):
			if xx * xx + yy * yy <= r * r:
				_put(img, cx + xx, cy + yy, color)

static func _ring(img: Image, cx: int, cy: int, ro: int, ri: int, color: Color) -> void:
	for yy in range(-ro, ro + 1):
		for xx in range(-ro, ro + 1):
			var d := xx * xx + yy * yy
			if d <= ro * ro and d > ri * ri:
				_put(img, cx + xx, cy + yy, color)

# Outline pass — for every transparent pixel that 4-neighbors at least one
# body pixel, paint it with `outline_color`. Two-pass to avoid mid-pass
# pollution: collect first, then write.
static func _apply_outline(img: Image, outline_color: Color) -> void:
	var to_paint: Array = []
	var w := img.get_width()
	var h := img.get_height()
	for y in h:
		for x in w:
			if img.get_pixel(x, y).a >= 0.5: continue
			var touches := false
			for d: Vector2i in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
				var nx: int = x + d.x
				var ny: int = y + d.y
				if nx < 0 or ny < 0 or nx >= w or ny >= h: continue
				if img.get_pixel(nx, ny).a >= 0.5:
					touches = true; break
			if touches: to_paint.append(Vector2i(x, y))
	for p in to_paint:
		img.set_pixel(p.x, p.y, outline_color)

# ---------------------------------------------------------------------------
# PIECE PATTERNS — 'X' = body, '.' = transparent. Outline added by pass.
# Each pattern is laid out so the silhouette never touches the image edge,
# giving the outline pass room to draw a 1-pixel border on every side.
# ---------------------------------------------------------------------------

## All piece silhouettes are designed at 16x16 with clear gestures: small
## features at the top distinguish piece TYPE; the bodies vary in width
## and height to give each piece a unique posture even at thumbnail size.
## 1-pixel gaps in crenellations / crowns / mitre slits get auto-filled by
## the outline pass into dark separator lines, which reads exactly like
## chess engraving in pixel art.

const PAWN_PATTERN := [
	"................",
	"................",
	"......XXXX......",
	".....XXXXXX.....",
	".....XXXXXX.....",
	"......XXXX......",
	".......XX.......",
	"......XXXX......",
	".....XXXXXX.....",
	".....XXXXXX.....",
	"......XXXX......",
	".....XXXXXX.....",
	"....XXXXXXXX....",
	"...XXXXXXXXXX...",
	"..XXXXXXXXXXXX..",
	"................",
]

const ROOK_PATTERN := [
	"................",
	"..XX.XX.XX.XX...",
	"..XX.XX.XX.XX...",
	"..XX.XX.XX.XX...",
	"..XXXXXXXXXXX...",
	"..XXXXXXXXXXX...",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	"...XXXXXXXXX....",
	".XXXXXXXXXXXXX..",
	".XXXXXXXXXXXXX..",
	"................",
]

## Horse silhouette facing left — pointed muzzle on the left, mane curving
## down the right side, neck connecting into a small base.
const KNIGHT_PATTERN := [
	"................",
	"......XX........",
	".....XXXX.......",
	"....XXXXXX......",
	"...XXXXXXXX.....",
	"..XXX.XXXXXX....",
	"..XXXXXXXXXXX...",
	"...XXXXXXXXXX...",
	"....XXXXXXXXX...",
	".....XXXXXXXX...",
	".....XXXXXXXX...",
	"....XXXXXXXXX...",
	"...XXXXXXXXXX...",
	"..XXXXXXXXXXXX..",
	"..XXXXXXXXXXXX..",
	"................",
]

## Tall mitre with the diagonal slit at row 5 — the 3-px gap there gets
## auto-filled by the outline pass into a dark slash, which is exactly the
## bishop's signature engraving.
const BISHOP_PATTERN := [
	"................",
	".......XX.......",
	"......XXXX......",
	"......XXXX......",
	".....XXXXXX.....",
	".....X....X.....",
	".....XXXXXX.....",
	"......XXXX......",
	"......XXXX......",
	".....XXXXXX.....",
	"....XXXXXXXX....",
	"....XXXXXXXX....",
	"...XXXXXXXXXX...",
	"..XXXXXXXXXXXX..",
	"..XXXXXXXXXXXX..",
	"................",
]

## Six-pointed crown — single-pixel-wide spikes with 1-px gaps between.
## After outline, the gaps render as dark valleys, giving a notched crown.
const QUEEN_PATTERN := [
	"................",
	"..X.X.X.X.X.X...",
	"..X.X.X.X.X.X...",
	"..XXXXXXXXXXX...",
	"..XXXXXXXXXXX...",
	"...XXXXXXXXX....",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	".....XXXXX......",
	"....XXXXXXX.....",
	"....XXXXXXX.....",
	"...XXXXXXXXX....",
	"..XXXXXXXXXXX...",
	".XXXXXXXXXXXXX..",
	".XXXXXXXXXXXXX..",
	"................",
]

## Distinctive cross above the crown band, then a tall slim body.
const KING_PATTERN := [
	"................",
	".......XX.......",
	".......XX.......",
	".....XXXXXX.....",
	".......XX.......",
	"...XXXXXXXXXX...",
	"...XXXXXXXXXX...",
	"....XXXXXXXX....",
	".....XXXXXX.....",
	"....XXXXXXXX....",
	"....XXXXXXXX....",
	"...XXXXXXXXXX...",
	"..XXXXXXXXXXXX..",
	".XXXXXXXXXXXXX..",
	".XXXXXXXXXXXXX..",
	"................",
]

static func _pattern_for(piece_id: String) -> Array:
	match piece_id:
		"pawn":   return PAWN_PATTERN
		"rook":   return ROOK_PATTERN
		"knight": return KNIGHT_PATTERN
		"bishop": return BISHOP_PATTERN
		"queen":  return QUEEN_PATTERN
		"king":   return KING_PATTERN
	return PAWN_PATTERN

static func _paint_pattern(img: Image, pattern: Array, color: int) -> void:
	var body: Color  = WHITE_BODY  if color == 0 else BLACK_BODY
	var shade: Color = WHITE_SHADE if color == 0 else BLACK_SHADE
	var rows: int = mini(pattern.size(), img.get_height())
	for y in rows:
		var row: String = pattern[y]
		var w: int = mini(row.length(), img.get_width())
		for x in w:
			if row[x] == 'X':
				img.set_pixel(x, y, body)
	## Bottom-edge shading — repaint the single lowest body pixel of each
	## column with `shade`. Gives a subtle ground-anchored feel without
	## breaking the silhouette into "two stacked colors".
	for x in img.get_width():
		for y in range(img.get_height() - 1, -1, -1):
			if img.get_pixel(x, y).a >= 0.5:
				img.set_pixel(x, y, shade)
				break

## No per-piece highlight pass — the silhouettes read clean enough with
## body + outline + bottom-shade. Kept as a no-op so callers don't need to
## branch.
static func _paint_highlights(_img: Image, _piece_id: String, _color: int) -> void:
	pass

# ---------------------------------------------------------------------------
# BOARD TILES
# ---------------------------------------------------------------------------

static func _draw_tile(img: Image, base: Color, alt: Color) -> void:
	var w := img.get_width()
	var h := img.get_height()
	## 2x2 dither — every other 2x2 block uses the alt color. This adds a
	## subtle pixel-art texture that reads as a wood grain at distance but
	## resolves into clean dither up close.
	for y in h:
		for x in w:
			var c := base
			if ((x >> 1) + (y >> 1)) % 3 == 0:
				c = alt
			img.set_pixel(x, y, c)
	## Inset darker border to give each tile its own outline.
	var border := base.darkened(0.18)
	for x in w:
		img.set_pixel(x, 0, border)
		img.set_pixel(x, h - 1, border)
	for y in h:
		img.set_pixel(0, y, border)
		img.set_pixel(w - 1, y, border)

# ---------------------------------------------------------------------------
# ABILITY ICONS
# ---------------------------------------------------------------------------

static func _draw_lightning_icon(img: Image) -> void:
	## Bolt silhouette — angled jagged shape, drawn as a sequence of
	## short rectangles rather than a single polygon so it reads as pixel art.
	var bolt := Color(1.00, 0.92, 0.30)
	var bolt_dark := Color(0.85, 0.65, 0.10)
	## Rows are exactly 14 chars wide so the silhouette stays symmetric
	## inside the 24x24 image (centered with ox=5, oy=5).
	var rows := [
		"..............",
		"...XXXXX......",
		"..XXXXXX......",
		".XXXXXXX......",
		".XXXXXX.......",
		"XXXXXX........",
		"XXXXX.........",
		"XXXXXXXXXXX...",
		".XXXXXXXXX....",
		"....XXXXXX....",
		"....XXXXX.....",
		"...XXXX.......",
		"..XXX.........",
		"..XX..........",
	]
	## Center 14x14 inside 24x24
	var ox := 5; var oy := 5
	for y in rows.size():
		var r: String = rows[y]
		for x in r.length():
			if r[x] == 'X':
				img.set_pixel(ox + x, oy + y, bolt)
	_apply_outline(img, bolt_dark)
	_apply_outline(img, OUTLINE)

static func _draw_cannon_icon(img: Image) -> void:
	## Concentric rings — the unicode ◎ but as pixel art.
	var inner := Color(1.00, 0.55, 0.20)
	var outer := Color(0.92, 0.40, 0.18)
	_filled_circle(img, 12, 12, 9, outer)
	_ring(img, 12, 12, 7, 5, Color(0, 0, 0, 0))
	_filled_circle(img, 12, 12, 4, inner)
	_filled_circle(img, 11, 11, 1, Color(1.0, 0.85, 0.55))
	_apply_outline(img, OUTLINE)
