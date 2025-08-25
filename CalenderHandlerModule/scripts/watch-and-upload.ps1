param(
    [string]$FilePath = "D:\\Code Files\\echoAgentsProject\\input.wav",
    [string]$ConfirmPath = "D:\\Code Files\\echoAgentsProject\\confirm.wav",
    [string]$DialogUrl = "http://localhost:8004/voice/dialog",
    [string]$ReplyOut = "D:\\Code Files\\echoAgentsProject\\echoagents_reply.wav",
    [switch]$ProcessExisting
)

Write-Host "Watching: $FilePath and $ConfirmPath"
$fsw = New-Object IO.FileSystemWatcher (Split-Path $FilePath), (Split-Path $FilePath -Leaf)
$fsw.IncludeSubdirectories = $false
$fsw.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, Size'
$fsw.EnableRaisingEvents = $true

# Separate watcher for confirmation file
$fsw2 = New-Object IO.FileSystemWatcher (Split-Path $ConfirmPath), (Split-Path $ConfirmPath -Leaf)
$fsw2.IncludeSubdirectories = $false
$fsw2.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite, Size'
$fsw2.EnableRaisingEvents = $true

$ConfirmUrl = $DialogUrl.Replace('/voice/dialog','/voice/confirm/audio')

function Get-ContentType([string]$path) {
    $ext = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
    switch ($ext) {
        '.wav' { return 'audio/wav' }
        '.mp3' { return 'audio/mpeg' }
        '.m4a' { return 'audio/mp4' }
        '.mp4' { return 'audio/mp4' }
        '.ogg' { return 'audio/ogg' }
        '.webm' { return 'audio/webm' }
        default { return 'audio/wav' }
    }
}

function Process-File([string]$path) {
    if (-not (Test-Path $path)) { return }
    # Debounce: avoid reprocessing identical writes
    $fi = Get-Item $path
    $key = $fi.FullName.ToLowerInvariant()
    if (-not $script:lastSeen) { $script:lastSeen = @{} }
    $sig = @($fi.Length, $fi.LastWriteTimeUtc.Ticks) -join ':'
    if ($script:lastSeen.ContainsKey($key) -and $script:lastSeen[$key] -eq $sig) { return }
    $script:lastSeen[$key] = $sig

    Write-Host "Detected update: $path"
    $ctype = Get-ContentType $path
    $formFile = "file=@$path;type=$ctype"
    $tmpOut = [System.IO.Path]::GetTempFileName().Replace('.tmp', '.wav')
    # If reply file is recent, treat as confirmation
    $recentReply = $false
    if (Test-Path $ReplyOut) {
        $age = (Get-Item $ReplyOut).LastWriteTimeUtc
        if ((Get-Date).ToUniversalTime().Subtract($age).TotalSeconds -lt 120) { $recentReply = $true }
    }
    # If this path is the dedicated confirmation file, force confirm
    if ($path -ieq $ConfirmPath) {
        & curl.exe -s -X POST -F $formFile $ConfirmUrl -o $tmpOut
    }
    elseif ($recentReply) {
        & curl.exe -s -X POST -F $formFile $ConfirmUrl -o $tmpOut
    } else {
        & curl.exe -s -X POST -F $formFile $DialogUrl -o $tmpOut
    }
    if (Test-Path $tmpOut) {
        Copy-Item $tmpOut $ReplyOut -Force
        Remove-Item $tmpOut -Force
        Write-Host "Saved voice reply to: $ReplyOut"
    }
}

$action = {
    param($source, $eventArgs)
    Start-Sleep -Milliseconds 300
    try {
        if ($null -ne $eventArgs -and $eventArgs.FullPath) {
            Process-File $eventArgs.FullPath
        }
    } catch {
        Write-Warning $_
    }
}

Register-ObjectEvent $fsw Changed -Action $action | Out-Null
Register-ObjectEvent $fsw Created -Action $action | Out-Null
Register-ObjectEvent $fsw Renamed -Action $action | Out-Null
Register-ObjectEvent $fsw2 Changed -Action $action | Out-Null
Register-ObjectEvent $fsw2 Created -Action $action | Out-Null
Register-ObjectEvent $fsw2 Renamed -Action $action | Out-Null

Write-Host "Press Ctrl+C to stop."
# Process existing file once on startup only if requested
if ($ProcessExisting.IsPresent -and (Test-Path $FilePath)) {
    Write-Host "Found existing file. Processing once..."
    Process-File $FilePath
}
while ($true) { Start-Sleep -Seconds 1 }
