param(
    [int]$Port = 8003
)

$ErrorActionPreference = 'Stop'

Write-Host "Starting voice-agent on port $Port..."

cd "$PSScriptRoot\..\services\voice-agent"
if (Test-Path requirements.txt) {
    ..\..\..\venv311\Scripts\pip.exe install -r requirements.txt | Write-Host
}
if (-not $env:MSG_PROXY_WEBHOOK_URL) {
    # Default to local msg-proxy 'voice' webhook
    $env:MSG_PROXY_WEBHOOK_URL = "http://localhost:8001/webhook/voice"
}
..\..\..\venv311\Scripts\uvicorn.exe server:app --host 0.0.0.0 --port $Port
