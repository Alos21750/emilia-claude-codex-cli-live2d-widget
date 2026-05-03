[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$hiyori = Join-Path $root 'frontend\public\assets\models\free\hiyori\Hiyori.model3.json'

if (-not (Test-Path -LiteralPath $hiyori)) {
    Write-Error "Hiyori model missing: $hiyori"
    exit 1
}

if (-not $SkipBackend) {
    Write-Host 'Building backend.exe via PyInstaller...'
    Push-Location (Join-Path $root 'server')
    try {
        & uvx --from pyinstaller pyinstaller `
            --onefile `
            --name widget-backend `
            --hidden-import widget_server.api `
            --hidden-import widget_server.monitor `
            --hidden-import widget_server.codex_jsonl `
            --hidden-import widget_server.claude_jsonl `
            --hidden-import widget_server.state `
            --hidden-import widget_server.ws `
            --hidden-import widget_server.claude_usage `
            main.py
        if ($LASTEXITCODE -ne 0) {
            throw 'PyInstaller failed'
        }
    } finally {
        Pop-Location
    }
}

if (-not $SkipFrontend) {
    Write-Host 'Building Vue + Electron portable...'
    Push-Location (Join-Path $root 'frontend')
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) {
            throw 'Vite build failed'
        }

        & npm run build:exe
        if ($LASTEXITCODE -ne 0) {
            throw 'electron-builder failed'
        }
    } finally {
        Pop-Location
    }
}

Write-Host 'Done. Artifact in frontend/release/EmiliaWidget-portable.exe'
