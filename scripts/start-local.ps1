param(
    [int]$FrontendPort = 3002,
    [int]$BackendPort = 8000,
    [ValidateRange(1, 1440)]
    [int]$SyncIntervalMinutes = 30,
    [switch]$DisableAutoSync,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $root "backend"
$frontendPath = Join-Path $root "frontend"
$backendPython = Join-Path $backendPath ".venv\Scripts\python.exe"
$pidFile = Join-Path $root ".local-dev-pids.json"
$syncScript = Join-Path $PSScriptRoot "sync-restart-local.ps1"
$syncPidFile = Join-Path $root ".local-sync-pid.json"

if (!(Test-Path $backendPython)) {
    throw "Backend Python not found at $backendPython. Create backend venv first."
}

if (-not $DisableAutoSync -and !(Test-Path $syncScript)) {
    throw "Auto-sync script not found at $syncScript."
}

$backendArgs = @(
    "-NoExit",
    "-Command",
    "Set-Location `"$backendPath`"; [Environment]::SetEnvironmentVariable('PYTHONPATH', '$backendPath', 'Process'); & `"$backendPython`" -m app.core.migration_bootstrap; & `"$backendPython`" -m uvicorn app.main:app --app-dir `"$backendPath`" --host 127.0.0.1 --port $BackendPort"
)

$frontendArgs = @(
    "-NoExit",
    "-Command",
    "Set-Location '$frontendPath'; npm run clean:next; npx next dev -H 127.0.0.1 -p $FrontendPort"
)

$syncArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $syncScript,
    "-FrontendPort",
    $FrontendPort.ToString(),
    "-BackendPort",
    $BackendPort.ToString(),
    "-IntervalMinutes",
    $SyncIntervalMinutes.ToString()
)

if ($DryRun) {
    Write-Output "Backend command:"
    Write-Output "powershell $($backendArgs -join ' ')"
    Write-Output ""
    Write-Output "Frontend command:"
    Write-Output "powershell $($frontendArgs -join ' ')"
    if (-not $DisableAutoSync) {
        Write-Output ""
        Write-Output "Auto-sync command (every $SyncIntervalMinutes minute(s)):"
        Write-Output "powershell $($syncArgs -join ' ')"
    }
    exit 0
}

$backendProcess = Start-Process -FilePath "powershell" -ArgumentList $backendArgs -PassThru
$frontendProcess = Start-Process -FilePath "powershell" -ArgumentList $frontendArgs -PassThru

$payload = @{
    backendPid = $backendProcess.Id
    frontendPid = $frontendProcess.Id
    startedAt = (Get-Date).ToString("o")
} | ConvertTo-Json

Set-Content -Path $pidFile -Value $payload

$syncProcess = $null
if (-not $DisableAutoSync) {
    try {
        $syncProcess = Start-Process -FilePath "powershell" -ArgumentList $syncArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru
        $syncPayload = @{
            syncPid = $syncProcess.Id
            intervalMinutes = $SyncIntervalMinutes
            startedAt = (Get-Date).ToString("o")
        } | ConvertTo-Json
        Set-Content -Path $syncPidFile -Value $syncPayload
    } catch {
        if ($syncProcess) {
            Stop-Process -Id $syncProcess.Id -ErrorAction SilentlyContinue
        }
        $stopScript = Join-Path $PSScriptRoot "stop-local.ps1"
        $cleanupArgs = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $stopScript,
            "-SkipAutoSync"
        )
        $cleanupProcess = Start-Process -FilePath "powershell" -ArgumentList $cleanupArgs -WorkingDirectory $root -Wait -PassThru -WindowStyle Hidden
        if ($cleanupProcess.ExitCode -ne 0) {
            Write-Output "Automatic cleanup after sync startup failure returned exit code $($cleanupProcess.ExitCode)."
        }
        throw
    }
}

Write-Output "Local dev started."
Write-Output "Backend URL: http://127.0.0.1:$BackendPort (PID: $($backendProcess.Id))"
Write-Output "Frontend URL: http://127.0.0.1:$FrontendPort (PID: $($frontendProcess.Id))"
if ($DisableAutoSync) {
    Write-Output "Automatic sync/restart: disabled for this start."
} else {
    Write-Output "Automatic sync/restart: every $SyncIntervalMinutes minute(s) (PID: $($syncProcess.Id))"
}
Write-Output "To stop both, run: .\scripts\stop-local.ps1"
