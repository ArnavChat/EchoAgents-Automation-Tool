param(
    [int]$MsgProxyPort     = 8001,
    [int]$OrchestratorPort = 8002,
    [int]$TimelinePort     = 8000,
    [int]$VoiceAgentPort   = 8003
)

$ErrorActionPreference = 'Stop'

Write-Host "Starting all services..."

# Load root .env if present (basic parser: KEY=VALUE, ignores comments)
$rootEnv = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path '.env'
if (Test-Path $rootEnv) {
    Write-Host "Loading environment variables from $rootEnv" -ForegroundColor Cyan
    Get-Content $rootEnv | ForEach-Object {
        if ($_ -match '^[#;]') { return }
        if ($_ -match '^\s*$') { return }
        if ($_ -match '^(?<k>[A-Za-z_][A-Za-z0-9_]*)=(?<v>.*)$') {
            $k = $Matches.k
            $v = $Matches.v.Trim()
            # Remove surrounding quotes if present
            if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Substring(1, $v.Length - 2) }
            if ($v.StartsWith("'") -and $v.EndsWith("'")) { $v = $v.Substring(1, $v.Length - 2) }
            # Only set if not already defined in current environment
            if (-not (Test-Path Env:$k)) {
                Set-Item -Path Env:$k -Value $v
            }
        }
    }
}

function Start-ServiceProcess {
    param (
        [string]$Name,
        [string]$WorkingDir,
        [string]$Command
    )
    Write-Host "Starting $Name ($WorkingDir)..."
    $wrapped = @"
Set-Location -LiteralPath '$WorkingDir'
$Command
"@
    Start-Process powershell -ArgumentList '-NoExit','-Command', $wrapped -WindowStyle Minimized
}

# Resolve venv using reliable $PSScriptRoot (PowerShell built-in) instead of Split-Path
$scriptRoot = $PSScriptRoot
$projectRoot = Resolve-Path (Join-Path $scriptRoot '..\..')

# Allow overriding venv path via -VenvPath param (optional future) or env var ECHO_VENV
$venvBase = $env:ECHO_VENV
if ([string]::IsNullOrWhiteSpace($venvBase)) {
    # Try common names in priority order
    $candidateNames = @('venv311','venv310','venv','.venv')
    foreach ($name in $candidateNames) {
        $candidate = Join-Path $projectRoot $name
        if (Test-Path (Join-Path $candidate 'Scripts')) { $venvBase = $candidate; break }
    }
}

if ([string]::IsNullOrWhiteSpace($venvBase) -or -not (Test-Path (Join-Path $venvBase 'Scripts'))) {
    Write-Host "⚠️  Could not locate a Python virtual environment automatically. Falling back to PATH tools." -ForegroundColor Yellow
    $Pip = 'pip'
    $Uvicorn = 'uvicorn'
} else {
    $scriptsDir = Join-Path $venvBase 'Scripts'
    $Pip      = Join-Path $scriptsDir 'pip.exe'
    $Uvicorn  = Join-Path $scriptsDir 'uvicorn.exe'
    Write-Host "Using virtual environment at: $venvBase" -ForegroundColor Cyan
}

function Build-RunCmd {
    param($Module, $Entry, $Port, $ExtraEnv = @{})
    $envSet = ($ExtraEnv.GetEnumerator() | ForEach-Object { "`$env:$($_.Key) = '$($_.Value)'" }) -join "`n"
    @"
Write-Host '[INIT] $Module installing deps (if needed)'
if (Test-Path requirements.txt) { & '$Pip' install --disable-pip-version-check --no-warn-script-location -r requirements.txt }
$envSet
if (-not (Get-Command '$Uvicorn' -ErrorAction SilentlyContinue)) { Write-Host 'ERROR: uvicorn not found in PATH or venv.' -ForegroundColor Red; exit 1 }
Write-Host '[RUN] $Module on port $Port'
& '$Uvicorn' $Entry --host 0.0.0.0 --port $Port
"@
}

# msg-proxy
Start-ServiceProcess -Name 'msg-proxy' `
  -WorkingDir (Resolve-Path "$scriptRoot\..\services\msg-proxy").Path `
  -Command (Build-RunCmd -Module 'msg-proxy' -Entry 'app:app' -Port $MsgProxyPort -ExtraEnv @{
        ORCHESTRATOR_URL = "http://localhost:$OrchestratorPort/handle-event"
        TIMELINE_URL     = "http://localhost:$TimelinePort/timeline/events"
    })

# orchestrator
Start-ServiceProcess -Name 'orchestrator' `
  -WorkingDir (Resolve-Path "$scriptRoot\..\services\orchestrator").Path `
  -Command (Build-RunCmd -Module 'orchestrator' -Entry 'main:app' -Port $OrchestratorPort -ExtraEnv @{
        TIMEZONE = 'Asia/Kolkata'
        TIMELINE_BASE_URL = "http://localhost:$TimelinePort"
        MSG_PROXY_BASE_URL = "http://localhost:$MsgProxyPort"
    })

# timeline (do not override DATABASE_URL if user already configured in .env; allow explicit env passthrough)
$timelineEnv = @{}
if ($env:DATABASE_URL) { $timelineEnv.DATABASE_URL = $env:DATABASE_URL }
Start-ServiceProcess -Name 'timeline' `
    -WorkingDir (Resolve-Path "$scriptRoot\..\services\timeline").Path `
    -Command (Build-RunCmd -Module 'timeline' -Entry 'main:app' -Port $TimelinePort -ExtraEnv $timelineEnv)

# voice-agent
Start-ServiceProcess -Name 'voice-agent' `
  -WorkingDir (Resolve-Path "$scriptRoot\..\services\voice-agent").Path `
  -Command (Build-RunCmd -Module 'voice-agent' -Entry 'server:app' -Port $VoiceAgentPort -ExtraEnv @{
        MSG_PROXY_WEBHOOK_URL = "http://localhost:$MsgProxyPort/webhook/voice"
    })

Write-Host "✅ All services launched."