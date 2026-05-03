param(
  [string]$VideoUrl = "https://www.youtube.com/watch?v=pXa59EFppv8"
)

$ErrorActionPreference = "Stop"

function Test-Tool {
  param([string]$Name)
  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Tool "uvx")) {
  Write-Host "Missing uvx. Install uv first:"
  Write-Host "  winget install astral-sh.uv"
  Write-Host "  irm https://astral.sh/uv/install.ps1 | iex"
  exit 1
}

if (-not (Test-Tool "ffmpeg")) {
  Write-Host "Missing ffmpeg. Install it first:"
  Write-Host "  winget install ffmpeg"
  exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $scriptDir "emilia-voices.json"
$voicesDir = Join-Path $scriptDir "..\public\assets\voices"
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "emilia-widget-voices"
$rawTemplate = Join-Path $tempDir "emilia_raw.%(ext)s"
$rawWav = Join-Path $tempDir "emilia_raw.wav"
$finalEndSeconds = 252.0
$culture = [System.Globalization.CultureInfo]::InvariantCulture

if (-not (Test-Path $manifestPath)) {
  throw "Voice manifest not found: $manifestPath"
}

$voicesRaw = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
$voices = if ($voicesRaw -is [array]) { $voicesRaw } else { @($voicesRaw) }
New-Item -ItemType Directory -Force -Path $voicesDir | Out-Null
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

$expectedFiles = @()
foreach ($voice in $voices) {
  $filename = "{0:D3}_{1}.m4a" -f [int]$voice.n, [string]$voice.slug
  $expectedFiles += (Join-Path $voicesDir $filename)
}

$missingFiles = @($expectedFiles | Where-Object { -not (Test-Path $_) })
if ($missingFiles.Count -eq 0 -and $expectedFiles.Count -eq 51) {
  Write-Host "All 51 Emilia voice clips already exist in $voicesDir"
  exit 0
}

try {
  if (Test-Path $rawWav) {
    Remove-Item -LiteralPath $rawWav -Force
  }

  Write-Host "Downloading source audio..."
  & uvx --from yt-dlp yt-dlp --no-playlist -x --audio-format wav -o $rawTemplate $VideoUrl
  if ($LASTEXITCODE -ne 0) {
    throw "yt-dlp failed with exit code $LASTEXITCODE"
  }
  if (-not (Test-Path $rawWav)) {
    throw "yt-dlp did not create expected WAV: $rawWav"
  }

  Write-Host "Splitting clips..."
  for ($i = 0; $i -lt $voices.Count; $i++) {
    $voice = $voices[$i]
    $start = [double]$voice.start
    if ($i -lt ($voices.Count - 1)) {
      $end = [double]$voices[$i + 1].start - 0.1
    } else {
      $end = $finalEndSeconds
    }
    $duration = [Math]::Max(0.5, $end - $start)
    $filename = "{0:D3}_{1}.m4a" -f [int]$voice.n, [string]$voice.slug
    $outputPath = Join-Path $voicesDir $filename
    $startArg = $start.ToString("0.###", $culture)
    $durationArg = $duration.ToString("0.###", $culture)

    & ffmpeg -hide_banner -loglevel error -y -ss $startArg -t $durationArg -i $rawWav -vn -af loudnorm=I=-14:TP=-1.5:LRA=11 -codec:a aac -b:a 128k $outputPath
    if ($LASTEXITCODE -ne 0) {
      throw "ffmpeg failed while writing $filename"
    }
  }

  Write-Host "Wrote $($voices.Count) Emilia voice clips to $voicesDir"
} finally {
  if (Test-Path $rawWav) {
    Remove-Item -LiteralPath $rawWav -Force -ErrorAction SilentlyContinue
  }
}
