**繁體中文** · [English](README.en.md) · [日本語](README.ja.md)

# ✨ Emilia Claude / Codex Live2D 桌寵

Live2D 桌寵在你電腦角落看顧 Claude Code 與 Codex 的工作狀態。

<p align="center">
  <img src="docs/images/widget-bubbles.png" alt="Emilia Live2D 桌寵主畫面截圖" width="280">
</p>

<p align="center">
  <strong>Windows · Electron 30 · Vue 3 · FastAPI</strong>
</p>

## 功能特色

- 🎀 角色 picker：內建 10 種 Emilia 造型變體。
- 😊 點一下角色可播放表情動作與隨機台詞。
- 🖱️ 按住角色即可拖曳到桌面任何角落。
- 📊 Codex / Claude 配額即時刷新：Claude 5h/7d，Codex P/S。
- ⚙️ 可調 zoom、resolution、FPS、置頂、髮絲物理、字幕與音量。
- 🪟 透明、無框、Always-on-top，適合放在螢幕邊角。
- 🔌 本機監看 Claude Code 與 Codex CLI session，不需要雲端後台。

## 截圖

<p align="center">
  <img src="docs/images/widget-bubbles.png" alt="主畫面：Emilia、配額泡泡與底部狀態 chip" width="360">
</p>

主畫面顯示 Emilia Live2D、Claude / Codex 配額泡泡，以及底部狀態 chip。這張是目前 README 使用的參考圖，可自行替換成最新截圖。

<p align="center">
  <img src="docs/images/widget-old.png" alt="舊版 widget 畫面參考" width="360">
</p>

舊版畫面保留作為視覺演進參考，方便比較泡泡、角色位置與透明視窗效果。

## 安裝

先準備：Node.js 20+、[uv](https://astral.sh/uv)、PowerShell 5+，以及你自己解出的 Re:Zero LiM Live2D 角色檔案。

```powershell
# 1) Clone
git clone https://github.com/Alos21750/emilia-claude-codex-cli-live2d-widget.git
cd emilia-claude-codex-cli-live2d-widget

# 2) Frontend
cd frontend
npm install

# 3) Backend (uv-managed)
cd ../server
uv venv
uv sync

# 4) Live2D character assets — needs YOUR copy of the ReZero LiM Live2D files
cd ../frontend
pwsh ./scripts/setup-emilia-models.ps1 -Source "<path to ReZero LiM Live2D Characters\Live2D Characters>"
```

## 選用：語音 clips

語音 clips 是本機產生的選用素材，腳本會透過 `uvx` 按需執行 `yt-dlp`，不需要全域安裝 `yt-dlp`。語音內容有著作權，請只用於個人、非商業用途。

```powershell
winget install ffmpeg
# uv supplies yt-dlp on demand (winget install astral-sh.uv if you don't have it yet)
cd frontend
pwsh ./scripts/setup-emilia-voices.ps1
```

產生後會得到 51 段常見情緒與互動用的語音 clips；README 不收錄任何台詞全文。

## 執行

```powershell
# Easy (Windows): double-click launch.bat
# Or manually in 3 terminals:
cd server && .venv\Scripts\python.exe main.py
cd frontend && npm run dev
cd frontend && npm run electron:dev
```

需要調整視窗預設大小時，可在啟動 Electron 前設定：

```powershell
$env:WIDGET_WIDTH=320
$env:WIDGET_HEIGHT=460
npm run electron:dev
```

## 自訂設定

齒輪面板提供這些選項：

- **Zoom** 0.5×–2.0× — 調整角色尺寸。
- **Resolution** 1×–4× — Pixi super-sampling，讓邊緣更銳利。
- **FPS** 15/30/60/120。
- **Always on top** — 切換視窗置頂。
- **Hair physics** — 切換髮絲物理；部分 Emilia 造型若抖動可關閉。
- **Voice on tap** — 點擊角色時是否播放語音。
- **Subtitle** — 點擊時是否顯示字幕。
- **Volume** 0–100。

## 疑難排解

- 角色跑到角落看不到：重新載入，或關掉 widget 後重開。這通常是 HMR 邊界情況。
- 髮絲還是抖：把 Resolution 拉到 3× 或 4×；其他造型可試著關閉 Hair physics。
- 沒聲音：先執行 `setup-emilia-voices.ps1`；`ffmpeg` 是必要工具。

## 架構

- Frontend：Vue 3 + PixiJS + `pixi-live2d-display`，包在 Electron 透明無框視窗中。
- Backend：精簡 FastAPI，tail `~/.codex/sessions` 與 `~/.claude/projects` JSONL 檔案，並代理 Anthropic OAuth `/usage` 查詢。
- WebSocket `session_state` stream 提供即時狀態更新。
- 100% 本機運作；除了 Claude OAuth 配額查詢外，不依賴外部服務。

## Credits & licensing

本專案**衍生自** [Dylin-code/agents-stage-live2d-vrm3d](https://github.com/Dylin-code/agents-stage-live2d-vrm3d)。全部 session-bridge 架構、Claude OAuth usage proxy 與核心 session 監看想法，都是原作者的工作；此 fork 將範圍收斂成單一 Windows 桌面 widget。

Live2D 角色資源 © 雷瑟莉雅、Re:Zero -Starting Life in Another World- Lost in Memories 各權利方，僅供個人非商業使用。本 repo 不提交角色模型或語音素材，所有資源都必須由使用者自行提供或本機產生。

`pixi-live2d-display`、PixiJS、Vue、Electron、FastAPI 與其他第三方套件保留各自的 MIT、MPL 或原授權條款。選用語音 clips 由使用者提供公開來源並在本機產生，僅供個人使用。

## License

MIT，見 [LICENSE](./LICENSE)。
