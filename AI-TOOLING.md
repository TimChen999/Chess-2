# AI Tooling for Claude Code

This project is configured to give Claude Code two kinds of "senses" beyond reading source files:

1. **Visual review** (Playwright MCP — installed, currently dormant) — runs a headless Chromium that Claude can drive, screenshot, and inspect. Useless against the native Godot build; activates once an HTML5 export exists. Configured below.
2. **Sprite generation** (procedural PIL drawer + PixelLab Python SDK) — all sprite-design code and docs live under [tools/sprites/](tools/sprites/). The full 18-piece chess suite has been generated; outputs live at [godot/assets/sprites/anim/pieces/](godot/assets/sprites/anim/pieces/). See [tools/sprites/README.md](tools/sprites/README.md) for the full pipeline, lessons learned, and regen instructions.

The active game lives in [godot/](godot/). The visual-review tooling only becomes useful after `Project → Export → Web` produces a runnable HTML5 build.

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

## 2. Sprite generation

Moved to [tools/sprites/README.md](tools/sprites/README.md) — covers the procedural PIL drawer (`generate_sprites.py`), the PixelLab AI generator (`gen_sprites.py`), the head-only inpaint helper (`inpaint_heads.py`), regen instructions, and lessons learned. The closed-loop workflow with Playwright (re-export → screenshot → critique → re-prompt) is also documented there.

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
- **PixelLab**: pay-per-use credits. The full 18-sprite chess set cost ~10 API calls (1 anchor + 5 base + 3 variants + 1 retry). Black versions are procedurally recolored from white via local PIL — no API calls. Total cost for the current state: a few cents to maybe a dollar.
- **Future regenerations**: each `--only <piece>` run is 1 API call. Iterating on a single piece's prompt costs cents.
- **Tier 2 upgrade (Replicate + LoRA)**: ~$15 one-time to train a custom LoRA on hand-curated reference sprites if PixelLab can't hit the exact aesthetic. Would replace PixelLab calls with Replicate calls in the same orchestration script.
