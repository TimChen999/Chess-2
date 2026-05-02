# AI Tooling for Claude Code

This project is configured to give Claude Code two kinds of "senses" beyond reading source files:

1. **Visual review** (installed) — Claude can open the running game in a real browser, take screenshots, click through UI, read the DOM/console, and critique what it sees.
2. **Sprite generation** (planned) — Claude can generate pixel-art sprites directly via the PixelLab API, using the existing game as visual context.

The combination closes a loop the developer otherwise has to run by hand: *generate sprite → drop into game → see how it looks in context → regenerate*.

---

## 1. Installed: Playwright MCP (visual review)

### What it is

[Playwright MCP](https://github.com/microsoft/playwright-mcp) is a Model Context Protocol server that exposes Chromium browser automation as tools Claude can call mid-conversation. When asked something like *"open the game and tell me what's wrong with the menu"*, Claude can navigate, screenshot, and respond — all in one turn — without the user manually capturing or pasting images.

### How it's configured

| File | Role |
|---|---|
| [.mcp.json](.mcp.json) | Declares the `playwright` MCP server, project-scoped (committed to git so any machine that clones the repo gets the same setup) |
| [.claude/settings.json](.claude/settings.json) | Pre-approves the server via `enabledMcpjsonServers` so it auto-starts without a permission prompt |
| `C:\Users\timch\AppData\Local\ms-playwright\` | Cached Chromium binaries (~400MB, machine-local, shared across all Playwright projects) |

The current `.mcp.json` invocation:

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
- `--browser chromium` — uses the bundled Chromium (not your system Chrome).
- `--allow-unrestricted-file-access` — lets the browser load `file:///c:/Users/timch/Documents/ML-Sandbox/Chess-2/index.html` directly, so no local server is needed for visual review.

### Available browser tools

Once Claude Code starts a session in this repo, ~25 tools become available, prefixed `mcp__playwright__`. The most useful for this project:

| Tool | What Claude does with it |
|---|---|
| `browser_navigate` | Open `index.html` or any URL |
| `browser_take_screenshot` | Capture the full page or a specific element by selector |
| `browser_snapshot` | Read the accessibility tree (semantic, faster than a screenshot for layout checks) |
| `browser_click` | Click buttons / pieces / menu items |
| `browser_evaluate` | Run arbitrary JS in the page (inspect game state, force a board position) |
| `browser_console_messages` | Read console errors/warnings |
| `browser_resize` | Test layouts at different viewport sizes |
| `browser_wait_for` | Wait for animations/state changes before screenshotting |

### How to use it (prompt patterns)

You don't call the tools directly — you ask in natural language and Claude chains the calls.

**Single-shot review:**
> "Open `index.html` and screenshot the main menu. Tell me three things that look weak."

**State-driven check:**
> "Load the game, click 'Local 2-player', start a match on the Moon stage, and screenshot the board after move 1.e4."

**Sprite-by-sprite audit:**
> "Open the customize screen and screenshot each piece variant at 2x resolution. List pixel-alignment or silhouette issues."

**Iterate-until-good:**
> "Screenshot the title screen, identify the weakest visual element, make one CSS change to improve it, screenshot again. Repeat 3 times."

**Combined visual + console:**
> "Start a match on the Moon stage and report any console errors alongside what's on screen."

### When to use it vs. dropping a screenshot manually

| Use Playwright MCP when... | Just paste a screenshot when... |
|---|---|
| You want Claude to drive the game to a specific state | You already have the exact frame you want critiqued |
| You're iterating many rounds (autonomous loops) | One-off design check |
| You want console + DOM + visual combined | Visual-only is enough |
| You're AFK and want a `/loop` to refine visuals | Quick targeted feedback |

---

## 2. Planned: PixelLab MCP (sprite generation)

> **Status:** not installed yet. Requires an API key from [pixellab.ai](https://www.pixellab.ai). This section documents the intended setup and integration plan.

### What it is

[PixelLab MCP](https://github.com/pixellab-code/pixellab-mcp) is a sprite generation service purpose-built for game pixel art. Unlike generic image generators (DALL-E, Flux, SDXL), it understands grid alignment, palette discipline, silhouette readability, and animation frame consistency — the things that matter for actual game sprites.

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
3. Set the env var in PowerShell: `$env:PIXELLAB_API_KEY = "your_key_here"` (or add it to your user environment via System Properties so it persists).
4. Pre-approve in `.claude/settings.json`: `"enabledMcpjsonServers": ["playwright", "pixellab"]`.
5. Restart Claude Code. Tools become available as `mcp__pixellab__*`.

### Expected tools

PixelLab's MCP exposes generation primitives. Likely names (verify against the GitHub repo when installing):

- `generate_image` — single sprite from a text prompt
- `generate_with_reference` — sprite that matches the style of an input image (the consistency primitive)
- `animate_sprite` — generate idle/walk/etc. animation frames for an existing sprite
- `generate_rotation` — 4 or 8 directional views of a character
- `generate_tileset` — seamless tileable terrain

### How it integrates with `generate_sprites.py`

The repo already has [generate_sprites.py](generate_sprites.py), which does **procedural** sprite generation: deterministic, free, but stylistically constrained. PixelLab and procedural are not competing — they fit together.

Three integration patterns, in increasing complexity:

#### Pattern A: PixelLab replaces `generate_sprites.py` entirely
- PixelLab generates 12 finished piece PNGs into `assets/sprites/` (or wherever the JS loads from).
- The procedural script is retired.
- **Tradeoff:** lose all parametric variant control (recolor, hue-shift, outline tweaks, spritesheet packing). Every variant requires a fresh API call.

#### Pattern B: PixelLab generates *base* sprites, `generate_sprites.py` does variants ← **recommended**
- PixelLab generates **one polished base sprite per piece type** (6 sprites: pawn, knight, bishop, rook, queen, king).
- `generate_sprites.py` is repurposed from "create from scratch" to "transform": it loads the base PNGs and produces:
  - White/black team recolors
  - Variant hue-shifts (per [PIECE-VARIANTS.md](PIECE-VARIANTS.md))
  - Outline / shadow passes
  - Final spritesheet packing
- **Tradeoff:** best of both — AI gives the artistic look that's hard to write rules for, code gives the cheap deterministic multiplication.
- **Cost:** ~6 API calls for the entire base set, then variants are free forever.

#### Pattern C: AI as reference, procedural at runtime
- Use PixelLab to generate concept art only.
- Manually translate the look back into procedural drawing rules in `generate_sprites.py`.
- **Tradeoff:** most labor-intensive, but builds remain fully deterministic with no PNG assets shipped.
- Only worth it if asset deterministic-ness is a hard requirement.

### The closed loop with Playwright

The combined workflow is the actual reason both MCPs are useful together:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   1. PixelLab MCP generates a sprite                        │
│      (mcp__pixellab__generate_image)                        │
│              │                                              │
│              ▼                                              │
│   2. Claude saves it to assets/sprites/knight.png           │
│              │                                              │
│              ▼                                              │
│   3. Playwright MCP loads index.html with the new sprite    │
│      (mcp__playwright__browser_navigate)                    │
│              │                                              │
│              ▼                                              │
│   4. Playwright screenshots the piece in actual game        │
│      context — on the board, against both light and dark    │
│      squares, alongside the other pieces                    │
│      (mcp__playwright__browser_take_screenshot)             │
│              │                                              │
│              ▼                                              │
│   5. Claude critiques: silhouette, palette match,           │
│      readability at game scale, consistency with siblings   │
│              │                                              │
│              ▼                                              │
│   6. Claude regenerates with adjusted prompt → loop         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Neither MCP alone produces this result. PixelLab in isolation only knows "looks good as a 256×256 preview." Only Playwright tells the loop "looks good on the chessboard at runtime."

### Sample prompts (post-install)

**Initial generation:**
> "Generate a base white queen sprite at 64×64 in a clean retro pixel-art style with strong silhouette. Use it as the style reference and generate the other 5 piece types matching it. Save to `assets/sprites/base/`."

**Generate + verify in-game:**
> "Generate a new knight sprite. Save it as `assets/sprites/base/knight.png`, run `python generate_sprites.py` to rebuild the spritesheet, then open `index.html` and screenshot the board with knights placed. Tell me if the new knight reads well against both square colors."

**Variant tuning:**
> "The shadow variant from PIECE-VARIANTS.md doesn't look distinct enough from the base. Generate three alternative shadow-style references via PixelLab, screenshot each rendered in-game, and recommend which works best."

---

## 3. Configuration reference

### Files involved

| File | Committed? | Purpose |
|---|---|---|
| [.mcp.json](.mcp.json) | yes | Project-scoped MCP server declarations |
| [.claude/settings.json](.claude/settings.json) | no (in `.gitignore` because it has machine-specific paths) | Pre-approves MCP servers, allows specific Bash commands without prompting |
| `.claude/settings.local.json` | no | Personal overrides — never commit |

### Adding a new MCP server

1. Add an entry under `mcpServers` in `.mcp.json`.
2. Add the server name to `enabledMcpjsonServers` in `.claude/settings.json` (otherwise Claude prompts for permission on session start).
3. Restart Claude Code so it loads the new server.

### Removing Playwright

1. Delete the `playwright` entry from `.mcp.json`.
2. Remove `"playwright"` from `enabledMcpjsonServers` in `.claude/settings.json`.
3. Optional: delete `C:\Users\timch\AppData\Local\ms-playwright\` to reclaim disk space (~400MB), or run `npx playwright uninstall --all`.

---

## 4. Cost notes

- **Playwright**: zero recurring cost. One-time ~400MB disk + bandwidth for Chromium. No API.
- **PixelLab**: pay-per-use credits (cents per sprite). For the chess piece set, expect single-digit dollars to land a polished base set, then $0 forever for procedural variants under Pattern B.
- **Tier 2 upgrade (Replicate + LoRA)**: ~$15 one-time to train a custom LoRA on hand-curated reference sprites if PixelLab can't hit the exact aesthetic. Would replace PixelLab calls with Replicate calls in the same MCP slot.
