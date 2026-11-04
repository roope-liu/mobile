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

$server = Start-Process -FilePath $python -ArgumentList "`"$PSScriptRoot\stream_server.py`"" -PassThru -WindowStyle Hidden
try {
    Write-Host "流代理已启动：http://127.0.0.1:$Port"
    Write-Host "接下来会输出一个 https://xxx.loca.lt 的隧道地址，把它填入 APP 的‘播放代理地址’。"
    npx --yes localtunnel --port $Port
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
    }
}
