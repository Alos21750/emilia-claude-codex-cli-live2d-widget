# Copies Emilia Live2D variants from local ReZero LiM source to widget public assets.
# Always refreshes each destination folder; idempotent re-runs are safe.
# Run from the agents-stage-live2d-vrm3d-fe directory or repo root.

[CmdletBinding()]
param(
    [string]$Source
)

$ErrorActionPreference = 'Stop'

if (-not $Source) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $live2dParent = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..\..')).Path
    $Source = Join-Path $live2dParent 'ReZero LiM Live2D Characters\Live2D Characters'
}

$variants = @(
    'ac_base_emilia01',
    'ac_base_emilia02',
    'ac_base_emilia_dress01',
    'ac_base_emilia_hood01',
    'ac_base_emilia_mizugi01',
    'ac_base_emilia_nemaki01',
    'ac_base_emilia_nemaki02',
    'ac_base_emilia_nemaki03',
    'ac_base_emilia_wedding01',
    'ac_base_emilia_xmas01'
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path -Path $scriptDir -ChildPath '..\public\assets\models\rezero'

if (-not (Test-Path -LiteralPath $Source)) {
    Write-Error "Source folder not found: $Source"
    exit 1
}

if (-not (Test-Path -LiteralPath $dest)) {
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
}

$dest = (Resolve-Path -LiteralPath $dest).Path

foreach ($name in $variants) {
    $srcDir = Join-Path -Path $Source -ChildPath $name
    $dstDir = Join-Path -Path $dest -ChildPath $name
    if (-not (Test-Path -LiteralPath $srcDir)) {
        Write-Error "Source variant missing: $srcDir"
        exit 1
    }
    Write-Host "Copying $name ..."
    if (Test-Path -LiteralPath $dstDir) {
        Remove-Item -LiteralPath $dstDir -Recurse -Force
    }
    Copy-Item -LiteralPath $srcDir -Destination $dstDir -Recurse -Force
}

Write-Host "Done. Copied $($variants.Count) Emilia variants to $dest"
