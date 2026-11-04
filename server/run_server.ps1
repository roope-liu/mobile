param(
    [int]$Port = 8000,
    [string]$FfmpegPath = ""
)

$root = Split-Path -Parent $PSScriptRoot
if (-not $FfmpegPath) {
    $FfmpegPath = Join-Path (Split-Path -Parent $root) "ffmpeg\ffmpeg.exe"
}

$env:PORT = "$Port"
$env:FFMPEG_PATH = $FfmpegPath
$env:STREAM_CACHE_DIR = Join-Path $PSScriptRoot "cache"

$python = Join-Path (Split-Path -Parent $root) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host "流代理启动：http://0.0.0.0:$Port"
& $python "$PSScriptRoot\stream_server.py"
