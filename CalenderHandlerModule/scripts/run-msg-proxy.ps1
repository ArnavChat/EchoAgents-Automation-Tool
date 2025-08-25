param(
    [int]$Port = 8001
)

$ErrorActionPreference = 'Stop'

Write-Host "Starting msg-proxy on port $Port..."

cd "$PSScriptRoot\..\services\msg-proxy"
if (Test-Path requirements.txt) {
    ..\..\..\venv311\Scripts\pip.exe install -r requirements.txt | Write-Host
}
..\..\..\venv311\Scripts\uvicorn.exe app:app --host 0.0.0.0 --port $Port
