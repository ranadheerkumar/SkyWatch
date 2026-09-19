param(
    [int]$FrontendPort = 3002,
    [int]$BackendPort = 8000,
    [ValidateRange(1, 1440)]
    [int]$IntervalMinutes = 30,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $PSScriptRoot "start-local.ps1"
$stopScript = Join-Path $PSScriptRoot "stop-local.ps1"
$syncPidFile = Join-Path $root ".local-sync-pid.json"
$logFile = Join-Path $root ".local-sync.log"
$sourceBranch = "AutomationTool_POC"
$targetBranch = "AutomationTool_POC_lkurra"

function Write-SyncLog {
    param(
        [string]$Message
    )

    $line = "[{0}] {1}" -f (Get-Date).ToString("o"), $Message
    Add-Content -Path $logFile -Value $line
}

function Invoke-Git {
    param(
        [string[]]$Arguments
    )

    $output = @(& git -C $root @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $details = ($output | ForEach-Object { $_.ToString() }) -join " "
        throw "git $($Arguments -join ' ') failed with exit code $exitCode. $details"
    }
    return $output
}

function Get-GitText {
    param(
        [string[]]$Arguments
    )

    $output = @(Invoke-Git -Arguments $Arguments)
    return (($output | ForEach-Object { $_.ToString() }) -join "`n").Trim()
}

function Get-WorkingTreeChanges {
    return @(Invoke-Git -Arguments @("status", "--porcelain", "--untracked-files=all") | Where-Object {
        $_ -and $_.ToString().Trim().Length -gt 0
    })
}

function Sync-Repository {
    $currentBranch = Get-GitText -Arguments @("branch", "--show-current")
    if ($currentBranch -ne $targetBranch) {
        throw "Automatic sync requires branch '$targetBranch'; current branch is '$currentBranch'."
    }

    try {
        Invoke-Git -Arguments @("fetch", "origin", $sourceBranch) | Out-Null
    } catch {
        Write-SyncLog "Fetch failed; services were not restarted. The worker will retry next cycle. $($_.Exception.Message)"
        return $false
    }

    $incomingCount = [int](Get-GitText -Arguments @("rev-list", "--count", "HEAD..origin/$sourceBranch"))
    if ($incomingCount -eq 0) {
        Write-SyncLog "No incoming commits from origin/$sourceBranch."
        return $true
    }

    $changes = @(Get-WorkingTreeChanges)
    $untrackedChanges = @($changes | Where-Object { $_.ToString().StartsWith("?? ") })
    if ($untrackedChanges.Count -gt 0) {
        $details = ($untrackedChanges | ForEach-Object { $_.ToString() }) -join "; "
        throw "Automatic sync stopped because untracked files require manual handling: $details"
    }

    $stashCreated = $false
    $mergeCompleted = $false
    try {
        if ($changes.Count -gt 0) {
            Invoke-Git -Arguments @("stash", "push", "-m", "automatic sync before merging $sourceBranch") | Out-Null
            $stashCreated = $true
            Write-SyncLog "Stashed $($changes.Count) local change(s) before merging upstream."
        }

        Invoke-Git -Arguments @("merge", "--no-edit", "origin/$sourceBranch") | Out-Null
        $mergeCompleted = $true

        if ($stashCreated) {
            Invoke-Git -Arguments @("stash", "pop") | Out-Null
            $stashCreated = $false
            Write-SyncLog "Restored local changes after merging upstream."
        }
    } catch {
        if (-not $mergeCompleted) {
            try {
                Invoke-Git -Arguments @("merge", "--abort") | Out-Null
            } catch {
                Write-SyncLog "Unable to abort the failed merge cleanly. $($_.Exception.Message)"
            }
        }

        if ($stashCreated -and -not $mergeCompleted) {
            try {
                Invoke-Git -Arguments @("stash", "pop") | Out-Null
                $stashCreated = $false
                Write-SyncLog "Restored local changes after aborting the upstream merge."
            } catch {
                Write-SyncLog "Unable to restore the local stash automatically. Manual recovery is required. $($_.Exception.Message)"
            }
        } elseif ($stashCreated -and $mergeCompleted) {
            Write-SyncLog "The upstream merge completed, but restoring local changes requires manual conflict resolution."
        }

        throw
    }

    Write-SyncLog "Merged $incomingCount incoming commit(s) from origin/$sourceBranch."
    return $true
}

function Invoke-LocalScript {
    param(
        [string]$Path,
        [string[]]$Arguments
    )

    $output = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Path @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    foreach ($line in $output) {
        Write-SyncLog $line.ToString()
    }
    if ($exitCode -ne 0) {
        throw "$Path failed with exit code $exitCode."
    }
}

if ($DryRun) {
    Write-Output "Would fetch origin/$sourceBranch and merge it into $targetBranch."
    Write-Output "Would restart backend on port $BackendPort and frontend on port $FrontendPort every $IntervalMinutes minute(s)."
    exit 0
}

$syncPayload = @{
    syncPid = $PID
    intervalMinutes = $IntervalMinutes
    startedAt = (Get-Date).ToString("o")
} | ConvertTo-Json
Set-Content -Path $syncPidFile -Value $syncPayload
Write-SyncLog "Auto-sync worker started for $targetBranch; interval is $IntervalMinutes minute(s)."

try {
    while ($true) {
        Start-Sleep -Seconds ($IntervalMinutes * 60)
        Write-SyncLog "Starting scheduled synchronization cycle."

        if (-not (Sync-Repository)) {
            continue
        }

        Invoke-LocalScript -Path $stopScript -Arguments @("-SkipAutoSync")
        Invoke-LocalScript -Path $startScript -Arguments @(
            "-FrontendPort", $FrontendPort.ToString(),
            "-BackendPort", $BackendPort.ToString(),
            "-DisableAutoSync"
        )
        Write-SyncLog "Scheduled synchronization cycle completed; services restarted."
    }
} catch {
    Write-SyncLog "Auto-sync worker stopped because of an unrecoverable error. $($_.Exception.Message)"
    exit 1
} finally {
    if (Test-Path $syncPidFile) {
        $currentSyncData = Get-Content -Path $syncPidFile -Raw | ConvertFrom-Json
        if ([int]$currentSyncData.syncPid -eq $PID) {
            Remove-Item -Path $syncPidFile -ErrorAction SilentlyContinue
        }
    }
}
