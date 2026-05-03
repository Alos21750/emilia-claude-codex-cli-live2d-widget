[繁體中文](README.md) · [English](README.en.md) · **日本語**

# ✨ Emilia Claude / Codex Live2D ウィジェット

Claude Code と Codex の作業状況を、画面の隅で見守る Live2D デスクトップペットです。

<p align="center">
  <img src="docs/images/widget-bubbles.png" alt="Emilia Live2D デスクトップウィジェットのメイン画面" width="280">
</p>

<p align="center">
  <strong>Windows · Electron 30 · Vue 3 · FastAPI</strong>
</p>

## 特長

- 🎀 10 種類の Emilia 衣装バリエーションを選べる character picker。
- 😊 キャラクターをクリックすると表情モーションとランダムなボイスを再生。
- 🖱️ キャラクターを押したままドラッグして、デスクトップの好きな場所へ移動。
- 📊 Codex / Claude のクォータをリアルタイム表示：Claude 5h/7d、Codex P/S。
- ⚙️ zoom、resolution、FPS、最前面表示、髪の物理、字幕、音量を調整可能。
- 🪟 透明・フレームレス・Always-on-top の Electron ウィジェット。
- 🔌 Claude Code と Codex CLI の session をローカルで監視し、ホスト型バックエンドは不要。

## スクリーンショット

<p align="center">
  <img src="docs/images/widget-bubbles.png" alt="Emilia、クォータ吹き出し、フッター chip があるメイン画面" width="360">
</p>

メイン画面では Emilia Live2D、Claude / Codex のクォータ吹き出し、下部のステータス chip を表示します。この画像は README 用の参考スクリーンショットで、あとから新しいものに差し替えられます。

<p align="center">
  <img src="docs/images/widget-old.png" alt="旧版ウィジェット画面の参考画像" width="360">
</p>

旧版の画面は、吹き出しの配置、キャラクター位置、透明ウィンドウの見え方を比較するための参考として残しています。

## セットアップ

事前に必要なもの：Node.js 20+、[uv](https://astral.sh/uv)、PowerShell 5+。デフォルトの Hiyori サンプルモデルは repo に含まれます。Emilia を使う場合は、自分で展開した Re:Zero LiM の Live2D キャラクターファイルを用意してください。

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

# 4) Optional Emilia assets — needs YOUR copy of the ReZero LiM Live2D files
cd ../frontend
pwsh ./scripts/setup-emilia-models.ps1 -Source "<path to ReZero LiM Live2D Characters\Live2D Characters>"
```

## 任意：ボイス clips

ボイス clips はローカルで生成する任意素材です。セットアップスクリプトは `uvx` 経由で必要なときだけ `yt-dlp` を実行するため、`yt-dlp` のグローバルインストールは不要です。ボイスには著作権があります。個人・非商用の範囲でのみ使用してください。

```powershell
winget install ffmpeg
# uv supplies yt-dlp on demand (winget install astral-sh.uv if you don't have it yet)
cd frontend
pwsh ./scripts/setup-emilia-voices.ps1
```

生成されるのは、よく使う感情やインタラクション向けの短い clips 51 個です。この README には台詞の全文は掲載していません。

## 起動

```powershell
# Easy (Windows): double-click launch.bat
# Or manually in 3 terminals:
cd server && .venv\Scripts\python.exe main.py
cd frontend && npm run dev
cd frontend && npm run electron:dev
```

ウィンドウの初期サイズを変えたい場合は、Electron を起動する前に次の環境変数を設定します。

```powershell
$env:WIDGET_WIDTH=320
$env:WIDGET_HEIGHT=460
npm run electron:dev
```

## カスタマイズ

歯車パネルでは以下を設定できます。

- **Zoom** 0.5×–2.0× — キャラクターのサイズ。
- **Resolution** 1×–4× — Pixi の super-sampling。輪郭をよりシャープにします。
- **FPS** 15/30/60/120。
- **Always on top** — ウィンドウの最前面表示を切り替え。
- **Hair physics** — 髪の物理を切り替え。一部の Emilia 衣装で揺れが気になる場合はオフにできます。
- **Voice on tap** — クリック時のボイス再生を切り替え。
- **Subtitle** — クリック時に字幕を表示。
- **Volume** 0–100。

## トラブルシューティング

- キャラクターが隅に寄って見えない：リロードするか、ウィジェットを閉じて開き直してください。多くの場合は HMR の境界ケースです。
- 髪の揺れがまだ気になる：Resolution を 3× または 4× に上げるか、衣装によっては Hair physics をオフにしてください。
- 音が出ない：`setup-emilia-voices.ps1` を実行してください。`ffmpeg` が必要です。

## アーキテクチャ

- Frontend：Vue 3 + PixiJS + `pixi-live2d-display` を、透明・フレームレスの Electron ウィンドウ内で実行。
- Backend：軽量な FastAPI。`~/.codex/sessions` と `~/.claude/projects` の JSONL ファイルを tail し、Anthropic OAuth `/usage` を proxy します。
- WebSocket の `session_state` stream でリアルタイム更新。
- Claude OAuth のクォータ取得以外は 100% ローカルで動作し、外部サービスに依存しません。

## Credits & licensing

このプロジェクトは [Dylin-code/agents-stage-live2d-vrm3d](https://github.com/Dylin-code/agents-stage-live2d-vrm3d) から**派生**しています。session-bridge アーキテクチャ、Claude OAuth usage proxy、session 監視の中核アイデアはすべて原作者の仕事です。この fork では、単一の Windows デスクトップウィジェットに範囲を絞っています。

Live2D キャラクター素材は © 雷瑟莉雅、Re:Zero -Starting Life in Another World- Lost in Memories、および各権利者に帰属します。利用は個人・非商用に限られます。この repo にはキャラクターモデルやボイス素材を含めていません。ユーザー自身がローカルで用意または生成してください。

デフォルトの Hiyori サンプルモデルは Live2D Inc. によるもので、[Free Material License Agreement](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html) および [Terms of Use for Live2D Cubism Sample Data](https://www.live2d.com/eula/live2d-sample-model-terms_en.html) に従って使用しています。

`pixi-live2d-display`、PixiJS、Vue、Electron、FastAPI、その他の第三者パッケージは、それぞれの MIT、MPL、その他のライセンスに従います。任意のボイス clips は、ユーザーが公開ソースから用意してローカル生成するもので、個人利用のみを想定しています。

## License

MIT。詳細は [LICENSE](./LICENSE) を参照してください。
