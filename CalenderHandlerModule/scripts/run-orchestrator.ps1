param(
    [int]$Port = 8002
)

$ErrorActionPreference = 'Stop'

Write-Host "Starting orchestrator on port $Port..."

cd "$PSScriptRoot\..\services\orchestrator"

# Set your local timezone so natural language times map correctly (IANA name)
if (-not $env:TIMEZONE) {
    # Example: Asia/Kolkata; change to your zone if needed (e.g., America/Los_Angeles)
    $env:TIMEZONE = "Asia/Kolkata"
}

if (Test-Path requirements.txt) {
    & "$PSScriptRoot\..\..\venv311\Scripts\pip.exe" install -r requirements.txt | Write-Host
}

& "$PSScriptRoot\..\..\venv311\Scripts\uvicorn.exe" main:app --host 0.0.0.0 --port $Port
