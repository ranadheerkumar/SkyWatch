param(
    [switch]$SkipAutoSync
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $root "backend"
$frontendPath = Join-Path $root "frontend"
$pidFile = Join-Path $root ".local-dev-pids.json"
$syncPidFile = Join-Path $root ".local-sync-pid.json"

function Get-ChildProcessIds {
    param(
        [int]$ParentProcessId
    )

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentProcessId" -ErrorAction SilentlyContinue
    if (-not $children) {
        return @()
    }

    $descendants = @()
    foreach ($child in $children) {
        $childId = [int]$child.ProcessId
        $descendants += $childId
        $descendants += Get-ChildProcessIds -ParentProcessId $childId
    }
    return $descendants
}

function Stop-ProcessTree {
    param(
        [int]$TargetProcessId
    )

    try {
        Get-Process -Id $TargetProcessId -ErrorAction Stop | Out-Null
    } catch {
        Write-Output "Process $TargetProcessId is not running."
        return
    }

    $childIds = @(Get-ChildProcessIds -ParentProcessId $TargetProcessId | Sort-Object -Unique)
    foreach ($childId in ($childIds | Sort-Object -Descending)) {
        try {
            Stop-Process -Id $childId -ErrorAction Stop
            Write-Output "Stopped child process $childId"
        } catch {
            # Child may have exited between discovery and stop call.
        }
    }

    try {
        Stop-Process -Id $TargetProcessId -ErrorAction Stop
        Write-Output "Stopped process $TargetProcessId"
    } catch {
        Write-Output "Process $TargetProcessId is not running."
    }
}

function Get-RepoScopedProcessIds {
    param(
        [switch]$IncludeAutoSync
    )

    $matches = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $commandLine = [string]$_.CommandLine
        if (-not $commandLine) {
            return $false
        }
        $isBackendScoped = $commandLine -like "*$backendPath*"
        $isFrontendScoped = $commandLine -like "*$frontendPath*"

        $isBackend = $isBackendScoped -and $commandLine -match "uvicorn\s+app\.main:app"
        $isNextDev = $isFrontendScoped -and $commandLine -match "\sdev(\s|$)"
        $isNextServer = $isFrontendScoped -and $commandLine -match "next\\dist\\server\\lib\\start-server\.js"
        $isNpmDev = $isFrontendScoped -and $commandLine -match "npm(\.cmd)?\s+run\s+dev(:clean)?"
        $isAutoSync = ($commandLine -like "*$PSScriptRoot*") -and $commandLine -match "sync-restart-local\.ps1"

        return ($isBackend -or $isNextDev -or $isNextServer -or $isNpmDev -or ($IncludeAutoSync -and $isAutoSync))
    }
    return @($matches | ForEach-Object { [int]$_.ProcessId } | Sort-Object -Unique)
}

$processIds = @()
if (Test-Path $pidFile) {
    $data = Get-Content -Path $pidFile -Raw | ConvertFrom-Json
    $processIds += @($data.backendPid, $data.frontendPid) | Where-Object { $_ } | ForEach-Object { [int]$_ }
} else {
    Write-Output "No PID file found. Attempting repository-scoped cleanup."
}

if (-not $SkipAutoSync -and (Test-Path $syncPidFile)) {
    $syncData = Get-Content -Path $syncPidFile -Raw | ConvertFrom-Json
    if ($syncData.syncPid) {
        $processIds += [int]$syncData.syncPid
    }
}

if ($SkipAutoSync) {
    $processIds += Get-RepoScopedProcessIds
} else {
    $processIds += Get-RepoScopedProcessIds -IncludeAutoSync
}
$processIds = @($processIds | Sort-Object -Unique)

if (-not $processIds -or $processIds.Count -eq 0) {
    if (Test-Path $pidFile) {
        Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
    }
    if (-not $SkipAutoSync -and (Test-Path $syncPidFile)) {
        Remove-Item -Path $syncPidFile -ErrorAction SilentlyContinue
    }
    Write-Output "No matching local dev processes found."
    exit 0
}

foreach ($processIdToStop in $processIds) {
    Stop-ProcessTree -TargetProcessId $processIdToStop
}

Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
if (-not $SkipAutoSync) {
    Remove-Item -Path $syncPidFile -ErrorAction SilentlyContinue
}
Write-Output "Local dev processes cleanup complete."
