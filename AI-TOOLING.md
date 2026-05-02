# AI Tooling for Claude Code

This project is configured to give Claude Code two kinds of "senses" beyond reading source files:

1. **Visual review** (Playwright MCP — installed, currently dormant) — runs a headless Chromium that Claude can drive, screenshot, and inspect. Useless against the native Godot build; activates once an HTML5 export exists.
2. **Sprite generation** (PixelLab MCP — planned) — Claude generates pixel-art sprites directly via the PixelLab API and they slot into the existing [generate_sprites.py](generate_sprites.py) pipeline.

The active game lives in [godot/](godot/). Anything below that talks about visual review only becomes useful after `Project → Export → Web` produces a runnable HTML5 build.

---

## 1. Installed: Playwright MCP

### What it is

[Playwright MCP](https://github.com/microsoft/playwright-mcp) is a Model Context Protocol server that exposes Chromium browser automation as tools Claude can call mid-conversation. Once a target URL exists, Claude can navigate, screenshot, click, read the DOM, and inspect the console — all in one turn.

### How it's configured

| File | Role |
|---|---|
| [.mcp.json](.mcp.json) | Declares the `playwright` MCP server, project-scoped (committed) |
| `.claude/settings.json` | Pre-approves the server via `enabledMcpjsonServers` so it auto-starts (gitignored — machine-specific) |
| `C:\Users\timch\AppData\Local\ms-playwright\` | Cached Chromium binaries (~500MB, machine-local, shared across all Playwright projects) |

The `.mcp.json` invocation:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--headless", "--browser", "chromium", "--allow-unrestricted-file-access"]
    }
  }
}
```

Flags:
- `--headless` — runs Chromium without a visible window. Faster, no popups. Screenshots still work normally.
- `--browser chromium` — uses the bundled Chromium, not your system Chrome.
- `--allow-unrestricted-file-access` — lets the browser load `file://` URLs directly, so no local server is needed once an export exists.

### Activating the visual loop

Playwright is currently dormant — there's no web target. Two paths to activate:

**(a) Export Godot to HTML5/WebAssembly** (recommended)
1. Open the Godot editor on [godot/project.godot](godot/project.godot).
2. `Project → Export → Web` (install the Web export template if prompted — Godot offers it automatically).
3. Pick an output dir, e.g. `godot/export/web/`. Godot produces `index.html`, `.wasm`, `.pck`, `.js`.
4. Ask Claude: *"Open `godot/export/web/index.html` and screenshot the main menu."* Playwright will navigate the file:// URL and the loop is live.
5. Re-export after significant visual changes. Until then, screenshots match the export, not the editor state.

**(b) One-off screenshots from the Godot editor or runtime**
Drop a PNG into chat (drag-and-drop or path reference). Claude reads it via the Read tool. No MCP needed. Fine for occasional design checks; doesn't enable autonomous loops.

**(c) Godot-side debug screenshotter**
Add a script in your Godot project that calls `get_viewport().get_texture().get_image().save_png("user://latest.png")` on a hotkey. Claude `Read`s the file when needed. Works without a Web export but requires Godot to be running.

### Available browser tools (post-activation)

Once Claude has a target URL, ~25 tools become available, prefixed `mcp__playwright__`. The most useful for this project:

| Tool | What Claude does with it |
|---|---|
| `browser_navigate` | Open the exported `index.html` or any URL |
| `browser_take_screenshot` | Capture full page or a specific element by selector |
| `browser_snapshot` | Read the accessibility tree (semantic, faster than a screenshot for layout checks) |
| `browser_click` | Click buttons, pieces, menu items — drives the game to specific states |
| `browser_evaluate` | Run arbitrary JS in the page (inspect engine state via the Godot Web export's window globals) |
| `browser_console_messages` | Read console errors/warnings from Godot's runtime |
| `browser_resize` | Test layouts at different viewport sizes |
| `browser_wait_for` | Wait for animations/state changes before screenshotting |

### Caveats with Godot HTML5

- The Godot Web build is a single canvas. Element-targeted screenshots (`target: "selector"`) won't reach into the game — everything inside the canvas is opaque pixels to the DOM. Workaround: full-canvas screenshots only, plus crop in post if needed.
- `browser_click` on canvas coordinates works (Playwright passes pixel-space coords). Driving menus requires knowing pixel positions, not selectors.
- Console output from GDScript `print()` shows up in `browser_console_messages` once the export is loaded.

---

## 2. Planned: PixelLab MCP (sprite generation)

> **Status:** not installed yet. Requires an API key from [pixellab.ai](https://www.pixellab.ai). This section documents the intended setup and integration plan for the Godot sprite pipeline.

### Why this over alternatives

| Tool | Verdict for chess pieces |
|---|---|
| **PixelLab** | Purpose-built for game sprites, official MCP, handles style consistency across pieces natively. **Recommended start.** |
| **Retro Diffusion** (via Replicate) | Excellent pixel-art models, no native MCP — needs a Python wrapper. Best if PixelLab can't hit the look. |
| **Scenario.com** | Has MCP, broader (3D/audio/video too), pay-as-you-go. Overkill for chess. |
| **OpenAI DALL-E / Flux / SDXL** | Generic image gen. Produces "pixel-styled" art that breaks at small sprite sizes. Avoid. |
| **Local ComfyUI + LoRAs** | Free after setup, full control, heavy install. Worth it only for 100+ assets long-term. |

### Setup steps (when ready)

1. Sign up at [pixellab.ai](https://www.pixellab.ai), grab an API key.
2. Add to `.mcp.json` next to `playwright`:
   ```json
   {
     "mcpServers": {
       "playwright": { ... existing ... },
       "pixellab": {
         "command": "npx",
         "args": ["-y", "@pixellab/mcp@latest"],
         "env": {
           "PIXELLAB_API_KEY": "${env:PIXELLAB_API_KEY}"
         }
       }
     }
   }
   ```
3. Set the env var in PowerShell: `$env:PIXELLAB_API_KEY = "your_key_here"` (or add it via System Properties → Environment Variables to persist).
4. Pre-approve in `.claude/settings.json`: `"enabledMcpjsonServers": ["playwright", "pixellab"]`.
5. Restart Claude Code. Tools become available as `mcp__pixellab__*`.

### How it integrates with `generate_sprites.py`

[generate_sprites.py](generate_sprites.py) already produces the Godot sprite atlas under [godot/assets/sprites/](godot/assets/sprites/) — pieces (`pawn`, `rook`, `knight`, `bishop`, `queen`, `king`, plus variants `bandit_pawn`, `assassin_bishop`, `alter_knight`), animation strips (`static`, `move`, `attack`, `hit`, `death`), and FX (`cannon_resolve`, `debris_fall`, `lightning_strike`).

It's currently fully procedural. PixelLab and procedural fit together rather than competing. Three integration patterns, in increasing complexity:

#### Pattern A: PixelLab replaces `generate_sprites.py` entirely
- PixelLab generates 12 finished piece PNGs into `godot/assets/sprites/anim/pieces/...`.
- The procedural script is retired.
- **Tradeoff:** lose all parametric variant control (recolor, hue-shift, outline tweaks, animation strip packing). Every variant requires a fresh API call.

#### Pattern B: PixelLab generates *base* sprites, `generate_sprites.py` does variants and animation packing ← **recommended**
- PixelLab generates a polished **base static sprite per piece type** (6 sprites: pawn, knight, bishop, rook, queen, king).
- `generate_sprites.py` is repurposed from "create from scratch" to "transform": it loads the base PNGs and produces:
  - White/black team recolors (currently driven by the `PALETTES` dict)
  - Variant hue-shifts (per [PIECE-VARIANTS.md](PIECE-VARIANTS.md))
  - Outline / shadow passes
  - Frame-strip packing for `move`, `attack`, `hit`, `death` animations
- **Tradeoff:** best of both — AI gives the artistic look that's hard to write rules for, code gives cheap deterministic multiplication.
- **Cost:** ~6 API calls for the entire base set, then variants are free forever.

#### Pattern C: AI as reference, procedural at runtime
- Use PixelLab to generate concept art only.
- Manually translate the look back into procedural drawing rules in `generate_sprites.py`.
- **Tradeoff:** most labor-intensive, but the build remains fully deterministic with no PNG assets shipped beyond what code emits.
- Only worth it if asset determinism is a hard requirement.

### The closed loop with Playwright (post Godot export)

The combined workflow is the actual reason both MCPs are useful together:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   1. PixelLab MCP generates a sprite                        │
│      (mcp__pixellab__generate_image)                        │
│              │                                              │
│              ▼                                              │
│   2. Claude saves it to godot/assets/sprites/...            │
│              │                                              │
│              ▼                                              │
│   3. python generate_sprites.py rebuilds variants/strips    │
│              │                                              │
│              ▼                                              │
│   4. (Manual) Re-export Godot to godot/export/web/          │
│      — or skip and rely on a debug screenshotter            │
│              │                                              │
│              ▼                                              │
│   5. Playwright loads the exported index.html and           │
│      screenshots the board in actual game context —         │
│      against light and dark squares, alongside siblings     │
│      (mcp__playwright__browser_take_screenshot)             │
│              │                                              │
│              ▼                                              │
│   6. Claude critiques: silhouette, palette match,           │
│      readability at game scale, consistency                 │
│              │                                              │
│              ▼                                              │
│   7. Claude regenerates with adjusted prompt → loop         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

The re-export step (4) is the friction. Until a Godot CLI export script lives in this repo (e.g. `godot --headless --export-release "Web" godot/export/web/index.html`), step 4 is manual. Once that's automated, the loop runs end-to-end without intervention.

---

## 3. Configuration reference

| File | Committed? | Purpose |
|---|---|---|
| [.mcp.json](.mcp.json) | yes | Project-scoped MCP server declarations |
| `.claude/settings.json` | no (`.claude/` is in `.gitignore` because it has machine-specific paths) | Pre-approves MCP servers, allows specific Bash commands without prompting |
| `.claude/settings.local.json` | no | Personal overrides — never commit |

### Adding a new MCP server

1. Add an entry under `mcpServers` in `.mcp.json`.
2. Add the server name to `enabledMcpjsonServers` in `.claude/settings.json`.
3. Restart Claude Code so it loads the new server.

### Removing Playwright

1. Delete the `playwright` entry from `.mcp.json`.
2. Remove `"playwright"` from `enabledMcpjsonServers`.
3. Optional: delete `C:\Users\timch\AppData\Local\ms-playwright\` to reclaim ~500MB, or run `npx playwright uninstall --all`.

---

## 4. Cost notes

- **Playwright**: zero recurring cost. One-time ~500MB disk + bandwidth for Chromium. No API.
- **PixelLab**: pay-per-use credits (cents per sprite). For the chess piece set, expect single-digit dollars to land a polished base set, then $0 forever for procedural variants under Pattern B.
- **Tier 2 upgrade (Replicate + LoRA)**: ~$15 one-time to train a custom LoRA on hand-curated reference sprites if PixelLab can't hit the exact aesthetic. Would replace PixelLab calls with Replicate calls in the same MCP slot.
