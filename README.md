# emilia-claude-codex-cli-live2d-widget

A small Windows desktop pet widget that watches your local **Claude Code** and **Codex CLI** sessions, shows real-time quota usage, and renders **Emilia** (Re:Zero -Starting Life in Another World- Lost in Memories) as a Live2D companion you can drag, click, and pin on top of any workspace.

> **Status: bootstrapping.** The skeleton is in place; frontend extraction and slim backend are landing in subsequent commits. See the `feat/widget-transparent-windows` branch on the parent fork (`Alos21750/agents-stage-live2d-vrm3d`) for the in-progress code that will be migrated here.

## What it shows

- **Live2D character** — Emilia (10 outfit variants), idle motions + click-to-play random motion/voice line, drag from any pixel of the character to move the window.
- **Codex quota** — primary / secondary rate limit % remaining.
- **Claude quota** — five-hour and seven-day usage from Anthropic's OAuth `/usage` endpoint, polled every 30s.
- **Per-session status** — which session is active, current state (IDLE / THINKING / TOOLING / RESPONDING), latest event.
- **Transparent, frameless, always-on-top** Electron window.

Out of scope for v1:
- Two-way chat with the agent
- Persona / model / approval workflow

## Architecture

Two-tier:
- `frontend/` — Vite + Vue 3 + PixiJS + pixi-live2d-display + Electron (main + preload).
- `server/` — slim FastAPI + watchfiles process that tails `~/.codex/sessions` and `~/.claude/projects` JSONL files and proxies Anthropic's OAuth usage endpoint.

This is intentionally narrower than the parent project: no chat, no TTS, no LangChain, no RAG, no torch.

## Setup

```powershell
# Clone
git clone https://github.com/Alos21750/emilia-claude-codex-cli-live2d-widget.git
cd emilia-claude-codex-cli-live2d-widget

# Frontend
cd frontend
npm install

# Backend
cd ../server
uv venv
uv sync

# Live2D character assets — Re:Zero LiM Live2D files must already exist on
# disk somewhere (e.g. extracted from your own copy). Run:
cd ../frontend
pwsh ./scripts/setup-emilia-models.ps1 -Source "<path to ReZero LiM Live2D Characters\Live2D Characters>"
```

Optional voice clips are local-only assets generated from a user-supplied YouTube source. The setup script runs `yt-dlp` through `uvx`, so no global `yt-dlp` install is needed. Install `uv` / `uvx` and `ffmpeg`, then run the setup script:

```powershell
winget install astral-sh.uv
# or:
irm https://astral.sh/uv/install.ps1 | iex
winget install ffmpeg
cd frontend
pwsh ./scripts/setup-emilia-voices.ps1
```

## Running

On Windows, after completing setup, you can double-click `launch.bat` from the repo root. It validates the frontend dependencies, backend virtualenv, and local Emilia model assets, then starts the backend, Vite, and Electron widget.

```powershell
# In one terminal: backend
cd server
.\.venv\Scripts\python.exe main.py

# In another: frontend dev server
cd frontend
npm run dev

# In a third: Electron widget
cd frontend
$env:DESKTOP_WIDGET_URL="http://127.0.0.1:5173/"
npm run electron:dev
```

Adjust window size via env vars (defaults 280×400):
```powershell
$env:WIDGET_WIDTH=320
$env:WIDGET_HEIGHT=460
npm run electron:dev
```

## Credits and acknowledgements

This project is **derived from** [Dylin-code/agents-stage-live2d-vrm3d](https://github.com/Dylin-code/agents-stage-live2d-vrm3d), the original visualization console for AI coding agents that pioneered the session-bridge architecture, the dual 2D/3D Live2D / VRM stage, and the OAuth-based Claude Code usage extraction this widget reuses verbatim. **All foundational ideas, the session-bridge runtime, and the Claude usage proxy are Dylin-code's work** — this fork narrows the scope to a single Windows monitor widget while preserving the parent's licensing.

The Re:Zero LiM Live2D character models and voice clips are © Kadokawa / Sekai Project / their respective rightsholders. They are referenced here only via local setup scripts that use your own source files or public links; **none of those assets are committed to this repository**, and use is intended for non-commercial personal experimentation only. Respect the original game's terms of use.

`pixi-live2d-display`, PixiJS, Vue, Electron, FastAPI, and all third-party libraries retain their original licenses.

## License

MIT — see [LICENSE](./LICENSE).
