param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

Write-Host "Starting timeline on port $Port..."

cd "$PSScriptRoot\..\services\timeline"
if (Test-Path requirements.txt) {
    ..\..\..\venv311\Scripts\pip.exe install -r requirements.txt | Write-Host
}
..\..\..\venv311\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port $Port
